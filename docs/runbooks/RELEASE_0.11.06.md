# Release 0.11.06 on production (mdarix.com): one navigation and persona work

Owner's go given on 19 Nov 2026 (window brought forward from 09:30 IST). Release 0.11.06 is the single release the
owner asked for: the W1e polish build, UX1 (persona work on Home), UX2 (one navigation for every organization), UX3
(investigation cockpit, Product Quality Engineer persona, persona Today screens) and the website refresh.

Running on production before the window: tag `v0.11.05`, schema `tr33inconclusive`. Everything else (VM, compose
files, the `dc` and `ro` shorthands, backup and off-site copy, rollback rules) is as in `RELEASE_0.11.05.md`.

**One database change: migration `ux2navigationnew`** (expand-only data update). It sets `tenants.navigation` to
`new` for every organization still on `classic` and prints how many it moved (6 on 19 Nov: Confidential, Galarix,
MDARIX Platform, MDARIX Validation Org, two Orbit Medical Devices organizations). The owner approved moving all
organizations on 18 Nov. Downgrade to `tr33inconclusive` only puts the column's default back to `classic`
(new organizations start on classic again); it does not move existing organizations back, because which ones were on
classic is not recorded. Set an organization back in Tenant 360 if needed.

## Checklist

| # | Step | Who | Kind |
|---|---|---|---|
| 0.1 | Owner's go recorded | OWNER | - |
| 0.2 | Disk at least 8 GB free; release `v0.11.05`, revision `tr33inconclusive` | CLAUDE | READ-ONLY |
| 0.3 | Settings copy `.env.production.pre-01106` | CLAUDE | WRITES (a copy) |
| 0.4 | Fresh backup and off-site copy (0.11.05 step 0.5), manifest check (0.6) | OWNER | WRITES |
| 1 | Check out `v0.11.06`, `MDARIX_RELEASE=v0.11.06`, build; offline config check; API import check | CLAUDE | WRITES (images) |
| 2 | **STOP: owner's OK**, then `dc up -d --wait` (migrate runs first) | OWNER says go, CLAUDE runs | WRITES (database) |
| 3 | `refresh_trial_story.py --counts`, owner's OK, `--apply` | CLAUDE, OWNER decides | READ-ONLY, then WRITES |
| 4 | Smoke checks: `/api/v1/public/version` = 0.11.06, health, site pages, one sign-in on the new navigation | CLAUDE + OWNER | READ-ONLY |
| 5 | Rollback only if needed: A (images) or B (downgrade `ux2navigationnew`) as in 0.11.05 step 10 | OWNER decides | WRITES |

## Expected results

- Step 1: `BUILD=0`, `CONFIG=0` with no output, `IMPORT=0`.
- Step 2: `migrate` exits 0 and its log names `ux2navigationnew` and the number of organizations moved; api and
  background healthy; one Alembic row `ux2navigationnew`.
- Step 3: per trial, the sample persona work (staged brief awaiting the Decision Maker, requested risk review) and the
  current SAMPLE-EV-003 wording; each trial in its own commit.
- Step 4: every organization opens on Today with the five work areas; Records & trust and Administration are in the
  avatar menu.

## Known and accepted

- Four backend tests compare the local IST date with the UTC date and fail only between 00:00 and 05:30 IST; they pass
  with the clock on UTC. Decision and effectiveness dates stay UTC days in this release (owner question open).
- Playwright was green per spec, partly on reruns after spec fixes; there was no single uninterrupted green run.
- The tag starts `release.yml`; cancel that run (no GitHub release), as for 0.11.05.
