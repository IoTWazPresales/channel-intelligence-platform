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

function Select-LiveWorkerBeat {
    # BACKLOG-245: readiness is a fresh worker heartbeat (written by a daemon thread, so a busy solo
    # worker still reports) whose pid is a running process. Input: the JSON line printed by
    # `python -m app.worker.liveness_check`. Returns the beat (node, pid, age_s) or $null.
    param([string]$Json, [scriptblock]$PidAlive)
    if (-not $Json) { return $null }
    $line = @($Json -split "`r?`n" | Where-Object { $_.Trim().StartsWith('{') } | Select-Object -Last 1)
    if (-not $line -or -not $line[0]) { return $null }
    try { $parsed = $line[0] | ConvertFrom-Json } catch { return $null }
    if (-not $parsed.ok) { return $null }
    foreach ($beat in @($parsed.beats)) {
        if ($null -ne $beat.pid -and (& $PidAlive ([int]$beat.pid))) { return $beat }
    }
    return $null
}

function New-DeployRecord {
    param([string]$Mode, [string]$Branch)
    return [ordered]@{
        started = (Get-Date).ToString('s'); mode = $Mode; branch = $Branch
        sha_before = $null; sha_after = $null; lockfile_changed = $null; install = 'not run'
        build = 'not run'; build_id_before = $null; build_id_after = $null
        restarts = @(); api_ready = $null; worker_heartbeat = $null; celery_ping = $null
        web_checks = @(); launches_first = $null; launches_second = $null; launch_problems = @()
        result = 'incomplete'; failure = $null; current_step = $null; failed_step = $null; steps = @(); finished = $null
    }
}

function Format-DeployRecord {
    # The block to paste into docs/memory/CURRENT.md (Wave 3 B2: output recorded in CURRENT.md).
    param($Record)
    $lines = @()
    $lines += "**Deploy $($Record.started) ($($Record.mode)):** $($Record.result). Branch ``$($Record.branch)`` ``$($Record.sha_before)`` -> ``$($Record.sha_after)``."
    $lines += "- Lockfile changed: $($Record.lockfile_changed); install: $($Record.install); build: $($Record.build); BUILD_ID ``$($Record.build_id_before)`` -> ``$($Record.build_id_after)``."
    foreach ($r in @($Record.restarts)) { $lines += "- Restart $($r.component): $($r.result) ($($r.detail))." }
    $lines += "- /health/ready: $($Record.api_ready); worker heartbeat: $($Record.worker_heartbeat); Celery ping (diagnostic): $($Record.celery_ping)."
    foreach ($w in @($Record.web_checks)) { $lines += "- web 3000 at $($w.at): HTTP $($w.code)." }
    $lines += "- Launch counts: first $(($Record.launches_first | ConvertTo-Json -Compress)), second $(($Record.launches_second | ConvertTo-Json -Compress)); problems: $(@($Record.launch_problems).Count)."
    if (@($Record.steps).Count -gt 0) {
        $lines += "- Steps: " + ((@($Record.steps) | ForEach-Object { "$($_.name) $($_.at)" }) -join ', ') + '.'
    }
    if ($Record.failure) {
        # Keep a multi-line failure (pnpm output tail, a list of dirty files) inside one bullet.
        $why = ("$($Record.failure)" -replace "`r?`n", "`n  ")
        if ($Record.failed_step) { $lines += "- Stopped at $($Record.failed_step): $why" } else { $lines += "- Stopped: $why" }
    }
    return ($lines -join "`n")
}

function Invoke-NativeCaptured {
    # Run a native command and capture stdout and stderr together without letting stderr text
    # become a terminating error. Under Windows PowerShell 5.1, `& exe 2>&1` with
    # $ErrorActionPreference = 'Stop' throws on the first stderr line (git pull writes progress
    # there), so the caller would stop half-way. Success is decided by the exit code only.
    #
    # A program that is not found never looks like success: it returns ExitCode 127 and an
    # Output saying so (a missing program leaves $LASTEXITCODE null or stale, so it is never
    # trusted). Any other failure to start the program is also a non-zero exit code.
    param([Parameter(Mandatory)][string]$FilePath, [string[]]$ArgumentList = @())
    $found = Get-Command -Name $FilePath -CommandType Application, ExternalScript -ErrorAction SilentlyContinue
    if (-not $found) {
        return [pscustomobject]@{ ExitCode = 127; Output = "program not found: $FilePath" }
    }
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $global:LASTEXITCODE = $null
    $lines = @()
    $code = $null
    try {
        $lines = & $FilePath @ArgumentList 2>&1 | ForEach-Object { "$_" }
        $code = $LASTEXITCODE
    } catch {
        $code = 126
        $lines = @("could not run ${FilePath}: $($_.Exception.Message)")
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($null -eq $code) {
        # The program ran but reported no exit code; do not call that success.
        $code = 125
        $lines = @($lines) + "no exit code was reported by $FilePath"
    }
    return [pscustomobject]@{ ExitCode = $code; Output = (($lines | Out-String).Trim()) }
}

function Invoke-NativeStep {
    # One native step of the deploy (pnpm install, pnpm build): run through Invoke-NativeCaptured,
    # print what it said, and throw a clear message when it failed or the program is missing.
    # Output is shown when the step ends (it is captured, not streamed).
    param(
        [Parameter(Mandatory)][string]$Description,
        [Parameter(Mandatory)][string]$FilePath,
        [string[]]$ArgumentList = @()
    )
    $r = Invoke-NativeCaptured -FilePath $FilePath -ArgumentList $ArgumentList
    if ($r.Output) { Write-Host $r.Output }
    if ($r.ExitCode -ne 0) {
        $tail = (@($r.Output -split "`r?`n") | Select-Object -Last 20) -join "`n"
        throw "$Description failed (exit $($r.ExitCode)): $tail"
    }
    return $r.Output
}

function Test-DeployPrerequisites {
    # Preflight: every program the deploy runs must exist before anything is pulled, built or restarted.
    # Throws "required program not found: X" for the first missing one (git, pnpm, then the API venv python).
    param([string]$Git = 'git', [string]$Pnpm = 'pnpm', [Parameter(Mandatory)][string]$Python)
    foreach ($p in @($Git, $Pnpm, $Python)) {
        $found = Get-Command -Name $p -CommandType Application, ExternalScript -ErrorAction SilentlyContinue
        if (-not $found) { throw "required program not found: $p" }
    }
}

function Get-InstallDecision {
    # Whether pnpm install must run. A marker left by an earlier run that started the install and did not
    # finish it forces the install even when the lockfile is unchanged between the two SHAs (a re-run after
    # a failed install has sha_before == sha_after, so the lockfile diff alone would skip it).
    param([bool]$LockfileChanged, [bool]$MarkerExists)
    if ($MarkerExists) { return [pscustomobject]@{ Run = $true; Reason = 'forced: a previous pnpm install did not finish' } }
    if ($LockfileChanged) { return [pscustomobject]@{ Run = $true; Reason = 'lockfile changed' } }
    return [pscustomobject]@{ Run = $false; Reason = 'skipped (lockfile unchanged)' }
}

function Invoke-GuardedInstall {
    # Write the marker before the install and remove it only after the install succeeded. If Action throws,
    # the marker stays, so the next run forces the install (Get-InstallDecision).
    param([Parameter(Mandatory)][string]$MarkerPath, [Parameter(Mandatory)][scriptblock]$Action)
    $dir = Split-Path -Parent $MarkerPath
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $enc = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($MarkerPath, "pnpm install started $((Get-Date).ToString('s'))", $enc)
    $null = & $Action
    Remove-Item -LiteralPath $MarkerPath -Force
}

function Set-DeployStep {
    # Name the step now running, so a failure can say where it stopped, and note when it began.
    param($Record, [string]$Name)
    $Record.current_step = $Name
    $Record.steps += [ordered]@{ name = $Name; at = (Get-Date).ToString('s') }
}

function Set-DeployFailure {
    param($Record, [string]$Why)
    $Record.result = 'FAILED'
    $Record.failure = $Why
    $Record.failed_step = $Record.current_step
}

function Invoke-DeployGuarded {
    # Run the execute path so that any terminating error still ends with the failure recorded and the
    # record saved (the Save block runs in finally). Returns $true only when Body completed.
    param([Parameter(Mandatory)]$Record, [Parameter(Mandatory)][scriptblock]$Body, [Parameter(Mandatory)][scriptblock]$Save)
    $ok = $false
    try {
        $null = & $Body
        $ok = $true
    } catch {
        if ($Record.result -ne 'FAILED') { Set-DeployFailure $Record "$($_.Exception.Message)" }
        Write-Host "DEPLOY STOPPED$(if ($Record.failed_step) { " at $($Record.failed_step)" }): $($Record.failure)"
    } finally {
        try { $null = & $Save } catch {
            # A deploy whose record is lost does not pass: the record is a deliverable, so the exit code is non-zero.
            Write-Host "COULD NOT SAVE THE DEPLOY RECORD: $($_.Exception.Message)$(if ($ok) { ' (the deploy steps passed, but the exit code is 1 because the record is missing)' })"
            $ok = $false
        }
    }
    return $ok
}

