# MDARIX R1

MDARIX is a medical-device investigation and decision-intelligence platform: a
*system of intelligence* that sits above QMS, PLM, ERP, MES and supplier systems,
reconstructs product and temporal context, and helps investigators work through
evidence, competing explanations and unknowns while a human keeps decision
authority.

This repository is the **internal synthetic MVP**. It runs on synthetic tenants,
seeded data, eight provider simulators and local Docker infrastructure. Real
customer integrations, hosted production operations and compliance
certification are out of scope. Current verified state: [STATUS.md](STATUS.md).

## Repository layout

| Path | What lives there |
|---|---|
| `backend/app/` | FastAPI application: routers, request context, auth/admin API, DB models and sessions |
| `infrastructure/database/` | Alembic migrations and database validation scripts |
| `ai/`, `genai/`, `retrieval/`, `evidence/`, `graph/` | Evidence extraction, LLM provider abstraction, retrieval, reality graph |
| `investigation_workspace/`, `investigator/`, `hypothesis_engine/`, `challenger/`, `unknowns/`, `failure_chain/`, `scenario_intelligence/`, `counterfactual/`, `briefs/`, `decision_center/` | Investigation intelligence services |
| `trust_engine/`, `evaluation/`, `validation/` | Assurance checks, golden-scenario evaluation, CSA package generation |
| `ask_mdarix/`, `regulatory_intelligence/` | Ask MDARIX interpretation/retrieval, regulatory drafting and eSTAR preparation |
| `auth/`, `access_control/`, `security/` | Local auth service, policy/persona/entitlement helpers, security contracts |
| `ingestion/`, `integration/`, `source_simulator/`, `outbox/` | File ingestion + normalization, provider connector contract, simulators, outbox worker |
| `communication/`, `object_storage/`, `reports/` | Email (Resend), object storage, report/export rendering |
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
copy .env.example .env                      # then fill in local values; never commit .env
docker compose up -d                        # control plane, 4 tenant data planes, simulators, worker, Mailpit, MinIO
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\scripts\check_database_connection.py
$env:MDARIX_DB_HARDENING_APPLY = "1"         # the hardening migration is opt-in and required to reach head
.\.venv\Scripts\python.exe -m alembic upgrade head
```

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
