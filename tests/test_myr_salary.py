"""tools/myr_salary.py: the salary shapes Malaysian portals actually emit."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from myr_salary import monthly_ceiling, parse_salary  # noqa: E402


class TestPortalShapes(unittest.TestCase):
    def test_jobstreet_range_with_en_dash(self):
        p = parse_salary("RM 9,500 – RM 13,000 per month")
        self.assertEqual((p["currency"], p["monthly_min"], p["monthly_max"]), ("MYR", 9500, 13000))
        self.assertEqual(p["period"], "month")
        self.assertFalse(p["period_assumed"])

    def test_hiredly_cli_output(self):
        p = parse_salary("RM 4,000 - RM 6,000 / month")
        self.assertEqual((p["monthly_min"], p["monthly_max"]), (4000, 6000))

    def test_hiredly_raw_value_without_currency_or_period(self):
        p = parse_salary("4000 - 6000")
        self.assertEqual((p["currency"], p["monthly_min"], p["monthly_max"]), ("MYR", 4000, 6000))
        self.assertTrue(p["period_assumed"])
        self.assertFalse(p["currency_stated"])

    def test_indeed_estimate_is_flagged(self):
        p = parse_salary("RM 10,000 - RM 15,000 a month (Estimated)")
        self.assertEqual(p["monthly_max"], 15000)
        self.assertTrue(p["estimated"])

    def test_weekly_rate_is_not_read_as_monthly(self):
        p = parse_salary("From RM 1,000 a week")
        self.assertEqual((p["period"], p["period_assumed"]), ("week", False))
        self.assertIsNone(p["monthly_min"])

    def test_myr_decimals_and_mth(self):
        p = parse_salary("MYR 5,000.00 - 8,000.00/mth (Negotiable)")
        self.assertEqual((p["monthly_min"], p["monthly_max"]), (5000, 8000))
        self.assertFalse(p["period_assumed"])

    def test_k_suffix_on_both_and_on_upper_only(self):
        self.assertEqual(parse_salary("RM15k - RM20k")["monthly_max"], 20000)
        p = parse_salary("RM 15 - 20k per month")
        self.assertEqual((p["monthly_min"], p["monthly_max"]), (15000, 20000))

    def test_annual_is_divided_by_twelve(self):
        p = parse_salary("RM 120,000 - RM 150,000 a year")
        self.assertEqual((p["monthly_min"], p["monthly_max"]), (10000, 12500))
        self.assertEqual(p["period"], "year")

    def test_unlabelled_six_figure_range_is_read_as_annual(self):
        p = parse_salary("RM 180,000 - 240,000")
        self.assertEqual(p["period"], "year")
        self.assertTrue(p["period_assumed"])
        self.assertEqual(p["monthly_max"], 20000)

    def test_up_to_and_from(self):
        up = parse_salary("Up to RM 8,000 per month")
        self.assertEqual((up["min"], up["max"]), (None, 8000))
        frm = parse_salary("From RM 5,000 monthly")
        self.assertEqual((frm["min"], frm["max"]), (5000, None))

    def test_malay_period_words(self):
        self.assertEqual(parse_salary("RM3,500 sebulan")["period"], "month")
        self.assertEqual(parse_salary("Sehingga RM 4,000")["max"], 4000)

    def test_daily_and_hourly_are_not_converted(self):
        d = parse_salary("RM 150 per day")
        self.assertEqual(d["period"], "day")
        self.assertIsNone(d["monthly_min"])
        self.assertIsNone(parse_salary("RM 20 an hour")["monthly_max"])

    def test_foreign_currency_is_kept_unconverted(self):
        p = parse_salary("SGD 8,000 - 10,000 per month")
        self.assertEqual(p["currency"], "SGD")
        self.assertIsNone(p["monthly_max"])
        self.assertEqual(p["max"], 10000)

    def test_no_figure_texts(self):
        for text in ("Undisclosed", "Negotiable", "Competitive", "", None):
            self.assertIsNone(parse_salary(text), text)


class TestMonthlyCeiling(unittest.TestCase):
    def test_ceiling_prefers_max_then_min(self):
        self.assertEqual(monthly_ceiling("RM 5,000 - RM 7,000"), 7000)
        self.assertEqual(monthly_ceiling("From RM 9,000 per month"), 9000)
        self.assertIsNone(monthly_ceiling("Undisclosed"))
        self.assertIsNone(monthly_ceiling("USD 5,000 per month"))


if __name__ == "__main__":
    unittest.main()
