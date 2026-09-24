import { describe, expect, test } from "bun:test"
import { runCLI } from "./helpers"

// Offline: every case below exits before any network call.

function expectJsonError(stderr: string, code: string) {
  const err = JSON.parse(stderr)
  expect(err.code).toBe(code)
  expect(typeof err.error).toBe("string")
}

describe("flag validation", () => {
  test("unknown long flag exits 1 with a JSON error", async () => {
    const r = await runCLI(["search", "--keywords", "ops"])
    expect(r.exitCode).toBe(1)
    expect(r.stdout).toBe("")
    expectJsonError(r.stderr, "UNKNOWN_FLAG")
  })

  test("unknown short flag exits 1", async () => {
    const r = await runCLI(["search", "-z", "1"])
    expect(r.exitCode).toBe(1)
    expectJsonError(r.stderr, "UNKNOWN_FLAG")
  })

  test("unknown state is rejected, not silently widened to all of Malaysia", async () => {
    const r = await runCLI(["search", "-l", "Atlantis"])
    expect(r.exitCode).toBe(1)
    expectJsonError(r.stderr, "BAD_ARG")
  })

  test("malformed category slug is rejected", async () => {
    const r = await runCLI(["search", "-c", "Supply Chain"])
    expect(r.exitCode).toBe(1)
    expectJsonError(r.stderr, "BAD_ARG")
  })

  test("unsupported job type is rejected", async () => {
    const r = await runCLI(["search", "--job-type", "part-time"])
    expect(r.exitCode).toBe(1)
    expectJsonError(r.stderr, "BAD_ARG")
  })

  for (const [flag, value] of [["--jobage", "0"], ["--page", "1.5"], ["--pages", "6"], ["--limit", "-3"]]) {
    test(`${flag} ${value} is rejected`, async () => {
      const r = await runCLI(["search", flag, value])
      expect(r.exitCode).toBe(1)
      expect(r.stderr).toContain('"code"')
    })
  }

  test("bad --format is rejected", async () => {
    const r = await runCLI(["search", "--format", "xml"])
    expect(r.exitCode).toBe(1)
    expectJsonError(r.stderr, "BAD_ARG")
  })

  test("detail without an id exits 1", async () => {
    const r = await runCLI(["detail"])
    expect(r.exitCode).toBe(1)
    expectJsonError(r.stderr, "NO_ID")
  })

  test("detail with an unparseable id exits 1", async () => {
    const r = await runCLI(["detail", "not a slug!"])
    expect(r.exitCode).toBe(1)
    expectJsonError(r.stderr, "BAD_ID")
  })

  test("unknown command exits 1", async () => {
    const r = await runCLI(["crawl"])
    expect(r.exitCode).toBe(1)
    expectJsonError(r.stderr, "BAD_CMD")
  })
})
