#!/usr/bin/env bash
# AgentSeed installer - download the latest release and drop it into a client.
# Usage: ./install.sh [--client cursor|claude|opencode|vscode|manual] [--dir TARGET]
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

install_to() {
  mkdir -p "$(dirname "$1")"
  rm -rf "$1"
  cp -R "$src" "$1"
  echo "==> installed to $1"
}

case "$client" in
  cursor)   install_to "$HOME/.cursor/extensions/agentseed/agentseed" ;;
  claude)   install_to "$HOME/.claude/skills/verify-before-code" ;;
  opencode) install_to "$HOME/.config/opencode/skill/verify-before-code" ;;
  vscode)   install_to "$HOME/.vscode/extensions/agentseed/agentseed" ;;
  manual|auto)
    dest="${dir:-$PWD}/AgentSeed"
    install_to "$dest"
    echo "==> done. Drop $dest into your client, or re-run with --client <name>."
    ;;
esac
