# ADR-0004: Documentation counterpart contract

**Counterparts:** [`adr-0004-documentation-contract.html`](adr-0004-documentation-contract.html) · [`adr-0004-documentation-contract.json`](adr-0004-documentation-contract.json)

- **Section:** ADRs
- **Audience:** Maintainers and contributors
- **Use when:** Creating or reviewing durable product documentation.
- **Status:** Accepted
- **Last reviewed:** 2026-07-13

## Context

The public release contained useful documentation but counterpart coverage, release manifests, and build validation were inconsistent across guide families.

## Decision

Use `docs/current/*.md` as canonical current guidance. Generate an accessible HTML reader view and compact JSON navigation/search representation for each canonical guide. Generate the portal, maps, release manifest, and validation report from the same source set.

## Positive consequences

- Readers, agents, and maintainers have synchronized representations.
- Public README files can link to one stable Documentation Home.
- CI can reject incomplete or stale documentation artifacts.

## Trade-offs

- Documentation updates must include generated output.
- Historical documents remain useful evidence but are not treated as current guidance.

## Alternatives considered

- Maintain Markdown only: rejected because public browsing and machine navigation would drift.
- Hand-edit every counterpart: rejected because it increases duplication and review cost.

## Verification

Run `pnpm docs:build` followed by `pnpm docs:check`.

## Related guides

- [Contributing](contributing.md)
- [Quality](quality.md)
- [Evidence log](evidence-log.md)
