# Production operations validation

What can be checked from outside a running deployment, and what still needs evidence from the real one.

## Health gate

```bash
MDARIX_OPERATIONAL_URLS=https://app.yourdomain.com python scripts/validate_production_operations.py
```

For every address (comma-separated; default `MDARIX_APP_URL`) the gate needs HTTP 200 from `/health/live` (the API
answers) and from `/health/status` with `ok` or `degraded`. `down` (HTTP 503: the database or its schema is not fit
for traffic) or an unreachable address fails it. `degraded` passes but names a component to look at: read
`/health/ready` on the server (DEPLOYMENT.md, section 5), which Caddy does not serve publicly.

The same gate runs inside CI against the full production stack (`prod-stack` job: Caddy, TLS database, migrate, API,
worker, scheduler, ClamAV) through `scripts/production_smoke.py --front-door`.

## Alerts and heartbeats

| What | Setting | Proof |
|---|---|---|
| Operational alerts (dead letters, stopped worker, failing or missed scheduled jobs, audit-chain failures) | `MDARIX_ALERT_WEBHOOK` and/or `MDARIX_ALERT_EMAIL` | `docker compose -f docker-compose.prod.yml --env-file .env.production exec api python scripts/send_test_alert.py` arrives |
| Scheduler stopped | `MDARIX_SCHEDULER_HEARTBEAT_URL` (dead-man's switch, pinged every 5 minutes) | the monitor shows recent pings; it alerts when they stop |
| Backup failed | `MDARIX_ALERT_WEBHOOK` (posted by the backup job) | BACKUP_AND_RESTORE.md, section 1 |
| Backups stopped arriving | `scripts/check_backup_age.sh` (cron), `MDARIX_BACKUP_HEARTBEAT_URL` | BACKUP_AND_RESTORE.md, section 1 |
| Site down | external uptime monitor on `https://<domain>/health/status` | DEPLOYMENT.md, section 6 |

The gate reports which of these are configured where it runs; configuration is not proof of delivery. The worker and
scheduler also write heartbeat files that their container health checks read (OUTBOX_AND_SCHEDULER.md).

## Still to be evidenced on the real deployment

Alert delivery to the on-call people (a test alert received), the uptime monitor and both heartbeat monitors set up,
a backup restored into a scratch database on the managed service (BACKUP_AND_RESTORE.md, section 2), and the
provider's point-in-time recovery tried once. Record each in the operations log with the date.
