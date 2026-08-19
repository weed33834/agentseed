# SDD Contract — Spec-Driven Development Guardrails

This contract is loaded by the `verify-before-code` skill **before** any code is
written. A coding task is only acceptable when it can be expressed against this
contract and then passes the AgentSeed MCP gates.

## 1. What a task contract must state

Before coding, the agent must be able to answer all of:

- **Goal** — what behavior the code must produce.
- **Interface** — the exact function/class/endpoint names and signatures the
  code exposes (no inventing names the caller did not ask for).
- **Inputs & outputs** — types and shapes, including error cases.
- **Non-goals** — explicitly what is out of scope (YAGNI).
- **Verification** — how "done" is proven (a test, a command, or a tool call).
- **Risk class** — Critical / High / Medium / Low (see the checklist).

If any of these is unknown, the agent must stop and ask, not guess.

## 2. Forbidden patterns (hallucination signals)

The following in produced code means the task is **not** done:

- `stub`, `mock`, `fake`, `placeholder`, `dummy`, `todo`, `fixme`, `tbd`,
  `tba`, `not implemented`, `coming soon` as a stand-in for real logic.
- Calling a function/class that is never defined or imported in the project
  (Knowledge-Conflicting hallucination — invented APIs are 15.1% of code
  hallucinations per arXiv:2404.00971).
- Calling an API that exists only in docs-for-latest but not in the installed
  version (check the lock file first).
- Returning a hardcoded value where a computed or fetched value was required.
- Referring to a file's content or line numbers without reading it in the
  current turn (files may have changed).
- Overclaim vocabulary in a completion report without attached evidence:
  `guaranteed`, `definitely works`, `all tests pass`, `everything works`,
  `fully tested`, `production ready`, `no bugs`, `works perfectly`,
  `should work`, `trust me`.

## 3. Verification gates (run by the agentseed MCP server)

| Tool | Pass condition |
| --- | --- |
| `verify_code` | `suspects` is empty (no undefined/unimported symbols used) |
| `scan_hallucination` | `clean` is `true` and no `stub_code` / `oversold` / `fabricated` hits |

Both must pass before the agent reports completion. Completion reports must
attach the evidence that produced the pass (the command, the output, the file).

## 4. Failure handling

When a gate fails, the agent must:

1. Read the flagged symbol/line and its `group` (`stub_code` / `oversold` /
   `fabricated`).
2. Either implement/import it correctly, or replace it with a real dependency,
   or attach the missing evidence.
3. Re-run the gate until it passes.
4. Only if a flag is genuinely unavoidable, surface it to the user — never
   silently mark done.

## 5. Companion resources

- `PROMPT-POOL.md` — copy-paste prompts for every rule in this contract.
- `HALLUCINATION-PATTERNS.md` — the failure-mode catalog behind these rules.
- `VERIFICATION-CHECKLIST.md` — the executable end-of-task checklist.
