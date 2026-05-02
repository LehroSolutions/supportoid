# Security

This document summarizes the current security posture for the open-source SupportOID release.

## Secure defaults

- No public default credentials are shipped
- Password hashing uses `bcrypt`
- Human sessions persist in SQLite
- Session cookies are `HttpOnly`
- Secure cookies are enabled in production profile
- Legacy anonymous API mode is disabled by default
- Deprecated `/api/*` aliases still require authentication

## Threats handled at request time

The enhanced security layer blocks high-risk input before orchestration when it detects:

- prompt injection and jailbreak patterns
- SQL injection
- NoSQL injection
- command injection
- XSS payloads
- SSRF attempts
- path traversal attempts
- oversized payloads that look like abuse or denial-of-service inputs

## Output safety

The response pipeline validates outgoing text to avoid:

- unsupported claims about completed backend actions
- accidental secret leakage
- empty or clearly unsafe output
- script-like content in returned text

## Storage redaction

Persisted traces, feedback, sync payloads, and automation audit envelopes redact common sensitive values such as:

- email addresses
- phone numbers
- card-like numbers
- bearer tokens
- API keys
- GitHub tokens
- password-like fields in JSON payloads

## Auth model

Human access:

- session cookie auth
- `support`, `analyst`, and `admin` roles

Automation access:

- bearer-token service accounts
- scoped capabilities
- approval-gated mutations for higher-risk admin actions

## Adapter trust boundary

The bundled adapter keeps `X-Adapter-Key` support and basic payload validation, but it is still positioned as:

- a demo or self-host bridge
- not a live Convex Cloud project connection
- not a hardened primary database
- something you should place behind network controls in production

## Operational hardening checklist

- Use TLS in front of the app
- Keep `SUPPORTOID_ALLOW_LEGACY_ANON=false`
- Bootstrap the first admin explicitly
- Rotate service-account tokens regularly
- Back up the SQLite database
- Keep runtime data out of Git
- Review health, traces, and security reports regularly
- Run the hardened test suites before publishing releases

## Reporting a vulnerability

Please do not open a public issue for a suspected security vulnerability.

Instead:

1. Email the maintainers listed in your project governance or release notes
2. Include a clear reproduction path and impact summary
3. Give maintainers reasonable time to validate and patch before public disclosure

If you publish this repository under your own organization, update the root [SECURITY.md](../SECURITY.md) and this doc with your preferred disclosure channel.
