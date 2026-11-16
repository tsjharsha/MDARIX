# MDX-SUP-002 GxP impact assessment and shared-responsibility matrix

| Field | Value |
|---|---|
| Document ID | MDX-SUP-002 |
| Title | GxP impact assessment for MDARIX and shared-responsibility matrix |
| Version | 0.1 |
| Status | DRAFT |
| Author (R) | Srinivas Telikicherla, QA/RA, quality approver |
| Reviewer | Independent CSV consultant (MDX-VAL-013 question 4; not engaged yet) |
| Approver (A) | Sriharsha Telikicherla, Product & Engineering, system owner, for technical accuracy (MDX-VAL-000 DC-R42) |
| Drafting | Drafted with software assistance; every line reviewed by Srinivas Telikicherla (MDX-VAL-000, DC-R43) |
| Date | 14 Nov 2026 |
| Code baseline | Product code at `6b01eda5` (tip of `feat/b6b-validation-pack`); B6b Part C changes no code; release in preparation 0.11.04 (`VERSION` file still 0.10.94) |

Change history

| Version | Date | Change | By |
|---|---|---|---|
| 0.1 | 14 Nov 2026 | First draft (B6b Part C, item C2) | Srinivas Telikicherla |

## 1. Purpose and scope

A customer's quality unit asks four questions before it uses a supplier's software for regulated work: what is it
for, can it affect patient safety or product quality, which GxP records does it create, and which GxP decisions does
it support. Section 2 answers them for MDARIX. Section 3 then splits each control between MDARIX and the customer.

This document covers MDARIX as a hosted service (software as a service) for medical device manufacturers. It does
not decide a customer's own GxP impact assessment: the customer makes its own, for its own intended use and its own
processes (section 4).

Shared under a non-disclosure agreement only (owner decision B6b-D19).

## 2. GxP impact assessment

### 2.1 Intended use

MDARIX is post-market intelligence and decision-support software for medical device manufacturers. It helps a
manufacturer's quality and regulatory team handle complaints and vigilance from the first contact to the closed
record, across markets (MDX-B10-001 section 4, `MDX-B10-001-Intended-Use-Statement.md:34-35`).

Three fixed rules limit that use (MDX-B10-001 section 4.2, `MDX-B10-001-Intended-Use-Statement.md:49-52`):

1. A person always decides and signs.
2. MDARIX never submits to an authority.
3. AI is off.

MDARIX is not an eQMS, not a submission gateway, not a decision maker and not a medical device (the last to confirm
with a regulatory consultant) (`MDX-B10-001-Intended-Use-Statement.md:81-89`).

### 2.2 The four questions

| Question | Answer | Basis |
|---|---|---|
| Can MDARIX affect patient safety? | **Indirectly.** MDARIX does not touch a device or a patient. A wrong legal clock, a wrong reportability suggestion or a lost record could delay a vigilance report, and a late report can delay field action that protects patients | MDX-VAL-002 section 4, `MDX-VAL-002_PRODUCT_RISK_ASSESSMENT.md:144,147` (clocks, reportability) |
| Can MDARIX affect product quality? | **Indirectly.** Complaint trends, investigations and CAPA effectiveness feed the manufacturer's quality decisions. MDARIX shows a "pattern to review", never a confirmed signal; a person decides | `MDX-B10-001-Intended-Use-Statement.md:46`; MDX-VAL-002 section 4, `MDX-VAL-002_PRODUCT_RISK_ASSESSMENT.md:164` |
| Which GxP records does MDARIX create? | Complaint records with their awareness time; per-market reportability assessments and their signed conclusions; authority report files (the customer submits them); investigation records and signed conclusions; signed reviews (audit trail review, access review, configuration snapshot); electronic signatures; the audit trail; the organisation export | MDX-VAL-002 section 4, rows marked "Direct", `MDX-VAL-002_PRODUCT_RISK_ASSESSMENT.md:143-162`; signature record `backend/app/db/models/foundation.py:1040-1069`; audit event `backend/app/db/models/foundation.py:676-696` |
| Which GxP decisions does MDARIX support? | Complaint or service only; triage and fast track; reportability per market; report approval; investigation conclusion; CAPA effectiveness. Each decision is made and signed by a named person; MDARIX suggests and counts | `MDX-B10-001-Intended-Use-Statement.md:37-47` |

### 2.3 Conclusion

- **GI-R01** MDARIX shall be treated as GxP-relevant software with indirect impact on patient safety and product
  quality.
- **GI-R02** The functions MDX-VAL-002 section 4 marks "Direct" shall be validated by MDARIX as class A, per release
  (MDX-VAL-001 section 8).
- **GI-R03** Each customer shall make its own GxP impact assessment for its own intended use before go-live
  (section 4; template MDX-CUS-001, B6b Part E).

The function-by-function GxP impact, class and assurance approach are in MDX-VAL-002 section 4. They are not
repeated here, so that there is one source.

## 3. Shared-responsibility matrix

"MDARIX" means MDARIX as supplier and operator of the hosted service. "Customer" means the medical device
manufacturer that uses it. "Both" means each party does its own part, as the row says.

### 3.1 MDARIX

| Control | What MDARIX does | Evidence |
|---|---|---|
| Hosting and infrastructure security | Runs the service on one cloud virtual machine in Mumbai, India; firewall allows web traffic only; administrator access through the cloud provider's identity-aware proxy | `docs/runbooks/GCP_DEPLOYMENT.md:4-6,23`; hosting assessment MDX-SUP-004 |
| Patching | Security updates install themselves on the server; kernel reboots by hand | `docs/runbooks/DEPLOYMENT.md:58-59` |
| Backups | Daily encrypted backup of every database and of the stored files, copied off-site; daily disk snapshot | `docs/runbooks/BACKUP_AND_RESTORE.md:10-15`; `docs/runbooks/GCP_DEPLOYMENT.md:21-22` |
| Restore drills and recovery validation | Quarterly restore drill with a written record; recovery validation of the GxP process after a restore (B6b Part D, record MDX-OPS-001) | `docs/runbooks/BACKUP_AND_RESTORE.md:91-157`; SOP MDX-SOP-004 |
| Time synchronisation | Server clock kept by NTP (chrony); clock check against a 1 s limit at each release, after a server change and in the restore drill | `docs/runbooks/DEPLOYMENT.md:57`; `scripts/clock_check.py:1-8` |
| Application validation per release | Validates each release for MDARIX's own intended use (the release pack) | MDX-VAL-001 section 9; release approval record MDX-VAL-012 |
| Sub-processor control | Keeps the list of providers that receive customer data; a new provider is added before it receives data | `legal/SUBPROCESSORS.md:3-6`; MDX-SUP-004 |
| Release notes and change notice | 10 working days' notice of a change to a class-A function, a rule floor or a sub-processor; emergency security fixes notified after | Owner decision B6b-D14; MDX-VAL-001 VMP-R37, VMP-R38; SOP MDX-SOP-002 |
| Incident notification | Notifies each affected customer without undue delay and no later than 72 hours after becoming aware of a personal-data incident | `docs/runbooks/INCIDENT_RESPONSE.md:72-76`; SOP MDX-SOP-003 |
| Support access only by customer grant | MDARIX staff reach an organisation's data only under a time-limited grant (at most 24 hours) that a second MDARIX administrator and then the customer's administrator approve; every use is written to the customer's own audit trail | `backend/app/support_access.py:1-17`; `tests/test_support_access_customer_approval.py::test_customer_data_opens_only_after_the_customer_approves_and_every_use_is_theirs_to_see`; SOP MDX-SOP-005 |
| Technical controls for records and signatures | Audit trail with hash chain, signature binding, re-authentication at each signing, role checks on the server | Part 11 / Annex 11 assessment MDX-SUP-003 |

### 3.2 Customer

| Control | What the customer does | MDARIX provides |
|---|---|---|
| Intended-use validation (UAT/PQ) | Validates MDARIX for its own intended use, processes and markets; its business users execute; its QA approves | UAT/PQ template MDX-CUS-001 (B6b Part E); the release pack |
| Configuration and signed configuration snapshot (G21) | Sets its markets, roles and settings; signs the configuration snapshot that its UAT/PQ tested | Configuration snapshot and comparison, `backend/app/signed_reviews/configuration.py:73,187` |
| User accounts and roles | Its Customer Administrators create accounts and assign roles | Role checks on the server, `backend/app/access/permissions.py:210-225` |
| Access reviews (G14) | Reviews who has access, at its own interval, and signs the review | Access review tool, `backend/app/signed_reviews/access_review.py`; `tests/test_b6a_signed_reviews.py::test_the_access_review` |
| Audit trail reviews (G1) | Reviews the audit trail at its own interval and signs the review | Audit trail review tool, `backend/app/signed_reviews/audit_review.py`; `tests/test_b6a_signed_reviews.py::test_who_signs_the_audit_trail_review_and_what_is_kept` |
| E-signature policy and the FDA certification letter (21 CFR 11.100(c)) | Writes its policy that holds people accountable for their signatures (11.10(j)); sends its own certification letter to FDA | Part 11 assessment MDX-SUP-003, rows 11.10(j) and 11.100(c) |
| Training records | Trains its users and keeps the records; records signer training in MDARIX where it uses that feature | Signer training records, `backend/app/signer_training/service.py:1-10` |
| Accuracy of data entered | Enters and checks the facts; MDARIX keeps unknowns as unknown | `MDX-B10-001-Intended-Use-Statement.md:40` |
| Starter rule content | Checks each market's starter question set, harm scale and word lists against its own procedure before use | `MDX-B10-001-Intended-Use-Statement.md:92` |
| Submission to authorities | Submits through the authority's own route and records the submission in MDARIX | `MDX-B10-001-Intended-Use-Statement.md:43,51` |
| Periodic review | Reviews its validated state at its own interval (MDARIX recommends every 12 months) | Owner decision B6b-D18; template MDX-CUS-004 (B6b Part E) |
| Outage procedure (G18) | Keeps a procedure to meet legal deadlines when MDARIX is unavailable | `MDX-B10-001-Intended-Use-Statement.md:100`; back-entry after an outage (MDX-VAL-002 section 4) |

### 3.3 Both

| Control | MDARIX | Customer |
|---|---|---|
| Data retention and exit | Keeps the audit trail and signatures at least 7 years; provides a full organisation export with a manifest; purges only after the export is handed back or waived, never under a legal hold | Decides its own retention periods; asks for the export and confirms the hand-back; instructs the purge or a legal hold |
| Periodic review inputs | Release packs, change notices, incident and deviation summaries, recovery records, health reports | Its own deviations, access and audit trail reviews, configuration changes, training |
| Investigation of a deviation that affects the customer | Investigates its own defect, tells the customer of a possible effect on a report or a deadline, fixes and records it (MDX-SOP-003) | Assesses the effect on its own records and reports, and acts under its own procedure |

Evidence for the "Data retention and exit" row: `docs/compliance/DATA_RETENTION_SCHEDULE.md:8-10,17,57-61`;
`backend/app/tenant_export.py:1-14,244`; `backend/app/tenant_purge.py:547,550-557`; `backend/app/legal_hold_api.py:1-10`.

## 4. What this document does not do

- It does not replace the customer's own GxP impact assessment, risk assessment or validation.
- It does not say that MDARIX is validated, compliant or certified for any customer. MDARIX validates each release
  for its own intended use; each customer validates its own use (MDX-VAL-000 DC-R30). Until the first Validation
  Summary Report is approved, MDARIX's validation status reads only: "Validation in progress; plan MDX-VAL-001
  (draft)." (MDX-VAL-001 VMP-R44).

## 5. Open points

| # | Point | Owner |
|---|---|---|
| OP-1 | The consultant confirms the indirect-impact conclusion and the split in section 3 (MDX-VAL-013 questions 1 and 4) | Consultant |
| OP-2 | The legal entity that supplies MDARIX: [legal entity: to be added on registration] (B6b spec section 11, blocker 2) | Owner |

## Signatures

Unsigned. The signed PDF and its `signatures.csv` row are added after review (MDX-VAL-000 section 2.6).

| Role | Name | Meaning of signature | Signature | Date |
|---|---|---|---|---|
| Author (R) | Srinivas Telikicherla, QA/RA | I am responsible for this document and reviewed every line of the draft. | | |
| Reviewer (C) | Independent CSV consultant | I reviewed this document; my comments are recorded. | | |
| Approver (A), second person (DC-R42) | Sriharsha Telikicherla, Product & Engineering, system owner | I confirm the technical accuracy of this document and approve it for use. | | |
