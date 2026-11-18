# Batch deploy after a merged batch (Wave 3 B2; orchestrator brief section 8).
#
# Default is a PLAN: it reads git state and prints the steps it would run. Nothing is pulled, built or
# restarted unless -Execute is given. Run -Execute only when a deploy is authorized.
#
#   .\scripts\cip-deploy.ps1                       # plan only (no changes)
#   .\scripts\cip-deploy.ps1 -Execute              # pull --ff-only, install if the lockfile changed, build,
#                                                  # restart api, worker, web one at a time, verify
#   .\scripts\cip-deploy.ps1 -Execute -SkipPull    # deploy what is checked out (no pull)
#
# Steps with -Execute, stopping at the first failure:
#   1. Refuse a linked worktree (the supervisor runs the primary checkout), a dirty tracked working tree or a
#      detached HEAD. Record branch and SHA before.
#   2. git pull --ff-only (never a merge or rebase). Record SHA after.
#   3. pnpm install --frozen-lockfile only when pnpm-lock.yaml changed between the two SHAs.
#   4. pnpm --filter @cip/web build. Record apps/web/.next/BUILD_ID before and after (must change).
#   5. For api, worker (includes beat), web in that order: scripts\cip-supervisor-stop.ps1 -Component <c> -Restart,
#      then wait until status.json shows it healthy with a launch after the request.
#   6. GET http://127.0.0.1:8001/health/ready must be 200; `celery inspect ping` must get a reply.
#   7. GET http://127.0.0.1:3000/login twice, -StableSeconds apart (default 60), both answering, with every
#      component's launch count unchanged between the two checks.
# With -Execute the record is written as JSON and as a CURRENT.md block under %LOCALAPPDATA%\CIP\deploys\.
# Exit code 0 only when every step passed (or, in plan mode, when the plan was printed).
param(
    [switch]$Execute,
    [switch]$SkipPull,
    [int]$StableSeconds = 60,
    [int]$HealthyTimeoutSeconds = 240,
    [string]$ApiBase = 'http://127.0.0.1:8001',
    [string]$WebBase = 'http://127.0.0.1:3000'
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'cip-deploy-lib.ps1')

$repo       = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$apiDir     = Join-Path $repo 'apps\api'
$py         = Join-Path $apiDir '.venv\Scripts\python.exe'
$buildIdFile = Join-Path $repo 'apps\web\.next\BUILD_ID'
$stateDir   = Join-Path $env:LOCALAPPDATA 'CIP\always-on'
$statusFile = Join-Path $stateDir 'status.json'
$stopScript = Join-Path $PSScriptRoot 'cip-supervisor-stop.ps1'
$recordDir  = Join-Path $env:LOCALAPPDATA 'CIP\deploys'
$components = @('wsl', 'redis', 'worker', 'api', 'web', 'tunnel')

function Invoke-Git {
    param([string[]]$GitArgs)
    $r = Invoke-NativeCaptured -FilePath 'git' -ArgumentList (@('-C', $repo) + $GitArgs)
    if ($r.ExitCode -ne 0) { throw "git $($GitArgs -join ' ') failed: $($r.Output)" }
    return $r.Output
}

function Read-Status {
    if (-not (Test-Path $statusFile)) { return $null }
    try { return (Get-Content $statusFile -Raw | ConvertFrom-Json) } catch { return $null }
}

function Read-BuildId {
    if (Test-Path $buildIdFile) { return (Get-Content $buildIdFile -Raw).Trim() }
    return $null
}

function Get-HttpCode {
    param([string]$Url)
    try {
        $r = [System.Net.HttpWebRequest]::Create($Url); $r.AllowAutoRedirect = $false; $r.Timeout = 15000; $r.Proxy = $null
        $resp = $r.GetResponse(); $c = [int]$resp.StatusCode; $resp.Close(); return $c
    } catch {
        $e = $_.Exception; while ($e -and -not ($e -is [System.Net.WebException])) { $e = $e.InnerException }
        if ($e -and $e.Response) { $c = [int]$e.Response.StatusCode; $e.Response.Close(); return $c }
        return 0
    }
}

$record = New-DeployRecord -Mode ($(if ($Execute) { 'execute' } else { 'plan' })) -Branch $null

function Save-Record {
    $record.finished = (Get-Date).ToString('s')
    New-Item -ItemType Directory -Path $recordDir -Force | Out-Null
    $stamp = (Get-Date).ToString('yyyyMMdd-HHmmss')
    $enc = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText((Join-Path $recordDir "deploy-$stamp.json"), ($record | ConvertTo-Json -Depth 6), $enc)
    $block = Format-DeployRecord $record
    [System.IO.File]::WriteAllText((Join-Path $recordDir "deploy-$stamp.current.md"), $block, $enc)
    Write-Host ''
    Write-Host '---- CURRENT.md block ----'
    Write-Host $block
    Write-Host "Record: $(Join-Path $recordDir "deploy-$stamp.json")"
}

function Stop-Deploy {
    param([string]$Why)
    $record.result = 'FAILED'; $record.failure = $Why
    Save-Record
    Write-Host "DEPLOY STOPPED: $Why"
    exit 1
}

# 1. Preconditions
$branch = Invoke-Git @('rev-parse', '--abbrev-ref', 'HEAD')
$record.branch = $branch
$record.sha_before = Invoke-Git @('rev-parse', 'HEAD')
$record.build_id_before = Read-BuildId
$dirty = Invoke-Git @('status', '--porcelain', '--untracked-files=no')
# A linked worktree has a .git file (gitdir: pointer); the primary checkout has a .git folder.
$linkedWorktree = Test-Path -LiteralPath (Join-Path $repo '.git') -PathType Leaf

if (-not $Execute) {
    Write-Host "PLAN ONLY (no changes). Repo $repo, branch $branch at $($record.sha_before)."
    if ($linkedWorktree) { Write-Host '  ! linked worktree: -Execute would refuse (run from the primary checkout).' }
    if ($branch -eq 'HEAD') { Write-Host '  ! detached HEAD: -Execute would refuse.' }
    if ($dirty) { Write-Host '  ! tracked changes present: -Execute would refuse.' }
    if ($SkipPull) { Write-Host '  1. no pull (-SkipPull)' } else { Write-Host '  1. git pull --ff-only' }
    Write-Host '  2. pnpm install --frozen-lockfile, only if pnpm-lock.yaml changed in the pull'
    Write-Host "  3. pnpm --filter @cip/web build (BUILD_ID now: $($record.build_id_before))"
    $n = 4
    foreach ($c in (Get-DeployRestartOrder)) { Write-Host "  $n. restart $c via cip-supervisor-stop.ps1, wait for healthy"; $n++ }
    Write-Host "  $n. $ApiBase/health/ready = 200 and celery inspect ping replies"; $n++
    Write-Host "  $n. $WebBase/login answers twice $StableSeconds s apart with unchanged launch counts"
    exit 0
}

if ($linkedWorktree) { Stop-Deploy 'this is a linked worktree; the supervisor runs the primary checkout' }
if ($branch -eq 'HEAD') { Stop-Deploy 'detached HEAD; check out the trunk branch first' }
if ($dirty) { Stop-Deploy "tracked changes in the working tree:`n$dirty" }

# 2. Pull
if ($SkipPull) {
    $record.sha_after = $record.sha_before
} else {
    Write-Host 'git pull --ff-only'
    try { Invoke-Git @('pull', '--ff-only') | Write-Host } catch { Stop-Deploy "$_" }
    $record.sha_after = Invoke-Git @('rev-parse', 'HEAD')
}

# 3. Install only when the lockfile changed
$changed = @()
if ($record.sha_after -ne $record.sha_before) {
    $changed = (Invoke-Git @('diff', '--name-only', $record.sha_before, $record.sha_after)) -split "`n"
}
$record.lockfile_changed = (Test-LockfileChanged $changed)
if ($record.lockfile_changed) {
    Write-Host 'pnpm install --frozen-lockfile'
    Push-Location $repo
    try { & pnpm install --frozen-lockfile; if ($LASTEXITCODE -ne 0) { throw "exit $LASTEXITCODE" } ; $record.install = 'ok' }
    catch { $record.install = "failed: $_"; Pop-Location; Stop-Deploy 'pnpm install failed' }
    Pop-Location
} else { $record.install = 'skipped (lockfile unchanged)' }

# 4. Build
Write-Host 'pnpm --filter @cip/web build'
Push-Location $repo
try { & pnpm --filter '@cip/web' build; if ($LASTEXITCODE -ne 0) { throw "exit $LASTEXITCODE" }; $record.build = 'ok' }
catch { $record.build = "failed: $_"; Pop-Location; Stop-Deploy 'web build failed' }
Pop-Location
$record.build_id_after = Read-BuildId
if (-not $record.build_id_after -or $record.build_id_after -eq $record.build_id_before) {
    Stop-Deploy 'BUILD_ID did not change after the build'
}

# 5. Ordered restarts
foreach ($c in (Get-DeployRestartOrder)) {
    $asked = Get-Date
    Write-Host "restart $c"
    try { & $stopScript -Component $c -Restart | Write-Host } catch {
        $record.restarts += [ordered]@{ component = $c; result = 'failed'; detail = "$_" }
        Stop-Deploy "restart request for $c failed"
    }
    $deadline = $asked.AddSeconds($HealthyTimeoutSeconds)
    $ok = $false
    while ((Get-Date) -lt $deadline) {
        if (Test-ComponentHealthy (Read-Status) $c $asked) { $ok = $true; break }
        Start-Sleep -Seconds 3
    }
    $st = Read-Status
    $detail = $null
    if ($st -and $st.components.$c) { $detail = "state=$($st.components.$c.state) launches=$($st.components.$c.launches)" }
    if (-not $ok) {
        $record.restarts += [ordered]@{ component = $c; result = 'not healthy'; detail = $detail }
        Stop-Deploy "$c was not healthy within $HealthyTimeoutSeconds s"
    }
    $record.restarts += [ordered]@{ component = $c; result = 'healthy'; detail = $detail }
}

# 6. Readiness and Celery
$ready = Get-HttpCode "$ApiBase/health/ready"
$record.api_ready = $ready
if ($ready -ne 200) { Stop-Deploy "/health/ready answered $ready" }
Push-Location $apiDir
$ping = (Invoke-NativeCaptured -FilePath $py -ArgumentList @('-m', 'celery', '-A', 'app.worker.celery_app', 'inspect', 'ping', '--timeout', '10')).Output
Pop-Location
$record.celery_ping = $(if (Test-CeleryPingOutput $ping) { 'replied' } else { 'no reply' })
if ($record.celery_ping -ne 'replied') { Stop-Deploy "celery ping: $($ping.Trim())" }

# 7. Web answering twice with unchanged launch counts
$first = Get-HttpCode "$WebBase/login"
$record.web_checks += [ordered]@{ at = (Get-Date).ToString('s'); code = $first }
$record.launches_first = Get-ComponentLaunches (Read-Status) $components
Start-Sleep -Seconds $StableSeconds
$second = Get-HttpCode "$WebBase/login"
$record.web_checks += [ordered]@{ at = (Get-Date).ToString('s'); code = $second }
$record.launches_second = Get-ComponentLaunches (Read-Status) $components
foreach ($code in @($first, $second)) { if ($code -lt 200 -or $code -ge 400) { Stop-Deploy "web answered $code" } }
$record.launch_problems = Compare-LaunchCounts $record.launches_first $record.launches_second
if (@($record.launch_problems).Count -gt 0) { Stop-Deploy ("launch counts not stable: " + ($record.launch_problems -join '; ')) }

$record.result = 'OK'
Save-Record
exit 0