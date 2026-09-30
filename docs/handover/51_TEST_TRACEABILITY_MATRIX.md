# Test Traceability Matrix

| Test family | Command/location | Purpose |
|---|---|---|
| Database | `tests/test_day2_database.py` | Schema, constraints and temporal foundations |
| Connector contract | `tests/test_api_connector_contract.py` | Retry, schema and provider failure contract |
| Simulator | `tests/test_source_simulator.py`, `test_persistent_source_simulator.py` | Provider API persistence and tenant scope |
| Ingestion | `tests/test_simulator_ingestion.py` | Outbox/idempotency boundary; needs live DB |
| Data plane | `tests/test_data_plane_routing.py` | Server-side tenant routing |
| Security/governance | `tests/test_connector_security.py` and related tests | Authorization, secrets and governance |
| Frontend | `frontend/src/**/*.test.*` | Component and route behavior |
| Browser | `frontend/e2e` and `frontend/playwright.config.ts` | Authenticated visual/accessibility workflows when browsers/fixtures exist |

Failures caused by unavailable PostgreSQL, browser downloads, provider credentials or hosted infrastructure must be reported as environment blockers rather than silently converted into passes.
