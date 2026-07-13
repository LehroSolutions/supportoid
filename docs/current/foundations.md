# Foundations

**Counterparts:** [`foundations.html`](foundations.html) · [`foundations.json`](foundations.json)

- **Section:** Foundations
- **Audience:** Support operators, Administrators, Backend and frontend contributors
- **Use when:** Starting a feature, review, or documentation update.
- **Status:** Current
- **Last reviewed:** 2026-07-13

## Purpose

Define the public documentation and experience baseline for SupportOID.

## On this page

- [Non-negotiable rules](#non-negotiable-rules)
- [Accessibility baseline](#accessibility-baseline)
- [Content rules](#content-rules)
- [Verification](#verification)

## Non-negotiable rules

- Keep product claims tied to shipped source, tests, or clearly labelled evidence.
- Preserve safe defaults and make consequential actions explicit.
- Keep current guidance separate from historical logs and release evidence.

## Accessibility baseline

- Every interactive control needs a programmatic label, visible keyboard focus, and a target size appropriate for its context.
- Do not communicate status by color alone; include text, icon, or state labels.
- Support reduced motion and explain loading, empty, error, and disabled states in workflow documentation.

## Content rules

Use task-first headings, concrete verification steps, and one source of truth per current topic. Mark unknowns as gaps instead of inferring them.

## Verification

- Review a changed interface with keyboard navigation and visible focus.
- Check that a reader can find the relevant workflow from [Start here](start-here.md).

## Related guides

- [Design system](design-system.md)
- [Patterns](patterns.md)
- [Quality](quality.md)
