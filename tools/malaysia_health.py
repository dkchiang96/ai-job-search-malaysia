#!/usr/bin/env python3
"""Monthly health check for the Malaysia adaptation (docs/malaysia/UPSTREAM-SYNC.md).

This fork's design rests on facts about other people's websites: which paths
robots.txt allows, which portal needs a login, which one has closed. Those
facts drift. This script re-checks each one and reports OK, CHANGED or ERROR.
CHANGED is not necessarily bad: JobStreet opening its job pages would mean a
real CLI becomes possible. It means a decision recorded in
docs/malaysia/PORTALS.md needs revisiting.

About 15 small requests (robots.txt files plus a few status probes), one
Hiredly search, and the offline parser self-test. Nothing is crawled.

Usage:
  python3 tools/malaysia_health.py            # all checks, table output
  python3 tools/malaysia_health.py --json
  python3 tools/malaysia_health.py --offline  # parser self-test only
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import digest_parsers  # noqa: E402
import robots_check  # noqa: E402

UA = "ai-job-search-malaysia-health/1.0 (+https://github.com/dkchiang96/ai-job-search-malaysia)"

# (check id, what we rely on, url, expected robots gate result: 0 allowed / 1 disallowed)
ROBOTS_EXPECTATIONS = [
    ("jobstreet-job-pages", "JobStreet job pages stay robots-disallowed (why JobStreet is email-alerts only)",
     "https://my.jobstreet.com/job/88888888", 1),
    ("hiredly-api", "Hiredly's search API stays robots-disallowed (hiredly-search never calls it)",
     "https://my-api.hiredly.com/api/job_seeker/v1/graphql", 1),
    ("hiredly-listing-pages", "Hiredly's server-rendered listing pages stay allowed",
     "https://my.hiredly.com/jobs-in-kuala-lumpur", 0),
    ("indeed-job-pages", "Indeed Malaysia job pages stay robots-disallowed",
     "https://malaysia.indeed.com/viewjob?jk=0000000000000000", 1),
    ("indeed-alert-links", "Indeed alert click-through links stay robots-disallowed (why /rank never opens them)",
     "https://malaysia.indeed.com/rc/clk/dl?jk=0000000000000000", 1),
    ("maukerja-search", "Maukerja job and search paths stay robots-disallowed",
     "https://www.maukerja.my/jobs/operations-manager", 1),
    ("glints-search", "Glints job search stays robots-disallowed",
     "https://glints.com/my/opportunities/jobs/explore?keyword=operations", 1),
    ("remoteok-api", "Remote OK API stays allowed", "https://remoteok.com/api", 0),
    ("weworkremotely-search", "We Work Remotely search stays allowed",
     "https://weworkremotely.com/remote-jobs/search?term=operations", 0),
    ("workingnomads-api", "Working Nomads API stays allowed", "https://www.workingnomads.com/api/exposed_jobs/", 0),
]

# (check id, what we rely on, url, expected HTTP status, body text that also confirms it)
STATUS_EXPECTATIONS = [
    ("jora-my-closed", "Jora Malaysia stays closed (its robots.txt is the closed-market file)",
     "https://my.jora.com/robots.txt", 410, "closed markets"),
    ("myfuturejobs-login", "MYFutureJobs job data still needs a login (HTTP 401)",
     "https://candidates.myfuturejobs.gov.my/api/vacancies?page=0&size=1", 401, None),
]
BLOCKED = {403, 429, 503}  # a bot wall: the fact could not be checked, which is not a change


def http_status(url: str) -> tuple[int, str]:
    r = subprocess.run(["curl", "-s", "-L", "-m", "15", "-A", UA, "-w", "\n%{http_code}", "--", url],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25)
    body, _, code = r.stdout.rpartition("\n")
    return int(code.strip() or 0), body


def check_robots(gate=robots_check.gate) -> list[dict]:
    out = []
    for cid, why, url, expected in ROBOTS_EXPECTATIONS:
        try:
            rc, msg = gate(url)
        except Exception as exc:  # noqa: BLE001
            out.append({"check": cid, "status": "ERROR", "why": why, "detail": str(exc)})
            continue
        if "UNCONFIRMED" in msg:
            out.append({"check": cid, "status": "ERROR", "why": why, "detail": msg})
        else:
            out.append({"check": cid, "status": "OK" if rc == expected else "CHANGED", "why": why, "detail": msg})
    return out


def check_status(status=http_status) -> list[dict]:
    out = []
    for cid, why, url, expected, confirm in STATUS_EXPECTATIONS:
        try:
            code, body = status(url)
        except Exception as exc:  # noqa: BLE001
            out.append({"check": cid, "status": "ERROR", "why": why, "detail": str(exc)})
            continue
        detail = f"HTTP {code} (expected {expected})"
        if code == expected:
            verdict = "OK"
        elif confirm and confirm.lower() in body.lower():
            verdict, detail = "OK", f"HTTP {code}; page states '{confirm}'"
        elif code in BLOCKED:
            verdict = "ERROR"  # couldn't verify - rerun later, don't read it as a change
        else:
            verdict = "CHANGED"
        out.append({"check": cid, "status": verdict, "why": why, "detail": detail})
    return out


def check_hiredly_live() -> dict:
    cli = ROOT / ".agents" / "skills" / "hiredly-search" / "cli" / "src" / "cli.ts"
    why = "hiredly-search still returns real listings"
    try:
        r = subprocess.run(["bun", "run", str(cli), "search", "-l", "kuala-lumpur", "--limit", "3", "--format", "json"],
                           capture_output=True, text=True, encoding="utf-8", timeout=90)
        if r.returncode != 0:
            return {"check": "hiredly-live", "status": "CHANGED", "why": why, "detail": r.stderr.strip()[:200]}
        n = len(json.loads(r.stdout)["results"])
        return {"check": "hiredly-live", "status": "OK" if n else "CHANGED", "why": why, "detail": f"{n} result(s)"}
    except Exception as exc:  # noqa: BLE001
        return {"check": "hiredly-live", "status": "ERROR", "why": why, "detail": str(exc)[:200]}


def check_parsers() -> dict:
    fx = ROOT / "tools" / "demo_fixtures"
    got = {
        "jobstreet": len(digest_parsers.parse_jobstreet((fx / "jobstreet_digest.txt").read_text(encoding="utf-8"))),
        "indeed": len(digest_parsers.parse_indeed((fx / "indeed_digest.txt").read_text(encoding="utf-8"))),
        "linkedin": len(digest_parsers.parse_linkedin((fx / "linkedin_digest.txt").read_text(encoding="utf-8"))),
    }
    ok = got == {"jobstreet": 4, "indeed": 2, "linkedin": 4}
    return {"check": "digest-parsers", "status": "OK" if ok else "CHANGED",
            "why": "alert parsers still read the recorded layouts (a real-inbox check is /gmail-alerts dry-run)",
            "detail": json.dumps(got)}


def _force_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args(argv)
    results = [check_parsers()]
    if not args.offline:
        results = check_robots() + check_status() + [check_hiredly_live()] + results
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(f"{r['status']:<8} {r['check']:<24} {r['why']}\n{'':<33}{r['detail']}")
        bad = [r for r in results if r["status"] != "OK"]
        print(f"\n{len(results) - len(bad)}/{len(results)} OK" +
              ("" if not bad else " - review docs/malaysia/PORTALS.md for each CHANGED/ERROR line"))
    return 0 if all(r["status"] == "OK" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
