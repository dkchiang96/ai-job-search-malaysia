// Data source: We Work Remotely's public search page (server-rendered HTML —
// the site returns every matching result in one response; its `?page`
// parameter has no effect over plain HTTP, confirmed during investigation)
// and each posting's detail page, which embeds a schema.org JobPosting
// JSON-LD block. No authentication required.

export const SEARCH_URL = "https://weworkremotely.com/remote-jobs/search"
export const DETAIL_BASE = "https://weworkremotely.com/remote-jobs"

export function writeError(error: string, code: string): void {
  process.stderr.write(JSON.stringify({ error, code }) + "\n")
}

const UA = "Mozilla/5.0 (compatible; weworkremotely-search-cli/1.0)"

/** Fetch HTML with exponential backoff on 429/5xx. Returns "" on a 404. */
export async function htmlFetch(url: string): Promise<string> {
  const maxRetries = 6
  let delay = 500
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const response = await fetch(url, {
      headers: {
        "User-Agent": UA,
        Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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
    if (response.status === 404) return ""
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status} ${response.statusText}`)
    }
    return response.text()
  }
  throw new Error("Request failed after max retries")
}

export interface JobCard {
  id: string
  title: string
  company: string | null
  /**
   * The posting's region/eligibility chip as WWR itself displays it, e.g.
   * "Anywhere in the World" or "🇺🇸 United States of America" — null when the
   * listing carries no region chip at all. This is NOT the company's
   * headquarters (WWR shows that separately); it is WWR's own signal for who
   * may apply, which is exactly what a remote-work eligibility check needs.
   */
  location: string | null
  /** ISO date estimate (day granularity) derived from the search page's relative-age chip, e.g. "3d". */
  date: string | null
  url: string
}

export interface JobDetail extends JobCard {
  description: string | null
  employmentType: string | null
  companyUrl: string | null
  /**
   * schema.org `validThrough` from the posting's JSON-LD, verbatim. Many
   * boards default this to a fixed window rather than an employer-set
   * deadline — treat as approximate, not confirmed.
   */
  deadline: string | null
  /**
   * schema.org `applicantLocationRequirements` from the posting's JSON-LD,
   * when present (e.g. "US"). WWR omits this field entirely for many
   * multi-region or unrestricted postings, so null here means "not stated in
   * structured data" — not "open to anywhere". Cross-check the search
   * result's `location` chip and the posting text itself.
   */
  applicantLocationRequirement: string | null
}

function numericEntity(cp: number): string {
  return cp >= 0 && cp <= 0x10ffff ? String.fromCodePoint(cp) : ""
}

function decodeHtmlEntities(text: string): string {
  return text
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'")
    .replace(/&#(\d+);/g, (_, dec) => numericEntity(parseInt(dec, 10)))
    .replace(/&#[xX]([0-9a-fA-F]+);/g, (_, hex) => numericEntity(parseInt(hex, 16)))
    .replace(/&nbsp;/g, " ")
}

function stripTags(html: string): string {
  return html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim()
}

function clean(html: string): string {
  return decodeHtmlEntities(stripTags(html))
}

const EMPLOYMENT_TYPES = new Set([
  "full-time",
  "part-time",
  "contract",
  "freelance",
  "internship",
  "full-time/part-time",
  "part-time/full-time",
])

/** Classify one category chip as salary, employment type, or a region/eligibility tag. */
function classifyChip(text: string): "salary" | "employment" | "region" {
  if (text.startsWith("$")) return "salary"
  if (EMPLOYMENT_TYPES.has(text.toLowerCase())) return "employment"
  return "region"
}

/** Convert We Work Remotely's relative date chip ("3d", "Today", "2mo") to an ISO date estimate. */
export function relativeToISODate(raw: string): string | null {
  const text = raw.trim().toLowerCase()
  if (!text) return null
  if (text === "today" || text === "new") return new Date().toISOString().slice(0, 10)
  const m = text.match(/^(\d+)\s*(h|d|mo|y)$/)
  if (!m) return null
  const n = parseInt(m[1], 10)
  const unit = m[2]
  const msPerUnit: Record<string, number> = {
    h: 3600_000,
    d: 86_400_000,
    mo: 30 * 86_400_000,
    y: 365 * 86_400_000,
  }
  const date = new Date(Date.now() - n * msPerUnit[unit])
  return date.toISOString().slice(0, 10)
}

/**
 * Parse the search-results page: one `<li>` per posting, anchored by its
 * `listing-link` `<a href="/remote-jobs/<slug>">`. Split on that anchor and
 * parse each chunk independently so one malformed card cannot break the rest.
 */
export function parseJobCards(html: string): JobCard[] {
  const results: JobCard[] = []
  const chunks = html.split(/<a class="listing-link[^"]*" href="\/remote-jobs\//).slice(1)

  for (const chunk of chunks) {
    const slugMatch = chunk.match(/^([a-z0-9-]+)"/)
    if (!slugMatch) continue
    const id = slugMatch[1]

    const titleMatch = chunk.match(/class="new-listing__header__title__text"[^>]*>([\s\S]*?)<\/span>/i)
    const title = titleMatch ? clean(titleMatch[1]) : null
    if (!title) continue // filters out non-job anchors (nav/CTA links) sharing the same href prefix

    const dateMatch = chunk.match(/class="new-listing__header__icons__date"[^>]*>([\s\S]*?)<\/p>/i)
    const date = dateMatch ? relativeToISODate(clean(dateMatch[1])) : null

    const companyMatch = chunk.match(/class="new-listing__company-name"[^>]*>([\s\S]*?)<\/p>/i)
    const company = companyMatch ? clean(companyMatch[1]) || null : null

    const categoriesBlock = chunk.match(/class="new-listing__categories"[^>]*>([\s\S]*?)<\/div>/i)
    let location: string | null = null
    if (categoriesBlock) {
      const chipRe = /class="new-listing__categories__category"[^>]*>([\s\S]*?)<\/p>/gi
      let cm: RegExpExecArray | null
      while ((cm = chipRe.exec(categoriesBlock[1])) !== null) {
        const text = clean(cm[1])
        if (text && classifyChip(text) === "region") {
          location = text
          break
        }
      }
    }

    results.push({
      id,
      title,
      company,
      location,
      date,
      url: `${DETAIL_BASE}/${id}`,
    })
  }

  return results
}

/**
 * WWR's JobPosting JSON-LD embeds its `description` value with literal,
 * unescaped newlines/tabs inside the string (confirmed live, 2026-08-30) —
 * invalid per strict JSON, and `JSON.parse` throws "Unterminated string" on
 * it as-is. Escape control characters found *inside* string literals only,
 * leaving structural whitespace between tokens untouched.
 */
function sanitizeJsonLdControlChars(raw: string): string {
  let out = ""
  let inString = false
  let escaped = false
  for (const c of raw) {
    if (inString) {
      if (escaped) {
        out += c
        escaped = false
      } else if (c === "\\") {
        out += c
        escaped = true
      } else if (c === '"') {
        inString = false
        out += c
      } else if (c === "\n") {
        out += "\\n"
      } else if (c === "\r") {
        // drop; either paired with a following \n already handled above, or a stray CR
      } else if (c === "\t") {
        out += "\\t"
      } else {
        out += c
      }
    } else {
      if (c === '"') inString = true
      out += c
    }
  }
  return out
}

/** Parse a posting's detail page via its embedded schema.org JobPosting JSON-LD block. */
export function parseJobDetail(html: string, id: string): JobDetail {
  const ldMatch = html.match(/<script type="application\/ld\+json">\s*([\s\S]*?)\s*<\/script>/i)
  let ld: any = null
  if (ldMatch) {
    try {
      ld = JSON.parse(sanitizeJsonLdControlChars(ldMatch[1]))
    } catch {
      ld = null
    }
  }

  const title = ld?.title ? clean(String(ld.title)) : null
  const company = ld?.hiringOrganization?.name ? clean(String(ld.hiringOrganization.name)) : null
  const companyUrl = ld?.hiringOrganization?.sameAs ?? null
  const employmentType = ld?.employmentType ?? null
  const deadline = ld?.validThrough ? String(ld.validThrough).slice(0, 10) : null

  let applicantLocationRequirement: string | null = null
  if (Array.isArray(ld?.applicantLocationRequirements) && ld.applicantLocationRequirements.length > 0) {
    applicantLocationRequirement =
      ld.applicantLocationRequirements
        .map((r: any) => r?.name)
        .filter(Boolean)
        .join(", ") || null
  }

  let description: string | null = null
  if (ld?.description) {
    // The JSON-LD description field is itself HTML, entity-encoded inside the JSON string value.
    const decoded = decodeHtmlEntities(String(ld.description))
    const withBreaks = decoded
      .replace(/<\s*br\s*\/?>/gi, "\n")
      .replace(/<\/(p|li|ul|ol|div|h\d)>/gi, "\n")
    description = decodeHtmlEntities(stripTags(withBreaks)).replace(/\n{3,}/g, "\n\n").trim() || null
  }

  return {
    id,
    title: title ?? "(untitled)",
    company,
    companyUrl,
    location: applicantLocationRequirement,
    date: ld?.datePosted ? String(ld.datePosted).slice(0, 10) : null,
    url: `${DETAIL_BASE}/${id}`,
    description,
    employmentType,
    deadline,
    applicantLocationRequirement,
  }
}
