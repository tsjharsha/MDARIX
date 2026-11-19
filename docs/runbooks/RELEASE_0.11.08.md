# Release 0.11.08 on production (mdarix.com): the Questions pages in the website's look

Release 0.11.08 changes only the public website: the Questions and answers index and its seven answer pages open with
the same dark page band as Product, Trust and Company (breadcrumb, eyebrow, heading and summary inside it). The band is
one shared component (`frontend/src/site/hero.tsx`). No application screen, API or database change.

Running on production before the window: tag `v0.11.07`, schema `ux2navigationnew`. Everything else (VM, compose
files, the `dc` and `ro` shorthands, backup and off-site copy, rollback rules) is as in `RELEASE_0.11.07.md`.

**No database change.** No new Alembic revision; the head stays `ux2navigationnew`.

## Checklist

| # | Step | Who | Kind |
|---|---|---|---|
| 0.1 | Owner's go recorded | OWNER | - |
| 0.2 | Disk at least 8 GB free; release `v0.11.07`, revision `ux2navigationnew` | OWNER (commands from Claude) | READ-ONLY |
| 0.3 | Settings copy with the suffix `pre-01108` | OWNER | WRITES (a copy) |
| 0.4 | Fresh backup and off-site copy, manifest check (as for 0.11.07; the off-site copy runs as the owner's login user, not `deploy`) | OWNER | WRITES |
| 1 | Check out `v0.11.08`, `MDARIX_RELEASE=v0.11.08`, build; offline config check; API import check | OWNER (commands from Claude) | WRITES (images) |
| 2 | `dc up -d --no-build --wait` (the AI host bridge has no health check, so `UP=1` alone is expected) | OWNER says go | WRITES (restart) |
| 3 | Smoke checks: `/api/v1/public/version` = 0.11.08, `/health/live`, every sitemap page 200, `/questions` shows the dark band | CLAUDE + OWNER | READ-ONLY |
| 4 | Rollback only if needed: images back to `v0.11.07` with the `pre-01108` settings copy | OWNER decides | WRITES |
