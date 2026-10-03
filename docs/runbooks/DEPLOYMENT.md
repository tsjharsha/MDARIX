# Deploying MDARIX for design partners

One Linux VM runs everything except the database: Caddy (HTTPS front door), the API, the background worker, the
scheduler and ClamAV. Postgres is a managed service with point-in-time recovery. Everything is defined in
`docker-compose.prod.yml`; settings live in `.env.production` (template: `.env.production.example`).

## 1. What you need

| Item | Recommendation |
|---|---|
| VM | Ubuntu 24.04 LTS, 4 vCPU, 8 GB RAM, 80 GB disk (ClamAV alone needs about 1.5 GB RAM) |
| Database | Managed PostgreSQL 16 with the `pgvector` extension, point-in-time recovery on (7+ days), automated daily snapshots, TLS required. AWS RDS, Azure Database for PostgreSQL Flexible Server or Google Cloud SQL all qualify. |
| DNS | An A record (and AAAA if IPv6) for the app domain pointing at the VM |
| Email | An SMTP account on your own domain with SPF, DKIM and DMARC set up (Amazon SES, Postmark, SendGrid, Microsoft 365) |
| Firewall | Inbound 80 and 443 from anywhere, 22 from your office/VPN only. Database reachable from the VM only. |
| Backups | An off-site bucket (S3-compatible) and an `age` key pair; the private key kept offline (see BACKUP_AND_RESTORE.md) |

## 2. First deployment

```bash
# On the VM, as a sudo user
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 git
sudo usermod -aG docker "$USER"   # log out and in again
git clone https://github.com/stelikicherla-stack/MDARIX-R1.git mdarix && cd mdarix
git checkout <release tag>

cp .env.production.example .env.production
chmod 600 .env.production
# Fill every value (see docs/runbooks/ENVIRONMENT_VARIABLES.md). Generate secrets with the commands at the top of the file.
```

Database preparation (once, as the managed database's admin user):

```sql
CREATE DATABASE mdarix;
\c mdarix
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
-- MDARIX_DB_OWNER_USER owns the schema; the migrations create the runtime role (mdarix_runtime).
```

Check the configuration before starting anything:

```bash
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml run --rm --no-deps api python -m backend.app.config_check
```

Every line printed is something to fix in `.env.production`. When it prints nothing:

```bash
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml ps          # all services healthy; migrate "exited (0)"
curl -fsS https://$MDARIX_DOMAIN/health/live           # {"status":"alive"}
docker compose -f docker-compose.prod.yml exec api python -c \
  "from backend.app.readiness import readiness_report as r; import json; print(json.dumps(r(), indent=1))"
```

`migrate` runs on every `up`: it applies new migrations, gives the runtime role its login and stores the
system-scope token. The API waits for it to finish.

Create the first Platform Administrator:

```bash
docker compose -f docker-compose.prod.yml run --rm -e POSTGRES_USER=$MDARIX_DB_OWNER_USER \
  -e POSTGRES_PASSWORD=$MDARIX_DB_OWNER_PASSWORD api python scripts/create_platform_admin.py you@yourcompany.com
```

The script emails an activation link (72 hours). Sign in, set up MFA (required for administrators), then create the
first customer from Platform Admin > Customers & Tenants > Onboarding.

## 3. Upgrading

Before promoting a release that changes AI behaviour (prompts, providers, models, retrieval), run **Actions > AI
evaluation gate > Run workflow** with the contracted provider. It needs the `MDARIX_EVALUATION_API_KEY` repository
secret and fails unless every golden scenario passes with model-written analyses
(`scripts/run_real_evaluation.py --gate --require-model`). Do not promote a release whose gate failed.

```bash
cd mdarix && git fetch --tags && git checkout <new release tag>
docker compose -f docker-compose.prod.yml --profile backup run --rm backup     # backup first
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d                                # migrate runs, then the API restarts
docker compose -f docker-compose.prod.yml ps
```

Readiness reports `not_ready` (HTTP 503) until the schema matches the code, so a missed migration is visible at once.
The `migrate` job also upgrades every dedicated customer database (data plane) with the same migrations
(`scripts/migrate_data_planes.py --apply`; a no-op while every customer is on the shared plane). A plane whose schema
is not at the code's head refuses requests (`DATA_PLANE_SCHEMA_OUTDATED`) and readiness names it. Each plane's
connection string is `MDARIX_DATA_PLANE_<KEY>_DATABASE_URL`; give the migrate job the plane owner's connection string
as `MDARIX_DATA_PLANE_<KEY>_DATABASE_URL_OWNER`.

## 4. Rolling back

1. `git checkout <previous tag>` and `docker compose ... up -d --build`.
2. If the new release ran migrations that the old code cannot use, restore the database to the moment before the
   upgrade with the provider's point-in-time recovery (BACKUP_AND_RESTORE.md, section 3), then start the old release.
   Downgrade migrations exist for every schema change but are a last resort on production data.

## 5. Day-to-day

| Task | Command |
|---|---|
| Logs (JSON, one line per request, with request id) | `docker compose -f docker-compose.prod.yml logs -f api` |
| Find a customer's error | search the logs for the `request_id` shown in their error message |
| Scheduled jobs and their last run | `docker compose -f docker-compose.prod.yml exec scheduler python scripts/run_scheduler.py --list` |
| Configuration check | `docker compose -f docker-compose.prod.yml exec api python -m backend.app.config_check` |
| Backup now | `docker compose -f docker-compose.prod.yml --profile backup run --rm backup` |
| Rotate the system-scope token | set a new `MDARIX_RLS_SYSTEM_TOKEN`, then `up -d` (migrate stores it, services restart) |

Alerts (dead letters, a stopped worker, a scheduled job failing three times) go to `MDARIX_ALERT_WEBHOOK` and/or
`MDARIX_ALERT_EMAIL`. Uptime: point an external monitor (UptimeRobot, Better Stack, Pingdom) at
`https://<domain>/health/live` every minute.
