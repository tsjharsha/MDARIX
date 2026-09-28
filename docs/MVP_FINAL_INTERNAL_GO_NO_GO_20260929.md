# MDARIX MVP 1.0 — final internal release report

Date: 2026-09-29  
Scope: synthetic validation tenants and local/internal MVP only.

## Decision

**NO-GO for final sign-off at this run.** The product remains suitable for a
controlled technical demonstration, but the final regression gate is not green:
`day0_db_test.py` fails during collection with PostgreSQL `WinError 10054`
(connection forcibly closed by the remote host). Re-run the complete suite after
reconciling the local database connection mode and credentials.

## Line-item disposition

| Area | Current disposition | Evidence |
|---|---|---|
| Specialized AI/regulatory workflows | Implemented for internal MVP; advisory only | Regulatory intelligence tests and AI workflow tests |
| Clause-level citation/provenance | Implemented for verified catalog entries; incomplete claims remain visible | `regulatory_intelligence` tests and source manifest |
| MFA/signature evidence | Local automated foundation implemented | `tests/test_mfa_mvp.py`, signature workflow tests |
| Audit diffs/evidence export | Implemented in controlled MVP paths | audit/compliance and report tests |
| Frontend routes/accessibility | Build and selected browser evidence exist | frontend build and browser artifacts |
| CSA package | Implemented and ready for controlled execution | `docs/CSA_MVP_VALIDATION_PROTOCOL.md` |
| Website trust claims | Corrected and qualified | `docs/WEBSITE_TRUST_CLAIMS_POLICY.md` |
| Competitive positioning | Sharpened; measurement plan added | `docs/COMPETITIVE_POSITIONING_MVP.md` |
| Full regression | **Blocked** | `day0_db_test.py`, PostgreSQL socket reset |

## Required closure actions

1. Confirm the intended local PostgreSQL port, database, credentials, and
   SSL mode for `day0_db_test.py`.
2. Re-run `python -m pytest -q` from a clean validation environment.
3. Preserve the complete test output and migration/health evidence.
4. Update this report only after the suite completes without collection errors.

## Explicitly outside this MVP decision

Production hosting, customer credentials, managed PostgreSQL TLS, production
backup/PITR/monitoring, enterprise IdP, customer ROI/reference evidence, and
regulatory certification remain deferred. The website must not claim ISO 27001,
HIPAA, GDPR, or 21 CFR Part 11 certification/compliance without separate
approved evidence.

