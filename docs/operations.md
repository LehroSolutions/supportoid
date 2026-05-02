# Operations

This guide covers day-2 operations for a self-hosted SupportOID deployment.

## Daily checks

Recommended quick checks:

```powershell
python -m src.cli status
python -m src.cli traces
python -m src.cli costs
```

HTTP checks:

- `GET /api/v1/health`
- `GET /api/v1/admin/security/report`

## Backups

Back up at least:

- `data/runtime/app/supportoid.db`
- `data/runtime/knowledge`

If you use local model artifacts or training artifacts, include:

- `data/runtime/models`
- `data/runtime/training`

## Restore

1. Stop the app
2. Restore the SQLite file and runtime directories
3. Start the app
4. Verify `/api/v1/health`
5. Verify admin login and traces access

## Retention and cleanup

Default retention:

- traces: 30 days
- feedback: 90 days

Tune with:

- `SUPPORTOID_TRACE_RETENTION_DAYS`
- `SUPPORTOID_FEEDBACK_RETENTION_DAYS`

## Service accounts

For automation credentials:

- create them through `/api/v1/agent/service-accounts`
- rotate them regularly
- revoke unused accounts
- scope them to the minimum required capabilities

## Sync and migration

Useful commands:

```powershell
python -m src.cli migrate
python -m src.cli sync --limit 100
```

Use migration when importing legacy JSON or JSONL artifacts. Use sync to flush queued adapter events.

## Incident handling

Suggested incident triage order:

1. Check `/api/v1/health`
2. Confirm login still works
3. Review recent traces
4. Check sync backlog and adapter health
5. Review admin security report

If the adapter is down, the app can continue operating on SQLite while sync remains queued.

## Release verification

Before tagging or publishing:

- run the Python tests
- run the frontend build
- run the adapter build
- confirm no runtime DBs or logs are staged
- verify docs still match the current runtime behavior
