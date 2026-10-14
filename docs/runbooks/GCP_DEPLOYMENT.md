# Deploying MDARIX on Google Cloud (Mumbai)

The design-partner deployment of [DEPLOYMENT.md](DEPLOYMENT.md), mapped onto Google Cloud in India: one VM runs Caddy,
the API, the background service and ClamAV; PostgreSQL is Cloud SQL with point-in-time recovery; uploaded files live in
Cloud Storage through its S3-compatible endpoint. Everything stays in India: Mumbai (`asia-south1`) for the service,
Delhi (`asia-south2`) for the off-site backup copy. DEPLOYMENT.md stays the reference for the steps that are the same on
any cloud (VM hardening, settings, start, upgrade, rollback, monitoring); this page gives the Google parts and the order.

## 1. What runs where

| Need (DEPLOYMENT.md section 1) | Google Cloud | Size to start | Monthly (on demand) |
|---|---|---|---|
| VM, 8 GB (compose limits 5.25 GB) | Compute Engine `e2-standard-2` (2 vCPU, 8 GB), Ubuntu 24.04, 80 GB balanced disk, static IP | e2-standard-2; `e2-standard-4` when CPU stays high | $58.75 ($37.01 with a 1-year commitment) |
| Managed PostgreSQL 16, `vector` + `pgcrypto`, PITR, TLS, direct connection | Cloud SQL for PostgreSQL 16, Enterprise edition, private IP in the VM's network, `ENCRYPTED_ONLY` | `db-g1-small` (shared core, 1.7 GB) for trials; a dedicated core (`db-custom-1-3840`) before paying customers: shared-core tiers have no SLA | $31 + storage |
| S3 bucket for uploads, versioning, private | Cloud Storage bucket in `asia-south1`, uniform access, public access prevention, versioning; HMAC key of a service account | 1 bucket | a few dollars |
| Off-site backup bucket, versioning, retention | Cloud Storage bucket in `asia-south2` with a retention policy; a second service account that can only create objects | 1 bucket | a few dollars |
| Firewall: 80/443 open, 22 restricted, database private | VPC firewall: 80/443 to the VM's tag; SSH only through Identity-Aware Proxy (`35.235.240.0/20`); Cloud SQL without public IP | | free |
| Disk safety net | Daily snapshot schedule on the VM disk, 14 days | | about $4 |
| Email | ZeptoMail SMTP on mdarix.in (SPF, DKIM, DMARC) | | as today |
| Monitoring | Cloud Monitoring uptime check on `/health/status` + the heartbeat service of DEPLOYMENT.md section 6 | | free tier |

Estimated total with `db-g1-small`: about $105 a month on demand, about $83 with a 1-year commitment on the VM (before
GST). The 90-day free-trial credit covers the first months. **Before the trial ends, choose "Activate full account" in
Billing**: a trial account's resources stop when the trial ends, and the remaining credit is kept when you activate.

## 2. Who does what

| Owner | Item |
|---|---|
| You | The Google Cloud project with billing (the trial), a budget alert (Billing > Budgets, e.g. at 50% and 90% of the monthly estimate), access to mdarix.in's DNS, the ZeptoMail sender, the two Platform Administrators' emails, the on-call names |
| You | **Lawyer-approved privacy policy, terms and trial agreement** in `./legal`: production refuses to start with DRAFT text (`config_check`). Until then the stack runs only as a rehearsal with synthetic data |
| You | An `age` key pair for the backups, the private key kept offline (BACKUP_AND_RESTORE.md) |
| You, once | Install the Google Cloud CLI on this PC and sign in yourself (`gcloud auth login`, in a browser) |
| Claude, with your go-ahead per phase | Every `gcloud` command below, the VM setup, the build, the settings (no secret is ever printed), the checks and the E2E run against the live site |

## 3. Phases

**Phase A: project and network (about 30 minutes).** Replace `PROJECT` with the project id.

```bash
gcloud config set project PROJECT
gcloud config set compute/region asia-south1 && gcloud config set compute/zone asia-south1-a
gcloud services enable compute.googleapis.com sqladmin.googleapis.com servicenetworking.googleapis.com \
  storage.googleapis.com monitoring.googleapis.com iap.googleapis.com
# Private services access, so Cloud SQL gets a private IP in the default network (no public database address).
gcloud compute addresses create google-managed-services-default --global --purpose=VPC_PEERING --prefix-length=16 --network=default
gcloud services vpc-peerings connect --service=servicenetworking.googleapis.com --ranges=google-managed-services-default --network=default
# Firewall: web open, SSH only through IAP; then remove the default rule that opens SSH to the internet.
gcloud compute firewall-rules create mdarix-web --network=default --allow=tcp:80,tcp:443 --target-tags=mdarix-web
gcloud compute firewall-rules create mdarix-ssh-iap --network=default --allow=tcp:22 --source-ranges=35.235.240.0/20 --target-tags=mdarix-web
gcloud compute firewall-rules delete default-allow-ssh default-allow-rdp --quiet
```

**Phase B: database (about 20 minutes, mostly waiting).**

```bash
gcloud sql instances create mdarix-db --database-version=POSTGRES_16 --edition=ENTERPRISE --tier=db-g1-small \
  --region=asia-south1 --availability-type=zonal --storage-type=SSD --storage-size=20GB --storage-auto-increase \
  --network=default --no-assign-ip --ssl-mode=ENCRYPTED_ONLY \
  --backup-start-time=20:30 --enable-point-in-time-recovery --retained-transaction-log-days=7 --retained-backups-count=14 \
  --maintenance-window-day=SUN --maintenance-window-hour=21 --deletion-protection
gcloud sql users set-password postgres --instance=mdarix-db --prompt-for-password      # typed by you, kept in your password manager
gcloud sql instances describe mdarix-db --format="value(ipAddresses[0].ipAddress)"     # the private IP for POSTGRES_HOST
gcloud sql instances describe mdarix-db --format="value(serverCaCert.cert)" > db-ca.pem # copied to ~/mdarix/certs on the VM
```

Then DEPLOYMENT.md section 2.3 runs from the VM as `postgres` (role `mdarix_owner` with `CREATEROLE`, database
`mdarix`, extensions `vector` and `pgcrypto`). Backup times are UTC: 20:30 UTC is 02:00 IST.

**Phase C: storage (about 15 minutes).**

```bash
gcloud storage buckets create gs://PROJECT-mdarix-files --location=asia-south1 --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update gs://PROJECT-mdarix-files --versioning
gcloud storage buckets create gs://PROJECT-mdarix-backups --location=asia-south2 --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update gs://PROJECT-mdarix-backups --versioning --retention-period=30d   # not locked yet: locking is irreversible
gcloud iam service-accounts create mdarix-files && gcloud iam service-accounts create mdarix-backup
gcloud storage buckets add-iam-policy-binding gs://PROJECT-mdarix-files --member=serviceAccount:mdarix-files@PROJECT.iam.gserviceaccount.com --role=roles/storage.objectAdmin
gcloud storage buckets add-iam-policy-binding gs://PROJECT-mdarix-backups --member=serviceAccount:mdarix-backup@PROJECT.iam.gserviceaccount.com --role=roles/storage.objectCreator
gcloud storage hmac create mdarix-files@PROJECT.iam.gserviceaccount.com    # -> .env.production (never printed in a chat)
gcloud storage hmac create mdarix-backup@PROJECT.iam.gserviceaccount.com   # -> .env.migrate
```

Settings for Cloud Storage's S3-compatible endpoint (verified on the rehearsal before go-live):

| File | Setting |
|---|---|
| `.env.production` | `MDARIX_OBJECT_STORAGE_PROVIDER=s3`, `MDARIX_OBJECT_STORAGE_ENDPOINT=https://storage.googleapis.com`, `MDARIX_OBJECT_STORAGE_REGION=asia-south1`, `MDARIX_OBJECT_STORAGE_BUCKET=PROJECT-mdarix-files`, the files HMAC key in `..._ACCESS_KEY` / `..._SECRET_KEY`, `AWS_REQUEST_CHECKSUM_CALCULATION=when_required`, `AWS_RESPONSE_CHECKSUM_VALIDATION=when_required` (Cloud Storage does not accept the newer default S3 checksums) |
| `.env.production` | `MDARIX_BACKUP_S3_URI=s3://PROJECT-mdarix-backups/prod` |
| `.env.migrate` | the backup HMAC key as `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`, `AWS_ENDPOINT_URL=https://storage.googleapis.com`, `AWS_DEFAULT_REGION=asia-south2`, the same two checksum settings |

**Phase D: VM (about 45 minutes).**

```bash
gcloud compute addresses create mdarix-ip --region=asia-south1
gcloud compute instances create mdarix-prod --machine-type=e2-standard-2 \
  --image-family=ubuntu-2404-lts-amd64 --image-project=ubuntu-os-cloud --boot-disk-size=80GB --boot-disk-type=pd-balanced \
  --address=mdarix-ip --tags=mdarix-web --shielded-secure-boot --shielded-vtpm --shielded-integrity-monitoring
gcloud compute resource-policies create snapshot-schedule mdarix-daily --max-retention-days=14 --daily-schedule --start-time=21:00
gcloud compute disks add-resource-policies mdarix-prod --resource-policies=mdarix-daily
gcloud compute ssh mdarix-prod --tunnel-through-iap
```

On the VM: DEPLOYMENT.md section 2.1 (updates, SSH keys only, ufw, fail2ban, chrony, swap, the `deploy` user), then
2.2. GitHub Actions does not run for this repository at the moment, so the release images are built on the VM from
the release tag (`v0.10.0`, tagged from `main` once you approve the release) instead of pulled: `git checkout v0.10.0`, `MDARIX_IMAGE_REPOSITORY=mdarix`, `MDARIX_RELEASE=v0.10.0`,
then `docker compose -f docker-compose.prod.yml --env-file .env.production build` before section 2.4.

**Phase E: rehearsal with synthetic data (half a day).** `MDARIX_ENV=staging` and the demo tenant only, no customer
data. Point `rehearsal.mdarix.in` (A record to the static IP) at it so Caddy gets a certificate.

1. `config_check --offline` prints nothing; `up -d --wait`; every service healthy; `/health/status` is `ok`.
2. Upload and download a file (proves the Cloud Storage endpoint and checksum settings), run one backup and copy it
   off-site (proves the backup settings), then the restore drill of BACKUP_AND_RESTORE.md into a scratch database.
3. A Cloud SQL point-in-time restore to a clone, then delete the clone.
4. The browser E2E (`frontend/e2e/trial-journey.spec.ts`) against the rehearsal site, with email on to a test inbox.
5. Two Platform Administrators invited, MFA on; uptime check and heartbeat alerts arriving.

**Phase F: go-live (about 1 hour), only with the lawyer-approved legal texts.** Empty the rehearsal database (drop and
recreate `mdarix`, section 2.3), switch to `MDARIX_ENV=production` and the domain `mdarix.in` (`MDARIX_WWW_REDIRECT=on`, DNS A record for
`mdarix.in` and a CNAME for `www`), run `config_check` (it must
print nothing: legal text, SMTP, backups, MFA roles, AI policy), start, re-invite the two administrators, smoke-test,
then send the first trial invitation. AI stays off until the provider contract and the AI release gate (AI_PROVIDERS.md).

## 4. After the first month

- Look at CPU, memory and database load in Cloud Monitoring; move the VM to `e2-standard-4` or the database to a
  dedicated core if either runs hot, and before the first paying customer move the database to a dedicated core in
  any case (SLA).
- Buy the 1-year commitment for the VM once the size is settled (about 37% less).
- Lock the backup bucket's retention policy once the backup routine has run unchanged for a month (irreversible).
