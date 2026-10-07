# Stop or restart the CIP always-on supervisor (N-0073), or one part of the stack it runs.
#
# Usage:
#   .\scripts\cip-supervisor-stop.ps1                        # stop the supervisor, the worker/API/web it started, then the tunnel
#   .\scripts\cip-supervisor-stop.ps1 -Restart               # same, then start a fresh supervisor (new tunnel address)
#   .\scripts\cip-supervisor-stop.ps1 -Component api -Restart  # restart one part now (e.g. the API after a code change)
#   .\scripts\cip-supervisor-stop.ps1 -Component worker      # stop one part and keep it stopped until "-Component worker -Restart"
#
# Redis and the WSL keeper stay up on a full stop. Works by writing stop.flag next to status.json;
# the supervisor picks it up within a second or two.
param(
    [ValidateSet('wsl', 'redis', 'worker', 'api', 'web', 'tunnel')]
    [string]$Component,
    [switch]$Restart
)
$ErrorActionPreference = 'Stop'

$stateDir = Join-Path $env:LOCALAPPDATA 'CIP\always-on'
$pidFile  = Join-Path $stateDir 'supervisor.pid'
$stopFlag = Join-Path $stateDir 'stop.flag'
$supervisor = Join-Path $PSScriptRoot 'cip-supervisor.ps1'

function Get-SupervisorProcess {
    if (-not (Test-Path $pidFile)) { return $null }
    $supPid = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1) -as [int]
    if (-not $supPid) { return $null }
    $p = Get-CimInstance Win32_Process -Filter "ProcessId=$supPid" -ErrorAction SilentlyContinue
    if ($p -and $p.CommandLine -and $p.CommandLine.Contains('cip-supervisor.ps1')) { return $p }
    return $null
}

function Start-Supervisor {
    Start-Process -FilePath 'powershell.exe' -WindowStyle Hidden -ArgumentList @(
        '-NoProfile', '-WindowStyle', 'Hidden', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f $supervisor)
    ) | Out-Null
    Write-Host 'Started a new supervisor (hidden). Status page: %LOCALAPPDATA%\CIP\always-on\link.html'
}

$sup = Get-SupervisorProcess
New-Item -ItemType Directory -Path $stateDir -Force | Out-Null

if (-not $sup) {
    Remove-Item -Path $stopFlag -Force -ErrorAction SilentlyContinue
    if ($Restart -and -not $Component) { Start-Supervisor; exit 0 }
    Write-Host 'The supervisor is not running. Nothing to stop.'
    exit 0
}

$action = 'stop'
if ($Restart) { $action = 'restart' }
$request = @{ action = $action; component = $Component; requested = (Get-Date).ToString('s') } | ConvertTo-Json -Compress
[System.IO.File]::WriteAllText($stopFlag, $request, (New-Object System.Text.UTF8Encoding($false)))

# Wait for the supervisor to take the request.
$deadline = (Get-Date).AddSeconds(30)
while ((Test-Path $stopFlag) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
if (Test-Path $stopFlag) {
    Remove-Item -Path $stopFlag -Force -ErrorAction SilentlyContinue
    throw "The supervisor (pid $($sup.ProcessId)) did not pick up the request within 30 s. Check its log in %LOCALAPPDATA%\CIP\always-on\logs\supervisor.log."
}

if ($Component) {
    if ($Restart) { Write-Host "Asked the supervisor to restart '$Component'. Watch link.html or status.json." }
    else { Write-Host "Stopped '$Component'. It stays stopped until: .\scripts\cip-supervisor-stop.ps1 -Component $Component -Restart" }
    exit 0
}

# Full stop: wait for the supervisor to finish stopping its processes and exit.
$deadline = (Get-Date).AddSeconds(90)
while ((Get-Process -Id $sup.ProcessId -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 1 }
if (Get-Process -Id $sup.ProcessId -ErrorAction SilentlyContinue) {
    Write-Host "Supervisor pid $($sup.ProcessId) did not exit within 90 s; stopping it."
    Stop-Process -Id $sup.ProcessId -Force -ErrorAction SilentlyContinue
}
Write-Host 'Supervisor stopped. Redis and WSL are left running.'
if ($Restart) { Start-Supervisor }
