# MDX-B10-006 Threat Model

| Field | Value |
|---|---|
| Document ID | MDX-B10-006 |
| Title | MDARIX Threat Model (STRIDE) |
| Version | 0.1 DRAFT |
| Owner | Srinivas Telikicherla (QA/RA) |
| Author | Drafted for review |
| Date | 8 Nov 2026 |
| Status | DRAFT |
| Code baseline | v0.10.92; production as described in `docs/runbooks/GCP_DEPLOYMENT.md` |
| Approval | |

## 1. Purpose
This document lists the threats to MDARIX's data, records and service, using STRIDE (Spoofing, Tampering, Repudiation, Information disclosure, Denial of service, Elevation of privilege) over the architecture as built. It names today's controls and the gaps. It is the input to the security policy set (MDX-B10-007) and the scope of the independent pen test (MDX-B10-009).

## 2. Scope
The production deployment on Google Cloud (Mumbai) and any staging copy of it; the web application, API, background service, database, file store, malware scanner, backups, e-mail delivery, and the platform-administration functions. The cell (dedicated data-plane) design is covered where code exists. AI is covered as a future surface (off today).

## 3. References
| Ref | Document (v0.10.92 unless stated) |
|---|---|
| R1 | `docs/handover/27_SECURITY_ARCHITECTURE.md`, `28_PRIVACY_PII_PHI_AI_BOUNDARIES.md`, `12_TENANT_ISOLATION.md`, `04_SYSTEM_ARCHITECTURE.md` |
| R2 | `docs/runbooks/GCP_DEPLOYMENT.md`, `DEPLOYMENT.md`, `PRODUCTION_SECURITY_AND_DR.md`, `BACKUP_AND_RESTORE.md`, `INCIDENT_RESPONSE.md`, `KEY_ROTATION.md`, `SUPPORT_ACCESS.md` |
| R3 | `docs/adr/ADR-011-control-plane-and-tenant-cell.md`, `ADR-015-platform-access-to-tenant-data.md` |
| R4 | `infrastructure/docker/Caddyfile`, `docker-compose.prod.yml`, `docker-compose.staging-oracle.yml` |
| R5 | `MDARIX-planning/b10-assurance-plan.md` (PT-01 to PT-15) |
| R6 | Internal security audit, 3 Nov 2026 (0 critical, 0 high, 3 medium, 6 low) (location to confirm) |

Note: handover documents 27 and 28 are short summaries (a few lines each). This model therefore relies mostly on the code and runbooks.

## 4. Architecture as built
```
Internet ──443/80──> [Caddy] ──internal network──> [API: FastAPI] ──TLS verify-full──> [PostgreSQL 16 + pgvector]
   │                   │ TLS (Let's Encrypt), HSTS, CSP,          │                       control data + tenant data
   │                   │ body limits, serves React build          │                       (forced RLS per organisation)
   │                                                              ├──> [ClamAV clamd] (every upload scanned)
   │                                                              ├──> [Encrypted file store on VM disk] (AES-GCM)
   │                                              [Background service: outbox worker + scheduler]
   │                                                              ├──> ZeptoMail SMTP (e-mail)
   │                                                              └──> sample clock, audit-chain check, exports, purges
   │
Operator ──IAP tunnel (35.235.240.0/20)──> SSH (OS Login, keys only) ──> VM (Shielded VM, Ubuntu 24.04)
VM cron ──age-encrypted dump + SHA-256 manifest──> /var/backups ──VM service account (create + view only)──> GCS bucket, Delhi
Daily disk snapshot (14 days, Mumbai)
```
- **One VM** (`e2-standard-2`, Mumbai) runs everything. Containers run read-only with all capabilities dropped (`docker-compose.prod.yml`). The database has no published port.
- **Tenancy:** one shared database (shared plane) with forced row-level security per organisation; tenant scope bound per session from the server-side session (`backend/app/db/tenant_scope.py`). Dedicated data planes and the cell design (ADR-011) exist in code and CI but are not used in production today.
- **Identity:** e-mail + password (NIST SP 800-63B rules, breached-password list), TOTP authenticator mandatory for administrators, Leaders and Approvers; fresh code per signing (`backend/app/mfa.py`); `__Host-` session cookie, 12-hour absolute limit and idle timeout (`auth/cookies.py`).
- **Platform access** to customer data only through customer-approved support grants (`backend/app/support_access.py`).
- **Start-up guard:** staging and production refuse to start on unsafe settings (`backend/app/config_check.py`).
- **Supply chain:** images scanned (high/critical stop the release), signed by digest, SBOM per image (`.github/workflows/release.yml`); dependency audit in CI (`pip-audit`); CodeQL workflow.

### 4.1 Assets
| Asset | Why it matters |
|---|---|
| Regulated records: complaints, conclusions, signatures, reports, audit trail | Integrity and availability are regulatory obligations of the customer |
| Personal data: reporters, patients (minimised), users | Confidentiality; GDPR/DPDP |
| Credentials and keys: passwords, TOTP secrets, file-encryption keys, RLS system token, backup age key, SMTP token | Compromise opens everything else |
| Tenant boundary | One breach across customers ends trust in the product |
| Service availability | Legal clocks run whether MDARIX is up or not |

### 4.2 Trust boundaries
TB1 Internet ↔ Caddy · TB2 Caddy ↔ API · TB3 API/worker ↔ database (and RLS scope inside it) · TB4 API ↔ file store and ClamAV · TB5 VM ↔ Google Cloud (bucket, snapshots, IAP) · TB6 worker ↔ e-mail provider · TB7 organisation ↔ organisation (logical) · TB8 MDARIX staff ↔ customer data · TB9 (future) API ↔ AI provider.

## 5. STRIDE by component
| Component | S | T | R | I | D | E |
|---|---|---|---|---|---|---|
| Caddy / browser | Phishing of users; cookie theft → `__Host-` cookie, HSTS | XSS changing pages → strict CSP (`script-src 'self'`) | – | Header leaks → nosniff, frame DENY, referrer policy | Large bodies → 25 MB / 1 MiB limits | – |
| API | Session-token or reset-link replay (PT-11, PT-12) | Changing an approved report (PT-04); ID tampering (PT-01); approval replay (PT-06); SQL injection (PT-07) | Actions without audit → audit events with actor, IP, reason | IDOR (PT-01), tenant-ID tampering (PT-02), expired-access download (PT-13), secondary surfaces (PT-16) | Rate limits in Postgres; auth scopes fail closed (`backend/app/rate_limit.py`) | Investigator doing an administrator action (PT-03); signing another user's decision (PT-05); platform access without a grant (PT-17) |
| Background service | – | Job writes in the wrong tenant (PT-15) | Jobs audited | E-mail to the wrong organisation (PT-15) | Dead-letter after 12 attempts; heartbeat monitors | Runs in system scope for some jobs → each call names its reason |
| PostgreSQL | Application role cannot widen scope without the system token | Audit rows: UPDATE/DELETE refused by trigger; hash chain (PT-14) | Chain verification daily | RLS forced; runtime role not superuser/BYPASSRLS (`config_check.py`) | Single instance on the VM | Owner credentials not allowed in long-running services (`config_check.py`) |
| File store + ClamAV | – | Malicious file (PT-08) → clamd INSTREAM; any failure refuses the file (`object_storage/service.py`) | Upload audited | Files encrypted (AES-GCM, key bound to object key); tenant-prefixed keys | Scanner down → uploads refused (fail closed) | – |
| Backups / GCS | – | Backup changed → SHA-256 manifest; bucket versioning, 30-day retention (not locked) | – | age-encrypted; private key off the server | VM loss → restore from Delhi copy | VM service account: create + view only, no delete |
| Operator access | IAP + OS Login; keys only | Direct DB edits by root on the VM (G-3) | Shell actions not recorded centrally (G-5) | Root reads `.env.production` secrets | – | Root on the VM = full control of every tenant (inherent to one VM) |
| Platform admins | MFA mandatory | Support grants: requester ≠ approver ≠ recipient, customer approves with authenticator, max 24 h | Grants audited | No standing access to tenant data (ADR-015) | – | Platform admin role guarded (`role_codes.py`) |
| AI (future) | – | Prompt injection via evidence (PT-09) | AI runs recorded | Extraction through AI (PT-10) → field allowlist (`ai_boundary.py`), PII masking (`genai/pii.py`), contracted providers only (`genai/policy.py`) | Monthly allowance | Release gate enforced in production (`ai_release_gate.py`) |

## 6. Pen-test threats PT-01 to PT-15
PT-01 to PT-15 are the external review's list, with its numbering and expected results. PT-16 and PT-17 are MDARIX's own extras, added to the pen-test scope.

| ID | Threat (expected result) | Today's controls (code, v0.10.92) | Gaps / what to test |
|---|---|---|---|
| PT-01 | **Change a complaint ID in the API** (expected: no unauthorised access) | Forced RLS: a session sees only its organisation's rows (`db/tenant_scope.py`, `md34_rls_defence.py`); 404 on foreign IDs (P360-11, S360-14); `tests/test_cross_tenant_routes.py`, `tests/test_rls_coverage.py` | Independent negative tests on every complaint and case route, both directions; legacy routes flagged in handover 42 |
| PT-02 | **Change the tenant ID** (expected: access denied) | Tenant comes only from the server-side session; clients cannot select a tenant or data plane (`db/data_plane.py`, handover 12) | Test every header, body, cookie and query field named `tenant_id` / `organization_id`; multi-organisation sign-in switching (`tests/test_multi_organization_signin.py`) |
| PT-03 | **An investigator attempts an administrator action** (expected: denied) | Server-side authorisation by role; UI visibility is not a boundary (`backend/app/access/authz.py`, `permissions.py`); `tests/test_authorization_matrix.py`, `tests/test_session_permissions.py` | Call every Customer Admin and Platform Admin endpoint with an INVESTIGATOR session; mass-assignment of role fields; `/api/v1/me/persona` (only the trial owner changes personas, `trial/team.py`) |
| PT-04 | **A user changes an approved report** (expected: the frozen record cannot change) | Approved snapshot and obligation lifecycle states (`authority_reports/rules.py`); signed records never edited, superseding versions only (`human_decision/rules.py`) | Direct API calls to update endpoints on approved and submitted reports; race with a concurrent supersede; the open-report "follow signed" path (`trial/open_deadlines.py`) |
| PT-05 | **Attempt to sign another user's decision** (expected: rejected) | Fresh authenticator code of the signed-in person per signing; signer taken from the session (`mfa.py`, `signing_commit.py`); SoD checks (`access/governance.py`) | Pass another user's ID in the signing request; session fixation; shared-device scenario |
| PT-06 | **Replay an approval request** (expected: no duplicate approval) | Version check (`seen_version`) refuses stale requests; a TOTP code is refused once its time step is used (`auth/totp.py` stores the last used step) | Replay of the request with a fresh code; replay after the record changes; race between two tabs |
| PT-07 | **SQL injection in search** (expected: no unauthorised database access) | ORM with bound parameters; RLS limits the blast radius | Search and sorting paths (`sorting_lookup.py`), raw SQL in data-plane code; second-order injection via imported data |
| PT-08 | **Malicious uploaded document** (expected: safe rejection or quarantine) | ClamAV scan, fail closed (`object_storage/service.py`); 10 MB limits; files encrypted; download names sanitised (`downloads.py`); CSV exports neutralised (`csv_safe.py`) | Archive bombs within 10 MB; file-type spoofing; macro documents; XLSX import parsing (`trial/xlsx.py`) |
| PT-09 | **Prompt injection in investigation evidence** (expected: AI ignores untrusted instructions) | AI off in 1.0; evidence treated as untrusted (IV-10); human review of every AI output; trust check (`trust_engine/auto.py`) | Test when AI is enabled; include IV-10 cases |
| PT-10 | **Extract sensitive information through AI** (expected: no disclosure) | AI off in 1.0; field allowlist for AI context (`ai_boundary.py`); PII masking (`genai/pii.py`); tenant-filtered retrieval (`tests/test_ai_isolation.py`); contracted providers only (`genai/policy.py`) | Test when AI is enabled: cross-tenant retrieval, protected fields, system-prompt disclosure |
| PT-11 | **Steal or replay session tokens** (expected: session controls hold) | `__Host-` cookie, Secure; idle timeout and 12 h absolute limit (`auth/cookies.py`); durable sessions ended on sign-out; single-use links (`auth/durable.py`) | Cookie reuse after sign-out and after password change; invitation-link reuse; cross-device |
| PT-12 | **Exploit the password-reset flow** (expected: no account takeover) | Reset links expire in 1 hour; older open links retired; rate limits; failed-only account counting (`auth/durable.py`, `rate_limit.py`) | Host-header poisoning of the reset link (app URL fixed by setting: confirm); user enumeration via timing or messages; MFA still required after reset |
| PT-13 | **Download evidence with expired access** (expected: denied) | Exports expire and are deleted (`tenant_export.py`); downloads streamed behind sign-in; support grants expire (≤ 24 h) | Download after offboarding, after role change, after grant expiry; direct object paths |
| PT-14 | **Modify audit history** (expected: prevented or detected) | Append-only trigger (`o31audit_immutability.py`); per-organisation hash chain; daily verification with anchors (`audit_chain.py`) | Anchors and logs on the same VM (G-3); test what a database-owner attacker can hide |
| PT-15 | **Exploit background-job tenant context** (expected: tenant boundary preserved) | One event per transaction; scope bound per session (`outbox/worker.py`) | No explicit negative test per job type (MDX-B10-004 RSK-026); sample-clock job scope |
| PT-16 | *Extra:* **Cross-tenant leakage through secondary surfaces** (search, trends, exports, reports, notifications, error messages, caches) (expected: no foreign data or counts) | Tenant-filtered search and exports; field policies; RLS | Count leaks ("no counts leak" in P360-11); error messages; e-mail digests |
| PT-17 | *Extra:* **Platform staff reach customer data without a customer-approved grant**; Customer Admin acting as approver (expected: denied) | Support grants with requester ≠ approver ≠ recipient and customer approval (`support_access.py`, ADR-015); administrators never approve (`md03_retire_viewer_approval_authority.py`) | Platform routes without `require_customer_approved_access`; grant scope (areas, read vs change) |

Acceptance criterion for the pen test: **zero unauthorised cross-tenant access**, shown by negative tests, not by RLS being enabled.

## 7. Gaps
| # | Gap | Effect | Proposed action | Gate |
|---|---|---|---|---|
| G-1 | **RPO**: no point-in-time recovery; daily dump + daily snapshot; files on VM disk (up to 24 h at risk). Documents disagree: `PRODUCTION_SECURITY_AND_DR.md` says RPO 1 h with PITR; `legal/SUBPROCESSORS.md` says no PITR; handover 38 describes managed-database PITR; SLO target is 24 h → 15 min. | Up to a day of regulated records lost | WAL archiving to the Delhi bucket or managed PostgreSQL with PITR before real data; fix the documents to one truth | B |
| G-2 | **Single VM**: database, application, files and backups' staging all on one host | Availability; one root compromise reaches everything | Accept for trials; for pilots decide shared plane vs dedicated cell (ADR-011 says dedicated cell for real data; the readiness decisions said shared plane) | B |
| G-3 | **Audit anchors and logs on the same VM** as the database | A root attacker could rewrite the chain and its anchors | Copy each day's chain heads to the backup bucket (create-only) or another store | B |
| G-4 | **Log retention**: container logs rotate at 10 × 20 MB | Possible shortfall against CERT-In 180-day log retention; weak forensics | Ship logs off-host with ≥ 180 days retention in India | B |
| G-5 | **No central security monitoring**: uptime and heartbeat checks only; error reporting off | Late detection | Alert on failed sign-ins spikes, support-grant use, chain-verification failure, config-check failure | B |
| G-6 | **Backup bucket retention not locked**; old versions deleted after 1 day | Ransom-style deletion through a stolen owner account | Consider a locked retention policy once retention is settled; restrict project owner accounts with MFA | C |
| G-7 | **Key custody**: the backup private key is with the operator alone | Single point of failure | Second sealed copy (owner + co-founder) | B |
| G-8 | **Handover 27/28 are stubs** | Weak documentation for auditors | Replaced by this model and MDX-B10-007 | B |
| G-9 | `object_storage/service.py` says "production must select s3"; production uses the encrypted local store by decision | Documentation conflict | Update the docstring or the decision record | B |
| G-10 | **CI blocked by GitHub billing** | Scans, CodeQL and tests not running on every change | Restore hosted CI or record self-hosted runs as evidence | B |
| G-11 | **No WAF / bot protection** in front of Caddy | Credential stuffing load, scraping | Rate limits exist; review need after pen test | C |
| G-12 | PT-03 (investigator → administrator action) and PT-10 (AI extraction) were missing from the first draft's threat list | Now covered in §6; PT-03 needs a full role × endpoint negative test, PT-10 waits for AI | Add both to the pen-test scope (done in MDX-B10-009) | B-0 |

## 8. Open points
| # | Point | Owner |
|---|---|---|
| OP-1 | Decide whether the extras PT-16 and PT-17 stay in the pen-test scope (recommended: yes). | Owner |
| OP-2 | Decide the pilot hosting model (shared plane or dedicated cell); the threat model and pen-test scope depend on it. | Owner |
| OP-3 | Locate and attach the 3 Nov 2026 security audit and its fix status; map its 3 medium and 6 low findings to this model. | Owner |
| OP-4 | Add an explicit test that a used TOTP step is refused for a second signing (code exists in `auth/totp.py`; test coverage to confirm). | Engineering |
| OP-5 | Review this model after every release that touches a trust boundary, and at least every 6 months. | Owner |
