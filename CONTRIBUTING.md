# Contributing to AgentSeed

Thanks for helping guard AI coding agents. Any contribution — a new
hallucination pattern, a bug report, a verified platform — makes the gate
better.

## Quick start

```bash
git clone https://github.com/weed33834/AgentSeed.git
cd AgentSeed
python -m unittest discover -s server -p "test_*.py"   # 56 tests, no deps needed
python server/guard_cli.py check . --ci                # must print ok: true
```

Optional extras used by the test suite when present:
`pip install -r server/requirements.txt`

## Ground rules

- **Zero required dependencies.** The plugin must run on a bare Python 3.9+.
  Third-party libraries are welcome only behind an optional import with a
  working stdlib fallback (see `server/engine/schema.py` for the pattern).
- **Every behavior change ships with tests.** CI runs the suite both with and
  without dependencies installed; both must pass.
- **The plugin must stay self-conformant**: `guard_cli.py check . --ci` is part
  of CI and blocks merges.
- Match the existing code style (stdlib, type hints, no comments unless the
  logic genuinely needs one).

## Adding a hallucination pattern

1. Add the token to the right group in `server/engine/hallucination.py`
   (`STUB_TOKENS` / `OVERSOLD_TOKENS` / `FABRICATED_TOKENS`).
2. Add a test in `server/test_guard.py` proving it fires — and, importantly,
   a case proving legitimate usage does *not* fire.
3. Update `CHANGELOG.md`.

## Reporting a false positive

False positives are bugs. Open an issue with:

- the exact source line that was flagged,
- which tool/group/severity fired,
- why the line is legitimate.

## Reporting a verified client

Ran AgentSeed in Cursor / VS Code / Cline / anything? Open a PR updating the
Platform support table in all three READMEs (`verified` + how you configured
it). Verified rows are the single most-trusted signal for new users.

## Pull requests

- Branch from `main`, keep commits atomic.
- CI must be green (tests × OS × Python matrix, bare job, conformance gate).
- Update `CHANGELOG.md` under an appropriate heading.
