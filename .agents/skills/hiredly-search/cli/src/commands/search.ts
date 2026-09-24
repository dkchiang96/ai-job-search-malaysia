import {
  buildListUrl,
  htmlFetch,
  matchesQuery,
  parseListPage,
  withinJobage,
  writeError,
  type JobCard,
} from "../helpers.js"

export interface SearchOpts {
  query?: string
  category?: string
  state?: string
  jobType?: string
  jobage?: number
  page: number
  pages: number
  limit?: number
  format: "json" | "table" | "plain"
}

// Hiredly serves 30 listings per page. `--pages` walks consecutive pages from
// `--page`, one request at a time with a pause between them, because the
// keyword filter is client-side and a single page of a broad state listing
// rarely holds enough matches on its own.
const PAGE_PAUSE_MS = 1000

function renderTable(cards: JobCard[]): string {
  if (cards.length === 0) return "No results."
  const header =
    "TITLE".padEnd(40) + " " + "COMPANY".padEnd(26) + " " + "LOCATION".padEnd(24) + " " + "SALARY".padEnd(28) + " DATE"
  const rows = cards.map((c) => {
    const title = c.title.slice(0, 40).padEnd(40)
    const company = (c.company || "—").slice(0, 26).padEnd(26)
    const loc = (c.location || "—").slice(0, 24).padEnd(24)
    const sal = (c.salary || "—").slice(0, 28).padEnd(28)
    return `${title} ${company} ${loc} ${sal} ${c.date || "—"}`
  })
  return [header, "-".repeat(header.length), ...rows].join("\n")
}

export async function runSearch(opts: SearchOpts): Promise<number> {
  try {
    const seen = new Set<string>()
    let cards: JobCard[] = []
    let scanned = 0
    for (let p = opts.page; p < opts.page + opts.pages; p++) {
      if (p > opts.page) await new Promise((r) => setTimeout(r, PAGE_PAUSE_MS))
      const html = await htmlFetch(
        buildListUrl({ category: opts.category, state: opts.state, jobType: opts.jobType, page: p }),
      )
      if (!html) {
        if (p === opts.page) throw new Error("Listing page not found - check --category / --location slugs (see SKILL.md)")
        break
      }
      const pageCards = parseListPage(html)
      scanned += pageCards.length
      if (pageCards.length === 0) break
      for (const c of pageCards) {
        if (seen.has(c.id)) continue
        seen.add(c.id)
        if (matchesQuery(c, opts.query) && withinJobage(c, opts.jobage)) cards.push(c)
      }
    }
    if (opts.limit !== undefined) cards = cards.slice(0, opts.limit)

    if (opts.format === "table") {
      process.stdout.write(renderTable(cards) + "\n")
    } else if (opts.format === "plain") {
      process.stdout.write(
        cards
          .map(
            (c) =>
              `${c.title}\n  ${c.company || "—"} · ${c.location || "—"} · ${c.salary || "salary undisclosed"} · ${c.date || "—"}\n  id: ${c.id}\n  ${c.url}`,
          )
          .join("\n\n") + "\n",
      )
    } else {
      process.stdout.write(
        JSON.stringify(
          { meta: { count: cards.length, page: opts.page, pagesScanned: opts.pages, listingsScanned: scanned }, results: cards },
          null,
          2,
        ) + "\n",
      )
    }
    return 0
  } catch (e) {
    writeError(e instanceof Error ? e.message : String(e), "SEARCH_FAILED")
    return 1
  }
}
