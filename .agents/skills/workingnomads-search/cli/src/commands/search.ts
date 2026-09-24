import { fetchJobList, parseJobList, writeError, type JobCard } from "../helpers.js"

const PAGE_SIZE = 20

export interface SearchOpts {
  query?: string
  jobage: number
  page: number
  limit?: number
  format: "json" | "table" | "plain"
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
    const company = (c.company || "—").slice(0, 24).padEnd(24)
    const loc = (c.location || "—").slice(0, 32).padEnd(32)
    const date = c.date || "—"
    return `${c.id.padEnd(9)} ${title} ${company} ${loc} ${date}`
  })
  const header =
    "ID".padEnd(9) + " " + "TITLE".padEnd(42) + " " + "COMPANY".padEnd(24) + " " + "LOCATION/ELIGIBILITY".padEnd(32) + " DATE"
  return [header, "-".repeat(header.length), ...rows].join("\n")
}

export async function runSearch(opts: SearchOpts): Promise<number> {
  try {
    // The API has no server-side filtering (confirmed via investigation) — it
    // always returns the site's full current listing set, so --query is
    // matched client-side over the whole thing. See helpers.ts.
    const raw = await fetchJobList()
    let cards = parseJobList(raw, opts.query).filter((c) => withinJobage(c, opts.jobage))

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
