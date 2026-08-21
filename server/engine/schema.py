"""AgentSeed JSON Schema validator — delegates to the ``jsonschema`` library.

Replaces the former hand-rolled subset validator with the industry-standard
``jsonschema`` library (Draft 2020-12). The public API is unchanged.
"""

from __future__ import annotations

from jsonschema import Draft202012Validator as _Validator
from jsonschema.exceptions import ValidationError as _ValidationError
from jsonschema.validators import validator_for as _validator_for


def schema_validate(instance, schema: dict) -> dict:
    """Validate an instance against a JSON Schema (Draft 2020-12).

    Supports all standard keywords: type, enum, const, minLength, maxLength,
    pattern, minItems, maxItems, items, properties, required,
    additionalProperties, plus any other Draft 2020-12 keyword.

    Boolean schemas (``True`` / ``False``) are supported natively.

    Returns:
        {"valid": bool, "errors": [human-readable messages]}
    """
    if not isinstance(schema, dict):
        return {"valid": False, "errors": ["schema must be a JSON object"]}

    try:
        # Auto-detect the best meta-schema for the given schema.
        # Falls back to Draft202012Validator if no $schema is present.
        cls = _validator_for(schema, default=_Validator)
        validator = cls(schema)
        errors = sorted(validator.iter_errors(instance), key=lambda e: e.path)
        if errors:
            return {"valid": False, "errors": [e.message for e in errors]}
        return {"valid": True, "errors": []}
    except _ValidationError as exc:
        return {"valid": False, "errors": [exc.message]}
    except Exception as exc:  # noqa: BLE001
        return {"valid": False, "errors": [f"validation crashed: {exc}"]}