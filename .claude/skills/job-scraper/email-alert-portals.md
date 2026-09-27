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
- **Listing anchor** (layout as of 2026-09; re-checked against all 64 JobStreet
  digests from 2026-09-19 to 26: 774 listings, none malformed). **Every card ends
  with its own tracking link in `[brackets]`**, so the parser splits on links and
  reads each card by position:
  1. **title**
  2. **company**
  3. zero or more of: a badge (`Strong applicant`, `Very strong applicant`) or
     `Posted on <D Mon YYYY>`
  4. **location** (`<Area>, <State>`, sometimes `Kuala Lumpur (Remote)`)
  5. then, in any order, all optional: the **salary** (`RM X – RM Y per month`,
     with a no-break space after `RM`), `Profile salary match`, up to three
     `* <benefit>` bullets (a long bullet **wraps onto a second line**), and
     `Recently posted`

  Only title, company and location depend on position. After the location,
  only the first `RM` line is used, so a decoration JobStreet adds later can't
  shift a field. A `logo` line comes with its own link (a card of just `logo`,
  which is skipped). A greeting precedes the first listing. A `Take your next career step` promo
  block sits between the main listings and an optional `Jobs you may have
  missed` section (heading plus a `Matches your preference...` subheading).
  Keep that section's listings; they are real. The footer starts at
  `Rate your recent employer`, `Was this email useful?` (followed by `Yes`/`No`
  links) or `View all matching jobs`, and parsing stops there.
  *History:* before 2026-09 the cards had no bullets, badge or recency lines, and
  the old fixed-sequence parser stored the new bullets and `Yes`/`No` links as
  job titles. A card-based parser is the fix: expect JobStreet to keep
  adding decoration lines.
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

## Indeed Malaysia (default on)

Indeed's Terms ban "any automated system (bots, scrapers, spiders, AI or Agentic
AI)" from the site, and `robots.txt` disallows its job pages (`/viewjob`) and
click-through links (`/rc/`, `/pagead/`). A plain request to its search page
returns 403. Alerts are the only permitted way in.

- **Suggested filter:** `from:(donotreply@jobalert.indeed.com)` → Skip Inbox,
  Apply label `Job Alerts/Indeed`. This address sends only alerts (checked:
  315 of 315 messages from it were alerts or alert activations). Application
  mail comes from `indeedapply@indeed.com` and stays in your inbox.
- **Alert name:** read from the body line `<N> new <search> jobs in <place>` (or
  `<N> new <search> jobs (Remote)`), giving `"<search> in <place>"`. The
  subject is the fallback only: Indeed has worded it at least eight ways since
  2026-04 (`"<title> at <company>. <N> more <search> jobs in <place>"`,
  `"<search>: <title> at <company> and <N> more new jobs"`, ...).
- **Listing anchor** (layout as of 2026-04 to 09; checked 2026-09-27 against
  every alert in one real inbox from 2026-04-01 to 26: 315 emails, 4,387
  cards, none malformed). **Every card ends with its own link on its own line**,
  so the parser splits on links, like JobStreet:
  1. Header, all skipped: `Indeed Job Alert`, the `<N> new <search> jobs ...`
     line (**listings start after it**), `Jobs 1-N of M new jobs`,
     `See matching results on Indeed: <url>`.
  2. Each card: **title**, **company - location** (split on the last `" - "`;
     a title may itself contain `" - "`), then optional **salary**, optional
     badges (`Responsive employer`, `Easily apply`), a one-line snippet, and a
     relative date (`Just posted`, `1 day ago`, `N days ago`) that **must** be
     the card's last line or the card is dropped.
  3. The link: `malaysia.indeed.com/rc/clk/...` (organic),
     `.../pagead/clk/...` (sponsored, which are extra cards beyond the header's
     count, so `Jobs 1-22 of 24` can carry 24 cards), or
     `engage.indeed.com/f/a/...` (in activation emails).
  4. Footer after the last link (`Do not share this email`, the estimate note,
     legal and unsubscribe lines) is ignored.
- **Salary:** only a whole line shaped `[From |Up to ]RM X[ - RM Y] a
  month|an hour|a day|a week|a year` counts, so a figure inside the snippet
  can't be mistaken for one. Seen: month 81%, hour 13%, then day, year and week.
  The footer says *"Salaries estimated if unavailable"*, and no card says which
  figure is an estimate, so the parser appends `(Indeed: may be estimated)` to
  every Indeed salary. `tools/myr_salary.py` reads that as `estimated`: the
  figure is shown and benchmarked separately, and never trips a salary floor.
- **Activation emails** (`"Your job alert for ... is now active"`) usually carry
  a first batch of listings under the same `<N> new ...` line, with
  `engage.indeed.com` links. They are parsed like digests. One with no
  listings has no count line and yields nothing.
- **Quirks:** every link is a per-recipient tracking redirect to a
  robots-disallowed page. **Never fetch one.** It's for the user to click. `/rank`
  finds the employer's own posting instead. Never rebuild a `viewjob?jk=` URL
  from the `jk=` value either; `/viewjob` is disallowed too.

## Adding another portal's alerts

Maukerja, Glints and others block automated search in `robots.txt` but may
offer email alerts (see `docs/malaysia/PORTALS.md`). To add one:

1. Collect 3+ real digests.
2. Document the anchor here.
3. Add `parse_<portal>` and a subject pattern to `tools/digest_parsers.py`.
4. Add a test built from a scrubbed sample.
5. Register its label in `gmail_alerts/config.json`.
