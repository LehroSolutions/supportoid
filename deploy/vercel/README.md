# Vercel Overlay Profile

This profile is a secondary deployment overlay.

## Notes
- Primary deployment target is Docker.
- Vercel can host the Python entrypoint with environment variables aligned to `Settings.from_env()`.
- Convex adapter should run as an external service and be referenced through `SUPPORTOID_CONVEX_ADAPTER_URL`.

## Required Env
- `SUPPORTOID_SQLITE_PATH`
- `SUPPORTOID_CONVEX_ADAPTER_URL`
- `SUPPORTOID_CONVEX_API_KEY`
- `SUPPORTOID_ALLOW_LEGACY_ANON=false`

