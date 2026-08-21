"""AgentSeed config loading — zero dependencies."""

from __future__ import annotations

import json
import os

CONFIG_FILENAME = "agentseed.config.json"
_VALID_SEVERITIES = {"error", "warning", "info"}


def load_config(explicit_path: str | None = None) -> dict:
    """Load the effective AgentSeed config (zero dependencies).

    Search order (first hit wins):
      1. ``explicit_path`` argument
      2. ``AGENTSEED_CONFIG`` environment variable
      3. ``${PLUGIN_DATA}/agentseed.config.json``
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
    """Extract a validated string-list value from config, or None."""
    value = config.get(key)
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return value
    return None


def _config_severities(config: dict) -> dict[str, str] | None:
    """Extract a validated severities map from config, or None."""
    value = config.get("severities")
    if isinstance(value, dict) and all(
        isinstance(k, str) and isinstance(v, str) and v in _VALID_SEVERITIES
        for k, v in value.items()
    ):
        return value
    return None


def _parse_timeout(config: dict, default: int = 30) -> int:
    """Extract and validate timeout from config dict."""
    try:
        return int(config.get("timeout", default))
    except (TypeError, ValueError):
        return default