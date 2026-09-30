# Current Implementation Status

| Area | Status | Evidence / boundary |
|---|---|---|
| Control-plane database | Implemented and locally validated | Alembic migrations, SQLAlchemy models, PostgreSQL 16 |
| Tenant registry and data-plane resolution | Implemented for synthetic MVP | Server-side registry resolution in `backend/app/db/data_plane.py` |
| Four customer data planes | Demo/synthetic only | Docker services `tenant-a-data` through `tenant-d-data` |
| Provider simulators | Demo/synthetic only | Eight isolated databases/services on ports 8101–8108 |
| Provider health/schema/read/history/write contract | Implemented for simulator boundary | `source_simulator/persistent_app.py`, `integration/api_contract.py` |
| Connector ingestion/outbox foundation | Partially implemented | Durable run/source ledger/outbox; full route migration remains service-by-service |
| Product/investigation/evidence data-plane cutover | Partially implemented | New data-plane routes exist; legacy routes require route-by-route validation |
| Tenant API/search/export/AI isolation | Implemented locally in selected paths | Production/hosted evidence is deferred |
| Authentication/RBAC/audit/signature foundation | Implemented or partial | MFA, certificate-backed signatures and full compliance validation remain bounded |
| AI provider abstraction | Implemented | Ollama/Groq/deterministic fallback; provider availability is environment-dependent |
| Regulatory dossier generation | Foundation/partial | Not a certified FDA/ISO submission workflow |
| Public website | Implemented locally | Claims are limited to verified MVP controls and synthetic boundary |
| Production readiness | Pending | TLS, runtime-role cutover, backups/PITR, monitoring and hosted multi-instance infrastructure |

## Important interpretation

Local tests, simulators and synthetic data prove controlled MVP behavior. They do not prove real customer connectivity, production security controls, production scale or regulatory certification.
