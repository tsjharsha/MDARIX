# MDARIX MVP 1.0 — Scope and Demo Readiness

Status: **FROZEN FOR CONTROLLED SYNTHETIC DEMO**  
Last reviewed: 2026-09-29

## Frozen MVP use case

MDARIX MVP helps medical-device quality and product teams move from a complaint or product signal to a reviewable investigation decision:

1. Import synthetic source records from provider simulators.
2. Map source fields to the MDARIX canonical model.
3. Connect complaint, product, version, supplier, lot, change, and evidence context.
4. Review evidence, contradictions, unknowns, and provenance.
5. Use advisory AI with tenant-filtered context and visible limitations.
6. Prepare and approve a human decision with re-authentication, MFA controls, and audit evidence.

The MVP does **not** expand into billing, payment processing, EHR/EMR workflows, clinical diagnosis, automated regulatory approval, or external writes to customer systems.

## Capability status language

- **Implemented** — available in the current codebase and covered by an automated or repeatable local check.
- **Synthetic/demo-only** — demonstrated with seeded validation tenants, provider simulators, or local services; not customer data.
- **Planned** — future product direction, not available functionality.
- **Production-dependent** — requires customer credentials, hosted infrastructure, approved providers, or operational evidence.

## Design-partner demo script

1. Sign in as an administrator and show the tenant/environment boundary.
2. Open a seeded complaint and show source identifier, product/version, timing, and provenance.
3. Open Product 360 and Timeline Intelligence; follow component, supplier, lot, change, and version relationships.
4. Open Mapping Studio, preview one-to-one mappings, validate, and show ingestion correlation evidence.
5. Review the investigation's evidence, contradictions, hypotheses, unknowns, and missing evidence.
6. Ask MDARIX a grounded question and show provenance, uncertainty, limitations, and human-review status.
7. Open Decision Center, re-authenticate, complete MFA when enabled, and approve/reject the current version.
8. Show signature verification and the audit event.
9. Switch synthetic tenants and demonstrate that records, search, exports, attachments, reports, and AI context do not cross the boundary.
10. Close by identifying synthetic/demo-only and production-dependent capabilities.

## Measurable demo success criteria

| Measure | MVP target | Evidence |
|---|---:|---|
| Complaint → investigation opened | ≤ 5 minutes | Timestamped audit events |
| Evidence retrieval | ≤ 60 seconds | Retrieval trace with sources |
| Mapping/import | 100% required fields; 0 unauthorized fields | Mapping result and correlation ID |
| Cross-tenant isolation | 0 foreign records across API, search, export, attachment, report, AI, and ingestion | Redacted traces and test report |
| Replay/idempotency | 0 duplicate business records on replay | Ingestion/outbox report |
| Decision traceability | 100% of approved decisions link to finding, observation, evidence, source, signer, version, and audit event | Signature and audit evidence |
| Human governance | 100% governed decisions require authorization, remarks, re-authentication, and MFA when enabled | Positive/negative test results |

## Demo release gate

**GO FOR CONTROLLED SYNTHETIC DEMO** only when the local validation report is green and no cross-tenant leakage is observed. This is not a production-readiness or customer-data certification claim.
