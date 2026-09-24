import { SEARCH_URL, htmlFetch, parseJobCards, writeError, type JobCard } from "../helpers.js"

const PAGE_SIZE = 20

export interface SearchOpts {
  query?: string
  jobage: number
  page: number
  limit?: number
  format: "json" | "table" | "plain"
}

function buildUrl(opts: SearchOpts): string {
  const params = new URLSearchParams()
  if (opts.query) params.set("term", opts.query)
  return `${SEARCH_URL}?${params.toString()}`
}

/** Keep a card if its date is within the jobage window, or if the date could not be determined (permissive). */
function withinJobage(card: JobCard, jobage: number): boolean {
  if (jobage >= 9999) return true
  if (!card.date) return true
  const days = Math.floor((Date.now() - new Date(card.date).getTime()) / 86_400_000)
  return days <= jobage
}

function renderTable(cards: JobCard[]): string {
  if (cards.length === 0) return "No results."
  const rows = cards.map((c) => {
    const title = (c.title || "").slice(0, 42).padEnd(42)
    const company = (c.company || "—").slice(0, 26).padEnd(26)
    const loc = (c.location || "—").slice(0, 28).padEnd(28)
    const date = c.date || "—"
    return `${c.id.slice(0, 30).padEnd(30)} ${title} ${company} ${loc} ${date}`
  })
  const header =
    "ID".padEnd(30) + " " + "TITLE".padEnd(42) + " " + "COMPANY".padEnd(26) + " " + "REGION/ELIGIBILITY".padEnd(28) + " DATE"
  return [header, "-".repeat(header.length), ...rows].join("\n")
}

export async function runSearch(opts: SearchOpts): Promise<number> {
  try {
    const html = await htmlFetch(buildUrl(opts))
    let cards = parseJobCards(html).filter((c) => withinJobage(c, opts.jobage))

    // The portal has no working server-side pagination over plain HTTP (confirmed:
    // ?page=2 returns the same result set as ?page=1) — every matching result comes
    // back in one response, so pagination is implemented client-side over the full set.
    const start = (opts.page - 1) * PAGE_SIZE
    cards = cards.slice(start, start + PAGE_SIZE)
    if (opts.limit !== undefined && opts.limit >= 0) cards = cards.slice(0, opts.limit)

    if (opts.format === "table") {
      process.stdout.write(renderTable(cards) + "\n")
    } else if (opts.format === "plain") {
      process.stdout.write(
        cards
          .map(
            (c) =>
              `${c.title}\n  ${c.company || "—"} · ${c.location || "—"} · ${c.date || "—"}\n  id: ${c.id}\n  ${c.url}`,
          )
          .join("\n\n") + "\n",
      )
    } else {
      process.stdout.write(
        JSON.stringify({ meta: { count: cards.length, page: opts.page }, results: cards }, null, 2) + "\n",
      )
    }
    return 0
  } catch (e) {
    writeError(e instanceof Error ? e.message : String(e), "SEARCH_FAILED")
    return 1
  }
}
