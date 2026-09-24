import { describe, test, expect } from "bun:test";
import { parseJobList, findJobDetail, idFromUrl } from "../src/helpers";

describe("idFromUrl", () => {
  test("extracts the trailing numeric id from a /job/go/<id>/ url", () => {
    expect(idFromUrl("https://www.workingnomads.com/job/go/1822420/")).toBe("1822420");
  });

  test("returns null for a url with no trailing id", () => {
    expect(idFromUrl("https://www.workingnomads.com/jobs")).toBeNull();
  });
});

describe("parseJobList", () => {
  // Shape matches the real /api/exposed_jobs/ response confirmed during
  // /add-portal investigation (2026-08-30): no `id` field — the numeric id
  // lives only in the trailing segment of `url`.
  const raw = [
    {
      url: "https://www.workingnomads.com/job/go/1822420/",
      title: "Head of Operations",
      description: "<p>Great <strong>role</strong>.</p>",
      company_name: "Acme Corp",
      category_name: "Operations",
      tags: "operations,leadership",
      location: "Global",
      pub_date: "2026-08-20T00:58:54-04:00",
    },
    {
      url: "https://www.workingnomads.com/job/go/1822421/",
      title: "Frontend Engineer",
      description: "<p>Build things.</p>",
      company_name: "Beta Inc",
      category_name: "Development",
      tags: "react,frontend",
      location: "USA or Canada only",
      pub_date: "2026-08-10T00:58:54-04:00",
    },
  ];

  test("maps id (from url), title, company, url, and date", () => {
    const cards = parseJobList(raw);
    expect(cards).toHaveLength(2);
    expect(cards[0].id).toBe("1822420");
    expect(cards[0].title).toBe("Head of Operations");
    expect(cards[0].company).toBe("Acme Corp");
    expect(cards[0].date).toBe("2026-08-20");
  });

  test("keeps the free-text location field verbatim", () => {
    const cards = parseJobList(raw);
    expect(cards[0].location).toBe("Global");
    expect(cards[1].location).toBe("USA or Canada only");
  });

  test("client-side query filter matches title, category, and tags case-insensitively", () => {
    expect(parseJobList(raw, "operations")).toHaveLength(1);
    expect(parseJobList(raw, "react")).toHaveLength(1);
    expect(parseJobList(raw, "chief of staff")).toHaveLength(0);
  });

  test("skips an entry whose url carries no extractable id", () => {
    const malformed = [{ url: "https://www.workingnomads.com/jobs", title: "Broken" }];
    expect(parseJobList(malformed)).toHaveLength(0);
  });
});

describe("findJobDetail", () => {
  const raw = [
    {
      url: "https://www.workingnomads.com/job/go/1822420/",
      title: "Head of Operations",
      description: "<p>Great <strong>role</strong>.</p>",
      company_name: "Acme Corp",
      category_name: "Operations",
      tags: "operations,leadership",
      location: "Global",
      pub_date: "2026-08-20T00:58:54-04:00",
    },
  ];

  test("returns the matching entry's full detail including decoded description", () => {
    const job = findJobDetail(raw, "1822420");
    expect(job).not.toBeNull();
    expect(job!.description).toBe("Great role ."); // HTML stripped; a space remains where </strong> was, before the period
    expect(job!.category).toBe("Operations");
    expect(job!.tags).toBe("operations,leadership");
  });

  test("returns null when no entry matches the id", () => {
    expect(findJobDetail(raw, "9999999")).toBeNull();
  });
});
