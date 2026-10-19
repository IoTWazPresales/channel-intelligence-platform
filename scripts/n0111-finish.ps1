# N-0111 finish: run from the repo root on Warren's machine, no Claude needed.
#   .\scripts\n0111-finish.ps1             checks, layout print-out, tests
#   .\scripts\n0111-finish.ps1 -Restart    also rebuilds web and restarts web, API and worker (supervisor)
# Writes nothing to cip. Tests run on cip_test only. Output also goes to .eif\audit\n0111_finish.log
param([switch]$Restart, [switch]$SkipTests)
$ErrorActionPreference = 'Continue'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $repo
$log = Join-Path $repo '.eif\audit\n0111_finish.log'
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
Start-Transcript -Path $log -Force | Out-Null

function Step($t) { Write-Host "`n=== $t ===" -ForegroundColor Cyan }
$api = Join-Path $repo 'apps\api'
$py = Join-Path $api '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }

Step '1. start check'
git branch --show-current
git fetch origin
git status --short
git log --oneline -1 HEAD
git log --oneline -1 origin/feat/ns-2-brief-nav-collapse

# Ask the app itself which database URLs it uses (env, apps/api/.env, or its built-in defaults).
Push-Location $api
$urls = & $py -c "from app.core.config import get_settings as g; s=g(); print(s.database_url); print(s.database_url_sync)" 2>$null
Pop-Location
if ($urls -and $urls.Count -ge 2) {
    if (-not $env:DATABASE_URL)      { $env:DATABASE_URL      = $urls[0].Trim() }
    if (-not $env:DATABASE_URL_SYNC) { $env:DATABASE_URL_SYNC = $urls[1].Trim() }
}

Step '2. database names (passwords never printed)'
foreach ($n in 'DATABASE_URL', 'DATABASE_URL_SYNC', 'DATABASE_URL_SYNC_MIGRATE') {
    $v = [Environment]::GetEnvironmentVariable($n)
    if ($v) { Write-Host ("{0} -> {1}" -f $n, ($v -replace '://[^@]*@', '://***@')) } else { Write-Host "$n not set in this shell (the app .env is used)" }
}

Step '3. migrations: bring cip and cip_test to head (20261019_0045 adds two nullable replenishment columns)'
Push-Location $api
& $py -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { Write-Host 'alembic upgrade failed on cip: if it says "must be owner", set DATABASE_URL_SYNC_MIGRATE to the postgres owner URL and re-run.' }
& $py -m alembic current
$sync = $env:DATABASE_URL_SYNC
$mig = $env:DATABASE_URL_SYNC_MIGRATE
if ($sync) {
    $env:DATABASE_URL_SYNC = ($sync -replace '/cip(\?|$)', '/cip_test$1')
    if ($mig) { $env:DATABASE_URL_SYNC_MIGRATE = ($mig -replace '/cip(\?|$)', '/cip_test$1') }
    Write-Host '-- cip_test --'
    & $py -m alembic upgrade head
    & $py -m alembic current
    $env:DATABASE_URL_SYNC = $sync
    if ($mig) { $env:DATABASE_URL_SYNC_MIGRATE = $mig }
} else { Write-Host 'DATABASE_URL_SYNC not set: set it, then re-run, to migrate cip_test too.' }
Step '4. saved layouts and how each is treated (read only, cip)'
& $py scripts\n0111_print_layouts.py
Pop-Location

if (-not $SkipTests) {
    Step '5. full API pytest on cip_test'
    $saveA = $env:DATABASE_URL; $saveS = $env:DATABASE_URL_SYNC
    if ($env:DATABASE_URL)      { $env:DATABASE_URL      = ($env:DATABASE_URL -replace '/cip(\?|$)', '/cip_test$1') }
    if ($env:DATABASE_URL_SYNC) { $env:DATABASE_URL_SYNC = ($env:DATABASE_URL_SYNC -replace '/cip(\?|$)', '/cip_test$1') }
    Write-Host "tests use: $($env:DATABASE_URL_SYNC -replace '://[^@]*@', '://***@')"
    if (($env:DATABASE_URL_SYNC -notmatch '/cip_test(\?|$)') -or ($env:DATABASE_URL -notmatch '/cip_test(\?|$)')) {
        Write-Host 'ABORT: the API tests would not run on cip_test (DATABASE_URL / DATABASE_URL_SYNC not found or not ending /cip). Skipping them.' -ForegroundColor Red
    } else {
        Push-Location $api
        & $py -m pytest tests -q -p no:cacheprovider 2>&1 | Select-Object -Last 40
        Pop-Location
    }
    $env:DATABASE_URL = $saveA; $env:DATABASE_URL_SYNC = $saveS

    Step '6. full web: typecheck and vitest'
    pnpm --filter "@cip/web" typecheck
    Push-Location (Join-Path $repo 'apps\web')
    pnpm exec vitest run 2>&1 | Select-Object -Last 15
    Pop-Location
}

if ($Restart) {
    Step '7. rebuild web, then restart web, API and worker through the supervisor'
    pnpm --filter "@cip/web" build
    foreach ($c in 'worker', 'api', 'web') { & (Join-Path $PSScriptRoot 'cip-supervisor-stop.ps1') -Component $c -Restart; Start-Sleep -Seconds 3 }
    & (Join-Path $PSScriptRoot 'cip-supervisor-status.ps1')
}

Step 'end check'
git status --short
git log --oneline -1 HEAD
git log --oneline -1 origin/feat/ns-2-brief-nav-collapse
Write-Host "`nLog saved to $log. Still manual: record N-0111 findings in the ledger, commit docs/ledger." -ForegroundColor Yellow
Stop-Transcript | Out-Null
