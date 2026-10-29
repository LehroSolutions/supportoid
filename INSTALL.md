# Install

SupportOID is hybrid:

## JavaScript / TypeScript (Bun)

From repository root:

```bash
bun install --frozen-lockfile
bun run build:js
bun run dev:web
```

Workspaces:
- `frontend/`
- `convex-adapter/`

## Python backend

PowerShell, from the repository root:

```powershell
python -m venv .venv
$env:Path = (Join-Path (Get-Location) '.venv\Scripts') + ';' + $env:Path
python -m pip install -r requirements-dev.txt
python -m pip check
bun run verify
bun run docs:check
python -m src.cli --help
```

On Linux or macOS, activate `.venv` with `source .venv/bin/activate` before
running the same pip and verification commands. Runtime-only installations can
use `requirements.txt`; `requirements-dev.txt` adds the release-check tools.

The built-browser check uses isolated synthetic accounts and temporary stores:
install Chromium with `bunx playwright install chromium`, then run
`bun run test:browser`. `PLAYWRIGHT_CHANNEL=chrome` selects installed Chrome.
See [PRODUCTION.md](PRODUCTION.md) for protected storage and recovery.

Bun is **not** used for Python dependencies.
