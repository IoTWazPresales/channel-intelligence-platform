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
    It 'reports false when the deploy passed but the record could not be saved (review B4)' {
        $r = New-DeployRecord -Mode 'execute' -Branch 'trunk'
        $ok = Invoke-DeployGuarded -Record $r -Save { throw 'disk full' } -Body { $r.result = 'OK' } 6>$null
        $ok | Should Be $false
        $r.result | Should Be 'OK'
    }
    It 'keeps a multi-line failure inside one CURRENT.md bullet (review B5)' {
        $r = New-DeployRecord -Mode 'execute' -Branch 'trunk'
        Set-DeployStep $r 'web build'
        Set-DeployFailure $r "web build failed (exit 1): line one`nline two`r`nline three"
        $lines = (Format-DeployRecord $r) -split "`n"
        $i = [array]::IndexOf(@($lines | ForEach-Object { $_ -match '^- Stopped at web build' }), $true)
        $i | Should BeGreaterThan -1
        $lines[$i + 1] | Should Match '^  line two'
        $lines[$i + 2] | Should Match '^  line three'
    }
}

Describe 'Test-DeployPrerequisites (review B1/B3: preflight before any change)' {
    $exe = $env:ComSpec
    It 'passes when git, pnpm and the python path all exist' {
        { Test-DeployPrerequisites -Git 'cmd.exe' -Pnpm 'cmd.exe' -Python $exe } | Should Not Throw
    }
    It 'throws "required program not found: X" for a missing git' {
        $msg = $null
        try { Test-DeployPrerequisites -Git 'cip-no-such-git' -Pnpm 'cmd.exe' -Python $exe } catch { $msg = "$($_.Exception.Message)" }
        $msg | Should Be 'required program not found: cip-no-such-git'
    }
    It 'throws "required program not found: X" for a missing pnpm' {
        $msg = $null
        try { Test-DeployPrerequisites -Git 'cmd.exe' -Pnpm 'cip-no-such-pnpm' -Python $exe } catch { $msg = "$($_.Exception.Message)" }
        $msg | Should Be 'required program not found: cip-no-such-pnpm'
    }
    It 'throws "required program not found: X" for a missing python path' {
        $missing = Join-Path $env:TEMP 'cip-missing-dir\python.exe'
        $msg = $null
        try { Test-DeployPrerequisites -Git 'cmd.exe' -Pnpm 'cmd.exe' -Python $missing } catch { $msg = "$($_.Exception.Message)" }
        $msg | Should Be "required program not found: $missing"
    }
    It 'names the first missing program when several are missing' {
        $msg = $null
        try { Test-DeployPrerequisites -Git 'cip-no-such-git' -Pnpm 'cip-no-such-pnpm' -Python 'cip-no-such-py' } catch { $msg = "$($_.Exception.Message)" }
        $msg | Should Be 'required program not found: cip-no-such-git'
    }
    It 'saves a prerequisites failure before invoking the pull action' {
        $script:saved = $null
        $script:pullInvoked = $false
        $pullAction = { $script:pullInvoked = $true }
        $r = New-DeployRecord -Mode 'execute' -Branch 'trunk'
        function Stop-Deploy {
            param([string]$Why)
            Set-DeployFailure $r $Why
            throw $Why
        }
        $ok = Invoke-DeployGuarded -Record $r -Save { $script:saved = @{ result = $r.result; failure = $r.failure; failed_step = $r.failed_step } } -Body {
            Set-DeployStep $r 'prerequisites'
            try { Test-DeployPrerequisites -Git 'cmd.exe' -Pnpm 'cip-no-such-pnpm' -Python $env:ComSpec } catch {
                Stop-Deploy "$($_.Exception.Message)"
            }
            Set-DeployStep $r 'git pull'
            & $pullAction
        } 6>$null
        $ok | Should Be $false
        $script:saved.result | Should Be 'FAILED'
        $script:saved.failure | Should Be 'required program not found: cip-no-such-pnpm'
        $script:saved.failed_step | Should Be 'prerequisites'
        $script:pullInvoked | Should Be $false
    }
}

Describe 'cip-deploy.ps1 wiring (review B1/B3: preflight runs first, git stays inside the guard)' {
    $scriptPath = Join-Path $PSScriptRoot 'cip-deploy.ps1'
    $tokens = $null; $errors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$tokens, [ref]$errors)
    function Get-BodyBlock($Ast, [string]$Name) {
        $assign = $Ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.AssignmentStatementAst] -and $n.Left.Extent.Text -eq "`$$Name" }, $true) | Select-Object -First 1
        if (-not $assign) { return $null }
        return $assign.Right.Find({ param($n) $n -is [System.Management.Automation.Language.ScriptBlockExpressionAst] }, $true)
    }
    function Get-CommandCalls($Node, [string]$CommandName) {
        return @($Node.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] -and $n.GetCommandName() -eq $CommandName }, $true) | Sort-Object { $_.Extent.StartOffset })
    }
    $deployBlock = Get-BodyBlock $ast 'deployBody'

    It 'parses without errors and defines the deploy body' {
        @($errors).Count | Should Be 0
        $deployBlock | Should Not BeNullOrEmpty
    }
    It 'starts the deploy body with the preflight step and check' {
        $stmts = @($deployBlock.ScriptBlock.EndBlock.Statements)
        $stmts[0].Extent.Text | Should Match "^Set-DeployStep \`$record 'prerequisites'"
        $stmts[1].Extent.Text | Should Match '^try\b'
        $check = Get-CommandCalls $deployBlock 'Test-DeployPrerequisites'
        $check.Count | Should Be 1
        $check[0].Extent.Text | Should Match '-Python \$py\b'
    }
    It 'runs the preflight before the first git call in the deploy body' {
        $pre = Get-CommandCalls $deployBlock 'Test-DeployPrerequisites'
        $git = Get-CommandCalls $deployBlock 'Invoke-Git'
        $pre.Count | Should BeGreaterThan 0
        $git.Count | Should BeGreaterThan 0
        $pre[0].Extent.StartOffset | Should BeLessThan $git[0].Extent.StartOffset
        $pull = @($git | Where-Object { $_.Extent.Text -match "'pull'" }) | Select-Object -First 1
        $pull | Should Not BeNullOrEmpty
        $pre[0].Extent.StartOffset | Should BeLessThan $pull.Extent.StartOffset
    }
    It 'has no Invoke-Git call outside the guarded deploy body, including the preview' {
        $all = Get-CommandCalls $ast 'Invoke-Git'
        $outside = @($all | Where-Object {
            $o = $_.Extent.StartOffset
            -not ($o -ge $deployBlock.Extent.StartOffset -and $o -lt $deployBlock.Extent.EndOffset)
        })
        $outside.Count | Should Be 0
    }
    It 'runs the execute body through Invoke-DeployGuarded' {
        $guarded = Get-CommandCalls $ast 'Invoke-DeployGuarded'
        ($guarded | ForEach-Object { $_.Extent.Text }) -join "`n" | Should Match '-Body \$deployBody'
        $guarded.Count | Should Be 1
    }
    It 'uses the install decision and marker guard with a frozen lockfile' {
        $decision = Get-CommandCalls $deployBlock 'Get-InstallDecision'
        $decision.Count | Should Be 1
        $decision[0].Extent.Text | Should Match '-MarkerExists \(Test-Path -LiteralPath \$installMarker\)'
        $install = Get-CommandCalls $deployBlock 'Invoke-GuardedInstall'
        $install.Count | Should Be 1
        $install[0].Extent.Text | Should Match '-MarkerPath \$installMarker'
        $install[0].Extent.Text | Should Match "Invoke-NativeStep -Description 'pnpm install'"
        $install[0].Extent.Text | Should Match '--frozen-lockfile'
    }
}

Describe 'Get-InstallDecision and Invoke-GuardedInstall (review B2: rerun after a failed install)' {
    It 'forces the install when the marker exists, even with the lockfile unchanged' {
        $d = Get-InstallDecision -LockfileChanged $false -MarkerExists $true
        $d.Run | Should Be $true
        $d.Reason | Should Match 'did not finish'
    }
    It 'skips the install when there is no marker and the lockfile is unchanged' {
        $d = Get-InstallDecision -LockfileChanged $false -MarkerExists $false
        $d.Run | Should Be $false
        $d.Reason | Should Match 'skipped'
    }
    It 'installs when the lockfile changed' {
        $d = Get-InstallDecision -LockfileChanged $true -MarkerExists $false
        $d.Run | Should Be $true
        $d.Reason | Should Match 'lockfile changed'
    }
    It 'leaves the marker behind when the install fails, so the rerun forces it' {
        $marker = Join-Path $env:TEMP "cip-install-marker-$([guid]::NewGuid().ToString('N')).txt"
        try {
            { Invoke-GuardedInstall -MarkerPath $marker -Action { throw 'pnpm install failed' } } | Should Throw 'pnpm install failed'
            Test-Path $marker | Should Be $true
            (Get-InstallDecision -LockfileChanged $false -MarkerExists (Test-Path $marker)).Run | Should Be $true
        } finally { Remove-Item $marker -Force -ErrorAction SilentlyContinue }
    }
    It 'removes the marker only after the install succeeded, and writes it before' {
        $marker = Join-Path $env:TEMP "cip-install-marker-$([guid]::NewGuid().ToString('N')).txt"
        $script:seenDuring = $null
        try {
            Invoke-GuardedInstall -MarkerPath $marker -Action { $script:seenDuring = (Test-Path $marker) }
            $script:seenDuring | Should Be $true
            Test-Path $marker | Should Be $false
        } finally { Remove-Item $marker -Force -ErrorAction SilentlyContinue }
    }
    It 'creates the marker folder when it does not exist yet' {
        $dir = Join-Path $env:TEMP "cip-install-dir-$([guid]::NewGuid().ToString('N'))"
        $marker = Join-Path $dir 'install-incomplete.marker'
        try {
            { Invoke-GuardedInstall -MarkerPath $marker -Action { throw 'x' } } | Should Throw
            Test-Path $marker | Should Be $true
        } finally { Remove-Item $dir -Recurse -Force -ErrorAction SilentlyContinue }
    }
}

Describe 'per-step timings (review B7)' {
    It 'saves the timestamps of completed and failed steps in order' {
        $script:savedJson = $null
        $script:savedBlock = $null
        $r = New-DeployRecord -Mode 'execute' -Branch 'trunk'
        $ok = Invoke-DeployGuarded -Record $r -Save {
            $script:savedJson = $r | ConvertTo-Json -Depth 6
            $script:savedBlock = Format-DeployRecord $r
        } -Body {
            Set-DeployStep $r 'prerequisites'
            Set-DeployStep $r 'preconditions'
            throw 'git read failed'
        } 6>$null
        $ok | Should Be $false
        $saved = $script:savedJson | ConvertFrom-Json
        $saved.failed_step | Should Be 'preconditions'
        @($saved.steps).Count | Should Be 2
        $saved.steps[0].name | Should Be 'prerequisites'
        $saved.steps[1].name | Should Be 'preconditions'
        foreach ($step in $saved.steps) {
            $step.at | Should Match '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$'
            $script:savedBlock | Should Match ([regex]::Escape("$($step.name) $($step.at)"))
        }
    }
    It 'appends name and ISO time to the steps list for every step' {
        $r = New-DeployRecord -Mode 'execute' -Branch 'trunk'
        Set-DeployStep $r 'prerequisites'
        Set-DeployStep $r 'git pull'
        @($r.steps).Count | Should Be 2
        $r.steps[0].name | Should Be 'prerequisites'
        $r.steps[1].name | Should Be 'git pull'
        $r.steps[0].at | Should Match '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$'
        $r.current_step | Should Be 'git pull'
    }
    It 'shows the steps in the CURRENT.md block and the JSON record' {
        $r = New-DeployRecord -Mode 'execute' -Branch 'trunk'
        Set-DeployStep $r 'prerequisites'
        Set-DeployStep $r 'web build'
        $b = Format-DeployRecord $r
        $b | Should Match 'Steps: prerequisites \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}, web build \d{4}-\d{2}-\d{2}T'
        ($r | ConvertTo-Json -Depth 6) | Should Match '"steps"'
    }
}

