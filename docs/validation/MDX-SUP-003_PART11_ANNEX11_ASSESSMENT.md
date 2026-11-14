# MDX-SUP-003 21 CFR Part 11 assessment and EU GMP Annex 11 benchmark

| Field | Value |
|---|---|
| Document ID | MDX-SUP-003 |
| Title | 21 CFR Part 11 assessment, clause by clause, and EU GMP Annex 11 benchmark |
| Version | 0.1 |
| Status | DRAFT |
| Author (R) | Srinivas Telikicherla, QA/RA, quality approver |
| Reviewer | Independent CSV consultant (confirms; MDX-VAL-013 questions 4 to 6 and 8; not engaged yet) |
| Approver (A) | Sriharsha Telikicherla, Product & Engineering, system owner, after commenting on the evidence (MDX-VAL-000 DC-R42) |
| Drafting | Drafted with software assistance; every line reviewed by Srinivas Telikicherla (MDX-VAL-000, DC-R43) |
| Date | 14 Nov 2026 |
| Code baseline | Product code at `6b01eda5` (tip of `feat/b6b-validation-pack`); B6b Part C changes no code; release in preparation 0.11.04 (`VERSION` file still 0.10.94) |

Change history

| Version | Date | Change | By |
|---|---|---|---|
| 0.1 | 14 Nov 2026 | First draft (B6b Part C, item C4). Replaces `docs/compliance/COMPLIANCE_VALIDATION_PROTOCOL.md` as the reference for the application controls (MDX-VAL-000 section 3.2) | Srinivas Telikicherla |

## 1. Purpose and scope

This document assesses MDARIX against 21 CFR Part 11 (electronic records; electronic signatures), clause by clause,
and benchmarks it against EU GMP Annex 11 (computerised systems). For each clause it states whether the clause
applies, the MDARIX control and its evidence, what the customer must do, and what the consultant is asked to
confirm.

Part 11 applies to the customer: the customer keeps records that FDA's predicate rules require (for example MDR
files under 21 CFR 803 and complaint files) or signs them in MDARIX. MDARIX designs and evidences the technical
controls; the customer's procedures, training and validation complete them (MDX-B10-002 row 1,
`MDX-B10-002-Regulatory-Applicability-Matrix.md:46`).

Annex 11 binds EU pharmaceutical GMP only. A medical device maker uses it by choice, as a benchmark auditors use
(owner decision B6b-D9; MDX-B10-002 row 16, `MDX-B10-002-Regulatory-Applicability-Matrix.md:61`). MDARIX is never
called "Annex 11 compliant".

This document makes no compliance or certification claim. It states which controls exist and where the evidence is.
Evidence is a `file:line` on the code baseline or a test node id. A test listed here is evidence of design; it is
validation evidence only when it is run in a release pack (MDX-VAL-001 VMP-R31, VMP-R32).

Shared under a non-disclosure agreement only (owner decision B6b-D19).

## 2. How to read the tables

| Column | Meaning |
|---|---|
| Clause | The Part 11 paragraph |
| Requirement in short | A plain-English summary; the regulation's own text governs |
| Applies? | Yes / Partly / No, with the reason |
| MDARIX control and evidence | What MDARIX does, with `file:line` or a test |
| Customer responsibility | What the customer does |
| Open point for the consultant | What to confirm; "none" when nothing is asked |

## 3. Requirements

- **P11-R01** Each Part 11 clause listed in section 4 shall have one row in this document.
- **P11-R02** Each "Yes" or "Partly" row shall name an MDARIX control with evidence, or a customer responsibility.
- **P11-R03** A row whose evidence is still to verify shall say so in its "Open point" column.
- **P11-R04** This assessment shall be reviewed at each release whose change-impact assessment touches signatures,
  the audit trail, access control or record export (MDX-VAL-010 section 3), and at least every 12 months (owner
  decision B6b-D18).

## 4. 21 CFR Part 11, clause by clause

### 4.1 Subpart B: electronic records, controls for closed systems (11.10)

| Clause | Requirement in short | Applies? | MDARIX control and evidence | Customer responsibility | Open point for the consultant |
|---|---|---|---|---|---|
| 11.10(a) | Validate the system to ensure accuracy, reliability, consistent intended performance, and the ability to discern invalid or altered records | Yes | Per-release validation for MDARIX's own intended use (MDX-VAL-001 section 9). Altered records are discernible: the audit hash chain (`backend/app/audit_chain.py:1-12`) and signature verification (`tests/test_decision_governance_hardening.py::test_verification_status_is_invalid_when_any_signature_fails`) | Validates its own intended use (UAT/PQ, MDX-CUS-001, B6b Part E) | Do automated tests tagged with scenario IDs count as OQ evidence under CSA? (MDX-VAL-013 question 3) |
| 11.10(b) | Generate accurate and complete copies, in human-readable and electronic form, for inspection | Yes | Full organisation export: every table as JSON Lines, every stored file, a readable CSV bundle of the quality records, and a manifest with row counts, SHA-256 of each entry and the audit trail's verified head (`backend/app/tenant_export.py:1-8`); the export needs the current authenticator code (`tests/test_export_purge_mfa.py::test_a_customer_administrators_own_export_needs_the_current_code`) | Requests the copies it needs for an inspection | Is the readable CSV bundle plus the record pages enough as the "human readable" copy, or is a PDF per record expected? |
| 11.10(c) | Protect records so they can be retrieved accurately and readily throughout the retention period | Yes | Audit rows kept at least 7 years: the database sets `retention_until` (`infrastructure/database/migrations/versions/md23_pilot_readiness.py:32-40`); audit rows cannot be changed or deleted (`tests/test_audit_hash_chain.py::test_events_cannot_be_changed_or_deleted`); legal hold stops every deletion (`backend/app/legal_hold_api.py:1-10`); daily encrypted backups (`docs/runbooks/BACKUP_AND_RESTORE.md:10-15`) | Sets its own retention periods; asks for an export before the end of the contract | MDARIX keeps validation records 10 years (15 for implantable devices) after a release leaves the last customer (owner decision O1): enough? (MDX-VAL-013 question 17) |
| 11.10(d) | Limit system access to authorised individuals | Yes | Server-side permission check on every protected route, refused with 403 (`backend/app/access/permissions.py:210-225`); forced row-level security on every tenant table (`tests/test_rls_coverage.py::test_every_table_with_a_tenant_id_has_forced_row_level_security`); no organisation sees another's records (`tests/test_cross_tenant_routes.py::test_tenant_a_never_sees_tenant_b_records_through_any_business_route`); idle sessions end after 30 minutes by default (`backend/app/request_context.py:32`; `tests/test_b6a_boundaries.py::test_29_idle_minutes_keep_the_session_and_31_end_it`) | Creates accounts and assigns roles; reviews access (G14) | none |
| 11.10(e) | Secure, computer-generated, time-stamped audit trail of operator actions that create, modify or delete records; changes do not obscure earlier values; kept as long as the records; available for review and copying | Yes | Each audit event holds actor, action, record, time, reason, old and new values, source address (`backend/app/db/models/foundation.py:676-696`). The database chains every event (SHA-256) and rejects updates and deletes (`infrastructure/database/migrations/versions/md18_audit_chain.py:1-11`; `backend/app/audit_chain.py:1-12,26`); the scheduler verifies every organisation daily (`backend/app/audit_chain.py:54`); a changed event breaks the chain (`tests/test_audit_hash_chain.py::test_a_changed_event_breaks_the_chain`). Reporting facts need a reason kept in the audit trail (`tests/test_b6a_change_reason.py::test_reporting_facts_need_a_reason_kept_in_the_audit`). Copies: the export (11.10(b)) | Reviews the audit trail at its own interval with the signed audit trail review (G1, `tests/test_b6a_signed_reviews.py::test_who_signs_the_audit_trail_review_and_what_is_kept`) | The one exception to "never delete": the organisation purge at the end of the contract, only after the export is handed back or waived and never under a legal hold (`backend/app/tenant_purge.py:547,550-557`). Acceptable? |
| 11.10(f) | Operational system checks to enforce permitted sequencing of steps and events | Yes | An unanswered material question blocks submission until answered (`tests/test_b5_brief.py::test_an_unanswered_material_question_blocks_submit_until_answered`); outside a free trial a signer signs only after a training record (`tests/test_complaint_disposition_api.py::test_an_organization_outside_a_trial_signs_only_after_its_training_record`); the preparer and the conclusion signer cannot approve their own report (`tests/test_authority_reports_api.py::test_the_preparer_and_the_conclusion_signer_cannot_approve_and_a_colleague_can`) | Defines its own workflow steps in its procedures and checks them in UAT/PQ | none |
| 11.10(g) | Authority checks: only authorised individuals can use the system, sign, access the operation or device, alter a record or perform the operation | Yes | Every signature re-authenticates the signed-in person: current password, then a current authenticator code (`backend/app/governance_router.py:439-470`); permission per action (`backend/app/access/permissions.py:210-225`) | Assigns signing roles only to people authorised by its procedure | none |
| 11.10(h) | Device (terminal) checks to determine the validity of the source of data input or operational instruction | Partly: required "as appropriate". MDARIX accepts input only from authenticated sessions (`backend/app/request_context.py:198`) and from the intake routes the customer configures (import, e-mail intake) | No terminal-level check | Decides whether any of its input routes needs a source check | Is the authenticated session plus configured intake routes enough for (h)? |
| 11.10(i) | People who develop, maintain or use the system have the education, training and experience for their tasks | Yes | MDARIX staff: training records per MDX-VAL-001 section 16.2. Users: signer training records on the current version of each document a signature relies on (`backend/app/signer_training/service.py:1-10`) | Trains its own users and keeps the records | none |
| 11.10(j) | Written policies that hold individuals accountable for actions under their electronic signatures | Yes, for the customer | Not an MDARIX control. MDARIX shows the meaning of each signature before signing and stores it (`backend/app/db/models/foundation.py:1053`) | Writes and enforces the policy | none |
| 11.10(k) | Controls over systems documentation: distribution, access and use; revision and change control with an audit trail | Yes | MDARIX's own documents: document control MDX-VAL-000 (git history, versions, signed PDFs). Change control: SOP MDX-SOP-002 | Controls its own procedures and the copies of MDARIX documents it keeps | none |

### 4.2 Subpart B: open systems (11.30)

| Clause | Requirement in short | Applies? | MDARIX control and evidence | Customer responsibility | Open point for the consultant |
|---|---|---|---|---|---|
| 11.30 | For an open system: the 11.10 controls plus measures such as document encryption and digital signature standards to ensure authenticity, integrity and confidentiality | **To decide with the consultant.** MDARIX is reached over the internet; access is controlled by MDARIX as operator. Until decided, this assessment lists the open-system measures that exist | Traffic over HTTPS only, HTTP redirected (`infrastructure/docker/Caddyfile:1-2`); stored files encrypted (AES-GCM, `object_storage/service.py:8`); authenticator secrets encrypted (`auth/totp.py:1`); signatures bound to content by hash (11.70 row) | Decides, with MDARIX, how its own procedures treat the system | Open or closed system for a SaaS reached over the internet? (MDX-VAL-013 question 5) |

### 4.3 Subpart B: signature manifestations (11.50) and signature/record linking (11.70)

| Clause | Requirement in short | Applies? | MDARIX control and evidence | Customer responsibility | Open point for the consultant |
|---|---|---|---|---|---|
| 11.50(a) | Signed records show the signer's printed name, the date and time of signing, and the meaning of the signature | Yes | The signature record stores the signer's account, role, meaning and time (`backend/app/db/models/foundation.py:1051-1053,1057`). The signature check page shows the signer's name and role (`frontend/src/features/signature/SignatureVerificationWorkspace.tsx:27-43`) | Checks the display and print in UAT/PQ | **To verify:** that the printed name, not only the account id or the role, appears on every display and print of a signed record. The page falls back to the role when no name is found (`SignatureVerificationWorkspace.tsx:41-42`) |
| 11.50(b) | These items are under the same controls as the record and appear in every human-readable form of it | Yes | The meaning, signer and time are columns of the signature record, under the same access control and audit trail; the content fingerprint covers the signed version (11.70 row) | As 11.50(a) | As 11.50(a) |
| 11.70 | Signatures are linked to their records so they cannot be removed, copied or transferred to falsify a record | Yes | Each signature stores the content fingerprint of the signed version and a signature hash (`backend/app/db/models/foundation.py:1054-1055`); one signature per object version and decision type (`foundation.py:1062-1069`); verification fails when any signature fails (`tests/test_decision_governance_hardening.py::test_verification_status_is_invalid_when_any_signature_fails`); a signed conclusion whose facts change is flagged, never rewritten (`tests/test_b6a_change_reason.py::test_a_signed_conclusion_is_flagged_never_rewritten_when_its_facts_change`) | none | Is hash binding to the record version enough for 11.70? (MDX-VAL-013 question 5) |

### 4.4 Subpart C: electronic signatures, general (11.100)

| Clause | Requirement in short | Applies? | MDARIX control and evidence | Customer responsibility | Open point for the consultant |
|---|---|---|---|---|---|
| 11.100(a) | Each electronic signature is unique to one individual and never reused by or reassigned to anyone else | Yes | A signature names the signer's account id (`backend/app/capa_effectiveness/router.py:348`; the signer is looked up by account id, `backend/app/governance_router.py:395-404`). Account ids are never reused. An e-mail address can be used again after its account is offboarded (`infrastructure/database/migrations/versions/p32_reusable_offboarded_emails.py:1,12`), as a new account with a new id | Does not share accounts; offboards leavers | Is a re-used e-mail address on a new account acceptable, given the signature names the account id? |
| 11.100(b) | Verify a person's identity before giving them an electronic signature | Yes, for the customer | Not an MDARIX control: the customer's administrator creates the account | Verifies identity before creating an account with signing rights | MDX-VAL-013 question 4 |
| 11.100(c) | Certify to FDA that electronic signatures are the legally binding equivalent of handwritten signatures | Yes, for the customer | Not an MDARIX control | Sends its own certification letter to FDA before or at first use | MDX-VAL-013 question 4 |

### 4.5 Subpart C: electronic signature components and controls (11.200)

| Clause | Requirement in short | Applies? | MDARIX control and evidence | Customer responsibility | Open point for the consultant |
|---|---|---|---|---|---|
| 11.200(a)(1) | At least two distinct identification components; in a continuous session the first signing uses all, later ones at least one; outside one, all | Yes | Every signing asks for both the current password and a current authenticator code, not only the first in a session (`backend/app/governance_router.py:439-470`); a server cannot switch the code requirement off (`backend/app/config_check.py:402-403`); a wrong, blank or reused code is refused (`tests/test_signing_code_refusals.py::test_a_wrong_blank_or_reused_code_is_a_signature_refusal`) | none | Is password plus authenticator code per signing enough? (MDX-VAL-013 question 5) |
| 11.200(a)(2) | Used only by their genuine owners | Yes | Password and authenticator are personal; the authenticator secret is encrypted and bound to its account (`auth/totp.py:1-6`) | Policy forbidding sharing (11.10(j)) | none |
| 11.200(a)(3) | Administered so that use by anyone other than the owner needs two or more people to collaborate | Yes | Signing needs the password and the code from the owner's own authenticator app; a support grant needs two MDARIX administrators and the customer's administrator (`backend/app/support_access.py:6-11`) | none | none |
| 11.200(b) | Biometric signatures can be used only by their genuine owners | No: MDARIX has no biometric signatures | n/a | n/a | none |

### 4.6 Subpart C: controls for identification codes and passwords (11.300)

| Clause | Requirement in short | Applies? | MDARIX control and evidence | Customer responsibility | Open point for the consultant |
|---|---|---|---|---|---|
| 11.300(a) | Each combination of identification code and password is unique | Yes | One account per e-mail address in each organisation (`backend/app/access/platform_customer_admins.py:216`); accounts identified by id (11.100(a) row) | none | none |
| 11.300(b) | Identification codes and passwords are checked, recalled or revised periodically (for example password ageing) | Partly | **No periodic password expiry** (owner decision O5, following NIST SP 800-63B). Instead: 12 to 128 characters, refused when on a list of breached passwords (`auth/service.py:15-16,141`); lockout (11.300(d)); an authenticator code at every signing (11.200 row); idle timeout (11.10(d) row) | Reviews accounts in its access review (G14) | Is no periodic expiry acceptable with these controls? (MDX-VAL-013 question 6) |
| 11.300(c) | Procedures to deauthorise lost, stolen or compromised tokens or passwords and issue replacements | Yes | Single-use recovery codes (`tests/test_mfa_recovery.py::test_recovery_codes_are_single_use`); an administrator resets a lost authenticator; changing the password ends every other session (`tests/test_auth_hardening.py::test_change_password_signs_out_other_sessions_and_keeps_this_one`) | Its administrators deactivate and reset accounts under its procedure | none |
| 11.300(d) | Safeguards against unauthorised use; detect and report attempts at once to security and management | Yes | Sign-in locks after 5 failures for 15 minutes (`backend/app/auth_router.py:70-71`); signing has its own lock (`tests/test_signing_code_refusals.py::test_repeated_wrong_codes_lock_signing_with_a_signature_code`); failures and lockouts are audited (`tests/test_auth_audit_events.py::test_sign_in_success_failure_lockout_and_sign_out_are_audited`) | Reviews the audit trail (G1); acts on what it shows | Is an audited lockout enough as "report at once", or is an alert to the customer expected? |
| 11.300(e) | Initial and periodic testing of devices that bear or generate codes or passwords | Partly | The authenticator is an app on the user's own phone; each code is checked at use, one 30-second step either side, and accepted once (`auth/totp.py:3-4`) | Manages the phones its users use | none |

## 5. EU GMP Annex 11 benchmark (owner decision B6b-D9)

Every row: **applies to a device maker only by choice; legally binding for EU pharmaceutical GMP.** The column
"Applies?" says whether MDARIX, as a supplier, has something to show for the clause.

| Clause | Requirement in short | Applies? | MDARIX control and evidence | Customer responsibility | Open point for the consultant |
|---|---|---|---|---|---|
| Principle A | Use of a computerised system must not lower product quality, process control or quality assurance, nor raise overall risk | Yes | Indirect GxP impact (MDX-SUP-002 section 2) | Its own assessment | none |
| Principle B | Applications validated; IT infrastructure qualified | Yes | MDX-VAL-001 (application); IQ of the environment per release (MDX-VAL-001 section 10) | Its own UAT/PQ | none |
| Principle C | Replacing a manual operation must not lower quality or raise risk | Partly | n/a for MDARIX | Its own assessment when MDARIX replaces paper | none |
| 1 Risk management | Risk management across the life cycle | Yes | Product risk assessment MDX-VAL-002 (FMEA) | Its own risk assessment for its use | Scales and thresholds (MDX-VAL-013 question 7) |
| 2 Personnel | Cooperation between process owner, system owner, qualified persons and IT; training | Yes | Roles and RACI, MDX-VAL-001 section 6 | Its own roles | none |
| 3 Suppliers and service providers | Formal agreements; supplier assessment based on risk; documentation available to inspectors | Yes | Supplier pack MDX-SUP-001; MDARIX's own provider assessment MDX-SUP-004 | Assesses MDARIX as its supplier; signs the agreement | none |
| 4 Validation | Life-cycle validation documentation, user requirements, change control, test methods | Yes | MDX-VAL-001 sections 9 to 12; change control SOP MDX-SOP-002 | Its own UAT/PQ against its own user requirements | none |
| 5 Data | Built-in checks for correct and secure data exchange with other systems | Yes | Import quarantine, quality report and the seven interface checks (MDX-VAL-001 Annex F) | Its own migration report (MDX-CUS-003, B6b Part E) | Reconciliation and sampling level (MDX-VAL-013 question 12) |
| 6 Accuracy checks | Additional check of critical data entered by hand | Partly | Reporting facts need a reason when changed (11.10(e) row); the preparer cannot approve their own report (11.10(f) row) | Decides which fields need a second check | none |
| 7 Data storage | Data secured physically and electronically; accessible and readable through the retention period; regular backups, restore tested | Yes | 11.10(c) row; restore drill records (`docs/runbooks/BACKUP_AND_RESTORE.md:121-128`) | none | Recovery validation list (MDX-VAL-013 question 11) |
| 8 Printouts | Clear printed copies; for batch release records, an indication of changed data | Partly | Readable export (11.10(b) row) | Prints what its procedures need | 11.50(a) open point |
| 9 Audit trails | Risk-based audit trail of GMP-relevant changes and deletions, with the reason; reviewed regularly | Yes | 11.10(e) row | Reviews the audit trail (G1) | none |
| 10 Change and configuration management | Changes controlled and defined | Yes | SOP MDX-SOP-002; configuration snapshot and comparison (`backend/app/signed_reviews/configuration.py:73,187`) | Signs its configuration snapshot (G21) | Shared plane, one version for all (MDX-VAL-013 question 10) |
| 11 Periodic evaluation | Periodic evaluation to confirm a valid state | Yes | Release packs; recovery and health records (B6b Part D) | Periodic review every 12 months recommended (MDX-CUS-004, B6b Part E) | Interval (MDX-VAL-013 question 13) |
| 12 Security | Physical and logical access controls; records of who granted and changed access | Yes | 11.10(d) row; support access grants (`backend/app/support_access.py:1-17`); access changes audited | Access review (G14) | none |
| 13 Incident management | All incidents reported and assessed; root cause found | Yes | SOP MDX-SOP-003 | Reports suspected defects to MDARIX | none |
| 14 Electronic signature | Same impact as handwritten in the company; permanently linked; time and date | Yes | Rows 11.50 to 11.300 | Its own policy (11.10(j)) | none |
| 15 Batch release | Only Qualified Persons certify batch release | No: MDARIX does not release batches | n/a | n/a | none |
| 16 Business continuity | Provisions to keep processes going after a breakdown; time to restore based on risk | Yes | SOP MDX-SOP-004; recovery time 4 hours, recovery point 24 hours today (owner decision B6b-D8) | Its own outage procedure (G18) | none |
| 17 Archiving | Archived data checked for accessibility, readability and integrity | Partly | Export with manifest and SHA-256 per entry (`backend/app/tenant_export.py:5-7`) | Keeps its archive copies | none |

## 6. Findings to carry

| # | Finding | Where it goes |
|---|---|---|
| F-1 | Printed name on every display and print of a signed record: to verify (11.50(a)) | OQ scenario for signature display; consultant |
| F-2 | Open or closed system (11.30) | Consultant (MDX-VAL-013 question 5) |
| F-3 | No periodic password expiry (11.300(b)) | Consultant (MDX-VAL-013 question 6); owner decision O5 stands meanwhile |
| F-4 | Re-used e-mail address after offboarding (11.100(a)) | Consultant |

## Signatures

Unsigned. The signed PDF and its `signatures.csv` row are added after review (MDX-VAL-000 section 2.6).

| Role | Name | Meaning of signature | Signature | Date |
|---|---|---|---|---|
| Author (R) | Srinivas Telikicherla, QA/RA | I am responsible for this document and reviewed every line of the draft. | | |
| Reviewer (C) | Independent CSV consultant | I reviewed this document; my comments are recorded. | | |
| Approver (A), second person (DC-R42) | Sriharsha Telikicherla, Product & Engineering, system owner | I confirm that the evidence cited is accurate and approve this document for use. | | |
