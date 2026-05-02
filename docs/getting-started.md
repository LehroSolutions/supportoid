# Getting Started

This guide gets a fresh SupportOID checkout running locally with a real admin user, optional demo knowledge, and the main developer workflows.

## What you need

- Python 3.13 or newer
- `pip`
- Node.js 18+ and `npm` if you want the React frontend or adapter
- Git if you are contributing changes
- A writable local filesystem for the SQLite database and runtime data directories

Optional:

- Docker Desktop for containerized local runs
- Access to an OpenAI-compatible endpoint if you want live model responses instead of deterministic fallback behavior

## Install dependencies

Backend runtime:

```powershell
python -m pip install -r requirements.txt
```

Backend development and test tooling:

```powershell
python -m pip install -r requirements-dev.txt
```

Frontend:

```powershell
cd frontend
npm install
cd ..
```

Adapter:

```powershell
cd convex-adapter
npm install
cd ..
```

## Create the first admin

SupportOID no longer ships public default credentials. Create the first user explicitly:

```powershell
python -m src.cli bootstrap-admin --username admin --password "change-this-password"
```

That command writes the first user into the SQLite database configured by `SUPPORTOID_SQLITE_PATH` or the default runtime path:

```text
./data/runtime/app/supportoid.db
```

## Optional: load sanitized demo knowledge

The repository includes sanitized demo KB entries under `data/seed/knowledge`. Load them into the runtime knowledge directory when you want a local demo:

```powershell
python -m src.cli seed-demo
```

Overwrite existing KB files if you want to reset the demo content:

```powershell
python -m src.cli seed-demo --overwrite
```

## Run the backend

```powershell
python -m src.cli serve
```

The app listens on `http://localhost:8001` by default.

## Run the frontend

In a second terminal:

```powershell
cd frontend
npm run dev
```

The Vite dev server runs on `http://localhost:5173`. The backend CORS defaults already allow that origin in local and test profiles.

## Run the adapter

In a third terminal:

```powershell
cd convex-adapter
npm run build
npm start
```

The adapter listens on `http://localhost:4010` by default.

## First login

1. Open `http://localhost:8001`
2. Sign in with the admin you created
3. Confirm `/api/v1/auth/me` returns your username and role
4. Open the dashboard, traces page, and chat flow

## Useful first commands

```powershell
python -m src.cli status
python -m src.cli traces
python -m src.cli chat --message "How do I reset my password?"
python -m src.cli sync --limit 50
```

## Run verification

Backend tests:

```powershell
python -m pytest -q
```

Frontend build:

```powershell
cd frontend
npm run build
```

Adapter build:

```powershell
cd convex-adapter
npm run build
```

## Next docs

- [configuration.md](configuration.md)
- [architecture.md](architecture.md)
- [how-to-use.md](how-to-use.md)
- [ai-evaluation.md](ai-evaluation.md)
