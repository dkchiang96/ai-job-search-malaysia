# /jobs - One-Command Discovery Run (Automation pack, optional)

Runs the whole discovery half of the framework in one go:
**scrape the portal CLIs → import email alerts → rank → (optional) history
mirror and Notion → summary.** Each step is the existing command, followed
exactly. `/jobs` adds only the order, the failure isolation, and a headless
mode for scheduled runs. Applying stays manual: `/jobs` never drafts, sends or
submits anything.

---

## Step 0: Parse Input

`$ARGUMENTS` may contain:
- `--scheduled` → unattended mode (see "Scheduled mode" below)
- `--since <YYYY-MM-DD>` → the run date used for scoping Steps 4-6 (default: today)
- `--skip-gmail`, `--skip-rank`, `--skip-notion` → leave out one step
- `--limit <N>` → passed to `/rank` (default 25)

Record `RUN_DATE` once, now (the `--since` value if given, else today), and use
that same value in every later step, even if the run crosses midnight.

## Step 1: Scrape the Portal CLIs

Follow `.claude/skills/job-scraper/SKILL.md` Steps 0-4.75 exactly (search every
enabled portal skill, fetch detail for promising results, dedupe, store,
health check). **Skip its Step 5 presentation and its closing question.**
Keep only the counts (portals run, new jobs stored, health lines) for Step 7.

## Step 2: Import Email Alerts

Unless `--skip-gmail`: follow `.claude/commands/gmail-alerts.md` Steps 2-3. If
the script's `error` names missing Gmail credentials, record `gmail: not set
up (docs/malaysia/JOB-ALERTS.md)` and continue. That is a skipped step, not a
failure.

## Step 3: Rank

Unless `--skip-rank`: follow `.claude/commands/rank.md` Steps 1-4 with
`--limit <N>`. That includes its scorer choice (the Fit Model if
`config/fit_model.json` exists) and its email-alert rule (never fetch a
JobStreet or Indeed page). Skip rank.md's closing question.

## Step 4: History Mirror (only if you opted in)

If `job_scraper/jobs.db` exists: `python3 tools/job_store.py sync`. Otherwise
skip silently.

## Step 5: Notion (only if configured)

Unless `--skip-notion`: if `NOTION_API_TOKEN` is set in `.env` or the environment, run

```bash
python3 tools/notion_sync_api.py sync --since <RUN_DATE>
```

with a Bash timeout of at least 180000 ms. `--since` keeps the sync bounded to
this run's rankings. Without the token, skip silently. The token should point
at a **database created for this sync**: its first run adds any columns it
needs (Key, Score, CS/DV/WP, ...) to whatever database it is given. Interactive users can
still run upstream's `/notion-sync` (Notion MCP) at any time.

## Step 6: Deterministic Summary

```bash
python3 tools/notify_email.py summary --date <RUN_DATE>
```

This is built from `seen_jobs.json` alone. In scheduled mode the wrapper
script emails it to you. Do not send it from here.

## Step 7: Report

```
## /jobs - <RUN_DATE>

scrape:  <P> portals, <N> new (<health lines if any>)
gmail:   <N> new from alerts | not set up | skipped
rank:    <N> ranked, <S> shortlisted, <D> deferred
history: synced | not enabled
notion:  <created>/<updated> | not configured | skipped
FAILED:  <step - one-line reason>        (omit if nothing failed)

<the Step 6 summary text>
```

---

## Failure Isolation

A step that errors is recorded as `FAILED: <step> - <reason>`, and the run
**continues** with the next step. One broken portal or an expired Gmail app
password must never cost the rest of the run. A slow step is not a failed step:
wait for it.

## Scheduled mode (`--scheduled`)

Used by `tools/run_jobs_scheduled.ps1` (Windows Task Scheduler), which starts a
headless `claude -p` session. Before scheduling anything, open the repo in
Claude Code once interactively and accept the "trust this folder" prompt;
otherwise the repo's `.claude/settings.json` permissions are ignored. The
wrapper also passes its own `--allowedTools` list. In this mode:

- **Run every command exactly as the steps write it, from the repo root.** No
  `cd "<path>" &&` prefix and no absolute paths (`python3 tools/x.py ...`,
  `bun run .agents/skills/...`). The pre-approved permissions match the
  literal command, so a prefixed command is denied, and nobody is there to
  approve it. Pass the same rule to every subagent you dispatch.
- **Never ask a question or wait for input.** Nobody is there to answer.
  Where a command would ask, take its documented default.
- **Run everything synchronously.** Never background a command or leave a
  subagent unawaited and then end the turn. A `-p` session gets no follow-up
  turn, so anything left running simply never finishes.
- **Your final message is the Step 7 report**, written only after Steps 1-6
  have actually finished. Anything that could not complete is labelled
  FAILED, never "in progress".

---

## Important Rules

1. **Discovery only.** `/jobs` never runs `/apply`, never drafts a document,
   never sends a message to anyone, never submits an application.
2. **Each step's own rules still apply**: robots.txt gating, never fabricating
   a listing, never fetching a JobStreet or Indeed job page, credentials never in
   context.
3. **Optional parts stay optional.** History, Notion and email run only when
   their setup exists. Their absence is reported, never treated as an error.
