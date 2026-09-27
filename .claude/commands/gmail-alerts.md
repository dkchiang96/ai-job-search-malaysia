# /gmail-alerts - Job Discovery via Portal Email Alerts (Malaysia)

Adds the job listings from your **JobStreet**, **Indeed** and **LinkedIn** alert
emails to the same `job_scraper/seen_jobs.json` that `/scrape` fills, so `/rank`
and `/apply` treat them like any other job.

**Why email:** JobStreet is Malaysia's largest job board, and its `robots.txt`
disallows automated access to its job pages and query-string searches (AI
crawlers are named explicitly). Indeed's Terms ban bots and AI agents from the
site outright. No `jobstreet-search` or `indeed-search` CLI can be built without
ignoring that. Both *do* let you save a search on their own site and email you
new matches. Reading your own inbox never touches their servers.
Background and setup: `docs/malaysia/JOB-ALERTS.md`.

**Everything deterministic runs outside model context.**
`tools/gmail_imap_fetch.py` logs into Gmail over IMAP with an app password,
reads only the configured labels, parses each digest with the recipes in
`tools/digest_parsers.py`, and writes new entries itself. You never see a raw
email body, only the script's compact JSON summary.

---

## Step 0: Prerequisites

Nothing to check up front. The script reports its own missing setup. If Step 2
returns an `error` naming `GMAIL_IMAP_USER` / `GMAIL_IMAP_APP_PASSWORD`, stop and
point the user at `docs/malaysia/JOB-ALERTS.md` (Part 3, about 5 minutes).
If they're unsure about connecting email, point them at that doc's "Privacy"
section: a separate Gmail just for alerts, or skipping this, are both fine. **Never ask for the app password in chat and never write it
anywhere yourself.** The user puts it in `gmail_alerts/.env`, which is
gitignored.

## Step 1: Parse Input

`$ARGUMENTS` may contain:
- nothing → every configured portal, since the last run (30 days on the first run)
- a portal name, e.g. `/gmail-alerts jobstreet` → that portal only
- `since <YYYY-MM-DD>` → override the lookback for this run
- `dry-run` → parse and count, write nothing

## Step 2: Fetch, Parse, Store

```bash
python3 tools/gmail_imap_fetch.py run [--portal <name>] [--since <YYYY-MM-DD>] [--dry-run]
```

Output (abridged):

```json
{
  "portals": [{"portal": "jobstreet", "label": "Job Alerts/JobStreet", "status": "ok",
               "messages_found": 9, "messages_new": 3, "listings_extracted": 41}],
  "new_jobs_stored": 17, "duplicates_skipped": 24,
  "new_listings": [{"key": "...", "title": "...", "company": "...", "location": "...",
                    "salary": "RM 9,000 – RM 12,000 per month", "portal": "jobstreet-alert",
                    "alert_name": "operations in Selangor", "url": "..."}]
}
```

- `status: "label not found - pending mailbox setup"`: that portal's Gmail
  filter/label doesn't exist yet. Report it and don't guess a workaround.
- `duplicates_skipped` is expected to be high. Portals re-send the same job
  across digests, and a job already found by a portal CLI is never
  overwritten (dedup uses `tools/job_key.py`'s company+title key, so rotating
  tracking links don't defeat it).

## Step 3: Quick Fit, from the Email Fields Only

For each entry in `new_listings`, assign a quick fit exactly as
`job-scraper/SKILL.md` Step 3 defines it (High / Medium / Low, with the Language
Gate override), using only title, company, location and salary. Also apply the
Location Filter in `search-queries.md`.

**Do not fetch the posting to do this.** The URLs are the portal's tracking
redirects:

- **JobStreet** links resolve to `my.jobstreet.com/job/...`, which
  `robots.txt` disallows. Never fetch them, never rewrite them into a
  JobStreet API call. They are for the user to click.
- **Indeed** links (`malaysia.indeed.com/rc/clk/...`, `/pagead/clk/...`,
  `engage.indeed.com/...`) redirect to robots-disallowed job pages, and Indeed's
  Terms bar AI agents. Never fetch them or rebuild a `viewjob` URL. Treat an
  Indeed salary as possibly Indeed's estimate; it's stored tagged as such.
- **LinkedIn** links are stored in the `my.linkedin.com/jobs/view/<id>` form.
  `linkedin-search detail <id>` is the supported way to read one, and it is
  `/rank`'s job, not this command's.

Write the verdicts back with the tool. Put `{"<key>": "high"|"medium"|"low", ...}`
in a temporary file outside the repo, then:

```bash
python3 tools/gmail_imap_fetch.py set-fit --results "<path to that file>"
```

It changes only the `fit` field of existing keys and reports unknown keys or
bad values. Never read or rewrite `seen_jobs.json` by hand.

## Step 4: Present

```
## Gmail Alerts - YYYY-MM-DD

Read N new alert emails across P portal(s) since <since>.
Stored X new jobs (Y duplicates of jobs already seen skipped).

pending mailbox setup: <portal>, <portal>

| # | Fit | Title | Company | Location | Salary (RM/month) | From alert | Link |
|---|-----|-------|---------|----------|-------------------|------------|------|
```

Omit the `pending mailbox setup:` line when every portal has its label. Then:

- If 8 or more new jobs were stored, suggest `/rank`. It finds and reads the full
  posting for each job (for JobStreet and Indeed jobs, on the employer's own
  site or a mirror; see `rank.md` Step 2) before scoring.
- Once a month, suggest `python3 tools/job_store.py yield --by alert` (optional
  SQLite mirror). It shows which JobStreet saved searches actually produce
  shortlisted jobs, which matters because JobStreet allows only 10.

---

## Important Rules

1. **Read-only against Gmail.** The script opens labels read-only and fetches with
   `BODY.PEEK`, so mail is never marked read, moved, labelled or deleted.
2. **Never fabricate a listing.** A digest block either matches its documented
   shape or yields nothing. No model step fills gaps with guesses.
3. **Never fetch a JobStreet or Indeed job page**, directly, via redirect, or
   via any of their endpoints. This rule is why the email path exists.
4. **Credentials never enter model context.** The app password lives in
   `gmail_alerts/.env` or the environment, is read by the script only, and is
   never echoed, requested in chat, or written by you.
5. **A missing Gmail label is reported, never guessed at.**
6. **Idempotent.** Processed message UIDs are tracked per label in
   `gmail_alerts/imap_state.json` (gitignored), so re-running never re-imports a
   message.
