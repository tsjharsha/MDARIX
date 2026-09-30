# Data Model v1 implementation plan

Implements *MDARIX Master Data Foundation v1.0* and *MDARIX Transactional Data
Architecture v1.0* (both R1 / MVP 1.0 baselines) in the database and the code.

## Decisions (confirmed 2026-09-30)

| Question | Decision |
|---|---|
| Physical topology | **Hybrid.** Control-plane database holds `md_master`, `md_control`, `md_audit` and platform-level `md_operations`. Each tenant data-plane database holds `md_transaction`, `md_intelligence`, `md_workflow`, `md_integration` and tenant-level `md_operations`. Business IDs come from one central allocator in the control plane. |
| Column naming | **Spec names.** Primary key `<entity>_uuid`; readable business ID `<entity>_id` (e.g. `product_id = PROD00001`); foreign keys `<entity>_uuid`. |
| Scope | **Everything** in both documents (P0, P1, P2) plus rewiring the application code. |

## Conventions that fill gaps in the specs

1. **Identity columns kept as UUID `_id`.** Both specs use `tenant_id`, `customer_id`,
   `user_id`, `role_id` and `membership_id` as UUID foreign keys. These keep the UUID
   meaning; their readable IDs use `_number` (`tenant_number = TEN00001`,
   `customer_number = CUST00001`) as allowed by Master Data §1.1.
2. **Business-ID allocator.** `md_master.business_id_prefix` registers every prefix,
   its PostgreSQL sequence and its numeric width (5 by default; 8 for high-volume
   objects such as `SRC` and `AUD`). `md_master.next_business_id(prefix)` issues IDs
   atomically. IDs never truncate: when the number outgrows the width it simply
   gets longer. MAX()+1 is not used anywhere.
3. **Prefix collision.** `CONV` is defined twice (Connector Version and AI
   Conversation). Connector Version keeps `CONV`; AI Conversation uses `CONVO`.
4. **Prefixes missing from the spec lists** (COMP, PCOMP, SUP, SITE, LOT, CHG, AIO,
   AIREV, REVREQ, RCM, SIGCER, CTXSNAP, SRC, SRCP, SDR, MCF, LIN, ACCEVT, AUTHEVT,
   EXPEVT, CFGEVT, AIAUD, WSC, OMSG, IMSG, USEVT, METER, OVRP, SAUT, DQR, FGRP,
   APPIND, AUTH, PAGE, SYNC, STAT, HAZ, FM, CTL, RAST, VIG, FA, REC) are registered in
   the one prefix registry.
5. **Time (Rule 5).** Tenant-owned source-derived records keep event, effective,
   source-recorded, known, received and ingested timestamps where material, so the
   current CURRENT / EVENT_AS_OF / KNOWN_AS_OF behaviour is preserved.
6. **Cross-cutting columns (§9)** are added where the table definitions omit them:
   `record_origin`, `created_by`, `created_at`, `updated_at`, and `lock_version` on
   editable controlled records.
7. **Status values** are enforced with CHECK constraints using the values listed
   in the specs.
8. **Cross-database references** (tenant data → master/control records, audit
   links) are UUID columns validated by the application, because foreign keys
   cannot span databases. References inside one database are real foreign keys.
9. **Tables the product uses that the specs do not list** keep their capability
   under spec-style names: evidence chunks/embeddings/retrieval queries and the
   reality graph (`md_intelligence`), requirement, lot_component,
   product_supplier, component_supplier (`md_transaction`), scenario/counterfactual,
   assurance and evaluation results (`md_intelligence`), regulatory documents
   (`md_workflow`), sessions/MFA/invitations/throttling (`md_control`).
10. **`md_control` tables** (not detailed in either document) follow the same
    conventions; they are specified in the Phase 2 migration docstrings.
11. **Master Data seeds** are synthetic/public reference values loaded by a
    controlled seed module, never customer data.

## Phases

Each phase ends with: migrations applied to a fresh database, full test suite
green, application smoke/browser comparison, documentation updated, commit.

| Phase | Scope |
|---|---|
| 1 | **Done (2026-09-30).** `md_master` schema, business-ID allocator (105 prefixes), all 41 Master Data tables, seed v1 and integrity triggers (migrations `md01`, `md02`); Mapping Studio catalog, dry-run and validation read Master Data instead of Python constants. |
| 2 | `md_control`: customer, tenant, environments, data-plane registry, tenant application instances, connections, tenant/effective mappings, identity (users, sessions, MFA, invitations), roles/permissions/personas, plans/subscriptions/entitlements, governance, support access, provisioning. Port auth, request context, access API, governance. |
| 3 | Separate tenant-database migration chain; `md_transaction` and `md_integration`; port ingestion, normalization and connectors to source record → mapping execution → field lineage → canonical records (with quarantine and schema drift); port Product 360, graph, data-plane routes, workspace, analytics. |
| 4 | `md_intelligence`: observation, hypothesis, contradiction, unknown, challenge, failure chain, AI execution/output/review, retrieval; port all intelligence services. |
| 5 | `md_workflow`: task, evidence/review requests, decision brief, decision, signature ceremony, context snapshot; fixes decision signing across databases. |
| 6 | `md_audit` (audit, access, authentication, export, configuration-change, AI audit) and `md_operations` (outbox, jobs, messages, usage, reports, workspace context, conversations). |
| 7 | API/frontend contract (business IDs in UI and URLs), removal of legacy tables and scripts, rebuilt demo environment, final verification. |
