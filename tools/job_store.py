#!/usr/bin/env python3
"""Optional SQLite history mirror of job_scraper/seen_jobs.json.

seen_jobs.json stays the system of record - every command still reads and
writes it exactly as upstream designed. This mirror answers the questions a
JSON blob can't answer cheaply once a search has run for a few months:

  * Which source actually produces jobs I shortlist and apply to?
    (`yield --by portal`)
  * Which JobStreet saved search earns one of my 10 alert slots?
    (`yield --by alert` - uses the alert name /gmail-alerts records)
  * How has volume moved week to week? (`stats`)
  * What do Malaysian postings like the ones I target actually pay?
    (`salary --title ...` - RM percentiles from every posting you have seen
    that stated a figure, parsed by tools/myr_salary.py)

`sync` is idempotent: it upserts every entry and appends a row to
`status_history` only when an entry's status actually changed, so re-running
it daily builds a timeline (new -> ranked -> expired) that seen_jobs.json,
which only holds the current status, cannot show. The database lives at
job_scraper/jobs.db and is gitignored.

Usage:
  python3 tools/job_store.py sync
  python3 tools/job_store.py stats
  python3 tools/job_store.py yield --by portal|alert|source [--since YYYY-MM-DD] [--min-score 55]
  python3 tools/job_store.py salary --title "operations manager" [--since YYYY-MM-DD]
  python3 tools/job_store.py query "SELECT title, company FROM jobs WHERE status = 'ranked' LIMIT 5"
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from rank_state import norm, tracker_pairs  # noqa: E402
import myr_salary  # noqa: E402

DEFAULT_DB = ROOT / "job_scraper" / "jobs.db"
DEFAULT_STATE = ROOT / "job_scraper" / "seen_jobs.json"
DEFAULT_TRACKER = ROOT / "job_search_tracker.csv"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    key           TEXT PRIMARY KEY,
    title         TEXT,
    company       TEXT,
    location      TEXT,
    url           TEXT,
    portal        TEXT,
    source        TEXT,
    alert_name    TEXT,
    salary        TEXT,
    status        TEXT,
    fit           TEXT,
    rank_score    INTEGER,
    rank_verdict  TEXT,
    rank_model    TEXT,
    first_seen    TEXT,
    posted_date   TEXT,
    deadline      TEXT,
    rank_date     TEXT,
    synced_at     TEXT,
    raw           TEXT
);
CREATE TABLE IF NOT EXISTS status_history (
    key        TEXT NOT NULL,
    status     TEXT NOT NULL,
    seen_on    TEXT NOT NULL,
    PRIMARY KEY (key, status, seen_on)
);
CREATE INDEX IF NOT EXISTS jobs_portal ON jobs(portal);
CREATE INDEX IF NOT EXISTS jobs_alert ON jobs(alert_name);
"""

COLUMNS = ("title", "company", "location", "url", "portal", "source", "alert_name", "salary", "status", "fit",
           "rank_score", "rank_verdict", "rank_model", "first_seen", "posted_date", "deadline", "rank_date")


def connect(db: Path, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        if not db.exists():
            raise FileNotFoundError(f"{db} not found - run `python3 tools/job_store.py sync` first")
        conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    else:
        db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db)
        conn.executescript(SCHEMA)
    conn.row_factory = sqlite3.Row
    return conn


def sync(conn: sqlite3.Connection, state: Path, today: str) -> dict:
    if not state.exists():
        raise FileNotFoundError(f"{state} not found - run /scrape or /gmail-alerts first")
    doc = json.loads(state.read_text(encoding="utf-8"))
    seen = doc.get("seen", doc) if isinstance(doc, dict) else {}
    inserted = updated = transitions = 0
    for key, entry in seen.items():
        if not isinstance(entry, dict):
            continue
        values = {c: entry.get(c) for c in COLUMNS}
        # A legacy entry may hold a PASS/FAIL/FLAG verdict in `location`; it is not a place.
        if values["location"] in ("PASS", "FAIL", "FLAG"):
            values["location"] = None
        prev = conn.execute("SELECT status FROM jobs WHERE key = ?", (key,)).fetchone()
        cols = ", ".join(COLUMNS)
        marks = ", ".join("?" for _ in COLUMNS)
        conn.execute(
            f"INSERT INTO jobs (key, {cols}, synced_at, raw) VALUES (?, {marks}, ?, ?) "
            f"ON CONFLICT(key) DO UPDATE SET {', '.join(f'{c}=excluded.{c}' for c in COLUMNS)}, "
            "synced_at=excluded.synced_at, raw=excluded.raw",
            (key, *[values[c] for c in COLUMNS], today, json.dumps(entry, ensure_ascii=False)),
        )
        if prev is None:
            inserted += 1
        elif prev["status"] != values["status"]:
            updated += 1
        if values["status"] and (prev is None or prev["status"] != values["status"]):
            conn.execute("INSERT OR IGNORE INTO status_history VALUES (?, ?, ?)", (key, values["status"], today))
            transitions += 1
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    return {"inserted": inserted, "status_changed": updated, "history_rows_added": transitions, "total_jobs": total}


def stats(conn: sqlite3.Connection) -> dict:
    by = lambda col: {  # noqa: E731
        (r[0] or "(none)"): r[1]
        for r in conn.execute(f"SELECT {col}, COUNT(*) FROM jobs GROUP BY {col} ORDER BY COUNT(*) DESC")
    }
    weekly = [
        {"week": r[0], "new_jobs": r[1]}
        for r in conn.execute(
            "SELECT strftime('%Y-W%W', first_seen) AS wk, COUNT(*) FROM jobs "
            "WHERE first_seen IS NOT NULL GROUP BY wk ORDER BY wk DESC LIMIT 12"
        )
    ]
    return {"total": conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
            "by_status": by("status"), "by_portal": by("portal"), "by_source": by("source"), "last_12_weeks": weekly}


def yield_report(conn: sqlite3.Connection, by: str, since: str | None, min_score: int, tracker: Path) -> list[dict]:
    column = {"portal": "portal", "alert": "alert_name", "source": "source"}[by]
    applied = tracker_pairs(tracker)
    groups: dict[str, dict] = {}
    params: list = []
    where = ""
    if since:
        where, params = "WHERE first_seen >= ?", [since]
    if by == "alert":
        where = (where + " AND " if where else "WHERE ") + "alert_name IS NOT NULL"
    for r in conn.execute(f"SELECT {column} AS grp, company, title, status, rank_score FROM jobs {where}", params):
        g = groups.setdefault(r["grp"] or "(none)", {"seen": 0, "ranked": 0, "shortlisted": 0, "applied": 0})
        g["seen"] += 1
        if r["rank_score"] is not None:
            g["ranked"] += 1
            if r["rank_score"] >= min_score:
                g["shortlisted"] += 1
        if (norm(r["company"]), norm(r["title"])) in applied:
            g["applied"] += 1
    rows = []
    for name, g in groups.items():
        rows.append({by: name, **g, "shortlist_rate_pct": round(100 * g["shortlisted"] / g["seen"], 1) if g["seen"] else 0.0})
    rows.sort(key=lambda r: (r["shortlisted"], r["seen"]), reverse=True)
    return rows


def _percentile(values: list[float], pct: float) -> int:
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return round(ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo))


def salary_report(conn: sqlite3.Connection, title_like: str, since: str | None) -> dict:
    """Monthly-RM spread of stated salaries for postings whose title matches.

    Each posting contributes the midpoint of its range (or its single figure).
    Employer-stated and portal-estimated figures are reported separately,
    because Indeed's estimates are not an employer's budget."""
    params: list = [f"%{title_like.lower()}%"]
    where = "WHERE lower(title) LIKE ? AND salary IS NOT NULL"
    if since:
        where += " AND first_seen >= ?"
        params.append(since)
    stated, estimated, skipped = [], [], 0
    for r in conn.execute(f"SELECT salary FROM jobs {where}", params):
        p = myr_salary.parse_salary(r["salary"])
        figs = [x for x in (p["monthly_min"], p["monthly_max"]) if x] if p else []
        if not figs:
            skipped += 1
            continue
        (estimated if p["estimated"] else stated).append(sum(figs) / len(figs))

    def spread(vals: list[float]) -> dict | None:
        if not vals:
            return None
        return {"n": len(vals), "p25": _percentile(vals, 0.25), "median": _percentile(vals, 0.5),
                "p75": _percentile(vals, 0.75), "min": round(min(vals)), "max": round(max(vals))}

    return {"title_like": title_like, "since": since, "currency": "MYR per month (posting midpoints)",
            "employer_stated": spread(stated), "portal_estimated": spread(estimated),
            "no_usable_figure": skipped}


def query(conn: sqlite3.Connection, sql: str) -> list[dict]:
    if not sql.lstrip().lower().startswith(("select", "with")):
        raise ValueError("query runs read-only SELECT/WITH statements only")
    return [dict(r) for r in conn.execute(sql)]


def _force_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--state", type=Path, default=DEFAULT_STATE)
    ap.add_argument("--tracker", type=Path, default=DEFAULT_TRACKER)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sync")
    sub.add_parser("stats")
    p_y = sub.add_parser("yield")
    p_y.add_argument("--by", choices=["portal", "alert", "source"], default="portal")
    p_y.add_argument("--since", default=None)
    p_y.add_argument("--min-score", type=int, default=55, help="rank_score counted as shortlisted (default 55)")
    p_s = sub.add_parser("salary")
    p_s.add_argument("--title", required=True, help="case-insensitive title substring, e.g. 'operations manager'")
    p_s.add_argument("--since", default=None)
    p_q = sub.add_parser("query")
    p_q.add_argument("sql")
    args = ap.parse_args(argv)

    try:
        if args.cmd == "sync":
            with closing(connect(args.db)) as conn:
                out = sync(conn, args.state, date.today().isoformat())
        else:
            conn = connect(args.db, readonly=True)
            if args.cmd == "stats":
                out = stats(conn)
            elif args.cmd == "salary":
                out = salary_report(conn, args.title, args.since)
            elif args.cmd == "yield":
                out = yield_report(conn, args.by, args.since, args.min_score, args.tracker)
            else:
                out = query(conn, args.sql)
            conn.close()
    except (FileNotFoundError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
