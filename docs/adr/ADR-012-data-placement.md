# ADR-012: Data Classification and Placement

## Context
Today customer users, sessions, MFA secrets, decision signatures, part of the audit trail, connector and mapping configuration, files and backups live in MDARIX-controlled storage even for tenants with a dedicated database (see `MVP1_PRODUCTION_DATABASE_ARCHITECTURE_REVIEW.md`, section 4).
## Decision
The placement matrix in `MDARIX_TARGET_ARCHITECTURE_DESIGN.md` section 6 is binding. Everything a customer creates or that describes a customer's operations lives only in that customer's cell: business records, users and roles, sessions and MFA, signatures, audit trail, AI inputs and outputs, embeddings, documents, reports, exports, logs with record content, backups, custom-field definitions, mappings and connector configuration. The platform holds only platform-owned data: tenant registry, licences and plans, standards and signed packages, platform staff, and metadata-only telemetry (versions, counts, error codes). Standards are replicated read-only into cells and referenced by `code@version`; there are no cross-database foreign keys. "Master data" is split by ownership: MDARIX-published definitions are central; a customer's products, parts, suppliers and sites are tenant data.
## Rationale
Clear ownership per data category is what customers, auditors and the validation package will check; it also makes residency, retention and offboarding mechanical (destroy the cell and its keys).
## Consequences
No platform route may return tenant records; heartbeats use a strict schema that refuses free text; problem reports carry free text only with the user's consent; backups are per cell with the cell's keys.
## Alternatives Considered
Keeping identity and audit central for easier platform support: rejected, because a customer's user directory and audit trail are customer data and central copies defeat the boundary.
## Status
ACCEPTED (2026-10-08)
