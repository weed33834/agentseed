"""AgentSeed undefined symbol detection.

Static analysis to flag symbols the model may have hallucinated
(called/used but never defined or imported). Supports python (AST)
and typescript/javascript (lexical regex pass).
"""

from __future__ import annotations

import ast
import builtins
import re

# Optional: pyflakes for more accurate Python undefined-name detection (F821).
# When available, its AST analysis catches hallucinated symbols more reliably
# than the hand-rolled AST walk. When unavailable, the zero-dep fallback applies.
_HAS_PYFLAKES = False
try:
    from pyflakes.checker import Checker as _PyflakesChecker  # noqa: N811
    from pyflakes.messages import UndefinedName as _UndefinedName
    _HAS_PYFLAKES = True
except ImportError:  # pragma: no cover
    pass


# ---------------------------------------------------------------------------
# TypeScript lightweight static analysis (zero-dependency regex pass).
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


def _deduplicate(items: list[str]) -> list[str]:
    """Remove duplicates while preserving order."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


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
    # const/let/var declarations
    for m in re.finditer(
        r"\b(?:const|let|var)\s+([^;\n]+)", source
    ):
        for part in m.group(1).split(","):
            decl = re.match(r"\s*(" + _TS_IDENT + r")(?:\s*[:=]|\s*$)", part)
            if decl:
                defined.add(decl.group(1))

    def _add_params(body: str) -> None:
        for part in re.split(r",", body):
            p = part.strip()
            if not p:
                continue
            p = re.sub(r":.*$", "", p)
            p = re.sub(r"^\.\.\.", "", p)
            p = re.sub(r"^\{|\}$", "", p)
            p = re.sub(r"^\[|\]$", "", p)
            if re.fullmatch(_TS_IDENT, p):
                defined.add(p)

    for m in re.finditer(r"\bfunction\s+(?:" + _TS_IDENT + r"\s*)?\(([^)]*)\)", source):
        _add_params(m.group(1))
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
    for m in re.finditer(r"\bnew\s+(" + _TS_IDENT + r")\s*\(", source):
        name = m.group(1)
        if name not in defined and name not in TS_KEYWORDS:
            suspects.append(name)
    for m in re.finditer(r"(?<![\w$.])(" + _TS_IDENT + r")\s*\(", source):
        name = m.group(1)
        if name not in defined and name not in TS_KEYWORDS:
            suspects.append(name)
    note = (
        "Lexical regex pass, not a type checker; may miss destructured "
        "imports or produce false positives on dynamic/global references."
    )
    return _deduplicate(suspects), note


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

    defined: set[str] = set(dir(builtins))
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

    return {
        "language": "python",
        "suspects": _deduplicate(suspects),
        "note": "Static scope analysis only; no runtime; attribute calls "
        "(foo.bar) are not expanded and may cause false negatives.",
    }