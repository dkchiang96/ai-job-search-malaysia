# Salaries in RM: how the numbers are worked out

Two separate questions, answered separately:

1. **What does this posting pay, in monthly RM?** This is parsing, done by
   `tools/myr_salary.py`.
2. **Is that enough for me?** This is judgment, and it uses only numbers
   *you* set at `/setup-malaysia`. Nothing is hard-coded, and nothing is
   guessed from your CV.

## 1. From posting text to monthly RM

Malaysian portals write pay many ways. `myr_salary.py` turns each into one
figure and records every assumption it made (`period_assumed`, `estimated`,
`currency_stated`), so no guess passes silently:

| Posting says | Parsed as | Rule |
|---|---|---|
| `RM 9,500 – RM 13,000 per month` (JobStreet) | 9,500-13,000 /month | stated |
| `4000 - 6000` (Hiredly raw) | 4,000-6,000 /month, *period assumed* | Malaysian convention: an unlabelled range is monthly... |
| `RM 180,000 - 240,000` | 15,000-20,000 /month, *period assumed* | ...unless the top figure is ≥ 100,000, which can only be annual |
| `RM 120,000 - 150,000 a year` | 10,000-12,500 /month | annual ÷ 12 |
| `RM15k - RM20k`, `RM 15 - 20k` | 15,000-20,000 | a `k` on the upper bound applies to both |
| `Up to RM 8,000` / `Sehingga RM 4,000` | max only | |
| `From RM 5,000` | min only | |
| `RM 3,500 sebulan` | monthly | BM period words understood |
| `RM 10,000 - 15,000 a month (Estimated)` (Indeed) | 10,000-15,000, **estimated** | an estimate never trips a salary floor |
| `RM 150 per day`, `RM 20 an hour` | parsed, **not converted** | working days vary too much to guess |
| `USD 4,000 - 5,500 per month` | USD, **not converted** | see the fx note below |
| `Negotiable`, `Competitive`, `Undisclosed` | no figure | never inferred |

What the figure means: the **stated monthly gross base**. Bonus months,
allowances and the employer's EPF share are **not** added. That's what a
posting's range means, and it keeps every job comparable. `/rank` mentions
bonuses or allowances in a job's strengths instead.

Try it: `python3 tools/myr_salary.py "RM 15 - 20k per month"`.

## 2. Your numbers, and what they do

`/setup-malaysia` asks for three optional monthly-RM figures. They're stored
only in `config/fit_model.json`, which is gitignored:

| Your figure | Plain question | What it does (Fit Model) |
|---|---|---|
| **Floor** | "Lowest base you'd accept at all?" | A posting whose **stated** ceiling is below it is dropped (gate G3). Estimates never drop a job. |
| **Current** | "What you earn now, or last earned?" | A job paying between your floor and current pay only scores well if it strongly matches your career direction. |
| **Target** | "What are you aiming for?" | A job at or above target gets a small boost (×1.10). |

The money multiplier the Fit Model applies:

| Posting's ceiling vs your figures | Multiplier |
|---|---|
| ≥ target | 1.10 |
| ≥ current | 1.00 |
| between floor and current, direction ≥ 70 | 0.85 |
| between floor and current, direction < 70 | 0.60 |
| below floor (stated, not estimated) | dropped (G3) |
| no figure stated | 0.90 |
| you set no figures | 1.00 for every job |

## How to choose your figures

- **Floor:** start from your fixed monthly costs, not your last salary. It's
  the number below which you'd genuinely say no.
- **Current:** your actual last base. If you're between jobs, use your last
  one.
- **Target:** anchor it to the market, not your history. Two sources:
  1. **Your own feed.** After a few weeks of searching:
     `python3 tools/job_store.py salary --title "your title"` gives RM
     percentiles from every posting you've seen that stated a figure, with
     employer-stated and portal-estimated figures kept apart. That's the
     market for *your* searches, not a national average.
  2. **Published salary guides.** Several recruitment firms publish annual
     Malaysia salary guides. Treat them as ranges for large employers. Upstream's
     `salary_lookup.py` was built for Danish data and isn't adapted here.

## Remote pay in other currencies

A USD or SGD figure is converted **only** with a rate you set yourself, in
`config/fit_model.json` → `worth.fx_to_myr` (e.g. `{"USD": 4.2}`). The code
never ships a live or built-in rate, because a stale rate would quietly
mis-score every remote job. Update it when the rate moves meaningfully.
