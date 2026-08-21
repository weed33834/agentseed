#!/usr/bin/env bash
# AgentSeed installer - download the latest release and wire it into a client.
#
# Usage: ./install.sh [--client claude|opencode|cursor|manual] [--dir TARGET]
#
# Layout after install:
#   ~/.agentseed/AgentSeed/            full plugin (MCP server lives here)
#   <client skill dir>/                flat skill copy (SKILL.md at top level)
#
# The installer prints the exact MCP registration step for your client.
set -e
repo="weed33834/AgentSeed"
client="auto"
dir=""
while [ $# -gt 0 ]; do
  case "$1" in
    --client) client="$2"; shift 2 ;;
    --dir) dir="$2"; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

echo "==> resolving latest release of $repo"
url=$(curl -fsSL "https://api.github.com/repos/$repo/releases/latest" |
  grep -o '"browser_download_url": *"[^"]*\.zip"' | head -1 |
  sed 's/.*"\(https[^"]*\)"/\1/')
[ -n "$url" ] || { echo "no .zip asset on the latest release" >&2; exit 1; }

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
echo "==> downloading $url"
curl -fsSL "$url" -o "$tmp/agentseed.zip"
unzip -q "$tmp/agentseed.zip" -d "$tmp/x"
src=$(dirname "$(find "$tmp/x" -name plugin.json | head -1)")
[ -n "$src" ] || { echo "plugin.json not found in archive" >&2; exit 1; }

# 1) stable full-plugin home (the MCP server runs from here)
plugin_home="${AGENTSEED_HOME:-$HOME/.agentseed}/AgentSeed"
mkdir -p "$(dirname "$plugin_home")"
rm -rf "$plugin_home"
cp -R "$src" "$plugin_home"
echo "==> full plugin installed to $plugin_home"

# 2) flat skill copy so clients that scan <dir>/SKILL.md find it
install_skill() {
  mkdir -p "$1"
  rm -rf "$1"
  mkdir -p "$1"
  cp -R "$plugin_home/skills/verify-before-code/"* "$1/"
  printf '%s' "$plugin_home" > "$1/.agentseed-plugin-root"
  echo "==> skill installed to $1"
}

case "$client" in
  claude)
    install_skill "$HOME/.claude/skills/verify-before-code"
    echo ""
    echo "==> final step - register the MCP server:"
    echo "    claude mcp add agentseed -- python \"$plugin_home/server/guard_server.py\""
    ;;
  opencode)
    install_skill "$HOME/.config/opencode/skill/verify-before-code"
    echo ""
    echo "==> final step - add to ~/.config/opencode/opencode.json:"
    cat <<EOF
    "mcp": {
      "agentseed": {
        "type": "local",
        "command": ["python", "$plugin_home/server/guard_server.py"],
        "enabled": true
      }
    }
EOF
    ;;
  cursor)
    echo "==> Cursor has no stable Agent Plugins directory yet."
    echo "    Plugin kept at: $plugin_home"
    echo "    Register the MCP server in Cursor settings:"
    echo "      command: python  args: [$plugin_home/server/guard_server.py]"
    ;;
  manual|auto)
    dest="${dir:-$PWD}/AgentSeed"
    mkdir -p "$(dirname "$dest")"
    rm -rf "$dest"
    cp -R "$src" "$dest"
    echo "==> plugin copied to $dest"
    echo "==> done. Drop it into your client, or re-run with --client claude|opencode."
    ;;
esac
