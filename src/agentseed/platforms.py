"""
Platform Registry — 声明式平台注册表。

支持两种注册方式：
  1. 代码级注册（内置平台，TOOL_OUTPUT / HOOK_PLATFORMS）
  2. 配置文件注册（adapters/platforms.yaml，用户可编辑）

格式（YAML）:
  platforms:
    <id>:
      name: <显示名>
      entry: <入口文件路径>          # 相对项目根目录
      format: <plain|markdown|cursor|comate>  # 默认 markdown
      char_limit: <数字>             # 可选，skeleton 分片阈值
      hooks:
        enabled: true|false
        dir: <.xxx 目录名>           # 检测用
        config_file: <配置文件路径>  # 如 settings.json
        script: <hook 脚本路径>      # 如 pre_tool_use.py

导入新平台：
  agentseed platform import           # 交互式引导
  agentseed platform import <id>      # 非交互，--name/--entry/--format 参数
  agentseed platform list             # 列出所有已注册平台
  agentseed platform validate <id>    # 验证平台配置
  agentseed platform remove <id>      # 移除用户添加的平台（内置不可删）
  agentseed platform export <id>      # 导出平台配置为 YAML 片段
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

# ─── 内置平台注册表 ────────────────────────────────────────────────────────

BUILTIN_PLATFORMS: Dict[str, dict] = {
    "claude-code": {
        "name": "Claude Code",
        "entry": "CLAUDE.md",
        "format": "markdown",
        "builtin": True,
        "hooks": {
            "enabled": True,
            "dir": ".claude",
            "settings": ("settings.json", "adapters/hooks/claude-code/settings.json.template"),
            "scripts": [
                ("adapters/hooks/claude-code/pre_tool_use.py", "adapters/hooks/claude-code/pre_tool_use.py"),
                ("adapters/hooks/shared/check.py", "adapters/hooks/shared/check.py"),
            ],
            "constraints": ("core/constraints.yaml", "core/constraints.yaml"),
        },
    },
    "cursor": {
        "name": "Cursor",
        "entry": ".cursor/rules/project.mdc",
        "format": "cursor",
        "builtin": True,
        "hooks": {
            "enabled": True,
            "dir": ".cursor",
            "settings": (".cursor/hooks.json", "adapters/hooks/cursor/hooks.json.template"),
            "scripts": [
                ("adapters/hooks/cursor/pre_tool_use.py", "adapters/hooks/cursor/pre_tool_use.py"),
                ("adapters/hooks/shared/check.py", "adapters/hooks/shared/check.py"),
            ],
            "constraints": ("core/constraints.yaml", "core/constraints.yaml"),
        },
    },
    "copilot": {
        "name": "GitHub Copilot",
        "entry": ".github/copilot-instructions.md",
        "format": "markdown",
        "builtin": True,
        "hooks": {"enabled": False},
    },
    "gemini": {
        "name": "Google Gemini (AI Studio)",
        "entry": "GEMINI.md",
        "format": "markdown",
        "builtin": True,
        "hooks": {
            "enabled": True,
            "dir": ".gemini",
            "settings": (".gemini/hooks.json", "adapters/hooks/gemini/hooks.json.template"),
            "scripts": [
                ("adapters/hooks/gemini/pre_tool_use.py", "adapters/hooks/gemini/pre_tool_use.py"),
                ("adapters/hooks/shared/check.py", "adapters/hooks/shared/check.py"),
            ],
            "constraints": ("core/constraints.yaml", "core/constraints.yaml"),
        },
    },
    "windsurf": {
        "name": "Windsurf (Codeium)",
        "entry": ".windsurfrules",
        "format": "markdown",
        "char_limit": 12000,
        "builtin": True,
        "hooks": {"enabled": False},
    },
    "cline": {
        "name": "Cline",
        "entry": ".clinerules/project.md",
        "format": "markdown",
        "builtin": True,
        "hooks": {
            "enabled": True,
            "dir": ".cline",
            "settings": (".cline/hooks.json", "adapters/hooks/cline/hooks.json.template"),
            "scripts": [
                ("adapters/hooks/cline/pre_tool_use.py", "adapters/hooks/cline/pre_tool_use.py"),
                ("adapters/hooks/shared/check.py", "adapters/hooks/shared/check.py"),
            ],
            "constraints": ("core/constraints.yaml", "core/constraints.yaml"),
        },
    },
    "continue": {
        "name": "Continue",
        "entry": ".continue/rules/project.md",
        "format": "markdown",
        "builtin": True,
        "hooks": {"enabled": False},
    },
    "amazon-q": {
        "name": "Amazon Q Developer",
        "entry": ".amazonq/rules/project.md",
        "format": "markdown",
        "builtin": True,
        "hooks": {"enabled": False},
    },
    "trae": {
        "name": "Trae",
        "entry": ".trae/rules/project_rules.md",
        "format": "markdown",
        "builtin": True,
        "hooks": {
            "enabled": True,
            "dir": ".trae",
            "settings": (".trae/sandbox-policy.json", "adapters/hooks/trae/sandbox-policy.json"),
            "scripts": [],
            "constraints": None,
        },
    },
    "codex": {
        "name": "OpenAI Codex / ChatGPT",
        "entry": "AGENTS.md",
        "format": "markdown",
        "builtin": True,
        "hooks": {
            "enabled": True,
            "dir": ".codex",
            "settings": (".codex/hooks.json", "adapters/hooks/codex/hooks.json.template"),
            "scripts": [
                ("adapters/hooks/codex/pre_tool_use.py", "adapters/hooks/codex/pre_tool_use.py"),
                ("adapters/hooks/shared/check.py", "adapters/hooks/shared/check.py"),
            ],
            "constraints": ("core/constraints.yaml", "core/constraints.yaml"),
        },
    },
    "agents-md": {
        "name": "AGENTS.md (Universal)",
        "entry": "AGENTS.md",
        "format": "markdown",
        "builtin": True,
        "hooks": {"enabled": False},
        "note": "被 20+ 平台原生读取（通用标准）",
    },
    "qwenwork": {
        "name": "千问办公 (QwenWork)",
        "entry": "AGENTS.md",
        "format": "markdown",
        "builtin": True,
        "hooks": {"enabled": False},
        "note": "原生读取 AGENTS.md（awareness 规则模式）",
    },
    "qodo": {
        "name": "Qodo (Former Codium)",
        "entry": "best_practices.md",
        "format": "markdown",
        "builtin": True,
        "hooks": {"enabled": False},
    },
    "lingma": {
        "name": "通义灵码 (Lingma)",
        "entry": ".lingma/rules/project.md",
        "format": "markdown",
        "char_limit": 10000,
        "builtin": True,
        "hooks": {"enabled": False},
    },
    "comate": {
        "name": "腾讯云代码助手 (Comate)",
        "entry": ".comate/rules/project.mdr",
        "format": "comate",
        "char_limit": 10000,
        "builtin": True,
        "hooks": {"enabled": False},
    },
}

# 内置检测信号（detect_tool_from_cwd 用）
BUILTIN_TOOL_SIGNALS: Dict[str, str] = {
    ".claude": "claude-code",
    ".cursor": "cursor",
    ".gemini": "gemini",
    ".cline": "cline",
    ".codex": "codex",
    ".trae": "trae",
    ".windsurfrules": "windsurf",
    ".continue": "continue",
    ".amazonq": "amazonq",
    ".lingma": "lingma",
    ".comate": "comate",
    ".github/copilot-instructions.md": "copilot",
    "CLAUDE.md": "claude-code",
    "GEMINI.md": "gemini",
    "best_practices.md": "qodo",
}


# ─── 用户平台配置 ─────────────────────────────────────────────────────────

def _get_config_path() -> Path:
    """用户平台配置的路径（放在仓库 adapters/ 下，随 git 追踪）"""
    from . import sync_rules as _sr
    return _sr.REPO_ROOT / "adapters" / "platforms.yaml"


def load_user_platforms() -> Dict[str, dict]:
    """加载用户添加的平台配置（adapters/platforms.yaml）"""
    cfg_path = _get_config_path()
    if not cfg_path.exists():
        return {}
    try:
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        return data.get("platforms", {})
    except Exception as e:
        print(f"[platforms] 配置加载失败: {e}", file=sys.stderr)
        return {}


def save_user_platforms(platforms: Dict[str, dict]) -> None:
    """保存用户平台配置"""
    cfg_path = _get_config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        "# AgentSeed 平台配置 — 由 agentseed platform import/remove 命令管理\n"
        "# 格式参考: https://github.com/agentseed/docs/platforms\n\n"
        + yaml.safe_dump({"platforms": platforms}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def get_all_platforms() -> Dict[str, dict]:
    """合并内置 + 用户平台"""
    merged = dict(BUILTIN_PLATFORMS)
    merged.update(load_user_platforms())
    return merged


def get_platform(platform_id: str) -> Optional[dict]:
    """获取单个平台配置（含内置和用户添加）"""
    return get_all_platforms().get(platform_id)


def resolve_tool_outputs() -> Dict[str, dict]:
    """合并所有平台为 {id: {entry, format, char_limit, hooks}} 字典。

    供 sync/apply 命令使用：既能处理内置平台，也能处理用户添加的平台。
    """
    result = {}
    for pid, p in get_all_platforms().items():
        result[pid] = {
            "entry": p["entry"],
            "format": p.get("format", "markdown"),
            "char_limit": p.get("char_limit"),
            "hooks": p.get("hooks", {}).get("enabled", False),
        }
    return result


def list_platforms(include_hidden: bool = False) -> List[dict]:
    """列出所有平台（返回列表方便展示）"""
    all_p = get_all_platforms()
    result = []
    for pid, p in all_p.items():
        if not include_hidden and p.get("hidden"):
            continue
        result.append({
            "id": pid,
            "name": p.get("name", pid),
            "entry": p["entry"],
            "format": p.get("format", "markdown"),
            "char_limit": p.get("char_limit"),
            "builtin": p.get("builtin", False),
            "hooks": p.get("hooks", {}).get("enabled", False),
            "note": p.get("note", ""),
        })
    return sorted(result, key=lambda x: 0 if x["builtin"] else 1)


def add_platform(
    platform_id: str,
    name: str,
    entry: str,
    format: str = "markdown",
    char_limit: Optional[int] = None,
    hook_dir: Optional[str] = None,
) -> None:
    """添加用户平台（写入 platforms.yaml）"""
    platforms = load_user_platforms()
    if platform_id in BUILTIN_PLATFORMS:
        raise ValueError(f"平台 {platform_id} 是内置平台，不可重复添加。")
    if platform_id in platforms:
        raise ValueError(f"平台 {platform_id} 已存在（用户配置中）。使用 --force 覆盖，或先 remove。")

    p = {
        "name": name,
        "entry": entry,
        "format": format,
        "builtin": False,
        "hooks": {"enabled": bool(hook_dir), "dir": hook_dir} if hook_dir else {"enabled": False},
    }
    if char_limit:
        p["char_limit"] = char_limit

    platforms[platform_id] = p
    save_user_platforms(platforms)
    # 自动生成钩子模板
    if hook_dir:
        generate_hooks(platform_id, hook_dir)


def generate_hooks(platform_id: str, hook_dir: str) -> dict:
    """为新平台自动生成钩子模板文件.

    Creates under adapters/hooks/<platform_id>/:
      - pre_tool_use.py       (pre-tool-use interceptor script)
      - hooks.json.template   (Hook config template)
      - README.md             (installation guide)

    所有模板都用 list+chr() 构造，不用 .format() 避免大括号冲突。
    中文字符用 chr() 拼接（确保 Windows GBK 环境也能写出 UTF-8 文件）。
    """
    from . import sync_rules as _sr
    hooks_root = _sr.REPO_ROOT / "adapters" / "hooks" / platform_id
    hooks_root.mkdir(parents=True, exist_ok=True)
    created = []

    # 常用中文字符的 chr() 编码（高频复用）
    def _ZHB(s):
        """直接返回字符串 s 本身（写入文件时用 encoding='utf-8'）。"""
        return s

    # ============ 1. pre_tool_use.py ============
    tool_script = hooks_root / "pre_tool_use.py"
    if not tool_script.exists():
        # 文档字符串：英文 docstring + 中文注释通过 chr() 拼接
        # 纯 ASCII 模板，避免 format() 大括号陷阱
        py_lines = [
            '"""AgentSeed ' + platform_id + ' PreToolUse Hook - Pre-tool-use interceptor.',
            "",
            "Auto-generated by agentseed platform import.",
            "Install steps: see README.md in this directory.",
            "Core logic: calls decide() from adapters/hooks/shared/check.py.",
            "Constraint source: core/constraints.yaml (loaded by agentseed forge --emit-constraints).",
            '"""',
            "from __future__ import annotations",
            "import json, sys",
            "from pathlib import Path",
            "",
            "_HOOKS_DIR = Path(__file__).resolve().parent.parent",
            '_SHARED = _HOOKS_DIR / "shared"',
            "sys.path.insert(0, str(_SHARED))",
            "from check import decide",
            "",
            "def main():",
            "    try:",
            "        raw = sys.stdin.read()",
            '        if not raw.strip():',
            '            print(json.dumps({"allow": True}))',
            "            return",
            "        data = json.loads(raw)",
            '        tool_name = data.get("tool_name", "")',
            '        tool_input = data.get("tool_input", {})',
            '        tool_args = data.get("tool_args", {})',
            "        tool_input.update(tool_args)",
            "        result = decide(",
            "            tool_name=tool_name,",
            "            tool_input=tool_input,",
            "        )",
            "        print(json.dumps({",
            '            "allow": not result.get("deny", False),',
            '            "reason": result.get("recommendation") or result.get("message", ""),',
            "        }))",
            "    except Exception as e:",
            "        # fail-open: 出错时默认放行，避免影响用户体验",
            '        print(json.dumps({"allow": True, "reason": f"Hook error (fail-open): {e}"}))',
            "",
            'if __name__ == "__main__":',
            "    main()",
            "",
        ]
        tool_script.write_text("\n".join(py_lines), encoding="utf-8")
        created.append(tool_script)

    # ============ 2. hooks.json.template ============
    template = hooks_root / "hooks.json.template"
    if not template.exists():
        # JSON 模板：含中文用 chr() 拼接
        ZH_SETUP = _ZHB("1) 确保 adapters/hooks/ 目录在项目根 2) 复制本模板为 hooks.json 或 settings.json（按平台要求）3) 修改 command 路径指向 pre_tool_use.py")
        ZH_COMMENT = _ZHB(" Hook 配置模板。参考同目录 README.md 安装指引。")
        json_lines = [
            "{",
            f'  "_comment": "' + platform_id + '",',
            f'  "_comment_zh": "' + ZH_COMMENT + '",',
            f'  "_setup": "' + ZH_SETUP + '",',
            '  "preToolUse": [',
            f'    {{"command": "python ./adapters/hooks/{platform_id}/pre_tool_use.py"}}',
            "  ]",
            "}",
            "",
        ]
        template.write_text("\n".join(json_lines), encoding="utf-8")
        created.append(template)

    # ============ 3. README.md ============
    readme = hooks_root / "README.md"
    if not readme.exists():
        # README 中英混合（中文用 chr()）
        def CN(s):
            return _ZHB(s)
        md_lines = [
            f"# {platform_id} PreToolUse Hook",
            "",
            "AgentSeed-generated PreToolUse hook template for " + platform_id + " platform.",
            "",
            "## " + CN("安装步骤"),
            "",
            "1. **" + CN("确保 AgentSeed 已安装") + "**:",
            "   ```bash",
            "   pip install agentseed",
            "   ```",
            "",
            "2. **" + CN("复制钩子配置") + "**:",
            "   " + CN("将 `hooks.json.template` 重命名为你的平台要求的配置文件名，放到钩子目录（") + hook_dir + CN("/）下。"),
            "",
            "3. **" + CN("修改 command 路径") + "**:",
            "   " + CN("确保 `command` 指向正确的 `pre_tool_use.py` 路径。"),
            "",
            "4. **" + CN("测试") + "**:",
            "   " + CN("在项目里执行 `agentseed forge`，会同时同步规则 + 钩子配置。"),
            "",
            "## " + CN("工作原理"),
            "",
            "- " + CN("`pre_tool_use.py` 读取平台传来的工具调用信息，调用 `adapters/hooks/shared/check.py` 的 `decide()` 函数。"),
            "- " + CN("`decide()` 从 `core/constraints.yaml` 读取约束并决策："),
            "  - " + CN("P0 红线 → 直接拒绝"),
            "  - " + CN("P1 警告 → 允许但输出警告"),
            "  - " + CN("其他 → 放行"),
            "",
            "## " + CN("自定义"),
            "",
            "- " + CN("你可以修改 `pre_tool_use.py` 添加自定义拦截逻辑。"),
            "- " + CN("核心入口是 `decide(tool_name, tool_input)` 函数。"),
            "",
            "## " + CN("故障恢复"),
            "",
            "1. " + CN("重命名/删除 `hooks.json`（或平台对应的配置文件）"),
            "2. " + CN("重启 AI 工具"),
            "3. " + CN("钩子是 fail-open 设计：脚本出错默认放行"),
            "",
        ]
        readme.write_text("\n".join(md_lines), encoding="utf-8")
        created.append(readme)

    return {"files_created": [str(c) for c in created], "hook_dir": str(hooks_root)}



def remove_platform(platform_id: str) -> None:
    """移除用户添加的平台"""
    platforms = load_user_platforms()
    if platform_id not in platforms:
        raise ValueError(f"平台 {platform_id} 不存在或为内置平台。")
    del platforms[platform_id]
    save_user_platforms(platforms)


def export_platform(platform_id: str) -> str:
    """导出平台配置为 YAML 片段（用于分享）"""
    p = get_platform(platform_id)
    if not p:
        raise ValueError(f"平台 {platform_id} 不存在。")
    return yaml.safe_dump({"platforms": {platform_id: dict(p)}}, allow_unicode=True, sort_keys=False)


# ─── 工具检测 ─────────────────────────────────────────────────────────────

def detect_tool(cwd: Path) -> str:
    """从项目目录检测 AI 工具。检测顺序：用户平台目录 → 内置平台目录 → 默认"""
    # 用户平台优先（允许覆盖内置检测）
    user_platforms = load_user_platforms()
    for pid, p in user_platforms.items():
        hook = p.get("hooks", {})
        if hook.get("enabled") and hook.get("dir"):
            if (cwd / hook["dir"]).exists():
                return pid
        # 用 entry 路径检测（不依赖 hook dir）
        entry = p.get("entry", "")
        if entry and (cwd / entry).exists():
            return pid

    # 内置平台
    for signal, tool_id in BUILTIN_TOOL_SIGNALS.items():
        if "/" in signal:
            if (cwd / signal).exists():
                return tool_id
        else:
            if (cwd / signal).is_dir() or (cwd / signal).exists():
                return tool_id

    return "agents-md"


# ─── CLI 交互式引导 ───────────────────────────────────────────────────────

def interactive_import() -> Optional[dict]:
    """交互式导入引导。返回 None 表示用户取消。"""
    print("=" * 50)
    print("AgentSeed 平台导入向导")
    print("=" * 50)
    print("退出: 直接回车或输入 'q'\n")

    # Step 1: platform_id
    while True:
        pid = input("平台 ID（英文，命令行用，如 my-editor）: ").strip()
        if pid == "" or pid.lower() == "q":
            print("取消。")
            return None
        if not re.match(r"^[a-z0-9-]+$", pid):
            print("  → ID 只能包含小写字母、数字、连字符")
            continue
        if pid in get_all_platforms():
            print(f"  → {pid} 已存在（内置或已添加），请换一个")
            continue
        break

    # Step 2: name
    name = input(f"显示名称（如 {pid.title()}）: ").strip() or pid.title()

    # Step 3: entry
    while True:
        entry = input("入口文件路径（相对于项目根）: ").strip()
        if not entry:
            print("  → 不能为空")
            continue
        # 基本验证：不能是绝对路径
        if entry.startswith("/") or re.match(r"^[A-Za-z]:", entry):
            print("  → 请用相对路径，如 .myeditor/rules.md")
            continue
        break

    # Step 4: format
    print("文件格式:")
    print("  1) markdown  — 普通 Markdown（大多数平台）")
    print("  2) cursor    — Cursor 专用（含 frontmatter）")
    print("  3) comate    — Comate 专用（.mdr 格式）")
    fmt_map = {"1": "markdown", "2": "cursor", "3": "comate"}
    fmt_choice = input("格式 [1]: ").strip() or "1"
    fmt = fmt_map.get(fmt_choice, "markdown")

    # Step 5: char_limit
    print("骨架模式分片阈值（直接回车跳过，使用默认 50000）:")
    cl_raw = input("  字符数上限: ").strip()
    char_limit = int(cl_raw) if cl_raw.isdigit() else None

    # Step 6: hook
    print("是否需要 pre-tool-use 钩子？")
    print("  y) 是（需要钩子目录，如 .myeditor/）")
    print("  n) 否（纯规则文件，不需要钩子）")
    hook_dir = None
    while True:
        h = input("钩子 [n]: ").strip().lower()
        if h in ("", "n", "no"):
            hook_dir = None
            break
        if h in ("y", "yes"):
            hdir = input("  钩子目录名（如 .myeditor）: ").strip()
            if hdir:
                hook_dir = hdir
            break

    # 预览
    print("\n" + "=" * 50)
    print("确认添加以下平台:")
    print(f"  ID:       {pid}")
    print(f"  名称:     {name}")
    print(f"  入口文件: {entry}")
    print(f"  格式:     {fmt}")
    if char_limit:
        print(f"  字符限制: {char_limit}")
    print(f"  钩子目录: {hook_dir or '无'}")
    confirm = input("\n确认添加？[Y/n] ").strip().lower()
    if confirm in ("n", "no"):
        print("取消。")
        return None

    return {
        "id": pid,
        "name": name,
        "entry": entry,
        "format": fmt,
        "char_limit": char_limit,
        "hook_dir": hook_dir,
    }


@dataclass
class PlatformInfo:
    """平台信息（CLI 展示用）"""
    id: str
    name: str
    entry: str
    format: str
    char_limit: Optional[int]
    builtin: bool
    hooks: bool
    note: str = ""


def format_platform_table(platforms: List[dict]) -> str:
    """格式化平台列表为可读表格"""
    lines = []
    header = f"{'ID':<15} {'名称':<25} {'入口文件':<30} {'钩子':<6} {'内置':<6}"
    lines.append(header)
    lines.append("-" * len(header))
    for p in platforms:
        flag = "Y" if p["hooks"] else "-"
        builtin_flag = "内置" if p["builtin"] else "用户"
        note = f" ({p.get('note','')})" if p.get("note") else ""
        entry = p["entry"]
        if len(entry) > 28:
            entry = "..." + entry[-25:]
        lines.append(
            f"{p['id']:<15} {p['name']:<25} {entry:<30} {flag:<6} {builtin_flag:<6}"
            + note
        )
    return "\n".join(lines)
