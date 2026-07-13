# Install

SupportOID is hybrid:

## JavaScript / TypeScript (Bun)

From repository root:

```bash
bun install
bun run build:js
bun run dev:web
```

Workspaces:
- `frontend/`
- `convex-adapter/`

## Python backend

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m src.cli --help
```

Bun is **not** used for Python dependencies.
