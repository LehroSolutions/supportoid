# ADR-0003: Package manager selection (Bun vs alternatives)

## Status
Accepted — hybrid (Bun for JS/TS only)

## Context
The constellation mixes Next.js/Vite/Node CLIs with pure Python services. Bun is excellent for JS/TS install + runtime ergonomics, but it is not a Python package manager.

## Decision
SupportOID is hybrid: Python backend + JS/TS frontend/adapters. **Bun is preferred only for the JS/TS packages** (`frontend`, `convex-adapter`). The Python backend remains pip/venv (or uv) based.

### Recommendation
Do not force Bun onto the Python service layer.

## Bun ideal when
- Dependencies are npm packages
- Scripts are Node/TypeScript CLIs or Vite/Next apps
- Fast local install and `bunx` DX matter

## Bun not ideal when
- Runtime is CPython/FastAPI/pytest
- Native Python packaging/metadata is required
- Tooling assumes pip/uv lock semantics exclusively

## Consequences
- JS/TS packages declare `packageManager: bun@...` and ship `bunfig.toml`
- npm lockfiles are archived as legacy artifacts
- Contributors generate `bun.lock` with `bun install` on a network machine
- Python packages keep their existing tooling

## Related
- [How to Use](./how-to-use.md)
- [Architecture](./architecture.md)
- [Index](./index.md)
