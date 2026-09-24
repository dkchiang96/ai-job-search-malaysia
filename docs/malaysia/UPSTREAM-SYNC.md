# Monthly maintenance: staying in sync with upstream

This fork promises Mads's index that it **merges upstream monthly**. Here is
the whole routine, about 30-60 minutes. Do it in the first week of each month.
If a month is busy, a skipped month is fine, but say so in the README's
"Tracking" line rather than letting it go stale.

## The checklist

```bash
# 0. Start clean
git checkout master && git pull
git status                      # must be clean

# 1. See what's new upstream
git fetch upstream
git log --oneline master..upstream/master
python3 tools/upstream_triage.py          # upstream's own "worth reviewing / skip" sorter
python3 tools/check_upstream_updates.py   # which methodology files changed upstream

# 2. Merge on a branch
git checkout -b sync/$(date +%Y-%m)
git merge upstream/master                 # resolve conflicts: see "Files this fork changes" below

# 3. Everything still passes
python3 -m pytest -q
python3 tools/security_guards.py
python3 tools/lint_skills.py
for d in hiredly remoteok weworkremotely workingnomads; do (cd .agents/skills/$d-search/cli && bun install && bun run typecheck && bun run test); done
python3 tools/run_pipeline.py --demo      # the offline demo still runs end to end

# 4. The outside world hasn't changed under us
python3 tools/malaysia_health.py          # robots.txt rules, logins, closures, a live Hiredly search, parsers

# 5. Real alert emails still parse (uses your own inbox, read-only)
python3 tools/gmail_imap_fetch.py run --dry-run

# 6. Ship it
git checkout master && git merge --no-ff sync/$(date +%Y-%m)
git push
git tag my-$(date +%Y.%m) && git push --tags
```

Then:

- Update the "Last synced with upstream commit" line in
  [README.md](README.md#honest-scoping-what-madss-index-asks-every-fork-to-state)
  with the new upstream commit (`git rev-parse --short upstream/master`).
- If step 4 printed **CHANGED**, update [PORTALS.md](PORTALS.md) and its
  "Checked" date. If a portal *opened up* (for example JobStreet allowing job
  pages), that's a new feature to consider, not an error.
- If you added or removed something user-visible, reply in
  [discussion #78](https://github.com/MadsLorentzen/ai-job-search/discussions/78)
  so the index line stays accurate.

## Resolving conflicts

The rule: **take upstream's version, then re-apply this fork's clearly-marked
additions.** Every edit this fork makes to an upstream file is labelled
"Malaysia adaptation" (or sits in a `# Malaysia fork:` comment), so it's easy
to find and re-insert.

### Files this fork changes

| Upstream file | What this fork adds |
|---|---|
| `README.md` | the Malaysia box under the intro |
| `.claude/commands/rank.md` | "Scorer: default, or the optional Fit Model" section; the email-alert bullet in Step 2; `12-malaysia-market.md` in Step 1's reading list |
| `.claude/commands/apply.md` | `12-malaysia-market.md` in Step 1's reading list; `.docx` edit-in-place branch (`<CV_METHOD>`) and the `.docx` checklist line |
| `.claude/commands/add-template.md` | `.docx` as a source type (compile command, manifest fields, verify step) |
| `.claude/commands/setup.md` | one "Job-hunting in Malaysia?" paragraph in Step 4 |
| `.claude/skills/job-scraper/search-queries.md` | the "Malaysia" and "Remote roles" sections at the end |
| `.claude/settings.json`, `tools/security_guards.py` | allowlist entries for this fork's CLIs and tools (always edited together) |
| `.gitignore` | the "Malaysia adaptation" block at the end |
| `templates/README.md` | the "Two authoring models" section |
| `tools/robots_check.py` | `encoding='utf-8'` in `_fetch` (fixes a Windows crash on non-Latin robots.txt bytes) |

Everything else in this fork is a **new file** and can't conflict:
`.agents/skills/{hiredly,remoteok,weworkremotely,workingnomads}-search/`,
`.claude/commands/{gmail-alerts,setup-malaysia,jobs}.md`,
`.claude/skills/job-application-assistant/{10-docx-editing,12-malaysia-market}.md`,
`.claude/skills/job-scraper/email-alert-portals.md`, `config/`, `docs/malaysia/`,
`templates/*/clean-resume/`, and the tools and tests named in them.

If upstream ever ships a feature that overlaps one of these (for example its
own email-alert importer), prefer upstream's, and retire this fork's version
in the same sync.
