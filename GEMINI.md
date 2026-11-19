# GEMINI.md

Context for Google Gemini (Gemini CLI, Gemini Code Assist) working on this repository.

The project conventions live in AGENTS.md (shared with every AI assistant) and are imported here so there is a
single source of truth:

@AGENTS.md

## Read before changing anything

1. `AGENTS.md` (imported above): where code goes, naming, security and tenancy, tests, formatting.
2. `docs/handover/MDARIX_0.11.07_HANDOVER.md`, sections 0 and 1: rules, product, architecture, glossary.
   It is large (about 12,800 lines): open the section that owns the code you touch, and use Appendix A
   (every API endpoint), Appendix B (every table) and Appendix C (migrations) to find it.
3. `STATUS.md`: the last verified state and known issues.

If the handover and the code disagree, the code wins: fix the handover in the same change.

## Rules that are easy to miss

- Tenant and acting user come only from `get_request_context` (`ctx.tenant_id`, `ctx.user_id`), never from the
  request body or query string. PostgreSQL uses forced row-level security; only system jobs and data migrations
  open the system scope (`backend/app/db/tenant_scope.py`), and every data migration gets a row-count test.
- Every schema change needs a SQLAlchemy model change plus an Alembic migration (single head).
- Every behaviour change ships with a test that fails without it. Run the gates in AGENTS.md before committing;
  run backend tests with `TZ=UTC` (four tests depend on the IST/UTC date between 00:00 and 05:30 IST).
- Tests use the test database `mdarix_r1_test`, never the demo database `mdarix_r1`, and never call real AI
  providers or send real e-mail.
- Never read, print, edit or commit `.env*` files, keys or tokens. Only the `*.example` templates are in git.
- AI output is a proposal a person reviews, never a fact. Do not name the AI model or provider in the product,
  the website or a demo. AI is off by default per organization.
- No certification claims, prices, competitor names, logos, testimonials or invented numbers anywhere public.
  Sample data stays labelled "Sample".
- MDARIX never submits to an authority directly; a person signs every reportability answer and decision, and the
  preparer of a record is never its approver or signer.
- Deploys, pushes, tags and production database writes need the owner's explicit OK each time.
- Never `git stash`, never `docker system prune`, never force-push, never skip hooks.
