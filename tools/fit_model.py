#!/usr/bin/env python3
"""Fit Model - an optional, deterministic alternative scorer for /rank.

/rank's default scorer asks each agent for four 0-100 dimension scores and
averages them. The Fit Model splits the work differently: the agent only
*reads* the posting and reports small, checkable facts (which requirements you
meet, the domain tier, required years, which of your career goals the role
feeds, the location category), and this script does every piece of arithmetic
from a config file you built at setup. The same inputs always give the same
score, and every number in the output traces to one input.

    Layer 0  hard gates   G1 location · G2 domain · G3 salary · G4 employer rating · G5 experience
    Layer 1  CS  candidacy strength   = (wR·R + wD·D + wE·E + wK·K) × A        "will they shortlist me?"
    Layer 2  DV  direction value      = Σ weight_g · goal_g  (optional cap)     "does it move me forward?"
    Layer 3  WP  worth pursuing       = (wDV·DV + wL·L) × M × Q
    Layer 4  FIT = round(√(CS × WP))  - a geometric mean, so a lopsided role can't score well

Nothing personal is hard-coded here. Your locations, salary floor/target, domain
tiers, employer preferences and 1-4 direction goals live in config/fit_model.json
(gitignored), which /setup-malaysia writes by interviewing you.
config/fit_model.example.json shows the shape.

Usage:
  python3 tools/fit_model.py validate [--config PATH]
  python3 tools/fit_model.py rubric   [--config PATH]           # compact text for /rank's agent prompt
  python3 tools/fit_model.py score    --input job.json [--config PATH]
  python3 tools/fit_model.py apply    --results results.json [--config PATH] [--state PATH] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import myr_salary  # noqa: E402

DEFAULT_CONFIG = ROOT / "config" / "fit_model.json"
EXAMPLE_CONFIG = ROOT / "config" / "fit_model.example.json"
STATE = ROOT / "job_scraper" / "seen_jobs.json"
SCORE_MODEL = "fit-model-v1"
URGENT_DAYS = 7


class ConfigError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config(path: Path = DEFAULT_CONFIG) -> dict:
    if not path.exists():
        raise ConfigError(
            f"{path} not found - run /setup-malaysia (Fit Model section) or copy "
            "config/fit_model.example.json to config/fit_model.json and edit it"
        )
    cfg = json.loads(path.read_text(encoding="utf-8"))
    validate_config(cfg)
    return cfg


def _close(a: float, b: float) -> bool:
    return abs(a - b) < 1e-6


def validate_config(cfg: dict) -> None:
    """Raise ConfigError naming the first problem found."""
    try:
        g = cfg["gates"]
        c = cfg["candidacy"]
        d = cfg["direction"]
        w = cfg["worth"]
    except (KeyError, TypeError) as exc:
        raise ConfigError(f"missing top-level section {exc}") from None

    locs = w.get("location_scores")
    if not isinstance(locs, dict) or not locs:
        raise ConfigError("worth.location_scores must map location categories to 0-100")
    for k, v in locs.items():
        if not isinstance(v, (int, float)) or not 0 <= v <= 100:
            raise ConfigError(f"worth.location_scores[{k!r}] must be 0-100")

    cw = c.get("weights", {})
    if set(cw) != {"requirements", "domain", "experience", "keywords"} or not _close(sum(cw.values()), 1.0):
        raise ConfigError("candidacy.weights needs requirements/domain/experience/keywords summing to 1.0")
    if not isinstance(c.get("employer_access"), dict) or not c["employer_access"]:
        raise ConfigError("candidacy.employer_access must map employer types to multipliers")
    if not isinstance(c.get("domain_tiers"), dict):
        raise ConfigError("candidacy.domain_tiers must map '100'/'70'/'40' to example domains")

    goals = d.get("goals")
    if not isinstance(goals, list) or not 1 <= len(goals) <= 4:
        raise ConfigError("direction.goals needs 1-4 goals")
    ids = [goal.get("id") for goal in goals]
    if len(set(ids)) != len(ids) or not all(ids):
        raise ConfigError("direction.goals ids must be unique and non-empty")
    if not _close(sum(goal.get("weight", 0) for goal in goals), 1.0):
        raise ConfigError("direction.goals weights must sum to 1.0")
    for goal in goals:
        if not goal.get("question"):
            raise ConfigError(f"direction goal {goal.get('id')!r} needs a question the scorer answers")
    req = d.get("required_goal")
    if req is not None and req not in ids:
        raise ConfigError(f"direction.required_goal {req!r} is not one of the goal ids {ids}")

    ww = w.get("weights", {})
    if set(ww) != {"direction", "location"} or not _close(sum(ww.values()), 1.0):
        raise ConfigError("worth.weights needs direction/location summing to 1.0")

    sal = w.get("salary_myr_month") or {}
    floor, current, target = sal.get("floor"), sal.get("current"), sal.get("target")
    figures = [x for x in (floor, current, target) if x is not None]
    if any(not isinstance(x, (int, float)) or x <= 0 for x in figures):
        raise ConfigError("worth.salary_myr_month figures must be positive monthly MYR amounts or null")
    if figures != sorted(figures):
        raise ConfigError("worth.salary_myr_month must satisfy floor <= current <= target")

    if not isinstance(g.get("experience_years"), (int, float)):
        raise ConfigError("gates.experience_years must be your years of relevant experience")


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def requirement_match(reqs: list | None) -> tuple[float, str]:
    """R: 1.0 proven, 0.5 partial/adjacent, 0 gap; must-haves weigh 2x."""
    if not reqs:
        return 50.0, "no requirements listed - neutral 50"
    got = possible = 0.0
    for r in reqs:
        weight = 2.0 if r.get("must", True) else 1.0
        s = float(r.get("score", 0))
        if s not in (0.0, 0.5, 1.0):
            raise ValueError(f"requirement score must be 0, 0.5 or 1, got {s}")
        got += s * weight
        possible += weight
    return round(got / possible * 100, 1), f"{got:g}/{possible:g} weighted"


def experience_delta(required: float | None, have: float) -> float:
    """E: how the posting's required years compare with yours."""
    if required is None:
        return 100.0
    if required <= have - 4:
        return 70.0  # over-qualification screen-out risk
    if required <= have:
        return 100.0
    if required <= have + 2:
        return 85.0
    return 45.0  # +3..+overshoot_max; beyond that G5 already stopped it


def monthly_ceiling_myr(parsed: dict | None, fx: dict) -> tuple[int | None, str | None]:
    """Monthly MYR ceiling of a parsed salary. A non-MYR figure (a remote role
    paid in USD/SGD) is converted only with a rate *you* set in
    worth.fx_to_myr - never a rate baked into the code, which would go stale."""
    if not parsed:
        return None, None
    top = parsed["max"] if parsed["max"] is not None else parsed["min"]
    if parsed["currency"] == "MYR":
        return (parsed["monthly_max"] if parsed["monthly_max"] is not None else parsed["monthly_min"]), None
    rate = fx.get(parsed["currency"])
    if top is None or not rate or parsed["period"] not in ("month", "year"):
        return None, f"{parsed['currency']} figure not converted (no fx_to_myr rate set)"
    monthly = top / 12 if parsed["period"] == "year" else top
    return round(monthly * rate), f"{parsed['currency']} converted at your rate {rate}"


def money_multiplier(ceiling: int | None, dv: float, sal: dict) -> tuple[float, str]:
    floor, current, target = sal.get("floor"), sal.get("current"), sal.get("target")
    if floor is None and current is None and target is None:
        return 1.0, "no salary targets configured"
    if ceiling is None:
        return float(sal.get("no_data", 0.90)), "no salary stated"
    if target is not None and ceiling >= target:
        return 1.10, f"RM{ceiling:,} >= target"
    if current is not None and ceiling >= current:
        return 1.00, f"RM{ceiling:,} >= current"
    if current is None and target is None:
        return 1.00, f"RM{ceiling:,} clears floor"
    threshold = sal.get("paycut_needs_direction", 70)
    if dv >= threshold:
        return 0.85, f"RM{ceiling:,} below current, but direction {dv:g} >= {threshold}"
    return 0.60, f"RM{ceiling:,} below current and direction {dv:g} < {threshold}"


def risk_multiplier(glassdoor: float | None, distress: bool) -> float:
    if glassdoor is None:
        q = 0.95
    elif glassdoor >= 3.5:
        q = 1.05
    elif glassdoor >= 3.0:
        q = 1.00
    else:
        q = 0.75
    return round(q - (0.10 if distress else 0.0), 2)


def band(fit: int, dv: float, cfg: dict) -> str:
    b = cfg.get("verdict_bands", {})
    high, std, cond = b.get("apply_high", 70), b.get("apply", 55), b.get("apply_if_direction", 40)
    if fit >= high:
        return "Apply - high priority"
    if fit >= std:
        return "Apply"
    if fit >= cond:
        return "Apply if direction matters" if dv >= b.get("direction_threshold", 60) else "Skip"
    return "Skip"


def score_job(inp: dict, cfg: dict, stored_salary: str | None = None) -> dict:
    """Score one job from its fit_inputs. Returns the full breakdown."""
    g, c, d, w = cfg["gates"], cfg["candidacy"], cfg["direction"], cfg["worth"]
    out: dict = {"model": SCORE_MODEL}

    # ---- Layer 0: gates -------------------------------------------------
    category = inp.get("location_category")
    salary_text = inp.get("salary_text") or stored_salary
    parsed = myr_salary.parse_salary(salary_text)
    ceiling, fx_note = monthly_ceiling_myr(parsed, w.get("fx_to_myr") or {})
    floor = (w.get("salary_myr_month") or {}).get("floor")
    have = float(g["experience_years"])
    required = inp.get("required_years")

    gate = None
    if inp.get("location_verdict") == "FAIL":
        gate = ("G1 location", inp.get("location_note") or "location verdict FAIL (relocation, hybrid elsewhere, or a remote role closed to Malaysia)")
    elif category not in w["location_scores"]:
        gate = ("G1 location", f"location category {category!r} is not in your accepted list")
    elif float(inp.get("domain_exclusion_pct") or 0) > g.get("domain_exclusion_max_pct", 40):
        gate = ("G2 domain", f"{inp.get('domain_exclusion_pct')}% of the core work is in your exclusion list")
    elif floor and ceiling is not None and ceiling < floor and not (parsed or {}).get("estimated"):
        gate = ("G3 salary", f"stated ceiling RM{ceiling:,}/month is below your floor RM{floor:,}")
    elif inp.get("glassdoor") is not None and float(inp["glassdoor"]) < g.get("glassdoor_min", 2.5):
        gate = ("G4 employer rating", f"rating {inp['glassdoor']} is below {g.get('glassdoor_min', 2.5)}")
    elif required is not None and float(required) > have + g.get("experience_overshoot_max", 4):
        gate = ("G5 experience", f"asks for {required} years; you have {have:g}")
    if gate:
        out.update({"gate_failed": gate[0], "gate_reason": gate[1], "fit": 0, "verdict": f"Skip ({gate[0]})"})
        return out

    # ---- Layer 1: candidacy strength -------------------------------------
    R, r_note = requirement_match(inp.get("requirements"))
    D = float(inp.get("domain_tier", 40))
    if D not in (0.0, 40.0, 70.0, 100.0):
        raise ValueError(f"domain_tier must be 0/40/70/100, got {D}")
    E = experience_delta(None if required is None else float(required), have)
    K = float(inp.get("keyword_coverage_pct", 50))
    access = c["employer_access"]
    A = float(access.get(inp.get("employer_type"), 1.0))
    pen = c.get("applicant_penalty", {})
    if inp.get("applicants") is not None and inp["applicants"] > pen.get("threshold", 600):
        A -= pen.get("minus", 0.10)
    A = min(max(A, 0.60), 1.10)
    cw = c["weights"]
    CS = min(100.0, (cw["requirements"] * R + cw["domain"] * D + cw["experience"] * E + cw["keywords"] * K) * A)

    # ---- Layer 2: direction value -----------------------------------------
    answers = inp.get("direction") or {}
    DV = 0.0
    for goal in d["goals"]:
        v = float(answers.get(goal["id"], 0))
        if v not in (0.0, 50.0, 100.0):
            raise ValueError(f"direction {goal['id']} must be 0/50/100, got {v}")
        DV += goal["weight"] * v
    req_goal = d.get("required_goal")
    capped = False
    if req_goal and float(answers.get(req_goal, 0)) == 0 and DV > d.get("cap_if_required_zero", 55):
        DV, capped = float(d.get("cap_if_required_zero", 55)), True

    # ---- Layer 3: worth pursuing ------------------------------------------
    L = float(w["location_scores"][category])
    M, m_note = money_multiplier(ceiling, DV, w.get("salary_myr_month") or {})
    Q = risk_multiplier(inp.get("glassdoor"), bool(inp.get("recent_distress")))
    ww = w["weights"]
    WP = min(100.0, (ww["direction"] * DV + ww["location"] * L) * M * Q)

    # ---- Layer 4 ------------------------------------------------------------
    fit = round(math.sqrt(CS * WP))
    verdict = band(fit, DV, cfg)
    out.update({
        "fit": fit,
        "verdict": verdict,
        "priority_signal": fit >= cfg.get("verdict_bands", {}).get("apply_high", 70) and CS >= 75,
        "cs": round(CS, 1), "dv": round(DV, 1), "wp": round(WP, 1),
        "parts": {
            "R": R, "R_note": r_note, "D": D, "E": E, "K": K, "A": round(A, 2),
            "L": L, "M": M, "M_note": m_note, "Q": Q, "dv_capped": capped,
            "salary_ceiling_myr_month": ceiling, "fx_note": fx_note,
        },
    })
    return out


# ---------------------------------------------------------------------------
# Rubric text for the scoring agents (what they must report, not how to add up)
# ---------------------------------------------------------------------------

def rubric(cfg: dict) -> str:
    g, c, d, w = cfg["gates"], cfg["candidacy"], cfg["direction"], cfg["worth"]
    lines = [
        "FIT MODEL - report these fit_inputs per job; do NOT compute any score yourself.",
        f"location_category: one of {list(w['location_scores'])} (use the verified location - a mislabeled",
        "  'Remote' that fails the Remote-Work Verification Gate is its real location, or omit the job).",
        f"domain_exclusion_pct: % of core responsibilities inside these exclusions: {g.get('domain_exclusions', [])}",
        "salary_text: the posting's pay text verbatim, or null.",
        "glassdoor: employer rating if the posting/portal shows one, else null. recent_distress: true only if the posting itself mentions layoffs/restructuring.",
        "required_years: the stricter of general vs named-skill years required, or null.",
        "requirements: [{req, must: true|false, score: 1 (proven in profile) | 0.5 (adjacent) | 0 (gap)}] for every listed requirement.",
        f"domain_tier: 100 if like {c['domain_tiers'].get('100', [])}; 70 if like {c['domain_tiers'].get('70', [])};",
        f"  40 if like {c['domain_tiers'].get('40', [])} or unfamiliar; 0 only if G2 applies.",
        "keyword_coverage_pct: % of the posting's 10 most repeated role nouns you can honestly claim.",
        f"employer_type: one of {list(c['employer_access'])}. applicants: the count if shown, else null.",
        "direction: answer each 0 (none) / 50 (some) / 100 (strong):",
    ]
    for goal in d["goals"]:
        lines.append(f"  {goal['id']}: {goal['question']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Writing results into seen_jobs.json (mirrors tools/rank_state.py apply)
# ---------------------------------------------------------------------------

def apply_results(results: list, cfg: dict, state: Path, today: date, dry_run: bool = False) -> dict:
    from rank_state import entry_location_verdict, load_state, parse_iso, save_state

    doc, seen = load_state(state)
    rows, expired, gated, errors = [], [], [], []
    for result in results:
        key = result.get("key")
        entry = seen.get(key)
        if entry is None:
            errors.append({"key": key, "error": "no such key in seen_jobs.json"})
            continue
        if result.get("status") == "expired":
            entry["status"] = "expired"
            expired.append({"key": key, "title": entry.get("title"), "company": entry.get("company"), "url": entry.get("url")})
            continue
        inputs = dict(result.get("fit_inputs") or {})
        inputs.setdefault("location_verdict", result.get("location_verdict"))
        if result.get("location_note"):
            inputs.setdefault("location_note", result["location_note"])
        try:
            breakdown = score_job(inputs, cfg, stored_salary=entry.get("salary"))
        except (ValueError, KeyError, TypeError) as exc:
            errors.append({"key": key, "error": f"fit_inputs: {exc}"})
            continue

        legacy = entry_location_verdict(entry)
        if entry.get("location") in ("PASS", "FAIL", "FLAG"):
            entry.pop("location", None)
        entry["status"] = "ranked"
        entry["rank_score"] = breakdown["fit"]
        entry["rank_verdict"] = breakdown["verdict"]
        entry["rank_date"] = today.isoformat()
        entry["rank_model"] = SCORE_MODEL
        entry["fit_breakdown"] = breakdown
        entry["location_verdict"] = result.get("location_verdict") or legacy or "PASS"
        entry["language_gate"] = result.get("language_gate") or "PASS"
        if entry["language_gate"] == "PASS":
            entry.pop("language_note", None)
        else:
            entry["language_note"] = result.get("language_note")
        if result.get("deadline"):
            entry["deadline"] = result["deadline"]
        for field in ("strengths", "gaps"):
            value = result.get(field)
            if isinstance(value, list):
                entry[field] = [str(b) for b in value][:3]

        parsed = parse_iso(entry.get("deadline"))
        row = {
            "key": key, "title": entry.get("title"), "company": entry.get("company"),
            "location": entry.get("location"), "url": entry.get("url"),
            "score": breakdown["fit"], "verdict": breakdown["verdict"],
            "cs": breakdown.get("cs"), "dv": breakdown.get("dv"), "wp": breakdown.get("wp"),
            "priority_signal": breakdown.get("priority_signal", False),
            "location_verdict": entry["location_verdict"], "language_gate": entry["language_gate"],
            "language_note": entry.get("language_note"), "deadline": entry.get("deadline"),
            "posted_date": entry.get("posted_date"),
            "urgent": bool(parsed and today <= parsed <= today + timedelta(days=URGENT_DAYS)),
            "strengths": entry.get("strengths", []), "gaps": entry.get("gaps", []),
        }
        if breakdown.get("gate_failed"):
            row["gate_failed"], row["gate_reason"] = breakdown["gate_failed"], breakdown["gate_reason"]
            gated.append(row)
        else:
            rows.append(row)

    if not dry_run:
        save_state(state, doc)
    rows.sort(key=lambda r: (r["score"], r["urgent"]), reverse=True)
    veto = lambda r: r["location_verdict"] == "FAIL" or r["language_gate"] == "FAIL"  # noqa: E731
    return {
        "ranked": [r for r in rows if not veto(r)],
        "vetoed": [r for r in rows if veto(r)] + gated,
        "expired": expired,
        "errors": errors,
        "written": not dry_run,
    }


def _force_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate")
    sub.add_parser("rubric")
    p_score = sub.add_parser("score")
    p_score.add_argument("--input", type=Path, required=True)
    p_apply = sub.add_parser("apply")
    p_apply.add_argument("--results", type=Path, required=True)
    p_apply.add_argument("--state", type=Path, default=STATE)
    p_apply.add_argument("--today", type=date.fromisoformat, default=date.today())
    p_apply.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    try:
        cfg = load_config(args.config)
    except (ConfigError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1

    if args.cmd == "validate":
        print(json.dumps({"ok": True, "config": str(args.config), "goals": [g["id"] for g in cfg["direction"]["goals"]]}))
        return 0
    if args.cmd == "rubric":
        print(rubric(cfg))
        return 0
    if args.cmd == "score":
        inp = json.loads(args.input.read_text(encoding="utf-8"))
        print(json.dumps(score_job(inp.get("fit_inputs", inp), cfg, inp.get("salary")), indent=2, ensure_ascii=False))
        return 0
    results = json.loads(args.results.read_text(encoding="utf-8"))
    if isinstance(results, dict):
        results = results.get("results", [])
    out = apply_results(results, cfg, args.state, args.today, args.dry_run)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 1 if out["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
