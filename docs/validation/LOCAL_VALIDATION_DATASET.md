# Local synthetic validation dataset

This dataset supports internal MVP checks only. It contains no customer or production data.

## Tenant coverage

| Tenant | Customer | Data-plane database | Users | Products | Complaints | Investigations | Evidence |
|---|---|---|---:|---:|---:|---:|---:|
| R1_TENANT_1 | Northstar Quality | `mdarix_tenant_a` | 9 | 4 | 29 | 2 | 4 |
| R1_TENANT_2 | Aster Medical | `mdarix_tenant_b` | 6 | 4 | 29 | 2 | 4 |
| R1_TENANT_3 | Nimbus Health | `mdarix_tenant_c` | 6 | 4 | 29 | 2 | 4 |
| R1_TENANT_4 | Orbit Devices | `mdarix_tenant_d` | 6 | 4 | 29 | 2 | 4 |

Each data plane also contains 7 product versions, 9 components, 2 suppliers, 15 lots, 3 hypotheses,
3 unknowns, a failure chain, 2 scenarios, a risk, a failure mode, a control, a CAPA, an AI execution,
a governed decision, a human review, 4 connector runs, 8 connector source records, 4 reconciliation
records, and 3 report jobs. Tenant A retains one additional historical AI execution.

Each tenant has three environments (Production, Validation, and Demo), one synthetic verified domain,
one simulated OIDC configuration, an active MVP validation plan/subscription, entitlement and quota
snapshots, service-health checks, tenant-isolation evidence, connector configurations, complaint mappings,
notification/reminder configuration, and an immutable seed audit event.

## Synthetic connector matrix

| Tenant | Sources |
|---|---|
| R1_TENANT_1 | TrackWise, Teamcenter, Oracle ERP, Coupa |
| R1_TENANT_2 | Veeva Vault QMS, Teamcenter, Oracle ERP, Coupa |
| R1_TENANT_3 | TrackWise, PLM simulator, ERP simulator, Supplier simulator |
| R1_TENANT_4 | Veeva Vault QMS, Teamcenter, Oracle ERP, Coupa |

## Commands

```powershell
# Read-only inventory
.\.venv\Scripts\python.exe scripts\inventory_validation_dataset.py

# Idempotent population; requires explicit write approval
.\.venv\Scripts\python.exe scripts\seed_validation_dataset.py --apply

# Completeness and tenant-boundary validation
.\.venv\Scripts\python.exe scripts\validate_validation_dataset.py
```

The seed command is idempotent. A second run must report zero newly added records in every category.
The validation command checks every table containing `tenant_id` in each isolated database and fails when
an unexpected tenant identifier or an insufficient workflow record count is found.
