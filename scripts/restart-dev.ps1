# Restart local CIP dev stack: kill stale processes, then Redis (WSL) + worker + API + web.
# Usage: .\scripts\restart-dev.ps1
# Local Windows only — does not use Docker. Redis must be reachable at 127.0.0.1:6379 from Windows
# (WSL redis-server with localhost forwarding, or native Redis).

$ErrorActionPreference = 'Continue'

. (Join-Path $PSScriptRoot 'stop-dev.ps1')
Stop-CipDevProcesses

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Wait-RedisWindows {
    param([int]$MaxSeconds = 90)
    $deadline = (Get-Date).AddSeconds($MaxSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-NetConnection -ComputerName 127.0.0.1 -Port 6379 -InformationLevel Quiet -WarningAction SilentlyContinue) {
            return $true
        }
        Start-Sleep -Seconds 2
    }
    return $false
}

$redisWindow = Start-Process powershell.exe -ArgumentList @(
    '-NoExit', '-Command',
    @"
`$ErrorActionPreference = 'Continue'
Write-Host 'Starting Redis in WSL (Ubuntu)...' -ForegroundColor Cyan
wsl -d Ubuntu -- bash -lc 'sudo service redis-server start 2>/dev/null; redis-cli ping'
Write-Host 'Redis window — leave open while developing.' -ForegroundColor Green
"@
) -PassThru

Write-Host 'Waiting for Redis on 127.0.0.1:6379 (Windows)...' -ForegroundColor DarkGray
if (-not (Wait-RedisWindows)) {
    Write-Host 'WARNING: Redis not reachable on localhost:6379 from Windows.' -ForegroundColor Yellow
    Write-Host '  Celery PM validate/commit will queue until Redis is up.' -ForegroundColor Yellow
    Write-Host '  Or set CIP_DEV_CELERY_DISPATCH=in_process_thread in apps/api/.env (dev only).' -ForegroundColor Yellow
}

function Start-DevWindow {
    param([string]$Title, [string]$Command)
    Start-Process powershell.exe -ArgumentList @(
        '-NoExit', '-Command',
        @"
`$host.ui.RawUI.WindowTitle = '$Title'
`$ErrorActionPreference = 'Continue'
try {
  Set-Location '$repo'
  $Command
} catch {
  Write-Host "ERROR: `$_" -ForegroundColor Red
}
Write-Host ''
Write-Host 'Press Enter to close this window...' -ForegroundColor DarkGray
Read-Host
"@
    )
}

Start-DevWindow -Title 'CIP Worker' -Command 'pnpm dev:worker'
Start-Sleep -Seconds 2
Start-DevWindow -Title 'CIP API :8001' -Command 'pnpm dev:api'
Start-Sleep -Seconds 1
Start-DevWindow -Title 'CIP Web :3000' -Command 'pnpm dev:web'

Write-Host 'Dev stack starting in separate windows (Redis WSL, worker, API :8001, web :3000).' -ForegroundColor Green
Write-Host "Redis helper PID: $($redisWindow.Id)" -ForegroundColor DarkGray
