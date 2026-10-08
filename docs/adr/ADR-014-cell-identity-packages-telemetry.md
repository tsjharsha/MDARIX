# ADR-014: Cell Identity, Signed Packages and Metadata-Only Telemetry

## Context
The platform must license cells, distribute standards and software, and see fleet health, without ever holding a credential for a tenant database or receiving customer records.
## Decision
All communication is cell-initiated over outbound HTTPS with mutual TLS: a one-time enrollment token is exchanged for a platform-issued client certificate whose fingerprint identifies the cell. The platform never connects into a cell. Cells pull **signed packages** (ed25519; the signing key is held by the release pipeline, the public key pinned in the cell at install): LICENCE, REFERENCE_DATA, MAPPING_TEMPLATE, POLICY for MVP, later DATA_MODEL, CONNECTOR, AI_MODEL. Software ships as signed container images with an SBOM; the platform offers a version and the cell operator upgrades. Cells push a heartbeat with a strict schema (versions, schema revision, job outcomes, counts, error codes) that refuses unknown fields and free text. A cell keeps serving when the platform is unreachable; the licence has a 30-day grace period, after which the cell becomes read-only (no new cases or signatures) until it reconnects.
## Rationale
Outbound-only with mTLS needs no inbound firewall openings in customer networks; signatures protect against supply-chain tampering; a strict telemetry schema makes "metadata only" testable.
## Consequences
New platform tables `cells` and `packages`, cell table `received_packages`; a cell job `platform-sync`; a fleet view built from heartbeats replaces the platform's tenant-data screens.
## Alternatives Considered
Platform-to-cell API calls: rejected (inbound access, platform holds cell credentials). Unsigned configuration pulled from the platform: rejected (supply-chain risk).
## Status
ACCEPTED (2026-10-08)
