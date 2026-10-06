# Production security and disaster recovery

This page is an index. The procedures live in:

| Topic | Runbook |
|---|---|
| Hosting, secrets (`.env.production` / `.env.migrate`), TLS, release and rollback by image tag | [DEPLOYMENT.md](DEPLOYMENT.md) |
| Every setting and which file holds it | [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) |
| Backups, restore drill, point-in-time recovery; targets RPO 1 hour, RTO 4 hours | [BACKUP_AND_RESTORE.md](BACKUP_AND_RESTORE.md) |
| Security incidents, breach notification, key rotation | [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md) |
| Database roles, TLS and row-level security | [DATABASE_HARDENING_RUNBOOK.md](DATABASE_HARDENING_RUNBOOK.md) |

What the code enforces: a staging or production server refuses to start on an unsafe configuration
(`backend/app/config_check.py`): API docs enabled, rate limits off, no alert destination, owner or backup database
credentials in a long-running service, a runtime role with superuser or BYPASSRLS, or `POSTGRES_SSLMODE` other than
`verify-full` in production. Only Caddy is reachable from the internet; it serves TLS and answers 404 for `/health`
and `/health/ready`.

Still needs evidence from the real deployment (record each in the runbook it belongs to):

- First restore drill and point-in-time recovery test on the managed database.
- Uptime monitor, alert channel and heartbeat monitors connected and a test alert received
  (`scripts/send_test_alert.py`).
- Performance: `scripts/k6/mdarix-smoke.js` or `scripts/benchmark_api.py` against a seeded non-production copy. No
  latency target is claimed until a result is recorded with dataset and hardware.
