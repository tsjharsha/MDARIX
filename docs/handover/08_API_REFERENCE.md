# API Reference and Route Families

The FastAPI application exposes OpenAPI metadata when enabled. The route inventory should be regenerated from the running application for a release-specific endpoint list.

| Route family | Purpose | Primary scope |
|---|---|---|
| `/api/v1/auth/*` | Sign-in, activation, password reset, MFA and sessions | Control plane |
| `/api/v1/session/*` | Authenticated context and session information | Control plane |
| `/api/v1/data-plane/*` | Tenant business reads, search and export | Customer data plane |
| `/api/v1/integrations/*` | Mapping preview, connector health and gateway operations | Control plane plus tenant scope |
| `/api/v1/admin/*` | Platform administration, configuration, identity and governance | Platform scope |
| `/api/v1/customers/*` and `/api/v1/tenants/*` | Customer/Tenant 360 and lifecycle | Platform/customer scope by endpoint |
| `/api/v1/investigations/*` | Investigation workspace, evidence, hypotheses and briefs | Tenant business scope |
| `/api/v1/stage3/*` | Ask MDARIX and AI interactions | Tenant business scope |
| `/health`, `/health/live` | Service health | Operational |

## Connector simulator API

All eight simulator services use the same contract:

- `GET /health`
- `GET /ready`
- `GET /schema/{entity}`
- `GET /records/{entity}`
- `GET /records/{entity}/{external_id}/history`
- `POST /records/{entity}`

Requests require `X-Provider-Token`; the token is bound to the tenant query parameter. Wrong-tenant requests return a controlled authorization failure.

## Error handling

API errors use structured codes where implemented. Connector transport normalizes authentication, rate-limit, timeout, connectivity, provider HTTP and schema failures. Credentials and provider secrets are excluded from diagnostics.
