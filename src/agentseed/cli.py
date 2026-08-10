"""AgentSeed CLI：分发层入口。

用法：
    agentseed list
    agentseed setup                          # 零配置默认链路（推荐入门）
    agentseed setup --intent "帮我写小说"      # 口语化意图自动切 profile
    agentseed forge                          # 一键装配（自动检测环境）
    agentseed forge --profile coding         # 指定画像装配
    agentseed forge --dry-run                # 预览不写入
    agentseed switch --profile novel         # 切换画像
    agentseed persona list                   # 列出画像
    agentseed persona search <query>         # 搜索社区画像
    agentseed persona install <name>         # 安装社区画像
    agentseed platform list                  # 列出平台
    agentseed platform import                # 交互式导入新平台
    agentseed platform import my-editor --entry .myeditor/rules.md
    agentseed status                         # 查看当前装配状态
    agentseed sync                           # 同步到所有平台（含用户平台）
    agentseed sync --platform my-editor      # 同步到用户平台
    agentseed apply --profile coding --tool claude-code
    agentseed apply --profile coding --tool all
    agentseed apply --profile coding --tool claude-code --mode full
    agentseed apply --profile coding --tool all --output /path/to/project
    agentseed apply --profile coding --tool claude-code --emit-constraints
    agentseed verify                       # 验证全部 profile（CI 用）
    agentseed verify --profile coding      # 验证单个 profile
"""
import argparse
import json
import sys
from pathlib import Path

from . import sync_rules as _sr

__version__ = "1.0.0"


def _emit_json(args, payload: dict) -> bool:
    """Emit payload as JSON when --json is given; returns True if emitted.

    强制 stdout 为 UTF-8：--json 面向脚本/Agent 消费，必须不受 Windows GBK
    控制台/管道编码影响（与 mcp_server._force_utf8_streams 同理）。
    """
    if getattr(args, "json", False):
        reconfigure = getattr(sys.stdout, "reconfigure", None)
        if callable(reconfigure):
            try:
                sys.stdout.reconfigure(encoding="utf-8")
            except Exception:
                pass
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        return True
    return False


def cmd_list(args) -> int:
    # 刷新资源根，响应当前 AGENTSEED_REPO 环境变量
    _sr.refresh_resources_root()
    _sr.merge_user_platforms()
    profiles = _sr.list_profiles()
    tools = [
        {"id": t, "output": _sr.TOOL_OUTPUT[t],
         "char_limit": _sr.TOOL_CHAR_LIMIT.get(t)}
        for t in _sr.TOOL_OUTPUT
    ]
    if _emit_json(args, {
        "profiles": profiles,
        "tools": tools,
        "resources_root": str(_sr.RESOURCES_ROOT),
        "resources_source": _sr.resources_source(),
    }):
        return 0
    print("可用场景规则包:")
    for p in profiles:
        print(f"  - {p}")
    print()
    print("可用输出平台:")
    for t in _sr.TOOL_OUTPUT:
        out = _sr.TOOL_OUTPUT[t]
        limit = _sr.TOOL_CHAR_LIMIT.get(t)
        suffix = f" (limit={limit})" if limit else ""
        print(f"  - {t:12s} -> {out}{suffix}")
    print()
    print(f"AgentSeed 资源根: {_sr.RESOURCES_ROOT}")
    print(f"资源来源: {_sr.resources_source()}")
    return 0


# ─── forge: 一键装配 ───

def cmd_forge(args) -> int:
    """agentseed forge — 检测环境 → 路由画像 → 生成平台文件。"""
    from .forge import forge
    try:
        result = forge(
            persona=args.profile,
            intent=args.intent,
            tool=args.tool,
            mode=args.mode,
            dry_run=args.dry_run,
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if _emit_json(args, {
        "persona": result.persona_selected,
        "tool": result.tool,
        "mode": result.mode,
        "capabilities_loaded": result.capabilities_loaded,
        "gap_analysis": result.gap_analysis,
        "files_generated": result.files_generated,
        "files_updated": result.files_updated,
        "warnings": result.warnings,
        "dry_run": args.dry_run,
    }):
        return 0

    print("=" * 60)
    print(f"agentseed forge: 装配完成")
    print("=" * 60)
    print(f"  场景规则包 : {result.persona_selected}")
    print(f"  tool    : {result.tool}")
    print(f"  mode    : {result.mode}")
    print(f"  能力插件   : {', '.join(result.capabilities_loaded) or '(无)'}")
    if result.gap_analysis:
        g = result.gap_analysis
        print(f"  GapScore: {g['gap_score']:.2f} → {g['action']}")
        print(f"  建议    : {g['recommendation']}")
    if result.files_generated:
        print(f"\n  新生成 ({len(result.files_generated)}):")
        for f in result.files_generated:
            print(f"    + {f}")
    if result.files_updated:
        print(f"\n  已更新 ({len(result.files_updated)}):")
        for f in result.files_updated:
            print(f"    ~ {f}")
    for w in result.warnings:
        print(f"  ⚠ {w}")
    if args.dry_run:
        print("\n  (dry-run: 未写入任何文件)")
    else:
        print("\n  完成。重启你的 AI 工具即可生效。")
    return 0


# ─── switch: 切换画像 ───

def cmd_switch(args) -> int:
    """agentseed switch --profile <id> — 切换画像（含互斥检查）。"""
    from .forge import switch_persona
    from .router import PERSONAS
    if args.profile not in PERSONAS:
        print(f"error: 未知画像 '{args.profile}'，可用: {list(PERSONAS)}", file=sys.stderr)
        return 1
    result = switch_persona(args.profile)
    print("=" * 60)
    print("agentseed switch: 场景规则包切换")
    print("=" * 60)
    print(f"  from : {result['from'] or '(未检测到)'}")
    print(f"  to   : {result['to']}")
    if result["warning"]:
        print(f"  ⚠ {result['warning']}")
    print("\n  提示: 运行 `agentseed forge --profile <id>` 重新生成平台文件。")
    return 0


# ─── persona: 画像管理 ───

def cmd_persona(args) -> int:
    """agentseed persona <sub> — list / search / install。"""
    from .router import list_personas, persona_info
    if args.persona_cmd == "list":
        personas = []
        for p in list_personas():
            info = persona_info(p)
            personas.append({
                "id": p,
                "mode": info["default_mode"],
                "capabilities": info["capabilities"],
            })
        if _emit_json(args, {"personas": personas}):
            return 0
        print("内置场景规则包:")
        for p in list_personas():
            info = persona_info(p)
            mode = info["default_mode"]
            caps = ", ".join(info["capabilities"])
            print(f"  - {p:18s} 模式={mode:10s} 能力={caps}")
        return 0

    if args.persona_cmd == "search":
        from .market import search_personas, format_search
        result = search_personas(args.query)
        print(format_search(result))
        return 0

    if args.persona_cmd == "install":
        from .market import install_persona, format_install
        result = install_persona(
            name=args.name,
            source=args.source,
            active_persona=args.active,
        )
        print(format_install(result))
        return 0 if result.ok else 1

    print(f"error: 未知 persona 子命令 '{args.persona_cmd}'", file=sys.stderr)
    return 1


# ─── status: 装配状态 ───

def cmd_status(args) -> int:
    """agentseed status — 查看当前装配状态。"""
    from .forge import detect_environment
    from .router import default_mode, default_rt
    _sr.refresh_resources_root()
    ctx = detect_environment()
    if _emit_json(args, {
        "resources_root": str(_sr.RESOURCES_ROOT),
        "resources_source": _sr.resources_source(),
        "cwd": str(ctx.cwd),
        "anchors_found": sorted(ctx.anchors_found),
        "suggested_persona": ctx.suggested_persona or "default",
        "default_mode": default_mode(ctx.suggested_persona) if ctx.suggested_persona else None,
        "default_rt": default_rt(ctx.suggested_persona) if ctx.suggested_persona else None,
        "platforms_detected": sorted(ctx.platforms_detected),
        "existing_rules_count": len(ctx.existing_rules),
    }):
        return 0
    print("=" * 60)
    print("agentseed status")
    print("=" * 60)
    print(f"  资源根    : {_sr.RESOURCES_ROOT} ({_sr.resources_source()})")
    print(f"  工作目录  : {ctx.cwd}")
    print(f"  检测锚点  : {', '.join(sorted(ctx.anchors_found)) or '(无)'}")
    print(f"  推断场景规则包 : {ctx.suggested_persona or 'default (内核通用)'}")
    if ctx.suggested_persona:
        print(f"  默认模式  : {default_mode(ctx.suggested_persona)}")
        print(f"  默认推理  : {default_rt(ctx.suggested_persona)}")
    print(f"  检测平台  : {', '.join(sorted(ctx.platforms_detected)) or '(无)'}")
    if ctx.existing_rules:
        print(f"  已存在规则: {len(ctx.existing_rules)} 个文件")
    return 0


# ─── sync: 同步到平台 ───

def cmd_sync(args) -> int:
    """agentseed sync [--platform <t>] — 同步当前画像到平台。"""
    from .forge import detect_environment
    from .router import default_mode, default_rt
    _sr.refresh_resources_root()
    _sr.merge_user_platforms()

    # 推断当前画像
    ctx = detect_environment()
    persona = args.profile or ctx.suggested_persona or "default"
    if persona not in _sr.list_profiles():
        print(f"error: 未知 profile '{persona}'，可用: {_sr.list_profiles()}", file=sys.stderr)
        return 1

    ruleset = _sr.build_ruleset(persona, mode=args.mode)
    out = Path.cwd().resolve()
    out.mkdir(parents=True, exist_ok=True)
    _sr.set_output_root(out)
    synced = []
    skipped = []
    try:
        if args.platform:
            tools = [args.platform] if args.platform != "all" else list(_sr.TOOL_OUTPUT)
        else:
            tools = list(_sr.TOOL_OUTPUT)
        # 去重：qwenwork 和 agents-md 写同一文件 AGENTS.md，跳过 qwenwork（agents-md 先写）
        seen_outputs = set()
        for t in tools:
            if t not in _sr.TOOL_OUTPUT:
                if not getattr(args, "json", False):
                    print(f"  ⚠ 跳过未知平台 {t}")
                skipped.append(t)
                continue
            out_rel = _sr.TOOL_OUTPUT[t]
            if out_rel in seen_outputs:
                if not getattr(args, "json", False):
                    print(f"  ⚡ 跳过 {t}（与已同步平台写同一文件 {out_rel}）")
                skipped.append(t)
                continue
            seen_outputs.add(out_rel)
            path = _sr.write_tool_file(t, persona, ruleset, mode=args.mode)
            try:
                rel = path.relative_to(out)
            except ValueError:
                rel = path
            if not getattr(args, "json", False):
                print(f"  [{t}] -> {rel}")
            synced.append({"id": t, "output": str(rel)})
    finally:
        _sr.reset_output_root()
    if _emit_json(args, {"persona": persona, "mode": args.mode,
                         "platforms": synced, "skipped": skipped}):
        return 0
    print(f"\n已同步 persona={persona} 到 {len(tools)} 个平台。")
    return 0


def cmd_setup(args) -> int:
    """零配置默认链路：自动检测 profile + tool + emit-constraints。
    用户口语化请求"帮我配置规则"时走这条路径。
    """
    _sr.refresh_resources_root()
    _sr.merge_user_platforms()
    user_intent = args.intent or ""
    output_dir = Path(args.output).resolve() if args.output else None

    result = _sr.setup_default(user_intent=user_intent, output_dir=output_dir)

    profile = result["profile"]
    tool = result["tool"]
    budget_status = "✓ 预算内" if result["ruleset_size"] <= _sr.SKELETON_BUDGET_BYTES else "✗ 超预算"

    print("=" * 60)
    print("agentseed setup: 默认链路已配置")
    print("=" * 60)
    print(f"  profile : {profile}")
    print(f"  tool    : {tool}")
    print(f"  mode    : skeleton")
    print(f"  output  : {result['output']}")
    print(f"  ruleset : {result['ruleset_path']} ({result['ruleset_size']} 字节 {budget_status})")

    if result["hook_files"]:
        print(f"\n  hook 适配器（{len(result['hook_files'])} 个文件已分发）：")
        for hf in result["hook_files"]:
            print(f"    - {hf}")
        print("\n  下一步：重启你的 AI 工具，hook 自动生效。")
    else:
        print("\n  该平台不支持 hook（仅软引导），规则文件已生成。")

    if user_intent:
        print(f"\n  （检测到用户意图: {user_intent!r}，已自动切换 profile）")
    return 0


def cmd_apply(args) -> int:
    profile = args.profile
    tool = args.tool
    mode = args.mode

    # 刷新资源根，响应当前 AGENTSEED_REPO 环境变量
    _sr.refresh_resources_root()
    _sr.merge_user_platforms()

    if profile not in _sr.list_profiles():
        print(f"error: 未知 profile '{profile}'，可用: {_sr.list_profiles()}", file=sys.stderr)
        return 1
    if tool != "all" and tool not in _sr.TOOL_OUTPUT:
        print(f"error: 未知 tool '{tool}'，可用: all 或 {list(_sr.TOOL_OUTPUT)}", file=sys.stderr)
        return 1

    # 装配规则集（读源，源根由 sync_rules 自动检测）
    ruleset = _sr.build_ruleset(profile, mode=mode)

    # 产物输出根：
    # - --output 指定 → 用户目录
    # - 否则默认 → 当前工作目录（符合 pip install 后端用户期望：
    #   在用户项目里运行 agentseed apply 应在项目里生成 AGENTS.md / CLAUDE.md）
    # - dev 模式（在 AgentSeed 仓库内运行）：cwd 通常 == RESOURCES_ROOT，行为不变
    output_dir_changed = True  # 默认就要切到 cwd（refresh_resources_root 把 OUTPUT_ROOT 重置到了 RESOURCES_ROOT）
    if args.output:
        output_dir = Path(args.output).resolve()
    else:
        output_dir = Path.cwd().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    _sr.set_output_root(output_dir)
    display_root = output_dir

    try:
        budget_status = "✓ 预算内" if len(ruleset) <= _sr.SKELETON_BUDGET_BYTES else "✗ 超预算"
        print(f"装配 profile={profile} mode={mode}")
        print(f"规则集大小: {len(ruleset)} 字符 (预算 {_sr.SKELETON_BUDGET_BYTES}) {budget_status}")

        tools = list(_sr.TOOL_OUTPUT.keys()) if tool == "all" else [tool]
        seen_outputs = set()
        for t in tools:
            out_rel = _sr.TOOL_OUTPUT.get(t, "")
            if out_rel in seen_outputs:
                print(f"  ⚡ 跳过 {t}（与已同步平台写同一文件 {out_rel}）")
                continue
            seen_outputs.add(out_rel)
            out_path = _sr.write_tool_file(t, profile, ruleset, mode=mode)
            try:
                rel = out_path.relative_to(display_root)
            except ValueError:
                rel = out_path
            extra = ""
            char_limit = _sr.TOOL_CHAR_LIMIT.get(t)
            if char_limit:
                extra = f" [limit={char_limit}, {'分片' if len(ruleset) > char_limit else '单文件'}]"
            print(f"  [{t}] -> {rel}{extra}")

            # 可选：同时分发 hook 适配器
            if getattr(args, "emit_constraints", False):
                hook_files = _sr.emit_constraints(t)
                for hf in hook_files:
                    try:
                        hf_rel = hf.relative_to(display_root)
                    except ValueError:
                        hf_rel = hf
                    print(f"           hook -> {hf_rel}")
    finally:
        # 恢复 OUTPUT_ROOT（避免污染后续调用）
        if output_dir_changed:
            _sr.reset_output_root()
    return 0


def cmd_verify(args) -> int:
    """CI 用：硬断言验证 skeleton 模式产物达标（预算、P0 内联、内容不丢、INDEX 完整）。
    任一断言失败抛 AssertionError，退出码 1。
    """
    _sr.refresh_resources_root()
    try:
        reports = _sr.verify_ruleset(profile_id=args.profile, strict_budget=True)
    except AssertionError as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        return 1

    print("=" * 80)
    print("agentseed verify: skeleton 模式硬断言报告")
    print("=" * 80)
    print(f"{'profile':18s} {'size':>7s}  {'margin':>7s}  P0  DEF  IDX  MTX  CAP  GAT")
    for pid, r in reports.items():
        p0 = "✓" if r["p0_inlined"] else "✗"
        df = "✓" if r["deferred_intact"] else "✗"
        ix = "✓" if r["index_complete"] else "✗"
        mt = "✓" if r.get("mutex_symmetric", True) else "✗"
        cp = "✓" if r.get("capabilities_consistent", True) else "✗"
        gt = "✓" if r.get("gates_files_exist", True) else "✗"
        margin = f"+{r['budget_margin']}" if r["budget_ok"] else f"{r['budget_margin']}"
        print(f"{pid:18s} {r['size']:>6d}B  {margin:>7s}  {p0}   {df}   {ix}   {mt}   {cp}   {gt}")
    print()
    print("  P0=P0内联  DEF=deferred完整  IDX=INDEX段  MTX=互斥对称  CAP=cap无冲突  GAT=gates文件存在")
    all_ok = all(
        r["budget_ok"] and r["p0_inlined"] and r["deferred_intact"] and r["index_complete"]
        and r.get("mutex_symmetric", True)
        and r.get("capabilities_consistent", True)
        and r.get("gates_files_exist", True)
        for r in reports.values()
    )
    print(f"[{'PASS' if all_ok else 'FAIL'}] {len(reports)} 个 profile 验证{'通过' if all_ok else '失败'}")
    return 0 if all_ok else 1


def cmd_check_output(args) -> int:
    """AI 交付前自检：按 profile + output_type 校验输出 schema。
    失败时给出明确的"哪里错了 + 怎么修"反馈，触发 AI 自动重写。
    """
    from . import output_schemas as _os
    _sr.refresh_resources_root()
    content = args.content
    if args.file:
        from pathlib import Path
        content = Path(args.file).read_text(encoding="utf-8")

    result = _os.validate_for_profile(args.profile, args.output_type, content)
    print("=" * 60)
    print(f"agentseed check-output: {args.profile}/{args.output_type}")
    print("=" * 60)
    print(f"  schema_id : {result.schema_id}")
    print(f"  is_valid   : {'✓ PASS' if result.is_valid else '✗ FAIL'}")
    if result.errors:
        print(f"\n  Errors ({len(result.errors)}):")
        for e in result.errors:
            print(f"    ✗ {e}")
    if result.warnings:
        print(f"\n  Warnings ({len(result.warnings)}):")
        for w in result.warnings:
            print(f"    ⚠ {w}")
    if result.fixes_suggested:
        print(f"\n  Suggested fixes:")
        for f in result.fixes_suggested:
            print(f"    → {f}")
    print()
    return 0 if result.is_valid else 1


def cmd_sandbox_run(args) -> int:
    """在沙箱里执行命令。三级降级：E2B → 本地 subprocess 隔离 → 拒绝破坏性命令。
    AI 想跑代码时应优先用此命令，而不是直接调用 Bash。
    """
    from . import sandbox as _sb
    _sr.refresh_resources_root()
    cwd = Path(args.cwd).resolve() if args.cwd else None
    result = _sb.run_in_sandbox(args.command, cwd=cwd, timeout=args.timeout)
    print("=" * 60)
    print(f"agentseed sandbox-run: {result.sandbox_used}")
    print("=" * 60)
    if result.denied_reason:
        print(f"  🚫 DENIED: {result.denied_reason}")
        return 1
    print(f"  exit_code  : {result.exit_code}")
    print(f"  duration   : {result.duration_ms}ms")
    if result.stdout:
        print(f"\n  stdout:")
        for line in result.stdout.splitlines()[:50]:
            print(f"    {line}")
        if len(result.stdout.splitlines()) > 50:
            print(f"    ... ({len(result.stdout.splitlines()) - 50} more lines)")
    if result.stderr:
        print(f"\n  stderr:")
        for line in result.stderr.splitlines()[:30]:
            print(f"    {line}")
    return 0 if result.exit_code == 0 else result.exit_code


def cmd_judge(args) -> int:
    """LLM-as-judge 语义合规检查。
    用 LLM 实时审查 agent 输出，违规即拒绝。
    降级策略：DeepEval → OpenAI → Anthropic → 跳过
    """
    from . import llm_judge as _lj
    _sr.refresh_resources_root()
    content = args.content
    if args.file:
        content = Path(args.file).read_text(encoding="utf-8")
    rules = [r.strip() for r in args.rules.split(",") if r.strip()]

    result = _lj.judge_output(content, rules, user_language=args.language)
    print("=" * 60)
    print(f"agentseed judge: {result.backend_used}")
    print("=" * 60)
    print(f"  is_compliant    : {'✓ PASS' if result.is_compliant else '✗ FAIL'}")
    if result.violated_rules:
        print(f"\n  Violated rules ({len(result.violated_rules)}):")
        for r in result.violated_rules:
            print(f"    ✗ {r}")
    if result.reasoning:
        print(f"\n  Reasoning: {result.reasoning}")
    if result.severity:
        print(f"  Severity : {result.severity}")
    if result.suggested_fix:
        print(f"\n  Suggested fix: {result.suggested_fix}")
    print()
    return 0 if result.is_compliant else 1


def cmd_platform(args) -> int:
    """agentseed platform — 平台管理：list / import / remove / validate / export。"""
    from . import platforms as _pf

    sub = args.platform_cmd

    if sub == "list":
        platforms = _pf.list_platforms()
        if _emit_json(args, {"platforms": platforms, "count": len(platforms)}):
            return 0
        print("已注册平台:")
        print(_pf.format_platform_table(platforms))
        print()
        print(f"共 {len(platforms)} 个平台（内置 + 用户添加）")
        print("提示: 用 `agentseed platform import` 添加自定义平台")
        return 0

    if sub == "import":
        pid = getattr(args, "id", None)
        if not pid:
            # 交互式引导
            info = _pf.interactive_import()
            if info is None:
                return 0
            try:
                _pf.add_platform(
                    info["id"],
                    info["name"],
                    info["entry"],
                    format=info["format"],
                    char_limit=info["char_limit"],
                    hook_dir=info["hook_dir"],
                )
            except ValueError as e:
                print(f"error: {e}", file=sys.stderr)
                return 1
            print(f"\n✅ 平台 {info['id']} 已添加！")
            print(f"  用 `agentseed sync --platform {info['id']}` 同步规则到该平台")
            return 0
        # 非交互
        if not getattr(args, "entry", None):
            print("error: 非交互模式需提供 --entry", file=sys.stderr)
            return 1
        try:
            _pf.add_platform(
                pid,
                args.name or pid.title(),
                args.entry,
                format=args.format,
                char_limit=args.char_limit,
                hook_dir=args.hook_dir,
            )
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        print(f"✅ 平台 {pid} 已添加！")
        print(f"  用 `agentseed sync --platform {pid}` 同步规则到该平台")
        return 0

    if sub == "remove":
        try:
            _pf.remove_platform(args.id)
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        print(f"已移除平台 {args.id}")
        return 0

    if sub == "validate":
        p = _pf.get_platform(args.id)
        if not p:
            print(f"error: 平台 {args.id} 不存在", file=sys.stderr)
            return 1
        print(f"平台 {args.id}:")
        print(f"  名称     : {p.get('name', args.id)}")
        print(f"  入口文件 : {p['entry']}")
        print(f"  格式     : {p.get('format', 'markdown')}")
        if p.get("char_limit"):
            print(f"  字符限制 : {p['char_limit']}")
        print(f"  钩子     : {'启用' if p.get('hooks', {}).get('enabled') else '未启用'}")
        print(f"  来源     : {'内置' if p.get('builtin') else '用户配置'}")
        # 校验入口文件格式
        entry = p["entry"]
        if entry.startswith("/") or "\\" in entry:
            print(f"  ⚠ 入口文件路径可能不合法: {entry}")
        print("✅ 配置有效")
        return 0

    if sub == "export":
        try:
            yaml_text = _pf.export_platform(args.id)
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        print(yaml_text)
        return 0

    return 1


# ─── pack: 场景规则包市场（仓库即市场，按需安装/创建/发布） ───

def cmd_pack(args) -> int:
    """agentseed pack <sub> — 市场场景规则包管理。"""
    from . import pack as _pk

    sub = args.pack_cmd

    if sub == "list":
        packs = _pk.list_market(Path.cwd())
        if _emit_json(args, {"packs": [p.__dict__ for p in packs],
                             "count": len(packs)}):
            return 0
        print(_pk.format_pack_list(packs))
        return 0

    if sub == "add":
        result = _pk.add_pack(args.id, source=getattr(args, "source", None))
        if not result.ok:
            print(f"error: {result.message}", file=sys.stderr)
            return 1
        if _emit_json(args, {"ok": True, "pack_id": result.pack_id,
                             "message": result.message,
                             "target": str(result.target) if result.target else None,
                             "gates": result.gates}):
            return 0
        print(f"✅ {result.message}")
        return 0

    if sub == "remove":
        result = _pk.remove_pack(args.id)
        if not result.ok:
            print(f"error: {result.message}", file=sys.stderr)
            return 1
        print(f"✅ {result.message}")
        return 0

    if sub == "new":
        result = _pk.new_pack(args.id, name=args.name or "",
                              scenario=args.scenario or "",
                              category=args.category)
        if not result.ok:
            print(f"error: {result.message}", file=sys.stderr)
            return 1
        if _emit_json(args, {"ok": True, "pack_id": result.pack_id,
                             "target": str(result.target)}):
            return 0
        print(f"✅ {result.message}")
        return 0

    if sub == "publish":
        result = _pk.publish_pack(args.id)
        if not result.ok:
            print(f"error: {result.message}", file=sys.stderr)
            return 1
        if _emit_json(args, {"ok": True, "pack_id": result.pack_id,
                             "message": result.message,
                             "details": result.details}):
            return 0
        print(result.message)
        return 0

    return 1


# ─── serve: MCP Server ───

def cmd_serve(args) -> int:
    """agentseed serve — 启动 MCP Server。"""
    from . import mcp_server

    port = getattr(args, "port", None)
    if port:
        mcp_server.run_http(port)
    else:
        mcp_server.run_stdio()
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="agentseed",
        description="AgentSeed CLI — 装配 AI 协作规则（skeleton + 按需加载）",
    )
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="列出可用场景规则包和输出平台")
    p_list.add_argument("--json", action="store_true", default=False,
                        help="输出 JSON（供脚本/Agent 消费）")
    p_list.set_defaults(func=cmd_list)

    p_forge = sub.add_parser("forge", help="一键装配：检测环境 → 路由场景 → 生成平台文件")
    p_forge.add_argument("--profile", default=None, help="显式指定场景规则包 (coding/novel/...)")
    p_forge.add_argument("--intent", default="", help="用户意图（用于自动路由场景规则包）")
    p_forge.add_argument("--tool", default=None, help="目标平台 (claude-code/all/...)，默认自动检测")
    p_forge.add_argument("--mode", default="skeleton", choices=["skeleton", "full"],
                         help="装配模式（默认 skeleton）")
    p_forge.add_argument("--dry-run", action="store_true", default=False,
                         help="预览装配结果，不写入文件")
    p_forge.add_argument("--json", action="store_true", default=False,
                         help="输出 JSON（供脚本/Agent 消费）")
    p_forge.set_defaults(func=cmd_forge)

    p_switch = sub.add_parser("switch", help="切换场景规则包（含互斥检查）")
    p_switch.add_argument("--profile", required=True, help="目标场景规则包 (coding/novel/...)")
    p_switch.set_defaults(func=cmd_switch)

    p_persona = sub.add_parser("persona", help="场景规则包管理：list / search / install")
    p_persona_sub = p_persona.add_subparsers(dest="persona_cmd", required=True)
    p_persona_list = p_persona_sub.add_parser("list", help="列出内置场景规则包")
    p_persona_list.add_argument("--json", action="store_true", default=False,
                                help="输出 JSON（供脚本/Agent 消费）")
    p_persona_list.set_defaults(func=cmd_persona)
    p_persona_search = p_persona_sub.add_parser("search", help="搜索社区场景规则包")
    p_persona_search.add_argument("query", help="搜索关键词")
    p_persona_search.set_defaults(func=cmd_persona)
    p_persona_install = p_persona_sub.add_parser("install", help="安装社区场景规则包")
    p_persona_install.add_argument("name", help="场景规则包名")
    p_persona_install.add_argument("--source", default=None, help="GitHub URL 或本地路径（默认查注册表）")
    p_persona_install.add_argument("--active", default="", help="当前激活场景规则包（用于兼容性检查）")
    p_persona_install.set_defaults(func=cmd_persona)

    p_status = sub.add_parser("status", help="查看当前装配状态（锚点/场景/平台）")
    p_status.add_argument("--json", action="store_true", default=False,
                          help="输出 JSON（供脚本/Agent 消费）")
    p_status.set_defaults(func=cmd_status)

    p_sync = sub.add_parser("sync", help="同步当前场景规则包到平台")
    p_sync.add_argument("--profile", default=None, help="场景规则包 (默认自动推断)")
    p_sync.add_argument("--platform", default=None, help="平台 (默认全部，可指定 claude-code 等)")
    p_sync.add_argument("--mode", default="skeleton", choices=["skeleton", "full"])
    p_sync.add_argument("--json", action="store_true", default=False,
                        help="输出 JSON（供脚本/Agent 消费）")
    p_sync.set_defaults(func=cmd_sync)

    p_setup = sub.add_parser("setup", help="零配置默认链路：自动检测 profile + tool + emit-constraints")
    p_setup.add_argument("--intent", default="",
                         help="用户口语化意图（如 '帮我写代码' / '写小说'），用于自动识别 profile")
    p_setup.add_argument("--output", default=None,
                         help="生成产物输出目录（默认当前工作目录）")
    p_setup.set_defaults(func=cmd_setup)

    p_apply = sub.add_parser("apply", help="生成指定 profile+tool 的规则文件")
    p_apply.add_argument("--profile", required=True, help="主 profile (如 coding/novel/paper...)")
    p_apply.add_argument("--tool", required=True,
                         help="目标工具 (claude-code/gemini/cursor/trae/agents-md/all/...)")
    p_apply.add_argument("--mode", default="skeleton", choices=["skeleton", "full"],
                         help="装配模式（默认 skeleton）")
    p_apply.add_argument("--output", default=None,
                         help="生成产物输出目录（默认当前工作目录）")
    p_apply.add_argument("--emit-constraints", action="store_true", default=False,
                         help="同时分发 hook 适配器配置（仅支持 PreToolUse 的 6 个平台有效；"
                              "其他平台静默跳过）")
    p_apply.set_defaults(func=cmd_apply)

    p_verify = sub.add_parser("verify", help="CI 用：硬断言验证 skeleton 模式产物达标")
    p_verify.add_argument("--profile", default=None,
                          help="只验证指定 profile（默认全部）")
    p_verify.set_defaults(func=cmd_verify)

    p_check = sub.add_parser("check-output", help="AI 交付前自检：按 profile + output_type 校验输出 schema")
    p_check.add_argument("--profile", required=True, help="主 profile (coding/novel/paper/...)")
    p_check.add_argument("--output-type", required=True,
                         help="输出类型 (code_change/paper_outline/novel_chapter/conversation_response/agent_design)")
    p_check.add_argument("--content", default="",
                         help="待校验内容（与 --content 二选一）")
    p_check.add_argument("--file", default=None,
                         help="从文件读取待校验内容（与 --content 二选一）")
    p_check.set_defaults(func=cmd_check_output)

    p_sandbox = sub.add_parser("sandbox-run", help="在沙箱里执行命令（三级降级：E2B→本地→拒绝）")
    p_sandbox.add_argument("--command", required=True, help="要执行的命令")
    p_sandbox.add_argument("--cwd", default=None, help="工作目录（默认当前目录）")
    p_sandbox.add_argument("--timeout", type=int, default=60, help="超时秒数（默认 60）")
    p_sandbox.set_defaults(func=cmd_sandbox_run)

    p_judge = sub.add_parser("judge", help="LLM-as-judge 语义合规检查")
    p_judge.add_argument("--content", default="", help="待检查内容（与 --file 二选一）")
    p_judge.add_argument("--file", default=None, help="从文件读取内容（与 --content 二选一）")
    p_judge.add_argument("--rules", required=True,
                         help="规则列表（逗号分隔），如 no_pii_in_commit,language_match_user")
    p_judge.add_argument("--language", default="", help="用户语言提示（如 '中文'/'English'）")
    p_judge.set_defaults(func=cmd_judge)

    p_platform = sub.add_parser("platform", help="平台管理：list / import / remove / validate / export")
    p_platform_sub = p_platform.add_subparsers(dest="platform_cmd", required=True)
    p_platform_list = p_platform_sub.add_parser("list", help="列出所有已注册平台")
    p_platform_list.add_argument("--json", action="store_true", default=False,
                                 help="输出 JSON（供脚本/Agent 消费）")
    p_platform_list.set_defaults(func=cmd_platform)
    p_platform_import = p_platform_sub.add_parser("import", help="导入新平台（交互式或参数指定）")
    p_platform_import.add_argument("id", nargs="?", default=None, help="平台 ID（省略则交互式引导）")
    p_platform_import.add_argument("--name", default=None, help="显示名称")
    p_platform_import.add_argument("--entry", default=None, help="入口文件路径（相对项目根）")
    p_platform_import.add_argument("--format", default="markdown",
                                   choices=["markdown", "cursor", "comate"],
                                   help="文件格式（默认 markdown）")
    p_platform_import.add_argument("--char-limit", type=int, default=None, help="骨架分片阈值")
    p_platform_import.add_argument("--hook-dir", default=None, help="钩子目录名（如 .myeditor）")
    p_platform_import.set_defaults(func=cmd_platform)
    p_platform_remove = p_platform_sub.add_parser("remove", help="移除用户添加的平台")
    p_platform_remove.add_argument("id", help="平台 ID")
    p_platform_remove.set_defaults(func=cmd_platform)
    p_platform_validate = p_platform_sub.add_parser("validate", help="验证平台配置")
    p_platform_validate.add_argument("id", help="平台 ID")
    p_platform_validate.set_defaults(func=cmd_platform)
    p_platform_export = p_platform_sub.add_parser("export", help="导出平台配置为 YAML")
    p_platform_export.add_argument("id", help="平台 ID")
    p_platform_export.set_defaults(func=cmd_platform)

    p_pack = sub.add_parser("pack", help="场景规则包市场：list / add / remove / new / publish（仓库即市场，按需安装）")
    p_pack_sub = p_pack.add_subparsers(dest="pack_cmd", required=True)
    p_pack_list = p_pack_sub.add_parser("list", help="列出市场全部场景包与安装状态")
    p_pack_list.add_argument("--json", action="store_true", default=False,
                             help="输出 JSON（供脚本/Agent 消费）")
    p_pack_list.set_defaults(func=cmd_pack)
    p_pack_add = p_pack_sub.add_parser("add", help="按需安装单个场景包（只拉取该包，不克隆全仓库）")
    p_pack_add.add_argument("id", help="场景包 ID（如 novel / paper / 自建包）")
    p_pack_add.add_argument("--source", default=None, help="市场仓库 URL（默认 AGENTSEED_MARKET 或主仓库）")
    p_pack_add.add_argument("--json", action="store_true", default=False,
                            help="输出 JSON（供脚本/Agent 消费）")
    p_pack_add.set_defaults(func=cmd_pack)
    p_pack_remove = p_pack_sub.add_parser("remove", help="移除本地场景包（git 仓库内可恢复）")
    p_pack_remove.add_argument("id", help="场景包 ID")
    p_pack_remove.set_defaults(func=cmd_pack)
    p_pack_new = p_pack_sub.add_parser("new", help="创建新场景包（模板 + 校验指引）")
    p_pack_new.add_argument("id", help="新包 ID（小写字母/数字/连字符）")
    p_pack_new.add_argument("--name", default="", help="显示名称")
    p_pack_new.add_argument("--scenario", default="", help="适用场景描述")
    p_pack_new.add_argument("--category", default="general",
                            choices=sorted(["general", "dev", "creative", "research", "strategic"]),
                            help="包分类（general/dev/creative/research/strategic）")
    p_pack_new.add_argument("--json", action="store_true", default=False,
                            help="输出 JSON（供脚本/Agent 消费）")
    p_pack_new.set_defaults(func=cmd_pack)
    p_pack_publish = p_pack_sub.add_parser("publish", help="发布自建包回市场（校验 + 生成 PR 材料）")
    p_pack_publish.add_argument("id", help="场景包 ID")
    p_pack_publish.add_argument("--json", action="store_true", default=False,
                                help="输出 JSON（供脚本/Agent 消费）")
    p_pack_publish.set_defaults(func=cmd_pack)

    p_serve = sub.add_parser("serve", help="启动 MCP Server（stdio 模式，--port 启用 HTTP/SSE）")
    p_serve.add_argument("--port", type=int, default=None, help="HTTP/SSE 端口（默认 stdio）")
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
