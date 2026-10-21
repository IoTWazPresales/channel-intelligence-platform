# GOV-008 (RUN-20261007-N0073-VER) plant-false probe of the tunnel auth gate. Audit helper, not product.
# Loads Test-SessionMode, Get-AuthOpenEvidence and Get-TunnelGate from scripts/cip-supervisor.ps1 by AST
# (without running its main loop), replaces Get-HttpStatus with a table of fake codes, and checks outcomes.
$src = Join-Path $PSScriptRoot '..\..\..\scripts\cip-supervisor.ps1'
$tokens = $null; $errs = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $src).Path, [ref]$tokens, [ref]$errs)
"parse errors: $($errs.Count)"
foreach ($name in @('Test-SessionMode', 'Get-AuthOpenEvidence', 'Get-TunnelGate')) {
    $fn = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name }, $true)
    if (-not $fn) { "MISSING function $name"; exit 2 }
    . ([scriptblock]::Create($fn.Extent.Text))
}

$tmp = Join-Path $env:TEMP ('n0073_ver_env_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmp | Out-Null
$script:envFile = Join-Path $tmp '.env'
$envFile = $script:envFile
$script:codes = @{}
function Get-HttpStatus { param([string]$Url, [int]$TimeoutSec = 5, [switch]$UseSystemProxy) if ($script:codes.ContainsKey($Url)) { return $script:codes[$Url] } return 0 }
$tunnel = @{ PublicMe = $null }
$savedMode = $env:CIP_AUTH_MODE
Remove-Item Env:CIP_AUTH_MODE -ErrorAction SilentlyContinue

$api = 'http://127.0.0.1:8001/api/v1/auth/me'; $login = 'http://127.0.0.1:3000/login'; $proxy = 'http://127.0.0.1:3000/api/v1/auth/me'
$fail = 0
function Check { param([string]$Label, $Actual, [bool]$ExpectNull)
    $ok = ($ExpectNull -and -not $Actual) -or (-not $ExpectNull -and $Actual)
    if (-not $ok) { $script:fail++ }
    "{0} {1} -> {2}" -f ($(if ($ok) { 'PASS' } else { 'FAIL' })), $Label, ($(if ($Actual) { $Actual } else { '(null)' }))
}
function Set-Codes { param($a, $l, $p) $script:codes = @{ $api = $a; $login = $l; $proxy = $p } }

Set-Content -Path $envFile -Value @('FOO=1', 'CIP_AUTH_MODE=session') -Encoding ASCII
Check 'Test-SessionMode .env session' (Test-SessionMode) $false
Set-Codes 401 200 401; $tunnel.PublicMe = 401
Check 'gate: all good (401/200/401)' (Get-TunnelGate) $true
Check 'evidence: all good' (Get-AuthOpenEvidence) $true
foreach ($code in @(500, 502, 503, 0)) {
    Set-Codes $code 200 401
    Check "evidence: API /auth/me $code is NOT auth-open" (Get-AuthOpenEvidence) $true
    Check "gate: API /auth/me $code refuses" (Get-TunnelGate) $false
    Set-Codes 401 200 $code
    Check "evidence: proxy /auth/me $code is NOT auth-open" (Get-AuthOpenEvidence) $true
    Check "gate: proxy /auth/me $code refuses" (Get-TunnelGate) $false
    Set-Codes 401 200 401; $tunnel.PublicMe = $code
    Check "evidence: public /auth/me $code is NOT auth-open" (Get-AuthOpenEvidence) $true
    $tunnel.PublicMe = 401
}
Set-Codes 200 200 401; Check 'evidence: API /auth/me 200 IS auth-open' (Get-AuthOpenEvidence) $false
Set-Codes 401 200 200; Check 'evidence: proxy /auth/me 200 IS auth-open' (Get-AuthOpenEvidence) $false
Set-Codes 401 200 401; $tunnel.PublicMe = 200; Check 'evidence: public /auth/me 200 IS auth-open' (Get-AuthOpenEvidence) $false; $tunnel.PublicMe = 401
Set-Codes 401 500 401; Check 'gate: web /login 500 refuses' (Get-TunnelGate) $false

Set-Content -Path $envFile -Value @('CIP_AUTH_MODE=dev') -Encoding ASCII
Check 'Test-SessionMode .env dev' (Test-SessionMode) $true
Set-Codes 401 200 401
Check 'gate: .env dev refuses' (Get-TunnelGate) $false
Check 'evidence: .env dev IS auth-open' (Get-AuthOpenEvidence) $false
Set-Content -Path $envFile -Value @('CIP_AUTH_MODE="session" # comment') -Encoding ASCII
Check 'Test-SessionMode quoted with comment' (Test-SessionMode) $false
Set-Content -Path $envFile -Value @('CIP_AUTH_MODE=session', 'CIP_AUTH_MODE=dev') -Encoding ASCII
Check 'Test-SessionMode last assignment dev wins' (Test-SessionMode) $true
Set-Content -Path $envFile -Value @('# CIP_AUTH_MODE=session') -Encoding ASCII
Check 'Test-SessionMode commented-out only' (Test-SessionMode) $true
Remove-Item $envFile
Check 'Test-SessionMode missing .env' (Test-SessionMode) $true
Set-Content -Path $envFile -Value @('CIP_AUTH_MODE=session') -Encoding ASCII
$env:CIP_AUTH_MODE = 'dev'
Check 'Test-SessionMode process env dev overrides .env session' (Test-SessionMode) $true
$env:CIP_AUTH_MODE = 'session'
Check 'Test-SessionMode process env session' (Test-SessionMode) $false

if ($savedMode) { $env:CIP_AUTH_MODE = $savedMode } else { Remove-Item Env:CIP_AUTH_MODE -ErrorAction SilentlyContinue }
Remove-Item -Recurse -Force $tmp
"failures: $fail"
if ($fail -gt 0) { exit 1 } else { exit 0 }
