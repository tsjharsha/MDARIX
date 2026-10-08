# ADR-016: Migration and Upgrade Policy for a Fleet of Cells

## Context
With one database per cell, tenants upgrade independently, so the platform and cells of neighbouring versions must work together, and a migration mistake would repeat in every cell.
## Decision
One Alembic chain serves every role; platform-only tables stay empty in cells and cell-only tables stay empty in the platform. Migrations follow **expand-then-contract**: a release only adds tables, nullable columns and triggers, or deprecates; drops happen one release later, after every cell has moved. During the implementation plan (P0-P12) no table is moved, renamed or dropped, and every migration has a working downgrade checked by the existing up/down/up CI step. The platform at version N must work with cells at N and N+1 (tested in CI). Upgrading a cell means: pre-upgrade backup, upgrade the signed image, migrate, smoke-test, roll back with the backup if needed. Per-cell backups use continuous archiving (pgBackRest or the managed service's point-in-time recovery) and the cell's own keys; a restore drill is run before go-live and recorded.
## Rationale
Add-only migrations make rollback always safe at the application level and keep version skew harmless; one chain avoids forks.
## Consequences
Tenant schemas use the `public` schema with clear table names (the logical groups in the design document are not separate database schemas); a dedicated-plane-routing cleanup waits for the contract release.
## Alternatives Considered
Separate migration chains per role: rejected (forks). Relying on down-migrations in production: rejected; backups plus point-in-time recovery are the rollback path.
## Status
ACCEPTED (2026-10-08)
