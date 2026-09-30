# MDARIX Internal MVP Validation Report

Date: 2026-09-28

## Decision

**GO for controlled internal MVP demonstration using synthetic validation tenants and local Docker infrastructure.**

This is not a production-readiness approval. Production hosting, live customer credentials, managed storage, and production database operations are explicitly outside this MVP gate.

## Evidence

| Area | Result |
|---|---|
| Backend regression | 433 passed, 4 non-blocking deprecation/serialization warnings |
| Frontend build | Passed |
| Frontend unit tests | 13 passed |
| Browser desktop/mobile | 20 Playwright tests passed |
| Keyboard/accessibility | Passed in browser suite with axe checks |
| Synthetic connector matrix | PASS: 32 provider/tenant rows; replay duplicates retained and not duplicated |
| Data-plane schema | PASS: 130 business tables in each of four planes |
| Cross-plane boundary | PASS: cross-plane query impossible by database boundary |
| Outbox worker | Healthy Docker service; heartbeat, retry/dead-letter metrics, tenant routing validated |
| Durable report jobs | PostgreSQL persistence and `SKIP LOCKED` worker claims validated |
| Object storage | Tenant keys, quota, malware hook, encryption-at-rest, signed URLs, retention marker validated |
| Mailpit | SMTP validation message accepted and visible through Mailpit API |
| Local backups | Four PostgreSQL custom-format backups created and `pg_restore --list` validated |

## MVP scope completed

- Tenant A–D synthetic data-plane databases and server-side registry resolution.
- Product, investigation, evidence, retrieval, AI interaction, report, attachment, connector, and worker routing.
- Cross-tenant authorization and physical data-plane separation checks.
- Durable report job/artifact metadata and multi-worker row-lock claiming.
- Internal SMTP capture, local storage controls, browser evidence, and accessibility checks.

## Deferred by MVP scope

- Hosted multi-instance deployment.
- Production TLS, managed backups, WAL/PITR, and monitoring.
- Real customer endpoints and credentials.
- Production S3/KMS and enterprise malware scanning.
- Production retention and restore rehearsal.

## Reproduction commands

```powershell
python -m pytest -q
npm.cmd --prefix frontend run build
npm.cmd --prefix frontend test -- --run
npm.cmd --prefix frontend run test:e2e
python scripts/validate_mvp_validation_matrix.py
python scripts/validate_data_plane_operations.py
python scripts/backup_validation_dataplanes.py
```
