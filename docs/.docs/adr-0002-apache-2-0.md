# ADR-0002: Standardize on Apache License 2.0

## Status
Accepted — 2026-07-10

## Context
Repositories previously mixed MIT, AGPL-family terms, dual commercial terms, or missing license metadata.

## Decision
All products in this constellation ship under **Apache-2.0** only, with root `LICENSE`, `NOTICE`, and package metadata aligned.

## Consequences
- Removes dual-license ambiguity for open distribution
- Requires updating badges/README/package manifests
- Commercial dual-license files are retired where present

## Related
- [License](./license.md)
- [Security](./security.md)
