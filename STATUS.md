# MDARIX R1 — current status

**Last verified:** 2026-10-03, branch `mvp/admin-console-areas`, local Windows development stack (Docker Compose). Earlier results
are kept below for comparison. Update this file only from real command output.

## 2026-10-03 verified results (branch `mvp/admin-console-areas`)

| Check | Command | Result |
|---|---|---|
| Backend tests | `python -m pytest` on `mdarix_r1_test` | 793 passed, 1 failed, 4 deselected (21 min 28 s). The failure was a test pinned to exactly seven investigations on the demo product while end-to-end runs had opened more; it now checks the seeded cases (21/21 in that file pass) |
| Lint / format | `ruff check .`, `ruff format --check .`, `npm run lint`, `npm run format:check` | All clean |
| Frontend | `npx vitest run`, `npm run build` | 78 tests passed; build succeeds |
| Migrations | `alembic upgrade head` on the test and dev databases; `downgrade -1` and back on test | Both at `md11masterseedv2`; md10 downgrades and re-applies |
| Dedicated data planes | `scripts/upgrade_data_planes.py --apply`, then a dry run | Before: 4 tables and 29 columns missing on each of the four planes. After: 0 and 0; schema version recorded |
| Simulated customer systems | `docker compose up -d --build` (14 simulators), then `scripts/load_source_templates.py --tenant E2E_DEMO` | All 14 healthy; a separate database per tenant created in all 11 systems; 36 template files loaded, none refused |
| Live connector run | One-off script (not in the repository, so not reproducible from it); the same path is covered by `tests/test_standard_mappings.py`, `tests/test_trackwise_integration_path.py` and `tests/test_connector_sync.py` | Recorded result at the time, 358/358 checks: all 39 standard mappings created, approved by a second administrator, released, connected with an encrypted API key, synced and imported; complaint list shows severity and safety flags; CAPAs and suppliers present; Ask MDARIX answered from the imported records (lots L24-0815 and L24-0902, citations verified) |
| Standard mappings, offline | `pytest tests/test_standard_mappings.py` | 41 passed: every standard mapping passes the release check, and loading every template in order imports the whole story |
| Screen crawl (Playwright, `e2e/deep-crawl.spec.ts`) | One persona at a time against the dev server | Platform admin 51 screens, two customer admins 28 each, investigator, viewer, investigator (AcmeCare) and approver with MFA 69 + 61 + 53 + 53: 0 issues. Both form flows (invite a user, open an investigation) pass. Found and fixed: a duplicate React key in Product 360 suppliers, and nested `main` landmarks in the admin consoles. The admin consoles have not yet been re-crawled after the landmark fix |
| Request a demo | `pytest tests/test_demo_requests.py tests/test_business_permissions.py tests/test_public_signup_onboarding.py`; browser run at 1440 and 390 px | 18 passed. Form submits, thank-you shown, no console errors, no sideways scroll; request listed for the Platform Admin and marked contacted (first browser run; a later retest of that step hit "Failed to fetch" while the backend suite shared the test database, and is to be repeated) |
| Backend tests after these changes | `python -m pytest` on `mdarix_r1_test` | First run (`-x`): 683 passed, then `test_outbox_worker_publishes` failed: it assumed an empty outbox and published only one batch of 50 behind earlier events; it now runs batches until its event is published. Rerun: 804 passed, 0 failed. After trial feedback was added: 810 passed, 0 failed (14 min 46 s) |
| Migrations md12, md13 | `alembic upgrade head`, `downgrade -1`, `upgrade head` on test; `upgrade head` on dev | Both at `md13trialfeedback` |
| Trial feedback | `pytest tests/test_trial_feedback.py`; browser run against the API on the test database | 6 tests pass (trial only, named and anonymous credit, private never published, withdrawal unpublishes, list values enforced, another person's feedback untouched). Browser: invitation shown to a trial user; questionnaire sent; an anonymous quote naming the company refused; invitation gone after sending; Platform Admin read and published it; the home page showed it credited "Regulatory affairs lead, medical-device company" without the company name |
| Request a demo, admin step | Browser run after the backend suite | Request listed for the Platform Admin, marked contacted, shown under Contacted. The earlier "Failed to fetch" was the dev server having stopped |

What changed (details in `git log`):

- Each tenant has its own database and API key in every simulated customer system; CSV upload API and page.
- 14 more record types import (components, suppliers, sites, BOM, approved suppliers, lot genealogy, changes,
  requirements, risks, failure modes, controls, investigations, evidence, CAPAs); complaints keep regulatory
  details. Mappings can filter rows and set fixed values; 39 standard mappings ship with the templates.
- Connectors keep the customer system's API key encrypted. Imported records are searchable by Ask MDARIX and the
  investigator.
- Supplier evidence requests are limited to the tenant's suppliers and cases, refuse links and are rate limited.
- Every dialog takes focus, closes with Escape and returns focus (it blocked the page before).
- Website: MedTech standards, connected-systems flow, example investigation charts; corrected two inaccurate
  claims about data isolation and credentials.
- Website: an animated lifecycle loop is the Product Lifecycle hero; the design-phases picture moved to its own
  section on that page.
- Request a demo: its own page in the sign-in frame (name, work email, phone), stored in `demo_requests` and listed
  for Platform Admins (Customers & Tenants > Onboarding) to mark contacted or closed; validated, rate limited, with an
  optional email alert. Start free trial is unchanged.
- Each admin page has one `main` landmark (the consoles nested up to three).
- Trial feedback: a trial workspace invites feedback (banner, "Not now" for three days) and has a Share feedback
  page: ratings, likelihood to recommend, features tried, what is good, what to improve, adoption, and consent to
  show a quote with the company's name, anonymously, or not at all. The consent wording is stored with the answer
  and can be withdrawn. Platform Admins read responses (Customers & Tenants > Feedback) and publish consented
  quotes; the home page shows published quotes, credited as the person chose. Migration md13 (`trial_feedback`,
  row-level security).

Known limits:

- Production has not been run: HTTPS, real email, backups, monitoring, load and a penetration test are untested.
- No formal validation package (IQ/OQ/PQ, Part 11 traceability) exists yet.
- AI runs on free provider tiers, which must not receive real customer data.
- Dedicated data planes are kept in line by script, not by Alembic; tenant-admin dashboards
  (`access/observability.py`) and platform product configuration still read the control database.

## 2026-10-02 verified results (branch `mvp/phase-3-ai`)

| Check | Command | Result |
|---|---|---|
| Backend tests | `python -m pytest` on a freshly recreated `mdarix_r1_test` (`prepare_test_environment.py --recreate`) | 609 passed, 0 failed, 4 data-plane tests deselected (9 min 10 s) |
| Lint / format | `ruff check .`, `ruff format --check .` | All checks passed; 849 files formatted |
| Frontend | `npm run lint`, `npm test`, `npm run build`, `npm run format:check` | lint clean; 47 tests passed; build succeeds; formatted |
| Runtime database role | `scripts/configure_runtime_role.py` | `mdarix_runtime`: login, not superuser, no RLS bypass |
| Browser golden path (demo tenant, live Groq model) | sign in as the demo investigator; analysis, hypotheses, challenges, brief on ACD-INV-101; then Ask, Trust and the viewer in a second run (the dev server stopped during the first) | All steps completed; the AI wrote analysis, hypotheses, challenges and brief; the viewer sees no run buttons; the second run logged 0 console errors or warnings |
| Honest golden evaluation | `scripts/run_real_evaluation.py --record` | Last run with the model available for all 12 (2026-10-01 UTC, committed in `artifacts/real-golden-evaluation.json`): 8/12, all 12 written by the model, 1 of the 4 scenarios with specific expectations (VS001). One of the failures (VS002) was the checker's false positive on "does not prove", fixed since. Later runs that day hit the Groq daily limit and fell back to the rules (see below). VS002-VS012 use placeholder evidence |

What changed on this branch (details in `git log`):

- Evidence search uses a local language-model embedding (bge-small, 384 dimensions); evidence text is not sent
  out for indexing.
- The language model writes the investigation analysis, competing hypotheses, challenges and the brief; MDARIX
  rules drop uncited, invented or causal statements and fall back to the rule engines when the model is
  unavailable. Ask MDARIX answers from the tenant's evidence search and checks its citations.
- The golden evaluation scores the real pipeline (it previously scored a canned answer) and is shown on the
  Trust page.
- The demo runs in its own tenant (`ACMECARE_DEMO`) with a curated synthetic story; the golden tenant is used
  for evaluation only.
- The interface hides actions the role may not take (the server still enforces them).
- The investigation workspace built its relationship graph for a default tenant; it now uses the case's tenant.

Known limits found in this pass:

- The Groq free plan in use allows 8,000 tokens per minute and 200,000 per day (both reached on 2026-10-02:
  "tokens per day (TPD): Limit 200000, Used 199752"). Groq counts each request's output allowance, so quick
  successive AI actions fall back to the rule engines, and a few full evaluations use the day's budget. A pitch or
  pilot needs a paid tier or another provider.
- The golden dataset is thin: only VS001 has real evidence behind its expectations.

## 2026-09-30 verified results (branch `cleanup/codebase-step1-step2`)

## Verdict

Internal **synthetic demo** only. Not ready for a design-partner pilot or
production: several security issues below must be fixed first.

## Verified results

| Check | Command | Result |
|---|---|---|
| Backend tests (unit + db) | `python -m pytest` on a freshly recreated `mdarix_r1_test` | 466 passed, 0 failed, 4 data-plane tests deselected (includes Master Data v1) |
| Backend unit tests only | `python -m pytest -m unit` (no database) | 253 passed |
| Frontend unit tests | `npm --prefix frontend test` | 14 passed (3 files) |
| Frontend production build | `npm --prefix frontend run build` | Succeeds (single 668 kB JS chunk, size warning) |
| Data-plane tests | `python -m pytest -m dataplane` | Not run in this pass (need registered tenant data planes; they write to them) |
| Browser: public site | `playwright test e2e/public-shell.spec.ts --project=chromium` | 3 passed (load, keyboard/axe critical, every header/footer link) |
| Browser: authenticated app | `browser-evidence.spec.ts`, each test run individually against the local stack | 4 passed, 2 skipped (need `E2E_CUSTOMER_ADMIN_EMAIL`), 7 failed; the same 7 fail on the code before this cleanup (stale assertions for the Simplified admin screen and older copy) |
| CI (GitHub Actions) | `.github/workflows/ci.yml` | Not re-run for this branch |

Before this cleanup the same suite on a fresh database gave 443 passed, 12
failed, 13 errors (stale fixtures, hard-coded UUIDs, order dependence and a lost
golden source file).

## Known issues listed on 2026-09-30

Items marked *addressed* were fixed in the named commit; the others have not been re-verified since.

Security / correctness (confirmed in code on 2026-09-30):

1. Privilege escalation: `backend/app/access/authz._is_platform_admin` treats the role
   strings `ADMINISTRATOR`/`ADMIN` as platform admin, and customer admins can
   assign those roles (including to themselves via the generic control-plane
   PATCH).
2. `governance_router.bootstrap()` runs on every governance call and grants the
   default `Viewer` role signing authority plus the Ask and signature
   entitlements.
3. Decision Center takes `authorized_by_ref` / `reviewer_ref` from the request
   body; the UI hard-codes `CONTROLLED_DEVELOPMENT_REVIEWER`.
4. Connector `credential_ref` can name any server environment variable and the
   endpoint is admin-controlled (secret exfiltration / SSRF). *Addressed: 8a0e7fd.*
5. `provision_tenant`: retry on an existing tenant raises `UnboundLocalError`;
   new tenants call `send_activation_email` with a missing argument.
6. Several queries compare `Tenant.status == "active"` while the schema only
   allows upper-case statuses.
7. `GET /api/v1/admin/tenant/lifecycle` returns 500: it reads
   `Tenant.lifecycle_status`, which does not exist (reproduced 2026-09-30).
8. RLS is not effective at runtime (superuser connection; `app.tenant_id` is
   set transaction-locally and committed before handler queries). *Addressed: b4a4f14.*
9. Evidence file references resolve against the repository root. *Addressed: a10b463.*

Architecture gaps:

- Decisions are created in the tenant data plane but signed in the control
  plane (sign returns 404 for UI-created decisions); audit is split across both.
  *Addressed: 984ed59.*
- Provider/simulator records stop at the connector ledger and never reach
  canonical tables; product views are fed by the file-based golden pipeline.
- Most investigation "AI" is deterministic templates; retrieval uses 32-dim
  hash embeddings; the golden evaluation grades a canned answer unless real
  outputs are supplied. *Addressed on `mvp/phase-3-ai` (see above).*
- No reachable UI creates roles, permission sets, personas, connectors,
  approval authorities or SoD policies (backend routes exist).
- Computed-but-unused values (formerly marked `noqa: F841`): reviewed and
  removed. The deterministic observations were saved all along (the extractor
  adds them to the session); the lifecycle retrieval is already scoped through
  the product's versions and components; the failure chain reads the unknowns
  directly. *Addressed in the readiness work (phase 10).*
- Deep links to `/platform-admin/*` render the public site (public-path prefix
  match on `/platform`). *Addressed: the application is matched by whole path
  segments (`/app`, `/platform-admin`); every other address is the website.*

## How to re-verify

```powershell
$env:MDARIX_ENV = "test"; $env:DAY35_FIXTURE_PASSWORD = "<test-only password>"
.\.venv\Scripts\python.exe .\scripts\prepare_test_environment.py --recreate
.\.venv\Scripts\python.exe -m pytest
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
```
