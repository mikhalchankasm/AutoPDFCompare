Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repo ".venv/Scripts/python.exe"
$python = if (Test-Path $venvPython) { $venvPython } else { "python" }

Push-Location $repo
try {
    & $python -m py_compile compare_pdfs.py pdfcompare_gui.py
}
finally {
    Pop-Location
}
