#!/usr/bin/env bash
# AgentSeed quick check — validate the plugin in the given directory.
# Usage: ./check.sh [--strict] [plugin-dir]
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
CLI="$DIR/../../../server/guard_cli.py"
if [ ! -f "$CLI" ] && [ -n "$PLUGIN_ROOT" ]; then CLI="$PLUGIN_ROOT/server/guard_cli.py"; fi
if [ "$1" = "--strict" ]; then
  shift
  "${PYTHON:-python3}" "$CLI" check "$1"
  exec "${PYTHON:-python3}" "$CLI" scan "$1" --strict
else
  exec "${PYTHON:-python3}" "$CLI" check "${1:-.}"
fi
