# Database Dictionary

The canonical generated inventory is `docs/generated/R1_SCHEMA_INVENTORY.md`. The principal domains are:

| Domain | Representative objects |
|---|---|
| Identity and tenancy | tenants, users, memberships, sessions, MFA records |
| Product reality | products, product_versions, components, suppliers, sites, lots, changes |
| Investigation | complaints, investigations, risks, hypotheses, unknowns, failure chains, scenarios |
| Evidence | evidence, embeddings, source records, provenance and relationship tables |
| Governance | decisions, human reviews, signatures, audit events |
| Configuration | mappings, mapping versions, baselines, releases, connectors |
| Operations | connector runs, source ledgers, outbox events, report jobs, incidents |

For exact columns, constraints and migration provenance, use the generated inventory plus the SQLAlchemy models under `backend/app/db/models` and Alembic files under `infrastructure/database/migrations/versions`.
