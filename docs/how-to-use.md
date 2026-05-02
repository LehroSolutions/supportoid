# How To Use SupportOID

This guide is written for operators using the application day to day.

## Roles

- `support`
  Can work chats, submit feedback, and inspect traces
- `analyst`
  Can review traces, stats, cost summaries, and KB quality
- `admin`
  Can do everything above plus sync, migration, cache, memory, and service-account operations

## Daily support workflow

1. Sign in through the web app.
2. Open the chat view.
3. Ask or replay a customer issue.
4. Review the returned answer, escalation flag, and suggested actions.
5. Submit feedback when the answer was strong or when it missed the intent.

## Trace review workflow

1. Open the traces page.
2. Review the newest conversation summaries.
3. Open a specific trace when you need session-level detail.
4. Look for:
   - escalation behavior
   - grounding quality
   - fallback use
   - unexpected error markers

## Analyst workflow

Use the analytics and quality pages to review:

- overall throughput
- escalation volume
- cost summaries
- active model profile usage
- knowledge quality gaps

Analysts should pay special attention to:

- repeated fallback use
- low-quality KB entries
- unexpected spikes in blocked or escalated conversations

## Admin workflow

Admins usually handle:

- first-user bootstrap
- demo seeding when needed
- service-account lifecycle management
- sync and migration jobs
- health checks
- cache and memory maintenance

Common admin commands:

```powershell
python -m src.cli bootstrap-admin --username admin --password "change-this-password"
python -m src.cli seed-demo
python -m src.cli status
python -m src.cli sync --limit 100
```

## Agent automation usage

Service accounts are the right choice for:

- external automation
- CI or scripted health checks
- internal tooling that should not depend on browser cookies

Typical flow:

1. Admin creates a service account
2. Client calls `/api/v1/agent/capabilities`
3. Client invokes an allowed operation
4. Client polls job state or handles approval requirements

## Recommended usage patterns

- Use the browser session flow for humans.
- Use service accounts for automation.
- Use `seed-demo` only for local demos, testing, or onboarding environments.
- Keep production KB content separate from demo seed content.

## Things the app will not do

- It will not ship public default credentials.
- It will not claim backend actions like refunds or escalations unless those actions were actually verified in context.
- It will not allow anonymous use of the deprecated `/api/*` aliases by default.
