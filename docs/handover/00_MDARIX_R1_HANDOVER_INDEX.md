# MDARIX-R1 Product and Technical Handover

## Purpose

This handover describes the implementation currently present in the repository. Status labels are evidence-based and do not convert synthetic validation into production readiness.

## Current baseline

- Product: MDARIX R1, a system of intelligence rather than a system of record.
- Control plane: FastAPI, SQLAlchemy, Alembic, PostgreSQL 16 and pgvector.
- Frontend: React/Vite TypeScript application plus public MDARIX website surfaces.
- Customer validation topology: four isolated synthetic PostgreSQL data planes.
- Provider validation topology: eight isolated simulator databases and authenticated APIs.
- Production customer endpoints, hosted monitoring, production TLS and production credentials are outside the current synthetic MVP boundary.

## Document map

| Document | Coverage |
|---|---|
| [01 Executive overview](01_EXECUTIVE_PRODUCT_OVERVIEW.md) | Product, users, journey and scope |
| [02 Implementation status](02_CURRENT_IMPLEMENTATION_STATUS.md) | Reconciled implementation classification |
| [03 Repository structure](03_REPOSITORY_STRUCTURE.md) | Source ownership and module map |
| [04 System architecture](04_SYSTEM_ARCHITECTURE.md) | Runtime and data-flow architecture |
| [05 Domain and data model](05_DOMAIN_AND_DATA_MODEL.md) | Core business objects and relationships |
| [06 Database handover](06_DATABASE_HANDOVER.md) | Database topology, migrations and isolation |
| [07 Backend architecture](07_BACKEND_ARCHITECTURE.md) | API/service/request flow |
| [08 API reference](08_API_REFERENCE.md) | API route inventory and behavior |
| [09 Frontend handover](09_FRONTEND_APPLICATION_HANDOVER.md) | Authenticated UI and public site |
| [12 Tenant isolation](12_TENANT_ISOLATION.md) | Tenant boundaries and tests |
| [20 AI architecture](20_AI_GENAI_AGENTIC_ARCHITECTURE.md) | AI providers, grounding and safety |
| [24 Integrations](24_INTEGRATION_ARCHITECTURE.md) | Connector contract and simulators |
| [37 Testing and validation](37_TESTING_QA_VALIDATION.md) | Test commands and evidence |
| [42 Limitations and debt](42_KNOWN_LIMITATIONS_TECHNICAL_DEBT.md) | Open gaps and deferred work |
| [44 Configuration reference](44_CONFIGURATION_REFERENCE.md) | Environment/configuration guidance |
| [46 Database dictionary](46_DATABASE_DICTIONARY.md) | Current table domains |
| [47 API matrix](47_API_ENDPOINT_MATRIX.md) | Route-level matrix |
| [48 UI matrix](48_UI_SCREEN_AND_ACTION_MATRIX.md) | Screen/action matrix |
| [50 Feature traceability](50_FEATURE_TRACEABILITY_MATRIX.md) | Feature-to-source/test traceability |

Additional domain and operational documents are added as the inventory is reconciled.

## Evidence rule

`Implemented` means source code and reasonable local evidence exist. `Synthetic only` means the behavior is validated against simulators or local tenants. `Production pending` means infrastructure, credentials, deployment or customer evidence is still required.
