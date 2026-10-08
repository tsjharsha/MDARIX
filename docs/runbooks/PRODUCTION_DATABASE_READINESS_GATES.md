# Production database readiness gates

Database for pilots: one managed PostgreSQL 16 with point-in-time recovery ([DEPLOYMENT.md](DEPLOYMENT.md)).

| Gate | How it is met | Evidence |
|---|---|---|
| Role separation | Owner (migrate job only), `mdarix_runtime` (API, worker, scheduler), `mdarix_backup` (backup job) | `config_check.py` refuses to start as owner, superuser or BYPASSRLS role |
| Least privilege | Migrate job runs `configure_runtime_role.py` and `grant_runtime_privileges.py` | Every deploy |
| Row-level security | Hardening migration (`MDARIX_DB_HARDENING_APPLY=1` in the migrate job); system scope needs `MDARIX_RLS_SYSTEM_TOKEN` | Cross-tenant tests in the CI backend suite (e.g. `tests/test_cross_tenant_routes.py`) |
| TLS | `POSTGRES_SSLMODE=verify-full` required in production | Startup check |
| Schema at head | Readiness reports `down` when the schema is not the one the release needs | `/health/status` |
| Connections | Direct connection, no transaction-mode pooler (the scheduler holds advisory locks on a session) | [DEPLOYMENT.md](DEPLOYMENT.md) |
| Backups | Managed PITR plus nightly encrypted off-site dump; RPO 1 h, RTO 4 h | [BACKUP_AND_RESTORE.md](BACKUP_AND_RESTORE.md) |
| Monitoring | Alerts, uptime monitor on `/health/status`, backup age check | [39_OPERATIONAL_SUPPORT_RUNBOOK.md](../handover/39_OPERATIONAL_SUPPORT_RUNBOOK.md) |

Still needs evidence on the real managed database: the first restore drill, a point-in-time recovery to a chosen
timestamp, and the monitoring hookup (a test alert received, the uptime and heartbeat monitors firing). Record them
in [BACKUP_AND_RESTORE.md](BACKUP_AND_RESTORE.md) and the release notes. Settings:
[ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md). Incidents: [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md).
