# AGENTS.md — SupportOID

Operating contract for AI coding agents, with human-in-the-loop checkpoints.

## Identity

SupportOID is a self-hosted customer support application: **FastAPI Python
backend** (chat, traces, analytics, admin), **React frontend** (Bun
workspace), a CLI for bootstrap/diagnostics/sync, a typed agent API under
`/api/v1/agent`, and SQLite persistence with an optional Convex-style
adapter bridge. License: Apache-2.0.

## Command Reference

Root is a Bun workspace (frontend + convex-adapter); Python uses venv/pip.

| Task | Command |
|---|---|
| Install JS workspaces | `bun install` |
| Frontend dev / build | `bun run dev:web` / `bun run build:web` |
| Frontend format check | `bun run format:check` |
| Frontend lint | `bun run lint` (ESLint flat config + react-hooks) |
| Build everything JS | `bun run build:js` |
| Backend setup | `python -m venv .venv && .venv/Scripts/pip install -e .` (or repo INSTALL.md) |
| Backend tests | `python -m pytest -q` |
| **Full verify (run before declaring done)** | `bun run verify` |

## Verify Contract

`bun run verify` = frontend format:check + eslint + full JS build (`build:js`
includes frontend `tsc`) + backend pytest. Must pass before you report
success. If the venv is missing, create it per INSTALL.md — do not skip
backend tests silently.

Frontend lint runs ESLint 10 with `typescript-eslint` and
`eslint-plugin-react-hooks`. `react-hooks/rules-of-hooks` violations are hard
errors — never suppress them with `eslint-disable`, they are real render bugs.

## Codebase Map

- `src/orchestrator.py` (+ `src/`) — FastAPI backend, agent API, sessions
- `tests/` — pytest suite (rounds-based regression files)
- `frontend/` — React operator UI (vite, prettier, eslint flat config)
- `convex-adapter/` — Convex-style adapter bridge (Bun workspace)
- `deploy/` — Docker/deployment assets; `data/` — sanitized seed data only
- `pytest.ini` — pytest configuration

## Conventions

- Backend: bootstrap-first auth — no public default credentials, ever.
- Sessions/traces are pruned deliberately (`round9` regression tests cover
  pruning on young runners) — preserve those behaviors.
- Frontend: TypeScript strict (`tsc` runs in `build`); prettier enforced;
  ESLint (flat config) is part of `lint`/`verify` — never silence a rule to
  land a change, fix the cause or add a scoped, justified disable.
- **Single lockfile:** Bun workspaces resolve to the root `bun.lock`. Install
  from the repo root; never create or commit a nested `frontend/bun.lock` — a
  stale one made CI installs ambiguous and has been removed deliberately.

## Human-in-the-Loop Checkpoints

Ask the human before:
- Changing auth/bootstrap flows or the agent API contract (`/api/v1/agent`).
- Changing session pruning or trace retention semantics.
- Changing Convex adapter bridge contracts.

## Danger Zones

- Never commit live credentials, runtime databases, feedback logs, or
  populated traces — the repo ships sanitized seed data only.
- Never commit `.env` files; `.env.example` is the template.
- Never run the backend against a production database during verification.
