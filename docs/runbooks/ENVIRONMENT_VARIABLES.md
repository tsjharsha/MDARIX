# Environment variables

Every setting MDARIX reads, by area. **Required** means staging and production refuse to start without a valid value
(`python -m backend.app.config_check` lists what is missing). Local development (`MDARIX_ENV=development`) uses safe
local defaults for most of them. `tests/test_environment_reference.py` fails when code reads a variable this page does
not list.

## Environment and address

| Variable | Required | Meaning |
|---|---|---|
| `MDARIX_ENV` | yes | `development`, `test`, `staging` or `production`. Unset or unknown means production, with every protection on. |
| `MDARIX_FEATURE_SET` | no | `full` (default: every screen and route, as built) or `mvp` (the lightweight MVP: the parked areas are hidden from the interface and their API routes answer 404 `NOT_IN_THIS_FEATURE_SET`; the code stays). Parked under `mvp`: the regulatory copilot and eSTAR package, the Risk & Traceability workspace, counterfactual and scenario engines, the legacy Decision Center, the static AI assurance view, the case story, and the platform's Stage 2, subscription and mapping-studio screens; in the workspace the Dashboard, Products, Evidence, Decisions, Intelligence and Trust & Audit sections (their work is on Readiness, the case page, My Work › Approvals and Records › Audit trail, Reports and Verify a signature); in customer administration Integrations and Data Mapping; in platform administration Data & Integrations, Renewals, Reminders, Tenant cells and Developer API (`backend/app/feature_set.py`, `frontend/src/app/featureSet.ts`). A free trial always shows the MVP interface (`feature_set.for_tenant`); the parked API routes follow this setting. Pilots run `mvp`. |
| `MDARIX_DEPLOYMENT_ROLE` | no | Which part of MDARIX this deployment is (ADR-013, `backend/app/deployment_role.py`): `MULTI` (default; everything in one deployment, as today), `PLATFORM` (platform administration only: customers, tenants, licences, standards; the workspace answers 404 and only platform staff sign in) or `CELL` (one organization's workspace and administration in its own database; platform administration answers 404 and platform staff cannot sign in). The scheduler and the worker run only their role's jobs. |
| `MDARIX_CELL_TENANT_ID`, `MDARIX_CELL_TENANT_KEY` | in a CELL | The UUID and key of the one organization a `CELL` serves. The start-up check refuses a cell whose database does not hold that organization under that key on the shared plane, and refuses any `MDARIX_DATA_PLANE_*` setting (a cell has one database). Not set for `MULTI` or `PLATFORM`. |
| `MDARIX_PLATFORM_SIGNING_PUBLIC_KEY` | in a CELL and on the PLATFORM | The platform's package-signing public key (Ed25519, URL-safe base64 of 32 bytes; `scripts/cell_platform.py keygen`). A cell applies only licences and packages signed with its private counterpart (`backend/app/cell_packages.py`); the platform verifies uploaded packages with it; `scripts/cell_install.py` writes it into the cell's settings. |
| `MDARIX_PLATFORM_URL` | in a CELL | The https address of the MDARIX platform the cell reports to (`backend/app/cell_link.py`): enrollment, a heartbeat every 15 minutes, the licence and packages. The platform never calls the cell. |
| `MDARIX_CELL_ENROLLMENT_TOKEN` | in a CELL, once | The one-time token from the enrollment bundle; the first `platform-sync` run exchanges it for the cell's certificate and credential, after which it is spent. Remove it from the settings once enrolled. |
| `MDARIX_CELL_IDENTITY_DIR` | no | Where a cell keeps its private key, certificate, the platform authority's certificate and its credential after enrollment (default `/var/lib/mdarix/cell`; `.mdarix-cell` in local development). Never in the database. |
| `MDARIX_PLATFORM_CA_FILE` | no | A CA bundle to trust for the platform's own server certificate when it is not publicly trusted (a private platform behind a corporate CA). |
| `MDARIX_PLATFORM_CA_KEY_FILE`, `MDARIX_PLATFORM_CA_CERT_FILE` | on the PLATFORM | The platform's small certificate authority (PEM; `scripts/cell_platform.py ca-init`) that signs each cell's client certificate at enrollment (`backend/app/cell_pki.py`). The front door requires that certificate from cells (`docs/runbooks/CELL_LINK.md`). |
| `MDARIX_CELL_MTLS_REQUIRED` | no | Whether the platform's API also requires the cell's certificate fingerprint, forwarded by the front door, besides the cell's credential (`backend/app/cell_link_api.py`). Default: yes outside local development. |
| `MDARIX_APP_URL` | yes | The https address people use (`https://app.example.com`). Links in emails and the trusted browser origin. |
| `MDARIX_ALLOWED_ORIGINS` | no | Extra trusted browser origins, comma-separated. |
| `MDARIX_DOMAIN`, `ACME_EMAIL` | yes (compose) | Caddy's domain and Let's Encrypt account email. |
| `MDARIX_WWW_REDIRECT` | no (compose) | `on`: Caddy also answers `www.<MDARIX_DOMAIN>` (its own certificate, so the www DNS record must exist) and redirects it to `MDARIX_DOMAIN`. Default `off`, the right value for a staging host name. |
| `MDARIX_REDIRECT_DOMAINS` | no (compose) | Other host names, separated by spaces (in double quotes in `.env.production`), that Caddy also answers and redirects permanently (301) to `https://<MDARIX_DOMAIN>` with the same path and query: a former main domain and the other registered domains, e.g. `"mdarix.in www.mdarix.in mdarix.net www.mdarix.net"`. Caddy obtains a certificate for each, so list only names whose DNS already points at the server; do not list `www.<MDARIX_DOMAIN>` while `MDARIX_WWW_REDIRECT=on` (Caddy refuses a name defined twice). Default empty: the site answers `MDARIX_DOMAIN` alone. |
| `MDARIX_SITE_ACCESS` | no | `public` (default) or `private`: Caddy asks for a login before every page and API call, except `/health/live` and `/health/status` for the uptime monitors. Read by Caddy and by the configuration check. Not for a PLATFORM front door, whose cells authenticate with their own `Authorization` header. |
| `MDARIX_SITE_LOGIN_USER`, `MDARIX_SITE_LOGIN_HASH` | when private | The login of a private site. The hash is the bcrypt output of `caddy hash-password`, in single quotes in `.env.production` (it contains `$`). Caddy refuses everyone while either is missing; the configuration check names the problem. |
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
| `MDARIX_DB_SOCKET_TIMEOUT_SECONDS` | no | Seconds a connection waits on the database socket before giving up (default 75, above the runtime role's 60 s statement timeout). |
| `MDARIX_DB_JOB_STATEMENT_TIMEOUT`, `MDARIX_DB_JOB_SOCKET_TIMEOUT_SECONDS` | no | Longer limits for the scheduler and the outbox worker only (defaults `300s` and 330 s); the API keeps 60 s. |
| `MDARIX_RLS_SYSTEM_TOKEN` | yes | Secret that lets the server read across tenants for platform work; the database stores only its hash. |
| `MDARIX_DATA_PLANE_<NAME>_DATABASE_URL` | per dedicated plane | Connection string of one dedicated tenant database (named by its registry row). |
| `MDARIX_DATA_PLANE_<NAME>_DATABASE_URL_OWNER` | per dedicated plane (migrate, backup) | The plane owner's connection string, in `.env.migrate` only; the migrate job migrates the plane with it and the backup job dumps it. |
| `MDARIX_DATA_PLANE_RUNTIME_USER`, `MDARIX_DATA_PLANE_RUNTIME_PASSWORD`, `MDARIX_DATA_PLANE_PASSWORD` | local only | Credentials of the four local synthetic planes. |
| `MDARIX_DATA_PLANE_POOL_SIZE`, `MDARIX_DATA_PLANE_MAX_OVERFLOW` | no | Pool per dedicated plane (defaults 3, 5). |

## Keys and secrets

| Variable | Required | Meaning |
|---|---|---|
| `MDARIX_MFA_ENCRYPTION_KEY` | yes | Encrypts authenticator secrets (URL-safe base64 of 32 bytes). Without it no one can set up MFA. |
| `MDARIX_MFA_ENCRYPTION_KEY_ID` | no | ID of the current MFA key (`k2` after the first rotation). Unset (the default): secrets are sealed without a key ID, exactly as before 0.10.47. Once set, new secrets record it. KEY_ROTATION.md. |
| `MDARIX_MFA_ENCRYPTION_KEYS` | no | Older MFA keys still readable during a rotation: `k1:<base64>` (the key in use before the first rotation is `k1`). Run `scripts/reseal_mfa_secrets.py --apply`, then remove them. Malformed entries, an ID listed twice or the current ID listed here stop the server; while any is listed the configuration check warns. |
| `MDARIX_CONNECTOR_ENCRYPTION_KEY` | yes | Encrypts customer-system API keys. |
| `MDARIX_DEMO_REQUEST_SALT` | yes | Salts the hashed address of demo requests. |
| `MDARIX_DEMO_REQUESTS_PER_SOURCE_HOUR`, `MDARIX_DEMO_REQUESTS_PER_DAY` | no | Demo request limits per sending address per hour (5) and in total per day (200). |
| `MDARIX_RATE_LIMIT_SALT` | yes | Salts rate-limit keys. |
| `MDARIX_PASSWORD_SCRYPT_LOG2_N` | no | Password hash cost. Unset (production default): N=2^15, r=8, p=3, an OWASP equivalent of N=2^17, p=1. When set, N=2^value with p=1; production refuses less than 17. Tests use 14. |
| `MDARIX_PASSWORD_HASH_CONCURRENCY` | no | Maximum password hashes allowed concurrently in one process (default 3), limiting CPU and memory pressure during sign-in bursts. |
| `MDARIX_RATE_LIMITS_ENABLED` | no | `false` only in automated tests; refused in production. |
| `MDARIX_SIGNUP_PER_ADDRESS_PER_HOUR` | no | Free-trial sign-up requests per network address per hour (default 30, since 0.10.62; 5 before). A venue's Wi-Fi is one address for everyone in the room. A missing, invalid or non-positive value keeps 30. Read when the API starts. |
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
| `MDARIX_OBJECT_STORAGE_ENCRYPTION_KEY_ID` | no | ID of the current file key (`k2` after the first rotation). Unset (the default): files are written without a key ID, exactly as before 0.10.47. KEY_ROTATION.md. |
| `MDARIX_OBJECT_STORAGE_ENCRYPTION_KEYS` | no | Older file keys still readable during a rotation: `k1:<base64>`. Run `scripts/reencrypt_object_storage.py --apply` in the API's container, then remove them, but keep each old key for as long as a backup made with it is kept. Checked as the MFA keys are. |
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
| `MDARIX_EMAIL_DELIVERY` | no | `off`: never hand an e-mail to SMTP (local scripts, timing runs, the demo stack); a `mdarix_whif_*` demo database is always off. Refused in staging and production. |
| `MDARIX_TRIAL_AUTO_APPROVE` | no | Which free-trial requests are approved right after sign-up (`backend/app/trial/auto_approval.py`). `company-and-personal` (default since 0.10.48, also when unset or empty): a company email, and a personal address at a known mail provider such as Gmail or Outlook (`PERSONAL_MAIL_DOMAINS`, approved by "Automatic approval (personal email)"). `company-domains` (the behaviour before 0.10.48): a company email only; a personal address waits for review. `off`: every request waits for review. Any other value is read as `company-domains`. In every mode a disposable address (`DISPOSABLE_MAIL_DOMAINS`), a second request from the same company domain or the same personal address, a domain that does not resolve, an address of the platform organization and anything over the day's caps wait for a Platform Administrator. To change it, set it in `.env.production` and run `dc up -d --no-build --wait` (`dc` as in DEPLOYMENT.md: the API is created again with it; no release); the sign-up page follows the setting (`/api/v1/public/site-info`, cached up to 5 minutes). |
| `MDARIX_TRIAL_AUTO_APPROVE_DAILY_MAX` | no | How many company-email trial requests per UTC day can be approved automatically (default 20). Every such request counts, approved or not; the rest wait for review. |
| `MDARIX_TRIAL_AUTO_APPROVE_PERSONAL_DAILY_MAX` | no | How many personal-address trial requests per UTC day can be approved automatically (default 10), a cap of their own: personal requests never use up the company cap, nor company requests this one. Every personal-address request counts, approved or not; the rest wait for review. |
| `MDARIX_TRIAL_USER_CAP` | no | The most people one free trial may have, the trial owner included (default 50, since 0.10.73; it was a fixed 3). A safety cap, not a sales limit: the trial owner is told plainly when it is reached ("Your trial has 50 people, its safety limit"). A value that is not a whole number from 1 reads as 50. After changing it, run `scripts/refresh_trial_story.py --apply` so the Free Trial plan's description and licensed-user limit say the same. |
| `MDARIX_TRIAL_DOMAIN_CHECK` | no | `dns` (default): automatic approval needs the email's domain to resolve (an A or AAAA record, 2-second lookup); otherwise the request waits for review. `off` skips the lookup on a development or test machine only (`MDARIX_ENV=development` or `test`); staging and production always look it up. |
| `MDARIX_TRIAL_ALERT_EMAIL`, `MDARIX_DEMO_ALERT_EMAIL` | `MDARIX_TRIAL_ALERT_EMAIL`: yes on a MULTI deployment (the one with free trials; since 0.10.37 the configuration check requires it there, because the alerts for a trial request waiting for review and for a trial asking to end early read only it); elsewhere one of the two | Who hears about new trial and demo requests, MVP conversation requests from trials (Next steps; the demo address first), and customer feedback (feedback falls back to `MDARIX_SUPPORT_EMAIL`). |
| `MDARIX_ROUTINE_PATH` | no | B7a, on unless `off`: Resolve and close, the Cases exports, files added to a Case, Settings › Alerts and files and the urgent e-mail. Off, those routes answer 404, the screens and the "Resolve and close" next step hide, the Cases import template is not offered and the closure checklist has no "customer told" item (closing behaves as before B7). Signed records stay readable and a complaint MDARIX closed can still reopen (`backend/app/feature_set.py`). Set it on `api` and `background`. |
| `MDARIX_RULE_REGISTER` | no | B4, on unless `off`: the five markets' reportability floors are read from the rule register (`backend/app/rule_register/data`), picked by the awareness day, and each market conclusion keeps the floor it used (signing refuses a draft whose floor changed: `FLOOR_CHANGED`). Off, every rule takes today's code (`reportability/legacy_v1.py`, the same outcomes, proved by `tests/test_b4_equivalence.py`), the rule register routes answer 404, the Rules tab and the Rules used panel hide, and no floor is recorded. Signed records are never changed either way (`backend/app/feature_set.py`). Set it on `api` and `background`. |
| `MDARIX_CHALLENGE` | no | B5a, on unless `off`: the investigation challenge (drafted explanations and challenge questions). Off, its routes answer 404 and the Challenge view and the brief's Challenge section hide (`backend/app/feature_set.py`). Set it on `api` and `background`. |
| `MDARIX_CLOSED_LOOP` | no | B5b, on unless `off`: "Did it work?" and the reopen triggers. Off, its routes answer 404, the screens hide and the hourly pass fires no trigger (`backend/app/feature_set.py`). Set it on `api` and `background`. |
| `MDARIX_B8_EU_MIR` | no | B8, on unless `off`: the EU MIR 7.3.1 file for EU and Northern Ireland reports (types by chain position, the follow-up made on submission, the XML checked against the Commission's schema at Send for approval and frozen with the approval, the PDF read from it, the EU rule book `eu-mir-rule-book-1`, the "MHRA MORE (EU form)" route for a Northern Ireland incident). Off, EU and NI reports work as before B8: one worksheet, the type chosen by hand, the worksheet PDF; `mir.xml` answers 404, no follow-up draft is created on submission and Northern Ireland keeps the single EU route. Chains and files already made stay readable (`backend/app/feature_set.py`, read on every call). Set it on `api` and `background`. |
| `MDARIX_B8_GB_MIR` | no | B8, on unless `off`: the same for GB reports, with MHRA's GB MIR 7.2.1 file (for upload in MORE), the GB rule book `gb-mir-rule-book-1` and the PDF record copy. Off, GB reports work as before B8. Set it on `api` and `background`. |
| `MDARIX_B9B_OTHER` | no | B9b, on unless `off`: a country outside the five markets (the country picker, the generic starter floor `OTHER-floor-1`, the "Other Regulatory Report" with its attached file, Report ID, acknowledgement and follow-ups). Off: the picker is hidden and its routes answer 404; assessments and reports already made stay readable. Needs the rule register on. Set it on `api` and `background`. |
| `MDARIX_B6_DEADLINE_LIST` | no | B6a, on unless `off`: the daily deadline list e-mail (job `deadline-list`, from 06:00 organization time) and the Deadlines CSV/PDF downloads on Oversight. Off: nothing is queued and the downloads answer 404. Set it on `api` and `background`. |
| `MDARIX_B6_LATE_ENTRY` | no | B6a, on unless `off`: a Case entered more than 24 h after awareness needs a late-entry reason, and Log a case shows possible duplicates before saving a back-entry. Off: today's behaviour (no reason asked, `/intake/possible-duplicates` answers 404). |
| `MDARIX_B6_REVIEWS` | no | B6a, on unless `off`: the signed reviews (audit trail, access, configuration) under `/api/v1/reviews` and their due items in Oversight. Off: the routes answer 404 and the tabs are hidden; signed reviews stay readable in the audit export. |
| `MDARIX_B6_CHANGE_REASON` | no | B6a, on unless `off`: a reason on every edit of a complaint's reporting facts and the working calendar, and on a re-upload that changes facts behind a signed conclusion. Off: no reason asked; "Facts changed after signing" still shows. |
| `MDARIX_B6_TRACE` | no | B6a, on unless `off`: "Trace" beside each report value and `GET /api/v1/reports/{id}/trace/{field}`. Off: links hidden, the route answers 404. |
| `MDARIX_B6_SIMILAR_WORDING` | no | B6a, on unless `off`: possible duplicates also by similar wording (half the words in common or more), in the duplicates list and at escalation. Off: only today's rule. |
| `MDARIX_B6_VALUE_CENTRE` | no | B6a, on unless `off`: the Value Centre (outcome numbers) on Oversight and `GET /api/v1/oversight/value-centre` (and `.csv`). Off: panel hidden, routes 404. |
| `MDARIX_NTP_SERVER` | no | B6a G19: the time server (`host` or `host:port`) the clock check asks once every 5 minutes; readiness and the operations alert compare it, and the database clock, with the application's within 1 s. Unset: the time server is not asked (app vs database only). Unreachable: the check is `unknown`, never ok. Use the hosting provider's time service, as the host's chrony does. |
| `MDARIX_EMAIL_INTAKE` | no | B7b e-mail intake. Off unless `on`: the `mail-in` receiver exits without listening, the "E-mail to check" routes answer 404 and no screen shows (`backend/app/mail_in/__init__.py`). Turn on only after inbound port 25, the MX record for the intake subdomain and the STARTTLS certificate are in place, and start the service with `--profile mail-in`. |
| `MDARIX_INTAKE_DOMAIN` | no | The intake subdomain the receiver accepts mail for (default `intake.mdarix.com`); every other domain is refused (no relay). |
| `MDARIX_MAIL_IN_HOST`, `MDARIX_MAIL_IN_PORT`, `MDARIX_MAIL_IN_CERT`, `MDARIX_MAIL_IN_KEY` | no | Where `mail-in` listens (default `0.0.0.0:2525`, published as port 25 by `docker-compose.prod.yml`) and the certificate and key it offers for opportunistic STARTTLS (no TLS when either is unset). |
| `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `RESEND_REPLY_TO`, `RESEND_VERIFIED_DOMAIN`, `RESEND_WEBHOOK_SECRET` | no | Inbound evidence email through Resend (optional feature). |

## Company and legal

| Variable | Required | Meaning |
|---|---|---|
| `MDARIX_COMPANY_LEGAL_NAME`, `MDARIX_COMPANY_ADDRESS` | yes | Shown on the legal pages, in the footer and in emails. |
| `MDARIX_SUPPORT_EMAIL`, `MDARIX_PRIVACY_EMAIL` | yes | Contact addresses shown to customers. |
| `MDARIX_LEGAL_TEXT_APPROVED` | yes | `true` once a lawyer approved the privacy policy, terms and trial agreement. |
| `MDARIX_PRIVATE_STAGING_ACKNOWLEDGED` | staging only | `true` on a private staging server (`MDARIX_ENV=staging`, `MDARIX_SITE_ACCESS=private` with its login): the legal texts may still be drafts and the company details empty, because only people given the login see the site (ADR-017). Refused in production, and ignored unless every condition holds. |
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
| `MDARIX_AI_FEATURES` | for any AI | The AI features this server lets call a model, comma-separated (`ask`, `summaries`, `case_analysis`, `drafting`, `evidence_extraction`, `code_suggestions`); empty (default) = none, so switching AI on for an organization runs nothing. The startup check warns when `MDARIX_AI_TRIAL_CHAIN` is set and this is empty; `/health/ready` reports it under `trial_ai_chain`. |
| `MDARIX_AI_TRIAL_CHAIN` | for free-trial AI | The free-trial providers in order, for example `freellmapi,omniroute`; empty (default) = no AI for free trials. Each must be in `genai/vetted_providers.json`; in staging and production FreeLLMAPI and OmniRoute must be at 127.0.0.1 (reached through the loopback forwarders, `docs/runbooks/AI_PROVIDERS.md`). |
| `MDARIX_AI_TRIAL_MONTHLY_TOKENS` | no | Monthly AI token allowance of a free trial without its own (200,000; lower than paid). |
| `MDARIX_GENAI_LOCATION` | with `vertex` | Vertex AI region (default `asia-south1`, Mumbai); production refuses another region unless `MDARIX_GENAI_VERTEX_REGION_EXCEPTION=true`. |
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
| `MDARIX_ALERT_FALLBACK_WEBHOOK` | recommended | An independent webhook that receives an alert only when the usual e-mail and webhook channels both failed to deliver it. Off when unset. |
| `MDARIX_EXPORT_MAX_BYTES` | no | Largest full organisation export, in bytes (default 1073741824 = 1 GiB). A larger export is refused before work starts. |
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
| `MDARIX_BACKUP_KEEP_DAYS` | no | Every local backup of the last 30 days is kept (default 30). |
| `MDARIX_BACKUP_KEEP_MONTHS` | no | Then the newest backup of each of this many months (default 12); the newest backup of all is always kept. |
| `MDARIX_BACKUP_DIR` | no | Host directory for backups (`/var/backups/mdarix`, owned by uid 70). |
| `MDARIX_BACKUP_HEARTBEAT_URL` | yes (production) | Dead-man's switch (https) pinged after every successful backup. |
| `MDARIX_BACKUP_MAX_AGE_HOURS` | no | `scripts/check_backup_age.sh` alerts when the newest backup is older (26). |
| `MDARIX_BACKUP_AGE_KEY_FILE` | restore only | Path of the age private key, mounted only for a restore. |
