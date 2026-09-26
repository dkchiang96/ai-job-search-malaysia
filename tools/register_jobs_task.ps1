<#
.SYNOPSIS
  Registers (or re-registers) the Windows scheduled task that runs /jobs
  unattended. Run it once by hand. Re-running replaces the task rather than
  duplicating it.

.PARAMETER Days
  Days of the week to run. Default: Monday and Thursday.

.PARAMETER At
  Local time. Default 07:00. Must be before 22:00 (see run_jobs_scheduled.ps1).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\register_jobs_task.ps1 -Days Monday,Wednesday,Friday -At 07:30

.NOTES
  Before registering: open this repo in Claude Code once, interactively, and
  accept the "trust this folder" prompt - an untrusted folder's
  .claude/settings.json permissions are ignored in headless runs.

  Registered without -User/-Password, which means "run only when user is
  logged on". claude needs your interactive credential store. Remove it with:
    Unregister-ScheduledTask -TaskName "AI Job Search - jobs" -Confirm:$false
#>
param(
    [string[]]$Days = @("Monday", "Thursday"),
    [string]$At = "07:00"
)

$ErrorActionPreference = "Stop"
$TaskName = "AI Job Search - jobs"
$Script = Join-Path (Split-Path -Parent $PSScriptRoot) "tools\run_jobs_scheduled.ps1"

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Script`""
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Days -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Runs the ai-job-search /jobs discovery pipeline headless and emails you a summary. See .claude/commands/jobs.md." | Out-Null

Write-Host "Registered '$TaskName' ($($Days -join ', ') at $At)."
Write-Host "Test it now:   schtasks /Run /TN `"$TaskName`""
Write-Host "Logs:          logs\jobs_*.log"
