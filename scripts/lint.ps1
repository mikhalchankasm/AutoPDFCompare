Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repo ".venv/Scripts/python.exe"
$python = if (Test-Path $venvPython) { $venvPython } else { "python" }

Push-Location $repo
try {
    & $python scripts/verify_environment.py
    if ($LASTEXITCODE -ne 0) { throw "Environment differs from runtime lock; run setup.ps1" }
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

    # mypy is a hard gate (the tree is currently clean).
    # Set $env:LINT_ALLOW_MYPY_FAIL=1 to temporarily downgrade it to informational.
    #
    # scripts/ is listed file by file, not as a directory: the .ps1 files are not
    # Python, and the two entry points below are the ones that actually run in
    # production. They were outside the gate until v0.1.20 and were carrying a real
    # type error (FastMCP.run's transport is a Literal, not a str), so CI was green
    # on code that mypy rejects. Anything new under scripts/ belongs on this list.
    & $python -m mypy `
        compare_pdfs.py `
        pdfcompare_gui.py `
        pdfcompare_core `
        pdfcompare_ui `
        scripts/pdfcompare_mcp.py `
        scripts/pdfcompare_worker.py `
        scripts/process_identity.py `
        scripts/verify_environment.py
    if ($env:LINT_ALLOW_MYPY_FAIL -ne "1" -and $LASTEXITCODE -ne 0) { throw "mypy failed" }
    if (Test-Path "pdfcompare_bot") {
        & $python -m ruff check pdfcompare_bot
        if ($LASTEXITCODE -ne 0) { throw "Private service ruff failed" }
        & $python -m mypy pdfcompare_bot
        if ($LASTEXITCODE -ne 0) { throw "Private service mypy failed" }
    }
}
finally {
    Pop-Location
}
