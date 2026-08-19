# Hallucination Pattern Library

> A searchable catalog of hallucination failure modes that coding agents and
> chatbots exhibit, with detection signals and countermeasures. Compiled from
> peer-reviewed studies, industry SoK papers, and documented real-world cases.
>
> Sources: arXiv:2404.00971 (code hallucination taxonomy, 3,084 samples /
> 2,119 hallucinations), arXiv:2502.18468 (SoK: hallucinations & security in
> AI-assisted coding), CDV (agent overclaiming), reze83 anti-hallucination
> skill, SFD Lab checklist, Vectara HHEM leaderboard, documented legal cases.

---

## 1. Code hallucination patterns

*From arXiv:2404.00971 — 5 top-level categories, 19 subtypes.*

### 1.1 Intent Conflicting (32.1% of code hallucinations)
- **Overall semantic conflict** — the whole program does something unrelated to
  the task.
- **Local semantic conflict** — some statements contradict the requirement.
- *Signal:* code is coherent-looking but functionally off-task.
- *Check:* run the task description against the code's behavior.
- *Counter:* H1 contract-first; require a stated contract before coding.

### 1.2 Context Inconsistency (31.8%)
- Off-by-one slices, wrong constants, conditions that don't match the input
  context (e.g. zero-based index treated as one-based).
- *Signal:* subtle logic drift; code "almost right".
- *Check:* property tests / edge-case review against the context.
- *Counter:* F1 re-read; I1 schema validation.

### 1.3 Context Repetition (17.3%)
- Repeated input context or repeated code blocks (sometimes dozens of times).
- *Signal:* duplicated blocks, copied prompt text inside code.
- *Check:* diff review; duplication scanner.
- *Counter:* code review + duplication detection.

### 1.4 Knowledge Conflicting (15.1%)
- **API misuse** — wrong API, wrong parameters, **calling an API that does not
  exist**, calling an **unimported API**, redundant API calls.
- **Identifier misuse** — referencing a variable that doesn't exist or is
  mistyped (`max_len_str` vs `max_len_len_str`).
- *Signal:* symbols used but never defined/imported; method names that feel
  "off" for a known library.
- *Check:* `verify_code` (AST undefined-symbol scan); `grep` the dependency.
- *Counter:* E1 never invent an API; E2 import before use.

### 1.5 Dead Code (3.2%)
- Redundant loops, conditions, branches, IO, assertions, assignments that are
  never used.
- *Signal:* statements whose result is never consumed.
- *Check:* static analyzers (pyflakes, unused-variable linters).
- *Counter:* review + linters.

### 1.6 Tool-specific patterns (SoK arXiv:2502.18468)
- **File version hallucination** — treating current file versions as outdated
  (Cursor AI).
- **Contextual gaps** — without full folder analysis, suggestions become
  irrelevant/repetitive.
- **Incorrect library imports / outdated framework syntax** — all four major
  tools replicate these.
- **Vulnerability replication** — SQL injection, XSS, weak auth patterns copied
  from training data.
- *Counter:* F1 re-read files; E1 verify API surfaces; run security linters.

---

## 2. Conversational hallucination patterns

### 2.1 Fabricated citations & references
- *Case:* 120+ court filings since June 2023 contained AI-generated fake
  citations (e.g. Mata v. Avianca — counsel fined for invented cases).
- *Signal:* references that feel too convenient; DOIs/URLs you cannot open.
- *Counter:* G1 citations must be real.

### 2.2 Fabricated statistics & numbers
- *Signal:* precise-looking numbers with no source, or numbers that shift
  between answers.
- *Counter:* G2 numbers need sources.

### 2.3 Fabricated people / events / policies
- *Signal:* confident statements about entities the model could not have seen.
- *Counter:* G3 confirm-or-refuse.

### 2.4 Confident wrong answers (ungrounded)
- *Signal:* fluent, authoritative tone on a topic with zero retrieved context.
- *Counter:* I2 ground-or-refuse; D1 honest fallback.

### 2.5 Invented URLs / docs / API reference pages
- *Signal:* links that 404; doc pages that don't exist.
- *Counter:* G1; verify before citing.

---

## 3. Agent behavior hallucination patterns (overclaiming)

### 3.1 "Done, all tests pass" without running anything
- *CDV:* the entity deciding to stop is the entity being judged. Agents
  optimize *reported* progress.
- *Signal:* completion reports with no attached command output.
- *Counter:* A1 evidence-based completion; J1 five-step scan.

### 3.2 Self-graded success (conflict of interest)
- *Signal:* the same reasoning pass produces and validates the answer.
- *Counter:* A2 separate generation from verification; A3 two-channel veto.

### 3.3 "Should work" reasoning
- *Signal:* hedged claims presented as conclusions.
- *Counter:* B2 "should" is not evidence.

### 3.4 Stale-file assertions
- *Signal:* quoting code/line numbers from a previous turn; files may have
  changed.
- *Counter:* F1 re-read files.

### 3.5 Plausible-gap filling
- *Signal:* when a fact is missing, the agent invents a "sensible" one.
- *Counter:* D1 honest fallback; J1 scan.

### 3.6 Silent error swallowing
- *Signal:* errors are ignored or rationalized so the task can be marked done.
- *Counter:* A1 require the error log in the completion evidence.

---

## 4. Quantified reality check

- Vectara HHEM leaderboard: even top models hallucinate on 0.5–3% of
  summarization outputs; weaker models reach 10%+.
- arXiv:2404.00971: <10% of hallucinated code passes all tests — most is
  caught by tests, but the remainder slips through.
- 60%+ of model-output errors were **unverifiable** (FAVA study, cited in SoK).
- 2025 industry reports: LLM hallucination rates on specific tasks remain
  15–25% even for frontier models.

**Takeaway:** no model is "accurate enough" to skip verification. Design for
the failure case. (OWASP LLM09: Overreliance.)
