import { describe, test, expect } from "bun:test";
import { runCLI, parseJSON } from "./helpers";

// Live smoke test against the real portal, per add-portal.md Step 3's "File specifics".
// Keep volume low: one search call, one detail call.
describe("live smoke test", () => {
  test("search returns real results with non-null id/title/url", async () => {
    const result = await runCLI(["search", "-q", "operations", "--limit", "5"]);
    const body = parseJSON<{ meta: { count: number }; results: any[] }>(result);
    expect(body.results.length).toBeGreaterThan(0);
    for (const r of body.results) {
      expect(r.id).toBeTruthy();
      expect(r.title).toBeTruthy();
      expect(r.url).toContain("weworkremotely.com/remote-jobs/");
    }
  }, 30000);

  test("detail returns a readable description for a real posting", async () => {
    const search = await runCLI(["search", "-q", "operations", "--limit", "1"]);
    const body = parseJSON<{ results: { id: string }[] }>(search);
    expect(body.results.length).toBeGreaterThan(0);

    const result = await runCLI(["detail", body.results[0].id, "--format", "plain"]);
    expect(result.exitCode).toBe(0);
    expect(result.stdout.length).toBeGreaterThan(0);
    expect(result.stdout).not.toMatch(/<[a-z]+>/i); // no leftover HTML tags
  }, 30000);
});
