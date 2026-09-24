"""tools/malaysia_health.py verdict logic, offline (network calls are injected)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import malaysia_health as mh  # noqa: E402


class TestVerdicts(unittest.TestCase):
    def test_robots_expectations_ok_changed_error(self):
        expected = {cid: exp for cid, _, _, exp in mh.ROBOTS_EXPECTATIONS}

        def gate_as_expected(url):
            exp = next(e for _, _, u, e in mh.ROBOTS_EXPECTATIONS if u == url)
            return exp, "ALLOWED" if exp == 0 else "DISALLOWED for *"

        self.assertTrue(all(r["status"] == "OK" for r in mh.check_robots(gate_as_expected)))

        opened = mh.check_robots(lambda url: (0, "ALLOWED - robots.txt permits this path"))
        changed = {r["check"] for r in opened if r["status"] == "CHANGED"}
        self.assertEqual(changed, {cid for cid, e in expected.items() if e == 1})
        self.assertIn("jobstreet-job-pages", changed)

        unreadable = mh.check_robots(lambda url: (1, "UNCONFIRMED (HTTP 500) - do not retry"))
        self.assertTrue(all(r["status"] == "ERROR" for r in unreadable))

    def test_status_checks_treat_bot_walls_as_unverified(self):
        results = {r["check"]: r["status"] for r in mh.check_status(lambda url: (403, "blocked"))}
        self.assertEqual(set(results.values()), {"ERROR"})
        results = {r["check"]: r["status"] for r in mh.check_status(lambda url: (200, "Welcome, we're hiring"))}
        self.assertEqual(set(results.values()), {"CHANGED"})

    def test_status_check_accepts_confirming_text(self):
        out = mh.check_status(lambda url: (200, "# Robots.txt for closed markets") if "jora" in url else (401, ""))
        self.assertTrue(all(r["status"] == "OK" for r in out))

    def test_offline_parser_self_test(self):
        self.assertEqual(mh.check_parsers()["status"], "OK")


if __name__ == "__main__":
    unittest.main()
