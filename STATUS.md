# MDARIX R1 — current status

**Last verified:** 2026-11-04 (0.10.88 final, local; section below). Before that 2026-10-08, `main` after PR #2 (`mvp/pilot-readiness-final`, merged as `c57e2d9`), CI on GitHub
Actions and the local Windows development stack (Docker Compose). Earlier results are kept below for comparison.
Update this file only from real command output.

## 2026-11-04 verified results (0.10.88 final, `fix/trial-0.10.88-journeys`, local, not pushed)

Build C's final 0.10.88: v0.10.87 merged in, the P0 fix (a story step counts only when its screen loaded), OD-2,
OD-4, backup retention, and the uploaded-data journey with the defects it found. The gates ran once on commit
0dd1449c (one test fixed after, in 2f9faf20), on `mdarix_r1_test_r3` dropped, recreated and prepared with `scripts/prepare_test_environment.py`
(`MDARIX_ENV=test`, a random `DAY35_FIXTURE_PASSWORD` for that step only). CI was not run (no push). Command results,
not a certification.

| Check | Command | Result on 0dd1449c |
|---|---|---|
| Backend suite | `python -m pytest -q -p no:cacheprovider` | Exit 1: 4,044 passed, 1 failed, 7 skipped, 4 deselected (dataplane), 1 h 12 min 57 s. The failure, `tests/test_standards_unit.py::test_each_template_names_its_basis`, expected the UK MDR 2002 template under "United Kingdom"; OD-2 names it Great Britain, as intended. The test was updated in 2f9faf20 and its file re-run alone: 15 passed. The whole suite was not run again (coordinator's instruction) |
| Python lint and format | `ruff check .`, `ruff format --check .` | Both exit 0 |
| Frontend type check | `npm run lint` | Exit 0 |
| Frontend format | `npm run format:check` | Exit 0 |
| Frontend tests | `npm test` | Exit 0; 1,556 tests in 212 files |
| Frontend build | `npm run build` | Exit 0 |
| DEV-13 load measurement (last, machine otherwise idle) | `MDARIX_TRIAL_LOAD_MEASURE=1 python -m pytest -s tests/test_trial_load_measure.py` (dc4e8959) | 1 passed in 6 min 35 s; no server error; 8 of 19 measured reads, writes and the import within target; the table is in `docs/runbooks/LOAD_AND_FAILURE_DRILLS.md` |

### The browser journeys: what each covers and how to run it

Each runs in Chrome against the API started by `scripts/journey_api.py`, which captures every e-mail into a folder
(no e-mail is sent) and refuses production, and the Vite dev server proxying `/api` to it. Synthetic people and data
only; a new trial is signed up on every run.

```
MDARIX_JOURNEY_MAIL_DIR=<mail folder> MDARIX_REQUIRE_MFA_ROLES=PLATFORM_ADMIN,CUSTOMER_ADMIN,LEADER,APPROVER   MDARIX_ENV=development MDARIX_FEATURE_SET=mvp MDARIX_APP_URL=http://127.0.0.1:5231   POSTGRES_DB=<test database> python scripts/journey_api.py --port 8121
# Vite on 5231 with /api proxied to 8121, then, in frontend/:
E2E_MAIL_DIR=<mail folder> PLAYWRIGHT_BASE_URL=http://127.0.0.1:5231   npx playwright test e2e/<spec> --project=chromium --reporter=list
```

| Spec | Covers | Result on the final code |
|---|---|---|
| `e2e/your-data-journey.spec.ts` (new) | Uploaded data, team, 1440 with a phone pass (390): a file whose most urgent complaint gives no incident country and no awareness date; Getting started switched to Your data; the country asked on the complaint page (first save lost, retried, saved once) and the awareness date in its triage form; step 1's complaint failing to load once (not ticked, no mark sent, until Retry); reload and resume at step 3; the reportable branch through the real forms with password and authenticator; a colleague's approval on a phone; a real PDF (`application/pdf`, a non-empty `%PDF-` file); submission, Records, Trends; a second upload's complaint concluded not reportable on a phone, steps 5 to 8 "Not needed", no report for it and exactly one for the first. No 5xx (one 503 on purpose excepted), no page error, ticks only in order | 4 passed (2.8 min). Its first runs found two defects, fixed in 934cb8d1 and 3403719d |
| `e2e/getting-started-journey.spec.ts` | The sample, solo at 1440: the ten steps with the authenticator, step 1's complaint failing to load once, a reload and resume, a step out of turn (409 STEP_NOT_YET, said on Getting started), a save lost and retried, the labelled practice approval. A team: the owner to Approve report, a colleague approving as the second person on a phone, the owner finishing on a phone; the team's own complaint concluded not reportable (steps 5 to 8 "Not needed"); a moved story refusing a stale step (409 STORY_MOVED) | 6 passed (9.5 min) |
| `e2e/trial-journeys.spec.ts` | Sign-up, the activation e-mail and the authenticator, Home and Getting started (desktop); a removed record and a session ending during a save; a team on a phone: invitation while e-mail is slow, an Excel upload, the colleague's activation and the retention notice; axe-core, accessible names and keyboard on every screen | 5 passed: 3 in the full run; the solo pair failed on 0.10.86's Getting started heading, fixed in 0dd1449c, then 2 passed (`-g "a solo owner"`) |

The local activation throttle ("Too many attempts", 15 minutes) stops a journey run that follows another within a
few minutes on one machine; the runs above were spaced for it.

## 2026-11-04 verified results (0.10.88 before the 0.10.87 merge, `fix/trial-0.10.88-journeys`, local, not pushed)

Build C of R2/R3 (DEV-10 journeys and accessibility, DEV-13 performance, monitoring and recovery), on 0.10.86 as
released (v0.10.86 merged in). Run on Windows on the disposable database `mdarix_r1_test_r3`, recreated and prepared
with `scripts/prepare_test_environment.py` before the gates. CI was not run (no push). Command results, not a
certification.

| Check | Command | Result |
|---|---|---|
| Backend suite | `python -m pytest` (commit 047da270) | 3,781 passed, 0 failed, 7 skipped, 4 deselected (dataplane), 42 min 35 s |
| Python lint and format | `ruff check .`, `ruff format --check .` | Both exit 0 |
| Frontend | `npm run lint`, `npm test`, `npm run build` | All exit 0; 1,488 tests in 207 files |
| Frontend format | `npm run format:check` | Exit 1 on 047da270 (one test file formatted from the repository root); fixed in ff968020, exit 0 on 7e4bf303 |
| Getting started's ten steps in the browser | `playwright test e2e/getting-started-journey.spec.ts` (Chrome, against `scripts/journey_api.py` and Vite) | 6 passed in 4 min 54 s: solo on the sample at 1440; a team with a second person approving at 390; its own data, not reportable; STEP_NOT_YET and STORY_MOVED refusals; no page error, no 5xx |
| The trial's other journeys | `playwright test e2e/trial-journeys.spec.ts` | 5 passed. The team describe first met the activation throttle ("Too many attempts", from back-to-back runs on one machine), then a check of its own that counted the status line (fixed in 047da270); passed after both |

## 2026-11-04 verified results (0.10.86, `fix/trial-0.10.86`, local, not pushed)

Run locally on Windows, each suite on its own disposable database (`mdarix_r1_test_rel86`, recreated and prepared with
`scripts/prepare_test_environment.py` before the final run). CI was not run (no push). These are command results,
not a certification.

| Check | Command | Result |
|---|---|---|
| Backend suite at 0.10.84 (5cb450e7), before the fixes | `python -m pytest` | 3,686 passed, 12 failed, 7 skipped, 4 deselected (dataplane). Each failure reproduced alone; classified in the 0.10.86 commits: 2 tests of one product defect (evidence-request downloads answered 500), 1 sample defect (the late call's S4, by weekday), 8 outdated expectations, 1 environment check too strict (database name). The embedding tests passed only because the old code downloaded the model at run time into the worktree's cache |
| Backend suite, final commit | `python -m pytest` | 3,742 passed, 0 failed, 6 skipped, 4 deselected, 1 h 14 min. Skips: 4 need `MDARIX_TEST_DATA_PLANE_URL` (a dedicated plane), 1 is a later-release scenario, 1 is the opt-in scale benchmark |
| Unit selection with no database | `MDARIX_TEST_NO_DATABASE=1 pytest -m unit` | 1,709 passed, 5 skipped, 1 failed (fixed in the next commit, then passed alone), 97 s, no database reachable |
| Markers | `pytest --collect-only` | 3,751 tests: unit 1,715, db 2,036 (4 dataplane), model 14; unit and db 0 (249 at 0.10.84) |
| Model tests with the pinned model | `MDARIX_REQUIRE_LOCAL_MODEL=1 pytest tests/test_local_embeddings.py tests/test_real_evaluation.py` | 22 passed, loaded offline from the main checkout's prepared cache; model SHA-256 51f1bd0a... equals Hugging Face's LFS oid for revision aa8f8b06 |
| Python lint and format | `ruff check .`, `ruff format --check .` | Both exit 0 |
| Frontend | `npm run lint`, `npm run format:check`, `npm test`, `npm run build` | All exit 0; 1,446 tests in 202 files |

## 2026-10-08 verified results (PR #2, `mvp/pilot-readiness-final`, merged into `main`)

The testing round ran every suite after the six-role workflow (Phases 1-7), the console redesigns and the readiness
fixes. Every failure was classified as an outdated test or a code regression; the commit messages say which.

| Check | Command | Result |
|---|---|---|
| Lint, format, build | `ruff check .`, `ruff format --check .`, `npm run lint`, `npm run format:check`, `npm run build` | All clean; build succeeds |
| Frontend unit tests | `npx vitest run` | 558 passed (68 files) in CI on the merged head `371fca3` |
| Migrations, fresh database | `alembic upgrade head`, `downgrade` 8 steps, `upgrade head`, `alembic check` | Up, down and up again; no schema drift. Before the fix, downgrades md26-md33 failed (they deleted business-ID prefixes, which the database refuses); prefixes and counters are now kept. md34 also downgrades and re-applies |
| Backend unit tests | `pytest -m unit` | 1,336 passed, 3 failed (outdated tests: renamed labels, a role code's case, the permission-coverage check); fixed and re-run green |
| Backend database tests, local | `pytest -m "db and not dataplane"` on `mdarix_r1_test` | First run 35 failed, 5 errors (outdated tests: plans now needed to sign, supplier requests need a recipient, ordering; code regressions: brief history order, audit labels, readiness rule, demo audit key). After fixes: 1,123 passed, 1 skipped, 0 failed (23 min 35 s) |
| Whole backend suite with md34, local | `pytest -m "not dataplane"` | 2,472 passed, 1 failed: a test asserting the organizations table had no row-level security (outdated by md34; fixed) |
| Backend suite, CI | `python -m pytest -q` (fresh database, runtime role under row-level security) | 2,477 passed, 5 skipped, 0 failed on `371fca3` (earlier CI runs found 7, then 1, fresh-database failures: test setup order and two timestamp ties, all fixed) |
| Dedicated data plane | `pytest tests/test_dedicated_plane.py` | 4 passed locally and in CI. Before the fix, copying organization rows to a plane failed on every plane ("pending trigger events") |
| Data-plane routing (four tenant databases) | CI job | 4 passed |
| Production stack | CI job: Caddy, TLS database, migrate, API, worker, scheduler, ClamAV; every scheduled job once; backup and restore with and without BYPASSRLS | Passed. Before the fix the scheduler was unhealthy: the legal documents were not mounted into the worker and scheduler |
| Production configuration | CI jobs "Production mode" and "Production compose definition"; `pytest tests/test_config_check.py` | Passed. The configuration check now also refuses draft legal documents and requires encrypted off-site backups and heartbeat monitors in production (69 config and environment tests pass; the CI jobs supply stand-in values) |
| Images | CI "Production image scan" (Trivy, fixable HIGH/CRITICAL fail) | Passed |
| Browser and accessibility (Playwright, desktop and phone) | CI "Browser and accessibility evidence": smoke, accessibility, every screen crawled for three personas, the invite and open-investigation flows, the golden path | 56 passed, 6 skipped (36.7 min) on `371fca3`. Earlier runs failed on outdated selectors (sortable table headers, the phone menu), on fixture organizations without products (the job now seeds them) and on an ended-session test that only cleared the browser's cookie; all fixed, none was a product fault |
| Release evidence gate | CI job that requires every gate above | Passed; all 17 checks on PR #2 green before the merge |
| Scripts under row-level security | The CI and operator scripts run as `mdarix_runtime` (subject to RLS) on a database with md34 | Fixed scripts see the 4 fixture organizations and 25 users; before the fix the same scripts saw 0 and 0 |

What changed (details in `git log` on the branch):

- The six-role investigation workflow (seven workflow roles counting Leader): signals and triage, versioned case
  scope, evidence review and requests, human judgements beside AI output, risk and regulatory reviews, the Decision
  Brief with quality review, signed decisions with password and MFA, follow-ups and late-evidence impact assessments,
  and per-case trust and audit. The pilot guide (`frontend/src/features/help/PILOT_GUIDE.md`) is rewritten around it,
  with the minimum team.
- Row-level security now also covers the organizations and customer tables (md34), and master data is writable only
  in system scope; every script and raw connection that reads them binds system scope.
  `tests/test_rls_coverage.py` fails when an organization-owned table lacks a forced policy (six reviewed exemptions).
- Platform and customer administration: customer and tenant lifecycle (suspend, reactivate; a suspended customer
  blocks its tenants), separate screens for platform users, customer administrators and customer users, sorting
  across all pages, movable and resizable columns, redesigned dashboards, Data & Integrations in ten ordered steps.
- Production gates: draft legal texts and placeholders refused; backups encrypted and off-site (or acknowledged), and
  heartbeat monitors for backups and the scheduler, required in production.

Known limits:

- Production has not been run on real infrastructure: no staging deployment, real email, restore drill on a managed
  database, end-to-end alert test or penetration test yet. No release has been tagged.
- The legal documents (privacy policy, terms, trial agreement) are drafts awaiting a lawyer; no DPA or subprocessor
  list is final.
- The default personal-data check of CSV imports misses most names ("Dr. Alan Grant", "Patient Jane Doe"). An import
  can now mask personal data (the masker every AI request uses) or set problem rows aside; making the default check
  refuse whatever the masker would change is proposed, not done.
- Four platform-only tables (onboarding requests, incidents, provisioning jobs and steps) and the session and
  data-plane routing tables have no row-level security, by reviewed exemption; three older features that look up
  accounts across organizations are blocked by row-level security and need their own fix.
- Risk and regulatory reviews have no separation-of-duties rule: the investigator may complete a review.
- No formal validation package (IQ/OQ/PQ, Part 11 traceability) exists yet.

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
  No longer offered (checked 2026-10-21 for 0.10.43, in the code and behind the release's Caddyfile): since 0.10.5 the
  website offers only the free trial. `DEMO_REQUESTS_OFFERED` is false (`frontend/src/site/offer.ts`), so no page
  links to a demo request and `/request-demo` opens the free-trial sign-up instead of the form. With
  `MDARIX_FEATURE_SET=mvp` (production) `POST /api/v1/public/demo-requests` answers 404; under `full` (the default:
  development and CI) the route still accepts a request. Since 0.10.44 Platform Admin > Identity & Access >
  Onboarding (no longer under Customers & Tenants) shows website demo requests only where the website offers them and
  the feature set serves their route (`websiteDemoRequestsOffered`, `frontend/src/app/featureSet.ts`): today under
  neither feature set. It lists the one-to-one demo requests a free trial sends from Getting started ("Free trials
  that asked for a one-to-one demo"), once there is one.
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
