# Database Handover

## Database layers

### Control plane

The control plane is PostgreSQL 16 with pgvector, locally exposed on port 5433 as database `mdarix_r1`. It contains identity, tenant registry, memberships, subscriptions, plans, configuration, mappings, connector registrations, audit, outbox, report jobs and platform administration records.

### Customer data planes

| Tenant | Database | Port |
|---|---|---:|
| A | `mdarix_tenant_a` | 5541 |
| B | `mdarix_tenant_b` | 5542 |
| C | `mdarix_tenant_c` | 5543 |
| D | `mdarix_tenant_d` | 5544 |

The registry row, not a request parameter, determines the database and secret reference. Hosted environments must provide the referenced secret; development fallback exists only for local validation.

## Migration management

- Tool: Alembic.
- Configuration: `alembic.ini` and `infrastructure/database/migrations/env.py`.
- Current migration chain: inspect with `alembic history` and `alembic current` in the configured environment.
- Migration files include canonical business foundations, tenant lifecycle, hardening, evidence, AI, reporting, mappings, outbox reliability, regulatory and audit capabilities.

## Isolation controls

- Tenant-owned business records carry `tenant_id`.
- Composite tenant-safe relationships are used where required.
- Application authorization filters every request by authenticated tenant.
- Local PostgreSQL RLS policies provide defense in depth.
- The seven authentication/bootstrap table classes establish tenant context and remain application-authorized by design.

## Operational boundary

Local backups and restore scripts support MVP validation. Encrypted production backup storage, WAL/PITR, production TLS, KMS/key rotation, retention archive monitoring and hosted restore rehearsal remain deployment activities.
