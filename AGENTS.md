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
- Frontend screens: `frontend/src/features/<area>/`. `main.tsx` only boots the
  app; the authenticated shell and view routing are in `app/App.tsx`, shared
  types in `app/types.ts`. Use `app/apiClient.ts` (`requestJson`) for new API
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

## Database rules (every new migration and model)

- Timestamps are `DateTime(timezone=True)`; JSON is `JSONB`.
- A reference between tenant tables is composite, `(tenant_id, x_id) -> (tenant_id, id)`, and the target has
  `UniqueConstraint("tenant_id", "id")`. The tenant reference column is always named `tenant_id`.
- Every foreign key has an index led by its columns; every tenant table has an index that starts with `tenant_id`.
- Business uniqueness on a tenant table starts with `tenant_id`.
- A new tenant table gets the forced `mdarix_tenant_isolation` row-level security policy in the same migration.
- A new numbered object goes in `LATER_OBJECTS` with `scope="tenant"`; never `allocate_business_id`.
- A column default satisfies the column's CHECK.
- Migrations are expand-only; a downgrade removes only what its migration added; `alembic heads` shows one head.
- Imports commit in batches; never hold a business-ID counter or audit-chain lock across a long loop.

## Regulated records and approvals

- Regulated records are never hard-deleted outside the retention policy.
- No production data in tests, fixtures or samples; sample data stays synthetic.
- Never commit, push or deploy without the owner's approval.
- A test or check is reported PASS only when it was executed and seen to pass.
- AI suggests; a person decides and signs.

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
