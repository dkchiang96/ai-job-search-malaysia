"""tools/run_pipeline.py --demo: runs the real modules end to end on invented
data, offline, without touching the real job_scraper/seen_jobs.json."""

import contextlib
import io
import json
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import run_pipeline  # noqa: E402

REAL_STATE = ROOT / "job_scraper" / "seen_jobs.json"


class TestDemo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "demo"
        cls.real_before = REAL_STATE.read_bytes() if REAL_STATE.exists() else None
        buf = io.StringIO()
        start = time.perf_counter()
        with contextlib.redirect_stdout(buf):
            cls.code = run_pipeline.run_demo(cls.out)
        cls.elapsed = time.perf_counter() - start
        cls.log = buf.getvalue()
        cls.seen = json.loads((cls.out / "seen_jobs.json").read_text(encoding="utf-8"))["seen"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_exits_cleanly_and_quickly(self):
        self.assertEqual(self.code, 0)
        self.assertLess(self.elapsed, 30)

    def test_cross_source_duplicates_are_merged(self):
        self.assertIn("4 new, 4 already found by a portal CLI", self.log)
        self.assertEqual(len(self.seen), 11)

    def test_every_job_ends_ranked_or_parked(self):
        statuses = sorted(e["status"] for e in self.seen.values())
        self.assertEqual(statuses.count("unverified"), 1)
        self.assertEqual(statuses.count("ranked"), 10)

    def test_gates_fire_with_reasons(self):
        gated = {e["title"]: e["fit_breakdown"]["gate_failed"] for e in self.seen.values()
                 if e.get("fit_breakdown", {}).get("gate_failed")}
        self.assertEqual(gated, {
            "Customer Service Executive (Mandarin Speaker)": "G3 salary",
            "Head of Support Operations": "G1 location",
            "Operations Excellence Lead": "G4 employer rating",
        })
        self.assertIn("must be authorized to work in the United States", self.log)

    def test_outputs_written_and_history_mirrored(self):
        rows = json.loads((self.out / "notion_preview.json").read_text(encoding="utf-8"))
        self.assertTrue(rows and all(r["Score"] >= 55 for r in rows))
        self.assertTrue((self.out / "email_preview.txt").read_text(encoding="utf-8").startswith("Subject: [jobs]"))
        conn = sqlite3.connect(self.out / "jobs.db")
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 11)
        conn.close()

    def test_real_state_is_untouched(self):
        after = REAL_STATE.read_bytes() if REAL_STATE.exists() else None
        self.assertEqual(after, self.real_before)

    def test_no_personal_or_inbox_data_in_outputs(self):
        blob = "".join(p.read_text(encoding="utf-8") for p in self.out.glob("*.json")) + self.log
        self.assertNotIn("Aisyah", blob)  # the digest greeting never survives parsing
        self.assertNotRegex(blob, r"[\w.+-]+@(?!example\.invalid)[\w-]+\.[a-z]{2,}")


if __name__ == "__main__":
    unittest.main()
