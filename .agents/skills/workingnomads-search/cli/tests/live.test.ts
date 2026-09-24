import { describe, test, expect } from "bun:test";
import { runCLI, parseJSON } from "./helpers";

// Live smoke test against the real portal, per add-portal.md Step 3's "File specifics".
// Keep volume low: one search call, one detail call.
describe("live smoke test", () => {
  test("search returns real results with non-null id/title/url", async () => {
    // No --query: this board's API has no server-side filtering and its feed
    // is small (dozens of listings), so the unfiltered call is the reliable
    // smoke test rather than betting on a keyword being present right now.
    const result = await runCLI(["search", "--limit", "5"]);
    const body = parseJSON<{ meta: { count: number }; results: any[] }>(result);
    expect(body.results.length).toBeGreaterThan(0);
    for (const r of body.results) {
      expect(r.id).toBeTruthy();
      expect(r.title).toBeTruthy();
      expect(r.url).toContain("workingnomads.com/job/go/");
    }
  }, 30000);

  test("detail returns a readable description for a real posting", async () => {
    const search = await runCLI(["search", "--limit", "1"]);
    const body = parseJSON<{ results: { id: string }[] }>(search);
    expect(body.results.length).toBeGreaterThan(0);

    const result = await runCLI(["detail", body.results[0].id, "--format", "plain"]);
    expect(result.exitCode).toBe(0);
    expect(result.stdout.length).toBeGreaterThan(0);
    expect(result.stdout).not.toMatch(/<[a-z]+>/i); // no leftover HTML tags
  }, 30000);
});
