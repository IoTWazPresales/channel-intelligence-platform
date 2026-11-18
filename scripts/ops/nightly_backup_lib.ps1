# Pure helpers for scripts/ops/nightly_backup_cip.ps1 (Wave 3 Phase C). No side effects, so
# scripts/ops/nightly_backup_cip.Tests.ps1 can check them without Postgres or the file system.

function Get-DumpStamp {
    # cip_YYYYMMDD_HHMMSS.dump (backup_cip.ps1's name) -> [datetime], or $null for any other name.
    param([string]$Name)
    if ($Name -match '^cip_(\d{8})_(\d{6})\.dump$') {
        return [datetime]::ParseExact($matches[1] + $matches[2], 'yyyyMMddHHmmss', [Globalization.CultureInfo]::InvariantCulture)
    }
    return $null
}

function Get-IsoWeekKey {
    param([datetime]$Date)
    $cal = [Globalization.CultureInfo]::InvariantCulture.Calendar
    # ISO 8601 week: shift to the Thursday of the same week, then take the year and week of that day.
    $dow = [int]$Date.DayOfWeek; if ($dow -eq 0) { $dow = 7 }
    $thu = $Date.Date.AddDays(4 - $dow)
    $week = $cal.GetWeekOfYear($thu, [Globalization.CalendarWeekRule]::FirstFourDayWeek, [DayOfWeek]::Monday)
    return ('{0}-W{1:D2}' -f $thu.Year, $week)
}

function Select-DumpsToDelete {
    # Keep the newest -KeepDaily dumps (one per calendar day, newest of that day) and the newest dump of
    # each of the newest -KeepWeekly ISO weeks. Everything else that matches the dump name is deleted.
    # Files with other names are never selected. The newest dump is always kept.
    param([string[]]$Names, [int]$KeepDaily = 14, [int]$KeepWeekly = 8)
    $dumps = @()
    foreach ($n in @($Names)) {
        $t = Get-DumpStamp $n
        if ($t) { $dumps += [pscustomobject]@{ Name = $n; At = $t } }
    }
    if ($dumps.Count -eq 0) { return ,@() }
    $sorted = @($dumps | Sort-Object At -Descending)
    $keep = @{}
    $keep[$sorted[0].Name] = $true
    $days = @{}
    foreach ($d in $sorted) {
        $k = $d.At.ToString('yyyy-MM-dd')
        if (-not $days.ContainsKey($k) -and $days.Count -lt $KeepDaily) { $days[$k] = $true; $keep[$d.Name] = $true }
    }
    $weeks = @{}
    foreach ($d in $sorted) {
        $k = Get-IsoWeekKey $d.At
        if (-not $weeks.ContainsKey($k) -and $weeks.Count -lt $KeepWeekly) { $weeks[$k] = $true; $keep[$d.Name] = $true }
    }
    $delete = @($sorted | Where-Object { -not $keep.ContainsKey($_.Name) } | ForEach-Object { $_.Name })
    return ,$delete
}

function Test-RestoreDue {
    # A disposable restore is due when none was recorded, the last one failed, or it is older than -EveryDays.
    param($LastRestore, [datetime]$Now, [int]$EveryDays = 7)
    if (-not $LastRestore -or -not $LastRestore.finished) { return $true }
    if ($LastRestore.result -ne 'ok') { return $true }
    return (($Now - [datetime]$LastRestore.finished).TotalDays -ge $EveryDays)
}

function Test-DumpListing {
    # `pg_restore --list` output of a readable custom-format dump has a TOC header and at least one entry.
    param([string]$Text)
    if (-not $Text) { return $false }
    return ($Text -match '(?m)^;\s*Archive created at') -and ($Text -match '(?m)^\d+;\s')
}