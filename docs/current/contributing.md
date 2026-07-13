# Contributing

**Counterparts:** [`contributing.html`](contributing.html) · [`contributing.json`](contributing.json)

- **Section:** Contributing
- **Audience:** Contributors and maintainers
- **Use when:** Preparing a pull request or changing product/documentation behavior.
- **Status:** Current
- **Last reviewed:** 2026-07-13

## Purpose

Provide a safe contribution path that keeps source, tests, and documentation aligned.

## On this page

- [Change workflow](#change-workflow)
- [Documentation workflow](#documentation-workflow)
- [Verification](#verification)

## Change workflow

1. Read [Start here](start-here.md), then the workflow and architecture guide that owns your change.
2. Keep scope small and preserve backward compatibility unless a documented decision changes it.
3. Add or update focused tests and evidence.
4. Update current guides before merging.

## Documentation workflow

1. Edit canonical prose in `docs/current/*.md`.
2. Run `pnpm docs:build`.
3. Run `pnpm docs:check`.
4. Review generated HTML and JSON changes together with the Markdown source.

## Verification

A contribution is ready only when product checks and the documentation gate both pass.

## Related guides

- [Quality](quality.md)
- [ADR: documentation contract](adr-0004-documentation-contract.md)
- [Evidence log](evidence-log.md)
