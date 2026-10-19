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

Step '2. database names (passwords never printed)'
foreach ($n in 'DATABASE_URL', 'DATABASE_URL_SYNC', 'DATABASE_URL_SYNC_MIGRATE') {
    $v = [Environment]::GetEnvironmentVariable($n)
    if ($v) { Write-Host ("{0} -> {1}" -f $n, ($v -replace '://[^@]*@', '://***@')) } else { Write-Host "$n not set in this shell (the app .env is used)" }
}

Step '3. migration state: cip and cip_test must both be at 20261019_0044'
Push-Location $api
& $py -m alembic current
$sync = $env:DATABASE_URL_SYNC
if ($sync) {
    $env:DATABASE_URL_SYNC = ($sync -replace '/cip(\?|$)', '/cip_test$1')
    Write-Host '-- cip_test --'
    & $py -m alembic current
    $env:DATABASE_URL_SYNC = $sync
} else { Write-Host 'DATABASE_URL_SYNC not set: set it, then re-run, to check cip_test too.' }
Step '4. saved layouts and how each is treated (read only, cip)'
& $py scripts\n0111_print_layouts.py
Pop-Location

if (-not $SkipTests) {
    Step '5. full API pytest on cip_test'
    $saveA = $env:DATABASE_URL; $saveS = $env:DATABASE_URL_SYNC
    if ($env:DATABASE_URL)      { $env:DATABASE_URL      = ($env:DATABASE_URL -replace '/cip(\?|$)', '/cip_test$1') }
    if ($env:DATABASE_URL_SYNC) { $env:DATABASE_URL_SYNC = ($env:DATABASE_URL_SYNC -replace '/cip(\?|$)', '/cip_test$1') }
    Write-Host "tests use: $($env:DATABASE_URL_SYNC -replace '://[^@]*@', '://***@')"
    Push-Location $api
    & $py -m pytest tests -q -p no:cacheprovider 2>&1 | Select-Object -Last 40
    Pop-Location
    $env:DATABASE_URL = $saveA; $env:DATABASE_URL_SYNC = $saveS

    Step '6. full web: typecheck and vitest (2 workers)'
    pnpm --filter "@cip/web" typecheck
    Push-Location (Join-Path $repo 'apps\web')
    pnpm exec vitest run --maxWorkers=2 2>&1 | Select-Object -Last 15
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
