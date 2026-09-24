// Data source: Remote OK's public JSON API (https://remoteok.com/api) for
// listings, and each posting's detail page (https://remoteok.com/remote-jobs/<id>),
// which embeds a schema.org JobPosting JSON-LD block. No authentication required.
//
// Robots.txt note (investigated 2026-08-30): the site's generic `User-agent: *`
// group (which this CLI's honest, tool-identifying User-Agent falls under)
// explicitly `Allow: /` with `Content-Signal: use=reference`, disallowing only
// AJAX/tracking paths this CLI never touches. A separate, narrower block
// specifically for the literal token "ClaudeBot" disallows everything, while
// yet another block groups "ClaudeBot" with other AI/LLM crawlers under
// `Allow: /` for citing public job listings — a self-contradiction in the
// site's own file. This CLI does not send "ClaudeBot" as its User-Agent, so it
// matches the generic allow-all group; flagged here for anyone auditing this
// skill later, since it directly involves Claude by name.

export const LIST_URL = "https://remoteok.com/api"
export const DETAIL_BASE = "https://remoteok.com/remote-jobs"

/**
 * Remote OK's `tags` query param matches against a fixed taxonomy (confirmed
 * via investigation: an unrecognized tag returns zero results, no free-text
 * fallback) but, when it does match, pulls from a materially larger backing
 * set than the ~100-most-recent unfiltered feed (e.g. `tags=operations`
 * returned 99 results vs. 1 from a client-side substring match over the
 * unfiltered feed for the same word). This list is deliberately not a
 * complete taxonomy of the whole site — it was sampled from operations-
 * tagged listings during investigation (2026-08-30) and covers the terms
 * this skill's actual queries use, not every category Remote OK supports.
 * Multi-word tags use a literal space (confirmed: `tags=project manager`,
 * URL-encoded, works), not a hyphen.
 */
export const KNOWN_TAGS = new Set([
  "admin", "administrator", "ai", "analyst", "analytics", "assistant", "banking",
  "bus dev", "cloud", "consulting", "content", "coordinator", "customer support",
  "data entry", "dev", "director", "ecommerce", "education", "engineer", "engineering",
  "excel", "exec", "finance", "financial", "full time", "fulltime", "gaming", "hardware",
  "healthcare", "hr", "instructor", "junior", "lead", "leader", "legal", "management",
  "manager", "marketing", "medical", "mobile", "non tech", "operational", "operations",
  "ops", "other", "part time", "product", "project manager", "quality assurance", "saas",
  "sales", "security", "senior", "social media", "strategy", "supervisor", "support",
  "technical", "telecommuting", "test", "testing", "training", "travel",
  "virtual assistant", "work from home",
])

/** The list URL to fetch for a given query: the tag endpoint when the query is an exact known-tag match (larger backing set), else the unfiltered feed (client-side substring match applied by the caller). */
export function buildListUrl(query: string | undefined): string {
  const q = query?.toLowerCase().trim()
  if (q && KNOWN_TAGS.has(q)) {
    return `${LIST_URL}?tags=${encodeURIComponent(q)}`
  }
  return LIST_URL
}

export function writeError(error: string, code: string): void {
  process.stderr.write(JSON.stringify({ error, code }) + "\n")
}

const UA = "Mozilla/5.0 (compatible; remoteok-search-cli/1.0)"

async function fetchWithBackoff(url: string): Promise<Response | null> {
  const maxRetries = 6
  let delay = 500
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const response = await fetch(url, {
      headers: {
        "User-Agent": UA,
        Accept: "application/json,text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
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

/** Fetch the list API. Returns the raw JSON array (element 0 is the API's own ToS notice, not a job). */
export async function fetchJobList(url: string): Promise<any[]> {
  const response = await fetchWithBackoff(url)
  if (!response) return []
  return (await response.json()) as any[]
}

/** Fetch a detail page's HTML. Returns "" on a 404. */
export async function htmlFetch(url: string): Promise<string> {
  const response = await fetchWithBackoff(url)
  if (!response) return ""
  return response.text()
}

export interface JobCard {
  id: string
  title: string
  company: string | null
  /**
   * Remote OK's own per-posting location string, e.g. "United States, ",
   * "Miami, Miami, Florida, United States", or the literal "Remote" (which
   * investigation confirmed corresponds to an unrestricted
   * `applicantLocationRequirements: [{"name":"Anywhere"}]` on the detail
   * page's structured data) — trimmed of trailing ", " noise. This is NOT
   * guaranteed to be a stated applicant-eligibility restriction on every
   * posting (Remote OK aggregates listings from many sources of varying
   * quality); cross-check against `detail`'s `applicantLocationRequirement`
   * and the posting text itself before relying on it.
   */
  location: string | null
  /** ISO date (day granularity), from the API's own `date` field. */
  date: string | null
  url: string
}

export interface JobDetail extends JobCard {
  description: string | null
  employmentType: string | null
  companyUrl: string | null
  /** schema.org `validThrough` from the posting's JSON-LD, verbatim — treat as approximate, not a confirmed employer-set deadline. */
  deadline: string | null
  /** schema.org `applicantLocationRequirements` from the posting's JSON-LD, when present. "Anywhere" means explicitly unrestricted. */
  applicantLocationRequirement: string | null
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

/** Trim Remote OK's trailing ", " noise on partially-populated location strings; empty becomes null. */
function cleanLocation(raw: string | undefined | null): string | null {
  if (!raw) return null
  const trimmed = raw.replace(/(,\s*)+$/, "").trim()
  return trimmed || null
}

/** Extract the id from a slug like "acme-head-of-operations-1132182" (Remote OK's convention: trailing numeric id). */
function idFromSlug(slug: string): string {
  const m = slug.match(/-(\d+)$/)
  return m ? m[1] : slug
}

/**
 * Map the raw /api array to JobCard[]. Skips element 0 (the API's ToS
 * notice — identifiable by having no `id` field) and any malformed entries.
 * When `query` is given AND `applyClientFilter` is true, filters
 * case-insensitively against the title, company, and tags. Pass
 * `applyClientFilter: false` when `raw` already came from a `tags=`-filtered
 * fetch (see `buildListUrl`/`KNOWN_TAGS`) — re-filtering by substring on top
 * of that would incorrectly drop server-matched entries whose title doesn't
 * happen to literally contain the query text (e.g. a listing tagged
 * "operations" but titled "COO").
 */
export function parseJobList(raw: any[], query?: string, applyClientFilter = true): JobCard[] {
  const results: JobCard[] = []
  const q = query?.toLowerCase().trim()

  for (const entry of raw) {
    if (!entry || typeof entry !== "object" || !entry.id) continue // skips the ToS notice object

    const title = typeof entry.position === "string" ? clean(entry.position) : null
    if (!title) continue

    if (q && applyClientFilter) {
      const haystack = [title, entry.company, ...(Array.isArray(entry.tags) ? entry.tags : [])]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
      if (!haystack.includes(q)) continue
    }

    results.push({
      id: String(entry.id),
      title,
      company: typeof entry.company === "string" ? clean(entry.company) || null : null,
      location: cleanLocation(entry.location),
      date: typeof entry.date === "string" ? entry.date.slice(0, 10) : null,
      url: typeof entry.url === "string" ? entry.url : `${DETAIL_BASE}/${entry.id}`,
    })
  }

  return results
}

/**
 * Some job boards' Rails/PHP templates embed JSON-LD with literal, unescaped
 * control characters inside string values (confirmed on We Work Remotely;
 * not observed on Remote OK during investigation, but cheap to guard against
 * defensively here too). Escapes control chars found *inside* string
 * literals only, leaving structural whitespace between tokens untouched.
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

/**
 * Parse a posting's detail page via its embedded schema.org JobPosting
 * JSON-LD block. Remote OK's detail pages carry multiple `<script
 * type="application/ld+json">` blocks (confirmed live: an `Organization`
 * block for the site itself precedes the `JobPosting` one) — every block is
 * parsed and the first with `"@type":"JobPosting"` is used, rather than
 * assuming the first script tag on the page is the right one.
 */
export function parseJobDetail(html: string, id: string): JobDetail {
  const blockRe = /<script type="application\/ld\+json">\s*([\s\S]*?)\s*<\/script>/gi
  let ld: any = null
  let m: RegExpExecArray | null
  while ((m = blockRe.exec(html)) !== null) {
    try {
      const parsed = JSON.parse(sanitizeJsonLdControlChars(m[1]))
      if (parsed?.["@type"] === "JobPosting") {
        ld = parsed
        break
      }
    } catch {
      // try the next block
    }
  }

  const title = ld?.title ? clean(String(ld.title)) : null
  const company = ld?.hiringOrganization?.name ? clean(String(ld.hiringOrganization.name)) : null
  const companyUrl = ld?.hiringOrganization?.url ?? ld?.hiringOrganization?.sameAs ?? null
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

  const description = ld?.description ? clean(String(ld.description)) || null : null

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
