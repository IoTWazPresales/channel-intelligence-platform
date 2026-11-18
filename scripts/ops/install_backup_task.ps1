# Register (or print) the Windows scheduled task that runs scripts/ops/nightly_backup_cip.ps1 daily.
# Default prints the task and the one-time setup; -Register creates it for the current user.
# Registering a task and setting the database URL environment variables are operator steps (Warren).
#
#   .\scripts\ops\install_backup_task.ps1                  # print only
#   .\scripts\ops\install_backup_task.ps1 -Register        # create or replace the task
param(
    [string]$TaskName = 'CIP nightly backup',
    [string]$At = '02:30',
    [switch]$Register
)
$ErrorActionPreference = 'Stop'
$script = (Resolve-Path (Join-Path $PSScriptRoot 'nightly_backup_cip.ps1')).Path
$taskArgs = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}"' -f $script

Write-Host "Task: '$TaskName', daily at $At, as $env:USERNAME, runs: powershell.exe $taskArgs"
Write-Host 'One-time setup (operator, not committed anywhere):'
Write-Host '  [Environment]::SetEnvironmentVariable(''CIP_BACKUP_DATABASE_URL'', ''postgresql://<user>:<password>@127.0.0.1:5432/cip'', ''User'')'
Write-Host '  [Environment]::SetEnvironmentVariable(''CIP_RESTORE_SMOKE_URL'', ''postgresql://<user>:<password>@127.0.0.1:5432/<disposable db>'', ''User'')'
if (-not $Register) { Write-Host 'Not registered (pass -Register).'; exit 0 }

$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $taskArgs
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description 'CIP nightly backup, retention and periodic disposable restore (scripts/ops/nightly_backup_cip.ps1)' -Force | Out-Null
Write-Host "Registered '$TaskName'. Check: Get-ScheduledTaskInfo -TaskName '$TaskName'"