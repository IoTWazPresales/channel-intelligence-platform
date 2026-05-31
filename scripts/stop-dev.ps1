# Stop local CIP dev stack processes (ports + repo-scoped node/python/pnpm).
# Usage: .\scripts\stop-dev.ps1

$ErrorActionPreference = 'Continue'

function Stop-CipDevProcesses {
    $repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
    $repoNorm = $repo.TrimEnd('\')

    Write-Host "Stopping CIP dev processes (repo: $repoNorm)" -ForegroundColor Cyan

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
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            Write-Host "  Killed PID $procId (listening on port $port)"
        }
    }

    $procNames = @('node.exe', 'python.exe', 'pythonw.exe', 'pnpm.exe', 'celery.exe')
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | ForEach-Object {
        if ($procNames -notcontains $_.Name) { return }
        $cmd = $_.CommandLine
        if (-not $cmd) { return }
        if ($cmd -notlike "*$repoNorm*") { return }
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host "  Killed $($_.Name) PID $($_.ProcessId) (repo command line)"
    }

    Write-Host "Waiting 3s for ports to clear..." -ForegroundColor DarkGray
    Start-Sleep -Seconds 3
    Write-Host "Done." -ForegroundColor Green
}

if ($MyInvocation.InvocationName -ne '.') {
    Stop-CipDevProcesses
}
