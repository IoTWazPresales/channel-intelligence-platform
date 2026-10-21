# N-0073 kill test: kill one component, then time until status.json shows it healthy again after a new launch.
param([Parameter(Mandatory = $true)][string]$Component, [int]$MaxSeconds = 420)
$statusFile = Join-Path $env:LOCALAPPDATA 'CIP\always-on\status.json'
function Read-Status { Get-Content $statusFile -Raw | ConvertFrom-Json }
$s = Read-Status
$before = $s.components.$Component
$t0 = Get-Date
"{0} kill {1}: pid={2} adopted={3} launches={4}" -f $t0.ToString('HH:mm:ss'), $Component, $before.pid, $before.adopted, $before.launches
switch ($Component) {
  'redis'  { wsl -d Ubuntu -u root -- service redis-server stop | Out-Null }
  default  { Stop-Process -Id ([int]$before.pid) -Force }
}
$seenDown = $false
while (((Get-Date) - $t0).TotalSeconds -lt $MaxSeconds) {
  Start-Sleep -Seconds 1
  try { $c = (Read-Status).components.$Component } catch { continue }
  if ($c.state -ne 'healthy') { $seenDown = $true }
  if ($c.state -eq 'healthy' -and $c.launches -gt $before.launches -and $seenDown) {
    $dt = [int]((Get-Date) - $t0).TotalSeconds
    "{0} {1} healthy again after {2}s: pid={3} adopted={4} launches={5} detail={6}" -f (Get-Date).ToString('HH:mm:ss'), $Component, $dt, $c.pid, $c.adopted, $c.launches, $c.detail
    exit 0
  }
}
"{0} {1} NOT healthy within {2}s; last state={3} detail={4}" -f (Get-Date).ToString('HH:mm:ss'), $Component, $MaxSeconds, $c.state, $c.detail
exit 1
