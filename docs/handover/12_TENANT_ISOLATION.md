# Tenant Isolation

## Boundary model

The authenticated session is the source of tenant identity. The client cannot select an arbitrary tenant database or override the server-derived tenant context. The control plane stores tenant membership and data-plane registry metadata; tenant business records are routed to the registered customer database.

## Required isolation surfaces

| Surface | Current MVP position |
|---|---|
| API reads/writes | Implemented in tenant-aware paths; legacy endpoints require route-by-route regression |
| Database | Four isolated synthetic data planes plus local RLS/application enforcement |
| Search | Tenant filters in data-plane search; full legacy route coverage must remain tested |
| Export | Tenant-scoped control and data-plane foundations |
| Attachments | Tenant-prefixed/object-storage foundation; full production storage validation deferred |
| Reports | Authorization foundations; multi-instance artifact validation deferred |
| AI context/retrieval | Tenant-filtered context and provider abstraction; all data-plane routes require validation |
| Connector ingestion | Tenant-bound provider token and durable ledger/outbox foundations |
| Audit | Tenant-scoped access and immutable protections |

## Test expectation

Every migrated endpoint must be exercised with Tenant A and Tenant B identities, including positive reads, wrong-tenant IDs, search, export, attachments, reports, AI context, and ingestion. A local pass is synthetic MVP evidence, not hosted production proof.
