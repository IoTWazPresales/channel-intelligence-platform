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

# Both source and target use one restricted libpq URL grammar. Unsupported forms fail closed;
# reasons never echo URLs, credentials or untrusted query parameter names.
function Get-PgUrlParts {
    param([string]$Url)
    $r = [pscustomobject]@{ Ok = $false; Reason = $null; HostPort = $null; Database = $null; Query = @() }
    if ([string]::IsNullOrEmpty($Url)) { $r.Reason = 'the URL is empty'; return $r }
    if ($Url -match '[\s\x00-\x1f\x7f]') { $r.Reason = 'the URL contains whitespace or control characters'; return $r }
    if ($Url -cnotmatch '^postgres(ql)?://') { $r.Reason = 'it is not a plain postgresql:// or postgres:// URL (keyword=value strings and other forms are refused)'; return $r }
    if ($Url.Contains('#')) { $r.Reason = 'the URL contains a fragment or an unencoded #'; return $r }
    $rest = $Url.Substring($Url.IndexOf('://') + 3)
    $query = $null
    $q = $rest.IndexOf('?')
    if ($q -ge 0) { $query = $rest.Substring($q + 1); $rest = $rest.Substring(0, $q) }
    $slash = $rest.IndexOf('/')
    if ($slash -lt 0) { $r.Reason = 'the URL has no /database path'; return $r }
    $authority = $rest.Substring(0, $slash)
    $path = $rest.Substring($slash + 1)
    if (($authority.Length - $authority.Replace('@', '').Length) -gt 1) { $r.Reason = 'the URL has more than one @ in its authority'; return $r }
    $hostPort = $authority.Substring($authority.LastIndexOf('@') + 1)
    if ($hostPort -notmatch '^(?:[A-Za-z0-9_.-]+|\[[0-9A-Fa-f:.]+\])(?::([0-9]{1,5}))?$') {
        $r.Reason = 'the URL host or port is not a plain single connection target'; return $r
    }
    if ($matches[1] -and ([int]$matches[1] -lt 1 -or [int]$matches[1] -gt 65535)) {
        $r.Reason = 'the URL port is outside 1..65535'; return $r
    }
    if ($path.Contains('%')) { $r.Reason = 'the database name is percent-encoded and could decode to a different database'; return $r }
    if ($path -cnotmatch '^[A-Za-z0-9_-]{1,63}$') {
        $r.Reason = 'the database must be one plain path segment (letters, digits, underscore or hyphen)'; return $r
    }
    if ($null -ne $query) {
        $seen = @{}
        foreach ($pair in @($query -split '&')) {
            $kv = $pair -split '=', 2
            $key = $kv[0]
            if (@('sslmode', 'connect_timeout', 'application_name') -cnotcontains $key) {
                $r.Reason = 'query parameter is not allowed (only sslmode, connect_timeout and application_name)'; return $r
            }
            if ($kv.Count -ne 2 -or $seen.ContainsKey($key)) {
                $r.Reason = 'query parameter is valueless or repeated'; return $r
            }
            $seen[$key] = $true
        }
        $r.Query = @($query -split '&')
    }
    $r.HostPort = $hostPort
    $r.Database = $path
    $r.Ok = $true
    return $r
}

function Get-RestoreTargetRefusal {
    # $null only when both URLs are supported and the disposable target differs from the source.
    param([string]$TargetUrl, [string]$SourceUrl)
    $p = Get-PgUrlParts $TargetUrl
    if (-not $p.Ok) { return "target refused: $($p.Reason)" }
    $refusal = Get-DisposableDatabaseNameRefusal -Database $p.Database -SourceUrl $SourceUrl
    if ($refusal) { return "target refused: $refusal" }
    return $null
}

function Get-EffectiveDatabaseName {
    # No partial interpretation of source overrides: the same URL grammar applies to both.
    param([string]$Url)
    $p = Get-PgUrlParts $Url
    if (-not $p.Ok) { return $null }
    return $p.Database.ToLowerInvariant()
}

function Get-DisposableDatabaseNameRefusal {
    # Shared by URL validation and the standalone helper's actual current_database() check.
    param([string]$Database, [string]$SourceUrl)
    if ([string]::IsNullOrWhiteSpace($Database)) { return 'the database name is empty' }
    $name = $Database.Trim().ToLowerInvariant()
    if (@('cip', 'cip_test', 'postgres', 'template0', 'template1') -contains $name) { return "'$name' is a protected database (cip, cip_test, postgres and the templates are never restored onto)" }
    if ([string]::IsNullOrWhiteSpace($SourceUrl)) { return 'the source URL is required to protect the backed-up database' }
    $src = Get-EffectiveDatabaseName $SourceUrl
    if (-not $src) { return 'the backed-up database could not be read from the source URL, so the target cannot be shown to differ from it' }
    if ($name -eq $src) { return "'$name' is the database being backed up" }
    if ($name -notmatch 'restore|smoke|scratch|disposable') { return "'$name' does not say it is disposable (name must contain restore, smoke, scratch or disposable)" }
    return $null
}

function Get-DatabaseName {
    param([string]$Url)
    return (Get-EffectiveDatabaseName $Url)
}

function Test-DisposableRestoreTarget {
    param([string]$TargetUrl, [string]$SourceUrl)
    return ($null -eq (Get-RestoreTargetRefusal -TargetUrl $TargetUrl -SourceUrl $SourceUrl))
}

function Test-RestoreSmokeResult {
    # Both exit zero and a complete marker for the expected target are required.
    param($ExitCode, [string]$Output, [string]$ExpectedDatabase)
    if ($null -eq $ExitCode -or $ExitCode -ne 0) { return $null }
    if ([string]::IsNullOrWhiteSpace($Output) -or [string]::IsNullOrWhiteSpace($ExpectedDatabase)) { return $null }
    foreach ($line in ($Output -split "\r?\n")) {
        if ($line -match '^RESTORE_SMOKE_OK database=(\S+) dim_product=\d+ import_job=\d+ alembic=\S+ live_cip_dim_product=\d+\s*$') {
            if ($matches[1].ToLowerInvariant() -eq $ExpectedDatabase.ToLowerInvariant()) { return $line.Trim() }
        }
    }
    return $null
}
