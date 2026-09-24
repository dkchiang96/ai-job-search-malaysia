# Email Alert Portal Reference

Parsing anchors for the job-alert digest emails `/gmail-alerts` reads
(`tools/digest_parsers.py` implements them, `tools/gmail_imap_fetch.py` runs
them). The same discipline as `/add-portal`: **never register an anchor that
hasn't been checked against a real sample email.** When a portal redesigns its
email, update the parser and this file together, and add a test built from the
new layout.

Each portal tracks two separate facts:

- **Gmail label**: a Gmail filter reliably sorts that portal's alert mail into
  one label, so the importer can find it.
- **Listing anchor**: the digest's plain-text layout has been parsed against real
  samples, so title / company / location / salary / link can be extracted.

To check a fresh sample: in Gmail, open the alert, then **⋮ → Show original →
Download original**. Save the plain-text part as a `.txt` and run
`python3 tools/gmail_imap_fetch.py test --portal <portal> --file <file>`.
Scrub your name and email from any sample before sharing it in an issue.

## JobStreet Malaysia (default on)

- **Suggested filter:** `from:("Jobstreet Job Alerts" OR "LiNa Recommendations")`
  → Skip Inbox, Apply label `Job Alerts/JobStreet`. Both display names send
  from the same address JobStreet uses for application-status mail
  ("Jobstreet Applications", "Jobstreet Reminders"). Matching on **display
  name** keeps those status emails in your inbox, where `/gmail-sync` looks for
  them.
- **Subjects:** saved-search digest `"<N> new jobs for <saved search name>"`,
  which is where the importer's `alert_name` comes from. Recommendation digest:
  `"<Job title> [Strong applicant] + <N> new jobs - Job Alert from Jobstreet.com"`
  (no alert name).
- **Listing anchor** (checked against 8 real digests 2026-08-22 and 14 more
  2026-09-10). Each listing is, in order:
  1. an optional `logo` line followed by its own tracking link (discard both)
  2. **title**
  3. **company**
  4. a blank line
  5. optionally a `Posted on <D Mon YYYY>` line or a `Strong applicant` badge,
     each optionally followed by a blank line
  6. **location** (`<Area>, <State>`)
  7. an optional **salary** line (`RM X – RM Y per month`)
  8. an optional blank line
  9. the listing's **tracking link** in `[brackets]`

  A greeting precedes the first listing. A `Take your next career step` promo
  block (CTA, sentence, `Explore now`, each with a link) sits between the main
  listings and an optional `Jobs you may have missed` section (heading plus a
  `Matches your preference...` subheading). Keep that section's listings; they
  are real. The footer starts at `View all matching jobs`, and parsing stops
  there.
- **Quirks:**
  - Links are per-recipient tracking redirects (`url.jobstreet.com/ss/c/...`)
    that land on `my.jobstreet.com/job/...`. That path is **robots-disallowed**
    for every agent. Never fetch it. The link is for the user to click. `/rank`
    finds the employer's own posting instead (see `rank.md` Step 2).
  - The same saved search is often re-sent hours apart with overlapping jobs.
    Dedup is by company+title (`tools/job_key.py`), never by link.
  - **JobStreet caps saved-search alerts at 10 per account.** See
    `docs/malaysia/JOB-ALERTS.md` for how to spend them.

## LinkedIn (default on)

`linkedin-search` already covers LinkedIn by CLI. The alert emails are included
because LinkedIn's own recommendation engine surfaces jobs a keyword search
misses, and the filter keeps the daily volume out of your inbox.

- **Suggested filter:** `from:(jobalerts-noreply@linkedin.com OR jobs-noreply@linkedin.com)`
  → Skip Inbox, Apply label `Job Alerts/LinkedIn`. This excludes invitations and
  messages. It sweeps in occasional "Your application was viewed" notices, which
  parse to nothing.
- **Subjects:** `"Your job alert for <search>"` gives the `alert_name`.
  Per-posting and "jobs similar to" alerts have no alert name.
- **Listing anchor** (checked against 5 real digests 2026-08-22): blocks
  separated by a `-----` rule line. Each block is **title**, **company**,
  **location**, then optional per-viewer decoration lines (`N connections`,
  `This company is actively hiring`, `Fast growing`, `N school alumni`, `Be an
  early applicant`), then `View job: <url>`. The first block also carries the
  email's own header, so the fields are the **three non-decoration lines
  immediately before `View job:`**, not the block's first three lines.
- **Quirks:** `linkedin.com/comm/jobs/view/<id>` links need a logged-in session.
  The parser rewrites them to `https://my.linkedin.com/jobs/view/<id>`, the form
  `linkedin-search` itself returns, so dedup against CLI results works.

## Indeed Malaysia (opt-in, not maintained)

The parser was built against 6 real digests on 2026-08-22 and has not been
re-checked since. Every Indeed tracking link tested at the time returned HTTP
404 when fetched, so an Indeed listing can rarely be read past its email
fields. Enable it only if you accept that. Add
`"indeed": "Job Alerts/Indeed"` to `gmail_alerts/config.json`, and send a fresh
sample (see above) if it no longer parses.

- **Suggested filter:** `from:(donotreply@jobalert.indeed.com)`. This address is
  used only for alerts.
- **Subjects:** the one-time "Your job alert for ... is now active" confirmation
  has no listings. Digest: `"<search> in <location>: <first title> at <company>
  and <N> more new jobs - ..."`.
- **Listing anchor:** after a `Jobs 1-N of N new jobs` header and a
  `See matching results on Indeed:` line, each listing is **title**,
  **company - location** (split on the last `" - "`), optional **salary**,
  optional `Easily apply`, a one-line snippet, a relative date (`Just posted`,
  `N days ago`), then the tracking link. There are no blank separators between
  listings; the relative-date line ends each one.
- **Quirks:** salaries are often Indeed's *estimate* (its footer says so).
  `tools/myr_salary.py` flags `estimated` when the text says it. The `jk=` job
  key in the plain-text body is often mangled. Never rebuild a `viewjob?jk=`
  URL from it.

## Adding another portal's alerts

Maukerja, Glints and others block automated search in `robots.txt` but may
offer email alerts (see `docs/malaysia/PORTALS.md`). To add one:

1. Collect 3+ real digests.
2. Document the anchor here.
3. Add `parse_<portal>` and a subject pattern to `tools/digest_parsers.py`.
4. Add a test built from a scrubbed sample.
5. Register its label in `gmail_alerts/config.json`.
