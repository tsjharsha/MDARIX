# Backup and restore

Targets: lose at most **1 hour** of data (RPO) and be back within **4 hours** (RTO).

MDARIX keeps three things: the control database (identities, audit trail, signatures, every shared-plane tenant's
records), any dedicated tenant databases, and uploaded files. Two independent layers protect them.

| Layer | What | How often | Kept |
|---|---|---|---|
| 1. Managed database | Point-in-time recovery of every database (provider feature) | continuous | 7+ days |
| 1. Managed database | Automated snapshots | daily | 14+ days |
| 2. MDARIX backup | Encrypted logical dump of every database plus the uploaded files, copied off-site | daily (cron) | 14 days local, 90 days off-site (bucket lifecycle rule) |

Layer 2 does not depend on the database provider, so it also covers a lost account or a provider outage.

## 1. Set up (once)

1. **Point-in-time recovery**: turn it on in the managed database with at least 7 days of retention, and automated
   daily snapshots.
2. **Encryption key**: on your own computer (not the server), create an age key pair:
   ```bash
   age-keygen -o mdarix-backup.key       # prints the public key: age1...
   ```
   Put the public key in `.env.production` as `MDARIX_BACKUP_AGE_RECIPIENT`. Keep `mdarix-backup.key` offline in two
   places (password manager and a sealed envelope). Without it the backups cannot be read; the server never has it.
3. **Off-site copy**: create a bucket with versioning, object lock (or a retention policy) and a 90-day lifecycle
   rule; give the VM write-only access; set `MDARIX_BACKUP_S3_URI`.
4. **Schedule** on the VM (`crontab -e` as the deploy user):
   ```cron
   15 2 * * * cd /home/deploy/mdarix && docker compose -f docker-compose.prod.yml --profile backup run --rm backup >> /var/log/mdarix-backup.log 2>&1
   ```
5. Keep the encryption keys (`MDARIX_MFA_ENCRYPTION_KEY`, `MDARIX_CONNECTOR_ENCRYPTION_KEY`,
   `MDARIX_OBJECT_STORAGE_ENCRYPTION_KEY`, `MDARIX_RLS_SYSTEM_TOKEN`) in the password manager as well: a restored
   database is of little use without the keys that open its encrypted columns and files.

## 2. Restore drill (quarterly, and before the first design partner)

1. Create an empty database `mdarix_restore_drill` on the managed server (with the `vector` extension).
2. Copy the latest backup folder to a workstation, mount the private key, and restore:
   ```bash
   docker run --rm --entrypoint mdarix-restore \
     -e PGUSER=<owner> -e PGPASSWORD=<owner password> -e MDARIX_BACKUP_AGE_KEY_FILE=/keys/mdarix-backup.key \
     -v /path/to/backups:/backups:ro -v /path/to/keys:/keys:ro mdarix-backup:<release> \
     /backups/<timestamp> control "host=<db host> port=5432 dbname=mdarix_restore_drill sslmode=require"
   ```
3. Grant the application roles their privileges (backups are taken without them):
   `POSTGRES_DB=mdarix_restore_drill python scripts/grant_runtime_privileges.py`
4. Checks: `alembic current` shows the release's head; row counts of `tenants`, `auth_users`, `audit_events`,
   `investigations`, `evidence` match the source at backup time; `SELECT count(*) FROM pg_policies` matches; a
   restored files archive extracts (`age -d -i key objects.tar.age | tar -t | head`).
5. Record the date, backup timestamp, duration and results in the operations log; drop the drill database.

### Drill record

| Date | Source | Result |
|---|---|---|
| 2026-10-03 | Local test database (`mdarix_r1_test`, md16), 11.7 MB encrypted dump | Manifest verified; restored into a new database; schema version, 112 row-level-security policies, the system-scope function and row counts of 13 tables (2,184 tenants, 4,135 accounts, 19,579 audit events) identical to the source. Found that restores carry no privileges for the runtime role; fixed with `scripts/grant_runtime_privileges.py`, now also run by the migrate job. |

## 3. Recovering production

| Situation | Action |
|---|---|
| Bad data or a bad release, database healthy | Provider point-in-time recovery to a new instance at the minute before the problem; point `POSTGRES_HOST` at it; `up -d` (migrate re-grants privileges). |
| Database or provider account lost | New managed instance; restore the latest layer-2 backup as in section 2; restore files: `age -d -i key objects.tar.age \| tar -x -C <objects volume>`; set `.env.production`; `up -d`. |
| VM lost | New VM, `git checkout <release>`, restore `.env.production` from the password manager, restore the `objects` volume from the latest backup, `up -d`. Caddy obtains a new certificate. |

After any restore: `python -m backend.app.config_check`, check `/health/ready`, sign in as a Platform Administrator,
and open one customer's Product 360 and audit trail before announcing recovery.
