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
- Complaints › Reportability: every complaint that reports a death, a serious injury or a malfunction, or a patient
  whose outcome is unknown, with its reporting clocks against the windows the organization entered from its own
  procedure (per market, calendar or work days), most urgent first; missing answers flagged (patient outcome, country,
  awareness date); records cancelled or logged as inquiries with harm counted and sent to the second look. A person
  records the decision (reported, with the report's reference and filing day, or not reportable) with a rationale; its
  timeliness against the binding window is kept and audited. A case's completed regulatory review with no reportability
  concern settles its complaints. MDARIX never decides reportability and never submits a report.
- Complaints › Reporting windows: the organization's windows, started from FDA and EU templates to check against the
  procedure, changed with regulatory approval and a reason, versioned and audited. Nothing is set by default.
- Records › Effectiveness checks: every CAPA's effectiveness check, including CAPAs closed without one and check days
  imported from the quality system; a plan (criteria, check day, measurement start), re-planned with a reason; the
  complaint recurrence before and since on the CAPA's product and problem codes (observed counts, not a statistical
  test); and a signed result (effective or not effective) with password and authenticator code, recorded as a signed
  approval record with the fingerprint of what was signed. After a failed check the next round is planned.
- Reminders: the scheduler job `reporting_reminders` (every 6 hours) puts reporting clocks due soon or overdue in the
  regulatory reviewers' queue (task REPORTABILITY_DECISION, at most 50 new a run) and checks due within 14 days in the
  quality reviewers' queue (task EFFECTIVENESS_CHECK); each is completed by the decision or the signature.
- The demo workspace shows hidden complaints, a recurring No Fault Found, reporting clocks and CAPAs without a check
  from the first minute (after `scripts/demo_tenant.py reset`).
- Migration `md41` adds `reportability_settings`, `complaint_reportability` and `capa_effectiveness_checks` (dedicated
  legacy databases: `scripts/add_workflow_tables_to_legacy_planes.py --apply`).
- Signals › one click to a case: "Open case" on a signal records the triage decision "investigation required" (when
  still due, marked as a one-step decision with its reason) and opens the case with every complaint, their versions
  and lots, for the person clicking, in one transaction (`POST /api/v1/triage/signals/{id}/open-case`,
  investigation.create, so an investigator no longer waits for a triage lead); the case page opens straight away.
- Signals › Trend check: every product version (or version and problem code, or complaint type) compared with its
  own history: the last 30 days against up to 180 days before them (never before the release), with the exact
  Poisson probability; significant below 1%, higher than usual below 5%, not assessed under 3 complaints or 60 days
  of history. Every complaint counts whatever its status (records dismissed on the second look are left out). A
  check beside the count rule: it raises no signal by itself; a triage lead raises one from a notable group.
- Signals › what the complaints have in common: a summary from the records (period, harm, lots, markets, recurring
  words, No Fault Found codes), every sentence citing its complaints, with the signal's own trend check; and an AI
  summary on request (ai.run), kept sentence by sentence only when every cited complaint is the signal's and no
  causal wording is used, recorded as an AI run. With AI off the records summary stands, with the reason.
- The case's one AI run: the analysis, competing explanations, challenges, unknowns, failure chains and the
  investigation brief in a single background pass for one point in time, each step reusing the one before, started by
  itself the first time the case page opens (never repeated), followed step by step on the case page and run again
  on demand (`/api/v1/investigations/{id}/ai-run`). Each step records whether AI or the rules wrote it.
- The Decision Brief writes itself first: starting from the AI draft fills the problem statement from the case's
  question and the recommended actions from the AI's next steps (only where empty; the conclusion stays the
  author's), and flags a draft older than the case's latest evidence or scope. The decision form ticks the follow-ups
  the recommended actions name (CAPA, risk file, regulatory action, field action, product change) for the decision
  maker to confirm.
- A case's regulatory review shows each complaint's reporting clock against the organization's windows (and any
  decision recorded), with a link to the reportability watch.
- Readiness (the home of the lightweight MVP): what an FDA investigator or a notified-body auditor would find today,
  read from the organization's records (rules only): the four numbers (complaints to recheck, complaints past target,
  reporting clocks, trends without CAPA or risk review) and further checks drawn from 2025-2026 findings (harm
  complaints closed without an investigation, CAPAs without a verified effect, signals past their triage date); each
  says why it matters and opens the records behind it (`GET /api/v1/readiness`). Under the `mvp` feature set it
  replaces the Dashboard as home.
- The readiness summary for management review as a PDF (`GET /api/v1/readiness/summary.pdf`, data.export, audited),
  for 90 days to 3 years: readiness checks, complaint handling by product version, second-look outcomes,
  reportability decisions and their timeliness, signals and trend check results, CAPAs and effectiveness checks,
  organized by the management review inputs of ISO 13485:2016 clause 5.6.2.
- Reporting window templates for Great Britain (MHRA: 15 days for a serious incident, 10 for a death; Medical Devices
  Regulations 2002 as amended, regulation 44ZH) and Canada (Health Canada: 10 days for a death or serious
  deterioration, 30 days for an incident that could cause one if it recurred; SOR/98-282 section 60).
- Migration `md42` adds `case_ai_runs` (dedicated legacy databases: `scripts/add_workflow_tables_to_legacy_planes.py
  --apply`).
- Records › Risk file input (ISO 14971:2019 clause 10): for every product, what post-market data said in the period
  (complaints reporting harm or a malfunction, a rising trend, decided signals) beside what reached its risk file
  (completed risk reviews, the risks they assessed, the outcomes, reassessments open or overdue). Each product shows
  one state, most urgent first: post-market data not reviewed against the risk file, reassessment overdue,
  reassessment open, no risk register, reviewed or quiet; the product view lists each risk with the reviews that
  assessed it, never-assessed risks first (`GET /api/v1/post-market/risk-file`, `.../risk-file/{product_id}`, 90 days
  to 3 years, rules only, no new tables).
- Readiness: a check for products whose post-market data has not reached the risk file (critical when not reviewed or
  a reassessment is overdue), opening Records › Risk file input; the management review summary PDF gains section 5,
  "Post-market data and the risk file".
- The automatic trust check (policy `MDARIX_AI_TRUST_POLICY_R1_V2`, `trust_engine/auto.py`): every AI result is checked
  as it is saved, not only when the API is asked. It covers the case's AI run, signal summaries, model-drafted briefs
  and second-look explanations. The checks are: every cited source exists (the case's evidence, including linked
  records, the signal's complaints, the complaint's own fields); no stated root cause, causal proof, probability, or
  decision that belongs to people; no asserted certainty (a warning); provider and model recorded; the right
  organization. Only what the reader sees is checked, never what the feature's checks already removed. The verdict
  (passed, passed with limitations, blocked) is saved with the result (`assurance_results`, `assurance_checks`), and
  every case AI step, signal summary and second-look explanation shows it as a badge that opens its checks. Ask answers
  carry the same verdict, judged on the answer as shown. A model-drafted investigation brief is now saved as an AI
  result (`InvestigationBrief.ai_execution_id`), so it is checked too. `GET /api/v1/ai/trust-policy` describes the
  checks.
- Complaints › Second look › Explain with AI (`POST /api/v1/complaints/{id}/second-look/explain`, ai.run): at most
  three sentences on why a flagged record may meet the complaint definition (ISO 13485:2016, 3.4), each quoting the
  record's own fields word for word. A sentence is dropped when a quote is not in the record, when it says the record is
  or is not a complaint, is reportable or needs a recall, or when it states a cause. Saved as an AI result with its
  trust check and shown beside the rules' reasons; when AI is off or unavailable, the reasons stand alone and the screen
  says why. The record and the decision are never changed.
- The AI release gate (`backend/app/ai_release_gate.py`, `GET /api/v1/ai/release-gate`). It has four bars: a contracted
  provider with zero data retention; the golden dataset signed off by a named person; the full golden evaluation (15 of
  15, model-written) passed with the configured model; the automatic trust check. In production, switching AI on for an
  organization is refused (`AI_RELEASE_GATE_NOT_MET`) until all four are met. Administrators see the bars under
  Security › AI processing, and MDARIX staff see them, with what to do, in the AI Control Center.
  `scripts/qualify_ai_golden_dataset.py --human-sign-off --name --role --confirm` records a person's sign-off bound to
  the lock's hashes, refusing names that read as a tool or an agent. `scripts/run_real_evaluation.py --gate
  --require-model --release-record` writes `evaluation/AI_RELEASE_RECORD.json` only for a full pass on the signed-off
  dataset. Neither file exists yet: the dataset awaits a person's sign-off, and the evaluation awaits the contracted
  provider.

- The quality loop, an animated hero on Readiness, the Dashboard and Getting started. The inspection checks are
  drawn as stations on one closed loop, in the order a complaint travels: hidden complaints found, handled on time,
  reported in window, harm investigated, signals triaged, trends acted on, CAPAs proven, risk file fed. A pulse
  travels the loop and stations that need attention pulse; the weakest link is named. A list beside it says the same
  in words and opens each station's records. The picture is still and complete under reduced motion.
- The free trial's story (`GET /api/v1/trial/story`, `backend/app/trial/story.py`): nine chapters of the loop. Each
  shows what the trial's records hold, the 2026 inspection pain it answers, and whether the organization acted in it.
  A chapter counts only on a record the organization created (a second-look decision, a reporting decision, a case
  from a signal, an AI run or Ask answer, a signed decision, an effectiveness check, a completed risk review, a
  summary download, its own imported complaints), never on page views.
- Platform Admin › Customers & Tenants › Trials (`GET /api/v1/platform-admin/trials`): every free trial holding data,
  with its days left, users and rows against the limits, and how far into the story it went. Each row shows the
  chapter to try next, the last activity and the trial's feedback. Figures show active trials, those ending within 7
  days, those that acted, engaged and uploaded their own data. A per-chapter funnel shows where trials stop, and a
  list names who needs attention first. A tenant's AI processing panel now shows the AI release gate.
- New free trials get the rest of the sample story at approval (`seed_story_examples`): 9 complaints, 2 CAPAs, 3 risks
  and sample FDA and EU reporting windows, all marked `MDARIX_SAMPLE`. The complaints cover a cancelled record and an
  inquiry with harm or complaint signs, a recurring No Fault Found, harm and malfunction complaints with running
  reporting clocks, and a harm complaint closed without an investigation. One CAPA was closed without an effectiveness
  check, one has its check due. Complaints, Records and Readiness therefore show findings from the first minute.
  `scripts/refresh_trial_story.py [--apply]` adds the same records once to trials approved earlier. It never changes a
  trial's own records or reporting windows.

- The trend check counts per unit in the field (md43 `lot_batches.quantity`). When every lot of the versions compared
  has a quantity, the expected number follows unit-days (each lot counted from its release for its quantity), so a
  version shipped in growing numbers no longer looks like a rising trend for that reason alone. Without quantities it
  counts by calendar days and says so. The lot import takes an optional `quantity` (a whole number, checked before
  saving; synonyms such as lot size and qty are matched in mapping). Legacy dedicated databases get the column from
  `scripts/add_workflow_tables_to_legacy_planes.py`.
- A new version is compared with the version it replaced. Too young for its own history, it was "not assessed" before.
  Now its last 30 days are compared with the previous version's complaints over the 180 days before its release: is
  the new version worse than the one it replaced? Trend check shows what each group was compared with and how it was
  counted.
- Free trials: the sample lots carry quantities, and signal detection runs at approval, so the trend chapter has a
  finding from the first minute. OrbitCare 300 Rev B is significantly higher than Rev A per unit in the field, with its
  count-rule signal waiting. The trial story's trend chapter counts signals waiting for a decision or a case.
  `scripts/refresh_trial_story.py --apply` adds the quantities and runs detection for trials approved earlier.
- AI go-live tools. `scripts/ai_provider_preflight.py` checks every provider setting (provider, key, contract, zero
  data retention, price, production policy) and lists the release gate's bars; it sends nothing and changes nothing.
  `scripts/golden_review_pack.py` writes the reviewer's pack for the golden dataset sign-off: each of the 15
  scenarios with its evidence, expected findings, forbidden conclusions and adversarial check, then the sign-off
  statement and command.
- Readiness › Inspection pack (ZIP): the readiness summary PDF, the eight checks as a table, one CSV per check with
  every record behind it (with the source system's identifier), a README and a manifest with each file's SHA-256, for
  the day an inspector arrives (`GET /api/v1/readiness/inspection-pack.zip`, data export permission, audited as
  `READINESS_INSPECTION_PACK_EXPORTED`). A list that cannot be read is named in the pack instead of failing it. The
  trial story's "Show the inspector" chapter counts the pack as well as the PDF.
- The weekly readiness email: on Monday from 06:00 UTC each organization's quality leads (Leader and Reviewer) get
  their quality loop (the eight checks in story order), what changed since last week and the weakest link, with a
  link to Readiness. The scheduler job `readiness-digest` (every 6 hours) queues it once per organization and ISO
  week through the outbox, which holds no email addresses. My Account › Profile lets each person switch it off
  (`GET/PUT /api/v1/me/email-preferences`, audited as `EMAIL_PREFERENCES_CHANGED`).
- Per-unit trends from day one: Import data explains the key columns of each template, and the lots template says
  what `quantity` does; Trend check, when it counts by calendar days, says so and opens Import data. Guide:
  `docs/user-guide/PER_UNIT_TRENDS.md`.
- Free trials book a one-to-one demo from Getting started: times that suit, an optional phone number, the chapters to
  focus on and a note (`GET/POST /api/v1/trial/demo-request`, one open request per trial, audited as
  `TRIAL_DEMO_REQUESTED`). The MDARIX team sees it in Platform Admin › Onboarding, marked as from a trial with the
  organization and how far into the story it went, and by email (`MDARIX_DEMO_ALERT_EMAIL`, else
  `MDARIX_TRIAL_ALERT_EMAIL`). Platform Admin › Trials counts the trials that booked a demo and shows each one's.
- Website home: the quality loop, drawn with illustrative synthetic values and labelled so, and a "Start free trial"
  button beside "Request a demo".
- Migration `md44` adds `auth_users.email_preferences` and the demo request's source, trial, organization, preferred
  time and context (legacy dedicated databases: `scripts/add_workflow_tables_to_legacy_planes.py --apply`).

### Fixed

- The AI release gate's first bar ("a contracted AI provider with zero data retention") is read from the contract
  settings themselves (`MDARIX_GENAI_CONTRACTED_PROVIDERS` and the provider's ZDR setting). Outside production the
  provider policy allows any provider, so a free development provider showed the bar as met.
- The readiness summary PDF no longer says the numbers of devices in use are unknown when lot quantities are
  imported; it says how the trends were counted (per unit in the field, by calendar days, or both).

### Changed

- Getting started tells the trial as a story. The quality loop names the next chapter, and each chapter shows its
  live finding, why it matters and where to try it. Progress comes from the server (what the organization did), not
  from the browser. The import, insights and team panels are unchanged.
- Under the `mvp` feature set the template engines that only looked like AI are hidden. The case AI run skips the
  failure-chain step (a fixed two-link template) and says why; the investigation panel no longer generates template
  chains; the static agent catalog (`GET /api/v1/ai/agents/catalog`) is parked, and the AI Control Center shows the
  trust check's policy instead. Chains people build on the case, and the full product, are unchanged.

- Production runs one `background` service instead of `worker` and `scheduler`: `scripts/run_background.py` starts the
  outbox worker and the scheduler unchanged as two processes, passes a stop signal to both and exits when either
  stops, so Docker restarts the container; its health check needs both heartbeats (1.5 GB, 60 s stop period). After
  upgrading, `docker compose up -d --remove-orphans` removes the old containers; `dc exec background python
  scripts/run_scheduler.py --list` replaces `dc exec scheduler ...`.
- ClamAV reloads its signatures in place (`CLAMD_CONF_ConcurrentDatabaseReload: "no"`), so its limit drops from 2 GB to
  1.5 GB; scans pause for a few seconds during the daily update. The long-running services now need 5.25 GB (was
  6.75 GB), plus 1 GB while the backup runs.
- CI: a pull request runs the fast checks (backend, frontend, security, image scan, production compose and stack, the
  desktop browser profile); dedicated data planes, data-plane routing, deployment roles, container and simulator
  validation and the mobile browser profile run after every merge to main, nightly (was weekly security scans only) and
  on demand. The release gate accepts those as skipped only on a pull request.
- Dependabot proposes updates monthly (was weekly), grouped (Python and npm minor and patch updates, the base images,
  the GitHub Actions); security updates still arrive as soon as an advisory is published.

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
