# Testing and Validation

## Main commands

```powershell
$env:MDARIX_ENV = "test"; $env:DAY35_FIXTURE_PASSWORD = "<test-only password>"
python scripts/prepare_test_environment.py --recreate   # builds mdarix_r1_test
python -m pytest -q                  # unit + db tests (data-plane tests excluded)
python -m pytest -q -m unit          # no database required
python -m pytest -q -m dataplane     # opt-in: needs the four tenant data planes
npm.cmd --prefix frontend test -- --run
npm.cmd --prefix frontend run build
```

Local runs use the dedicated `mdarix_r1_test` database (set in `tests/conftest.py`) and never the demo database; tests never call Groq or Resend with developer credentials unless `MDARIX_TEST_ALLOW_LIVE_PROVIDERS=1`. The golden AcmeCare dataset is loaded on demand, so test order does not matter. Current results are recorded in `STATUS.md`.

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
