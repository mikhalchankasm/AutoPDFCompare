param(
    [switch]$AutoUpdate
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$stateDir = Join-Path $repo ".pdfcompare_mcp"
$log = Join-Path $stateDir "bootstrap.log"

function Write-BootstrapLog {
    param([string]$Message)

    $timestamp = Get-Date -Format "o"
    Add-Content -LiteralPath $log -Value "[$timestamp] $Message" -Encoding UTF8
}

function Invoke-Logged {
    param(
        [scriptblock]$Script,
        [string]$Action,
        [switch]$ContinueOnError
    )

    Write-BootstrapLog $Action
    try {
        & $Script *>> $log
        return $true
    }
    catch {
        Write-BootstrapLog "$Action failed: $($_.Exception.Message)"
        if (-not $ContinueOnError) {
            throw
        }
        return $false
    }
}

function Get-RequirementsStamp {
    $parts = @()
    foreach ($file in @("requirements/base.txt", "requirements/mcp.txt")) {
        $path = Join-Path $repo $file
        if (Test-Path $path) {
            $hash = Get-FileHash -LiteralPath $path -Algorithm SHA256
            $parts += "$file=$($hash.Hash)"
        }
        else {
            $parts += "$file=missing"
        }
    }

    $git = Get-Command git -ErrorAction SilentlyContinue
    if ($git) {
        try {
            $head = (& git -C $repo rev-parse HEAD 2>> $log).Trim()
            $parts += "HEAD=$head"
        }
        catch {
            $parts += "HEAD=unknown"
        }
    }

    return ($parts -join "`n")
}

New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
if ((Test-Path $log) -and ((Get-Item -LiteralPath $log).Length -gt 1MB)) {
    Move-Item -LiteralPath $log -Destination (Join-Path $stateDir "bootstrap.log.old") -Force
}

Push-Location $repo
try {
    $git = Get-Command git -ErrorAction SilentlyContinue
    $envAutoUpdate = $env:PDFCOMPARE_MCP_AUTO_UPDATE -in @("1", "true", "TRUE", "yes", "YES", "on", "ON")
    if ($git -and ($AutoUpdate -or $envAutoUpdate)) {
        $branch = (& git rev-parse --abbrev-ref HEAD 2>> $log).Trim()
        $dirty = & git status --porcelain --untracked-files=no 2>> $log
        if ($branch -ne "master") {
            Write-BootstrapLog "Skipping auto-update because current branch is '$branch', not 'master'."
        }
        elseif ($dirty) {
            Write-BootstrapLog "Skipping auto-update because the working tree has local changes."
        }
        else {
            Invoke-Logged -Action "Updating repository from origin/master." -ContinueOnError -Script {
                git fetch --prune origin
                if ($LASTEXITCODE -ne 0) {
                    throw "git fetch failed with exit code $LASTEXITCODE"
                }
                git pull --ff-only origin master
                if ($LASTEXITCODE -ne 0) {
                    throw "git pull failed with exit code $LASTEXITCODE"
                }
            } | Out-Null
        }
    }
    elseif ($git) {
        Write-BootstrapLog "Auto-update is disabled. Run with -AutoUpdate or set PDFCOMPARE_MCP_AUTO_UPDATE=1 to update on start."
    }
    else {
        Write-BootstrapLog "Git is not available; skipping auto-update."
    }

    $venvPython = Join-Path $repo ".venv/Scripts/python.exe"
    $stampFile = Join-Path $stateDir "bootstrap-stamp.txt"
    $currentStamp = (Get-RequirementsStamp).TrimEnd("`r", "`n")
    $savedStamp = if (Test-Path $stampFile) { (Get-Content -Raw -LiteralPath $stampFile).TrimEnd("`r", "`n") } else { "" }
    $needsSetup = (-not (Test-Path $venvPython)) -or ($savedStamp -ne $currentStamp)

    if ($needsSetup) {
        Invoke-Logged -Action "Ensuring Python dependencies." -Script {
            & (Join-Path $repo "scripts/setup.ps1") -WithMcp
            if ($LASTEXITCODE -ne 0) {
                throw "setup.ps1 failed with exit code $LASTEXITCODE"
            }
        } | Out-Null
        Set-Content -LiteralPath $stampFile -Value $currentStamp -Encoding UTF8
    }
    else {
        Write-BootstrapLog "Python dependencies are up to date."
    }

    & (Join-Path $repo "scripts/run_mcp.ps1")
}
finally {
    Pop-Location
}
