# Vendor Solutions — Anti-Hallucination Techniques & Adoption Status

> A curated map of anti-hallucination techniques from major vendors, academia,
> and the MCP ecosystem — and where each one lives inside AgentSeed.
>
> Adoption legend: ✅ imported (prompt/rules) · 🛠 implemented as an AgentSeed
> MCP tool · ➡️ recommended for a future release · 📄 documented as reference.

## 1. Adoption matrix

| Technique | Source | Core mechanism | In AgentSeed |
| --- | --- | --- | --- |
| "I don't know" fallback | Anthropic / OpenAI | allow uncertainty instead of guessing | ✅ PROMPT-POOL D1/D2 |
| Direct-quote grounding | Anthropic | extract quotes before reasoning | ✅ PROMPT-POOL C1/G1 |
| Verify-with-citations | Anthropic | claim → find supporting quote, else retract | ✅ PROMPT-POOL G1-J1 |
| Chain-of-thought verification | Anthropic / academia | separate reasoning pass as critic | ✅ PROMPT-POOL A2 |
| Best-of-N / self-consistency | Anthropic / academia | run N times, compare outputs | ✅ PROMPT-POOL J3/J4 |
| Iterative refinement | Anthropic | feed output back for re-check | ✅ PROMPT-POOL J3/J4 |
| External knowledge restriction | Anthropic | only provided docs, not general knowledge | ✅ PROMPT-POOL I2 |
| Grounding / RAG | Google / Microsoft / Progress | answer anchored in retrieved sources | ✅ PROMPT-POOL I2 |
| Instruction hierarchy | OpenAI | system > user > model in conflict | 📄 recommended |
| Structured outputs (JSON Schema) | OpenAI / Guardrails AI | schema-validate before trust | 🛠 `schema_validate` |
| Input/output guardrails | OpenAI Agents SDK | halt pipeline on violations | ✅ 4-gate SKILL |
| Deterministic execution | CDV / sandboxed tool use | run the test, observe the result | 🛠 `sandbox_run` |
| Dual-channel min-fusion | CDV | deterministic + LLM critic, veto wins | ✅ SKILL Gate 3/4 |
| Static AST analysis | Axivion / tree-sitter MCP | undefined symbols = invented APIs | 🛠 `verify_code` |
| NeMo five rail types | NVIDIA NeMo Guardrails | input/dialog/retrieval/execution/output | ✅ mapped to 4 gates |
| Automated Reasoning checks | AWS Bedrock | mathematical verification of policies | 📄 recommended |
| Granite Guardian risk flags | IBM | guardrail model flags hallucination/harm | 📄 recommended |
| Validator hub (50+) | Guardrails AI | pluggable validators (PII, toxicity...) | ✅ PROMPT-POOL (subset) |
| Hallucination eval model | Vectara HHEM | detect unsupported content in summaries | 📄 recommended |
| SelfCheckGPT / FActScore | academia | sample-based / fact-grounded checks | 📄 recommended |
| Constrained decoding | academia (outlines) | grammar-constrained generation | ➡️ roadmap (TS/Go + grammar) |
| Hallucination-pattern taxonomy | arXiv:2404.00971 | 5-class code hallucination catalog | ✅ HALLUCINATION-PATTERNS |

## 2. Tool capabilities

| New capability | Type | Technique imported |
| --- | --- | --- |
| `sandbox_run` | MCP tool | Deterministic execution channel (CDV Channel A / Anthropic verify-with-execution / AWS reasoning spirit) — "tests pass" becomes an observed fact |
| `schema_validate` | MCP tool | Structured-output validation (OpenAI structured outputs / Guardrails AI validators / OWASP LLM09) — schema before trust |
| Best-of-N + iterative refinement | PROMPT-POOL | Anthropic advanced techniques J3/J4 |
| VENDOR-SOLUTIONS | reference doc | full adoption map (this file) |

## 3. Recommended next (future releases)

1. **Constrained decoding / grammar** — wire `schema_validate`'s schema into
   generation (outlines-style) so the model can only emit conformant JSON.
2. **HHEM-style fact checker** — optional remote MCP server wrapping a
   hallucination-eval model for long-form summaries.
3. **Sandbox isolation hardening** — resource caps (memory/network/fs) for
   `sandbox_run` (Docker/gVisor backend).
4. **TypeScript/Go static analysis** — tree-sitter-based `verify_code` for
   non-Python projects (current AST pass is Python-only).

## 4. Why these stay conformant

Everything above lives inside the `skills/` + `mcp.json` packaging defined by
Agent Plugins 1.0.0 (§6/§7). The spec constrains *how* a plugin is packaged and
discovered — it never constrains *what* a skill teaches or *what* tools an MCP
server exposes. New tools are pure standard-library Python (zero deps), so no
client-side installation is required.
