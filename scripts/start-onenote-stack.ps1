param(
    [switch]$NoBrowser,
    [int]$HealthTimeoutSeconds = 180,
    [int]$CompanyKnowledgeUITimeoutSeconds = 240
)

# Power button: starts the stack and nothing else.
#   - Does NOT stop, remove, recreate, or rebuild anything.
#   - Does NOT touch host ports or any process outside this project.
#   - Does NOT sync/re-index data.
# `docker compose up -d` starts services that are down and leaves running ones
# (and all data volumes) untouched. Safe to run repeatedly.

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $PSScriptRoot
$EnvPath = Join-Path $RepoRoot ".env"
$EnvExamplePath = Join-Path $RepoRoot ".env.example"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

function Read-DotEnv {
    param([string]$Path)

    $values = @{}
    if (-not (Test-Path $Path)) {
        return $values
    }

    foreach ($line in Get-Content $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) {
            continue
        }

        $key, $value = $trimmed.Split("=", 2)
        $values[$key.Trim()] = $value.Trim().Trim('"').Trim("'")
    }

    return $values
}

function Get-Setting {
    param(
        [hashtable]$Values,
        [string]$Key,
        [string]$Default = ""
    )

    if ($Values.ContainsKey($Key) -and $Values[$Key]) {
        return $Values[$Key]
    }

    return $Default
}

function Wait-Http {
    param(
        [string]$Url,
        [int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5 | Out-Null
            return
        } catch {
            Start-Sleep -Seconds 2
        }
    }

    throw "Timed out waiting for $Url"
}

Push-Location $RepoRoot
try {
    Write-Step "Checking Docker"
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker CLI was not found. Start Docker Desktop first."
    }
    Invoke-Checked docker info | Out-Null

    if (-not (Test-Path $EnvPath)) {
        if (-not (Test-Path $EnvExamplePath)) {
            throw ".env is missing and .env.example was not found."
        }
        Copy-Item $EnvExamplePath $EnvPath
        Write-Host "Created .env from .env.example (existing .env is never modified)."
    }

    $envValues = Read-DotEnv $EnvPath
    $ragApiPort = Get-Setting $envValues "RAG_API_PORT" "8080"
    $companyKnowledgeUiPort = Get-Setting $envValues "COMPANY_KNOWLEDGE_UI_PORT" "5173"
    $ragApiUrl = "http://localhost:$ragApiPort"
    $companyKnowledgeUiUrl = "http://localhost:$companyKnowledgeUiPort"

    Write-Step "Starting the stack (nothing is stopped, removed, or rebuilt)"
    Invoke-Checked docker compose up -d

    Write-Step "Waiting for the RAG API at $ragApiUrl"
    Wait-Http -Url "$ragApiUrl/health" -TimeoutSeconds $HealthTimeoutSeconds
    Wait-Http -Url "$ragApiUrl/ready" -TimeoutSeconds $HealthTimeoutSeconds

    Write-Step "Waiting for the Company Knowledge UI at $companyKnowledgeUiUrl"
    try {
        Wait-Http -Url $companyKnowledgeUiUrl -TimeoutSeconds $CompanyKnowledgeUITimeoutSeconds
    } catch {
        Write-Host "UI not reachable yet; it may still be starting. Check: docker compose logs company-knowledge-ui" -ForegroundColor Yellow
    }

    if (-not $NoBrowser) {
        Start-Process $companyKnowledgeUiUrl
    }

    Write-Step "Ready"
    Write-Host "RAG API:              $ragApiUrl"
    Write-Host "API docs:             $ragApiUrl/docs"
    Write-Host "Company Knowledge UI: $companyKnowledgeUiUrl"
} finally {
    Pop-Location
}
