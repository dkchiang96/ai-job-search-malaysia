#!/usr/bin/env python3
"""Deterministic parsers for job-alert digest emails (plain-text bodies).

Ports the block-anchor recipes documented in
.claude/skills/job-scraper/email-alert-portals.md into code, so extraction is a
script call, not the model re-deriving the same parse from a raw email body on
every run. If a portal redesigns its alert email, fix the parser here and the
anchor description in that doc together.

Validation status: the JobStreet and LinkedIn parsers were built against real
Malaysian alert digests and re-checked on 2026-09-26 against every alert from
the previous 7 days (JobStreet: 64 digests, 774 listings; LinkedIn: 21 digests,
120 listings; none malformed). That check drove the card-based JobStreet
rewrite below. The Indeed parser was
built against 6 real digests on 2026-08-22 and has **not been maintained** since
(see email-alert-portals.md). The unit tests use synthetic text shaped like
those samples, so they prove the parsing logic, not that a portal's layout is
unchanged. Check a fresh sample any time with
`python3 tools/gmail_imap_fetch.py test --portal <p> --file <saved.txt>`.
"""

from __future__ import annotations

import re


_JOBSTREET_FOOTER_RE = re.compile(
    r"^(View all matching jobs|Download Jobstreet App|Edit this alert|Unsubscribe from this alert"
    r"|Rate your recent employer|Was this email useful\??)$",
    re.IGNORECASE,
)
# Card decorations JobStreet added to alert digests (seen on real digests
# 2026-09-26): up to three "* <benefit>" highlight bullets after the salary,
# and a recency line ("Recently posted") before the tracking link. Neither is
# a field, and before this they desynced the parser into storing bullets as jobs.
_JOBSTREET_BULLET_RE = re.compile(r"^[*•]\s+")
_JOBSTREET_RECENCY_RE = re.compile(
    r"^(recently posted|new|posted (today|yesterday|on\b.*|\d+\+?\s*(minute|hour|day)s?\s+ago)"
    r"|\d+\+?\s*(minute|hour|day)s?\s+ago)$",
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


_JOBSTREET_PRE_LOCATION_RE = re.compile(r"(strong applicant|salary match)$|^posted on\b", re.IGNORECASE)
_JOBSTREET_GREETING_RE = re.compile(r"^(hi|hello|dear)\b|saved search|new jobs? for\b|^here are\b", re.IGNORECASE)
_JOBSTREET_SALARY_RE = re.compile(r"\bRM\s?[\d,.]+|per month", re.IGNORECASE)


def _link(line: str) -> str | None:
    if line.startswith("[") and line.endswith("]") and "://" in line:
        return line[1:-1].strip()
    if re.match(r"^https?://\S+$", line):
        return line
    return None


def _jobstreet_card(card: list[str], url: str) -> dict | None:
    """One listing card = the non-blank lines since the previous link.

    Fields are read by position, decorations by pattern:
      title, company, [badge | "Posted on <date>"]*, location,
      then anything: salary (the first RM line), "Profile salary match",
      "* benefit" bullets (which can wrap onto a second line),
      "Recently posted".
    Only title/company/location depend on position; everything after the
    location is ignored unless it is the salary, so a new decoration line
    JobStreet adds later cannot shift a field."""
    if not card or re.match(r"^logo\b", card[-1], re.IGNORECASE):
        return None  # a logo line's own tracking link, not a listing
    while card and (_JOBSTREET_GREETING_RE.search(card[0]) or re.match(r"^logo$", card[0], re.IGNORECASE)):
        card = card[1:]  # the digest's greeting preamble, or a logo without its own link
    if len(card) < 2:
        return None  # promo copy, CTA lines
    title, company, rest = card[0], card[1], card[2:]
    if _JOBSTREET_BULLET_RE.match(title) or _JOBSTREET_BULLET_RE.match(company):
        return None
    location = salary = None
    for ln in rest:
        if location is None:
            if _JOBSTREET_PRE_LOCATION_RE.search(ln) or _JOBSTREET_RECENCY_RE.match(ln):
                continue
            location = ln
        elif salary is None and _JOBSTREET_SALARY_RE.search(ln) and not _JOBSTREET_BULLET_RE.match(ln):
            salary = ln
    if location is not None and (_JOBSTREET_SALARY_RE.search(location) or _JOBSTREET_BULLET_RE.match(location)):
        return None  # a card missing its location line: never shift the salary into it
    return {"title": title, "company": company, "location": location, "salary": salary, "url": url}


def parse_jobstreet(body: str) -> list[dict]:
    """Card-based: every listing ends with its own tracking link, so the lines
    between two links are exactly one card (or a logo, promo line or the
    greeting, which _jobstreet_card rejects). This replaced an earlier
    line-sequence walker that assumed a fixed field order after the location;
    JobStreet's 2026-09 layout added benefit bullets (some wrapping onto two
    lines), "Profile salary match" and "Recently posted" lines, and that walker
    stored those bullets as job titles. Re-checked against 64 real digests
    (7 days, 2026-09-19..26).

    The chrome pass still runs first: the footer ends parsing, and the
    "Take your next career step" promo is skipped up to the optional "Jobs you
    may have missed" section, whose listings are kept."""
    # JobStreet puts a no-break space between "RM" and the figure.
    raw_lines = [ln.replace("\u00a0", " ").strip() for ln in body.splitlines()]
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

    listings, card = [], []
    for ln in lines:
        url = _link(ln)
        if url is None:
            if ln:
                card.append(ln)
            continue
        listing = _jobstreet_card(card, url)
        card = []
        if listing and not any(re.match(r"^logo\b", v or "", re.IGNORECASE) for v in listing.values()):
            listings.append(listing)
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
            return m.group("name").strip()
    return None
