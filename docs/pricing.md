# Pricing Notes

This repository includes pricing-like data only as product-demo and test-fixture context. It is not a billing system of record.

## Customer plan examples in seed content

Sanitized KB examples currently reference:

- Free
- Pro
- Enterprise

These values are useful for demo flows and tests, but they should not be treated as authoritative commercial policy.

## Model cost tracking

`src/agents/cost_tracker.py` records approximate per-conversation usage for analytics. It is intended for:

- local visibility
- testing
- support analytics

It is not intended for:

- official invoicing
- tax handling
- region-aware billing
- provider reconciliation

## PersonaPlex note

PersonaPlex is documented as an optional voice-oriented integration. The default text support path is the OpenAI-compatible `gpt-oss` and `gemma4` chain.
