# Install (or remove) the CIP always-on supervisor for this Windows user (N-0073). No admin rights needed.
#
# Usage:
#   .\scripts\cip-supervisor-install.ps1             # Startup shortcut + desktop shortcuts
#   .\scripts\cip-supervisor-install.ps1 -Start      # same, and start the supervisor now (hidden)
#   .\scripts\cip-supervisor-install.ps1 -Uninstall  # remove the shortcuts (does not stop a running supervisor)
#   .\scripts\cip-supervisor-install.ps1 -Check      # report whether the shortcuts exist and what they run; changes nothing
#
# The Startup shortcut lives in %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup and runs:
#   powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File <repo>\scripts\cip-supervisor.ps1
# Desktop: 'CIP status.url' opens the local status page; 'CIP public link.url' is written by the
# supervisor whenever the tunnel address changes.
param([switch]$Uninstall, [switch]$Start, [switch]$Check)
$ErrorActionPreference = 'Stop'

$supervisor = Join-Path $PSScriptRoot 'cip-supervisor.ps1'
$startupDir = [Environment]::GetFolderPath('Startup')
$desktop    = [Environment]::GetFolderPath('Desktop')
$startupLnk = Join-Path $startupDir 'CIP always-on.lnk'
$statusUrl  = Join-Path $desktop 'CIP status.url'
$publicUrl  = Join-Path $desktop 'CIP public link.url'
$stateDir   = Join-Path $env:LOCALAPPDATA 'CIP\always-on'
$linkHtml   = Join-Path $stateDir 'link.html'

if ($Check) {
    $shell = New-Object -ComObject WScript.Shell
    $ok = $true
    if (Test-Path $startupLnk) {
        $l = $shell.CreateShortcut($startupLnk)
        "Startup shortcut: present ($startupLnk)"
        "  target: $($l.TargetPath)"
        "  args:   $($l.Arguments)"
        "  window: $($l.WindowStyle) (7 = minimized/hidden)"
        if (-not $l.Arguments.Contains($supervisor)) { "  WARNING: it does not run $supervisor"; $ok = $false }
    } else { "Startup shortcut: MISSING ($startupLnk)"; $ok = $false }
    foreach ($f in @($statusUrl, $publicUrl)) {
        if (Test-Path $f) {
            $url = (Get-Content $f | Where-Object { $_.StartsWith('URL=') } | Select-Object -First 1)
            "Desktop shortcut: present ($f) $url"
        } else { "Desktop shortcut: MISSING ($f)"; $ok = $false }
    }
    if ($ok) { exit 0 } else { exit 1 }
}

if ($Uninstall) {
    foreach ($f in @($startupLnk, $statusUrl, $publicUrl)) {
        if (Test-Path $f) { Remove-Item $f -Force; Write-Host "Removed $f" }
    }
    Write-Host 'Uninstalled. A running supervisor keeps running; stop it with .\scripts\cip-supervisor-stop.ps1'
    exit 0
}

# Group Policy can forbid -ExecutionPolicy Bypass; then the Startup shortcut would silently do nothing.
foreach ($scope in @('MachinePolicy', 'UserPolicy')) {
    $policy = Get-ExecutionPolicy -Scope $scope
    if ($policy -ne 'Undefined' -and $policy -ne 'Bypass' -and $policy -ne 'Unrestricted') {
        Write-Warning "Execution policy is set by Group Policy ($scope = $policy). The Startup shortcut may be blocked."
    }
}

New-Item -ItemType Directory -Path $stateDir -Force | Out-Null

$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($startupLnk)
$lnk.TargetPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$lnk.Arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}"' -f $supervisor
$lnk.WorkingDirectory = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$lnk.WindowStyle = 7
$lnk.Description = 'CIP always-on supervisor (Redis, worker, API, web, Cloudflare tunnel)'
$lnk.Save()
Write-Host "Startup shortcut: $startupLnk"

$fileUrl = 'file:///' + $linkHtml.Replace('\', '/')
[System.IO.File]::WriteAllText($statusUrl, "[InternetShortcut]`r`nURL=$fileUrl`r`n", [System.Text.Encoding]::ASCII)
Write-Host "Desktop shortcut: $statusUrl"

if ($Start) {
    Start-Process -FilePath 'powershell.exe' -WindowStyle Hidden -ArgumentList @(
        '-NoProfile', '-WindowStyle', 'Hidden', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f $supervisor)
    ) | Out-Null
    Write-Host 'Supervisor started (hidden). A second copy exits on its own, so this is safe to repeat.'
}
