# N-0073 validation probe (implementation run). Read-only HTTP checks and status.json summary.
param([switch]$Public, [switch]$Status)
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor [System.Net.SecurityProtocolType]::Tls12
function Code($url, [switch]$Proxy) {
  try {
    $r = [System.Net.HttpWebRequest]::Create($url); $r.AllowAutoRedirect = $false; $r.Timeout = 15000
    if (-not $Proxy) { $r.Proxy = $null }
    $resp = $r.GetResponse(); $c = [int]$resp.StatusCode; $resp.Close(); return $c
  } catch {
    $e = $_.Exception; while ($e -and -not ($e -is [System.Net.WebException])) { $e = $e.InnerException }
    if ($e -and $e.Response) { $c = [int]$e.Response.StatusCode; $e.Response.Close(); return $c }
    return 0
  }
}
$ts = Get-Date -Format 'HH:mm:ss'
if ($Status) {
  $s = Get-Content (Join-Path $env:LOCALAPPDATA 'CIP\always-on\status.json') -Raw | ConvertFrom-Json
  "$ts supervisor pid=$($s.supervisor.pid) state=$($s.supervisor.state) cycle=$($s.supervisor.cycle) heartbeat=$($s.supervisor.heartbeat) link=$($s.link.url) public_login=$($s.link.public_login) public_me=$($s.link.public_auth_me)"
  foreach ($p in $s.components.PSObject.Properties) { "  {0,-7} {1,-10} pid={2,-6} adopted={3,-5} launches={4} {5}" -f $p.Name, $p.Value.state, $p.Value.pid, $p.Value.adopted, $p.Value.launches, $p.Value.detail }
}
if ($Public) {
  $qt = Invoke-RestMethod -Uri 'http://127.0.0.1:20241/quicktunnel' -TimeoutSec 5
  $base = 'https://' + $qt.hostname
  "$ts host=$($qt.hostname) public /login=$(Code ($base + '/login') -Proxy) public /api/v1/auth/me=$(Code ($base + '/api/v1/auth/me') -Proxy)"
}
"$ts local api /health=$(Code 'http://127.0.0.1:8001/health') api /auth/me=$(Code 'http://127.0.0.1:8001/api/v1/auth/me') web /login=$(Code 'http://127.0.0.1:3000/login') web proxy /auth/me=$(Code 'http://127.0.0.1:3000/api/v1/auth/me')"
