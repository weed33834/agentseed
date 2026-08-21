"""AgentSeed guard engine — modular package.

Modules:
  config    — Config loading (load_config, config helpers)
  symbols   — Undefined symbol detection (detect_undefined_symbols)
  hallucination — Hallucination word scanning (scan_hallucination_words)
  plugin    — Agent Plugins 1.0.0 conformance checker (check_plugin_conformance)
  sandbox   — Deterministic execution channel (sandbox_run)
  schema    — JSON Schema subset validator (schema_validate)
"""

from .config import CONFIG_FILENAME, _config_severities, _config_str_list, _parse_timeout, load_config
from .hallucination import (
    DEFAULT_ALLOWLIST,
    HALLUCINATION_WORDS,
    _GROUP_LABELS,
    scan_hallucination_words,
)
from .plugin import check_plugin_conformance
from .sandbox import sandbox_run
from .schema import schema_validate
from .symbols import detect_undefined_symbols

__all__ = [
    "CONFIG_FILENAME",
    "DEFAULT_ALLOWLIST",
    "HALLUCINATION_WORDS",
    "_GROUP_LABELS",
    "_config_severities",
    "_config_str_list",
    "_parse_timeout",
    "check_plugin_conformance",
    "detect_undefined_symbols",
    "load_config",
    "sandbox_run",
    "scan_hallucination_words",
    "schema_validate",
]