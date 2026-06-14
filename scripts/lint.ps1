Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repo ".venv/Scripts/python.exe"
$python = if (Test-Path $venvPython) { $venvPython } else { "python" }

Push-Location $repo
try {
    $compileFiles = @(
        "compare_pdfs.py",
        "pdfcompare_gui.py"
    )
    $compileFiles += Get-ChildItem -Path "pdfcompare_core", "pdfcompare_ui", "scripts" -Filter "*.py" -Recurse |
        ForEach-Object { $_.FullName }

    & $python -m py_compile @compileFiles
    if ($LASTEXITCODE -ne 0) { throw "py_compile failed" }

    & $python -m ruff check compare_pdfs.py pdfcompare_gui.py pdfcompare_core pdfcompare_ui scripts tests
    if ($LASTEXITCODE -ne 0) { throw "ruff check failed" }

    # mypy is informational — many cv2/tkinter false positives still to clean up.
    # Set $env:LINT_STRICT_MYPY=1 to make mypy a hard gate.
    & $python -m mypy compare_pdfs.py pdfcompare_gui.py pdfcompare_core pdfcompare_ui
    if ($env:LINT_STRICT_MYPY -eq "1" -and $LASTEXITCODE -ne 0) { throw "mypy failed" }
}
finally {
    Pop-Location
}
