# SupportOID Architecture

  ## Intent
  AI-native support orchestration platform with FastAPI backend, Vite frontend, and ops surfaces.

  ## Runtime shape
  - Domain: **Customer support AI**
  - Primary stack: Python FastAPI, React, Vite, Framer Motion, SQLite automation store
  - Key entrypoints:
- `src/main.py`
- `src/app/auth.py`
- `frontend/src/pages/Dashboard.tsx`

  ## Boundaries
  - Validate inputs at trust boundaries.
  - Keep authorization explicit near data access.
  - Prefer recoverable errors over silent failure.
  - Keep side effects isolated and observable.

  ## Related
  - [Design System](./design-system.md)
  - [Security](./security.md)
  - [ADR-0001](./adr-0001-docs-system.md)
  - [Roadmap](./roadmap.md)
