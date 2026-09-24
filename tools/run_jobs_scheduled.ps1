<#
.SYNOPSIS
  Unattended /jobs run for Windows Task Scheduler (Automation pack, optional).

.DESCRIPTION
  1. Fixes RUN_DATE before Claude starts and refuses to start after 22:00, so
     a slow run can't cross midnight and split its date scoping.
  2. Takes a lock file so an overrunning run is never launched twice.
  3. Runs headless Claude Code:  claude -p "/jobs --scheduled --since RUN_DATE"
     with --permission-mode acceptEdits and an explicit --allowedTools list.
     It never uses bypassPermissions. A tool that isn't on the list is denied
     and shows up in the log, and you decide whether to add it.
  4. Emails you a summary built from job_scraper/seen_jobs.json by
     tools/notify_email.py (to your own address only).

  Register it with tools/register_jobs_task.ps1. The task must run "only
  when user is logged on": claude reads its login from your Windows
  credential store, which a logged-off (session 0) task cannot reach.
#>

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$RunDate  = Get-Date -Format "yyyy-MM-dd"
$Stamp    = Get-Date -Format "yyyy-MM-dd_HHmmss"
$LogDir   = Join-Path $RepoRoot "logs"
$LockFile = Join-Path $LogDir "jobs_scheduled.lock"
$LogFile  = Join-Path $LogDir "jobs_$Stamp.log"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Log([string]$msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path $LogFile -Value $line -Encoding utf8
    Write-Output $line
}

# Tools the unattended run may use without a prompt. Mirrors what /jobs'
# steps call; nothing here can send mail except notify_email.py, and that
# only to yourself. Add an entry only after a denial in the log shows it's needed.
$PyTools = @("job_key.py", "rank_state.py", "robots_check.py", "gmail_imap_fetch.py", "fit_model.py",
             "job_store.py", "notion_sync_api.py", "myr_salary.py")
$AllowedTools = (@(
    "Read", "Write", "Edit", "Glob", "Grep", "WebSearch", "WebFetch", "Agent",
    "Bash(bun --version)",
    "Bash(bun run .agents/skills/*/cli/src/cli.ts *)",
    "Bash(python tools/notify_email.py summary:*)", "Bash(python3 tools/notify_email.py summary:*)"
) + ($PyTools | ForEach-Object { "Bash(python tools/$_`:*)"; "Bash(python3 tools/$_`:*)" })) -join ","

if ((Get-Date).Hour -ge 22) {
    Write-Log "Not starting: after 22:00 a slow run could cross midnight and split RUN_DATE scoping."
    exit 0
}
if (Test-Path $LockFile) {
    $lock = Get-Content $LockFile -Raw | ConvertFrom-Json
    if (((Get-Date) - [datetime]$lock.started).TotalHours -lt 3) {
        Write-Log "Not starting: previous run (PID $($lock.pid), $($lock.started)) is still inside its 3-hour window."
        exit 0
    }
    Write-Log "Ignoring stale lock from $($lock.started)."
}
@{ pid = $PID; started = (Get-Date -Format "o") } | ConvertTo-Json | Set-Content -Path $LockFile -Encoding utf8

try {
    $prompt = "/jobs --scheduled --since $RunDate"
    $jsonOut = Join-Path $LogDir "jobs_$Stamp.json"
    Write-Log "Starting: claude -p `"$prompt`" (acceptEdits, explicit allowed tools)"

    # A native command's stderr under ErrorActionPreference=Stop becomes a
    # terminating error on the first harmless stderr line - relax it for this call only.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $raw = & claude -p $prompt --output-format json --permission-mode acceptEdits --allowedTools $AllowedTools 2>&1
    } finally { $ErrorActionPreference = $prev }
    $exit = $LASTEXITCODE
    $raw | Set-Content -Path $jsonOut -Encoding utf8

    $parsed = $null
    try { $parsed = ($raw | Out-String) | ConvertFrom-Json } catch { Write-Log "Could not parse claude's JSON output." }
    $ok = ($exit -eq 0) -and -not ($parsed -and $parsed.is_error)
    if ($parsed -and $parsed.permission_denials -and $parsed.permission_denials.Count -gt 0) {
        Write-Log "Permission denials (review before widening AllowedTools): $($parsed.permission_denials | ConvertTo-Json -Compress -Depth 4)"
    }
    if ($parsed -and $parsed.total_cost_usd) { Write-Log ("Cost this run: USD {0:N4}" -f [double]$parsed.total_cost_usd) }

    if ($ok) {
        Write-Log "Run finished. Sending summary."
        & python tools\notify_email.py summary --date $RunDate --send
    } else {
        Write-Log "Run FAILED (exit $exit). Sending failure notice."
        $body = Join-Path $LogDir "failbody_$Stamp.txt"
        "Scheduled /jobs run did not complete for $RunDate (exit code $exit).`n`nLog: $LogFile`nClaude output: $jsonOut" |
            Set-Content -Path $body -Encoding utf8
        & python tools\notify_email.py send --subject "[jobs] Scheduled run FAILED - $RunDate" --body-file $body
    }
} finally {
    Remove-Item $LockFile -ErrorAction SilentlyContinue
    Write-Log "Done."
}
