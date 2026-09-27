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


INDEED_DIGEST = (
    "Indeed Job Alert\n"
    "3 new supply chain jobs in Penang\n"
    "\n"
    "Jobs 1-3 of 3 new jobs\n"
    "See matching results on Indeed: https://malaysia.indeed.com/jobs?q=supply+chain&l=Penang\n"
    "\n\n"
    "Supply Chain Manager\n"
    "Syarikat Contoh Bhd - Bayan Lepas\n"
    "RM 10,000 - RM 15,000 a month\n"
    "Responsive employer\n"
    "Easily apply\n"
    "Lead planning and logistics across three plants. Salary RM 12k negotiable.\n"
    "2 days ago\n"
    "https://malaysia.indeed.com/rc/clk/dl?jk=abc123\n"
    "\n"
    "Warehouse Lead\n"
    "Contoh Neo - Butterworth\n"
    "From RM 1,000 a week\n"
    "Run a two-shift warehouse team.\n"
    "Just posted\n"
    "https://malaysia.indeed.com/pagead/clk/dl?mo=r&ad=demo\n"
    "\n"
    "Planner - Demand & Supply\n"
    "Kilang Contoh Group - Penang\n"
    "Own the monthly demand plan.\n"
    "1 day ago\n"
    "https://malaysia.indeed.com/rc/clk/dl?jk=def456\n"
    "\n\n\n"
    "Do not share this email\n"
    "Salaries estimated if unavailable. When a job posting doesn't include a salary, we estimate it.\n"
    "Unsubscribe from this job alert: https://subscriptions.indeed.com/alerts/cancel?t=demo\n"
)


class TestIndeedParser(unittest.TestCase):
    """Shaped like the 2026-04..09 layout (315 real emails checked 2026-09-27)."""

    def test_every_card_parsed_including_the_first_and_sponsored(self):
        listings = parse_indeed(INDEED_DIGEST)
        self.assertEqual([x["title"] for x in listings],
                         ["Supply Chain Manager", "Warehouse Lead", "Planner - Demand & Supply"])
        self.assertEqual(listings[0]["company"], "Syarikat Contoh Bhd")
        self.assertEqual(listings[0]["location"], "Bayan Lepas")
        self.assertEqual(listings[0]["url"], "https://malaysia.indeed.com/rc/clk/dl?jk=abc123")
        self.assertIn("pagead", listings[1]["url"])
        self.assertIsNone(listings[2]["salary"])

    def test_title_with_a_dash_keeps_it(self):
        self.assertEqual(parse_indeed(INDEED_DIGEST)[2]["title"], "Planner - Demand & Supply")

    def test_salary_is_the_salary_line_not_a_figure_in_the_snippet(self):
        salary = parse_indeed(INDEED_DIGEST)[0]["salary"]
        self.assertTrue(salary.startswith("RM 10,000 - RM 15,000 a month"))

    def test_every_salary_is_tagged_possibly_estimated(self):
        from myr_salary import parse_salary
        for listing in parse_indeed(INDEED_DIGEST)[:2]:
            self.assertIn("may be estimated", listing["salary"])
            self.assertTrue(parse_salary(listing["salary"])["estimated"])

    def test_weekly_pay_is_not_read_as_monthly(self):
        from myr_salary import parse_salary
        p = parse_salary(parse_indeed(INDEED_DIGEST)[1]["salary"])
        self.assertEqual(p["period"], "week")
        self.assertIsNone(p["monthly_min"])

    def test_card_without_a_date_line_is_dropped_not_guessed(self):
        body = INDEED_DIGEST.replace("Just posted\n", "")
        self.assertEqual([x["title"] for x in parse_indeed(body)],
                         ["Supply Chain Manager", "Planner - Demand & Supply"])

    def test_activation_email_listings_use_engage_links(self):
        body = (
            "Your job alert is active\n"
            "You'll receive your first daily job alert for supply chain in Penang when jobs become available.\n"
            "https://engage.indeed.com/f/a/browse~demo\n"
            "https://engage.indeed.com/f/a/unsubscribe~demo\n"
            "1 new supply chain jobs in Penang\n"
            "Buyer\n"
            "Contoh Neo - Penang\n"
            "Easily apply\n"
            "Source parts.\n"
            "3 days ago\n"
            "https://engage.indeed.com/f/a/job~demo\n"
        )
        listings = parse_indeed(body)
        self.assertEqual([(x["title"], x["url"]) for x in listings],
                         [("Buyer", "https://engage.indeed.com/f/a/job~demo")])

    def test_activation_email_without_listings_yields_nothing(self):
        body = ("Your job alert is active\n"
                "https://engage.indeed.com/f/a/browse~demo\n"
                "Privacy Policy: https://engage.indeed.com/f/a/p~demo\n")
        self.assertEqual(parse_indeed(body), [])

    def test_alert_name_comes_from_the_body_not_the_subject(self):
        from digest_parsers import alert_name
        subject = "Supply Chain Manager at Syarikat Contoh Bhd. 2 more supply chain jobs in Penang"
        self.assertEqual(alert_name("indeed", subject, INDEED_DIGEST), "supply chain in Penang")
        self.assertEqual(alert_name("indeed", None, "7 new customer service jobs (Remote)\n"),
                         "customer service in Remote")


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
