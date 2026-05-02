# SupportOID Use Cases

## External
### Customer Support Automation
- Resolve common customer questions (billing, account, onboarding, technical issues) through AI-assisted chat.
- Escalate risky or high-friction conversations to human teams with priority and role hints.
- Provide consistent answers backed by knowledge-base retrieval and quality scoring.

### Team Analytics
- View trace summaries for each support conversation.
- Review model usage and estimated cost trends.
- Track knowledge-base quality and coverage gaps for continuous improvement.

### Multi-Role Operations
- `support` users handle daily chats and feedback.
- `analyst` users inspect trends, costs, and quality dashboards.
- `admin` users manage migrations, sync jobs, and platform-wide settings.

## Internal
### Platform Engineering
- Run a unified core backend used by web, API, and CLI.
- Maintain compatibility for legacy command names and route aliases.
- Support hybrid persistence: Convex adapter + SQLite fallback/cache.

### Data and Reliability
- Persist traces, feedback, and cost records with deterministic IDs.
- Queue sync events for retry-safe adapter delivery.
- Run migration jobs from legacy JSON/JSONL artifacts into canonical store.

