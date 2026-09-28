# Multi-tenant architecture evidence

Validation date: 2026-09-28

## Local database/RLS proof

The local PostgreSQL 16 instance was checked using the non-superuser
`mdarix_runtime` role. The role reported `rolsuper = false`.

With `app.tenant_id` set to the authenticated tenant:

- visible investigation tenant count: `1`
- visible investigation rows: `19`
- visible evidence rows: `55`

With `app.tenant_id` set to an unrelated UUID:

- visible investigation rows: `0`

The database hardening validation also reported:

- tenant-scoped tables: `111`
- RLS policies: `104`
- RLS-enabled tables: `104`
- duplicate memberships: `0`
- cross-tenant memberships: `0`

Commands used:

```powershell
python scripts/validate_db_hardening.py
python scripts/verify_day35_database.py
docker exec mdarix-r1-postgres psql -U mdarix_app -d mdarix_r1 -c "SET ROLE mdarix_runtime; ..."
```

## Local two-instance proof

`python scripts/verify_stage2_multi_instance.py` passed:

- both application instances reached health and shared the database;
- a session issued by instance 1 was reused by instance 2;
- revocation performed through instance 2 was rejected by instance 1;
- tenant context remained present;
- tenant-prefixed object storage and signed URL verification passed.

## Implementation references

- `backend/app/request_context.py`
- `backend/app/access_router.py`
- `backend/app/ai_boundary.py`
- `backend/app/controlled_export.py`
- `infrastructure/database/migrations/versions/ab44_database_hardening.py`
- `infrastructure/database/migrations/versions/ad46_customer_tenant_lifecycle.py`
- `scripts/verify_stage2_multi_instance.py`
- `tests/test_day28_lifecycle_retrieval.py`
- `tests/test_day23_governance_security.py`

## Remaining production gates

These are not claimed as complete because they require deployment-specific
infrastructure and approved credentials:

- production PostgreSQL TLS certificates and enforced encrypted connections;
- application secret cutover to `mdarix_runtime` in the deployment secret manager;
- production backup, restore, PITR, retention, and monitoring evidence;
- independent hosted multi-instance deployment evidence;
- real customer connector credentials and production endpoint validation.

The local multi-tenant blocker is validated. Production readiness remains
subject to the infrastructure gates above.
