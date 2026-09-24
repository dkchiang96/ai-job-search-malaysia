#!/usr/bin/env python3
"""Email yourself a run summary after an unattended /jobs run (Automation pack).

Sends one plain-text email through Gmail SMTP using the same app password
tools/gmail_imap_fetch.py already uses (Google allows one app password for
both IMAP and SMTP). **It can only send to your own address** (GMAIL_IMAP_USER):
there is no --to flag, no CC, no attachments of your documents. It is a
notification to you, never a message to anyone else.

The summary is built deterministically from job_scraper/seen_jobs.json, not
from anything the model said, so it is accurate even when a headless run ended
early.

Usage:
  python3 tools/notify_email.py summary --date 2026-09-24            # print only
  python3 tools/notify_email.py summary --date 2026-09-24 --send
  python3 tools/notify_email.py send --subject "..." --body-file body.txt
"""

from __future__ import annotations

import argparse
import json
import os
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / "gmail_alerts" / ".env"
STATE = ROOT / "job_scraper" / "seen_jobs.json"
SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 465
TOP_N = 10


def _credentials() -> tuple[str, str]:
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    user, pw = os.environ.get("GMAIL_IMAP_USER"), os.environ.get("GMAIL_IMAP_APP_PASSWORD")
    if not user or not pw:
        raise RuntimeError("GMAIL_IMAP_USER / GMAIL_IMAP_APP_PASSWORD are not set - see docs/malaysia/JOB-ALERTS.md")
    return user, pw


def build_summary(seen: dict, run_date: str, min_score: int = 55) -> tuple[str, str]:
    """(subject, body) for everything first seen or ranked on run_date."""
    found = [e for e in seen.values() if isinstance(e, dict) and e.get("first_seen") == run_date]
    ranked = [e for e in seen.values() if isinstance(e, dict) and e.get("rank_date") == run_date
              and e.get("status") == "ranked" and e.get("rank_score") is not None]
    ranked.sort(key=lambda e: e["rank_score"], reverse=True)
    good = [e for e in ranked if e["rank_score"] >= min_score
            and e.get("location_verdict") != "FAIL" and e.get("language_gate") != "FAIL"]
    unranked = [e for e in found if e.get("status") == "new"]
    by_portal: dict[str, int] = {}
    for e in found:
        by_portal[e.get("portal") or "unknown"] = by_portal.get(e.get("portal") or "unknown", 0) + 1

    subject = f"[jobs] {len(good)} job(s) worth a look - {run_date}"
    lines = [
        f"Job search run for {run_date}",
        "",
        f"New jobs found: {len(found)}  ({', '.join(f'{p} {n}' for p, n in sorted(by_portal.items())) or 'none'})",
        f"Ranked this run: {len(ranked)}   Score >= {min_score}: {len(good)}",
    ]
    if unranked:
        lines.append(f"Found but not ranked yet: {len(unranked)} (run /rank to continue)")
    lines += ["", "Top matches:"] if good else ["", "No new matches above the threshold this run."]
    for e in good[:TOP_N]:
        lines.append(f"  [{e['rank_score']}] {e.get('rank_verdict', '')} - {e.get('title')} @ {e.get('company')}"
                     f" ({e.get('location') or '-'})")
        if e.get("url"):
            lines.append(f"      {e['url']}")
    lines += ["", "Scores are triage from the posting text only - /apply re-evaluates before anything is drafted."]
    return subject, "\n".join(lines)


def send(subject: str, body: str) -> dict:
    user, pw = _credentials()
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, user
    msg.set_content(body)
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
        smtp.login(user, pw)
        smtp.send_message(msg)
    return {"sent": True, "to": "self", "subject": subject}


def _force_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_sum = sub.add_parser("summary")
    p_sum.add_argument("--date", required=True)
    p_sum.add_argument("--min-score", type=int, default=55)
    p_sum.add_argument("--state", type=Path, default=STATE)
    p_sum.add_argument("--send", action="store_true")
    p_send = sub.add_parser("send")
    p_send.add_argument("--subject", required=True)
    p_send.add_argument("--body-file", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        if args.cmd == "summary":
            doc = json.loads(args.state.read_text(encoding="utf-8")) if args.state.exists() else {"seen": {}}
            subject, body = build_summary(doc.get("seen", doc), args.date, args.min_score)
            if not args.send:
                print(f"Subject: {subject}\n\n{body}")
                return 0
            print(json.dumps(send(subject, body)))
        else:
            print(json.dumps(send(args.subject, args.body_file.read_text(encoding="utf-8"))))
    except Exception as exc:  # noqa: BLE001 - a JSON line for the calling wrapper, never a traceback
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
