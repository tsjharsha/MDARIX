# MDARIX target architecture: phase-by-phase implementation plan

| | |
|---|---|
| Status | **Proposal for approval.** No code, database or configuration has been changed for this plan. |
| Date | 2026-10-08 |
| Implements | `docs/architecture/MDARIX_TARGET_ARCHITECTURE_DESIGN.md` (control plane + tenant cell) |
| Code checked | Branch `mvp/p2-hardening` (main `c57e2d9` plus the three unmerged branches `mvp/docs-refresh`, `mvp/import-options`, `mvp/p2-hardening`), in three read-only code inventories: data placement per table; runtime, identity and jobs; integration, reference data, AI and support access. File references below come from those inventories. |
| Sizes | S = days, M = 1-3 weeks, L = 3-6 weeks, for one experienced developer. Relative estimates, not commitments. |

---

## 1. Summary

**The key finding makes the plan smaller and safer than the design document suggested.**

A tenant database created today by `scripts/migrate_data_planes.py` already receives **every table** in the application (it runs the full Alembic chain). When a tenant is on the "shared plane", the application already uses **one database session for everything** (`backend/app/db/data_plane.py:81-83, 196-200` returns the control session). That is the configuration in which the whole test suite runs today.

So a **tenant cell does not need tables to be re-routed one by one.** A cell is the existing application, running in a new `CELL` role, for exactly one tenant, against one database that belongs to that tenant. Everything that is today written to the central database (users, sessions, MFA secrets, signatures, audit events, outbox, connector and mapping configuration, settings) is then automatically in the tenant's own database. The 16 places that today write to two databases in one request become single-database writes. The audit screens that today miss half the audit trail see all of it.

The work is therefore mainly:
1. a **deployment role switch** (`MULTI` = today, `PLATFORM`, `CELL`) that mounts the right screens, routes and background jobs;
2. a **cell installer**, a **licence** delivered to the cell, and a **tool to move an existing tenant** into a cell;
3. the **platform-to-cell link** (enrollment, heartbeat, signed packages);
4. **removing platform staff's reach into tenant data**, with customer-approved support access;
5. **per-cell storage, keys, backups and residency checks**;
6. the **two-cell proof** with an automated isolation suite;
7. then the product capabilities: integration in the cell, custom fields, AI policy, reference-data packages and upgrades.

**Safety principle:** `MULTI` (today's behaviour) stays the default and keeps working, unchanged, until the final cutover. Every phase must leave the existing CI suite green. Nothing is moved or deleted until a tenant is deliberately moved into a cell with your approval.

---

## 2. Ground rules for every phase

1. **Nothing breaks the current system.** `MDARIX_DEPLOYMENT_ROLE` defaults to `MULTI`, which behaves exactly as today. New behaviour is reached only by setting `PLATFORM` or `CELL`.
2. **Database migrations only add** (new tables, new nullable columns, new triggers). No table is moved, renamed or dropped during this plan. Each migration has a working downgrade, checked by the existing up/down/up step in CI. Removals happen in a later "contract" release, after every tenant has moved.
3. **One branch and one pull request per phase** (smaller pull requests per step where a phase is large). The relevant tests run before anything is pushed. Nothing is pushed without your go-ahead, and nothing is merged without your approval.
4. **The golden tenant `ACME_CARE_SYNTHETIC` is never touched in the real database.** Tests and the proof of concept use synthetic tenants only (Tenant A "Aster Medical", Tenant B "Nimbus Health").
5. **No secrets in the repository; `.env` files are not edited.** Package-signing keys live in CI secrets or offline, never in code.
6. **Each phase has a stated rollback:** revert its pull request. Because `MULTI` is the default, reverting never affects running tenants.
7. **The golden AI dataset lock stays as it is.** If a phase changes AI outputs, you re-approve the lock.

---

## 3. Decisions needed from you before Phase 1

| # | Decision | Recommendation |
|---|---|---|
| D1 | Approve the 12 decisions in the design document (section 17, question 12), with the corrections in section 9 of this plan | Approve |
| D2 | Build the cell as the existing application against one tenant database (this plan's approach), rather than re-routing each table | Approve: it reuses the configuration the test suite already proves |
| D3 | Where design partners run: MDARIX-managed cells (which cloud and region), or the partner's own cloud | MDARIX-managed cells in one EU or US region per partner's contract; customer cloud when a partner requires it |
| D4 | Free trials and the public demo: keep one `MULTI` "sandbox" deployment restricted to synthetic data and trial terms, or give each trial its own cell | Keep a sandbox for trials and demos; terms forbid real patient data; a converting customer is moved into a cell with the Phase 3 tool |
| D5 | Who configures a customer's products during onboarding (today platform staff can, `backend/app/access/platform_reference.py:143-360`) | The customer administrator in the cell, or MDARIX staff through an approved support grant |
| D6 | Licence when the platform cannot be reached: grace period, and what happens at expiry | 30 days' grace; after that the cell becomes read-only (no new cases or signatures); data stays available |
| D7 | How a cell proves its identity to the platform | Mutual TLS with a platform-issued client certificate (as in the design) |
| D8 | How cells receive software updates | Signed container images pulled from the registry by the cell operator; the platform only offers the version |
| D9 | Problem reports from a cell to MDARIX support | Reference number, page and error code always; free text only when the user ticks "send my description to MDARIX" |
| D10 | Open policy question: may the quality reviewer who accepted a brief also sign it? (Today only the brief's authors are barred.) | Bar them too, for stronger separation of duties. Your call. |
| D11 | Replace the earlier decision "pilots start on the shared plane" | Replace: pilots with real data start in their own cell |

---

## 4. The phases at a glance

```
  P0 Prepare ──► P1 Security fixes ──► P2 Deployment roles ──► P3 Cell installer,
  (S)            (M)                    (L)                     licence, tenant move (L)
                                                                     │
        ┌────────────────────────────────────────────────────────────┘
        ▼
  P4 Platform ↔ cell link ──► P5 Platform out of ──► P6 Per-cell storage, keys,
  (L)                          tenant data (M)        backups, residency (M)
                                                            │
        ┌───────────────────────────────────────────────────┘
        ▼
  P7 Two-cell proof + isolation suite in CI (M)
        │
        ╞══ GATE A: design-partner demonstrations (synthetic data) ══
        ▼
  P8 Integration in the cell (L) ──► P9 Custom fields (M) ──► P10 AI policy per cell (M)
        │
        ▼
  P11 Reference packages, upgrades, restore drill (M) ──► P12 Readiness and cutover (M)
        │
        ╞══ GATE B: first real customer data ══
```

P8, P9 and P10 can partly run in parallel once P7 is done, if more than one developer is available. P10 depends only on P2 and P6.

| Phase | Goal | Size | Depends on | Exit criterion (summary) |
|---|---|---|---|---|
| P0 | Clean starting point, decisions recorded | S | none | Branches merged, ADRs written, baseline recorded |
| P1 | Close security gaps that exist in any architecture | M | P0 | Each fix has a test; full CI green |
| P2 | One codebase, three roles (`MULTI`, `PLATFORM`, `CELL`) | L | P1 | Route and job inventories per role tested; `MULTI` suite unchanged |
| P3 | Install a cell, license it, move a tenant into it | L | P2 | Fresh cell is empty; moved tenant is identical and works |
| P4 | Cell talks to the platform: outbound only, metadata only | L | P3 | Enrollment, heartbeat and signed packages tested; cell works offline |
| P5 | Platform staff cannot reach tenant data; support needs customer approval | M | P4 | Scenario 7 tests green |
| P6 | Each cell has its own files, keys, backups; residency enforced | M | P3 | Cell backup and restore tested in CI; residency refusals tested |
| P7 | Two isolated cells, proven automatically | M | P4-P6 | Isolation suite green in CI |
| P8 | Integration runs in the cell: incremental, quarantine, governed mappings | L | P7 | Live-simulator sync tests green in both cells |
| P9 | Customer custom fields without code | M | P8 | Custom-field tests green in both cells |
| P10 | AI policy per cell; no AI traffic through MDARIX | M | P2, P6 | AI boundary tests green |
| P11 | Standard updates adopted safely; upgrades and restores proven | M | P4, P8 | Scenarios 10 and 11 green; restore drill recorded |
| P12 | Ready for real customer data; tenants moved | M | all | Security test and validation draft done; pilot tenants in cells |

**Mapping to the design document's phases:**

| Design phase | This plan |
|---|---|
| 1, cell boundary in code | P1, P2, P3, P5 |
| 2, two-tenant proof | P4, P6, P7 |
| 3, integration | P8 |
| 4, custom fields | P9 |
| 5, AI policy | P10 |
| 6, operations | P11 |
| 7, readiness | P12 |

---

## 5. Phase details

### Phase 0: Prepare (S)

**Goal:** start from a clean, green main branch with the decisions written down.

| Step | Work |
|---|---|
| 0.1 | Push the three stacked branches (`mvp/docs-refresh` → `mvp/import-options` → `mvp/p2-hardening`; the P2 rerun passed 1,359 tests), open the pull requests, wait for CI, and merge **only with your approval**. Fix the outdated *Import data* screen text (`frontend/src/features/workspace/UserWorkspace.tsx:136-141`, "nothing is saved unless every row passes"). |
| 0.2 | Record decisions D1-D11 as ADRs in `docs/adr/` (ADR-011 onwards: control plane and cell; data placement; deployment roles; cell identity and packages; support access; migrations policy). |
| 0.3 | Record the baseline: the CI test counts, the migration head (`md34rlsdefence`) and the route list, so later phases can prove nothing was lost. |
| 0.4 | User-owned: tag `v0.9.0` on the last green main as the pre-change reference. |

**Exit:** main green with the three branches merged; ADRs merged.
**Rollback:** not applicable (no behaviour change).

### Phase 1: Security fixes needed in every architecture (M)

**Goal:** close gaps that are real today and would be carried into the cells. Behaviour is otherwise unchanged.

| Step | Problem today (evidence) | Change | Test |
|---|---|---|---|
| 1.1 | The generic edit route can set a mapping to RELEASED or rewrite a released mapping's rules without the second approval (`backend/app/access/configuration.py:603-607, 693-701`); only a string check tests it (`tests/test_day35_admin_control_plane.py:88`) | The generic route refuses `status` and `mapping_rules` for mappings in governed states; status changes only through the release flow (`:988-1113`) | New `tests/test_mapping_edit_route_governance.py`: each bypass is refused and audited |
| 1.2 | A support-access grant does not record who requested it, so a requester can approve a grant made for someone else (`backend/app/access/platform_tenants.py:464-501`, model `customer_lifecycle.py:181-198`) | Migration md35 adds `requested_by`; approver must differ from requester and target. (Interim: P5 replaces this with customer approval.) | Extend `tests/test_business_ids_platform_api.py` or a new support-grant test |
| 1.3 | Database errors can carry record values (`backend/app/db/data_plane.py:155-162` lacks `hide_parameters`; same for the control engine in `backend/app/db/session.py`) | `hide_parameters=True` on every engine | Test that a failing statement's logged message holds no bound values |
| 1.4 | Sentry sends exception text, local variables and breadcrumbs (`backend/app/logging_setup.py:81-106`) | No personal data, no local variables; a `before_send` that keeps the exception type and stack frames but drops messages and request bodies | Unit test of the scrubber |
| 1.5 | The proxy logs search terms in query strings (`infrastructure/docker/Caddyfile:72-84`) | Log the path without the query string | Compose config check in the production-stack CI job |
| 1.6 | The embedding model downloads from the network with no checksum when not cached (`retrieval/embedding_provider.py:107-109`) | Production refuses to download: the model must be in the image, verified by checksum at startup (`config_check`) | Test that production mode with no cached model fails clearly |
| 1.7 | Schema discovery calls `/health` when no path is configured (`backend/app/access/common.py:384`) and omits the tenant parameter | Default to the schema path; add the tenant parameter as `connector_sync.py:99-101` does | Unit test |
| 1.8 | The outbox worker does not bind the tenant on a dedicated plane (`scripts/run_outbox_worker.py:56-67`) | Bind the tenant on every plane | Worker test on a dedicated plane (dataplane CI job) |

**Exit:** each fix has a passing test; the full CI suite is green.
**Rollback:** revert per fix.

### Phase 2: Deployment roles: `MULTI`, `PLATFORM`, `CELL` (L)

**Goal:** one codebase and one image, three roles. `MULTI` is today's behaviour and the default.

| Step | Work |
|---|---|
| 2.1 | **Setting** `MDARIX_DEPLOYMENT_ROLE` (default `MULTI`). `config_check` rules per role:<br>• `CELL` requires `MDARIX_CELL_TENANT_ID` and `MDARIX_CELL_TENANT_KEY`, and refuses any `MDARIX_DATA_PLANE_*` setting (a cell has one database).<br>• `PLATFORM` refuses workspace-only settings. |
| 2.2 | **Router inventory.** Classify every router in `backend/app/main.py:312-359, 607` and `access_router.py:31-50` as public, auth, ops, workspace, customer-admin or platform.<br>• Split the mixed routers into their tenant part and their platform part, **keeping every URL unchanged**: `ai_settings`, `audit_chain_api`, `tenant_export_api` (including legal hold), `support_api`, `trial/router`, `trial/feedback`, `demo_requests`, the platform endpoints in `access/configuration.py:297-342`.<br>• `main.py` mounts routers by role: `MULTI` mounts all of them (as today); `CELL` mounts no `/platform-admin/*` or `/platform/*` route; `PLATFORM` mounts no workspace route. |
| 2.3 | **Roles at sign-in.** In `CELL`, the platform-admin roles are not accepted anywhere (`authz.py:24-28` today lets `PLATFORM_ADMIN` use every `/admin/*` route). In `PLATFORM`, only platform roles can sign in. |
| 2.4 | **Single-tenant guard in `CELL`:**<br>• Sign-in (`auth_router.py:665-733`) searches only the cell's tenant, so no organization choice is offered.<br>• `request_context.py:209` refuses any session whose tenant is not the cell's tenant.<br>• The cell's data-plane registry row must be the shared marker. |
| 2.5 | **Background jobs by role** (`backend/app/scheduler.py:227-250`):<br>• **Platform:** tenant-lifecycle, subscription-lifecycle, trial-reminders, trial-retention.<br>• **Cell:** embedding-catch-up, connector-sync, signal_detection, late_evidence_sweep, audit-chain-verification, export-expiry, purge-completion, operations-alerts.<br>• **`MULTI`:** all of them, as today.<br>In `CELL`, the "all tenants" loops see only the cell's tenant, and a test asserts it. |
| 2.6 | **Outbox worker in `CELL`:** binds the cell's tenant; report jobs come from the cell database only. |
| 2.7 | **Frontend, still one bundle:**<br>• The role is read from `/public/site-info`.<br>• `navigationPolicy.ts` hides the platform screens in `CELL` and the workspace in `PLATFORM`.<br>• The server remains the authority (2.2). |
| 2.8 | **CI job "Deployment roles":**<br>• Start the API in `CELL` and in `PLATFORM`.<br>• Compare the mounted routes and scheduled jobs with approved snapshots.<br>• Smoke-test sign-in for each role.<br>• `MULTI` keeps running the full existing suite. |

**Exit:** the existing suite is green and unchanged in `MULTI`; the role snapshots and smoke tests are green; in `CELL` zero platform routes respond.
**Rollback:** revert; `MULTI` is unaffected.
**Risk:** splitting mixed routers could change a URL or a permission. Mitigation: the 0.3 route baseline must match exactly in `MULTI`.

### Phase 3: Cell installer, licence, and moving a tenant (L)

**Goal:** create a cell from nothing, license it, and move an existing tenant into it without changing the source.

| Step | Work |
|---|---|
| 3.1 | **Platform registry migration** (md36), used only by `PLATFORM`; stays empty elsewhere:<br>• new table `cells`: tenant, hosting mode, public endpoint, enrollment token hash, client certificate fingerprint, software and schema versions, last heartbeat, status;<br>• new columns on `tenants`: `hosting_mode` and residency region.<br>One Alembic chain serves every role, so there is no fork. |
| 3.2 | **Cell installer** `scripts/cell_install.py`, reusing the steps of the production `migrate` service (`docker-compose.prod.yml:93-122`) and `scripts/migrate_data_planes.py`:<br>1. create the database roles (`mdarix_t_<key>_owner`, `_app`, `_ro`, `_backup`) and the `vector` and `pgcrypto` extensions;<br>2. run `alembic upgrade head`;<br>3. grant the runtime role and set a new RLS system token;<br>4. insert the tenant and customer rows from a signed **enrollment bundle**;<br>5. apply the licence (3.3);<br>6. generate the cell's own keys (MFA, connector, object storage, signing secret);<br>7. verify every business table is empty;<br>8. create the first customer-administrator invitation in the cell. |
| 3.3 | **Licence in the cell.** A signed licence document (plan code, features, seats, status, valid until) is written into the cell's own `plan_definitions`, `feature_entitlements` and `tenant_plan_assignments`. `backend/app/access/plan_features.py` already reads exactly these tables, unchanged.<br>• Licence status SUSPENDED → the cell applies today's suspension behaviour.<br>• Grace and expiry follow D6. |
| 3.4 | **Tenant move tool** `scripts/move_tenant_to_cell.py`:<br>• Source: a `MULTI` deployment (control database, the tenant's dedicated plane if any, the tenant's object-storage prefix), opened **read-only**. Target: a freshly installed cell.<br>• Copies every table with the tenant's rows in foreign-key order (reusing the table discovery in `backend/app/tenant_export.py`), including users, roles, audit, signatures, outbox history, connectors and mappings. Sessions are not copied: users sign in again.<br>• **Re-encrypts** MFA secrets, connector keys and stored files from the source keys to the cell's keys. They are encrypted with global keys today (`auth/totp.py:74-101`, `access_control/connector_secrets.py`, `object_storage/service.py:126-139`).<br>• **Audit chain:** copies events with their hashes and sequence, then runs `mdarix_verify_audit_chain` in the cell. The move fails if the chain does not verify identically.<br>• Advances the business-ID counters past the copied IDs.<br>• Supports a dry run and prints per-table counts for source and target.<br>• Refuses `ACME_CARE_SYNTHETIC` unless the source is a test database.<br>• Marking the source tenant as moved, and deleting its source data later, are separate steps that each need your approval and the customer's sign-off. |
| 3.5 | **Tests:**<br>• a fresh cell has empty business tables;<br>• moving a seeded synthetic tenant gives equal counts per table, a verified audit chain, working MFA codes, decryptable connector keys and readable files;<br>• the source is unchanged;<br>• the cell serves the tenant in `CELL` mode. |

**Exit:** the 3.5 tests are green in CI.
**Rollback:** delete the target cell. The source is never modified.
**Risk:** an incomplete copy (a table without `tenant_id`, or a missed foreign key). Mitigation: the tool fails on any table with tenant-linked rows it does not know about; counts are compared table by table.

### Phase 4: Platform ↔ cell link (L)

**Goal:** the cell calls the platform, outbound only, and sends only metadata. The platform never calls the cell.

| Step | Work |
|---|---|
| 4.1 | **Platform endpoints**, mounted only in `PLATFORM`:<br>• `POST /api/v1/cells/enroll`: one-time token in exchange for a client certificate;<br>• `POST /api/v1/cells/heartbeat`;<br>• `GET /api/v1/cells/packages`;<br>• `GET /api/v1/cells/packages/{id}/content`.<br>Mutual TLS is terminated by the proxy with a platform CA, and the API matches the certificate fingerprint to the `cells` row (D7). |
| 4.2 | **Heartbeat:** a strict schema that refuses unknown fields. It carries only versions, schema revision, job outcomes, counts and error codes, never free text or record values. Test: a heartbeat with an extra field or a text value is refused. |
| 4.3 | **Cell job `platform-sync`** (every 15 minutes): send the heartbeat, fetch offered packages and verify their signatures. The licence is applied automatically; every other package is offered to the customer administrator (adoption in P11). |
| 4.4 | **Signed packages:**<br>• ed25519 signatures; the private key is held by the release pipeline as a CI secret, and the public key is pinned in the cell at install.<br>• Package kinds for MVP: LICENCE, REFERENCE_DATA, MAPPING_TEMPLATE (today's `backend/app/access/standard_mappings.json`), POLICY (AI provider catalog).<br>• Tables: platform `packages`, cell `received_packages` (migration md37).<br>• Unsigned, tampered or incompatible packages are refused. |
| 4.5 | **Software releases:** extend `.github/workflows/release.yml`, which already builds and scans the images, with image signing and an SBOM. The platform offers the version; the cell operator upgrades (runbook in P11). |
| 4.6 | **Platform fleet view:** a console page built from heartbeats (version, health, last contact, job failures). It replaces the tenant-data tabs removed in P5. |
| 4.7 | **Cell resilience:** with the platform unreachable, the cell keeps serving; the licence grace period applies. |

**Exit:** tests for enrollment (wrong or reused token refused), heartbeat schema, signature verification, and offline operation.
**Rollback:** revert; cells keep working without the link (licence applied manually by the installer).

### Phase 5: Platform out of tenant data; customer-approved support (M)

**Goal:** design scenario 7. Platform staff cannot read or change tenant data without a time-limited grant approved by the customer.

| Step | Work |
|---|---|
| 5.1 | **Relocate the platform routes that reach tenant data.** They are not mounted in `PLATFORM` (from the P2 classification); each capability moves to the customer administrator in the cell:<br>• tenant export and purge (`tenant_export_api.py:321-474`);<br>• product configuration read and write (`platform_reference.py:143-360`, per D5);<br>• tenant mappings (`configuration.py:297-342`);<br>• tenant AI settings (`ai_settings.py:140-148`);<br>• audit chain, audit and tenant 360 tabs (`platform_tenants.py:1282-1460`);<br>• customer record tabs (`platform_customers.py:863`);<br>• console integration runs, AI activity, audit and dead letters (`platform_console.py:211-794`);<br>• customer user erasure, MFA reset and activation links (`platform_customer_admins.py:381-469`).<br>The screens already exist for most of these on the customer-admin side; the missing ones are added. |
| 5.2 | **Offboarding:**<br>1. The platform sets the tenant to OFFBOARDING, and the licence carries that to the cell.<br>2. The customer administrator exports.<br>3. The cell operator destroys the cell (database, bucket, keys; destroying the keys makes the backups unreadable).<br>4. The platform archives the record. |
| 5.3 | **Customer-approved support access:**<br>1. A support request (purpose only) is created in the platform and delivered by `platform-sync`.<br>2. The customer administrator approves a scope (read-only), a duration (at most 24 hours) and a named person.<br>3. The cell creates a temporary support account: a read-only role, MFA required, no export, expires automatically.<br>4. Every action is audited with a support tag; the grant can be revoked at any time. |
| 5.4 | **Sole-administrator lockout:** `scripts/cell_recover_admin.py`, run by the cell operator on the cell host and audited. It replaces platform-side MFA resets. |
| 5.5 | **Problem reports from a cell follow D9:** reference, page and error code are sent; free text only with the user's consent. Supplier evidence-request emails contain a link to the cell rather than case content (`stage3_workflow_router.py:475-498`). |

**Exit:**
- In `PLATFORM`, every relocated route returns 404.
- Support access without customer approval is refused and the refusal is audited in the cell.
- An approved grant expires on time.

**Rollback:** revert; `MULTI` keeps today's platform features.

### Phase 6: Per-cell storage, keys, backups and residency (M)

| Step | Work |
|---|---|
| 6.1 | **Per-cell configuration**, generated by the installer:<br>• bucket `mdarix-t-<key>`;<br>• MFA, connector and object-storage keys;<br>• RLS token, SMTP and alert channel.<br>In `CELL`, `config_check` refuses a bucket that does not carry the tenant key and refuses the development default keys. |
| 6.2 | **Key rotation:** add keyrings for the MFA and object-storage keys, as the connector key already has (`docs/runbooks/KEY_ROTATION.md:28-57` lists them as missing). |
| 6.3 | **Backups per cell:**<br>• `infrastructure/docker/backup/backup.sh` in `CELL` mode backs up only the cell database and the cell bucket, to the cell's own target, encrypted for the cell's recipient.<br>• Point-in-time recovery: WAL archiving with pgBackRest for a self-hosted database, or the managed service's PITR, documented.<br>• `restore.sh` restores a cell.<br>• CI: back up a cell, restore it into a new one, and verify counts and the audit chain. |
| 6.4 | **Residency:** `MDARIX_CELL_REGION` is checked at startup against the declared database region, the storage region and the AI provider's region from the catalog. A mismatch refuses to start (today regions are stored but never checked, `foundation.py:61-68`). |

**Exit:** cell backup and restore pass in CI; residency refusal tests pass.
**Rollback:** revert; `MULTI` backups are unchanged.

### Phase 7: Two-cell proof and isolation suite in CI (M)

| Step | Work |
|---|---|
| 7.1 | **`docker-compose.cells.yml`:**<br>• `platform-api` and `platform-db`;<br>• `cell-a` and `cell-b`, each with api, worker, scheduler, its own PostgreSQL instance and its own MinIO;<br>• internal networks per cell, plus a control egress network;<br>• simulators per cell: A uses TrackWise-, Teamcenter- and SAP-like; B uses Veeva-, Windchill- and Oracle-like.<br>Each cell is installed with the P3 installer and enrolled through P4. |
| 7.2 | **`tests/cells/` isolation suite.** Network probes run inside the containers (for example, from `cell-a-api` to `cell-b-db` must fail), so the test runner itself does not bridge the networks. |
| 7.3 | **New CI job "Two-cell isolation"** on Linux. |

**Scenarios proven here** (the full list is in section 6): 1, 2, 4, 5, 6, 7, 9 and 12 in full. Scenario 3 is proven partly (today's connector, full sync, no custom fields), and scenario 8 with a stub AI endpoint inside the cell network.

**Exit, which is GATE A:** the suite is green in CI. Design-partner demonstrations with synthetic data may start.

### Phase 8: Integration in the cell (L)

| Step | Work |
|---|---|
| 8.1 | **One mapping and validation engine.** Today there are four engines with three sets of transform codes: `integration/gateway.py:130-178`, `connector_mapping.check_mapping` (`:250-291`), the catalog dry-run and validate (`mapping_catalog_router.py:266-386`), and the import checks (`trial/imports.py`).<br>• One engine with one set of codes; the others become thin wrappers.<br>• Mapping suggestions return a code the engine accepts (today `"DIRECT"`, `:564-592`). |
| 8.2 | **Mapping governance:**<br>• a trigger freezes rules once APPROVED;<br>• PROMOTE supersedes the previously released version;<br>• the connector's pinned `mapping_version` is honoured (`connector_mapping.py:68-83` takes the newest instead);<br>• reject, version diff, and export or import of the approved mapping specification. |
| 8.3 | **Incremental sync:**<br>• a watermark per connection and object (new table);<br>• `since` and delta requests, plus delete and tombstone handling;<br>• the simulators gain paging and `since` (today they return everything, `source_simulator/persistent_app.py:204-212`). |
| 8.4 | **Per-record quarantine:**<br>• rejected rows are stored with their reasons in a quarantine table, building on the import-options "skip" path, instead of the whole batch failing;<br>• chunked, resumable loads beyond the 50,000-row single batch;<br>• reconciliation written per run;<br>• `run_id`, `mapping_version` and `source_version` recorded on imported rows (new nullable columns). |
| 8.5 | **Operations:**<br>• the sync schedule can be set in the UI;<br>• one failing connection no longer stops the scheduler cycle;<br>• the `CONNECTOR_EXECUTED` audit is tested. |
| 8.6 | **Adapters:**<br>• OAuth2 client credentials (TrackWise Digital on Salesforce);<br>• OData paging (SAP S/4HANA);<br>• configurable response and paging formats;<br>• a reply without the expected key fails instead of "succeeding" with zero records. |
| 8.7 | **Tests:** live sync over HTTP from the simulators into both cells (initial load, changed records, deleted records, a bad record quarantined, no duplicates, reconciliation MATCH). Vendor-sandbox contract tests come later (P12 or after). |

**Exit:** 8.7 is green in the two-cell CI job.

### Phase 9: Custom fields (M)

1. **Migration:**
   - an `extensions` JSONB column (default `{}`, with a GIN index) on complaints, products, components, suppliers, sites, lots, investigations, CAPAs and evidence;
   - a `custom_field_definitions` table (entity, key, label, type, value set, required, validation, classification, version, status).
2. **APIs and customer-admin screens** to add, version and deactivate a field, with a usage check before deactivation.
3. **The P8 engine validates extension values.** Mappings can target custom fields, and imports accept defined custom fields (today unknown fields are refused).
4. **Display:** fields appear in record details and list filters; field visibility is set per role; fields are included in exports.
5. **Tests:** Tenant A and Tenant B define different fields; each cell sees only its own.

**Exit:** design scenario 3 is complete.

### Phase 10: AI policy per cell (M)

1. **AI is configured per cell.** Each cell has its own `MDARIX_GENAI_*` settings, so per-tenant provider configuration comes from the deployment itself (today it is process-wide, `genai/provider.py:194-200`).
2. **Policy modes:**
   - OFF: today's default;
   - LOCAL_MODEL: Ollama inside the cell;
   - CUSTOMER_ENDPOINT: a base URL in the customer's own cloud account;
   - MDARIX_CONTRACTED: today's allowlist, with zero-retention terms and consent.
   The mode is shown to the customer administrator. The existing switch, budget and acknowledgement remain (`backend/app/ai_settings.py`, `genai/governance.py:112-139`).
3. **Region check:** the provider's region must match the cell's region (P6.4). Masking (`genai/pii.py`) stays on.
4. **Tests:** an egress capture in the two-cell environment shows no AI traffic leaving `cell_a_net` in LOCAL_MODEL mode; a refused provider is audited; AI runs are stored only in the cell.

**Exit:** design scenario 8 is complete.

### Phase 11: Reference packages, upgrades and restore drill (M)

1. **Reference-data adoption:**
   - for an offered REFERENCE_DATA package, the cell produces an impact report listing the mappings, custom fields and rules that use changed or deprecated items;
   - the customer administrator adopts it, and it is applied in one transaction to the cell's `md_master` tables;
   - the previous version is kept for rollback.

   Within a major version, packages may only add or deprecate. Import checks that are hard-coded today (`trial/imports.py:61-158`) stay hard-coded for MVP; moving them to data-driven checks is later work.
2. **Upgrades:**
   - runbook: take a pre-upgrade backup, upgrade the cell, migrate, smoke-test, and roll back with the backup if needed;
   - CI test: the platform at version N works with cells at N and N+1;
   - review rule: migrations follow expand-then-contract.
3. **Restore drill:** CI restores a cell to a point in time after a simulated corruption. The drill on real infrastructure is user-owned and its result is recorded.

**Exit:** design scenarios 10 and 11 are green; drill recorded.

### Phase 12: Readiness and cutover (M)

1. **External penetration test** of the two-cell topology, with no open high findings.
2. **Validation package draft:** requirements, risk analysis, IQ/OQ protocols and traceability to the tests.
3. **Contracts (user-owned):** DPA, sub-processors and legal review.
4. **Cutover:**
   - move the pilot and demo tenants into cells with the P3 tool, one at a time, each with your approval;
   - keep `MULTI` only for development, CI and the trial sandbox (D4).
5. **Documentation:** update the pilot guide, STATUS and the architecture documents.
6. **Later "contract" release:** remove the dedicated data-plane routing code once no tenant uses it.

**Exit, which is GATE B:** the first real customer data may be loaded into a customer's cell.

---

## 6. The 12 proof-of-concept scenarios: where each is proven

| # | Scenario | Phase proven | Automated test |
|---|---|---|---|
| 1 | Independent provisioning | P3, P7 | `tests/cells/test_provisioning.py` |
| 2 | Empty start | P3, P7 | `tests/cells/test_empty_start.py` |
| 3 | Ingestion with own mapping and custom fields | P7 (partial), P8, P9 | `tests/cells/test_ingestion.py` |
| 4 | Same application in both cells | P7 | Smoke suite against both cells, same image digest |
| 5 | Admin scope | P2, P7 | Route inventory with Tenant A's token against Tenant B |
| 6 | Cross-tenant access | P7 | Network, database-credential, token and RLS probes |
| 7 | Platform staff cannot read tenant data | P5, P7 | `tests/cells/test_platform_reach.py` |
| 8 | AI inside the boundary | P7 (stub), P10 | Egress capture |
| 9 | AI output and reports stay in the cell | P7 | Storage and platform-database assertions |
| 10 | Safe standard update | P11 | Package impact, adoption and rollback |
| 11 | Backup, restore, migration, rollback | P6, P11 | Restore and N/N+1 tests |
| 12 | Auditing | P7 | Events per cell; chain verifies |

---

## 7. Risks and how the plan handles them

| Risk | Mitigation |
|---|---|
| Something breaks for today's users | `MULTI` is the default and unchanged; the full existing suite must pass in every phase; route baseline from P0 |
| A tenant is copied incompletely into a cell | The move tool is read-only on the source, refuses unknown tenant tables, compares counts per table, verifies the audit chain, and needs a dry run first |
| Encrypted data unreadable after a move | Explicit re-encryption step with tests for MFA, connector keys and files |
| A user with accounts in two organizations | In cells, each organization has its own address and sign-in; documented for users |
| Version skew across many cells | Expand-then-contract migrations; N/N+1 CI test; platform offers versions, cells pin them |
| Package supply-chain attack | Signed packages and images; pinned public key; refusal tests |
| CI time grows | The two-cell job runs in parallel with the existing jobs; scenarios share one environment |
| Scope creep before GATE A | P8-P11 features are not started until P7 is green (except fixes) |
| Cost per tenant | Small default cell (one VM); the trial sandbox stays shared (D4) |

---

## 8. Not in MVP 1.0

- SSO through the customer's identity provider (OIDC/SAML).
- Record-level and field-level permission policies beyond custom-field visibility.
- Vendor-sandbox certification for every connector.
- On-premises cells with offline package import.
- Kubernetes.
- Data-driven import checks from reference packages.
- Opt-in cross-tenant benchmarks.

---

## 9. Corrections to the design document found while planning

These should be applied to `MDARIX_TARGET_ARCHITECTURE_DESIGN.md` once you approve this plan:

1. **Section 5 (tenant schemas `iam`, `cfg`, `integ`, `ai`, `audit`, `files`).** For MVP, keep all existing tables in `public` and add new tables there with clear names. The schema names are a logical grouping, not a database move. Moving tables would create rework and risk with no benefit.
2. **Sections 13 and 14 ("move signatures, users, sessions and configuration into the tenant database").** This is achieved by the single-database cell (D2), not by re-routing tables. The phase sizes change accordingly.
3. **Section 13 gap table additions:**
   - a support-grant requester is not recorded;
   - platform staff can erase customer users and reset their MFA;
   - there are four separate validation engines;
   - the embedding model can download unverified from the network;
   - audit-chain verification covers only the control database;
   - business-ID counters are per database.
4. **Section 14 phase numbering** is replaced by this plan (mapping in section 4).
