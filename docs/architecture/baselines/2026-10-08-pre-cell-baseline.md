# Baseline before the cell architecture work (Phase 0.3)

Recorded 2026-10-08 so later phases can prove that nothing was lost in the `MULTI` role (ADR-013). Re-generate the
route list with the command below and compare it with `2026-10-08-api-routes.txt`; in `MULTI` it must match exactly.

| Item | Value | Source |
|---|---|---|
| Main | `c57e2d9` (PR #2 merged) | `git log` |
| Branches queued for Phase 0.1 | `mvp/docs-refresh` (2 commits) → `mvp/import-options` (3) → `mvp/p2-hardening` (13, including the *Import data* text fix) | `git log main..` |
| Alembic head | `md34rlsdefence` (one chain, root `ea1eb54290f5`) | `alembic heads` |
| API routes | 501 operations (110 under `/platform` or `/platform-admin`, 126 under `/admin/`) | `2026-10-08-api-routes.txt` |
| CI run that merged PR #2 | 17 of 17 checks green: 2,477 backend, 558 frontend, 56 browser tests; dedicated data plane, four-database routing, production stack, image scan and release gate green | STATUS.md |
| Local rerun on `mvp/p2-hardening` | backend unit selection: 1,359 passed, 4 skipped; frontend: lint, Prettier, 561 tests, build | task outputs 2026-10-08 |
| Scheduler jobs | tenant-lifecycle, subscription-lifecycle, trial-reminders, trial-retention, embedding-catch-up, operations-alerts, export-expiry, connector-sync, purge-completion, signal_detection, late_evidence_sweep, audit-chain-verification | `backend/app/scheduler.py` |
| Public tables / md_master tables | 159 / 45 | `Base.metadata` |

Route list command (run from the repository root with the project virtual environment):

```
MDARIX_ENV=local python -c "from backend.app.main import app; paths = app.openapi()['paths']; rows = sorted((m.upper(), p) for p, ops in paths.items() for m in ops); print(len(rows)); print('\n'.join(f'{m} {p}' for m, p in rows))"
```
