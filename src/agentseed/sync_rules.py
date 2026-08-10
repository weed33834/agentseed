"""
统一规则中枢同步脚本 v2 — 实际实现位于此。

- 默认 skeleton 模式：CORE + PROFILE 主层内联，其余（skills/subagents/capabilities/MCP/templates/personas）
  走 ON-DEMAND INDEX，由 agent 按需 Read。
- --mode full：旧行为，全量内联（向后兼容）。
- 限长平台（windsurf/lingma/comate）自动多文件分片，不再"末尾贴警告"。
- persona.yaml 中声明的 templates 段会被真正装配进索引（此前是死配置）。

资源根（RESOURCES_ROOT）检测策略（让 `pip install agentseed` 也能独立工作，无需外部仓库）：
  0. AGENTSEED_REPO 环境变量（用户显式指定 AgentSeed 仓库路径，最高优先级便于改规则后立即生效）
  1. 包内打包资源（pip install agentseed 后，规则源随包分发到 agentseed/_resources/，离线可用）
  2. 包目录上一级（dev 模式：agentseed/ 在 REPO_ROOT/agentseed/，parent.parent = REPO_ROOT）
  3. 沿 cwd 祖先链查找含 personas/ 的目录
  4. 都没找到时，clone AgentSeed 到 ~/.cache/agentseed/ 并返回该路径

用法:
    python scripts/sync_rules.py --list
    python scripts/sync_rules.py --profile coding --tool claude-code
    python scripts/sync_rules.py --profile coding --tool claude-code --mode full
    python scripts/sync_rules.py --profile novel --tool all
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from . import env as _env

# ─── 资源根检测 ─────────────────────────────────────────
_AGENTSEED_REPO_URL = "https://github.com/weed33834/agentseed.git"

# 模块级缓存：避免每次 build_ruleset 都重复探查文件系统
_RESOURCES_ROOT_CACHE: Path = None
_RESOURCES_SOURCE: str = None  # 'packaged' | 'env' | 'dev' | 'cwd' | 'cache'


_PACK_DIR_NAMES = ("scenarios", "personas")  # scenarios 优先（未来规范目录），personas 兼容


def _has_pack_dir(p: Path) -> bool:
    """目录是否为 AgentSeed 资源根（含场景包目录 scenarios/ 或 personas/）。"""
    return any((p / name).is_dir() for name in _PACK_DIR_NAMES)


def _pack_dir(p: Path) -> Path:
    """返回场景包目录：scenarios/ 优先，personas/ 兼容回退。"""
    for name in _PACK_DIR_NAMES:
        cand = p / name
        if cand.is_dir():
            return cand
    return p / "personas"


def _packaged_resources_root() -> Path:
    """检查包内是否打包了规则源（pip install agentseed 后存在）。

    包内资源路径：agentseed/_resources/，由 setup.py / pyproject.toml 的 package-data 打包。
    返回该目录若存在且含场景包目录，否则返回 None。
    """
    pkg_root = Path(__file__).resolve().parent / "_resources"
    if _has_pack_dir(pkg_root) and (pkg_root / "core").is_dir():
        return pkg_root
    return None


def _find_rule_hub_root() -> Path:
    """检测 AgentSeed 资源根目录。

    优先级：
    0. AGENTSEED_REPO 环境变量（用户显式指定，最高优先级便于改规则后立即生效）
    1. 包内打包资源（pip install agentseed 后存在 agentseed/_resources/）
    2. 本文件所在目录的上一级（dev 模式：agentseed/ 在 REPO_ROOT/agentseed/）
    3. 沿 cwd 祖先链查找含场景包目录 (scenarios/ 或 personas/) + core/ 的目录
    4. clone 到 ~/.cache/agentseed/ 并返回

    注意：AGENTSEED_REPO 优先于 packaged，是为了让用户能用本地 clone 覆盖
    pip 安装的旧版本规则（开发/调试/规则自定义场景）。
    """
    global _RESOURCES_ROOT_CACHE, _RESOURCES_SOURCE

    if _RESOURCES_ROOT_CACHE is not None:
        return _RESOURCES_ROOT_CACHE

    # 0) 环境变量（最高用户优先级，便于改规则后立即生效）
    env = os.environ.get("AGENTSEED_REPO")
    if env:
        p = Path(env).expanduser().resolve()
        if _has_pack_dir(p):
            _RESOURCES_ROOT_CACHE = p
            _RESOURCES_SOURCE = "env"
            return p

    # 1) 包内打包资源（pip install 模式，无需外部仓库）
    pkg = _packaged_resources_root()
    if pkg is not None:
        _RESOURCES_ROOT_CACHE = pkg
        _RESOURCES_SOURCE = "packaged"
        return pkg

    # 2) dev 模式：agentseed/sync_rules.py 的 parent.parent = REPO_ROOT
    dev_root = Path(__file__).resolve().parent.parent
    if _has_pack_dir(dev_root) and (dev_root / "core").is_dir():
        _RESOURCES_ROOT_CACHE = dev_root
        _RESOURCES_SOURCE = "dev"
        return dev_root

    # 3) 沿 cwd 祖先链查找（用户在 AgentSeed 仓库子目录里运行 CLI）
    cwd = Path.cwd().resolve()
    for parent in [cwd, *cwd.parents]:
        if _has_pack_dir(parent) and (parent / "core").is_dir():
            _RESOURCES_ROOT_CACHE = parent
            _RESOURCES_SOURCE = "cwd"
            return parent

    # 4) clone 到缓存（跨平台：使用 env.user_cache_dir()）
    cache = _env.user_cache_dir()
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        print(f"[agentseed] AgentSeed 源未在本地找到，正在 clone 到 {cache} ...", file=sys.stderr)
        try:
            code, stdout, stderr = _env.run_command(
                ["git", "clone", "--depth", "1", _AGENTSEED_REPO_URL, str(cache)],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            print(
                f"[agentseed] clone 失败: {e.stderr.decode(errors='ignore') if e.stderr else e}\n"
                f"请手动 git clone {_AGENTSEED_REPO_URL} 到任意位置，"
                f"然后设 AGENTSEED_REPO 环境变量指向该目录。",
                file=sys.stderr,
            )
            raise
        except FileNotFoundError:
            print(
                f"[agentseed] 系统未安装 git，无法自动 clone。请手动 git clone {_AGENTSEED_REPO_URL}，"
                f"然后设 AGENTSEED_REPO 环境变量指向 clone 后的目录。",
                file=sys.stderr,
            )
            raise
    elif not _has_pack_dir(cache):
        # 缓存目录存在但内容不完整，重新 clone
        shutil.rmtree(cache, ignore_errors=True)
        # 递归调用前清掉缓存（否则会立即返回 None）
        # 注意：因为 _RESOURCES_ROOT_CACHE 仍为 None，递归安全
        result = _find_rule_hub_root()
        return result
    _RESOURCES_ROOT_CACHE = cache
    _RESOURCES_SOURCE = "cache"
    return cache


def _resolve_resources_root() -> Path:
    """运行时动态解析资源根（供 build_ruleset 等使用）。

    与 _find_rule_hub_root() 的区别：本函数在每次调用时重新检查
    AGENTSEED_REPO 环境变量（允许用户在 CLI 启动后临时改环境变量），
    但包内打包资源仅在首次确定后保持稳定。
    """
    # 环境变量优先（允许用户运行时切换）
    env = os.environ.get("AGENTSEED_REPO")
    if env:
        p = Path(env).expanduser().resolve()
        if _has_pack_dir(p):
            return p
    # 其余回退到首次检测的缓存
    return _find_rule_hub_root()


def resources_source() -> str:
    """返回当前资源来源（用于溯源信息）"""
    if _RESOURCES_SOURCE is None:
        _find_rule_hub_root()
    # 运行时若改了 AGENTSEED_REPO，需重新判定
    env = os.environ.get("AGENTSEED_REPO")
    if env:
        p = Path(env).expanduser().resolve()
        if _has_pack_dir(p):
            return "env"
    return _RESOURCES_SOURCE or "unknown"


REPO_ROOT = _find_rule_hub_root()
# RESOURCES_ROOT 与 REPO_ROOT 同义，保留 REPO_ROOT 是为了向后兼容（测试和外部代码可能引用）
# 资源根：只读源文件用，永不指向用户输出目录
RESOURCES_ROOT = REPO_ROOT
PERSONAS_DIR = _pack_dir(RESOURCES_ROOT)
CORE_DIR = RESOURCES_ROOT / "core"
ADAPTERS_DIR = RESOURCES_ROOT / "adapters"

# OUTPUT_ROOT：写生成产物用，默认指向 RESOURCES_ROOT（旧行为）
# cli.py 的 --output 会临时切到用户目录
OUTPUT_ROOT = RESOURCES_ROOT


def set_output_root(path: Path) -> None:
    """切换产物输出根（仅影响 write_tool_file / _shard_root / write_provenance）"""
    global OUTPUT_ROOT
    OUTPUT_ROOT = path


def reset_output_root() -> None:
    """恢复 OUTPUT_ROOT 为 RESOURCES_ROOT"""
    global OUTPUT_ROOT
    OUTPUT_ROOT = RESOURCES_ROOT


def refresh_resources_root() -> Path:
    """重新检测资源根（响应当前 AGENTSEED_REPO 环境变量）。

    用于 cli.py 在 build_ruleset 前主动刷新，让运行时改的环境变量生效。
    同时刷新派生常量 PERSONAS_DIR / CORE_DIR / ADAPTERS_DIR。
    """
    global RESOURCES_ROOT, REPO_ROOT, PERSONAS_DIR, CORE_DIR, ADAPTERS_DIR
    global _RESOURCES_ROOT_CACHE, _RESOURCES_SOURCE
    # 清缓存重新检测
    _RESOURCES_ROOT_CACHE = None
    _RESOURCES_SOURCE = None
    new_root = _find_rule_hub_root()
    RESOURCES_ROOT = new_root
    REPO_ROOT = new_root
    PERSONAS_DIR = _pack_dir(new_root)
    CORE_DIR = new_root / "core"
    ADAPTERS_DIR = new_root / "adapters"
    # 若 OUTPUT_ROOT 当前等于旧值（未被 --output 切走），同步刷新
    global OUTPUT_ROOT
    OUTPUT_ROOT = new_root
    return new_root

# 工具到生成路径的映射
TOOL_OUTPUT = {
    # ── 跨工具标准（AGENTS.md 被 20+ 平台原生读取）──
    "agents-md": "AGENTS.md",
    # ── 千问办公（QwenWork，原生读取 AGENTS.md）──
    "qwenwork": "AGENTS.md",
    # ── 已有平台 ──
    "claude-code": "CLAUDE.md",
    "gemini": "GEMINI.md",
    "cursor": ".cursor/rules/project.mdc",
    "copilot": ".github/copilot-instructions.md",
    "trae": ".trae/rules/project_rules.md",
    # ── 国际平台 ──
    "windsurf": ".windsurfrules",
    "cline": ".clinerules/project.md",
    "continue": ".continue/rules/project.md",
    "amazon-q": ".amazonq/rules/project.md",
    "codex": ".codex/rules.md",
    "qodo": "best_practices.md",
    # ── 国内平台 ──
    "lingma": ".lingma/rules/project.md",
    "comate": ".comate/rules/project.mdr",
}

# 平台检测标记表 — 统一真相源，供 detect_tool_from_cwd() 和 forge.py 使用
# 每个 tuple: (文件/目录标记, 对应平台 ID)
# 检测顺序：从上到下，第一个匹配即返回
PLATFORM_DETECT_MARKERS = [
    # Claude Code — 优先检测（最常见）
    (".claude", "claude-code"),
    ("CLAUDE.md", "claude-code"),
    # Cursor
    (".cursor", "cursor"),
    (".cursorrules", "cursor"),
    # Gemini
    (".gemini", "gemini"),
    ("GEMINI.md", "gemini"),
    # Cline
    (".cline", "cline"),
    (".clinerules", "cline"),
    # Codex
    (".codex", "codex"),
    # Trae
    (".trae", "trae"),
    # Windsurf
    (".windsurfrules", "windsurf"),
    # Copilot
    (".github/copilot-instructions.md", "copilot"),
    # Continue
    (".continue", "continue"),
    # Amazon Q
    (".amazonq", "amazon-q"),
    # Qodo
    ("best_practices.md", "qodo"),
    # Lingma
    (".lingma", "lingma"),
    # Comate
    (".comate", "comate"),
]

# 平台字符限制（skeleton 模式下超限会自动多文件分片）
TOOL_CHAR_LIMIT = {
    "windsurf": 12000,
    "lingma": 10000,
    "comate": 10000,
}

# skeleton 模式下必须内联的 profile 段文件名（其余进 ON-DEMAND INDEX）
# 注：INIT-PROMPT.md 是给用户阅读的初始化指引，不参与规则装配，故不在此列
PROFILE_INLINE_BASENAMES = {"AGENTS.md", "system-prompt.md"}

# skeleton 模式下整体预算（字节，对齐 governance §Instruction Budget）
# 注：profile AGENTS.md + system-prompt 自身可能就 17-88KB（如 agent-builder），
# 因此本预算是"CORE + ON-DEMAND INDEX 应尽量克制"的目标，非硬性上限。
# 真正的硬上限在测试里另行断言（test_skeleton_budget）。
SKELETON_BUDGET_BYTES = 50000

# PROFILE LAYER 单文件内联预算（超限则按章节拆分：P0 内联 + 方法论 deferred）
# 策略：AGENTS.md / system-prompt.md 源文件保持不变（内容不丢），skeleton 只内联 P0 部分，
# 方法论章节转为 ON-DEMAND 索引项（指向源文件），agent 按需 Read。
# 10000B 让 agent-builder/AGENTS.md（13.7K）也触发拆分，配合 CORE 14.6K + INDEX 14-18K，
# 单 profile skeleton 总产物稳定 ≤ 50K（agent-builder 含 38 skills 是最大场景）。
PROFILE_LAYER_BUDGET = 10000

# P0 章节标记：包含这些关键词的章节强制内联（红线 / 优先级 / 工作流）。
# 启发式：前 N 字节 + 包含这些关键词的章节强制内联。
P0_KEYWORDS = [
    "Core Positioning", "Rule Priority", "Iron Rule", "铁律", "P0", "Workflow", "工作流",
    # XML 标签格式 system-prompt 的 P0 章节关键词
    "<rule_priority>", "<truthfulness>", "<safety>",
]

# ─── Domain-Specific Quality Gates (各 Profile 特色场景的公式触发器表) ───
# 每条：(场景名, 应读 skill 路径, 应算公式名, 阈值说明)
# 用于在 ON-DEMAND INDEX 末尾生成"本 Profile 特色场景的判断节点"表，告诉 agent
# 遇到该场景时必须先 Read 对应 skill 走公式，不准凭直觉判断。
DOMAIN_QUALITY_GATES = {
    "paper": [
        ("文献检索", "personas/paper/skills/literature-synthesis.md §10", "LSQ (Literature Search_Quality)", "≥0.85 高 / 0.6-0.85 中 / <0.6 低"),
        ("单篇引用", "personas/paper/skills/literature-synthesis.md §11", "Paper_Credibility_Score", "≥0.8 高 / 0.5-0.8 中 / <0.5 低"),
        ("数据清洗", "personas/paper/skills/data-cleaning.md", "Data_Quality", "≥0.85 高 / 0.7-0.85 中 / <0.7 低"),
        ("数据-声明对照", "personas/paper/skills/data-claim-alignment.md", "Claim_Support_Score", "=1.0 高 / ≥0.85 中 / <0.85 低"),
        ("论证强度", "personas/paper/skills/peer-review-simulation.md §6", "Argument_Strength_Score", "≥0.85 强 / 0.6-0.85 中 / <0.6 弱"),
    ],
    "coding": [
        ("代码审查", "personas/coding/skills/code-review-quality.md", "Code_Review_Quality", "≥0.85 Approve / 0.6-0.85 Comments / <0.6 Reject"),
        ("bug 排查", "personas/coding/skills/bug-investigation.md", "Root_Cause_Confidence (RCC)", "≥0.8 直接修 / 0.5-0.8 待观察 / <0.5 禁修"),
        ("技术选型/检索", "capabilities/research/skills/deep-search.md §6", "Search_Quality (通用)", "≥0.8 高 / 0.5-0.8 中 / <0.5 低"),
    ],
    "default": [
        ("事实回答", "capabilities/research/skills/truth-protocol.md §2", "CoV 5 步流程", "全通过=可输出"),
        ("检索质量", "capabilities/research/skills/deep-search.md §6", "Search_Quality", "≥0.8 高 / 0.5-0.8 中 / <0.5 低"),
        ("置信度标注", "capabilities/research/skills/truth-protocol.md §8", "Confidence Calibration", "高/中/中-/低/待验证"),
        ("来源可信度", "capabilities/research/skills/source-credibility.md", "T1-T4 + 三维评估", "T1 最高 → T4 最低"),
        ("思维深度", "capabilities/research/skills/reasoning-depth.md §7", "元认知检查清单", "4 维全通过"),
    ],
    "novel": [
        ("角色一致性", "personas/novel/skills/character-consistency-system.md §5", "Character_Consistency_Score", "≥0.95 优 / 0.85-0.95 良 / <0.7 差"),
        ("伏笔回收", "personas/novel/skills/foreshadow-tracking.md §3", "Foreshadow_Resolution_Rate", "≥0.9 优秀 / 0.7-0.9 合格 / <0.7 不合格"),
    ],
    "agent-builder": [
        ("评估严谨度", "personas/agent-builder/skills/evaluation-framework.md", "Eval_Rigor_Score", "≥0.85 高 / 0.6-0.85 中 / <0.4 极低"),
        ("工具设计副作用", "personas/agent-builder/skills/tool-design.md", "副作用五级 + 决策树", "L1-L5 分级"),
        ("自我精炼", "personas/agent-builder/skills/self-refinement.md", "三问自检", "全通过"),
    ],
}


# ─── manifest 解析（保持向后兼容）──────────────────────────────

def parse_manifest(profile_id: str) -> dict:
    """简单解析 manifest YAML，只处理本仓库使用的固定结构"""
    manifest_path = PERSONAS_DIR / profile_id / "persona.yaml"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest 不存在: {manifest_path}")
    text = manifest_path.read_text(encoding="utf-8")

    result = {"includes": {}, "profile": {}, "enables_capabilities": []}
    current_section = None
    current_list = None

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        # key: value
        m = re.match(r"^(\w+):\s*(.*)$", stripped)
        if m and not line.startswith(" "):
            key, val = m.group(1), m.group(2)
            if val:
                result.setdefault("profile", {})[key] = val
            else:
                current_section = key
                current_list = []
                result["includes"] = result.get("includes", {})
        elif stripped.startswith("- ") and current_section is not None:
            item = stripped[2:].strip()
            current_list.append(item)
    # 重新解析 includes 块（core/profile/skills/templates）
    result["includes"] = parse_includes(text)
    result["enables_capabilities"] = parse_list_field(text, "enables_capabilities")
    result["forbids_capabilities"] = parse_list_field(text, "forbids_capabilities")
    result["mutually_exclusive_with"] = parse_list_field(text, "mutually_exclusive_with")
    return result


def parse_includes(text: str) -> dict:
    """解析 includes 下的 core/profile/skills/templates 列表"""
    includes = {"core": [], "profile": [], "skills": [], "templates": []}
    current = None
    in_includes = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "includes:":
            in_includes = True
            continue
        if not in_includes:
            continue
        # 顶格 key 表示已离开 includes 块
        if not line.startswith(" "):
            in_includes = False
            continue
        # 缩进 section key（如 core: profile: skills: templates:）
        if re.match(r"^\w+:", stripped) and not stripped.startswith("-"):
            current = stripped[:-1]
            if current not in includes:
                includes[current] = []
        elif stripped.startswith("- ") and current:
            includes[current].append(stripped[2:].strip())
    return includes


def parse_list_field(text: str, field: str) -> list:
    """解析 enables_capabilities 等列表字段"""
    items = []
    in_field = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{field}:"):
            in_field = True
            continue
        if in_field:
            if stripped.startswith("- "):
                items.append(stripped[2:].strip())
            elif re.match(r"^\w+:", stripped) and not stripped.startswith("-"):
                in_field = False
    return items


# ─── 文件读写 ──────────────────────────────────────

def read_file(path: Path) -> str:
    p = REPO_ROOT / path if not path.is_absolute() else path
    if not p.exists():
        return f"> [missing] {path}\n"
    return p.read_text(encoding="utf-8")


def expand_refs(text: str, base_dir: Path = None, inline: bool = True) -> str:
    """处理 @path 引用。
    - inline=True（full 模式）：把引用文件内容内联展开（旧行为，递归展开）。
    - inline=False（skeleton 模式）：保留为路径提示，agent 遇到时自行 Read。
      路径解析为相对仓库根的稳定路径，便于 agent 直接调用 Read。
    """
    search_base = base_dir if base_dir else REPO_ROOT

    def resolve_ref(ref: str) -> Path:
        p = search_base / ref
        if p.exists():
            return p
        p = REPO_ROOT / ref
        if p.exists():
            return p
        for parent in search_base.parents:
            p = parent / ref
            if p.exists():
                return p
        return None

    def inline_replacer(m):
        ref = m.group(1)
        p = resolve_ref(ref)
        if p:
            inner = p.read_text(encoding="utf-8")
            inner = expand_refs(inner, p.parent, inline=True)
            return f"\n{inner}\n"
        return f"> [unresolved ref] {ref}\n"

    def hint_replacer(m):
        ref = m.group(1)
        p = resolve_ref(ref)
        if p:
            try:
                rel = p.relative_to(REPO_ROOT).as_posix()
            except ValueError:
                rel = ref
            return f"`@{rel}` (按需 Read)"
        return f"`@{ref}` (未解析)"

    if inline:
        return re.sub(r"@([\w/.-]+\.md)", inline_replacer, text)
    return re.sub(r"@([\w/.-]+\.md)", hint_replacer, text)


# ─── 文件元数据提取（用于 ON-DEMAND INDEX）──────────────────────

def extract_metadata(path: Path) -> dict:
    """从 markdown 文件提取 H1 + 首个 > 引用块（描述）+ 大小 + 关键词 + 四元组 frontmatter。

    frontmatter 字段（Skills 四元组 S = C, π, T, R；悉尼科大 + CSIRO Data61 2026 形式化）：
      applicable_when / terminates_when / provides / interface
    若文件无 frontmatter，相应字段返回空字符串。
    """
    if not path.exists():
        return {"title": path.stem, "purpose": "", "size": 0, "keywords": [],
                "applicable_when": "", "terminates_when": "", "provides": "", "interface": ""}
    text = path.read_text(encoding="utf-8")

    # 解析 YAML frontmatter（仅取四个固定字段，避免引入 yaml 依赖）
    # Skills 四元组 frontmatter 形如：
    #   applicable_when: C    # 用户要做 git commit / push / rebase
    # 冒号后第一个 token 是占位符号（C/π/T/R，来自 S = (C, π, T, R) 形式化记号），
    # 真正的描述在 # 注释里。渲染时取注释部分；若无注释则取冒号后的完整值。
    applicable_when = ""
    terminates_when = ""
    provides = ""
    interface = ""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm = text[3:end]
            for line in fm.splitlines():
                m = re.match(r"^(applicable_when|terminates_when|provides|interface):\s*(.*)$", line.strip())
                if m:
                    raw = m.group(2)
                    # 优先取 # 后的注释作为描述；若无注释则取整个 raw
                    if "#" in raw:
                        val = raw.split("#", 1)[1].strip()
                    else:
                        val = raw.strip()
                    # 去掉行内反引号（避免 markdown 表格渲染异常）
                    val = val.replace("`", "'")
                    if m.group(1) == "applicable_when":
                        applicable_when = val
                    elif m.group(1) == "terminates_when":
                        terminates_when = val
                    elif m.group(1) == "provides":
                        provides = val
                    elif m.group(1) == "interface":
                        interface = val
            # frontmatter 之后的正文
            text = text[end + 4:].lstrip("\n")

    title = path.stem
    m = re.search(r"^#\s+(.+)$", text, re.M)
    if m:
        title = m.group(1).strip()
    # 收集所有 > 引用块行
    quote_lines = []
    in_quote = False
    for line in text.splitlines():
        if line.startswith("> "):
            quote_lines.append(line[2:].strip())
            in_quote = True
        elif line.startswith(">"):
            quote_lines.append(line[1:].strip())
            in_quote = True
        elif in_quote and line.strip() == "":
            break
        elif in_quote and not line.startswith(">"):
            break
    purpose = " ".join(quote_lines).strip() if quote_lines else ""
    return {
        "title": title,
        "purpose": purpose[:200],
        "size": len(text),
        "keywords": derive_keywords(path.stem),
        "applicable_when": applicable_when,
        "terminates_when": terminates_when,
        "provides": provides,
        "interface": interface,
    }


def derive_keywords(stem: str) -> list:
    """从文件名推断触发关键词"""
    parts = re.split(r"[-_]+", stem)
    return [p for p in parts if p and len(p) > 1]


def _collect_mcp_files(manifest: dict) -> list:
    """从 manifest 的 skills 中识别 MCP 相关文件，返回 [(path, purpose), ...]"""
    result = []
    for sf in manifest["includes"].get("skills", []):
        stem = Path(sf).stem.lower()
        if "mcp" in stem:
            p = REPO_ROOT / sf
            meta = extract_metadata(p)
            result.append((sf, meta["purpose"] or meta["title"]))
    return result


# ─── 装配 ─────────────────────────────────────────────

def _truncate_field(s: str, max_len: int) -> str:
    """截断字段到 max_len 字符（保留完整词，加省略号）。
    用于 ON-DEMAND INDEX 中过长的 C/T 描述字段，控制 INDEX 体积。
    完整内容在 Read 源文件后可见，索引只需触发信号。
    """
    if not s or len(s) <= max_len:
        return s
    # 优先在空格/逗号/中文标点处截断
    cut = s[:max_len - 1]
    # 找最后一个分隔符
    for sep in ['，', ',', '；', ';', ' / ', ' ']:
        idx = cut.rfind(sep)
        if idx > max_len // 2:
            return cut[:idx].rstrip() + "…"
    return cut + "…"


def _infer_trigger(section_title: str) -> str:
    """根据章节标题推断触发场景（用于 ON-DEMAND INDEX 的方法论章节表）。"""
    t = section_title.lower()
    if "citation" in t or "引用" in t:
        return "引用文献/格式化来源时"
    if "literature" in t or "文献" in t:
        return "检索/综述文献时"
    if "methodology" in t or "方法" in t:
        return "设计研究方法时"
    if "data" in t or "数据" in t:
        return "处理/呈现数据时"
    if "review" in t or "审" in t:
        return "模拟评审/自检时"
    if "revision" in t or "修订" in t:
        return "撰写修订信/回复信时"
    if "structure" in t or "结构" in t:
        return "搭建论文框架时"
    if "question" in t or "假设" in t or "问题" in t:
        return "提出研究问题/假设时"
    if "anti-ai" in t or "ai 味" in t or "反 ai" in t:
        return "去除 AI 学术味时"
    if "tool" in t or "工具" in t:
        return "编排工具/MCP 时"
    if "safety" in t or "安全" in t:
        return "设计安全护栏时"
    if "evaluation" in t or "评估" in t:
        return "评估 agent/测试时"
    if "memory" in t or "记忆" in t:
        return "设计记忆系统时"
    if "prompt" in t or "提示" in t:
        return "工程化提示词时"
    if "reasoning" in t or "推理" in t:
        return "选择推理模式时"
    if "context" in t or "上下文" in t:
        return "管理上下文时"
    if "multi-agent" in t or "多智能" in t:
        return "多 agent 协作时"
    if "deploy" in t or "部署" in t:
        return "部署/适配时"
    if "iter" in t or "演进" in t:
        return "迭代演进时"
    if "privacy" in t or "隐私" in t:
        return "处理隐私/合规时"
    if "emergency" in t or "紧急" in t:
        return "紧急例外处理时"
    if "role" in t or "角色" in t:
        return "定义 agent 角色时"
    if "conversation" in t or "对话" in t:
        return "设计对话流程时"
    if "knowledge" in t or "知识" in t:
        return "注入知识时"
    return "对应业务场景触发时"


def _extract_section_title(sec: str) -> str:
    """从章节片段提取标题（支持 ## / ### / #### markdown 标题与 XML 顶级标签）。

    - `## Title` → "Title"
    - `### Title` → "Title"
    - `<tag>\\nLabel...` → "Label"（XML 标签格式如 agent-builder/system-prompt.md，
      label 是标签后的第一行说明，比 <tag> 更可读）
    - `<tag>` (无 label) → "<tag>"
    """
    m = re.match(r'^#{2,4}\s+(.+?)(?:\n|$)', sec)
    if m:
        return m.group(1).strip()
    m = re.match(r'^<([a-z_]+)>\s*\n([^\n<]+)', sec, re.I)
    if m:
        label = m.group(2).strip()
        # 去掉标签行尾可能的冒号或破折号
        label = re.sub(r'[:：]\s*$', '', label)
        if label and not label.startswith('-') and not label.startswith('<'):
            return label
        return f"<{m.group(1)}>"
    m = re.match(r'^<([a-z_]+)>', sec, re.I)
    if m:
        return f"<{m.group(1)}>"
    return "(无标题)"


def _is_section_start(sec: str) -> bool:
    """判断片段是否以章节边界开头（## / ### / 顶级 XML 标签）。"""
    if not sec:
        return False
    if sec.startswith('## ') or sec.startswith('### ') or sec.startswith('#### '):
        return True
    return bool(re.match(r'^<[a-z_]+>\s*(?:\n|$)', sec, re.I))


def _split_profile_content(content: str, budget: int, file_path: str) -> tuple:
    """把 profile 主层文件按章节边界拆分（内容不变，只改装配方式）。

    支持三种章节格式：
    1. Markdown 标题：`## ` / `### ` / `#### `
    2. XML 顶级标签：`<tag>` 单独成行（如 agent-builder/system-prompt.md）
    3. 无结构：返回原内容，不拆分（deferred 为空）

    策略：
    - 强制内联：含 P0_KEYWORDS 的章节 + 文件头（首个章节前的内容）
    - 其余章节：预算内继续内联，超预算的转为 deferred
    - 返回 (inline_part, deferred_sections)
        - inline_part: 内联内容（含 P0 + 预算内的方法论）
        - deferred_sections: [(section_title, section_anchor), ...] 供 ON-DEMAND INDEX 引用

    保证：源文件不变，agent 仍可 Read 原路径拿到全部内容。
    """
    if len(content) <= budget:
        return content, []

    # 统一识别章节边界：## / ### / #### / <xml-tag>
    sections = re.split(r'(?=^(?:#{2,4}\s|<[a-z_]+>\s*(?:\n|$)))', content, flags=re.M)

    # 若无章节边界（split 后仍只有 1 段），无法拆分，返回原内容
    if len(sections) <= 1:
        return content, []

    inline_parts = []
    deferred = []
    current_size = 0

    for sec in sections:
        if not sec.strip():
            continue

        title = _extract_section_title(sec)
        is_section = _is_section_start(sec)
        is_header = not is_section  # 文件头（首个章节前的内容，如 H1、frontmatter）

        # 判断是否 P0 章节（强制内联）
        is_p0 = any(kw.lower() in title.lower() for kw in P0_KEYWORDS) and is_section

        if is_p0 or is_header:
            inline_parts.append(sec)
            current_size += len(sec)
        elif current_size + len(sec) <= budget:
            # 预算内，内联
            inline_parts.append(sec)
            current_size += len(sec)
        else:
            # 超预算，转为 deferred
            anchor = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff]+', '-', title.lower()).strip('-')
            deferred.append((title, anchor))

    inline_part = ''.join(inline_parts)
    # 在内联部分末尾加 deferred 提示
    if deferred:
        inline_part += (
            f"\n> ⚠️ **本文件的方法论章节（共 {len(deferred)} 节）已转为按需加载**——"
            f"内容仍在源文件 `{file_path}` 中，未删除。Agent 遇到对应场景时必须 `Read({file_path})` "
            f"并定位到对应章节获取完整规则。详见下方 ON-DEMAND INDEX 的「PROFILE 方法论章节」段。\n"
        )

    return inline_part, deferred


def _resolve_capability_path(cap: str, profile_id: str = "") -> tuple:
    """解析能力包路径，处理非常规布局（如 dar 在 research/dar/ 下）。

    返回 (cap_dir, cap_prompt_path)。
    cap_prompt_path 为 None 时表示该能力包无 prompt.md（只有配置文件）。
    """
    # 标准路径: capabilities/<cap>/prompt.md
    standard = REPO_ROOT / "capabilities" / cap / "prompt.md"
    if standard.exists():
        return (REPO_ROOT / "capabilities" / cap, standard)

    # dar 特殊路径: capabilities/research/dar/README.md
    if cap == "dar":
        dar_dir = REPO_ROOT / "capabilities" / "research" / "dar"
        dar_readme = dar_dir / "README.md"
        if dar_readme.exists():
            return (dar_dir, dar_readme)

    return (None, None)


def _default_manifest() -> dict:
    """内核通用模式（default）的合成清单：仅 core 层，无 personas 目录依赖。

    conversation 场景包已并入内核（2026-08-08）：其通用规则沉淀在
    core/{governance,interaction,tool-policy,language-mediation}.md。
    """
    return {
        "includes": {
            "core": ["core/governance.md", "core/interaction.md",
                     "core/persona-router.md", "core/language-mediation.md",
                     "core/attention-budget.md", "core/agent-modes.md",
                     "core/tool-policy.md", "core/session-refresh.md"],
            "profile": [],
            "skills": [],
        },
        "profile": {"id": "default", "name": "内核通用模式",
                    "default_mode": "task",
                    "capabilities": ["research", "dar"]},
        "enables_capabilities": ["research", "dar"],
    }


def build_ruleset(profile_id: str, mode: str = "skeleton") -> str:
    """装配规则集。
    - mode=skeleton（默认）：CORE + PROFILE 主层内联，其余走 ON-DEMAND INDEX。
    - mode=full：旧行为，全部内联（向后兼容）。
    - profile_id="default"：内核通用模式（无 personas 目录，仅 core 层）。
    """
    manifest = _default_manifest() if profile_id == "default" else parse_manifest(profile_id)
    parts = []

    # ── 生成头（含正确溯源，修 governance §8 的"AGENTS.md 是源"矛盾）──
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    src_hash = hashlib.sha256(f"{profile_id}|{mode}".encode()).hexdigest()[:12]
    parts.append(
        f"<!-- 由 sync_rules.py 自动生成 | profile: {profile_id} | mode: {mode} | "
        f"generated: {ts} | hash: {src_hash} | 禁止手工编辑 -->\n"
    )
    parts.append(
        "<!-- 源: core/*.md + personas/<id>/{AGENTS.md,prompts/} + capabilities/<cap>/  + personas/*.yaml | "
        "生成产物（AGENTS.md / CLAUDE.md / GEMINI.md 等）均非源，请勿手改 -->\n\n"
    )

    # ── 会话运行时刷新协议（自动注入，无需每个 profile 手工配置）──
    # 让 Agent 在会话中检测规则更新并应用（详见 core/session-refresh.md）
    refresh_path = REPO_ROOT / "core" / "session-refresh.md"
    if refresh_path.exists():
        parts.append("\n## [core] core/session-refresh.md\n")
        parts.append(expand_refs(read_file(Path("core/session-refresh.md")), refresh_path.parent, inline=False))

    # skeleton 模式下引用保留为路径提示，agent 按需 Read；full 模式下递归内联
    inline_mode = (mode == "full")

    # skeleton 模式下把 persona-router.md 也按需化（profile 已选定后它是冗余的元规则）
    ON_DEMAND_CORE = {"core/persona-router.md"} if mode == "skeleton" else set()

    # ── CORE LAYER（始终内联，P0 红线）──
    parts.append("# === CORE LAYER (P0 红线，始终生效) ===\n")
    core_inline = [c for c in manifest["includes"].get("core", []) if c not in ON_DEMAND_CORE]
    core_on_demand = [c for c in manifest["includes"].get("core", []) if c in ON_DEMAND_CORE]
    for core_file in core_inline:
        core_path = REPO_ROOT / core_file
        parts.append(f"\n## [core] {core_file}\n")
        parts.append(expand_refs(read_file(Path(core_file)), core_path.parent, inline=inline_mode))

    # ── PROFILE LAYER ──
    profile_files = manifest["includes"].get("profile", [])
    if profile_files:
        parts.append("\n# === PROFILE LAYER ===\n")
    profile_inline = []
    profile_on_demand = []
    deferred_profile_sections = []  # 拆分出的方法论章节 [(file_path, [(title, anchor), ...])]
    for pf in profile_files:
        basename = Path(pf).name
        if mode == "full" or basename in PROFILE_INLINE_BASENAMES:
            profile_inline.append(pf)
        else:
            profile_on_demand.append(pf)
    for pf in profile_inline:
        prof_path = REPO_ROOT / pf
        content = expand_refs(read_file(Path(pf)), prof_path.parent, inline=inline_mode)
        # skeleton 模式下：若 PROFILE LAYER 单文件超预算，按 ## 章节拆分（内容不变）
        if mode == "skeleton" and len(content) > PROFILE_LAYER_BUDGET:
            inline_part, deferred = _split_profile_content(content, PROFILE_LAYER_BUDGET, pf)
            parts.append(f"\n## [profile] {pf}\n")
            parts.append(inline_part)
            if deferred:
                deferred_profile_sections.append((pf, deferred))
        else:
            parts.append(f"\n## [profile] {pf}\n")
            parts.append(content)

    if mode == "skeleton":
        parts.extend(_build_on_demand_index(profile_id, manifest, profile_on_demand, core_on_demand,
                                            deferred_profile_sections))
    else:
        # full 模式：内联剩余 profile + skills + capabilities（旧行为）
        for pf in profile_on_demand:
            prof_path = REPO_ROOT / pf
            parts.append(f"\n## [profile] {pf}\n")
            parts.append(expand_refs(read_file(Path(pf)), prof_path.parent, inline=True))
        parts.append("\n# === SKILLS LAYER ===\n")
        for skill_file in manifest["includes"].get("skills", []):
            skill_path = REPO_ROOT / skill_file
            parts.append(f"\n## [skill] {skill_file}\n")
            parts.append(expand_refs(read_file(Path(skill_file)), skill_path.parent, inline=True))
        parts.append("\n# === CAPABILITIES LAYER ===\n")
        for cap in manifest.get("enables_capabilities", []):
            cap_dir, cap_prompt = _resolve_capability_path(cap, profile_id)
            if cap_prompt is None or not cap_prompt.exists():
                parts.append(f"\n> [missing capability] {cap}\n")
                continue
            parts.append(f"\n## [capability] {cap}\n")
            parts.append(expand_refs(cap_prompt.read_text(encoding="utf-8"), cap_dir, inline=True))

    return "".join(parts)


def _build_on_demand_index(profile_id: str, manifest: dict, profile_on_demand: list,
                            core_on_demand: list = None,
                            deferred_profile_sections: list = None) -> list:
    """生成 ON-DEMAND INDEX 段落"""
    core_on_demand = core_on_demand or []
    deferred_profile_sections = deferred_profile_sections or []
    parts = []
    parts.append("\n# === ON-DEMAND INDEX (按需加载，不预载) ===\n")
    # 写入生成时的资源根（开发时为 repo 根，打包后为包内 _resources）
    # 不再写本机绝对路径，改为中性标识
    src = resources_source()
    src_note = {
        "packaged": "包内打包资源（pip install agentseed 后随包分发，离线可用）",
        "env": "AGENTSEED_REPO 环境变量指向的本地仓库",
        "dev": "AgentSeed 仓库 dev 模式（agentseed/ 在仓库内）",
        "cwd": "cwd 祖先链中找到的 AgentSeed 仓库",
        "cache": "缓存 clone（~/.cache/agentseed/）",
    }.get(src, src)
    parts.append(
        "> 以下内容默认**不加载**。Agent 在对话中遇到对应触发条件时，必须主动用 `Read` 工具读取对应文件后再行动。\n"
        f"> 资源来源: {src_note}\n"
        "> 远程仓库: https://github.com/weed33834/agentseed.git\n"
        "> 预算对齐 governance.md §Instruction Budget：不预载是为避免指令过载导致 P0 红线失守。\n\n"
        "> **路径解析协议（agent 必读，按顺序尝试，首个成功即用）**:\n"
        "> 1. 优先从 AgentSeed 仓库根（当前项目或 AGENTSEED_REPO 环境变量指向）读取相对路径\n"
        "> 2. 若是 pip 安装的 agentseed 包，规则源已随包分发，可从 Python 解释器内查：`python -c \"import agentseed, pathlib; print(pathlib.Path(agentseed.__file__).parent / '_resources')\"`，得到路径后拼接表中相对路径\n"
        "> 3. 若仍不存在，从 https://github.com/weed33834/agentseed.git 重新 clone 到 `~/.cache/agentseed/`，再从该目录 Read\n"
        "> 4. 若网络不可用且本地无仓库，**直接告知用户**：「我需要访问 AgentSeed 仓库才能加载该 skill，请执行 `pip install agentseed` 或 `git clone https://github.com/weed33834/agentseed.git` 并设置 `AGENTSEED_REPO` 环境变量」，不要跳过或自行编造规则内容\n\n"
    )

    # ── Meta Rules (按需的 core 元规则，如 persona-router) ──
    if core_on_demand:
        parts.append("## Meta Rules (按需，仅切换 profile 时加载)\n")
        parts.append("| 用途 | 文件路径 |\n|---|---|\n")
        for cf in core_on_demand:
            p = REPO_ROOT / cf
            meta = extract_metadata(p)
            purpose = (meta["purpose"] or meta["title"]).replace("|", "\\|")
            parts.append(f"| {purpose} | {cf} |\n")
        parts.append("\n")

    # ── Subagent Prompts ──
    if profile_on_demand:
        parts.append("## Subagent Prompts (按需)\n")
        parts.append("| 触发关键词 | 用途 | 文件路径 | 大小 |\n|---|---|---|---|\n")
        for pf in profile_on_demand:
            p = REPO_ROOT / pf
            meta = extract_metadata(p)
            kw = ", ".join(meta["keywords"][:3]) or "—"
            purpose = meta["purpose"] or meta["title"]
            purpose = purpose.replace("|", "\\|")
            parts.append(f"| {kw} | {purpose} | {pf} | {meta['size']}B |\n")
        parts.append("\n")

    # ── Skills ──
    # 标题保留「SKILLS LAYER」字样（全大写，与 full 模式 `# === SKILLS LAYER ===` 对齐）：
    # skeleton 模式下 skills 是三层结构中的 Skills 层（内容为按需索引而非内联）。
    skills = manifest["includes"].get("skills", [])
    if skills:
        parts.append("## SKILLS LAYER (按需)\n")
        parts.append("| 触发条件 (C) | 终止条件 (T) | 文件路径 | 大小 |\n|---|---|---|---|\n")
        for sf in skills:
            p = REPO_ROOT / sf
            meta = extract_metadata(p)
            # C = applicable_when（何时该 Read 本 skill）；T = terminates_when（何时认为本 skill 已用完）
            # 有 frontmatter 时用 C/T，没有就回退到关键词 + 描述（向后兼容旧 skills 文件）
            c_field = meta["applicable_when"]
            t_field = meta["terminates_when"]
            if not c_field:
                kw = ", ".join(meta["keywords"][:3]) or "—"
                c_field = kw
            if not t_field:
                t_field = "—"
            # 截断过长描述，控制 INDEX 体积（对齐 SKELETON_BUDGET_BYTES）
            # 完整 C/T 描述在 Read 文件后可见，索引只需给出主要触发信号
            c_field = _truncate_field(c_field, 60)
            t_field = _truncate_field(t_field, 40)
            c_field = c_field.replace("|", "\\|")
            t_field = t_field.replace("|", "\\|")
            parts.append(f"| {c_field} | {t_field} | {sf} | {meta['size']}B |\n")
        parts.append("\n")

    # ── Capabilities ──
    caps = manifest.get("enables_capabilities", [])
    if caps:
        parts.append("## Capabilities (按需)\n")
        parts.append("| 能力包 | 用途 | 文件路径 |\n|---|---|---|\n")
        for cap in caps:
            if cap == "dar":
                dar_path = REPO_ROOT / "capabilities" / "research" / "dar"
                dar_md = dar_path / "README.md"
                meta = extract_metadata(dar_md)
                purpose = (meta["purpose"] or "域权威注册表").replace("|", "\\|")
                dar_cfg = dar_path / f"dar-{profile_id}.yaml"
                dar_ref = "capabilities/research/dar/README.md"
                if dar_cfg.exists():
                    dar_ref += f" + capabilities/research/dar/dar-{profile_id}.yaml"
                parts.append(f"| dar | {purpose} | {dar_ref} |\n")
            else:
                cap_prompt = REPO_ROOT / "capabilities" / cap / "prompt.md"
                meta = extract_metadata(cap_prompt)
                purpose = (meta["purpose"] or meta["title"]).replace("|", "\\|")
                parts.append(f"| {cap} | {purpose} | capabilities/{cap}/ |\n")
        parts.append("\n")

    # ── MCP (任何 profile 都列出，按需) ──
    mcp_files = _collect_mcp_files(manifest)
    parts.append("## MCP (按需，常驻服务由用户手动配置)\n")
    parts.append("> ⚠️ MCP 红线：AI 禁止自下载/自安装/自启动/自配置 MCP。仅可输出命令与配置 JSON 供用户审阅后粘贴。\n\n")
    if mcp_files:
        parts.append("| 用途 | 文件路径 |\n|---|---|\n")
        for mf, purpose in mcp_files:
            purpose = purpose.replace("|", "\\|")
            parts.append(f"| {purpose} | {mf} |\n")
        parts.append("| MCP 配置示例（占位 token） | mcp.example.json |\n")
    else:
        parts.append("本 profile 无内置 MCP skill。如需对接外部系统，请参考根目录 `mcp.example.json` 与 governance.md §MCP 红线。\n")
    parts.append("\n")

    # ── Templates (agent-builder 等) ──
    templates = manifest["includes"].get("templates", [])
    if templates:
        parts.append("## Templates (按需，使用对应模板时加载该目录全部文件)\n")
        parts.append("| 模板 | 路径 |\n|---|---|\n")
        for tp in templates:
            name = Path(tp).name
            parts.append(f"| {name} | {tp} |\n")
        parts.append("\n")

    # ── PROFILE 方法论章节（因预算拆分而 deferred 的 AGENTS.md 章节）──
    if deferred_profile_sections:
        parts.append("## PROFILE 方法论章节 (按需，因 skeleton 预算从源文件拆分)\n")
        parts.append(
            "> 以下章节原属 AGENTS.md / system-prompt.md，因 skeleton 预算（PROFILE_LAYER_BUDGET）已转为按需加载。\n"
            "> **内容未删除**——仍在源文件中。Agent 遇到对应场景时必须 `Read(源文件)` 并定位到对应章节。\n\n"
        )
        for file_path, sections in deferred_profile_sections:
            parts.append(f"### 源文件: `{file_path}`\n\n")
            parts.append("| 章节 | 触发场景 |\n|---|---|\n")
            for title, anchor in sections:
                # 推断触发场景
                trigger = _infer_trigger(title)
                # 截断过长的章节标题（含嵌套 @path 引用等）
                display_title = _truncate_field(title, 50)
                display_title = display_title.replace("|", "\\|")
                parts.append(f"| {display_title} | {trigger} |\n")
            parts.append(f"\n加载: `Read({file_path})` 后定位到对应章节。\n\n")

    # ── Domain-Specific Quality Gates (本 Profile 特色场景的公式触发器) ──
    gates = DOMAIN_QUALITY_GATES.get(profile_id)
    if gates:
        parts.append("## Domain-Specific Quality Gates (本 Profile 特色场景的质量门槛)\n")
        parts.append(
            "> 以下为本 Profile 特色的判断节点。AI 在对应场景下**必须先用公式量化再行动**——不准凭直觉判断。\n"
            "> 公式优先于直觉；自评与公式冲突取较低值（保守原则，对齐 truth-protocol.md §8）。\n\n"
        )
        parts.append("| 场景 | 应 Read skill | 应算公式 | 阈值（高分→低分） |\n|---|---|---|---|\n")
        for gate in gates:
            parts.append(f"| {gate[0]} | {gate[1]} | {gate[2]} | {gate[3]} |\n")
        parts.append("\n")
        parts.append(
            "强制标注：交付回复时标注本次走了哪些公式及分数，如 `[LSQ: 0.88 / 置信度: 中 / CoV: 已通过]`，便于用户校验。\n\n"
        )

    # ── Loading Protocol ──
    parts.append("## Loading Protocol\n")
    parts.append(
        "1. 优先遵循 CORE LAYER + PROFILE LAYER 的内联规则；这是会话内始终生效的最小集。\n"
        "2. 遇到具体场景时，对照上表关键词，用 `Read(路径)` 工具加载对应文件后再行动。\n"
        "3. **不要预加载所有文件**——按需读取避免指令过载（参考 governance.md §Instruction Budget）。\n"
        "4. 加载的 skill / capability / subagent 在当前会话内有效；切换 profile 时清除上一 profile 全部状态。\n"
        "5. 加载后如与本层规则冲突，优先级：CORE(P0) > 用户明确确认 > 主 PROFILE > 加载的能力包 > 模型默认。\n"
        "6. **遇到 Domain-Specific Quality Gates 列出的场景时，必须先 Read 对应 skill 走公式，再交付**——不准跳过自评。\n"
    )
    return parts


# ─── 写出 ─────────────────────────────────────────────

def write_tool_file(tool: str, profile_id: str, ruleset: str, mode: str = "skeleton") -> Path:
    """按工具格式写入目标文件。
    - 限长平台（windsurf/lingma/comate）在 skeleton 模式下自动多文件分片。
    - full 模式或非限长平台：单文件输出（旧行为）。
    - 写入位置由 OUTPUT_ROOT 决定（默认 = RESOURCES_ROOT；cli.py 的 --output 会切换）。
    """
    out_rel = TOOL_OUTPUT[tool]
    out_path = OUTPUT_ROOT / out_rel
    out_path.parent.mkdir(parents=True, exist_ok=True)

    content = ruleset
    # 可选适配器追加层（adapter 从源读，不受 OUTPUT_ROOT 影响）
    for cand in (ADAPTERS_DIR / f"{tool}.md", ADAPTERS_DIR / tool / "append.md"):
        if cand.exists():
            content = content + f"\n\n# === ADAPTER OVERRIDE ({tool}) ===\n" + cand.read_text(encoding="utf-8")
            break

    # 平台专属格式
    final_content = content
    if tool == "cursor":
        header = f"---\ndescription: {profile_id} profile rules ({mode})\nalwaysApply: true\n---\n\n"
        final_content = header + content
    # comate: .mdr 文件，内容为 Markdown，无 frontmatter
    # 其他平台：纯 Markdown

    # 限长平台分片：skeleton 模式下若仍超限，拆成多文件 + INDEX
    char_limit = TOOL_CHAR_LIMIT.get(tool)
    if mode == "skeleton" and char_limit and len(final_content) > char_limit:
        _write_sharded(tool, profile_id, final_content, char_limit)
        # 主入口文件保留极简版本（只含 CORE + ON-DEMAND INDEX 头）
        entry = _build_sharded_entry(tool, profile_id, final_content, char_limit)
        out_path.write_text(entry, encoding="utf-8")
        write_provenance(tool, profile_id, entry, mode=mode, sharded=True,
                         extra_files=_shard_listing(tool, profile_id))
        return out_path

    out_path.write_text(final_content, encoding="utf-8")
    write_provenance(tool, profile_id, final_content, mode=mode)
    return out_path


# ─── Hook 适配器分发 ─────────────────────────────────

# 每个平台要分发的 hook 文件（相对于 OUTPUT_ROOT 的路径 → 源文件路径）
# 平台不在表中 = 不支持 hook，不输出（README 自述 7 个不支持的平台）
HOOK_PLATFORMS = {
    "claude-code": {
        "settings": (".claude/settings.json", "adapters/hooks/claude-code/settings.json.template"),
        "scripts": [
            ("adapters/hooks/claude-code/pre_tool_use.py", "adapters/hooks/claude-code/pre_tool_use.py"),
            ("adapters/hooks/shared/check.py", "adapters/hooks/shared/check.py"),
        ],
        "constraints": ("core/constraints.yaml", "core/constraints.yaml"),
    },
    "cursor": {
        "settings": (".cursor/hooks.json", "adapters/hooks/cursor/hooks.json.template"),
        "scripts": [
            ("adapters/hooks/cursor/pre_tool_use.py", "adapters/hooks/cursor/pre_tool_use.py"),
            ("adapters/hooks/shared/check.py", "adapters/hooks/shared/check.py"),
        ],
        "constraints": ("core/constraints.yaml", "core/constraints.yaml"),
    },
    "gemini": {
        "settings": (".gemini/hooks.json", "adapters/hooks/gemini/hooks.json.template"),
        "scripts": [
            ("adapters/hooks/gemini/pre_tool_use.py", "adapters/hooks/gemini/pre_tool_use.py"),
            ("adapters/hooks/shared/check.py", "adapters/hooks/shared/check.py"),
        ],
        "constraints": ("core/constraints.yaml", "core/constraints.yaml"),
    },
    "cline": {
        "settings": (".cline/hooks.json", "adapters/hooks/cline/hooks.json.template"),
        "scripts": [
            ("adapters/hooks/cline/pre_tool_use.py", "adapters/hooks/cline/pre_tool_use.py"),
            ("adapters/hooks/shared/check.py", "adapters/hooks/shared/check.py"),
        ],
        "constraints": ("core/constraints.yaml", "core/constraints.yaml"),
    },
    "codex": {
        "settings": (".codex/hooks.json", "adapters/hooks/codex/hooks.json.template"),
        "scripts": [
            ("adapters/hooks/codex/pre_tool_use.py", "adapters/hooks/codex/pre_tool_use.py"),
            ("adapters/hooks/shared/check.py", "adapters/hooks/shared/check.py"),
        ],
        "constraints": ("core/constraints.yaml", "core/constraints.yaml"),
    },
    "trae": {
        "settings": (".trae/sandbox-policy.json", "adapters/hooks/trae/sandbox-policy.json"),
        "scripts": [],
        "constraints": None,
    },
}


def emit_constraints(tool: str) -> list:
    """把指定平台的 hook 配置文件分发到 OUTPUT_ROOT。

    返回写入的文件路径列表。
    平台不支持 hook 时返回空列表（不报错，对齐 APM 协议：unsupported targets silently skipped）。
    """
    if tool not in HOOK_PLATFORMS:
        return []

    config = HOOK_PLATFORMS[tool]
    written = []

    # 1. 写 settings 配置（hooks.json / settings.json）
    if config.get("settings"):
        out_rel, src_rel = config["settings"]
        src_path = REPO_ROOT / src_rel
        if src_path.exists():
            out_path = OUTPUT_ROOT / out_rel
            out_path.parent.mkdir(parents=True, exist_ok=True)
            # 模板文件含 _comment 字段，转写为干净的 settings.json
            content = src_path.read_text(encoding="utf-8")
            try:
                import json as _json
                tpl = _json.loads(content)
                # 删除 _ 开头的辅助字段
                clean = {k: v for k, v in tpl.items() if not k.startswith("_")}
                out_path.write_text(_json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
            except (_json.JSONDecodeError, ValueError):
                # 模板不是 JSON（如 Trae 的 sandbox-policy.json），原样写出
                out_path.write_text(content, encoding="utf-8")
            written.append(out_path)

    # 2. 复制脚本文件
    for out_rel, src_rel in config.get("scripts", []):
        src_path = REPO_ROOT / src_rel
        if src_path.exists():
            out_path = OUTPUT_ROOT / out_rel
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(src_path.read_text(encoding="utf-8"), encoding="utf-8")
            # 设置可执行位
            try:
                out_path.chmod(0o755)
            except OSError:
                pass
            written.append(out_path)

    # 3. 复制 constraints.yaml（机器可读规则源）
    if config.get("constraints"):
        out_rel, src_rel = config["constraints"]
        src_path = REPO_ROOT / src_rel
        if src_path.exists():
            out_path = OUTPUT_ROOT / out_rel
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(src_path.read_text(encoding="utf-8"), encoding="utf-8")
            written.append(out_path)

    return written


# ─── 默认链路（agentseed setup 用）──────────────────────

# 项目锚点 → Profile 自动识别表（与 core/persona-router.md §锚点识别 一致）
PROFILE_ANCHORS = {
    # 项目类型锚点（按文件/目录存在判定）
    "pyproject.toml": "coding",
    "package.json": "coding",
    "requirements.txt": "coding",
    "setup.py": "coding",
    "Cargo.toml": "coding",
    "go.mod": "coding",
    "pom.xml": "coding",
    "build.gradle": "coding",
    "manuscript.md": "novel",
    "novel.md": "novel",
    # paper 锚点：含 .tex / .bib / paper.md
    "main.tex": "paper",
    "paper.md": "paper",
    "references.bib": "paper",
    # agent-builder 锚点
    "agent.yaml": "agent-builder",
    "agent.json": "agent-builder",
}

# 意图关键词 → Profile（用户口语化请求匹配）
INTENT_KEYWORDS = {
    "coding": ["写代码", "开发", "bug", "重构", "code", "develop", "编程", "修复"],
    "novel": ["写小说", "小说", "章节", "novel", "story", "创作小说"],
    "default": ["问答", "调研", "对比", "信息检索", "general", "通用"],
    "paper": ["论文", "文献综述", "paper", "academic", "research paper", "投稿", "research"],
    "agent-builder": ["智能体", "agent", "bot", "助手", "构建 agent"],
}


def detect_tool_from_cwd() -> str:
    """从当前工作目录自动检测用户用的 AI 工具。

    检测顺序：先看项目里已存在的工具配置目录/文件，
    多个匹配时取第一个（用户可显式 --tool 覆盖）。
    无匹配时回退到 agents-md（跨工具标准，20+ 平台原生读取）。
    """
    cwd = Path.cwd()
    for marker, tool in PLATFORM_DETECT_MARKERS:
        path = cwd / marker
        if path.exists() or path.is_dir():
            return tool
    return "agents-md"


def detect_profile_from_cwd(user_intent: str = "") -> str:
    """从当前工作目录的项目锚点 + 用户意图关键词自动识别 Profile。
    user_intent 非空时优先匹配意图关键词。
    """
    cwd = Path.cwd()

    # 1. 用户意图关键词优先
    if user_intent:
        intent_lower = user_intent.lower()
        for profile, kws in INTENT_KEYWORDS.items():
            if any(kw.lower() in intent_lower for kw in kws):
                return profile

    # 2. 项目锚点
    for anchor, profile in PROFILE_ANCHORS.items():
        if (cwd / anchor).exists():
            return profile

    # 3. 默认回退：coding（软件开发是最常见场景）
    return "coding"


def setup_default(
    user_intent: str = "",
    output_dir: Path | None = None,
) -> dict:
    """零配置默认链路：自动检测 profile + tool + emit-constraints + write。
    返回 {"profile": ..., "tool": ..., "output": ..., "ruleset_size": ..., "hook_files": [...]}
    """
    # 刷新资源根
    refresh_resources_root()

    profile = detect_profile_from_cwd(user_intent)
    tool = detect_tool_from_cwd()
    if output_dir is None:
        output_dir = Path.cwd().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    set_output_root(output_dir)

    try:
        ruleset = build_ruleset(profile, mode="skeleton")
        out_path = write_tool_file(tool, profile, ruleset, mode="skeleton")

        # 默认开启 emit-constraints（hook 是核心价值）
        hook_files = []
        if tool in HOOK_PLATFORMS:
            hook_files = emit_constraints(tool)

        return {
            "profile": profile,
            "tool": tool,
            "output": str(output_dir),
            "ruleset_path": str(out_path),
            "ruleset_size": len(ruleset),
            "hook_files": [str(f) for f in hook_files],
        }
    finally:
        reset_output_root()


def merge_user_platforms() -> None:
    """将用户添加的平台并入 TOOL_OUTPUT / TOOL_CHAR_LIMIT（幂等）。

    用户平台默认按 markdown 格式写入口文件；若配置了 hooks 目录则登记到
    HOOK_PLATFORMS 以便 emit_constraints 分发钩子配置。
    """
    try:
        from .platforms import load_user_platforms
    except ImportError:
        return
    user_p = load_user_platforms()
    if not user_p:
        return
    changed = False
    for pid, p in user_p.items():
        if pid in TOOL_OUTPUT:
            continue  # 内置优先，不覆盖
        entry = p.get("entry")
        if not entry:
            continue
        TOOL_OUTPUT[pid] = entry
        if p.get("char_limit"):
            TOOL_CHAR_LIMIT[pid] = int(p["char_limit"])
        if p.get("hooks", {}).get("enabled") and p.get("hooks", {}).get("dir"):
            # 用户平台钩子：配置文件模板不存在，登记空条目（emit 时跳过）
            HOOK_PLATFORMS[pid] = {
                "settings": None,
                "scripts": [],
                "constraints": None,
                "dir": p["hooks"]["dir"],
            }
        changed = True
    return changed


def _shard_root(tool: str) -> Path:
    """限长平台的分片目录根（写入位置由 OUTPUT_ROOT 决定）"""
    out_rel = TOOL_OUTPUT[tool]
    # .windsurfrules -> .windsurfrules.d/；.lingma/rules/project.md -> .lingma/rules/
    out_path = OUTPUT_ROOT / out_rel
    if out_path.suffix in (".md", ".mdr", ".mdc"):
        shard_dir = out_path.parent / f"{out_path.stem}.d"
    else:
        shard_dir = OUTPUT_ROOT / f"{out_rel}.d"
    shard_dir.mkdir(parents=True, exist_ok=True)
    return shard_dir


def _shard_listing(tool: str, profile_id: str) -> list:
    """返回该 profile 在该 tool 下生成的分片文件相对路径列表（相对 OUTPUT_ROOT）"""
    shard_dir = _shard_root(tool)
    if not shard_dir.exists():
        return []
    return sorted(str(p.relative_to(OUTPUT_ROOT)) for p in shard_dir.glob("*"))


def _byte_len(s: str) -> int:
    """UTF-8 字节长度（平台限制以字节为准，中文 3 字节/字符）"""
    return len(s.encode("utf-8"))


def _truncate_to_bytes(s: str, max_bytes: int, suffix: str = "") -> str:
    """按 UTF-8 字节长度截断字符串，不切断多字节字符。"""
    if _byte_len(s) <= max_bytes:
        return s + suffix
    # 二分查找最大字符数
    lo, hi = 0, len(s)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _byte_len(s[:mid]) <= max_bytes:
            lo = mid
        else:
            hi = mid - 1
    return s[:lo] + suffix


def _build_sharded_entry(tool: str, profile_id: str, full_content: str, limit: int) -> str:
    """生成限长平台的入口文件：保留 ADAPTER + CORE LAYER + ON-DEMAND INDEX 头，强制 UTF-8 字节 < limit"""
    # 截取 CORE LAYER 段
    m = re.search(r"(# === CORE LAYER.*?)(?=# === PROFILE LAYER|$)", full_content, re.S)
    core = m.group(1) if m else ""
    m = re.search(r"(# === ON-DEMAND INDEX.*)", full_content, re.S)
    index = m.group(1) if m else ""
    # 截取 ADAPTER OVERRIDE 段（若有）
    m = re.search(r"(# === ADAPTER OVERRIDE.*?)(?=# === |$)", full_content, re.S)
    adapter = m.group(1) if m else ""

    shard_dir = _shard_root(tool)
    shard_rel = shard_dir.relative_to(OUTPUT_ROOT)
    header = (
        f"<!-- {tool} 入口文件 | profile: {profile_id} | mode: skeleton-sharded | 禁止手工编辑 -->\n"
        f"<!-- 本平台单文件字节上限 {limit}，规则已拆分到 {shard_rel}/ 目录 -->\n"
        f"<!-- 完整规则请逐个 Read 该目录下的分片文件 -->\n\n"
    )
    footer = f"\n\n> ⚠ 入口已截断。完整索引见 {shard_rel}/INDEX.md\n"
    # 按 UTF-8 字节计算预算（中文 3 字节/字符，按字符数会低估实际大小）
    # adapter 优先保留（平台专属使用说明），不计入预算扣减
    adapter_budget = _byte_len(adapter)
    reserve = _byte_len(header) + _byte_len(footer) + adapter_budget + 50
    # 分配预算：CORE 占 60%，INDEX 占 40%
    core_budget = int((limit - reserve) * 0.6)
    index_budget = limit - reserve - core_budget

    # 截断 CORE
    if _byte_len(core) > core_budget:
        core = _truncate_to_bytes(core, core_budget - 60,
                                  "\n> ⚠ CORE 段已截断，完整内容见分片目录\n")

    # 截断 INDEX：保留 Skills 表优先
    if _byte_len(index) > index_budget:
        # 尝试截到 Skills 表结束
        m = re.search(r"(.*?## Skills \(按需\)\n(?:\|[^\n]*\n)+)", index, re.S)
        if m and _byte_len(m.group(1)) <= index_budget:
            index = m.group(1)
        else:
            # 截到 Skills 表头之前
            m = re.search(r"(.*?## Skills \(按需\)\n)", index, re.S)
            if m and _byte_len(m.group(1)) <= index_budget:
                index = m.group(1) + "> 完整 Skills 列表见 INDEX.md\n"
            else:
                index = _truncate_to_bytes(index, index_budget - 60, "\n> ⚠ INDEX 已截断\n")

    # 组装：adapter 在最前（平台专属说明），然后 CORE，然后 INDEX
    parts = [header]
    if adapter:
        parts.append(adapter + "\n\n")
    parts.append(core)
    parts.append("\n\n")
    parts.append(index)
    parts.append(footer)
    entry = "".join(parts)
    # 终极兜底：硬截断（按字节）
    if _byte_len(entry) > limit:
        entry = _truncate_to_bytes(entry, limit - 80,
                                   "\n\n> ⚠ 硬截断。完整索引见 {}/INDEX.md\n".format(shard_rel))
    return entry


def _write_oversized_shard(base_path: Path, content: str, limit: int) -> None:
    """单段（如 agent-builder AGENTS.md）按行切分到多个文件 base_path, base_path-02, -03, ..."""
    base_path.parent.mkdir(parents=True, exist_ok=True)
    stem = base_path.stem
    suffix = base_path.suffix
    part = 0
    buf = []
    buf_bytes = 0
    for line in content.splitlines(keepends=True):
        line_bytes = _byte_len(line)
        if buf_bytes + line_bytes > limit and buf:
            part += 1
            (base_path.parent / f"{stem}-{part:02d}{suffix}").write_text(
                "".join(buf), encoding="utf-8"
            )
            buf = []
            buf_bytes = 0
        buf.append(line)
        buf_bytes += line_bytes
    if buf:
        part += 1
        (base_path.parent / f"{stem}-{part:02d}{suffix}").write_text(
            "".join(buf), encoding="utf-8"
        )


def _write_sharded(tool: str, profile_id: str, full_content: str, limit: int) -> None:
    """把完整 ruleset 按 # === 段切分，每个段写入独立文件"""
    shard_dir = _shard_root(tool)
    # 清空旧分片
    for old in shard_dir.glob("*"):
        old.unlink()

    # 写一个 INDEX.md（完整索引表）
    m = re.search(r"(# === ON-DEMAND INDEX.*)", full_content, re.S)
    if m:
        (shard_dir / "INDEX.md").write_text(
            f"<!-- {profile_id} 完整按需索引 -->\n\n" + m.group(1),
            encoding="utf-8",
        )

    # 按 LAYER 切分主内容
    sections = re.split(r"(?=^# === (?:CORE LAYER|PROFILE LAYER|ON-DEMAND INDEX))", full_content, flags=re.M)
    idx = 0
    for sec in sections:
        sec = sec.strip()
        if not sec or not sec.startswith("# === "):
            continue
        m = re.match(r"# === ([A-Z ]+)", sec)
        name = (m.group(1).strip().lower().replace(" ", "-") if m else f"sec-{idx}")
        # 若段本身超 limit，进一步按 ## 切分（按 UTF-8 字节判断）
        if _byte_len(sec) <= limit:
            idx += 1
            (shard_dir / f"{idx:02d}-{name}.md").write_text(sec, encoding="utf-8")
        else:
            sub_idx = 0
            for sub in re.split(r"(?=^## \[)", sec, flags=re.M):
                sub = sub.strip()
                if not sub:
                    continue
                sub_idx += 1
                idx += 1
                fname = f"{idx:02d}-{name}-{sub_idx:02d}.md"
                # 单个子段仍可能超 limit（如 agent-builder 的 AGENTS.md），按字节再切
                if _byte_len(sub) <= limit:
                    (shard_dir / fname).write_text(sub, encoding="utf-8")
                else:
                    # 按 ## 段落进一步无法切分时，按字符行切分
                    _write_oversized_shard(shard_dir / fname, sub, limit)


def write_provenance(tool: str, profile_id: str, content: str,
                     mode: str = "skeleton", sharded: bool = False,
                     extra_files: list = None) -> None:
    """记录本次生成产物的溯源信息到 provenance/"""
    PROV_DIR = OUTPUT_ROOT / "provenance"
    PROV_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    rec = {
        "generated_at": ts,
        "profile": profile_id,
        "tool": tool,
        "mode": mode,
        "sharded": sharded,
        "output": TOOL_OUTPUT[tool],
        "hash": hashlib.sha256(content.encode("utf-8")).hexdigest()[:16],
        "size": len(content),
        "extra_files": extra_files or [],
    }
    (PROV_DIR / f"{profile_id}-{tool}.json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ─── 验证（CI 硬断言）─────────────────────────────────

def verify_ruleset(profile_id: str = None, strict_budget: bool = True) -> dict:
    """对一个或全部 profile 做 skeleton 模式硬断言验证。

    断言项（任一失败即抛 AssertionError，CI 可拦截）：
    1. 产物大小 ≤ SKELETON_BUDGET_BYTES（strict_budget=True 时）
    2. P0 红线章节必须内联（不能 deferred）
    3. deferred 章节内容仍在源文件中（内容不变性）
    4. ON-DEMAND INDEX 含必要段（Skills/Capabilities/MCP/Loading Protocol）

    返回每个 profile 的验证报告 dict。失败时抛 AssertionError。
    """
    profiles = [profile_id] if profile_id else list_profiles()
    reports = {}

    for pid in profiles:
        manifest = parse_manifest(pid)
        # 1. build skeleton
        ruleset = build_ruleset(pid, mode="skeleton")
        size = len(ruleset)

        # 2. 预算断言
        budget_ok = size <= SKELETON_BUDGET_BYTES
        if strict_budget and not budget_ok:
            raise AssertionError(
                f"[verify] {pid}: skeleton 产物 {size}B 超预算 {SKELETON_BUDGET_BYTES}B "
                f"(超出 {size - SKELETON_BUDGET_BYTES}B)。"
                f"建议降低 PROFILE_LAYER_BUDGET 或压缩 ON-DEMAND INDEX。"
            )

        # 3. P0 红线不应被 deferred（应内联在 PROFILE LAYER）
        # 检查所有触发拆分的 profile 文件，看 deferred 章节中是否含 P0 关键词
        p0_deferred = []
        # 4. 检查 deferred 章节内容仍在源文件
        deferred_lost = []
        for pf in manifest["includes"].get("profile", []):
            prof_path = REPO_ROOT / pf
            if not prof_path.exists():
                continue
            content = expand_refs(read_file(Path(pf)), prof_path.parent, inline=False)
            if len(content) <= PROFILE_LAYER_BUDGET:
                continue
            _, deferred = _split_profile_content(content, PROFILE_LAYER_BUDGET, pf)
            src_text = prof_path.read_text(encoding="utf-8")
            for title, _ in deferred:
                # P0 检查：deferred 章节标题含 P0 关键词说明 P0 被错误拆出
                if any(kw.lower() in title.lower() for kw in P0_KEYWORDS):
                    p0_deferred.append((pf, title))
                # 内容完整性检查：title 关键部分应在源文件中
                key = title.split("(")[0].strip().lstrip("#").strip()
                if key.startswith("<"):
                    if key not in src_text:
                        deferred_lost.append((pf, title))
                else:
                    if key and key not in src_text:
                        deferred_lost.append((pf, title))

        if p0_deferred:
            raise AssertionError(
                f"[verify] {pid}: P0 章节被错误地拆到 deferred（应内联）: {p0_deferred}"
            )

        if deferred_lost:
            raise AssertionError(
                f"[verify] {pid}: deferred 章节内容在源文件中找不到（内容丢失！）: {deferred_lost}"
            )

        # 5. INDEX 必要段（用前缀匹配，避免括号内描述差异导致误报）
        index_required = ["## SKILLS LAYER (按需", "## Capabilities (按需", "## MCP (按需", "## Loading Protocol"]
        missing_index = [seg for seg in index_required if seg not in ruleset]
        if missing_index:
            raise AssertionError(
                f"[verify] {pid}: ON-DEMAND INDEX 缺必要段: {missing_index}"
            )

        # 6. PROJECT.md 引用断言（governance §8 要求 PROJECT.md 作为仓库导航入口）
        #    生成文件中应含 PROJECT.md 字符串引用（在 CORE LAYER 的 governance §8 内联段中）
        if "PROJECT.md" not in ruleset:
            raise AssertionError(
                f"[verify] {pid}: 生成产物未引用 PROJECT.md（governance §8 要求）。"
                f"请检查 core/governance.md 是否含 PROJECT.md 引用条款。"
            )

        # 7. mutually_exclusive_with 对称性断言
        #    A 声明与 B 互斥，B 必须也声明与 A 互斥
        mutex_asymmetry = []
        for enemy in manifest.get("mutually_exclusive_with", []):
            try:
                enemy_manifest = parse_manifest(enemy)
            except FileNotFoundError:
                mutex_asymmetry.append((enemy, "manifest 不存在"))
                continue
            reverse = enemy_manifest.get("mutually_exclusive_with", [])
            if pid not in reverse:
                mutex_asymmetry.append((enemy, f"反向未声明 {pid}"))
        if mutex_asymmetry:
            raise AssertionError(
                f"[verify] {pid}: mutually_exclusive_with 不对称: {mutex_asymmetry}"
            )

        # 8. enables_capabilities 与 forbids_capabilities 无交集断言
        enables = set(manifest.get("enables_capabilities", []))
        forbids = set(manifest.get("forbids_capabilities", []))
        cap_conflict = enables & forbids
        if cap_conflict:
            raise AssertionError(
                f"[verify] {pid}: enables_capabilities 与 forbids_capabilities 冲突: {cap_conflict}"
            )

        # 9. DOMAIN_QUALITY_GATES 表中的 skill 路径真实存在断言
        #    防止 agent 按表去 Read 一个不存在的文件
        missing_gates = []
        for gate_profile, gates in DOMAIN_QUALITY_GATES.items():
            if gate_profile != pid:
                continue
            for scene_name, skill_path, formula, threshold in gates:
                # 提取路径（去掉 § 章节）
                path_str = skill_path.split(" §")[0].split(" ")[0]
                gate_file = REPO_ROOT / path_str
                if not gate_file.exists():
                    missing_gates.append((scene_name, skill_path, str(gate_file)))
        if missing_gates:
            raise AssertionError(
                f"[verify] {pid}: DOMAIN_QUALITY_GATES 引用了不存在的 skill 文件: {missing_gates}"
            )

        # 10. constraints.yaml 完整性断言（机器可读规则源必须有效）
        #     每条约束必须有 id/description/severity/enforce_at/intercept_tools/match/action/message
        #     只在第一次循环时检查（constraints.yaml 是全局的，不区分 profile）
        if pid == sorted(profiles)[0]:
            constraints_issues = _verify_constraints_yaml()
            if constraints_issues:
                raise AssertionError(
                    f"[verify] core/constraints.yaml 校验失败: {constraints_issues}"
                )

        reports[pid] = {
            "size": size,
            "budget_ok": budget_ok,
            "budget_margin": SKELETON_BUDGET_BYTES - size,
            "p0_inlined": len(p0_deferred) == 0,
            "deferred_intact": len(deferred_lost) == 0,
            "index_complete": len(missing_index) == 0,
            "mutex_symmetric": len(mutex_asymmetry) == 0,
            "capabilities_consistent": len(cap_conflict) == 0,
            "gates_files_exist": len(missing_gates) == 0,
        }

    return reports


def _verify_constraints_yaml() -> list:
    """校验 core/constraints.yaml 结构完整性。
    返回 issue 列表（空列表表示通过）。
    """
    issues = []
    constraints_path = CORE_DIR / "constraints.yaml"
    if not constraints_path.exists():
        return ["core/constraints.yaml 不存在"]

    text = constraints_path.read_text(encoding="utf-8")
    # 简单 YAML 解析（不依赖 PyYAML，避免引入依赖）
    # 检查每个 constraint 块都有必需字段
    required_fields = ["id:", "severity:", "enforce_at:", "action:", "message:"]
    # 用 - id: 作为分隔
    blocks = re.split(r"\n\s*-\s+id:\s+", text)
    if len(blocks) <= 1:
        return ["未找到任何 constraint 块"]

    for i, block in enumerate(blocks[1:], 1):
        block_id = block.split("\n", 1)[0].strip()
        for field in required_fields[1:]:  # 跳过 id（已用于分隔）
            if field not in block:
                issues.append(f"constraint #{i} ({block_id}): 缺字段 {field}")

    # 检查 meta 段
    if "platforms_supported:" not in text:
        issues.append("缺 meta.platforms_supported 段")
    if "claude-code" not in text:
        issues.append("meta.platforms_supported 缺 claude-code 平台")
    if "cursor" not in text:
        issues.append("meta.platforms_supported 缺 cursor 平台")

    return issues


# ─── CLI ─────────────────────────────────────────────

def list_profiles() -> list:
    return sorted(p.name for p in PERSONAS_DIR.iterdir() if p.is_dir() and (p / "persona.yaml").exists())


def main():
    # 合并用户添加的平台（幂等）
    merge_user_platforms()

    parser = argparse.ArgumentParser(description="统一规则中枢同步 v2")
    parser.add_argument("--list", action="store_true", help="列出可用 profile")
    parser.add_argument("--profile", type=str, help="选择主 profile")
    parser.add_argument("--tool", type=str, default="claude-code",
                        choices=list(TOOL_OUTPUT.keys()) + ["all"],
                        help="目标工具")
    parser.add_argument("--mode", type=str, default="skeleton",
                        choices=["skeleton", "full"],
                        help="skeleton（默认，按需索引）/ full（全量内联，旧行为）")
    args = parser.parse_args()

    if args.list:
        print("可用 Profile:")
        for p in list_profiles():
            print(f"  - {p}")
        return

    if not args.profile:
        print("error: 必须指定 --profile，或用 --list 查看", file=sys.stderr)
        sys.exit(1)

    if args.profile not in list_profiles():
        print(f"error: 未知 profile '{args.profile}'，可用: {list_profiles()}", file=sys.stderr)
        sys.exit(1)

    ruleset = build_ruleset(args.profile, mode=args.mode)
    tools = list(TOOL_OUTPUT.keys()) if args.tool == "all" else [args.tool]

    budget_status = "✓ 预算内" if len(ruleset) <= SKELETON_BUDGET_BYTES else "✗ 超预算"
    print(f"装配 profile={args.profile} mode={args.mode}")
    print(f"规则集大小: {len(ruleset)} 字符 (预算 {SKELETON_BUDGET_BYTES}) {budget_status}")
    seen_outputs = set()
    for tool in tools:
        out_rel = TOOL_OUTPUT.get(tool, "")
        if out_rel in seen_outputs:
            print(f"  ⚡ 跳过 {tool}（与已同步平台写同一文件 {out_rel}）")
            continue
        seen_outputs.add(out_rel)
        out_path = write_tool_file(tool, args.profile, ruleset, mode=args.mode)
        extra = ""
        char_limit = TOOL_CHAR_LIMIT.get(tool)
        if char_limit:
            extra = f" [limit={char_limit}, {'分片' if len(ruleset) > char_limit else '单文件'}]"
        try:
            rel = out_path.relative_to(REPO_ROOT)
        except ValueError:
            rel = out_path
        print(f"  [{tool}] -> {rel}{extra}")


if __name__ == "__main__":
    main()
