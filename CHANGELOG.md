# Changelog

All notable changes to AgentSeed are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com); versioning follows [SemVer](https://semver.org).

## [1.3.3] — 2026-08

### Added
- **Compatibility & graceful-degradation matrix** in the READMEs: full Agent Plugins clients (drop-in) → MCP-only clients → skills-only clients → plain terminal/CI, each with a defined setup path.
- **CLI fallback built into the skill**: when the `agentseed` MCP tools are not registered in the session, SKILL.md/zh/ja now instruct the agent to run `guard_cli.py verify/scan` via the shell and apply the same blocking rules — verification is never silently skipped.
- CI: `macos-latest` added to the test matrix; POSIX skill-script smoke now runs on macOS too.

## [1.3.2] — 2026-08

### Fixed
- Skill scripts check `.agentseed-plugin-root` at both the `scripts/` and skill-root level; the v1.3.1 installers shipped scripts that missed the skill-root copy, so freshly installed check.ps1/check.sh still could not locate guard_cli.py. Verified against a real installer run.

## [1.3.1] — 2026-08

### Fixed
- **Installers rewired after an end-to-end fresh-clone audit**: full plugin now lives at a stable home (~/.agentseed/AgentSeed) so the MCP server path never breaks; skill is copied *flat* (SKILL.md at the top level) so clients that scan one level deep actually discover it; installer prints the exact MCP registration step for claude/opencode/cursor.
- Skill scripts resolve guard_cli.py via AGENTSEED_PLUGIN_ROOT, a .agentseed-plugin-root pointer file written by the installer, or directory walk-up.
- install.ps1: replaced PowerShell 7-only ?? operator (parse error on Windows PowerShell 5.1).

### Added
- Community files: CONTRIBUTING.md, bug/feature issue templates, pull request template.
- READMEs: exact per-client configuration snippets (Claude Code, opencode, generic MCP).

## [1.3.0] — 2026-08

### Changed — modular engine, standard libraries over hand-rolled code
- `guard_engine.py` split into the `server/engine/` package (config / hallucination / plugin / sandbox / schema / symbols); `guard_engine.py` remains as the import hub.
- **schema_validate** now delegates to [`jsonschema`](https://pypi.org/project/jsonschema/) (Draft 2020-12, full keyword coverage) when installed; a built-in subset validator keeps bare environments working. Results report which validator ran (`validator` field).
- **verify_code** (Python) uses [`pyflakes`](https://pypi.org/project/pyflakes/) F821 analysis when available for more reliable undefined-name detection; zero-dep AST walk remains the fallback.
- SKILL.md frontmatter parsing uses PyYAML when available; lite parser remains the fallback.
- Optional extras: `pip install -r server/requirements.txt` (jsonschema, pyflakes, pyyaml). The plugin still runs without any of them.

### Fixed
- Skill rules and tool text aligned with the severity model (only error-severity hits block; warnings reported but non-blocking).
- `serverInfo` version is now read from root `plugin.json` (single source of truth) instead of a drifting literal.
- Skill scripts (`check.sh`/`check.ps1`) locate the CLI by walking up to the plugin root or `AGENTSEED_PLUGIN_ROOT`; ps1 no longer assigns to the reserved `$args` variable.
- Install scripts dropped speculative Cursor/VS Code auto-paths; platform matrix marks only actually-exercised clients as verified.
- CI: main matrix installs requirements.txt; a new `bare` job pins the zero-dependency fallback path so an unconditional import cannot land again.

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
