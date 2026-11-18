# Pester 3 tests for scripts/cip-deploy-lib.ps1 (no git, pnpm or services touched).
#   Invoke-Pester .\scripts\cip-deploy.Tests.ps1
. (Join-Path $PSScriptRoot 'cip-deploy-lib.ps1')

function New-Status {
    param([hashtable]$Comps)
    $json = @{ components = $Comps } | ConvertTo-Json -Depth 5
    return ($json | ConvertFrom-Json)
}

Describe 'restart order' {
    It 'restarts api, then worker, then web' {
        (Get-DeployRestartOrder) -join ',' | Should Be 'api,worker,web'
    }
}

Describe 'Test-LockfileChanged' {
    It 'is true for the root lockfile, either slash' {
        Test-LockfileChanged @('apps/web/src/a.ts', 'pnpm-lock.yaml') | Should Be $true
        Test-LockfileChanged @('sub\pnpm-lock.yaml') | Should Be $true
    }
    It 'is false when no lockfile changed or nothing changed' {
        Test-LockfileChanged @('package.json', 'apps/web/package.json') | Should Be $false
        Test-LockfileChanged @() | Should Be $false
        Test-LockfileChanged @('', $null) | Should Be $false
    }
}

Describe 'launch counts' {
    $names = @('api', 'web', 'worker')
    It 'reads counts and marks a missing component unknown' {
        $s = New-Status @{ api = @{ launches = 3 }; web = @{ launches = 1 } }
        $l = Get-ComponentLaunches $s $names
        $l['api'] | Should Be 3
        $l['web'] | Should Be 1
        $l['worker'] | Should Be $null
    }
    It 'is stable when nothing relaunched' {
        $a = Get-ComponentLaunches (New-Status @{ api = @{ launches = 3 }; web = @{ launches = 1 }; worker = @{ launches = 2 } }) $names
        $b = Get-ComponentLaunches (New-Status @{ api = @{ launches = 3 }; web = @{ launches = 1 }; worker = @{ launches = 2 } }) $names
        (Compare-LaunchCounts $a $b).Count | Should Be 0
    }
    It 'reports a relaunch and an unknown count' {
        $a = Get-ComponentLaunches (New-Status @{ api = @{ launches = 3 }; web = @{ launches = 1 } }) $names
        $b = Get-ComponentLaunches (New-Status @{ api = @{ launches = 4 }; web = @{ launches = 1 } }) $names
        $p = Compare-LaunchCounts $a $b
        $p.Count | Should Be 2
        ($p -join ';') | Should Match 'api relaunched \(3 -> 4\)'
        ($p -join ';') | Should Match 'worker launch count unknown'
    }
}

Describe 'Test-ComponentHealthy' {
    $asked = [datetime]'2026-11-18T14:00:00'
    It 'needs healthy and a launch at or after the request' {
        $s = New-Status @{ api = @{ state = 'healthy'; last_start = '2026-11-18T14:00:05' } }
        Test-ComponentHealthy $s 'api' $asked | Should Be $true
    }
    It 'is false for the old process still healthy from before the request' {
        $s = New-Status @{ api = @{ state = 'healthy'; last_start = '2026-11-18T13:00:00' } }
        Test-ComponentHealthy $s 'api' $asked | Should Be $false
    }
    It 'is false while starting, when missing, or without status' {
        Test-ComponentHealthy (New-Status @{ api = @{ state = 'starting'; last_start = '2026-11-18T14:00:05' } }) 'api' $asked | Should Be $false
        Test-ComponentHealthy (New-Status @{ web = @{ state = 'healthy' } }) 'api' $asked | Should Be $false
        Test-ComponentHealthy $null 'api' $asked | Should Be $false
    }
}

Describe 'Test-CeleryPingOutput' {
    It 'accepts a node reply' {
        Test-CeleryPingOutput "-> celery@PC: OK`n        pong`n`n1 node online." | Should Be $true
    }
    It 'rejects no reply and empty output' {
        Test-CeleryPingOutput 'Error: No nodes replied within time constraint' | Should Be $false
        Test-CeleryPingOutput '' | Should Be $false
    }
}

Describe 'deploy record' {
    It 'formats a CURRENT.md block with build identity, restarts and launch counts' {
        $r = New-DeployRecord -Mode 'execute' -Branch 'trunk'
        $r.sha_before = 'aaa'; $r.sha_after = 'bbb'; $r.lockfile_changed = $false; $r.install = 'skipped'
        $r.build = 'ok'; $r.build_id_before = 'old'; $r.build_id_after = 'new'
        $r.restarts += [ordered]@{ component = 'api'; result = 'healthy'; detail = 'state=healthy launches=2' }
        $r.api_ready = 200; $r.celery_ping = 'replied'
        $r.web_checks += [ordered]@{ at = 't1'; code = 200 }
        $r.launches_first = [ordered]@{ api = 2 }; $r.launches_second = [ordered]@{ api = 2 }
        $r.result = 'OK'
        $b = Format-DeployRecord $r
        $b | Should Match 'OK\. Branch `trunk` `aaa` -> `bbb`'
        $b | Should Match 'BUILD_ID `old` -> `new`'
        $b | Should Match 'Restart api: healthy'
        $b | Should Match '/health/ready: 200; Celery ping: replied'
        $b | Should Match 'web 3000 at t1: HTTP 200'
    }
}