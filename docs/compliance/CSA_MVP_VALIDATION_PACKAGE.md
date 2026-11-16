# MDARIX-CSA-MVP-1.0

> **SUPERSEDED (12 Nov 2026, B6b).** This MVP-1.0 package was never executed and is retired. Do not give it to a customer or use it as evidence. The current plan is [MDX-VAL-001](../validation/MDX-VAL-001_VALIDATION_MASTER_PLAN.md); the document index is [docs/validation/README.md](../validation/README.md).

Release: `MVP-1.0`
Status: **SUPERSEDED**

## Intended use
Internal design-partner MVP validation; not a regulatory certification.

## Requirements
- **MDX-SEC-001** — Authenticated users can access only authorized tenant data.
- **MDX-SEC-002** — Protected fields are excluded from API, search, export, and AI context.
- **MDX-AI-001** — AI output is advisory, provenance-aware, and requires human review.
- **MDX-AUD-001** — Governed mutations create tenant-scoped audit evidence.
- **MDX-DOC-001** — Regulatory drafts preserve version, citations, limitations, and approval state.
- **MDX-OPS-001** — Migrations, health checks, worker processing, and recovery are observable.

## IQ/OQ/PQ tests
### IQ-001 — Verify installation identity and source integrity.
Phase: `IQ`; Requirement: `MDX-OPS-001`
Procedure:
1. Record release commit and package versions.
1. Record Python, Node, PostgreSQL, and pgvector versions.
1. Verify migration head.
Acceptance: All versions and the approved migration head are recorded.
Evidence: `IQ-001 environment record`

### IQ-002 — Verify required services and configuration are installed.
Phase: `IQ`; Requirement: `MDX-SEC-001`
Procedure:
1. Start the controlled test stack.
1. Verify API, database, worker, simulator, and frontend health endpoints.
Acceptance: All required services report healthy without secrets in logs.
Evidence: `IQ-002 health traces`

### OQ-001 — Verify two tenants cannot read each other's records.
Phase: `OQ`; Requirement: `MDX-SEC-001`
Procedure:
1. Sign in as Tenant A.
1. Request Tenant B record, search, export, attachment, and AI context by ID.
1. Repeat in reverse.
Acceptance: Every unauthorized request returns denial or no foreign data.
Evidence: `OQ-001 API traces and audit IDs`

### OQ-002 — Verify field policy enforcement across all retrieval surfaces.
Phase: `OQ`; Requirement: `MDX-SEC-002`
Procedure:
1. Mark a field hidden.
1. Read API, search, export, attachment metadata, and AI context.
Acceptance: The hidden value is absent from every response and artifact.
Evidence: `OQ-002 redacted response set`

### OQ-003 — Verify grounded AI safeguards.
Phase: `OQ`; Requirement: `MDX-AI-001`
Procedure:
1. Submit a scoped investigation question.
1. Inspect citations, provenance, uncertainty, limitations, and human-review flag.
1. Submit an unsupported causal claim.
Acceptance: Unsupported causality is rejected or abstained from and human review remains required.
Evidence: `OQ-003 AI response evidence`

### OQ-004 — Verify governed mutation auditability.
Phase: `OQ`; Requirement: `MDX-AUD-001`
Procedure:
1. Perform a governed update and approval.
1. Inspect actor, tenant, timestamp, reason, old/new values, and signature binding.
Acceptance: The mutation and approval are immutable and version-bound.
Evidence: `OQ-004 audit/signature evidence`

### PQ-001 — Verify a complete regulatory authoring journey.
Phase: `PQ`; Requirement: `MDX-DOC-001`
Procedure:
1. Create CER, IFU, GSPR, and eSTAR preparation documents.
1. Create a second version.
1. Review, approve, archive, export, and verify the content hash.
Acceptance: The complete history is reproducible and no version is silently overwritten.
Evidence: `PQ-001 document package`

### PQ-002 — Verify normal and failure recovery workflows.
Phase: `PQ`; Requirement: `MDX-OPS-001`
Procedure:
1. Run connector ingestion, retry, dead-letter, replay, report generation, and stale-job recovery.
1. Capture worker and audit evidence.
Acceptance: Retries are bounded, replay is idempotent, and failures are visible and recoverable.
Evidence: `PQ-002 operational report`

### PQ-003 — Verify browser persona workflows.
Phase: `PQ`; Requirement: `MDX-SEC-001`
Procedure:
1. Exercise Platform Admin, Customer Admin, investigator, and approver journeys on desktop and mobile.
1. Review keyboard focus and screen-reader semantics.
Acceptance: Authorized journeys work without overflow, leakage, or inaccessible critical controls.
Evidence: `PQ-003 browser/accessibility evidence`

## Deviations
1. Record deviation ID and impact.
2. Assess patient/product/data integrity impact.
3. Approve corrective action.
4. Retest affected requirement.
5. Obtain QA and system-owner approval.

## Approval
System owner: PENDING
Quality reviewer: PENDING

## Limitations
- Execution evidence must be generated against the approved test environment.
- This package does not certify FDA, ISO, HIPAA, or 21 CFR Part 11 compliance.
