# CIP always-on supervisor (N-0073).
# Keeps the local stack running on this PC: WSL keeper, Redis (WSL), Celery worker + beat,
# API on 127.0.0.1:8001, production web on 127.0.0.1:3000 and the Cloudflare quick tunnel.
#
# Started hidden at logon by the per-user Startup shortcut (scripts/cip-supervisor-install.ps1).
# Stop or restart it with scripts/cip-supervisor-stop.ps1.
#
# State lives outside the repo, in %LOCALAPPDATA%\CIP\always-on\:
#   supervisor.pid, status.json (with heartbeat), link.html, stop.flag, logs\
#
# Rules (from N0073_DESIGN.md):
#   - Only one copy runs (named mutex Local\CIP-AlwaysOn).
#   - Healthy running processes are adopted, never restarted just because the supervisor started.
#   - The web must listen on 127.0.0.1 only; a 0.0.0.0 / :: listener on 3000 is replaced.
#   - The tunnel starts only when CIP_AUTH_MODE=session and /api/v1/auth/me answers 401.
#   - The tunnel is closed (and not restarted) on positive evidence that auth is open.
#   - The public address comes from the cloudflared metrics endpoint /quicktunnel (.hostname).
#   - The supervisor never builds the web, never sets CIP_LISTING_* and changes no machine setting.

$ErrorActionPreference = 'Continue'

$repo      = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$apiDir    = Join-Path $repo 'apps\api'
$webDir    = Join-Path $repo 'apps\web'
$py        = Join-Path $apiDir '.venv\Scripts\python.exe'
$envFile   = Join-Path $apiDir '.env'
$nextBin   = Join-Path $webDir 'node_modules\next\dist\bin\next'
$buildId   = Join-Path $webDir '.next\BUILD_ID'

$stateDir  = Join-Path $env:LOCALAPPDATA 'CIP\always-on'
$logDir    = Join-Path $stateDir 'logs'
$pidFile   = Join-Path $stateDir 'supervisor.pid'
$statusFile = Join-Path $stateDir 'status.json'
$linkFile  = Join-Path $stateDir 'link.html'
$stopFlag  = Join-Path $stateDir 'stop.flag'
$supLog    = Join-Path $logDir 'supervisor.log'

$CycleSeconds      = 30
$Delays            = @(0, 30, 60, 120, 300)   # wait before restart 1, 2, 3, 4, 5+
$FlapLimit         = 5                        # more than this many launches in 30 min = flapping
$TunnelDeadMinutes = 10                       # /ready or public /login failing this long -> restart tunnel
$PublicEverySec    = 300
$PublicFirstDelay  = 60                       # give a new hostname time to resolve before the first public check
$MetricsPort       = 20241
$Utf8NoBom         = New-Object System.Text.UTF8Encoding($false)

New-Item -ItemType Directory -Path $logDir -Force | Out-Null

# ---------------------------------------------------------------- single instance
$mutex = New-Object System.Threading.Mutex($false, 'Local\CIP-AlwaysOn')
$owned = $false
try {
    $owned = $mutex.WaitOne(0)
} catch {
    # The previous owner died without releasing it: Windows hands the mutex to us.
    $e = $_.Exception
    while ($e -and -not ($e -is [System.Threading.AbandonedMutexException])) { $e = $e.InnerException }
    if ($e) { $owned = $true }
}
if (-not $owned) {
    Add-Content -Path $supLog -Value ("{0} [pid {1}] another supervisor is already running; exiting." -f (Get-Date -Format 's'), $PID)
    exit 0
}

# ---------------------------------------------------------------- helpers
function Write-Log {
    param([string]$Message)
    try {
        if ((Test-Path $supLog) -and ((Get-Item $supLog).Length -gt 10MB)) {
            Move-Item -Path $supLog -Destination "$supLog.1" -Force
        }
        Add-Content -Path $supLog -Value ("{0} {1}" -f (Get-Date -Format 's'), $Message)
    } catch { }
}

# Atomic rename for status.json / link.html. Measured (N0073_swap_probe.ps1, 300 rewrites under a busy reader):
#   Move-Item -Force  -> reader found the file missing 101 times (it deletes, then moves)
#   File.Replace      -> missing 89 times (ReplaceFile is not one rename) plus 208 sharing errors
#   MoveFileEx(REPLACE_EXISTING|WRITE_THROUGH) -> missing 0 times
$script:HaveMoveFileEx = $false
try {
    Add-Type -Namespace CipSupervisor -Name Native -MemberDefinition @'
[DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
public static extern bool MoveFileEx(string existingFileName, string newFileName, int flags);
'@ -ErrorAction Stop
    $script:HaveMoveFileEx = $true
} catch { }

function Write-TextFile {
    # Write to a temp file, then rename it over the destination in one step, so a reader (link.html in a
    # browser, supervisor-guard.cjs reading status.json) never sees the file missing.
    param([string]$Path, [string]$Text)
    $tmp = "$Path.tmp"
    [System.IO.File]::WriteAllText($tmp, $Text, $Utf8NoBom)
    if (-not [System.IO.File]::Exists($Path)) { [System.IO.File]::Move($tmp, $Path); return }
    $err = 0
    foreach ($attempt in 1..5) {
        if ($script:HaveMoveFileEx) {
            if ([CipSupervisor.Native]::MoveFileEx($tmp, $Path, 0x1 -bor 0x8)) { return }   # REPLACE_EXISTING | WRITE_THROUGH
            $err = 'MoveFileEx ' + [System.Runtime.InteropServices.Marshal]::GetLastWin32Error()
        }
        # The rename is refused (error 5) while a reader holds the file open; File.Replace copes with that
        # case, and without Add-Type (constrained language) it is the only option. [NullString]::Value = no
        # backup file; a plain $null reaches .NET as "" and Replace rejects it.
        try { [System.IO.File]::Replace($tmp, $Path, [NullString]::Value); return } catch { $err = "$err; Replace $($_.Exception.Message)" }
        Start-Sleep -Milliseconds 100
    }
    throw "could not replace $Path (last error $err)"
}

function Get-HttpResult {
    # Returns @{ Status = <int, 0 on network error>; Body = <string or $null> }. Never throws.
    param([string]$Url, [int]$TimeoutSec = 5, [switch]$UseSystemProxy, [switch]$ReadBody)
    $result = @{ Status = 0; Body = $null }
    try {
        $req = [System.Net.HttpWebRequest]::Create($Url)
        $req.Method = 'GET'
        $req.Timeout = $TimeoutSec * 1000
        $req.ReadWriteTimeout = $TimeoutSec * 1000
        $req.AllowAutoRedirect = $false
        if (-not $UseSystemProxy) { $req.Proxy = $null }
        $resp = $req.GetResponse()
        $result.Status = [int]$resp.StatusCode
        if ($ReadBody) {
            $reader = New-Object System.IO.StreamReader($resp.GetResponseStream())
            $result.Body = $reader.ReadToEnd()
            $reader.Close()
        }
        $resp.Close()
    } catch {
        $e = $_.Exception
        while ($e -and -not ($e -is [System.Net.WebException])) { $e = $e.InnerException }
        if ($e -and $e.Response) {
            $result.Status = [int]$e.Response.StatusCode
            $e.Response.Close()
        }
    }
    return $result
}

function Get-HttpStatus {
    param([string]$Url, [int]$TimeoutSec = 5, [switch]$UseSystemProxy)
    return (Get-HttpResult -Url $Url -TimeoutSec $TimeoutSec -UseSystemProxy:$UseSystemProxy).Status
}

function Test-RedisPing {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect('127.0.0.1', 6379, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne(2000)) { return $false }
        $client.EndConnect($iar)
        $stream = $client.GetStream()
        $stream.ReadTimeout = 2000
        $ping = [System.Text.Encoding]::ASCII.GetBytes("PING`r`n")
        $stream.Write($ping, 0, $ping.Length)
        $buf = New-Object byte[] 64
        $n = $stream.Read($buf, 0, 64)
        return ([System.Text.Encoding]::ASCII.GetString($buf, 0, $n)).StartsWith('+PONG')
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Test-SessionMode {
    # Mirrors pilot-tunnel.ps1: apps/api/.env must say CIP_AUTH_MODE=session.
    # A process-level CIP_AUTH_MODE would override .env in the API, so it must agree too.
    if ($env:CIP_AUTH_MODE -and $env:CIP_AUTH_MODE.Trim() -ne 'session') { return $false }
    if (-not (Test-Path $envFile)) { return $false }
    $mode = $null
    foreach ($line in (Get-Content -Path $envFile -ErrorAction SilentlyContinue)) {
        $t = $line.Trim()
        if ($t.StartsWith('CIP_AUTH_MODE=')) {
            $mode = $t.Substring(14)
            $hash = $mode.IndexOf(' #')
            if ($hash -ge 0) { $mode = $mode.Substring(0, $hash) }
            $mode = $mode.Trim().Trim('"').Trim("'")
        }
    }
    return ($mode -eq 'session')
}

function Get-AllProcesses {
    return @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
}

function Test-AnyContains {
    param([string]$Text, [string[]]$Needles)
    if (-not $Text) { return $false }
    foreach ($n in $Needles) { if ($n -and $Text.IndexOf($n, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) { return $true } }
    return $false
}

function Get-OrphanRoots {
    # Live processes whose parent $ParentPid is gone (or was reused by an unrelated process).
    #   ChildMatch: when given, the child's command line must contain one of these strings.
    #   RootStart:  when known, the child must be no older than the original parent.
    #   NotAfter:   the reused parent's start time; the child must be older than it.
    param($All, [int]$ParentPid, [string[]]$ChildMatch, $RootStart, $NotAfter)
    return @($All | Where-Object {
        if ($_.ParentProcessId -ne $ParentPid -or $_.ProcessId -eq $ParentPid) { return $false }
        if ($RootStart -and $_.CreationDate -lt ([datetime]$RootStart).AddSeconds(-2)) { return $false }
        if ($NotAfter -and $_.CreationDate -ge [datetime]$NotAfter) { return $false }
        if ($ChildMatch -and $ChildMatch.Count -gt 0 -and -not (Test-AnyContains $_.CommandLine $ChildMatch)) { return $false }
        return $true
    })
}

function Stop-Tree {
    # Stops a process and every descendant (children must be younger than their parent,
    # so a reused parent PID cannot pull in unrelated processes).
    # When the root is already dead (or its PID now belongs to a process that started at another time than
    # RootStart), its orphaned children are stopped instead: e.g. the uvicorn --reload server child keeps
    # serving port 8001 after the reloader parent died. ChildMatch/RootStart narrow which orphans count.
    param([int]$RootPid, [string]$Why, [string[]]$ChildMatch = @(), $RootStart = $null)
    if ($RootPid -le 4) { return }
    $all = Get-AllProcesses
    $root = $all | Where-Object { $_.ProcessId -eq $RootPid } | Select-Object -First 1
    $notAfter = $null
    if ($root -and $RootStart -and ([Math]::Abs(($root.CreationDate - [datetime]$RootStart).TotalSeconds) -gt 2)) {
        $notAfter = $root.CreationDate   # PID reused: leave the new owner alone
        $root = $null
    }
    $victims = New-Object System.Collections.ArrayList
    $queue = New-Object System.Collections.Queue
    $label = 'root'
    if ($root) {
        $queue.Enqueue($root)
    } else {
        $label = 'orphans of dead root'
        foreach ($o in (Get-OrphanRoots $all $RootPid $ChildMatch $RootStart $notAfter)) { $queue.Enqueue($o) }
    }
    while ($queue.Count -gt 0) {
        $p = $queue.Dequeue()
        if ($victims -contains $p.ProcessId) { continue }
        [void]$victims.Add($p.ProcessId)
        foreach ($child in ($all | Where-Object { $_.ParentProcessId -eq $p.ProcessId -and $_.CreationDate -ge $p.CreationDate })) {
            $queue.Enqueue($child)
        }
    }
    $list = $victims -join ','
    if ($victims.Count -eq 0) { $list = 'nothing running' }
    Write-Log ("stop tree {0} ({1}; {2}): {3}" -f $RootPid, $Why, $label, $list)
    foreach ($v in $victims) { Stop-Process -Id $v -Force -ErrorAction SilentlyContinue }
}

function Get-ApiChildMatch {
    # What may still serve 8001 after its owner died: a uvicorn app.main process, or the
    # multiprocessing child that uvicorn --reload spawned from that owner.
    param([int]$OwnerPid)
    return @('uvicorn app.main', 'app.main:app', ("spawn_main(parent_pid={0}," -f $OwnerPid))
}

$WebChildMatch = @('next start', 'next\dist', 'next/dist')

function Resolve-PortOwner {
    # The live process that serves a listener. Normally the owning process; when that process is gone
    # (Windows keeps reporting the dead PID while an inherited socket is still open), a live child of it
    # whose command line matches ChildMatch. Returns $null when nothing live can be found.
    param([int]$OwnerPid, [string[]]$ChildMatch)
    if (Get-Process -Id $OwnerPid -ErrorAction SilentlyContinue) { return $OwnerPid }
    $kids = @(Get-OrphanRoots (Get-AllProcesses) $OwnerPid $ChildMatch $null $null)
    if ($kids.Count -gt 0) { return [int]$kids[0].ProcessId }
    return $null
}

function Get-Listeners {
    param([int]$Port)
    return @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

function Move-LogGenerations {
    # name.log -> name.log.1 -> name.log.2 (3 generations). Returns $false when a file is still locked.
    param([string]$Path)
    try {
        if (Test-Path "$Path.2") { Remove-Item "$Path.2" -Force -ErrorAction Stop }
        if (Test-Path "$Path.1") { Move-Item "$Path.1" "$Path.2" -Force -ErrorAction Stop }
        if (Test-Path $Path)     { Move-Item $Path "$Path.1" -Force -ErrorAction Stop }
        return $true
    } catch {
        return $false
    }
}

function New-LogPair {
    param([string]$Name)
    $out = Join-Path $logDir "$Name.log"
    $err = Join-Path $logDir "$Name.err.log"
    if (-not ((Move-LogGenerations $out) -and (Move-LogGenerations $err))) {
        # An orphan from an earlier launch still holds the file; use a dated name instead.
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $out = Join-Path $logDir "$Name-$stamp.log"
        $err = Join-Path $logDir "$Name-$stamp.err.log"
    }
    return @{ Out = $out; Err = $err }
}

function Quote {
    param([string]$Value)
    if ($Value.Contains(' ')) { return '"' + $Value + '"' }
    return $Value
}

# ---------------------------------------------------------------- component state
function New-Component {
    param([string]$Name, [int]$FailLimit, [int]$GraceSec)
    return [ordered]@{
        Name = $Name; State = 'unknown'; Detail = ''
        Pid = $null; StartTime = $null; Adopted = $false
        FailLimit = $FailLimit; GraceSec = $GraceSec; Fails = 0
        Launches = New-Object System.Collections.ArrayList
        ConsecutiveRestarts = 0; NextStartAt = [datetime]::MinValue
        LastStart = $null; LastHealthy = $null; EverHealthy = $false
        Held = $false; Log = $null; MetricsPort = $null
    }
}

$Components = [ordered]@{
    wsl    = New-Component 'wsl'    1 5
    redis  = New-Component 'redis'  2 0
    worker = New-Component 'worker' 2 60
    api    = New-Component 'api'    3 90
    web    = New-Component 'web'    3 60
    tunnel = New-Component 'tunnel' 1 60
}
$tunnel = @{
    Hostname = $null; HostnameSince = $null
    LastReadyOk = $null; LastPublicOk = $null; LastPublicCheck = $null; PublicEverOk = $false
    PublicLogin = $null; PublicMe = $null; ClosedReason = $null; FirstPublicAfter = $null
}

function Set-State {
    param($Comp, [string]$State, [string]$Detail = '')
    if ($Comp.State -ne $State) { Write-Log ("{0}: {1} -> {2} {3}" -f $Comp.Name, $Comp.State, $State, $Detail) }
    $Comp.State = $State
    $Comp.Detail = $Detail
}

function Set-Healthy {
    param($Comp, [string]$Detail = '')
    Set-State $Comp 'healthy' $Detail
    $Comp.Fails = 0
    $Comp.ConsecutiveRestarts = 0
    $Comp.NextStartAt = [datetime]::MinValue
    $Comp.LastHealthy = Get-Date
    $Comp.EverHealthy = $true
}

function Test-CompAlive {
    param($Comp)
    if (-not $Comp.Pid) { return $false }
    $p = Get-Process -Id $Comp.Pid -ErrorAction SilentlyContinue
    if (-not $p) { return $false }
    if ($Comp.StartTime) {
        try { if ($p.StartTime -ne $Comp.StartTime) { return $false } } catch { }
    }
    return $true
}

function Set-Adopted {
    param($Comp, [int]$ProcId)
    $p = Get-Process -Id $ProcId -ErrorAction SilentlyContinue
    $changed = ($Comp.Pid -ne $ProcId -or -not $Comp.Adopted)
    $Comp.Pid = $ProcId
    $Comp.StartTime = $null
    if ($p) { try { $Comp.StartTime = $p.StartTime } catch { } }
    $Comp.Adopted = $true
    if ($changed) { Write-Log ("{0}: adopted running process {1}" -f $Comp.Name, $ProcId) }
}

function Clear-Process {
    param($Comp)
    $Comp.Pid = $null
    $Comp.StartTime = $null
    $Comp.Adopted = $false
}

function Test-InGrace {
    param($Comp)
    return ($Comp.LastStart -and -not $Comp.Adopted -and ((Get-Date) - $Comp.LastStart).TotalSeconds -lt $Comp.GraceSec)
}

function Test-MayStart {
    # Backoff gate. Returns $true when a (re)start is allowed now.
    param($Comp)
    if ($Comp.Held) { Set-State $Comp 'held' 'stopped by operator (cip-supervisor-stop.ps1)'; return $false }
    $now = Get-Date
    if ($now -lt $Comp.NextStartAt) {
        $wait = [int]($Comp.NextStartAt - $now).TotalSeconds
        $state = 'backoff'
        if ((Get-RecentLaunches $Comp) -gt $FlapLimit) { $state = 'flapping' }
        Set-State $Comp $state ("next start in {0}s ({1} launches in 30 min)" -f $wait, (Get-RecentLaunches $Comp))
        return $false
    }
    return $true
}

function Get-RecentLaunches {
    param($Comp)
    $cut = (Get-Date).AddMinutes(-30)
    return @($Comp.Launches | Where-Object { $_ -gt $cut }).Count
}

function Register-Launch {
    param($Comp)
    $now = Get-Date
    [void]$Comp.Launches.Add($now)
    while ($Comp.Launches.Count -gt 50) { $Comp.Launches.RemoveAt(0) }
    $Comp.LastStart = $now
    $Comp.Fails = 0
    $Comp.Adopted = $false
    # The next start may follow after Delays[n]: 0 s after a healthy run, then 30, 60, 120, 300.
    $i = [Math]::Min($Comp.ConsecutiveRestarts + 1, $Delays.Count - 1)
    if ($Comp.ConsecutiveRestarts -eq 0) { $i = 0 }
    $delay = $Delays[$i]
    if ((Get-RecentLaunches $Comp) -gt $FlapLimit) { $delay = $Delays[$Delays.Count - 1] }
    $Comp.ConsecutiveRestarts++
    $Comp.NextStartAt = $now.AddSeconds($delay)
}

function Start-Component {
    param($Comp, [string]$File, [string[]]$Arguments, [string]$WorkDir, [hashtable]$ExtraEnv = @{})
    $logs = New-LogPair $Comp.Name
    $saved = @{}
    foreach ($k in $ExtraEnv.Keys) {
        $saved[$k] = [Environment]::GetEnvironmentVariable($k, 'Process')
        [Environment]::SetEnvironmentVariable($k, $ExtraEnv[$k], 'Process')
    }
    try {
        $p = Start-Process -FilePath $File -ArgumentList $Arguments -WorkingDirectory $WorkDir `
            -WindowStyle Hidden -RedirectStandardOutput $logs.Out -RedirectStandardError $logs.Err -PassThru
    } finally {
        foreach ($k in $saved.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k], 'Process') }
    }
    Register-Launch $Comp
    if (-not $p) { Set-State $Comp 'error' "could not start $File"; return }
    $Comp.Pid = $p.Id
    $Comp.StartTime = $null
    try { $Comp.StartTime = $p.StartTime } catch { }
    $Comp.Log = $logs.Out
    $listing = 'CIP_LISTING_LIVE_FETCH present={0}, CIP_LISTING_CAPTURE_SCHEDULE present={1}' -f `
        [bool]$env:CIP_LISTING_LIVE_FETCH, [bool]$env:CIP_LISTING_CAPTURE_SCHEDULE
    Write-Log ("{0}: started pid {1} (launch {2}; {3}): {4} {5}" -f $Comp.Name, $p.Id, $Comp.Launches.Count, $listing, $File, ($Arguments -join ' '))
    Set-State $Comp 'starting' ("pid {0}" -f $p.Id)
}

# ---------------------------------------------------------------- checks, one per component
function Find-Procs {
    param($All, [string]$Name, [string[]]$Contains)
    return @($All | Where-Object {
        if ($_.Name -ne $Name -or -not $_.CommandLine) { return $false }
        foreach ($s in $Contains) { if (-not $_.CommandLine.Contains($s)) { return $false } }
        return $true
    })
}

function Get-RootProcs {
    # The venv python.exe is a launcher that re-spawns the real interpreter with the same command line;
    # count only processes whose parent is not itself a match.
    param($Found)
    $ids = @($Found | ForEach-Object { $_.ProcessId })
    return @($Found | Where-Object { $ids -notcontains $_.ParentProcessId })
}

function Invoke-WslKeeper {
    param($All)
    $c = $Components.wsl
    if (Test-CompAlive $c) { Set-Healthy $c ("pid {0}" -f $c.Pid); return }
    Clear-Process $c
    $existing = @(Find-Procs $All 'wsl.exe' @('Ubuntu', 'sleep infinity'))
    if ($existing.Count -gt 0) { Set-Adopted $c $existing[0].ProcessId; Set-Healthy $c ("pid {0}" -f $c.Pid); return }
    if (-not (Test-MayStart $c)) { return }
    Start-Component $c 'wsl.exe' @('-d', 'Ubuntu', '-u', 'root', '--', 'sleep', 'infinity') $repo
}

function Invoke-Redis {
    $c = $Components.redis
    if (Test-RedisPing) {
        if (-not $c.EverHealthy -and -not $c.LastStart) { $c.Adopted = $true }
        Set-Healthy $c 'PING -> +PONG'
        return
    }
    $c.Fails++
    if ($c.EverHealthy -and $c.Fails -lt $c.FailLimit) { Set-State $c 'unhealthy' ("PING failed ({0}/{1})" -f $c.Fails, $c.FailLimit); return }
    if (-not (Test-MayStart $c)) { return }
    $logs = New-LogPair 'redis'
    Register-Launch $c
    Write-Log 'redis: starting redis-server in WSL (service redis-server start)'
    $p = Start-Process -FilePath 'wsl.exe' -ArgumentList @('-d', 'Ubuntu', '-u', 'root', '--', 'service', 'redis-server', 'start') `
        -WorkingDirectory $repo -WindowStyle Hidden -RedirectStandardOutput $logs.Out -RedirectStandardError $logs.Err -PassThru
    $c.Log = $logs.Out
    if (-not $p.WaitForExit(60000)) { Write-Log 'redis: service start did not finish within 60s' }
    foreach ($i in 1..10) {
        if (Test-RedisPing) { Set-Healthy $c 'PING -> +PONG'; $c.Adopted = $false; return }
        Start-Sleep -Seconds 1
    }
    Set-State $c 'unhealthy' 'started but PING still failing'
}

function Invoke-Worker {
    param($All)
    $c = $Components.worker
    $workers = @(Get-RootProcs @(Find-Procs $All 'python.exe' @('app.worker.celery_app worker')))
    $beats   = @(Get-RootProcs @(Find-Procs $All 'python.exe' @('app.worker.celery_app beat')))
    $counts  = "worker={0} beat={1}" -f $workers.Count, $beats.Count

    $alive = Test-CompAlive $c
    $prevPid = $c.Pid; $prevStart = $c.StartTime
    if (-not $alive) {
        Clear-Process $c
        $wrappers = @(Find-Procs $All 'node.exe' @('dev-worker.js'))
        if ($wrappers.Count -gt 0) { Set-Adopted $c $wrappers[0].ProcessId; $alive = $true }
    }

    if ($Components.redis.State -ne 'healthy') {
        Set-State $c 'waiting' ("redis is not healthy; {0}" -f $counts)
        return
    }
    if ($alive) {
        if ($workers.Count -eq 1 -and $beats.Count -eq 1) { Set-Healthy $c ("wrapper pid {0}; {1}" -f $c.Pid, $counts); return }
        if (Test-InGrace $c) { Set-State $c 'starting' $counts; return }
        $c.Fails++
        if ($c.Fails -lt $c.FailLimit) { Set-State $c 'unhealthy' ("wrong process count ({0}); {1}/{2}" -f $counts, $c.Fails, $c.FailLimit); return }
        if (-not (Test-MayStart $c)) { return }
        Stop-Tree $c.Pid "worker count wrong: $counts" -RootStart $c.StartTime
        foreach ($p in (@($workers) + @($beats))) { Stop-Tree $p.ProcessId 'stray celery' }
        Clear-Process $c
    } else {
        if ($c.LastStart) { Set-State $c 'dead' ("wrapper exited; {0}" -f $counts) }
        # Celery children of a wrapper that died (dev-worker.js also stops stray celery before it spawns).
        if ($prevPid) { Stop-Tree $prevPid 'worker wrapper exited' @('app.worker.celery_app') $prevStart }
        if (-not (Test-MayStart $c)) { return }
    }
    # dev-worker.js stops any stray celery itself before it spawns (single consumer).
    $node = (Get-Command node.exe -ErrorAction SilentlyContinue).Source
    if (-not $node) { Set-State $c 'error' 'node.exe not found on PATH'; return }
    Start-Component $c $node @((Quote (Join-Path $repo 'scripts\dev-worker.js'))) $repo @{
        CIP_ENABLE_DEV_BEAT = '1'; PYTHONUNBUFFERED = '1'; CIP_SUPERVISOR_CHILD = '1'
        CIP_CELERY_BEAT_SCHEDULE = (Join-Path $stateDir 'celerybeat-schedule')
    }
}

function Invoke-Api {
    $c = $Components.api
    $status = Get-HttpStatus 'http://127.0.0.1:8001/health'
    $alive = Test-CompAlive $c
    if ($status -eq 200) {
        if (-not $alive) {
            $l = Get-Listeners 8001 | Select-Object -First 1
            $owner = $null
            if ($l) { $owner = Resolve-PortOwner ([int]$l.OwningProcess) (Get-ApiChildMatch ([int]$l.OwningProcess)) }
            if ($owner) { Set-Adopted $c $owner }
            elseif ($l) {
                # Windows still names a dead PID and no live child of it matches: nothing to adopt.
                Clear-Process $c
                Set-Healthy $c ("/health 200; listener owner pid {0} has no live process" -f $l.OwningProcess)
                return
            }
        }
        Set-Healthy $c ("/health 200; pid {0}" -f $c.Pid)
        return
    }
    $listeners = @(Get-Listeners 8001)
    if ($alive -and (Test-InGrace $c)) { Set-State $c 'starting' ("/health {0}" -f $status); return }
    if ($alive -or $listeners.Count -gt 0) {
        $c.Fails++
        if ($c.Fails -lt $c.FailLimit) { Set-State $c 'unhealthy' ("/health {0} ({1}/{2})" -f $status, $c.Fails, $c.FailLimit); return }
    } else {
        if ($c.Pid) { Set-State $c 'dead' 'process exited' }
    }
    if (-not (Test-MayStart $c)) { return }
    if ($c.Pid) { Stop-Tree $c.Pid "api /health $status" (Get-ApiChildMatch $c.Pid) $c.StartTime }
    foreach ($l in (Get-Listeners 8001)) {
        Stop-Tree ([int]$l.OwningProcess) 'port 8001 occupied by an unhealthy process' (Get-ApiChildMatch ([int]$l.OwningProcess))
    }
    Clear-Process $c
    # Same interpreter, cwd and env as scripts/dev-api.js (settings read apps/api/.env by absolute path),
    # but loopback only and without --reload so a git checkout cannot restart it mid-request.
    if (-not (Test-Path $py)) { Set-State $c 'error' "missing venv python at $py"; return }
    Start-Component $c $py @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8001') $apiDir @{ PYTHONUNBUFFERED = '1' }
}

function Invoke-Web {
    $c = $Components.web
    if (-not (Test-Path $buildId)) {
        Set-State $c 'needs build' 'apps/web/.next/BUILD_ID is missing; run: pnpm --filter @cip/web build'
        return
    }
    $listeners = @(Get-Listeners 3000)
    $wide = @($listeners | Where-Object { $_.LocalAddress -ne '127.0.0.1' })
    if ($wide.Count -gt 0) {
        $addr = ($wide | ForEach-Object { $_.LocalAddress } | Select-Object -Unique) -join ','
        Set-State $c 'unhealthy' "listening on $addr (must be 127.0.0.1 only); replacing"
        foreach ($l in $wide) { Stop-Tree ([int]$l.OwningProcess) "web listening on $($l.LocalAddress)" $WebChildMatch }
        Clear-Process $c
        Start-Sleep -Seconds 2
        $listeners = @(Get-Listeners 3000)
    }
    $login = Get-HttpStatus 'http://127.0.0.1:3000/login' 10
    $me    = Get-HttpStatus 'http://127.0.0.1:3000/api/v1/auth/me' 10
    $apiUp = ($Components.api.State -eq 'healthy')
    $alive = Test-CompAlive $c
    $detail = "/login {0}; proxy /auth/me {1}" -f $login, $me
    if ($listeners.Count -gt 0 -and $login -eq 200 -and ($me -eq 401 -or ($me -ne 200 -and -not $apiUp))) {
        if (-not $alive) {
            $owner = Resolve-PortOwner ([int]$listeners[0].OwningProcess) $WebChildMatch
            if ($owner) { Set-Adopted $c $owner }
            else { Clear-Process $c; $detail = "{0}; listener owner pid {1} has no live process" -f $detail, $listeners[0].OwningProcess }
        }
        Set-Healthy $c ("{0}; pid {1}" -f $detail, $c.Pid)
        return
    }
    if ($alive -and (Test-InGrace $c)) { Set-State $c 'starting' $detail; return }
    if ($alive -or $listeners.Count -gt 0) {
        $c.Fails++
        if ($c.Fails -lt $c.FailLimit) { Set-State $c 'unhealthy' ("{0} ({1}/{2})" -f $detail, $c.Fails, $c.FailLimit); return }
    } elseif ($c.Pid) {
        Set-State $c 'dead' 'process exited'
    }
    if (-not (Test-MayStart $c)) { return }
    if ($c.Pid) { Stop-Tree $c.Pid "web $detail" $WebChildMatch $c.StartTime }
    foreach ($l in (Get-Listeners 3000)) { Stop-Tree ([int]$l.OwningProcess) 'port 3000 occupied by an unhealthy process' $WebChildMatch }
    Clear-Process $c
    $node = (Get-Command node.exe -ErrorAction SilentlyContinue).Source
    if (-not $node) { Set-State $c 'error' 'node.exe not found on PATH'; return }
    Start-Component $c $node @((Quote $nextBin), 'start', '-H', '127.0.0.1', '-p', '3000') $webDir
}

function Get-QuickTunnels {
    param($All)
    return @(Find-Procs $All 'cloudflared.exe' @('tunnel', '--url', ':3000'))
}

function Stop-QuickTunnels {
    param([string]$Why)
    foreach ($t in (Get-QuickTunnels (Get-AllProcesses))) { Stop-Tree $t.ProcessId $Why }
    Clear-Process $Components.tunnel
}

function Get-AuthOpenEvidence {
    # Positive evidence only. A 5xx or a network error is NOT evidence that auth is open.
    if (-not (Test-SessionMode)) { return 'apps/api/.env no longer says CIP_AUTH_MODE=session' }
    if ((Get-HttpStatus 'http://127.0.0.1:8001/api/v1/auth/me') -eq 200) { return 'API /api/v1/auth/me answered 200 without a token' }
    if ((Get-HttpStatus 'http://127.0.0.1:3000/api/v1/auth/me' 10) -eq 200) { return 'web proxy /api/v1/auth/me answered 200 without a token' }
    if ($tunnel.PublicMe -eq 200) { return 'public /api/v1/auth/me answered 200 without a token' }
    return $null
}

function Get-TunnelGate {
    if (-not (Test-SessionMode)) { return 'apps/api/.env must contain CIP_AUTH_MODE=session' }
    $s = Get-HttpStatus 'http://127.0.0.1:8001/api/v1/auth/me'
    if ($s -ne 401) { return "API /api/v1/auth/me is $s, expected 401" }
    $s = Get-HttpStatus 'http://127.0.0.1:3000/login' 10
    if ($s -ne 200) { return "web /login is $s, expected 200" }
    $s = Get-HttpStatus 'http://127.0.0.1:3000/api/v1/auth/me' 10
    if ($s -ne 401) { return "web proxy /api/v1/auth/me is $s, expected 401" }
    return $null
}

function Get-MetricsPort {
    param([int]$ProcId)
    $l = @(Get-NetTCPConnection -State Listen -OwningProcess $ProcId -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalAddress -eq '127.0.0.1' } | Sort-Object LocalPort)
    if ($l.Count -gt 0) { return [int]$l[0].LocalPort }
    return $MetricsPort
}

function Test-HostnameShape {
    param([string]$Name)
    if (-not $Name -or -not $Name.EndsWith('.trycloudflare.com')) { return $false }
    foreach ($ch in $Name.ToCharArray()) {
        if (-not ([char]::IsLetterOrDigit($ch) -or $ch -eq '-' -or $ch -eq '.')) { return $false }
    }
    return $true
}

function Update-Hostname {
    param([int]$Port)
    $r = Get-HttpResult -Url ("http://127.0.0.1:{0}/quicktunnel" -f $Port) -ReadBody
    if ($r.Status -ne 200 -or -not $r.Body) { return }
    try { $name = ($r.Body | ConvertFrom-Json).hostname } catch { return }
    if (-not (Test-HostnameShape $name)) { return }
    if ($name -ne $tunnel.Hostname) {
        Write-Log ("tunnel: public link is now https://{0}" -f $name)
        $tunnel.Hostname = $name
        $tunnel.HostnameSince = Get-Date
        $tunnel.FirstPublicAfter = (Get-Date).AddSeconds($PublicFirstDelay)
        $tunnel.LastPublicCheck = $null
        $tunnel.PublicLogin = $null
        $tunnel.PublicMe = $null
        Write-DesktopLink
    }
}

function Invoke-PublicCheck {
    if (-not $tunnel.Hostname) { return }
    $now = Get-Date
    if ($tunnel.FirstPublicAfter -and $now -lt $tunnel.FirstPublicAfter) { return }
    if ($tunnel.LastPublicCheck -and ($now - $tunnel.LastPublicCheck).TotalSeconds -lt $PublicEverySec) { return }
    $base = 'https://' + $tunnel.Hostname
    $tunnel.PublicLogin = Get-HttpStatus ($base + '/login') 15 -UseSystemProxy
    $tunnel.PublicMe    = Get-HttpStatus ($base + '/api/v1/auth/me') 15 -UseSystemProxy
    $tunnel.LastPublicCheck = $now
    if ($tunnel.PublicLogin -eq 200) { $tunnel.LastPublicOk = $now; $tunnel.PublicEverOk = $true }
    Write-Log ("tunnel: public check /login {0}, /api/v1/auth/me {1}" -f $tunnel.PublicLogin, $tunnel.PublicMe)
}

function Invoke-Tunnel {
    param($All)
    $c = $Components.tunnel
    if ($tunnel.ClosedReason) {
        if (@(Get-QuickTunnels $All).Count -gt 0) { Stop-QuickTunnels 'auth open (latched)' }
        Set-State $c 'closed' ("auth open: {0}. Fix auth, then restart the supervisor (cip-supervisor-stop.ps1 -Restart)." -f $tunnel.ClosedReason)
        return
    }
    $evidence = Get-AuthOpenEvidence
    if ($evidence) {
        Write-Log "tunnel: CLOSING the public tunnel - $evidence"
        $tunnel.ClosedReason = $evidence
        Stop-QuickTunnels $evidence
        $tunnel.Hostname = $null
        Set-State $c 'closed' "auth open: $evidence"
        return
    }

    $now = Get-Date
    $alive = Test-CompAlive $c
    if (-not $alive) {
        Clear-Process $c
        $running = @(Get-QuickTunnels $All)
        if ($running.Count -gt 0) {
            $port = Get-MetricsPort $running[0].ProcessId
            if ((Get-HttpStatus ("http://127.0.0.1:{0}/quicktunnel" -f $port)) -eq 200) {
                Set-Adopted $c $running[0].ProcessId
                $c.MetricsPort = $port
                $tunnel.LastReadyOk = $now
                $tunnel.LastPublicOk = $now
                $alive = $true
            }
        }
    }

    if ($alive) {
        $port = $MetricsPort
        if ($c.MetricsPort) { $port = $c.MetricsPort }
        $ready = Get-HttpStatus ("http://127.0.0.1:{0}/ready" -f $port)
        if ($ready -eq 200) { $tunnel.LastReadyOk = $now }
        Update-Hostname $port
        Invoke-PublicCheck
        $detail = "/ready {0}; public /login {1}, /auth/me {2}; pid {3}" -f $ready, $tunnel.PublicLogin, $tunnel.PublicMe, $c.Pid
        if ($tunnel.PublicMe -eq 200) { return }   # handled as auth-open evidence on the next cycle
        $readyStale  = $tunnel.LastReadyOk -and (($now - $tunnel.LastReadyOk).TotalMinutes -ge $TunnelDeadMinutes)
        # Public failure restarts only once the public check has worked at least once in this
        # supervisor's life, so a network that blocks trycloudflare cannot churn the address.
        $publicStale = $tunnel.PublicEverOk -and $tunnel.LastPublicOk -and (($now - $tunnel.LastPublicOk).TotalMinutes -ge $TunnelDeadMinutes)
        if (-not $readyStale -and -not $publicStale) {
            if ($ready -eq 200 -and $tunnel.Hostname) { Set-Healthy $c $detail }
            elseif (Test-InGrace $c) { Set-State $c 'starting' $detail }
            else { Set-State $c 'unhealthy' $detail }
            return
        }
        if (-not (Test-MayStart $c)) { return }
        $why = 'public /login failing for 10 min'
        if ($readyStale) { $why = '/ready failing for 10 min' }
        Write-Log "tunnel: restarting ($why)"
        Stop-QuickTunnels $why
    } else {
        if ($c.LastStart -or $tunnel.Hostname) { Set-State $c 'dead' 'cloudflared is not running' }
        if (-not (Test-MayStart $c)) { return }
    }

    $gate = Get-TunnelGate
    if ($gate) { Set-State $c 'gated' "not starting: $gate"; return }
    $cf = Join-Path $env:LOCALAPPDATA 'cloudflared\cloudflared.exe'
    if (-not (Test-Path $cf)) { $cf = (Get-Command cloudflared.exe -ErrorAction SilentlyContinue).Source }
    if (-not $cf) { Set-State $c 'error' 'cloudflared.exe not found'; return }
    Stop-QuickTunnels 'starting a fresh quick tunnel'
    $tunnel.Hostname = $null
    Start-Component $c $cf @('tunnel', '--url', 'http://127.0.0.1:3000', '--protocol', 'http2',
        '--metrics', ("127.0.0.1:{0}" -f $MetricsPort), '--no-autoupdate') $repo
    $c.MetricsPort = $MetricsPort
    $tunnel.LastReadyOk = Get-Date
    $tunnel.LastPublicOk = Get-Date
    foreach ($i in 1..30) {
        Start-Sleep -Seconds 1
        Update-Hostname $MetricsPort
        if ($tunnel.Hostname) { break }
    }
}

# ---------------------------------------------------------------- outputs
function Write-DesktopLink {
    if (-not $tunnel.Hostname) { return }
    try {
        $desk = [Environment]::GetFolderPath('Desktop')
        $text = "[InternetShortcut]`r`nURL=https://{0}/login`r`n" -f $tunnel.Hostname
        [System.IO.File]::WriteAllText((Join-Path $desk 'CIP public link.url'), $text, [System.Text.Encoding]::ASCII)
    } catch { Write-Log "desktop link not written: $_" }
}

function Format-Time {
    param($Value)
    if ($Value) { return ([datetime]$Value).ToString('s') }
    return $null
}

function Write-Status {
    param([string]$SupervisorState = 'running')
    $now = Get-Date
    $comps = [ordered]@{}
    foreach ($k in $Components.Keys) {
        $c = $Components[$k]
        $comps[$k] = [ordered]@{
            state = $c.State; detail = $c.Detail; pid = $c.Pid; adopted = $c.Adopted
            launches = $c.Launches.Count; launches_30m = (Get-RecentLaunches $c)
            last_start = (Format-Time $c.LastStart); last_healthy = (Format-Time $c.LastHealthy); log = $c.Log
        }
    }
    $url = $null
    if ($tunnel.Hostname) { $url = 'https://' + $tunnel.Hostname }
    $status = [ordered]@{
        supervisor = [ordered]@{
            state = $SupervisorState; pid = $PID; started = (Format-Time $script:SupervisorStarted)
            heartbeat = $now.ToString('yyyy-MM-ddTHH:mm:ss.fffzzz'); heartbeat_unix_ms = [int64](($now.ToUniversalTime() - [datetime]'1970-01-01').TotalMilliseconds)
            cycle = $script:Cycle; cycle_seconds = $CycleSeconds; log = $supLog
        }
        link = [ordered]@{
            hostname = $tunnel.Hostname; url = $url; since = (Format-Time $tunnel.HostnameSince)
            public_login = $tunnel.PublicLogin; public_auth_me = $tunnel.PublicMe
            public_checked = (Format-Time $tunnel.LastPublicCheck); closed_reason = $tunnel.ClosedReason
        }
        env = [ordered]@{
            CIP_LISTING_LIVE_FETCH_present = [bool]$env:CIP_LISTING_LIVE_FETCH
            CIP_LISTING_CAPTURE_SCHEDULE_present = [bool]$env:CIP_LISTING_CAPTURE_SCHEDULE
        }
        components = $comps
    }
    try { Write-TextFile $statusFile ($status | ConvertTo-Json -Depth 6) } catch { Write-Log "status.json not written: $_" }
    try { Write-TextFile $linkFile (Get-LinkHtml $status) } catch { Write-Log "link.html not written: $_" }
}

function Get-LinkHtml {
    param($Status)
    $enc = { param($v) [System.Net.WebUtility]::HtmlEncode([string]$v) }
    $link = 'No public link yet'
    $loginUrl = ''
    if ($Status.link.url) { $loginUrl = $Status.link.url + '/login'; $link = $loginUrl }
    if ($Status.link.closed_reason) { $link = 'Tunnel closed: ' + $Status.link.closed_reason }
    $rows = foreach ($k in $Status.components.Keys) {
        $c = $Status.components[$k]
        $cls = 'bad'
        if ($c.state -eq 'healthy') { $cls = 'ok' } elseif ($c.state -eq 'starting') { $cls = 'warn' }
        $adopted = ''
        if ($c.adopted) { $adopted = 'adopted' }
        "<tr><td>{0}</td><td class='{1}'>{2}</td><td>{3}</td><td>{4}</td><td>{5}</td><td>{6}</td></tr>" -f `
            (& $enc $k), $cls, (& $enc $c.state), (& $enc $c.pid), $adopted, (& $enc $c.launches), (& $enc $c.detail)
    }
    return @"
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta http-equiv="refresh" content="30">
<title>CIP status</title>
<style>
 body { font-family: Segoe UI, Arial, sans-serif; margin: 24px; color: #1b1b1b; background: #fafafa; }
 .link { font-size: 28px; font-weight: 600; word-break: break-all; margin: 8px 0 12px; }
 button { font-size: 16px; padding: 6px 14px; }
 table { border-collapse: collapse; margin-top: 20px; font-size: 14px; }
 td, th { border: 1px solid #ccc; padding: 4px 8px; text-align: left; vertical-align: top; }
 .ok { color: #116611; font-weight: 600; } .warn { color: #8a6100; font-weight: 600; } .bad { color: #a40000; font-weight: 600; }
 #stale { display: none; background: #a40000; color: #fff; padding: 10px; font-weight: 600; margin-bottom: 12px; }
 .muted { color: #666; font-size: 13px; }
</style></head><body>
<div id="stale">Supervisor heartbeat is stale (more than 3 minutes old). The supervisor may have stopped; this page is out of date.</div>
<div class="muted">CIP public link</div>
<div class="link" id="link">$(& $enc $link)</div>
<button onclick="navigator.clipboard.writeText(document.getElementById('link').textContent)">Copy</button>
<p class="muted">Heartbeat $(& $enc $Status.supervisor.heartbeat) &middot; supervisor pid $(& $enc $Status.supervisor.pid) &middot; public /login $(& $enc $Status.link.public_login), /api/v1/auth/me $(& $enc $Status.link.public_auth_me)</p>
<table><tr><th>Component</th><th>State</th><th>PID</th><th></th><th>Launches</th><th>Detail</th></tr>
$($rows -join "`n")
</table>
<p class="muted">Stop: scripts\cip-supervisor-stop.ps1 &middot; Restart one part: scripts\cip-supervisor-stop.ps1 -Component api -Restart &middot; Logs: $(& $enc $logDir)</p>
<script>
 var hb = $($Status.supervisor.heartbeat_unix_ms);
 function check() { if (Date.now() - hb > 180000) { document.getElementById('stale').style.display = 'block'; } }
 check(); setInterval(check, 10000);
</script>
</body></html>
"@
}

# ---------------------------------------------------------------- stop / restart requests
function Stop-Owned {
    param($Comp, [string]$Why)
    # Stop-Tree also stops orphans when the root already exited, and leaves a reused PID alone (RootStart).
    if ($Comp.Pid) { Stop-Tree $Comp.Pid $Why @() $Comp.StartTime }
    Clear-Process $Comp
}

function Stop-OneComponent {
    param([string]$Name, [string]$Why)
    $c = $Components[$Name]
    switch ($Name) {
        'tunnel' { Stop-QuickTunnels $Why }
        'redis'  { Start-Process -FilePath 'wsl.exe' -ArgumentList @('-d', 'Ubuntu', '-u', 'root', '--', 'service', 'redis-server', 'stop') -WindowStyle Hidden -Wait }
        default  {
            if ($c.Pid) { Stop-Tree $c.Pid $Why @() $c.StartTime }
            if ($Name -eq 'api') { foreach ($l in (Get-Listeners 8001)) { Stop-Tree ([int]$l.OwningProcess) $Why (Get-ApiChildMatch ([int]$l.OwningProcess)) } }
            if ($Name -eq 'web') { foreach ($l in (Get-Listeners 3000)) { Stop-Tree ([int]$l.OwningProcess) $Why $WebChildMatch } }
            Clear-Process $c
        }
    }
}

function Invoke-StopFlag {
    # Returns 'exit' when the supervisor should stop, 'cycle' when it should check now, else $null.
    if (-not (Test-Path $stopFlag)) { return $null }
    $req = $null
    try { $req = Get-Content -Path $stopFlag -Raw | ConvertFrom-Json } catch { }
    Remove-Item -Path $stopFlag -Force -ErrorAction SilentlyContinue
    $action = 'stop'; $name = $null
    if ($req) { if ($req.action) { $action = [string]$req.action }; if ($req.component) { $name = [string]$req.component } }
    if (-not $name) {
        Write-Log "stop requested ($action): stopping owned worker, api, web, then the tunnel; Redis and WSL stay up"
        foreach ($k in @('worker', 'api', 'web')) { if (-not $Components[$k].Adopted) { Stop-Owned $Components[$k] 'supervisor stop' } }
        Stop-QuickTunnels 'supervisor stop'
        return 'exit'
    }
    if (-not $Components.Contains($name)) { Write-Log "stop.flag names unknown component '$name'; ignored"; return $null }
    $c = $Components[$name]
    Write-Log ("{0} requested for {1}" -f $action, $name)
    Stop-OneComponent $name "operator $action"
    if ($action -eq 'restart') {
        $c.Held = $false
        $c.ConsecutiveRestarts = 0
        $c.NextStartAt = [datetime]::MinValue
        $c.Fails = $c.FailLimit
        if ($name -eq 'tunnel') { $tunnel.Hostname = $null }
        Set-State $c 'restarting' 'operator restart'
    } else {
        $c.Held = $true
        Set-State $c 'held' 'stopped by operator (cip-supervisor-stop.ps1)'
    }
    return 'cycle'
}

# ---------------------------------------------------------------- main loop
$script:SupervisorStarted = Get-Date
$script:Cycle = 0
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor [System.Net.SecurityProtocolType]::Tls12
Set-Content -Path $pidFile -Value $PID -Encoding ASCII
Write-Log ("supervisor started, pid {0}, repo {1}; CIP_LISTING_LIVE_FETCH present={2}, CIP_LISTING_CAPTURE_SCHEDULE present={3}" -f `
    $PID, $repo, [bool]$env:CIP_LISTING_LIVE_FETCH, [bool]$env:CIP_LISTING_CAPTURE_SCHEDULE)

$exitRequested = $false
try {
    while (-not $exitRequested) {
        $script:Cycle++
        try {
            $all = Get-AllProcesses
            Invoke-WslKeeper $all
            Invoke-Redis
            Invoke-Worker $all
            Invoke-Api
            Invoke-Web
            Invoke-Tunnel (Get-AllProcesses)
        } catch {
            Write-Log ("cycle {0} error: {1} at {2}" -f $script:Cycle, $_, $_.InvocationInfo.PositionMessage)
        }
        Write-Status
        $deadline = (Get-Date).AddSeconds($CycleSeconds)
        while ((Get-Date) -lt $deadline) {
            $r = $null
            try { $r = Invoke-StopFlag } catch { Write-Log "stop.flag error: $_" }
            if ($r -eq 'exit') { $exitRequested = $true; break }
            if ($r -eq 'cycle') { Write-Status; break }
            Start-Sleep -Seconds 1
        }
    }
} finally {
    Write-Status 'stopped'
    Write-Log 'supervisor stopped'
    Remove-Item -Path $pidFile -Force -ErrorAction SilentlyContinue
    try { $mutex.ReleaseMutex() } catch { }
    $mutex.Dispose()
}
