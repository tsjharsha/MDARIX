# Release 0.11.09 on production (mdarix.com): the legal and trust pages in the website's look

Release 0.11.09 changes only the public website: Privacy policy, Terms of service, Free trial agreement, Security and
Accessibility open with the same dark page band as Product, Trust, Company and Questions (eyebrow, heading and a
one-line summary inside it; the legal texts load below it as before). No application screen, API or database change.

Running on production before the window: tag `v0.11.08`, schema `ux2navigationnew`. Everything else (VM, compose
files, the `dc` shorthand, backup and off-site copy, rollback rules) is as in `RELEASE_0.11.07.md` and
`RELEASE_0.11.08.md`.

**No database change.** No new Alembic revision; the head stays `ux2navigationnew`.

## Checklist

| # | Step | Who | Kind |
|---|---|---|---|
| 0.1 | Owner's go recorded | OWNER | - |
| 0.2 | Fresh backup and off-site copy, manifest check (the off-site copy runs as the owner's login user, not `deploy`) | OWNER | WRITES |
| 0.3 | As `deploy` in `~/mdarix`: settings copy with the suffix `pre-01109`; disk at least 8 GB free; release `v0.11.08` | OWNER (commands from Claude) | WRITES (a copy) |
| 1 | Check out `v0.11.09`, `MDARIX_RELEASE=v0.11.09`, build; offline config check; API import check | OWNER (commands from Claude) | WRITES (images) |
| 2 | `dc up -d --no-build --wait` (the AI host bridge has no health check, so `UP=1` alone is expected) | OWNER says go | WRITES (restart) |
| 3 | Smoke checks: `/api/v1/public/version` = 0.11.09, `/health/live`, every sitemap page 200, the five pages show the dark band | CLAUDE + OWNER | READ-ONLY |
| 4 | Rollback only if needed: images back to `v0.11.08` with the `pre-01109` settings copy | OWNER decides | WRITES |
