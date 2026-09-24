# Search Queries for Job Scraper

<!-- SETUP: Customize these queries based on your skills, target roles, and location -->

## Installed portal CLIs (primary for `/scrape`)

`/scrape` discovers every portal skill under `.agents/skills/*/SKILL.md` and runs its CLI first. Shipped country-agnostic CLIs include `linkedin-search` and `freehire-search`; Danish demos and any skill you add with `/add-portal` are included the same way. You do **not** need a matching `site:` line below for those CLIs to run.

The `site:` query templates in this file are the **WebSearch fallback** — for portals without a CLI, company career pages, or when a CLI fails.

**Language scope:** write every query category in every language listed in your CLAUDE.md Languages table (typically 1-2, sometimes more). A posting requiring a language you have *not* declared, as a job condition, is excluded before scoring; a posting requiring a *higher level* than you declared in a language you *do* work in is flagged for your own judgment, not excluded — see `04-job-evaluation.md`'s Language Gate, the single source of truth for this rule. Translate each category's keywords rather than machine-translating word-for-word (e.g. "Frontend Developer" -> "Desarrollador Frontend", not a literal word-for-word translation) if you work in more than one language.

## Search Sites

Primary (your market's job boards - scaffold one with `/add-portal`):
- **[YOUR_JOB_BOARD]** - your market's largest general job board
- **linkedin.com/jobs** - LinkedIn job listings (filter: [YOUR_COUNTRY] / [YOUR_CITY]); also covered by `linkedin-search` CLI
- **[YOUR_INDUSTRY_JOB_BOARD]** - a niche/industry board for your field (optional)
- **[YOUR_ADDITIONAL_JOB_BOARD]** - another major board for your market (optional)

Secondary (company career pages via Google):
- Direct Google searches with `site:` filters for known target companies

## Query Categories

Queries are grouped by priority. Write **each category in every language from your Languages table** (see Language scope above). Combine each query with your location terms (e.g. your city, region, or metro area) where the site supports it.

**Organize by function, not job title.** The same underlying work carries different titles across companies and markets (a "Data Scientist" role at one employer may be posted as "Insights Analyst" or "Data Consultant" at another). Name each priority category after the function it covers, and list several plausible job titles as query variants within that category rather than betting an entire priority tier on one exact title string.

### Priority 1: [YOUR_PRIMARY_ROLE_TYPE]

These match your strongest and most desired career direction.

```
site:[YOUR_JOB_BOARD] "[YOUR_PRIMARY_JOB_TITLE_1]" [YOUR_CITY]
site:[YOUR_JOB_BOARD] "[YOUR_PRIMARY_JOB_TITLE_2]" [YOUR_CITY]
site:[YOUR_JOB_BOARD] "[YOUR_KEY_SKILL]" [YOUR_CITY]
site:linkedin.com/jobs "[YOUR_PRIMARY_JOB_TITLE_1]" [YOUR_COUNTRY]
```

### Priority 2: [YOUR_DOMAIN_EXPERTISE]

These match your domain expertise.

```
site:[YOUR_JOB_BOARD] [YOUR_DOMAIN_KEYWORD_1] [YOUR_CITY] OR [YOUR_REGION]
site:[YOUR_JOB_BOARD] [YOUR_DOMAIN_KEYWORD_2] [YOUR_COUNTRY]
site:linkedin.com/jobs [YOUR_DOMAIN_KEYWORD_1] [YOUR_CITY] [YOUR_COUNTRY]
```

### Priority 3: [YOUR_ADJACENT_ROLE_TYPE]

Adjacent roles you could pivot into.

```
site:[YOUR_JOB_BOARD] "[YOUR_ADJACENT_TITLE_1]" [YOUR_KEY_SKILL] [YOUR_CITY]
site:[YOUR_JOB_BOARD] "[YOUR_ADJACENT_TITLE_2]" [YOUR_KEY_SKILL] [YOUR_CITY]
```

### Priority 4: Broader Technical / Consulting

Wider net for general technical roles.

```
site:[YOUR_JOB_BOARD] [YOUR_KEY_SKILL] developer [YOUR_CITY]
site:linkedin.com/jobs "[YOUR_KEY_SKILL] developer" [YOUR_CITY]
site:[YOUR_JOB_BOARD] "technical consultant" [YOUR_DOMAIN] [YOUR_CITY]
```

## Location Filter

When evaluating results, verify the job location is within reasonable commute distance from your home. Define acceptable areas:
- [YOUR_CITY] and surrounding areas
- [ACCEPTABLE_AREA_1]
- [ACCEPTABLE_AREA_2]
- [BORDERLINE_AREA] (borderline - ~X min by transit)
- [TOO_FAR_AREA] (too far)

## Language Filter

Your working languages and levels are in CLAUDE.md's Languages table. When filtering scraped results, apply `04-job-evaluation.md`'s Language Gate: a posting requiring a language you haven't declared at all is excluded; a posting requiring a higher level than you declared in a language you do work in is not excluded, flag it clearly instead (see `job-scraper/SKILL.md`'s Step 3 "Quick Fit Assessment" for how the flag surfaces in `/scrape` output). Postings simply *written* in a language you don't work in, that don't require it on the job, are fine.

## Date Filter

Only include jobs posted within the last 14 days, or with an application deadline that has not yet passed. If a posting date cannot be determined, include it but flag as "date unknown".

## Adapting Queries

If the user specifies a focus area, select queries from the matching category and also generate 2-3 custom queries for that focus. For example:
- "/scrape [focus_area]" -> relevant category queries + custom focus-specific queries

## Malaysia (Malaysia adaptation - filled by `/setup-malaysia`)

<!-- SETUP: /setup-malaysia replaces the [MY_*] tokens below. Delete this section if you are not job-hunting in Malaysia. -->

**Where Malaysian jobs come from in this fork** (full access table: `docs/malaysia/PORTALS.md`):

| Source | How `/scrape` reaches it |
|---|---|
| Hiredly | `hiredly-search` CLI. Search by **state + category**; keywords are filtered client-side. Queries below. |
| JobStreet | **Not searchable** (robots.txt). Saved-search **email alerts** instead, via `/gmail-alerts`. Your alert list lives in `docs/malaysia/JOB-ALERTS.md`'s worksheet, not here. |
| LinkedIn | `linkedin-search` CLI with a Malaysian location, plus optional alert emails via `/gmail-alerts`. |
| freehire | `freehire-search --country MY` (tech-leaning aggregator). |
| MYFutureJobs, Maukerja, Glints | Login-walled or search-disallowed. Check them by hand, or add their alert emails later. |

**Hiredly searches** (state + category; `-q` narrows within the fetched pages):

```
hiredly-search search -l [MY_STATE_1] -c [MY_HIREDLY_CATEGORY_1] --jobage 14 --pages 2
hiredly-search search -l [MY_STATE_1] -c [MY_HIREDLY_CATEGORY_2] -q "[MY_KEYWORD]" --jobage 14 --pages 3
hiredly-search search -l [MY_STATE_2] -c [MY_HIREDLY_CATEGORY_1] --jobage 14
```

**LinkedIn searches** (always pass a full Malaysian location):

```
linkedin-search search -q "[YOUR_PRIMARY_JOB_TITLE_1]" -l "Kuala Lumpur, Federal Territory of Kuala Lumpur, Malaysia" --jobage 14
linkedin-search search -q "[YOUR_PRIMARY_JOB_TITLE_1]" -l "Selangor, Malaysia" --jobage 14
```

**Location tiers** (Klang Valley = KL + most of Selangor + Putrajaya; see `12-malaysia-market.md`):
- Ideal: [MY_IDEAL_AREAS]
- Acceptable: [MY_ACCEPTABLE_AREAS]
- Only with a strong reason: [MY_STRETCH_AREAS]   (e.g. Penang, Johor Bahru, Singapore)

## Remote roles open to Malaysia (optional - only if you opted in at `/setup-malaysia`)

<!-- SETUP: /setup-malaysia keeps this section and enables the remote boards only if you choose "also remote". -->

Every remote result goes through `12-malaysia-market.md`'s **Remote-Work
Verification Gate**. A remote tag is where checking starts, not a verdict.

```
remoteok-search search -q "[MY_REMOTE_KEYWORD]" --limit 20
weworkremotely-search search -q "[MY_REMOTE_KEYWORD]" --limit 20
workingnomads-search search -q "[MY_REMOTE_KEYWORD]" --limit 20
freehire-search search -q "[MY_REMOTE_KEYWORD]" --remote remote --jobage 14
linkedin-search search -q "[YOUR_PRIMARY_JOB_TITLE_1]" -l "Malaysia" --remote remote --jobage 14
```

Check each board's own `SKILL.md` for its exact flags, since the remote boards
differ. Remote pay is usually USD. Set your conversion rate in
`config/fit_model.json` → `worth.fx_to_myr` if you use the Fit Model.
