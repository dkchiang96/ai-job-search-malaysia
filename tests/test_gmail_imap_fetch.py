"""tools/gmail_imap_fetch.py: message parsing, storage into seen_jobs.json, and a
fake IMAP session - all offline. The digests are the invented-but-real-layout
fixtures in tools/demo_fixtures/."""

import json
import sys
import tempfile
import unittest
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import gmail_imap_fetch as g  # noqa: E402
from digest_parsers import alert_name_from_subject, parse_linkedin  # noqa: E402
from job_key import make_key  # noqa: E402

FIXTURES = ROOT / "tools" / "demo_fixtures"


def _message(subject: str, body: str) -> bytes:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = "Jobstreet Job Alerts <noreply@example.invalid>"
    msg.set_content(body)
    msg.add_alternative("<html><body>html part is ignored</body></html>", subtype="html")
    return msg.as_bytes()


class FakeIMAP:
    """Just enough of imaplib.IMAP4_SSL for fetch_portal()."""

    def __init__(self, mailbox: dict[str, dict[str, bytes]]):
        self.mailbox = mailbox
        self.selected = None
        self.fetch_specs = []

    def select(self, label, readonly=False):
        assert readonly, "the fetcher must open labels read-only"
        name = label.strip('"')
        if name not in self.mailbox:
            return "NO", [b"no such label"]
        self.selected = name
        return "OK", [b"1"]

    def uid(self, command, *args):
        if command == "search":
            return "OK", [" ".join(self.mailbox[self.selected]).encode()]
        if command == "fetch":
            uid, spec = args
            self.fetch_specs.append(spec)
            return "OK", [(b"1 (BODY[] {1})", self.mailbox[self.selected][uid])]
        raise AssertionError(command)


class TestMessageParsing(unittest.TestCase):
    def test_jobstreet_digest_message_yields_tagged_listings(self):
        body = (FIXTURES / "jobstreet_digest.txt").read_text(encoding="utf-8")
        listings = g.listings_from_message("jobstreet", _message("4 new jobs for operations in Selangor", body))
        self.assertEqual([x["title"] for x in listings], [
            "Operations Manager", "Head of Fulfilment Operations",
            "Operations Excellence Lead", "Regional Operations Manager",
        ])
        self.assertTrue(all(x["alert_name"] == "operations in Selangor" for x in listings))
        self.assertTrue(all(x["portal"] == "jobstreet" for x in listings))
        # The greeting, promo block and footer never become listings.
        self.assertFalse(any("career advice" in (x["title"] + x["company"]) for x in listings))
        # 2026-09 layout: benefit bullets, "Recently posted" and the Yes/No feedback
        # footer are decorations, never titles, companies or locations.
        for x in listings:
            for field in (x["title"], x["company"], x["location"] or ""):
                self.assertFalse(field.startswith("*") or field in ("Yes", "No", "Recently posted"), field)
        self.assertEqual(listings[0]["salary"], "RM 9,000 – RM 12,000 per month")
        self.assertEqual(listings[0]["url"], "https://url.jobstreet.com/ss/c/u001.demo-0001")

    def test_linkedin_header_is_not_read_as_a_listing(self):
        listings = parse_linkedin((FIXTURES / "linkedin_digest.txt").read_text(encoding="utf-8"))
        self.assertEqual(listings[0]["title"], "Operations Manager")
        self.assertEqual(listings[0]["company"], "Contoh Logistik Sdn Bhd")
        self.assertEqual(listings[0]["url"], "https://my.linkedin.com/jobs/view/4000000101")
        self.assertEqual(len(listings), 4)

    def test_alert_names_from_subjects(self):
        self.assertEqual(alert_name_from_subject("jobstreet", "20 new jobs for Head of Operations in Kuala Lumpur"),
                         "Head of Operations in Kuala Lumpur")
        self.assertIsNone(alert_name_from_subject("jobstreet", "Ops Lead [Strong applicant] + 5 new jobs - Job Alert"))
        self.assertEqual(alert_name_from_subject("linkedin", "Your job alert for operations manager"), "operations manager")
        self.assertIsNone(alert_name_from_subject("jobstreet", None))
        # quoted boolean searches keep their quotes intact (a real saved-search shape)
        self.assertEqual(alert_name_from_subject("jobstreet", '12 new jobs for "COO" OR "Chief Operating Officer" in Kuala Lumpur'),
                         '"COO" OR "Chief Operating Officer" in Kuala Lumpur')


class TestStorage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.seen = Path(self.tmp.name) / "job_scraper" / "seen_jobs.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _listing(self, **kw):
        base = {"title": "Operations Manager", "company": "Contoh Logistik Sdn Bhd", "location": "Shah Alam, Selangor",
                "salary": "RM 9,000 – RM 12,000 per month", "url": "https://url.jobstreet.com/ss/c/u001.a",
                "portal": "jobstreet", "alert_name": "operations in Selangor"}
        base.update(kw)
        return base

    def test_creates_state_file_with_upstream_schema_plus_additive_fields(self):
        out = g.store_listings([self._listing()], self.seen, today="2026-09-24")
        self.assertEqual(out["stored"], 1)
        doc = json.loads(self.seen.read_text(encoding="utf-8"))
        key = make_key("Contoh Logistik Sdn Bhd", "Operations Manager")
        entry = doc["seen"][key]
        for field in ("title", "company", "url", "first_seen", "posted_date", "deadline", "fit", "status", "portal", "source"):
            self.assertIn(field, entry)
        self.assertEqual(entry["status"], "new")
        self.assertEqual(entry["source"], "email-alert")
        self.assertEqual(entry["portal"], "jobstreet-alert")
        self.assertEqual(entry["salary_monthly_myr"], {"min": 9000, "max": 12000})
        self.assertEqual(entry["alert_name"], "operations in Selangor")

    def test_rotating_tracking_url_does_not_defeat_dedup(self):
        g.store_listings([self._listing(url="https://url.jobstreet.com/ss/c/u001.first")], self.seen, today="2026-09-24")
        out = g.store_listings([self._listing(url="https://url.jobstreet.com/ss/c/u001.second")], self.seen, today="2026-09-25")
        self.assertEqual((out["stored"], out["duplicates"]), (0, 1))

    def test_existing_cli_entry_is_never_overwritten(self):
        key = make_key("Contoh Logistik Sdn Bhd", "Operations Manager")
        self.seen.parent.mkdir(parents=True)
        self.seen.write_text(json.dumps({"seen": {key: {"title": "Operations Manager", "status": "ranked",
                                                         "portal": "hiredly-search", "rank_score": 71}}}), encoding="utf-8")
        g.store_listings([self._listing()], self.seen, today="2026-09-24")
        entry = json.loads(self.seen.read_text(encoding="utf-8"))["seen"][key]
        self.assertEqual((entry["status"], entry["portal"], entry["rank_score"]), ("ranked", "hiredly-search", 71))

    def test_dry_run_writes_nothing(self):
        out = g.store_listings([self._listing()], self.seen, dry_run=True)
        self.assertEqual(out["stored"], 1)
        self.assertFalse(self.seen.exists())

    def test_set_fit_updates_only_fit_and_reports_bad_input(self):
        out = g.store_listings([self._listing()], self.seen, today="2026-09-24")
        key = out["keys"][0]
        res = g.set_fit({key: "High", "no-such-key": "low", key + "x": "great"}, self.seen)
        self.assertEqual(res["updated"], 1)
        self.assertEqual(len(res["errors"]), 2)
        entry = json.loads(self.seen.read_text(encoding="utf-8"))["seen"][key]
        self.assertEqual((entry["fit"], entry["status"]), ("high", "new"))

    def test_set_unverified_only_parks_new_email_alert_entries(self):
        key = g.store_listings([self._listing()], self.seen, today="2026-09-24")["keys"][0]
        doc = json.loads(self.seen.read_text(encoding="utf-8"))
        doc["seen"]["acme_ops"] = {"title": "Ops", "status": "ranked", "source": "cli"}
        self.seen.write_text(json.dumps(doc), encoding="utf-8")
        res = g.set_unverified([key, "acme_ops", "missing"], self.seen)
        self.assertEqual((res["parked"], len(res["errors"])), (1, 2))
        seen = json.loads(self.seen.read_text(encoding="utf-8"))["seen"]
        self.assertEqual((seen[key]["status"], seen["acme_ops"]["status"]), ("unverified", "ranked"))

    def test_listing_without_company_is_skipped(self):
        self.assertEqual(g.store_listings([self._listing(company=None)], self.seen)["stored"], 0)


class TestFetchPortal(unittest.TestCase):
    def test_reads_new_uids_only_with_peek(self):
        body = (FIXTURES / "jobstreet_digest.txt").read_text(encoding="utf-8")
        imap = FakeIMAP({"Job Alerts/JobStreet": {"1": _message("4 new jobs for ops", body),
                                                  "2": _message("4 new jobs for ops", body)}})
        summary, listings = g.fetch_portal(imap, "jobstreet", "Job Alerts/JobStreet", "2026-09-01", {"1"})
        self.assertEqual((summary["messages_found"], summary["messages_new"]), (2, 1))
        self.assertEqual(len(listings), 4)
        self.assertEqual(imap.fetch_specs, ["(BODY.PEEK[])"])  # never marks mail as read

    def test_missing_label_is_reported_not_guessed(self):
        summary, listings = g.fetch_portal(FakeIMAP({}), "linkedin", "Job Alerts/LinkedIn", None, set())
        self.assertIn("pending mailbox setup", summary["status"])
        self.assertEqual(listings, [])


class TestConfig(unittest.TestCase):
    def test_defaults_cover_all_three_alert_portals(self):
        self.assertEqual(g.load_portals(Path("does-not-exist.json")), g.DEFAULT_PORTALS)
        self.assertEqual(set(g.DEFAULT_PORTALS), {"jobstreet", "linkedin", "indeed"})

    def test_unknown_portal_in_config_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.json"
            p.write_text(json.dumps({"portals": {"maukerja": "Job Alerts/Maukerja"}}), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                g.load_portals(p)


if __name__ == "__main__":
    unittest.main()
