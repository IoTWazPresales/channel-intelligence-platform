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

Describe 'native calls (review fix: stderr must not stop the deploy under PS 5.1)' {
    It 'captures stderr text from a command that succeeds without throwing, even with Stop' {
        $ErrorActionPreference = 'Stop'
        $r = Invoke-NativeCaptured -FilePath 'cmd.exe' -ArgumentList @('/c', 'echo progress 1>&2 & echo done & exit /b 0')
        $r.ExitCode | Should Be 0
        $r.Output | Should Match 'progress'
        $r.Output | Should Match 'done'
        $ErrorActionPreference | Should Be 'Stop'
    }
    It 'reports a failing exit code instead of throwing' {
        $ErrorActionPreference = 'Stop'
        $r = Invoke-NativeCaptured -FilePath 'cmd.exe' -ArgumentList @('/c', 'echo bad 1>&2 & exit /b 3')
        $r.ExitCode | Should Be 3
        $r.Output | Should Match 'bad'
    }
}

Describe 'missing program (review r2 item 1: must never look like success)' {
    It 'fails with a clear message when the program is not found' {
        $r = Invoke-NativeCaptured -FilePath 'cip-no-such-program-xyz' -ArgumentList @('--version')
        $r.ExitCode | Should Not Be 0
        $r.ExitCode | Should Not BeNullOrEmpty
        $r.Output | Should Match 'cip-no-such-program-xyz'
        $r.Output | Should Match 'not found'
    }
    It 'does not reuse a stale zero exit code from an earlier successful command' {
        $ok = Invoke-NativeCaptured -FilePath 'cmd.exe' -ArgumentList @('/c', 'exit /b 0')
        $ok.ExitCode | Should Be 0
        $r = Invoke-NativeCaptured -FilePath 'cip-no-such-program-xyz'
        $r.ExitCode | Should Not Be 0
    }
    It 'fails the same way for a path that does not exist, even under Stop' {
        $ErrorActionPreference = 'Stop'
        $r = Invoke-NativeCaptured -FilePath (Join-Path $env:TEMP 'cip-missing-dir\python.exe')
        $r.ExitCode | Should Not Be 0
        $r.Output | Should Match 'not found'
    }
}

Describe 'Invoke-NativeStep (review r2 item 2: pnpm failures must stop the deploy clearly)' {
    It 'returns the output of a step that succeeds, even when it writes to stderr under Stop' {
        $ErrorActionPreference = 'Stop'
        $out = Invoke-NativeStep -Description 'demo step' -FilePath 'cmd.exe' -ArgumentList @('/c', 'echo warn 1>&2 & echo fine & exit /b 0') 6>$null
        $out | Should Match 'warn'
        $out | Should Match 'fine'
    }
    It 'throws a message naming the step, the exit code and the output when it fails' {
        $ErrorActionPreference = 'Stop'
        $msg = $null
        try { Invoke-NativeStep -Description 'demo build' -FilePath 'cmd.exe' -ArgumentList @('/c', 'echo compile error 1>&2 & exit /b 7') 6>$null }
        catch { $msg = "$($_.Exception.Message)" }
        $msg | Should Match 'demo build failed'
        $msg | Should Match 'exit 7'
        $msg | Should Match 'compile error'
    }
    It 'throws a clear message when the program is not installed' {
        $msg = $null
        try { Invoke-NativeStep -Description 'demo install' -FilePath 'cip-no-such-program-xyz' -ArgumentList @('install') 6>$null }
        catch { $msg = "$($_.Exception.Message)" }
        $msg | Should Match 'demo install failed'
        $msg | Should Match 'not found'
    }
}

Describe 'failed step still saves the record (review r2 item 3)' {
    It 'saves a record naming the failure and the step when a step throws' {
        $script:saved = $null
        $r = New-DeployRecord -Mode 'execute' -Branch 'trunk'
        $ok = Invoke-DeployGuarded -Record $r -Save { $script:saved = @{ result = $r.result; failure = $r.failure; failed_step = $r.failed_step } } -Body {
            Set-DeployStep $r 'restart worker'
            throw 'something odd happened'
        } 6>$null
        $ok | Should Be $false
        $script:saved | Should Not BeNullOrEmpty
        $script:saved.result | Should Be 'FAILED'
        $script:saved.failure | Should Match 'something odd happened'
        $script:saved.failed_step | Should Be 'restart worker'
    }
    It 'keeps the failure a step recorded itself and still saves' {
        $script:saved = $null
        $r = New-DeployRecord -Mode 'execute' -Branch 'trunk'
        $ok = Invoke-DeployGuarded -Record $r -Save { $script:saved = @{ result = $r.result; failure = $r.failure; failed_step = $r.failed_step } } -Body {
            Set-DeployStep $r 'web build'
            Set-DeployFailure $r 'BUILD_ID did not change after the build'
            throw 'BUILD_ID did not change after the build'
        } 6>$null
        $ok | Should Be $false
        $script:saved.failure | Should Be 'BUILD_ID did not change after the build'
        $script:saved.failed_step | Should Be 'web build'
    }
    It 'stops on a failing native step run through Invoke-NativeStep and records it' {
        $script:saved = $null
        $r = New-DeployRecord -Mode 'execute' -Branch 'trunk'
        $ok = Invoke-DeployGuarded -Record $r -Save { $script:saved = @{ result = $r.result; failure = $r.failure; failed_step = $r.failed_step } } -Body {
            Set-DeployStep $r 'pnpm install'
            Invoke-NativeStep -Description 'pnpm install' -FilePath 'cmd.exe' -ArgumentList @('/c', 'exit /b 1') 6>$null
            $r.result = 'OK'
        } 6>$null
        $ok | Should Be $false
        $script:saved.result | Should Be 'FAILED'
        $script:saved.failure | Should Match 'pnpm install failed'
        $script:saved.failed_step | Should Be 'pnpm install'
    }
    It 'saves on success too, and reports true' {
        $script:saved = $null
        $r = New-DeployRecord -Mode 'execute' -Branch 'trunk'
        $ok = Invoke-DeployGuarded -Record $r -Save { $script:saved = @{ result = $r.result; failure = $r.failure; failed_step = $r.failed_step } } -Body { $r.result = 'OK' } 6>$null
        $ok | Should Be $true
        $script:saved.result | Should Be 'OK'
    }
    It 'does not let a failing save hide the original failure' {
        $r = New-DeployRecord -Mode 'execute' -Branch 'trunk'
        $ok = Invoke-DeployGuarded -Record $r -Save { throw 'disk full' } -Body { throw 'step broke' } 6>$null
        $ok | Should Be $false
        $r.failure | Should Match 'step broke'
    }
    It 'shows the failed step in the CURRENT.md block' {
        $r = New-DeployRecord -Mode 'execute' -Branch 'trunk'
        Set-DeployStep $r 'restart web'
        Set-DeployFailure $r 'web was not healthy within 240 s'
        (Format-DeployRecord $r) | Should Match 'Stopped at restart web: web was not healthy within 240 s'
    }
}

