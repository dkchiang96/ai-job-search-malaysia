import { describe, expect, test } from "bun:test"
import { parseJSON, runCLI } from "./helpers"

// Live smoke test against my.hiredly.com - two requests per run. Skipped when
// HIREDLY_OFFLINE=1 (e.g. CI without network).

const live = process.env.HIREDLY_OFFLINE === "1" ? describe.skip : describe

interface SearchOut {
  meta: { count: number; page: number }
  results: Array<{ id: string; title: string; url: string }>
}

live("live hiredly", () => {
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
