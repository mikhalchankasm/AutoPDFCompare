param(
    [string]$OutputDir = "dist_portable"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$outRoot = Join-Path $repo $OutputDir
$stage = Join-Path $outRoot "PDFCompareLocal-portable"
$zip = Join-Path $outRoot "PDFCompareLocal-portable.zip"
$resolvedOutRoot = [IO.Path]::GetFullPath($outRoot)
$resolvedRepo = [IO.Path]::GetFullPath($repo).TrimEnd('\', '/')
if (-not $resolvedOutRoot.StartsWith($resolvedRepo + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw "OutputDir must stay inside the repository"
}

Push-Location $repo
try {
    if (Test-Path $stage) {
        Remove-Item -LiteralPath $stage -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $stage | Out-Null

    $files = @(
        "compare_pdfs.py",
        "pdfcompare_gui.py",
        "README.md",
        "CHANGELOG.md"
    )
    foreach ($file in $files) {
        Copy-Item -LiteralPath (Join-Path $repo $file) -Destination $stage
    }

    foreach ($dir in @("pdfcompare_core", "pdfcompare_ui")) {
        Copy-Item -LiteralPath (Join-Path $repo $dir) -Destination $stage -Recurse
    }

    $requirementsStage = Join-Path $stage "requirements"
    New-Item -ItemType Directory -Force -Path $requirementsStage | Out-Null
    foreach ($requirement in @("base.txt", "dev.txt", "mcp.txt", "lock.txt", "lock-runtime.txt", "lock.in", "lock-runtime.in")) {
        Copy-Item -LiteralPath (Join-Path $repo "requirements/$requirement") -Destination $requirementsStage
    }
    Copy-Item -LiteralPath (Join-Path $repo "scripts/run_gui.bat") -Destination (Join-Path $stage "run_gui.bat")
    Copy-Item -LiteralPath (Join-Path $repo "scripts/run_gui_silent.vbs") -Destination (Join-Path $stage "run_gui_silent.vbs")

    $docsStage = Join-Path $stage "docs"
    New-Item -ItemType Directory -Force -Path $docsStage | Out-Null
    foreach ($doc in @("LOCAL_AGENT_MCP.md", "PDFCOMPARE_AGENT_SKILL.md", "AGENT_PROMPTS.md", "SETUP_PROMPT.md")) {
        Copy-Item -LiteralPath (Join-Path $repo "docs/$doc") -Destination $docsStage
    }

    New-Item -ItemType Directory -Force -Path (Join-Path $stage "scripts") | Out-Null
    foreach ($script in @(
        "setup.ps1",
        "run.ps1",
        "run_mcp.ps1",
        "run_mcp_bootstrap.ps1",
        "pdfcompare_mcp.py",
        "pdfcompare_worker.py",
        "process_identity.py",
        "verify_environment.py"
    )) {
        Copy-Item -LiteralPath (Join-Path $repo "scripts/$script") -Destination (Join-Path $stage "scripts")
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
