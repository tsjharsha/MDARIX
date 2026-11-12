# MDX-VAL-000 Validation document control and index

| Field | Value |
|---|---|
| Document ID | MDX-VAL-000 |
| Title | Validation document control and index |
| Version | 0.1 |
| Status | DRAFT, for review and signature |
| Author (R) | Srinivas Telikicherla, QA/RA |
| Reviewer | Independent CSV consultant (first full pack, VMP-R07; not engaged yet) |
| Approver (A) | Sriharsha Telikicherla, Product & Engineering, system owner |
| Date | 12 Nov 2026 |
| Code baseline | Product code at `628c624a` (branch `feat/b6b-validation-pack` adds documents only); release in preparation 0.11.04 (`VERSION` file still 0.10.94) |

Change history

| Version | Date | Change | By |
|---|---|---|---|
| 0.1 | 12 Nov 2026 | First draft (B6b Part A); rules numbered DC-Rnn and split into single statements after an independent review | Srinivas Telikicherla |

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
| MDX-VAL | MDARIX validation documents | -000 this index, -001 Validation Master Plan, -002 product risk assessment, -003 GAMP 5 category justification, -004 URS, -005 FS/DS, -006 IQ, -007 OQ, -008 MDARIX PQ, -009 RTM, -010 deviation log, -011 Validation Summary Report, -012 release approval record |
| MDX-SUP | Supplier documents given to customers | -001 supplier pack, -002 GxP impact and shared responsibility, -003 Part 11 / Annex 11 assessment, -004 hosting assessment, -005 SOC 2 / ISO 27001 mapping, -006 trust facts |
| MDX-SOP | MDARIX procedures | -001 SDLC, -002 change control, -003 incident response, -004 backup and business continuity, -005 access control |
| MDX-OPS | Operational records | -001 recovery record, -002 monthly health report |
| MDX-CUS | Templates for customers | -001 UAT/PQ, -002 migration plan, -003 migration report, -004 periodic review, -005 go-live checklist and support plan, -006 customer validation instructions |

- **DC-R07** Each document shall carry an ID from the table above.
- **DC-R08** A document ID shall not be reused, even after the document is retired.
- **DC-R09** Each requirement inside a document shall carry a document prefix and a number (for example VMP-R01).

### 2.3 Versions and status

- **DC-R10** A draft shall carry version 0.x.
- **DC-R11** The first approved issue shall carry version 1.0.
- **DC-R12** A later approved issue shall raise the version: 1.1 for a correction, 2.0 for a change of scope or
  approach.
- **DC-R13** Each document shall carry one of these statuses: DRAFT, IN REVIEW, APPROVED, SUPERSEDED, RETIRED.
- **DC-R14** A document shall carry the status APPROVED only when its signed PDF is listed in
  [signatures.csv](signatures.csv).
- **DC-R15** An approved document shall not be changed in place.
- **DC-R16** A correction to an approved document shall be a new version whose change history names the version it
  replaces.

### 2.4 Header

- **DC-R17** Every document shall start with this header, followed by a change history table:

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
| Date | d Mon yyyy |
| Code baseline | tag or commit of the product code the document describes |
```

- **DC-R18** The author named in the header shall be a person.
- **DC-R19** Where a draft was prepared with software assistance, the named author shall review every line before
  the document goes for approval.
- **DC-R20** Software shall not be named as author, reviewer or signer.
- **DC-R21** A generated Word copy shall carry the same header fields as its source. (The Word generator comes with
  B6b Part B.)

### 2.5 Writing standard

- **DC-R22** Each document shall state its purpose and scope in its first section.
- **DC-R23** A requirement shall use "shall"; "may", "should" and "probably" shall not be used in a requirement.
- **DC-R24** Each numbered requirement shall hold one requirement that can be checked as met or not met.
- **DC-R25** Each product requirement shall be traced to a test and to its evidence (B6b Part B, RTM).
- **DC-R26** No document shall name a competitor.
- **DC-R27** No document shall state a price.
- **DC-R28** No document shall say that MDARIX is "validated", "compliant", "aligned" or "certified" for every
  customer. MDARIX is validated for its own intended use; each customer validates its own use.
- **DC-R29** Before signature, the author shall check consistency, numbering, references and the signature block,
  and record that check in the change history.

Style (guidance, not a requirement): plain English, short sentences, one idea per sentence.

### 2.6 Review and signature (owner decision B6b-D6)

- **DC-R30** A document shall be signed as a PDF, by hand and scanned or with a PDF digital signature.
- **DC-R31** MDARIX's own electronic signature shall not be used for MDARIX's own documents.
- **DC-R32** Each signed PDF shall be stored as `docs/validation/signed/<document ID>_v<version>.pdf`.
- **DC-R33** Each signature shall be one row in [signatures.csv](signatures.csv) with: document ID, version, signer,
  role, meaning, date (UTC), PDF path and the PDF's SHA-256.
- **DC-R34** A signature row and its PDF shall be committed in the same commit.
- **DC-R35** The approver (A) of a document shall be a different person from its author (R) (MDX-VAL-001, VMP-R01).

### 2.7 Retirement

- **DC-R36** A retired or superseded document shall stay in the repository.
- **DC-R37** A retired or superseded document shall carry a banner at the top that names its successor.
- **DC-R38** A superseded document shall not be given to a customer or used as evidence.

## 3. Document index

| ID | Title | File | Version | Status |
|---|---|---|---|---|
| MDX-VAL-000 | Validation document control and index | this file | 0.1 | DRAFT |
| MDX-VAL-001 | Validation Master Plan | [MDX-VAL-001_VALIDATION_MASTER_PLAN.md](MDX-VAL-001_VALIDATION_MASTER_PLAN.md) | 0.1 | DRAFT |
| MDX-VAL-002 | Product risk assessment | [MDX-VAL-002_PRODUCT_RISK_ASSESSMENT.md](MDX-VAL-002_PRODUCT_RISK_ASSESSMENT.md) | 0.1 | DRAFT |
| MDX-VAL-003 | GAMP 5 category justification | [MDX-VAL-003_GAMP5_CATEGORY_JUSTIFICATION.md](MDX-VAL-003_GAMP5_CATEGORY_JUSTIFICATION.md) | 0.1 | DRAFT |
| (register) | Scenario register (master copy) | [scenario-register.md](scenario-register.md) | n/a | Controlled by git history |
| (register) | Signature register | [signatures.csv](signatures.csv) | n/a | Empty: nothing signed yet |
| MDX-VAL-004 to -012, MDX-SUP, MDX-SOP, MDX-OPS, MDX-CUS | Planned (B6b Parts B to E) | | | Not written |

Other files in this folder: [AI_GOLDEN_DATASET_QUALIFICATION.md](AI_GOLDEN_DATASET_QUALIFICATION.md) and
[LOCAL_VALIDATION_DATASET.md](LOCAL_VALIDATION_DATASET.md) predate this index. They are kept for the AI release gate
and the local data set; AI is off and out of scope (MDX-VAL-001, section 15).

### 3.1 Referenced planning documents (not under version control yet)

MDX-VAL-001 and -002 reference these drafts of 8 Nov 2026 in `MDARIX-planning/b10/`: MDX-B10-001 (intended use),
-002 (regulatory applicability matrix), -005 (traceability structure) and -006 (threat model). They stay in force as
drafts. MDX-B10-003 (validation plan) is superseded by MDX-VAL-001, and MDX-B10-004 (software risk assessment) by
MDX-VAL-002; both carry a banner saying so.

### 3.2 Superseded and corrected documents

| Document | Status | Successor |
|---|---|---|
| `docs/compliance/CSA_MVP_VALIDATION_PACKAGE.md` and `.json` (MDARIX-CSA-MVP-1.0, never executed) | SUPERSEDED | MDX-VAL-001 now; the per-release pack (B6b Part B) |
| `docs/compliance/CSA_MVP_VALIDATION_PROTOCOL.md` | SUPERSEDED | MDX-VAL-001 |
| `docs/compliance/CSA_REQUIREMENTS_TRACEABILITY.md` | SUPERSEDED | The generated RTM (MDX-VAL-009, B6b Part B) |
| `docs/compliance/CSA_CUSTOMER_IMPLEMENTATION_INSTRUCTIONS.md` | SUPERSEDED | MDX-CUS-006 (B6b Part E) |
| `docs/compliance/COMPLIANCE_VALIDATION_PROTOCOL.md` | Corrected 12 Nov 2026 (no password expiry); current reference for the application controls | The Part 11 / Annex 11 assessment (MDX-SUP-003, B6b Part C) |

## 4. Signatures

Unsigned. The signed PDF and its `signatures.csv` row are added after review (DC-R30 to DC-R34).

| Role | Name | Meaning of signature | Signature | Date |
|---|---|---|---|---|
| Author (R), quality approver | Srinivas Telikicherla, QA/RA | I wrote this document and reviewed every line. | | |
| Reviewer (C) | Independent CSV consultant | I reviewed this document; my comments are recorded. | | |
| Approver (A), system owner | Sriharsha Telikicherla, Product & Engineering | I approve these document-control rules for use. | | |
