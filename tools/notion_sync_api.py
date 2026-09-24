#!/usr/bin/env python3
"""Headless Notion sync for scheduled runs (Automation pack, optional).

Upstream's /notion-sync uses the Notion MCP server, which authenticates by
interactive OAuth - by its own design it exits cleanly in a headless context.
A scheduled `claude -p "/jobs"` run is exactly that context. This script is the
headless counterpart: plain Notion REST API calls (stdlib urllib, no SDK) with
an integration token, no model in the loop, so an unattended run can still
refresh a Notion board you check on your phone.

It publishes ranked jobs from job_scraper/seen_jobs.json one way only - Notion
never writes back. Upsert is keyed on the seen_jobs.json key (stored in a
"Key" property), not the URL, because JobStreet alert links rotate on every
email. A Status you set by hand in Notion (Shortlist / Applied / Rejected /
anything custom) is never overwritten, and Applied/Rejected pages are skipped.

Use a separate Notion database from the one /notion-sync writes to: the two
tools deliberately don't share a page layout.

SETUP (~3 minutes), shipped off - nothing runs until both values exist:
  1. https://www.notion.so/my-integrations -> New integration -> copy the secret.
  2. Open (or create) an empty Notion database -> ... -> Connections -> add it.
  3. Copy the database id (the 32-hex segment of its URL, before any ?v=).
  4. In .env at the repo root (gitignored):
       NOTION_API_TOKEN=ntn_...
       NOTION_DATABASE_ID=<32-hex id>

Usage:
  python3 tools/notion_sync_api.py preview [--min-score 55] [--since YYYY-MM-DD]   # no API call
  python3 tools/notion_sync_api.py verify-schema
  python3 tools/notion_sync_api.py sync [--min-score 55] [--since YYYY-MM-DD] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "job_scraper" / "seen_jobs.json"
PAGE_MAP = ROOT / "job_scraper" / "notion_api_sync.json"
ENV_FILE = ROOT / ".env"
NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
DEFAULT_MIN_SCORE = 55

STATUS_OPTIONS = ["New", "Shortlist", "Applied", "Rejected"]
SCRIPT_STATUS = "New"
SKIP_STATUSES = {"Applied", "Rejected"}

RICH_TEXT = ["Key", "Company", "Location", "Salary", "Verdict", "Alert", "Strengths", "Gaps", "Gate"]
NUMBERS = ["Score", "CS", "DV", "WP"]
DATES = ["Found on", "Posted", "Deadline"]

_MIN_INTERVAL = 0.35  # Notion allows ~3 requests/second
_last = [0.0]


class NotionError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Rows (pure - also used by tools/run_pipeline.py --demo)
# --------------------------------------------------------------------------

def build_rows(seen: dict, min_score: int = DEFAULT_MIN_SCORE, since: str | None = None) -> list[dict]:
    rows = []
    for key, e in seen.items():
        if not isinstance(e, dict) or e.get("status") != "ranked":
            continue
        score = e.get("rank_score")
        if score is None or score < min_score:
            continue
        if since and (e.get("rank_date") or "") < since:
            continue
        if e.get("location_verdict") == "FAIL" or e.get("language_gate") == "FAIL":
            continue
        fb = e.get("fit_breakdown") or {}
        rows.append({
            "Key": key,
            "Title": e.get("title"),
            "Company": e.get("company"),
            "Location": e.get("location"),
            "Salary": e.get("salary"),
            "Score": score,
            "Verdict": e.get("rank_verdict"),
            "Source": e.get("portal"),
            "Alert": e.get("alert_name"),
            "URL": e.get("url"),
            "Found on": e.get("first_seen"),
            "Posted": e.get("posted_date"),
            "Deadline": e.get("deadline"),
            "CS": fb.get("cs"), "DV": fb.get("dv"), "WP": fb.get("wp"),
            "Gate": fb.get("gate_failed"),
            "Strengths": "; ".join(e.get("strengths") or []),
            "Gaps": "; ".join(e.get("gaps") or []),
        })
    rows.sort(key=lambda r: r["Score"], reverse=True)
    return rows


def _text(v: Any) -> dict:
    return {"rich_text": [{"type": "text", "text": {"content": str(v)[:2000]}}] if v else []}


def to_properties(row: dict, include_status: bool) -> dict:
    props: dict[str, Any] = {"Title": {"title": [{"type": "text", "text": {"content": str(row["Title"] or "")[:2000]}}]}}
    for name in RICH_TEXT:
        props[name] = _text(row.get(name))
    for name in NUMBERS:
        props[name] = {"number": row.get(name)}
    for name in DATES:
        value = row.get(name)
        props[name] = {"date": {"start": value} if isinstance(value, str) and len(value) == 10 else None}
    props["Source"] = {"select": {"name": row["Source"]} if row.get("Source") else None}
    props["URL"] = {"url": row.get("URL") or None}
    if include_status:
        props["Status"] = {"select": {"name": SCRIPT_STATUS}}
    return props


def plan_schema_patch(db: dict) -> dict:
    """Properties to add/rename so the database fits. Never removes or retypes."""
    existing = db.get("properties", {})
    patch: dict[str, Any] = {}
    title = next((n for n, p in existing.items() if p.get("type") == "title"), None)
    if title and title != "Title":
        patch[title] = {"name": "Title"}
    for n in RICH_TEXT:
        if n not in existing:
            patch[n] = {"rich_text": {}}
    for n in NUMBERS:
        if n not in existing:
            patch[n] = {"number": {"format": "number"}}
    for n in DATES:
        if n not in existing:
            patch[n] = {"date": {}}
    if "Source" not in existing:
        patch["Source"] = {"select": {}}
    if "URL" not in existing:
        patch["URL"] = {"url": {}}
    if "Status" not in existing:
        patch["Status"] = {"select": {"options": [{"name": o} for o in STATUS_OPTIONS]}}
    else:
        have = {o["name"] for o in existing["Status"].get("select", {}).get("options", [])}
        missing = [o for o in STATUS_OPTIONS if o not in have]
        if missing:
            patch["Status"] = {"select": {"options": existing["Status"]["select"]["options"] + [{"name": o} for o in missing]}}
    return patch


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

def _load_env() -> None:
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def credentials() -> tuple[str, str]:
    _load_env()
    token, db = os.environ.get("NOTION_API_TOKEN"), os.environ.get("NOTION_DATABASE_ID")
    if not token or not db:
        raise NotionError("MISSING_CREDENTIALS: set NOTION_API_TOKEN and NOTION_DATABASE_ID in .env "
                          "(see this script's docstring) - the automation pack ships switched off")
    return token, db


def make_request(token: str) -> Callable[[str, str, dict | None], dict]:
    def request(method: str, path: str, body: dict | None = None) -> dict:
        delay = 1.0
        for attempt in range(6):
            wait = _MIN_INTERVAL - (time.monotonic() - _last[0])
            if wait > 0:
                time.sleep(wait)
            _last[0] = time.monotonic()
            req = urllib.request.Request(
                f"{NOTION_API}{path}", method=method,
                data=json.dumps(body).encode("utf-8") if body is not None else None,
                headers={"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION,
                         "Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    raw = resp.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", errors="replace")[:300]
                if (e.code == 429 or e.code >= 500) and attempt < 5:
                    time.sleep(float(e.headers.get("Retry-After") or delay))
                    delay = min(delay * 2, 30)
                    continue
                raise NotionError(f"{method} {path} -> HTTP {e.code}: {detail}") from None
            except urllib.error.URLError as e:
                if attempt < 5:
                    time.sleep(delay)
                    delay = min(delay * 2, 30)
                    continue
                raise NotionError(f"{method} {path} -> network error: {e.reason}") from None
        raise NotionError(f"{method} {path} failed after retries")
    return request


# --------------------------------------------------------------------------
# Sync
# --------------------------------------------------------------------------

def _load_map() -> dict:
    return json.loads(PAGE_MAP.read_text(encoding="utf-8")) if PAGE_MAP.exists() else {}


def _page_status(page: dict) -> str | None:
    sel = (page.get("properties", {}).get("Status") or {}).get("select")
    return sel.get("name") if sel else None


def sync(rows: list[dict], db_id: str, request: Callable, page_map: dict, dry_run: bool = False) -> dict:
    created = updated = skipped = 0
    failed = []
    for row in rows:
        page_id = page_map.get(row["Key"])
        try:
            if page_id:
                page = request("GET", f"/pages/{page_id}", None)
                if page.get("archived") or page.get("in_trash"):
                    page_id = None
                elif _page_status(page) in SKIP_STATUSES:
                    skipped += 1
                    continue
            if page_id:
                status = _page_status(page)
                props = to_properties(row, include_status=status in (None, SCRIPT_STATUS))
                if not dry_run:
                    request("PATCH", f"/pages/{page_id}", {"properties": props})
                updated += 1
            else:
                if not dry_run:
                    page = request("POST", "/pages", {"parent": {"database_id": db_id},
                                                      "properties": to_properties(row, include_status=True)})
                    page_map[row["Key"]] = page["id"]
                created += 1
        except NotionError as exc:
            failed.append({"key": row["Key"], "error": str(exc)})
    return {"created": created, "updated": updated, "skipped_user_status": skipped, "failed": failed,
            "dry_run": dry_run}


def _load_seen(path: Path) -> dict:
    if not path.exists():
        raise NotionError(f"{path} not found - run /scrape and /rank first")
    doc = json.loads(path.read_text(encoding="utf-8"))
    return doc.get("seen", doc)


def _force_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state", type=Path, default=STATE)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("preview", "sync"):
        p = sub.add_parser(name)
        p.add_argument("--min-score", type=int, default=DEFAULT_MIN_SCORE)
        p.add_argument("--since", default=None, help="only jobs ranked on/after YYYY-MM-DD")
        if name == "sync":
            p.add_argument("--dry-run", action="store_true")
    sub.add_parser("verify-schema")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "preview":
            rows = build_rows(_load_seen(args.state), args.min_score, args.since)
            print(json.dumps({"would_sync": len(rows), "rows": rows}, indent=2, ensure_ascii=False))
            return 0
        token, db_id = credentials()
        request = make_request(token)
        if args.cmd == "verify-schema":
            patch = plan_schema_patch(request("GET", f"/databases/{db_id}", None))
            if patch:
                request("PATCH", f"/databases/{db_id}", {"properties": patch})
            print(json.dumps({"properties_added_or_renamed": sorted(patch)}))
            return 0
        patch = plan_schema_patch(request("GET", f"/databases/{db_id}", None))
        if patch and not args.dry_run:
            request("PATCH", f"/databases/{db_id}", {"properties": patch})
        page_map = _load_map()
        out = sync(build_rows(_load_seen(args.state), args.min_score, args.since), db_id, request, page_map, args.dry_run)
        if not args.dry_run:
            PAGE_MAP.parent.mkdir(parents=True, exist_ok=True)
            PAGE_MAP.write_text(json.dumps(page_map, indent=2), encoding="utf-8")
        print(json.dumps(out, indent=2))
        return 1 if out["failed"] else 0
    except NotionError as exc:
        code = "MISSING_CREDENTIALS" if str(exc).startswith("MISSING_CREDENTIALS") else "NOTION_ERROR"
        print(json.dumps({"error": str(exc), "code": code}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
