# Start CIP for a pilot and open a Cloudflare quick tunnel.
param([switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$cf = Join-Path $env:LOCALAPPDATA 'cloudflared\cloudflared.exe'

function Up($url) {
  try { (Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5).StatusCode }
  catch { if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 0 } }
}

if (-not (Select-String -Path apps\api\.env -Pattern '^CIP_AUTH_MODE=session' -Quiet)) {
  throw "apps/api/.env must contain CIP_AUTH_MODE=session before exposing CIP. Refusing."
}
if (-not (Test-Path $cf)) { throw "cloudflared not found. Install the official release first." }

if ((Up 'http://127.0.0.1:8001/health') -ne 200) {
  Start-Process pnpm -ArgumentList 'dev:api' -WindowStyle Minimized
  1..30 | ForEach-Object { if ((Up 'http://127.0.0.1:8001/health') -eq 200) { break }; Start-Sleep 2 }
}
if ((Up 'http://127.0.0.1:8001/api/v1/auth/me') -ne 401) {
  throw "API is not enforcing session auth (expected 401 on /auth/me without a token). Refusing."
}

$listening = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue
if (-not $listening) {
  if (-not $SkipBuild) {
    pnpm --filter @cip/web build
    if ($LASTEXITCODE -ne 0) { throw 'next build failed' }
  }
  Start-Process pnpm -ArgumentList '--filter','@cip/web','exec','next','start','-H','127.0.0.1','-p','3000' -WindowStyle Minimized
  1..30 | ForEach-Object { if ((Up 'http://127.0.0.1:3000/login') -eq 200) { break }; Start-Sleep 2 }
}
if ((Up 'http://127.0.0.1:3000/login') -ne 200) { throw 'web /login is not 200' }
if ((Up 'http://127.0.0.1:3000/api/v1/auth/me') -ne 401) { throw 'proxy is not enforcing auth' }

$log = Join-Path $env:TEMP 'cloudflared-cip.log'
$url = $null
if (-not (Get-Process cloudflared -ErrorAction SilentlyContinue)) {
  if (Test-Path $log) { Remove-Item $log -Force }
  Start-Process $cf -ArgumentList 'tunnel','--url','http://localhost:3000','--protocol','http2','--metrics','127.0.0.1:20241' -RedirectStandardError $log -WindowStyle Minimized
}
# The public address comes from the cloudflared metrics endpoint (N-0073); no log scraping.
foreach ($i in 1..40) {
  try {
    $qt = Invoke-RestMethod -Uri 'http://127.0.0.1:20241/quicktunnel' -TimeoutSec 5
    if ($qt.hostname) { $url = 'https://' + $qt.hostname }
  } catch { }
  if ($url) { break }
  Start-Sleep 2
}
if (-not $url) { throw "cloudflared did not report a quick-tunnel hostname on http://127.0.0.1:20241/quicktunnel" }
"CIP pilot is up."
"local: http://127.0.0.1:3000/login"
"public: $url/login"
