"""Unit tests for tools/digest_parsers.py against synthetic text built to
match the block-anchor formats documented in
.claude/skills/job-scraper/email-alert-portals.md exactly.

These prove the parsing logic is correct against the documented spec. They do
NOT prove the spec still matches a live email - see that file's own
confirmation dates and digest_parsers.py's module docstring.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from digest_parsers import parse_indeed, parse_jobstreet, parse_linkedin, normalize_linkedin_url


class TestJobStreetParser(unittest.TestCase):
    def test_two_listings_with_optional_salary_and_badge(self):
        body = (
            "logo\n"
            "Head of Operations\n"
            "Kilang Contoh Group\n"
            "Strong applicant\n\n"
            "Kuala Lumpur, Federal Territory of Kuala Lumpur\n"
            "RM 9,500 – RM 13,000 per month\n"
            "[https://url.jobstreet.com/ss/c/u001.abc123]\n"
            "\n"
            "Operations Manager\n"
            "Acme Sdn Bhd\n\n"
            "Petaling Jaya, Selangor\n"
            "[https://url.jobstreet.com/ss/c/u001.def456]\n"
        )
        listings = parse_jobstreet(body)
        self.assertEqual(len(listings), 2)
        self.assertEqual(listings[0]["title"], "Head of Operations")
        self.assertEqual(listings[0]["company"], "Kilang Contoh Group")
        self.assertIn("Kuala Lumpur", listings[0]["location"])
        self.assertIn("RM", listings[0]["salary"])
        self.assertEqual(listings[0]["url"], "https://url.jobstreet.com/ss/c/u001.abc123")
        self.assertEqual(listings[1]["title"], "Operations Manager")
        self.assertIsNone(listings[1]["salary"])

    def test_no_salary_does_not_break_parse(self):
        body = "Director of Operations\nContoh Fintech Sdn Bhd\n\nKuala Lumpur, Malaysia\n[https://url.jobstreet.com/x]\n"
        listings = parse_jobstreet(body)
        self.assertEqual(len(listings), 1)
        self.assertIsNone(listings[0]["salary"])
        self.assertEqual(listings[0]["url"], "https://url.jobstreet.com/x")


class TestIndeedParser(unittest.TestCase):
    def test_relative_date_terminates_block_no_blank_lines(self):
        body = (
            "Jobs 1-2 of 2 new jobs\n"
            "See matching results on Indeed: https://malaysia.indeed.com/jobs?q=operations\n"
            "Operations Director\n"
            "Syarikat Contoh Bhd - Kuala Lumpur\n"
            "RM 10,000 - RM 15,000 a month\n"
            "Easily apply\n"
            "Lead our operations team across three markets and drive growth.\n"
            "2 days ago\n"
            "https://malaysia.indeed.com/rc/clk/dl?jk=abc123\n"
            "Head of Operations\n"
            "Contoh Neo - Petaling Jaya\n"
            "Manage day to day payment operations for a fast growing fintech.\n"
            "Just posted\n"
            "https://malaysia.indeed.com/rc/clk/dl?jk=def456\n"
        )
        listings = parse_indeed(body)
        self.assertEqual(len(listings), 2)
        self.assertEqual(listings[0]["title"], "Operations Director")
        self.assertEqual(listings[0]["company"], "Syarikat Contoh Bhd")
        self.assertEqual(listings[0]["location"], "Kuala Lumpur")
        self.assertIn("RM", listings[0]["salary"])
        self.assertEqual(listings[1]["title"], "Head of Operations")
        self.assertIsNone(listings[1]["salary"])


class TestLinkedInParser(unittest.TestCase):
    def test_dash_rule_separated_blocks_skip_decoration_lines(self):
        body = (
            "Chief of Staff\n"
            "Contoh Pay\n"
            "Petaling Jaya, Selangor, Malaysia\n"
            "12 connections work here\n"
            "This company is actively hiring\n"
            "View job: https://www.linkedin.com/comm/jobs/view/4000000001\n"
            "---------------------------------\n"
            "Operations Manager\n"
            "Kedai Online Sdn Bhd\n"
            "Kuala Lumpur, Malaysia\n"
            "View job: https://my.linkedin.com/jobs/view/4000000002\n"
        )
        listings = parse_linkedin(body)
        self.assertEqual(len(listings), 2)
        self.assertEqual(listings[0]["title"], "Chief of Staff")
        # comm/jobs/view must be rewritten to the stable my.linkedin.com form
        self.assertEqual(listings[0]["url"], "https://my.linkedin.com/jobs/view/4000000001")
        self.assertEqual(listings[1]["url"], "https://my.linkedin.com/jobs/view/4000000002")

    def test_normalize_linkedin_url_rewrites_comm_path(self):
        self.assertEqual(
            normalize_linkedin_url("https://www.linkedin.com/comm/jobs/view/4000000003"),
            "https://my.linkedin.com/jobs/view/4000000003",
        )
        self.assertEqual(
            normalize_linkedin_url("https://my.linkedin.com/jobs/view/4000000003"),
            "https://my.linkedin.com/jobs/view/4000000003",
        )
        self.assertIsNone(normalize_linkedin_url(None))


if __name__ == "__main__":
    unittest.main()
