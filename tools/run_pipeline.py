#!/usr/bin/env python3
"""Offline demo of the Malaysia pipeline - the real code, on invented data.

    python3 tools/run_pipeline.py --demo

No network, no credentials, no LLM, and nothing outside job_scraper/.demo/ is
touched (your real seen_jobs.json is never read or written). Every stage calls
the same functions the real commands use:

  1 scrape   recorded portal-CLI output (hiredly-search, linkedin-search,
             remoteok-search) stored with tools/job_key.py keys, as /scrape Step 4 does
  2 alerts   invented JobStreet, Indeed and LinkedIn alert emails in their real layout, parsed by
             tools/digest_parsers.py and stored by tools/gmail_imap_fetch.py - which
             merges jobs already found by a portal CLI
  3 salary   tools/myr_salary.py normalises every pay string to monthly RM
  4 rank     tools/fit_model.py scores each job from the FACTS a /rank agent would
             report (tools/demo_fixtures/agent_facts.json) - every number is computed
             here; an alert-only job whose posting can't be found is parked, not scored
  5 history  tools/job_store.py mirrors the result into SQLite and reports yield per alert
  6 outputs  the rows tools/notion_sync_api.py would upsert, and the email
             tools/notify_email.py would send you - previewed, never sent

The only thing the demo does not run is the language model itself: reading a
posting and reporting facts. Those facts are the recorded fixture.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from contextlib import closing
from datetime import date
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fit_model  # noqa: E402
import digest_parsers  # noqa: E402
import gmail_imap_fetch  # noqa: E402
import job_store  # noqa: E402
import myr_salary  # noqa: E402
import notify_email  # noqa: E402
import notion_sync_api  # noqa: E402
from job_key import make_key  # noqa: E402

FIXTURES = ROOT / "tools" / "demo_fixtures"
DEFAULT_OUT = ROOT / "job_scraper" / ".demo"
CONFIG = ROOT / "config" / "fit_model.example.json"


DEMO_FILES = ("seen_jobs.json", "jobs.db", "notion_preview.json", "email_preview.txt")


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def say(msg: str = "") -> None:
    print(msg, flush=True)


def head(n: int, title: str) -> None:
    say(f"\n[{n}] {title}")


# ---------------------------------------------------------------------------
def stage_scrape(state: Path, today: str) -> int:
    doc = {"seen": {}}
    stored = 0
    for fixture in sorted(FIXTURES.glob("portal_*.json")):
        portal = fixture.stem.removeprefix("portal_")
        results = json.loads(fixture.read_text(encoding="utf-8"))["results"]
        for r in results:
            key = make_key(r["company"], r["title"], r["url"])
            if key in doc["seen"]:
                continue
            doc["seen"][key] = {
                "title": r["title"], "company": r["company"], "url": r["url"], "location": r.get("location"),
                "salary": r.get("salary"), "first_seen": today, "posted_date": r.get("date"), "deadline": None,
                "fit": None, "status": "new", "portal": portal, "source": "cli",
            }
            stored += 1
        say(f"    {portal:<22} {len(results)} result(s)")
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    say(f"    -> {stored} jobs stored in {rel(state)}")
    return stored


def _as_email(subject: str, body: str) -> bytes:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = "alerts@example.invalid"
    msg.set_content(body)
    return msg.as_bytes()


def stage_alerts(state: Path, today: str) -> dict:
    digests = [
        ("jobstreet", "4 new jobs for operations in Selangor", "jobstreet_digest.txt"),
        ("indeed", "Warehouse Operations Lead at Gudang Contoh Sdn Bhd. 1 more operations jobs in Selangor",
         "indeed_digest.txt"),
        ("linkedin", "Your job alert for operations manager in Malaysia", "linkedin_digest.txt"),
    ]
    listings = []
    for portal, subject, name in digests:
        body = (FIXTURES / name).read_text(encoding="utf-8")
        found = gmail_imap_fetch.listings_from_message(portal, _as_email(subject, body))
        listings += found
        say(f"    {portal:<10} digest '{subject}': {len(found)} listing(s) parsed "
            f"(greeting, promo block and footer discarded)")
    out = gmail_imap_fetch.store_listings(listings, state, today=today)
    say(f"    -> {out['stored']} new, {out['duplicates']} already found by a portal CLI (merged, not duplicated)")
    return out


def stage_salary(state: Path) -> None:
    seen = json.loads(state.read_text(encoding="utf-8"))["seen"]
    for e in seen.values():
        if not e.get("salary"):
            continue
        p = myr_salary.parse_salary(e["salary"])
        if p["currency"] == "MYR":
            view = f"RM {p['monthly_min'] or '?':,} - {p['monthly_max'] or '?':,} /month"
        else:
            view = f"{p['currency']} {p['min']:,.0f} - {p['max']:,.0f} /{p['period']} (converted only with your own fx rate)"
        flag = (" [period assumed]" if p["period_assumed"] else "") + (" [may be estimated]" if p["estimated"] else "")
        shown = e["salary"].replace(digest_parsers.INDEED_ESTIMATE_TAG, "")
        say(f"    {shown[:38]:<38} -> {view}{flag}")


def stage_rank(state: Path, today: date) -> dict:
    cfg = fit_model.load_config(CONFIG)
    facts = json.loads((FIXTURES / "agent_facts.json").read_text(encoding="utf-8"))
    seen = json.loads(state.read_text(encoding="utf-8"))["seen"]
    results, not_found = [], []
    for key, e in seen.items():
        f = facts.get(f"{e['company']}|{e['title']}")
        if f is None:
            continue
        if f.get("not_found"):
            not_found.append(key)
            continue
        results.append({"key": key, "status": "scored", "location_verdict": f["location_verdict"],
                        "location_note": f.get("location_note"),
                        "language_gate": f.get("language_gate", "PASS"), "language_note": f.get("language_note"),
                        "strengths": f.get("strengths", []), "gaps": f.get("gaps", []),
                        "fit_inputs": {**f["fit_inputs"], "salary_text": e.get("salary")}})
    out = fit_model.apply_results(results, cfg, state, today)
    if not_found:
        gmail_imap_fetch.set_unverified(not_found, state)

    say(f"    scorer: Fit Model (config/fit_model.example.json - goals: "
        f"{', '.join(g['label'] for g in cfg['direction']['goals'])})")
    say(f"    {'FIT':>3}  {'CS':>5} {'DV':>5} {'WP':>5}  VERDICT                   JOB")
    for r in out["ranked"]:
        flag = " (location FLAG)" if r["location_verdict"] == "FLAG" else ""
        say(f"    {r['score']:>3}  {r['cs']:>5} {r['dv']:>5} {r['wp']:>5}  {r['verdict']:<25} "
            f"{r['title']} @ {r['company']}{flag}")
    for r in out["vetoed"]:
        reason = r.get("gate_reason") or (r.get("language_note") if r["language_gate"] == "FAIL" else "location FAIL")
        say(f"    ---  excluded: {r['title']} @ {r['company']} - {r.get('gate_failed', 'veto')}: {reason}")
    for key in not_found:
        say(f"    ---  parked 'unverified': {seen[key]['title']} @ {seen[key]['company']} - alert email only, "
            "posting not found online, so it is not scored from its title")
    return out


def stage_history(state: Path, db: Path) -> None:
    with closing(job_store.connect(db)) as conn:
        synced = job_store.sync(conn, state, date.today().isoformat())
    conn = job_store.connect(db, readonly=True)
    by_alert = job_store.yield_report(conn, "alert", None, 55, ROOT / "does-not-exist.csv")
    by_portal = job_store.yield_report(conn, "portal", None, 55, ROOT / "does-not-exist.csv")
    conn.close()
    say(f"    {synced['total_jobs']} jobs mirrored to {rel(db)}")
    for r in by_portal:
        say(f"    portal {r['portal']:<22} seen {r['seen']}  shortlisted {r['shortlisted']}")
    for r in by_alert:
        say(f"    alert  {r['portal'] + ' ' + repr(r['alert']):<50} seen {r['seen']}  shortlisted {r['shortlisted']}")


def stage_outputs(state: Path, out_dir: Path, run_date: str) -> None:
    seen = json.loads(state.read_text(encoding="utf-8"))["seen"]
    rows = notion_sync_api.build_rows(seen)
    (out_dir / "notion_preview.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    say(f"    Notion: {len(rows)} row(s) would be upserted -> {rel(out_dir / 'notion_preview.json')} (no API call)")
    subject, body = notify_email.build_summary(seen, run_date)
    (out_dir / "email_preview.txt").write_text(f"Subject: {subject}\n\n{body}\n", encoding="utf-8")
    say(f"    Email to yourself (not sent): \"{subject}\"")


def run_demo(out_dir: Path) -> int:
    start = time.perf_counter()
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in DEMO_FILES:  # only ever the demo's own files - never a directory wipe
        (out_dir / name).unlink(missing_ok=True)
    state, db = out_dir / "seen_jobs.json", out_dir / "jobs.db"
    today = date.today()

    say("== ai-job-search-malaysia demo: real pipeline code, invented jobs, no network ==")
    head(1, "Scrape portal CLIs (recorded output)")
    stage_scrape(state, today.isoformat())
    head(2, "Import JobStreet, Indeed and LinkedIn alert emails")
    stage_alerts(state, today.isoformat())
    head(3, "Normalise salaries to monthly RM")
    stage_salary(state)
    head(4, "Rank with the Fit Model (agent facts recorded, arithmetic live)")
    stage_rank(state, today)
    head(5, "History mirror (SQLite) and alert yield")
    stage_history(state, db)
    head(6, "Outputs")
    stage_outputs(state, out_dir, today.isoformat())
    say(f"\n== done in {time.perf_counter() - start:.2f}s - everything is in {rel(out_dir)} ==")
    return 0


def _force_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demo", action="store_true", help="run the offline demo")
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    if not args.demo:
        say("Only --demo is implemented here. Live runs use the agent commands: /scrape, /gmail-alerts, /rank - or /jobs.")
        return 1
    out = args.out_dir.resolve()
    if ROOT not in out.parents:
        say(f"--out-dir must be inside the repo ({ROOT}); got {out}")
        return 1
    return run_demo(out)


if __name__ == "__main__":
    sys.exit(main())
