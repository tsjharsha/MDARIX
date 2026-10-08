# MDARIX MVP 1.0: production database architecture and tenant transactional database review

| | |
|---|---|
| Date | 2026-10-08 |
| Code reviewed | `main` at `c57e2d9` (PR #2 merged), plus the unmerged branches `mvp/docs-refresh`, `mvp/import-options`, `mvp/p2-hardening` |
| Method | Four independent read-only reviews of the code, database migrations, deployment configuration and tests (tenant databases; integration layer; data residency; test and CI evidence), then a direct re-check of the findings that decide the outcome. Nothing is rated on documentation or plans alone. |
| Evidence base | The CI run that merged PR #2 (17 of 17 checks green: 2,477 backend, 558 frontend and 56 browser tests passed; dedicated tenant database, four-database routing, production stack and image scan jobs green) |

Status used for every capability:

- **Implemented**: code exists and an automated test proves it.
- **Partially implemented**: code exists but is incomplete, or not tested for this purpose.
- **Not implemented**: needs new development.
- **Architectural change required**: the current design has to change, not just grow.
- **Not verified**: no evidence either way.

## 1. Decision

**NO-GO for MVP 1.0 under the customer-hosted Tenant Transactional Database model.**

MDARIX is a sound multi-tenant application, and part of the target model already exists: each customer *can* be given its own database, the application routes almost every business record to it, the schema is migrated and checked, and a dedicated database is exported and purged correctly (all tested in CI). But the model as specified (database in the customer's infrastructure, owned by the customer, no customer transactional data permanently stored by MDARIX) is not what the product does today:

1. **Every customer's data is in MDARIX's own database by default.** A new customer is placed on the "shared plane", which is the MDARIX control database, separated by row-level security. No production path creates or registers a dedicated database; it is a manual registry edit.
2. **Even with a dedicated database, customer data still reaches MDARIX infrastructure:** decision signatures with their written rationale and some audit reasons are written to the MDARIX control database; evidence attachments, generated reports and export archives go to one MDARIX-managed file store; MDARIX's backup job dumps every dedicated database into MDARIX backups and an MDARIX bucket.
3. **MDARIX owns the dedicated database rather than the customer:** it needs owner-level credentials (create roles, install the `vector` extension, manage triggers) and runs schema migrations against it on every deployment. There is no customer-side agent or gateway; the only connection is a direct database connection from MDARIX.
4. **The integration layer is a generic connector proven only against simulators.** There are no TrackWise Digital, PLM or SAP clients (no SAP OData, RFC or IDoc), authentication is a single static API key, every sync re-reads everything (no incremental sync, no deletes), and no test pulls data from a running source system.
5. **The mandatory end-to-end scenario has never been run as one chain,** and "no prohibited customer data in MDARIX infrastructure" is untested (and, per points 1 and 2, currently untrue).

**This does not need a rewrite.** The data model is the same in the shared and dedicated databases, routing to a dedicated database already covers products, complaints, investigations, evidence and embeddings, signals, tasks, reviews, briefs, decisions, follow-ups and AI runs, and isolation, export and purge work per tenant. What is needed is targeted architectural change in five places (section 6) plus real connectors and incremental sync.

**What can go ahead now:** design-partner pilots and demonstrations on the current MDARIX-hosted model (shared database with forced row-level security), provided the agreement and privacy terms say that MDARIX hosts the data. That is a business and legal decision, not a technical one; it should not be presented as the customer-hosted model.

## 2. Current state vs target production architecture

| Layer | Target (as specified) | Current state (verified in code) | Status |
|---|---|---|---|
| Customer applications | TrackWise Digital, PLM, SAP and others stay in the customer environment | Same; MDARIX reads them over HTTP. In tests only simulators exist (14 defined, 8 started in CI, SAP not started) | Partially implemented |
| Integration layer | Connectors, APIs, mapping, validation, transformation, incremental sync, error handling, traceability | One generic REST/JSON pull connector configured per connection; mappings with two-person release; all-or-nothing validated import; full re-read on every sync; retries and failure runs; limited reconciliation and lineage | Partially implemented |
| Tenant transactional database | Dedicated per customer, in the customer's approved infrastructure, owned by the customer | Dedicated databases supported and tested, but **default is the MDARIX control database**; dedicated ones are created, migrated, backed up and administered by MDARIX with owner credentials | Architectural change required |
| Connectivity MDARIX ↔ tenant database | Secure, approved network path, authenticated access | Direct PostgreSQL connection from the MDARIX API/worker/scheduler; one global TLS setting and CA bundle for all databases; no client certificates, no connection or statement timeouts; never tested across a network boundary | Partially implemented / Not verified |
| MDARIX application services | Read and process tenant data in place | Most domains read and write the tenant database; some screens and reports read only the control database and miss dedicated-database data; signatures are written to the control database first, the decision to the tenant database second, with no cross-database transaction | Partially implemented |
| Files (evidence, attachments, reports, exports) | In the customer's environment | One MDARIX-managed object store (one bucket or VM volume, one key, one region) | Architectural change required |
| Backups and recovery | Per the data-residency policy | MDARIX dumps the control database **and every dedicated database** plus all files into MDARIX storage (14 days local, 90 days off-site) | Architectural change required |
| AI processing | Transfers comply with residency | Masking, contracted-provider allowlist with zero-retention flag, per-organization switch and budget; provider endpoints are global; tenant AI region never checked | Partially implemented |
| Logs, error reporting, email | Comply with residency | Secrets redacted; but tenant-database errors can include record values (no `hide_parameters`), Sentry sends exception text and local variables, Caddy logs search terms, some emails carry case content via MDARIX's SMTP | Partially implemented |

## 3. The twelve questions

| # | Question | Status | Evidence (code and tests) | Gap and proposed change |
|---|---|---|---|---|
| 1 | Does the database structure match the target? | **Architectural change required** | Control + per-tenant "data plane" design: `backend/app/db/data_plane.py`, `tenant_data_planes` registry (`backend/app/db/models/customer_lifecycle.py:93-120`). Default shared plane = control database (`data_plane.py:23-26, 81-83`; trigger in migration `md20_default_data_plane.py:21-50`; `customer_lifecycle.py:234-256`) | Make a dedicated, customer-hosted database the production model and move the items in Q10 out of MDARIX storage |
| 2 | Separate tenant database per customer? | **Partially implemented** | Routing, schema gate, export and purge on a dedicated database verified in CI (`tests/test_dedicated_plane.py`, job "Dedicated data plane": 4 passed; job "Data-plane routing (four tenant databases)": 4 passed) | No production API or script to register, verify and migrate a customer's database (only `scripts/register_mvp_data_planes.py`, hard-coded to four test tenants; the test edits the registry row directly). No move of an existing tenant from shared to dedicated. Engine cache holds 32 databases |
| 3 | Can it be deployed inside the customer's infrastructure? | **Architectural change required** | Any database URL is accepted (`data_plane.py:29-54`). Migrations run by MDARIX's migrate job with the database owner's credentials on every deployment (`docker-compose.prod.yml:93-115`, `scripts/migrate_data_planes.py:158-184`); they need CREATEROLE, `CREATE EXTENSION vector/pgcrypto`, trigger control | Customer-run or least-privilege migration (signed migration bundle the customer's DBA applies, or a pre-provisioned schema owner without superuser rights); documented prerequisites (pgvector); runtime role login on the tenant database (today never given one: `migrate_data_planes.py:142-155`; tests run as superuser); RLS system token propagated to tenant databases on rotation (`scripts/set_rls_system_token.py` updates only the control database) |
| 4 | Secure connection from central MDARIX to a customer-hosted database? | **Partially implemented / Not verified** | TLS settings shared with the control database (`backend/app/db/tls.py:19-46`); production requires `verify-full` but only on the global setting (`config_check.py:173-186`); two scripts connect without TLS (`scripts/upgrade_data_planes.py:291`, `scripts/initialize_data_planes.py:94`) | Per-tenant TLS (own CA, `verify-full`), optional client certificates (mTLS), connect and statement timeouts, plane URL validation, private connectivity (VPN or private link) or a customer-side gateway; a test against a database reached through a separate network |
| 5 | Does a new tenant database start without transactional records? | **Implemented in code, Not verified** | `migrate()` creates the full schema, row-level security, triggers, master/reference data (`md_master`), business-ID counters and copies only the customer and tenant rows (`migrate_data_planes.py:99-130, 158-184`); test checks policies, triggers and the tenant row (`tests/test_dedicated_plane.py:100-106`) | Add a test asserting every business table is empty after provisioning |
| 6 | Connections to TrackWise Digital, PLM, SAP and others implemented? | **Not implemented** (for real systems) / Partially (generic) | One generic HTTP connector: `GET {endpoint}/{records_path}`, expects `{"records": [...], "next"}` (`backend/app/access/connector_sync.py:87-136`); auth is one static key sent as Bearer and `X-Provider-Token` (`:102-105`). Simulators for TrackWise, Veeva QMS, Teamcenter, Windchill, SAP S/4HANA, Oracle ERP, Coupa, Salesforce, MES, LIMS (`docker-compose.yml`, all one app `source_simulator/persistent_app.py`). No OData, RFC or IDoc anywhere | Auth adapters (OAuth2 client credentials/JWT for TrackWise Digital on Salesforce, Teamcenter/Windchill session/CSRF, SAP OData with CSRF token), response and paging adapters (`d.results`, `value`, `@odata.nextLink`, `nextRecordsUrl`), vendor object models; contract tests against vendor sandboxes. Note: a reply without a `records` key currently "succeeds" with zero records |
| 7 | Mapping from source systems to tenant tables implemented? | **Partially implemented** | Field rules with filters, defaults and simple conversions (`backend/app/access/connector_mapping.py`); versioned; request → second-administrator approval → release, with audit (`backend/app/access/configuration.py:988-1113`); 39 standard mappings all pass the release check (`tests/test_standard_mappings.py`) | **Security gap:** the generic edit route can set a mapping to RELEASED or change a released mapping's rules without the second approval (`configuration.py:603-607, 693-694`; the governed-status check exists only on the status endpoint, `:923`). No approved mapping document to export or import; targets limited to 17 fixed entities (no custom tables or fields); no value maps or lookups; mapping version not recorded on runs or rows |
| 8 | Does data flow automatically after configuration? | **Partially implemented** | Scheduler job every 15 minutes syncs active connections with a released mapping when `sync_every_minutes` is set (`connector_sync.py:268-312`, `backend/app/scheduler.py:159-162`); imports go to the tenant's database session (`connector_sync.py:165-184`) | `sync_every_minutes` cannot be set in the UI; no webhook; no test syncs from a running source into a dedicated database (scheduled sync tested with a faked HTTP layer and no mapping, `tests/test_connector_sync.py:108-152`); one failing tenant can stop the rest of a scheduler cycle |
| 9 | Incremental sync, error handling, reconciliation and audit? | **Incremental: Not implemented. Others: Partially implemented** | No watermark, `since` or delta token (`connector_sync.py`; the gateway's `read_incremental` ignores its watermark, `integration/gateway.py:81-82`). Page retries with backoff and Retry-After (`connector_sync.py:58-84`, tested); failed runs recorded and administrators emailed once per outage (tested); run counts and a MATCH/MISMATCH status | Watermarks and delete handling; chunked loads beyond the 50,000-row / 50 MB single batch; per-record quarantine instead of all-or-nothing; reconciliation against source totals (the Reconciliation tab reads a table sync never writes); run ID, source version and mapping version on each imported row; `CONNECTOR_EXECUTED` audit untested |
| 10 | Does the implementation prevent customer data being stored in MDARIX infrastructure? | **Not implemented / Architectural change required** | See section 4 | See section 6, changes A-C |
| 11 | Isolation, authentication, authorization, encryption, backups, recovery adequate? | **Isolation, authentication, authorization: Implemented. Encryption: Partially. Backup/recovery: Architectural change required for this model** | Forced row-level security on every organization table with a CI coverage test (`tests/test_rls_coverage.py`, migration md34), cross-tenant route tests, MFA, session controls, permission checks per action (all in CI). Connector keys and stored files encrypted (one global key each). Backup and restore proven in CI for the MDARIX-hosted stack | Backups copy customer databases into MDARIX storage; no point-in-time recovery for tenant databases (docs promise it, code only runs `pg_dump`); restore drill not yet done on real infrastructure; per-tenant keys and regions |
| 12 | Multiple customers with different applications, schemas and integrations without code changes? | **Partially implemented** | Connectors, mappings, keys and schedules are per tenant configuration; a dedicated database is added by configuration (registry row, URL in environment, restart, migrate) | Steps are manual (registry edit, environment files, restart, manual role login); customers cannot map to their own tables or fields; MES/LIMS/risk-file sources exist only as simulators |

## 4. Where customer data is stored or sent outside the tenant database today

Ranked by severity. "Shared plane" tenants (every tenant today) have *all* of their data in the MDARIX control database; the rows below apply even to a tenant with a dedicated database.

| Severity | What | Where | Evidence |
|---|---|---|---|
| Critical | All business records of shared-plane tenants (the default) | MDARIX control database and its managed point-in-time recovery | `data_plane.py:81-83, 196-200`; `md20_default_data_plane.py` |
| Critical | Full copies of every dedicated tenant database, plus all stored files | MDARIX backup volume and backup bucket (one key, no tenant region) | `infrastructure/docker/backup/backup.sh:129-160` |
| High | Evidence and attachment files, generated reports (never expire), tenant export archives (7 days, then old bucket versions) | One MDARIX object store (`object_storage/service.py:26-52`; default region `us-east-1`) | `evidence_workflow/requests.py:945-951`; `reports/service.py:427-440`; `tenant_export.py:341-348` |
| High | Decision signatures with their written rationale; legacy decision context snapshots; audit reasons for signatures, regulatory documents and risk reviews | MDARIX control database | `human_decision/router.py:866-908`; `governance_router.py:643-692`; `risk_router.py:199-209`; `regulatory_router.py:180-198` |
| High | No residency enforcement: tenant region fields are stored but never checked for the database, files, backups or AI provider; AI providers are called at global endpoints | — | `foundation.py:61-68` (fields); `genai/policy.py:65-76`, `genai/provider.py:22-35` |
| Medium | Record values in errors: tenant-database engine lacks `hide_parameters`; Sentry sends exception text, local variables and breadcrumbs; Caddy logs search terms; outbox errors go to the alert webhook | MDARIX logs, Sentry, alert channel | `data_plane.py:155-162`; `logging_setup.py:81-106`; `infrastructure/docker/Caddyfile:72-84`; `outbox/worker.py:41-45` |
| Medium | Free text that can quote customer data: client error reports, support problem reports (also emailed to MDARIX support), supplier evidence-request emails | MDARIX control database and MDARIX's SMTP provider | `client_errors.py:93-118`; `support_api.py:105-210`; `stage3_workflow_router.py:475-498` |
| Low | Validation-only ingestion path puts full source records in the control-database outbox; unused file-retention setting; legacy reports volume neither purged nor backed up | MDARIX control database / VM | `integration/simulator_ingestion.py:103-117, 219-235`; `object_storage/service.py:33`; `reports/service.py:472-491` |

Already compliant (verified in code): embeddings are computed locally (no text leaves; model baked into the image), chunks and embeddings live in the tenant database, AI run inputs and outputs live in the tenant database, connector runs in the control database hold counts only, case and risk exports are streamed and not stored, temporary files are in memory, and browser storage holds UI preferences only.

## 5. Mandatory end-to-end scenario: what is proven today

No single test or CI job chains the nine steps. The pieces:

| Step | Coverage | Evidence | Runs in CI |
|---|---|---|---|
| 1. Provision a customer tenant | **Full** | `tests/test_customer_tenant_admin_workflows.py` (wizard, seven provisioning steps, audit), `tests/test_platform_customer_tenants.py` | Yes, passed |
| 2. Empty tenant database in a simulated customer environment | **Partial** | `tests/test_dedicated_plane.py` migrates a separate database (CI service container) after editing the registry row directly; four tenant databases registered and migrated by script in the routing job | Yes, passed |
| 3. Connect TrackWise, PLM and SAP simulators | **Not covered** | CI starts eight simulators and checks four ports only; no test makes MDARIX call a running simulator; the SAP simulator is never started | Port check only |
| 4. Configure approved mappings | **Full** (on the shared database) | `tests/test_standard_mappings.py`, `tests/test_data_import_path.py` (two-person release), `tests/test_trackwise_integration_path.py` | Yes, passed |
| 5. Initial ingestion and incremental sync | **Initial: partial (records pushed in the request); incremental: not covered (not implemented)** | `tests/test_trackwise_integration_path.py:89`, `tests/test_connector_sync.py` (faked transport) | Yes |
| 6. Mapped data stored in the tenant database | **Partial** | A product written through the API lands only in the dedicated database (`tests/test_dedicated_plane.py:82-97`); connector imports are tested only on the shared database | Yes |
| 7. Workflows and analytics on the synchronized data | **Partial** | Routing tests read seeded rows on a dedicated database; the 25 workflow scenarios run on directly inserted data on the shared database | Yes |
| 8. Isolation, residency, auditability, sync integrity | **Isolation full; residency not covered; audit and integrity partial** | Cross-tenant and row-level security suites; no residency test; `CONNECTOR_EXECUTED` audit not asserted | Yes (isolation) |
| 9. No prohibited customer data in MDARIX infrastructure | **Not covered (and currently untrue)** | One test checks a single product is absent from the control database | — |

## 6. Remediation plan

Grouped by what it changes. Sizes are relative (S days, M one to three weeks, L more) and are estimates, not commitments.

**A. Keep customer data out of MDARIX storage (architectural, L)**
1. Store decision signatures, context snapshots and the reason text of audit events in the tenant database; keep only identifiers and hashes in the control database. Replace the two separate commits when signing with an outbox or compensation so the two databases cannot disagree.
2. Per-tenant object storage in the customer's environment (customer-owned bucket and keys, or files stored in the tenant database); reports and exports written there; enforce the retention setting.
3. Backups by deployment model: for customer-hosted tenants MDARIX backs up only its control database, and the customer backs up (with point-in-time recovery) its own database; remove tenant databases from MDARIX's backup job for that model.
4. Enforce residency: check the tenant's regions when connecting a database, storing a file, backing up and choosing an AI provider; per-tenant AI provider and region; `hide_parameters` on tenant engines; scrub Sentry and logs of record content; drop query strings from proxy logs.

**B. Make the tenant database customer-owned (architectural, M-L)**
1. A provisioning API and screen to register a customer database, verify connectivity, TLS and schema, run or hand over the migration, and confirm it is empty.
2. A migration path the customer controls (versioned bundle applied by the customer's DBA, or a non-superuser schema owner), documented prerequisites (PostgreSQL version, pgvector), and a least-privilege runtime login created and tested under row-level security.
3. Per-tenant TLS (CA, `verify-full`), optional client certificates, timeouts, URL validation; private connectivity (VPN or private link), or a lightweight customer-side gateway if direct database access is not acceptable to customers.
4. Move an existing tenant from the shared to a dedicated database; RLS system token propagated to tenant databases; fix the screens that read only the control database; report an unreachable database as unreachable, not as "schema outdated"; bind the tenant in the outbox worker's database session.

**C. Integration layer (M-L)**
1. Quick security fix first (S): close the generic edit route for mappings (governed statuses and released rules only through the approval flow), with a test.
2. Incremental sync (watermark per connection, `since`/delta requests, delete and tombstone handling) in the connector and in the simulators.
3. Chunked, resumable loads; per-record quarantine with stored rejects; reconciliation against source totals written to the reconciliation table; run ID, source version and mapping version on each row; schedule settable in the UI; per-connection error isolation in the scheduler.
4. Connector adapters: OAuth2/JWT, session/CSRF, SAP OData; configurable response and paging formats; then vendor-sandbox contract tests for TrackWise Digital, one PLM (Teamcenter or Windchill) and SAP S/4HANA.
5. Mapping governance: export and import of the approved mapping specification; pin the mapping version used; supersede older released versions; value maps and lookups.

**D. Prove it end to end (M)**
1. A CI job for the mandatory scenario: provision a tenant through the API; register and migrate a dedicated database on a separate network; start the TrackWise, Teamcenter (or Windchill) and SAP simulators; load and release the standard mappings with two administrators; run an initial and an incremental sync over HTTP; assert the records are in the tenant database and none are in the control database or MDARIX file storage; run the six-role workflow (signal, case, brief, signed decision) and analytics on that data; check isolation against a second dedicated tenant, the audit chain, and residency.
2. Supporting tests: tenant database empty after provisioning; outbox and control database hold no record content; residency refusals; re-sync with changed and new records (no duplicates, reconciliation MATCH).

**Minimum to demonstrate one end-to-end customer integration:** B1, B2 (runtime login), B3 (TLS and timeouts), A1, A2, A3 for the demo tenant, C1, C2, D1. With simulators this proves the architecture; contract tests against real vendor sandboxes (C4) are additionally needed before a customer goes live.

## 7. What already works and should be kept

- Per-tenant database routing for nearly every business domain, with a schema-version gate, tested on separate databases in CI.
- One schema for shared and dedicated databases, so moving to dedicated databases needs no data-model rewrite.
- Forced row-level security on every organization table (md34), enforced by a CI coverage test; cross-tenant route tests; least-privilege runtime role on the control database.
- Per-tenant export (including the dedicated database) and staged purge with legal hold.
- Connector security: encrypted, tenant-bound API keys with rotation; SSRF protection with DNS-rebinding checks; same-host paging; retries with backoff.
- Mapping release with second-administrator approval (via the approval flow) and 39 standard mappings that pass the release check.
- AI governance: masking, contracted-provider allowlist with zero-retention requirement, per-organization switch and budget, local embeddings.

## 8. Exit criteria to change the decision to GO

1. The CI job in D1 is green, including the "no customer data in MDARIX storage" assertions.
2. A tenant can be provisioned onto a customer-hosted database through the product (no manual registry edits), with the customer running its own migrations and backups.
3. Signatures, audit reasons, files, reports and exports for that tenant stay in the customer's environment; MDARIX backups exclude it.
4. Incremental sync and per-record quarantine are implemented and tested; the mapping edit-route gap is closed.
5. Residency settings are enforced for the database, files, backups and AI provider.
6. A restore drill has been run against a real customer-style database, and the result recorded.

## 9. Extension: data mapping enforcement, custom fields and Customer Administrator configuration

Additional review (same method: two further read-only code reviews, then a direct re-check of the deciding findings).

### 9.1 Answer to the expected outcome

**Partly.** MDARIX already provides configuration-driven, administrator-managed mapping *for the standard data model*: a customer administrator can build a mapping in a three-step form, start from one of 39 standard templates, have it checked, and release it through a two-person approval, with no developer code per onboarding, **as long as the source data fits MDARIX's 17 fixed target entities**. It does **not** provide customer custom fields, live schema discovery that is stored and monitored, AI-assisted mapping, validation of a mapping against sample data through the real import checks, or execution of mappings by a customer-side service. Mapping runs only inside MDARIX.

All of these are achievable with the split deployment, without moving customer transactional data into MDARIX, using the design in 9.6: **MDARIX governs and publishes mapping and field definitions; a customer-side integration service executes them.**

### 9.2 Section 10: platform-controlled mapping across environments

| # | Question | Current status | Feasible with the split model? | Evidence and gap |
|---|---|---|---|---|
| 10.1 | Centrally define, validate and enforce mapping rules while data stays in the customer environment | **Partially implemented** | Yes | Definitions and the structural check are central: `mapping_configurations` in the control database, `check_mapping` (`backend/app/access/connector_mapping.py:250-291`) at save and at release (`backend/app/access/configuration.py:1068-1081`), tested. Enforcement on data happens in MDARIX's own process, not in the customer environment |
| 10.2 | How the integration layer gets central mapping definitions and applies them in the customer environment | **Not implemented** | Yes, with a customer-side service | Mappings are read and executed only by MDARIX's API and scheduler (`connector_sync.py:165-184, 268-312`). No customer-side service, no mapping export or package format |
| 10.3 | Enforce mandatory fields, types, relationships, validation and referential integrity without moving data to MDARIX | **Partially implemented** | Yes | Mandatory columns, identifier and date formats, Y/N flags, lengths, complaint status, personal data, duplicates and in-tenant references are checked in `backend/app/trial/imports.py:378-542` against the tenant database session, tested. But the checks run in MDARIX, are hard-coded, and the central validation rules, data-quality rules and value sets in `md_master` are **never applied** (display only) |
| 10.4 | Propagate changes to master data, reference values and mapping standards to tenants | **Partially implemented** | Yes | Only by new code releases: master data is seeded by migrations (`md02`, `md11`) and copied to dedicated databases when they are migrated (`scripts/migrate_data_planes.py:158-184`); the dedicated database's copy is never read. Standard mappings are a JSON file shipped with the code. Tenant mappings are not re-based when a standard changes (`/platform-admin/mapping-impact` returns `silent_propagation: False`) |
| 10.5 | Architecture for reliable execution, version control, security and synchronization between central configuration and customer data | **Partially implemented** | Yes | Versions, a two-person release and audit exist. Missing: content freeze after approval (the generic edit route can change a released mapping's rules or status: `configuration.py:603-607, 693-701`), version pinning at run time (the most recently updated released version of a code is used: `connector_mapping.py:68-83`), signed or hashed packages, and a channel to a customer-side runner |
| 10.6 | Implemented today? | **Partially implemented** | — | Central definition, check and release: yes. Customer-side execution, central rule enforcement, controlled propagation: no |

### 9.3 Section 11: customer-specific custom fields

| # | Question | Current status | Evidence and gap |
|---|---|---|---|
| 11.1 | Fields not in the standard TrackWise, PLM or SAP model | **Not implemented** | Every business table has fixed columns (`backend/app/db/models/foundation.py:125-414`); no extension or attribute column, no field-definition table per tenant. Imports refuse unknown columns (`imports.py:346-350, 553-555`; tests `test_free_trial.py:190-193`, `test_trackwise_integration_path.py:61-71`) |
| 11.2 | Created and managed in the Customer Administrator interface | **Not implemented** | No screen or API writes field definitions; the platform "Data model" screen is read-only (`frontend/src/features/admin/areas/DataConfiguration.tsx:64-156`) |
| 11.3 | Name, type, description, default, mandatory, validation, mapping | **Not implemented** | The central `md_master.canonical_field_definition` has type and required, but no default, no description and no validation link (the API hard-codes `"validation_rule": None`, `backend/app/master_data/catalog.py:245`), and it is global, platform-owned and read-only |
| 11.4 | Extend the tenant data model without core code changes | **Not implemented** | No runtime DDL; dedicated databases must match the code's schema exactly or are refused (`data_plane.py:124-148`), and the CI schema-drift check fails on any extra column |
| 11.5 | Same standard model with per-customer extensions and isolation | **Not implemented** (isolation of what exists: implemented) | Tenant configuration is isolated by forced row-level security (tested). Stored tenant "mapping overrides" exist (`backend/app/access/catalog.py:387-582`) but the import never reads them |
| 11.6 | How custom fields would be stored in the customer database | **Not implemented** | Proposed in 9.6: one `extensions` JSON column on core tables, validated against definitions |
| 11.7 | Modify, deactivate or version without losing data | **Not implemented** for custom fields | Central master data is retired rather than deleted, and released master mapping versions are immutable (tested), which is the pattern to reuse |
| 11.8 | Use in search, filters, reports, analytics, workflows, AI | **Not implemented** | Lists, reports and the searchable record for Ask MDARIX are built from fixed columns (`complaints_router.py:28-86`, `imports.py:909-944`) |
| 11.9 | Implemented, or needed before MVP 1.0? | **Not implemented** | Priority in 9.9 |

### 9.4 Section 12: manual, automated and AI-assisted mapping

| # | Capability | Current status | Evidence and gap |
|---|---|---|---|
| 12.1 | Manual mapping in a graphical interface | **Partially implemented** | Three-step form: pick system, record and MDARIX target; rows of drop-downs (customer field → MDARIX field → transform); server check; save as draft (`frontend/src/features/mapping/MappingWizard.tsx`). No drag-and-drop, no editing of a saved mapping in the UI, defaults only inherited from a template, every mapping saved as version `v1` |
| 12.2 | Automatic discovery of source schemas, fields and types | **Partially implemented** | Fields shown come from a static central catalog seeded at release time. A live "discover schema" call exists but its default path is wrong (falls back to the health endpoint: `backend/app/access/common.py:384` vs `:420`), the UI shows only a status, and nothing is stored or versioned (`configuration.py:775-792`) |
| 12.3 | Automatic mapping proposals | **Partially implemented** | A synonym table auto-fills required fields (`frontend/src/features/mapping/mappingModel.ts:30-69`, tested) and the 39 standard templates prefill a mapping (tested end to end). A server-side name matcher exists but is platform-only, unused by the UI and does not store decisions (`backend/app/mapping_catalog_router.py:564-609`) |
| 12.4 | AI-assisted mapping across naming conventions | **Not implemented** | No AI model or embedding is used for mapping anywhere |
| 12.5 | Confidence scores and explanations | **Not implemented** | The name matcher labels every hit `confidence: "MEDIUM"`, `reason: "Name similarity"` |
| 12.6 | Prefill high-confidence, route ambiguous or high-risk mappings to review | **Not implemented** | No confidence tiers, no conflict or ambiguity queue |
| 12.7 | Modify, approve, reject and publish without code | **Partially implemented** | Request approval, approve (second administrator), release and roll back are in the UI; approval and release are tested. No "reject" action; no editing of a draft in the UI; rules and status can be changed after approval through the generic edit route (security gap) |
| 12.8 | Validate against sample data before activation | **Partially implemented** | Two preview endpoints exist, but neither runs the real checked import: the platform Mapping Studio dry-run uses a different mapping model; the saved-mapping preview applies rules sent in the request, not the saved ones, without filters, defaults or reference checks; neither has a UI for customer administrators or a behavioural test. The real checks run only during a live sync, which writes or refuses the whole batch |
| 12.9 | Schema changes trigger impact analysis and alerts | **Not implemented** | Drift and diff helpers work only on field lists supplied by the caller and are never run during a sync; release "impact" echoes the mapping's own source and target; no alert on field changes |
| 12.10 | Version-controlled, auditable, able to roll back | **Partially implemented** | Version column, version list, audited release transitions (tested). No diff between versions, no content freeze, rule edits audited without before/after, rollback untested and implicit (falls back to any older released version), run time not pinned to a version |
| 12.11 | Which are available today | — | Manual form mapping, template prefill, synonym auto-fill of required fields, structural check, two-person release, roll back. Not available: live discovery, AI, confidence, sample validation, schema-change alerts, custom fields |

### 9.5 Section 13: the intended Customer Administrator workflow, today

| Step | Today | Gap |
|---|---|---|
| 1. Open Data & Configuration → Data Mapping | **Exists** as Data Mapping (Mappings, Field mappings) and Integrations in the customer console | — |
| 2. Select an application or create an integration | **Exists** (Integrations, "Add connection") | Source system type is free text |
| 3. Connect through an authorized connector | **Partially**: one generic connector with a static API key; Test and Sync now work | OAuth2, SAP OData and other adapters (section 6, C4) |
| 4. Discover entities, fields and types | **Partially**: static catalog only | Fix and store live discovery; schema fingerprint per version |
| 5. Load standard templates and master data | **Exists**: "Use the standard mapping" | Templates shipped only with code releases |
| 6. Propose mappings, AI-assisted | **Partially**: synonym auto-fill of required fields | Scored proposals, AI assistance (9.8) |
| 7. Add custom fields for unmapped attributes | **Not available** | Custom fields (9.6) |
| 8. Review rules, validation results and conflicts | **Partially**: structural check shown | Sample-data validation with the real import checks; conflict list |
| 9. Approve and publish | **Exists**: two-person release | Reject action; freeze after approval; close the edit-route bypass |
| 10. Customer-side service executes and fills the customer database | **Not available**: execution is inside MDARIX | Customer-side integration service (9.6) |
| 11. Monitor execution, errors, schema changes and data quality | **Partially**: runs, failures, an email on failed scheduled syncs | Schema-change detection, data-quality rules, real reconciliation (section 6, C3) |

### 9.6 Architecture recommendation: central governance, customer-side execution

**MDARIX (central) governs; it never needs the data values.**
- Holds standard data models, master data and value sets, mapping templates, tenant mapping versions, custom-field *definitions*, approval workflow and audit, all in the control database (configuration and metadata only).
- Publishes each released mapping as an immutable, versioned **mapping package**: the mapping rules, the custom-field definitions it uses, the master-data version and value sets it depends on, and a content hash signed by MDARIX. A package changes only through a new version and a new approval.

**A customer-side integration service executes; data stays in the customer environment.**
- Runs in the customer's infrastructure next to the source applications and the Tenant Transactional Database.
- Connects *outbound* to MDARIX over HTTPS (no inbound connection into the customer network), authenticates with a per-tenant credential, pulls approved packages, verifies their signature, and pins each integration to an exact package version.
- Reads the source applications locally, applies the mapping, validates every record (mandatory fields, types, value sets from the package, custom-field rules, referential integrity against the tenant database), writes accepted records to the Tenant Transactional Database and quarantines rejected ones there.
- Reports back **metadata only**: run counts, error codes, reconciliation totals, schema fingerprints and field names, never record values.
- Uses the *same* mapping and validation engine as MDARIX (extracted into a shared library from `connector_mapping.py` and `trial/imports.py`), so a mapping validated centrally behaves identically when executed locally.

**Schema discovery and AI assistance can run without moving transactional data:** they need field names, types and descriptions, which the integration service sends as metadata. Sample *values* are used only when the customer allows it, are masked, and are processed in the customer's environment or by the configured AI provider under the AI controls already in place.

**Master-data and template propagation:** new master data and template versions are published as packages; each tenant adopts a version explicitly (impact report first, then approval), and the integration service applies it locally. No silent propagation, matching the current `silent_propagation: False` principle.

### 9.7 Database impact

| Where | Change |
|---|---|
| Control database (MDARIX) | `tenant_field_definitions` (tenant, entity, key, label, type, description, default, required, validation rules, status, version, created and retired by); mapping package table (version, content hash, signature, status, approvals) with released content frozen; per-integration pinned package version; stored schema snapshots and fingerprints per source object version; mapping-suggestion decisions (accepted or rejected, by whom, confidence) |
| Tenant Transactional Database (customer) | One `extensions` JSON column on the core business tables (complaints, products, lots, investigations, evidence, CAPAs, suppliers…) holding custom-field values keyed by field key, with an index for search; a quarantine table for rejected records; a local copy of the adopted master-data version and value sets that the integration service reads. Because the `extensions` column is part of the standard model, every customer database keeps the same schema and the drift check stays valid |
| Code that reads business data | Lists, filters, reports, the searchable record for Ask MDARIX and workflow conditions read `extensions` according to the field definitions and the user's permissions |

### 9.8 Customer Administrator screens needed

1. **Custom fields** (new, under Data & Configuration): list per entity; add, edit, deactivate and version a field (name, type, description, default, mandatory, validation rule); show usage (mappings, reports) before deactivating; deactivation keeps stored values.
2. **Data Mapping editor**: edit a draft, create a new version, show the difference between versions, map to custom fields, edit defaults, see suggestions with confidence and reason (accept or reject each), see conflicts.
3. **Discover and test**: live schema discovery with the stored snapshot and what changed since the last one; "test with sample data" running the real import checks without writing, showing accepted rows, rejected rows and why.
4. **Review and release**: reject with a reason; frozen content after approval; impact of adopting a new template or master-data version.
5. **Integration service**: register the customer-side service, show its version, last contact, pinned packages and health.
6. **Monitoring**: schema-change alerts, quarantine queue with reasons, reconciliation against source totals, data-quality rule results.

### 9.9 Automation and the human decision

| Operation | Approach |
|---|---|
| Schema discovery, fingerprinting, change detection | **Automated** |
| Name, synonym, type and template matching with confidence | **Automated** (deterministic) |
| Matching across customer naming conventions, explanations | **AI-assisted**, on metadata; values only with consent and masking; always a proposal |
| Prefilling high-confidence proposals in a draft | **Automated**, still requires review |
| Ambiguous, conflicting or high-risk mappings (personal data, regulatory fields, mandatory targets) | **Human review** required |
| Sample validation, impact analysis on schema or template change | **Automated**, results shown to the administrator |
| Approval and release of a mapping or custom field; adopting a new template or master-data version | **Human, two-person approval** (never automatic) |
| Rolling back to a pinned earlier version | **Human decision**, automated execution |

### 9.10 MVP priority and implementation tasks

**Mandatory for MVP 1.0 (customer-hosted model):**
1. Close the mapping edit-route bypass; freeze content after approval; add Reject; pin the package version at run time; test rollback (S-M).
2. Customer-side integration service executing central mapping packages with the shared engine, outbound-only, metadata-only reporting (L; depends on section 6 B).
3. Sample-data validation through the real import checks without writing, with a UI (M).
4. Live schema discovery fixed, stored and fingerprinted; schema-change detection at each sync with an alert (M).
5. Custom fields, minimum: definitions screen and API, `extensions` storage in the tenant database, mapping into custom fields, validation by definition, shown on records and usable in list filters (L).

**Later release:**
6. Custom fields in reports, analytics, workflow conditions and AI context.
7. Scored suggestions with confidence tiers and stored decisions; AI-assisted matching on metadata.
8. Version diff view, template and master-data package adoption with impact report, central data-quality rules enforced by the integration service.

**Validation tests to add:**
- Edit-route bypass refused; released content immutable; rollback restores the pinned earlier version.
- A package executed by the customer-side service produces the same accepted and rejected rows as the central check on the same sample.
- Custom field defined, mapped from a TrackWise-style source field, stored in `extensions` on the tenant database, filtered in a list, deactivated without losing values, invisible to another tenant.
- A removed or renamed source field is detected at the next sync, raises an alert and blocks the affected mapping until reviewed.
- Nothing but metadata reaches MDARIX from the integration service (record values absent from the control database, logs and outbox).
