<#
.SYNOPSIS
    Force an incremental OneNote sync (only changed pages).

.DESCRIPTION
    Runs a single incremental sync pass: it asks OneNote for pages modified since
    the last sync (using the stored timestamp checkpoint) and re-indexes only
    those, plus removes pages that were deleted. It does NOT re-pull everything,
    so it is fast and light on Microsoft Graph.

    Use this for routine "I edited a few pages" updates.

    Caveat: incremental relies on OneNote's lastModified timestamp, which OneNote
    does not always advance on an edit (especially edits made in the desktop app).
    If an edit does not show up after this, run a full bootstrap instead, which
    compares the actual content hash and reliably catches it:
        .\scripts\force-sync.ps1

    Tip: edit on onenote.com (server-side) so the timestamp advances immediately.

.EXAMPLE
    .\scripts\force-incremental-sync.ps1
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

    Write-Host "==> Running incremental OneNote sync (changed pages only)..." -ForegroundColor Cyan
    & docker compose run --rm sync-worker python -m sync_worker.jobs.onenote_incremental
    if ($LASTEXITCODE -ne 0) {
        throw "Incremental sync failed with exit code $LASTEXITCODE."
    }

    Write-Host ""
    Write-Host "==> Done. Only changed pages were re-indexed." -ForegroundColor Green
    Write-Host "If an edit did not appear, run a full sync: .\scripts\force-sync.ps1" -ForegroundColor DarkGray
} finally {
    Pop-Location
}
