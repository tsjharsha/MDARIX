# MDX-VAL-000 Validation document control and index

| Field | Value |
|---|---|
| Document ID | MDX-VAL-000 |
| Title | Validation document control and index |
| Version | 0.3 |
| Status | DRAFT |
| Author (R) | Srinivas Telikicherla, QA/RA |
| Reviewer | Independent CSV consultant (first issue, VMP-R09; not engaged yet) |
| Approver (A) | Sriharsha Telikicherla, Product & Engineering, system owner, as the second person (DC-R42: the quality approver is the author) |
| Drafting | Drafted with software assistance; every line reviewed by Srinivas Telikicherla (DC-R43) |
| Date | 12 Nov 2026 |
| Code baseline | Product code at `628c624a`, plus two changes on branch `feat/b6b-validation-pack`: the SUPERSEDED banner in `validation/csa_package.py` and its test, and `cb75e8da` (the rule register refuses a version approved by its own builder, owner decision O3: `backend/app/rule_register/register.py` and its test); release in preparation 0.11.04 (`VERSION` file still 0.10.94) |

Change history

| Version | Date | Change | By |
|---|---|---|---|
| 0.1 | 12 Nov 2026 | First draft (B6b Part A); rules numbered DC-Rnn and split into single statements after a software-assisted review, findings dispositioned by the author | Srinivas Telikicherla |
| 0.2 | 12 Nov 2026 | After a second software-assisted review, findings dispositioned by the author: one signature rule for every document and the header field "Drafting"; signing sequence; registers and legacy files; owner decisions (section 4) and codes (section 5) recorded here; rules renumbered in reading order | Srinivas Telikicherla |
| 0.3 | 12 Nov 2026 | Owner answers of 12 Nov 2026: B6b-D7 in force from the big-bang deploy (OP-8 closed); O4 reason confirmed; O6 (RSK-066 S5, RSK-067 S4); editorial fixes after a third software-assisted review (code baseline names `cb75e8da`; cross-references) | Srinivas Telikicherla |

## 1. Purpose and scope

This document sets how MDARIX's own validation documents are numbered, versioned, reviewed, signed, stored and
retired, and lists them. It covers every document in this folder (`docs/validation/`) and the per-release records
in `docs/validation/releases/<version>/`.

It does not cover a customer's own validation records. Those stay with the customer.

## 2. Rules

Each rule has a number (DC-Rnn), so that a review comment, a deviation or a check can point to it.

### 2.1 Place and format

- **DC-R01** Every MDARIX validation document shall be kept in this repository under `docs/validation/` (owner
  decision B6b-D2).
- **DC-R02** The source of every document shall be a text file (Markdown, CSV or JSON).
- **DC-R03** A Word, Excel or PDF copy shall be generated from the source at a tagged commit.
- **DC-R04** A generated copy shall not be edited by hand.
- **DC-R05** The master copy of the scenario register shall be [scenario-register.md](scenario-register.md) in this
  folder (owner decision B6b-D3).
- **DC-R06** A customer's filled templates, test logs and approvals shall not be committed to this repository.

### 2.2 Numbering

| Prefix | Used for | Examples |
|---|---|---|
| MDX-VAL | MDARIX validation documents | -000 this index, -001 Validation Master Plan, -002 product risk assessment, -003 GAMP 5 category justification, -004 URS, -005 FS/DS, -006 IQ, -007 OQ, -008 MDARIX PQ, -009 RTM, -010 deviation log, -011 Validation Summary Report, -012 release approval record, -013 consultant brief and question pack |
| MDX-SUP | Supplier documents given to customers | -001 supplier pack, -002 GxP impact and shared responsibility, -003 Part 11 / Annex 11 assessment, -004 hosting assessment, -005 SOC 2 / ISO 27001 mapping, -006 trust facts |
| MDX-SOP | MDARIX procedures | -001 SDLC, -002 change control, -003 incident response, -004 backup and business continuity, -005 access control |
| MDX-OPS | Operational records | -001 recovery record, -002 monthly health report |
| MDX-CUS | Templates for customers | -001 UAT/PQ, -002 migration plan, -003 migration report, -004 periodic review, -005 go-live checklist and support plan, -006 customer validation instructions |

- **DC-R07** Each document shall carry an ID from the table above, or, for the four drafts moved in by owner decision O2, its legacy MDX-B10 ID (section 3.1).
- **DC-R08** A document ID shall not be reused, even after the document is retired.
- **DC-R09** A register (the scenario register, `signatures.csv`, the deviation log) shall be controlled by its git
  history; it needs no document ID and no DC-R19 header.
- **DC-R10** A file in this folder that predates this index and carries no document ID shall not be cited as
  validation evidence until it is re-issued with an ID.
- **DC-R11** Each requirement inside a document shall carry a document prefix and a number (for example VMP-R02).

### 2.3 Versions and status

- **DC-R12** A draft shall carry version 0.x.
- **DC-R13** The first approved issue shall carry version 1.0.
- **DC-R14** A later approved issue shall raise the version: 1.1 for a correction, 2.0 for a change of scope or
  approach.
- **DC-R15** Each document shall carry one of these statuses: DRAFT, IN REVIEW, APPROVED, SUPERSEDED, RETIRED.
- **DC-R16** A document shall carry the status APPROVED only when its signed PDF is listed in
  [signatures.csv](signatures.csv).
- **DC-R17** An approved document shall not be changed in place.
- **DC-R18** A correction to an approved document shall be a new version whose change history names the version it
  replaces.

### 2.4 Header

- **DC-R19** Every document shall start with this header, followed by a change history table:

```markdown
| Field | Value |
|---|---|
| Document ID | MDX-XXX-nnn |
| Title | |
| Version | 0.1 |
| Status | DRAFT |
| Author (R) | name, role |
| Reviewer | name, role |
| Approver (A) | name, role |
| Drafting | "Written by the author" or "Drafted with software assistance; every line reviewed by <name>" |
| Date | d Mon yyyy |
| Code baseline | tag or commit of the product code the document describes |
```

- **DC-R20** The author named in the header shall be a person.
- **DC-R21** Where a draft was prepared with software assistance, the named author shall review every line before
  the document goes for approval.
- **DC-R22** Software shall not be named as author, reviewer or signer.
- **DC-R23** A generated Word copy shall carry the same header fields as its source. (The Word generator comes with
  B6b Part B.)

### 2.5 Writing standard

- **DC-R24** Each document shall state its purpose and scope in its first section.
- **DC-R25** A requirement shall use "shall"; "may", "should" and "probably" shall not be used in a requirement.
- **DC-R26** Each numbered requirement shall hold one requirement that can be checked as met or not met.
- **DC-R27** Each product requirement shall be traced to a test and to its evidence (B6b Part B, RTM).
- **DC-R28** No document shall name a competitor.
- **DC-R29** No document shall state a price.
- **DC-R30** No document shall say that MDARIX is "validated", "compliant", "aligned" or "certified" for every
  customer, nor state a validation status that an approved VSR does not support (MDX-VAL-001, VMP-R44). MDARIX validates each release for its own intended use; each customer validates its own use.
- **DC-R31** Before signature, the author shall check consistency, numbering, references and the signature block,
  and record that check in the change history.

Style (guidance, not a requirement): plain English, short sentences, one idea per sentence.

### 2.6 Review and signature (owner decision B6b-D6)

- **DC-R32** A document shall be signed as a PDF, by hand and scanned or with a PDF digital signature.
- **DC-R33** MDARIX's own electronic signature shall not be used for MDARIX's own documents.
- **DC-R34** Each signed PDF shall be stored as `docs/validation/signed/<document ID>_v<version>.pdf`.
- **DC-R35** Each signature shall be one row in [signatures.csv](signatures.csv) with: document ID, version, signer,
  role, meaning, date (UTC), PDF path and the PDF's SHA-256.
- **DC-R36** A signature row and its PDF shall be committed in the same commit.
- **DC-R37** The PDF for signature shall be generated at the version it approves (1.0 for a first issue) with the
  status line "APPROVED when signed below".
- **DC-R38** The signed PDF shall be the approved record.
- **DC-R39** The source shall change to the status APPROVED in the same commit that adds the signed PDF and its
  `signatures.csv` row.
- **DC-R40** The approver (A) of a document shall be a different person from its author (R) (MDX-VAL-001, VMP-R02).
- **DC-R41** The quality approver (Srinivas Telikicherla, QA/RA; owner decision B6b-D1) shall approve every MDARIX
  validation document that the quality approver did not write.
- **DC-R42** A document that the quality approver wrote shall be approved by the system owner (Sriharsha
  Telikicherla, Product & Engineering) as the second person.
- **DC-R43** The header field "Drafting" of a document drafted with software assistance shall name the person who
  reviewed every line.

### 2.7 Retirement

- **DC-R44** A retired or superseded document shall stay in the repository.
- **DC-R45** A retired or superseded document shall carry a banner at the top that names its successor.
- **DC-R46** A superseded document shall not be given to a customer or used as evidence.

## 3. Document index

| ID | Title | File | Version | Status |
|---|---|---|---|---|
| MDX-VAL-000 | Validation document control and index | this file | 0.3 | DRAFT |
| MDX-VAL-001 | Validation Master Plan | [MDX-VAL-001_VALIDATION_MASTER_PLAN.md](MDX-VAL-001_VALIDATION_MASTER_PLAN.md) | 0.3 | DRAFT |
| MDX-VAL-002 | Product risk assessment | [MDX-VAL-002_PRODUCT_RISK_ASSESSMENT.md](MDX-VAL-002_PRODUCT_RISK_ASSESSMENT.md) | 0.3 | DRAFT |
| MDX-VAL-003 | GAMP 5 category justification | [MDX-VAL-003_GAMP5_CATEGORY_JUSTIFICATION.md](MDX-VAL-003_GAMP5_CATEGORY_JUSTIFICATION.md) | 0.3 | DRAFT |
| MDX-B10-001, -002, -005, -006 | Validation planning drafts (section 3.1) | MDX-B10-001-Intended-Use-Statement.md, MDX-B10-002-Regulatory-Applicability-Matrix.md, MDX-B10-005-Traceability-Structure.md, MDX-B10-006-Threat-Model.md | 0.1 | DRAFT |
| MDX-VAL-013 | Consultant brief and question pack | [MDX-VAL-013_CONSULTANT_BRIEF.md](MDX-VAL-013_CONSULTANT_BRIEF.md) | 0.2 | DRAFT |
| (register) | Scenario register (master copy) | [scenario-register.md](scenario-register.md) | n/a | Controlled by git history |
| (register) | Signature register | [signatures.csv](signatures.csv) | n/a | Empty: nothing signed yet |
| MDX-VAL-008 | MDARIX PQ protocol | [MDX-VAL-008_PQ_PROTOCOL.md](MDX-VAL-008_PQ_PROTOCOL.md) | 0.1 | DRAFT |
| MDX-VAL-010 | Deviation log and change-impact template | [MDX-VAL-010_DEVIATION_LOG_AND_CHANGE_IMPACT.md](MDX-VAL-010_DEVIATION_LOG_AND_CHANGE_IMPACT.md); log [deviation-log.csv](deviation-log.csv) | 0.1 | DRAFT; log empty |
| MDX-VAL-004, -005, -006, -007, -009, -011, -012 | URS, FS/DS, IQ record, OQ protocol and results, RTM, VSR, release approval record | Generated per release by `scripts/validation_pack.py` into `releases/<release>/` | per release | None generated yet for a release |
| (register) | Requirements (URS source) | [requirements.csv](requirements.csv) | n/a | Controlled by git history; 69 requirements |
| MDX-SUP, MDX-SOP, MDX-OPS, MDX-CUS | Planned (B6b Parts C to E, section 5) | | | Not written |

Other files in this folder: [AI_GOLDEN_DATASET_QUALIFICATION.md](AI_GOLDEN_DATASET_QUALIFICATION.md) and
[LOCAL_VALIDATION_DATASET.md](LOCAL_VALIDATION_DATASET.md) predate this index. They are kept for the AI release gate
and the local data set; AI is off and out of scope (MDX-VAL-001, section 15). Neither is cited as validation
evidence (DC-R10).

### 3.1 Validation planning drafts of 8 Nov 2026

MDX-VAL-001 and -002 reference these drafts, moved into this folder on 12 Nov 2026 (owner decision O2) unchanged:
[MDX-B10-001](MDX-B10-001-Intended-Use-Statement.md) intended use, [MDX-B10-002](MDX-B10-002-Regulatory-Applicability-Matrix.md) regulatory applicability matrix,
[MDX-B10-005](MDX-B10-005-Traceability-Structure.md) traceability structure and [MDX-B10-006](MDX-B10-006-Threat-Model.md) threat model. Each is version
0.1, status DRAFT. They are now under version control; MDX-VAL-001 is not approved as 1.0 before they are approved
(VMP-R01). The planning copies carry a pointer to these. MDX-B10-003 (validation plan) is superseded by MDX-VAL-001, and MDX-B10-004 (software risk assessment) by
MDX-VAL-002; both carry a banner saying so.

### 3.2 Superseded and corrected documents

| Document | What happened | Successor |
|---|---|---|
| `docs/compliance/CSA_MVP_VALIDATION_PACKAGE.md` and `.json` (MDARIX-CSA-MVP-1.0, never executed) | SUPERSEDED | MDX-VAL-001 now; the per-release pack (B6b Part B) |
| `docs/compliance/CSA_MVP_VALIDATION_PROTOCOL.md` | SUPERSEDED | MDX-VAL-001 |
| `docs/compliance/CSA_REQUIREMENTS_TRACEABILITY.md` | SUPERSEDED | The generated RTM (MDX-VAL-009, B6b Part B) |
| `docs/compliance/CSA_CUSTOMER_IMPLEMENTATION_INSTRUCTIONS.md` | SUPERSEDED | MDX-CUS-006 (B6b Part E) |
| `docs/compliance/COMPLIANCE_VALIDATION_PROTOCOL.md` | Corrected 12 Nov 2026 (no password expiry); current reference for the application controls | The Part 11 / Annex 11 assessment (MDX-SUP-003, B6b Part C) |

## 4. Owner decisions in force

These documents cite "owner decision B6b-Dn" or "owner decision On". Each one is listed here, so that the signed
copy of this document is the controlled record of it. The owner (Srinivas Telikicherla) approved D1 to D21 on
12 Nov 2026 ("approve B6b spec") and answered O1 to O4 and O6 on 12 Nov 2026. O5 is older (see its row). Items marked "consultant to confirm" are
also questions in MDX-VAL-013.

| ID | Decision |
|---|---|
| B6b-D1 | System owner: Sriharsha Telikicherla (Product & Engineering). Quality approver: Srinivas Telikicherla (QA/RA). Nobody approves their own work |
| B6b-D2 | MDARIX validation documents live in the product repository under `docs/validation/`, tagged with each release; customers' filled copies never go there |
| B6b-D3 | The master scenario register is `docs/validation/scenario-register.md`; the planning copy keeps a pointer only |
| B6b-D4 | FMEA: severity, occurrence and detectability 1 to 5; RPN = S x O x D; class set by severity alone; action at RPN 40 or more, or S5 with D 3 or more (consultant to confirm) |
| B6b-D5 | GAMP 5: Category 4 for MDARIX, Category 5 for anything written for one customer, Category 1 for infrastructure; not shown to a customer before the consultant confirms |
| B6b-D6 | MDARIX's own documents are signed as PDFs (by hand and scanned, or a PDF digital signature), with the SHA-256 in `signatures.csv`; MDARIX's own e-signature is not used for them |
| B6b-D7 | The quality approver signs a release approval record before every production deploy; for an emergency fix, a written OK before the deploy and the signed record within 1 working day. In force for every production deploy from the big-bang deploy onward, before MDX-VAL-001 is approved as 1.0 (owner, 12 Nov 2026; MDX-VAL-001 VMP-R41, OP-8 closed) |
| B6b-D8 | Recovery point stated to customers: 24 hours today (daily encrypted backup, no point-in-time recovery); target 15 minutes with point-in-time recovery on pilot hosting |
| B6b-D9 | EU GMP Annex 11 is assessed clause by clause as a benchmark; it binds EU pharmaceutical GMP only; MDARIX is never called "Annex 11 compliant" |
| B6b-D10 | After a restore, every unsent outbox event older than the restore point is held (dead-lettered, audited); only those the mail provider's log shows as not sent are replayed |
| B6b-D11 | Health-report uptime from the cloud monitoring uptime check; one fixed list of read-only production queries, approved once |
| B6b-D12 | Excel files are written by a small standard-library writer, tested against the existing reader; no new dependency |
| B6b-D13 | Documents: the PDF is saved from the approved Word copy. Records (recovery, health, approval): the product's PDF module |
| B6b-D14 | Customers get 10 working days' notice of a change to a class-A function, a rule floor or a sub-processor; emergency security fixes are notified after |
| B6b-D15 | The GxP workflow check of a real recovery runs on a scratch copy of the same backup, never as test data in production |
| B6b-D16 | Until staging exists, formal execution runs on a controlled local environment (a clean test database built from the tagged commit), recorded as an IQ of that environment and labelled in the VSR |
| B6b-D17 | Tests are tagged for class-A scenarios first; class B and C are reported as "automated suite, untagged", with coverage per class shown |
| B6b-D18 | Review intervals: customer periodic review every 12 months; health report monthly; supplier re-assessment every 12 months |
| B6b-D19 | The supplier pack and the release pack are shared under a non-disclosure agreement only; the public trust page carries only verified facts |
| B6b-D20 | The consultant is engaged before Part A is approved, for Part A, the GxP impact and Part 11 / Annex 11 assessments and the first release pack; until then Part A stays DRAFT and is shared with no customer |
| B6b-D21 | The test marker is `requirement(<scenario ID>)`, as registered in `pytest.ini`; `requirements.csv` maps REQ IDs to scenarios |
| O1 | Validation records are kept at least 10 years after a release leaves the last customer, 15 years where a customer makes implantable devices (consultant to confirm) |
| O2 | MDX-B10-001, -002, -005 and -006 move from the planning folder into `docs/validation/` (done 12 Nov 2026, commit `69248534`) |
| O3 | The rule register refuses the same person as builder and approver of a rule version (MDX-VAL-002 RSK-065; `backend/app/rule_register/register.py`, added 12 Nov 2026, commit `cb75e8da`) |
| O4 | RSK-023, RSK-029 and RSK-039 are class A: RSK-023 by the late-report line of severity 5 (confirmed by the owner, 12 Nov 2026); RSK-039 by the privacy line of severity 4; RSK-029 by the privacy line, now severity 5 (O8) |
| O5 | No periodic password expiry (NIST SP 800-63B); lockout, breached-password checks and multi-factor authentication instead. Decided by the owner at MVP readiness, before B6b; listed here so that it is controlled (consultant to confirm, MDX-VAL-013 question 6) |
| O6 | RSK-066 (purge, retention, legal hold) has severity S5; RSK-067 (sign-in and sessions) stays S4 (owner, 12 Nov 2026) |
| O7 | Severity 5 includes the permanent loss of regulated records; severity 4 the loss of regulated records that can be recovered (owner, 12 Nov 2026; MDX-VAL-002 section 3.7) |
| O8 | RSK-029 (formula injection in an exported CSV) has severity S5: data can leave the organisation (owner, 12 Nov 2026) |

## 5. Codes used in these documents

| Code | Meaning |
|---|---|
| B2, B3, B4, B5, B7, B8, B9, B9b | Approved product builds: B2 import and migration; B3 FDA eMDR; B4 rule register; B5 investigation challenge loop; B7 routine complaint path; B8 EU and GB MIR files; B9 India, Canada and US roles; B9b other countries |
| B6a | Approved build for speed and evidence (deadline list, back-entry, clock check, signed reviews, reason for change, trace, similar wording, Value Centre) |
| B6b | This validation build. Parts A to E: A foundation (these documents); B per-release validation pack; C supplier pack and assessments; D recovery validation, health report and registers; E customer templates. "B6b B1" is item B1 of Part B (`requirements.csv`) |
| MDX-B10-nnn | Validation planning drafts of 8 Nov 2026 (section 3.1) |
| PT-nn, G-n | Penetration-test threats and threat-model gaps in MDX-B10-006 |
| RSK-nnn | Failure modes in MDX-VAL-002 |
| REQ-&lt;AREA&gt;-nnn | Requirements (seed rows in MDX-B10-005 section 7; full list in `requirements.csv`, MDX-VAL-004) |
| IN, CI, TR, RG, DT, RR, IV, B5, CP, RT, BK, EM, UA, B8, B9, OC, P360, S360, B6 followed by a number | Scenario IDs in the scenario register |
| O1 to O6, B6b-D1 to -D21 | Owner decisions (section 4) |

## 6. How the rules in section 2 are checked

| Rules | Check | Evidence |
|---|---|---|
| Place, format, numbering, versions, header, writing standard (sections 2.1 to 2.5) | The author's pre-signature check (DC-R31), recorded in the change history; the reviewer's comments | Change history; signed PDF |
| Traceability of product requirements (DC-R27) | The validation-pack generator refuses a requirement without a test or scenario (B6b Part B) | RTM in the release folder |
| Review, signature and signing sequence (section 2.6) | The approver checks the signature block against DC-R40 to DC-R43 before signing; each signature has its `signatures.csv` row | `signatures.csv`; git history |
| Retirement (section 2.7) | Banner check at each document's next review | The superseded file in git |

## 7. Signatures

Unsigned. The signed PDF and its `signatures.csv` row are added after review (DC-R32 to DC-R36).

| Role | Name | Meaning of signature | Signature | Date |
|---|---|---|---|---|
| Author (R) | Srinivas Telikicherla, QA/RA | I am responsible for this document and reviewed every line of the draft. | | |
| Reviewer (C) | Independent CSV consultant | I reviewed this document; my comments are recorded. | | |
| Approver (A), second person (DC-R42) | Sriharsha Telikicherla, Product & Engineering, system owner | I approve these document-control rules for use. | | |
