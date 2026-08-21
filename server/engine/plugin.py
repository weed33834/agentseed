"""AgentSeed Agent Plugins 1.0.0 conformance checker.

Validates plugin.json / skills / mcp.json against the Agent Plugins spec
(§5, §6, §7). Acts as the spec's missing official linter.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
from urllib.parse import urlsplit

# ---------------------------------------------------------------------------
# Agent Plugins 1.0.0 conformance constants
# ---------------------------------------------------------------------------

PLUGIN_TOP_LEVEL_FIELDS = {
    "$schema", "name", "version", "description",
    "author", "homepage", "repository", "license", "keywords", "extensions",
}
AUTHOR_FIELDS = {"name", "email", "url"}
MCP_TOP_LEVEL_FIELDS = {"$schema", "mcpServers"}
_PLUGIN_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9.\-]*[a-z0-9])?$")
_SKILL_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?$")


def _check_plugin_name(name: str) -> list[str]:
    """Validate plugin.json ``name`` against §5.5 naming constraints."""
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


def _parse_plugin_json(plugin_dir: str) -> tuple[dict, list[str]]:
    """Load and return (plugin_data, errors) from plugin.json."""
    pj = os.path.join(plugin_dir, "plugin.json")
    errors: list[str] = []
    if not os.path.isfile(pj):
        errors.append("Missing root plugin.json (spec requires checking root plugin.json)")
        return {}, errors
    try:
        with open(pj, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"plugin.json is not valid JSON: {exc}")
        return {}, errors
    if not isinstance(data, dict):
        errors.append("plugin.json top level must be a JSON object")
        return {}, errors
    return data, errors


def _parse_frontmatter(skill_md_path: str) -> dict:
    """Extract name/description from a SKILL.md frontmatter block.

    Uses PyYAML when available for full YAML coverage (nested maps, lists,
    quoting rules); falls back to a zero-dependency YAML-lite parser that
    handles ``key: value`` and folded scalars (``description: >-`` followed
    by indented lines).
    """
    try:
        with open(skill_md_path, encoding="utf-8") as fh:
            content = fh.read()
    except OSError:
        return {}
    if not content.startswith("---"):
        return {}
    end_m = re.search(r"^---\s*$", content[3:], re.MULTILINE)
    if end_m is None:
        return {}
    block = content[3:3 + end_m.start()]

    try:
        import yaml  # type: ignore import-not-found

        parsed = yaml.safe_load(block)
        return parsed if isinstance(parsed, dict) else {}
    except ImportError:
        pass
    except Exception:  # malformed YAML -> fall through to the lite parser
        pass

    out: dict = {}
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
        return errs
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


def _is_loopback_address(host: str) -> bool:
    """Check if host is loopback (localhost hostname, 127.0.0.0/8, ::1).

    Uses stdlib ``ipaddress`` instead of a hand-rolled IPv4-only check.
    """
    if host.lower() in ("localhost",):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _check_mcp_servers(m: dict, errors: list[str]) -> None:
    """Validate the mcpServers section of mcp.json."""
    servers = m.get("mcpServers", {})
    if not isinstance(servers, dict):
        errors.append("mcp.json 'mcpServers' must be an object")
        return
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
                    and not _is_loopback_address(host)
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


def check_plugin_conformance(plugin_dir: str) -> dict:
    """Validate a directory against Agent Plugins 1.0.0 (§5/§6/§7).

    Strict linter: closed-schema top-level fields, ``name`` constraints,
    SKILL.md frontmatter, mcp.json fields and cwd form.

    Returns:
        {"ok": bool, "errors": [...], "warnings": [...]}
    """
    errors: list[str] = []
    warnings: list[str] = []

    # ---- §5 manifest ------------------------------------------------------
    data, pe = _parse_plugin_json(plugin_dir)
    errors.extend(pe)

    if data:
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
            msg = (
                "No skills/ directory (pure-MCP plugin is conformant, but this "
                "plugin is designed hybrid)"
            )
            warnings.append(msg)
    else:
        msg = (
            "No skills/ directory (pure-MCP plugin is conformant, but this "
            "plugin is designed hybrid)"
        )
        warnings.append(msg)

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
        _check_mcp_servers(m, errors)
    else:
        warnings.append("No mcp.json (pure-skill plugin is conformant)")

    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}