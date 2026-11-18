# Nightly cip backup with verification, retention, status files and a periodic disposable restore
# (Wave 3 Phase C; docs/BACKUP_AND_DR.md). Meant to run from Windows Task Scheduler
# (scripts/ops/install_backup_task.ps1), but safe to run by hand.
#
# The database URL is read from an environment variable (default CIP_BACKUP_DATABASE_URL), so no
# password is written into the scheduled task. The restore target, also from an environment variable
# (default CIP_RESTORE_SMOKE_URL), must be a disposable database; restore_cip_smoke.ps1 refuses cip.
#
#   .\scripts\ops\nightly_backup_cip.ps1                       # backup, verify, prune, restore if due
#   .\scripts\ops\nightly_backup_cip.ps1 -NoRestore            # never restore on this run
#   .\scripts\ops\nightly_backup_cip.ps1 -PlanOnly             # print what would run and be pruned
#
# Visible results: <OutDir>\last_backup.json and <OutDir>\last_restore.json (read by GET /ops/overview),
# <OutDir>\nightly_backup.log, and the exit code (Task Scheduler "Last Run Result"): 0 = all ok.
param(
    [string]$DatabaseUrlEnv = 'CIP_BACKUP_DATABASE_URL',
    [string]$RestoreTargetUrlEnv = 'CIP_RESTORE_SMOKE_URL',
    [string]$OutDir = (Join-Path $env:LOCALAPPDATA 'CIP\backups'),
    [int]$KeepDaily = 14,
    [int]$KeepWeekly = 8,
    [int]$RestoreEveryDays = 7,
    [string]$PgBin = 'C:\Program Files\PostgreSQL\18\bin',
    [switch]$NoRestore,
    [switch]$PlanOnly
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'nightly_backup_lib.ps1')

$enc = New-Object System.Text.UTF8Encoding($false)
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
$logFile = Join-Path $OutDir 'nightly_backup.log'
$backupStatus = Join-Path $OutDir 'last_backup.json'
$restoreStatus = Join-Path $OutDir 'last_restore.json'

function Write-Log {
    param([string]$Msg)
    $line = '{0} {1}' -f (Get-Date).ToString('s'), $Msg
    Write-Host $line
    [System.IO.File]::AppendAllText($logFile, $line + "`r`n", $enc)
}

function Write-Json {
    param([string]$Path, $Obj)
    $tmp = "$Path.tmp"
    [System.IO.File]::WriteAllText($tmp, ($Obj | ConvertTo-Json -Depth 5), $enc)
    Move-Item -LiteralPath $tmp -Destination $Path -Force
}

function Read-Json {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $null }
    try { return (Get-Content $Path -Raw | ConvertFrom-Json) } catch { return $null }
}

$existing = @(Get-ChildItem -LiteralPath $OutDir -Filter 'cip_*.dump' -File -ErrorAction SilentlyContinue | ForEach-Object { $_.Name })
if ($PlanOnly) {
    Write-Host "PLAN ONLY. Out dir $OutDir; database URL from `$env:$DatabaseUrlEnv (set: $([bool][Environment]::GetEnvironmentVariable($DatabaseUrlEnv)))."
    Write-Host "  1. backup_cip.ps1 -> $OutDir, then pg_restore --list must read the dump"
    $wouldDelete = Select-DumpsToDelete -Names $existing -KeepDaily $KeepDaily -KeepWeekly $KeepWeekly
    Write-Host "  2. retention: keep $KeepDaily daily + $KeepWeekly weekly; of $($existing.Count) dumps now, would delete $(@($wouldDelete).Count): $(@($wouldDelete) -join ', ')"
    $due = Test-RestoreDue (Read-Json $restoreStatus) (Get-Date) $RestoreEveryDays
    Write-Host "  3. disposable restore due: $due (every $RestoreEveryDays days; target from `$env:$RestoreTargetUrlEnv, set: $([bool][Environment]::GetEnvironmentVariable($RestoreTargetUrlEnv)))"
    exit 0
}

$record = [ordered]@{
    result = 'failed'; started = (Get-Date).ToString('s'); finished = $null; path = $null; bytes = $null
    verified = $false; pruned = @(); error = $null; restore = 'not run'
}
$exitCode = 0
try {
    $url = [Environment]::GetEnvironmentVariable($DatabaseUrlEnv)
    if ([string]::IsNullOrWhiteSpace($url)) { throw "environment variable $DatabaseUrlEnv is not set" }
    Write-Log 'backup start'
    $out = & (Join-Path $PSScriptRoot 'backup_cip.ps1') -DatabaseUrl $url -OutDir $OutDir -PgBin $PgBin 6>&1 | Out-String
    $dump = ($out -split "`r?`n" | Where-Object { $_ -match '\.dump\s*$' } | Select-Object -Last 1).Trim()
    if (-not $dump -or -not (Test-Path -LiteralPath $dump)) { throw 'backup_cip.ps1 did not report a dump file' }
    $record.path = $dump
    $record.bytes = (Get-Item -LiteralPath $dump).Length
    if ($record.bytes -le 0) { throw "dump is empty: $dump" }

    $pgRestore = Join-Path $PgBin 'pg_restore.exe'
    if (-not (Test-Path $pgRestore)) { $c = Get-Command pg_restore -ErrorAction SilentlyContinue; if ($c) { $pgRestore = $c.Source } else { throw 'pg_restore not found' } }
    $listing = & $pgRestore --list $dump 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0 -or -not (Test-DumpListing $listing)) { throw "pg_restore --list could not read $dump" }
    $record.verified = $true

    $names = @(Get-ChildItem -LiteralPath $OutDir -Filter 'cip_*.dump' -File | ForEach-Object { $_.Name })
    foreach ($n in (Select-DumpsToDelete -Names $names -KeepDaily $KeepDaily -KeepWeekly $KeepWeekly)) {
        Remove-Item -LiteralPath (Join-Path $OutDir $n) -Force
        $record.pruned += $n
    }
    $record.result = 'ok'
    Write-Log "backup ok $dump bytes=$($record.bytes) pruned=$(@($record.pruned).Count)"
} catch {
    $record.error = "$_"
    $exitCode = 1
    Write-Log "BACKUP FAILED: $_"
}

if ($record.result -eq 'ok' -and -not $NoRestore) {
    $last = Read-Json $restoreStatus
    $target = [Environment]::GetEnvironmentVariable($RestoreTargetUrlEnv)
    if ([string]::IsNullOrWhiteSpace($target)) {
        $record.restore = "not configured ($RestoreTargetUrlEnv unset)"
    } elseif (-not (Test-DisposableRestoreTarget $target $url)) {
        # Review fix: never let the schedule wipe a real database (cip_test, the source, ...).
        $record.restore = "refused: $RestoreTargetUrlEnv must name a disposable database (name containing restore, smoke, scratch or disposable; not cip, cip_test, postgres or the backed-up database)"
        $exitCode = 1
        Write-Log "RESTORE REFUSED: target database '$(Get-DatabaseName $target)' is not a disposable name"
    } elseif (-not (Test-RestoreDue $last (Get-Date) $RestoreEveryDays)) {
        $record.restore = 'not due'
    } else {
        $r = [ordered]@{ result = 'failed'; started = (Get-Date).ToString('s'); finished = $null; dump = $record.path; detail = $null }
        try {
            Write-Log 'disposable restore start'
            $rout = & (Join-Path $PSScriptRoot 'restore_cip_smoke.ps1') -DumpPath $record.path -TargetUrl $target -PgBin $PgBin 6>&1 | Out-String
            $ok = ($rout -split "`r?`n" | Where-Object { $_ -match '^RESTORE_SMOKE_OK ' } | Select-Object -Last 1)
            if (-not $ok) { throw 'restore_cip_smoke.ps1 did not print RESTORE_SMOKE_OK' }
            $r.detail = $ok.Trim(); $r.result = 'ok'
            Write-Log "restore ok: $($r.detail)"
        } catch {
            $r.detail = "$_"; $exitCode = 1
            Write-Log "RESTORE FAILED: $_"
        }
        $r.finished = (Get-Date).ToString('s')
        Write-Json $restoreStatus $r
        $record.restore = $r.result
    }
}

$record.finished = (Get-Date).ToString('s')
Write-Json $backupStatus $record
exit $exitCode