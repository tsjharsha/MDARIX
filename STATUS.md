# MDARIX R1 — current status

**Last verified:** 2026-10-02, branch `mvp/phase-3-ai`, local Windows development stack
(Docker Compose). The 2026-09-30 results are kept below for comparison. This file replaces
the earlier GO/NO-GO documents (archived in `docs/history/release-decisions/`). Update it
only from real command output.

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
- Computed-but-unused values that suggest missing logic (marked `noqa: F841`):
  deterministic evidence observations are extracted and never persisted
  (`evidence/services/evidence_service.py`); product/supplier id sets in
  `ask_mdarix/lifecycle_retrieval.py` and the unknowns map in
  `failure_chain/engine.py` are built but not used.
- Deep links to `/platform-admin/*` render the public site (public-path prefix
  match on `/platform`).

## How to re-verify

```powershell
$env:MDARIX_ENV = "test"; $env:DAY35_FIXTURE_PASSWORD = "<test-only password>"
.\.venv\Scripts\python.exe .\scripts\prepare_test_environment.py --recreate
.\.venv\Scripts\python.exe -m pytest
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
```
