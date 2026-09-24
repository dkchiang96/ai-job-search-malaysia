#!/usr/bin/env bun
// Self-contained CLI for searching Hiredly Malaysia (my.hiredly.com) job listings.
// No external CLI framework and zero runtime dependencies - it runs anywhere
// `bun` is available.
//
// Personal, non-commercial use only. Hiredly's Terms and Conditions (§3.1)
// authorise viewing and downloading a single copy of its content "solely for
// your personal, non-commercial use". Keep volume low (a few pages per run),
// never republish the listings, and never point this at my-api.hiredly.com,
// which robots.txt disallows for every user agent.

import { runSearch, type SearchOpts } from "./commands/search.js"
import { runDetail, type DetailOpts } from "./commands/detail.js"
import { JOB_TYPES, STATES, normalizeState, writeError } from "./helpers.js"

interface Flags {
  _: string[]
  [k: string]: string | boolean | string[]
}

function parseFlags(argv: string[]): Flags {
  const flags: Flags = { _: [] }
  const alias: Record<string, string> = { q: "query", l: "location", n: "limit", c: "category" }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a.startsWith("--") || a.startsWith("-")) {
      const raw = a.replace(/^-+/, "")
      const [name, inline] = raw.split(/=(.*)/s)
      const key = alias[name] ?? name
      if (inline !== undefined) {
        flags[key] = inline
        continue
      }
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

const HELP = `hiredly-cli — search Hiredly Malaysia job listings (my.hiredly.com)

USAGE
  bun run src/cli.ts search [flags]
  bun run src/cli.ts detail <slug|url> [--format json|plain]

SEARCH FLAGS
  --location, -l <state>  Malaysian state, e.g. "Kuala Lumpur", selangor, penang, johor
                          (also: kl, pj, jb, melaka, overseas). Omit for all of Malaysia.
  --category, -c <slug>   Hiredly specialisation slug, optionally with a sub-specialisation:
                          supply-chain-logistics, information-technology,
                          accounting-finance/audit-taxation ... (see SKILL.md for the list).
  --query, -q <text>      Keywords. Applied CLIENT-SIDE to title, company, categories and
                          skills (Hiredly's server-side search API is robots-disallowed).
  --job-type <type>       full-time | internship.
  --jobage <days>         Only listings active within N days (client-side, from activeAt).
  --page <n>              1-indexed start page (30 listings per page). Default 1.
  --pages <n>             Consecutive pages to scan from --page, 1-5. Default 1.
  --limit, -n <n>         Cap results emitted (client-side).
  --format <fmt>          json (default) | table | plain.

EXAMPLES
  bun run src/cli.ts search -l "Kuala Lumpur" -c supply-chain-logistics --format table
  bun run src/cli.ts search -l selangor -q "operations manager" --pages 3 --jobage 14 --format table
  bun run src/cli.ts search -c information-technology -l penang --job-type full-time --format table
  bun run src/cli.ts search -c accounting-finance/audit-taxation -l kl --format table
  bun run src/cli.ts detail jobs-malaysia-acme-sdn-bhd-job-operations-executive --format plain

Personal, non-commercial use only (Hiredly Terms §3.1) — keep volume low.
`

const KNOWN_FLAGS: Record<string, Set<string>> = {
  search: new Set([
    "location", "category", "query", "job-type", "jobage", "page", "pages", "limit", "format", "help", "h",
  ]),
  detail: new Set(["format", "help", "h"]),
}

function badArg(error: string): number {
  writeError(error, "BAD_ARG")
  return 1
}

function parsePositiveInt(name: string, raw: string | boolean | string[], max?: number): number | null {
  const val = typeof raw === "string" ? Number(raw.trim()) : NaN
  if (!Number.isInteger(val) || val < 1 || (max !== undefined && val > max)) {
    writeError(
      `--${name} must be a whole number of at least 1${max !== undefined ? ` and at most ${max}` : ""}, got "${raw}"`,
      "BAD_ARG",
    )
    return null
  }
  return val
}

async function main(): Promise<number> {
  const argv = process.argv.slice(2)
  const flags = parseFlags(argv)
  const cmd = (flags._ as string[])[0]

  if (!cmd || flags.help || flags.h) {
    process.stdout.write(HELP)
    return cmd ? 0 : 1
  }

  // Reject unknown flags instead of silently discarding them: a discarded
  // filter changes what the search returns with no error. add-portal.md's
  // contract requires a bogus flag to exit 1 with a JSON error on stderr.
  const knownFlags = KNOWN_FLAGS[cmd]
  if (knownFlags) {
    for (const key of Object.keys(flags)) {
      if (key === "_" || knownFlags.has(key)) continue
      writeError(
        `unknown flag --${key} for '${cmd}' - flags are never silently ignored, because a discarded filter changes what the search returns; see --help for the supported flags`,
        "UNKNOWN_FLAG",
      )
      return 1
    }
  }

  if (cmd === "search") {
    const fmt = typeof flags.format === "string" ? flags.format : "json"
    if (!["json", "table", "plain"].includes(fmt)) return badArg(`--format must be json, table or plain, got "${fmt}"`)

    let state: string | undefined
    if (flags.location !== undefined) {
      if (typeof flags.location !== "string") return badArg("--location needs a value, e.g. -l selangor")
      const s = normalizeState(flags.location)
      if (!s) return badArg(`unknown Malaysian state "${flags.location}" - use one of: ${STATES.join(", ")}`)
      state = s
    }

    let category: string | undefined
    if (flags.category !== undefined) {
      if (typeof flags.category !== "string" || !/^[a-z0-9-]+(\/[a-z0-9-]+)?$/.test(flags.category)) {
        return badArg(`--category must be a Hiredly slug like "supply-chain-logistics" or "accounting-finance/audit-taxation", got "${flags.category}"`)
      }
      category = flags.category
    }

    let jobType: string | undefined
    if (flags["job-type"] !== undefined) {
      const jt = String(flags["job-type"])
      if (!(JOB_TYPES as readonly string[]).includes(jt)) return badArg(`--job-type must be one of: ${JOB_TYPES.join(", ")}`)
      jobType = jt
    }

    const nums: Record<string, number | undefined> = {}
    for (const [name, max] of [["jobage", undefined], ["page", undefined], ["pages", 5], ["limit", undefined]] as const) {
      if (flags[name] === undefined) continue
      const v = parsePositiveInt(name, flags[name], max)
      if (v === null) return 1
      nums[name] = v
    }

    const query = flags.query === undefined ? undefined : typeof flags.query === "string" ? flags.query : ""
    if (query === "") return badArg("--query needs a value")

    const opts: SearchOpts = {
      query,
      category,
      state,
      jobType,
      jobage: nums.jobage,
      page: nums.page ?? 1,
      pages: nums.pages ?? 1,
      limit: nums.limit,
      format: fmt as SearchOpts["format"],
    }
    return runSearch(opts)
  }

  if (cmd === "detail") {
    const id = (flags._ as string[])[1]
    if (!id) {
      writeError("detail requires a <slug|url>", "NO_ID")
      return 1
    }
    const fmt = typeof flags.format === "string" ? flags.format : "json"
    if (!["json", "plain"].includes(fmt)) return badArg(`--format must be json or plain for detail, got "${fmt}"`)
    const opts: DetailOpts = { id, format: fmt as DetailOpts["format"] }
    return runDetail(opts)
  }

  writeError(`Unknown command "${cmd}"`, "BAD_CMD")
  return 1
}

main()
  .then((code) => process.exit(code))
  .catch((e) => {
    writeError(e instanceof Error ? e.message : String(e), "INTERNAL_ERROR")
    process.exit(1)
  })
