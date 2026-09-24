---
name: hiredly-search
version: 1.0.0
description: >
  Use this skill whenever the user wants to search Hiredly (my.hiredly.com), one of
  Malaysia's largest job boards for graduates, executives and mid-career
  professionals, or wants Malaysian job listings by state (Kuala Lumpur, Selangor,
  Penang, Johor ...) and field, or wants to look up a specific Hiredly posting.
  Results carry the posted monthly salary range in RM when the employer discloses
  it. Trigger phrases: Hiredly, WOBB, jobs in Malaysia, jobs in KL, jobs in
  Selangor, kerja kosong, jawatan kosong, cari kerja, kerja di Kuala Lumpur,
  kerja di Selangor, 马来西亚工作, 吉隆坡工作.
context: fork
enabled: true  # set to false to keep this portal installed but have /scrape skip it
allowed-tools: Bash(bun run .agents/skills/hiredly-search/cli/src/cli.ts *)
---

# Hiredly Search Skill (Malaysia)

Search live job listings from **Hiredly Malaysia** (formerly WOBB). No
authentication, no API key, **zero runtime dependencies**: it runs with just `bun`.

> **Personal, non-commercial use only.** Hiredly's Terms and Conditions (§3.1)
> authorise viewing and downloading its content "solely for your personal,
> non-commercial use". Keep volume low (the CLI caps a run at 5 pages of 30
> listings, with a pause between pages), never republish the listings, and do not
> run it on anyone else's behalf.

## How it reaches Hiredly (and what it deliberately avoids)

Hiredly's keyword search runs through `my-api.hiredly.com`, and that host's
`robots.txt` is `Disallow: /` for every user agent. **This CLI never touches it.**
It only fetches `my.hiredly.com` pages. That host publishes no rule for general
crawlers, and it lists its category, state and job-type pages in its own
sitemaps. Those pages are server-rendered and include their 30 listings as JSON.

**Declared deviations from the portal-skill contract:**

- **`--query` is applied client-side.** Keywords filter the fetched pages (title,
  company, Hiredly categories, skills). They are never sent to Hiredly. Narrow
  with `--location` and `--category` first, then add `--query`. Use `--pages`
  (max 5) when a filter is broad.
- **`--jobage` is applied client-side** to each listing's `activeAt` date. Hiredly
  has no age parameter on these pages.
- **`--location` takes a Malaysian state**, not free text (city names map to their
  state, e.g. `PJ` → Selangor).
- **Extra flags:** `--category`, `--job-type`, `--pages`.

## Commands

### search

```
bun run .agents/skills/hiredly-search/cli/src/cli.ts search [flags]
```

| Flag | Meaning |
|---|---|
| `--location`, `-l` | State: `kuala-lumpur` (`KL`), `selangor` (`PJ`), `putrajaya`, `penang`, `johor` (`JB`), `perak`, `pahang`, `negeri-sembilan`, `malacca` (`melaka`), `kedah`, `kelantan`, `terengganu`, `perlis`, `sabah`, `sarawak`, `labuan`, `overseas`. Omit for all of Malaysia. |
| `--category`, `-c` | Specialisation slug, optionally `<category>/<sub>`. Table below. |
| `--query`, `-q` | Keywords, client-side. Every term must match. `"quoted phrase"` matches as one term. |
| `--job-type` | `full-time` or `internship`. These are the only two types Hiredly's sitemaps expose. |
| `--jobage` | Listings active within N days (client-side). |
| `--page` | 1-indexed start page (30 listings per page). |
| `--pages` | Consecutive pages to scan, 1-5 (default 1). |
| `--limit`, `-n` | Cap results emitted. |
| `--format` | `json` (default), `table`, `plain`. |

### detail

```
bun run .agents/skills/hiredly-search/cli/src/cli.ts detail <slug|url> [--format json|plain]
```

Returns the full description and requirements as readable text, plus salary,
job type, career level, experience range, `datePosted`, `validThrough` and
`isActive`. A closed posting comes back with `isActive: false`. It is not an
error.

## Categories

| Category (`-c`) | Sub-categories (`-c <category>/<sub>`) |
|---|---|
| `accounting-finance` | `audit-taxation`, `corporate-finance-investment`, `general-cost-accounting` |
| `admin-human-resources` | `clerical-administrative-secretarial`, `hr-operations-payroll-admin-office-management`, `hr-strategy-ld-performance-management`, `talent-acquisition-recruitment` |
| `building-construction` | `architecture`, `property-real-estate-management`, `quantity-surveying` |
| `creative` | `copywriting-content-creation`, `graphic-design`, `interior-design`, `multimedia-design`, `ui-ux-design`, `videography-photography` |
| `customer-service` | `customer-service` |
| `education-training` | `education-teaching` |
| `engineering` | `aeronautical-engineering`, `agricultural-engineering`, `automotive-engineering`, `biomedical-engineering`, `chemical-engineering`, `civil-engineering`, `computer-engineering`, `electrical-engineering`, `electronic-engineering`, `environmental-engineering`, `general-engineering`, `industrial-engineering`, `mechanical-engineering`, `mechatronics-engineering`, `oil-gas-engineering`, `telecommunications-engineering` |
| `financial-services-banking` | `financial-services-banking` |
| `food-beverage` | `food-beverage-on-ground` |
| `healthcare` | `dentist-opticians`, `doctor-health-specialist`, `nurse-medical-support`, `pharmaceutical` |
| `hospitality` | `hospitality-on-ground` |
| `information-technology` | `cybersecurity-network-security`, `data-science-analytics`, `general-it`, `hardware-network-infrastructure-on-premises-cloud`, `pre-sales-it-business-analyst-business-intelligence`, `software-development-qa-testing`, `system-it-helpdesk-database-administrator` |
| `legal` | `law-legal-services` |
| `manufacturing` | `general-manufacturing`, `manufacturing-maintenance`, `manufacturing-operations`, `manufacturing-process-design`, `manufacturing-quality-assurance`, `procurement-material-management` |
| `marketing-communications` | `advertising-branding`, `digital-marketing`, `events-management`, `merchandising-buyer`, `public-relations` |
| `others` | `general-work`, `management-trainee`, `others` |
| `product-management` | `general-product-management`, `it-product-management` |
| `project-management` | `general-project-management`, `it-project-management` |
| `retail` | `retail-jobs` |
| `sales` | `business-development`, `general-sales`, `key-account-relationship-management`, `telesales-telemarketing` |
| `sciences` | `actuarial-statistical-science`, `field-science`, `lab-science` |
| `supply-chain-logistics` | `supply-chain-logistics` |

(Snapshot of Hiredly's own specialisation list, 2026-09-24. If a slug starts
returning "Listing page not found", re-check it against
`https://my.hiredly.com/sitemap-1-filter.xml`.)

## Examples

```bash
# Supply chain roles in Kuala Lumpur
bun run .agents/skills/hiredly-search/cli/src/cli.ts search -l "Kuala Lumpur" -c supply-chain-logistics --format table

# "Operations" anywhere in Selangor listings from the last 2 weeks, scanning 3 pages
bun run .agents/skills/hiredly-search/cli/src/cli.ts search -l selangor -q operations --pages 3 --jobage 14 --format table

# Full-time data roles in Penang
bun run .agents/skills/hiredly-search/cli/src/cli.ts search -c information-technology/data-science-analytics -l penang --job-type full-time --format table

# Graduate / management-trainee programmes in KL
bun run .agents/skills/hiredly-search/cli/src/cli.ts search -c others/management-trainee -l kl --format table

# Full posting
bun run .agents/skills/hiredly-search/cli/src/cli.ts detail <slug> --format plain
```

## Output

| Field | Notes |
|---|---|
| `id` | Hiredly job slug. Pass it to `detail`. |
| `title`, `company`, `location`, `date`, `url` | Contract fields. `location` is `"<city>, <state>"`, and is sometimes a full street address. `date` is the listing's `activeAt` date. |
| `salary` | `"RM 4,000 - RM 6,000 / month"`. `null` when the employer marks it undisclosed. Hiredly salaries are monthly MYR, and `tools/myr_salary.py` normalises them for scoring. |
| `jobType`, `careerLevel`, `experience` | As Hiredly states them (`experience` e.g. `"2-4 years"`). |
| `categories`, `skills` | Hiredly's own tags. |
| `externalUrl` | Set when Hiredly lists a job that is hosted on the employer's own site. |

## Notes

- **Language signal:** many Malaysian postings put a language requirement in the
  title ("Mandarin Speaker", "Thai Speaking") or write the whole ad in Bahasa
  Malaysia. `04-job-evaluation.md`'s Language Gate reads the detail text for this.
  Do not skip a posting just because it is written in BM.
- **`externalUrl` listings** are Hiredly-hosted summaries of jobs that live on
  another site. Apply via that URL, and run `tools/robots_check.py` on it before
  any fetch.
- Parsing anchors and the path grammar are recorded in `url-reference.md`.
