# JobStreet, Indeed and LinkedIn alerts → your pipeline

JobStreet and Indeed don't allow automated search (see [PORTALS.md](PORTALS.md)),
but both will email you new jobs that match a search you've saved.
`/gmail-alerts` reads those emails from your Gmail and adds each job to the same
list `/scrape` builds, so `/rank` and `/apply` treat them like any other job.
LinkedIn alerts work the same way. They add jobs that LinkedIn's own
recommendations surface and a keyword search misses.

Setup takes about 20 minutes, once. **Uneasy about connecting your email?**
Read [Privacy: what reads your email, and the alternatives](#privacy-what-reads-your-email-and-the-alternatives)
first. You can use a separate Gmail just for job alerts, or skip this part
entirely.

---

## Part 1: Plan your saved searches

### JobStreet (10 at most)

**JobStreet allows at most 10 saved-search alerts per account**, so each slot
matters. The lessons behind this worksheet came from running it on a real
search:

1. **Scope to a city, not "Remote".** JobStreet listings are mostly tagged with
   a city. In one account, the same search produced **99+ matches scoped to Kuala
   Lumpur versus 11 scoped to Remote**. Use Remote only for a search you
   specifically want remote-only results from.
2. **Use exact titles in quotes, and `OR` for synonyms.** For example
   `"Operations Director" OR "Director of Operations"`. A bare generic word
   ("manager") floods the alert with noise.
3. **Put the salary filter on broad searches.** A single keyword like
   `operations` with a salary band set is a good broad net.
4. **Set every alert to daily.** Weekly alerts batch a week of jobs into one
   email, and your competition applies days earlier.
5. **Don't duplicate.** Two alerts that differ only in wording waste a slot.
   After a month, `python3 tools/job_store.py yield --by alert` shows which
   alerts actually produce shortlisted jobs. Cut the ones that don't.

| # | Search text | Location | Salary filter | Why this slot |
|---|---|---|---|---|
| 1 | `"<your main title>"` | Kuala Lumpur | - | your core role, where most listings are |
| 2 | `"<your main title>"` | Selangor | - | same role, the rest of the Klang Valley |
| 3 | `"<title variant 1>" OR "<title variant 2>"` | Kuala Lumpur | - | the same job under other names |
| 4 | `"<one level up>"` | Kuala Lumpur | - | stretch roles |
| 5 | `<broad keyword>` | Kuala Lumpur | your range | the broad net |
| 6 | `<broad keyword>` | Selangor | your range | the broad net, Selangor |
| 7 | `"<adjacent title>"` | Kuala Lumpur | - | a pivot you'd consider |
| 8 | `"<industry keyword>" <function>` | Kuala Lumpur | - | your strongest industry |
| 9 | `"<main title>"` | Remote | - | only if you opted into remote |
| 10 | (keep free) | | | test a new search for 2 weeks before committing |

**How to save one (in your browser, on JobStreet itself):** run the search
with its filters, then use the save / job-alert option on the results page and
choose **daily** email. Nothing in this repo does this for you. It's your
account, and it's a one-time step.

### Indeed

On `malaysia.indeed.com`, run a search (what + where), then use **Get new jobs
for this search by email**. Indeed doesn't impose JobStreet's tight cap, but the
same rules apply: exact titles, a city rather than "Remote" unless you want
remote-only, and cut alerts that never produce a shortlisted job.

- **Indeed shows its own salary estimate** when a posting has none, and the
  email doesn't mark which figures are estimates. Every Indeed salary is
  therefore stored tagged "(Indeed: may be estimated)". You still see it, and
  it's benchmarked separately, but it never rules a job out.
- **"Sponsored" jobs** in the email are kept. They're real postings an employer
  paid to promote.

### LinkedIn

On LinkedIn Jobs, run a search and switch on **Set alert**. Daily, again.

## Part 2: Gmail filters and labels

In Gmail: **Settings → See all settings → Filters and Blocked Addresses →
Create a new filter.** Create one per portal you use. For each, choose **Skip
the Inbox**, **Mark as read** and **Apply the label**. These strings were checked
against real alert emails:

| Label (create it exactly like this) | "From" field of the filter |
|---|---|
| `Job Alerts/JobStreet` | `"Jobstreet Job Alerts" OR "LiNa Recommendations"` |
| `Job Alerts/Indeed` | `donotreply@jobalert.indeed.com` |
| `Job Alerts/LinkedIn` | `jobalerts-noreply@linkedin.com OR jobs-noreply@linkedin.com` |

You don't need all three. A portal whose label doesn't exist is reported as
"pending mailbox setup" and skipped.

Why the JobStreet filter matches display names: JobStreet sends alerts **and**
your application-status emails from the same address. Matching on the alert
display names keeps "your application was viewed" emails in your inbox, where
upstream's `/gmail-sync` looks for them. Indeed's alert address sends nothing
but alerts; application emails come from other Indeed addresses.

Different label names? Put yours in `gmail_alerts/config.json`, listing only
the portals you want:

```json
{"portals": {"jobstreet": "Alerts/JS", "indeed": "Alerts/Indeed", "linkedin": "Alerts/LI"}}
```

## Part 3: Let the script read those labels

`/gmail-alerts` uses IMAP with a Gmail **app password**. That's a separate
16-character password, which you can revoke any time without changing your
real password.

1. **Turn on IMAP:** Gmail → Settings → See all settings → *Forwarding and
   POP/IMAP* → Enable IMAP → Save.
2. **Turn on 2-Step Verification** for your Google account if it isn't
   already. App passwords require it.
3. **Create an app password:** go to `myaccount.google.com/apppasswords` and
   name it `ai-job-search`. Copy the 16 characters.
4. **Create `gmail_alerts/.env`** in the repo (the whole `gmail_alerts/` folder
   is gitignored). Type in these two lines yourself. Never paste the password
   into a chat:

   ```
   GMAIL_IMAP_USER=you@gmail.com
   GMAIL_IMAP_APP_PASSWORD=abcdefghijklmnop
   ```

5. **Test without writing anything:**

   ```bash
   python3 tools/gmail_imap_fetch.py run --dry-run
   ```

   You should see each label with `"status": "ok"` and a count of listings.
   `label not found` means the Gmail label name doesn't match. Fix it in Gmail
   or in `gmail_alerts/config.json`.

Then in Claude Code: `/gmail-alerts`, then `/rank`.

## When a parser stops working

Portals redesign their emails now and then. The symptom is an alert label
with messages but `listings_extracted: 0`. To fix it:

1. In Gmail, open the newest alert → **⋮ → Show original → Download original**.
2. Copy the plain-text part into a `.txt` file and **remove your name and email**.
3. Run `python3 tools/gmail_imap_fetch.py test --portal indeed --file that.txt`
   (or `jobstreet` / `linkedin`).
4. Fix the parser (the anchors are documented in
   `.claude/skills/job-scraper/email-alert-portals.md`), or open an issue with
   the scrubbed sample.

## Privacy: what reads your email, and the alternatives

It's reasonable to be uneasy about an AI tool and your inbox, so here is
exactly what happens.

**What reads the email is a Python script, not the AI.**
[`tools/gmail_imap_fetch.py`](../../tools/gmail_imap_fetch.py) logs in, opens
only the labels in your config, parses each alert with fixed rules
([`tools/digest_parsers.py`](../../tools/digest_parsers.py)), and writes the jobs
to `job_scraper/seen_jobs.json` on your computer.

**What reaches Claude** is only each job's title, company, location, salary,
link and alert name: the same fields a job-board search returns. Claude never
receives an email body, a sender, or anything from outside the job-alert labels.

**What the script does not do:** it opens the labels read-only and fetches with
`BODY.PEEK`, so it never marks, moves, labels, deletes or sends mail. The
optional run-summary email (`tools/notify_email.py`) can only send to your own
address.

**The honest limit:** Google's app passwords are all-or-nothing. An app password
*could* open your whole mailbox. The code is what keeps it to the job-alert
labels: two short files you can read. If that isn't enough for you, use one of
these instead:

1. **A separate Gmail just for job alerts (recommended if you're unsure).**
   Create a new Gmail account and point the job-alert emails at it. You can
   either sign up to JobStreet, Indeed and LinkedIn alerts with it, or have
   your main Gmail auto-forward only those senders to it (Settings → Forwarding
   → add the address, then a filter on the senders above → *Forward it to*).
   The app password then unlocks an inbox that contains nothing but job alerts.
2. **Skip email entirely.** Don't create `gmail_alerts/.env`. `/scrape` still
   searches LinkedIn, Hiredly and freehire (plus the remote boards if you opted
   in). You lose JobStreet and Indeed, which can't be reached any other
   permitted way; you can still read their alerts yourself and paste a posting
   into `/apply`.

**To stop at any time:** delete the app password at
`myaccount.google.com/apppasswords`. Access ends immediately, and nothing else
changes.
