# Connecting a customer system (for example TrackWise Digital)

How a customer's quality-system records reach MDARIX today, step by step. Everything below works end to end and is
covered by `tests/test_trackwise_integration_path.py`.

## Where the data lives

- **Control database (shared).** Customers, tenants, users, connections, mappings, sync runs and the audit trail.
  Every row carries its `tenant_id`, and row-level security keeps tenants apart.
- **Data plane (per tenant).** Products, versions, lots, complaints and the rest of the business data. The
  `tenant_data_planes` registry chooses where each tenant's data plane is:
  - **Shared database.** The default for every new tenant: onboarding, Add tenant, the customer import, trials and
    the demo. Rows are keyed by tenant and isolated by row-level security.
  - **Dedicated database.** Ops replace the tenant's registry row with one that names a database secret
    (`MDARIX_DATA_PLANE_<TENANT>_DATABASE_URL`). The four synthetic `R1_TENANT_*` tenants work this way locally.
  - Tenants created before onboarding registered a data plane can be registered with
    `python scripts/register_shared_data_planes.py`. It is a dry run by default; pass `--apply` to write.

## Steps

| # | Who | Step | Where |
|---|---|---|---|
| 1 | Ops | Prefer the connection's own API key (Integrations > connection > Set API key, encrypted at rest). Only if a server secret is needed, name it `MDARIX_CONNECTOR_SECRET_<TENANT ID>_<NAME>` with the tenant's identifier (for example `TEN0351`); other names are refused in staging and production. If the host is internal, add it to `MDARIX_CONNECTOR_ALLOWED_HOSTS`. | Server environment |
| 2 | Customer Administrator | **New mapping**. (1) Name it, choose the system (TrackWise Digital), the record in that system (Complaint) and the MDARIX record it fills (Complaints). (2) Click "Add the required fields": TrackWise fields are matched by name (complaint_id, product_code → product ID, problem_description → description). Add optional fields such as received date, and choose how each value is carried over. (3) Check: it says whether the mapping can import records, then save it as a draft. | Customer administration → Data Mapping |
| 3 | Two different administrators | Open the mapping: request approval, approve (a different administrator), release. The release is refused if the mapping has no field rules. | Data Mapping → the mapping |
| 4 | Customer Administrator | **Add a connection**: code, system type, https endpoint, credential reference (`MDARIX_CONNECTOR_SECRET_<TENANT ID>_…`) or, better, the connection's own API key, the record to read (Complaint) and the mapping. For an existing connection, use "Choose mapping". | Customer administration → Integrations |
| 5 | Customer Administrator | Health check, then activate the connection. | Integrations → Connections |
| 6 | Customer Administrator | **Sync now**. The records read are imported through the released mapping as one checked batch: all of it is written, or none of it if a record is invalid. Each sync is recorded as a run (records read, kept, rejected; reconciled match or mismatch). | Integrations; results under Sync activity and Reconciliation |

Platform administrators see every tenant's runs under Integrations → Runs & failures.

## What the import accepts today

| MDARIX record | Required | Optional |
|---|---|---|
| Complaints | complaint_id, product_id, description | version, lot_id, event_date, received_date, status |
| Products and versions | product_id, product_name | version, product_family, version_release_date |
| Lots and batches | lot_id, product_id, version | manufacture_date |

Conversions: as is, remove spaces at the ends, upper case, lower case, as text, as a date, as yes / no.

## Not yet

- **Mostly simulated sources.** There is no TrackWise Digital API client; local runs use the source simulators,
  and the simulator's complaint has only a few fields.
- **No scheduled or incremental sync.** "Sync now" reads one page.
- **Fields the import has no column for.** TrackWise complaint fields outside the table above (severity, country,
  UDI, serial number, clinical flags) are not stored yet, and the seeded value mappings (for example severity
  MIN/MAJ/CRIT → Minor/Major/Critical) are not applied.
- **Investigation, CAPA and Evidence.** These objects have no import yet.
- **Batches are all or nothing.** There is no per-record quarantine.
