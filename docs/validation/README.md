# MDX-VAL-000 Validation document control and index

| Field | Value |
|---|---|
| Document ID | MDX-VAL-000 |
| Title | Validation document control and index |
| Version | 0.1 |
| Status | DRAFT, for review and signature |
| Author (R) | Srinivas Telikicherla, QA/RA |
| Reviewer | Independent CSV consultant (not engaged yet) |
| Approver (A) | Sriharsha Telikicherla, Product & Engineering, system owner |
| Date | 12 Nov 2026 |
| Code baseline | Branch `feat/b6b-validation-pack` from `628c624a`; release in preparation 0.11.04 (`VERSION` file still 0.10.94) |

Change history

| Version | Date | Change | By |
|---|---|---|---|
| 0.1 | 12 Nov 2026 | First draft (B6b Part A) | Srinivas Telikicherla |

## 1. Purpose and scope

This document sets how MDARIX's own validation documents are numbered, versioned, reviewed, signed, stored and
retired, and lists them. It covers every document in this folder (`docs/validation/`) and the per-release records
in `docs/validation/releases/<version>/`.

It does not cover a customer's own validation records. A customer's filled templates, test logs and approvals stay
with the customer and never enter this repository.

## 2. Rules

### 2.1 Place and format

1. Every MDARIX validation document shall be kept in this repository under `docs/validation/` (owner decision B6b-D2).
2. The source of every document shall be text (Markdown, CSV or JSON), so that every change shows in a diff.
3. A Word, Excel or PDF copy shall be generated from the source at a tagged commit; it shall never be edited by hand.
4. The scenario register master copy shall be [scenario-register.md](scenario-register.md) in this folder (owner
   decision B6b-D3). The copy in the planning folder carries a pointer and is no longer updated.

### 2.2 Numbering

| Prefix | Used for | Examples |
|---|---|---|
| MDX-VAL | MDARIX validation documents | -000 this index, -001 Validation Master Plan, -002 product risk assessment, -003 GAMP 5 category justification, -004 URS, -005 FS/DS, -006 IQ, -007 OQ, -008 MDARIX PQ, -009 RTM, -010 deviation log, -011 Validation Summary Report, -012 release approval record |
| MDX-SUP | Supplier documents given to customers | -001 supplier pack, -002 GxP impact and shared responsibility, -003 Part 11 / Annex 11 assessment, -004 hosting assessment, -005 SOC 2 / ISO 27001 mapping, -006 trust facts |
| MDX-SOP | MDARIX procedures | -001 SDLC, -002 change control, -003 incident response, -004 backup and business continuity, -005 access control |
| MDX-OPS | Operational records | -001 recovery record, -002 monthly health report |
| MDX-CUS | Templates for customers | -001 UAT/PQ, -002 migration plan, -003 migration report, -004 periodic review, -005 go-live checklist and support plan, -006 customer validation instructions |

5. A document number shall never be reused, even after the document is retired.
6. Requirements inside a document shall carry a local number (for example VMP-R01), so that a review comment, a
   deviation or a test can point to one requirement.

### 2.3 Versions and status

7. A draft shall carry version 0.x. The first approved issue shall be 1.0. A later approved change shall raise the
   version (1.1 for a correction, 2.0 for a change of scope or approach).
8. Each document shall carry one of these statuses: DRAFT, IN REVIEW, APPROVED, SUPERSEDED, RETIRED.
9. A document shall be called APPROVED only when its signed PDF is listed in [signatures.csv](signatures.csv).
10. An approved document shall never be changed in place. A correction shall be a new version that names the
    version it replaces in its change history.

### 2.4 Header

11. Every document shall start with this header, then the change history table:

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
| Code baseline | tag or commit |
```

12. The author named in the header shall be a person. Where a draft was prepared with software assistance, the named
    author shall have reviewed every line and is responsible for the content; software is never an author, reviewer
    or signer.
13. The Word header of a generated copy shall carry the same fields. (The Word generator comes with B6b Part B.)

### 2.5 Writing standard

14. Each document shall state its purpose and scope first.
15. A requirement shall use "shall". "May", "should" and "probably" shall not be used for a requirement.
16. Each statement shall hold one requirement, and each requirement shall be testable.
17. Each product requirement shall be traced to a test and to its evidence (B6b Part B, RTM).
18. Text shall be plain English in short sentences.
19. No document shall name a competitor, state a price, or say that MDARIX is "validated", "compliant", "aligned" or
    "certified" for every customer. MDARIX is validated for its own intended use; each customer validates its use.
20. Before signature, the author shall check consistency, numbering, references and the signature block.

### 2.6 Review and signature (owner decision B6b-D6)

21. A document shall be signed as a PDF, either by hand and scanned or with a PDF digital signature.
22. MDARIX's own electronic signature shall not be used for MDARIX's own documents.
23. Each signed PDF shall be stored as `docs/validation/signed/<document ID>_v<version>.pdf`.
24. Each signature shall be one row in [signatures.csv](signatures.csv): document ID, version, signer, role, meaning,
    date (UTC), PDF path and the PDF's SHA-256. The row and the PDF shall be committed together.
25. Nobody shall approve their own work: the approver (A) shall be a different person from the author (R)
    (MDX-VAL-001, section 6).

### 2.7 Retirement

26. A retired or superseded document shall stay in the repository with a banner at the top that names its successor.
27. A superseded document shall not be given to a customer or used as evidence.

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
and the local data set; AI is off and out of scope (MDX-VAL-001, section 2).

### 3.1 Referenced planning documents (not under version control yet)

MDX-VAL-001 and -002 reference these drafts of 8 Nov 2026 in `MDARIX-planning/b10/`: MDX-B10-001 (intended use),
-002 (regulatory applicability matrix), -005 (traceability structure) and -006 (threat model). They stay in force as
drafts. MDX-B10-003 (validation plan) is superseded by MDX-VAL-001, and MDX-B10-004 (software risk assessment) by
MDX-VAL-002.

### 3.2 Superseded documents

| Document | Superseded by |
|---|---|
| `docs/compliance/CSA_MVP_VALIDATION_PACKAGE.md` and `.json` (MDARIX-CSA-MVP-1.0, never executed) | MDX-VAL-001 now; the per-release pack (B6b Part B) |
| `docs/compliance/CSA_MVP_VALIDATION_PROTOCOL.md` | MDX-VAL-001 |
| `docs/compliance/CSA_REQUIREMENTS_TRACEABILITY.md` | The generated RTM (MDX-VAL-009, B6b Part B) |
| `docs/compliance/CSA_CUSTOMER_IMPLEMENTATION_INSTRUCTIONS.md` | MDX-CUS-006 (B6b Part E) |

## 4. Signatures

Unsigned. The signed PDF and its `signatures.csv` row are added after review.

| Role | Name | Meaning of signature | Signature | Date |
|---|---|---|---|---|
| Author (R) | Srinivas Telikicherla, QA/RA, quality approver | I wrote this document and reviewed every line. | | |
| Approver (A), system owner | Sriharsha Telikicherla, Product & Engineering | I approve these document-control rules for use. | | |
