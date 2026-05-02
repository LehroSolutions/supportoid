# Security Policy

## Supported use
- The public repository is intended for self-hosted development and evaluation.
- The bundled adapter is a lightweight sync bridge, not a hardened primary datastore.

## Reporting
- Please report suspected vulnerabilities privately through your standard coordinated disclosure channel before opening a public issue.
- Include reproduction steps, affected versions or commits, and any proposed mitigations if available.

## Security expectations
- Do not commit secrets, tokens, traces, or production datasets.
- Service accounts and bootstrap users should be created with strong credentials.
- Legacy anonymous API mode is disabled by default and should stay off outside controlled local testing.
