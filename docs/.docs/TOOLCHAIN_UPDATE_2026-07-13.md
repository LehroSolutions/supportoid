# Toolchain Update — 2026-07-13

**Counterparts:** [HTML](TOOLCHAIN_UPDATE_2026-07-13.html) · [JSON](TOOLCHAIN_UPDATE_2026-07-13.json)

- **Section:** Evidence logs
- **Audience:** Maintainers and release engineers
- **Use when:** Updating Bun, Node, CI, or formatting policy.
- **Status:** Current
- **Last reviewed:** 2026-07-13

## Decision

supportoid uses Bun 1.3.14 as its canonical JavaScript package manager and targets Node 24+ in CI. Legacy npm lockfile paths are ignored to prevent `npm ci` drift.

## Verification

- CI uses Bun installation rather than `npm ci`.
- Package metadata, README guidance, and workflow runtime requirements agree.
- Existing dependency majors are retained unless a tested compatibility migration is available.

## Related guides

- [Current quality guide](../current/quality.md)
- [Current evidence log](../current/evidence-log.md)
