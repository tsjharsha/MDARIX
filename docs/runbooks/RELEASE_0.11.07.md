# Release 0.11.07 on production (mdarix.com): the application on wide screens, its new look and the website

Release 0.11.07 changes only what people see. In the application: the work canvas uses wide screens (fluid to
1680 px, centred beside the rail; it was capped at 1340 px and pinned left), the 0.11.07 palette, the story rail
(Today > Cases > Investigations > Products > Decisions & Reports), a compact hero band per page with key figures,
calm motion (none with reduced motion), and a phone fix (the Cases list no longer scrolls sideways). On the website:
the refreshed home, platform and story pages with the application's own screens (captured from a free trial's sample
data) and the animated story card, which now sits under the screenshot instead of over it.

Running on production before the window: tag `v0.11.06`, schema `ux2navigationnew`. Everything else (VM, compose
files, the `dc` and `ro` shorthands, backup and off-site copy, rollback rules) is as in `RELEASE_0.11.05.md`.

**No database change.** There is no new Alembic revision: the head stays `ux2navigationnew` (checked with
`alembic heads` on the release commit). The `migrate` service still runs at start-up and finds nothing to do.

## Checklist

| # | Step | Who | Kind |
|---|---|---|---|
| 0.1 | Owner's go recorded | OWNER | - |
| 0.2 | Disk at least 8 GB free; release `v0.11.06`, revision `ux2navigationnew` | CLAUDE | READ-ONLY |
| 0.3 | Settings copy as in 0.11.06 step 0.3, with the suffix `pre-01107` | CLAUDE | WRITES (a copy) |
| 0.4 | Fresh backup and off-site copy (0.11.05 step 0.5), manifest check (0.6), even with no database change | OWNER | WRITES |
| 1 | Check out `v0.11.07`, `MDARIX_RELEASE=v0.11.07`, build; offline config check; API import check | CLAUDE | WRITES (images) |
| 2 | **STOP: owner's OK**, then `dc up -d --wait` (migrate runs first and changes nothing) | OWNER says go, CLAUDE runs | WRITES (restart) |
| 3 | Smoke checks: `/api/v1/public/version` = 0.11.07, health, site home and platform pages, one sign-in on a trial: Today, Cases and the cockpit at 1920 and 1440 | CLAUDE + OWNER | READ-ONLY |
| 4 | Rollback only if needed: A (images, back to `v0.11.06`) as in 0.11.05 step 10; there is no database change to roll back | OWNER decides | WRITES |

## Expected results

- Step 0.2: one Alembic row `ux2navigationnew`.
- Step 1: `BUILD=0`, `CONFIG=0` with no output, `IMPORT=0`.
- Step 2: `migrate` exits 0 with no upgrade in its log; api and background healthy; still one Alembic row
  `ux2navigationnew`.
- Step 3: the version reads 0.11.07; the home hero shows the story card under the screenshot, not over it; on a 1920
  screen the application's content is centred with no empty band on the right; the rail shows the five work areas with
  their story lines.

## Known and accepted

- Four backend tests compare the local IST date with the UTC date and fail only between 00:00 and 05:30 IST; the gate
  ran with the clock on UTC. Decision and effectiveness dates stay UTC days (owner question open).
- The tag starts `release.yml`; cancel that run (no GitHub release), as for 0.11.05 and 0.11.06.
