param(
    [switch]$WithMcp,
    # Install the loose ranges from base.txt/mcp.txt instead of the hashed lock.
    [switch]$Loose
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

    # The MCP checkout pulls master on every start, so it installs the hashed
    # runtime lock: the same commit must not silently pick up a different
    # NumPy/OpenCV/PyMuPDF tomorrow. -Loose is the developer escape hatch.
    $lock = Join-Path $repo "requirements/lock-runtime.txt"
    if ((-not $Loose) -and (Test-Path $lock)) {
        & $python -m pip install --require-hashes -r $lock
        if ($LASTEXITCODE -ne 0) { throw "pip install --require-hashes failed" }
    }
    else {
        & $python -m pip install -r (Join-Path $repo "requirements/base.txt")
        if ($WithMcp) {
            & $python -m pip install -r (Join-Path $repo "requirements/mcp.txt")
        }
    }
}
finally {
    Pop-Location
}
