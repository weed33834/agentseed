# AgentSeed installer - download the latest release and wire it into a client.
#
# Usage: .\install.ps1 [-Client claude|opencode|cursor|manual] [-Dir TARGET]
#
# Layout after install:
#   ~\.agentseed\AgentSeed\            full plugin (MCP server lives here)
#   <client skill dir>\                flat skill copy (SKILL.md at top level)
#
# The installer prints the exact MCP registration step for your client.
param(
    [ValidateSet("auto", "claude", "opencode", "cursor", "manual")]
    [string]$Client = "auto",
    [string]$Dir = ""
)
$ErrorActionPreference = "Stop"
$repo = "weed33834/AgentSeed"

Write-Host "==> resolving latest release of $repo"
$rel = Invoke-RestMethod -Uri "https://api.github.com/repos/$repo/releases/latest" `
        -Headers @{ "User-Agent" = "agentseed-installer" }
$asset = $rel.assets | Where-Object { $_.name -like "*.zip" } | Select-Object -First 1
if (-not $asset) { throw "no .zip asset on the latest release" }

$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("agentseed-" + [guid]::NewGuid())
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
try {
    Write-Host "==> downloading $($asset.browser_download_url)"
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile "$tmp\agentseed.zip" `
        -Headers @{ "User-Agent" = "agentseed-installer" }
    Expand-Archive "$tmp\agentseed.zip" "$tmp\x" -Force
    $src = Get-ChildItem "$tmp\x" -Recurse -Filter plugin.json |
        Select-Object -First 1 | ForEach-Object { $_.Directory.FullName }
    if (-not $src) { throw "plugin.json not found in archive" }

    # 1) stable full-plugin home (the MCP server runs from here)
    $base = if ($env:AGENTSEED_HOME) { $env:AGENTSEED_HOME } else { Join-Path $HOME ".agentseed" }
    $pluginHome = Join-Path $base "AgentSeed"
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $pluginHome) | Out-Null
    if (Test-Path $pluginHome) { Remove-Item -Recurse -Force $pluginHome }
    Copy-Item -Recurse $src $pluginHome
    Write-Host "==> full plugin installed to $pluginHome"

    # 2) flat skill copy so clients that scan <dir>\SKILL.md find it
    $skillSrc = Join-Path $pluginHome "skills\verify-before-code"
    function Install-Skill([string]$dest) {
        if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
        New-Item -ItemType Directory -Force -Path $dest | Out-Null
        Copy-Item -Recurse (Join-Path $skillSrc "*") $dest
        Set-Content -Path (Join-Path $dest ".agentseed-plugin-root") -Value $pluginHome -NoNewline
        Write-Host "==> skill installed to $dest"
    }
    $serverPy = Join-Path $pluginHome "server\guard_server.py"

    switch ($Client) {
        "claude" {
            Install-Skill "$HOME\.claude\skills\verify-before-code"
            Write-Host ""
            Write-Host "==> final step - register the MCP server:"
            Write-Host "    claude mcp add agentseed -- python `"$serverPy`""
        }
        "opencode" {
            Install-Skill "$HOME\.config\opencode\skill\verify-before-code"
            Write-Host ""
            Write-Host "==> final step - add to ~/.config/opencode/opencode.json:"
            Write-Host "    `"mcp`": { `"agentseed`": { `"type`": `"local`","
            Write-Host "        `"command`": [`"python`", `"$serverPy`"], `"enabled`": true } }"
        }
        "cursor" {
            Write-Host "==> Cursor has no stable Agent Plugins directory yet."
            Write-Host "    Plugin kept at: $pluginHome"
            Write-Host "    Register the MCP server in Cursor settings:"
            Write-Host "      command: python  args: [$serverPy]"
        }
        default {
            $dest = if ($Dir) { Join-Path $Dir "AgentSeed" } else { Join-Path $PWD "AgentSeed" }
            if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
            Copy-Item -Recurse $src $dest
            Write-Host "==> plugin copied to $dest"
            Write-Host "==> done. Drop it into your client, or re-run with -Client claude|opencode."
        }
    }
}
finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
