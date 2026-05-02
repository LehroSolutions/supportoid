## v9.0 - Foundation-First Platform Upgrade (2026-04-18)

### Highlights
- Introduced a canonical shared application core for CLI, API, and web (`src/app/*`).
- Added typed DTO contracts for chat, feedback, traces, costs, KB quality, and stats.
- Replaced broken API wiring with stable FastAPI v1 routes and deprecated legacy aliases.
- Added authenticated server-rendered web UI with RBAC-aware pages.
- Added hybrid persistence with SQLite fallback/cache plus deterministic Convex sync queue.
- Added migration and sync operations (`serve`, `migrate`, `sync`) while preserving legacy command names.
- Added deployment profiles with Docker primary plus Vercel/local overlays.
- Added docs baseline in `docs/` for use cases, architecture, usage, pricing, API, deployment, and operations.

### Added
- `src/app/dto.py`
- `src/app/auth.py`
- `src/app/storage.py`
- `src/app/service.py`
- `src/interface/web_routes.py`
- `src/interface/templates/*`
- `convex-adapter/*`
- `Dockerfile`
- `docker-compose.yml`
- `deploy/vercel/*`
- `deploy/local/.env.example`
- `tests/test_stabilized_core_gate.py`
- `tests/test_api_contracts_v1.py`

### Changed
- `src/main.py` now serves as canonical FastAPI app factory and server entrypoint.
- `src/cli/__main__.py` now routes commands through the canonical service layer.
- `src/api/routes.py` now exposes typed v1 endpoints and deprecation-marked legacy aliases.
- `src/config/settings.py` expanded for auth/RBAC, storage, adapter, and deployment settings.


## v8.1 - Final Integration + E2E Tests + Performance Benchmarks (2026-04-05)

### Previous Work Snapshot
- Added advanced RAG retrieval and trace/learning modules.
- Added dashboard upgrades for summaries, correlation, and KB quality.
- Added broad integration and performance test coverage in prior rounds.

