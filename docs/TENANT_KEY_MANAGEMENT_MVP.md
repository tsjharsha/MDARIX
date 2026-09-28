# Tenant onboarding and key management MVP

Tenant provisioning uses an opaque tenant-bound key reference. The local
contract supports create, active-version lookup, rotation, retirement, and
cross-tenant authorization checks. Secret key material is never stored in
MDARIX or returned by the registry; a KMS/Vault adapter must resolve the
reference at runtime.

Provisioning remains idempotent at the tenant/data-plane layer. Production
database creation, managed KMS/Vault integration, automatic key rotation
schedules, and hosted token lifecycle validation require deployment services
and credentials. The synthetic MVP proves the lifecycle and isolation rules
without pretending that local metadata is a production key manager.
