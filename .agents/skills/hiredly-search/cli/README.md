# hiredly-cli

Zero-dependency CLI for Hiredly Malaysia (`my.hiredly.com`) job listings. See
`../SKILL.md` for usage and `../url-reference.md` for the parsing anchors.

```bash
bun install          # dev types only (typescript, @types/bun); nothing at runtime
bun run typecheck
bun run test         # offline parsing/flag/backoff tests + one live smoke test
HIREDLY_OFFLINE=1 bun run test   # skip the live test
```

Personal, non-commercial use only (Hiredly Terms §3.1). This CLI never calls
`my-api.hiredly.com`, which robots.txt disallows.
