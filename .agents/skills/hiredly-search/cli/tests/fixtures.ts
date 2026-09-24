// Synthetic fixtures shaped exactly like Hiredly's __NEXT_DATA__ payloads
// (field names and nesting observed live on 2026-09-24). Company names, titles
// and text are invented - no real listing content is reproduced here.

export function listingJob(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: "00000000-0000-0000-0000-000000000001",
    title: "Operations Executive",
    jobType: "Full-Time",
    stateRegion: "Selangor",
    location: "Petaling Jaya",
    salary: "4000 - 6000",
    expired: false,
    slug: "jobs-malaysia-contoh-logistik-sdn-bhd-job-operations-executive",
    active: true,
    externalJobUrl: "",
    activeAt: "2026-09-20T10:00:00+08:00",
    skills: [{ name: "Process Improvement" }, { name: "Excel" }],
    tracks: [{ id: "1", title: "Supply Chain & Logistics" }],
    company: { name: "Contoh Logistik Sdn Bhd" },
    minYearsExperience: 2,
    maxYearsExperience: 4,
    careerLevel: "Senior Executive",
    ...overrides,
  }
}

export function pageHtml(pageProps: Record<string, unknown>): string {
  const nextData = { props: { pageProps }, page: "/[...filter]", query: {}, buildId: "test" }
  return `<!DOCTYPE html><html><head><title>t</title></head><body><div id="__next"></div>` +
    `<script id="__NEXT_DATA__" type="application/json">${JSON.stringify(nextData)}</script></body></html>`
}

export const LIST_PAGE = pageHtml({
  jobs: [
    listingJob(),
    listingJob({
      slug: "jobs-malaysia-kedai-runcit-job-store-supervisor",
      title: "Store Supervisor (Mandarin Speaker)",
      stateRegion: "Kuala Lumpur",
      location: "Cheras",
      salary: "Undisclosed",
      activeAt: "2026-07-01T09:00:00+08:00",
      company: { name: "Kedai Runcit Enterprise" },
      tracks: [{ id: "2", title: "Retail" }],
      skills: [],
      minYearsExperience: 0,
      maxYearsExperience: 0,
    }),
    { title: "Broken record without a slug" },
    listingJob({
      slug: "jobs-malaysia-aggregated-job-regional-ops-lead",
      title: "Regional Ops Lead",
      company: null,
      aggregatedCompanyName: "Syarikat Agregat",
      externalJobUrl: "https://careers.example.invalid/ops-lead",
      location: "Kuala Lumpur",
      stateRegion: "Kuala Lumpur",
    }),
  ],
})

export const DETAIL_PAGE = pageHtml({
  id: "x",
  job: listingJob({
    description: "<p>&nbsp;<strong>About the role</strong></p><p>Run daily dispatch &amp; returns.</p><ul><li>Own SLAs</li><li>Report KPIs</li></ul>",
    requirements: "<p>Diploma or degree</p><p>Boleh berbahasa Melayu</p>",
    structuredJobData: { "@type": "JobPosting", datePosted: "2026-09-19", validThrough: "2026-10-19T00:00:00Z" },
  }),
})

export const EXPIRED_DETAIL_PAGE = pageHtml({
  id: "x",
  job: listingJob({ active: false, expired: true, description: "<p>Closed.</p>" }),
})
