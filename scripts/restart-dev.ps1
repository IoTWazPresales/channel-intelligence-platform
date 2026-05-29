# Restart local CIP dev stack: kill stale processes, then Redis (WSL) + worker + API + web.
# Usage: .\scripts\restart-dev.ps1

$ErrorActionPreference = 'Continue'

. (Join-Path $PSScriptRoot 'stop-dev.ps1')
Stop-CipDevProcesses

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

Start-Process powershell.exe -ArgumentList @(
    '-NoExit', '-Command',
    "wsl -d Ubuntu -- bash -lc 'sudo service redis-server start; redis-cli ping; exec bash'"
)

Start-Process powershell.exe -ArgumentList @(
    '-NoExit', '-Command',
    "cd `"$repo`"; while (-not (Test-NetConnection 127.0.0.1 -Port 6379 -InformationLevel Quiet)) { Write-Host 'Waiting for Redis...'; Start-Sleep -Seconds 2 }; pnpm dev:worker"
)

Start-Process powershell.exe -ArgumentList @(
    '-NoExit', '-Command',
    "cd `"$repo`"; pnpm dev:api"
)

Start-Process powershell.exe -ArgumentList @(
    '-NoExit', '-Command',
    "cd `"$repo`"; pnpm dev:web"
)

Write-Host "Dev stack starting in separate windows (Redis WSL, worker, API :8001, web :3000)..." -ForegroundColor Green
