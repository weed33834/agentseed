"""AgentSeed hallucination word scanning.

Flags tokens across three signal groups:
  - stub_code:     stub/mock/fake/placeholder/dummy/todo/...
  - oversold:      guaranteed/"all tests pass"/"production ready"/...
  - fabricated:    simulated/hypothetical/imaginary/invented/...
"""

from __future__ import annotations

import re

from .config import _VALID_SEVERITIES

# ---------------------------------------------------------------------------
# Hallucination token pools (grouped by signal type).
# ---------------------------------------------------------------------------

STUB_TOKENS = [
    "stub", "mock", "fake", "placeholder", "dummy",
    "todo", "fixme", "xxx", "tbd", "tba",
    "wip", "not implemented", "coming soon",
]

OVERSOLD_TOKENS = [
    "guaranteed", "definitely works", "all tests pass", "everything works",
    "fully tested", "production ready", "no bugs", "works perfectly",
    "should work", "trust me", "works on my machine", "100% correct",
    "bug free", "zero errors",
]

FABRICATED_TOKENS = [
    "simulated", "hypothetical", "imaginary", "invented",
    "fabricated", "fictional", "pretend", "made up",
]

# Full pool: token -> group (kept for backward compatibility).
HALLUCINATION_WORDS: dict[str, str] = {}
for _tokens, _group in [
    (STUB_TOKENS, "stub_code"),
    (OVERSOLD_TOKENS, "oversold"),
    (FABRICATED_TOKENS, "fabricated"),
]:
    for _t in _tokens:
        HALLUCINATION_WORDS[_t] = _group

_GROUP_LABELS = {
    "stub_code": "placeholder / not-really-done code",
    "oversold": "unverified confidence claim",
    "fabricated": "fabricated / invented content",
}

# Tokens that are legitimate in common testing/idiomatic contexts.
DEFAULT_ALLOWLIST = [
    "unittest.mock",
    "Mock(",
    "MagicMock(",
    "AsyncMock(",
    "PropertyMock(",
    "patch(",
    "monkeypatch",
    "mocker",
]

_IMPORT_LINE_RE = re.compile(
    r"^\s*(?:from\s+[\w.]+\s+import\b|import\s+\w)", re.IGNORECASE
)

# Default severity per signal group.
DEFAULT_SEVERITIES: dict[str, str] = {
    "stub_code": "warning",
    "oversold": "error",
    "fabricated": "error",
}

# ---------------------------------------------------------------------------
# Precompiled regex patterns (one per group, compiled once at import time).
# Each group uses alternation to match all tokens in a single pass.
# ---------------------------------------------------------------------------

_HALLUCINATION_PATTERNS: list[tuple[re.Pattern, str]] = []
for _group_name, _tokens in [
    ("stub_code", STUB_TOKENS),
    ("oversold", OVERSOLD_TOKENS),
    ("fabricated", FABRICATED_TOKENS),
]:
    _escaped = [re.escape(t).replace(r"\ ", r"\s+") for t in _tokens]
    _pattern = re.compile(rf"\b(?:{'|'.join(_escaped)})\b", re.IGNORECASE)
    _HALLUCINATION_PATTERNS.append((_pattern, _group_name))


def scan_hallucination_words(
    source: str,
    allowlist: list[str] | None = None,
    severities: dict[str, str] | None = None,
) -> dict:
    """Scan source for tokens in the grouped hallucination pool.

    To avoid flagging legitimate code, matches are skipped when:
      - the line is an import statement;
      - the match is part of a dotted path (``unittest.mock``, ``os.path``);
      - the matched text starts with an entry of the effective allowlist.

    Each hit carries a severity (``error`` | ``warning`` | ``info``) taken
    from ``severities`` (group -> severity), falling back to
    DEFAULT_SEVERITIES.

    Returns:
        {
          "hits": [{"word": "stub", "group": "stub_code", "line": 12,
                    "severity": "warning"}, ...],
          "clean": bool,
          "blocking": bool,
          "groups": {"stub_code": 2, "oversold": 1, "fabricated": 0},
          "severities": {"error": 1, "warning": 2, "info": 0}
        }
    """
    if allowlist is None:
        allowlist = DEFAULT_ALLOWLIST
    sev = dict(DEFAULT_SEVERITIES)
    if severities:
        for g, s in severities.items():
            if g in _GROUP_LABELS and s in _VALID_SEVERITIES:
                sev[g] = s
    hits: list[dict] = []
    group_counts: dict[str, int] = {g: 0 for g in _GROUP_LABELS}
    severity_counts: dict[str, int] = {"error": 0, "warning": 0, "info": 0}
    for i, line in enumerate(source.splitlines(), start=1):
        if _IMPORT_LINE_RE.match(line):
            continue
        for pattern, group in _HALLUCINATION_PATTERNS:
            for m in pattern.finditer(line):
                before = line[max(0, m.start() - 1):m.start()]
                after = line[m.end():m.end() + 1]
                if before == "." or after == ".":
                    continue  # part of a dotted path (module/attribute)
                rest = line[m.start():]
                if any(rest.lower().startswith(a.lower()) for a in allowlist):
                    continue
                word = m.group(0).lower()
                severity = sev.get(group, "warning")
                hits.append(
                    {"word": word, "group": group, "line": i, "severity": severity}
                )
                group_counts[group] += 1
                severity_counts[severity] += 1
    return {
        "hits": hits,
        "clean": len(hits) == 0,
        "blocking": severity_counts["error"] > 0,
        "groups": group_counts,
        "severities": severity_counts,
    }