param(
    [switch]$Build,
    [switch]$Bootstrap,
    [switch]$SkipSync,
    [switch]$SkipOpsWorker,
    [switch]$SkipOpenWebUI,
    [switch]$NoBrowser,
    [switch]$NoEnvUpdate,
    [int]$HealthTimeoutSeconds = 120,
    [int]$OpenWebUITimeoutSeconds = 300
)

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

function Set-DotEnvValues {
    param(
        [string]$Path,
        [hashtable]$Updates
    )

    $lines = [System.Collections.Generic.List[string]]::new()
    $seen = @{}

    if (Test-Path $Path) {
        foreach ($line in Get-Content $Path) {
            if ($line.Trim().StartsWith("#") -or -not $line.Contains("=")) {
                $lines.Add($line)
                continue
            }

            $key = $line.Split("=", 2)[0].Trim()
            if ($Updates.ContainsKey($key)) {
                $lines.Add("$key=$($Updates[$key])")
                $seen[$key] = $true
            } else {
                $lines.Add($line)
            }
        }
    }

    foreach ($key in $Updates.Keys) {
        if (-not $seen.ContainsKey($key)) {
            $lines.Add("$key=$($Updates[$key])")
        }
    }

    Set-Content -Path $Path -Value $lines -Encoding UTF8
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

function Show-ComposeDiagnostics {
    param([string[]]$Services)

    Write-Host ""
    Write-Host "Docker Compose status:" -ForegroundColor Yellow
    & docker compose ps @Services

    foreach ($service in $Services) {
        Write-Host ""
        Write-Host "Recent logs for ${service}:" -ForegroundColor Yellow
        & docker compose logs --tail 80 $service
    }
}

Push-Location $RepoRoot
try {
    Write-Step "Checking prerequisites"
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker CLI was not found. Install/start Docker Desktop first."
    }

    Invoke-Checked docker info | Out-Null

    if (-not (Test-Path $EnvPath)) {
        if (-not (Test-Path $EnvExamplePath)) {
            throw ".env is missing and .env.example was not found."
        }

        Copy-Item $EnvExamplePath $EnvPath
        Write-Host "Created .env from .env.example"
    }

    if (-not $NoEnvUpdate) {
        Write-Step "Applying OneNote-only local defaults to .env"
        Set-DotEnvValues -Path $EnvPath -Updates @{
            SHAREPOINT_GRAPH_MODE          = "mock"
            ONENOTE_GRAPH_MODE             = "live"
            ONENOTE_AUTH_MODE              = "device_code"
            GRAPH_ONENOTE_SCOPES           = "Notes.Read"
            GRAPH_ONENOTE_SCOPE_MODE       = "me"
            GRAPH_ONENOTE_SITE_HOSTNAME    = ""
            GRAPH_ONENOTE_SITE_SCOPE       = ""
            RETRIEVAL_PROVIDER             = "qdrant"
            RETRIEVAL_VECTOR_COLLECTIONS   = "onenote_chunks"
            AUTH_DEFAULT_ACL_TAGS          = "public,employees"
        }
    }

    $envValues = Read-DotEnv $EnvPath
    $onenoteGraphMode = Get-Setting $envValues "ONENOTE_GRAPH_MODE" "mock"
    $tenantId = Get-Setting $envValues "GRAPH_ONENOTE_TENANT_ID"
    $clientId = Get-Setting $envValues "GRAPH_ONENOTE_CLIENT_ID"
    $postgresUser = Get-Setting $envValues "POSTGRES_USER" "cloudrag"
    $postgresDb = Get-Setting $envValues "POSTGRES_DB" "cloudrag"

    if (-not $SkipSync -and $onenoteGraphMode -eq "live" -and (-not $tenantId -or -not $clientId)) {
        throw "Set GRAPH_ONENOTE_TENANT_ID and GRAPH_ONENOTE_CLIENT_ID in .env before running live OneNote sync."
    }

    $ragApiPort = Get-Setting $envValues "RAG_API_PORT" "8080"
    $openWebUiPort = Get-Setting $envValues "OPENWEBUI_PORT" "3000"
    $ragApiUrl = "http://localhost:$ragApiPort"
    $openWebUiUrl = "http://localhost:$openWebUiPort"

    Write-Step "Starting PostgreSQL, Redis, and Qdrant"
    Invoke-Checked docker compose up -d postgres redis qdrant

    Write-Step "Verifying PostgreSQL"
    Invoke-Checked docker compose exec -T postgres psql -U $postgresUser -d $postgresDb -c "select current_user, current_database();"

    if (-not $SkipSync) {
        $syncJob = if ($Bootstrap) { "onenote_bootstrap" } else { "onenote_incremental" }
        Write-Step "Running OneNote $syncJob"

        $syncArgs = @("compose", "run", "--rm")
        if ($Build) {
            $syncArgs += "--build"
        }
        $syncArgs += @("sync-worker", "python", "-m", "sync_worker.jobs.$syncJob")

        Invoke-Checked docker @syncArgs

        Write-Step "Checking indexed OneNote chunks"
        Invoke-Checked docker compose exec -T postgres psql -U $postgresUser -d $postgresDb -c "select count(*) as onenote_chunks from chunk_documents where source_system='onenote';"
    }

    if (-not $SkipOpsWorker) {
        Write-Step "Starting background sync worker"
        $workerArgs = @("compose", "up", "-d", "--force-recreate")
        if ($Build) {
            $workerArgs += "--build"
        }
        $workerArgs += "sync-worker"
        Invoke-Checked docker @workerArgs
    }

    Write-Step "Starting RAG API"
    $apiArgs = @("compose", "up", "-d", "--force-recreate")
    if ($Build) {
        $apiArgs += "--build"
    }
    $apiArgs += "rag-api"
    Invoke-Checked docker @apiArgs

    Wait-Http -Url "$ragApiUrl/health" -TimeoutSeconds $HealthTimeoutSeconds
    Wait-Http -Url "$ragApiUrl/ready" -TimeoutSeconds $HealthTimeoutSeconds

    if (-not $SkipOpenWebUI) {
        Write-Step "Starting Open WebUI"
        Invoke-Checked docker compose up -d --force-recreate openwebui

        Write-Step "Waiting for Open WebUI at $openWebUiUrl"
        try {
            Wait-Http -Url $openWebUiUrl -TimeoutSeconds $OpenWebUITimeoutSeconds
        } catch {
            Show-ComposeDiagnostics -Services @("rag-api", "openwebui")
            throw
        }

        if (-not $NoBrowser) {
            Start-Process $openWebUiUrl
        }
    }

    Write-Step "Ready"
    Write-Host "RAG API:    $ragApiUrl"
    Write-Host "API docs:   $ragApiUrl/docs"
    if (-not $SkipOpenWebUI) {
        Write-Host "Open WebUI: $openWebUiUrl"
    }
    Write-Host ""
    Write-Host "Default run uses incremental sync. For the first real OneNote import, run:"
    Write-Host ".\scripts\start-onenote-stack.ps1 -Build -Bootstrap"
} finally {
    Pop-Location
}
