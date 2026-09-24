# JobStreet and LinkedIn alerts → your pipeline

JobStreet doesn't allow automated search (see [PORTALS.md](PORTALS.md)), but it
will email you new jobs that match a search you've saved. `/gmail-alerts`
reads those emails from your Gmail and adds each job to the same list
`/scrape` builds, so `/rank` and `/apply` treat them like any other job.
LinkedIn alerts work the same way.

Setup takes about 20 minutes, once.

---

## Part 1: Plan your 10 JobStreet searches

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

## Part 2: Gmail filters and labels

In Gmail: **Settings → See all settings → Filters and Blocked Addresses →
Create a new filter.** Create these three (the third only if you use LinkedIn
alerts). For each one, choose **Skip the Inbox**, **Mark as read** and **Apply
the label**. These strings were checked against real alert emails:

| Label (create it exactly like this) | "From" field of the filter |
|---|---|
| `Job Alerts/JobStreet` | `"Jobstreet Job Alerts" OR "LiNa Recommendations"` |
| `Job Alerts/LinkedIn` | `jobalerts-noreply@linkedin.com OR jobs-noreply@linkedin.com` |
| `Job Alerts/Indeed` *(optional, unmaintained parser)* | `donotreply@jobalert.indeed.com` |

Why the JobStreet filter matches display names: JobStreet sends alerts **and**
your application-status emails from the same address. Matching on the alert
display names keeps "your application was viewed" emails in your inbox, where
upstream's `/gmail-sync` looks for them.

Different label names? Put yours in `gmail_alerts/config.json`:

```json
{"portals": {"jobstreet": "Alerts/JS", "linkedin": "Alerts/LI"}}
```

## Part 3: Let the script read those labels

`/gmail-alerts` uses IMAP with a Gmail **app password**. That's a separate
16-character password for one app, which you can revoke any time without
changing your real password. The script opens only the labels above,
read-only, and never marks, moves or deletes mail.

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
3. Run `python3 tools/gmail_imap_fetch.py test --portal jobstreet --file that.txt`.
4. Fix the parser (the anchors are documented in
   `.claude/skills/job-scraper/email-alert-portals.md`), or open an issue with
   the scrubbed sample.

## Privacy, in one list

- The model never sees an email. The script sends it only title, company,
  location, salary and link.
- The app password lives in `gmail_alerts/.env` (gitignored) and is read only
  by the scripts.
- Only the labels you configure are opened, read-only.
- To stop, delete the app password at `myaccount.google.com/apppasswords`.
