# MDARIX automated validation

The repeatable validation layers are:

0. Copy `.env.test.example` to a test-only environment and run `python scripts/run_validation.py`.
1. `python scripts/validate_local_stack.py` records local service reachability without exposing secrets.
2. `alembic upgrade head` validates the migration chain against the configured PostgreSQL instance.
3. `python -m pytest -q` runs backend, tenant-isolation, connector, audit, AI, and worker tests.
4. `npm.cmd --prefix frontend run build` validates the frontend production build.
5. `npm.cmd --prefix frontend test -- --run` runs frontend unit tests.
6. `npm.cmd --prefix frontend run test:e2e` runs Chromium and mobile-shell browser checks and writes screenshots/reports under `artifacts/`.

The automated checks do not claim production validation. Production TLS, runtime-role cutover,
backup/PITR, monitoring, real provider credentials, and multi-instance deployment remain explicit
environment gates and are reported rather than silently marked passed.

The test bootstrap refuses database writes unless `MDARIX_ENV=test`. CI credentials are supplied by
the isolated workflow/service environment; production secrets must never be placed in source control.
