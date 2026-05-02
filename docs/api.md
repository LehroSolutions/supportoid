# API Reference

SupportOID exposes two public HTTP surfaces:

- Human-facing application API: `/api/v1`
- Agent automation API: `/api/v1/agent`

Deprecated compatibility aliases remain under `/api/*` and include deprecation headers, but they still require authentication.

## Human auth

### Login

`POST /api/v1/auth/login`

Request:

```json
{
  "username": "admin",
  "password": "change-this-password"
}
```

Response:

```json
{
  "ok": true,
  "user": {
    "username": "admin",
    "role": "admin"
  },
  "message": "Login successful"
}
```

Notes:

- Successful login sets the `supportoid_session` cookie.
- If no users exist yet, login returns `503` with a bootstrap hint.

### Logout

`POST /api/v1/auth/logout`

### Current user

`GET /api/v1/auth/me`

## Human API endpoints

### Chat

`POST /api/v1/chat`

```json
{
  "message": "How do I reset my password?",
  "conversation_id": null,
  "user_id": "alice",
  "tier": "free"
}
```

### Feedback

`POST /api/v1/feedback`

```json
{
  "conversation_id": "conv_123",
  "rating": 5,
  "feedback_text": "Helpful answer",
  "corrected_intent": ""
}
```

### Traces

- `GET /api/v1/traces?limit=50&offset=0`
- `GET /api/v1/traces/{session_id}`

### Analytics and health

- `GET /api/v1/stats`
- `GET /api/v1/costs`
- `GET /api/v1/kb-quality`
- `GET /api/v1/health`

### Admin-only mutations

- `POST /api/v1/sync`
- `POST /api/v1/migrate`
- `GET /api/v1/admin/security/report`
- `GET /api/v1/admin/cache/stats`
- `POST /api/v1/admin/cache/clear`
- `GET /api/v1/admin/memory/status`
- `POST /api/v1/admin/memory/cleanup`
- `GET /api/v1/admin/sessions`
- `GET /api/v1/admin/rate-limit`
- `GET /api/v1/admin/tier`

## Agent automation API

Service accounts authenticate with `Authorization: Bearer <token>`.

### Capabilities

`GET /api/v1/agent/capabilities`

### Invoke

`POST /api/v1/agent/invoke`

Headers:

- `Authorization: Bearer <service-account-token>`
- `Idempotency-Key: <required for mutating idempotent operations>`

Body:

```json
{
  "operation_id": "chat.send",
  "input": {
    "message": "Need help with billing"
  }
}
```

### Jobs

- `GET /api/v1/agent/jobs`
- `GET /api/v1/agent/jobs/{job_id}`

### Approvals

`POST /api/v1/agent/approvals/{approval_id}/decision`

### Service-account management

- `GET /api/v1/agent/service-accounts`
- `POST /api/v1/agent/service-accounts`
- `POST /api/v1/agent/service-accounts/{account_id}/rotate`
- `POST /api/v1/agent/service-accounts/{account_id}/revoke`

## CSRF behavior

Browser clients receive a `csrf_token` cookie. For state-changing `/api/*` requests that include an `Origin` or `Referer` header, send the same token back as `X-CSRF-Token`.

## Error model

Errors use a `ProblemDetail`-style shape:

```json
{
  "type": "https://supportoid.dev/errors/validation",
  "title": "Validation failed",
  "status": 422,
  "detail": "Request validation failed",
  "request_id": "..."
}
```

Common status codes:

- `401` unauthenticated
- `403` forbidden
- `404` not found
- `409` idempotency conflict or already-decided approval
- `422` validation failure
- `429` rate-limited
- `500` internal error

## Compatibility headers for legacy aliases

Responses from `/api/*` compatibility routes include:

- `Deprecation: true`
- `Sunset: 2026-12-31`
- `Link: <successor>; rel="successor-version"`
