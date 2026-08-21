"""AgentSeed JSON Schema validator.

Primary path: the industry-standard ``jsonschema`` library (Draft 2020-12
and friends) — full keyword coverage. Fallback path: a zero-dependency
subset validator so the plugin still runs in bare environments (the
``verify-before-code`` skill only relies on subset keywords).
"""

from __future__ import annotations

import re

try:
    from jsonschema import Draft202012Validator as _Validator
    from jsonschema.exceptions import ValidationError as _ValidationError
    from jsonschema.validators import validator_for as _validator_for

    _HAS_JSONSCHEMA = True
except ImportError:  # pragma: no cover - exercised via the bare CI job
    _HAS_JSONSCHEMA = False


def schema_validate(instance, schema: dict) -> dict:
    """Validate an instance against a JSON Schema.

    Uses ``jsonschema`` when installed (all Draft 2020-12 keywords, boolean
    schemas); otherwise falls back to the built-in subset validator
    (type incl. type arrays / enum / const / minLength / maxLength /
    pattern / minItems / maxItems / items / properties / required /
    additionalProperties).

    Returns:
        {"valid": bool, "errors": [human-readable messages],
         "validator": "jsonschema" | "builtin-subset"}
    """
    if not isinstance(schema, dict):
        return {"valid": False, "errors": ["schema must be a JSON object"],
                "validator": "builtin-subset" if not _HAS_JSONSCHEMA else "jsonschema"}

    if _HAS_JSONSCHEMA:
        try:
            cls = _validator_for(schema, default=_Validator)
            validator = cls(schema)
            errors = sorted(validator.iter_errors(instance), key=lambda e: e.path)
            return {
                "valid": not errors,
                "errors": [e.message for e in errors],
                "validator": "jsonschema",
            }
        except _ValidationError as exc:
            return {"valid": False, "errors": [exc.message], "validator": "jsonschema"}
        except Exception as exc:  # noqa: BLE001
            return {"valid": False, "errors": [f"validation crashed: {exc}"],
                    "validator": "jsonschema"}

    errors: list[str] = []
    try:
        _validate_subset(instance, schema, "$", errors)
    except Exception as exc:  # noqa: BLE001
        return {"valid": False, "errors": [f"validation crashed: {exc}"],
                "validator": "builtin-subset"}
    return {"valid": len(errors) == 0, "errors": errors, "validator": "builtin-subset"}


# ---------------------------------------------------------------------------
# Zero-dependency fallback (subset)
# ---------------------------------------------------------------------------

def _json_equal(a, b) -> bool:
    """JSON-Schema equality: booleans never equal numbers (True != 1)."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a is b
    return a == b


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


def _validate_subset(instance, schema: dict, path: str, errors: list[str]) -> None:
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
                _validate_subset(item, schema["items"], f"{path}[{idx}]", errors)
    if isinstance(instance, dict):
        if "properties" in schema:
            for prop, subschema in schema["properties"].items():
                if prop in instance:
                    _validate_subset(instance[prop], subschema, f"{path}.{prop}", errors)
        for req in schema.get("required", []):
            if req not in instance:
                errors.append(f"{path}: missing required property '{req}'")
        if schema.get("additionalProperties") is False and "properties" in schema:
            for key in instance:
                if key not in schema["properties"]:
                    errors.append(f"{path}: unexpected property '{key}'")
