# ADR-013: One Codebase, Three Deployment Roles

## Context
A tenant database created by `scripts/migrate_data_planes.py` already receives every table (the full Alembic chain), and on the shared plane the application already uses a single session for control and business data. The design must introduce the cell without re-routing tables one by one and without forking the code.
## Decision
One backend codebase and one container image run in one of three roles selected by `MDARIX_DEPLOYMENT_ROLE`: `MULTI` (today's multi-tenant behaviour, the default), `PLATFORM` (platform routes, platform jobs, platform staff only) and `CELL` (one tenant, one database, workspace and customer-admin routes, tenant jobs, no platform routes). A cell is the existing application running against a single tenant database; everything written today to the control database is then automatically in the tenant's own database.
## Rationale
This reuses the configuration the whole test suite already runs in, turns the sixteen two-database writes into single-database writes, and lets the audit screens see the whole trail, with no table moves. `MULTI` as the default guarantees that nothing changes for running tenants until a tenant is deliberately moved.
## Consequences
Mixed routers are split by role with URLs unchanged; `main.py` mounts routers and the scheduler registers jobs by role; `config_check` enforces per-role settings; sign-in in `CELL` searches one tenant only. `MULTI` is retained for development, CI and the trial sandbox. Dedicated data-plane routing is removed in a later contract release once no tenant uses it.
## Alternatives Considered
Separate services or repositories per role: rejected (code forks, microservice sprawl). Re-routing each table to the tenant plane: rejected (large, risky, unnecessary).
## Status
ACCEPTED (2026-10-08)
