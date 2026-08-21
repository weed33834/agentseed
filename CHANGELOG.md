# Changelog

All notable changes to AgentSeed are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com); versioning follows [SemVer](https://semver.org).

## [1.2.0] — 2026-08

### Added
- **Severity levels** for `scan_hallucination`: each hit carries `error` / `warning` / `info`; defaults block on oversold & fabricated claims, warn on stub markers. Result includes a `blocking` flag and severity counts. Group severities are remappable via config.
- **Persistent config** via Agent Plugins §9.1: `load_config()` resolves `agentseed.config.json` from `${PLUGIN_DATA}` (spec-guaranteed persistent per-plugin dir), `AGENTSEED_CONFIG`, or cwd. Keys: `allowlist`, `severities`, `timeout`.
- **CLI** (`server/guard_cli.py`, zero dependencies): `verify`, `scan`, `check --ci`, `sandbox` with CI-friendly exit codes — the same gates that bind agent sessions can now block human PRs. `scan --strict` restores strict matching with stub hits as errors.
- **Skill scripts**: `skills/verify-before-code/scripts/check.sh` / `check.ps1` one-command gate using the CLI.

### Changed — conformance linter (§7.2.1, §9.1)
- Server entries validated as closed variants: unknown fields are errors (e.g. `url` on stdio).
- stdio `command` must be a bare token or plugin-relative `./...` path; `args` string arrays enforced.
- `env` must not define reserved `PLUGIN_ROOT` / `PLUGIN_DATA`.
- Remote URLs: absolute HTTP(S), no userinfo/fragment, HTTPS required off-loopback; duplicate header names rejected.

## [1.1.0] — 2026-08

### Fixed
- `verify_code` (Python): collect all binding targets (assignments, `for`/`with`/`except as`, walrus, comprehensions, `global`/`nonlocal`) — ordinary local state no longer flagged as hallucinated symbols.
- `scan_hallucination`: skip import lines and dotted paths; default allowlist covers standard test doubles (`unittest.mock`, `Mock()`, `patch()`, …); new optional `allowlist` argument.
- `schema_validate`: `const: null` validated; boolean ≠ number in enum/const equality; `type` arrays supported.
- MCP server: unknown methods return JSON-RPC `-32601`; `ping` returns `{}`; internal errors return `-32603` without killing the session; BrokenPipe handled.
- Frontmatter parser tolerates `---` lines in body; TS analysis collects multi-declarations.

### Changed
- Tests use `sys.executable` (Windows portability); protocol and CLI test suites added.

## [1.0.0] — initial release
- Hybrid Skill + MCP guardrails: `verify_code`, `scan_hallucination`, `check_plugin`, `sandbox_run`, `schema_validate`. First strict Agent Plugins 1.0.0 linter. Zero dependencies (pure Python standard library).
