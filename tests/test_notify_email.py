"""tools/notify_email.py: the summary is built from state alone, and sending can
only ever address the account owner."""

import inspect
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import notify_email as ne  # noqa: E402

SEEN = {
    "a": {"title": "Ops Lead", "company": "A", "first_seen": "2026-09-24", "portal": "hiredly-search",
          "status": "ranked", "rank_date": "2026-09-24", "rank_score": 74, "rank_verdict": "Apply", "url": "u"},
    "b": {"title": "Clerk", "company": "B", "first_seen": "2026-09-24", "portal": "jobstreet-alert",
          "status": "ranked", "rank_date": "2026-09-24", "rank_score": 20},
    "c": {"title": "Ops", "company": "C", "first_seen": "2026-09-24", "portal": "jobstreet-alert", "status": "new"},
    "d": {"title": "US Ops", "company": "D", "first_seen": "2026-09-24", "portal": "remoteok-search",
          "status": "ranked", "rank_date": "2026-09-24", "rank_score": 88, "location_verdict": "FAIL"},
    "old": {"title": "Old", "company": "O", "first_seen": "2026-09-01", "status": "ranked",
            "rank_date": "2026-09-01", "rank_score": 90},
}


class TestSummary(unittest.TestCase):
    def test_counts_and_top_list(self):
        subject, body = ne.build_summary(SEEN, "2026-09-24")
        self.assertEqual(subject, "[jobs] 1 job(s) worth a look - 2026-09-24")
        self.assertIn("New jobs found: 4", body)
        self.assertIn("jobstreet-alert 2", body)
        self.assertIn("Found but not ranked yet: 1", body)
        self.assertIn("[74] Apply - Ops Lead @ A", body)
        self.assertNotIn("US Ops", body)  # a location veto never appears as a match
        self.assertNotIn("Old", body)

    def test_empty_run(self):
        subject, body = ne.build_summary({}, "2026-09-24")
        self.assertIn("0 job(s)", subject)
        self.assertIn("No new matches", body)


class TestSelfOnly(unittest.TestCase):
    def test_send_takes_no_recipient(self):
        self.assertEqual(list(inspect.signature(ne.send).parameters), ["subject", "body"])


if __name__ == "__main__":
    unittest.main()
