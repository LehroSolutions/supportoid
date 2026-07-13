# Architecture

**Counterparts:** [`architecture.html`](architecture.html) · [`architecture.json`](architecture.json)

- **Section:** Architecture
- **Audience:** Developers, maintainers, and security reviewers
- **Use when:** Changing system boundaries, data flow, integrations, or runtime behavior.
- **Status:** Current
- **Last reviewed:** 2026-07-13

## Purpose

Name the major responsibilities and safe change boundaries for the current release snapshot.

## On this page

- [System map](#system-map)
- [Ownership boundaries](#ownership-boundaries)
- [Safe change sequence](#safe-change-sequence)
- [Verification](#verification)

## System map

```text
React operator UI and CLI → versioned Python API → agent orchestration, storage, traces, analytics, and optional adapter bridge
```

## Ownership boundaries

- **Entry point:** `src/app/service.py`
- **Runtime and build context:** Python API and React/TypeScript operator frontend
- **Public documentation source of truth:** `docs/current/*.md`
- **Generated reader and agent counterparts:** `docs/current/*.html` and `docs/current/*.json`

## Safe change sequence

1. Identify the owning layer and its existing verification.
2. Change the source boundary before changing generated documentation.
3. Update the affected workflow, security, and quality guides.
4. Run product checks and `pnpm docs:check`.

## Verification

- Confirm the changed boundary is reflected in this guide and the related workflow.
- Ensure no current guide makes a claim that source or evidence cannot support.

## Related guides

- [Operations](operations.md)
- [Security](security.md)
- [ADR: documentation contract](adr-0004-documentation-contract.md)
