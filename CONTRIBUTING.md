# Contributing

## Setup
- Install Python with a working virtual environment.
- Install backend dependencies with `python -m pip install -r requirements-dev.txt`.
- Install the JavaScript workspaces ([frontend](./frontend) and [convex-adapter](./convex-adapter)) with `bun install` from the repository root. Bun is the canonical install path; do not use `npm install` or `npm ci`, and do not create a nested lockfile — both workspaces resolve to the root `bun.lock`.
- Requires Bun 1.3.14 or newer (`.tool-versions`, `engines`, and CI all pin 1.3.14).

## Workflow
- Create a bootstrap admin before local login: `python -m src.cli bootstrap-admin --username admin --password <strong-password>`. There is no default password — choose your own strong, unique secret.
- Seed demo knowledge when needed: `python -m src.cli seed-demo`.
- Run backend tests with `python -m pytest -q`.
- Build the frontend with `bun run build:web` from the repository root, or `bun run build:js` for every JavaScript workspace.
- Run `bun run verify` (format, lint, JavaScript build, backend tests) plus `bun run docs:check` before opening a pull request.

## Standards
- Keep secrets, local databases, traces, and runtime feedback out of commits.
- Add or update tests for behavior changes.
- Use `ProblemDetail` responses for new API errors.
- Preserve the stable `/api/v1` and `/api/v1/agent` surfaces unless a breaking change is explicitly planned.
