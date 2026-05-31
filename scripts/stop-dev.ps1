# Stop local CIP dev stack processes.
# Kill order: PID file trees → ports → WMI name+path sweep → verify.
# Usage: .\scripts\stop-dev.ps1

$ErrorActionPreference = 'Continue'

function Stop-ProcessTree {
    param([int]$ParentPid)
    if ($ParentPid -le 4) { return }
    try {
        $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$ParentPid" -ErrorAction SilentlyContinue)
        foreach ($child in $children) {
            Stop-ProcessTree -ParentPid $child.ProcessId
        }
    } catch { }
    Stop-Process -Id $ParentPid -Force -ErrorAction SilentlyContinue
}

function Stop-CipDevProcesses {
    $repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
    $repoNorm = $repo.TrimEnd('\')
    $pidDir = Join-Path $repo '.cip-dev-pids'

    Write-Host "Stopping CIP dev processes (repo: $repoNorm)" -ForegroundColor Cyan

    # 1. Kill by PID files (most precise — process trees rooted at recorded PIDs).
    if (Test-Path $pidDir) {
        $pidFiles = Get-ChildItem -Path $pidDir -Filter '*.pid' -ErrorAction SilentlyContinue
        foreach ($pf in $pidFiles) {
            $rawPid = (Get-Content $pf.FullName -ErrorAction SilentlyContinue) -as [int]
            if ($rawPid -and $rawPid -gt 4) {
                Write-Host "  Killing PID tree $rawPid (from $($pf.Name))" -ForegroundColor DarkGray
                Stop-ProcessTree -ParentPid $rawPid
            }
        }
        # Clean up PID files.
        Remove-Item -Path (Join-Path $pidDir '*.pid') -Force -ErrorAction SilentlyContinue
    }

    # 2. Port-based kill (catches anything not in PID files).
    foreach ($port in @(8001, 3000, 5555)) {
        $pids = @()
        try {
            $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
            foreach ($conn in $conns) {
                $procId = [int]$conn.OwningProcess
                if ($procId -gt 4) { $pids += $procId }
            }
        } catch {
            Write-Host "  Get-NetTCPConnection failed for port ${port}: $_" -ForegroundColor DarkYellow
        }
        foreach ($procId in ($pids | Select-Object -Unique)) {
            Write-Host "  Killing PID $procId (listening on port $port)" -ForegroundColor DarkGray
            Stop-ProcessTree -ParentPid $procId
        }
    }

    # 3. WMI name+path sweep (catches celery worker, any missed children).
    #    Note: 'celery.exe' does not exist as a process name — Celery runs as python.exe.
    $procNames = @('node.exe', 'python.exe', 'pythonw.exe', 'pnpm.exe')
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | ForEach-Object {
        if ($procNames -notcontains $_.Name) { return }
        $cmd = $_.CommandLine
        if (-not $cmd) { return }
        if ($cmd -notlike "*$repoNorm*") { return }
        Write-Host "  Killing $($_.Name) PID $($_.ProcessId) (repo command line)" -ForegroundColor DarkGray
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

    Write-Host "Waiting 5s for ports to clear..." -ForegroundColor DarkGray
    Start-Sleep -Seconds 5

    # 4. Verify ports are free; warn if not.
    $busy = @()
    foreach ($port in @(8001, 3000)) {
        $still = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if ($still) { $busy += $port }
    }
    if ($busy.Count -gt 0) {
        Write-Host "WARNING: port(s) $($busy -join ', ') still occupied after kill." -ForegroundColor Yellow
        Write-Host "  Run: netstat -ano | findstr LISTENING" -ForegroundColor Yellow
        Write-Host "  Then: taskkill /PID <id> /F" -ForegroundColor Yellow
    } else {
        Write-Host "Done. Ports 8001 and 3000 are free." -ForegroundColor Green
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    Stop-CipDevProcesses
}
