# Deploying MDARIX on Google Cloud (Mumbai)

The design-partner deployment of [DEPLOYMENT.md](DEPLOYMENT.md), set up on Google Cloud in India for the product
validation phase (free trials), at the lowest cost that keeps every production check. One VM runs Caddy, the API, the
background service, ClamAV and PostgreSQL; uploaded files are encrypted on the VM's disk; encrypted backups are copied
to a second region. Everything stays in India: Mumbai (`asia-south1`) for the service, Delhi (`asia-south2`) for the
backup copies. Nothing uses a downloadable key: new Google Cloud projects forbid service-account keys
(`iam.disableServiceAccountKeyCreation`), so the VM's own service account copies the backups.

DEPLOYMENT.md stays the reference for what is the same on any cloud (settings, start, upgrade, rollback, monitoring);
[STAGING_ORACLE.md](STAGING_ORACLE.md) for PostgreSQL on the server; this page gives the Google parts, the order, and
the move to managed services when the first design partners pay (section 5).

## 1. What runs where

| Need | Google Cloud | Monthly (on demand) |
|---|---|---|
| VM, 8 GB (compose limits 5.25 GB plus PostgreSQL) | Compute Engine `e2-standard-2` (2 vCPU, 8 GB), Ubuntu 24.04, 50 GB balanced disk, static IP, Shielded VM | $58.75 |
| PostgreSQL 16, `vector` + `pgcrypto`, TLS, `verify-full` | On the VM: `docker-compose.staging-oracle.yml` layered on the production file; its own CA from `infrastructure/staging/prepare-database.sh` | included |
| Uploaded files | Encrypted on the VM disk (`MDARIX_OBJECT_STORAGE_PROVIDER=local`): up to 24 hours of uploads at risk, as `.env.production.example` says | included |
| Disk safety net | Daily snapshot schedule `mdarix-daily`, 14 days, stored in Mumbai (`--storage-location=asia-south1`) | about $2 |
| Off-site backup copies | Bucket `PROJECT-mdarix-backups` in `asia-south2`: versioning, 30-day retention policy, deleted after 89 days (lifecycle; the privacy policy says up to 90 days) | cents |
| Firewall | VPC rules: 80/443 to the VM's tag `mdarix-web`; SSH only through Identity-Aware Proxy (`35.235.240.0/20`); the default SSH and RDP rules removed | free |
| Email | ZeptoMail (`smtp.zeptomail.in:587`, user `emailapikey`), sender `no-reply@mdarix.in`; mailboxes on Zoho Mail | ZeptoMail credits |
| Monitoring | Cloud Monitoring uptime check on `/health/status` every 5 minutes with an email alert; healthchecks.io for the scheduler (5 min, 15 min grace) and the backup (1 day, 2 h grace) | free |

Total about $70 a month before GST; the 90-day free-trial credit covers the trial period. **Before the trial ends,
choose "Activate full account" in Billing**: a trial account's resources stop when the trial ends, and the remaining
credit is kept when you activate.

## 2. Who does what

| Owner | Item |
|---|---|
| Operator | The project and its billing, a budget alert, DNS at BigRock, the ZeptoMail sender and token, the Zoho mailboxes, the healthchecks.io account, the two Platform Administrators, the legal texts' approval |
| Operator, offline | `C:\Users\<you>\.mdarix-deploy` (or a password manager): the tester login, the backup `age` private key, copies of `.env.production`, `.env.migrate` and the database TLS files. Without them a backup cannot be restored onto a new VM |
| Engineering | The commands below; no secret is printed, every generated secret goes straight into the files above |

## 3. Build it (as done on 2026-10-14)

Run `gcloud` from a terminal where you signed in (`gcloud auth login`) with the project set. In Git Bash on Windows,
arguments that start with `/` are rewritten into Windows paths: set `MSYS_NO_PATHCONV=1` and run
`python <sdk>/lib/gcloud.py ...` for those.

**Network and firewall**

```bash
gcloud config set project PROJECT && gcloud config set compute/region asia-south1 && gcloud config set compute/zone asia-south1-a
gcloud services enable compute.googleapis.com storage.googleapis.com monitoring.googleapis.com iap.googleapis.com
gcloud compute firewall-rules create mdarix-web --network=default --allow=tcp:80,tcp:443 --target-tags=mdarix-web
gcloud compute firewall-rules create mdarix-ssh-iap --network=default --allow=tcp:22 --source-ranges=35.235.240.0/20 --target-tags=mdarix-web
gcloud compute firewall-rules delete default-allow-ssh default-allow-rdp --quiet
```

**Backup bucket and the VM's identity**

```bash
gcloud storage buckets create gs://PROJECT-mdarix-backups --location=asia-south2 --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update gs://PROJECT-mdarix-backups --versioning --retention-period=30d   # not locked: locking is irreversible
gcloud storage buckets update gs://PROJECT-mdarix-backups --lifecycle-file=lifecycle.json        # delete after 89 days, old versions after 1
gcloud iam service-accounts create mdarix-backup --display-name="MDARIX off-site backups (create only)"
for role in roles/storage.objectCreator roles/storage.objectViewer; do   # add and list, never delete
  gcloud storage buckets add-iam-policy-binding gs://PROJECT-mdarix-backups \
    --member=serviceAccount:mdarix-backup@PROJECT.iam.gserviceaccount.com --role=$role
done
```

`lifecycle.json`: `{"rule": [{"action": {"type": "Delete"}, "condition": {"age": 89}}, {"action": {"type": "Delete"},
"condition": {"isLive": false, "daysSinceNoncurrentTime": 1}}]}`.

**The VM**

```bash
gcloud compute addresses create mdarix-ip --region=asia-south1
gcloud compute instances create mdarix-prod --machine-type=e2-standard-2 \
  --service-account=mdarix-backup@PROJECT.iam.gserviceaccount.com --scopes=cloud-platform \
  --image-family=ubuntu-2404-lts-amd64 --image-project=ubuntu-os-cloud --boot-disk-size=50GB --boot-disk-type=pd-balanced \
  --address=mdarix-ip --tags=mdarix-web --shielded-secure-boot --shielded-vtpm --shielded-integrity-monitoring \
  --metadata=enable-oslogin=TRUE
gcloud compute resource-policies create snapshot-schedule mdarix-daily --region=asia-south1 --max-retention-days=14 --daily-schedule --start-time=21:00 \n  --storage-location=asia-south1
gcloud compute disks add-resource-policies mdarix-prod --resource-policies=mdarix-daily
gcloud compute ssh mdarix-prod --tunnel-through-iap
```

The snapshots hold the database, so they must stay in India: `--storage-location=asia-south1` keeps them in
Mumbai. Without it Google stores them in the `asia` multi-region, which is not limited to India, while the privacy
policy says that we do not transfer personal data outside India. Check with
`gcloud compute snapshots list --format="table(name,storageLocations)"`: every snapshot shows `asia-south1`.

From Windows, copy a script with `gcloud compute scp` and run it with `--command`: piping a script into `ssh` loses
its first line to PuTTY's host-key prompt.

On the VM, as a sudo user: DEPLOYMENT.md section 2.1 (updates, Docker, SSH keys only, `ufw` with SSH from
`35.235.240.0/20` and 80/443, fail2ban, chrony, 4 GB swap, the `deploy` user). The repository is private: give the
VM a read-only deploy key (`ssh-keygen` as `deploy`, then `gh repo deploy-key add <key>.pub --title ...` from a
machine signed in to GitHub) and clone with `git@github.com:...`.

**Code, settings, database, images (as `deploy`)**

```bash
git clone git@github.com:OWNER/MDARIX-R1.git ~/mdarix && cd ~/mdarix && git checkout vX.Y.Z
echo 'export COMPOSE_FILE=docker-compose.prod.yml:docker-compose.staging-oracle.yml COMPOSE_ENV_FILES=.env.production' >> ~/.profile
```

Fill `.env.production` and `.env.migrate` from their templates (STAGING_ORACLE.md section 4 lists the values that
differ from a managed database: `POSTGRES_HOST=postgres`, `POSTGRES_SSLMODE=verify-full`, `MDARIX_IMAGE_REPOSITORY=mdarix`,
`MDARIX_OBJECT_STORAGE_PROVIDER=local`). Also: `MDARIX_BACKUP_S3_URI` empty and `MDARIX_BACKUP_OFFSITE_ACKNOWLEDGED=true`
(the copies leave through the host cron below), and `MDARIX_GENAI_COST_PER_1K_TOKENS=0` on releases before 0.10.1.
Then STAGING_ORACLE.md section 5 (`prepare-database.sh`, the owner role, the database and its extensions), and build
the images on the VM: `docker compose build` and `docker compose --profile backup build backup`. Check, start and
check again (DEPLOYMENT.md section 2.4); invite two Platform Administrators (section 2.5).

**Backups (BACKUP_AND_RESTORE.md section 1)**: the age key pair is made off the server and its private key never
stays there; `scripts/configure_backup_role.py` in the `migrate` service; the backup in the `deploy` crontab at
02:15 UTC; the off-site copy as `/etc/cron.d/mdarix-offsite` at 02:45 UTC:

```cron
45 2 * * * root /snap/bin/gcloud storage rsync --recursive /var/backups/mdarix gs://PROJECT-mdarix-backups/<environment> >> /var/log/mdarix-offsite.log 2>&1
```

## 4. Rehearsal, then go-live

The first deployment runs as a **private rehearsal** (`MDARIX_ENV=staging`, `MDARIX_SITE_ACCESS=private` with a tester
login, `MDARIX_PRIVATE_STAGING_ACKNOWLEDGED=true`; STAGING_ORACLE.md section 0) on `rehearsal.mdarix.in`, with sample
data only. Check: every service healthy, `config_check` clean, a real invitation email arrives, a backup lands in
the Delhi bucket, the restore drill of BACKUP_AND_RESTORE.md, and one trial walked end to end by a person.

Go-live, once the operator has approved the legal texts and the rehearsal is done (done on 2026-10-16, in this order):

1. **DNS** (the owner, at the registrar): `mdarix.in` A record and `www` CNAME to `mdarix.in` at the static IP. Leave
   the mail records (MX, SPF, DKIM, DMARC, the ZeptoMail bounce CNAME) as they are.
2. **Keep a way back**: a final backup (`docker compose --profile backup run --rm backup`), copied off-site at once
   with the cron's `gcloud storage rsync` command and listed in the bucket, its `MANIFEST.sha256` checked; and a disk
   snapshot (`gcloud compute disks snapshot mdarix-prod --zone=asia-south1-a --snapshot-names=mdarix-pre-golive-<date> --storage-location=asia-south1`).
3. **Draft the production settings** beside the live file (`.env.production.next`, mode 600): `MDARIX_ENV=production`,
   `MDARIX_DOMAIN=mdarix.in`, `MDARIX_APP_URL` and `MDARIX_ALLOWED_ORIGINS` to `https://mdarix.in` (the app URL is the
   only trusted origin: a wrong value refuses every sign-in), `MDARIX_WWW_REDIRECT=on`, `MDARIX_SITE_ACCESS=public`;
   remove `MDARIX_SITE_LOGIN_USER`, `MDARIX_SITE_LOGIN_HASH` and `MDARIX_PRIVATE_STAGING_ACKNOWLEDGED`; add
   `MDARIX_OPERATOR_COUNTRY=IN` and `MDARIX_OPERATOR_REGION=IN` (the operator organization is recorded as US
   otherwise); keep `MDARIX_TRUSTED_PROXY_HOPS=1` in the file (compose sets it for `api` only, and production needs
   it in every process) and both heartbeat URLs (`MDARIX_BACKUP_HEARTBEAT_URL` is required in production). Check the
   draft without touching the live stack:
   `docker run --rm --env-file <draft without quotes> -e MDARIX_LEGAL_DIR=/var/lib/mdarix/legal -v "$PWD/legal:/var/lib/mdarix/legal:ro" -v "$PWD/certs:/etc/mdarix/certs:ro" mdarix/api:<tag> python -m backend.app.config_check --offline`:
   the only problem left must be `MDARIX_LEGAL_TEXT_APPROVED`.
4. **Empty the database and the file stores**: `docker compose stop web api background`; as `postgres`,
   `DROP DATABASE mdarix WITH (FORCE); CREATE DATABASE mdarix OWNER mdarix_owner;` then both extensions in it
   (STAGING_ORACLE.md section 5); `docker volume rm mdarix_objects mdarix_reports` (the rehearsal's files would
   otherwise stay and go into every production backup). Never `docker compose down -v` (it deletes the database
   volume and the certificates).
5. **Backups to production**: move the rehearsal's local backups out of `/var/backups/mdarix` (else the next rsync
   copies them under `/prod`) and change `/rehearsal` to `/prod` in `/etc/cron.d/mdarix-offsite`.
6. **Install the settings**: keep the rehearsal file (`.env.production.rehearsal-final`), move the draft into place.
   **The owner** sets `MDARIX_LEGAL_TEXT_APPROVED=true`: production refuses to start without it.
7. **Start and check**: `config_check --offline` prints only its "Offline check: ..." line and exits 0 (judge by the
   exit code); `docker compose up -d --no-build --wait`; every service healthy and `migrate` exited 0;
   `docker compose exec api python -m backend.app.config_check` prints nothing; `docker compose logs web` shows
   "certificate obtained successfully" for `mdarix.in` and `www.mdarix.in` (`--wait` passes even when a certificate
   fails).
8. **Re-grant the backup role** (grants live in the database that was just recreated):
   `docker compose run --rm migrate python scripts/configure_backup_role.py`.
9. **Invite the two Platform Administrators** (DEPLOYMENT.md section 2.5), send a test alert
   (`scripts/send_test_alert.py`), take the first production backup and copy it off-site by hand, and move the
   uptime check and its alert policy to `mdarix.in` (delete the rehearsal check). Copy the tutorial videos into the
   host `videos/` folder if the server is new.
10. **Smoke test from outside**: `/health/status` ok, `/` returns 200 (not the private 401), `www` returns 301 to the
    apex, `/health/ready` 404, the security headers, `/api/v1/public/site-info` shows the company name and address
    only, `/api/v1/public/version` the release, every video plays. Do not run `scripts/production_smoke.py` (it
    sets a fixed password on the account it activates), `scripts/demo_tenant.py` or `scripts/seed_demo_expansion.py`
    against production.

Known gap: with `MDARIX_BACKUP_S3_URI` empty, the off-site copy is the host cron alone and nothing alerts when it
fails; check `/var/log/mdarix-offsite.log` and the bucket listing until a check is added. The self-hosted database
has no point-in-time recovery: a daily dump and a daily disk snapshot give a recovery point of about a day, accepted
for the free-trial phase (section 5 moves the database to Cloud SQL when design partners pay).

## 5. When design partners pay

- Move the database to Cloud SQL for PostgreSQL 16 (point-in-time recovery, SLA): create it with
  `--server-ca-mode=GOOGLE_MANAGED_CAS_CA` so its certificate names a DNS host, which `POSTGRES_SSLMODE=verify-full`
  needs (the per-instance CA mode does not name the private IP), on a private IP (private services access), with a
  dedicated core rather than a shared-core tier, which has no SLA. Restore the latest backup into it, then drop the
  PostgreSQL service from the compose files.
- Add native Cloud Storage support for uploaded files to `object_storage/service.py` (keyless, through the VM's service
  account), so files no longer depend on the nightly backup.
- Take a 1-year commitment on the VM once its size is settled (about 37% less).
- Lock the backup bucket's retention policy once the routine has run unchanged for a month (irreversible).
