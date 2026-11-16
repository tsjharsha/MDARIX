# MDX-SUP-006 Trust facts

| Field | Value |
|---|---|
| Document ID | MDX-SUP-006 |
| Title | Trust facts: the verified statements MDARIX may publish, with their evidence |
| Version | 0.1 |
| Status | DRAFT |
| Author (R) | Sriharsha Telikicherla, Product & Engineering, system owner (evidence check) |
| Reviewer | none named (B6b spec section 3: R system owner, A quality approver) |
| Approver (A) | Srinivas Telikicherla, QA/RA, quality approver: owner of the claims |
| Drafting | Drafted with software assistance; every line reviewed by Sriharsha Telikicherla (MDX-VAL-000, DC-R43) |
| Date | 14 Nov 2026 |
| Code baseline | Product code at `6b01eda5` (tip of `feat/b6b-validation-pack`); B6b Part C changes no code; release in preparation 0.11.04 (`VERSION` file still 0.10.94) |

Change history

| Version | Date | Change | By |
|---|---|---|---|
| 0.1 | 14 Nov 2026 | First draft (B6b Part C, item C7), from the verified trust-claims list of 11 Nov 2026 (planning input for the public trust page, M7) | Sriharsha Telikicherla |

## 1. Purpose and scope

This is the only list of statements about security, data protection and validation that MDARIX may put on its public
trust page or in sales material (owner decision B6b-D19: the public page carries only verified facts). Each fact
carries its evidence: a `file:line`, a test, a restore-drill row or a dated live check. A fact whose evidence is
marked "to record" or "to obtain" shall not be published until that evidence exists.

It sits under the website trust-claims policy (`docs/compliance/WEBSITE_TRUST_CLAIMS_POLICY.md:19-23`): every claim
has an owner, source evidence, scope, environment and review date.

## 2. Rules

- **TF-R01** A statement about security, data protection, availability or validation shall be published only if it
  is a row of section 3 with status "Publishable".
- **TF-R02** A row shall be "Publishable" only when every evidence item in it exists on the code baseline or as a
  dated record.
- **TF-R03** The wording published shall not go beyond the "Wording" column.
- **TF-R04** This list shall be re-checked against the code at each release whose change-impact assessment touches a
  listed control, and at least every 12 months.
- **TF-R05** No statement in the "Never claim" list (section 5) shall be published.

## 3. Facts

| # | Wording | Evidence | Scope and environment | Status |
|---|---|---|---|---|
| TF-01 | Customer data is hosted in India: the service in Mumbai, encrypted backup copies in Delhi | `docs/runbooks/GCP_DEPLOYMENT.md:4-6`; `legal/SUBPROCESSORS.md:12-15` | Production | Publishable |
| TF-02 | Stored files and authenticator secrets are encrypted by the application (AES-GCM) | `object_storage/service.py:8`; `auth/totp.py:1` | Production (files stored on the server) | Publishable |
| TF-03 | Stored files and authenticator secrets are encrypted with 256-bit keys | The code accepts 128, 192 or 256-bit keys (`auth/totp.py:5`); the production key length: to record (owner, read-only check) | Production | Not yet: evidence to record |
| TF-04 | Encryption keys were rotated in October 2026 | Dated rotation record: to record (owner) | Production | Not yet: evidence to record |
| TF-05 | Disks are encrypted at rest by the cloud provider | Provider reports, MDX-SUP-004 E-1, E-4: to obtain (owner, provider compliance portal) | Production | Not yet: evidence to obtain |
| TF-06 | Backups are encrypted with a key the cloud provider never holds | `docs/runbooks/BACKUP_AND_RESTORE.md:41-46`; `legal/SUBPROCESSORS.md:15` | Production | Publishable |
| TF-07 | All traffic uses HTTPS; plain HTTP is redirected | `infrastructure/docker/Caddyfile:1-2` | Production | Publishable |
| TF-08 | TLS 1.2 and 1.3 only | A live check was made on 11 Nov 2026; its dated record is not in the repository: to record (owner) | Production | Not yet: evidence to record |
| TF-09 | Access is role-based, per user and per function, checked on the server; an action not granted is refused | `backend/app/access/permissions.py:210-225` | All environments | Publishable |
| TF-10 | Each organisation's data is isolated by row-level security forced on every organisation table; a dedicated database per customer is available | `tests/test_rls_coverage.py::test_every_table_with_a_tenant_id_has_forced_row_level_security`; `tests/test_dedicated_plane.py::test_business_records_are_written_to_the_customers_own_database` | All environments | Publishable |
| TF-11 | Multi-factor authentication is required for administrators, leaders and approvers, and for every electronic signature | `backend/app/mfa.py:35,45`; `backend/app/config_check.py:402-403` | Production | Publishable |
| TF-12 | Personal data is left out of exports by default; the AI layer (switched off) has a step that masks personal information in text | `tests/test_b8_export_personal_data.py::test_an_unmasked_export_leaves_out_snapshot_personal_data_by_default`; `tests/test_ai_controls.py::test_personal_information_is_masked_and_investigation_facts_are_kept` | All environments (AI is off) | Publishable |
| TF-13 | Personal data is excluded from search | Evidence: to verify on the code baseline (not checked in this draft) | All environments | Not yet: evidence to record |
| TF-14 | The audit trail records who did what and when, with old and new values, sign-ins and electronic signatures; it cannot be changed and is verified daily by a hash chain | `backend/app/db/models/foundation.py:676-696`; `tests/test_audit_hash_chain.py::test_events_cannot_be_changed_or_deleted`; `tests/test_auth_audit_events.py::test_sign_in_success_failure_lockout_and_sign_out_are_audited`; `backend/app/audit_chain.py:8-11` | All environments | Publishable |
| TF-15 | Regulatory rules are versioned with effective dates; a signed conclusion keeps the rule version it used | `backend/app/rule_register/register.py:7`; `tests/test_b4_effective_dating.py::test_a_signed_conclusion_never_changes_when_a_new_floor_version_arrives` | All environments | Publishable |
| TF-16 | Signed records are frozen and bound to their content with SHA-256 | `backend/app/db/models/foundation.py:1054-1055`; `tests/test_decision_governance_hardening.py::test_verification_status_is_invalid_when_any_signature_fails` | All environments | Publishable |
| TF-17 | Backups run daily; restore drills from production backups were completed on 16 Oct 2026 and 3 Nov 2026, the second in 7 min 19 s against a recovery time objective of 4 hours | `docs/runbooks/BACKUP_AND_RESTORE.md:154,156` | Production | Publishable |
| TF-18 | Recovery point: 24 hours today (daily encrypted backup, no point-in-time recovery); target 15 minutes with point-in-time recovery on pilot hosting. Recovery time objective: 4 hours | Owner decision B6b-D8; `docs/runbooks/BACKUP_AND_RESTORE.md:3-5` | Production | Publishable, in these words only |
| TF-19 | Customers can review and sign their own access reviews and audit trail reviews in MDARIX | `tests/test_b6a_signed_reviews.py::test_the_access_review`; `tests/test_b6a_signed_reviews.py::test_who_signs_the_audit_trail_review_and_what_is_kept` | All environments | Publishable |
| TF-20 | MDARIX staff see a customer's data only with that customer's approval, for at most 24 hours, and every use is in the customer's own audit trail | `backend/app/support_access.py:1-17`; `tests/test_support_access_customer_approval.py::test_customer_data_opens_only_after_the_customer_approves_and_every_use_is_theirs_to_see` | All environments | Publishable |
| TF-21 | Validation status | Only these words: "Validation in progress; plan MDX-VAL-001 (draft)." (MDX-VAL-001 VMP-R44) | n/a | Publishable, in these words only |

## 4. Not claimable yet (work before the claim)

| Topic | What is needed first |
|---|---|
| GDPR | DPA template, sub-processor list, records of processing, transfer basis; lawyer review |
| 21 CFR Part 11 | The clause-by-clause assessment (MDX-SUP-003) confirmed by the consultant and verified in a release pack; even then, only "designed to support the customer's Part 11 controls", never "compliant" |
| SOC 2 / ISO/IEC 27001 | Only "mapped" (MDX-SUP-005); a certificate or report needs an audit |
| Independent penetration test | The test and its closure statement (before the first paid pilot) |
| Full traceability | The generated RTM of an approved release pack |

## 5. Never claim

Copied from the trust-claims list of 11 Nov 2026 and the website trust-claims policy
(`docs/compliance/WEBSITE_TRUST_CLAIMS_POLICY.md:10-17`):

- "certified", "compliant", "aligned" or "ready" without the evidence named in section 4;
- ISO/IEC 27001 certification, or wording equal to it;
- HIPAA compliance; GDPR compliance; 21 CFR Part 11 compliance;
- FDA, EU MDR, ISO or Notified Body approval or certification;
- "Annex 11 compliant" (owner decision B6b-D9);
- that MDARIX is validated for any customer, or for every customer (MDX-VAL-000 DC-R30);
- customer logos, metrics, testimonials or security attestations without written approval;
- a price, a competitor's name, or the name of a legal entity before the company is registered
  ([legal entity: to be added on registration]).

## Signatures

Unsigned. The signed PDF and its `signatures.csv` row are added after review (MDX-VAL-000 section 2.6).

| Role | Name | Meaning of signature | Signature | Date |
|---|---|---|---|---|
| Author (R), system owner | Sriharsha Telikicherla, Product & Engineering | I checked the evidence of every row. | | |
| Approver (A), quality approver | Srinivas Telikicherla, QA/RA | I own these claims and approve the rows marked "Publishable" for publication. | | |
