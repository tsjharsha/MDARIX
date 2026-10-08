# Database hardening

In production the hardening is applied by the one-shot `migrate` job on every deploy ([DEPLOYMENT.md](DEPLOYMENT.md)).
It runs with the database owner's credentials from `.env.migrate`, which no long-running service holds, and in order:

1. `alembic upgrade head` with `MDARIX_DB_HARDENING_APPLY=1` (row-level security policies on every tenant-owned table).
2. `scripts/configure_runtime_role.py`: gives `mdarix_runtime` (or `MDARIX_DB_RUNTIME_USER`) a login with
   `MDARIX_DB_RUNTIME_PASSWORD`, always without superuser, BYPASSRLS, CREATEDB or CREATEROLE.
3. `scripts/grant_runtime_privileges.py`: the runtime role's table and sequence grants (also needed after a restore).
4. `scripts/set_rls_system_token.py`: stores the hash of `MDARIX_RLS_SYSTEM_TOKEN`, which the runtime role cannot read.
5. `scripts/migrate_data_planes.py --apply`: the same schema for dedicated tenant databases.

Backups run as `mdarix_backup` with BYPASSRLS, created by `scripts/configure_backup_role.py` where the provider allows
it; otherwise the backup reads through the system scope ([BACKUP_AND_RESTORE.md](BACKUP_AND_RESTORE.md)).

The API, worker and scheduler refuse to start (`backend/app/config_check.py`) when they connect as a superuser, a
BYPASSRLS role or the schema owner, when the owner or backup password is in their environment, when the database does
not hold their system-scope token, or, in production, when `POSTGRES_SSLMODE` is not `verify-full`.

Every request binds its transaction to one organization (`app.tenant_id`) or to an audited system scope
(`backend/app/db/tenant_scope.py`); a session with neither sees no tenant-owned rows. Connect directly, not through a
transaction-mode pooler. Settings: [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md). Rotation after an incident:
[INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md).
