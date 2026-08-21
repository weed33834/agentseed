# AgentSeed installer - download the latest release and drop it into a client.
# Usage: .\install.ps1 [-Client cursor|claude|opencode|vscode|manual] [-Dir TARGET]
param(
    [ValidateSet("auto", "cursor", "claude", "opencode", "vscode", "manual")]
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

    function Install-To([string]$dest) {
        if ($dest -like "*skills*") {
            # skill layout: contents go directly under skills/<name>
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
        } else {
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
        }
        if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
        Copy-Item -Recurse $src $dest
        Write-Host "==> installed to $dest"
    }

    switch ($Client) {
        "cursor"   { Install-To "$HOME\.cursor\extensions\agentseed\agentseed" }
        "claude"   { Install-To "$HOME\.claude\skills\verify-before-code" }
        "opencode" { Install-To "$HOME\.config\opencode\skill\verify-before-code" }
        "vscode"   { Install-To "$HOME\.vscode\extensions\agentseed\agentseed" }
        "manual"   { Install-To $(if ($Dir) { $Dir } else { Join-Path $PWD "AgentSeed" }) }
        default    {
            $dest = if ($Dir) { Join-Path $Dir "AgentSeed" } else { Join-Path $PWD "AgentSeed" }
            Install-To $dest
            Write-Host "==> done. Drop $dest into your client, or re-run with -Client <name>."
        }
    }
}
finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
