import { describe, test, expect } from "bun:test";
import { parseJobList, parseJobDetail, buildListUrl, KNOWN_TAGS } from "../src/helpers";

describe("parseJobList", () => {
  // Shape matches the real /api response confirmed during /add-portal investigation
  // (2026-08-30): element 0 is the API's ToS notice (no `id` field), remaining
  // elements are job objects.
  const raw = [
    { legal: "API Terms of Service: ..." },
    {
      id: "1132182",
      slug: "acme-head-of-operations-1132182",
      position: "Head of Operations",
      company: "Acme Corp",
      location: "Remote",
      date: "2026-08-20T19:02:21+00:00",
      tags: ["operations", "exec"],
      url: "https://remoteok.com/remote-jobs/acme-head-of-operations-1132182",
    },
    {
      id: "1132183",
      position: "Frontend Engineer",
      company: "Beta Inc",
      location: "United States, ",
      date: "2026-08-10T19:02:21+00:00",
      tags: ["dev", "engineer"],
      url: "https://remoteok.com/remote-jobs/beta-frontend-engineer-1132183",
    },
  ];

  test("skips the ToS notice object", () => {
    const cards = parseJobList(raw);
    expect(cards).toHaveLength(2);
  });

  test("maps id, title, company, url, and date", () => {
    const cards = parseJobList(raw);
    expect(cards[0].id).toBe("1132182");
    expect(cards[0].title).toBe("Head of Operations");
    expect(cards[0].company).toBe("Acme Corp");
    expect(cards[0].date).toBe("2026-08-20");
    expect(cards[0].url).toBe("https://remoteok.com/remote-jobs/acme-head-of-operations-1132182");
  });

  test("trims trailing comma noise from location, keeps bare Remote as-is", () => {
    const cards = parseJobList(raw);
    expect(cards[0].location).toBe("Remote");
    expect(cards[1].location).toBe("United States");
  });

  test("client-side query filter matches title case-insensitively", () => {
    const cards = parseJobList(raw, "operations");
    expect(cards).toHaveLength(1);
    expect(cards[0].id).toBe("1132182");
  });

  test("query with no match returns an empty array, not an error", () => {
    const cards = parseJobList(raw, "chief of staff");
    expect(cards).toHaveLength(0);
  });

  test("applyClientFilter: false trusts server-side tag filtering as-is, no substring re-check", () => {
    // A listing tagged "operations" but titled something that doesn't contain
    // the literal word — would be dropped by the client-side substring check,
    // but must survive when the caller says the feed already came from the
    // tags= endpoint.
    const tagFiltered = [
      { legal: "..." },
      { id: "9", position: "COO", company: "Gamma LLC", location: "Remote", date: "2026-08-01T00:00:00+00:00", tags: ["operations"], url: "https://remoteok.com/remote-jobs/gamma-coo-9" },
    ];
    const cards = parseJobList(tagFiltered, "operations", false);
    expect(cards).toHaveLength(1);
    expect(cards[0].title).toBe("COO");
  });
});

describe("buildListUrl / KNOWN_TAGS", () => {
  test("routes an exact known-tag query to the tags= endpoint", () => {
    expect(KNOWN_TAGS.has("operations")).toBe(true);
    expect(buildListUrl("operations")).toBe("https://remoteok.com/api?tags=operations");
  });

  test("routes a multi-word known tag with an encoded space", () => {
    expect(buildListUrl("project manager")).toBe("https://remoteok.com/api?tags=project%20manager");
  });

  test("routes an unrecognized query to the unfiltered feed", () => {
    expect(buildListUrl("chief of staff")).toBe("https://remoteok.com/api");
  });

  test("routes an undefined query to the unfiltered feed", () => {
    expect(buildListUrl(undefined)).toBe("https://remoteok.com/api");
  });
});

describe("parseJobDetail", () => {
  test("extracts fields from the schema.org JobPosting JSON-LD block", () => {
    const ld = {
      "@type": "JobPosting",
      title: "Head of Operations",
      description: "Great role.",
      datePosted: "2026-08-20T19:02:21+00:00",
      validThrough: "2026-09-20T19:02:21+00:00",
      employmentType: "FULL_TIME",
      hiringOrganization: { name: "Acme Corp", url: "https://acme.example" },
      applicantLocationRequirements: [{ "@type": "Country", name: "United States" }],
    };
    const html = `<script type="application/ld+json"> ${JSON.stringify(ld)} </script>`;
    const job = parseJobDetail(html, "1132182");

    expect(job.title).toBe("Head of Operations");
    expect(job.company).toBe("Acme Corp");
    expect(job.applicantLocationRequirement).toBe("United States");
    expect(job.location).toBe("United States");
    expect(job.deadline).toBe("2026-09-20");
  });

  test("'Anywhere' applicantLocationRequirements means explicitly unrestricted", () => {
    const ld = {
      "@type": "JobPosting",
      title: "Ops Manager",
      hiringOrganization: { name: "Beta Inc" },
      applicantLocationRequirements: [{ "@type": "Country", name: "Anywhere" }],
    };
    const html = `<script type="application/ld+json"> ${JSON.stringify(ld)} </script>`;
    const job = parseJobDetail(html, "1132183");
    expect(job.applicantLocationRequirement).toBe("Anywhere");
  });

  test("malformed JSON-LD does not throw", () => {
    const html = `<script type="application/ld+json"> not json </script>`;
    const job = parseJobDetail(html, "1132184");
    expect(job.title).toBe("(untitled)");
  });
});
