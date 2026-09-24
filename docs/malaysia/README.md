# Malaysia adaptation

A fork of [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search)
for job-hunting in Malaysia. Mads's workflow (`/setup`, `/scrape`, `/rank`,
`/apply`, `/interview`) is unchanged, and his [README](../../README.md) still
applies. This layer adds what Malaysia needs, mostly as new files. The handful
of places it touches his files are listed in
[UPSTREAM-SYNC.md](UPSTREAM-SYNC.md#files-this-fork-changes).

**In one paragraph:** Malaysia's largest job board, JobStreet, blocks automated
search in `robots.txt`, and so do Maukerja and Glints. MYFutureJobs needs a
login, and Jora Malaysia has closed. So this fork adds a search skill for
**Hiredly** (the board that can be reached properly) and reads
**JobStreet's own alert emails** from your Gmail instead of scraping it. It
understands **RM salaries**, Malaysian location, language (BM/Mandarin) and
eligibility wording, and can optionally include **remote roles open to
Malaysia**, with a check that throws out "remote" jobs that are really
US-only or hybrid.

## What's added

| Module | What it does | Default | Doc |
|---|---|---|---|
| `hiredly-search` | Portal skill for my.hiredly.com: state + category search, full job detail. Zero dependencies, contract-compliant, 35 tests. | on | [SKILL.md](../../.agents/skills/hiredly-search/SKILL.md) |
| `/gmail-alerts` | Reads JobStreet and LinkedIn alert digests over read-only IMAP, parses them deterministically, adds them to `seen_jobs.json`. Indeed parser included but unmaintained. | on (needs Gmail setup) | [JOB-ALERTS.md](JOB-ALERTS.md) |
| Remote roles | Remote OK, We Work Remotely, Working Nomads skills, plus the **Remote-Work Verification Gate** | **off**; `/setup-malaysia` asks | [REMOTE.md](REMOTE.md) |
| Malaysia rules | `12-malaysia-market.md`: RM salary conventions, BM/Mandarin requirement phrasing, "Malaysian only" wording, Klang Valley, agency duplicates | on after `/setup-malaysia` | [12-malaysia-market.md](../../.claude/skills/job-application-assistant/12-malaysia-market.md) |
| `tools/myr_salary.py` | Normalises any Malaysian pay text to monthly RM, recording every assumption | on | [SALARY.md](SALARY.md) |
| `/setup-malaysia` | Guided setup: states, remote yes/no, work rights, RM salary, alerts, CV format, scorer, extras | run after `/setup` | [setup-malaysia.md](../../.claude/commands/setup-malaysia.md) |
| Word resume track | Edit your own `.docx` resume in place (formatting can't drift), with a placeholder template | off | [10-docx-editing.md](../../.claude/skills/job-application-assistant/10-docx-editing.md) |
| Fit Model | Optional `/rank` scorer: the agent reports facts, a script does the maths from *your* goals, locations and salary | off | [FIT-MODEL.md](FIT-MODEL.md) |
| History | SQLite mirror of `seen_jobs.json`, with yield per portal/alert and RM salary benchmarks from your own feed | off | `tools/job_store.py` |
| Automation pack | `/jobs` one-command run, Windows scheduled runs, headless Notion sync, summary email to yourself | off | [jobs.md](../../.claude/commands/jobs.md) |
| Demo | `python3 tools/run_pipeline.py --demo` runs the real code on invented data, offline | - | below |
| Health check | `python3 tools/malaysia_health.py` re-checks every portal rule this fork relies on | - | [UPSTREAM-SYNC.md](UPSTREAM-SYNC.md) |

## Try it in a minute

```bash
python3 tools/run_pipeline.py --demo
```

Portal results and alert emails are merged without duplicates, salaries are
converted to monthly RM, a US-only "remote" job and a below-floor salary are
excluded with their reasons, an alert-only job whose posting can't be found is
parked rather than guessed at, and everything is ranked by the Fit Model. It's
all invented data, with no network and no credentials.

## Getting started for real

1. Fork this repo **privately** (see Mads's README warning: `/setup` writes
   your personal data into tracked files). Clone it and install
   [Claude Code](https://claude.com/claude-code), Python 3.10+ and
   [Bun](https://bun.sh).
2. In Claude Code: `/setup`, then `/setup-malaysia`.
3. `/scrape` → `/gmail-alerts` → `/rank`, or just `/jobs`.
4. Pick a job and run `/apply <url>`. Applying stays manual. Nothing in this
   fork submits an application or messages an employer.

## Honest scoping (what Mads's index asks every fork to state)

- **Licence and attribution:** MIT, Mads Lorentzen's copyright intact (see
  [LICENSE](../../LICENSE)).
- **Personal use:** `hiredly-search` is for personal, non-commercial use under
  Hiredly's Terms §3.1. Remote OK's API asks for a link back and attribution
  if you publish anything from it.
- **Declared deviations** from the portal contract: `hiredly-search` filters
  `--query` and `--jobage` client-side, because the site's search API is
  robots-disallowed. See its SKILL.md.
- **Metered or credentialed parts ship off:** Gmail (app password), Notion
  (token) and scheduled runs do nothing until you set them up yourself.
- **No application automation.** Discovery and drafting only. The one
  outbound email is a run summary sent to your own address.
- **Upstream tracking:** merges upstream monthly
  ([routine](UPSTREAM-SYNC.md)). Last synced with upstream commit `120f476`
  (2026-09-21).
- **Built by** Derrick Chiang ([@dkchiang96](https://github.com/dkchiang96)),
  using Claude Code. Why and how: [CASE-STUDY.md](CASE-STUDY.md).
