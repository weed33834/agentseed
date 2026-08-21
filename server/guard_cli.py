"""AgentSeed CLI — zero-dependency command-line entry point.

Enables CI gating for human PRs as well as agent sessions:

    python guard_cli.py verify  [source_or_path] [--language LANG]
    python guard_cli.py scan    [source_or_path] [--strict]
    python guard_cli.py check   [plugin_dir] [--ci]
    python guard_cli.py sandbox -- <command> [args...]

Exit codes: 0 = pass, 1 = findings/errors, 2 = usage error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard_engine as engine  # noqa: E402


def _read_source(path_or_source: str) -> str:
    if os.path.isfile(path_or_source):
        with open(path_or_source, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    return path_or_source


def cmd_verify(args: argparse.Namespace) -> int:
    source = _read_source(args.source)
    result = engine.detect_undefined_symbols(source, args.language)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("note", "").startswith("Cannot parse"):
        return 0  # syntax error is reported, not a finding
    return 1 if result["suspects"] else 0


def cmd_scan(args: argparse.Namespace) -> int:
    config = engine.load_config(args.config)
    allowlist = [] if args.strict else (
        args.allowlist
        or engine._config_str_list(config, "allowlist")
        or engine.DEFAULT_ALLOWLIST
    )
    severities = {"stub_code": "error"} if (args.strict and not args.stub_ok) else \
        engine._config_severities(config)
    source = _read_source(args.source)
    result = engine.scan_hallucination_words(source, allowlist, severities)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["blocking"] else 0


def cmd_check(args: argparse.Namespace) -> int:
    path = os.path.abspath(args.plugin_dir or ".")
    if not os.path.isdir(path):
        print(json.dumps({"ok": False, "errors": [f"not a directory: {path}"],
                          "warnings": []}, ensure_ascii=False, indent=2))
        return 1
    result = engine.check_plugin_conformance(path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def cmd_sandbox(args: argparse.Namespace) -> int:
    config = engine.load_config()
    try:
        timeout = int(args.timeout) if args.timeout is not None else \
            int(config.get("timeout", 30))
    except (TypeError, ValueError):
        timeout = 30
    result = engine.sandbox_run(args.command, timeout, args.cwd)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["timed_out"]:
        return 1
    return result["exit_code"] if result["exit_code"] > 0 else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentseed", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser("verify", help="flag possibly-hallucinated symbols")
    p_verify.add_argument("source", help="source code or a file path")
    p_verify.add_argument("--language", default="python",
                          choices=["python", "typescript", "javascript", "ts", "js"])
    p_verify.set_defaults(func=cmd_verify)

    p_scan = sub.add_parser("scan", help="scan for hallucination signals")
    p_scan.add_argument("source", help="source text or a file path")
    p_scan.add_argument("--allowlist", action="append",
                        help="exclusion prefix (repeatable)")
    p_scan.add_argument("--strict", action="store_true",
                        help="disable default exclusions; stub hits become errors")
    p_scan.add_argument("--stub-ok", action="store_true",
                        help="with --strict: keep stub_code at warning severity")
    p_scan.add_argument("--config", help="explicit config file path")
    p_scan.set_defaults(func=cmd_scan)

    p_check = sub.add_parser("check", help="validate a plugin directory")
    p_check.add_argument("plugin_dir", nargs="?", default=".")
    p_check.add_argument("--ci", action="store_true",
                         help="(default in CI use) exit 1 on any conformance error")
    p_check.set_defaults(func=cmd_check)

    p_sandbox = sub.add_parser("sandbox", help="run a command with timeout + captured output")
    p_sandbox.add_argument("command", nargs="+",
                           help="command to run; use '--' before flags of the child")
    p_sandbox.add_argument("--timeout", help="seconds (1-120)")
    p_sandbox.add_argument("--cwd", help="working directory")
    p_sandbox.set_defaults(func=cmd_sandbox)

    args = parser.parse_args(argv)
    if args.cmd == "sandbox" and args.command and args.command[0] == "--":
        args.command = args.command[1:]
    try:
        return args.func(args)
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    sys.exit(main())
