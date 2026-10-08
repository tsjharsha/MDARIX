# ADR-011: Control Plane and Tenant Cell

## Context
Enterprise medical-device customers require their quality data to stay under their control. The current deployment is one multi-tenant application with one control database (customers separated by forced row-level security) and optional dedicated databases that MDARIX still administers, backs up and processes centrally. `docs/architecture/MDARIX_TARGET_ARCHITECTURE_DESIGN.md` compares four options.
## Decision
MDARIX adopts a **control plane plus tenant cell** architecture (Option C). The MDARIX Platform holds only platform data (tenant registry, licences, standards, packages, metadata telemetry). Each customer runs in its own **tenant cell**: the tenant database, object storage, keys, and every MDARIX service that touches customer data (application, workers, integration, AI). One cell artifact is deployable in three hosting modes: MDARIX-managed dedicated cell (MVP default), customer cloud, and later customer on-premises.
## Rationale
Separating storage alone does not keep data under customer control: a central application still processes, logs, caches and backs up the records it reads. Placing the services with the data closes that gap, needs no inbound path into customer networks, and fits enterprise security reviews, while MDARIX-managed cells keep the simplicity of a hosted service for small customers.
## Consequences
Cost per tenant rises (one database and service set per cell); fleet operations become the main operational concern; cross-tenant analytics is opt-in only. Design partners with real data start in their own cell (this replaces the earlier decision that pilots start on the shared plane). Free trials and demonstrations stay on one shared sandbox deployment restricted to synthetic data by its terms.
## Alternatives Considered
A, fully MDARIX-hosted multi-tenant: fails enterprise data-control requirements. B, central application with customer-hosted databases: worst of both (central processing, inbound database access). D, fully customer-hosted private installs for everyone: costly to support; kept as a hosting mode of the same cell instead.
## Status
ACCEPTED (2026-10-08)
