---
name: weworkremotely-search
version: 1.0.0
description: >
  Use this skill whenever the user wants to search We Work Remotely, one of the
  largest general-purpose remote-work job boards, or wants genuinely-remote job
  listings across any function (operations, management, engineering, marketing,
  design, support, etc.) rather than a "remote" tag on a location-bound board.
  Every listing on this portal is remote by definition; results carry the
  portal's own per-posting region/eligibility tag (e.g. "Anywhere in the
  World", "United States of America") so callers can tell a genuinely
  worldwide-remote role from one that is remote-only-within-one-country.
  Trigger phrases: remote job, remote jobs, work from home, work from
  anywhere, We Work Remotely, WWR, fully remote, distributed team.
context: fork
enabled: false  # remote-only board: /setup-malaysia switches this on when you opt into remote work
allowed-tools: Bash(bun run .agents/skills/weworkremotely-search/cli/src/cli.ts *)
---

# We Work Remotely Search Skill

Search live remote-job listings from We Work Remotely's public search page. No
authentication, no API key, **zero runtime dependencies** — it runs with just
`bun`.

## Why this portal matters for a remote-work search

A "Remote" tag on a big general job board frequently turns out to be
US-hybrid or US-nationals-only once you read the posting. We Work Remotely is
a **remote-only** board — nothing on it requires an office — but it still
varies by **who** may apply: many postings are US-only or region-restricted,
not worldwide. This CLI surfaces that distinction directly: every search
result's `location` field is the portal's own region/eligibility chip for
that specific posting (e.g. `"Anywhere in the World"`, `"🇺🇸 United States of
America"`), not a generic "Remote" label. Treat a `null` location as
**unverified**, not as "open to anywhere" — check the posting text.

## Commands

### Search job listings

```bash
bun run .agents/skills/weworkremotely-search/cli/src/cli.ts search [flags]
```

Key flags:
- `--query <text>` / `-q <text>` — keyword search (title, skill, role).
- `--jobage <days>` — posted within N days. Applied client-side (day granularity) against the search page's relative-age chip. Omit for all postings.
- `--page <n>` — 1-indexed, 20 results/page. Client-side — the portal has no working server-side pagination over plain HTTP (confirmed: `?page=2` returns the same set as `?page=1`).
- `--limit <n>` / `-n <n>` — cap total results emitted (client-side), applied after `--page`.
- `--format json|table|plain` — default `json`.

There is **no `--location` flag** — every listing is remote, so location isn't
a search filter here. Use the `location` field on each result instead (see
above).

### Fetch full job detail

```bash
bun run .agents/skills/weworkremotely-search/cli/src/cli.ts detail <slug|url> [--format json|plain]
```

`slug` is the `id` from `search` results (e.g. `crb-director-people-operations`).
A full `weworkremotely.com/remote-jobs/...` URL also works. Returns the full
description, employment type, an approximate deadline, and — when the
posting's structured data states one — the explicit `applicantLocationRequirement`.

## Usage examples

```bash
# Ops-leadership roles, any region tag
bun run .agents/skills/weworkremotely-search/cli/src/cli.ts search -q "Head of Operations" --format table

# Automation/ops roles posted in the last 14 days
bun run .agents/skills/weworkremotely-search/cli/src/cli.ts search -q "operations" --jobage 14 --format table

# Full detail for a specific posting
bun run .agents/skills/weworkremotely-search/cli/src/cli.ts detail crb-director-people-operations --format plain
```

## Output formats

| Format | Best for |
|--------|----------|
| `json` | Default — programmatic use, passing IDs to `detail` |
| `table` | Quick human-readable scanning |
| `plain` | Reading a single job's full detail (`detail` command) |

All errors are written to **stderr** as `{ "error": "...", "code": "..." }` and the process exits with code `1`.

## Notes

- Data is from We Work Remotely's public search and detail pages — no credentials required. `robots.txt` disallows only `/admin/`, `/account/`, `/job-seekers/*`, and `/manage-company/` — none of which this CLI touches.
- **Region/eligibility signal, not just a badge.** The `location` field on `search` results comes from the portal's own category chip for that posting (distinguished from the salary chip, which starts with `$`, and the employment-type chip, e.g. `Full-Time`). The `detail` command instead reports the posting's schema.org `applicantLocationRequirements` when present — the two can legitimately differ in wording (chip text vs. structured country code) but should agree on substance; treat a mismatch as worth a manual check.
- `null` on `location` means the posting's structured data doesn't state a restriction — **not** automatic confirmation that it's open worldwide; read the posting text to be sure. When `applicantLocationRequirements` *is* present, check it directly for the target country code (e.g. `MY` for Malaysia) rather than trusting the title or chip wording alone — one real posting titled "Canada, Europe" turned out to list ~195 countries including `MY` in its structured data.
- `deadline` (from `detail`) is schema.org `validThrough`, which some boards default to a fixed window rather than a real employer-set date — treat as approximate.
- The portal has no working page parameter over plain HTTP; `--page`/`--limit` are both implemented client-side over the full result set the search page returns.
