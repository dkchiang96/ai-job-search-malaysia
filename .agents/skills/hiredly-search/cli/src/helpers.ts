// Data source: Hiredly Malaysia's public, server-rendered job pages
// (https://my.hiredly.com). Each listing page is a Next.js page that embeds its
// results in a <script id="__NEXT_DATA__"> JSON blob, so parsing is one
// JSON.parse - no DOM parser, no runtime dependencies.
//
// What this CLI deliberately does NOT touch: Hiredly's keyword search and its
// job API run through my-api.hiredly.com, whose robots.txt is `Disallow: /` for
// every user agent. my.hiredly.com itself publishes no rule for general
// crawlers (checked 2026-09-24), and its server-rendered category / state /
// job-type pages are listed in its own sitemaps - those pages are the only
// thing this CLI fetches. The consequence: `--query` cannot be sent to Hiredly
// and is applied client-side to the fetched page(s). See url-reference.md.

export const BASE_URL = "https://my.hiredly.com"

export function writeError(error: string, code: string): void {
  process.stderr.write(JSON.stringify({ error, code }) + "\n")
}

const UA = "Mozilla/5.0 (compatible; hiredly-search-cli/1.0)"

/** Fetch HTML with exponential backoff on 429/5xx. Returns "" on a 404. */
export async function htmlFetch(url: string): Promise<string> {
  const maxRetries = 6
  let delay = 500
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const response = await fetch(url, {
      headers: {
        "User-Agent": UA,
        Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-MY,en;q=0.9",
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

/** Pull the __NEXT_DATA__ JSON out of a Hiredly page. Throws if absent. */
export function extractNextData(html: string): any {
  const m = html.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/)
  if (!m) throw new Error("Could not locate __NEXT_DATA__ in Hiredly HTML (page layout changed?)")
  return JSON.parse(m[1])
}

// ---------------------------------------------------------------------------
// URL building. Every path shape below appears in Hiredly's own sitemaps
// (sitemap-1/2/3-filter.xml): /jobs-in-<category>[/<sub>][/in-<state>][/<type>]
// and /jobs-in-<state>[/<type>]. Only the two job types those sitemaps list
// are accepted.
// ---------------------------------------------------------------------------

export const JOB_TYPES = ["full-time", "internship"] as const

export const STATES = [
  "kuala-lumpur", "selangor", "putrajaya", "penang", "johor", "perlis", "kedah",
  "kelantan", "terengganu", "malacca", "negeri-sembilan", "pahang", "perak",
  "sabah", "sarawak", "labuan", "overseas",
] as const

/** "Kuala Lumpur" / "KL" / "kuala_lumpur" -> "kuala-lumpur". */
export function normalizeState(input: string): string | null {
  const s = input.trim().toLowerCase()
  const aliases: Record<string, string> = {
    kl: "kuala-lumpur", "wp kuala lumpur": "kuala-lumpur", "federal territory of kuala lumpur": "kuala-lumpur",
    melaka: "malacca", "pulau pinang": "penang", ns: "negeri-sembilan", jb: "johor", "johor bahru": "johor",
    pj: "selangor", "petaling jaya": "selangor", "shah alam": "selangor", cyberjaya: "selangor",
  }
  if (aliases[s]) return aliases[s]
  const slug = s.replace(/[\s_]+/g, "-")
  return (STATES as readonly string[]).includes(slug) ? slug : null
}

export interface PathOpts {
  category?: string // "<category>" or "<category>/<sub>"
  state?: string // normalized slug
  jobType?: string
  page: number
}

export function buildListUrl(opts: PathOpts): string {
  const parts: string[] = []
  if (opts.category) {
    const [cat, sub] = opts.category.split("/")
    parts.push(`jobs-in-${cat}`)
    if (sub) parts.push(sub)
    if (opts.state) parts.push(`in-${opts.state}`)
  } else if (opts.state) {
    parts.push(`jobs-in-${opts.state}`)
  }
  if (opts.jobType) parts.push(opts.jobType)
  const path = parts.length ? "/" + parts.join("/") : "/jobs"
  return `${BASE_URL}${path}${opts.page > 1 ? `?page=${opts.page}` : ""}`
}

// ---------------------------------------------------------------------------
// Parsing
// ---------------------------------------------------------------------------

export interface JobCard {
  id: string // Hiredly job slug - the identifier `detail` takes
  title: string
  company: string | null
  location: string | null
  date: string | null // YYYY-MM-DD (the listing's activeAt date)
  url: string
  salary: string | null // "RM 4,000 - RM 6,000 / month", or null when undisclosed
  jobType: string | null
  careerLevel: string | null
  experience: string | null // "1-3 years"
  categories: string[]
  skills: string[]
  externalUrl: string | null // set when Hiredly lists a job hosted elsewhere
}

export interface JobDetail extends JobCard {
  description: string | null
  requirements: string | null
  datePosted: string | null
  validThrough: string | null
  isActive: boolean
}

function str(v: unknown): string | null {
  return typeof v === "string" && v.trim() !== "" ? v.trim() : null
}

/** Hiredly salaries are monthly MYR ranges like "4000 - 6000" or "Undisclosed". */
export function formatSalary(raw: unknown): string | null {
  const s = str(raw)
  if (!s || /undisclosed|negotiable|not specified/i.test(s)) return null
  const nums = s.match(/\d[\d,]*/g)
  if (!nums) return null
  const fmt = (n: string) => `RM ${Number(n.replace(/,/g, "")).toLocaleString("en-US")}`
  return nums.length >= 2 ? `${fmt(nums[0])} - ${fmt(nums[1])} / month` : `${fmt(nums[0])} / month`
}

function formatLocation(job: any): string | null {
  const city = str(job?.location)
  const state = str(job?.stateRegion)
  // Hiredly's `location` is sometimes a full street address; keep it, but lead
  // with the state so a location gate can read it at a glance.
  if (city && state && !city.toLowerCase().includes(state.toLowerCase())) return `${city}, ${state}`
  return city ?? state
}

function formatExperience(job: any): string | null {
  const min = job?.minYearsExperience
  const max = job?.maxYearsExperience
  if (typeof min === "number" && typeof max === "number") {
    if (min === 0 && max === 0) return "no experience required"
    return min === max ? `${min} years` : `${min}-${max} years`
  }
  if (typeof min === "number") return `${min}+ years`
  return null
}

function isoDate(v: unknown): string | null {
  const s = str(v)
  const m = s?.match(/^(\d{4}-\d{2}-\d{2})/)
  return m ? m[1] : null
}

export function toJobCard(job: any): JobCard | null {
  const slug = str(job?.slug)
  const title = str(job?.title)
  if (!slug || !title) return null // one malformed record never breaks the rest
  return {
    id: slug,
    title,
    company: str(job?.company?.name) ?? str(job?.aggregatedCompanyName),
    location: formatLocation(job),
    date: isoDate(job?.activeAt) ?? isoDate(job?.createdAt),
    url: `${BASE_URL}/jobs/${slug}`,
    salary: formatSalary(job?.salary),
    jobType: str(job?.jobType),
    careerLevel: str(job?.careerLevel),
    experience: formatExperience(job),
    categories: Array.isArray(job?.tracks) ? job.tracks.map((t: any) => str(t?.title)).filter(Boolean) : [],
    skills: Array.isArray(job?.skills) ? job.skills.map((s: any) => str(s?.name)).filter(Boolean) : [],
    externalUrl: str(job?.externalJobUrl),
  }
}

/** Parse a listing page's HTML into job cards. */
export function parseListPage(html: string): JobCard[] {
  const data = extractNextData(html)
  const jobs = data?.props?.pageProps?.jobs
  if (!Array.isArray(jobs)) return []
  const cards: JobCard[] = []
  for (const job of jobs) {
    try {
      const card = toJobCard(job)
      if (card) cards.push(card)
    } catch {
      // skip a malformed record rather than failing the page
    }
  }
  return cards
}

/** Minimal HTML -> readable text: paragraphs and list items become lines. */
export function htmlToText(html: string | null): string | null {
  if (!html) return null
  let t = html
    .replace(/<\s*br\s*\/?>/gi, "\n")
    .replace(/<\s*li[^>]*>/gi, "\n- ")
    .replace(/<\/\s*li\s*>/gi, "")
    .replace(/<\/\s*(p|div|h[1-6]|ul|ol)\s*>/gi, "\n")
    .replace(/<[^>]+>/g, "")
  t = decodeEntities(t)
  t = t
    .split("\n")
    .map((l) => l.replace(/[ \t ]+/g, " ").trim())
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim()
  return t || null
}

export function decodeEntities(s: string): string {
  return s
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'")
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
    .replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16)))
}

/** Parse a job page (my.hiredly.com/jobs/<slug>) into a detail record. */
export function parseJobDetail(html: string): JobDetail {
  const data = extractNextData(html)
  const job = data?.props?.pageProps?.job
  const card = toJobCard(job)
  if (!card) throw new Error("Job page did not contain a readable job record")
  const ld = job?.structuredJobData ?? {}
  return {
    ...card,
    description: htmlToText(str(job?.description)),
    requirements: htmlToText(str(job?.requirements)),
    datePosted: isoDate(ld?.datePosted) ?? card.date,
    validThrough: isoDate(ld?.validThrough),
    isActive: job?.active !== false && job?.expired !== true,
  }
}

/**
 * Client-side keyword filter. Every whitespace-separated term must appear in
 * the title, company, categories or skills (case-insensitive). Quoted phrases
 * are matched as one term.
 */
export function matchesQuery(card: JobCard, query: string | undefined): boolean {
  if (!query || !query.trim()) return true
  const hay = [card.title, card.company ?? "", ...card.categories, ...card.skills].join(" ").toLowerCase()
  const terms = (query.toLowerCase().match(/"[^"]+"|\S+/g) ?? []).map((t) => t.replace(/"/g, ""))
  return terms.every((t) => hay.includes(t))
}

/** Client-side posting-age filter (Hiredly exposes no age parameter). */
export function withinJobage(card: JobCard, jobage: number | undefined, today = new Date()): boolean {
  if (!jobage) return true
  if (!card.date) return true // no date: keep it, /scrape flags "date unknown"
  const posted = new Date(card.date + "T00:00:00Z").getTime()
  const ageDays = (today.getTime() - posted) / 86_400_000
  return ageDays <= jobage
}

/** Accept a slug or a full my.hiredly.com/jobs/<slug> URL. */
export function normalizeId(input: string): string | null {
  const s = input.trim()
  const url = s.match(/hiredly\.com\/jobs\/([a-z0-9][a-z0-9-]*)/i)
  if (url) return url[1]
  return /^[a-z0-9][a-z0-9-]*$/i.test(s) ? s : null
}
