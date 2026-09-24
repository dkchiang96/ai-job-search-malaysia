"""tools/fit_model.py: config validation, every gate, the layer arithmetic, and
the seen_jobs.json write-back - all against the shipped example config."""

import copy
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import fit_model as fm  # noqa: E402

EXAMPLE = json.loads((ROOT / "config" / "fit_model.example.json").read_text(encoding="utf-8"))


def inputs(**kw):
    base = {
        "location_category": "Kuala Lumpur",
        "location_verdict": "PASS",
        "domain_exclusion_pct": 0,
        "salary_text": "RM 8,000 - RM 11,000 per month",
        "glassdoor": 3.6,
        "required_years": 5,
        "requirements": [
            {"req": "ops experience", "must": True, "score": 1},
            {"req": "SQL", "must": True, "score": 0.5},
            {"req": "Mandarin", "must": False, "score": 1},
        ],
        "domain_tier": 100,
        "keyword_coverage_pct": 80,
        "employer_type": "startup_or_sme",
        "direction": {"growth": 100, "skills": 50, "stability": 50},
    }
    base.update(kw)
    return base


class TestConfig(unittest.TestCase):
    def test_example_config_is_valid(self):
        fm.validate_config(EXAMPLE)

    def test_bad_configs_name_the_problem(self):
        cases = [
            (lambda c: c["direction"]["goals"][0].update(weight=0.9), "sum to 1.0"),
            (lambda c: c["candidacy"]["weights"].update(domain=0.5), "summing to 1.0"),
            (lambda c: c["worth"]["salary_myr_month"].update(floor=20000), "floor <= current <= target"),
            (lambda c: c["direction"].update(required_goal="nope"), "required_goal"),
            (lambda c: c["direction"].update(goals=[]), "1-4 goals"),
            (lambda c: c["worth"]["location_scores"].update(Mars=150), "0-100"),
        ]
        for mutate, msg in cases:
            cfg = copy.deepcopy(EXAMPLE)
            mutate(cfg)
            with self.assertRaisesRegex(fm.ConfigError, msg):
                fm.validate_config(cfg)


class TestGates(unittest.TestCase):
    def gate(self, **kw):
        return fm.score_job(inputs(**kw), EXAMPLE).get("gate_failed")

    def test_each_gate(self):
        self.assertEqual(self.gate(location_category="Johor"), "G1 location")
        self.assertEqual(self.gate(location_verdict="FAIL"), "G1 location")
        self.assertEqual(self.gate(domain_exclusion_pct=60), "G2 domain")
        self.assertEqual(self.gate(salary_text="RM 3,000 - RM 5,000 per month"), "G3 salary")
        self.assertEqual(self.gate(glassdoor=2.1), "G4 employer rating")
        self.assertEqual(self.gate(required_years=11), "G5 experience")
        self.assertIsNone(self.gate())

    def test_estimated_salary_below_floor_does_not_gate(self):
        self.assertIsNone(self.gate(salary_text="RM 3,000 - RM 5,000 a month (Estimated)"))

    def test_gated_job_scores_zero_with_reason(self):
        out = fm.score_job(inputs(glassdoor=2.0), EXAMPLE)
        self.assertEqual((out["fit"], out["verdict"]), (0, "Skip (G4 employer rating)"))
        self.assertIn("2.0", out["gate_reason"])


class TestArithmetic(unittest.TestCase):
    def test_hand_computed_example(self):
        out = fm.score_job(inputs(), EXAMPLE)
        p = out["parts"]
        # R = (1*2 + 0.5*2 + 1*1) / (2+2+1) = 4/5 = 80
        self.assertEqual(p["R"], 80.0)
        self.assertEqual((p["D"], p["E"], p["K"], p["A"]), (100.0, 100.0, 80.0, 1.10))
        # CS = (0.4*80 + 0.25*100 + 0.2*100 + 0.15*80) * 1.1 = 89 * 1.1 = 97.9
        self.assertEqual(out["cs"], 97.9)
        # DV = 0.4*100 + 0.35*50 + 0.25*50 = 70
        self.assertEqual(out["dv"], 70.0)
        # ceiling 11,000 >= target 10,000 -> M 1.10; glassdoor 3.6 -> Q 1.05
        self.assertEqual((p["M"], p["Q"], p["L"]), (1.10, 1.05, 100.0))
        # WP = min(100, (0.65*70 + 0.35*100) * 1.1 * 1.05) = min(100, 92.9775) = 92.98
        self.assertAlmostEqual(out["wp"], 93.0, places=0)
        self.assertEqual(out["fit"], round((97.9 * 92.9775) ** 0.5))
        self.assertEqual(out["verdict"], "Apply - high priority")
        self.assertTrue(out["priority_signal"])

    def test_experience_bands(self):
        e = fm.experience_delta
        self.assertEqual([e(None, 6), e(2, 6), e(6, 6), e(8, 6), e(10, 6)], [100, 70, 100, 85, 45])

    def test_paycut_rule_depends_on_direction(self):
        sal = EXAMPLE["worth"]["salary_myr_month"]
        self.assertEqual(fm.money_multiplier(7000, 80, sal)[0], 0.85)
        self.assertEqual(fm.money_multiplier(7000, 50, sal)[0], 0.60)
        self.assertEqual(fm.money_multiplier(None, 50, sal)[0], 0.90)
        self.assertEqual(fm.money_multiplier(9000, 50, sal)[0], 1.00)
        self.assertEqual(fm.money_multiplier(9000, 50, {})[0], 1.0)

    def test_foreign_salary_uses_only_the_users_rate(self):
        remote = inputs(location_category="Remote (open to Malaysia)", salary_text="USD 3,000 - 4,000 per month")
        bare = copy.deepcopy(EXAMPLE)
        bare["worth"].pop("fx_to_myr", None)
        no_rate = fm.score_job(remote, bare)
        self.assertIsNone(no_rate["parts"]["salary_ceiling_myr_month"])
        self.assertEqual(no_rate["parts"]["M"], 0.90)
        cfg = copy.deepcopy(EXAMPLE)
        cfg["worth"]["fx_to_myr"] = {"USD": 4.2}
        with_rate = fm.score_job(remote, cfg)
        self.assertEqual(with_rate["parts"]["salary_ceiling_myr_month"], 16800)
        self.assertEqual(with_rate["parts"]["M"], 1.10)
        low = fm.score_job(inputs(salary_text="USD 1,000 per month"), cfg)
        self.assertEqual(low["gate_failed"], "G3 salary")

    def test_required_goal_caps_direction(self):
        cfg = copy.deepcopy(EXAMPLE)
        cfg["direction"]["required_goal"] = "skills"
        out = fm.score_job(inputs(direction={"growth": 100, "skills": 0, "stability": 100}), cfg)
        self.assertEqual(out["dv"], 55.0)
        self.assertTrue(out["parts"]["dv_capped"])

    def test_invalid_agent_inputs_raise(self):
        with self.assertRaises(ValueError):
            fm.score_job(inputs(domain_tier=85), EXAMPLE)
        with self.assertRaises(ValueError):
            fm.score_job(inputs(direction={"growth": 75}), EXAMPLE)

    def test_lopsided_role_cannot_score_well(self):
        weak = inputs(requirements=[{"req": "x", "must": True, "score": 0}], domain_tier=40,
                      keyword_coverage_pct=10, required_years=9, employer_type="big4_or_top_consulting")
        out = fm.score_job(weak, EXAMPLE)
        self.assertLess(out["cs"], 40)
        self.assertEqual(out["verdict"], "Skip")

    def test_rubric_lists_every_goal_question(self):
        text = fm.rubric(EXAMPLE)
        for goal in EXAMPLE["direction"]["goals"]:
            self.assertIn(goal["question"], text)
        self.assertIn("do NOT compute", text)


class TestApply(unittest.TestCase):
    def test_writes_rank_fields_and_breakdown(self):
        with tempfile.TemporaryDirectory() as d:
            state = Path(d) / "seen_jobs.json"
            state.write_text(json.dumps({"seen": {
                "a_ops": {"title": "Ops Lead", "company": "A", "url": "u1", "status": "new", "salary": None},
                "b_ops": {"title": "Ops Mgr", "company": "B", "url": "u2", "status": "new"},
                "c_ops": {"title": "Ops", "company": "C", "url": "u3", "status": "new"},
            }}), encoding="utf-8")
            results = [
                {"key": "a_ops", "status": "scored", "fit_inputs": inputs(), "location_verdict": "PASS",
                 "language_gate": "PASS", "strengths": ["s1"], "gaps": ["g1"], "deadline": "2026-09-28"},
                {"key": "b_ops", "status": "scored", "fit_inputs": inputs(glassdoor=1.9), "location_verdict": "PASS"},
                {"key": "c_ops", "status": "expired"},
                {"key": "missing", "status": "scored", "fit_inputs": inputs()},
            ]
            out = fm.apply_results(results, EXAMPLE, state, date(2026, 9, 24))
            self.assertEqual([r["key"] for r in out["ranked"]], ["a_ops"])
            self.assertTrue(out["ranked"][0]["urgent"])
            self.assertEqual(out["vetoed"][0]["gate_failed"], "G4 employer rating")
            self.assertEqual(len(out["expired"]), 1)
            self.assertEqual(len(out["errors"]), 1)
            seen = json.loads(state.read_text(encoding="utf-8"))["seen"]
            self.assertEqual(seen["a_ops"]["status"], "ranked")
            self.assertEqual(seen["a_ops"]["rank_model"], "fit-model-v1")
            self.assertIn("parts", seen["a_ops"]["fit_breakdown"])
            self.assertEqual(seen["c_ops"]["status"], "expired")


if __name__ == "__main__":
    unittest.main()
