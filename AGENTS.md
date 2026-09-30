# Working on MDARIX R1

Conventions for everyone changing this repository, human or AI assistant.
Read [README.md](README.md) for layout and setup and [STATUS.md](STATUS.md) for
the verified current state and known issues.

## Where code goes

- API routes: `backend/app/` routers mounted in `backend/app/main.py`. Access,
  administration and platform endpoints live in `backend/app/access/<domain>.py`
  (aggregated by `access_router.py`); authorization helpers are in
  `backend/app/access/authz.py`. Put new routes in the module for their domain.
- Domain logic: the matching top-level package (`retrieval/`, `evidence/`,
  `investigator/`, `failure_chain/`, ...). No new top-level packages or
  root-level modules without a reason recorded in the commit message.
- Database schema: SQLAlchemy models in `backend/app/db/models/` plus an Alembic
  migration in `infrastructure/database/migrations/versions/` for every change.
- Frontend screens: `frontend/src/features/<area>/`. Keep `main.tsx` to routing
  and the application shell. Use `app/apiClient.ts` (`requestJson`) for new API
  calls instead of raw `fetch`.
- Scripts: `scripts/`. Documentation: see `docs/README.md`; `docs/history/` is an
  archive and must not be edited to describe the present.

## Naming

- Never name new modules, routers, classes, env vars or feature flags after a
  day, stage, part or package number (`day14_`, `DAY31_`, `stage3_`...). Name
  them after what they do. Existing persisted identifiers (orchestration
  versions, audit action codes) stay as they are because stored data uses them.

## Security and tenancy rules

- The tenant and the acting user come only from the authenticated request
  context (`get_request_context` -> `ctx.tenant_id`, `ctx.user_id`). Never take
  a tenant id, actor, reviewer or signer from the request body or query string.
- Tenant business data uses `get_data_plane_db`; identity, tenancy, plans,
  configuration and platform audit use the control plane (`get_db`).
- Authorization is enforced on the server. Hiding a menu item is not a control.
- Never commit secrets or personal data. `.env` stays local; tests and e2e
  specs read credentials from environment variables.

## Tests

- Every behaviour change ships with a test that fails without the change.
- Run before committing:
  `python -m pytest` (uses `mdarix_r1_test`, see README), `python -m ruff check .`,
  `python -m ruff format --check .`, and in `frontend/`: `npm run lint`,
  `npm run format:check`, `npm test`, `npm run build`.
- Tests never touch the demo database (`mdarix_r1`) and never call Groq or
  Resend with developer credentials (`tests/conftest.py` enforces both).
- Prefer behavioural tests over tests that grep source files. A static test
  must target code a user can actually reach.

## Formatting

- Python: `ruff format` (config in `ruff.toml`, 120 columns).
- Frontend: `prettier` (config in `frontend/.prettierrc.json`, 120 columns).
- Pure formatting goes in its own commit and into `.git-blame-ignore-revs`.

## Status and evidence

- Update `STATUS.md` only from real command output, with the date. Do not add
  new GO/NO-GO or "complete" reports; state what was run and what it showed.
- Remove dead code instead of commenting it out.
