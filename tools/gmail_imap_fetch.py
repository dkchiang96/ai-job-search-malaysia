#!/usr/bin/env python3
"""Read job-alert digest emails over IMAP and add their listings to seen_jobs.json.

Why this exists: JobStreet - Malaysia's largest job board - disallows automated
requests to its job pages and to query-string searches in robots.txt, and names
AI crawlers explicitly. What it does offer is an opt-in email alert: you save a
search on JobStreet's own site and it emails you new matches. Reading your own
inbox touches none of JobStreet's servers. This script does exactly that, for
JobStreet, LinkedIn and Indeed alert digests (Indeed's Terms ban automated
access outright, so its alerts are the only way in there too).

The model never sees a raw email. The script logs in with a Gmail app password,
reads only the labels you configured, parses each digest with the deterministic
recipes in tools/digest_parsers.py, and writes new listings straight into
job_scraper/seen_jobs.json (same schema /scrape writes, same tools/job_key.py
keys, so a job that also arrives from Hiredly or LinkedIn search is not stored
twice). It prints a small JSON summary. It is read-only against Gmail: it never
labels, moves, marks or deletes mail.

SETUP (one-time, ~5 minutes) - full walkthrough in docs/malaysia/JOB-ALERTS.md:
  1. Gmail -> Settings -> "See all settings" -> Forwarding and POP/IMAP -> enable IMAP.
  2. Create an app password at myaccount.google.com/apppasswords (needs 2-Step
     Verification). Name it "ai-job-search".
  3. Put two lines in gmail_alerts/.env (the whole gmail_alerts/ folder is
     gitignored) or set them as environment variables:
       GMAIL_IMAP_USER=you@gmail.com
       GMAIL_IMAP_APP_PASSWORD=<the 16-character app password>
  4. Create one Gmail filter + label per portal (defaults below). Change the
     label names in gmail_alerts/config.json if yours differ:
       {"portals": {"jobstreet": "Job Alerts/JobStreet", "linkedin": "Job Alerts/LinkedIn",
                    "indeed": "Job Alerts/Indeed"}}

Usage:
  python3 tools/gmail_imap_fetch.py run [--since YYYY-MM-DD] [--portal jobstreet] [--dry-run]
  python3 tools/gmail_imap_fetch.py test --portal jobstreet --file saved_digest.txt
  python3 tools/gmail_imap_fetch.py config
  python3 tools/gmail_imap_fetch.py set-fit --results fits.json   # {"<key>": "high"|"medium"|"low"}
  python3 tools/gmail_imap_fetch.py set-unverified --keys "<k1>,<k2>"
"""

from __future__ import annotations

import argparse
import email
import email.header
import imaplib
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import digest_parsers  # noqa: E402
import myr_salary  # noqa: E402
from job_key import make_key  # noqa: E402

ALERTS_DIR = ROOT / "gmail_alerts"
STATE_PATH = ALERTS_DIR / "imap_state.json"
ENV_FILE = ALERTS_DIR / ".env"
CONFIG_FILE = ALERTS_DIR / "config.json"
SEEN_JOBS = ROOT / "job_scraper" / "seen_jobs.json"

# Default labels. A portal whose label doesn't exist yet is reported as
# "pending mailbox setup", never an error, so unused defaults cost nothing.
DEFAULT_PORTALS = {
    "jobstreet": "Job Alerts/JobStreet",
    "linkedin": "Job Alerts/LinkedIn",
    "indeed": "Job Alerts/Indeed",
}
FIRST_RUN_LOOKBACK_DAYS = 30
NEW_LISTINGS_SHOWN = 60  # cap on listings echoed back to the model per run


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _credentials() -> tuple[str, str]:
    _load_env_file(ENV_FILE)
    user = os.environ.get("GMAIL_IMAP_USER")
    pw = os.environ.get("GMAIL_IMAP_APP_PASSWORD")
    if not user or not pw:
        raise RuntimeError(
            "GMAIL_IMAP_USER / GMAIL_IMAP_APP_PASSWORD are not set - see docs/malaysia/JOB-ALERTS.md "
            "(or this script's docstring) for the one-time setup, then put them in gmail_alerts/.env"
        )
    return user, pw


def load_portals(config_path: Path = CONFIG_FILE) -> dict[str, str]:
    if not config_path.exists():
        return dict(DEFAULT_PORTALS)
    data = json.loads(config_path.read_text(encoding="utf-8"))
    portals = data.get("portals") if isinstance(data, dict) else None
    if not isinstance(portals, dict) or not portals:
        raise RuntimeError(f"{config_path}: expected {{\"portals\": {{\"<portal>\": \"<Gmail label>\"}}}}")
    unknown = [p for p in portals if p not in digest_parsers.PARSERS]
    if unknown:
        raise RuntimeError(f"{config_path}: no parser for {unknown}; known portals: {sorted(digest_parsers.PARSERS)}")
    return {str(k): str(v) for k, v in portals.items()}


def _load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"last_run": None, "processed_uids": {}}


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _decode_header(value: str | None) -> str | None:
    if not value:
        return None
    parts = []
    for chunk, charset in email.header.decode_header(value):
        parts.append(chunk.decode(charset or "utf-8", errors="replace") if isinstance(chunk, bytes) else chunk)
    return "".join(parts).strip()


def _extract_plain_text(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                charset = part.get_content_charset() or "utf-8"
                payload = part.get_payload(decode=True)
                return payload.decode(charset, errors="replace") if payload else ""
        return ""
    charset = msg.get_content_charset() or "utf-8"
    payload = msg.get_payload(decode=True)
    return payload.decode(charset, errors="replace") if payload else ""


def listings_from_message(portal: str, raw: bytes) -> list[dict]:
    """Parse one RFC822 message into listings tagged with portal and alert name."""
    msg = email.message_from_bytes(raw)
    body = _extract_plain_text(msg)
    parser = digest_parsers.PARSERS.get(portal)
    if parser is None or not body:
        return []
    alert = digest_parsers.alert_name(portal, _decode_header(msg.get("Subject")), body)
    out = []
    for listing in parser(body):
        listing["portal"] = portal
        listing["alert_name"] = alert
        out.append(listing)
    return out


def fetch_portal(imap: imaplib.IMAP4_SSL, portal: str, label: str, since: str | None,
                 processed_uids: set) -> tuple[dict, list[dict]]:
    """Returns (summary, listings); listings is empty when status != 'ok'."""
    typ, _ = imap.select(f'"{label}"', readonly=True)
    if typ != "OK":
        return {"portal": portal, "label": label, "status": "label not found - pending mailbox setup"}, []

    criteria = ["ALL"]
    if since:
        d = datetime.strptime(since, "%Y-%m-%d")
        criteria = [f'(SINCE "{d.strftime("%d-%b-%Y")}")']
    typ, data = imap.uid("search", None, *criteria)
    if typ != "OK":
        return {"portal": portal, "label": label, "status": "search failed"}, []

    uids = [u.decode() for u in data[0].split()]
    new_uids = [u for u in uids if u not in processed_uids]
    listings: list[dict] = []
    fetched = []
    for uid in new_uids:
        # BODY.PEEK never sets the \Seen flag - the script stays read-only.
        typ, msg_data = imap.uid("fetch", uid, "(BODY.PEEK[])")
        if typ != "OK" or not msg_data or msg_data[0] is None:
            continue
        fetched.append(uid)
        listings.extend(listings_from_message(portal, msg_data[0][1]))

    summary = {
        "portal": portal, "label": label, "status": "ok",
        "messages_found": len(uids), "messages_new": len(new_uids),
        "listings_extracted": len(listings), "new_uids": fetched,
    }
    return summary, listings


# --------------------------------------------------------------------------
# seen_jobs.json storage - same shape /scrape Step 4 writes, additive fields only
# --------------------------------------------------------------------------

def _load_seen(path: Path) -> dict:
    if not path.exists():
        return {"seen": {}}
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or not isinstance(doc.get("seen"), dict):
        raise RuntimeError(f"{path}: expected {{\"seen\": {{...}}}}")
    return doc


def _save_seen(path: Path, doc: dict) -> None:
    # Reuse /rank's atomic writer so a crash mid-write can't truncate the history.
    from rank_state import save_state
    path.parent.mkdir(parents=True, exist_ok=True)
    save_state(path, doc)


def store_listings(listings: list[dict], seen_path: Path = SEEN_JOBS, today: str | None = None,
                   dry_run: bool = False) -> dict:
    """Insert listings not already present (by canonical key or URL).

    Returns counts plus the stored entries' keys. Existing entries are never
    modified - a job first found by a portal CLI keeps its richer record."""
    today = today or date.today().isoformat()
    doc = _load_seen(seen_path)
    seen = doc["seen"]
    known_urls = {e.get("url") for e in seen.values() if isinstance(e, dict)}
    stored, duplicates = [], 0
    for item in listings:
        title, company, url = item.get("title"), item.get("company"), item.get("url")
        if not title or not company:
            continue
        key = make_key(company, title, url or "")
        if key in seen or (url and url in known_urls):
            duplicates += 1
            continue
        salary = myr_salary.parse_salary(item.get("salary"))
        seen[key] = {
            "title": title,
            "company": company,
            "url": url,
            "location": item.get("location"),
            "salary": item.get("salary"),
            "salary_monthly_myr": (
                {"min": salary["monthly_min"], "max": salary["monthly_max"]}
                if salary and (salary["monthly_min"] or salary["monthly_max"]) else None
            ),
            "first_seen": today,
            "posted_date": None,
            "deadline": None,
            "fit": None,
            "status": "new",
            "portal": f"{item.get('portal')}-alert",
            "source": "email-alert",
            "alert_name": item.get("alert_name"),
        }
        known_urls.add(url)
        stored.append(key)
    if stored and not dry_run:
        _save_seen(seen_path, doc)
    return {"stored": len(stored), "duplicates": duplicates, "keys": stored,
            "entries": {k: seen[k] for k in stored}}


def run(since: str | None, only_portal: str | None, dry_run: bool = False) -> dict:
    portals = load_portals()
    if only_portal:
        if only_portal not in portals:
            raise RuntimeError(f"portal '{only_portal}' is not configured; configured: {sorted(portals)}")
        portals = {only_portal: portals[only_portal]}
    user, pw = _credentials()
    state = _load_state()
    first_run = not state.get("last_run")
    since = since or state.get("last_run")
    if not since:
        since = date.fromordinal(date.today().toordinal() - FIRST_RUN_LOOKBACK_DAYS).isoformat()

    imap = imaplib.IMAP4_SSL("imap.gmail.com")
    imap.login(user, pw)
    results, all_listings = [], []
    try:
        for portal, label in portals.items():
            processed = set(state.get("processed_uids", {}).get(label, []))
            summary, listings = fetch_portal(imap, portal, label, since, processed)
            results.append(summary)
            all_listings.extend(listings)
            if summary.get("new_uids") and not dry_run:
                bucket = state.setdefault("processed_uids", {}).setdefault(label, [])
                state["processed_uids"][label] = sorted(set(bucket) | set(summary["new_uids"]), key=int)
    finally:
        imap.logout()

    stored = store_listings(all_listings, dry_run=dry_run)
    if not dry_run:
        state["last_run"] = date.today().isoformat()
        _save_state(state)
    for r in results:
        r.pop("new_uids", None)
    return {
        "since": since, "first_run": first_run, "dry_run": dry_run,
        "portals": results,
        "listings_extracted_total": len(all_listings),
        "new_jobs_stored": stored["stored"],
        "duplicates_skipped": stored["duplicates"],
        # Compact view for the calling command's quick-fit table - never the raw email.
        "new_listings": [
            {"key": k, "title": e["title"], "company": e["company"], "location": e["location"],
             "salary": e["salary"], "portal": e["portal"], "alert_name": e["alert_name"], "url": e["url"]}
            for k, e in list(stored["entries"].items())[:NEW_LISTINGS_SHOWN]
        ],
        "new_listings_truncated": max(0, stored["stored"] - NEW_LISTINGS_SHOWN),
    }


VALID_FITS = {"high", "medium", "low"}


def set_fit(results: dict, seen_path: Path = SEEN_JOBS) -> dict:
    """Write /gmail-alerts Step 3's quick-fit verdicts back to their entries.

    Only the `fit` field of existing keys changes; unknown keys and bad values
    are reported, never created or guessed."""
    doc = _load_seen(seen_path)
    seen = doc["seen"]
    updated, errors = [], []
    for key, fit in results.items():
        fit_value = str(fit).strip().lower()
        if key not in seen:
            errors.append({"key": key, "error": "unknown key"})
        elif fit_value not in VALID_FITS:
            errors.append({"key": key, "error": f"fit must be one of {sorted(VALID_FITS)}"})
        else:
            seen[key]["fit"] = fit_value
            updated.append(key)
    if updated:
        _save_seen(seen_path, doc)
    return {"updated": len(updated), "errors": errors}


def set_unverified(keys: list[str], seen_path: Path = SEEN_JOBS) -> dict:
    """Park email-alert entries whose posting /rank could not find anywhere.

    `unverified` is an additive status: /rank's `candidates` only selects `new`
    (or everything with --all, which retries these), and /scrape's dedup treats
    any existing key as seen. Only `new` email-alert entries can be parked, so
    this can never demote a ranked or applied job."""
    doc = _load_seen(seen_path)
    seen = doc["seen"]
    parked, errors = [], []
    for key in keys:
        entry = seen.get(key)
        if entry is None:
            errors.append({"key": key, "error": "unknown key"})
        elif entry.get("source") != "email-alert" or entry.get("status") != "new":
            errors.append({"key": key, "error": "only new email-alert entries can be parked"})
        else:
            entry["status"] = "unverified"
            parked.append(key)
    if parked:
        _save_seen(seen_path, doc)
    return {"parked": len(parked), "errors": errors}


def test_file(portal: str, file_path: Path) -> dict:
    parser = digest_parsers.PARSERS.get(portal)
    if parser is None:
        return {"error": f"no parser for portal '{portal}'"}
    body = file_path.read_text(encoding="utf-8", errors="replace")
    listings = parser(body)
    return {"portal": portal, "listings_extracted": len(listings), "listings": listings}


def _force_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main(argv=None) -> int:
    _force_utf8_output()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run", help="fetch configured labels and store new listings")
    p_run.add_argument("--since", default=None, help="YYYY-MM-DD; default: last run, or 30 days on the first run")
    p_run.add_argument("--portal", default=None)
    p_run.add_argument("--dry-run", action="store_true", help="parse and count, write nothing")
    p_test = sub.add_parser("test", help="parse a saved plain-text digest without touching IMAP")
    p_test.add_argument("--portal", required=True, choices=sorted(digest_parsers.PARSERS))
    p_test.add_argument("--file", type=Path, required=True)
    sub.add_parser("config", help="show the portal -> Gmail label map in use")
    p_fit = sub.add_parser("set-fit", help="write quick-fit verdicts: JSON file of {key: high|medium|low}")
    p_fit.add_argument("--results", type=Path, required=True)
    p_unv = sub.add_parser("set-unverified", help="park email-alert jobs whose posting /rank could not find")
    p_unv.add_argument("--keys", required=True, help="comma-separated seen_jobs.json keys")
    args = ap.parse_args(argv)

    try:
        if args.cmd == "run":
            print(json.dumps(run(args.since, args.portal, args.dry_run), indent=2, ensure_ascii=False))
        elif args.cmd == "test":
            print(json.dumps(test_file(args.portal, args.file), indent=2, ensure_ascii=False))
        elif args.cmd == "set-unverified":
            out = set_unverified([k.strip() for k in args.keys.split(",") if k.strip()])
            print(json.dumps(out, indent=2))
            if out["errors"]:
                return 1
        elif args.cmd == "set-fit":
            out = set_fit(json.loads(args.results.read_text(encoding="utf-8")))
            print(json.dumps(out, indent=2))
            if out["errors"]:
                return 1
        else:
            print(json.dumps({"config_file": str(CONFIG_FILE.relative_to(ROOT)), "exists": CONFIG_FILE.exists(),
                              "portals": load_portals()}, indent=2))
    except Exception as e:  # noqa: BLE001 - surface as JSON for the calling command, never a traceback
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
