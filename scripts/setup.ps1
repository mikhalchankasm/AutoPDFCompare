param(
    [switch]$WithMcp
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $repo ".venv"

Push-Location $repo
try {
    if (-not (Test-Path $venv)) {
        python -m venv $venv
    }

    $python = Join-Path $venv "Scripts/python.exe"
    & $python -m pip install --upgrade pip
    & $python -m pip install -r requirements.txt
    if ($WithMcp) {
        & $python -m pip install -r requirements-mcp.txt
    }
}
finally {
    Pop-Location
}
