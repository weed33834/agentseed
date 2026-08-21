"""AgentSeed guard engine.

Pure standard-library implementation -> zero third-party dependencies.
Imported directly by the MCP server.

Capabilities (research-informed, expanded):
1. detect_undefined_symbols -- static AST analysis that flags symbols the
   model may have hallucinated (called/used but never defined or imported).
   Technique source: "Exploring and Evaluating Hallucinations in LLM-Powered
   Code Generation" (arXiv:2404.00971) -- Knowledge-Conflicting hallucinations
   (nonexistent APIs / undefined identifiers) are 15.1% of code hallucinations;
   <10% of hallucinated code still passes all tests, so static detection adds a
   hard floor on top of test suites.
2. scan_hallucination_words -- flags tokens across three signal groups:
   - stub_code:  stub/mock/fake/placeholder/dummy/todo/fixme/xxx/tbd/tba/
                 "not implemented"/"coming soon"
   - oversold:   guaranteed/"definitely works"/"all tests pass"/
                 "everything works"/"fully tested"/"production ready"/
                 "no bugs"/"works perfectly"/"should work"/"trust me"
   - fabricated: simulated/hypothetical/imaginary/invented/fabricated/fictional
   Technique sources: SFD Lab 5-step anti-hallucination checklist (step 5);
   CDV "Conservative Dual-Verify" ("'Done, all tests pass' is a claim, not
   evidence"); reze83 anti-hallucination skill (verify-before-claim rules).
3. check_plugin_conformance -- Agent Plugins 1.0.0 conformance linter.
   Technique source: the spec defines MUST/SHOULD but ships no official linter;
   AgentSeed is the first to provide one.
4. sandbox_run -- deterministic execution channel (CDV Channel A / Anthropic
   "verify with execution" / AWS Automated Reasoning spirit): runs a command in
   a subprocess with timeout and captured output, so "tests pass" becomes an
   observed fact instead of a claim.
5. schema_validate -- zero-dependency JSON Schema subset validator for
   structured outputs (Guardrails AI Hub validator pattern / Anthropic
   schema-constrained outputs / "validate before trust").
"""

from __future__ import annotations

import ast
import builtins
import json
import os
import re

# ---------------------------------------------------------------------------
# Hallucination token pool (grouped by signal type).
# Research-informed: expanded beyond the original 6 words; each group maps to
# a documented failure mode (stub/fabricated -> not really done,
# oversold -> unverified confidence claims).
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

# Full pool: token -> group.
HALLUCINATION_WORDS: dict[str, str] = {}
for _t in STUB_TOKENS:
    HALLUCINATION_WORDS[_t] = "stub_code"
for _t in OVERSOLD_TOKENS:
    HALLUCINATION_WORDS[_t] = "oversold"
for _t in FABRICATED_TOKENS:
    HALLUCINATION_WORDS[_t] = "fabricated"

_GROUP_LABELS = {
    "stub_code": "placeholder / not-really-done code",
    "oversold": "unverified confidence claim",
    "fabricated": "fabricated / invented content",
}

# ---------------------------------------------------------------------------
# Agent Plugins 1.0.0 conformance constants
# (normative rules from spec/1.0.0.md §5, §6, §7)
# ---------------------------------------------------------------------------

PLUGIN_TOP_LEVEL_FIELDS = {
    "$schema", "name", "version", "description",
    "author", "homepage", "repository", "license", "keywords", "extensions",
}
AUTHOR_FIELDS = {"name", "email", "url"}
MCP_TOP_LEVEL_FIELDS = {"$schema", "mcpServers"}
_PLUGIN_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9.\-]*[a-z0-9])?$")
_SKILL_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?$")


# Tokens that are legitimate in common testing/idiomatic contexts and are
# excluded from matching by default (can be re-enabled via `allowlist`).
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


def _token_re(token: str) -> re.Pattern:
    """Build a word-boundary regex for a token (supports multi-word phrases)."""
    escaped = re.escape(token).replace(r"\ ", r"\s+")
    return re.compile(rf"\b{escaped}\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# TypeScript lightweight static analysis (zero-dependency regex pass).
# Not a full type checker: catches "called but never defined/imported" at the
# lexical level (Knowledge-Conflicting hallucinations). False positives on
# dynamic/global references are possible; documented as such.
# ---------------------------------------------------------------------------

TS_GLOBALS = {
    "console", "Math", "JSON", "Object", "Array", "String", "Number", "Boolean",
    "Date", "Promise", "RegExp", "Error", "Set", "Map", "Symbol", "BigInt",
    "process", "global", "window", "document", "module", "exports", "require",
    "fetch", "setTimeout", "setInterval", "clearTimeout", "clearInterval",
    "parseInt", "parseFloat", "isNaN", "isFinite", "encodeURIComponent",
    "decodeURIComponent", "undefined", "NaN", "Infinity",
}

TS_KEYWORDS = {
    "if", "for", "while", "switch", "catch", "return", "typeof", "instanceof",
    "function", "class", "interface", "import", "export", "const", "let", "var",
    "new", "delete", "in", "of", "await", "yield", "throw", "try", "do", "case",
    "default", "else", "this", "super", "void", "break", "continue", "as",
    "from", "type", "extends", "implements", "public", "private", "protected",
    "readonly", "static", "async", "keyof", "never", "unknown", "any",
}

_TS_IDENT = r"[A-Za-z_$][A-Za-z0-9_$]*"


def _ts_defined_symbols(source: str) -> set[str]:
    """Collect identifiers defined or imported in a TS/JS source (lexical pass)."""
    defined: set[str] = set(TS_GLOBALS)
    # import { a, b as c } from '...'
    for m in re.finditer(r"\bimport\s*\{([^}]*)\}\s*from", source):
        for part in m.group(1).split(","):
            p = part.strip()
            if not p:
                continue
            alias = re.search(r"\bas\s+(" + _TS_IDENT + r")\s*$", p)
            defined.add(alias.group(1) if alias else p.split(":")[-1].strip())
    # import a / import * as a / import a = require()
    for m in re.finditer(r"\bimport\s+(?:\*\s+as\s+)?(" + _TS_IDENT + r")\s*(?:from|=)", source):
        defined.add(m.group(1))
    # const { a, b: c } = require(...) / import(...) / destructuring
    for m in re.finditer(r"\b(?:const|let|var)\s*\{([^}]*)\}\s*=\s*(?:require|import)\s*\(", source):
        for part in m.group(1).split(","):
            p = part.strip()
            if not p:
                continue
            alias = re.search(r":\s*(" + _TS_IDENT + r")\s*$", p)
            defined.add(alias.group(1) if alias else p.split(":")[0].strip())
    # function/class/interface/type declarations
    for m in re.finditer(
        r"\b(?:async\s+)?(?:function|class|interface|type|enum)\s+(" + _TS_IDENT + r")",
        source,
    ):
        defined.add(m.group(1))
    # const/let/var declarations — capture the full declarator list so
    # multi-declarations (`const a = 1, b = 2`) register every name.
    for m in re.finditer(
        r"\b(?:const|let|var)\s+([^;\n]+)", source
    ):
        for part in m.group(1).split(","):
            decl = re.match(r"\s*(" + _TS_IDENT + r")(?:\s*[:=]|\s*$)", part)
            if decl:
                defined.add(decl.group(1))
    # function parameters — ONLY from real declarations / arrow functions,
    # never from call sites (a call's arguments are not definitions)
    def _add_params(body: str) -> None:
        for part in re.split(r",", body):
            p = part.strip()
            if not p:
                continue
            p = re.sub(r":.*$", "", p)          # strip type annotations
            p = re.sub(r"^\.\.\.", "", p)        # rest params
            p = re.sub(r"^\{|\}$", "", p)        # destructured
            p = re.sub(r"^\[|\]$", "", p)
            if re.fullmatch(_TS_IDENT, p):
                defined.add(p)

    # function declarations: `function foo(a, b) {` / `function (a, b) {`
    for m in re.finditer(r"\bfunction\s+(?:" + _TS_IDENT + r"\s*)?\(([^)]*)\)", source):
        _add_params(m.group(1))
    # arrow functions: `const foo = (a, b) =>` and `const foo = a =>`
    for m in re.finditer(
        r"\b(?:const|let|var)\s+" + _TS_IDENT + r"\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>",
        source,
    ):
        _add_params(m.group(1))
    for m in re.finditer(
        r"\b(?:const|let|var)\s+" + _TS_IDENT + r"\s*=\s*(?:async\s*)?(" + _TS_IDENT + r")\s*=>",
        source,
    ):
        _add_params(m.group(1))
    return defined


def _detect_ts_undefined(source: str) -> tuple[list[str], str]:
    """Lexical pass: calls/new-expressions whose callee is never defined."""
    defined = _ts_defined_symbols(source)
    suspects: list[str] = []
    # `new Foo(...)` — not a member access
    for m in re.finditer(r"\bnew\s+(" + _TS_IDENT + r")\s*\(", source):
        name = m.group(1)
        if name not in defined and name not in TS_KEYWORDS:
            suspects.append(name)
    # top-level calls `foo(` — but not member access `obj.foo(`
    for m in re.finditer(r"(?<![\w$.])(" + _TS_IDENT + r")\s*\(", source):
        name = m.group(1)
        if name not in defined and name not in TS_KEYWORDS:
            suspects.append(name)
    seen: set[str] = set()
    out: list[str] = []
    for s in suspects:
        if s not in seen:
            seen.add(s)
            out.append(s)
    note = (
        "Lexical regex pass, not a type checker; may miss destructured "
        "imports or produce false positives on dynamic/global references."
    )
    return out, note


def detect_undefined_symbols(source: str, language: str = "python") -> dict:
    """Parse source and return symbols that look hallucinated
    (used/called but never defined or imported).

    Supports: python (AST), typescript/javascript (lexical regex pass).
    Returns:
        {"language": ..., "suspects": ["foo", "Bar"], "note": "..."}
    """
    if language in ("typescript", "ts", "javascript", "js"):
        suspects, note = _detect_ts_undefined(source)
        return {"language": language, "suspects": suspects, "note": note}
    if language != "python":
        return {
            "language": language,
            "suspects": [],
            "note": "Supports python (AST) and typescript/javascript (lexical); "
            "other languages are not implemented yet.",
        }

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {
            "language": "python",
            "suspects": [],
            "note": f"Cannot parse (syntax error): {exc}",
        }

    defined: set[str] = set(dir(builtins))  # builtins
    # module-level dunders are legal globals (not hallucinated symbols)
    defined |= {
        "__file__", "__doc__", "__package__", "__spec__", "__loader__",
        "__main__", "__dict__", "__builtins__", "__cached__",
    }
    imported: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.add(alias.asname or alias.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.arg):
            defined.add(node.arg)
        elif isinstance(node, ast.Global) or isinstance(node, ast.Nonlocal):
            defined.update(node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            defined.add(node.name)

    # Any Name in Store context is a binding: plain assignments
    # (x = ...), annotated/augmented assignment, for/with/except targets,
    # walrus expressions, and comprehension variables. Collecting every
    # Store-context name avoids false positives on ordinary local state.
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            defined.add(node.id)

    defined |= imported

    suspects: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id not in defined:
                suspects.append(node.func.id)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id not in defined:
                suspects.append(node.id)

    seen: set[str] = set()
    out: list[str] = []
    for s in suspects:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return {
        "language": "python",
        "suspects": out,
        "note": "Static scope analysis only; no runtime; attribute calls "
        "(foo.bar) are not expanded and may cause false negatives.",
    }


# Default severity per signal group. Tunable via config (see load_config):
#   error   -> blocks completion
#   warning -> reported, does not block
#   info    -> informational only
# stub_code defaults to warning: TODO/WIP markers are common in legitimate
# work-in-progress sections; oversold/fabricated claims are always suspect.
DEFAULT_SEVERITIES: dict[str, str] = {
    "stub_code": "warning",
    "oversold": "error",
    "fabricated": "error",
}
_VALID_SEVERITIES = {"error", "warning", "info"}

CONFIG_FILENAME = "agentseed.config.json"


def load_config(explicit_path: str | None = None) -> dict:
    """Load the effective AgentSeed config (zero dependencies).

    Search order (first hit wins):
      1. ``explicit_path`` argument
      2. ``AGENTSEED_CONFIG`` environment variable
      3. ``${PLUGIN_DATA}/agentseed.config.json`` — the Agent Plugins spec
         (v1.0.0 §9.1) guarantees clients set PLUGIN_DATA to a persistent,
         writable per-plugin directory, making it the natural place for
         user overrides that survive plugin updates.
      4. ``./agentseed.config.json`` in the current working directory.

    Recognized keys (all optional):
      allowlist   : list[str] - scan exclusions (replaces DEFAULT_ALLOWLIST)
      severities  : dict[str, str] - group -> error|warning|info
      timeout     : int - default sandbox_run timeout in seconds

    Returns {} when no config file exists or it cannot be parsed.
    """
    candidates: list[str] = []
    if explicit_path:
        candidates.append(explicit_path)
    env_path = os.environ.get("AGENTSEED_CONFIG")
    if env_path:
        candidates.append(env_path)
    plugin_data = os.environ.get("PLUGIN_DATA")
    if plugin_data:
        candidates.append(os.path.join(plugin_data, CONFIG_FILENAME))
    candidates.append(CONFIG_FILENAME)

    for path in candidates:
        if path and os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    return data
            except (OSError, ValueError):
                continue
    return {}


def _config_str_list(config: dict, key: str) -> list[str] | None:
    value = config.get(key)
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return value
    return None


def _config_severities(config: dict) -> dict[str, str] | None:
    value = config.get("severities")
    if isinstance(value, dict) and all(
        isinstance(k, str) and isinstance(v, str) and v in _VALID_SEVERITIES
        for k, v in value.items()
    ):
        return value
    return None


def scan_hallucination_words(
    source: str,
    allowlist: list[str] | None = None,
    severities: dict[str, str] | None = None,
) -> dict:
    """Scan source for tokens in the grouped hallucination pool.

    To avoid flagging legitimate code, matches are skipped when:
      - the line is an import statement (``from unittest.mock import Mock``
        is standard test practice, not a stub marker);
      - the match is part of a dotted path (``unittest.mock``, ``os.path``);
      - the matched text starts with an entry of the effective allowlist
        (defaults to DEFAULT_ALLOWLIST; pass a custom list to override,
        or an empty list to disable all exclusions).

    Each hit carries a severity (``error`` | ``warning`` | ``info``) taken
    from ``severities`` (group -> severity), falling back to
    DEFAULT_SEVERITIES. ``blocking`` reports whether any error-severity hit
    exists; warnings/info never block completion on their own.

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
        for token, group in HALLUCINATION_WORDS.items():
            for m in _token_re(token).finditer(line):
                before = line[max(0, m.start() - 1):m.start()]
                after = line[m.end():m.end() + 1]
                if before == "." or after == ".":
                    continue  # part of a dotted path (module/attribute)
                rest = line[m.start():]
                if any(rest.lower().startswith(a.lower()) for a in allowlist):
                    continue
                severity = sev.get(group, "warning")
                hits.append(
                    {"word": token, "group": group, "line": i, "severity": severity}
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


def _check_plugin_name(name: str) -> list[str]:
    """Validate plugin.json `name` against §5.5 naming constraints."""
    errs: list[str] = []
    if not isinstance(name, str):
        return ["plugin.json 'name' must be a string"]
    if not (1 <= len(name) <= 64):
        errs.append(f"plugin.json 'name' length {len(name)} not in 1..64")
    if not _PLUGIN_NAME_RE.match(name):
        errs.append(
            "plugin.json 'name' must be lowercase alphanumeric with - and . "
            "only, start and end alphanumeric, no '--' or '..'"
        )
    if "--" in name:
        errs.append("plugin.json 'name' must not contain consecutive hyphens '--'")
    if ".." in name:
        errs.append("plugin.json 'name' must not contain consecutive dots '..'")
    return errs


def _parse_frontmatter(skill_md_path: str) -> dict:
    """Extract name/description/license from a SKILL.md frontmatter block.

    Zero-dependency YAML-lite parser: handles `key: value` and folded
    scalars (`description: >-` followed by indented lines).
    """
    out: dict = {}
    try:
        with open(skill_md_path, encoding="utf-8") as fh:
            content = fh.read()
    except OSError:
        return out
    if not content.startswith("---"):
        return out
    end_m = re.search(r"^---\s*$", content[3:], re.MULTILINE)
    if end_m is None:
        return out
    block = content[3:3 + end_m.start()]
    lines = block.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^([A-Za-z0-9\-]+):\s*(.*)$", line)
        if not m:
            i += 1
            continue
        key, value = m.group(1), m.group(2).strip()
        if value in (">", ">-", "|", "|-"):
            folded: list[str] = []
            i += 1
            while i < len(lines) and (lines[i].startswith(" ") or lines[i] == ""):
                if lines[i].strip():
                    folded.append(lines[i].strip())
                i += 1
            out[key] = " ".join(folded)
            continue
        out[key] = value
        i += 1
    return out


def _check_skill_dir(skill_root: str, entry: str) -> list[str]:
    """Validate one skills/<entry>/ against Agent Skills spec (via §7.1)."""
    errs: list[str] = []
    skill_md = os.path.join(skill_root, entry, "SKILL.md")
    if not os.path.isfile(skill_md):
        return errs  # no SKILL.md -> not a skill, silently skipped
    fm = _parse_frontmatter(skill_md)
    name = fm.get("name", "")
    if not name:
        errs.append(f"skills/{entry}/SKILL.md missing required frontmatter 'name'")
    elif name != entry:
        errs.append(
            f"skills/{entry}/SKILL.md frontmatter 'name' ({name}) must match "
            f"directory name ({entry})"
        )
    elif not _SKILL_NAME_RE.match(name):
        errs.append(
            f"skills/{entry}/SKILL.md 'name' must be lowercase alphanumeric "
            "with hyphens only, not starting/ending with a hyphen"
        )
    desc = fm.get("description", "")
    if not desc:
        errs.append(f"skills/{entry}/SKILL.md missing required frontmatter 'description'")
    elif len(desc) > 1024:
        errs.append(f"skills/{entry}/SKILL.md 'description' exceeds 1024 chars")
    return errs


def _is_loopback_ipv4(host: str) -> bool:
    """True if host is an IPv4 literal in the loopback range 127.0.0.0/8."""
    parts = host.split(".")
    if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
        return parts[0] == "127"
    return False


def check_plugin_conformance(plugin_dir: str) -> dict:
    """Validate a directory against Agent Plugins 1.0.0 (§5/§6/§7).

    Strict linter: closed-schema top-level fields, `name` constraints,
    SKILL.md frontmatter (via the Agent Skills spec), mcp.json fields and
    cwd form.

    Returns:
        {"ok": bool, "errors": [...], "warnings": [...]}
    """
    errors: list[str] = []
    warnings: list[str] = []

    # ---- §5 manifest ------------------------------------------------------
    pj = os.path.join(plugin_dir, "plugin.json")
    if not os.path.isfile(pj):
        errors.append("Missing root plugin.json (spec requires checking root plugin.json)")
    else:
        try:
            with open(pj, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"plugin.json is not valid JSON: {exc}")
            data = {}
        if not isinstance(data, dict):
            errors.append("plugin.json top level must be a JSON object")
            data = {}

        for key in data:
            if key not in PLUGIN_TOP_LEVEL_FIELDS:
                errors.append(
                    f"plugin.json has unknown top-level field '{key}' "
                    f"(closed schema: only {sorted(PLUGIN_TOP_LEVEL_FIELDS)})"
                )
        if data.get("$schema") != "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json":
            errors.append("plugin.json $schema missing or not the 1.0.0 address")
        if "name" not in data:
            errors.append("plugin.json missing required field 'name'")
        else:
            errors.extend(_check_plugin_name(data["name"]))
        for field, ftype in (("version", str), ("description", str),
                             ("homepage", str), ("repository", str), ("license", str)):
            if field in data and not isinstance(data[field], ftype):
                errors.append(f"plugin.json '{field}' must be a string")
        if "keywords" in data and (
            not isinstance(data["keywords"], list)
            or any(not isinstance(k, str) for k in data["keywords"])
        ):
            errors.append("plugin.json 'keywords' must be an array of strings")
        if "author" in data:
            author = data["author"]
            if not isinstance(author, dict):
                errors.append("plugin.json 'author' must be an object")
            else:
                for key in author:
                    if key not in AUTHOR_FIELDS:
                        errors.append(
                            f"plugin.json 'author' has unknown field '{key}' "
                            f"(only {sorted(AUTHOR_FIELDS)} allowed)"
                        )
                for key, value in author.items():
                    if not isinstance(value, str):
                        errors.append(f"plugin.json 'author.{key}' must be a string")

    # ---- §6 skills ---------------------------------------------------------
    skills_dir = os.path.join(plugin_dir, "skills")
    if os.path.isdir(skills_dir):
        found_skill = False
        for entry in sorted(os.listdir(skills_dir)):
            if os.path.isdir(os.path.join(skills_dir, entry)):
                found_skill = True
                errors.extend(_check_skill_dir(skills_dir, entry))
        if not found_skill:
            warnings.append(
                "No skills/ directory (pure-MCP plugin is conformant, but this "
                "plugin is designed hybrid)"
            )
    else:
        warnings.append(
            "No skills/ directory (pure-MCP plugin is conformant, but this "
            "plugin is designed hybrid)"
        )

    # ---- §7 mcp.json -------------------------------------------------------
    mcp = os.path.join(plugin_dir, "mcp.json")
    if os.path.isfile(mcp):
        try:
            with open(mcp, encoding="utf-8") as fh:
                m = json.load(fh)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"mcp.json is not valid JSON: {exc}")
            m = {}
        if not isinstance(m, dict):
            errors.append("mcp.json top level must be a JSON object")
            m = {}
        for key in m:
            if key not in MCP_TOP_LEVEL_FIELDS:
                errors.append(
                    f"mcp.json has unknown top-level field '{key}' "
                    f"(only {sorted(MCP_TOP_LEVEL_FIELDS)} allowed)"
                )
        if m.get("$schema") != "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json":
            errors.append("mcp.json $schema missing or not the 1.0.0 address")
        servers = m.get("mcpServers", {})
        if not isinstance(servers, dict):
            errors.append("mcp.json 'mcpServers' must be an object")
            servers = {}
        for sname, cfg in servers.items():
            if not isinstance(cfg, dict):
                errors.append(f"mcp.json server '{sname}' must be an object")
                continue
            stype = cfg.get("type")
            if stype not in ("stdio", "streamable-http", "sse"):
                errors.append(
                    f"mcp.json server '{sname}' missing/unknown 'type' "
                    "(must be stdio | streamable-http | sse)"
                )
                continue
            # §7.2.1: closed variants — a field belonging to another variant,
            # or any unknown field, makes the entry invalid.
            allowed_fields = {"stdio": {"type", "command", "args", "env", "cwd"},
                              "streamable-http": {"type", "url", "headers"},
                              "sse": {"type", "url", "headers"}}[stype]
            for key in cfg:
                if key not in allowed_fields:
                    errors.append(
                        f"mcp.json server '{sname}' has unknown field '{key}' "
                        f"for type '{stype}' (closed variant: only "
                        f"{sorted(allowed_fields)})"
                    )
            if stype == "stdio":
                command = cfg.get("command")
                if not command:
                    errors.append(f"mcp.json server '{sname}' (stdio) missing required 'command'")
                elif not isinstance(command, str):
                    errors.append(f"mcp.json server '{sname}' 'command' must be a string")
                elif not ("./" in command.split("/")[0:1] or re.fullmatch(r"[A-Za-z0-9._\-]+", command)):
                    # bare executable token, or plugin-relative './...' path (§7.2.1)
                    errors.append(
                        f"mcp.json server '{sname}' 'command' must be a single "
                        "executable token or a plugin-relative './...' path"
                    )
                args = cfg.get("args")
                if args is not None and (
                    not isinstance(args, list)
                    or any(not isinstance(a, str) for a in args)
                ):
                    errors.append(f"mcp.json server '{sname}' 'args' must be an array of strings")
                env = cfg.get("env")
                if env is not None:
                    if not isinstance(env, dict) or any(
                        not isinstance(v, str) for v in env.values()
                    ):
                        errors.append(
                            f"mcp.json server '{sname}' 'env' must be an object of strings"
                        )
                    else:
                        # §9.1: clients supply these; configuring them is invalid
                        for reserved in ("PLUGIN_ROOT", "PLUGIN_DATA"):
                            if reserved in env:
                                errors.append(
                                    f"mcp.json server '{sname}' 'env' must not define "
                                    f"reserved variable '{reserved}'"
                                )
                cwd = cfg.get("cwd")
                if cwd is not None and not (
                    cwd == "${PLUGIN_ROOT}"
                    or cwd.startswith("${PLUGIN_ROOT}/")
                    or cwd == "${PLUGIN_DATA}"
                    or cwd.startswith("${PLUGIN_DATA}/")
                    or cwd.startswith("./")
                ):
                    errors.append(
                        f"mcp.json server '{sname}' 'cwd' must be './relative', "
                        "${PLUGIN_ROOT}[-rooted] or ${PLUGIN_DATA}[-rooted]"
                    )
            else:
                url = cfg.get("url")
                if not url:
                    errors.append(f"mcp.json server '{sname}' missing required 'url'")
                elif isinstance(url, str):
                    # §7.2.1: absolute HTTP(S) URL, no userinfo, no fragment;
                    # HTTPS required except for loopback hosts.
                    parsed = re.match(r"^https?://([^/?#]*)(.*)$", url)
                    if "#" in url:
                        errors.append(
                            f"mcp.json server '{sname}' 'url' must not contain a fragment"
                        )
                    if "@" in parsed.group(1):
                        errors.append(
                            f"mcp.json server '{sname}' 'url' must not contain user information"
                        )
                    host = (parsed.group(1).split("@")[-1] or "").rsplit(":", 1)[0].strip("[]")
                    if (
                        url.startswith("http://")
                        and host.lower() not in ("localhost", "::1")
                        and not _is_loopback_ipv4(host)
                    ):
                        errors.append(
                            f"mcp.json server '{sname}' non-loopback 'url' must use HTTPS"
                        )
                headers = cfg.get("headers")
                if headers is not None and (
                    not isinstance(headers, dict)
                    or any(not isinstance(v, str) for v in headers.values())
                    or len({k.lower() for k in headers}) != len(headers)
                ):
                    errors.append(
                        f"mcp.json server '{sname}' 'headers' must be an object of "
                        "strings without duplicate (case-insensitive) names"
                    )
    else:
        warnings.append("No mcp.json (pure-skill plugin is conformant)")

    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}


def sandbox_run(command: list[str], timeout: int = 30, cwd: str | None = None) -> dict:
    """Run a command as a subprocess (no shell) with a timeout.

    Deterministic verification channel: turns "the test passes" into an
    observed fact (exit code + output). No shell means no injection via args;
    output is truncated to keep the tool response bounded.

    Returns:
        {"exit_code": int, "stdout": str, "stderr": str, "timed_out": bool}
    """
    import subprocess  # local import keeps module import light

    if not isinstance(command, list) or not command:
        return {"exit_code": -3, "stdout": "", "stderr": "command must be a non-empty list", "timed_out": False}
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=max(1, min(int(timeout), 120)),
            cwd=cwd,
            check=False,
        )
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-8000:],
            "stderr": proc.stderr[-4000:],
            "timed_out": False,
        }
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "stdout": "", "stderr": f"timed out after {timeout}s", "timed_out": True}
    except FileNotFoundError as exc:
        return {"exit_code": -2, "stdout": "", "stderr": f"command not found: {exc}", "timed_out": False}
    except Exception as exc:  # noqa: BLE001
        return {"exit_code": -9, "stdout": "", "stderr": f"run failed: {exc}", "timed_out": False}


def _schema_type_ok(value, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def _json_equal(a, b) -> bool:
    """JSON-Schema equality: booleans never equal numbers (True != 1)."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a is b
    return a == b


def _validate(instance, schema: dict, path: str, errors: list[str]) -> None:
    """Validate one value against one JSON Schema node (subset)."""
    type_spec = schema.get("type")
    if type_spec is not None:
        if isinstance(type_spec, list):
            if not any(_schema_type_ok(instance, t) for t in type_spec):
                errors.append(
                    f"{path}: expected type in {type_spec}, got {type(instance).__name__}"
                )
                return
        elif not _schema_type_ok(instance, type_spec):
            errors.append(f"{path}: expected type {type_spec}, got {type(instance).__name__}")
            return
    if "enum" in schema and not any(_json_equal(instance, v) for v in schema["enum"]):
        errors.append(f"{path}: value not in enum {schema['enum']}")
    if "const" in schema and not _json_equal(instance, schema["const"]):
        errors.append(f"{path}: expected const {schema['const']!r}")
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: shorter than minLength {schema['minLength']}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{path}: longer than maxLength {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path}: does not match pattern {schema['pattern']}")
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: fewer than minItems {schema['minItems']}")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{path}: more than maxItems {schema['maxItems']}")
        if "items" in schema:
            for idx, item in enumerate(instance):
                _validate(item, schema["items"], f"{path}[{idx}]", errors)
    if isinstance(instance, dict):
        if "properties" in schema:
            for prop, subschema in schema["properties"].items():
                if prop in instance:
                    _validate(instance[prop], subschema, f"{path}.{prop}", errors)
        # `required` is independent of `properties` in JSON Schema
        for req in schema.get("required", []):
            if req not in instance:
                errors.append(f"{path}: missing required property '{req}'")
        if schema.get("additionalProperties") is False and "properties" in schema:
            for key in instance:
                if key not in schema["properties"]:
                    errors.append(f"{path}: unexpected property '{key}'")


def schema_validate(instance, schema: dict) -> dict:
    """Validate an instance against a JSON Schema subset (type incl. type
    arrays/enum/const/minLength/maxLength/pattern/minItems/maxItems/items/
    properties/required/additionalProperties). Zero dependencies.

    Returns:
        {"valid": bool, "errors": [path messages]}
    """
    errors: list[str] = []
    if not isinstance(schema, dict):
        return {"valid": False, "errors": ["schema must be a JSON object"]}
    try:
        _validate(instance, schema, "$", errors)
    except Exception as exc:  # noqa: BLE001
        return {"valid": False, "errors": [f"validation crashed: {exc}"]}
    return {"valid": len(errors) == 0, "errors": errors}


if __name__ == "__main__":
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print("== Plugin conformance self-check ==")
    print(json.dumps(check_plugin_conformance(here), ensure_ascii=False, indent=2))

    print("\n== Hallucination word scan (demo: stub code) ==")
    demo = "def run():\n    return stub_result  # TODO: replace with real call\n"
    print(json.dumps(scan_hallucination_words(demo), ensure_ascii=False, indent=2))

    print("\n== Hallucination word scan (demo: oversold claim) ==")
    demo2 = "The feature is production ready, all tests pass, no bugs. Trust me."
    print(json.dumps(scan_hallucination_words(demo2), ensure_ascii=False, indent=2))

    print("\n== Undefined symbol detection (demo) ==")
    demo3 = "def f():\n    return magic_unknown()\n"
    print(json.dumps(detect_undefined_symbols(demo3), ensure_ascii=False, indent=2))
