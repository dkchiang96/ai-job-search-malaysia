# Malaysian job portals: what can be automated, and how this fork reaches each

Checked **2026-09-24** against each site's live `robots.txt` (and terms of use
where it mattered). Re-check monthly with `python3 tools/malaysia_health.py`.
Every decision below is re-verified there.

The rule this fork follows is the one upstream follows: **a path
`robots.txt` disallows is not fetched, and a site that needs a login is not
logged into by a script.** Where a site says no, the fork uses a channel the
site offers you instead (its own email alerts), or leaves it to you.

| Portal | What its robots.txt / terms say | How this fork reaches it |
|---|---|---|
| **JobStreet** (my.jobstreet.com) | `Disallow: */job/` for everyone. Query-string URLs are disallowed except `?keywords` searches. `/api/jobsearch/` and `/graphql` are disallowed. AI crawlers (`anthropic-ai`, `GPTBot`, ...) are named and blocked from job pages. | **Email alerts via `/gmail-alerts`.** Save searches on JobStreet, and it emails you matches. No request ever reaches JobStreet. Job pages are never fetched; `/rank` finds the employer's own posting instead. |
| **Hiredly** (my.hiredly.com) | No rules for general agents on `my.hiredly.com`; category/state pages are in its sitemaps. **`my-api.hiredly.com` (the search API) is `Disallow: /`.** Terms §3.1: personal, non-commercial use. | **`hiredly-search`** portal skill, `my.hiredly.com` pages only. Keyword filtering happens locally because the API is off-limits. Personal use, low volume. |
| **LinkedIn** | (upstream's `linkedin-search` skill, unchanged) | `linkedin-search` with a Malaysian location, plus optional LinkedIn alert emails via `/gmail-alerts`. |
| **Indeed Malaysia** | `/viewjob` (job pages) and `/rc/` (click-through) are disallowed; the search page is not. | Alert emails via `/gmail-alerts` (**opt-in, unmaintained**). No CLI: a search that can't open any posting isn't worth building. |
| **Maukerja** / **Ricebowl** (same group) | `/jobs/`, `/search/*`, `/job/read/`, `/api/*` disallowed. | Not automated. Check by hand, or add their alert emails (see `email-alert-portals.md`, "Adding another portal"). |
| **Glints** | `*/opportunities/jobs/explore?*` (search) disallowed. | Not automated. Individual job pages are allowed, so `/rank` may read a Glints copy of a job it found elsewhere, after `robots_check.py`. |
| **MYFutureJobs** (PERKESO) | The public site is WordPress. Job data lives in `candidates.myfuturejobs.gov.my`, where every job API call returns **HTTP 401 without a login**. | Not automated, since a script won't log in on your behalf. Use it directly, especially if you're claiming EIS. |
| **Jora Malaysia** | **Closed.** The site says "Jora Malaysia has closed" (HTTP 410), and robots.txt is Jora's closed-market file. | Nothing to reach. |
| **JobMajestic** | robots.txt allows most paths, but its **terms** grant "personal, non-commercial transitory viewing only" and forbid copying the materials. | Not built. A tool that stores listings would copy them. Check by hand. |
| **freehire** (aggregator) | (upstream's `freehire-search` skill) | `freehire-search --country MY`, tech-leaning. |
| **Remote OK** | Allowed (`Crawl-delay: 1`). The API's own notice asks for a link back and attribution. | `remoteok-search`, **off unless you opt into remote**. |
| **We Work Remotely** | Allowed except account/admin paths. | `weworkremotely-search`, off unless remote. |
| **Working Nomads** | Allows everything (empty `Disallow:`). | `workingnomads-search`, off unless remote. |

## Why not just scrape JobStreet anyway?

Because its robots.txt says not to, and names AI crawlers specifically. The
alert emails carry the same fields a search result would (title, company,
location, salary when stated, link), and they cost nothing. What they don't
carry is the full job description. `/rank` handles that honestly: it looks for
the same role on the employer's site, Hiredly, LinkedIn, or one web search,
and if it finds nothing, the job is parked as `unverified` rather than scored
from its title.

## Found a portal this table is missing?

Open an issue with its name. If you'd like its alert emails supported, attach
a **scrubbed** sample digest (remove your name and email). The parser recipe is
in `.claude/skills/job-scraper/email-alert-portals.md`.
