# weworkremotely-search CLI

Zero-dependency CLI for searching remote jobs on [We Work Remotely](https://weworkremotely.com), one of the largest general-purpose remote-work job boards. No authentication, no API key — just `bun` and `fetch`.

## Install

```bash
cd .agents/skills/weworkremotely-search/cli
bun install
```

`bun install` only pulls dev-only type packages (`typescript`, `@types/bun`) — there are no runtime dependencies.

## Usage

```bash
bun run src/cli.ts search -q "Head of Operations" --format table
bun run src/cli.ts detail crb-director-people-operations --format plain
```

See `../SKILL.md` for the full command reference and `../url-reference.md` for the endpoints and parsing anchors this CLI relies on.

## Test

```bash
bun run typecheck
bun run test
```

`tests/parsing.test.ts` and `tests/cli-flag-validation.test.ts` are network-free (fixture-based / dispatch-time validation). `tests/live.test.ts` makes real requests against the live portal — keep it to the existing low-volume calls when editing.
