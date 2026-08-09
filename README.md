# AgentSeed

<!-- mcp-name: io.github.weed33834/agentseed -->

> **`pip install https://github.com/weed33834/agentseed/releases/download/v1.0.0/agentseed-1.0.0-py3-none-any.whl && agentseed forge`**

**🌐 [English](README.md) · [中文](README.zh.md) · [日本語](README.ja.md)**

**📦 [GitHub](https://github.com/weed33834/agentseed) (primary) · [Gitee](https://gitee.com/badhope/agentseed) · [Gitcode](https://gitcode.com/badhope/agentseed)**

![License](https://img.shields.io/badge/license-Apache_2.0-blue)
![CI](https://github.com/weed33834/agentseed/actions/workflows/ci.yml/badge.svg)
![Personas](https://img.shields.io/badge/personas-5-green)
![Platforms](https://img.shields.io/badge/platforms-15-orange)
![Tests](https://img.shields.io/badge/tests-171%20passing-brightgreen)
![Python](https://img.shields.io/badge/python-3.10%2B-informational)

---

You know the drill. Every time you open a new AI coding session, you spend the first 10 minutes reminding it not to hallucinate, not to run `rm -rf`, and what stack you're using. AgentSeed turns that into a **non-negotiable constraint layer**, then plugs in the **scenario pack** for your task context — once, and synced everywhere.

One command detects your project scenario, plugs in the matching scenario pack, and generates highly-constrained rule files for all your tools — Claude Code, Cursor, Copilot, Windsurf, Trae, whatever you use.

```bash
agentseed forge
```

That's it. From empty directory to a 1200-line AGENTS.md with safety rules, project-specific skills, and platform configs. Works the same whether you're coding, writing a novel, drafting a paper, or building another agent.

---

## What you get

**A baseline that doesn't get overwritten.** Core safety rules (don't rm -rf, don't hallucinate credentials, don't install things unprompted) are part of the governance kernel and ship with AgentSeed — no scenario pack can override them.

**Pluggable scenario packs.** Kernel default mode + four starter packs: `default` (kernel-general, built-in), `coding` (your dev default), `novel`, `paper`, `agent-builder`. Each pack bundles a scenario protocol, prompts, skills, and a capability whitelist, routed automatically from project anchors and user intent (or switched manually with `agentseed switch --profile novel`). Packs are pluggable and extensible — a new scenario is just a directory plus a manifest; the kernel never changes.

**All your tools, one sync.** Generates the right format for 15 platforms:
- Claude Code → `CLAUDE.md`
- Cursor → `.cursor/rules/project.mdc`
- Copilot → `.github/copilot-instructions.md`
- Windsurf → `.windsurfrules`
- Gemini → `GEMINI.md`
- Trae → `.trae/rules/project_rules.md`
- Cline → `.clinerules/project.md`
- Continue → `.continue/rules/project.md`
- Amazon Q → `.amazonq/rules/project.md`
- Qodo → `best_practices.md`
- Lingma → `.lingma/rules/project.md`
- Comate → `.comate/rules/project.mdr`
- Codex → `.codex/rules.md`
- QwenWork → `AGENTS.md` (read natively)
- AGENTS.md (works with 20+ tools that natively read it)

**Hooks with teeth.** Every platform gets a `pre_tool_use.py` interceptor that blocks dangerous operations before they execute. Fail-open design: if the hook crashes, the tool call goes through.

**MCP Server.** Run `agentseed serve` and any MCP-compatible client gets `governance_check` (P0 red-line check), `persona_list` (scenario packs), `persona_activate` (activate a pack), and `gap_detect`.

**Self-evolution.** AgentSeed scores capability gaps (missing tools, unknown domains) and suggests what to install. Not magic — just a weighted formula that gets better as you add more skills.

---

## Install

```bash
pip install https://github.com/weed33834/agentseed/releases/download/v1.0.0/agentseed-1.0.0-py3-none-any.whl
```

Or build from source:

```bash
git clone https://github.com/weed33834/agentseed.git
cd agentseed
pip install -e .
```

---

## Usage

```bash
agentseed forge              # detect project → assemble → generate
agentseed forge --dry-run    # preview what would be generated
agentseed forge --profile coding
agentseed forge --profile novel

agentseed switch --profile paper

agentseed sync               # sync to all platforms
agentseed sync --platform cursor

agentseed status             # what's assembled, what's missing

agentseed serve              # start MCP server (stdio)
agentseed serve --port 8080  # start MCP server (HTTP)

agentseed platform list      # 15 built-in platforms
agentseed platform import my-ide --entry .myide/rules.md --format markdown

agentseed pack list          # market catalog (installed status)
agentseed pack add novel     # install a single scenario pack on demand
agentseed pack new my-scenario  # scaffold a custom scenario pack

agentseed persona list       # list scenario packs (command name kept for compatibility)
agentseed persona search "product manager"
```

---

## Add your own platform

```bash
agentseed platform import my-editor --entry .myeditor/rules.md --format markdown --hook-dir .myeditor
```

This registers the platform, generates a pre-tool-use hook, and includes it in every `agentseed sync`.

---

## Project structure

```
core/                  governance kernel (P0 red lines, decision formulas, routing — immutable)
personas/              one directory per scenario pack (coding, novel, paper, … — pluggable)
capabilities/          capability plugins (testing, research, creative, … — on-demand)
adapters/hooks/        platform adapters: per-platform pre-tool-use interceptors
src/agentseed/         CLI, sync engine, router, forge, evolution
```

---

## vs. similar projects

- **agent-rules (steipete)** — archived, coding-only Cursor rules.
- **agents.md** — file format proposal; no content, no toolchain.
- **ACP** — agent config manager; no governance or self-evolution.
- **Cursor Directory / cursor.directory** — community rule snippets; no multi-platform sync.
- **AgentSeed** — governance kernel + pluggable scenario packs + 15-platform sync + hooks + self-evolution, all from one CLI.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Short version: edit source files in `core/`, `personas/`, or `capabilities/`; run `agentseed sync` to regenerate platform files; don't hand-edit generated files.

Tests: `python -m pytest tests/` (171 passing).

---

MIT
