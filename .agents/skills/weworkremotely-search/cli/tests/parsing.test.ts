import { describe, test, expect } from "bun:test";
import { parseJobCards, parseJobDetail, relativeToISODate } from "../src/helpers";

describe("relativeToISODate", () => {
  test("parses days", () => {
    const iso = relativeToISODate("3d");
    const expected = new Date(Date.now() - 3 * 86_400_000).toISOString().slice(0, 10);
    expect(iso).toBe(expected);
  });

  test("parses Today", () => {
    expect(relativeToISODate("Today")).toBe(new Date().toISOString().slice(0, 10));
  });

  test("returns null for unrecognized text", () => {
    expect(relativeToISODate("recently")).toBeNull();
  });
});

describe("parseJobCards", () => {
  // Shape matches the real search page confirmed during /add-portal investigation
  // (2026-08-30): one <li> per posting, anchored by a listing-link <a>, containing
  // title/date/company/categories blocks in this order.
  const html = `
    <a class="new-header__post-job-cta" href="/remote-jobs/find-your-plan">Post a job</a>
    <li class=" new-listing-container "><a class="listing-link--unlocked" href="/remote-jobs/acme-head-of-operations"><div class=" new-listing "><div class="new-listing__header"><h3 class="new-listing__header__title"><span class="new-listing__header__title__text">Head of Operations</span></h3><div class="new-listing__header__icons"><p class="new-listing__header__icons__date"> 5d </p></div></div><p class="new-listing__company-name"> Acme Corp </p><p class="new-listing__company-headquarters"> Remote </p><div class="new-listing__categories"><p class="new-listing__categories__category"> Full-Time </p><p class="new-listing__categories__category"> Anywhere in the World </p></div></div></a></li>
    <li class=" new-listing-container "><a class="listing-link--unlocked" href="/remote-jobs/beta-ops-manager"><div class=" new-listing "><div class="new-listing__header"><h3 class="new-listing__header__title"><span class="new-listing__header__title__text">Ops Manager</span></h3><div class="new-listing__header__icons"><p class="new-listing__header__icons__date"> 12d </p></div></div><p class="new-listing__company-name"> Beta Inc </p><p class="new-listing__company-headquarters"> Austin, TX, USA </p><div class="new-listing__categories"><p class="new-listing__categories__category"> Full-Time </p><p class="new-listing__categories__category"> $50,000 - $74,999 USD </p><p class="new-listing__categories__category"> 🇺🇸 United States of America </p></div></div></a></li>
  `;

  test("extracts real job listings and skips the promotional CTA anchor", () => {
    const cards = parseJobCards(html);
    expect(cards).toHaveLength(2);
  });

  test("parses title, company, id, url, and date", () => {
    const cards = parseJobCards(html);
    expect(cards[0].id).toBe("acme-head-of-operations");
    expect(cards[0].title).toBe("Head of Operations");
    expect(cards[0].company).toBe("Acme Corp");
    expect(cards[0].url).toBe("https://weworkremotely.com/remote-jobs/acme-head-of-operations");
    expect(cards[0].date).toBe(new Date(Date.now() - 5 * 86_400_000).toISOString().slice(0, 10));
  });

  test("picks the region chip, not the salary or employment-type chip, as location", () => {
    const cards = parseJobCards(html);
    expect(cards[0].location).toBe("Anywhere in the World");
    expect(cards[1].location).toBe("🇺🇸 United States of America");
  });
});

describe("parseJobDetail", () => {
  test("extracts fields from the schema.org JobPosting JSON-LD block", () => {
    const ld = {
      "@context": "http://schema.org/",
      "@type": "JobPosting",
      title: "Head of Operations",
      description: "&lt;p&gt;Great role.&lt;/p&gt;",
      datePosted: "2026-08-04 20:13:58 UTC",
      validThrough: "2026-09-03 20:13:58 UTC",
      employmentType: "Full-Time",
      hiringOrganization: { name: "Acme Corp", sameAs: "https://acme.example" },
      applicantLocationRequirements: [{ "@type": "Country", name: "US" }],
    };
    const html = `<script type="application/ld+json"> ${JSON.stringify(ld)} </script>`;
    const job = parseJobDetail(html, "acme-head-of-operations");

    expect(job.title).toBe("Head of Operations");
    expect(job.company).toBe("Acme Corp");
    expect(job.applicantLocationRequirement).toBe("US");
    expect(job.location).toBe("US");
    expect(job.deadline).toBe("2026-09-03");
    expect(job.description).toContain("Great role.");
  });

  test("location is null when applicantLocationRequirements is absent (multi-region or unrestricted posting)", () => {
    const ld = { "@type": "JobPosting", title: "Deal Ops Manager", hiringOrganization: { name: "Storyblok" } };
    const html = `<script type="application/ld+json"> ${JSON.stringify(ld)} </script>`;
    const job = parseJobDetail(html, "storyblok-deal-ops-manager");
    expect(job.applicantLocationRequirement).toBeNull();
    expect(job.location).toBeNull();
  });

  test("malformed JSON-LD does not throw", () => {
    const html = `<script type="application/ld+json"> not json </script>`;
    const job = parseJobDetail(html, "some-slug");
    expect(job.title).toBe("(untitled)");
  });
});
