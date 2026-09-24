#!/usr/bin/env python3
"""Deterministic parsers for job-alert digest emails (plain-text bodies).

Ports the block-anchor recipes documented in
.claude/skills/job-scraper/email-alert-portals.md into code, so extraction is a
script call, not the model re-deriving the same parse from a raw email body on
every run. If a portal redesigns its alert email, fix the parser here and the
anchor description in that doc together.

Validation status: the JobStreet and LinkedIn parsers were built against real
Malaysian alert digests (JobStreet: 8 digests on 2026-08-22, re-checked against
14 more on 2026-09-10; LinkedIn: 5 digests on 2026-08-22). The Indeed parser was
built against 6 real digests on 2026-08-22 and has **not been maintained** since
(see email-alert-portals.md). The unit tests use synthetic text shaped like
those samples, so they prove the parsing logic, not that a portal's layout is
unchanged. Check a fresh sample any time with
`python3 tools/gmail_imap_fetch.py test --portal <p> --file <saved.txt>`.
"""

from __future__ import annotations

import re


_JOBSTREET_FOOTER_RE = re.compile(
    r"^(View all matching jobs|Download Jobstreet App|Edit this alert|Unsubscribe from this alert)$",
    re.IGNORECASE,
)
_JOBSTREET_PROMO_CTA_RE = re.compile(r"^Take your next career step$", re.IGNORECASE)
_JOBSTREET_MISSED_HEADING_RE = re.compile(r"^Jobs you may have missed$", re.IGNORECASE)


def _strip_jobstreet_chrome(lines: list[str]) -> list[str]:
    """Drop the "Take your next career step" promo block and the footer
    (app-download badges, edit/unsubscribe-alert links, legal boilerplate) -
    none of it is a listing, but left in place it desyncs the resync loop
    into treating promo/footer copy as fake title/company/location fields
    (confirmed against a real digest 2026-09-10: "Your destination for
    personalised advice..." got parsed as a bogus listing). The promo block
    sits between the primary listings and an optional "Jobs you may have
    missed" section - jump past it to that heading rather than truncating,
    since email-alert-portals.md documents that section as real content to
    keep. If the heading never appears, the promo block truly is the end of
    content and everything from it onward is dropped."""
    n = len(lines)
    out = []
    i = 0
    while i < n:
        line = lines[i]
        if _JOBSTREET_FOOTER_RE.match(line):
            break
        if _JOBSTREET_PROMO_CTA_RE.match(line):
            missed_idx = next(
                (k for k in range(i + 1, n) if _JOBSTREET_MISSED_HEADING_RE.match(lines[k])), None
            )
            if missed_idx is None:
                break
            i = missed_idx
            continue
        if _JOBSTREET_MISSED_HEADING_RE.match(line):
            i += 1
            if i < n and lines[i] != "":
                i += 1  # its "Matches your preference..." subheading line
            continue
        out.append(line)
        i += 1
    return out


def parse_jobstreet(body: str) -> list[dict]:
    """Line-based, not blank-line-block-based: a blank line appears BOTH
    between company and location (within one listing) AND between listings,
    so naive blank-line splitting cannot tell them apart. Walk lines in a
    fixed sequence instead: [logo]? title / company / (blank) / [Posted on
    <date> or badge, (blank)]? / location / [salary]? / (blank)? / tracking
    link.

    Confirmed against real mailbox digests 2026-09-10: both the badge line
    and the "Posted on <date>" line (the "Jobs you may have missed" section's
    per-listing date) sit AFTER the company/location blank, not before it as
    an earlier version of this parser assumed - and a blank often separates
    the last field from the tracking link too. Every attempt to open a
    listing at a given line is self-resyncing: on failure (no URL found), it
    advances by exactly one line and retries from there, rather than
    aborting the whole block - this is what lets it skip the free-form
    greeting preamble ("Hi <name>, based on your saved search...") that
    precedes the first real listing without needing to pattern-match that
    boilerplate text directly."""
    raw_lines = [ln.strip() for ln in body.splitlines()]
    # collapse repeated blank lines to single markers, drop leading/trailing blanks
    lines = []
    for ln in raw_lines:
        if ln == "" and (not lines or lines[-1] == ""):
            continue
        lines.append(ln)
    while lines and lines[0] == "":
        lines.pop(0)
    while lines and lines[-1] == "":
        lines.pop()
    lines = _strip_jobstreet_chrome(lines)

    n = len(lines)
    listings = []
    i = 0
    while i < n:
        if lines[i] == "":
            i += 1
            continue
        if re.match(r"^logo\b", lines[i], re.IGNORECASE):
            i += 1
            # the logo's own tracking link immediately follows - discard it too
            if i < n and (lines[i].startswith("[") or re.match(r"^https?://", lines[i])):
                i += 1
            continue

        j = i
        title = lines[j]
        j += 1
        if j >= n or lines[j] == "":
            i += 1  # no adjacent company line - not a real listing start, resync
            continue
        company = lines[j]
        j += 1

        if j < n and lines[j] == "":
            j += 1  # the company/location separator blank

        if j < n and lines[j] != "" and (
            re.search(r"strong applicant", lines[j], re.IGNORECASE) or re.match(r"^Posted on\b", lines[j], re.IGNORECASE)
        ):
            j += 1  # skip badge or "Posted on <date>" decoration
            if j < n and lines[j] == "":
                j += 1  # blank after the decoration line, if present

        location = lines[j] if j < n else None
        j += 1

        salary = None
        if j < n and (re.search(r"\bRM\s?[\d,.]+", lines[j]) or re.search(r"per month", lines[j], re.IGNORECASE)):
            salary = lines[j]
            j += 1

        if j < n and lines[j] == "":
            j += 1  # blank before the tracking link

        url = None
        if j < n:
            ln = lines[j]
            if ln.startswith("[") and ln.endswith("]"):
                url = ln[1:-1].strip()
                j += 1
            elif re.match(r"^https?://", ln):
                url = ln
                j += 1

        # a stray "logo" line landing in a field (not caught by the top-of-loop
        # skip, e.g. when the greeting preamble's wrapped sentence lines get
        # mistaken for title/company) means this attempt latched onto noise,
        # not a real listing - reject it even though title/company/url all matched
        if title and company and url and not any(
            v and re.match(r"^logo\b", v, re.IGNORECASE) for v in (title, company, location)
        ):
            listings.append({"title": title, "company": company, "location": location, "salary": salary, "url": url})
            i = j
            if i < n and lines[i] == "":
                i += 1  # consume the blank separator before the next listing
        else:
            i += 1  # not a real listing block - resync by one line and retry
    return listings


_INDEED_DATE_RE = re.compile(r"^(Just posted|\d+\+?\s*day(s)?\s*ago|Today|Active\s+\d+\+?\s*day(s)?\s*ago)$", re.IGNORECASE)
_INDEED_APPLY_URL_RE = re.compile(r"^https?://\S*indeed\.com/(rc/clk|pagead/clk)\S*")


_INDEED_HEADER_RE = re.compile(r"^Jobs \d+-\d+ of \d+|^See matching results on Indeed", re.IGNORECASE)


def parse_indeed(body: str) -> list[dict]:
    """No blank-line separators. Per listing: title / "company - location" /
    [salary]? / [Easily apply]? / description snippet / relative-date / apply
    link - the apply link trails its OWN listing's date line, immediately
    before the next listing's title starts, so it must be consumed before the
    next accumulation window begins rather than folded into either block."""
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    lines = [ln for ln in lines if not _INDEED_HEADER_RE.match(ln)]

    listings = []
    i, n = 0, len(lines)
    while i < n:
        title = lines[i]
        i += 1
        if i >= n:
            break
        company_location = lines[i]
        i += 1
        company, _, location = company_location.rpartition(" - ")

        body_lines = []
        while i < n and not _INDEED_DATE_RE.match(lines[i]):
            body_lines.append(lines[i])
            i += 1
        if i >= n:
            break  # no date terminator found - malformed tail, stop rather than guess
        i += 1  # consume the date line itself

        url = None
        if i < n and _INDEED_APPLY_URL_RE.match(lines[i]):
            url = lines[i]
            i += 1

        body_lines = [ln for ln in body_lines if not re.match(r"^easily apply$", ln, re.IGNORECASE)]
        salary = next((ln for ln in body_lines if re.search(r"\b(RM|MYR|\$)\s?[\d,]+", ln)), None)

        if title and company:
            listings.append({"title": title, "company": company or None, "location": location or None,
                              "salary": salary, "url": url})
    return listings


_LINKEDIN_RULE_RE = re.compile(r"^-{3,}$")
# Per-viewer decoration lines between a listing's fields and its `View job:`
# link. Anchored whole-line shapes only, so a real title that merely contains
# one of these words ("Alumni Relations Manager") is never dropped.
_LINKEDIN_DECORATION_RE = re.compile(
    r"^(\d+\+?\s+(connections?|school alumni|alumni|applicants?)\b.*"
    r"|this company is actively (hiring|recruiting)"
    r"|actively (hiring|recruiting)"
    r"|fast growing"
    r"|be an early applicant"
    r"|easy apply"
    r"|promoted)$",
    re.IGNORECASE,
)
_LINKEDIN_VIEW_JOB_RE = re.compile(r"^View job:\s*(\S+)")


def parse_linkedin(body: str) -> list[dict]:
    """Blocks separated by a `---` rule line: title / company / location /
    [decoration lines]* / `View job: <url>`.

    The three fields are the three non-decoration lines immediately *before*
    `View job:`, not the first three lines of the block: the first block of a
    digest also carries the email's own header ("Your job alert for ...",
    "N new jobs match your preferences."), which a first-three-lines read
    mistakes for a listing's title and company."""
    blocks: list[list[str]] = [[]]
    for raw in body.splitlines():
        ln = raw.strip()
        if _LINKEDIN_RULE_RE.match(ln):
            blocks.append([])
            continue
        if ln:
            blocks[-1].append(ln)

    listings = []
    for block in blocks:
        lines = [ln for ln in block if not _LINKEDIN_DECORATION_RE.search(ln)]
        view_job_idx = next((i for i, ln in enumerate(lines) if _LINKEDIN_VIEW_JOB_RE.match(ln)), None)
        if view_job_idx is None or view_job_idx < 3:
            continue
        title, company, location = lines[view_job_idx - 3:view_job_idx]
        m = _LINKEDIN_VIEW_JOB_RE.match(lines[view_job_idx])
        url = m.group(1) if m else None
        url = normalize_linkedin_url(url)
        if title and company and url:
            listings.append({"title": title, "company": company, "location": location, "salary": None, "url": url})
    return listings


_LINKEDIN_ID_RE = re.compile(r"/jobs/view/(\d{6,})")


def normalize_linkedin_url(url: str | None) -> str | None:
    """Per email-alert-portals.md's hard rule: always store the CLI-style
    my.linkedin.com/jobs/view/<id> form - the comm/jobs/view form requires an
    authenticated session and fails a stateless fetch on every URL tested."""
    if not url:
        return url
    m = _LINKEDIN_ID_RE.search(url)
    if m:
        return f"https://my.linkedin.com/jobs/view/{m.group(1)}"
    return url


PARSERS = {
    "jobstreet": parse_jobstreet,
    "indeed": parse_indeed,
    "linkedin": parse_linkedin,
}


# Saved-search / alert name, taken from the digest's Subject line. Recording it
# per listing is what lets `tools/job_store.py yield` show which saved search
# earns its slot - JobStreet caps a jobseeker at 10 saved-search alerts.
_SUBJECT_ALERT_PATTERNS = {
    "jobstreet": [
        re.compile(r"^\s*\d+\+?\s+new jobs? for (?P<name>.+?)\s*$", re.IGNORECASE),
    ],
    "indeed": [
        re.compile(r"^\s*(?P<name>.+?)\s*:\s*.+?\s+and\s+\d+\s+more new jobs", re.IGNORECASE),
    ],
    "linkedin": [
        re.compile(r"^\s*Your job alert for (?P<name>.+?)\s*$", re.IGNORECASE),
    ],
}


def alert_name_from_subject(portal: str, subject: str | None) -> str | None:
    """Return the saved-search name a digest was sent for, or None when the
    subject does not follow a known saved-search pattern (recommendation
    digests, per-posting alerts)."""
    if not subject:
        return None
    for pattern in _SUBJECT_ALERT_PATTERNS.get(portal, []):
        m = pattern.match(subject)
        if m:
            return m.group("name").strip().strip('"')
    return None
