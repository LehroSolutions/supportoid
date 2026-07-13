# frontend

Bun-first JavaScript/TypeScript package.


## Package manager (Bun)

This package is **Bun-first**.

```bash
bun install
bun run dev    # if defined
bun run build  # if defined
bun test       # or: bun run test
```

- Lockfile target: `bun.lock` (generate locally with `bun install`)
- `packageManager` field pins Bun via Corepack-compatible tooling ecosystems
- Node remains a compatibility runtime floor; prefer Bun for install/run/test

See docs for the package-manager decision: search for `ADR-0003` in `docs/.docs/` when present.
