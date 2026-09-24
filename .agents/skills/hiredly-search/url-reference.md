# Hiredly Malaysia: URL and Response Reference

Investigated 2026-09-24. This is the file to update when Hiredly changes its markup.

## Access rules (checked 2026-09-24)

| Host | robots.txt | Used by this CLI |
|---|---|---|
| `my.hiredly.com` | Groups only for named search/AI bots (Googlebot, Bingbot, GPTBot, ChatGPT-User → `Allow: /`). No `User-agent: *` group, so there is no restriction for other agents. Sitemap: `/sitemap-index.xml`. | Yes: listing pages and job pages only |
| `my-api.hiredly.com` | `User-agent: *` / `Disallow: /` | **Never.** This is the GraphQL job API behind the site's keyword search. |
| `cms.hiredly.com` | not checked | Never |

Terms and Conditions (`/terms-and-conditions`, client-rendered): §3.1 grants a
licence to view and download a single copy "solely for your personal,
non-commercial use". §3.2 forbids using Hiredly content for any public or
commercial purpose. There is no clause on automated access. §4.3 forbids security
probing and overloading, so stay low-volume.

## Listing pages

Path grammar. Every shape appears in `sitemap-{1,2,3}-filter.xml`:

```
/jobs                                              all listings (default feed)
/jobs-in-<state>[/<job-type>]                      e.g. /jobs-in-selangor/full-time
/jobs-in-<category>[/<sub>][/in-<state>][/<job-type>]
    e.g. /jobs-in-supply-chain-logistics/in-kuala-lumpur
         /jobs-in-accounting-finance/audit-taxation/in-penang/full-time
?page=<n>                                          30 listings per page, 1-indexed
```

- `<job-type>`: `full-time` and `internship` are the only values in the
  sitemaps.
- `?search=<text>` is accepted in the URL but the server-rendered page **ignores
  it** and returns the default feed. The real keyword search is a client-side
  call to `my-api.hiredly.com`, which is robots-disallowed. That is why `--query`
  is filtered locally.

Response: HTML with `<script id="__NEXT_DATA__" type="application/json">`.
Listings are at `props.pageProps.jobs[]`, 30 per page. Also on the page:
`props.pageProps.specialisationList[]` (`slug`, `name`,
`subSpecialisations[].slug`) and `props.pageProps.cmsLocations[].attributes.slug`.

Per-listing fields used:

| Field | Example | Maps to |
|---|---|---|
| `slug` | `jobs-malaysia-<company>-job-<title>` | `id`, `url` = `/jobs/<slug>` |
| `title` | | `title` |
| `company.name` (fallback `aggregatedCompanyName`) | | `company` |
| `location`, `stateRegion` | `Petaling Jaya`, `Selangor` | `location` |
| `activeAt` | `2026-09-16T20:19:47+08:00` | `date` |
| `salary` | `"4000 - 6000"` or `"Undisclosed"` | `salary` (monthly MYR) |
| `jobType`, `careerLevel` | `Full-Time`, `Senior Executive` | same |
| `minYearsExperience`, `maxYearsExperience` | `1`, `3` | `experience` |
| `tracks[].title` | `Supply Chain & Logistics` | `categories` |
| `skills[].name` | | `skills` |
| `externalJobUrl` | `""` or a URL | `externalUrl` |

Also present but unused: `gptSummary` / `gptSummaryMs` (Hiredly's own
AI-written summaries in English and BM), `boosted`, `spotlight`, `company.logo`,
`globalHirePreferences`.

## Job page

`/jobs/<slug>` returns the same `__NEXT_DATA__` pattern, with the record at
`props.pageProps.job`: every listing field plus `description` (HTML),
`requirements` (HTML), `createdAt`, and `structuredJobData` (schema.org
`JobPosting`: `datePosted`, `validThrough`, `description` as text). An unknown
slug returns HTTP 404.
