# MDARIX R1 — current status

**Last verified:** 2026-09-30, branch `cleanup/codebase-step1-step2`, local Windows
development stack (Docker Compose). This file replaces the earlier GO/NO-GO
documents (archived in `docs/history/release-decisions/`). Update it only from
real command output.

## Verdict

Internal **synthetic demo** only. Not ready for a design-partner pilot or
production: several security issues below must be fixed first.

## Verified results

| Check | Command | Result |
|---|---|---|
| Backend tests (unit + db) | `python -m pytest` on a freshly recreated `mdarix_r1_test` | 458 passed, 0 failed, 4 data-plane tests deselected |
| Backend unit tests only | `python -m pytest -m unit` (no database) | 253 passed |
| Frontend unit tests | `npm --prefix frontend test` | 14 passed (3 files) |
| Frontend production build | `npm --prefix frontend run build` | Succeeds (single 668 kB JS chunk, size warning) |
| Data-plane tests | `python -m pytest -m dataplane` | Not run in this pass (need registered tenant data planes; they write to them) |
| Browser / Playwright e2e | `npm --prefix frontend run test:e2e` | Not run in this pass; the spec contains stale selectors for the Simplified admin screen |
| CI (GitHub Actions) | `.github/workflows/ci.yml` | Not re-run for this branch |

Before this cleanup the same suite on a fresh database gave 443 passed, 12
failed, 13 errors (stale fixtures, hard-coded UUIDs, order dependence and a lost
golden source file).

## Known issues to fix before any design partner uses the system

Security / correctness (confirmed in code):

1. Privilege escalation: `access_router._is_platform_admin` treats the role
   strings `ADMINISTRATOR`/`ADMIN` as platform admin, and customer admins can
   assign those roles (including to themselves via the generic control-plane
   PATCH).
2. `governance_router.bootstrap()` runs on every governance call and grants the
   default `Viewer` role signing authority plus the Ask and signature
   entitlements.
3. Decision Center takes `authorized_by_ref` / `reviewer_ref` from the request
   body; the UI hard-codes `CONTROLLED_DEVELOPMENT_REVIEWER`.
4. Connector `credential_ref` can name any server environment variable and the
   endpoint is admin-controlled (secret exfiltration / SSRF).
5. `provision_tenant`: retry on an existing tenant raises `UnboundLocalError`;
   new tenants call `send_activation_email` with a missing argument.
6. Several queries compare `Tenant.status == "active"` while the schema only
   allows upper-case statuses.
7. RLS is not effective at runtime (superuser connection; `app.tenant_id` is
   set transaction-locally and committed before handler queries).
8. Evidence file references resolve against the repository root.

Architecture gaps:

- Decisions are created in the tenant data plane but signed in the control
  plane (sign returns 404 for UI-created decisions); audit is split across both.
- Provider/simulator records stop at the connector ledger and never reach
  canonical tables; product views are fed by the file-based golden pipeline.
- Most investigation "AI" is deterministic templates; retrieval uses 32-dim
  hash embeddings; the golden evaluation grades a canned answer unless real
  outputs are supplied.
- No reachable UI creates roles, permission sets, personas, connectors,
  approval authorities or SoD policies (backend routes exist).
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
