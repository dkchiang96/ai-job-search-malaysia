---
name: workingnomads-search
version: 1.0.0
description: >
  Use this skill whenever the user wants to search Working Nomads, a curated
  remote-work job board, or wants genuinely-remote job listings across any
  function (operations, management, development, marketing, customer
  success, education, legal, etc.) rather than a "remote" tag on a
  location-bound board. Every listing on this portal is remote by
  definition; results carry the portal's own free-text eligibility string
  for that specific posting (e.g. "Global", "USA or Canada only", "Anywhere
  (working US business hours)") so callers can tell a genuinely
  worldwide-remote role from one that is region-restricted. Trigger
  phrases: remote job, remote jobs, work from home, work from anywhere,
  Working Nomads, fully remote, distributed team.
context: fork
enabled: false  # remote-only board: /setup-malaysia switches this on when you opt into remote work
allowed-tools: Bash(bun run .agents/skills/workingnomads-search/cli/src/cli.ts *)
---

# Working Nomads Search Skill

Search live remote-job listings from Working Nomads' public JSON API. No
authentication, no API key, **zero runtime dependencies** — it runs with
just `bun`.

## Why this portal matters for a remote-work search

A "Remote" tag on a big general job board frequently turns out to be
US-hybrid or US-nationals-only once you read the posting. Working Nomads is
a **remote-only, curated** board (a smaller, hand-reviewed listing set —
dozens of live postings at any time, not thousands) — but it still varies by
**who** may apply. This is the most direct eligibility signal of any portal
skill in this repo: each posting's own `location` field is **free text
written by the poster themselves** (e.g. `"Global"`, `"USA or Canada
only"`, `"Anywhere (working US business hours)"`, `"APAC,Middle East"`, `"the
EU, the US, Canada, the UK, Australia, Singapore"`) rather than a controlled
taxonomy or a generic badge — read it directly rather than pattern-matching
it, since this board doesn't constrain what posters write there.

## Known limitation: no server-side filtering at all

Working Nomads' public API (`/api/exposed_jobs/`) ignores every query
parameter tested during investigation (`?category=`, `?keywords=`) and
always returns the site's **full current listing set** in one response —
confirmed: both filtered calls returned byte-identical output to the
unfiltered call. `--query` is therefore always applied client-side (matched
against title/company/category/tags), mirroring what the site's own
frontend does. Because the underlying feed is small and curated (not a
large aggregator), a query with no match may legitimately return nothing —
that's a real coverage characteristic of this board, not a bug.

The same feed already includes each posting's **full description inline**,
so there is no separate per-posting detail endpoint to call — `detail`
re-fetches this same feed and returns the matching entry.

## Commands

### Search job listings

```bash
bun run .agents/skills/workingnomads-search/cli/src/cli.ts search [flags]
```

Key flags:
- `--query <text>` / `-q <text>` — keyword search, client-side (see limitation above).
- `--jobage <days>` — posted within N days, using the feed's own date field. Omit for all postings.
- `--page <n>` — 1-indexed, 20 results/page. Client-side.
- `--limit <n>` / `-n <n>` — cap total results emitted (client-side), applied after `--page`.
- `--format json|table|plain` — default `json`.

There is **no `--location` flag** — every listing is remote, so location isn't
a search filter here. Use the `location` field on each result instead (see
above).

### Fetch full job detail

```bash
bun run .agents/skills/workingnomads-search/cli/src/cli.ts detail <id|url> [--format json|plain]
```

`id` is the numeric id from `search` results (e.g. `1822420`, extracted from
the posting's `/job/go/<id>/` URL). A full URL also works. Returns the full
description, category, and tags. Note: since this re-fetches the live feed
rather than an archived per-posting page, `detail` on an id that has since
been delisted returns `NOT_FOUND` — there is no historical archive behind
this API.

## Usage examples

```bash
# Ops-related roles currently on the site
bun run .agents/skills/workingnomads-search/cli/src/cli.ts search -q "operations" --format table

# Same, posted in the last 14 days
bun run .agents/skills/workingnomads-search/cli/src/cli.ts search -q "operations" --jobage 14 --format table

# Full detail for a specific posting
bun run .agents/skills/workingnomads-search/cli/src/cli.ts detail 1822420 --format plain
```

## Output formats

| Format | Best for |
|--------|----------|
| `json` | Default — programmatic use, passing IDs to `detail` |
| `table` | Quick human-readable scanning |
| `plain` | Reading a single job's full detail (`detail` command) |

All errors are written to **stderr** as `{ "error": "...", "code": "..." }` and the process exits with code `1`.

## Notes

- Data is from Working Nomads' public `/api/exposed_jobs/` JSON endpoint — no credentials required. `robots.txt` is a bare `Disallow:` (empty value = allow everything).
- **Read the `location` field, don't pattern-match it.** Unlike some other remote boards in this repo, Working Nomads doesn't constrain posters to a fixed set of region strings — it is genuinely free text. Values seen during investigation ranged from single countries to explicit multi-region lists to timezone bands (`"CET (+/- 3 hours)"`). Treat "Global", "Anywhere", "APAC", or a list that includes a candidate's region as a positive signal; treat a single different country/region as a restriction.
- `/job/go/<id>/` (the `url` field) is Working Nomads' own click-through link — it redirects through a "confirm location" interstitial page before reaching the employer's actual application. This CLI never follows that chain; the full description is already inline in the list feed.
- No pagination exists behind the feed (it's the full current set already); `--page`/`--limit` are both implemented client-side.
