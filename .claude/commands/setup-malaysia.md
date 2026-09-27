# /setup-malaysia - Malaysia Setup (run after /setup)

`/setup` builds your profile the way upstream designed it. `/setup-malaysia`
then adds everything specific to job-hunting in Malaysia: which states you'll
work in, **whether you also want remote roles**, how JobStreet and Indeed reach you
(email alerts, or not at all if you'd rather), your salary numbers in RM, your CV format (LaTeX or your own
Word file), and the optional extras. Every section can be skipped, and
re-running it only changes the sections you pick (`/setup-malaysia remote`,
`/setup-malaysia salary`, ...).

Ask one section at a time, in plain language. After each answer, say in one
line what you will write and where. Nothing personal is ever written to a
tracked file except what upstream's `/setup` already writes there (the profile
files and `search-queries.md`). Everything else goes to `config/` and
`gmail_alerts/`, which are gitignored.

**Before starting:** check that `/setup` has run (CLAUDE.md's Identity section
no longer holds `[YOUR_NAME]`). If it hasn't, ask the user to run `/setup`
first and stop.

---

## Section 1: Where you'll work

Ask:
1. "Which state or area do you live in?"
2. "Which areas would you commute to every day?" Offer the Klang Valley
   default (KL, Petaling Jaya, Subang, Shah Alam, Cyberjaya, Putrajaya) and let
   them trim or extend it.
3. "Anywhere you'd consider only for the right role?" For example Penang, JB,
   Singapore, or relocating.

Write:
- The Location tiers in `search-queries.md`'s **Malaysia** section (`[MY_IDEAL_AREAS]`, `[MY_ACCEPTABLE_AREAS]`, `[MY_STRETCH_AREAS]`).
- `config/malaysia.json` → `"locations": {"ideal": [...], "acceptable": [...], "stretch": [...]}`.

## Section 2: Remote work (make this choice explicit)

Explain first, in three short lines:

> Besides Malaysian jobs, you can also search remote jobs that hire people
> living in Malaysia, usually for foreign companies, often paid in USD, and
> sometimes as a contractor rather than an employee. Many "remote" jobs turn
> out to be US-only or hybrid. This fork checks every one before it reaches
> your shortlist.

Then ask: **"Do you want (a) Malaysia-based roles only, or (b) Malaysia-based
roles and remote roles open to Malaysia?"**

If **(b)**:
- Ask which hours they could reliably overlap with (e.g. "evenings until
  11pm", "no night work") and whether contractor roles are acceptable. Store
  both in `config/malaysia.json` → `"remote": {"enabled": true, "overlap": "...", "contractor_ok": true|false}`.
- Set `enabled: true` in the frontmatter of `.agents/skills/remoteok-search/SKILL.md`,
  `weworkremotely-search/SKILL.md` and `workingnomads-search/SKILL.md`.
- Fill `[MY_REMOTE_KEYWORD]` in `search-queries.md`'s **Remote roles** section
  with 1-3 short, generic keywords for their function (remote boards match
  single words better than full titles).
- Point them to `docs/malaysia/REMOTE.md` (EOR vs contractor, EPF/SOCSO,
  tax, getting paid).

If **(a)**: leave the three remote boards `enabled: false`, delete the
**Remote roles** section from `search-queries.md`, and write `"remote":
{"enabled": false}`. Say they can switch later with `/setup-malaysia remote`.

## Section 3: Work rights and languages

1. "Are you a Malaysian citizen, a PR, or on a pass (EP, DP, RP-T...)?" This
   drives the Eligibility Gate's "Malaysian only" handling
   (`12-malaysia-market.md` §4). Write `config/malaysia.json` → `"work_rights": "citizen"|"pr"|"<pass>"`.
2. Check CLAUDE.md's Languages table. For Malaysia, make sure **English**,
   **Bahasa Malaysia**, **Mandarin** and **Cantonese / Tamil / others** are each
   either listed with an honest level or deliberately absent. Postings here
   often require one of them (`12-malaysia-market.md` §3). Update the table
   only with the user's confirmation. It is upstream's tracked profile file,
   so the privacy note from `/setup` applies.

## Section 4: Salary in RM

Explain: Malaysian postings quote **monthly gross base in RM**. Ask for three
numbers, each optional:
- **Floor**: "the lowest monthly base you would accept at all"
- **Current or last base**: "what you earn now, or earned last"
- **Target**: "what you're aiming for"

Explain what each does. Below the floor, a job is dropped (only when the
posting states a real figure; estimates never drop a job). Between the floor
and your current pay, a job has to be strongly on-direction to score well.
Above target, it scores a little higher. Ask whether they'd like to set an
exchange rate for USD/SGD-paid remote roles (they must update it themselves;
nothing is fetched).

Write the figures to `config/fit_model.json` → `worth.salary_myr_month` and
`worth.fx_to_myr` if they choose the Fit Model (Section 7), otherwise to
`config/malaysia.json` → `"salary_myr_month"`. **Never** write them to any
tracked file. The method is in `docs/malaysia/SALARY.md`.

## Section 5: JobStreet, Indeed and LinkedIn email alerts

Explain why (JobStreet and Indeed block automated search, but their own email
alerts are fine). Then **ask before anything else**: *"This part lets a script
on your computer read your job-alert emails. Only job title, company,
location, salary and link reach me, never an email. Would you like to (a)
connect your main Gmail, (b) use a separate Gmail just for job alerts, or (c)
skip it for now?"* Summarise the doc's "Privacy" section if they hesitate, and
treat (c) as a perfectly good answer: `/scrape` still covers LinkedIn, Hiredly
and freehire.

For (a) or (b), walk them through `docs/malaysia/JOB-ALERTS.md` one step at a
time:
1. Plan the saved searches with the worksheet in that doc: **10 JobStreet
   alerts at most**, plus Indeed and LinkedIn alerts. Scope most to a city, not
   "Remote", and set each to daily. For (b), sign up to the alerts with the new
   address, or forward those senders to it.
2. Create the Gmail filters and labels for the portals they use (the exact
   filter strings are in the doc).
3. Enable IMAP, create a Gmail app password, and put both lines in
   `gmail_alerts/.env`. **The user types the password into that file
   themselves. Never ask for it in chat.**
4. Test: `python3 tools/gmail_imap_fetch.py run --dry-run`.

If they'd rather skip this now, say `/gmail-alerts` will explain what's
missing when they run it.

## Section 6: CV format

Ask: **"Do you want (a) the stock LaTeX CV (needs a TeX install), or (b) your
own Word resume, edited in place so it keeps its exact look?"**

- **(a)**: nothing to do. Upstream's templates are active by default.
- **(b)**: ask them to put their real `.docx` resume in `documents/cv/`
  (gitignored). Then run `/add-template` with it, following
  `10-docx-editing.md`'s `/add-template` notes. If they don't have one they
  like, offer the shipped placeholder design `templates/cv/clean-resume/`,
  filled with their details into a copy in `documents/cv/`. Check that Word
  or LibreOffice is available (`tools/docx_to_pdf.ps1` or `soffice`) and say
  plainly if neither is.

## Section 7: Scorer (optional)

Explain: `/rank` has a default scorer (upstream's). This fork adds an
optional **Fit Model**: the scoring agent only reports facts, and a script
does the arithmetic from your own settings, so every score can be checked.
Ask if they want it. If yes, interview them to build `config/fit_model.json`
from `config/fit_model.example.json`:

1. **Experience**: "How many years of relevant experience do you have?" → `gates.experience_years`.
2. **Deal-breaker work**: "What kinds of work would you not take on, even at a
   good salary?" → `gates.domain_exclusions` (short phrases).
3. **Industries**: "Which industries know you best?" → `domain_tiers["100"]`.
   "Which are close enough?" → `"70"`. "Which would be a stretch?" → `"40"`.
4. **Employers**: "Which kinds of employers usually call you back: startups
   and SMEs, mid-size firms, MNCs, GLCs?" Set `candidacy.employer_access`
   multipliers from their answer. Where you usually get calls, 1.10. Neutral,
   1.00. Rarely or never, 0.70-0.85. Keep every value between 0.60 and 1.10.
5. **Direction goals (the part that makes it yours)**: "What should your next
   role do for you? Name 1-4 things." Examples: more seniority, a skill you
   want to build, stability, a sector switch, flexibility, a path to
   starting something. For each goal, write **one yes/no-style question a
   reader could answer from a job posting**, confirm the wording with them,
   and agree weights that sum to 1.0. Ask whether one goal is a must-have. If
   so, set `required_goal` (a role with none of it has its direction score
   capped at 55).
6. **Locations**: turn Section 1 (and Section 2's remote choice) into
   `worth.location_scores`. Ideal 95-100, acceptable 70-90, stretch 50-65, and
   remote per their preference. Leave out any place that should drop a job
   outright.
7. **Salary** from Section 4.

Then run `python3 tools/fit_model.py validate` and fix anything it names.
Show them `python3 tools/fit_model.py rubric` so they can see exactly what
the scorer will be asked. Method: `docs/malaysia/FIT-MODEL.md`.

## Section 8: Extras (all optional, all off until set up)

- **History:** "Keep a searchable history of every job seen, and a
  monthly report on which alerts earn their slot?" If yes, run
  `python3 tools/job_store.py sync` once. `/jobs` keeps it updated after that.
- **One-command runs:** `/jobs` runs scrape → alerts → rank → summary in one go.
- **Scheduled runs (Windows):** explain `tools/register_jobs_task.ps1` (runs
  `/jobs` headless on chosen days and emails *you* a summary). **The user runs
  the registration script themselves.** Never register a scheduled task on
  their behalf.
- **Notion board:** explain `tools/notion_sync_api.py`'s docstring setup
  (integration token in `.env`). The user creates the integration and pastes
  the token into `.env` themselves.

## Finish

Write `config/malaysia.json` with every answer collected (`"version": 1`),
then summarise:

> **Malaysia setup done.**
> - Areas: <ideal> (acceptable: <...>)
> - Remote roles: <on - 3 remote boards enabled | off>
> - JobStreet/Indeed/LinkedIn alerts: <connected | separate Gmail | skipped | to do - see docs/malaysia/JOB-ALERTS.md>
> - CV: <stock LaTeX | your Word resume (<file>)>
> - Scorer: <default | Fit Model with goals: ...>
> - Extras: <history, /jobs, schedule, Notion - whichever are on>
>
> Try: `/scrape`, then `/gmail-alerts`, then `/rank`, or just `/jobs`.

---

## Rules

1. **Never ask for, echo, or write a password or token.** App passwords and
   API tokens go into gitignored `.env` files, and the user types them in.
2. **Personal numbers never land in a tracked file.** Salary, work rights and
   goals go in `config/*.json` (gitignored). Only the location tiers and
   search keywords go in `search-queries.md`, the same file upstream's
   `/setup` already personalises.
3. **Nothing is scheduled, subscribed or connected on the user's behalf.**
   Explain the step, and let them do it.
4. **Every setting can be changed later** with `/setup-malaysia <section>`.
