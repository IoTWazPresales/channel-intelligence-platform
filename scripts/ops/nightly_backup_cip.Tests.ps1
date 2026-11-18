# Pester 3 tests for scripts/ops/nightly_backup_lib.ps1.  Invoke-Pester .\scripts\ops\nightly_backup_cip.Tests.ps1
. (Join-Path $PSScriptRoot 'nightly_backup_lib.ps1')

function Dump([datetime]$d) { 'cip_{0}.dump' -f $d.ToString('yyyyMMdd_HHmmss') }

Describe 'Get-DumpStamp' {
    It 'reads the backup_cip.ps1 name and ignores others' {
        (Get-DumpStamp 'cip_20261118_023000.dump') | Should Be ([datetime]'2026-11-18T02:30:00')
        Get-DumpStamp 'cip-tables-20261110-131940.dump' | Should Be $null
        Get-DumpStamp 'last_backup.json' | Should Be $null
    }
}

Describe 'Get-IsoWeekKey' {
    It 'uses ISO weeks, including week 53 and the year boundary' {
        Get-IsoWeekKey ([datetime]'2026-11-18') | Should Be '2026-W47'
        Get-IsoWeekKey ([datetime]'2026-12-31') | Should Be '2026-W53'
        Get-IsoWeekKey ([datetime]'2027-01-03') | Should Be '2026-W53'
        Get-IsoWeekKey ([datetime]'2027-01-04') | Should Be '2027-W01'
    }
}

Describe 'Select-DumpsToDelete' {
    It 'keeps nothing extra when there are fewer dumps than the daily window' {
        $names = 1..5 | ForEach-Object { Dump ([datetime]'2026-11-18T02:30:00').AddDays(-$_) }
        (Select-DumpsToDelete -Names $names -KeepDaily 14 -KeepWeekly 8).Count | Should Be 0
    }
    It 'keeps 14 daily plus the newest of each older week up to 8 weeks' {
        $start = [datetime]'2026-11-18T02:30:00'
        $names = 0..89 | ForEach-Object { Dump $start.AddDays(-$_) }
        $del = Select-DumpsToDelete -Names $names -KeepDaily 14 -KeepWeekly 8
        $kept = @($names | Where-Object { $del -notcontains $_ })
        foreach ($k in 0..13) { $kept -contains (Dump $start.AddDays(-$k)) | Should Be $true }
        $weeks = @($kept | ForEach-Object { Get-IsoWeekKey (Get-DumpStamp $_) } | Sort-Object -Unique)
        $weeks.Count | Should Be 8
        $kept.Count | Should BeLessThan 23
        $kept -contains (Dump $start.AddDays(-89)) | Should Be $false
    }
    It 'keeps the newest of several dumps on one day and never selects other files' {
        $names = @('cip_20261118_010000.dump', 'cip_20261118_230000.dump', 'notes.txt', 'cip_manual.dump')
        $del = Select-DumpsToDelete -Names $names -KeepDaily 1 -KeepWeekly 1
        @($del) -join ',' | Should Be 'cip_20261118_010000.dump'
    }
    It 'always keeps the newest dump even with zero windows' {
        $del = Select-DumpsToDelete -Names @('cip_20261117_023000.dump', 'cip_20261118_023000.dump') -KeepDaily 0 -KeepWeekly 0
        @($del) -join ',' | Should Be 'cip_20261117_023000.dump'
    }
}

Describe 'Test-RestoreDue' {
    $now = [datetime]'2026-11-18T03:00:00'
    It 'is due with no record, after a failure, or when older than the interval' {
        Test-RestoreDue $null $now 7 | Should Be $true
        Test-RestoreDue ([pscustomobject]@{ result = 'failed'; finished = '2026-11-17T03:00:00' }) $now 7 | Should Be $true
        Test-RestoreDue ([pscustomobject]@{ result = 'ok'; finished = '2026-11-10T03:00:00' }) $now 7 | Should Be $true
    }
    It 'is not due after a recent good restore' {
        Test-RestoreDue ([pscustomobject]@{ result = 'ok'; finished = '2026-11-15T03:00:00' }) $now 7 | Should Be $false
    }
}

Describe 'Test-DumpListing' {
    It 'accepts a TOC with entries and rejects empty or error text' {
        Test-DumpListing ";`n; Archive created at 2026-11-18 02:30:01 SAST`n;`n215; 1259 16385 TABLE public dim_product cip`n" | Should Be $true
        Test-DumpListing 'pg_restore: error: input file does not appear to be a valid archive' | Should Be $false
        Test-DumpListing '' | Should Be $false
    }
}