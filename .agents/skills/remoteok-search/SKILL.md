---
name: remoteok-search
version: 1.0.0
description: >
  Use this skill whenever the user wants to search Remote OK, one of the
  largest general-purpose remote-work job boards, or wants genuinely-remote
  job listings across any function (operations, management, engineering,
  marketing, design, support, etc.) rather than a "remote" tag on a
  location-bound board. Every listing on this portal is remote by
  definition; results carry the portal's own per-posting location/eligibility
  string so callers can tell a genuinely worldwide-remote role from one that
  is remote-only-within-one-country. Trigger phrases: remote job, remote
  jobs, work from home, work from anywhere, Remote OK, RemoteOK, fully
  remote, distributed team.
context: fork
enabled: false  # remote-only board: /setup-malaysia switches this on when you opt into remote work
allowed-tools: Bash(bun run .agents/skills/remoteok-search/cli/src/cli.ts *)
---

# Remote OK Search Skill

Search live remote-job listings from Remote OK's public JSON API. No
authentication, no API key, **zero runtime dependencies** — it runs with
just `bun`.

> **Remote OK API terms:** the feed's own notice asks consumers to "link back to
> the URL on Remote OK and mention Remote OK as a source". Every result keeps its
> `remoteok.com` URL, and anything you publish from this (a Notion page or a report
> you share) must keep that link and name Remote OK. Don't use the Remote OK logo.

## Why this portal matters for a remote-work search

A "Remote" tag on a big general job board frequently turns out to be
US-hybrid or US-nationals-only once you read the posting. Remote OK is a
**remote-only** board — nothing on it requires an office — but it still
varies by **who** may apply. This CLI surfaces that distinction directly:
each search result's `location` field is the portal's own per-posting
location/eligibility string (e.g. `"United States, "` trimmed to `"United
States"`, or the literal `"Remote"` for a posting confirmed unrestricted),
and `detail` additionally reports the posting's structured
`applicantLocationRequirements` when present. Treat a `null`/absent value as
**unverified**, not as "open to anywhere" — check the posting text.

## Known limitation: no true free-text search

Remote OK's public API (`/api`) has no keyword-search endpoint — only a
fixed tag taxonomy. `--query` is handled two ways depending on whether it
matches that taxonomy exactly (case-insensitive):
- **Known tag** (e.g. `operations`, `management`, `director`, `exec`,
  `project manager` — see `url-reference.md` for the full sampled list):
  routed to Remote OK's own `tags=` endpoint, which draws from a materially
  larger backing set than the unfiltered feed (confirmed: `operations`
  returned ~99 results this way vs. ~1 via substring match over the
  unfiltered feed).
- **Anything else** (multi-word phrases, unrecognized terms): falls back to
  fetching the unfiltered feed — capped at roughly the **~100
  most-recently-posted listings site-wide**, no deeper history or
  pagination behind it — and matching client-side against title/company/tags,
  the same way the site's own frontend filters in the browser.

A niche query with no known-tag match can legitimately return nothing if
nothing in that recent window matches; that's a real coverage limit of the
free API, not a bug.

## Commands

### Search job listings

```bash
bun run .agents/skills/remoteok-search/cli/src/cli.ts search [flags]
```

Key flags:
- `--query <text>` / `-q <text>` — keyword search (see limitation above).
- `--jobage <days>` — posted within N days, using the API's own date field. Omit for all postings.
- `--page <n>` — 1-indexed, 20 results/page. Client-side, over the feed above.
- `--limit <n>` / `-n <n>` — cap total results emitted (client-side), applied after `--page`.
- `--format json|table|plain` — default `json`.

There is **no `--location` flag** — every listing is remote, so location isn't
a search filter here. Use the `location` field on each result instead (see
above).

### Fetch full job detail

```bash
bun run .agents/skills/remoteok-search/cli/src/cli.ts detail <id|url> [--format json|plain]
```

`id` is the numeric `id` from `search` results (e.g. `1132182`) — a bare id
resolves correctly (Remote OK redirects it to the full slugged URL). A full
`remoteok.com/remote-jobs/...` URL also works. Returns the full description,
employment type, an approximate deadline, and — when the posting's
structured data states one — the explicit `applicantLocationRequirement`.

## Usage examples

```bash
# Ops-related roles currently on the site
bun run .agents/skills/remoteok-search/cli/src/cli.ts search -q "operations" --format table

# Same, posted in the last 14 days
bun run .agents/skills/remoteok-search/cli/src/cli.ts search -q "operations" --jobage 14 --format table

# Full detail for a specific posting
bun run .agents/skills/remoteok-search/cli/src/cli.ts detail 1132182 --format plain
```

## Output formats

| Format | Best for |
|--------|----------|
| `json` | Default — programmatic use, passing IDs to `detail` |
| `table` | Quick human-readable scanning |
| `plain` | Reading a single job's full detail (`detail` command) |

All errors are written to **stderr** as `{ "error": "...", "code": "..." }` and the process exits with code `1`.

## Notes

- Data is from Remote OK's public `/api` JSON endpoint and detail pages — no credentials required.
- **robots.txt has a self-contradiction naming ClaudeBot specifically** — one block fully disallows it, another (grouped with other AI/LLM crawlers) explicitly allows citing public job listings. This CLI's own User-Agent (`remoteok-search-cli/1.0`, the same honest-identification convention every portal CLI in this repo uses) is not literally "ClaudeBot" and falls under the site's generic `User-agent: *` group, which explicitly `Allow: /` with `Content-Signal: use=reference` and disallows only AJAX/tracking paths this CLI never touches. Flagged here for anyone auditing this skill later, since it directly involves Claude by name — see `url-reference.md` for the full text.
- **Location/eligibility signal, not just a badge.** The `location` field on `search` results is Remote OK's own field for that posting, confirmed during investigation to correlate with the detail page's structured `applicantLocationRequirements` (a US-restricted posting's API `location` read `"United States, "` and its JSON-LD listed `{"name":"United States"}`; a posting with API `location: "Remote"` had `{"name":"Anywhere"}`). It is not guaranteed accurate on every listing — Remote OK aggregates from many source feeds of varying quality — so cross-check against `detail` and the posting text for anything you're relying on.
- `deadline` (from `detail`) is schema.org `validThrough`, which some boards default to a fixed window rather than a real employer-set date — treat as approximate.
- No real pagination exists behind the feed; `--page`/`--limit` are both implemented client-side over the ~100-listing feed described above.
