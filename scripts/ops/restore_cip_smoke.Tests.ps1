# Pester 3 behavioral tests. Every native command and filesystem probe is mocked.
# A mock wiring failure throws before any executable can be launched.
function psql.exe {
    param($d, $v, $tAc, $c)
    throw 'Unmocked psql is forbidden in restore unit tests'
}
function pg_restore.exe { throw 'Unmocked pg_restore is forbidden in restore unit tests' }

Describe 'restore smoke native failures and identity checks' {
    $smoke = Join-Path $PSScriptRoot 'restore_cip_smoke.ps1'

    BeforeEach {
        $global:CipSmokeCase = @{
            Calls = @(); Messages = @(); Fail = ''; Bad = ''
            Source = 'cip'; Target = 'cip_scratch'
        }
        Mock Test-Path { $true }
        Mock Join-Path { $ChildPath } -ParameterFilter { $Path -eq 'cip-test-native' }
        Mock Write-Host { $global:CipSmokeCase.Messages += "$Object" }
        Mock psql.exe {
            $isSource = $d -eq 'postgresql://u:p@h/cip'
            if ($c) {
                $step = 'wipe'; $value = ''
            } elseif ($tAc -eq 'SELECT current_database();') {
                if ($isSource) { $step = 'source identity'; $value = $global:CipSmokeCase.Source }
                else { $step = 'target identity'; $value = $global:CipSmokeCase.Target }
            } elseif ($tAc -eq 'SELECT count(*) FROM dim_product;') {
                if ($isSource) { $step = 'source count' } else { $step = 'product count' }
                $value = '4'
            } elseif ($tAc -eq 'SELECT count(*) FROM import_job;') {
                $step = 'job count'; $value = '2'
            } elseif ($tAc -eq 'SELECT version_num FROM alembic_version LIMIT 1;') {
                $step = 'alembic'; $value = 'unit_revision'
            } else {
                throw "Unexpected SQL in restore test: $tAc $c"
            }
            $global:CipSmokeCase.Calls += $step
            $global:LASTEXITCODE = 0
            if ($global:CipSmokeCase.Fail -eq $step) { $global:LASTEXITCODE = 9 }
            if ($global:CipSmokeCase.Bad -eq $step) { $value = 'invalid result' }
            $value
        }
        Mock pg_restore.exe {
            $global:CipSmokeCase.Calls += 'restore'
            $global:LASTEXITCODE = 0
            if ($global:CipSmokeCase.Fail -eq 'restore') { $global:LASTEXITCODE = 9 }
        }
    }

    AfterEach { Remove-Variable CipSmokeCase -Scope Global -ErrorAction SilentlyContinue }

    It 'prints success only after every native step succeeds' {
        & $smoke -DumpPath 'not-a-real-dump' -TargetUrl 'postgresql://u:p@h/cip_scratch' -SourceUrl 'postgresql://u:p@h/cip' -PgBin 'cip-test-native'
        $LASTEXITCODE | Should Be 0
        ($global:CipSmokeCase.Calls -join ',') | Should Be 'source identity,target identity,wipe,restore,product count,job count,alembic,source count'
        @($global:CipSmokeCase.Messages | Where-Object { $_ -match '^RESTORE_SMOKE_OK ' }).Count | Should Be 1
    }

    It 'stops without a success marker when <Step> fails, even if output looks valid' -TestCases @(
        @{ Step = 'source identity' }, @{ Step = 'target identity' }, @{ Step = 'wipe' },
        @{ Step = 'restore' }, @{ Step = 'product count' }, @{ Step = 'job count' },
        @{ Step = 'alembic' }, @{ Step = 'source count' }
    ) {
        param($Step)
        $global:CipSmokeCase.Fail = $Step
        { & $smoke -DumpPath 'not-a-real-dump' -TargetUrl 'postgresql://u:p@h/cip_scratch' -SourceUrl 'postgresql://u:p@h/cip' -PgBin 'cip-test-native' } | Should Throw
        $global:CipSmokeCase.Calls[-1] | Should Be $Step
        @($global:CipSmokeCase.Messages | Where-Object { $_ -match '^RESTORE_SMOKE_OK ' }).Count | Should Be 0
    }

    It 'refuses an unexpected or protected actual target before wiping' -TestCases @(
        @{ Database = 'cip_test' }, @{ Database = 'cip' }, @{ Database = 'other_scratch' }
    ) {
        param($Database)
        $global:CipSmokeCase.Target = $Database
        { & $smoke -DumpPath 'not-a-real-dump' -TargetUrl 'postgresql://u:p@h/cip_scratch' -SourceUrl 'postgresql://u:p@h/cip' -PgBin 'cip-test-native' } | Should Throw 'Refusing to restore'
        $global:CipSmokeCase.Calls -contains 'wipe' | Should Be $false
        $global:CipSmokeCase.Calls -contains 'restore' | Should Be $false
    }

    It 'refuses a source server whose identity differs from its URL before wiping' {
        $global:CipSmokeCase.Source = 'cip_scratch'
        { & $smoke -DumpPath 'not-a-real-dump' -TargetUrl 'postgresql://u:p@h/cip_scratch' -SourceUrl 'postgresql://u:p@h/cip' -PgBin 'cip-test-native' } | Should Throw 'Refusing to restore'
        $global:CipSmokeCase.Calls -contains 'wipe' | Should Be $false
    }

    It 'does not print success for malformed verification output' -TestCases @(
        @{ Step = 'product count' }, @{ Step = 'job count' }, @{ Step = 'alembic' },
        @{ Step = 'source count' }
    ) {
        param($Step)
        $global:CipSmokeCase.Bad = $Step
        { & $smoke -DumpPath 'not-a-real-dump' -TargetUrl 'postgresql://u:p@h/cip_scratch' -SourceUrl 'postgresql://u:p@h/cip' -PgBin 'cip-test-native' } | Should Throw
        @($global:CipSmokeCase.Messages | Where-Object { $_ -match '^RESTORE_SMOKE_OK ' }).Count | Should Be 0
    }
}
