# Configuration

SupportOID is configured through environment variables and the `Settings` dataclass in `src/config/settings.py`.

## Runtime directories

Default runtime paths:

```text
SUPPORTOID_SEED_DIR=./data/seed
SUPPORTOID_MODEL_DIR=./data/runtime/models
SUPPORTOID_KB_DIR=./data/runtime/knowledge
SUPPORTOID_FEEDBACK_DIR=./data/runtime/feedback
SUPPORTOID_TRAINING_DIR=./data/runtime/training
SUPPORTOID_COST_DIR=./data/runtime/costs
SUPPORTOID_TRACE_DIR=./data/runtime/traces
SUPPORTOID_SQLITE_PATH=./data/runtime/app/supportoid.db
SUPPORTOID_SEED_DEMO_KB_ON_EMPTY=false
```

These directories are created automatically at startup.

If `SUPPORTOID_SEED_DEMO_KB_ON_EMPTY=true`, the app will copy the sanitized seed knowledge pack into an empty KB directory on startup. Leave this disabled for public or production-like deployments and prefer `python -m src.cli seed-demo` for intentional local demo setup.

## Core server settings

- `SUPPORTOID_HOST`
  Default: `0.0.0.0`
- `SUPPORTOID_PORT`
  Default: `8001`
- `SUPPORTOID_DEPLOYMENT_PROFILE`
  Common values: `local`, `test`, `docker`, `production`
- `SUPPORTOID_CORS_ORIGINS`
  Comma-separated list for non-default origins

## Authentication and sessions

- `SUPPORTOID_AUTH_USERS_JSON`
  Optional bootstrap-style user map for local or scripted setups. Example:

```json
{
  "admin": { "password": "change-me-now", "role": "admin" }
}
```

- `SUPPORTOID_AGENT_TOKEN_TTL_SECONDS`
  Service account token lifetime
- `SUPPORTOID_ALLOW_LEGACY_ANON`
  Default: `false`
  This should stay disabled in public or production-like deployments.

Notes:

- Browser sessions are stored in SQLite, not process memory.
- Passwords are hashed with `bcrypt`.
- Public releases should prefer `bootstrap-admin` over long-lived plaintext user env vars.

## Retention

- `SUPPORTOID_TRACE_RETENTION_DAYS`
  Default: `30`
- `SUPPORTOID_FEEDBACK_RETENTION_DAYS`
  Default: `90`

Retention cleanup runs during service initialization.

## LLM runtime settings

Base compatibility variables:

- `SUPPORTOID_LLM_API_KEY`
- `SUPPORTOID_LLM_MODEL`
- `SUPPORTOID_LLM_ENDPOINT`
- `SUPPORTOID_LLM_TIMEOUT_MS`

Advanced model configuration:

- `SUPPORTOID_MODEL_CHAIN`
  Comma-separated profile order
- `SUPPORTOID_MODELS_JSON`
  JSON override for profile definitions

Default text model story:

- `gpt-oss-remote`
- `gemma4-remote`
- `gpt-oss-local`
- `gemma4-local`

PersonaPlex remains optional and voice-oriented through the `voice` config block. It is not the default text support model.

## Adapter bridge

- `SUPPORTOID_CONVEX_ADAPTER_URL`
- `SUPPORTOID_CONVEX_API_KEY`

Notes:

- The adapter accepts `X-Adapter-Key`.
- The bundled adapter is a local Convex-style compatibility bridge. It is not connected to a live Convex Cloud project.
- Adapter storage is intended for self-host/demo sync workflows, not as a hardened source-of-truth database.
- Do not commit `convex.json`, `.convex/`, generated Convex client files, deployment names, or real adapter API keys.

## Recommended local `.env`

See [../deploy/local/.env.example](../deploy/local/.env.example) for the current local baseline.

## Recommended production posture

- Set `SUPPORTOID_DEPLOYMENT_PROFILE=production`
- Terminate TLS in front of the app
- Keep `SUPPORTOID_ALLOW_LEGACY_ANON=false`
- Store secrets outside the repository
- Back up the SQLite file and runtime data regularly
- Restrict admin account creation to the initial bootstrap workflow
