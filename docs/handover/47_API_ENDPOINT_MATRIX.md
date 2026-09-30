# API Endpoint Matrix

| Family | Representative endpoints | Authorization boundary |
|---|---|---|
| Authentication | `/api/v1/auth/signin`, `/api/v1/auth/mfa/*`, password reset | Auth/session |
| Context | `/api/v1/session/context` | Authenticated user |
| Data plane | `/api/v1/data-plane/products`, `investigations`, `evidence`, `search`, `export.csv` | Authenticated tenant |
| Integrations | `/api/v1/integrations/preview`, `/health/{connector_type}` | Authenticated tenant/configuration |
| Admin | `/api/v1/admin/*` | Platform administrator or scoped admin |
| Investigation | `/api/v1/investigations/*` | Tenant object/action policy |
| AI | `/api/v1/stage3/genai-health`, `/api/v1/stage3/interactions` | Tenant retrieval and AI policy |
| Health | `/health`, `/health/live` | Operational |

The running FastAPI OpenAPI document is the release-specific source for the complete route and schema list.
