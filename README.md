<div align="center">

# 🛡️ AgentSeed

**Anti-hallucination guardrails for AI coding agents.**

A hybrid [Agent Plugins 1.0.0](https://agent-plugins.org) plugin (Skill + MCP Server) that forces spec-driven development and **verifies code before it is marked done** — so "Done, all tests pass" becomes an observed fact, not a claim.

[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.3.0-blue)](https://github.com/weed33834/AgentSeed/releases)
[![Agent Plugins](https://img.shields.io/badge/Agent%20Plugins-1.0.0-purple)](https://agent-plugins.org)
[![CI](https://github.com/weed33834/AgentSeed/actions/workflows/ci.yml/badge.svg)](https://github.com/weed33834/AgentSeed/actions)
[![Stars](https://img.shields.io/github/stars/weed33834/AgentSeed)](https://github.com/weed33834/AgentSeed)
[![Platforms](https://img.shields.io/badge/platform-Cursor%20%7C%20VS%20Code%20%7C%20Claude%20Code%20%7C%20Copilot-blue)](https://agent-plugins.org)

**English** · [中文](./README.zh.md) · [日本語](./README.ja.md)

⭐ **Like this project? Consider giving it a star — it helps developers find guardrails before they ship hallucinated code.**

</div>

---

## Why AgentSeed

LLMs hallucinate — in code, that means **invented APIs, undefined identifiers, fake test passes, and confident overclaims**. The numbers:

- **15.1%** of code hallucinations are knowledge-conflicting: calling APIs that don't exist or were never imported ([arXiv:2404.00971](https://arxiv.org/abs/2404.00971)).
- **<10%** of hallucinated code fails tests — most slips through CI ([arXiv:2404.00971](https://arxiv.org/abs/2404.00971)).
- **60%+** of model-output errors are *unverifiable* — no way to tell fact from fiction (FAVA, cited in [SoK](https://arxiv.org/abs/2502.18468)).

Prompt-only guardrails are soft: a model can *agree* to verify and then skip it. **AgentSeed binds the instruction to a hard MCP gate** — the evidence comes from running code, not from the model's self-report.

It also fills two gaps the 1.0.0 spec deliberately leaves open:

| Gap in Agent Plugins 1.0.0 | What AgentSeed does |
| --- | --- |
| No enforcement mechanism (skills are optional to follow) | `verify-before-code` skill makes verification **non-skippable** |
| No official conformance linter | `check_plugin` is the **first strict 1.0.0 linter** |

## What it does

Five MCP tools — zero *required* dependencies, enhanced by optional extras:

| Tool | Catches | Technique |
| --- | --- | --- |
| `verify_code` | Invented APIs / undefined symbols | Python AST + TS/JS lexical pass |
| `scan_hallucination` | Placeholder code, overclaims, fabricated content | 28+ signals in 3 groups |
| `check_plugin` | Non-conformant plugin packaging | Strict 1.0.0 linter |
| `sandbox_run` | "Tests pass" without running anything | Deterministic execution channel |
| `schema_validate` | Invalid structured output | JSON Schema validation |

## Live demo

```
$ verify_code(source="def f():\n    return magic_unknown()\n", language="python")
{
  "language": "python",
  "suspects": ["magic_unknown"]      # ← hallucinated API caught
}

$ scan_hallucination(source="The feature is production ready, all tests pass. Trust me.")
{
  "hits": [
    {"word": "all tests pass", "group": "oversold", "line": 1},
    {"word": "production ready", "group": "oversold", "line": 1},
    {"word": "trust me", "group": "oversold", "line": 1}
  ],
  "clean": false                      # ← overclaim caught
}

$ check_plugin(path="/path/to/AgentSeed")
{ "ok": true, "errors": [], "warnings": [] }   # ← strict 1.0.0 conformance
```

## Quick start

**Option A — download a release (no git needed):**

```bash
# grab the latest asset from https://github.com/weed33834/AgentSeed/releases
# or use the installer, which drops it into a client of your choice:
bash install.sh --client auto        # macOS / Linux
./install.ps1 -Client auto           # Windows PowerShell
# --client: claude | opencode | cursor | manual
```

**Option B — clone:**

```bash
git clone https://github.com/weed33834/AgentSeed.git
# or: https://gitcode.com/badhope/AgentSeed · https://gitee.com/badhope/AgentSeed
```

1. **Drop** the `AgentSeed/` directory into any client that supports Agent Plugins 1.0.0 (Cursor, VS Code, Claude Code, Copilot…). No build, no install; zero required dependencies (optional extras below).
2. The client auto-discovers the `verify-before-code` skill and the `agentseed` MCP server from `plugin.json` + `mcp.json`.
3. **That's it.** The skill now gates every coding task: contract → implement → verify → evidence.

Run it standalone for a self-check:

```bash
python3 server/guard_engine.py              # conformance + demos
python3 -m unittest discover -s server      # 50+ unit tests
```

Gate a human PR with the same rules (CI mode):

```bash
python3 server/guard_cli.py check . --ci    # plugin conformance, exit 1 on errors
python3 server/guard_cli.py scan src/ --strict   # hallucination scan, blocking severities only
```

> **Windows note:** `mcp.json` launches the server via `python3`. On many
> Windows installs that alias is a Microsoft Store stub; if the server fails
> to start, change `command` to `["python", "server/guard_server.py"]` or
> point it at your interpreter's absolute path.

## Optional dependencies

AgentSeed runs on the Python standard library alone. Installing the extras
upgrades two tools to industry-standard engines (auto-detected, graceful
fallback either way):

```bash
pip install -r server/requirements.txt
```

| Extra | Upgrades | Without it |
| --- | --- | --- |
| `jsonschema` | `schema_validate` → full Draft 2020-12 validation | built-in subset validator |
| `pyflakes` | `verify_code` → pyflakes F821 undefined-name analysis | built-in AST walk |
| `pyyaml` | SKILL.md frontmatter parsing → full YAML | built-in lite parser |

## Platform support

| Client | Agent Plugins 1.0.0 | Status | Notes |
| --- | --- | --- | --- |
| Claude Code | skills + MCP config | verified | skills via `~/.claude/skills`, server via `claude mcp add` |
| opencode | skills + MCP config | verified | `~/.config/opencode/opencode.json`, see docs |
| Cursor | skills + mcp.json | untested* | copy into project; no stable plugin dir yet |
| VS Code (+Copilot) | MCP support rolling out | untested* | use mcp.json fields as-is |
| Cline / Windsurf | MCP config compatible | untested* | stdio server entry maps directly |

\* honest states: the formats are spec-compatible and expected to work, but we
have not run AgentSeed in these clients ourselves. Verified = actually exercised
by the maintainers. If you verify one, open a PR updating this table.

Clients honoring the full spec also set `${PLUGIN_DATA}`; AgentSeed reads
`agentseed.config.json` from there (allowlist, severity map, sandbox timeout).

## Changelog

See [CHANGELOG.md](./CHANGELOG.md).

## Built-in guardrail library (EN / 中文 / 日本語)

| Resource | Contents |
| --- | --- |
| `PROMPT-POOL` | 20+ copy-paste guardrail prompts: completion evidence, verify-before-claim, uncertainty, API verification, citation rules… |
| `HALLUCINATION-PATTERNS` | Failure-mode catalog: 5-class code taxonomy + SoK findings + real legal/chat cases |
| `VERIFICATION-CHECKLIST` | Executable end-of-task checklist: risk class → contract → evidence → language audit |
| `SDD-CONTRACT` | The contract every coding task must satisfy |
| `VENDOR-SOLUTIONS` | Adoption map of vendor techniques (Anthropic, OpenAI, AWS, NVIDIA, IBM, Guardrails AI, Vectara) |

## How the gate works

1. **Before coding** — load the SDD contract, state it in one sentence.
2. **Implement** — real code only: no placeholders, no invented APIs.
3. **Before "done"** — call `verify_code` + `scan_hallucination`; prove runtime claims with `sandbox_run`; validate structure with `schema_validate`.
4. **Language audit** — completion reports attach evidence; overclaim vocabulary is banned.
5. Only when **all checks pass** may the task be marked complete.

## Why AgentSeed vs. alternatives

| | Anti-Hallucinate (mcpmarket) | superpowers | **AgentSeed** |
| --- | --- | --- | --- |
| Touches code | ❌ chat-only | prompt-only | ✅ AST analysis |
| Runs tools | ❌ | ❌ | ✅ 5 MCP tools |
| Enforcement | soft | soft | **hard gate** |
| 1.0.0 conformance linter | ❌ | ❌ | ✅ first |

## Roadmap

- [x] Hybrid Skill + MCP guardrail, 5 tools — first strict 1.0.0 linter
- [x] Prompt pool + pattern library + grouped signals + vendor techniques
- [x] `verify_code` for TypeScript / JavaScript (zero-dependency lexical pass)
- [ ] `verify_code` for Go
- [ ] Grammar-constrained decoding for structured outputs
- [ ] Optional remote fact-checker (HHEM-style) MCP server

## FAQ

**Does it need a specific LLM?** No — it's client-agnostic and model-agnostic. The gate is enforced by the skill + MCP server, not by any model.

**Zero dependencies?** Yes. The entire MCP server is pure Python standard library.

**Conformant?** `check_plugin` validates the plugin against 1.0.0 §5/§6/§7 — and AgentSeed passes its own linter (`ok: true`).

## Contributing

Issues, PRs and ideas welcome. See the [roadmap](#roadmap) for directions — or open an issue for a hallucination pattern we haven't catalogued yet.

## License

MIT © AgentSeed. See [LICENSE](./LICENSE).

---

<div align="center">

⭐ **If AgentSeed saved you from shipping hallucinated code, star the repo — it's the best signal that guardrails matter.**

</div>
