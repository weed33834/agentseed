# AgentSeed quick check - validate the plugin in the given directory.
# Usage: .\check.ps1 [-Strict] [plugin-dir]
#
# Locates guard_cli.py by walking up from this script until a plugin.json
# (the plugin root) is found; override with AGENTSEED_PLUGIN_ROOT.
param(
    [switch]$Strict,
    [string]$Target = "."
)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

$cli = $null
if ($env:AGENTSEED_PLUGIN_ROOT -and (Test-Path (Join-Path $env:AGENTSEED_PLUGIN_ROOT "server\guard_cli.py"))) {
    $cli = Join-Path $env:AGENTSEED_PLUGIN_ROOT "server\guard_cli.py"
}
elseif ((Test-Path (Join-Path $here ".agentseed-plugin-root")) -or (Test-Path (Join-Path $here "..\.agentseed-plugin-root"))) {
    $pf = Join-Path $here ".agentseed-plugin-root"
    if (-not (Test-Path $pf)) { $pf = Join-Path $here "..\.agentseed-plugin-root" }
    $root = (Get-Content $pf -Raw).Trim()
    if ($root -and (Test-Path (Join-Path $root "server\guard_cli.py"))) {
        $cli = Join-Path $root "server\guard_cli.py"
    }
}
else {
    $d = $here
    foreach ($i in 1..5) {
        $d = Split-Path -Parent $d
        if (-not $d) { break }
        if ((Test-Path (Join-Path $d "plugin.json")) -and (Test-Path (Join-Path $d "server\guard_cli.py"))) {
            $cli = Join-Path $d "server\guard_cli.py"
            break
        }
    }
}

if (-not $cli) {
    Write-Error "cannot locate server/guard_cli.py. Install the full AgentSeed plugin, or set AGENTSEED_PLUGIN_ROOT to its directory."
    exit 2
}

$py = if ($env:PYTHON) { $env:PYTHON } else { "python" }
if ($Strict) {
    & $py $cli check $Target
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $py $cli scan $Target --strict
    exit $LASTEXITCODE
}
else {
    & $py $cli check $Target
    exit $LASTEXITCODE
}
