# MDARIX MVP 1.0 — Internal Evidence Report

Date: 2026-09-29  
Decision: **GO FOR CONTROLLED SYNTHETIC DEMO**

## Scope

This report covers the current internal MVP only. Validation uses synthetic tenants, seeded business records, provider simulators, local PostgreSQL, local Mailpit, local object-storage contracts, and test fixtures. It makes no production-readiness claim.

## Results

| Area | Result | Evidence |
|---|---|---|
| Local MFA enrollment, invalid/expired code, replay rejection, challenge issuance, and MFA-required authorized signature gate | PASS | `tests/test_mfa_mvp.py`; `tests/test_day23_governance_security.py` |
| Synthetic tenant/data-plane matrix | PASS | `scripts/validate_mvp_validation_matrix.py`; four tenants, eight simulators |
| Data-plane schema and database boundaries | PASS | `scripts/validate_data_plane_operations.py`; 130 business tables per plane |
| Business routing, evidence, reports, exports, retrieval/AI, simulator, replay, retry, dead-letter, and schema drift regression | PASS | 40 focused tests passed |
| Local Mailpit reachability | PASS | `scripts/validate_local_stack.py`; port 8025 returned HTTP 200 |
| Local object storage tenant prefix, signing, quota, report artifacts, and worker/outbox behavior | PASS | `tests/test_stage3_completion.py`, `tests/test_stage2_operations.py`, `tests/test_compliance_report.py` |
| Customer 360 and Tenant 360 specialized tab render paths | PRESENT | `frontend/src/features/admin/PlatformAdminScreen.tsx`; dedicated tab panels, quick actions, structured records, and tab-specific API loading |
| Frontend production build | PASS | `npm.cmd --prefix frontend run build` |
| Frontend automated tests | PASS | 13 tests across 3 files |

## MVP demo success criteria

- Complaint-to-investigation workflow can be demonstrated with timestamped records.
- Evidence retrieval and provenance are visible in the investigation workflow.
- Mapping/import validation produces controlled results and correlation evidence.
- Four synthetic tenant boundaries are validated with zero cross-plane query capability.
- Replay/idempotency, retry, dead-letter, and schema-drift behavior are covered.
- Decision traceability includes signer, object version, signature verification, and audit evidence.

## Deferred production gates

These are intentionally deferred and are not MVP blockers: hosted multi-instance deployment, production TLS/runtime roles, production backups/PITR/monitoring, real SMTP/provider delivery, real customer credentials, production object storage/malware scanning, enterprise IdP, and final production accessibility certification.

## Notes

The multi-instance verification script was not treated as an MVP failure because it requires a second deployed application instance. The local stack check confirmed frontend, backend, PostgreSQL, Mailpit, and all eight simulator endpoints. A MinIO endpoint is not required for the current local MVP because object-storage contract behavior is covered by the local tenant-scoped storage tests.
