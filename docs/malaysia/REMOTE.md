# Remote roles open to Malaysia (optional)

Remote work widens the pool beyond Malaysian employers: foreign companies
hiring people who live here, usually paid in USD, often through an Employer of
Record or as a contractor. It's **off by default**. `/setup-malaysia` asks
you (Section 2), and you can switch later with `/setup-malaysia remote`.

## What turning it on does

- **Enables three remote-only boards**, all with zero-dependency CLIs and
  their own tests:
  - `remoteok-search` (Remote OK's public API)
  - `weworkremotely-search`
  - `workingnomads-search`
- **Adds remote searches** to `search-queries.md`. That includes
  `freehire-search --remote remote` and `linkedin-search -l "Malaysia" --remote remote`.
- **Turns on the Remote-Work Verification Gate** for every remote result
  (`12-malaysia-market.md` §1).

## The Remote-Work Verification Gate

A "Remote" tag is where the check starts, not a verdict. Many remote jobs
turn out to be:

- **geography-restricted** ("must be authorised to work in the US",
  "UK residents only"), which is a **FAIL**, or
- **hybrid in disguise** (named office days, "must live near London"), also a
  **FAIL**, with the job's real location re-checked against your commute area,
  or
- **silent** about who can apply, which is a **FLAG**: it stays in your
  shortlist with a warning to check the careers page first.

Only postings open to Malaysia, APAC/Asia or "anywhere" **PASS**. Every
verdict quotes the posting's own words, so you can check it. A FAIL never
reaches your shortlist. It's listed under "Excluded" with the quote.

For every remote job that passes or is flagged, `/rank` also surfaces:

- **Time zone:** the required overlap, in Malaysia time. For example, "9am-5pm
  EST" means roughly 9pm-5am here.
- **Employment model:** employee through an Employer of Record (EOR), or a
  contractor.
- **Pay currency:** converted to RM only with the rate you set (see
  [SALARY.md](SALARY.md)).

## Things to know before you accept a remote offer

This is general information, **not tax or legal advice**. Check the official
sources.

- **Employee via EOR vs contractor.** Through an EOR, a Malaysian entity
  employs you, so EPF, SOCSO and EIS work as in any local job. As a
  **contractor** there is no employer contribution. You can contribute to EPF
  yourself (KWSP's voluntary schemes, e.g. i-Saraan) and register for
  PERKESO's self-employment social security scheme.
- **Tax.** Income from work you do while living in Malaysia is generally
  taxable in Malaysia, whoever pays it. Declare it to LHDN, and keep invoices
  and payment records. A tax agent is worth one conversation before your first
  contract.
- **Getting paid.** Check the transfer fees and FX spread of whatever channel
  the employer uses. On a USD salary, that spread is a real part of your pay.
- **Contract terms.** Look for notice period, currency, who bears transfer
  fees, equipment, and which country's law governs the contract.

## Turning it off

`/setup-malaysia remote` → choose "Malaysia-based roles only". The three
boards go back to `enabled: false` and the remote searches are removed. Jobs
already found stay in your history.
