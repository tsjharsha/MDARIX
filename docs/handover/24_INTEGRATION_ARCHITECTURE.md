# Integration Architecture

## Connector families

| Family | Validation provider | Port | Status |
|---|---|---:|---|
| QMS/complaints | TrackWise | 8101 | Synthetic simulator |
| PLM | PLM / Teamcenter | 8102 / 8106 | Synthetic simulator |
| ERP | ERP / Oracle Fusion | 8103 / 8107 | Synthetic simulator |
| Supplier | Supplier / Coupa | 8104 / 8108 | Synthetic simulator |
| QMS | Veeva Vault QMS | 8105 | Synthetic simulator |

Each simulator has its own PostgreSQL database and service. MDARIX communicates through an authenticated API, never through simulator tables.

## Contract

Health, readiness, schema, bounded records, record history and source-record write endpoints are implemented. The shared client now resolves all eight providers and supports bounded retryable pages, schema reads and tenant-scope validation.

## Durable ingestion

The ingestion boundary creates a connector run, source-record ledger entries and outbox events. Idempotency uses tenant, provider, entity, external ID, version and payload fingerprint. Duplicate records remain observable and do not create a second source identity.

## Not real customer integration

These are synthetic validation providers. Customer endpoint URLs, authentication schemes, schemas, credentials, rate limits, retention and ownership rules must be configured separately for a real design partner.
