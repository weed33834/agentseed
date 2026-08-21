"""AgentSeed MCP server (hand-written, zero third-party dependencies).

Why hand-written instead of the `mcp` SDK: the SDK API drifts between
releases (e.g. `list_tools`/`call_tool` decorators were removed in newer
versions). A minimal JSON-RPC 2.0 stdio implementation over the standard
library works against Cursor / VS Code / Claude Code / Copilot regardless of
which MCP SDK version the client ships.

Protocol: line-delimited JSON-RPC 2.0 over stdin/stdout (stdio transport).

Tools:
  - verify_code        -> detect_undefined_symbols
  - scan_hallucination -> scan_hallucination_words
  - check_plugin       -> check_plugin_conformance
  - sandbox_run        -> deterministic command execution (verification channel)
  - schema_validate    -> JSON Schema subset validator for structured outputs
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard_engine as engine  # noqa: E402

VERSION = "1.2.0"

# Loaded once at startup: AGENTSEED_CONFIG env, ${PLUGIN_DATA}/
# agentseed.config.json (Agent Plugins v1.0.0 §9.1), or ./agentseed.config.json.
CONFIG = engine.load_config()
CONFIG_ALLOWLIST = engine._config_str_list(CONFIG, "allowlist")
CONFIG_SEVERITIES = engine._config_severities(CONFIG)
try:
    CONFIG_TIMEOUT = int(CONFIG.get("timeout", 30))
except (TypeError, ValueError):
    CONFIG_TIMEOUT = 30


def _tool(name: str, description: str, props: dict, required: list[str]) -> dict:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": props,
            "required": required,
        },
    }


TOOLS = [
    _tool(
        "verify_code",
        "Static analysis to flag symbols the model may have hallucinated "
        "(called/used but never defined or imported). Supports python (AST) "
        "and typescript/javascript (lexical regex pass). Use before marking a "
        "coding task complete.",
        {
            "source": {"type": "string", "description": "Source code to analyze."},
            "language": {
                "type": "string",
                "description": "Source language: python | typescript | javascript.",
                "default": "python",
            },
        },
        ["source"],
    ),
    _tool(
        "scan_hallucination",
        "Scan source for hallucination signals in three groups: stub_code "
        "(stub/mock/fake/placeholder/todo/...), oversold (guaranteed/all tests "
        "pass/production ready/...), fabricated (simulated/invented/...). If "
        "any hit is found, the task must be downgraded to incomplete.",
        {
            "source": {"type": "string", "description": "Source code to scan."},
            "allowlist": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional case-insensitive prefixes to exclude "
                "from matching (e.g. ['Mock(']). Defaults to built-in test-idiom "
                "exclusions; pass [] to disable all exclusions.",
            },
        },
        ["source"],
    ),
    _tool(
        "check_plugin",
        "Validate a plugin directory against Agent Plugins 1.0.0 packaging "
        "(plugin.json / skills / mcp.json). Acts as the spec's missing "
        "official linter.",
        {
            "path": {
                "type": "string",
                "description": "Absolute path to the plugin root directory.",
            },
        },
        ["path"],
    ),
    _tool(
        "sandbox_run",
        "Deterministic execution channel: run a command (no shell) in a "
        "subprocess with a timeout and captured output. Turns 'tests pass' "
        "into an observed fact. Use to verify test suites, type checks, "
        "linters, or any claim that requires running code.",
        {
            "command": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Command as an argument list, e.g. ['python3', '-m', 'pytest'].",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (1-120, default 30).",
                "default": 30,
            },
            "cwd": {
                "type": "string",
                "description": "Working directory (optional).",
            },
        },
        ["command"],
    ),
    _tool(
        "schema_validate",
        "Validate structured output (JSON) against a JSON Schema subset "
        "(type/enum/const/minLength/maxLength/pattern/minItems/maxItems/items/"
        "properties/required/additionalProperties). Zero dependencies.",
        {
            "instance": {
                "description": "The value to validate (any JSON value).",
            },
            "schema": {
                "type": "object",
                "description": "The JSON Schema to validate against.",
            },
        },
        ["instance", "schema"],
    ),
]


def _dispatch(method: str, params: dict) -> dict:
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments", {}) or {}
        if name == "verify_code":
            result = engine.detect_undefined_symbols(
                args.get("source", ""), args.get("language", "python")
            )
        elif name == "scan_hallucination":
            # explicit tool arguments win over config-file values
            allowlist = args.get("allowlist")
            if allowlist is None:
                allowlist = CONFIG_ALLOWLIST
            result = engine.scan_hallucination_words(
                args.get("source", ""), allowlist, CONFIG_SEVERITIES
            )
        elif name == "check_plugin":
            result = engine.check_plugin_conformance(args.get("path", ""))
        elif name == "sandbox_run":
            timeout = args.get("timeout")
            result = engine.sandbox_run(
                args.get("command", []),
                int(timeout) if timeout is not None else CONFIG_TIMEOUT,
                args.get("cwd"),
            )
        elif name == "schema_validate":
            result = engine.schema_validate(
                args.get("instance"), args.get("schema", {})
            )
        else:
            return {"isError": True, "content": [{"type": "text", "text": f"Unknown tool: {name}"}]}
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, ensure_ascii=False, indent=2),
                }
            ]
        }
    return {"isError": True, "content": [{"type": "text", "text": f"Unsupported method: {method}"}]}


def _error(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def main() -> None:
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue

        msg_id = msg.get("id")
        method = msg.get("method", "")

        try:
            if method == "initialize":
                resp = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "agentseed", "version": VERSION},
                    },
                }
            elif method == "notifications/initialized":
                continue
            elif method == "ping":
                resp = {"jsonrpc": "2.0", "id": msg_id, "result": {}}
            elif method.startswith("tools/"):
                payload = _dispatch(method, msg.get("params", {}) or {})
                resp = {"jsonrpc": "2.0", "id": msg_id, "result": payload}
            else:
                # JSON-RPC 2.0 §5.1: unknown methods must be reported as the
                # error -32601 (Method not found), not as a result.
                resp = _error(msg_id, -32601, f"Method not found: {method}")
        except Exception as exc:  # noqa: BLE001 - never kill the session
            resp = _error(msg_id, -32603, f"Internal error: {exc}")

        try:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
        except BrokenPipeError:
            return  # client disconnected; exit quietly


if __name__ == "__main__":
    main()
