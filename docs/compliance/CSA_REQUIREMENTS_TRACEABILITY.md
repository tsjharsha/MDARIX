# CSA requirements-to-test traceability

> **SUPERSEDED (12 Nov 2026, B6b).** This hand-kept MVP-1.0 table is retired. Do not give it to a customer or use it as evidence. Traceability is generated per release from `requirements.csv`, the [scenario register](../validation/scenario-register.md) and test results (MDX-VAL-009, B6b Part B); see [docs/validation/README.md](../validation/README.md).

| Requirement | Verification tests | Evidence | Acceptance |
|---|---|---|---|
| MDX-SEC-001 Tenant authorization | IQ-002, OQ-001, PQ-003 | Health traces, isolation traces, browser evidence | No foreign data or unauthorized action |
| MDX-SEC-002 Field protection | OQ-002 | Redacted API/search/export/AI artifacts | Hidden values absent from every surface |
| MDX-AI-001 Advisory grounded AI | OQ-003 | Prompt, response, provenance, limitation evidence | Human review required; unsupported causality abstains |
| MDX-AUD-001 Governed audit | OQ-004 | Audit IDs, old/new values, signature evidence | Immutable, tenant-scoped, version-bound record |
| MDX-DOC-001 Controlled documents | PQ-001 | Versioned drafts, export hashes, approvals | Reproducible history; no silent overwrite |
| MDX-OPS-001 Operations/recovery | IQ-001, IQ-002, PQ-002 | Versions, health, worker/retry/dead-letter evidence | Recovery bounded, observable, and idempotent |

Test results, evidence hashes, deviations, and approval status are recorded in
the versioned evidence manifest; this table is not itself proof of execution.

