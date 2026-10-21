# N-0107 GOV-008 verification (RUN-20261008-N0107-VER). Audit helper, not product.
# Independent of N0107_detector_test.ps1: drives Invoke-Tunnel on a simulated clock (stubbed Get-Date, I/O and launch)
# for hours of 30 s cycles and counts launches; checks the re-arm after a fresh launch and after a crash while blocked,
# the precedence of /ready 200 over a stale blocked log, and the unchanged old rule. Loads functions by AST only.
param([switch]$Quiet)
$src = Join-Path $PSScriptRoot '..\..\..\scripts\cip-supervisor.ps1'
$tokens = $null; $errs = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $src).Path, [ref]$tokens, [ref]$errs)
"parse errors: $($errs.Count)"
if ($errs.Count -gt 0) { $errs | ForEach-Object { $_.ToString() }; exit 2 }
foreach ($name in @('Read-LogTail', 'Get-TunnelNetworkVerdict', 'Get-TunnelErrLogPath', 'Invoke-Tunnel', 'Set-State',
                    'Set-Healthy', 'Test-InGrace', 'Test-MayStart', 'Get-RecentLaunches', 'New-Component', 'Format-Time')) {
    $fn = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name }, $true)
    if (-not $fn) { "MISSING function $name"; exit 2 }
    . ([scriptblock]::Create($fn.Extent.Text))
}
# Script constants as the product defines them (read from the script, not retyped).
foreach ($v in @('TunnelBlockedDialErrors', 'TunnelBlockedRetryMinutes', 'TunnelLogTailBytes', 'TunnelDeadMinutes', 'MetricsPort', 'FlapLimit')) {
    $a = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.AssignmentStatementAst] -and
                     $n.Left.Extent.Text -eq ('$' + $v) }, $false)
    if (-not $a) { "MISSING constant $v"; exit 2 }
    Set-Variable -Name $v -Value ([scriptblock]::Create($a.Right.Extent.Text).Invoke()[0])
}
"constants: dial errors $TunnelBlockedDialErrors, retry $TunnelBlockedRetryMinutes min, dead $TunnelDeadMinutes min"

$fail = 0
function Check { param([string]$Label, $Actual, $Expected)
    $ok = ("$Actual" -eq "$Expected")
    if (-not $ok) { $script:fail++ }
    "{0} {1} -> {2} (expected {3})" -f ($(if ($ok) { 'PASS' } else { 'FAIL' })), $Label, $Actual, $Expected
}

# Lines in cloudflared's format; each failed attempt writes 2 timeout lines ('Unable to establish' + 'Serve tunnel error').
function Get-Attempt { param([int]$i)
    $ip = "198.41.192.$i"
    "2026-10-08T08:00:{0:D2}Z ERR Unable to establish connection with Cloudflare edge error=""DialContext error: dial tcp {1}:7844: i/o timeout"" connIndex=0 event=0 ip={1}" -f $i, $ip
    "2026-10-08T08:00:{0:D2}Z ERR Serve tunnel error error=""DialContext error: dial tcp {1}:7844: i/o timeout"" connIndex=0 event=0 ip={1}" -f $i, $ip
    "2026-10-08T08:00:{0:D2}Z INF Retrying connection in up to 2s connIndex=0 event=0 ip={1}" -f $i, $ip
}
$reg = '2026-10-08T08:01:00Z INF Registered tunnel connection connIndex=0 connection=aaaa event=0 ip=198.41.200.13 location=lhr16 protocol=http2'
$two  = @(1..2 | ForEach-Object { Get-Attempt $_ })   # 4 timeout lines
$three = @(1..3 | ForEach-Object { Get-Attempt $_ })  # 6 timeout lines
$ten  = @(1..10 | ForEach-Object { Get-Attempt $_ })  # 20 timeout lines

# ---------------------------------------------------------------- detector edges not in the implementation test
Check 'threshold-1 timeouts (2 attempts) -> unknown' (Get-TunnelNetworkVerdict $two $TunnelBlockedDialErrors) 'unknown'
Check 'threshold timeouts (3 attempts) -> port-blocked' (Get-TunnelNetworkVerdict $three $TunnelBlockedDialErrors) 'port-blocked'
Check 'registered after 10 failed attempts resets -> connected' (Get-TunnelNetworkVerdict ($ten + $reg) $TunnelBlockedDialErrors) 'connected'
Check 'registered after 10 failed, then 2 more failed -> connected' (Get-TunnelNetworkVerdict ($ten + $reg + $two) $TunnelBlockedDialErrors) 'connected'
Check 'regex-like text is literal (dial tcp x.7844 i/o timeout without colon)' (Get-TunnelNetworkVerdict @($ten | ForEach-Object { $_.Replace(':7844: ', '.7844 ') }) 6) 'unknown'
Check 'port 17844 is not 7844? (contains :7844 only when preceded by colon)' (Get-TunnelNetworkVerdict @($ten | ForEach-Object { $_.Replace(':7844:', ':17844:') }) 6) 'unknown'
Check 'case: REGISTERED upper-case is not matched (Contains is ordinal)' (Get-TunnelNetworkVerdict ($ten + $reg.ToUpper()) 6) 'port-blocked'

# ---------------------------------------------------------------- simulated clock harness
$tmp = Join-Path $env:TEMP ('n0107_ver_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmp | Out-Null
$enc = New-Object System.Text.UTF8Encoding($false)
$errLog = Join-Path $tmp 'tunnel.err.log'
$logDir = $tmp
function Set-ErrLog { param([string[]]$Lines) [System.IO.File]::WriteAllText($errLog, ($Lines -join "`n") + "`n", $enc) }

$script:clock = [datetime]'2026-10-08T09:00:00'
function Get-Date { param([string]$Format) if ($Format) { return $script:clock.ToString($Format) } return $script:clock }
function Start-Sleep { param([int]$Seconds) }
function Test-Path { param($Path) return $true }
$script:log = New-Object System.Collections.ArrayList
$script:stops = New-Object System.Collections.ArrayList
$script:launchTimes = New-Object System.Collections.ArrayList
$script:readyCode = 503
$script:alive = $true
function Write-Log { param([string]$Message) [void]$script:log.Add(("{0:HH:mm:ss} {1}" -f $script:clock, $Message)) }
function Get-AuthOpenEvidence { return $null }
function Test-CompAlive { param($Comp) return $script:alive }
function Clear-Process { param($Comp) $Comp.Pid = $null }
function Get-QuickTunnels { param($All) return @() }
function Get-HttpStatus { param([string]$Url, [int]$TimeoutSec = 5, [switch]$UseSystemProxy) return $script:readyCode }
function Update-Hostname { param([int]$Port) if (-not $script:tunnel.Hostname) { $script:tunnel.Hostname = 'h' + $script:launchTimes.Count + '.trycloudflare.com' } }
function Invoke-PublicCheck { $script:tunnel.PublicLogin = 530; $script:tunnel.PublicMe = 530 }
function Stop-QuickTunnels { param([string]$Why) [void]$script:stops.Add($Why) }
function Get-TunnelGate { return $null }
function Start-Component { param($Comp, $File, $Arguments, $Dir, $ExtraEnv)
    [void]$script:launchTimes.Add($script:clock); [void]$Comp.Launches.Add($script:clock)
    $Comp.LastStart = $script:clock; $Comp.Pid = 4242; $Comp.Adopted = $false; $Comp.ErrLog = $errLog
    $script:alive = $true
    Set-State $Comp 'starting' 'pid 4242'
}
function Reset-World {
    $script:Components = [ordered]@{ tunnel = (New-Component 'tunnel' 1 60) }
    $script:Components.tunnel.Pid = 4242; $script:Components.tunnel.ErrLog = $errLog
    $script:Components.tunnel.LastStart = $script:clock
    $script:tunnel = @{
        Hostname = 'h0.trycloudflare.com'; HostnameSince = $script:clock
        LastReadyOk = $script:clock; LastPublicOk = $script:clock; LastPublicCheck = $null; PublicEverOk = $false
        PublicLogin = $null; PublicMe = $null; ClosedReason = $null; FirstPublicAfter = $null
        BlockedReason = $null; BlockedSince = $null; BlockedRetryAt = $null
    }
    $script:stops.Clear(); $script:launchTimes.Clear(); $script:log.Clear(); $script:alive = $true; $script:readyCode = 503
}
function Invoke-Minutes { param([int]$Minutes, [scriptblock]$Each)
    foreach ($i in 1..($Minutes * 2)) { $script:clock = $script:clock.AddSeconds(30); if ($Each) { & $Each }; Invoke-Tunnel @() }
}
$Components = $null; $tunnel = $null

# Scenario A: blocked network for 4 hours. The new code must launch about once per 30 min, never more.
Set-ErrLog $ten; $script:clock = [datetime]'2026-10-08T09:00:00'; Reset-World
Invoke-Minutes 240
$n = $script:launchTimes.Count
Check 'A: 4 h blocked -> fresh launches between 7 and 8 (one per 30 min)' ([bool]($n -ge 7 -and $n -le 8)) $true
$gaps = @(); for ($i = 1; $i -lt $n; $i++) { $gaps += ($script:launchTimes[$i] - $script:launchTimes[$i - 1]).TotalMinutes }
Check 'A: smallest gap between launches >= 30 min' ([bool](($gaps | Measure-Object -Minimum).Minimum -ge 30)) $true
Check 'A: every restart reason is the fresh-attempt reason' (@($script:stops | Where-Object { $_ -ne 'port 7844 blocked for 30 min; one fresh attempt' -and $_ -ne 'starting a fresh quick tunnel' }).Count) 0
Check 'A: state after 4 h' $Components.tunnel.State 'blocked'
Check 'A: hold logged once (episode not restarted by fresh attempts)' (@($script:log | Where-Object { $_.Contains('holding the tunnel') }).Count) 1
"   A launches: " + (($script:launchTimes | ForEach-Object { $_.ToString('HH:mm') }) -join ', ')

# Scenario B: same 4 h with a log that does not show the 7844 pattern: old rule (restart after /ready fails 10 min).
Set-ErrLog @($ten | ForEach-Object { $_.Replace(':7844:', ':443:') }); $script:clock = [datetime]'2026-10-08T09:00:00'; Reset-World
Invoke-Minutes 240
$nB = $script:launchTimes.Count
Check 'B: old rule unchanged -> about one launch per 10 min (>= 20 in 4 h)' ([bool]($nB -ge 20)) $true
Check 'B: never enters blocked' ([bool]$tunnel.BlockedSince) $false
"   B launches in 4 h: $nB"

# Scenario C: re-arm after a fresh launch: next attempt is 30 min after that launch.
Set-ErrLog $ten; $script:clock = [datetime]'2026-10-08T09:00:00'; Reset-World
Invoke-Minutes 1
$since = $tunnel.BlockedSince
Invoke-Minutes 31
Check 'C: one fresh launch by 32 min' $script:launchTimes.Count 1
Check 'C: BlockedRetryAt re-armed to launch + 30 min' (($tunnel.BlockedRetryAt - $script:launchTimes[0]).TotalMinutes) 30
Check 'C: BlockedSince unchanged by the fresh attempt' ($tunnel.BlockedSince -eq $since) $true

# Scenario D: cloudflared dies while blocked -> relaunched (dead branch), back-off clock re-armed.
$script:alive = $false
Invoke-Minutes 1
Check 'D: crash while blocked relaunches once' $script:launchTimes.Count 2
Check 'D: re-armed to the crash relaunch + 30 min' (($tunnel.BlockedRetryAt - $script:launchTimes[1]).TotalMinutes) 30

# Scenario E: /ready 200 ends the episode even though the log tail still shows timeouts (no registered line).
$script:readyCode = 200
Invoke-Minutes 1
Check 'E: /ready 200 -> healthy' $Components.tunnel.State 'healthy'
Check 'E: blocked fields cleared' ("{0}|{1}|{2}" -f [bool]$tunnel.BlockedSince, [bool]$tunnel.BlockedRetryAt, [bool]$tunnel.BlockedReason) 'False|False|False'
Check 'E: recovery logged once' (@($script:log | Where-Object { $_.Contains('no longer blocked') }).Count) 1
$launchesE = $script:launchTimes.Count
Invoke-Minutes 60
Check 'E: healthy 60 min more, no launches' ($script:launchTimes.Count - $launchesE) 0

# Scenario F: connected, then network lost -> new episode after threshold, old 10-min rule does not fire first.
$script:readyCode = 503
Set-ErrLog ($ten + $reg + $two)
Invoke-Minutes 5
Check 'F: below threshold after registered -> not blocked yet' ([bool]$tunnel.BlockedSince) $false
Set-ErrLog ($ten + $reg + $ten)
Invoke-Minutes 20
Check 'F: new episode starts, no restart within the 30 min hold' ("{0}/{1}" -f $Components.tunnel.State, ($script:launchTimes.Count - $launchesE)) 'blocked/0'

Remove-Item -Recurse -Force $tmp
"failures: $fail"
if ($fail -gt 0) { exit 1 } else { exit 0 }
