# Contributing

## Setup
- Install Python with a working virtual environment.
- Install backend dependencies with `python -m pip install -r requirements-dev.txt`.
- Install frontend dependencies with `npm install` in [frontend](./frontend).
- Install adapter dependencies with `npm install` in [convex-adapter](./convex-adapter).

## Workflow
- Create a bootstrap admin before local login: `python -m src.cli bootstrap-admin --username admin --password <strong-password>`.
- Seed demo knowledge when needed: `python -m src.cli seed-demo`.
- Run backend tests with `python -m pytest -q`.
- Build the frontend with `npm run build` in [frontend](./frontend).

## Standards
- Keep secrets, local databases, traces, and runtime feedback out of commits.
- Add or update tests for behavior changes.
- Use `ProblemDetail` responses for new API errors.
- Preserve the stable `/api/v1` and `/api/v1/agent` surfaces unless a breaking change is explicitly planned.
