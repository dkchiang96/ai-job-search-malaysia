import { fetchJobList, findJobDetail, idFromUrl, writeError } from "../helpers.js"

export interface DetailOpts {
  id: string
  format: "json" | "plain"
}

/** Accept a raw numeric id or a full "/job/go/<id>/" URL. */
function normalizeId(input: string): string | null {
  if (/^\d+$/.test(input)) return input
  return idFromUrl(input)
}

export async function runDetail(opts: DetailOpts): Promise<number> {
  const id = normalizeId(opts.id)
  if (!id) {
    writeError(`Could not parse a job id from "${opts.id}"`, "BAD_ID")
    return 1
  }
  try {
    // The API has no per-posting detail endpoint — the full description is
    // already inline in the list feed, so detail re-fetches that same feed
    // and returns the matching entry.
    const raw = await fetchJobList()
    const job = findJobDetail(raw, id)
    if (!job) {
      writeError("Job not found", "NOT_FOUND")
      return 1
    }

    if (opts.format === "plain") {
      const lines = [
        job.title,
        `${job.company || "—"} · ${job.location || "eligibility not stated"}`,
        "",
        job.category ? `Category: ${job.category}` : "",
        job.tags ? `Tags: ${job.tags}` : "",
        "",
        job.description || "(no description)",
        "",
        `URL: ${job.url}`,
      ].filter((l) => l !== "")
      process.stdout.write(lines.join("\n") + "\n")
    } else {
      process.stdout.write(JSON.stringify(job, null, 2) + "\n")
    }
    return 0
  } catch (e) {
    writeError(e instanceof Error ? e.message : String(e), "DETAIL_FAILED")
    return 1
  }
}
