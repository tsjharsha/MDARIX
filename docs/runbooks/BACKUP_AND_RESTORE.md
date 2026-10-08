# Backup and restore

Targets: lose at most **1 hour** of database changes (RPO) and be back within **4 hours** (RTO).

MDARIX keeps three things: the control database (identities, audit trail, signatures, every shared-plane tenant's
records), any dedicated tenant databases, and uploaded files. Two independent layers protect them.

| Layer | What | How often | Kept |
|---|---|---|---|
| 1. Managed database | Point-in-time recovery of every database (provider feature) | continuous | 7+ days |
| 1. Managed database | Automated snapshots | daily | 14+ days |
| 1. File bucket (pilots: `MDARIX_OBJECT_STORAGE_PROVIDER=s3`) | Object versioning in the bucket that holds uploaded files | every write | 90 days of old versions (lifecycle rule) |
| 2. MDARIX backup | Encrypted logical dump of every database (plus the `objects` volume when files are stored locally), copied off-site | daily (cron) | 14 days local, 90 days off-site (bucket lifecycle rule) |

Erased data stays in these backups for that period; see section 4.

Layer 2 does not depend on the database provider, so it also covers a lost account or a provider outage.

**File RPO.** Database changes are protected to the minute by point-in-time recovery; uploaded files are not part of
it. With the pilot choice, files in an S3 bucket with versioning, a stored file is durable as soon as the upload
finishes and an overwritten or deleted one can be recovered from its previous version, so the file RPO is
effectively zero for the provider's own failures. Files are *not* in the daily layer-2 dump in that setup: losing the
bucket's account loses them, which is why the bucket has versioning and the backup bucket lives in another account.
With `MDARIX_OBJECT_STORAGE_PROVIDER=local`, files exist only on the VM's `objects` volume and are copied off-site by
the daily backup: up to **24 hours** of uploads can be lost with the VM.

## 1. Set up (once)

1. **Point-in-time recovery**: turn it on in the managed database with at least 7 days of retention, and automated
   daily snapshots. Turn on versioning in the files bucket with a 90-day rule for noncurrent versions.
2. **Encryption key**: on your own computer (not the server), create an age key pair:
   ```bash
   age-keygen -o mdarix-backup.key       # prints the public key: age1...
   ```
   Put the public key in `.env.production` as `MDARIX_BACKUP_AGE_RECIPIENT`. Keep `mdarix-backup.key` offline in two
   places (password manager and a sealed envelope). Without it the backups cannot be read; the server never has it.
3. **Off-site copy**: create a bucket in another account or region with versioning, object lock (or a retention
   policy) and a 90-day lifecycle rule. Give the VM credentials that may only write and list it
   (`s3:PutObject`, `s3:ListBucket`): `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_DEFAULT_REGION` in
   `.env.migrate` (or an instance role), and `MDARIX_BACKUP_S3_URI` in `.env.production`.
4. **Backup folder** on the VM, owned by the backup image's user (uid 70); the job stops with this hint when the
   folder is not writable:
   ```bash
   sudo install -d -o 70 -g 70 -m 700 /var/backups/mdarix
   ```
5. **Backup login.** Row-level security is forced on every tenant table, for the schema owner too, so `pg_dump` can
   only read every row as a role that bypasses it. Set `MDARIX_BACKUP_DB_PASSWORD` (24+ random characters) in
   `.env.migrate`, then:
   ```bash
   docker compose -f docker-compose.prod.yml --env-file .env.production run --rm migrate python scripts/configure_backup_role.py
   ```
   It creates `mdarix_backup`: it may log in and read every table and sequence (also those later migrations add), and
   nothing else. It gives the role `BYPASSRLS` when the owner may grant it. **Managed providers often do not allow
   that** (PostgreSQL 16 lets only a superuser, or a CREATEROLE account that has BYPASSRLS itself, grant it; RDS,
   Azure and Cloud SQL do not give their admin users superuser). The script then says so and the role is created
   without it; ask the provider's admin user to run `ALTER ROLE mdarix_backup BYPASSRLS;` if their service permits.
   Without BYPASSRLS the backup still reads every row, through the application's system scope: it sends
   `MDARIX_RLS_SYSTEM_TOKEN` for its own session (`pg_dump --enable-row-security`), under which every policy shows
   every row, and it first checks that the database accepts the token, refusing to write a dump that could silently
   miss rows. Each run logs which way it read. Without a backup login the job uses the owner the same way.
6. **Schedule** on the VM (`crontab -e` as the deploy user): the backup at 02:15 UTC, the age check two hours later.
   ```cron
   15 2 * * * cd /home/deploy/mdarix && docker compose -f docker-compose.prod.yml --env-file .env.production --profile backup run --rm backup >> /var/log/mdarix-backup.log 2>&1
   15 4 * * * cd /home/deploy/mdarix && docker compose -f docker-compose.prod.yml --env-file .env.production --profile backup run --rm --entrypoint mdarix-check-backup-age backup >> /var/log/mdarix-backup.log 2>&1
   ```
   (`sudo touch /var/log/mdarix-backup.log && sudo chown deploy /var/log/mdarix-backup.log` first.)
7. **Alerts.** A failed backup posts to `MDARIX_ALERT_WEBHOOK` (the job cannot send email) and removes its incomplete
   folder. A successful one pings `MDARIX_BACKUP_HEARTBEAT_URL`: set a daily heartbeat check with a 2-hour grace, so
   a backup that never runs (cron removed, VM rebuilt) is noticed too. `scripts/check_backup_age.sh` (the second cron
   line) alerts on the webhook when the newest off-site backup is older than 26 hours (`MDARIX_BACKUP_MAX_AGE_HOURS`).
8. Keep the encryption keys (`MDARIX_MFA_ENCRYPTION_KEY`, `MDARIX_CONNECTOR_ENCRYPTION_KEY`,
   `MDARIX_OBJECT_STORAGE_ENCRYPTION_KEY`, `MDARIX_RLS_SYSTEM_TOKEN`) and both settings files in the password manager
   as well: a restored database is of little use without the keys that open its encrypted columns and files.

Each backup is a folder `<UTC timestamp>/` holding `control.dump.age`, `plane-<key>.dump.age` per dedicated
database (dumped with its owner URL `MDARIX_DATA_PLANE_<KEY>_DATABASE_URL_OWNER` when set), `objects.tar.age` when
files are stored locally, and `MANIFEST.sha256`. Database connections use the application's TLS settings
(`POSTGRES_SSLMODE`, with `POSTGRES_SSLROOTCERT` or the system's public CAs).

## 2. Restore drill (quarterly, and before the first design partner)

1. Create an empty database `mdarix_restore_drill` on the managed server, owned by the MDARIX owner, and as the
   provider's admin user create both extensions in it: `CREATE EXTENSION vector; CREATE EXTENSION pgcrypto;`
2. Copy the latest backup folder to a workstation, mount the private key, and restore as the owner:
   ```bash
   docker run --rm --entrypoint mdarix-restore \
     -e PGPASSWORD=<owner password> -e MDARIX_BACKUP_AGE_KEY_FILE=/keys/mdarix-backup.key \
     -v /path/to/backups:/backups:ro -v /path/to/keys:/keys:ro -v /path/to/ca:/certs:ro \
     ghcr.io/<owner>/<repo>/backup:<release> \
     /backups/<timestamp> control "host=<db host> port=5432 dbname=mdarix_restore_drill user=<owner> sslmode=verify-full sslrootcert=/certs/db-ca.pem"
   ```
   The manifest is checked first. Extension comments are skipped (only the extension's owner may set them); the
   tables' row-level security, policies and forced RLS come back as they were. Files stored locally restore into an
   empty folder with `... /backups/<timestamp> objects /restore/objects` (mount that folder).
3. Grant the application roles their privileges and store the system-scope token (backups are taken without
   privileges), with only those two steps of the migrate job (its full command would also migrate the live
   dedicated databases from the drill's registry):
   `docker compose -f docker-compose.prod.yml --env-file .env.production run --rm -e POSTGRES_DB=mdarix_restore_drill migrate sh -c "python scripts/grant_runtime_privileges.py && python scripts/set_rls_system_token.py"`.
4. `python scripts/reapply_erasures.py --dry-run` on the drill database — record the count of pending
   re-applications (it should list erasures made after the backup's timestamp).
5. Checks: `alembic current` shows the release's head; row counts of `tenants`, `auth_users`, `audit_events`,
   `investigations`, `evidence` match the source at backup time; `SELECT count(*) FROM pg_policies` matches; a
   restored files archive extracts (`age -d -i key objects.tar.age | tar -t | head`).
6. Record the date, backup timestamp, duration and results in the operations log; drop the drill database.

CI runs the same drill on every change (`prod-stack` job): a backup with the BYPASSRLS login and one through the
system scope, each restored into a scratch database and checked with `alembic current` and row counts.

### Drill record

| Date | Source | Result |
|---|---|---|
| 2026-10-03 | Local test database (`mdarix_r1_test`, md16), 11.7 MB encrypted dump | Manifest verified; restored into a new database; schema version, 112 row-level-security policies, the system-scope function and row counts of 13 tables (2,184 tenants, 4,135 accounts, 19,579 audit events) identical to the source. Found that restores carry no privileges for the runtime role; fixed with `scripts/grant_runtime_privileges.py`, now also run by the migrate job. |
| 2026-10-05 | Throw-away PostgreSQL 16 with TLS (`verify-full`) and a **non-superuser** owner (CREATEROLE only), as on a managed service; schema md25 | Migrations, runtime role and backup role ran as that owner; the owner could not grant BYPASSRLS, so the backup read through the system scope; restored as the owner into a fresh database: md25 head, 117 policies, 117 tables with forced RLS, tenants, accounts and the token hash identical. Same result with a BYPASSRLS backup login. The files archive restored into an empty folder. A wrong system token failed the run before dumping, with an alert attempt. |

## 3. Recovering production

| Situation | Action |
|---|---|
| Bad data or a bad release, database healthy | Provider point-in-time recovery to a new instance at the minute before the problem; point `POSTGRES_HOST` at it; `up -d --no-build --wait` (migrate re-grants privileges). Then section 4. |
| Database or provider account lost | New managed instance; restore the latest layer-2 backup as in section 2; restore locally stored files with `mdarix-restore ... objects <empty folder>` and copy them into the `objects` volume; set `.env.production`; `up -d --no-build --wait`. Then section 4. |
| VM lost | New VM (DEPLOYMENT.md, section 2), `git checkout <release>`, restore `.env.production` and `.env.migrate` from the password manager, restore the `objects` volume from the latest backup when files are stored locally, `up -d --no-build --wait`. Caddy obtains a new certificate. |
| Files bucket damaged | Restore the affected objects' previous versions in the bucket (versioning), then section 4, step 2 (purged organizations' files must not come back). |

## 4. Re-apply erasures after any restore

The scripts below need the owner's credentials. On the VM run them in the migrate job with a folder for the log
file, e.g. `docker compose -f docker-compose.prod.yml --env-file .env.production run --rm -v "$PWD/restore-work:/work" migrate python scripts/reapply_erasures.py --export-log /work/erasure_log.jsonl`
(`install -d -o 10001 -m 700 restore-work` first; add `-e POSTGRES_HOST=... -e POSTGRES_DB=...` to point at the
newest copy).

A backup taken before a personal-data erasure or an organization purge still holds that data. Every erasure and
purge is written to the `erasure_log` table, and a restored system must repeat them **before anyone signs in**
(retention: `docs/compliance/DATA_RETENTION_SCHEDULE.md`; procedure: `docs/runbooks/DATA_REQUESTS.md` section 6).

The restored database only knows the erasures made before its backup was taken, so first take the log from the
newest copy that still exists: the instance being replaced (point-in-time recovery leaves it running) or, if it is
lost, the newest layer-2 backup restored aside (as in the drill, section 2).

1. Against the newest copy (`POSTGRES_HOST`/`POSTGRES_DB` pointing at it, owner credentials):
   `python scripts/reapply_erasures.py --export-log erasure_log.jsonl`
2. Against the restored database:
   `python scripts/reapply_erasures.py --import-log erasure_log.jsonl --dry-run` — lists every account that is
   identifiable again and every purged organization whose rows, accounts or files are back (exit code 1 when there
   is something to re-apply). Nothing is changed.
3. `python scripts/reapply_erasures.py --import-log erasure_log.jsonl` — imports the missing log rows, erases and
   purges again, and stamps each log row `reapplied_at`. Organizations under a legal hold are listed and left
   alone. Exit code 1 if anything failed; fix and run again (it is idempotent).
4. Then `python scripts/complete_tenant_purge.py --dry-run`: an organization that was PURGING at backup time
   (rows deleted, files not yet) is finished with `python scripts/complete_tenant_purge.py`.
5. Record in the operations log: the restore point, the log file's row count, and the script's summary.

If the old database is lost and the newest backup is older than the last erasures, those erasures are not in any
log: check the operations log and the support tickets since that backup and repeat them by hand
(`POST /api/v1/platform-admin/users/{id}/erase`, Delete all data).

Restoring only the uploaded files (the `objects` volume or bucket) can also bring back a purged organization's
files: run step 2 after a file-only restore too.

## 5. After any restore

`docker compose -f docker-compose.prod.yml --env-file .env.production exec api python -m backend.app.config_check`,
check readiness (DEPLOYMENT.md, section 5) and `/health/status`, sign in as a Platform Administrator, and open one
customer's Product 360 and audit trail before announcing recovery.
