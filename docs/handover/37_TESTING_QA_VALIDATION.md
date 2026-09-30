# Testing and Validation

## Main commands

```powershell
python -m pytest -q
npm.cmd --prefix frontend test -- --run
npm.cmd --prefix frontend run build
```

Targeted connector contract validation currently passes independently. Database-backed tests require the configured local PostgreSQL service and correct SSL mode/password.

## Test categories

- Database models and migration chain.
- Tenant isolation and governance.
- Connector contract, simulator ingestion, replay and idempotency.
- Audit, signature, MFA and policy controls.
- AI provider abstraction, deterministic fallback and structured outputs.
- Frontend component and workflow tests.
- Playwright/browser evidence where browser dependencies and authenticated fixtures are available.

## Evidence classification

Unit tests and local simulator tests validate implementation behavior. They do not prove hosted multi-instance operation, production TLS, customer connector success, production backup/PITR or regulatory certification.
