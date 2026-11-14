# MDX-SUP-001 Supplier pack

| Field | Value |
|---|---|
| Document ID | MDX-SUP-001 |
| Title | MDARIX supplier pack for customers' supplier qualification |
| Version | 0.2 |
| Status | DRAFT |
| Author (R) | Srinivas Telikicherla, QA/RA, quality approver |
| Reviewer | Independent CSV consultant (not engaged yet) |
| Approver (A) | Sriharsha Telikicherla, Product & Engineering, system owner, for technical accuracy (MDX-VAL-000 DC-R42) |
| Drafting | Drafted with software assistance; every line reviewed by Srinivas Telikicherla (MDX-VAL-000, DC-R43) |
| Date | 14 Nov 2026 |
| Code baseline | Product code at `6b01eda5` (tip of `feat/b6b-validation-pack`); B6b Part C changes no code; release in preparation 0.11.04 (`VERSION` file still 0.10.94) |

Change history

| Version | Date | Change | By |
|---|---|---|---|
| 0.1 | 14 Nov 2026 | First draft (B6b Part C, item C1) | Srinivas Telikicherla |
| 0.2 | 14 Nov 2026 | OP-5 closed: SP-R02 and the emergency-notice period confirmed as written (owner decision O37) | Srinivas Telikicherla |

## 1. Purpose and scope

A medical device manufacturer that uses MDARIX for regulated work must qualify MDARIX as a supplier. This pack gives
its quality unit, in one place, what a supplier audit usually asks for: who MDARIX is, how it controls quality,
development, change, security, hosting, backup, incidents, support access, sub-processors and exit, and how the
customer can audit MDARIX. Each section points to the controlled document or the evidence that supports it.

The pack is shared under a non-disclosure agreement only (owner decision B6b-D19). It does not replace the
customer's own assessment of MDARIX or its own validation.

## 2. Who MDARIX is

| Item | Content |
|---|---|
| Supplier | [legal entity: to be added on registration]. The operating company is not registered yet (B6b spec section 11, blocker 2); the legal entity and its signatory will be named here before any contract |
| Product | MDARIX: post-market intelligence and decision-support software for medical device manufacturers, offered as a hosted service (`MDX-B10-001-Intended-Use-Statement.md:34-35`) |
| Intended use and limits | MDX-B10-001; GxP impact and the MDARIX/customer split: MDX-SUP-002 |
| System owner | Sriharsha Telikicherla, Product & Engineering |
| Quality approver | Srinivas Telikicherla, QA/RA |
| Support contact | The support address shown in the product's Help menu and on every e-mail (`docs/handover/52_SUPPORT_AND_OWNERSHIP_HANDOVER.md:64-67`) |

## 3. Quality management overview

MDARIX runs its own procedures for validation, development, change, incidents, backup and access. **MDARIX holds no
quality-management or security certification and claims none.**

| Area | Controlled document |
|---|---|
| Document control and the owner decisions in force | MDX-VAL-000 |
| Validation Master Plan (roles, segregation of duties, per-release validation) | MDX-VAL-001 |
| Product risk assessment (FMEA) | MDX-VAL-002 |
| GAMP 5 category justification | MDX-VAL-003 |
| Software development lifecycle | MDX-SOP-001 |
| Change control, re-test rules and customer change notice | MDX-SOP-002 |
| Incident response and complaints about MDARIX | MDX-SOP-003 |
| Backup, recovery and business continuity | MDX-SOP-004 |
| Access control | MDX-SOP-005 |
| Deviation log and change impact | MDX-VAL-010 |

Every document is DRAFT until signed (MDX-VAL-000 section 2.6). Nobody approves their own work (owner decision
B6b-D1).

**Validation status.** MDARIX validates each release for its own intended use; each customer validates its own use.
Until the first Validation Summary Report is approved, the status reads only: "Validation in progress; plan
MDX-VAL-001 (draft)." (MDX-VAL-001 VMP-R44).

## 4. Software development lifecycle

Specs are approved before build; every behaviour change ships with a test that fails without it; secrets are scanned
on every pull request; release images are scanned and carry a software bill of materials; a release is a tag equal
to the `VERSION` file. Details and evidence: MDX-SOP-001.

## 5. Change control and customer notice

- Every customer on the shared plane runs the same version (MDX-VAL-001 section 9.2).
- Each release has a change-impact assessment and re-test per its risk (MDX-SOP-002 sections 3.2, 3.3).
- The quality approver signs a release approval record before every production deploy (owner decision B6b-D7).
- Customers get at least **10 working days' notice** of a change to a class-A function, a rule floor or a
  sub-processor; an emergency security fix is notified within 1 working day after the deploy (owner decision
  B6b-D14; MDX-SOP-002 sections 3.5, 3.6).
- Every release has release notes.

## 6. Security

| Topic | Summary | Detail |
|---|---|---|
| Threat model | Components, assets, trust boundaries, STRIDE and 15 penetration-test threats, with known gaps | MDX-B10-006 |
| Control mapping | ISO/IEC 27001:2022 Annex A and SOC 2 criteria, mapped control by control, gaps named | MDX-SUP-005 |
| Records and signatures | Audit trail with hash chain; re-authentication at each signing; signatures bound to content | MDX-SUP-003 |
| Penetration test | No independent penetration test has been run yet; one is planned before the first paid pilot, with real data only after it (`MDX-B10-001-Intended-Use-Statement.md:97`) | to follow |
| Verified public statements | The only statements MDARIX publishes, each with evidence | MDX-SUP-006 |

## 7. Hosting and data location

The service runs on Google Cloud in Mumbai, India; encrypted backup copies are kept in Delhi, India; transactional
e-mail and mailboxes are with Zoho in India (`legal/SUBPROCESSORS.md:12-17`). The hosting assessment, its risks and
its decision are in MDX-SUP-004. Today's production runs on the provider's free-trial billing account, which ends
about 11 Jan 2027 (MDX-SUP-004, H-1).

## 8. Backup and disaster recovery

| Item | Content | Evidence |
|---|---|---|
| Backup | Daily encrypted backup of every database and of stored files, copied off-site; daily disk snapshot kept 14 days | `docs/runbooks/BACKUP_AND_RESTORE.md:10-15`; `docs/runbooks/GCP_DEPLOYMENT.md:21-22` |
| Recovery point | 24 hours today (daily encrypted backup, no point-in-time recovery); target 15 minutes with point-in-time recovery on pilot hosting | Owner decision B6b-D8; `docs/runbooks/BACKUP_AND_RESTORE.md:3-5` |
| Recovery time | 4 hours | `docs/runbooks/BACKUP_AND_RESTORE.md:5` |
| Restore drills | Quarterly. Production backups restored on 16 Oct 2026 and 3 Nov 2026; the 3 Nov drill took 7 min 19 s | `docs/runbooks/BACKUP_AND_RESTORE.md:149-157` |
| Recovery validation | After a restore, a recovery check and a signed recovery record (MDX-OPS-001) covering the audit chain, configuration, held e-mail events and the recovery window per customer | MDX-SOP-004 section 5; built in B6b Part D (not yet in this baseline) |

## 9. Incident handling and notification

Incidents are recorded (`INC-YYYY-NNN`), triaged SEV1 to SEV3, contained, notified and reviewed (MDX-SOP-003). A
customer whose personal data may be affected is told without undue delay and no later than 72 hours after MDARIX
becomes aware (`docs/runbooks/INCIDENT_RESPONSE.md:72-76`). A complaint about MDARIX is assessed for its effect on
the customer's reports and deadlines within 1 working day (MDX-SOP-003 section 4).

## 10. Support access

MDARIX staff see or change a customer's data only under a support grant that a second MDARIX administrator and
then the customer's own administrator approve, for at most 24 hours; every use is written to the customer's own audit
trail (`backend/app/support_access.py:1-17`; MDX-SOP-005 section 3).

## 11. Sub-processors

The services that receive customer or personal data are listed in `legal/SUBPROCESSORS.md:10-20`, with purpose,
data, region and when each is used. A new provider is added there before it receives any data
(`legal/SUBPROCESSORS.md:5-6`), and a sub-processor change gets 10 working days' notice (section 5). AI providers are
not used: AI is off for every organisation (`legal/SUBPROCESSORS.md:18`).

## 12. Exit and retirement

| Step | What happens | Evidence |
|---|---|---|
| Export | The customer receives a full organisation export: every table, every stored file, a readable CSV bundle of the quality records, and a manifest with counts, SHA-256 per entry and the audit trail's verified head. Credentials are never exported | `backend/app/tenant_export.py:1-8` |
| Download window | The export can be downloaded for 7 days, then it is deleted | `backend/app/tenant_export.py:11-14,42` |
| Hand-back before purge | A customer organisation is purged only after the export was handed back or a waiver recorded | `backend/app/tenant_purge.py:550-557` |
| Audit trail retention | Audit events and signatures are kept at least 7 years after each event while the account exists, never changed or deleted; at exit the whole trail goes to the customer in the export, and the customer keeps it for its own regulatory period | `docs/compliance/DATA_RETENTION_SCHEDULE.md:17` |
| Legal hold | While a legal hold is set, nothing of the organisation is purged, erased or retired | `backend/app/legal_hold_api.py:1-10`; `tests/test_legal_hold.py::test_a_hold_stops_the_purge_and_the_erasure_and_records_the_refusal` |
| Backups after purge | Purged data remains in encrypted backups for up to 90 days; a restore re-applies every purge before anyone signs in | `docs/compliance/DATA_RETENTION_SCHEDULE.md:51-55`; `docs/runbooks/BACKUP_AND_RESTORE.md:183-185` |

## 13. Audit support

- **SP-R01** MDARIX shall give a customer, under a non-disclosure agreement and on request, the documents listed in
  this pack and the release pack of the release the customer runs.
- **SP-R02** MDARIX shall answer a customer's supplier questionnaire within 10 working days of receipt.
- **SP-R03** MDARIX shall support a remote audit by video call with screen sharing of records; an on-site audit by
  agreement.
- **SP-R04** MDARIX shall record each customer audit finding in its register of customer audit findings (B6b Part D)
  and answer it with an action and a date.
- **SP-R05** This pack shall be reviewed every 12 months (owner decision B6b-D18) and at each change to a section's
  source document.

## 14. Open points

| # | Point | Owner |
|---|---|---|
| OP-1 | Name the legal entity and its signatory (section 2) | Owner |
| OP-2 | Obtain the provider audit reports and terms (MDX-SUP-004 section 3) | Owner |
| OP-3 | Fill the named roles of `docs/handover/52_SUPPORT_AND_OWNERSHIP_HANDOVER.md` before the first pilot | Owner |
| OP-4 | `docs/compliance/DATA_RETENTION_SCHEDULE.md:48` states 14 days for local backups; `docs/runbooks/BACKUP_AND_RESTORE.md:15-21` states 30 daily and 12 monthly (owner decision, 5 Nov 2026). Correct the retention schedule | System owner |
| OP-5 | Closed: the questionnaire response time (SP-R02, 10 working days) and the emergency-notice period (section 5; MDX-SOP-002 CC-R17, 1 working day) confirmed as written by the owner, 14 Nov 2026 (MDX-VAL-000 owner decision O37) | Owner |

## Signatures

Unsigned. The signed PDF and its `signatures.csv` row are added after review (MDX-VAL-000 section 2.6).

| Role | Name | Meaning of signature | Signature | Date |
|---|---|---|---|---|
| Author (R) | Srinivas Telikicherla, QA/RA | I am responsible for this document and reviewed every line of the draft. | | |
| Reviewer (C) | Independent CSV consultant | I reviewed this document; my comments are recorded. | | |
| Approver (A), second person (DC-R42) | Sriharsha Telikicherla, Product & Engineering, system owner | I confirm the technical accuracy of this document and approve it for use under a non-disclosure agreement. | | |
