# Case study: adapting an AI job-search framework for Malaysia

*Derrick Chiang, operations and automation. Built with Claude Code on top of
[Mads Lorentzen's ai-job-search](https://github.com/MadsLorentzen/ai-job-search).*

## The starting point

Mads built a Claude Code framework that turns job hunting into a pipeline:
profile yourself once, scrape job boards, rank postings against your profile,
and draft a tailored CV and cover letter for the ones worth applying to, each
checked by a reviewer agent before you see it. It's built around Danish job
boards and designed for forks to adapt to their own market.

I used it for my own search in Malaysia and hit the obvious wall: the portals
it knows don't exist here, and the ones that do exist mostly don't want to be
scraped.

## The constraint I designed around

Before writing any code, I checked each Malaysian portal's `robots.txt` and
terms (full table: [PORTALS.md](PORTALS.md)):

- **JobStreet**, the largest, disallows job pages for every crawler and names
  AI crawlers explicitly.
- **Maukerja** and **Glints** disallow their search paths.
- **MYFutureJobs** requires a login for all job data.
- **Jora Malaysia** has shut down.
- **Hiredly** allows its public pages but disallows its search API.

Scraping around any of those was never an option. The question became how to
get the same information through channels the portals themselves offer.

## What I built

**1. JobStreet through its own alert emails.** JobStreet lets you save a search
and emails you matches. A read-only IMAP importer takes those digests from a
Gmail label, and a deterministic parser (not an LLM) extracts title, company,
location, salary and link. The parser was built against real digests,
including the traps a naive parser falls into: blank lines that mean
different things in different places, a promo block in the middle of the
listings, and a "jobs you may have missed" section that looks like footer but
is real content. The model never sees an email. It sees a 5-field summary.

**2. A Hiredly portal skill that stays inside the rules.** The site's keyword
search runs through an API that robots.txt disallows, so the skill uses only
the server-rendered category and state pages that Hiredly lists in its own
sitemaps, and filters keywords locally. It is zero-dependency, follows
upstream's portal contract (identical flags, output shape, error format and
backoff), and has 35 tests.

**3. Honest handling of what can't be read.** A JobStreet alert only gives a
title, and upstream's rule is that nothing gets scored from a title alone. So
the ranker looks for the same job on the employer's site, Hiredly, LinkedIn or
one web search. If it finds nothing, the job is parked as "unverified" and
shown to you, never guessed at.

**4. Malaysian rules the framework didn't have:**
- RM salary parsing that records its assumptions (annual vs monthly, `k`
  suffixes, "sehingga", Indeed's estimates).
- Language requirements written the way Malaysian ads write them ("Mandarin
  speaker", "BM compulsory").
- "Malaysian only" eligibility wording, and duplicate detection across boards.

**5. Remote work as an explicit choice.** Remote-only boards are off unless you
opt in, and every "remote" job passes a verification gate. That catches the
large share of remote listings that are really US-only or hybrid, and quotes
the line that proves it.

**6. A scorer anyone can make their own.** My private scorer was a
headhunter-style formula with my own goals and salary tiers hard-coded. For
the public version I split it cleanly: the language model reports checkable
facts, and a script does all the arithmetic from a config built by
interviewing the user. Every score can be traced to its inputs.

**7. Automation around it**, all off by default:
- a one-command `/jobs` run
- Windows scheduled runs that use explicit tool permissions, never a blanket
  bypass
- a headless Notion sync that never overwrites a status you set by hand
- a summary email that can only go to your own address

## How AI was used, and where it deliberately wasn't

Claude Code wrote most of the code with me, in the same way the framework
itself works: I set the design, constraints and acceptance tests, reviewed
every change, and checked claims against primary sources. Every robots.txt
decision in this repo was verified live, not assumed.

The more useful skill was **deciding what the model should not do**. Parsing
emails, deduplicating, converting salaries and computing scores are all
deterministic code. The model does what only a model can: read a job
description and report what it asks for. That split makes the system
cheaper, testable, and honest about uncertainty.

## Engineering hygiene

- **Personal data never enters the public history.** The repo was rebuilt
  from upstream rather than stripped from my working copy. Every test fixture
  uses invented companies. Word templates were rebuilt without author metadata
  or revision IDs.
- **Upstream's safety guards extended, not bypassed.** Every new
  pre-approved command went into upstream's security allowlist in the same
  change.
- **Tests.** 79 new Python tests on top of upstream's 484, plus 92 CLI tests
  across the four portal skills. An offline demo runs the real pipeline code
  on invented data in about a second.
- **Maintenance planned for.** A monthly routine merges upstream, and a
  health-check script re-verifies every external assumption: robots rules,
  logins, closures, and a live search. The first run caught a real bug:
  upstream's robots checker crashed on Windows when a robots.txt contained a
  non-Latin character.

## Credit

The architecture, the drafter-reviewer workflow, the portal contract and most
of this repository are Mads Lorentzen's work
([MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search),
MIT). This fork is my adaptation of it for Malaysia.
