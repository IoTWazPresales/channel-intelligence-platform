# Restart local CIP dev stack: kill stale processes, then Redis (WSL) + worker + API + web.
# Spawned window PIDs are written to .cip-dev-pids/ so stop-dev.ps1 can kill them precisely.
# Usage: .\scripts\restart-dev.ps1
# Local Windows only — does not use Docker. Redis must be reachable at 127.0.0.1:6379 from Windows
# (WSL redis-server with localhost forwarding, or native Redis).

$ErrorActionPreference = 'Continue'

. (Join-Path $PSScriptRoot 'stop-dev.ps1')
Stop-CipDevProcesses

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pidDir = Join-Path $repo '.cip-dev-pids'

# Ensure PID directory exists and is clean for this session.
if (-not (Test-Path $pidDir)) {
    New-Item -ItemType Directory -Path $pidDir -Force | Out-Null
}
Remove-Item -Path (Join-Path $pidDir '*.pid') -Force -ErrorAction SilentlyContinue

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
    param([string]$Title, [string]$Command, [string]$PidFile)
    $proc = Start-Process powershell.exe -ArgumentList @(
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
    ) -PassThru

    if ($proc -and $proc.Id -and $PidFile) {
        Set-Content -Path $PidFile -Value $proc.Id -Encoding UTF8
        Write-Host "  Spawned '$Title' window PID $($proc.Id) → $PidFile" -ForegroundColor DarkGray
    }
    return $proc
}

Start-DevWindow -Title 'CIP Worker' -Command 'pnpm dev:worker' -PidFile (Join-Path $pidDir 'worker-window.pid')
Start-Sleep -Seconds 2
Start-DevWindow -Title 'CIP API :8001' -Command 'pnpm dev:api' -PidFile (Join-Path $pidDir 'api-window.pid')
Start-Sleep -Seconds 1
Start-DevWindow -Title 'CIP Web :3000' -Command 'pnpm dev:web' -PidFile (Join-Path $pidDir 'web-window.pid')

Write-Host 'Dev stack starting in separate windows (Redis WSL, worker, API :8001, web :3000).' -ForegroundColor Green
Write-Host "Redis helper PID: $($redisWindow.Id)" -ForegroundColor DarkGray
Write-Host "PID files in: $pidDir" -ForegroundColor DarkGray
Write-Host "Run .\scripts\stop-dev.ps1 to cleanly stop all services." -ForegroundColor DarkGray
