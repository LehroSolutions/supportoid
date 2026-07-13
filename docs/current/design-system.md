# Design system

**Counterparts:** [`design-system.html`](design-system.html) · [`design-system.json`](design-system.json)

- **Section:** Design system
- **Audience:** Product designers and frontend contributors
- **Use when:** Adding or reviewing reusable UI, interaction, or content states.
- **Status:** Current
- **Last reviewed:** 2026-07-13

## Purpose

Document the shared interface contract without replacing product-specific implementation details.

## On this page

- [Visual grammar](#visual-grammar)
- [Interaction states](#interaction-states)
- [Component contract](#component-contract)
- [Verification](#verification)

## Visual grammar

Use a clear hierarchy, a restrained accent color, readable system typography, semantic borders, and whitespace before elevation. Keep data-dense views responsive and preserve reading order on small screens.

## Interaction states

Every consequential control documents or implements: default, hover, keyboard focus, disabled, loading, success, empty, and error/recovery states.

## Component contract

Reusable controls must define label, purpose, inputs, variants, validation, accessibility behavior, and safe fallback state. Product screens should compose these contracts rather than introduce competing patterns.

## Verification

- Capture desktop and approximately 390px views for changed screens.
- Check no overflow, overlap, unlabeled controls, or color-only state indicators remain.

## Related guides

- [Foundations](foundations.md)
- [Patterns](patterns.md)
- [Quality](quality.md)
