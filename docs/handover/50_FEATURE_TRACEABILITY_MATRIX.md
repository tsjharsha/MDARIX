# Feature Traceability Matrix

| Feature | Source | Data/API | Tests/evidence | Status |
|---|---|---|---|---|
| Tenant context | `backend/app/request_context.py` | Session context APIs | Isolation/governance tests | Implemented locally |
| Data-plane resolution | `backend/app/db/data_plane.py` | `tenant_data_planes` | Data-plane routing tests | Synthetic MVP |
| Provider contract | `integration/api_contract.py`, `source_simulator` | Health/schema/records/history | Connector contract tests | Implemented simulator boundary |
| Durable ingestion | `integration/simulator_ingestion.py` | Connector runs/source ledger/outbox | Simulator ingestion tests | Partial route coverage |
| Product/evidence context | `backend/app/data_plane_router.py` | Data-plane routes | Route-specific tests | Implemented selected paths |
| Ask MDARIX | `ask_mdarix`, `genai`, stage3 routes | AI execution/session records | AI provider tests | Advisory; provider-dependent |
| Audit/signature | governance/audit modules | Audit/signature records | Governance tests | Foundation/partial evidence |
| Frontend public capability pages | `frontend/src/PublicMegaSite.tsx`, `styles.css` | Static/content plus route handling | Frontend tests/build | Implemented locally |
