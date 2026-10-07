# Show the CIP always-on supervisor state (N-0073): status.json, optionally the tail of the supervisor log,
# the listeners on the stack's ports and (with -Public) the public /login and /api/v1/auth/me codes.
#
# Usage:
#   .\scripts\cip-supervisor-status.ps1                 # status.json summary
#   .\scripts\cip-supervisor-status.ps1 -Log 40         # plus the last 40 supervisor log lines
#   .\scripts\cip-supervisor-status.ps1 -Raw            # status.json as written
#   .\scripts\cip-supervisor-status.ps1 -Ports -Public  # listeners on 3000/8001/6379/20241 and public HTTP codes
#   .\scripts\cip-supervisor-status.ps1 -LogFile worker.err.log -Log 30   # tail another log in the logs folder
param([int]$Log = 0, [string]$LogFile = 'supervisor.log', [switch]$Raw, [switch]$Ports, [switch]$Public, [switch]$Local)

$stateDir   = Join-Path $env:LOCALAPPDATA 'CIP\always-on'
$statusFile = Join-Path $stateDir 'status.json'
$logPath    = Join-Path (Join-Path $stateDir 'logs') $LogFile
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor [System.Net.SecurityProtocolType]::Tls12

function Get-Code {
    param([string]$Url, [switch]$Proxy)
    try {
        $r = [System.Net.HttpWebRequest]::Create($Url); $r.AllowAutoRedirect = $false; $r.Timeout = 15000
        if (-not $Proxy) { $r.Proxy = $null }
        $resp = $r.GetResponse(); $c = [int]$resp.StatusCode; $resp.Close(); return $c
    } catch {
        $e = $_.Exception; while ($e -and -not ($e -is [System.Net.WebException])) { $e = $e.InnerException }
        if ($e -and $e.Response) { $c = [int]$e.Response.StatusCode; $e.Response.Close(); return $c }
        return 0
    }
}

$ts = Get-Date -Format 'HH:mm:ss'
$s = $null
if (Test-Path $statusFile) {
    $text = Get-Content $statusFile -Raw
    if ($Raw) { $text }
    try { $s = $text | ConvertFrom-Json } catch { "status.json is not valid JSON: $_" }
} else {
    "No status.json yet ($statusFile)."
}
if ($s -and -not $Raw) {
    $age = [int]((Get-Date) - [datetime]$s.supervisor.heartbeat).TotalSeconds
    $live = [bool](Get-Process -Id ([int]$s.supervisor.pid) -ErrorAction SilentlyContinue)
    "$ts supervisor pid=$($s.supervisor.pid) alive=$live state=$($s.supervisor.state) cycle=$($s.supervisor.cycle) heartbeat_age=${age}s started=$($s.supervisor.started)"
    "  link=$($s.link.url) since=$($s.link.since) public_login=$($s.link.public_login) public_me=$($s.link.public_auth_me) checked=$($s.link.public_checked) closed=$($s.link.closed_reason)"
    "  env CIP_LISTING_LIVE_FETCH present=$($s.env.CIP_LISTING_LIVE_FETCH_present) CIP_LISTING_CAPTURE_SCHEDULE present=$($s.env.CIP_LISTING_CAPTURE_SCHEDULE_present)"
    foreach ($p in $s.components.PSObject.Properties) {
        "  {0,-7} {1,-10} pid={2,-6} adopted={3,-5} launches={4} last_healthy={5} {6}" -f $p.Name, $p.Value.state, $p.Value.pid, $p.Value.adopted, $p.Value.launches, $p.Value.last_healthy, $p.Value.detail
    }
}
if ($Ports) {
    foreach ($port in @(3000, 8001, 6379, 20241)) {
        foreach ($l in @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)) {
            $proc = Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $l.OwningProcess) -ErrorAction SilentlyContinue
            $name = '(no live process)'
            if ($proc) { $name = $proc.Name }
            "  listen {0}:{1} pid={2} {3}" -f $l.LocalAddress, $port, $l.OwningProcess, $name
        }
    }
    # Redis runs inside WSL: Windows forwards 127.0.0.1:6379 to it, but the forward does not appear in the
    # Windows listener table above. Ask Redis itself instead.
    $pong = 'no answer'
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect('127.0.0.1', 6379, $null, $null)
        if ($iar.AsyncWaitHandle.WaitOne(2000)) {
            $client.EndConnect($iar)
            $stream = $client.GetStream(); $stream.ReadTimeout = 2000
            $ping = [System.Text.Encoding]::ASCII.GetBytes("PING`r`n"); $stream.Write($ping, 0, $ping.Length)
            $buf = New-Object byte[] 64; $n = $stream.Read($buf, 0, 64)
            $pong = ([System.Text.Encoding]::ASCII.GetString($buf, 0, $n)).Trim()
        }
    } catch { $pong = "error: $($_.Exception.Message)" } finally { $client.Close() }
    "  redis 127.0.0.1:6379 PING -> $pong"
}
if ($Local) {
    "$ts local api /health=$(Get-Code 'http://127.0.0.1:8001/health') api /auth/me=$(Get-Code 'http://127.0.0.1:8001/api/v1/auth/me') web /login=$(Get-Code 'http://127.0.0.1:3000/login') web proxy /auth/me=$(Get-Code 'http://127.0.0.1:3000/api/v1/auth/me')"
}
if ($Public) {
    $hostName = $null
    if ($s -and $s.link.hostname) { $hostName = [string]$s.link.hostname }
    if ($hostName) {
        $base = 'https://' + $hostName
        "$ts public $base /login=$(Get-Code ($base + '/login') -Proxy) /api/v1/auth/me=$(Get-Code ($base + '/api/v1/auth/me') -Proxy)"
    } else {
        "$ts no hostname in status.json; public check skipped"
    }
}
if ($Log -gt 0) {
    if (Test-Path $logPath) { "---- last $Log lines of $LogFile"; Get-Content $logPath -Tail $Log }
    else { "No log at $logPath" }
}
