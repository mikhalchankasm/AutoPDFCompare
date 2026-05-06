param(
    [string]$OutputDir = "dist_portable"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$outRoot = Join-Path $repo $OutputDir
$stage = Join-Path $outRoot "PDFCompareLocal-portable"
$zip = Join-Path $outRoot "PDFCompareLocal-portable.zip"

Push-Location $repo
try {
    if (Test-Path $stage) {
        Remove-Item -LiteralPath $stage -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $stage | Out-Null

    $files = @(
        "compare_pdfs.py",
        "pdfcompare_gui.py",
        "run_gui.bat",
        "run_gui_silent.vbs",
        "requirements.txt",
        "README.md",
        "CHANGELOG.md"
    )
    foreach ($file in $files) {
        Copy-Item -LiteralPath (Join-Path $repo $file) -Destination $stage
    }

    New-Item -ItemType Directory -Force -Path (Join-Path $stage "scripts") | Out-Null
    foreach ($script in @("setup.ps1", "run.ps1", "lint.ps1", "test.ps1", "ai_review_context.ps1")) {
        Copy-Item -LiteralPath (Join-Path $repo "scripts/$script") -Destination (Join-Path $stage "scripts")
    }

    if (Test-Path (Join-Path $repo "tests")) {
        Copy-Item -LiteralPath (Join-Path $repo "tests") -Destination $stage -Recurse
    }
    Get-ChildItem -Path $stage -Directory -Recurse -Filter "__pycache__" | Remove-Item -Recurse -Force

    if (Test-Path $zip) {
        Remove-Item -LiteralPath $zip -Force
    }
    Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -Force
    Write-Output (Resolve-Path $zip)
}
finally {
    Pop-Location
}
