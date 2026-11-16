# MDARIX compliance validation protocol

This document records what the application enforces and what still requires a
controlled operational environment. It is evidence guidance, not a regulatory
certification.

Corrected 12 Nov 2026 (B6b): it said passwords expire after 90 days; the code
has no password expiry. The current validation documents are in
[docs/validation/](../validation/README.md).

## Application controls

- Authentication is durable, tenant-bound, throttled, and lockout-protected.
- Passwords are scrypt-hashed; password reuse is rejected against the current
  password and the last five recorded hashes. Passwords have at least 12
  characters and are refused when they appear in a list of breached passwords
  (`auth/service.py`). Passwords do **not** expire on a timer (owner decision,
  following NIST SP 800-63B): a password changes when there is a reason to
  (`backend/app/auth_router.py`, `_record_password_change`; tested in
  `tests/test_auth_hardening.py`). Five failed sign-ins lock the account for
  15 minutes (`backend/app/auth_router.py`, `LOCK_AFTER_FAILURES`).
- Audit events support actor, tenant, timestamp, correlation, source IP,
  user-agent, reason, old values, new values, and a seven-year retention date.
  Secret-like values are redacted before persistence.
- Audit rows are append-only through the database immutability trigger.
- Governed signatures require re-authentication, current object version,
  approval authority, segregation-of-duties checks, remarks, and a durable
  signature hash. Every signature needs a fresh authenticator code:
  `MDARIX_REQUIRE_MFA_FOR_SIGNATURES` is on by default (`backend/app/mfa.py`)
  and the production configuration check refuses to start with it off
  (`backend/app/config_check.py`).
- `GET /api/v1/governance/decisions/{decision_id}/signature-verification`
  recomputes the content fingerprint and signature hash and reports validity.

## Required test evidence

1. Sign in with a valid and invalid password; capture lockout and audit IDs.
2. Prove password reuse is rejected, a breached password is refused, and a
   password stays valid with no expiry date set after a change.
3. Execute a governed approval with a reason and verify the stored actor,
   source IP, user-agent, reason, timestamp, and signature hash.
4. Tamper-test a signature row in an isolated database and prove verification
   reports invalid; prove direct UPDATE/DELETE is rejected by the trigger.
5. Run the audit export as two tenants and verify there is no foreign data.
6. Run the retention report and verify every audit row has a retention date.

## Operational gates still required

Digital certificate issuance/rotation, MFA delivery or an external IdP
ceremony, seven-year retention enforcement in backup/archive storage, TLS
certificates, PITR/WAL archiving, restore rehearsal, production monitoring and
alert routing, and browser accessibility evidence require approved deployment
infrastructure. They must remain **PENDING — production infrastructure
required** until those controls are exercised and recorded.
