# Production operations

Use Node 24+, Bun 1.3.14, and Python 3.11+ in a dedicated virtual environment. Install JS dependencies from the root with `bun install --frozen-lockfile`, and Python dependencies with `python -m pip install -r requirements-dev.txt`. `requirements.txt` loads `constraints.txt` to pin the verified dependency versions; refresh those pins intentionally with the full release gate. Run `bun run verify` before a release; it checks JS formatting/lint/build and Python behavior. The adapter runtime regression requires its compiled output, which the JS build produces first. Never point tests at live data; omitted Settings runtime paths are isolated automatically under `.pytest-fixtures/`.

Configure the variables documented in `.env.example`. Provision the first account with `python -m src.cli bootstrap-admin --username <operator> --password <initial-password>` in the intended environment. Use a unique password and protect shell history. Production runs need HTTPS and `SUPPORTOID_DEPLOYMENT_PROFILE=production` for secure cookies. Configure an enabled model profile and its provider credentials to verify live model responses; local fallback tests do not prove provider availability or answer quality.

The optional adapter binds to loopback by default. Public binds and `NODE_ENV=production` require `ADAPTER_API_KEY` with at least 32 characters. Set the identical value in `SUPPORTOID_CONVEX_API_KEY`; Docker Compose requires it and exposes the adapter only inside the Compose network. The adapter remains a single-process JSON store: run one writer per `ADAPTER_DATA_FILE`. Event IDs are immutable idempotency keys; retrying identical content succeeds, while different content returns 409.

Before upgrades, stop writes and back up the entire data volume and configuration separately. SQLite backups must include a consistent database snapshot (use SQLite's backup API or stop the app before copying the database and its WAL/SHM files). Keep adapter JSON backups outside the served filesystem and restrict access to the service account. Adapter writes promote a fully written temporary file atomically; corrupt existing JSON stops startup instead of silently replacing records. Restore a validated backup while stopped, then start one instance and verify auth, chat, traces, sync, and logout.

Changing a user's password or role revokes existing sessions. Disabling an account blocks login and session reuse. After recovery, rotate credentials if the data or configuration may have been exposed. Roll back to the previous application version together with a compatible data backup; do not overwrite a newer schema blindly.

Deployment gates still requiring the target environment are HTTPS/reverse-proxy behavior, real model-provider calls, backups restored on the target storage, and workload latency under expected concurrency. Docker images must be built and smoke-tested on the target platform before rollout.

After the full verify gate, run `bunx playwright install chromium` and
`bun run test:browser` for the built React application against isolated local
FastAPI and adapter processes. Set `PLAYWRIGHT_CHANNEL=chrome` to use an installed
Chrome browser instead. The script uses `.venv` by default; `SUPPORTOID_TEST_PYTHON`
can select another prepared interpreter. It bootstraps synthetic accounts, keeps
all runtime files temporary, disables model profiles, and checks chat/feedback,
per-user conversation-ID restore, login/logout failures, authorization and sync.
Only a conversation ID is kept per browser tab; chat content stays on the server.
Login or logout network failures remain visible and can be retried.

`bun run verify:deps` checks the actual workspace resolutions of Vite, React
Router and the browser driver against their pins. A root install can leave
older independent workspace `node_modules` trees behind. If this check fails,
preserve any needed local dependency patches, move the generated dependency
trees out of the checkout, and perform a fresh root frozen install. A matching
lockfile alone does not prove that the local build uses its resolved versions.

Python pins include patched Requests, urllib3, Starlette, certifi, Pygments,
pytest and the development installer. Check `python -m pip check` after installing
requirements. Cached enhanced-orchestrator answers are scoped to the caller and
thread; warm requests still run input guards and rate limits while avoiding
redundant classification. Intent-specific TTL metadata remains unchanged.
