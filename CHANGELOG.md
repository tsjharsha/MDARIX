# Changelog

All notable changes to MDARIX are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/).
The version being prepared is in `VERSION`; a release is the git tag `v<VERSION>` (`.github/workflows/release.yml`
builds, scans and publishes its images, and refuses a tag that does not match `VERSION`).

Every entry says what changed for the people who use or run MDARIX. Schema changes name their migration, so an
operator knows a release migrates the database.

## [Unreleased]

### Added

- Complaints › Second look: records cancelled or logged as inquiries or service records that carry a sign of a
  complaint (harm, a malfunction, a serious severity, a problem code or one of the organization's words), and No Fault
  Found or User Error codes that recur (3 or more on one product in 12 months), are listed most serious first, each
  with why it was flagged and its matched words marked. A person confirms or dismisses each with a reason, and may
  revise it; both are in the audit trail. MDARIX never changes the record in the source system.
- Complaints › Backlog: open complaints in no signal and no case, oldest first, against the organization's target
  (30 days by default), with past-target and due-soon counts and age bands; a record confirmed on the second look
  counts until it is closed.
- Complaints › Review settings: the backlog target and the second look's words, changed by a triage lead with a reason,
  versioned and audited. Migration `md40` adds the `complaint_settings` and `complaint_second_looks` tables (dedicated
  legacy databases: `scripts/add_workflow_tables_to_legacy_planes.py --apply`).

## [0.9.0] - 2026-10-12

The design-partner pilot readiness release.

### Added

- Production deployment for one VM with a managed PostgreSQL: `docker-compose.prod.yml` (Caddy with automatic HTTPS,
  API, worker, scheduler, ClamAV, one-shot migrate job, on-demand encrypted backups), with memory and CPU limits,
  graceful stop periods, health checks for every long-running service and bounded logs.
- Owner database credentials kept out of every long-running service: `.env.migrate` (template `.env.migrate.example`)
  is loaded only by the migrate and backup jobs, and the API, worker and scheduler refuse to start with the owner or
  backup password in their environment.
- Encrypted backups (age) of the control database, dedicated tenant databases and uploaded files, copied off-site, with
  a dedicated read-only `mdarix_backup` login (`scripts/configure_backup_role.py`), a failure alert, a success
  heartbeat, a backup-age check for cron (`scripts/check_backup_age.sh`) and restore of databases and files
  (`mdarix-restore`).
- Break-glass reset of a platform administrator's MFA (`scripts/reset_platform_admin_mfa.py`), audited.
- Public status endpoint `/health/status` (`ok`, `degraded` or `down`) for uptime monitors; readiness detail stays
  internal.
- Configuration gate (`python -m backend.app.config_check [--offline]`) covering alert destinations, staff alerts,
  MFA policy, database certificate verification, runtime role, placeholders, session limits, proxy hops and AI cost
  rates.
- Release pipeline: tagged releases build, scan (Trivy) and publish the api, web and backup images to GitHub Container
  Registry with their digests in the release notes; Dependabot for Python, npm, Docker images and GitHub Actions.
- CI: the full production stack started behind Caddy with a TLS database, the production smoke test, a scheduler run,
  a backup and a restore drill; data-plane routing tests against four tenant databases; migration downgrade/upgrade
  round trip; weekly security and image scans.
- Runbooks: incident response, outbox and scheduler, deployment hardening and monitoring; support ownership with
  response targets.
- Pilot readiness features: legal hold, client error and support problem reports, erasure log, seven-year audit
  retention by default, tamper-evident audit-chain verification, tenant exports, risk register and traceability,
  report content (migrations md23 to md25).
- Investigation workflow, phases 0 to 7: workflow roles, tasks and saved case context; signals, triage and detection;
  case scope and evidence review; intelligence judgements and structured Ask; risk and regulatory reviews with a
  controlled Decision Brief; the signed human decision, follow-ups, late evidence and closure; trust and audit of a
  case (migrations md26 to md33, human-readable business IDs in md26).
- Customer and organization lifecycle for Platform Administrators, platform accounts, redesigned dashboards for the
  platform, customer and workspace consoles, and shared tables with movable, resizable columns and server-side
  sorting.
- Imports keep the rows that pass, with a rejects file, and mask personal data instead of refusing the file.
- Deployment roles MULTI, PLATFORM and CELL from one codebase (ADR-013); tenant cells built from signed documents and
  licensed; the platform-cell link with enrollment, heartbeats, signed packages and licence grace (migrations md36,
  md37).
- Customer-approved support access: platform staff read an organization's data only after its administrator
  approves, for a limited time, and every use is audited (migrations md35, md38).
- A richer free-trial request: job title, country, phone in international format, company size, devices, markets,
  complaint system and volume, trial data and goal, and the confirmation that no patient data will be uploaded. Shown
  to the reviewers; the personal answers are erased with the organization (migration md39).
- A redesigned two-step sign-up page. An email that already has an account is told so, with Sign in and Reset password
  links; a repeated trial request is told it is still under review.
- Staging on an Oracle Cloud Always Free ARM server (`docker-compose.staging-oracle.yml`, ADR-017), private behind a
  login until the lawyer-approved legal texts exist (`MDARIX_SITE_ACCESS=private`,
  `MDARIX_PRIVATE_STAGING_ACKNOWLEDGED`).
- Optional `www.` redirect at Caddy (`MDARIX_WWW_REDIRECT=on`).
- Self-hosted GitHub Actions runners (`infrastructure/ci/self-hosted/`), chosen through the repository variables
  `CI_LINUX_RUNNER` and `CI_WINDOWS_RUNNER`; releases use the same runner.
- Draft privacy policy, terms of service and free trial agreement for the lawyer (`legal/`); runbooks for key and
  secret rotation.

### Changed

- AI processing is off for new organizations until an administrator enables it (migration md23).
- A contracted AI provider is refused in staging and production unless `MDARIX_GENAI_<NAME>_ZDR=true` (zero data
  retention confirmed) or `MDARIX_GENAI_ACCEPT_RETENTION=true`: add one before upgrading a server that uses a model.
- Servers split their settings into `.env.production` and `.env.migrate` and pass `--env-file .env.production` to
  every compose command; move `MDARIX_DB_OWNER_PASSWORD` into `.env.migrate` before upgrading.
- Administrator roles are stored in one canonical form (migration md25); ORM models and the schema are aligned
  (migration md24).
- The embedding model in the API image is pinned to one revision.
- GitHub Actions are pinned to commit SHAs; CI uses Node 22, as the web image does.
- Sign-up answers 409 for an email that already has an account (`EMAIL_ALREADY_REGISTERED`) or an earlier trial
  request (`TRIAL_ALREADY_REQUESTED`), instead of the same answer for every email. Rate limits still apply.
- The configuration check refuses draft legal documents (a DRAFT banner or a `[PLACEHOLDER]`) and, in production,
  requires encrypted off-site backups and outside monitors.
- Separation of duties: the last person to make a material edit to a decision cannot approve it.
- Large screens split into smaller files (case intelligence views, demo golden path); the older embedded platform
  administration screen is removed.

### Security

- The API image takes Debian's security updates at build time (fixes the libpcre2 finding); the backup image drops
  the unused `gosu` binary.
- Caddy no longer logs single-use tokens from links, marks API responses `no-store`, and sends
  `Cross-Origin-Resource-Policy: same-origin`.
- The web container runs read-only without Linux capabilities other than binding ports 80 and 443.
- Row-level security for organizations and customers, with every writer scoped (migration md34).
- Session cookie `SameSite=Strict`; invitation and activation links expire after 48 hours (was 72); a full export and a
  purge also need a current authenticator code; the API sets the same browser protections as Caddy.
- Image scans fail on every high or critical finding except the reviewed ones in `.trivyignore.yaml`.
- Caddy is built with `golang.org/x/net` v0.60.0 (CVE-2026-78669; Caddy v2.11.7 pins v0.59.0).
