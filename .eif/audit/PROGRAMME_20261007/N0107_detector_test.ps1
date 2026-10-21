# N-0107 (RUN-20261008-N0107-IMPL) test of the port-7844 detector in scripts/cip-supervisor.ps1. Audit helper,
# not product. Loads the detector functions (and, for the decision test, Invoke-Tunnel with its state helpers)
# from the script by AST without running its main loop, then checks them on log lines.
#   Blocked lines: recorded 2026-10-08 from this PC's cloudflared tunnel.err.log (network drops TCP 7844).
#   Registered lines: written in cloudflared's INF line format; no registered line was available on this PC.
$src = Join-Path $PSScriptRoot '..\..\..\scripts\cip-supervisor.ps1'
$tokens = $null; $errs = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $src).Path, [ref]$tokens, [ref]$errs)
"parse errors: $($errs.Count)"
if ($errs.Count -gt 0) { $errs | ForEach-Object { $_.ToString() }; exit 2 }
$load = @('Read-LogTail', 'Get-TunnelNetworkVerdict', 'Get-TunnelErrLogPath', 'Invoke-Tunnel', 'Set-State', 'Set-Healthy',
          'Test-InGrace', 'Test-MayStart', 'Get-RecentLaunches', 'New-Component', 'Format-Time', 'Get-LinkHtml')
foreach ($name in $load) {
    $fn = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name }, $true)
    if (-not $fn) { "MISSING function $name"; exit 2 }
    . ([scriptblock]::Create($fn.Extent.Text))
}

$fail = 0
function Check { param([string]$Label, $Actual, $Expected)
    $ok = ("$Actual" -eq "$Expected")
    if (-not $ok) { $script:fail++ }
    "{0} {1} -> {2} (expected {3})" -f ($(if ($ok) { 'PASS' } else { 'FAIL' })), $Label, $Actual, $Expected
}

# ---------------------------------------------------------------- recorded / sample lines
$blocked = @(
    '2026-10-08T07:38:03Z INF Requesting new quick Tunnel on trycloudflare.com...'
    '2026-10-08T07:38:08Z INF Version 2026.9.1 (Checksum 2837888cc0f5d58f15b6dc478376de90b4d3ba5241c7947455d1e0a0df429712)'
    '2026-10-08T07:38:08Z INF GOOS: windows, GOVersion: go1.26.8, GoArch: amd64'
    '2026-10-08T07:38:24Z ERR Unable to establish connection with Cloudflare edge error="DialContext error: dial tcp 198.41.192.67:7844: i/o timeout" connIndex=0 event=0 ip=198.41.192.67'
    '2026-10-08T07:38:24Z ERR Serve tunnel error error="DialContext error: dial tcp 198.41.192.67:7844: i/o timeout" connIndex=0 event=0 ip=198.41.192.67'
    '2026-10-08T07:38:24Z INF Retrying connection in up to 2s connIndex=0 event=0 ip=198.41.192.67'
    '2026-10-08T07:38:41Z ERR Unable to establish connection with Cloudflare edge error="DialContext error: dial tcp 198.41.200.113:7844: i/o timeout" connIndex=0 event=0 ip=198.41.200.113'
    '2026-10-08T07:38:41Z ERR Serve tunnel error error="DialContext error: dial tcp 198.41.200.113:7844: i/o timeout" connIndex=0 event=0 ip=198.41.200.113'
    '2026-10-08T07:38:41Z INF Retrying connection in up to 4s connIndex=0 event=0 ip=198.41.200.113'
    '2026-10-08T07:38:57Z ERR Unable to establish connection with Cloudflare edge error="DialContext error: dial tcp 198.41.192.47:7844: i/o timeout" connIndex=0 event=0 ip=198.41.192.47'
    '2026-10-08T07:38:57Z ERR Serve tunnel error error="DialContext error: dial tcp 198.41.192.47:7844: i/o timeout" connIndex=0 event=0 ip=198.41.192.47'
    '2026-10-08T07:38:57Z INF Retrying connection in up to 8s connIndex=0 event=0 ip=198.41.192.47'
    '2026-10-08T07:39:17Z ERR Unable to establish connection with Cloudflare edge error="DialContext error: dial tcp 198.41.192.107:7844: i/o timeout" connIndex=0 event=0 ip=198.41.192.107'
    '2026-10-08T07:39:17Z ERR Serve tunnel error error="DialContext error: dial tcp 198.41.192.107:7844: i/o timeout" connIndex=0 event=0 ip=198.41.192.107'
)
$registered = @(
    '2026-10-07T16:32:05Z INF Requesting new quick Tunnel on trycloudflare.com...'
    '2026-10-07T16:32:09Z INF Version 2026.9.1 (Checksum 2837888cc0f5d58f15b6dc478376de90b4d3ba5241c7947455d1e0a0df429712)'
    '2026-10-07T16:32:10Z INF Registered tunnel connection connIndex=0 connection=0f1e2d3c-4b5a-6978-8091-a2b3c4d5e6f7 event=0 ip=198.41.200.13 location=lhr16 protocol=http2'
    '2026-10-07T16:32:11Z INF Registered tunnel connection connIndex=1 connection=1f1e2d3c-4b5a-6978-8091-a2b3c4d5e6f7 event=0 ip=198.41.192.67 location=man01 protocol=http2'
)
$threshold = 6

Check 'blocked sample (recorded, 8 timeout lines)' (Get-TunnelNetworkVerdict $blocked $threshold) 'port-blocked'
Check 'registered sample' (Get-TunnelNetworkVerdict $registered $threshold) 'connected'
Check 'mixed: 3 timeout lines then registered' (Get-TunnelNetworkVerdict (@($blocked[0..6]) + $registered) $threshold) 'connected'
Check 'mixed: registered then 8 timeout lines (network lost after connect)' (Get-TunnelNetworkVerdict ($registered + $blocked) $threshold) 'port-blocked'
Check 'mixed: registered then 4 timeout lines (below threshold)' (Get-TunnelNetworkVerdict ($registered + @($blocked[3..8])) $threshold) 'connected'
Check 'below threshold, never registered (5 timeout lines)' (Get-TunnelNetworkVerdict @($blocked[0..9]) $threshold) 'unknown'
Check 'exactly threshold (6 timeout lines)' (Get-TunnelNetworkVerdict @($blocked[0..10]) $threshold) 'port-blocked'
Check 'empty input' (Get-TunnelNetworkVerdict @() $threshold) 'unknown'
$other = @($blocked | ForEach-Object { $_.Replace(':7844: i/o timeout', ':443: i/o timeout') })
Check 'timeouts on another port are not counted' (Get-TunnelNetworkVerdict $other $threshold) 'unknown'
$refused = @($blocked | ForEach-Object { $_.Replace('i/o timeout', 'connectex: No connection could be made because the target machine actively refused it.') })
Check 'refused (not timeout) is not counted' (Get-TunnelNetworkVerdict $refused $threshold) 'unknown'

# ---------------------------------------------------------------- Read-LogTail
$tmp = Join-Path $env:TEMP ('n0107_test_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmp | Out-Null
$enc = New-Object System.Text.UTF8Encoding($false)
$f1 = Join-Path $tmp 'tunnel.err.log'
[System.IO.File]::WriteAllText($f1, (($registered + $blocked) -join "`n") + "`n", $enc)
Check 'tail of whole small file = all lines + trailing empty' (@(Read-LogTail $f1 65536).Count) ($registered.Count + $blocked.Count + 1)
Check 'file verdict (registered then blocked)' (Get-TunnelNetworkVerdict @(Read-LogTail $f1 65536) $threshold) 'port-blocked'

# A registered line far back, beyond the tail window, followed by many timeouts: the tail sees only timeouts.
$big = New-Object System.Collections.ArrayList
[void]$big.AddRange($registered)
foreach ($i in 1..400) { [void]$big.AddRange(@($blocked[3..5])) }
[System.IO.File]::WriteAllText($f1, ($big -join "`r`n") + "`r`n", $enc)
$tail = @(Read-LogTail $f1 4096)
Check 'bounded tail: size of returned text <= 4096 bytes' ([bool](($enc.GetByteCount(($tail -join "`n"))) -le 4096)) $true
Check 'bounded tail: first partial line dropped (every line starts with the date)' (@($tail | Where-Object { $_ -and -not $_.StartsWith('2026-10-08T') }).Count) 0
Check 'bounded tail: CR stripped' (@($tail | Where-Object { $_.EndsWith("`r") }).Count) 0
Check 'bounded tail verdict' (Get-TunnelNetworkVerdict $tail $threshold) 'port-blocked'

# Read while another handle holds the file open for writing (as cloudflared does).
$writer = New-Object System.IO.FileStream($f1, [System.IO.FileMode]::Append, [System.IO.FileAccess]::Write, [System.IO.FileShare]::Read)
$bytes = $enc.GetBytes($registered[2] + "`n")
$writer.Write($bytes, 0, $bytes.Length); $writer.Flush()
Check 'readable while a writer holds it (sees the appended registered line)' (Get-TunnelNetworkVerdict @(Read-LogTail $f1 4096) $threshold) 'connected'
$writer.Dispose()
Check 'missing file -> no lines' (@(Read-LogTail (Join-Path $tmp 'nope.err.log') 4096).Count) 0
Check 'null path -> no lines' (@(Read-LogTail $null 4096).Count) 0

# ---------------------------------------------------------------- Get-TunnelErrLogPath
$logDir = $tmp
[System.IO.File]::WriteAllText((Join-Path $tmp 'tunnel.err.log.1'), 'old', $enc)
(Get-Item (Join-Path $tmp 'tunnel.err.log.1')).LastWriteTime = (Get-Date).AddMinutes(5)
$f2 = Join-Path $tmp 'tunnel-20261008-090000.err.log'
[System.IO.File]::WriteAllText($f2, 'dated', $enc)
(Get-Item $f2).LastWriteTime = (Get-Date).AddMinutes(1)
$comp = @{ ErrLog = 'X:\own.err.log'; Adopted = $false }
Check 'launched by this supervisor -> own err log' (Get-TunnelErrLogPath $comp) 'X:\own.err.log'
$comp.Adopted = $true
Check 'adopted -> newest tunnel*.err.log (rotated .1 ignored)' (Split-Path -Leaf (Get-TunnelErrLogPath $comp)) 'tunnel-20261008-090000.err.log'

# ---------------------------------------------------------------- Invoke-Tunnel decisions (stubbed I/O)
$CycleSeconds = 30; $Delays = @(0, 30, 60, 120, 300); $FlapLimit = 5; $TunnelDeadMinutes = 10
$PublicEverySec = 300; $PublicFirstDelay = 60; $MetricsPort = 20241
$TunnelBlockedDialErrors = 6; $TunnelBlockedRetryMinutes = 30; $TunnelLogTailBytes = 65536
$script:logLines = New-Object System.Collections.ArrayList
$script:stops = New-Object System.Collections.ArrayList
$script:readyCode = 503
function Write-Log { param([string]$Message) [void]$script:logLines.Add($Message) }
function Get-AuthOpenEvidence { return $null }
function Test-CompAlive { param($Comp) return $true }
function Clear-Process { param($Comp) }
function Get-HttpStatus { param([string]$Url, [int]$TimeoutSec = 5, [switch]$UseSystemProxy) return $script:readyCode }
function Update-Hostname { param([int]$Port) }
function Invoke-PublicCheck { }
function Stop-QuickTunnels { param([string]$Why) [void]$script:stops.Add($Why) }
function Get-TunnelGate { return 'test gate (no cloudflared launched)' }
function Reset-World {
    $script:Components = [ordered]@{ tunnel = (New-Component 'tunnel' 1 60) }
    $script:Components.tunnel.Pid = 1234; $script:Components.tunnel.ErrLog = $f1
    $script:tunnel = @{
        Hostname = 'a-b-c.trycloudflare.com'; HostnameSince = (Get-Date)
        LastReadyOk = (Get-Date).AddMinutes(-11); LastPublicOk = (Get-Date); LastPublicCheck = $null; PublicEverOk = $false
        PublicLogin = 530; PublicMe = 530; ClosedReason = $null; FirstPublicAfter = $null
        BlockedReason = $null; BlockedSince = $null; BlockedRetryAt = $null
    }
    $script:stops.Clear()
}
$Components = $null; $tunnel = $null

[System.IO.File]::WriteAllText($f1, ($blocked -join "`n") + "`n", $enc)
Reset-World; $script:readyCode = 503
Invoke-Tunnel @()
Check 'blocked log + /ready 503 for 11 min: state' $Components.tunnel.State 'blocked'
Check 'blocked: no restart' $stops.Count 0
Check 'blocked: detail reason' ($Components.tunnel.Detail.StartsWith('network blocks tunnel port 7844 (outbound TCP); not restarting')) $true
Check 'blocked: retry at ~30 min' ([int][Math]::Round(($tunnel.BlockedRetryAt - $tunnel.BlockedSince).TotalMinutes)) 30
foreach ($i in 1..3) { Invoke-Tunnel @() }
Check 'blocked: 3 more cycles, still no restart' $stops.Count 0
$tunnel.BlockedRetryAt = (Get-Date).AddSeconds(-1)
Invoke-Tunnel @()
Check 'blocked 30 min: one fresh attempt (stop called once)' $stops.Count 1
Check 'blocked 30 min: reason' ($stops[0]) 'port 7844 blocked for 30 min; one fresh attempt'
Check 'blocked 30 min: proceeds to the launch gate' $Components.tunnel.State 'gated'
Check 'blocked episode kept (since unchanged)' ([bool]$tunnel.BlockedSince) $true

Reset-World; $script:readyCode = 503
Invoke-Tunnel @()
$script:readyCode = 200
Invoke-Tunnel @()
Check '/ready 200 ends the episode: state' $Components.tunnel.State 'healthy'
Check '/ready 200 ends the episode: BlockedSince cleared' ([bool]$tunnel.BlockedSince) $false
Check '/ready 200 ends the episode: no restart' $stops.Count 0

# Unchanged behaviour: a log without 7844 timeouts and /ready failing for 11 min still restarts.
[System.IO.File]::WriteAllText($f1, ($other -join "`n") + "`n", $enc)
Reset-World; $script:readyCode = 503
Invoke-Tunnel @()
Check 'no 7844 timeouts + /ready stale 11 min: restart (old rule)' ($stops -join '|') '/ready failing for 10 min'
Reset-World; $script:readyCode = 503; $tunnel.LastReadyOk = (Get-Date).AddMinutes(-2)
Invoke-Tunnel @()
Check 'no 7844 timeouts + /ready failing 2 min: unhealthy, no restart' ("{0}/{1}" -f $Components.tunnel.State, $stops.Count) 'unhealthy/0'

# ---------------------------------------------------------------- link.html shows the reason
function New-FakeStatus { param($Reason, [string]$TunnelState)
    [ordered]@{
        supervisor = [ordered]@{ heartbeat = '2026-10-08T10:00:00.000+02:00'; heartbeat_unix_ms = 0; pid = 1 }
        link = [ordered]@{ url = 'https://a-b-c.trycloudflare.com'; closed_reason = $null; public_login = 530; public_auth_me = 530
                           blocked_reason = $Reason; blocked_since = '2026-10-08T09:57:30'; next_fresh_attempt = '2026-10-08T10:27:30' }
        components = [ordered]@{ tunnel = [ordered]@{ state = $TunnelState; pid = 1; adopted = $false; launches = 1; detail = 'x' } }
    }
}
$html = Get-LinkHtml (New-FakeStatus 'network blocks tunnel port 7844 (outbound TCP)' 'blocked')
Check 'link.html: blocked note shown' ($html.Contains("<div class='blocked'>") -and $html.Contains('network blocks tunnel port 7844 (outbound TCP)') -and $html.Contains('next fresh attempt 2026-10-08T10:27:30')) $true
Check 'link.html: blocked row styled warn' ($html.Contains("<td class='warn'>blocked</td>")) $true
$html = Get-LinkHtml (New-FakeStatus $null 'healthy')
Check 'link.html: no note when not blocked' ($html.Contains("<div class='blocked'>")) $false

Remove-Item -Recurse -Force $tmp
"failures: $fail"
if ($fail -gt 0) { exit 1 } else { exit 0 }
