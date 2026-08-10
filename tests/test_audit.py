"""
深度审查测试
找出边界违规、未响应引用、冲突和结构缺陷。
运行: python tests/test_audit.py
"""
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from sync_rules import parse_manifest, build_ruleset, list_profiles, TOOL_OUTPUT

PROFILES = ["coding", "novel", "paper", "agent-builder"]

issues = []

def err(category, msg):
    issues.append(f"[{category}] {msg}")
    print(f"  [FAIL] {msg}")

def ok(category, msg):
    print(f"  [ok] {msg}")


def test_no_missing_refs_in_generated():
    """生成的规则集不应有任何 [missing] 或 [unresolved ref] 标记"""
    print("\n=== 1. 生成规则集的引用完整性 ===")
    for pid in PROFILES:
        ruleset = build_ruleset(pid)
        if "[missing]" in ruleset:
            # 找出具体哪些文件缺失
            missing = re.findall(r"\[missing\] ([^\n]+)", ruleset)
            err("缺失引用", f"{pid}: {len(missing)} 个缺失引用: {missing[:3]}")
        elif "[unresolved ref]" in ruleset:
            unresolved = re.findall(r"\[unresolved ref\] ([^\n]+)", ruleset)
            err("未解析引用", f"{pid}: {len(unresolved)} 个未解析: {unresolved[:3]}")
        else:
            ok("引用完整", f"{pid}: 无缺失/未解析引用")


def test_agents_md_referenced_tests_exist():
    """AGENTS.md 引用的测试脚本必须存在"""
    print("\n=== 2. AGENTS.md 引用的测试文件存在性 ===")
    agents_path = REPO_ROOT / "AGENTS.md"
    if not agents_path.exists():
        pytest.skip("AGENTS.md not yet generated — run agentseed sync first")
    agents = agents_path.read_text(encoding="utf-8")
    referenced = re.findall(r"python (tests/[\w.]+)", agents)
    for t in referenced:
        p = REPO_ROOT / t
        if not p.exists():
            err("测试缺失", f"AGENTS.md 引用的 {t} 不存在")
        else:
            ok("测试存在", f"{t}")


def test_capability_files_exist():
    """manifest 声明的 capability 应有对应定义文件"""
    print("\n=== 3. Capability 定义文件存在性 ===")
    caps_dir = REPO_ROOT / "capabilities"
    declared_caps = set()
    for pid in PROFILES:
        m = parse_manifest(pid)
        for c in m.get("enables_capabilities", []):
            declared_caps.add(c)
        for c in m.get("forbids_capabilities", []):
            declared_caps.add(c)
    for cap in sorted(declared_caps):
        # 尝试多种命名约定
        candidates = [
            caps_dir / f"{cap}.md",
            caps_dir / cap / "README.md",
            caps_dir / cap / "AGENTS.md",
        ]
        found = any(p.exists() for p in candidates)
        if found:
            ok("Capability", f"{cap}: 定义文件存在")
        else:
            err("Capability", f"{cap}: 无定义文件 (capabilities/{cap}.md 缺失)")


def test_mutex_symmetry():
    """互斥关系必须对称"""
    print("\n=== 4. 互斥关系对称性 ===")
    for pid in PROFILES:
        m = parse_manifest(pid)
        enemies = m.get("mutually_exclusive_with", [])
        for enemy in enemies:
            em = parse_manifest(enemy)
            reverse = em.get("mutually_exclusive_with", [])
            if pid not in reverse:
                err("互斥不对称", f"{pid} 声明与 {enemy} 互斥，但 {enemy} 未声明与 {pid} 互斥")
            else:
                ok("互斥对称", f"{pid} <-> {enemy}")


def test_forbids_not_in_enables():
    """禁止的能力包不能同时出现在启用列表"""
    print("\n=== 5. 启用/禁止能力包无自相矛盾 ===")
    for pid in PROFILES:
        m = parse_manifest(pid)
        enables = set(m.get("enables_capabilities", []))
        forbids = set(m.get("forbids_capabilities", []))
        overlap = enables & forbids
        if overlap:
            err("能力包矛盾", f"{pid}: 同时启用和禁止 {overlap}")
        else:
            ok("无矛盾", f"{pid}: enables={sorted(enables)}, forbids={sorted(forbids)}")


def test_generated_files_have_header():
    """所有生成文件必须有禁止编辑标记"""
    print("\n=== 6. 生成文件标记完整性 ===")
    for tool, rel in TOOL_OUTPUT.items():
        p = REPO_ROOT / rel
        if not p.exists():
            err("文件缺失", f"{tool}: 输出文件 {rel} 不存在")
            continue
        content = p.read_text(encoding="utf-8")
        if "禁止手工编辑" not in content:
            err("标记缺失", f"{tool}: 缺少禁止编辑标记")
        elif "profile:" not in content:
            err("标记缺失", f"{tool}: 缺少 profile 标识")
        else:
            ok("标记完整", f"{tool}: {rel}")


def test_drift_detection():
    """手改生成文件应被检测——通过重新生成对比"""
    print("\n=== 7. 漂移检测（重新生成应覆盖手改）===")
    for tool, rel in TOOL_OUTPUT.items():
        p = REPO_ROOT / rel
        if not p.exists():
            continue
        original = p.read_text(encoding="utf-8")
        # 注入手改标记
        tampered = original + "\n<!-- HAND_EDIT -->\n"
        p.write_text(tampered, encoding="utf-8")
        # 重新生成
        build_ruleset("coding")
        from sync_rules import write_tool_file
        ruleset = build_ruleset("coding")
        write_tool_file(tool, "coding", ruleset)
        regenerated = p.read_text(encoding="utf-8")
        if "HAND_EDIT" in regenerated:
            err("漂移未检测", f"{tool}: 手改未被覆盖")
        else:
            ok("漂移已检测", f"{tool}: 手改被重新生成覆盖")


def test_root_docs_duplication():
    """根 docs/ 是否与 personas/coding/docs/ 重复"""
    print("\n=== 8. 根 docs/ 与 personas/coding/docs/ 重复检查 ===")
    root_docs = REPO_ROOT / "docs"
    coding_docs = REPO_ROOT / "personas" / "coding" / "docs"
    if root_docs.exists() and coding_docs.exists():
        root_files = {f.relative_to(root_docs) for f in root_docs.rglob("*") if f.is_file()}
        coding_files = {f.relative_to(coding_docs) for f in coding_docs.rglob("*") if f.is_file()}
        overlap = root_files & coding_files
        if overlap:
            err("目录重复", f"根 docs/ 与 personas/coding/docs/ 有 {len(overlap)} 个重复文件")
        else:
            ok("无重复", "根 docs/ 与 coding/docs/ 无重叠")
    else:
        ok("跳过", "其中一个目录不存在")


def test_profile_agents_md_content():
    """每个 profile 的 AGENTS.md 必须有实质内容"""
    print("\n=== 9. Profile AGENTS.md 内容实质性 ===")
    for pid in PROFILES:
        p = REPO_ROOT / "personas" / pid / "AGENTS.md"
        content = p.read_text(encoding="utf-8")
        lines = [l for l in content.splitlines() if l.strip() and not l.startswith(">")]
        if len(lines) < 20:
            err("内容过少", f"{pid}: AGENTS.md 仅 {len(lines)} 有效行")
        elif "本文件是规则唯一源头" not in content and "Rule" not in content and "规则" not in content:
            err("内容异常", f"{pid}: AGENTS.md 缺少规则标识")
        else:
            ok("内容充实", f"{pid}: {len(lines)} 有效行")


def test_mutex_pairwise_conflict():
    """互斥 Profile 的 manifest 不得引用对方的文件——真正的隔离检查"""
    print("\n=== 10. 互斥 Profile manifest 路径隔离 ===")
    for pid in PROFILES:
        m = parse_manifest(pid)
        enemies = m.get("mutually_exclusive_with", [])
        # 收集本 profile 引用的所有文件路径
        all_refs = []
        for section_files in m["includes"].values():
            all_refs.extend(section_files)
        # 检查是否引用了互斥 profile 的目录
        for enemy in enemies:
            enemy_dir = f"personas/{enemy}/"
            leaked_refs = [r for r in all_refs if r.startswith(enemy_dir)]
            if leaked_refs:
                err("跨 Profile 引用", f"{pid} manifest 引用了互斥的 {enemy} 的文件: {leaked_refs}")
            else:
                ok("路径隔离", f"{pid}: manifest 不引用 {enemy}/")
        # 检查只引用自己的 profile 目录（除 core 外）
        own_dir = f"personas/{pid}/"
        profile_refs = [r for r in all_refs if r.startswith("personas/")]
        wrong_profile = [r for r in profile_refs if not r.startswith(own_dir)]
        if wrong_profile:
            err("路径错引", f"{pid} 引用了其他 profile 目录: {wrong_profile}")
        else:
            ok("自引正确", f"{pid}: profile 引用均在 {own_dir} 下")


def extract_section(text: str, start_marker: str, end_marker: str) -> str:
    s = text.find(start_marker)
    e = text.find(end_marker)
    if s < 0:
        return ""
    if e < 0 or e < s:
        return text[s:]
    return text[s:e]


def test_manifest_yaml_valid():
    """manifest YAML 语法基本有效"""
    print("\n=== 11. Manifest YAML 基本语法 ===")
    for pid in PROFILES:
        p = REPO_ROOT / "personas" / pid / "persona.yaml"
        content = p.read_text(encoding="utf-8")
        # 检查关键 section 都存在
        required = ["profile:", "id:", "mutually_exclusive_with:", "includes:", "enables_capabilities:"]
        missing = [s for s in required if s not in content]
        if missing:
            err("YAML 不全", f"{pid}: 缺少 section {missing}")
        else:
            ok("YAML 完整", f"{pid}: 所有 section 存在")


def test_single_profile_loading():
    """一次只能加载一个主 profile——验证 build_ruleset 不会混入其他 profile"""
    print("\n=== 12. 单一 Profile 加载隔离 ===")
    for pid in PROFILES:
        ruleset = build_ruleset(pid)
        # PROFILE LAYER 段的截断点：
        # - skeleton 模式下 PROFILE LAYER 之后是 ON-DEMAND INDEX（Skills 层以
        #   「## Skills LAYER (按需)」索引形式出现，非内联）
        # - full 模式下 PROFILE LAYER 之后是 SKILLS LAYER
        # ON-DEMAND INDEX 段里的「跨 profile 复用」路径（如 DOMAIN_QUALITY_GATES
        # 显式标注"(跨 profile 复用)"的 skill 引用）是有意保留的复用关系，
        # 不属于 PROFILE LAYER 内联违规。
        end_marker = "# === ON-DEMAND INDEX" if "# === ON-DEMAND INDEX" in ruleset else "# === SKILLS LAYER"
        profile_section = extract_section(ruleset, "# === PROFILE LAYER", end_marker)
        for other in PROFILES:
            if other == pid:
                continue
            other_path = f"personas/{other}/"
            if other_path in profile_section:
                err("跨 Profile 引用", f"{pid} 的 profile 层引用了 {other_path}")
        ok("隔离检查", f"{pid}: 无跨 profile 加载（profile 层）")


def test_language_mediation_loaded():
    """所有 profile 的生成规则集必须包含语言中介协议"""
    print("\n=== 13. 语言中介协议加载 ===")
    for pid in PROFILES:
        ruleset = build_ruleset(pid)
        if "Language Mediation" not in ruleset and "语言中介" not in ruleset:
            err("语言协议缺失", f"{pid}: 规则集不含语言中介协议")
        else:
            ok("语言协议", f"{pid}: 含语言中介协议")


def test_language_mediation_content():
    """语言中介协议含关键条款"""
    print("\n=== 14. 语言中介协议内容 ===")
    lang = (REPO_ROOT / "core" / "language-mediation.md").read_text(encoding="utf-8")
    required = ["英语", "输入阶段", "输出阶段", "反翻译腔", "进行+动词", "代码注释", "语言切换"]
    for kw in required:
        if kw not in lang:
            err("条款缺失", f"language-mediation.md 缺少: {kw}")
        else:
            ok("条款", f"language-mediation.md 含: {kw}")


def test_docs_exist():
    """关键文档存在且有内容"""
    print("\n=== 15. 关键文档存在性 ===")
    docs = {
        "README.md": "用户使用指南",
        "PROJECT.md": "AI 导航文档",
        "AGENTS.md": "规则中枢入口",
    }
    for path, desc in docs.items():
        p = REPO_ROOT / path
        if not p.exists():
            err("文档缺失", f"{desc} ({path}) 不存在")
            continue
        content = p.read_text(encoding="utf-8")
        lines = [l for l in content.splitlines() if l.strip()]
        if len(lines) < 20:
            err("内容过少", f"{path}: 仅 {len(lines)} 行")
        else:
            ok("文档", f"{path}: {len(lines)} 行 ({desc})")


def test_manifest_language_ref():
    """所有 manifest 的 core includes 含 language-mediation.md"""
    print("\n=== 16. manifest 引用语言协议 ===")
    for pid in PROFILES:
        m = parse_manifest(pid)
        core_files = m["includes"].get("core", [])
        if "core/language-mediation.md" not in core_files:
            err("manifest 缺失", f"{pid}: core 未引用 language-mediation.md")
        else:
            ok("manifest", f"{pid}: core 含 language-mediation.md")


def test_agents_md_references():
    """根 AGENTS.md 引用 PROJECT.md 和语言协议"""
    print("\n=== 17. AGENTS.md 引用完整性 ===")
    agents_path = REPO_ROOT / "AGENTS.md"
    if not agents_path.exists():
        pytest.skip("AGENTS.md not yet generated — run agentseed sync first")
    agents = agents_path.read_text(encoding="utf-8")
    required_refs = [
        ("PROJECT.md", "AI 入口文档"),
        ("core/language-mediation.md", "语言中介协议"),
        ("core/governance.md", "治理层"),
        ("core/interaction.md", "交互层"),
        ("core/persona-router.md", "Profile 选择器"),
    ]
    for ref, desc in required_refs:
        if ref not in agents:
            err("引用缺失", f"AGENTS.md 未引用 {ref} ({desc})")
        else:
            ok("引用", f"AGENTS.md 引用 {ref}")


def run_all():
    print("=" * 60)
    print("深度审查测试")
    print("=" * 60)
    tests = [
        test_no_missing_refs_in_generated,
        test_agents_md_referenced_tests_exist,
        test_capability_files_exist,
        test_mutex_symmetry,
        test_forbids_not_in_enables,
        test_generated_files_have_header,
        test_drift_detection,
        test_root_docs_duplication,
        test_profile_agents_md_content,
        test_mutex_pairwise_conflict,
        test_manifest_yaml_valid,
        test_single_profile_loading,
        test_language_mediation_loaded,
        test_language_mediation_content,
        test_docs_exist,
        test_manifest_language_ref,
        test_agents_md_references,
    ]
    for t in tests:
        t()
    print("\n" + "=" * 60)
    if issues:
        print(f"发现 {len(issues)} 个问题:")
        for i in issues:
            print(f"  {i}")
        return False
    print("全部审查通过，无问题")
    return True


if __name__ == "__main__":
    ok = run_all()
    sys.exit(0 if ok else 1)
