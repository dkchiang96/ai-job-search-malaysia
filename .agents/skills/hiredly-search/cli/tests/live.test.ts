import { describe, expect, test } from "bun:test"
import { BASE_URL } from "../src/helpers"
import { parseJSON, runCLI } from "./helpers"

// Live smoke test against my.hiredly.com. Skipped when HIREDLY_OFFLINE=1, or
// automatically when the site can't be reached at all (no network, DNS
// failure, timeout), so an offline `bun test` reports 34 pass + 1 skip rather
// than a failure. It still FAILS when the site answers but the CLI can't read
// it: a layout change is exactly what this test exists to catch.

async function reachable(): Promise<boolean> {
  if (process.env.HIREDLY_OFFLINE === "1") return false
  try {
    await fetch(`${BASE_URL}/robots.txt`, {
      headers: { "User-Agent": "Mozilla/5.0 (compatible; hiredly-search-cli/1.0)" },
      signal: AbortSignal.timeout(8000),
    })
    return true // any HTTP answer counts as reachable
  } catch {
    return false
  }
}

const online = await reachable()
if (!online) console.warn("live hiredly: my.hiredly.com unreachable - live test skipped")

interface SearchOut {
  meta: { count: number; page: number }
  results: Array<{ id: string; title: string; url: string }>
}

describe.skipIf(!online)("live hiredly", () => {
  test("search returns real results with id/title/url", async () => {
    const out = parseJSON<SearchOut>(await runCLI(["search", "-l", "kuala-lumpur", "--limit", "3"]))
    expect(out.results.length).toBeGreaterThan(0)
    for (const r of out.results) {
      expect(r.id).toBeTruthy()
      expect(r.title).toBeTruthy()
      expect(r.url).toStartWith("https://my.hiredly.com/jobs/")
    }
  })
})
