#!/usr/bin/env bun
// Self-contained CLI for searching remote jobs on Remote OK's public JSON API.
// No external CLI framework, so it runs anywhere `bun` is available with zero
// install beyond the repo clone.
//
// Remote OK is a remote-only board, but "remote" here can still mean
// "remote, but only if you're in the US". Each result's `location` field
// carries the portal's own per-posting location/eligibility string (e.g.
// "United States, ", or the literal "Remote" for postings confirmed
// unrestricted) instead of a flattened generic "Remote" label.

import { runSearch, type SearchOpts } from "./commands/search.js"
import { runDetail, type DetailOpts } from "./commands/detail.js"

interface Flags {
  _: string[]
  [k: string]: string | boolean | string[]
}

function parseFlags(argv: string[]): Flags {
  const flags: Flags = { _: [] }
  const alias: Record<string, string> = { q: "query", n: "limit" }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a.startsWith("--") || a.startsWith("-")) {
      const key = alias[a.replace(/^-+/, "")] ?? a.replace(/^-+/, "")
      const next = argv[i + 1]
      if (next === undefined || next.startsWith("-")) {
        flags[key] = true
      } else {
        flags[key] = next
        i++
      }
    } else {
      ;(flags._ as string[]).push(a)
    }
  }
  return flags
}

const HELP = `remoteok-cli — search remote jobs on Remote OK (global)

USAGE
  bun run src/cli.ts search [flags]
  bun run src/cli.ts detail <id|url> [--format json|plain]

SEARCH FLAGS
  --query, -q <text>      Keywords. An exact match against Remote OK's own tag
                          taxonomy (e.g. "operations", "director", "project manager")
                          is routed to its tags= endpoint for full recall; anything
                          else falls back to a client-side match over the ~100
                          most-recently-posted listings site-wide (Remote OK's public
                          API has no true free-text search, and that feed has no
                          deeper history) — a niche query may legitimately return
                          nothing if nothing current matches.
  --jobage <days>         Posted within N days. Default: all. Uses the API's own
                          ISO date field (day granularity).
  --page <n>              1-indexed page, 20 results/page. Client-side, over the feed above.
  --limit, -n <n>         Cap results emitted (client-side), applied after --page.
  --format <fmt>          json (default) | table | plain.

  There is no --location flag: every listing on this board is remote, so
  location isn't a search filter here. Each result's "location" field instead
  carries Remote OK's own per-posting location/eligibility string for that
  specific posting (e.g. "United States, ", or the literal "Remote" for a
  posting confirmed unrestricted) — check it before treating a result as open
  to a candidate outside that location.

EXAMPLES
  bun run src/cli.ts search -q "operations" --format table
  bun run src/cli.ts search -q "director" --jobage 14 --format table
  bun run src/cli.ts search -q "automation" --limit 10 --format json
  bun run src/cli.ts detail 1132182 --format plain

Data source: Remote OK's public API (https://remoteok.com/api) and detail pages. No authentication required.
`

const KNOWN_FLAGS: Record<string, Set<string>> = {
  search: new Set(["query", "jobage", "page", "limit", "format", "help", "h"]),
  detail: new Set(["format", "help", "h"]),
}

async function main(): Promise<number> {
  const argv = process.argv.slice(2)
  const flags = parseFlags(argv)
  const cmd = (flags._ as string[])[0]

  if (!cmd || flags.help || flags.h) {
    process.stdout.write(HELP)
    return cmd ? 0 : 1
  }

  const knownFlags = KNOWN_FLAGS[cmd]
  if (knownFlags) {
    for (const key of Object.keys(flags)) {
      if (key === "_" || knownFlags.has(key)) continue
      process.stderr.write(
        JSON.stringify({
          error: `unknown flag --${key} for '${cmd}' - flags are never silently ignored, because a discarded filter changes what the search returns; see --help for the supported flags`,
          code: "UNKNOWN_FLAG",
        }) + "\n",
      )
      return 1
    }
  }

  if (cmd === "search") {
    const fmt = (flags.format as string) || "json"

    const parseIntFlag = (name: string, raw: string | boolean | string[]): number | null => {
      const val = parseInt(raw as string, 10)
      if (isNaN(val)) {
        process.stderr.write(JSON.stringify({ error: `--${name} must be a number, got "${raw}"`, code: "BAD_ARG" }) + "\n")
        return null
      }
      return val
    }

    if (flags.jobage !== undefined) {
      const v = parseIntFlag("jobage", flags.jobage)
      if (v === null) return 1
      flags.jobage = String(v)
    }
    if (flags.page !== undefined) {
      const v = parseIntFlag("page", flags.page)
      if (v === null) return 1
      flags.page = String(v)
    }
    if (flags.limit !== undefined) {
      const v = parseIntFlag("limit", flags.limit)
      if (v === null) return 1
      flags.limit = String(v)
    }

    const opts: SearchOpts = {
      query: typeof flags.query === "string" ? flags.query : undefined,
      jobage: flags.jobage ? parseInt(flags.jobage as string, 10) : 9999,
      page: flags.page ? Math.max(1, parseInt(flags.page as string, 10)) : 1,
      limit: flags.limit ? parseInt(flags.limit as string, 10) : undefined,
      format: (["json", "table", "plain"].includes(fmt) ? fmt : "json") as SearchOpts["format"],
    }
    return runSearch(opts)
  }

  if (cmd === "detail") {
    const id = (flags._ as string[])[1]
    if (!id) {
      process.stderr.write(JSON.stringify({ error: "detail requires an <id|url>", code: "NO_ID" }) + "\n")
      return 1
    }
    const fmt = (flags.format as string) || "json"
    const opts: DetailOpts = {
      id,
      format: (fmt === "plain" ? "plain" : "json") as DetailOpts["format"],
    }
    return runDetail(opts)
  }

  process.stderr.write(JSON.stringify({ error: `Unknown command "${cmd}"`, code: "BAD_CMD" }) + "\n")
  return 1
}

main()
  .then((code) => process.exit(code))
  .catch((e) => {
    process.stderr.write(
      JSON.stringify({
        error: e instanceof Error ? e.message : String(e),
        code: "INTERNAL_ERROR",
      }) + "\n",
    )
    process.exit(1)
  })
