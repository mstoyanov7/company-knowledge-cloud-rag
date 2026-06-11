param(
    [string]$Question = "What do my OneNote notes say about onboarding?"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $PSScriptRoot
$EnvPath = Join-Path $RepoRoot ".env"

function Read-DotEnv {
    param([string]$Path)
    $values = @{}
    if (-not (Test-Path $Path)) {
        return $values
    }
    foreach ($line in Get-Content $Path) {
        $trimmed = $line.Trim()
        if ($trimmed -and -not $trimmed.StartsWith("#") -and $trimmed.Contains("=")) {
            $key, $value = $trimmed.Split("=", 2)
            $values[$key.Trim()] = $value.Trim().Trim('"').Trim("'")
        }
    }
    return $values
}

function Get-Setting {
    param([hashtable]$Values, [string]$Key, [string]$Default)
    if ($Values.ContainsKey($Key) -and $Values[$Key]) {
        return $Values[$Key]
    }
    return $Default
}

function Test-HttpEndpoint {
    param([string]$Name, [string]$Url)
    try {
        Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5 | Out-Null
        [pscustomobject]@{ Name = $Name; Url = $Url; Status = "OK" }
    } catch {
        [pscustomobject]@{ Name = $Name; Url = $Url; Status = "FAILED: $($_.Exception.Message)" }
    }
}

Push-Location $RepoRoot
try {
    $envValues = Read-DotEnv $EnvPath
    $ragApiPort = Get-Setting $envValues "RAG_API_PORT" "8080"
    $qdrantPort = Get-Setting $envValues "QDRANT_PORT" "6333"
    $ragApiKey = Get-Setting $envValues "RAG_API_KEY" "cloudrag-rag-key"
    $postgresUser = Get-Setting $envValues "POSTGRES_USER" "cloudrag"
    $postgresDb = Get-Setting $envValues "POSTGRES_DB" "cloudrag"

    Write-Host "Docker Compose services"
    docker compose ps

    Write-Host ""
    Write-Host "HTTP endpoints"
    @(
        Test-HttpEndpoint "RAG API health" "http://localhost:$ragApiPort/health"
        Test-HttpEndpoint "RAG API ready" "http://localhost:$ragApiPort/ready"
        Test-HttpEndpoint "Qdrant" "http://localhost:$qdrantPort/collections"
        Test-HttpEndpoint "Ollama host" "http://localhost:11434/v1/models"
    ) | Format-Table -AutoSize

    Write-Host ""
    Write-Host "RAG API runtime settings"
    $settingsScript = @'
from shared_schemas import AppSettings
s = AppSettings()
print("DEFAULT_LLM_PROVIDER=", s.default_llm_provider)
print("DEFAULT_MODEL_NAME=", s.default_model_name)
print("RETRIEVAL_PROVIDER=", s.retrieval_provider)
print("RETRIEVAL_VECTOR_COLLECTIONS=", s.retrieval_vector_collections)
print("RETRIEVAL_MIN_KEYWORD_OVERLAP=", s.retrieval_min_keyword_overlap)
print("AUTH_DEFAULT_ACL_TAGS=", s.auth_default_acl_tags)
'@
    docker compose exec -T rag-api python -c $settingsScript

    Write-Host ""
    Write-Host "OneNote chunks in PostgreSQL"
    docker compose exec -T postgres psql -U $postgresUser -d $postgresDb -c "select count(*) as onenote_chunks from chunk_documents where source_system='onenote';"

    Write-Host ""
    Write-Host "Direct secured RAG test"
    $body = @{
        question = $Question
        user_context = @{
            tenant_id = "local-tenant"
            acl_tags = @("public", "employees")
        }
        source_filters = @("onenote")
        top_k = 5
    } | ConvertTo-Json -Depth 5
    Invoke-RestMethod -Method Post "http://localhost:$ragApiPort/api/v1/answer" `
        -Headers @{ Authorization = "Bearer $ragApiKey" } `
        -ContentType "application/json" `
        -Body $body | ConvertTo-Json -Depth 8
} finally {
    Pop-Location
}
