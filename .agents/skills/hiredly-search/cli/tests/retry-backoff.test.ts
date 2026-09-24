import { afterEach, describe, expect, test } from "bun:test"
import { htmlFetch } from "../src/helpers"

// The portal contract requires backoff on 429/5xx. A stubbed fetch counts
// attempts and a stubbed setTimeout fires immediately, so this runs offline
// and does not sleep through the real 500ms -> 8s schedule.

const originalFetch = globalThis.fetch
const originalSetTimeout = globalThis.setTimeout

afterEach(() => {
  globalThis.fetch = originalFetch
  globalThis.setTimeout = originalSetTimeout
})

function instantTimers() {
  globalThis.setTimeout = ((fn: () => void) => originalSetTimeout(fn, 0)) as unknown as typeof setTimeout
}

function stubFetch(responses: Array<() => Response>): { calls: number; ua: string[] } {
  const state = { calls: 0, ua: [] as string[] }
  globalThis.fetch = (async (_url: string, init?: RequestInit) => {
    state.ua.push(String((init?.headers as Record<string, string>)?.["User-Agent"] ?? ""))
    const i = Math.min(state.calls, responses.length - 1)
    state.calls++
    return responses[i]()
  }) as unknown as typeof fetch
  return state
}

describe("htmlFetch", () => {
  test("retries a 429 and succeeds on the next attempt", async () => {
    instantTimers()
    const state = stubFetch([() => new Response("", { status: 429 }), () => new Response("<html>ok</html>")])
    expect(await htmlFetch("https://my.hiredly.com/x")).toContain("ok")
    expect(state.calls).toBe(2)
  })

  test("retries a 503", async () => {
    instantTimers()
    const state = stubFetch([() => new Response("", { status: 503 }), () => new Response("ok")])
    expect(await htmlFetch("https://my.hiredly.com/x")).toBe("ok")
    expect(state.calls).toBe(2)
  })

  test("gives up after the retry budget", async () => {
    instantTimers()
    const state = stubFetch([() => new Response("", { status: 500 })])
    await expect(htmlFetch("https://my.hiredly.com/x")).rejects.toThrow(/500/)
    expect(state.calls).toBe(7)
  })

  test("returns empty string on 404 without retrying", async () => {
    const state = stubFetch([() => new Response("", { status: 404 })])
    expect(await htmlFetch("https://my.hiredly.com/x")).toBe("")
    expect(state.calls).toBe(1)
  })

  test("identifies itself honestly", async () => {
    const state = stubFetch([() => new Response("ok")])
    await htmlFetch("https://my.hiredly.com/x")
    expect(state.ua[0]).toBe("Mozilla/5.0 (compatible; hiredly-search-cli/1.0)")
  })
})
