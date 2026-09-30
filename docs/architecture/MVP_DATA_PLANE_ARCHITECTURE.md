# MDARIX MVP data-plane architecture

MDARIX now models the modified architecture as a control plane plus isolated
customer data planes.

## Control plane

The central `postgres` service stores identity, tenant membership, plans,
entitlements, connector metadata, mappings, configuration, audit metadata, and
operational job state. It is the source of truth for resolving the signed-in
tenant.

## Customer data planes

The MVP Compose topology provides four isolated PostgreSQL services:

| Tenant | Service | Database reference |
|---|---|---|
| R1_TENANT_1 | `tenant-a-data` | `mdarix-tenant-a-data` |
| R1_TENANT_2 | `tenant-b-data` | `mdarix-tenant-b-data` |
| R1_TENANT_3 | `tenant-c-data` | `mdarix-tenant-c-data` |
| R1_TENANT_4 | `tenant-d-data` | `mdarix-tenant-d-data` |

The control-plane table `tenant_data_planes` stores only the approved database
reference, secret reference, region, residency, and schema status. Passwords
are not stored in the database or exposed to the browser.

## Request routing rule

1. The user signs in.
2. The server derives the tenant from the authenticated membership.
3. The server loads that tenant's `tenant_data_planes` row.
4. The service resolves the connection from the deployment secret reference.
5. Business data is read or written only in that customer's data plane.

A browser-supplied tenant ID or database reference is never an authority.

## Current rollout status

The isolated databases and registry are additive and safe to enable. Existing
routes still use the shared control-plane session by default until each business
data route is explicitly migrated to the data-plane adapter. This avoids a
partial cutover that could break authentication, migrations, RLS, or existing
APIs.
