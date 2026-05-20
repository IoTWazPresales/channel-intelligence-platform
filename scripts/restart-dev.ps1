$repo = "C:\Users\warren_eliason\channel-intelligence-platform"

# Kill processes on specific dev ports only
$ports = @(8000, 3000, 6379)
foreach ($port in $ports) {
    $procId = (netstat -ano | findstr ":$port " | findstr "LISTENING" | ForEach-Object { ($_ -split '\s+')[-1] }) | Select-Object -First 1
    if ($procId) {
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        Write-Host "Killed process on port $port (PID $procId)"
    }
}

Start-Sleep -Seconds 2

Start-Process powershell.exe -ArgumentList @(
  "-NoExit", "-Command",
  "wsl -d Ubuntu -- bash -lc 'sudo service redis-server start; redis-cli ping; exec bash'"
)

Start-Process powershell.exe -ArgumentList @(
  "-NoExit", "-Command",
  "cd `"$repo`"; while (-not (Test-NetConnection 127.0.0.1 -Port 6379 -InformationLevel Quiet)) { Write-Host 'Waiting for Redis...'; Start-Sleep -Seconds 2 }; pnpm dev:worker"
)

Start-Process powershell.exe -ArgumentList @(
  "-NoExit", "-Command",
  "cd `"$repo`"; pnpm dev:api"
)

Start-Process powershell.exe -ArgumentList @(
  "-NoExit", "-Command",
  "cd `"$repo`"; pnpm dev:web"
)

Write-Host "Dev stack restarting..."
