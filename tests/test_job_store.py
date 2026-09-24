"""tools/job_store.py: sync idempotency, status history, yield by alert/portal,
and the read-only query guard."""

import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import job_store as js  # noqa: E402


def _state(path: Path, seen: dict) -> None:
    path.write_text(json.dumps({"seen": seen}), encoding="utf-8")


class TestJobStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.db, self.state, self.tracker = d / "jobs.db", d / "seen_jobs.json", d / "tracker.csv"
        _state(self.state, {
            "a_ops": {"title": "Ops Lead", "company": "A Sdn Bhd", "status": "new", "portal": "jobstreet-alert",
                      "source": "email-alert", "alert_name": "ops in KL", "first_seen": "2026-09-01"},
            "b_ops": {"title": "Ops Manager", "company": "B Bhd", "status": "ranked", "rank_score": 72,
                      "portal": "jobstreet-alert", "source": "email-alert", "alert_name": "ops in KL",
                      "first_seen": "2026-09-02"},
            "c_ops": {"title": "COO", "company": "C", "status": "ranked", "rank_score": 40,
                      "portal": "hiredly-search", "source": "cli", "first_seen": "2026-09-03",
                      "location": "FAIL"},
        })
        self.tracker.write_text("company,role,status\nB Bhd,Ops Manager,applied\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_sync_is_idempotent_and_records_status_changes(self):
        with closing(js.connect(self.db)) as conn:
            first = js.sync(conn, self.state, "2026-09-10")
            again = js.sync(conn, self.state, "2026-09-10")
        self.assertEqual((first["inserted"], first["history_rows_added"]), (3, 3))
        self.assertEqual((again["inserted"], again["history_rows_added"]), (0, 0))

        seen = json.loads(self.state.read_text(encoding="utf-8"))["seen"]
        seen["a_ops"]["status"] = "ranked"
        _state(self.state, seen)
        with closing(js.connect(self.db)) as conn:
            out = js.sync(conn, self.state, "2026-09-11")
            history = conn.execute("SELECT status FROM status_history WHERE key='a_ops' ORDER BY seen_on").fetchall()
            loc = conn.execute("SELECT location FROM jobs WHERE key='c_ops'").fetchone()[0]
        self.assertEqual(out["status_changed"], 1)
        self.assertEqual([r[0] for r in history], ["new", "ranked"])
        self.assertIsNone(loc)  # a legacy PASS/FAIL verdict is never stored as a place

    def test_yield_by_alert_and_portal(self):
        with closing(js.connect(self.db)) as conn:
            js.sync(conn, self.state, "2026-09-10")
        conn = js.connect(self.db, readonly=True)
        by_alert = js.yield_report(conn, "alert", None, 55, self.tracker)
        by_portal = js.yield_report(conn, "portal", None, 55, self.tracker)
        conn.close()
        self.assertEqual(by_alert, [{"alert": "ops in KL", "seen": 2, "ranked": 1, "shortlisted": 1, "applied": 1,
                                     "shortlist_rate_pct": 50.0}])
        self.assertEqual({r["portal"]: r["shortlisted"] for r in by_portal}, {"jobstreet-alert": 1, "hiredly-search": 0})

    def test_salary_report_separates_estimates_and_uses_midpoints(self):
        seen = json.loads(self.state.read_text(encoding="utf-8"))["seen"]
        seen["a_ops"]["salary"] = "RM 8,000 - RM 10,000 per month"
        seen["b_ops"]["salary"] = "RM 12,000 per month"
        seen["c_ops"]["salary"] = "Negotiable"
        seen["d_est"] = {"title": "Ops Lead", "company": "D", "status": "new", "salary": "RM 5,000 - RM 7,000 a month (Estimated)"}
        _state(self.state, seen)
        with closing(js.connect(self.db)) as conn:
            js.sync(conn, self.state, "2026-09-10")
        conn = js.connect(self.db, readonly=True)
        out = js.salary_report(conn, "OPS", None)
        conn.close()
        self.assertEqual(out["employer_stated"], {"n": 2, "p25": 9750, "median": 10500, "p75": 11250, "min": 9000, "max": 12000})
        self.assertEqual(out["portal_estimated"]["n"], 1)
        self.assertEqual(out["no_usable_figure"], 0)  # "Negotiable" is on the COO row, which doesn't match "ops"

    def test_query_is_read_only(self):
        with closing(js.connect(self.db)) as conn:
            js.sync(conn, self.state, "2026-09-10")
        conn = js.connect(self.db, readonly=True)
        self.assertEqual(len(js.query(conn, "SELECT key FROM jobs")), 3)
        with self.assertRaises(ValueError):
            js.query(conn, "DELETE FROM jobs")
        with self.assertRaises(sqlite3.OperationalError):
            conn.execute("DELETE FROM jobs")  # the connection itself is mode=ro
        conn.close()

    def test_missing_db_for_readonly_commands(self):
        with self.assertRaises(FileNotFoundError):
            js.connect(Path(self.tmp.name) / "nope.db", readonly=True)


if __name__ == "__main__":
    unittest.main()
