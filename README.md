# SupportOID

SupportOID is a self-hosted customer support application with:

- A FastAPI backend for chat, traces, analytics, health, and admin workflows
- A React frontend for operators
- A CLI for bootstrap, diagnostics, sync, and local automation
- A typed agent API under `/api/v1/agent`
- SQLite-backed persistence with an optional Convex-style adapter bridge

This repository is prepared for an Apache 2.0 open-source release. It ships source code, tests, deployment assets, and sanitized seed data. It does not ship live credentials, runtime databases, feedback logs, or populated traces.

## Highlights

- Bootstrap-first auth: no public default credentials
- Persistent users and sessions in SQLite
- Bcrypt-required password hashing outside test mode
- Redacted storage for traces, feedback, and automation audit payloads
- Deprecated `/api/*` aliases kept for compatibility, but authenticated only
- Deterministic offline AI scenario tests plus opt-in `live_llm` smoke coverage
- Docker and local self-host workflows

## Quickstart

### 1. Install dependencies

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

Optional frontend and adapter dependencies:

```powershell
cd frontend
bun install
cd ..\convex-adapter
bun install
cd ..
```

### 2. Create the first admin

```powershell
python -m src.cli bootstrap-admin --username admin --password "change-this-password"
```

### 3. Optional: load the sanitized demo KB

```powershell
python -m src.cli seed-demo
```

SupportOID does not auto-import demo knowledge on first run. Demo content is opt-in.

### 4. Start the API and web app

```powershell
python -m src.cli serve
```

Open [http://localhost:8001](http://localhost:8001).

### 5. Optional: run the adapter bridge

```powershell
cd convex-adapter
bun run build
bun start
```

## Public surfaces

- Browser and API auth: `/api/v1/auth/*`
- Support chat: `/api/v1/chat`
- Feedback: `/api/v1/feedback`
- Traces and analytics: `/api/v1/traces`, `/api/v1/stats`, `/api/v1/costs`, `/api/v1/kb-quality`
- Agent automation: `/api/v1/agent/*`
- CLI: `python -m src.cli ...`

## Security notes

- Browser auth uses session cookies and CSRF protection.
- Passwords are hashed with `bcrypt`.
- Sessions persist in SQLite and survive restarts.
- Trace and feedback persistence redact common secrets and basic PII.
- High-risk prompt injection, SQLi, NoSQLi, command injection, XSS, SSRF, path traversal, and oversized payloads are blocked before orchestration.
- The bundled adapter is intended for demo and self-host use. It is not connected to a live Convex Cloud project and is not a hardened primary database.

## Model story

- Default text support uses the OpenAI-compatible `gpt-oss` and `gemma4` profile chain configured in `src/config/settings.py`.
- PersonaPlex remains optional and voice-oriented. It is not required for the default text support path.
- Offline tests cover deterministic fallback behavior. Provider-backed tests are opt-in and marked `live_llm`.

## Documentation

- [docs/getting-started.md](docs/getting-started.md)
- [docs/configuration.md](docs/configuration.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/api.md](docs/api.md)
- [docs/how-to-use.md](docs/how-to-use.md)
- [docs/ai-evaluation.md](docs/ai-evaluation.md)
- [docs/security.md](docs/security.md)
- [docs/deployment.md](docs/deployment.md)
- [docs/operations.md](docs/operations.md)
- [docs/open-source-release-checklist.md](docs/open-source-release-checklist.md)

## Common commands

```powershell
python -m src.cli status
python -m src.cli traces
python -m src.cli sync --limit 100
python -m pytest -q
cd frontend; bun run build
cd ..\convex-adapter; bun run build
```

## License

Copyright © 2026 Lehro Solutions. Licensed under the [Apache License 2.0](LICENSE). See [NOTICE](NOTICE).

## Documentation

Canonical docs hub: [`docs/.docs/index.md`](docs/.docs/index.md)

## Package managers

- **Frontend / convex-adapter:** Bun-first (`bun install`, `bun run build`)
- **Python backend:** venv + pip/uv (Bun is not used for Python deps)

See `docs/.docs/adr-0003-package-manager-bun.md`.

## Install

See [INSTALL.md](INSTALL.md) for Bun workspaces (frontend/adapter) and Python backend setup.

```bash
bun install
bun run build:js
```

## Security

See [SECURITY.md](SECURITY.md).

<!-- docs-system:start -->

## Documentation

The current public documentation is available in [`docs/index.html`](docs/index.html). Start with [`docs/current/start-here.md`](docs/current/start-here.md) for scope, current changes, workflows, architecture, security, quality, and contribution guidance.

### Latest public changes

- Operations and analytics dashboards
- Knowledge-quality surfaces
- Trace search and expansion
- Open-source release hardening

Documentation is maintained as canonical Markdown plus generated HTML and JSON counterparts. Run `pnpm docs:build` after changing `docs/current/*.md` and `pnpm docs:check` before a public release.
<!-- docs-system:end -->

<!-- bun-toolchain:start -->

## Bun and CI

This repository uses **Bun 1.3.14** and targets **Node 24+** for JavaScript tooling and CI.

```bash
rm -f package-lock.json
bun install
bun run build
bun run test
bun run docs:check
```

Do not use `npm ci`; Bun is the canonical install path. Run `bun install` after dependency changes and commit the resulting `bun.lock`.
<!-- bun-toolchain:end -->
