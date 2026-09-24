# Working Nomads URL Reference

Investigated 2026-08-30 for `/add-portal`. Public, unauthenticated JSON API —
no login required. Discovered via a link literally labeled "API" in the
site's own footer (`/api/exposed_jobs/`), served with `Content-Type:
application/json` regardless of the request's `Accept` header.

## robots.txt

```
User-agent: *
Disallow:
```

Empty `Disallow` value = allow everything. No portal-specific restrictions
of any kind.

## List (search)

```
GET https://www.workingnomads.com/api/exposed_jobs/
```

Returns a JSON array of the site's **full current listing set** directly —
no wrapper object, no pagination metadata. 44 entries observed during
investigation (this appears to be genuinely the total live count on a
curated board, not a truncated page of a larger set).

**No server-side filtering of any kind.** Tested `?category=operations` and
`?category=management` against the unfiltered baseline — both returned
byte-identical payloads (196115 bytes each), confirming the query string is
ignored entirely. The site's own `/jobs?keywords=...` HTML search page
likely filters this same feed client-side in the browser; this CLI does the
same server-side-equivalent (client-side substring match in `helpers.ts`).

### Result fields (per array element)

| API field | Mapped to | Notes |
|---|---|---|
| `url` | `url`, and `id` extracted from it | Format `https://www.workingnomads.com/job/go/<id>/` — no separate `id` field exists in the payload at all; `idFromUrl` in `helpers.ts` pulls the trailing digits. |
| `title` | `title` | |
| `company_name` | `company` | |
| `location` | `location` | **Free text, not a taxonomy** — see SKILL.md's "Why this portal matters" section for real examples and how to read it. |
| `pub_date` (ISO datetime with offset, e.g. `2026-08-29T00:58:54-04:00`) | `date` | Sliced to `YYYY-MM-DD`. |
| `description` | (not surfaced on `search`; `detail` returns it) | HTML (`<p>`, `<strong>`, `<ul>`, entities) — stripped/decoded the same way every other portal skill in this repo handles description HTML. |
| `category_name` | (used for `--query` matching; surfaced as `category` on `detail`) | Observed values (partial, from a live sample): Legal, Administration, Development, Customer Success, Education, Marketing. Not useful as a `tags=` filter param — see above. |
| `tags` | (used for `--query` matching; surfaced as `tags` on `detail`) | Comma-separated free-text string, e.g. `"attorney,advocacy,communication"` — not the same taxonomy concept as Remote OK's `tags`. |

### Click-through link quirk

`url` (`/job/go/<id>/`) is a redirect, not a direct posting page — confirmed
live: `curl -L` on `/job/go/1822420/` followed through to
`/job/confirm-location/<slug>-<id>/`, an interstitial "confirm your
location" page before the employer's actual application. This CLI never
follows that chain: the full posting `description` is already present in
the list response, so `detail` re-fetches the list endpoint and returns the
matching entry rather than fetching a per-posting page at all. Documented
here so a future maintainer doesn't "fix" `detail` into fetching a page that
doesn't add anything the list response doesn't already have.

## Detail

No separate detail endpoint exists. `detail <id>` re-fetches
`GET https://www.workingnomads.com/api/exposed_jobs/` and returns the entry
whose `url` contains the requested id (see `findJobDetail` in
`helpers.ts`). This means `detail` on a posting that has since been
delisted returns `NOT_FOUND` — there is no historical archive behind this
API, only "what's live right now."

## Notes

- No authentication required; no credential/paid-fetcher path needed.
- Respect rate limits — the CLI backs off on 429/5xx with jitter, same
  convention as every other portal CLI in this repo (observed no rate
  limiting during investigation, but kept for consistency/safety).
- If Working Nomads changes its API shape, this file's field-name table is
  what to check first against a fresh fetch of
  `https://www.workingnomads.com/api/exposed_jobs/`.
