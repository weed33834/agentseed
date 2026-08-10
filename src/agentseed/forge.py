"""
Forge Engine: One-command assembly of Persona Packs into a fully-equipped Agent.

`agentseed forge` → detects environment → selects Persona Pack →
capability gap detection → generates platform entry files → agent is ready.

forge() 完整链路：
  detect_environment()  检测锚点 + 已有平台
  → route()             路由画像（显式>锚点>意图>fallback）
  → evolution 主动补：detect_gap() 发现能力缺口
      ├─ GapScore 0.30-0.55 → 建议命令（用户手动执行）
      ├─ GapScore 0.55-0.75 → 建议能力包（用户确认后装配）
      └─ GapScore > 0.75     → 建议并可选自动装配能力包
  → build_ruleset()      组装规则集（宪法+画像+能力包）
  → evolution Quality Gate: 安全/质量/兼容三关
  → write_tool_file()    生成 15 个平台入口文件
  → emit_constraints()   分发平台钩子

本模块将 router.py / evolution.py / sync_rules.py 三者串联为统一装配体验。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set

from . import sync_rules as _sr
from .router import (
    PERSONAS, detect_anchors, route, allowed_capabilities,
    forbidden_capabilities, default_mode, default_rt,
    are_mutually_exclusive, conflict_check, list_personas, persona_info,
)
from .evolution import (
    GapType, RiskLevel, detect_gap, compute_gap_score, decide_action,
    ActionType, run_quality_gates,
)


# Platform anchor files — 从 sync_rules.PLATFORM_DETECT_MARKERS 派生（统一真相源）
PLATFORM_DETECTION = dict(
    (marker, tool) for marker, tool in _sr.PLATFORM_DETECT_MARKERS
)


@dataclass
class ForgeContext:
    """What the forge engine detected about the environment."""
    cwd: Path
    anchors_found: Set[str] = field(default_factory=set)
    suggested_persona: str = ""
    platforms_detected: Set[str] = field(default_factory=set)
    existing_rules: Set[Path] = field(default_factory=set)
    detected_capabilities: Set[str] = field(default_factory=set)  # 目录下检测到的能力信号
    # ── 新增：推断的能力缺口 ──
    tool_gap: float = 0.0
    knowledge_gap: float = 0.0
    overall_gap: float = 0.0


@dataclass
class ForgeResult:
    """Result of a forge assembly operation."""
    persona_selected: str
    files_generated: List[Path] = field(default_factory=list)
    files_updated: List[Path] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    capabilities_loaded: List[str] = field(default_factory=list)
    capabilities_suggested: List[str] = field(default_factory=list)  # 新增：建议添加的能力包
    gap_analysis: Optional[dict] = None
    quality_gate_results: Optional[List[dict]] = None  # 新增：三关结果
    mode: str = "skeleton"
    tool: str = ""
    interactive_mode: bool = False


def detect_environment(start_dir: Optional[Path] = None) -> ForgeContext:
    """Scan cwd (or start_dir) for project anchors, platforms, and capability signals."""
    cwd = start_dir or Path.cwd()
    ctx = ForgeContext(cwd=cwd)

    # Persona anchors
    anchors = detect_anchors(cwd)
    ctx.anchors_found = set(anchors.keys())
    if anchors:
        ctx.suggested_persona = next(iter(set(anchors.values())))

    # Platform configs
    for plat_path, plat_name in PLATFORM_DETECTION.items():
        if (cwd / plat_path).exists():
            ctx.platforms_detected.add(plat_name)

    # Existing entry files
    for name in ["CLAUDE.md", "GEMINI.md", "AGENTS.md", "best_practices.md"]:
        p = cwd / name
        if p.exists():
            ctx.platforms_detected.add("agents-md")
            ctx.existing_rules.add(p)

    # Capability signals (目录下检测到的能力包信号)
    CAPABILITY_SIGNALS = {
        "tests": "testing",
        "docs": "research",
        "references.bib": "research",
        "chapters": "creative",
        "outline.md": "creative",
    }
    for signal, cap in CAPABILITY_SIGNALS.items():
        if (cwd / signal).exists():
            ctx.detected_capabilities.add(cap)

    # Tool gap estimation: 目录下是否有 MCP/Skills
    tool_score = 0.0
    if (cwd / ".mcp.json").exists():
        tool_score = 0.1  # 有 MCP 配置
    if (cwd / "skills").exists():
        tool_score = max(tool_score, 0.3)
    if (cwd / "requirements.txt").exists() or (cwd / "package.json").exists():
        tool_score = max(tool_score, 0.4)
    ctx.tool_gap = 1.0 - tool_score

    # Knowledge gap: 推断与画像的差距
    ctx.knowledge_gap = 0.5  # 默认中缺口（待路由后精确计算）
    ctx.overall_gap = max(ctx.tool_gap, ctx.knowledge_gap)

    return ctx


def forge(
    cwd: Optional[Path] = None,
    persona: Optional[str] = None,
    intent: str = "",
    tool: Optional[str] = None,
    mode: str = "skeleton",
    output_dir: Optional[Path] = None,
    emit_hooks: bool = True,
    dry_run: bool = False,
    interactive: bool = False,
) -> ForgeResult:
    """Main forge entry: detect → route → evolve → build → write → verify.

    interactive=True 时：先打印环境报告 + 画像选项，再进入交互确认。
    """
    cwd = cwd or Path.cwd()
    _sr.refresh_resources_root()

    # ── 1. Route to persona ──
    route_result = route(cwd=cwd, intent=intent, explicit=persona)
    if route_result.ambiguous:
        raise ValueError(
            f"画像选择不明确（候选: {route_result.candidates}）。"
            f"请用 --profile 显式指定。"
        )
    selected = route_result.persona

    # ── 2. Capability gap detection（关键：装配前主动评估）──
    ctx = detect_environment(cwd)
    caps = allowed_capabilities(selected)
    forbids = forbidden_capabilities(selected)

    # 精确计算知识缺口（基于当前画像 vs 检测到的能力信号）
    knowledge_score = 1.0  # 画像覆盖度
    for cap_signal in ctx.detected_capabilities:
        if cap_signal not in caps:
            knowledge_score -= 0.15  # 检测到但画像未覆盖的能力
    knowledge_score = max(0.0, knowledge_score)
    knowledge_gap = 1.0 - knowledge_score

    # 工具缺口
    tool_score = 1.0 - ctx.tool_gap

    gap = detect_gap(
        gap_type=GapType.KNOWLEDGE,
        tool_available=tool_score,
        knowledge_coverage=knowledge_score,
        urgency=0.6,
        risk=RiskLevel.LOW,
    )

    # 建议添加的能力包（当前画像未覆盖，但检测到信号）
    suggested_caps = []
    for cap_signal in ctx.detected_capabilities:
        if cap_signal not in caps and cap_signal not in forbids:
            # 检查该能力包是否在 capabilities/ 下存在
            cap_path = _sr.REPO_ROOT / "capabilities" / cap_signal
            if cap_path.exists():
                suggested_caps.append(cap_signal)

    gap_analysis = {
        "persona": selected,
        "gap_score": gap.score,
        "action": gap.action.value,
        "recommendation": gap.recommendation,
        "suggested_capabilities": suggested_caps,
        "detected_signals": sorted(ctx.detected_capabilities),
        "tool_gap": ctx.tool_gap,
        "knowledge_gap": knowledge_gap,
    }

    warnings = []

    # 工具分辨率
    if tool is None:
        tool = _sr.detect_tool_from_cwd()
    if tool not in _sr.TOOL_OUTPUT and tool != "all":
        tool = "agents-md"

    # ── Interactive 模式：打印报告后让用户确认 ──
    if interactive:
        _print_interactive_report(ctx, selected, caps, gap_analysis, suggested_caps)
        choice = _prompt_user_choice(selected, suggested_caps)
        if choice == "abort":
            return ForgeResult(
                persona_selected=selected,
                warnings=["用户取消"],
                interactive_mode=True,
            )
        elif choice == "custom":
            # 用户输入了自定义画像
            selected = choice
        else:
            selected = choice  # 用户选择的画像

    # ── 3. Build ruleset（用最终确定的画像）──
    ruleset = _sr.build_ruleset(selected, mode=mode)

    # ── 4. Quality Gate：三关验证（校验画像包本身，而非目标项目目录）──
    # 装配时 Quality Gate 的对象是 personas/<selected>/ 画像包：
    #   - 安全关：画像包内无密钥/.git/可疑可执行
    #   - 质量关：persona.yaml/SOUL.md/AGENTS.md 结构完整
    #   - 兼容关：与目标项目已有画像互斥检查
    quality_results = []
    # 画像包本体：全三关（安全/质量/兼容）——default 为内核通用模式（无 personas 目录，跳过）
    if selected != "default":
        for gr in run_quality_gates(str(_sr.PERSONAS_DIR / selected), active_persona=selected):
            quality_results.append({
                "gate": gr.gate,
                "passed": gr.passed,
                "reason": gr.reason,
                "scope": f"personas/{selected}",
            })
            if not gr.passed and gr.gate == "safety":
                warnings.append(f"[安全关失败:personas/{selected}] {gr.reason} — 规则集仍生成但请检查。")
    # 目标项目：仅兼容关（是否与已有画像冲突）
    for gr in run_quality_gates(str(cwd), active_persona=selected):
        if gr.gate == "compatibility":
            quality_results.append({
                "gate": gr.gate,
                "passed": gr.passed,
                "reason": gr.reason,
                "scope": f"cwd",
            })

    # ── 5. Write files ──
    files_generated: List[Path] = []
    files_updated: List[Path] = []

    if not dry_run:
        out = output_dir or cwd
        out.mkdir(parents=True, exist_ok=True)
        _sr.set_output_root(out)
        try:
            tools = list(_sr.TOOL_OUTPUT.keys()) if tool == "all" else [tool]
            for t in tools:
                if t not in _sr.TOOL_OUTPUT:
                    warnings.append(f"[跳过] 未知平台: {t}")
                    continue
                path = _sr.write_tool_file(t, selected, ruleset, mode=mode)
                try:
                    rel = path.relative_to(out)
                except ValueError:
                    rel = path
                if any(p == path for p in ctx.existing_rules):
                    files_updated.append(rel)
                else:
                    files_generated.append(rel)

                # Hook 分发
                if emit_hooks and t in _sr.HOOK_PLATFORMS:
                    try:
                        _sr.emit_constraints(t)
                    except Exception as e:
                        warnings.append(f"[{t}] hook 分发失败: {e}")
        finally:
            _sr.reset_output_root()

    return ForgeResult(
        persona_selected=selected,
        files_generated=files_generated,
        files_updated=files_updated,
        warnings=warnings,
        capabilities_loaded=caps,
        capabilities_suggested=suggested_caps,
        gap_analysis=gap_analysis,
        quality_gate_results=quality_results,
        mode=mode,
        tool=tool,
        interactive_mode=interactive,
    )


def _print_interactive_report(
    ctx: ForgeContext,
    selected: str,
    caps: List[str],
    gap_analysis: dict,
    suggested_caps: List[str],
) -> None:
    """打印交互式装配环境报告。"""
    print("=" * 60)
    print("AgentSeed forge: 环境检测报告")
    print("=" * 60)
    print(f"  工作目录  : {ctx.cwd}")
    print(f"  检测锚点  : {', '.join(sorted(ctx.anchors_found)) or '(无)'}")
    print(f"  检测平台  : {', '.join(sorted(ctx.platforms_detected)) or '(无)'}")
    print(f"  推断画像  : {selected} (mode={default_mode(selected)}, rt={default_rt(selected)})")
    print(f"  当前能力  : {', '.join(caps) or '(无)'}")
    if ctx.detected_capabilities:
        print(f"  检测到信号: {', '.join(sorted(ctx.detected_capabilities))}")
    print()
    print(f"  GapScore  : {gap_analysis['gap_score']:.2f} → {gap_analysis['action']}")
    print(f"  建议      : {gap_analysis['recommendation']}")
    if suggested_caps:
        print(f"  建议能力包: {', '.join(suggested_caps)} (检测到但当前画像未启用)")
    print()
    print("  可用画像:")
    for pid in list_personas():
        info = persona_info(pid)
        flag = " ← 当前" if pid == selected else ""
        flag2 = " ← 推荐" if pid == ctx.suggested_persona and pid != selected else ""
        caps_str = ", ".join(info["capabilities"])
        print(f"    {pid:20s} {info['default_mode']:10s} {caps_str}{flag}{flag2}")
    print()


def _prompt_user_choice(default_persona: str, suggested_caps: List[str]) -> str:
    """Prompt user for confirmation or different choice. Returns the chosen persona or 'abort'."""
    print("  请选择画像 [直接回车确认为 '{}']: ".format(default_persona), end="")
    try:
        choice = input().strip()
    except (EOFError, OSError):
        choice = ""
    if not choice:
        return default_persona
    # 'a' = abort
    if choice.lower() in ("a", "abort", "q", "quit"):
        return "abort"
    # Accept persona id if valid
    if choice in PERSONAS:
        return choice
    # Default on unknown
    return default_persona


# ─── Persona switch (persona-router.md §7) ───

def switch_persona(target: str, cwd: Optional[Path] = None) -> dict:
    """Switch active persona (persona-router.md §7).

    Validates mutual exclusion, returns warnings about state clearing.
    """
    cwd = cwd or Path.cwd()
    active = _current_persona(cwd)

    if active and active != target:
        warn = conflict_check(active, target)
        if warn:
            return {"ok": True, "from": active, "to": target, "warning": warn}
    return {"ok": True, "from": active, "to": target, "warning": None}


def _current_persona(cwd: Path) -> str:
    """Best-effort: detect current persona from cwd anchors."""
    anchors = detect_anchors(cwd)
    if anchors:
        return next(iter(set(anchors.values())))
    return ""


# ─── Capability check (used by CLI status) ───

@dataclass
class CapabilityCheck:
    """Check whether a persona can handle a given task."""
    persona: str
    task_domain: str
    has_skills: bool
    has_mcp: bool
    has_knowledge: bool

    def analyze(self) -> dict:
        tool_avail = 0.8 if self.has_mcp else (0.3 if self.has_skills else 0.0)
        knowledge_cov = 1.0 if self.has_knowledge else 0.2
        urgency = 0.8 if (not self.has_mcp and not self.has_skills and not self.has_knowledge) else 0.5

        gap = detect_gap(
            gap_type=GapType.KNOWLEDGE,
            tool_available=tool_avail,
            knowledge_coverage=knowledge_cov,
            urgency=urgency,
            risk=RiskLevel.LOW,
        )
        return {
            "persona": self.persona,
            "domain": self.task_domain,
            "gap_score": gap.score,
            "action": gap.action.value,
            "recommendation": gap.recommendation,
            "constraints": gap.constraints,
        }
