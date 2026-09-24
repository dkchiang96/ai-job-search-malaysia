# We Work Remotely URL Reference

Investigated 2026-08-30 for `/add-portal`. Public, unauthenticated pages — no
API key or login required.

## robots.txt

```
User-agent: *
Disallow: /admin/
Disallow: /account/
Disallow: /job-seekers/account/
Disallow: /job-seekers/profile/
Disallow: /manage-company/
Disallow: /*edit?token=/
Disallow: /*cancel?token=/
```

Search (`/remote-jobs/search`) and posting pages (`/remote-jobs/<slug>`) are
not disallowed.

## Search

```
GET https://weworkremotely.com/remote-jobs/search?term=<query>
```

- `term` — free-text query, matched against title/company/description.
- **No location parameter.** The board is remote-only; there is nothing to
  filter by geography on the request side. Each result instead carries its
  own region/eligibility tag (see below).
- **No working pagination over plain HTTP.** The page's `sort`/date-range
  dropdown and `?page=` parameter are driven by client-side JS; a plain
  `?page=2` request returned the identical result set as `?page=1` in
  testing. The server-rendered HTML includes **every** matching result in one
  response (confirmed: a 76-result query returned 77 unique `/remote-jobs/...`
  links in a single fetch). The CLI paginates and limits client-side over
  that full set.
- No working recency query parameter either; `--jobage` is applied
  client-side against each card's relative-age chip.

### Result structure

One `<li class=" new-listing-container ">` per posting, each wrapping an
`<a class="listing-link--unlocked" href="/remote-jobs/<slug>">`:

| Field | Anchor |
|---|---|
| id | the `<slug>` in the href — also the canonical URL/detail-page key |
| title | `<span class="new-listing__header__title__text">` |
| date (relative) | `<p class="new-listing__header__icons__date">` — text like `3d`, `16d`, `Today`; converted client-side to an ISO estimate |
| company | `<p class="new-listing__company-name">` |
| company headquarters | `<p class="new-listing__company-headquarters">` — **not surfaced**; this is the employer's HQ, not who may apply, and using it as `location` would be actively misleading for a remote-eligibility check |
| region/eligibility + salary + employment type | three `<p class="new-listing__categories__category">` chips inside `<div class="new-listing__categories">`, in no fixed order |

**Chip classification** (`classifyChip` in `helpers.ts`): a chip starting
with `$` is salary; a chip matching a known employment-type string
(`Full-Time`, `Part-Time`, `Contract`, `Freelance`, `Internship`, or a
`/`-joined combination) is employment type; anything else — `"Anywhere in
the World"`, a flag emoji + country name, a continent name — is the
region/eligibility tag, stored as the result's `location`. Not every posting
carries a region chip; absence means "unstated", not "worldwide".

## Detail

```
GET https://weworkremotely.com/remote-jobs/<slug>
```

Returns a full HTML page with an embedded `schema.org/JobPosting` block:

```html
<script type="application/ld+json"> { "@type": "JobPosting", ... } </script>
```

Fields used:

| JSON-LD field | Mapped to |
|---|---|
| `title` | `title` |
| `description` | `description` (HTML-encoded inside the JSON string; decoded and tag-stripped, paragraph breaks kept as newlines) |
| `datePosted` | `date` (absolute, more precise than the search page's relative chip) |
| `validThrough` | `deadline` — **approximate**; some boards default this to a fixed window rather than an employer-set date |
| `employmentType` | `employmentType` |
| `hiringOrganization.name` / `.sameAs` | `company` / `companyUrl` |
| `applicantLocationRequirements` | `applicantLocationRequirement` and `location` — an array of `{"@type":"Country","name":"<code>"}`; joined by `, ` when present |

**Confirmed during investigation:** a US-restricted posting
(`crb-director-people-operations`) carried
`"applicantLocationRequirements":[{"@type":"Country","name":"US"}]`, matching
its search-page chip (`🇺🇸 United States of America`). A posting whose own
title reads "Canada, Europe" (`storyblok-deal-operations-manager-canada-europe`)
turned out, once the control-character bug below was fixed, to carry an
`applicantLocationRequirements` array of **~195 country codes — effectively
worldwide, and it includes `MY`** — even though its search-page region chip
read "Anywhere in the World" and its title suggested a narrower scope. This
is a real example of why a single signal (title wording, or the chip alone)
isn't enough: the structured `applicantLocationRequirements` array is the
most authoritative field when present, worth checking directly for the
target country code (e.g. `MY`) rather than pattern-matching the chip text or
the title. `null`/absent still means "unstated in structured data" for
postings where the field genuinely isn't populated — not confirmation of
worldwide eligibility.
- **Known parsing hazard:** WWR's `description` field in this JSON-LD block
  contains literal, unescaped newline/tab characters inside the JSON string
  (confirmed on every detail page fetched during investigation) — invalid
  per strict JSON, and a plain `JSON.parse` throws `"Unterminated string"` on
  it. `sanitizeJsonLdControlChars` in `helpers.ts` escapes control characters
  found *inside* string literals (tracked via a stateful scan) before
  parsing; this cost an early false negative during Step 4 testing where two
  real postings appeared to have no structured data at all until the bug was
  found and fixed. Do not "fix" this by loosening the JSON.parse call itself
  or falling back to regex field extraction — the sanitizer is what makes
  strict parsing work.

## Notes

- No authentication required; no credential/paid-fetcher path needed (Step
  2.5 of `/add-portal` — plain `fetch` with an honest User-Agent worked for
  every request during investigation and live testing).
- Respect rate limits — the CLI backs off on 429/5xx with jitter, same
  convention as every other portal CLI in this repo.
- If We Work Remotely changes its markup, this file's class-name anchors
  (`new-listing__*`, `new-listing__categories__category`) are what to check
  first against a fresh fetch of `/remote-jobs/search?term=test`.
