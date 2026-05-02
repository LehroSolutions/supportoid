# Deployment

SupportOID supports local self-hosting and Docker-based deployment. Treat this repository as a source release, not a registry-published package.

## Local self-host

Backend:

```powershell
python -m pip install -r requirements.txt
python -m src.cli bootstrap-admin --username admin --password "change-this-password"
python -m src.cli serve
```

Optional demo content:

```powershell
python -m src.cli seed-demo
```

Optional adapter:

```powershell
cd convex-adapter
npm install
npm run build
npm start
```

The adapter is local/self-hosted. The open-source repo should not point at a real Convex Cloud deployment.

## Docker

Bring up the backend and adapter:

```powershell
docker compose up --build
```

The Docker image:

- installs from `requirements.txt`
- includes `bcrypt`
- builds the React frontend into `/app/frontend/dist`
- runs as a non-root user
- exposes port `8001`
- includes a healthcheck against `/api/v1/health`

## Persistent data

The main runtime volume is `./data`, which contains:

- `runtime/app/supportoid.db`
- `runtime/knowledge`
- `runtime/feedback`
- `runtime/training`
- `runtime/costs`
- `runtime/traces`

Do not commit runtime data back into Git.

## Recommended production topology

- reverse proxy with TLS termination
- FastAPI app behind the proxy
- optional adapter on a private network
- persistent volume for the SQLite database and runtime directories

## Required environment variables

Minimum practical production set:

```text
SUPPORTOID_DEPLOYMENT_PROFILE=production
SUPPORTOID_HOST=0.0.0.0
SUPPORTOID_PORT=8001
SUPPORTOID_SQLITE_PATH=/app/data/runtime/app/supportoid.db
SUPPORTOID_ALLOW_LEGACY_ANON=false
```

For live model calls, also provide the relevant LLM endpoint and credentials.

## Reverse proxy notes

At the proxy layer:

- force HTTPS
- preserve `X-Forwarded-*` headers correctly
- keep cookie paths intact
- restrict large request bodies if your environment requires it

## What not to do

- Do not rely on `SUPPORTOID_AUTH_USERS_JSON` as your long-term production user management path.
- Do not expose the adapter publicly without additional network controls.
- Do not connect this public source tree to your organization's real Convex Cloud project.
- Do not ship a pre-populated production database as part of your release artifact.
