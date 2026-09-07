Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repo ".venv/Scripts/python.exe"
$python = if (Test-Path $venvPython) { $venvPython } else { "python" }

Push-Location $repo
try {
    # Coverage gate: core engine only (GUI is intentionally excluded — Tk
    # widgets are not unit-testable in CI). Actual core coverage is ~85%;
    # the threshold sits a couple of points lower so an unrelated line
    # does not block a merge. Raise it as coverage grows.
    New-Item -ItemType Directory -Force -Path (Join-Path $repo "tmp/coverage-core") | Out-Null
    & $python -m pytest --cov=pdfcompare_core --cov-config=requirements/coverage-core.ini --cov-report=term --cov-report=json:tmp/coverage-core/coverage.json --cov-fail-under=82
    if ($LASTEXITCODE -ne 0) {
        throw "pytest failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
