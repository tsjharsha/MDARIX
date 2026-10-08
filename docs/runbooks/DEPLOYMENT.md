# Deploying MDARIX for design partners

One Linux VM runs everything except the database: Caddy (HTTPS front door), the API, the background worker, the
scheduler and ClamAV. Postgres is a managed service with point-in-time recovery; uploaded files live in an S3 bucket.
Everything is defined in `docker-compose.prod.yml`. Settings live in two files on the VM:

| File | Template | Read by | Holds |
|---|---|---|---|
| `.env.production` | `.env.production.example` | api, worker, scheduler (and migrate, backup) | everything except the secrets below |
| `.env.migrate` | `.env.migrate.example` | the one-shot `migrate` job and the `backup` job only | the database owner's password, dedicated-plane owner URLs, the backup login, the off-site bucket keys |

The API, worker and scheduler refuse to start if an owner or backup password reaches their environment, so a
compromised long-running service never holds credentials that bypass row-level security.

**Every compose command passes `--env-file .env.production`.** Compose fills the `${...}` values in
`docker-compose.prod.yml` (image tags, domain, backup folder) only from that file, never from the services'
`env_file`; without it a fresh VM stops with "required variable MDARIX_DOMAIN is missing". The commands below are
run from the checkout folder (`~/mdarix`). To type less, add to the deploy user's `~/.profile`:

```bash
export COMPOSE_FILE=docker-compose.prod.yml COMPOSE_ENV_FILES=.env.production   # then plain "docker compose ..."
```

## 1. What you need

| Item | Recommendation |
|---|---|
| VM | Ubuntu 24.04 LTS, 4 vCPU, 8 GB RAM, 80 GB disk. The compose limits add up to about 7 GB (ClamAV 2 GB, API 2 GB, worker 1.5 GB, scheduler 1 GB, backup 1 GB, Caddy 256 MB). |
| Database | Managed PostgreSQL 16 with the `pgvector` and `pgcrypto` extensions, point-in-time recovery on (7+ days), automated daily snapshots, TLS required (AWS RDS, Azure Database for PostgreSQL Flexible Server, Google Cloud SQL). **Direct connection only, no transaction-mode pooler** (PgBouncer in transaction mode, RDS Proxy pinning aside): the scheduler holds session-level advisory locks, which a transaction pooler would hand to other clients. |
| Files | An S3 bucket in the same region (versioning on, private, SSE), `MDARIX_OBJECT_STORAGE_PROVIDER=s3`. The provider keeps uploaded files durable on its own; see BACKUP_AND_RESTORE.md for the file RPO. |
| DNS | An A record (and AAAA if IPv6) for the app domain pointing at the VM |
| Email | An SMTP account on your own domain with SPF, DKIM and DMARC set up (Amazon SES, Postmark, SendGrid, Microsoft 365) |
| Firewall | Inbound 80 and 443 from anywhere, 22 from your office/VPN only. Database reachable from the VM only. |
| Backups | A second bucket (another account or region) with versioning and object lock, and an `age` key pair whose private key is kept offline (BACKUP_AND_RESTORE.md) |
| Monitoring | An uptime monitor and a heartbeat (dead-man's switch) service, e.g. Better Stack, UptimeRobot, Healthchecks.io (section 6) |
| People | Two platform administrators (one can reset the other's MFA) and a named on-call rota (docs/handover/52_SUPPORT_AND_OWNERSHIP_HANDOVER.md) |

## 2. First deployment

### 2.1 Prepare the VM (as a sudo user)

```bash
sudo apt-get update && sudo apt-get -y upgrade
sudo apt-get install -y docker.io docker-compose-v2 git ufw fail2ban unattended-upgrades chrony
# Security updates install themselves; reboots for kernel updates are done by hand in a quiet hour.
sudo dpkg-reconfigure -plow unattended-upgrades
# SSH: keys only, no root login. Put your public key in ~/.ssh/authorized_keys first, then:
sudo sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/; s/^#\?PermitRootLogin .*/PermitRootLogin no/' /etc/ssh/sshd_config
sudo systemctl restart ssh
# Firewall: web from anywhere, SSH from your network only (Docker publishes 80/443 itself; keep the cloud firewall
# rules of section 1 as the outer layer, because Docker's port publishing bypasses ufw).
sudo ufw default deny incoming && sudo ufw allow from <office/VPN CIDR> to any port 22 proto tcp
sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw enable
sudo systemctl enable --now fail2ban chrony          # SSH brute-force bans; NTP (TOTP codes and TLS need the time)
# 4 GB swap, so a memory spike slows a service down instead of the kernel killing it.
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
sudo adduser --disabled-password deploy && sudo usermod -aG docker deploy
```

Everything below runs as `deploy`.

### 2.2 Code, settings and certificates

```bash
git clone https://github.com/stelikicherla-stack/MDARIX-R1.git ~/mdarix && cd ~/mdarix
git checkout v0.9.0                                   # the release tag you deploy
cp .env.production.example .env.production && cp .env.migrate.example .env.migrate
chmod 600 .env.production .env.migrate
# Fill every value (docs/runbooks/ENVIRONMENT_VARIABLES.md); generate secrets with the commands at the top of
# .env.production. MDARIX_RELEASE is the tag, MDARIX_IMAGE_REPOSITORY the registry path of the release images.
mkdir -p certs                                        # the managed database's CA bundle, when it is not public:
# curl -o certs/db-ca.pem <provider CA bundle URL>; chmod 644 certs/db-ca.pem; POSTGRES_SSLROOTCERT=/etc/mdarix/certs/db-ca.pem
sudo install -d -o 70 -g 70 -m 700 /var/backups/mdarix   # backup folder, owned by the backup image's user
# The lawyer-approved privacy policy, terms and trial agreement go in ./legal (legal/README.md).
echo "<read:packages token>" | docker login ghcr.io -u <github user> --password-stdin   # if the images are private
```

### 2.3 Database (once, as the managed database's admin user)

```sql
CREATE ROLE mdarix_owner LOGIN CREATEROLE PASSWORD '<MDARIX_DB_OWNER_PASSWORD>';
CREATE DATABASE mdarix OWNER mdarix_owner;
\c mdarix
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

The owner does not need to be a superuser: the migrations create the runtime role (`mdarix_runtime`) and the
read-only role themselves (CREATEROLE is enough). `MDARIX_DB_OWNER_USER=mdarix_owner` goes in `.env.production`, its
password in `.env.migrate`.

### 2.4 Pre-flight, start and check

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production pull
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm --no-deps api python -m backend.app.config_check --offline
```

Every line printed is something to fix in `.env.production` (`--offline` skips the two checks that need the migrated
database). When it prints nothing:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --no-build --wait
docker compose -f docker-compose.prod.yml --env-file .env.production ps -a      # all healthy; migrate "Exited (0)"
docker compose -f docker-compose.prod.yml --env-file .env.production exec api python -m backend.app.config_check
curl -fsS https://<your domain>/health/status          # {"status":"ok"} ("degraded" is serving; see section 6)
docker compose -f docker-compose.prod.yml --env-file .env.production exec api python -c \
  "from backend.app.readiness import readiness_report as r; import json; print(json.dumps(r(), indent=1))"
docker compose -f docker-compose.prod.yml --env-file .env.production exec api python scripts/send_test_alert.py
```

`migrate` runs on every `up`: it applies new migrations, gives the runtime role its login, grants the application
privileges, stores the system-scope token and migrates any dedicated customer databases. The API, worker and
scheduler wait for it. It connects as the owner (`MDARIX_DB_OWNER_USER` with the password from `.env.migrate`).

### 2.5 Platform administrators, backups, monitoring

Invite **two** Platform Administrators, so either can reset the other's MFA. The `migrate` service carries the owner
credentials, so bootstrap scripts run in it:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm migrate python scripts/create_platform_admin.py you@yourcompany.com --name "Your Name"
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm migrate python scripts/create_platform_admin.py colleague@yourcompany.com --name "Colleague Name"
```

Each person receives an activation link (48 hours; printed instead when email is not working). They sign in, set up
MFA (required for administrators), and create the first customer from Platform Admin > Customers & Tenants >
Onboarding.

Then set up the backup login, the backup cron jobs and the restore drill (BACKUP_AND_RESTORE.md, section 1), and the
monitors in section 6.

## 3. Upgrading

The normal CI release-evidence gate first verifies the reviewed AI golden-dataset lock. Any source, scenario, or
ground-truth change invalidates that lock and blocks release until the controlled-change procedure in
`docs/validation/AI_GOLDEN_DATASET_QUALIFICATION.md` is completed.

Before promoting a release that changes AI behaviour (prompts, providers, models, retrieval), run **Actions > AI
evaluation gate > Run workflow** with the contracted provider. It needs the `MDARIX_EVALUATION_API_KEY` repository
secret and fails unless every golden scenario passes with model-written analyses
(`scripts/run_real_evaluation.py --gate --require-model`). Do not promote a release whose gate failed.

A release is a git tag `vX.Y.Z` (matching `VERSION`). `.github/workflows/release.yml` builds the api, web and backup
images, scans them, pushes them to `ghcr.io/<owner>/<repo>/{api,web,backup}:<tag>` and lists their digests in the
GitHub release. The VM never builds: it pulls exactly those images. Read the release's CHANGELOG entry first; it
names new settings and migrations.

```bash
cd ~/mdarix && git fetch --tags && git checkout v0.9.1          # compose file, scripts and templates of the release
# compare .env.production / .env.migrate with the new templates; set MDARIX_RELEASE=v0.9.1
docker compose -f docker-compose.prod.yml --env-file .env.production --profile backup run --rm backup   # backup first
docker compose -f docker-compose.prod.yml --env-file .env.production pull
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm --no-deps api python -m backend.app.config_check --offline
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --no-build --wait   # migrate runs, then the services restart
docker compose -f docker-compose.prod.yml --env-file .env.production ps -a
```

Readiness reports `not_ready` (and `/health/status` says `down`, HTTP 503) until the schema matches the code, so a
missed migration is visible at once. The `migrate` job also upgrades every dedicated customer database (data plane)
with the same migrations (`scripts/migrate_data_planes.py --apply`; a no-op while every customer is on the shared
plane). A plane whose schema is not at the code's head refuses requests (`DATA_PLANE_SCHEMA_OUTDATED`) and readiness
names it. Each plane's connection string is `MDARIX_DATA_PLANE_<KEY>_DATABASE_URL` (`.env.production`); the migrate
job uses the plane owner's connection string `MDARIX_DATA_PLANE_<KEY>_DATABASE_URL_OWNER` (`.env.migrate`).

**Migrations are expand/contract**, so the previous release keeps working on the new schema and a rollback needs no
database change: a release only adds (nullable or defaulted columns, new tables, new indexes created concurrently) and
backfills; code stops using a column or table first, and a *later* release removes it. A migration that cannot
follow this (a rename, a type change, a destructive data fix) is called out in the CHANGELOG and needs a fresh
backup and a planned window. CI runs every new migration down and up again (`alembic downgrade -1`), but a downgrade
is a last resort on production data.

## 4. Rolling back

1. Set `MDARIX_RELEASE` to the previous tag, `git checkout <previous tag>`, then `pull` and `up -d --no-build --wait`
   as above. With expand/contract migrations the old release runs on the new schema.
2. If the new release ran a migration the old code cannot use (the CHANGELOG says so), restore the database to the
   moment before the upgrade with the provider's point-in-time recovery (BACKUP_AND_RESTORE.md, section 3), then start
   the old release.

## 5. Day-to-day

All commands run in `~/mdarix`; `dc` stands for `docker compose -f docker-compose.prod.yml --env-file .env.production`
(or plain `docker compose` with the profile exports above).

| Task | Command |
|---|---|
| Logs (JSON, one line per request, with request id) | `dc logs -f api` (also `worker`, `scheduler`, `web`) |
| Find a customer's error | search the logs for the `request_id` shown in their error message |
| Readiness detail (components, errors) | `dc exec api python -c "from backend.app.readiness import readiness_report as r; import json; print(json.dumps(r(), indent=1))"` |
| Scheduled jobs and their last run | `dc exec scheduler python scripts/run_scheduler.py --list` |
| Run every due job now | `dc exec scheduler python scripts/run_scheduler.py --once` |
| Configuration check | `dc exec api python -m backend.app.config_check` |
| Test the alert channels | `dc exec api python scripts/send_test_alert.py` |
| Backup now | `dc --profile backup run --rm backup` |
| Invite a Platform Administrator | `dc run --rm migrate python scripts/create_platform_admin.py person@yourcompany.com --name "Full Name"` |
| Rotate the system-scope token | set a new `MDARIX_RLS_SYSTEM_TOKEN`, then `dc up -d --no-build --wait` (migrate stores it, services restart) |
| Rotate the backup login's password | change `MDARIX_BACKUP_DB_PASSWORD` in `.env.migrate`, then `dc run --rm migrate python scripts/configure_backup_role.py` |
| Rotate any other key or secret | KEY_ROTATION.md: which ones rotate freely, the connector keyring, and the two that need a plan |

**Break-glass: a platform administrator lost their MFA device and no other platform administrator can reset it** (the
normal path is a colleague resetting it). On the VM:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm migrate \
  python scripts/reset_platform_admin_mfa.py admin@yourcompany.com --reason "Lost phone, ticket OPS-123" --operator "Your Name"
```

It clears that platform administrator's authenticator and recovery codes (nobody else's), ends their sessions and
records `PLATFORM_ADMIN_MFA_BREAK_GLASS_RESET` with the reason in the MDARIX_PLATFORM audit trail; they set up a new
authenticator at their next sign-in. Confirm the person's identity out of band first (a video call, not email) and
note it in the ticket.

## 6. Monitoring, alerts and logs

| Watch | How | Alert when |
|---|---|---|
| Site up | External uptime monitor on `https://<domain>/health/status` every minute (public, no detail; `ok`/`degraded` are 200, `down` is 503) | not 200 twice in a row |
| Degraded | the same monitor matching the body `"degraded"`, or the readiness command above | degraded for 15 minutes |
| Application alerts | `MDARIX_ALERT_WEBHOOK` / `MDARIX_ALERT_EMAIL`: dead letters, stopped worker, failing or missed scheduled jobs, audit-chain failures | any (see docs/handover/39_OPERATIONAL_SUPPORT_RUNBOOK.md) |
| Scheduler alive | `MDARIX_SCHEDULER_HEARTBEAT_URL` (heartbeat check, 5-minute period, 15-minute grace) | no ping |
| Backups | `MDARIX_BACKUP_HEARTBEAT_URL` (daily, 2-hour grace), backup failures on the webhook, `scripts/check_backup_age.sh` (cron) | no ping; failure; newest off-site backup older than 26 h |
| Disk | the cloud provider's agent or `node_exporter` on `/` and `/var/lib/docker` | over 80 % |
| Database | the provider's metrics: CPU, storage, connections, replication/PITR status | storage over 80 %, connections over 80 % of the limit, PITR off |
| TLS certificate | the uptime monitor's certificate check (Caddy renews 30 days ahead) | expires within 14 days |
| ClamAV | `dc ps clamav` health; the API refuses uploads it cannot scan | unhealthy (signatures stale or daemon down) |
| Containers | `dc ps -a`: every long-running service has a health check (api, worker, scheduler, web, clamav) | any unhealthy or restarting |

Logs: every service writes JSON to Docker's `json-file` driver, at most 10 files of 20 MB per container, so a chatty
service cannot fill the disk. To keep logs in the host journal instead (one place for `journalctl`, shipping with the
host's log agent), set `{"log-driver": "journald"}` in `/etc/docker/daemon.json`, remove the `logging:` blocks (the
`x-logging` anchor) from `docker-compose.prod.yml`, restart Docker and `up -d`; bound the journal with
`SystemMaxUse=2G` in `/etc/systemd/journald.conf`.

Response targets and who is paged: docs/handover/52_SUPPORT_AND_OWNERSHIP_HANDOVER.md. Incidents:
docs/runbooks/INCIDENT_RESPONSE.md.
