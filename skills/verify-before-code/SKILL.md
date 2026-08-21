---
name: verify-before-code
description: >-
  Guardrail for coding agents. Loads the SDD contract and the prompt pool
  before code is written, then calls the agentseed MCP server's verify_code and
  scan_hallucination tools; a task may only be marked complete when both pass
  and the completion report attaches evidence. Use whenever the agent writes,
  edits, or claims completion of code.
license: MIT
compatibility: Requires Python 3.9+ for the MCP server. Zero required dependencies; optional extras (jsonschema, pyflakes, pyyaml) upgrade analysis engines with automatic fallback.
metadata:
  author: AgentSeed
  version: "1.0.0"
  spec: agent-plugins-1.0.0
---

# Verify Before Code

You are running inside an AgentSeed-guarded coding session. The AgentSeed MCP
server (`agentseed`) is available. Its job is to stop you from shipping
hallucinated or stubbed code. Follow the gates below **in order**, and treat
Gate 3 as non-skippable.

## Reference library (load as needed)

| Resource | Purpose |
| --- | --- |
| `references/SDD-CONTRACT.md` | the contract every coding task must satisfy |
| `references/PROMPT-POOL.md` | copy-paste guardrail prompts (completion claims, uncertainty, API verification, citation rules, etc.) |
| `references/HALLUCINATION-PATTERNS.md` | catalog of hallucination failure modes with signals and countermeasures |
| `references/VERIFICATION-CHECKLIST.md` | executable checklist for end-of-task verification |

## Gate 1 — Load the contract (BEFORE writing code)

Read `references/SDD-CONTRACT.md` before producing any implementation. It
defines the spec the code must satisfy. Do not write code against an unstated
or assumed contract; if the contract is missing, ask the user to supply it
first.

- State the contract you are coding against in one sentence.
- If the task cannot be expressed as a contract, stop and clarify.
- Classify output risk (Critical / High / Medium / Low) per the checklist —
  full rigor for Critical/High.

## Gate 2 — Implement against the contract

Write the smallest code that satisfies the contract. Prefer real, runnable
implementations over placeholders.

- **Never** emit `stub`/`mock`/`fake`/`placeholder`/`dummy`/`todo`/`fixme`/
  `tbd`/`not implemented`/`coming soon` as a substitute for working logic.
- **Never** call a symbol that is not defined or imported in this project.
- **Never** trust an API that you have not verified against the installed
  version (see PROMPT-POOL E1 — "never invent an API").
- **Never** assert a file's content or line numbers without reading it in this
  turn (PROMPT-POOL F1).

## Gate 3 — Verify BEFORE claiming done (MANDATORY, NON-SKIPPABLE)

Before you tell the user the task is complete, call BOTH tools on the final
source:

```
verify_code(source=<final source>, language="python")
scan_hallucination(source=<final source>)
```

**If the `agentseed` MCP tools are not available in this session**, do NOT
skip verification — degrade to the CLI equivalents via the shell:

```bash
python <agentseed-plugin-root>/server/guard_cli.py verify <changed-file> --language python
python <agentseed-plugin-root>/server/guard_cli.py scan  "<final source or file>"
```

Locate `<agentseed-plugin-root>` by (in order): the `AGENTSEED_PLUGIN_ROOT`
environment variable; a `.agentseed-plugin-root` file next to this skill;
walking up from this skill's directory until you find a directory containing
both `plugin.json` and `server/guard_cli.py`. The CLI uses the same gate
rules: exit code 0 = pass, 1 = blocking findings.

Decision rules:

- `verify_code` returns `suspects: []` AND `scan_hallucination` returns
  `blocking: false` → verification gate passed.
- `verify_code` returns any suspect (a symbol used/called but never defined or
  imported) → you likely hallucinated an API. Fix it (import it, define it, or
  replace it with a real call) and re-run.
- `scan_hallucination` returns hits. Severity decides what happens — check the
  `severity` field first:
  - `error` (any hit) → `blocking: true`; the task is **not** done. Fix the
    flagged lines and re-run. By default `oversold` and `fabricated` are
    errors: attach evidence or remove the claim/content.
  - `warning` (e.g. default for `stub_code`) → does not block, but you must
    mention it in the completion report; if it marks genuinely unfinished work,
    treat it like an error.
  - `info` → informational only; no action required.

Never mark a coding task complete while either tool still reports a *blocking*
problem (`suspects` non-empty or `blocking: true`). If you cannot resolve a
flag, report it explicitly to the user instead of claiming success.

Execution and structure are verified the same way — as observed facts, not
claims:

- Claims that require running code (tests pass, type check clean, linter ok)
  → prove them with `sandbox_run(["python3", "-m", "pytest", ...])` and cite
  the exit code + output.
- Structured outputs (JSON, config) → validate with
  `schema_validate(instance, schema)` before use. Never trust "it's valid" on
  self-assessment.

## Gate 4 — Language audit before the final message

Even when the gates pass, run the language audit (PROMPT-POOL C/D/G/J):

- Every statement is OBSERVED or labeled INFERRED.
- No overclaim vocabulary without evidence (`guaranteed`, `fully tested`,
  `production ready`, `should work`, `trust me`, ...).
- Uncertainty is expressed honestly; citations and statistics are real.
- Your completion report attaches evidence: the command run, the output, the
  file read. "Done, all tests pass" without the log is a claim, not a result.

## Optional — Validate the plugin itself

To check that this plugin conforms to Agent Plugins 1.0.0:

```
check_plugin(path=<absolute path to the agentseed plugin root>)
```

## Why this exists

Plain prompt-only guardrails are soft: a model can "agree" to verify and then
skip it. AgentSeed binds the soft Skill instruction to a hard MCP gate — the
evidence is generated by running code, not by the model's self-report. The
reference library turns every anti-hallucination principle from research into
an executable instruction.
