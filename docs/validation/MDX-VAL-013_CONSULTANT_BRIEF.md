# MDX-VAL-013 Consultant brief and question pack

| Field | Value |
|---|---|
| Document ID | MDX-VAL-013 |
| Title | Consultant brief and question pack |
| Version | 0.1 |
| Status | DRAFT |
| Author (R) | Srinivas Telikicherla, QA/RA |
| Reviewer | None: the consultant is the addressee and answers in writing (section 7) |
| Approver (A) | Sriharsha Telikicherla, Product & Engineering, system owner, as the second person (MDX-VAL-000, DC-R42: the quality approver is the author) |
| Drafting | Drafted with software assistance; every line reviewed by Srinivas Telikicherla (DC-R43) |
| Date | 12 Nov 2026 |
| Code baseline | Product code at `628c624a` (branch `feat/b6b-validation-pack` changes documentation only, plus the SUPERSEDED banner in `validation/csa_package.py` and its test; no product-code change) |

Change history

| Version | Date | Change | By |
|---|---|---|---|
| 0.1 | 12 Nov 2026 | First draft (B6b Part A, item A5) | Srinivas Telikicherla |

## 1. Purpose and scope

This brief asks an independent computerised-system validation (CSV) and GxP consultant to review MDARIX's validation
approach before any of it is shown to a customer (owner decision B6b-D20, MDX-VAL-000 section 4). It says what
MDARIX is, what we ask you to confirm, which documents to review, and the questions we need answered.

It covers MDARIX's validation of its own product for its own intended use. It does not ask you to validate any
customer's use. The documents are drafts; none is signed. Nothing in them claims that MDARIX is validated or
compliant for any customer.

## 2. What MDARIX is

- **Product.** Post-market intelligence and decision-support software for medical device manufacturers: complaint
  intake, triage, reportability per market with legal clocks, authority-report files (FDA eMDR, EU and GB MIR, and
  other markets), investigation, CAPA reference and effectiveness, trends, records and inspection export.
- **Fixed rules of the intended use.** A person always decides and signs. MDARIX never submits to an authority; the
  customer does. AI is off; no AI output reaches a record.
- **Delivery.** Software as a service on one shared version for every customer, released in small, frequent
  releases. Two operating modes: Connect (a layer over the customer's QMS) and Complete (MDARIX holds the
  post-market records).
- **Hosting today.** One virtual machine in Mumbai with PostgreSQL on it; encrypted daily backups copied to Delhi;
  no point-in-time recovery, so the stated recovery point is 24 hours (owner decision B6b-D8). No staging
  environment yet.
- **Company.** Two founders: Sriharsha Telikicherla (Product & Engineering, system owner) and Srinivas Telikicherla
  (QA/RA, quality approver). The company is not registered yet. The product runs today in a free-trial phase; no
  release in production has been validated under the new plan (MDX-VAL-001 section 9.4).
- **Users.** Trained employees of device manufacturers (or their authorised representatives and importers), not
  patients or clinicians.

## 3. What we ask you to confirm

1. **GxP impact per function:** which functions have a direct, indirect or no GxP impact (MDX-VAL-002 section 4).
2. **GAMP 5 category and rationale:** Category 4 for the product, Category 5 for anything written for one customer,
   Category 1 for platform software (MDX-VAL-003).
3. **Validation activities per risk class:** scripted, negative and scenario testing, and what counts as evidence
   (MDX-VAL-001 sections 7, 8 and 12).
4. **MDARIX and customer responsibilities:** the split in section 5 below.
5. **Electronic records and signatures:** the controls listed in section 6 below.
6. **Part 11 and Annex 11 approach:** a clause-by-clause assessment, Annex 11 as a benchmark only (owner decision
   B6b-D9); the assessment itself (MDX-SUP-003) follows in B6b Part C.
7. **The methods set:** ISO/TR 80002-2:2017 as the main method, GAMP 5 2nd edition for categories and supplier
   leverage, FDA Computer Software Assurance for risk-based assurance, PIC/S PI 011-3 as the inspector's cross-check
   (MDX-VAL-001 section 3, R9 to R13).

## 4. Documents to review

| Order | Document | What to look at |
|---|---|---|
| 1 | MDX-VAL-001 Validation Master Plan | Roles, approach, classes, per-release validation, transition (9.4), acceptance criteria, deviations |
| 2 | MDX-VAL-002 Product risk assessment | Severity, occurrence and detectability scales; class by severity; the 67 failure modes; Open rows |
| 3 | MDX-VAL-003 GAMP 5 category justification | Category per part and its rationale |
| 4 | MDX-VAL-000 Validation document control and index | Signing, versions, owner decisions (section 4) |
| 5 | `docs/validation/scenario-register.md` | The scenarios that requirements and tests trace to. Its PASS statuses are development results, not validation evidence (MDX-VAL-001 VMP-R31) |
| Later | First release pack (B6b Part B); GxP impact and shared responsibility (MDX-SUP-002) and Part 11 / Annex 11 assessment (MDX-SUP-003) (B6b Part C) | Sent when written |

Context documents (drafts of 8 Nov 2026, moving into `docs/validation/` under owner decision O2): MDX-B10-001
intended use, MDX-B10-002 regulatory applicability matrix, MDX-B10-005 traceability structure, MDX-B10-006 threat
model.

## 5. Proposed MDARIX and customer responsibilities

| Party | Responsibilities |
|---|---|
| MDARIX | Hosting, infrastructure security and patching; backups, restore drills and recovery validation; time synchronisation; validation of each release for MDARIX's intended use (the release pack); control of sub-processors; release notes and a 10-working-day change notice (owner decision B6b-D14); incident notification; support access only by customer grant |
| Customer | Validation of its own intended use (UAT/PQ); its configuration and its signed configuration snapshot; user accounts and roles; access reviews and audit-trail reviews with the product's tools; its e-signature policy and the certification letter to FDA (21 CFR 11.100(c)); training records; accuracy of data entered; checking starter rule content against its own procedure; submission to authorities; its periodic review; its outage procedure |
| Both | Data retention and exit; inputs to the periodic review; investigation of a deviation that affects the customer |

## 6. Electronic-record and electronic-signature controls in place

Each signing needs the password session plus a fresh authenticator code; the signature records the signer, the
time and the stated meaning, and is bound to the record version by a content fingerprint and signature hash. Audit
events are append-only (a database trigger refuses update and delete) and chained by hash per organisation, with a
daily verification. Signers need training on the current document versions. Five wrong codes lock signing for
15 minutes. There is no periodic password expiry (owner decision O5; NIST SP 800-63B): lockout, breached-password
checks and multi-factor authentication apply instead. File and line references are in MDX-VAL-002 (RSK-009 to
RSK-021) and will be in MDX-SUP-003.

## 7. Question pack

Please answer each question in writing; we record each answer, with your name and date, against the question
number. Questions 1 to 14 keep the numbers used across the MDARIX documents.

| # | Question | Where it arises |
|---|---|---|
| 1 | Do you agree with the GxP impact per function: direct, indirect or none? | MDX-VAL-002 section 4 |
| 2 | Category 4 for MDARIX, Category 1 for platform software, Category 5 for anything written for one customer: is the rationale enough? What else would you treat as Category 5? | MDX-VAL-003 OP-1 |
| 3 | Which validation activities fit each class? Do automated tests tagged with scenario IDs and run on the tagged build count as OQ evidence under CSA? Is execution on a controlled local environment acceptable until a staging environment exists (owner decision B6b-D16)? | MDX-VAL-001 sections 7, 8, 10 |
| 4 | The MDARIX and customer split in section 5, in particular 21 CFR 11.10(i) to (k), 11.100(b) and (c), and the customer's intended-use PQ | Section 5 |
| 5 | Is 21 CFR 11.30 (open system) relevant to a SaaS reached over the internet? Are the signing controls in section 6 enough for 11.50, 11.70 and 11.200? Must the printed name, not only the user ID, appear on every display and print of a signature? | Section 6 |
| 6 | No periodic password expiry, with lockout, breached-password checks and multi-factor authentication, under 11.300(b): acceptable? | Section 6 |
| 7 | FMEA scales of 1 to 5, RPN = S x O x D, class set by severity alone, action at RPN 40 or more or S5 with D 3 or more: acceptable? | MDX-VAL-002 section 3 |
| 8 | Annex 11 for device makers: benchmark only? The status of the revised Annex 11 and of the draft Annex 22 (AI)? | MDX-VAL-001 R14, Annex D |
| 9 | ISO/TR 80002-2:2017 as the main method, PIC/S PI 011-3 as cross-check, FDA CSA final guidance (please confirm its date and status): the right set? | MDX-VAL-001 section 7 |
| 10 | One shared version for every customer: with a 10-working-day change notice and a per-release pack, can customers keep control of change without deferring upgrades? | MDX-VAL-001 VMP-R37 |
| 11 | Recovery validation after a restore (database, audit chain, configuration, held outbox events): is the list sufficient? Is holding unsent outbox events the right control? | MDX-VAL-001 section 14 |
| 12 | Data migration: what reconciliation and sampling level do you expect for imported regulated records? | MDX-VAL-002 RSK-027, RSK-028 |
| 13 | A periodic review every 12 months: enough for a Category 4 SaaS? | MDX-VAL-001 section 14 |
| 14 | "Mapped" wording for SOC 2 and ISO/IEC 27001 control mappings in a supplier pack: acceptable? | B6b Part C |
| 15 | The releases already in production were not validated under the plan. Is a first release pack that executes every class-A scenario, stated as the retrospective validation, an acceptable transition? | MDX-VAL-001 section 9.4, OP-7 |
| 16 | An Open class-A failure mode that a release relies on is accepted by the quality approver with an interim control and a due date: acceptable, and what limits would you set? | MDX-VAL-002 RA-R07 |
| 17 | Retention of validation records: 10 years after a release leaves the last customer, 15 years where a customer makes implantable devices. Acceptable? | MDX-VAL-001 section 16.4 (owner decision O1) |
| 18 | The starter question sets and floor rules per market: who should check them against the regulations, and how often? Please also check the GB, India day-1 and Canada counting rules | MDX-VAL-002 RSK-002, RSK-003 |
| 19 | Customer-written organisation rules can only raise an outcome. Do they need any customer test beyond the UAT/PQ template? | MDX-VAL-003 OP-2 |
| 20 | Should a customer's ISO 14971 risk management file reference MDARIX's product risk assessment? | MDX-VAL-002 OP-4 |
| 21 | Two founders cover system owner and quality approver, with each approving the other's documents. Is that segregation of duties enough for the first pilots, and when should a third person be added? | MDX-VAL-001 section 6 |
| 22 | The recovery point is 24 hours today (no point-in-time recovery). Is that acceptable for the first pilots, and with what interim control, until point-in-time recovery is in place? | MDX-VAL-002 RSK-038 (owner decision B6b-D8) |
| 23 | Audit events are kept 7 years from each event, with a full export at exit. Is that sufficient against customers' own record-retention periods? | MDX-VAL-001 section 16.4 |

## 8. Open points

| # | Point | Owner |
|---|---|---|
| OP-1 | Select and engage the consultant; agree scope (Part A, MDX-SUP-002, MDX-SUP-003 and the first release pack) and a written-answer format | Srinivas |
| OP-2 | Share this brief and the documents under a non-disclosure agreement (owner decision B6b-D19) | Srinivas |

## Signatures

Unsigned. The signed PDF and its `signatures.csv` row are added after review (MDX-VAL-000 section 2.6).

| Role | Name | Meaning of signature | Signature | Date |
|---|---|---|---|---|
| Author (R) | Srinivas Telikicherla, QA/RA | I am responsible for this brief and reviewed every line of the draft. | | |
| Approver (A), second person (DC-R42) | Sriharsha Telikicherla, Product & Engineering, system owner | I approve this brief for sending to the consultant. | | |
