# AI Evaluation

SupportOID uses a hybrid evaluation approach:

- Deterministic offline tests for repeatable CI
- Optional provider-backed smoke tests for configured live environments

## Default model story

Text support uses the OpenAI-compatible profile chain from `src/config/settings.py`:

- `gpt-oss-remote`
- `gemma4-remote`
- `gpt-oss-local`
- `gemma4-local`

PersonaPlex remains optional and voice-oriented. It is not required for the default text support path.

## Guardrails under test

The support pipeline and security layer are designed to cover:

- grounded answers when KB evidence exists
- clarification when evidence is weak
- safe fallback behavior when LLM calls are unavailable or rejected
- no false claims about completed backend actions
- escalation for high-risk or high-friction support cases
- input blocking for prompt injection, SQLi, NoSQLi, command injection, XSS, SSRF, path traversal, and oversized payloads
- redaction of common secrets and basic PII in persisted artifacts

## Deterministic scenario suite

The repository includes scenario fixtures in:

```text
tests/fixtures/ai_eval_scenarios.json
```

And the deterministic evaluator in:

```text
tests/test_ai_eval_scenarios.py
```

Current scenarios cover:

- password reset
- billing confusion
- refund request
- webhook setup issues
- account compromise and security concern
- angry customer escalation
- multilingual request fallback
- weak-grounding clarification behavior

Run it with:

```powershell
python -m pytest tests/test_ai_eval_scenarios.py -q
```

## Live smoke path

Optional live tests are marked `live_llm`.

Enable them only when:

- provider credentials are configured
- network access is allowed
- you are intentionally testing a live model deployment

Example:

```powershell
$env:SUPPORTOID_RUN_LIVE_LLM_TESTS="1"
python -m pytest -m live_llm -q
```

If no live profiles are configured, the test skips cleanly.

## Recommended release gates

Before publishing a public release, run:

```powershell
python -m pytest tests/test_oss_release_hardening.py -q
python -m pytest tests/test_ai_eval_scenarios.py -q
python -m pytest tests/test_api_contracts_v1.py -q
python -m pytest tests/test_agent_api_cli.py -q
```

Recommended additional gates:

- full Python test suite
- frontend build
- adapter build
- GitHub CI and CodeQL

## Extending the scenario matrix

When adding new cases, include:

- a stable scenario ID
- the customer message
- the intended classification context
- any KB snippets used for grounding
- expected escalation and clarification outcomes
- phrases that must appear
- phrases that must not appear

That keeps the tests easy to review and useful for regressions.
