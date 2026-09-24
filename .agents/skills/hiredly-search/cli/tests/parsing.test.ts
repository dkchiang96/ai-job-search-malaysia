import { describe, expect, test } from "bun:test"
import {
  buildListUrl,
  formatSalary,
  htmlToText,
  matchesQuery,
  normalizeId,
  normalizeState,
  parseJobDetail,
  parseListPage,
  withinJobage,
} from "../src/helpers"
import { DETAIL_PAGE, EXPIRED_DETAIL_PAGE, LIST_PAGE } from "./fixtures"

describe("parseListPage", () => {
  const cards = parseListPage(LIST_PAGE)

  test("skips a malformed record without failing the page", () => {
    expect(cards.map((c) => c.id)).toEqual([
      "jobs-malaysia-contoh-logistik-sdn-bhd-job-operations-executive",
      "jobs-malaysia-kedai-runcit-job-store-supervisor",
      "jobs-malaysia-aggregated-job-regional-ops-lead",
    ])
  })

  test("emits every contract field, null when missing", () => {
    for (const c of cards) {
      for (const key of ["id", "title", "company", "location", "date", "url"]) expect(key in c).toBe(true)
    }
    expect(cards[0].url).toBe("https://my.hiredly.com/jobs/jobs-malaysia-contoh-logistik-sdn-bhd-job-operations-executive")
    expect(cards[0].date).toBe("2026-09-20")
  })

  test("formats location as city, state without duplicating the state", () => {
    expect(cards[0].location).toBe("Petaling Jaya, Selangor")
    expect(cards[2].location).toBe("Kuala Lumpur")
  })

  test("salary: monthly MYR range, null when undisclosed", () => {
    expect(cards[0].salary).toBe("RM 4,000 - RM 6,000 / month")
    expect(cards[1].salary).toBeNull()
  })

  test("experience wording", () => {
    expect(cards[0].experience).toBe("2-4 years")
    expect(cards[1].experience).toBe("no experience required")
  })

  test("falls back to aggregatedCompanyName and surfaces externalUrl", () => {
    expect(cards[2].company).toBe("Syarikat Agregat")
    expect(cards[2].externalUrl).toBe("https://careers.example.invalid/ops-lead")
  })

  test("a page without __NEXT_DATA__ throws a clear error", () => {
    expect(() => parseListPage("<html>maintenance</html>")).toThrow(/__NEXT_DATA__/)
  })
})

describe("parseJobDetail", () => {
  test("converts description HTML to readable text", () => {
    const job = parseJobDetail(DETAIL_PAGE)
    expect(job.description).toBe("About the role\nRun daily dispatch & returns.\n\n- Own SLAs\n- Report KPIs")
    expect(job.requirements).toContain("Boleh berbahasa Melayu")
    expect(job.datePosted).toBe("2026-09-19")
    expect(job.validThrough).toBe("2026-10-19")
    expect(job.isActive).toBe(true)
  })

  test("an expired job is reported inactive, not dropped", () => {
    expect(parseJobDetail(EXPIRED_DETAIL_PAGE).isActive).toBe(false)
  })
})

describe("filters", () => {
  const [ops, store] = parseListPage(LIST_PAGE)

  test("query terms must all match title/company/categories/skills", () => {
    expect(matchesQuery(ops, "operations")).toBe(true)
    expect(matchesQuery(ops, "operations excel")).toBe(true)
    expect(matchesQuery(ops, "operations finance")).toBe(false)
    expect(matchesQuery(store, '"mandarin speaker"')).toBe(true)
    expect(matchesQuery(store, undefined)).toBe(true)
  })

  test("jobage keeps recent and undated listings", () => {
    const today = new Date("2026-09-24T00:00:00Z")
    expect(withinJobage(ops, 14, today)).toBe(true)
    expect(withinJobage(store, 14, today)).toBe(false)
    expect(withinJobage({ ...store, date: null }, 14, today)).toBe(true)
  })
})

describe("URL and argument helpers", () => {
  test("buildListUrl mirrors Hiredly's sitemap path shapes", () => {
    expect(buildListUrl({ page: 1 })).toBe("https://my.hiredly.com/jobs")
    expect(buildListUrl({ state: "selangor", page: 2 })).toBe("https://my.hiredly.com/jobs-in-selangor?page=2")
    expect(buildListUrl({ category: "supply-chain-logistics", state: "kuala-lumpur", page: 1 })).toBe(
      "https://my.hiredly.com/jobs-in-supply-chain-logistics/in-kuala-lumpur",
    )
    expect(
      buildListUrl({ category: "accounting-finance/audit-taxation", state: "penang", jobType: "full-time", page: 1 }),
    ).toBe("https://my.hiredly.com/jobs-in-accounting-finance/audit-taxation/in-penang/full-time")
    expect(buildListUrl({ state: "johor", jobType: "internship", page: 1 })).toBe(
      "https://my.hiredly.com/jobs-in-johor/internship",
    )
  })

  test("normalizeState accepts names, slugs and common abbreviations", () => {
    expect(normalizeState("Kuala Lumpur")).toBe("kuala-lumpur")
    expect(normalizeState("KL")).toBe("kuala-lumpur")
    expect(normalizeState("PJ")).toBe("selangor")
    expect(normalizeState("Melaka")).toBe("malacca")
    expect(normalizeState("negeri_sembilan")).toBe("negeri-sembilan")
    expect(normalizeState("Atlantis")).toBeNull()
  })

  test("normalizeId accepts a slug or a job URL", () => {
    expect(normalizeId("jobs-malaysia-x-job-y")).toBe("jobs-malaysia-x-job-y")
    expect(normalizeId("https://my.hiredly.com/jobs/jobs-malaysia-x-job-y?ref=abc")).toBe("jobs-malaysia-x-job-y")
    expect(normalizeId("not a slug!")).toBeNull()
  })

  test("formatSalary handles commas, single figures and free text", () => {
    expect(formatSalary("3,500 - 4,500")).toBe("RM 3,500 - RM 4,500 / month")
    expect(formatSalary("5000")).toBe("RM 5,000 / month")
    expect(formatSalary("Negotiable")).toBeNull()
    expect(formatSalary(null)).toBeNull()
  })

  test("htmlToText decodes entities and returns null for empty input", () => {
    expect(htmlToText("<p>A &amp; B&#39;s</p>")).toBe("A & B's")
    expect(htmlToText("")).toBeNull()
  })
})
