<#
.SYNOPSIS
    Force a full OneNote re-sync (bootstrap).

.DESCRIPTION
    Runs a full bootstrap sync: re-pulls and re-hashes every OneNote page,
    ignoring the incremental "last modified" timestamp cursor. Use this when an
    edit does not show up after a normal (incremental) sync — OneNote does not
    always advance a page's lastModified timestamp, so the incremental sync can
    miss edits. The bootstrap compares the actual content hash, so it reliably
    picks up any real change.

    This is the same operation the admin panel's "Run sync now" button performs.

    Note: the edit must already be saved to Microsoft's cloud. If you edited in
    the OneNote desktop app, sync it first (Shift+F9) or edit on onenote.com.

.EXAMPLE
    .\scripts\force-sync.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $RepoRoot
try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker CLI was not found. Start Docker Desktop first."
    }

    Write-Host "==> Running full OneNote bootstrap sync..." -ForegroundColor Cyan
    & docker compose run --rm sync-worker python -m sync_worker.jobs.onenote_bootstrap
    if ($LASTEXITCODE -ne 0) {
        throw "Bootstrap sync failed with exit code $LASTEXITCODE."
    }

    Write-Host ""
    Write-Host "==> Done. The knowledge base is re-indexed with the latest content." -ForegroundColor Green
} finally {
    Pop-Location
}
