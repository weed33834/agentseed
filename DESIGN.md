# AgentSeed — Technical Design

> English technical design for AgentSeed. See [DESIGN.zh.md](./DESIGN.zh.md) for 中文.

## 1. Background & problem

### 1.1 The spec is real, but oversold

Agent Plugins **1.0.0** is a genuine open specification published in August 2026.
Its Technical Steering Committee draws one representative each from **Amazon,
Cursor, Microsoft, OpenAI, and Vercel**. Two corrections to the hype:

- **Google is NOT on the committee.** "Six giants jointly launched it" is content-farm
  inflation of "vendor-neutral standards body."
- It is a **packaging standard**, not a product. It standardizes the "box"
  (`plugin.json`, `skills/`, `mcp.json`) but deliberately leaves two gaps.

### 1.2 The two spec gaps (our opportunity)

1. **No enforcement mechanism.** A client *may* load a skill; nothing forces the
   model to actually verify its output before claiming done.
2. **No registry / marketplace / distribution** — distribution is open (directories,
   VCS). And crucially, **no official 1.0.0 linter** exists despite the spec's
   MUST/SHOULD rules.

### 1.3 Market gap

| Existing | What it does | What it misses |
| --- | --- | --- |
| mcpmarket `Anti-Hallucinate` | Behavioral guardrail, only keeps chat honest (don't invent citations/dates) | No code, no tooling |
| `obra/superpowers` | Prompt-only coding workflow | No hard verification |
| Typical MCP servers | Expose an API to the model | None *verify the model's own emitted code* |

AgentSeed fills: **code-level + real tooling + Skill/MCP closed-loop enforcement.**
`check_plugin` is a first-mover 1.0.0 linter.

## 2. Design goals

- **Cross-client** — conforms to 1.0.0, loads anywhere the spec is supported.
- **Closed-loop enforcement** — soft Skill instruction bound to a hard MCP gate.
- **Zero dependencies** — pure standard-library Python; no SDK version drift.
- **First-mover linter** — `check_plugin` for 1.0.0.

## 3. Architecture

```
            ┌─────────────────────────────────────────────┐
            │  Coding agent (Cursor / VS Code / Copilot)  │
            └───────────────┬───────────────┬─────────────┘
                            │ loads          │ launches (stdio)
                            ▼                ▼
                 ┌──────────────────┐  ┌──────────────────────────┐
                 │  Skill           │  │  MCP Server (agentseed)   │
                 │  verify-before-  │  │  guard_server.py          │
                 │  code            │  │    │                      │
                 │  (gate logic)    │  │    ▼                      │
                 └────────┬─────────┘  │  guard_engine.py          │
                          │ instructs  │   ├ detect_undefined_      │
                          │ agent to   │   │   symbols (AST)        │
                          │ call:      │   ├ scan_hallucination_    │
                          │            │   │   words (regex)        │
                          │            │   └ check_plugin_          │
                          ▼            │       conformance (JSON)   │
                 ┌──────────────────┐  └──────────────────────────┘
                 │  SDD-CONTRACT     │
                 │  (loaded before  │
                 │   coding)        │
                 └──────────────────┘

  Flow: load contract → implement → verify_code + scan_hallucination →
        both pass? → mark done. Otherwise fix and re-run.
```

### 3.1 Component responsibilities

| File | Role |
| --- | --- |
| `plugin.json` | 1.0.0 manifest (`name: agentseed`) |
| `mcp.json` | declares the stdio `agentseed` MCP server |
| `skills/verify-before-code/SKILL.md` | non-skippable 4-gate guardrail |
| `references/SDD-CONTRACT.md` | contract the agent must load before coding |
| `references/PROMPT-POOL.md` | 20+ copy-paste guardrail prompts (EN/ZH/JA) |
| `references/HALLUCINATION-PATTERNS.md` | failure-mode catalog (EN/ZH/JA) |
| `references/VERIFICATION-CHECKLIST.md` | executable end-of-task checklist (EN/ZH/JA) |
| `references/VENDOR-SOLUTIONS.md` | vendor technique adoption map (EN/ZH/JA) |
| `server/guard_engine.py` | pure-stdlib checks (5 capabilities) |
| `server/guard_server.py` | hand-written JSON-RPC stdio MCP server |

## 4. MCP interface contract

Transport: line-delimited JSON-RPC 2.0 over stdio. Server name `agentseed`,
version `1.0.0`, protocol `2024-11-05`.

### 4.1 `initialize` → result
```json
{ "protocolVersion": "2024-11-05",
  "capabilities": { "tools": {} },
  "serverInfo": { "name": "agentseed", "version": "1.0.0" } }
```

### 4.2 `tools/list` → tools
- `verify_code(source: string, language?: "python")` → `{language, suspects[], note}`
- `scan_hallucination(source: string)` → `{hits[{word,group,line}], clean: bool, groups{}}`
- `check_plugin(path: string)` → `{ok: bool, errors[], warnings[]}`
- `sandbox_run(command: string[], timeout?: int, cwd?: string)` →
  `{exit_code, stdout, stderr, timed_out}`
- `schema_validate(instance: any, schema: object)` → `{valid: bool, errors[]}`

### 4.3 `tools/call` example
Request:
```json
{ "jsonrpc":"2.0", "id":3, "method":"tools/call",
  "params": { "name":"verify_code",
              "arguments": { "source":"def f():\n    return magic_unknown()\n",
                             "language":"python" } } }
```
Response (text content carries the JSON result):
```json
{ "content": [ { "type":"text",
  "text": "{\"language\": \"python\", \"suspects\": [\"magic_unknown\"], \"note\": \"...\"}" } ] }
```

## 5. Key algorithms

### 5.1 `detect_undefined_symbols`
Two backend passes:
- **Python (AST):** parse with `ast`, collect defined names (builtins, imports
  asnames, def/class names, args), then walk for `Name`/`Call` loads not in the
  defined set.
- **TypeScript/JavaScript (lexical):** regex pass collecting imports (named/
  default/namespace/destructured), declarations (function/class/interface/type/
  enum/const/let/var), function params, then flags top-level calls and `new`
  expressions whose callee is never defined (member access `obj.foo()` is not
  flagged; keywords/globals are whitelisted).
**Scope/limits:** static only, no runtime; the TS pass is lexical, not a type
checker — dynamic/global references may produce false positives, destructured
edge cases may be missed.

### 5.2 `scan_hallucination_words`
Word-boundary regex scan over a **grouped pool of 28+ signals**:
- `stub_code`: stub/mock/fake/placeholder/dummy/todo/fixme/xxx/tbd/tba/wip/
  "not implemented"/"coming soon"
- `oversold`: guaranteed/"definitely works"/"all tests pass"/"everything works"/
  "fully tested"/"production ready"/"no bugs"/"works perfectly"/"should work"/
  "trust me"/"works on my machine"/"100% correct"/"bug free"/"zero errors"
- `fabricated`: simulated/hypothetical/imaginary/invented/fabricated/fictional/
  pretend/"made up"
Returns `hits[]` (word/group/line), `clean`, and per-group counts.
Source: SFD Lab 5-step anti-hallucination checklist (step 5); CDV
("'done, all tests pass' is a claim, not evidence"); reze83
verify-before-claim rules.

### 5.3 `check_plugin_conformance`
Validates `plugin.json` (`$schema` = 1.0.0 address, required `name`, valid JSON),
each `skills/*/SKILL.md` presence, and `mcp.json` (`$schema`, `mcpServers`).
Returns `ok`, `errors[]`, `warnings[]`.

## 6. 1.0.0 conformance checklist

| Spec section | Requirement | AgentSeed |
| --- | --- | --- |
| §5.2 manifest | root `plugin.json`, closed schema (only `$schema`/`name`/`version`/`description`/`author`/`homepage`/`repository`/`license`/`keywords`/`extensions`) | ✅ |
| §5.3 required | `$schema` = 1.0.0 address; `name` required | ✅ |
| §5.5 name | 1–64 chars, `[a-z0-9.-]`, alphanumeric ends, no `--`/`..` | ✅ |
| §5.4 metadata | `repository`/`homepage`/`license` are strings; `author` limited to `name`/`email`/`url` | ✅ |
| §6.1/§7.1 skills | `skills/<name>/SKILL.md`; Agent Skills frontmatter (name matches dir, description ≤1024) | ✅ |
| §7.2 mcp.json | only `$schema` + `mcpServers`; stdio server with `command`, `cwd` = `${PLUGIN_ROOT}` | ✅ |
| §8 discovery | client reads manifest + skills + mcp | ✅ (by design) |
| §11 linter | (spec ships none) | ✅ `check_plugin` strict 1.0.0 linter |

## 7. Competitive comparison

| | Anti-Hallucinate | superpowers | **AgentSeed** |
| --- | --- | --- | --- |
| Touches code | ❌ | prompt only | ✅ AST |
| Runs tools | ❌ | ❌ | ✅ MCP |
| Enforcement | soft | soft | **hard gate** |
| 1.0.0 linter | ❌ | ❌ | ✅ |

## 8. Roadmap (moat)

1. Extend `verify_code` to Go (TS/JS lexical pass already shipped in v1.0).
2. Add `sandbox_run` — actually execute tests/commands in a sandbox
   (implements CDV Channel A deterministic floor).
3. Add `check_contract` — ingest the user's private spec as the contract.
4. Wire the PROMPT-POOL into per-client configs (Cursor rules, CLAUDE.md,
   AGENTS.md) so the prompts apply outside plugin-aware clients.
5. Ship the missing **registry** for 1.0.0 distribution.

## 9. Risks

- Static scope analysis → false negatives on dynamic/attribute access.
- Spec is young (Aug 2026); client adoption and schema may shift.
- Enforcement depends on the client honoring the skill's gate instruction.

## 10. Build & test

```bash
python3 server/guard_engine.py                 # self-check + demos
# MCP handshake + a tools/call:
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize",...}' \
            '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
            '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | python3 server/guard_server.py
```
