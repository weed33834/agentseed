#!/usr/bin/env bash
# AgentSeed quick check - validate the plugin in the given directory.
# Usage: ./check.sh [--strict] [plugin-dir]
#
# Locates guard_cli.py by walking up from this script until a plugin.json
# (the plugin root) is found; override with AGENTSEED_PLUGIN_ROOT.
set -e
here="$(cd "$(dirname "$0")" && pwd)"

cli=""
if [ -n "$AGENTSEED_PLUGIN_ROOT" ] && [ -f "$AGENTSEED_PLUGIN_ROOT/server/guard_cli.py" ]; then
  cli="$AGENTSEED_PLUGIN_ROOT/server/guard_cli.py"
elif [ -f "$here/.agentseed-plugin-root" ] || [ -f "$here/../.agentseed-plugin-root" ]; then
  pf="$here/.agentseed-plugin-root"
  [ -f "$pf" ] || pf="$here/../.agentseed-plugin-root"
  root="$(cat "$pf")"
  [ -f "$root/server/guard_cli.py" ] && cli="$root/server/guard_cli.py"
else
  d="$here"
  for _ in 1 2 3 4 5; do
    d="$(dirname "$d")"
    if [ -f "$d/plugin.json" ] && [ -f "$d/server/guard_cli.py" ]; then
      cli="$d/server/guard_cli.py"; break
    fi
  done
fi

if [ -z "$cli" ]; then
  echo "error: cannot locate server/guard_cli.py." >&2
  echo "Install the full AgentSeed plugin, or set AGENTSEED_PLUGIN_ROOT to its directory." >&2
  exit 2
fi

py="${PYTHON:-python3}"
command -v "$py" >/dev/null 2>&1 || py=python

target="${1:-.}"
if [ "$1" = "--strict" ]; then
  target="${2:-.}"
  "$py" "$cli" check "$target"
  exec "$py" "$cli" scan "$target" --strict
else
  exec "$py" "$cli" check "$target"
fi
