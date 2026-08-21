#!/usr/bin/env pwsh
# AgentSeed quick check - validate the plugin in the given directory.
# Usage: .\check.ps1 [-Strict] [plugin-dir]
param(
    [switch]$Strict,
    [string]$Target = "."
)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$cli = Join-Path $here "..\..\..\server\guard_cli.py"
if (-not (Test-Path $cli) -and $env:PLUGIN_ROOT) {
    $cli = Join-Path $env:PLUGIN_ROOT "server\guard_cli.py"
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
