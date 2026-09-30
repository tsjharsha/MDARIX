# Repository Structure

| Directory | Responsibility |
|---|---|
| `backend/app` | FastAPI application, routers, request context, models and data-plane access |
| `backend/app/db` | Control-plane session, models and data-plane session factory |
| `infrastructure/database` | Alembic migrations and validation scripts |
| `integration` | Connector gateway, provider contracts and simulator ingestion |
| `source_simulator` | Provider simulator API and simulator persistence |
| `frontend/src` | React/Vite authenticated application and public-site entry points |
| `frontend/src/features` | Customer admin, platform admin, investigator, mapping, regulatory and signature features |
| `ai`, `genai`, `retrieval`, `trust_engine` | AI orchestration, provider abstraction, retrieval and assurance |
| `investigator`, `hypothesis_engine`, `challenger`, `unknowns`, `failure_chain` | Investigation intelligence services |
| `object_storage`, `reports`, `outbox`, `communication` | Files, reports, background events and notifications |
| `tests` | Backend, integration, simulator, isolation, governance and reliability tests |
| `e2e` | Browser test configuration and evidence workflows |
| `docs` | Architecture, day reports, diagrams, evidence and handover documentation |
| `.github` | Hosted CI workflows and release gates |

## Current inventory snapshot

At the time of handover generation the repository contained approximately 1,042 tracked/untracked files, 363 Python files, 36 TypeScript/TSX files, 452 Markdown/text/Mermaid documents and 39 Alembic migration files. These counts are inventory aids, not product requirements.
