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

Describe 'disposable restore target (review fix: the schedule must not wipe a real database)' {
    $src = 'postgresql://u:p@127.0.0.1:5432/cip'
    It 'accepts a database whose name says it is disposable' {
        Test-DisposableRestoreTarget 'postgresql://u:p@127.0.0.1:5432/cip_restore_smoke' $src | Should Be $true
        Test-DisposableRestoreTarget 'postgresql://u:p@127.0.0.1:5432/Scratch_DB?sslmode=disable' $src | Should Be $true
    }
    It 'refuses cip, cip_test, postgres and other real names' {
        Test-DisposableRestoreTarget 'postgresql://u:p@127.0.0.1:5432/cip' $src | Should Be $false
        Test-DisposableRestoreTarget 'postgresql://u:p@127.0.0.1:5432/cip_test' $src | Should Be $false
        Test-DisposableRestoreTarget 'postgresql://u:p@127.0.0.1:5432/postgres' $src | Should Be $false
        Test-DisposableRestoreTarget 'postgresql://u:p@127.0.0.1:5432/reporting' $src | Should Be $false
        Test-DisposableRestoreTarget '' $src | Should Be $false
    }
    It 'refuses the database being backed up even with a disposable-looking name' {
        Test-DisposableRestoreTarget 'postgresql://u:p@h:5432/restore_x' 'postgresql://u:p@h:5432/restore_x' | Should Be $false
    }
}

Describe 'restore target guard validates the EFFECTIVE database (review round 1, P1)' {
    $src = 'postgresql://u:p@127.0.0.1:5432/cip'
    $base = 'postgresql://u:secretpw@127.0.0.1:5432/scratch'

    It 'refuses a query parameter that can change the database or connection target' {
        foreach ($q in @('dbname=cip_test', 'dbname=cip', 'service=prod', 'host=otherhost', 'hostaddr=10.0.0.5', 'port=5433',
                'user=postgres', 'options=-csearch_path%3Dx', 'sslmode=disable&dbname=cip_test', 'foo=bar', 'DBNAME=cip_test', 'password=x', 'target_session_attrs=any')) {
            Test-DisposableRestoreTarget "${base}?$q" $src | Should Be $false
        }
    }
    It 'reports the query restriction without repeating untrusted URL data' {
        $why = Get-RestoreTargetRefusal -TargetUrl "${base}?dbname=cip_test" -SourceUrl $src
        $why | Should Match 'query parameter'
        $why | Should Not Match 'secretpw'
        $why | Should Not Match '127\.0\.0\.1'
    }
    It 'allows only sslmode, connect_timeout and application_name' {
        Test-DisposableRestoreTarget "${base}?sslmode=require" $src | Should Be $true
        Test-DisposableRestoreTarget "${base}?sslmode=require&connect_timeout=10&application_name=nightly" $src | Should Be $true
    }
    It 'refuses a repeated, valueless or empty query' {
        Test-DisposableRestoreTarget "${base}?sslmode=require&sslmode=disable" $src | Should Be $false
        Test-DisposableRestoreTarget "${base}?sslmode" $src | Should Be $false
        Test-DisposableRestoreTarget "${base}?" $src | Should Be $false
        Test-DisposableRestoreTarget "${base}?sslmode=require&" $src | Should Be $false
    }
    It 'refuses percent-encoded path segments that decode to a different name' {
        Test-DisposableRestoreTarget 'postgresql://u:p@127.0.0.1:5432/cip%5Ftest' $src | Should Be $false
        Test-DisposableRestoreTarget 'postgresql://u:p@127.0.0.1:5432/%63ip' $src | Should Be $false
        Test-DisposableRestoreTarget 'postgresql://u:p@127.0.0.1:5432/scratch%5Fdb' $src | Should Be $false
        Test-DisposableRestoreTarget 'postgresql://u:p@127.0.0.1:5432/scratch%2Fcip_test' $src | Should Be $false
        Test-DisposableRestoreTarget 'postgresql://u:p@127.0.0.1:5432/scratch%00' $src | Should Be $false
    }
    It 'refuses keyword=value strings and any URL form that is not plain postgresql:// or postgres://' {
        foreach ($t in @('host=127.0.0.1 dbname=scratch user=u', 'dbname=cip_test', 'host=h dbname=restore_x',
                'jdbc:postgresql://h/scratch', 'mysql://u:p@h/scratch', 'POSTGRESQL://u:p@h/scratch', 'file:///scratch',
                ' postgresql://u:p@h/scratch', "postgresql://u:p@h/scratch`n", 'postgresql://u:p@h/scratch extra', '//u:p@h/scratch')) {
            Test-DisposableRestoreTarget $t $src | Should Be $false
        }
        Test-DisposableRestoreTarget 'postgres://u:p@127.0.0.1:5432/scratch' $src | Should Be $true
    }
    It 'refuses a URL with no database, no host, several hosts, several segments or a fragment' {
        Test-DisposableRestoreTarget 'postgresql://u:p@127.0.0.1:5432' $src | Should Be $false
        Test-DisposableRestoreTarget 'postgresql://u:p@127.0.0.1:5432/' $src | Should Be $false
        Test-DisposableRestoreTarget 'postgresql:///scratch' $src | Should Be $false
        Test-DisposableRestoreTarget 'postgresql://u:p@h1:5432,h2:5432/scratch' $src | Should Be $false
        Test-DisposableRestoreTarget 'postgresql://u:p@127.0.0.1:5432/scratch/cip_test' $src | Should Be $false
        Test-DisposableRestoreTarget 'postgresql://u:p@127.0.0.1:5432/scratch#cip_test' $src | Should Be $false
        Test-DisposableRestoreTarget 'postgresql://u:p@host?dbname=scratch' $src | Should Be $false
        Test-DisposableRestoreTarget 'postgresql://u@a@h/scratch' $src | Should Be $false
    }
    It 'refuses protected names in any letter case, and names with odd characters' {
        Test-DisposableRestoreTarget 'postgresql://u:p@h/CIP_TEST' $src | Should Be $false
        Test-DisposableRestoreTarget 'postgresql://u:p@h/Cip' $src | Should Be $false
        Test-DisposableRestoreTarget 'postgresql://u:p@h/template1' $src | Should Be $false
        Test-DisposableRestoreTarget 'postgresql://u:p@h/restore.smoke' $src | Should Be $false
        Test-DisposableRestoreTarget 'postgresql://u:p@h/"restore"' $src | Should Be $false
    }
    It 'fails closed on source URLs with overrides or encoded database aliases' {
        Test-DisposableRestoreTarget 'postgresql://u:p@h/restore_x' 'postgresql://u:p@h/other?dbname=restore_x' | Should Be $false
        Test-DisposableRestoreTarget 'postgresql://u:p@h/restore_x' 'postgresql://u:p@h/cip?sslmode=require' | Should Be $true
        Test-DisposableRestoreTarget 'postgresql://u:p@h/restore_x' 'postgresql://u:p@h/%72estore_x' | Should Be $false
    }
    It 'refuses when the backed-up database cannot be read, since it cannot be shown to differ' {
        Test-DisposableRestoreTarget 'postgresql://u:p@h/restore_x' 'host=h dbname=restore_x' | Should Be $false
        Test-DisposableRestoreTarget 'postgresql://u:p@h/restore_x' 'not a url' | Should Be $false
    }
}

Describe 'effective database name and the name-level rules the smoke script re-checks' {
    It 'reads a plain database name; unsupported forms fail closed' {
        Get-EffectiveDatabaseName 'postgresql://u:p@h:5432/Cip' | Should Be 'cip'
        Get-EffectiveDatabaseName 'postgresql://u:p@h/scratch?dbname=CIP_Test' | Should BeNullOrEmpty
        Get-EffectiveDatabaseName 'postgresql://u:p@h/cip%5Ftest' | Should BeNullOrEmpty
        Get-EffectiveDatabaseName 'host=h dbname=cip' | Should BeNullOrEmpty
        Get-EffectiveDatabaseName '' | Should BeNullOrEmpty
        Get-DatabaseName 'postgresql://u:p@h/cip?sslmode=disable' | Should Be 'cip'
    }
    It 'refuses protected, source and non-disposable names from current_database()' {
        $src = 'postgresql://u:p@h/cip'
        Get-DisposableDatabaseNameRefusal -Database 'cip_test' -SourceUrl $src | Should Match 'protected'
        Get-DisposableDatabaseNameRefusal -Database 'CIP' -SourceUrl $src | Should Match 'protected'
        Get-DisposableDatabaseNameRefusal -Database 'reporting' -SourceUrl $src | Should Match 'disposable'
        Get-DisposableDatabaseNameRefusal -Database 'restore_x' -SourceUrl 'postgresql://u:p@h/restore_x' | Should Match 'being backed up'
        Get-DisposableDatabaseNameRefusal -Database '' -SourceUrl $src | Should Match 'empty'
        Get-DisposableDatabaseNameRefusal -Database 'cip_restore_smoke' -SourceUrl $src | Should BeNullOrEmpty
    }
}

Describe 'restore_cip_smoke.ps1 refuses by itself (defence in depth; refusal happens before any psql call)' {
    $smoke = Join-Path $PSScriptRoot 'restore_cip_smoke.ps1'
    $dump = Join-Path ([IO.Path]::GetTempPath()) ('cip_pester_{0}.dump' -f [guid]::NewGuid().ToString('N'))
    Set-Content -LiteralPath $dump -Value 'x'
    $noBin = Join-Path ([IO.Path]::GetTempPath()) 'no_such_pg_bin'
    $src = 'postgresql://u:p@127.0.0.1:5432/cip'

    It 'refuses cip_test, cip, postgres and the source database' {
        foreach ($t in @('postgresql://u:p@127.0.0.1:5432/cip_test', 'postgresql://u:p@127.0.0.1:5432/cip', 'postgresql://u:p@127.0.0.1:5432/postgres')) {
            { & $smoke -DumpPath $dump -TargetUrl $t -SourceUrl $src -PgBin $noBin } | Should Throw 'Refusing to restore'
        }
        { & $smoke -DumpPath $dump -TargetUrl 'postgresql://u:p@h/restore_x' -SourceUrl 'postgresql://u:p@h/restore_x' -PgBin $noBin } | Should Throw 'being backed up'
    }
    It 'refuses a query override that points the connection at cip_test' {
        { & $smoke -DumpPath $dump -TargetUrl 'postgresql://u:p@127.0.0.1:5432/scratch?dbname=cip_test' -SourceUrl $src -PgBin $noBin } | Should Throw 'query parameter'
    }
    It 'refuses keyword=value and percent-encoded targets' {
        { & $smoke -DumpPath $dump -TargetUrl 'host=127.0.0.1 dbname=cip_test' -SourceUrl $src -PgBin $noBin } | Should Throw 'Refusing to restore'
        { & $smoke -DumpPath $dump -TargetUrl 'postgresql://u:p@127.0.0.1:5432/cip%5Ftest' -SourceUrl $src -PgBin $noBin } | Should Throw 'percent-encoded'
    }
    It 'never reaches psql for a refused target (the missing PgBin is not what stops it)' {
        $msg = try { & $smoke -DumpPath $dump -TargetUrl 'postgresql://u:p@h/cip_test' -SourceUrl $src -PgBin $noBin; '' } catch { "$_" }
        $msg | Should Not Match 'psql not found'
        Remove-Item -LiteralPath $dump -Force -ErrorAction SilentlyContinue
    }
}

Describe 'restore_cip_smoke.ps1 checks every native step (review round 1, P1)' {
    $text = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'restore_cip_smoke.ps1') -Raw
    It 'parses cleanly' {
        $errs = $null
        [void][System.Management.Automation.Language.Parser]::ParseInput($text, [ref]$null, [ref]$errs)
        @($errs).Count | Should Be 0
    }
    It 'checks the exit code after the schema wipe, pg_restore and the count queries, before printing the marker' {
        $marker = $text.IndexOf('Write-Host "RESTORE_SMOKE_OK')
        $marker | Should BeGreaterThan 0
        $lastCheck = $text.LastIndexOf('$LASTEXITCODE -ne 0')
        $lastCheck | Should BeLessThan $marker
        foreach ($step in @('& $psql -d $TargetUrl -v ON_ERROR_STOP=1 -c', '& $pgRestore')) {
            $i = $text.IndexOf($step); $i | Should BeGreaterThan 0
            $text.Substring($i, [Math]::Min(700, $text.Length - $i)) | Should Match 'LASTEXITCODE -ne 0'
        }
        $text | Should Match 'function Invoke-PsqlScalar'
        $text.Substring($text.IndexOf('function Invoke-PsqlScalar'), 400) | Should Match 'LASTEXITCODE -ne 0'
    }
    It 'ends with exit 0 only after the marker, so the caller can read a real exit code' {
        $text.TrimEnd().EndsWith('exit 0') | Should Be $true
    }
}

Describe 'restore success needs exit code 0 AND the marker (review round 1, P1)' {
    $line = 'RESTORE_SMOKE_OK database=cip_restore_smoke dim_product=18177 import_job=589 alembic=20260906_0022 live_cip_dim_product=18177'
    $out = "Target database=cip_restore_smoke`r`nWiping public schema`r`n$line`r`n"
    It 'accepts exit 0 with the marker for the expected database' {
        Test-RestoreSmokeResult -ExitCode 0 -Output $out -ExpectedDatabase 'cip_restore_smoke' | Should Be $line
        Test-RestoreSmokeResult -ExitCode 0 -Output $out -ExpectedDatabase 'CIP_Restore_Smoke' | Should Be $line
    }
    It 'rejects the marker when the exit code is non-zero or missing' {
        Test-RestoreSmokeResult -ExitCode 1 -Output $out -ExpectedDatabase 'cip_restore_smoke' | Should BeNullOrEmpty
        Test-RestoreSmokeResult -ExitCode 2 -Output $out -ExpectedDatabase 'cip_restore_smoke' | Should BeNullOrEmpty
        Test-RestoreSmokeResult -ExitCode $null -Output $out -ExpectedDatabase 'cip_restore_smoke' | Should BeNullOrEmpty
    }
    It 'rejects exit 0 without a complete marker line' {
        Test-RestoreSmokeResult -ExitCode 0 -Output '' -ExpectedDatabase 'cip_restore_smoke' | Should BeNullOrEmpty
        Test-RestoreSmokeResult -ExitCode 0 -Output 'pg_restore: error: could not execute query' -ExpectedDatabase 'cip_restore_smoke' | Should BeNullOrEmpty
        Test-RestoreSmokeResult -ExitCode 0 -Output 'RESTORE_SMOKE_OK database=cip_restore_smoke dim_product=1 import_job=1 alembic=x' -ExpectedDatabase 'cip_restore_smoke' | Should BeNullOrEmpty
        Test-RestoreSmokeResult -ExitCode 0 -Output 'RESTORE_SMOKE_OK' -ExpectedDatabase 'cip_restore_smoke' | Should BeNullOrEmpty
        Test-RestoreSmokeResult -ExitCode 0 -Output 'echo RESTORE_SMOKE_OK database=x dim_product=1 import_job=1 alembic=a' -ExpectedDatabase 'x' | Should BeNullOrEmpty
    }
    It 'rejects a marker for a different database than the target' {
        Test-RestoreSmokeResult -ExitCode 0 -Output $out -ExpectedDatabase 'cip_scratch' | Should BeNullOrEmpty
    }
    It 'is what the nightly script uses to decide result ok' {
        $nightly = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'nightly_backup_cip.ps1') -Raw
        $nightly | Should Match 'Test-RestoreSmokeResult -ExitCode \$smokeExit'
        $nightly | Should Match 'Get-RestoreTargetRefusal'
        $nightly.Contains("'^RESTORE_SMOKE_OK '") | Should Be $false   # the old marker-only check is gone
        $errs = $null
        [void][System.Management.Automation.Language.Parser]::ParseInput($nightly, [ref]$null, [ref]$errs)
        @($errs).Count | Should Be 0
    }
}


Describe 'unsupported source connections cannot bypass same-source protection' {
    It 'refuses connection overrides, encoded keys and an absent source' {
        foreach ($src in @('', 'postgresql://u:p@h/cip?service=prod',
                'postgresql://u:p@h/cip?%64bname=scratch',
                'postgresql://u:p@h/cip?dbname=postgresql%3A%2F%2Fh%2Fscratch',
                'postgresql://u:p@h/cip?host=other',
                'postgresql://u:p@h:99999/cip')) {
            Test-DisposableRestoreTarget 'postgresql://u:p@h/scratch' $src | Should Be $false
        }
        Test-DisposableRestoreTarget 'postgresql://u:p@h:0/scratch' 'postgresql://u:p@h/cip' | Should Be $false
        Test-DisposableRestoreTarget 'postgresql://u:p@h\\other/scratch' 'postgresql://u:p@h/cip' | Should Be $false
    }
}
