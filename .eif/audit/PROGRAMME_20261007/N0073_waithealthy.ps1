# N-0073: wait until status.json (from a live supervisor) shows every component healthy; print the time taken.
param([int]$MaxSeconds = 300)
$statusFile = Join-Path $env:LOCALAPPDATA 'CIP\always-on\status.json'
$t0 = Get-Date
$s = $null
while (((Get-Date) - $t0).TotalSeconds -lt $MaxSeconds) {
    try {
        $s = Get-Content $statusFile -Raw | ConvertFrom-Json
        $states = @($s.components.PSObject.Properties | ForEach-Object { $_.Value.state })
        $live = [bool](Get-Process -Id ([int]$s.supervisor.pid) -ErrorAction SilentlyContinue)
        if ($live -and $s.supervisor.state -eq 'running' -and @($states | Where-Object { $_ -ne 'healthy' }).Count -eq 0) {
            "{0} all healthy after {1}s (supervisor pid {2}, cycle {3}, link {4})" -f (Get-Date -Format 'HH:mm:ss'), [int]((Get-Date) - $t0).TotalSeconds, $s.supervisor.pid, $s.supervisor.cycle, $s.link.url
            exit 0
        }
    } catch { }
    Start-Sleep -Seconds 2
}
"NOT all healthy within ${MaxSeconds}s"
if ($s) { foreach ($p in $s.components.PSObject.Properties) { "  {0} {1} {2}" -f $p.Name, $p.Value.state, $p.Value.detail } }
exit 1
