# MDARIX R1

MDARIX is a medical-device investigation and decision-intelligence platform: a
*system of intelligence* that sits above QMS, PLM, ERP, MES and supplier systems,
reconstructs product and temporal context, and helps investigators work through
evidence, competing explanations and unknowns while a human keeps decision
authority.

Locally it runs on synthetic tenants, seeded data, 14 provider simulators and
Docker infrastructure. Production deployment for design-partner pilots (one VM
with Docker Compose and a managed PostgreSQL) is documented in
[docs/runbooks/DEPLOYMENT.md](docs/runbooks/DEPLOYMENT.md). No compliance
certification is claimed. Current verified state: [STATUS.md](STATUS.md).

## Repository layout

| Path | What lives there |
|---|---|
| `backend/app/` | FastAPI application: routers, request context, auth/admin API (`access/`), Master Data read model (`master_data/`), DB models and sessions |
| `infrastructure/database/` | Alembic migrations, Master Data seeds (`seeds/`) and database validation scripts |
| `ai/`, `genai/`, `retrieval/`, `evidence/`, `graph/` | Evidence extraction, LLM provider abstraction, retrieval, reality graph |
| `investigation_workspace/`, `investigator/`, `hypothesis_engine/`, `challenger/`, `unknowns/`, `failure_chain/`, `scenario_intelligence/`, `counterfactual/`, `briefs/`, `decision_center/` | Investigation intelligence services |
| `trust_engine/`, `evaluation/`, `validation/` | Assurance checks, golden-scenario evaluation, CSA package generation |
| `ask_mdarix/`, `regulatory_intelligence/` | Ask MDARIX interpretation/retrieval, regulatory drafting and eSTAR preparation |
| `auth/`, `access_control/`, `security/` | Local auth service, policy/persona/entitlement helpers, security contracts |
| `ingestion/`, `integration/`, `source_simulator/`, `outbox/` | File ingestion + normalization, provider connector contract, simulators, outbox worker |
| `communication/`, `object_storage/`, `reports/` | Optional inbound evidence email (Resend webhooks), object storage, report/export rendering. All outgoing email is SMTP (`auth/emailer.py`) |
| `data/golden/` | Deterministic synthetic dataset (AcmeCare) and its generator |
| `frontend/` | React/Vite app: public website, Platform/Customer admin, investigator workspace |
| `tests/` | Backend test suite (see *Tests*) |
| `scripts/` | Setup, seeding, data-plane, validation and evidence scripts |
| `docs/` | Documentation — start at [docs/README.md](docs/README.md) |
| `artifacts/` | Generated validation evidence (not source) |

## Local setup (Windows)

Prerequisites: Docker Desktop, Python 3.13 with a virtual environment at `.venv`,
Node.js/npm, Git. MDARIX uses `pg8000` for PostgreSQL (psycopg's native DLL is
blocked by Windows Application Control on the development machine).

```powershell
copy .env.example .env                      # keep MDARIX_ENV=development; fill in local values; never commit .env
docker compose up -d                        # control plane, 4 tenant data planes, simulators, worker, Mailpit, MinIO
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\scripts\check_database_connection.py
$env:MDARIX_DB_HARDENING_APPLY = "1"         # the hardening migration is opt-in and required to reach head
.\.venv\Scripts\python.exe -m alembic upgrade head
# The API runs as the least-privilege role: set MDARIX_DB_RUNTIME_PASSWORD (24+ characters) in .env first
.\.venv\Scripts\python.exe .\scripts\configure_runtime_role.py
```

Create accounts to sign in with (synthetic passwords of 12+ characters, local only):

```powershell
# Fixture organizations and users r1-user-NN@synthetic.invalid
$env:DAY35_FIXTURE_APPLY = "1"; $env:DAY35_FIXTURE_PASSWORD = "<local password>"
.\.venv\Scripts\python.exe .\scripts\provision_day35_fixture.py
# AcmeCare demo workspace and its team (investigator@acmecare-demo.invalid, admin@acmecare-demo.invalid, ...)
$env:MDARIX_DEMO_PASSWORD = "<local password>"
.\.venv\Scripts\python.exe .\scripts\demo_tenant.py setup
```

Mailpit captures mail sent to its SMTP port 1025; read it at http://127.0.0.1:8025.

Run the API and the web app:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8007
npm.cmd --prefix frontend install
npm.cmd --prefix frontend run dev            # http://127.0.0.1:5177 (proxies /api to :8007)
```

Tenant data planes are registered and populated by the scripts in `scripts/`
(`initialize_data_planes.py`, `expand_data_plane_schema.py`,
`register_mvp_data_planes.py`); see
[docs/architecture/CURRENT_DATABASE_ARCHITECTURE.md](docs/architecture/CURRENT_DATABASE_ARCHITECTURE.md).

## Tests

The backend suite runs against a dedicated `mdarix_r1_test` database, never the
demo database, and never calls Groq or Resend with your `.env` credentials.

```powershell
# one-time (or --recreate to rebuild): migrate, load golden data, fixtures, demo seed
$env:MDARIX_ENV = "test"; $env:DAY35_FIXTURE_PASSWORD = "<test-only password>"
.\.venv\Scripts\python.exe .\scripts\prepare_test_environment.py --recreate

.\.venv\Scripts\python.exe -m pytest                 # unit + database tests
.\.venv\Scripts\python.exe -m pytest -m unit         # fast, no database needed
.\.venv\Scripts\python.exe -m pytest -m dataplane    # opt-in: needs the tenant data planes

npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
```

Markers are assigned automatically in `tests/conftest.py`: `unit` (no database),
`db` (control-plane test database) and `dataplane` (also needs the four tenant
databases; excluded by default).

## Conventions

Engineering conventions for people and AI assistants are in
[AGENTS.md](AGENTS.md) (imported by [CLAUDE.md](CLAUDE.md)).
