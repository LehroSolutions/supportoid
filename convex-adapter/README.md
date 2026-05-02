# SupportOID Convex Adapter

Hybrid Node/TypeScript adapter that accepts deterministic sync events from the Python runtime.

This is not wired to a live Convex Cloud project. It is a local, self-hosted compatibility bridge that stores JSON data on disk by default. Do not commit `convex.json`, `.convex/`, generated Convex client files, deployment names, or real adapter API keys to the public repository.

## Endpoints
- `GET /sync/health`
- `POST /sync/event`
- `GET /data/traces`
- `GET /data/traces/:sessionId`
- `GET /data/costs`

## Run
1. `npm install`
2. `npm run build`
3. `npm start`

Optional env:
- `ADAPTER_PORT` (default `4010`)
- `ADAPTER_API_KEY`
- `ADAPTER_DATA_FILE` (default `adapter-data.json`)
