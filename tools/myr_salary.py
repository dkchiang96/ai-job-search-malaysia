#!/usr/bin/env python3
"""Normalise Malaysian job-posting salary text into monthly MYR figures.

Malaysian portals state pay in several shapes, and scoring needs one number:

    JobStreet   "RM 9,500 – RM 13,000 per month"
    Hiredly     "RM 4,000 - RM 6,000 / month"   (hiredly-search output; raw "4000 - 6000")
    Indeed      "RM 10,000 - RM 15,000 a month" (often Indeed's own *estimate*)
    Others      "MYR 5,000.00 - 8,000.00/mth (Negotiable)", "RM15k - RM20k",
                "Up to RM 8,000", "From RM 5,000", "RM 120,000 - 150,000 a year"

Rules (every one is a documented assumption, never a silent guess):

  * Monthly is the Malaysian convention. A range with no stated period is read
    as monthly - unless its upper figure is 100,000 or more, which no monthly
    salary here plausibly reaches, so it is read as annual. Either way
    `period_assumed` is true so a reader knows the period was inferred.
  * Annual figures are divided by 12 for the monthly view. Bonus months,
    allowances and the employer's EPF share are NOT added - the figure is the
    stated base, which is what a posting's range means.
  * Weekly, daily and hourly rates are parsed but never converted to monthly
    (working days vary too much); `monthly_*` stay null and the period says
    why. Indeed uses "a week" ("From RM 1,000 a week").
  * Non-MYR currencies (SGD, USD, ...) are parsed with their currency and left
    unconverted - an FX rate baked in here would silently go stale.
  * "Undisclosed", "Negotiable", "Competitive" and similar yield no figures.
  * A text containing "estimate" (Indeed's disclosure) sets `estimated`, so the
    figure is not treated as employer-verified.

Usage:
  python3 tools/myr_salary.py "RM 5k - 8k per month"
  python3 tools/myr_salary.py --stdin < salaries.txt     # one per line, JSON lines out
"""

from __future__ import annotations

import argparse
import json
import re
import sys

_CURRENCIES = {
    "RM": "MYR", "MYR": "MYR",
    "SGD": "SGD", "S$": "SGD",
    "USD": "USD", "US$": "USD", "$": "USD",
    "EUR": "EUR", "€": "EUR", "GBP": "GBP", "£": "GBP",
    "AUD": "AUD", "A$": "AUD", "HKD": "HKD", "HK$": "HKD",
    "IDR": "IDR", "RP": "IDR", "THB": "THB", "฿": "THB",
}
_CURRENCY_RE = re.compile(r"(MYR|RM|SGD|S\$|US\$|USD|EUR|€|GBP|£|AUD|A\$|HKD|HK\$|IDR|Rp|THB|฿|\$)", re.IGNORECASE)
_NUMBER_RE = re.compile(r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*([kK])?(?![\d,])")
_NO_FIGURE_RE = re.compile(r"\b(undisclosed|negotiable|competitive|not (?:disclosed|specified)|attractive)\b", re.IGNORECASE)

_PERIODS = [
    ("year", re.compile(r"(per\s+(?:year|annum)|a\s+year|/\s*(?:yr|year|annum)|p\.?\s*a\.?(?![a-z])|annual(?:ly)?|yearly)", re.IGNORECASE)),
    ("month", re.compile(r"(per\s+month|a\s+month|/\s*(?:mth|mo|month)\b|monthly|\bmth\b|sebulan|bulanan)", re.IGNORECASE)),
    ("week", re.compile(r"(per\s+week|a\s+week|/\s*(?:wk|week)\b|weekly|seminggu)", re.IGNORECASE)),
    ("day", re.compile(r"(per\s+day|a\s+day|/\s*day|daily|sehari)", re.IGNORECASE)),
    ("hour", re.compile(r"(per\s+hour|an\s+hour|/\s*(?:hr|hour)|hourly|sejam)", re.IGNORECASE)),
]

ANNUAL_THRESHOLD = 100_000  # an unlabelled figure at or above this is annual


def _to_number(num: str, k: str | None) -> float:
    value = float(num.replace(",", ""))
    return value * 1000 if k else value


def parse_salary(text: str | None) -> dict | None:
    """Return a dict describing the salary, or None when the text carries no figure."""
    if text is None:
        return None
    raw = str(text).strip()
    if not raw or (_NO_FIGURE_RE.search(raw) and not re.search(r"\d", raw)):
        return None

    currency_match = _CURRENCY_RE.search(raw)
    currency = _CURRENCIES.get(currency_match.group(1).upper(), "MYR") if currency_match else "MYR"
    currency_stated = currency_match is not None

    # Drop anything in parentheses except figures ("(Negotiable)", "(Estimated)").
    scan = re.sub(r"\((?![^)]*\d)[^)]*\)", " ", raw)
    numbers = [_to_number(n, k) for n, k in _NUMBER_RE.findall(scan)]
    # A bare "k" suffix on only the upper bound ("15 - 20k") applies to both.
    pairs = _NUMBER_RE.findall(scan)
    if len(pairs) >= 2 and not pairs[0][1] and pairs[1][1] and numbers[0] < 1000:
        numbers[0] *= 1000
    numbers = [n for n in numbers if n > 0]
    if not numbers:
        return None

    lowered = raw.lower()
    if re.search(r"\bup\s*to\b|\bmax(?:imum)?\b|\bsehingga\b", lowered) and len(numbers) == 1:
        lo, hi = None, numbers[0]
    elif re.search(r"\b(from|min(?:imum)?|starting|at least|dari)\b", lowered) and len(numbers) == 1:
        lo, hi = numbers[0], None
    elif len(numbers) >= 2:
        lo, hi = min(numbers[:2]), max(numbers[:2])
    else:
        lo = hi = numbers[0]

    period = next((name for name, rx in _PERIODS if rx.search(raw)), None)
    period_assumed = period is None
    if period is None:
        top = hi if hi is not None else lo
        period = "year" if top is not None and top >= ANNUAL_THRESHOLD else "month"

    def monthly(v: float | None) -> int | None:
        if v is None or currency != "MYR":
            return None
        if period == "month":
            return round(v)
        if period == "year":
            return round(v / 12)
        return None  # week / day / hour: never converted

    return {
        "raw": raw,
        "currency": currency,
        "currency_stated": currency_stated,
        "min": lo,
        "max": hi,
        "period": period,
        "period_assumed": period_assumed,
        "monthly_min": monthly(lo),
        "monthly_max": monthly(hi),
        "estimated": "estimate" in lowered,
    }


def monthly_ceiling(text: str | None) -> int | None:
    """The highest monthly MYR figure a posting states (its max, else its min).

    This is the figure a salary floor is compared against: a posting whose
    ceiling is below your floor cannot pay your floor."""
    parsed = parse_salary(text)
    if not parsed:
        return None
    return parsed["monthly_max"] if parsed["monthly_max"] is not None else parsed["monthly_min"]


def _force_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("text", nargs="?", help="salary text to parse")
    ap.add_argument("--stdin", action="store_true", help="read one salary text per line from stdin")
    args = ap.parse_args(argv)
    if args.stdin:
        for line in sys.stdin:
            line = line.rstrip("\n")
            if line.strip():
                print(json.dumps(parse_salary(line), ensure_ascii=False))
        return 0
    if args.text is None:
        ap.error("give a salary text or --stdin")
    print(json.dumps(parse_salary(args.text), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
