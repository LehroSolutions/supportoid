        # Audit & Improvements — 2026-07-10

        Product: **SupportOID**

        ## Audit findings addressed
        - High: no package.json at repo root; frontend/adapter nested
- Hybrid Python backend must remain pip/venv

        ## Improvements applied
        - Added root Bun workspaces for frontend + convex-adapter
- Added INSTALL.md clarifying Bun vs Python paths
- Root scripts: dev:web, build:js

        ## Install verification
        - JS/TS packages: run `bun install` from the directory containing `package.json` (repo root for workspace packages).
        - Python packages: use venv + pip (`INSTALL.md`).

        ## Related
        - [How to Use](./how-to-use.md)
        - [Security](./security.md)
        - [ADR-0003 Package Manager](./adr-0003-package-manager-bun.md)
