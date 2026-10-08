# Environment variables

Every setting MDARIX reads, by area. **Required** means staging and production refuse to start without a valid value
(`python -m backend.app.config_check` lists what is missing). Local development (`MDARIX_ENV=development`) uses safe
local defaults for most of them. `tests/test_environment_reference.py` fails when code reads a variable this page does
not list.

## Environment and address

| Variable | Required | Meaning |
|---|---|---|
| `MDARIX_ENV` | yes | `development`, `test`, `staging` or `production`. Unset or unknown means production, with every protection on. |
| `MDARIX_DEPLOYMENT_ROLE` | no | Which part of MDARIX this deployment is (ADR-013, `backend/app/deployment_role.py`): `MULTI` (default; everything in one deployment, as today), `PLATFORM` (platform administration only: customers, tenants, licences, standards; the workspace answers 404 and only platform staff sign in) or `CELL` (one organization's workspace and administration in its own database; platform administration answers 404 and platform staff cannot sign in). The scheduler and the worker run only their role's jobs. |
| `MDARIX_CELL_TENANT_ID`, `MDARIX_CELL_TENANT_KEY` | in a CELL | The UUID and key of the one organization a `CELL` serves. The start-up check refuses a cell whose database does not hold that organization under that key on the shared plane, and refuses any `MDARIX_DATA_PLANE_*` setting (a cell has one database). Not set for `MULTI` or `PLATFORM`. |
| `MDARIX_APP_URL` | yes | The https address people use (`https://app.example.com`). Links in emails and the trusted browser origin. |
| `MDARIX_ALLOWED_ORIGINS` | no | Extra trusted browser origins, comma-separated. |
| `MDARIX_DOMAIN`, `ACME_EMAIL` | yes (compose) | Caddy's domain and Let's Encrypt account email. |
| `MDARIX_RELEASE` | yes (compose) | The release tag the server runs (e.g. `v0.9.0`): the image tag in docker-compose.prod.yml; also reported with client errors. |
| `MDARIX_IMAGE_REPOSITORY` | yes (compose) | Where the release images are pulled from, e.g. `ghcr.io/stelikicherla-stack/mdarix-r1` (images `api`, `web`, `backup` under it); `mdarix` when building on the server. |
| `MDARIX_TRUSTED_PROXY_HOPS` | yes behind Caddy | Number of proxies in front of the API (1 with Caddy); the client address is read from X-Forwarded-For accordingly. |
| `MDARIX_TRUST_PROXY_HEADERS` | no | Older form of the above (`true` = 1 hop). |
| `MDARIX_COOKIE_SECURE` | no | Development only: use the secure `__Host-` session cookie over https locally. |
| `MDARIX_ENABLE_API_DOCS` | no | Development only: the /docs page. Refused in production. |
| `MDARIX_SESSION_IDLE_MINUTES` | no | Sign out after this many minutes without activity (default 30). Sessions end after 60 minutes regardless. |

## Database

| Variable | Required | Meaning |
|---|---|---|
| `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB` | yes | The control database. |
| `POSTGRES_USER`, `POSTGRES_PASSWORD` | yes | The account services connect as. In production this is the runtime role, not the owner. |
| `POSTGRES_SSLMODE` | yes | `require`, `verify-ca` or `verify-full` (production); `disable` locally. |
| `POSTGRES_SSLROOTCERT` | no | CA bundle for `verify-ca` / `verify-full` inside the containers, e.g. `/etc/mdarix/certs/db-ca.pem`; empty = the system's public CAs. The backup job passes it to pg_dump (`sslrootcert=system` when empty). |
| `MDARIX_DB_CA_DIR` | no (compose) | Host folder mounted read-only at `/etc/mdarix/certs` in every container that talks to the database (default `./certs`). |
| `MDARIX_DB_RUNTIME_USER`, `MDARIX_DB_RUNTIME_PASSWORD` | yes | The least-privilege role every request runs as (row-level security). |
| `MDARIX_DB_OWNER_USER` | yes | The schema owner's name (`.env.production`): the migrate job connects as it, and the API refuses to run as it. |
| `MDARIX_DB_OWNER_PASSWORD` | yes (migrate, backup) | The schema owner's password, in `.env.migrate` only: the API, worker and scheduler refuse to start with it in their environment. |
| `MDARIX_DB_HARDENING_APPLY` | migrate | `1` lets the hardening migration create the runtime and read-only roles. |
| `MDARIX_DB_POOL_SIZE`, `MDARIX_DB_MAX_OVERFLOW`, `MDARIX_DB_POOL_TIMEOUT_SECONDS` | no | Connection pool per process (defaults 5, 10, 30 s). |
| `MDARIX_RLS_SYSTEM_TOKEN` | yes | Secret that lets the server read across tenants for platform work; the database stores only its hash. |
| `MDARIX_DATA_PLANE_<NAME>_DATABASE_URL` | per dedicated plane | Connection string of one dedicated tenant database (named by its registry row). |
| `MDARIX_DATA_PLANE_<NAME>_DATABASE_URL_OWNER` | per dedicated plane (migrate, backup) | The plane owner's connection string, in `.env.migrate` only; the migrate job migrates the plane with it and the backup job dumps it. |
| `MDARIX_DATA_PLANE_RUNTIME_USER`, `MDARIX_DATA_PLANE_RUNTIME_PASSWORD`, `MDARIX_DATA_PLANE_PASSWORD` | local only | Credentials of the four local synthetic planes. |
| `MDARIX_DATA_PLANE_POOL_SIZE`, `MDARIX_DATA_PLANE_MAX_OVERFLOW` | no | Pool per dedicated plane (defaults 3, 5). |

## Keys and secrets

| Variable | Required | Meaning |
|---|---|---|
| `MDARIX_MFA_ENCRYPTION_KEY` | yes | Encrypts authenticator secrets (URL-safe base64 of 32 bytes). Without it no one can set up MFA. |
| `MDARIX_CONNECTOR_ENCRYPTION_KEY` | yes | Encrypts customer-system API keys. |
| `MDARIX_DEMO_REQUEST_SALT` | yes | Salts the hashed address of demo requests. |
| `MDARIX_DEMO_REQUESTS_PER_SOURCE_HOUR`, `MDARIX_DEMO_REQUESTS_PER_DAY` | no | Demo request limits per sending address per hour (5) and in total per day (200). |
| `MDARIX_RATE_LIMIT_SALT` | yes | Salts rate-limit keys. |
| `MDARIX_PASSWORD_SCRYPT_LOG2_N` | no | Password hash cost (default 17; production refuses less). Tests use 14. |
| `MDARIX_PASSWORD_HASH_CONCURRENCY` | no | Maximum password hashes allowed concurrently in one process (default 3), limiting CPU and memory pressure during sign-in bursts. |
| `MDARIX_RATE_LIMITS_ENABLED` | no | `false` only in automated tests; refused in production. |
| `MDARIX_CONNECTOR_SECRET_<TENANT ID>_<NAME>` | no | Server secrets a connector may reference by name (prefer the per-connector API key). In staging and production a connector may only name secrets that start with its tenant's identifier, for example `MDARIX_CONNECTOR_SECRET_TEN0351_TRACKWISE`. |
| `MDARIX_CONNECTOR_MAX_BYTES` | no | Most a connector sync may read from a provider across all pages (50,000,000 bytes; each page at most 5 MB). |
| `MDARIX_CONNECTOR_ENCRYPTION_KEY_ID` | no | ID of the current connector encryption key (`k1`). Change it whenever the key changes. |
| `MDARIX_CONNECTOR_ENCRYPTION_KEYS` | no | Older connector keys still readable during a rotation: `k1:<base64>,k0:<base64>`. Run `scripts/reseal_connector_keys.py --apply`, then remove them. |

## Files

| Variable | Required | Meaning |
|---|---|---|
| `MDARIX_OBJECT_STORAGE_PROVIDER` | yes | `local` (encrypted files on a volume) or `s3`. |
| `MDARIX_OBJECT_STORAGE_ROOT` | local | Where local files live. |
| `MDARIX_OBJECT_STORAGE_ENCRYPTION_KEY` | local | Encrypts local files. |
| `MDARIX_OBJECT_STORAGE_SIGNING_SECRET` | yes | Signs download links. |
| `MDARIX_OBJECT_STORAGE_BUCKET`, `MDARIX_OBJECT_STORAGE_REGION`, `MDARIX_OBJECT_STORAGE_ENDPOINT`, `MDARIX_OBJECT_STORAGE_ACCESS_KEY`, `MDARIX_OBJECT_STORAGE_SECRET_KEY`, `MDARIX_OBJECT_STORAGE_SSE` | s3 | Bucket settings (server-side encryption `AES256` by default). |
| `MDARIX_OBJECT_STORAGE_MAX_BYTES`, `MDARIX_OBJECT_STORAGE_TENANT_QUOTA_BYTES` | no | Per-file and per-tenant limits (10 MB, 100 MB). |
| `MDARIX_OBJECT_STORAGE_RETENTION_DAYS` | no | Default retention of stored files (2555 days). |
| `MDARIX_EVIDENCE_STORAGE_ROOT` | no | Where evidence attachments are stored on a local volume. |
| `MDARIX_CLAMD_HOST`, `MDARIX_CLAMD_PORT`, `MDARIX_CLAMD_TIMEOUT_SECONDS` | yes (one scanner) | ClamAV daemon that scans every upload; no clean verdict refuses the file. |
| `MDARIX_MALWARE_SCANNER_COMMAND` | alternative | A scanner command reading the file on stdin (exit 0 = clean). |
| `MDARIX_REPORT_TEMP_ROOT` | yes (compose) | Where generated reports are written (a volume shared by API and worker). |

## Email

| Variable | Required | Meaning |
|---|---|---|
| `MDARIX_SMTP_HOST`, `MDARIX_SMTP_PORT`, `MDARIX_SMTP_USERNAME`, `MDARIX_SMTP_PASSWORD` | yes | The SMTP account (STARTTLS). |
| `MDARIX_SMTP_FROM` | yes | Sender, e.g. `MDARIX <no-reply@example.com>`. |
| `MDARIX_SMTP_VERIFIED_DOMAIN` | no | Refuse a sender outside this domain. |
| `MDARIX_TRIAL_ALERT_EMAIL`, `MDARIX_DEMO_ALERT_EMAIL` | no | Who hears about new trial and demo requests, and about customer feedback (feedback falls back to `MDARIX_SUPPORT_EMAIL`). |
| `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `RESEND_REPLY_TO`, `RESEND_VERIFIED_DOMAIN`, `RESEND_WEBHOOK_SECRET` | no | Inbound evidence email through Resend (optional feature). |

## Company and legal

| Variable | Required | Meaning |
|---|---|---|
| `MDARIX_COMPANY_LEGAL_NAME`, `MDARIX_COMPANY_ADDRESS` | yes | Shown on the legal pages, in the footer and in emails. |
| `MDARIX_SUPPORT_EMAIL`, `MDARIX_PRIVACY_EMAIL` | yes | Contact addresses shown to customers. |
| `MDARIX_LEGAL_TEXT_APPROVED` | yes | `true` once a lawyer approved the privacy policy, terms and trial agreement. |
| `MDARIX_LEGAL_DIR` | yes | Folder holding the approved `privacy.md`, `terms.md` and `trial-agreement.md` shown on the website (set by `docker-compose.prod.yml` to the mounted `./legal` folder; see `legal/README.md`). |
| `MDARIX_OPERATOR_COUNTRY`, `MDARIX_OPERATOR_REGION` | no | Country and region of the MDARIX operator organization (create_platform_admin.py). |

## AI

| Variable | Required | Meaning |
|---|---|---|
| `MDARIX_GENAI_PROVIDER` | no | `controlled` (no model, default), or a provider name. |
| `MDARIX_GENAI_API_KEY`, `MDARIX_GENAI_MODEL`, `MDARIX_GENAI_BASE_URL`, `MDARIX_GENAI_MODEL_VERSION` | with a provider | The primary provider. |
| `MDARIX_GENAI_CONTRACTED_PROVIDERS` | production with AI | Providers under a no-training / DPA contract. Only these and `ollama` may receive customer data in production. |
| `MDARIX_GENAI_<NAME>_ZDR` (for example `MDARIX_GENAI_ANTHROPIC_ZDR`) | production with a contracted provider | `true` once the contract or account setting confirms zero data retention for that provider; `false` or unset otherwise. In staging and production a contracted provider without `true` is refused (the API does not start) unless `MDARIX_GENAI_ACCEPT_RETENTION=true`. Record it in `docs/compliance/AI_PROVIDER_REGISTER.md`. |
| `MDARIX_GENAI_ACCEPT_RETENTION` | no | `true` records that the data processing agreement accepts the contracted providers' limited retention (for example 30 days for abuse monitoring), clearing providers without a `_ZDR=true`. Default unset: retention must be zero. |
| `MDARIX_GENAI_FALLBACKS` | no | Providers tried in order when the primary is limited or down; each reads `MDARIX_GENAI_<NAME>_API_KEY`, `_MODEL`, `_BASE_URL`, `_TIMEOUT_SECONDS`, `_MAX_RETRIES`. |
| `MDARIX_GENAI_TIMEOUT_SECONDS`, `MDARIX_GENAI_MAX_RETRIES`, `MDARIX_GENAI_MAX_RETRY_WAIT_SECONDS` | no | Request limits (20 s, 2, 10 s). |
| `MDARIX_GENAI_MAX_INPUT_TOKENS`, `MDARIX_GENAI_MAX_OUTPUT_TOKENS`, `MDARIX_GENAI_COST_PER_1K_TOKENS` | no | Size limits and cost estimate. |
| `MDARIX_GENAI_RATE_LIMIT_REST_SECONDS`, `MDARIX_GENAI_OUTAGE_REST_SECONDS` | no | How long a limited or failing provider rests. |
| `MDARIX_GENAI_SHARED_REST` | no | `true` (default): a resting provider is skipped by every API, worker and scheduler process (table `genai_provider_rest`). Tests set `false`. |
| `MDARIX_GENAI_TENANT_MONTHLY_TOKENS` | no | Monthly AI token allowance of an organization without its own (2,000,000). Platform administrators set per-organization allowances; customer administrators can switch AI off. |
| `MDARIX_GENAI_PII_MASKING` | no | `true` (default): personal information is masked before any model request (`genai/pii.py`): email addresses, phone numbers, card/national/insurance/record numbers, labelled IP addresses, postcodes, addresses, dates of birth, age-with-sex phrases, care facilities after "at", values under personal-data keys, and names when something marks them as a name (a label such as "Patient:", a title such as "Dr", a role word such as "Nurse" or "Complainant", "reported by", initials with a surname, or a common given name followed by a surname). **An unusual name written bare in free text, with none of those markers, is not recognised**; put names in labelled fields. Product, lot, change and standard identifiers and ordinary event dates are kept. `false` is honoured only in local development on synthetic data; staging and production always mask. |
| `MDARIX_GENAI_MASK_SERIALS_NEAR_PII` | no | `true` (default): a serial or lot number in the same sentence as a patient-side identifier (patient, complainant, reporter, date of birth, record number, address, age with sex) is masked too, because the pair could lead back to the patient. A staff name beside a lot does not mask the lot. `false` keeps every serial and lot. |
| `MDARIX_EMBEDDING_PROVIDER`, `MDARIX_EMBEDDING_CACHE_DIR` | no | Local embedding model (runs on the server; nothing is sent out). |

## Security policy

| Variable | Required | Meaning |
|---|---|---|
| `MDARIX_REQUIRE_MFA_ROLES` | no | Roles that must set up MFA (default platform and customer administrators, Leaders and Approvers; production refuses an empty value). |
| `MDARIX_REQUIRE_MFA_FOR_SIGNATURES` | no | Signatures need a fresh authenticator code (default true). |
| `MDARIX_SUPPLIER_REQUESTS_PER_DAY`, `MDARIX_SUPPLIER_REQUESTS_PER_HOUR` | no | Supplier evidence request limits per organization. |
| `MDARIX_CONNECTOR_ALLOWED_HOSTS` | no | Hosts connectors may reach even when private (development simulators); leave empty on servers. |
| `MDARIX_CONNECTOR_DATABASE_URL`, `MDARIX_CONNECTOR_REST_BASE_URL` | no | Development connector endpoints. |
| `MDARIX_SIMULATE_DEPENDENCY_FAILURE` | local only | `1` makes analysis dependencies fail on purpose, to test the controlled error path. Refused in staging and production. |
| `MDARIX_ALLOW_LEGACY_AUTH_FALLBACK` | never | Removed with the in-memory session store; staging and production refuse to start when it is set. |

## Operations

| Variable | Required | Meaning |
|---|---|---|
| `MDARIX_ALERT_WEBHOOK`, `MDARIX_ALERT_EMAIL`, `MDARIX_ALERT_TIMEOUT_SECONDS` | recommended | Where operational alerts go (dead letters, stopped worker, failing jobs). |
| `MDARIX_SENTRY_DSN`, `MDARIX_SENTRY_TRACES_SAMPLE_RATE` | no | Error reporting. Only the shape of an error leaves: its type, the stack frames (file, function, line) and the request method and path. Exception messages, local variables, log breadcrumbs, request bodies, headers, cookies, query strings and user details are not sent (`backend/app/logging_setup.py`). |
| `MDARIX_LOG_LEVEL`, `MDARIX_LOG_FORMAT` | no | `INFO`; `json` (default in production) or `text`. |
| `MDARIX_OUTBOX_INTERVAL_SECONDS`, `MDARIX_OUTBOX_BATCH_SIZE`, `MDARIX_OUTBOX_MAX_ATTEMPTS` | no | Worker cycle: every 5 s, up to 50 events, 12 delivery attempts before an event is dead-lettered (OUTBOX_AND_SCHEDULER.md). |
| `MDARIX_OUTBOX_BASE_DELAY_SECONDS` | no | Wait before the first retry of a failed event (30 s), doubling with each further attempt. |
| `MDARIX_OUTBOX_MAX_DELAY_SECONDS` | no | Longest wait between two retries (3600 s); with the defaults the 12 attempts span about five hours. |
| `MDARIX_OUTBOX_PUBLISHER`, `MDARIX_OUTBOX_HEARTBEAT_FILE` | no | Event delivery adapter and the container health file. |
| `MDARIX_REPORT_WORKER_BATCH_SIZE` | no | Report jobs per worker cycle (10). |
| `MDARIX_SCHEDULER_HEARTBEAT_FILE` | no | File touched after every healthy scheduler cycle; defaults to the scheduler container health-file path. |
| `MDARIX_SCHEDULER_HEARTBEAT_URL` | yes (production) | External heartbeat endpoint (https) called after a healthy scheduler cycle, so an outside monitor notices when the scheduler stops. |
| `MDARIX_OPERATIONAL_URLS` | no | Addresses `scripts/validate_production_operations.py` checks from outside (comma-separated; default `MDARIX_APP_URL`). |

## Backups

The backup job (docker-compose.prod.yml, profile `backup`) reads `.env.production` and `.env.migrate`;
docs/runbooks/BACKUP_AND_RESTORE.md.

| Variable | Required | Meaning |
|---|---|---|
| `MDARIX_BACKUP_AGE_RECIPIENT` | yes (production) | age public key (`age1...`) backups are encrypted to. |
| `MDARIX_BACKUP_DB_USER`, `MDARIX_BACKUP_DB_PASSWORD` | recommended (`.env.migrate`) | The read-only backup login (`mdarix_backup`, created by `scripts/configure_backup_role.py`). Empty: backups log in as the owner. The password is refused in a long-running service's environment. |
| `MDARIX_BACKUP_S3_URI` | yes (production), or the acknowledgement below | Off-site copy, e.g. `s3://bucket/mdarix`. |
| `MDARIX_BACKUP_OFFSITE_ACKNOWLEDGED` | no | `true` states that backups leave the server another way (e.g. the managed database's own backups and point-in-time recovery), so production starts without `MDARIX_BACKUP_S3_URI`. |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION` | with `MDARIX_BACKUP_S3_URI` (`.env.migrate`) | Write-and-list credentials for the backup bucket (not needed with an instance role). |
| `MDARIX_BACKUP_KEEP_DAYS` | no | Local backups kept (14 days). |
| `MDARIX_BACKUP_DIR` | no | Host directory for backups (`/var/backups/mdarix`, owned by uid 70). |
| `MDARIX_BACKUP_HEARTBEAT_URL` | yes (production) | Dead-man's switch (https) pinged after every successful backup. |
| `MDARIX_BACKUP_MAX_AGE_HOURS` | no | `scripts/check_backup_age.sh` alerts when the newest backup is older (26). |
| `MDARIX_BACKUP_AGE_KEY_FILE` | restore only | Path of the age private key, mounted only for a restore. |
