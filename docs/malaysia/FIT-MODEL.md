# The Fit Model: an optional scorer you configure

Upstream's `/rank` asks a scoring agent for four 0-100 numbers (technical,
experience, behavioural, career) and averages them. That works, but a "72"
is hard to check: nobody can say which fact in the posting produced it.

The Fit Model splits the job in two:

- **The agent reports facts**: which listed requirements you meet (1 / 0.5 /
  0), the job's domain tier, the years it asks for, your location category,
  and for each of *your* career goals whether the role delivers it
  (0 / 50 / 100). All of them can be checked against the posting.
- **A script does every calculation** (`tools/fit_model.py`), from the config
  `/setup-malaysia` built with you.

The same facts always give the same score, and each score traces back to
inputs you can read in `seen_jobs.json` → `fit_breakdown`.

## The layers

```
Layer 0  hard gates (stop, no score)
         G1 location  - verified location not in your list, or the remote check failed
         G2 domain    - over N% of the work is in your "would not do" list
         G3 salary    - a STATED ceiling below your floor (estimates never trip it)
         G4 employer  - employer rating below your minimum
         G5 years     - asks for more than your experience + a margin

Layer 1  CS  "will they shortlist me?"
         CS = (0.40 R + 0.25 D + 0.20 E + 0.15 K) × A
         R requirements met (must-haves count double) · D domain tier (100/70/40)
         E required years vs yours · K share of the posting's key terms you can honestly claim
         A employer-type multiplier (where you get call-backs: SME 1.10 ... big consultancies 0.70)

Layer 2  DV  "does it move me where I want to go?"
         DV = Σ weight × goal   - YOUR 1-4 goals, each answered 0 / 50 / 100
         optional must-have goal: if the role has none of it, DV is capped at 55

Layer 3  WP  "is it worth pursuing?"
         WP = (0.65 DV + 0.35 L) × M × Q
         L your location score · M money multiplier (SALARY.md) · Q employer-rating multiplier

Layer 4  FIT = round( √(CS × WP) )
         a geometric mean: a job can't score well by being strong on only one side
```

| FIT | Verdict |
|---|---|
| ≥ 70 | Apply - high priority (and if CS ≥ 75: worth a portal's limited "top choice" slot) |
| 55-69 | Apply |
| 40-54 | Apply if direction matters (only when DV ≥ 60, otherwise Skip) |
| < 40 | Skip |

## What makes it *yours*

Nothing about any one person is in the code. `/setup-malaysia` Section 7
interviews you and writes `config/fit_model.json` (gitignored):

- **Direction goals.** "What should your next role do for you?" You name 1-4
  goals, and each becomes a question a reader can answer from a posting. For
  example: *"Does the role add a team or seniority compared with my current
  level?"* or *"Will I use data and automation tools every day?"* You also set
  their weights, and whether one is a must-have.
- **Domain tiers**: industries that know you (100), that are close (70),
  and that would be a stretch (40).
- **Employer access**: which kinds of employer actually call you back.
- **Locations and their scores**, including remote if you opted in.
- **Salary floor / current / target** in RM (and your own FX rates).
- **Deal-breaker work** and your years of experience.

`config/fit_model.example.json` shows a complete example for a fictional
mid-career operations candidate. `python3 tools/fit_model.py rubric` prints
exactly what the scoring agent will be asked about your config.

## Using it

- It switches on automatically when `config/fit_model.json` exists. Use
  `/rank --scorer default` to use upstream's scorer for one run.
- `python3 tools/fit_model.py validate` catches weights that don't sum to 1,
  a floor above your target, a must-have goal that doesn't exist, and similar.
- It's just as honest as upstream: gates stop scoring, gaps are listed, and a
  job whose posting can't be read is never scored from its title.

## Calibrating

After a couple of weeks, look at jobs you felt strongly about that scored
oddly. The breakdown shows which input caused it. Usually the fix is a goal
question that's worded too loosely, or a domain tier. Change the config, not
the scores, then run `/rank --all` to re-score.

## Origin

The model began as the author's own scorer: a headhunter-style formula tuned
to one person's career, with goals and salary tiers hard-coded. For this fork
it was rebuilt so that every personal element comes from setup, and the
arithmetic is covered by `tests/test_fit_model.py`.
