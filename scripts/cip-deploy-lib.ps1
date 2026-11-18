# Pure helpers for scripts/cip-deploy.ps1 (Wave 3 B2). No side effects: every function takes its
# inputs as arguments so scripts/cip-deploy.Tests.ps1 can check them without git, pnpm or services.

$script:DeployRestartOrder = @('api', 'worker', 'web')

function Get-DeployRestartOrder {
    # API first (migration-aware code paths answer /health/ready), then the worker (includes beat), then web.
    return $script:DeployRestartOrder
}

function Test-LockfileChanged {
    param([string[]]$ChangedPaths)
    foreach ($p in @($ChangedPaths)) {
        if (-not $p) { continue }
        $n = $p.Trim().Replace('\', '/')
        if ($n -eq 'pnpm-lock.yaml' -or $n.EndsWith('/pnpm-lock.yaml')) { return $true }
    }
    return $false
}

function Get-ComponentLaunches {
    # status.json (as parsed by ConvertFrom-Json) -> ordered name => launch count.
    param($Status, [string[]]$Names)
    $out = [ordered]@{}
    foreach ($n in $Names) {
        $c = $null
        if ($Status -and $Status.components) { $c = $Status.components.$n }
        if ($c -and $null -ne $c.launches) { $out[$n] = [int]$c.launches } else { $out[$n] = $null }
    }
    return $out
}

function Compare-LaunchCounts {
    # Stable means every component has a known count and none changed. Returns a list of problems.
    param($Before, $After)
    $problems = @()
    foreach ($k in $Before.Keys) {
        $b = $Before[$k]; $a = $After[$k]
        if ($null -eq $b -or $null -eq $a) { $problems += "$k launch count unknown"; continue }
        if ($a -ne $b) { $problems += "$k relaunched ($b -> $a)" }
    }
    return ,$problems
}

function Test-ComponentHealthy {
    param($Status, [string]$Name, $NotBefore)
    if (-not $Status -or -not $Status.components) { return $false }
    $c = $Status.components.$Name
    if (-not $c -or $c.state -ne 'healthy') { return $false }
    if ($NotBefore) {
        if (-not $c.last_start) { return $false }
        if (([datetime]$c.last_start) -lt ([datetime]$NotBefore).AddSeconds(-1)) { return $false }
    }
    return $true
}

function Test-CeleryPingOutput {
    # `celery inspect ping` prints "-> worker@host: OK" and "pong" lines; "Error: No nodes replied" otherwise.
    param([string]$Text)
    if (-not $Text) { return $false }
    if ($Text -match 'No nodes replied') { return $false }
    return ($Text -match '(?im)^\s*->\s*\S+:\s*OK\b') -or ($Text -match '(?i)\bpong\b')
}

function New-DeployRecord {
    param([string]$Mode, [string]$Branch)
    return [ordered]@{
        started = (Get-Date).ToString('s'); mode = $Mode; branch = $Branch
        sha_before = $null; sha_after = $null; lockfile_changed = $null; install = 'not run'
        build = 'not run'; build_id_before = $null; build_id_after = $null
        restarts = @(); api_ready = $null; celery_ping = $null
        web_checks = @(); launches_first = $null; launches_second = $null; launch_problems = @()
        result = 'incomplete'; failure = $null; finished = $null
    }
}

function Format-DeployRecord {
    # The block to paste into docs/memory/CURRENT.md (Wave 3 B2: output recorded in CURRENT.md).
    param($Record)
    $lines = @()
    $lines += "**Deploy $($Record.started) ($($Record.mode)):** $($Record.result). Branch ``$($Record.branch)`` ``$($Record.sha_before)`` -> ``$($Record.sha_after)``."
    $lines += "- Lockfile changed: $($Record.lockfile_changed); install: $($Record.install); build: $($Record.build); BUILD_ID ``$($Record.build_id_before)`` -> ``$($Record.build_id_after)``."
    foreach ($r in @($Record.restarts)) { $lines += "- Restart $($r.component): $($r.result) ($($r.detail))." }
    $lines += "- /health/ready: $($Record.api_ready); Celery ping: $($Record.celery_ping)."
    foreach ($w in @($Record.web_checks)) { $lines += "- web 3000 at $($w.at): HTTP $($w.code)." }
    $lines += "- Launch counts: first $(($Record.launches_first | ConvertTo-Json -Compress)), second $(($Record.launches_second | ConvertTo-Json -Compress)); problems: $(@($Record.launch_problems).Count)."
    if ($Record.failure) { $lines += "- Stopped: $($Record.failure)" }
    return ($lines -join "`n")
}

function Invoke-NativeCaptured {
    # Run a native command and capture stdout and stderr together without letting stderr text
    # become a terminating error. Under Windows PowerShell 5.1, `& exe 2>&1` with
    # $ErrorActionPreference = 'Stop' throws on the first stderr line (git pull writes progress
    # there), so the caller would stop half-way. Success is decided by the exit code only.
    param([Parameter(Mandatory)][string]$FilePath, [string[]]$ArgumentList = @())
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $lines = & $FilePath @ArgumentList 2>&1 | ForEach-Object { "$_" }
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    return [pscustomobject]@{ ExitCode = $code; Output = (($lines | Out-String).Trim()) }
}

