# Verification Checklist

> The executable counterpart of the guardrail. Run this checklist at the end of
> any coding task. Inspired by: SFD Lab 5-step checklist, DevelopersGlobal
> hallucination-prevention (risk classification + verification layers), CDV
> dual-channel verification, reze83 verify-before-claim rules.

---

## Phase 0 — Risk classification (before starting)

Classify the task's output risk:
- **Critical** — wrong output causes harm (code executed, legal, financial, medical).
- **High** — wrong output wastes significant effort (large refactors, deployments).
- **Medium** — wrong output is annoying but recoverable.
- **Low** — cosmetic.

Apply full rigor to Critical/High; lighter checks to Medium/Low.

- [ ] Risk class assigned before implementation starts.

## Phase 1 — Contract check (before coding)

- [ ] I can state the contract in one sentence (behavior / interface / scope).
- [ ] No assumption is silently baked in — unknowns were asked, not guessed.
- [ ] The target interface exists or is explicitly proposed for approval.

## Phase 2 — Implementation hygiene

- [ ] No stub / mock / fake / placeholder / dummy / TODO / FIXME as logic.
- [ ] Every called symbol is defined or imported in this project.
- [ ] Every external API used was checked against the **installed** version
      (lock file), not the latest docs.
- [ ] No dead code: every statement's result is consumed.
- [ ] Security basics: input validation, no SQL injection/XSS patterns, no
      hardcoded secrets.

## Phase 3 — Execution evidence (the hard gate)

- [ ] I ran the test suite and can paste the command + output.
- [ ] I ran the code end-to-end (not a partial path).
- [ ] Deployment/serving layer is confirmed live (if claimed).
- [ ] I re-read any file I cite in this turn; no stale-file assertions.
- [ ] Claims that require running code were proven via `sandbox_run`.
- [ ] Structured outputs passed `schema_validate`.
- [ ] `verify_code` → `suspects` empty.
- [ ] `scan_hallucination` → `clean: true` (no stub/oversold/fabricated hits).

## Phase 4 — Language audit (final answer)

- [ ] Every statement is OBSERVED or labeled INFERRED.
- [ ] No overclaim vocabulary without evidence:
      guaranteed / definitely works / all tests pass / everything works /
      fully tested / production ready / no bugs / works perfectly /
      should work / trust me.
- [ ] Uncertainty is expressed ("I need to check X", "I'm not certain"),
      never masked.
- [ ] Citations, links, statistics are real and attributable.

## Phase 5 — Downgrade rule

If **any** item above is unchecked for a Critical/High task, the task is NOT
complete. Downgrade to "in progress", report exactly which checks failed, and
list the remaining work. Never silently mark done.

---

### Quick gate (for chat-style answers, non-coding)

1. Would a reader be able to verify my key claims from what I provided?
2. Did I cite anything I haven't actually seen?
3. Am I phrasing uncertainty honestly?
4. Did I invent any number, name, link, or policy?
