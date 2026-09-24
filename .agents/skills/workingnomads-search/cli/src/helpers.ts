// Data source: Working Nomads' public JSON API (https://www.workingnomads.com/api/exposed_jobs/).
// No authentication required. The endpoint returns the site's full current
// listing set in one response (no query params affect it — confirmed via
// investigation: ?category=... and ?keywords=... both return the identical
// unfiltered payload) and already includes the full description inline, so
// there is no separate detail-page fetch to make; `detail <id>` re-fetches
// this same feed and returns the matching entry.

export const LIST_URL = "https://www.workingnomads.com/api/exposed_jobs/"

export function writeError(error: string, code: string): void {
  process.stderr.write(JSON.stringify({ error, code }) + "\n")
}

const UA = "Mozilla/5.0 (compatible; workingnomads-search-cli/1.0)"

async function fetchWithBackoff(url: string): Promise<Response | null> {
  const maxRetries = 6
  let delay = 500
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const response = await fetch(url, {
      headers: {
        "User-Agent": UA,
        Accept: "application/json",
        "Accept-Language": "en-US,en;q=0.9",
      },
      redirect: "follow",
      signal: AbortSignal.timeout(15000),
    })
    if (response.status === 429 || response.status >= 500) {
      if (attempt === maxRetries) {
        throw new Error(`Request failed: ${response.status} ${response.statusText}`)
      }
      const jitter = Math.floor(Math.random() * 500)
      await new Promise((r) => setTimeout(r, delay + jitter))
      delay = Math.min(delay * 2, 8000)
      continue
    }
    if (response.status === 404) return null
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status} ${response.statusText}`)
    }
    return response
  }
  throw new Error("Request failed after max retries")
}

/** Fetch the full current listing feed. Returns [] on a 404 (shouldn't happen in practice). */
export async function fetchJobList(): Promise<any[]> {
  const response = await fetchWithBackoff(LIST_URL)
  if (!response) return []
  const data = await response.json()
  return Array.isArray(data) ? data : []
}

export interface JobCard {
  id: string
  title: string
  company: string | null
  /**
   * Working Nomads' own free-text location/eligibility field, verbatim
   * (e.g. "Global", "USA or Canada only", "Anywhere (working US business
   * hours)", "APAC,Middle East", "the EU, the US, Canada, the UK, Australia,
   * Singapore"). Postings on this board write this field themselves — it is
   * the richest, most direct eligibility signal of any portal skill in this
   * repo, but it is free text, not a controlled taxonomy: match against it
   * with judgment (e.g. "APAC" or "Global" or "Anywhere" as a positive
   * signal for a Malaysia-based candidate), not exact string equality.
   */
  location: string | null
  /** ISO date (day granularity) from the feed's own `pub_date`. */
  date: string | null
  url: string
}

export interface JobDetail extends JobCard {
  description: string | null
  category: string | null
  tags: string | null
}

function decodeHtmlEntities(text: string): string {
  return text
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'")
    .replace(/&nbsp;/g, " ")
}

function stripTags(html: string): string {
  return html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim()
}

function clean(html: string): string {
  return decodeHtmlEntities(stripTags(html))
}

/** Working Nomads' `url` field is a "/job/go/<id>/" redirect link — extract the trailing numeric id. */
export function idFromUrl(url: string): string | null {
  const m = url.match(/\/job\/go\/(\d+)\/?/)
  return m ? m[1] : null
}

function toCard(entry: any): JobCard | null {
  const id = typeof entry.url === "string" ? idFromUrl(entry.url) : null
  if (!id) return null
  const title = typeof entry.title === "string" ? clean(entry.title) : null
  if (!title) return null

  return {
    id,
    title,
    company: typeof entry.company_name === "string" ? clean(entry.company_name) || null : null,
    location: typeof entry.location === "string" ? clean(entry.location) || null : null,
    date: typeof entry.pub_date === "string" ? entry.pub_date.slice(0, 10) : null,
    url: entry.url,
  }
}

/**
 * Map the raw feed to JobCard[]. The API has no server-side filtering at
 * all (confirmed: ?category= and ?keywords= both return the identical
 * unfiltered payload), so a `query` is always matched client-side —
 * case-insensitively against title, company, category, and tags.
 */
export function parseJobList(raw: any[], query?: string): JobCard[] {
  const results: JobCard[] = []
  const q = query?.toLowerCase().trim()

  for (const entry of raw) {
    const card = toCard(entry)
    if (!card) continue

    if (q) {
      const haystack = [card.title, card.company, entry.category_name, entry.tags]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
      if (!haystack.includes(q)) continue
    }

    results.push(card)
  }

  return results
}

/** Find one entry's full detail (including description) by id, from the same feed `detail` re-fetches. */
export function findJobDetail(raw: any[], id: string): JobDetail | null {
  for (const entry of raw) {
    const card = toCard(entry)
    if (!card || card.id !== id) continue
    return {
      ...card,
      description: typeof entry.description === "string" ? clean(entry.description) || null : null,
      category: typeof entry.category_name === "string" ? entry.category_name : null,
      tags: typeof entry.tags === "string" ? entry.tags : null,
    }
  }
  return null
}
