param(
    [string]$OutputPath = "tmp/ai_review_context.md"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
Push-Location $repo
try {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutputPath) | Out-Null

    $status = git status --short
    $diff = git diff -- compare_pdfs.py pdfcompare_gui.py README.md tests scripts

    $prompt = @"
# PDFCompare AI Review Context

You are reviewing a local Python desktop tool that compares two PDF revisions and generates an HTML report.

Focus on:
- correctness of PDF page matching and visual diff classification;
- performance and memory use on large engineering drawings;
- storage size of generated run folders and report ZIPs;
- low-risk changes suitable for a Windows desktop app.

Please return:
- findings first, ordered by severity;
- file/function references;
- concrete fixes or test cases;
- any risky recommendations clearly marked as risky.

## Git Status

````text
$status
````

## Current Diff

````diff
$diff
````
"@

    $prompt | Set-Content -Path $OutputPath -Encoding UTF8
    Write-Output (Resolve-Path $OutputPath)
}
finally {
    Pop-Location
}
