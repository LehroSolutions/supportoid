# SupportOID Convex Adapter

Hybrid Node/TypeScript adapter that accepts deterministic sync events from the Python runtime.

This is not wired to a live Convex Cloud project. It is a local, self-hosted compatibility bridge that stores JSON data on disk by default. Do not commit `convex.json`, `.convex/`, generated Convex client files, deployment names, or real adapter API keys to the public repository.

## Endpoints

- `GET /sync/health`
- `POST /sync/event`
- `GET /data/traces`
- `GET /data/traces/:sessionId`
- `GET /data/costs`

## Run

1. `bun install`
2. `bun run build`
3. `npm start`

Optional env:

- `ADAPTER_PORT` (default `4010`)
- `ADAPTER_API_KEY`
- `ADAPTER_DATA_FILE` (default `adapter-data.json`)

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
