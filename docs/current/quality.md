# Quality and verification

**Counterparts:** [`quality.html`](quality.html) · [`quality.json`](quality.json)

- **Section:** Quality
- **Audience:** Contributors and release maintainers
- **Use when:** Changing product behavior, documentation, or preparing a release.
- **Status:** Current
- **Last reviewed:** 2026-07-13

## Purpose

Define the minimum evidence required before describing a change as ready.

## On this page

- [Required gates](#required-gates)
- [Documentation gate](#documentation-gate)
- [Definition of done](#definition-of-done)

## Required gates

1. Run the appropriate product command: `python -m compileall -q src`.
2. Run focused tests for changed behavior.
3. Inspect relevant empty, loading, error, disabled, desktop, and narrow-width UI states.
4. Record evidence without turning historical output into current product guidance.

## Documentation gate

`pnpm docs:build` regenerates reader, agent, portal, map, and release-manifest artifacts from canonical documentation. `pnpm docs:check` fails when counterpart, metadata, checksum, or navigation contracts are not satisfied.

## Definition of done

- The code, workflow, architecture, security, and quality docs agree.
- Every current canonical guide has Markdown, HTML, and JSON counterparts.
- Local links and counterpart metadata validate.
- The public README links to the current Documentation Home.

## Related guides

- [Contributing](contributing.md)
- [Evidence log](evidence-log.md)
- [Roadmap](roadmap.md)
