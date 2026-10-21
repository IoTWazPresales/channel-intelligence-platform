# GOV-008 (RUN-20261007-N0073-VER) kill-and-time probe. Audit helper, not product.
# Kills one PID and polls status.json every 2 s until the named component is healthy under a new PID.
param([Parameter(Mandatory)][string]$Component, [Parameter(Mandatory)][int]$KillPid, [int]$TimeoutSec = 240)
$statusFile = Join-Path $env:LOCALAPPDATA 'CIP\always-on\status.json'
function Read-Status { try { return (Get-Content $statusFile -Raw | ConvertFrom-Json) } catch { return $null } }
$before = Read-Status
"before: $Component state=$($before.components.$Component.state) pid=$($before.components.$Component.pid) launches=$($before.components.$Component.launches)"
$p = Get-Process -Id $KillPid -ErrorAction SilentlyContinue
if (-not $p) { "pid $KillPid not running; abort"; exit 2 }
"killing pid $KillPid ($($p.ProcessName))"
$t0 = Get-Date
Stop-Process -Id $KillPid -Force
"killed at $($t0.ToString('HH:mm:ss.fff'))"
$seen = @{}
while (((Get-Date) - $t0).TotalSeconds -lt $TimeoutSec) {
    Start-Sleep -Seconds 2
    $s = Read-Status
    if (-not $s) { continue }
    $c = $s.components.$Component
    $key = "$($c.state)|$($c.pid)"
    if (-not $seen.ContainsKey($key)) {
        $seen[$key] = 1
        "{0} +{1,5:N1}s state={2} pid={3} launches={4} detail={5}" -f (Get-Date -Format 'HH:mm:ss'), ((Get-Date) - $t0).TotalSeconds, $c.state, $c.pid, $c.launches, $c.detail
    }
    if ($c.state -eq 'healthy' -and [string]$c.pid -ne [string]$KillPid -and $c.pid) {
        "RECOVERED in {0:N1}s (new pid {1})" -f ((Get-Date) - $t0).TotalSeconds, $c.pid
        exit 0
    }
}
"NOT RECOVERED within $TimeoutSec s"
exit 1
