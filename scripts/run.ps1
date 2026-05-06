Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repo ".venv/Scripts/python.exe"
$python = if (Test-Path $venvPython) { $venvPython } else { "python" }

Push-Location $repo
try {
    & $python pdfcompare_gui.py
}
finally {
    Pop-Location
}
