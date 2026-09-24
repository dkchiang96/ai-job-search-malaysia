---
framework_version: 1.0.0
---

# Malaysia Market Rules (Malaysia adaptation)

Malaysia-specific rules for reading postings. They are **added** to
`04-job-evaluation.md`, never substituted for it. The Eligibility Gate and the
Language Gate there still run first, and nothing here overrides them. `/rank`
and `/apply` read this file alongside `04-job-evaluation.md` whenever
`config/malaysia.json` exists (written by `/setup-malaysia`). `/scrape` and
`/gmail-alerts` pick up its location and remote rules through the Malaysia
sections of `search-queries.md`.

---

## 1. Remote-Work Verification Gate (run before scoring any "Remote" posting)

Applies to any posting whose title, location field or portal tag says remote,
"WFH", "work from home", "anywhere", or comes from a remote-only board
(`remoteok-search`, `weworkremotely-search`, `workingnomads-search`,
`freehire-search --remote remote`). A remote badge is where checking starts. It
is not a verdict. Read the work-arrangement and "who can apply" text verbatim.

| Posting wording | Verdict |
|---|---|
| Open to Malaysia, APAC/SEA/Asia, "anywhere", "worldwide", or no in-office requirement **and** no country restriction | **PASS** |
| "Hybrid", named office days, or "must live within commuting distance of <city>", despite the remote tag | **FAIL: mislabeled remote.** Quote it. Its real location is that city. Re-apply the location filter to that city. |
| Restricted to a country/region that excludes Malaysia ("US only", "must be authorised to work in the EU", "UK residents") | **FAIL: geography-restricted.** Quote it. |
| Silent on both | **FLAG: unverified.** Proceed, and tell the user to check the careers page or application FAQ before applying. |

Its verdict feeds the same `location_verdict` that `04-job-evaluation.md` and
`/rank` already use. A mislabeled or restricted remote job is a location FAIL,
not a lower score. In Fit Model mode, a PASS maps to the `location_category`
you named for remote at setup (default `"Remote (open to Malaysia)"`).

**Three facts to surface for every remote PASS or FLAG.** Put them in
strengths/gaps. They are not gates:

- **Time zone.** Quote any required overlap ("core hours 9am-5pm EST" means
  roughly 9pm-5am in Malaysia). Flag overlap that falls outside roughly
  08:00-23:00 Malaysia time.
- **Employment model.** Employee via an Employer of Record (EOR), or
  contractor/freelancer? A contractor in Malaysia has no employer EPF/SOCSO
  contributions and pays their own tax. That is worth knowing, not
  disqualifying. See `docs/malaysia/REMOTE.md`.
- **Pay currency.** USD/SGD/EUR pay is not converted by `tools/myr_salary.py`.
  The Fit Model converts it only with the rate you set in
  `config/fit_model.json` → `worth.fx_to_myr`.

## 2. Salary conventions

- **Postings quote monthly gross base in RM** ("RM 5,000 - RM 7,000 per
  month"). Annual figures are the exception. `tools/myr_salary.py` normalises
  every shape to monthly MYR and records which assumptions it made. Use its
  output, never re-derive the figure in prose.
- **Base is not total cost.** Employers add EPF (the employer share is on top
  of the posted figure), SOCSO and EIS, and many pay bonus months (a "13th
  month" or a performance bonus), plus allowances (transport, phone, parking,
  shift). Compare **base with base**. Mention bonus months or allowances in
  strengths, never add them into the figure.
- **Indeed's figures are often estimates**, and the email says so.
  `myr_salary` flags `estimated`, and an estimate never trips a salary gate.
- **JobStreet's "Strong applicant" badge and salary-match labels** are the
  portal's own matching signals. Record them in strengths. They are not
  employer-stated pay.
- **"Negotiable", "Competitive", "Undisclosed"** mean no figure. Never infer one.

## 3. Language requirements

Malaysian postings state language requirements in ways the generic Language
Gate should treat as **job conditions**:

- "**Mandarin speaker**", "**Chinese-speaking**", "able to converse in
  Mandarin/Cantonese to liaise with Mandarin-speaking clients/suppliers" all
  mean Mandarin (or Cantonese) is required.
- "**Bahasa Malaysia**/**BM** is compulsory", "good command of BM", "SPM BM
  credit" all mean Malay is required. A BM credit in SPM is often asked for
  government and GLC roles.
- "Thai / Vietnamese / Bahasa Indonesia speaking" (common in regional
  shared-service centres in KL) mean that language is required.

A posting **written** in BM or Chinese is not by itself a requirement. Apply
the Language Gate to what the role needs, as `04-job-evaluation.md` says.

## 4. Eligibility wording

These go to `04-job-evaluation.md`'s Eligibility Gate verbatim:

- "**Malaysian only**", "**Warganegara Malaysia sahaja**", "open to Malaysians"
  are a citizenship requirement. FAIL for non-citizens, and quote it.
- "Employment Pass (EP) holders welcome", "we sponsor EP" are an explicit PASS
  for foreign candidates.
- Government and many GLC roles are citizen-only even when the ad is silent.
  Treat silence there as unverified, not permission.

## 5. Location vocabulary

- **Klang Valley** = Kuala Lumpur + most of Selangor (Petaling Jaya, Subang
  Jaya, Shah Alam, Cyberjaya, Puchong, Klang) + Putrajaya. A candidate "in
  KL" usually accepts all of it. Confirm tiers at setup, don't assume them.
- JobStreet locations read `<Area>, <State>` ("Petaling Jaya, Selangor").
  Hiredly sometimes gives a full street address. Judge by the state, then the
  area.
- Johor Bahru roles sometimes mean a Singapore-side commute or cross-border
  work. Check the posting rather than assuming.

## 6. Duplicate and agency postings

- The same job often appears on JobStreet, Hiredly and LinkedIn at once.
  `tools/job_key.py` merges identical company+title pairs automatically.
- **Recruitment-agency posts** ("Our client, a leading MNC...", company shown as
  the agency or "Confidential") will not merge with the employer's own post,
  because the company differs. Flag the likely duplicate in the table instead
  ("possibly the same role as #3, via agency") and never merge by guess.
- An agency post is a legitimate route in, not a red flag. The employer's own
  post, if you find it, usually carries more detail.

## 7. Portal access (what may be fetched)

The authoritative table, with dates and robots.txt quotes, is
`docs/malaysia/PORTALS.md`. The rules that matter while scoring:

- **Never fetch `my.jobstreet.com/job/...`** or any JobStreet search URL with a
  query string. They are robots-disallowed, and AI crawlers are named
  explicitly. JobStreet jobs arrive only through `/gmail-alerts`.
- **Never call `my-api.hiredly.com`**, which is robots-disallowed for all
  agents. `hiredly-search` uses only `my.hiredly.com` pages.
- **MYFutureJobs** requires a login for all job data. Don't try to fetch it.
- **Jora Malaysia has closed.** Its pages return HTTP 410.
- Everything else goes through `tools/robots_check.py` before any `WebFetch`,
  exactly as `09-web-research.md` says.
