# Open-Source Release Checklist

Use this checklist before publishing SupportOID or a fork of it to GitHub.

## Repository hygiene

- Add or verify `LICENSE`
- Add or verify `NOTICE`
- Confirm `.gitignore` and `.dockerignore` exclude runtime data and build output
- Confirm no local databases, traces, feedback logs, or model artifacts are staged
- Confirm internal-only tooling bundles are not included

## Security posture

- Confirm there are no shipped public credentials
- Confirm `SUPPORTOID_ALLOW_LEGACY_ANON=false`
- Confirm passwords are bcrypt-hashed
- Confirm session storage is persistent
- Confirm redaction tests pass
- Confirm high-risk security-block tests pass

## Documentation

- README updated
- quickstart tested
- bootstrap workflow documented
- deployment env vars documented
- API and agent API docs current
- AI evaluation docs current
- disclosure path updated in `SECURITY.md`

## Tests and builds

- `python -m pytest -q`
- `python -m pytest tests/test_oss_release_hardening.py -q`
- `python -m pytest tests/test_ai_eval_scenarios.py -q`
- `cd frontend && npm run build`
- `cd convex-adapter && npm run build`

## GitHub automation

- CI workflow enabled
- CodeQL enabled
- dependency review enabled
- Dependabot enabled
- issue templates present
- PR template present

## Final review

- Search the tree for personal secrets or local-only URLs
- Verify no generated runtime content is committed
- Verify demo KB content is sanitized
- Verify release notes and changelog are accurate
