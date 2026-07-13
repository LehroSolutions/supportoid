# How to Use SupportOID

Self-hosted support stack: FastAPI backend + React operator UI + CLI.

## 1) Backend install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## 2) Bootstrap admin (required)

```bash
python -m src.cli bootstrap-admin --username admin --password 'change-this-password'
```

Optional demo knowledge:

```bash
python -m src.cli seed-demo
```

## 3) Start API

```bash
python -m src.cli serve
```

Open http://localhost:8001

## 4) Frontend (optional)

```bash
bun install
bun run dev:web
```

## 5) Operator workflows
- Login with bootstrap admin
- Use chat for support replies
- Inspect traces/analytics/KB quality
- Use CLI for diagnostics and automation

## 6) Production checklist
- Strong admin password
- No committed `.env`
- HTTPS reverse proxy
- Non-test profile with bcrypt hashing

## Related
- [Getting Started](../getting-started.md)
- [INSTALL.md](../../INSTALL.md)
- [Security](../../SECURITY.md)
- [API](../api.md)
