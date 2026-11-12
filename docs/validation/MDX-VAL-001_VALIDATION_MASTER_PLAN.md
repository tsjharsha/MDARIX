# MDX-VAL-001 Validation Master Plan

| Field | Value |
|---|---|
| Document ID | MDX-VAL-001 |
| Title | Validation Master Plan |
| Version | 0.2 |
| Status | DRAFT |
| Author (R) | Sriharsha Telikicherla, Product & Engineering, system owner |
| Reviewer | Independent CSV consultant (first version; not engaged yet) |
| Approver (A) | Srinivas Telikicherla, QA/RA, quality approver |
| Drafting | Drafted with software assistance; every line reviewed by Sriharsha Telikicherla (MDX-VAL-000, DC-R43) |
| Date | 12 Nov 2026 |
| Code baseline | Product code at `628c624a` (branch `feat/b6b-validation-pack` changes documentation only, plus the SUPERSEDED banner in `validation/csa_package.py` and its test; no product-code change); release in preparation 0.11.04 (`VERSION` file still 0.10.94) |

Change history

| Version | Date | Change | By |
|---|---|---|---|
| 0.1 | 12 Nov 2026 | First draft. Replaces MDX-B10-003 v0.1 (8 Nov 2026) and the MVP-1.0 CSA package (`docs/compliance/CSA_MVP_VALIDATION_PACKAGE.md`). Revised after a software-assisted review, findings dispositioned by the author: single-statement requirements, supporting controls (section 16), Annexes C and D | Sriharsha Telikicherla |
| 0.2 | 12 Nov 2026 | After a second software-assisted review, findings dispositioned by the author: current status and transition (section 9.4); approval gate on R4 to R7; consultant scope; class C approach; development results are not validation evidence; MIR schema criterion; retention per owner decision O1; qualification of executors and approvers; Annex E (how each rule is checked); requirements split and renumbered in reading order | Sriharsha Telikicherla |

## 1. Purpose

This plan states how MDARIX shows, with evidence proportionate to risk, that the software does what its intended use
says, and how it keeps doing so through every release. It names who does what, which documents are produced, and
when a release may go to production.

This plan covers MDARIX's validation of its own product for its own intended use. It does not validate any customer's
use. Each customer validates MDARIX for its own intended use with the customer templates (MDX-CUS-001 to -006,
B6b Part E). No document produced under this plan states that MDARIX is validated or compliant for every customer.

## 2. Scope

| In scope | Out of scope |
|---|---|
| The MDARIX web application, API, background service (outbox worker and scheduler) and database schema, as released by tag | A customer's own procedures, configuration choices and intended-use validation (the customer's UAT/PQ) |
| Both operating modes: Connect (a layer over the customer's QMS) and Complete (MDARIX holds the post-market records) | Website pages, marketing material, demo videos |
| The markets US, EU and Northern Ireland, Great Britain, India, Canada, and the other countries held in the rule register (build B9b) | AI helpers: AI is off; see section 15 |
| Hosting and configuration that affect records: backup, restore, recovery, time source, TLS, access, keys | The cloud provider's own infrastructure: covered by supplier assessment (MDX-SUP-004) |
| The free-trial edition, only where its behaviour differs (sample clock, same-person signing in a trial) | |

## 3. References

| Ref | Document | Note |
|---|---|---|
| R1 | MDX-VAL-000 Validation document control and index | This folder |
| R2 | MDX-VAL-002 Product risk assessment | This folder |
| R3 | MDX-VAL-003 GAMP 5 category justification | This folder |
| R4 | MDX-B10-001 Intended Use Statement, draft 8 Nov 2026 | [MDX-B10-001-Intended-Use-Statement.md](MDX-B10-001-Intended-Use-Statement.md) |
| R5 | MDX-B10-002 Regulatory Applicability Matrix, draft 8 Nov 2026 | [MDX-B10-002-Regulatory-Applicability-Matrix.md](MDX-B10-002-Regulatory-Applicability-Matrix.md) |
| R6 | MDX-B10-005 Traceability Structure, draft 8 Nov 2026 | [MDX-B10-005-Traceability-Structure.md](MDX-B10-005-Traceability-Structure.md) |
| R7 | MDX-B10-006 Threat Model, draft 8 Nov 2026 | [MDX-B10-006-Threat-Model.md](MDX-B10-006-Threat-Model.md) |
| R8 | Scenario register (master copy) | [scenario-register.md](scenario-register.md) |
| R9 | ISO/TR 80002-2:2017, validation of software for medical device quality systems | Main method. **To confirm with your consultant** |
| R10 | ISPE GAMP 5, A Risk-Based Approach to Compliant GxP Computerized Systems, 2nd edition (2022) | Software categories and supplier leverage. **To confirm with your consultant** |
| R11 | FDA guidance, Computer Software Assurance for Production and Quality Management System Software (final guidance, 2025) | Risk-based assurance. Title, date and status **to confirm with your consultant** |
| R12 | PIC/S PI 011-3, Good Practices for Computerised Systems in Regulated "GxP" Environments | The inspector's cross-check. **To confirm with your consultant** |
| R13 | ISO 13485:2016 clause 4.1.6 (validation of software used in the QMS); 21 CFR 820 as amended (QMSR) | The customer's obligation that this plan supports. **To confirm with your consultant** |
| R14 | 21 CFR Part 11; EU GMP Annex 11 | Assessed in MDX-SUP-003. Annex 11 is used as a benchmark only (owner decision B6b-D9) |
| R15 | MDX-VAL-000 section 4 (owner decisions) and section 5 (codes) | This folder |
| R16 | MDX-VAL-013 Consultant brief and question pack | This folder |

- **VMP-R01** R4 to R7 shall be under document control in this folder and approved before this plan is approved as
  version 1.0 (they were moved here on 12 Nov 2026, owner decision O2).

## 4. Intended use (summary of R4)

MDARIX is post-market intelligence and decision-support software for medical device manufacturers. It helps a
manufacturer's quality and regulatory team handle complaints and vigilance from first contact to the closed record,
across markets: intake, triage, per-market reportability with legal clocks, preparation of authority-report files,
investigation, CAPA reference and effectiveness, trends, records and inspection export.

Three fixed rules bound the intended use:

1. A person always decides and signs. Every regulatory conclusion, report approval and closure needs a named person,
   a fresh authenticator code and a stated meaning.
2. MDARIX never submits to an authority. The customer submits through the authority's own route and records it.
3. AI is off. No AI output reaches any record.

Users are trained employees of a medical device manufacturer (or its authorised representative or importer), working
in the personas listed in R4 section 5. They are not patients or clinicians.

## 5. System description

| Component | What it is | Where it is described |
|---|---|---|
| Web application | React and TypeScript single-page application, built with Vite | `frontend/`, `docs/architecture/FRONTEND_MVP_ARCHITECTURE.md` |
| API | Python FastAPI service; authorisation on the server; tenant taken from the server session only | `backend/app/`, `docs/architecture/` |
| Background service | Outbox worker (one event per transaction) and scheduler (for example the daily deadline list, audit-chain verification, export expiry, trial retention) | `outbox/worker.py`, `backend/app/scheduler.py`, `docs/runbooks/OUTBOX_AND_SCHEDULER.md` |
| Database | PostgreSQL 16 with forced row-level security per organisation; one Alembic migration chain | `infrastructure/database/migrations/`, `docs/architecture/DATABASE_SCHEMA_REFERENCE.md` |
| Audit trail | Append-only audit events with a hash chain per organisation and daily verification | `backend/app/audit_chain.py` |
| Signatures | Signature records bound to the object version by a content fingerprint and signature hash | `backend/app/db/models/foundation.py` |
| Hosting (production today) | One virtual machine in Mumbai running the web server, API, background service, file scanning and PostgreSQL; encrypted daily backups copied to Delhi; daily disk snapshot | `docs/runbooks/GCP_DEPLOYMENT.md` |
| Configuration held as data | Rule register versions with content hashes, question sets, reporting windows, roles and permissions, organisation settings, switches | MDX-VAL-003 section 4 |

The architecture decisions are in `docs/adr/`. The security design is in R7.

## 6. Roles, responsibilities and segregation of duties

### 6.1 Roles (owner decision B6b-D1)

| Role | Who | Duties |
|---|---|---|
| System owner | Sriharsha Telikicherla, Product & Engineering | Writes and maintains the system documents (FS/DS, IQ, OQ); executes IQ and OQ; approves, as system owner, the documents the quality approver writes |
| Quality approver | Srinivas Telikicherla, QA/RA | Writes the URS from the business view; executes the MDARIX PQ as a business user; independently reviews every protocol and result the system owner writes; approves the plan, risk assessment, VSR and every release |
| Independent CSV consultant | To be engaged (B6b-D20) | Reviews the first issue of each document marked C in the consultant column of section 6.3, and the first full validation pack |
| Customer QA/RA | Each customer | Approves its own intended use and its own validation |

### 6.2 Rules

- **VMP-R02** Nobody shall approve their own work. The approver (A) of a document or result shall be a different
  person from its author or executor (R).
- **VMP-R03** The quality approver shall independently review every protocol and every result that the system owner
  writes or executes.
- **VMP-R04** The system owner shall approve, as system owner, every document that the quality approver writes.
- **VMP-R05** Text drafted with software assistance shall have a named person as author (R).
- **VMP-R06** That author shall review every line before the text goes for approval.
- **VMP-R07** The document header shall name that reviewer in the field "Drafting" (MDX-VAL-000).
- **VMP-R08** Software shall not be named as author, reviewer or signer.
- **VMP-R09** The independent CSV consultant shall review the first issue of each document marked C in the
  consultant column of section 6.3, and the first full validation pack.
- **VMP-R10** For a class-A control, the review or the execution shall be done by someone other than the developer
  of that control.
- **VMP-R11** No document marked C for the consultant in section 6.3 shall be given to a customer before the
  consultant has reviewed its first issue.
- **VMP-R12** A later issue of such a document shall be approved under section 6.3 without waiting for the
  consultant.
- **VMP-R13** A record without a consultant entry in section 6.3 (for example a release approval record) shall be
  approved under section 6.3 without waiting for the consultant.

### 6.3 RACI

R = writes or does the work. A = approves and signs (one person). C = reviews and comments. I = informed.

| Deliverable | System owner (Sriharsha) | Quality approver (Srinivas) | Consultant | Customer |
|---|---|---|---|---|
| Document control and index (MDX-VAL-000) | A | R | C (first version) | |
| This plan (MDX-VAL-001) | R | A | C (first version) | I |
| Product risk assessment (-002) | R (proposes every rating) | C (reviews every severity), then A | C (confirms severities and scales) | I |
| GAMP 5 justification (-003) | R | A | C (confirms) | I |
| URS and `requirements.csv` (-004) | C (feasibility), then A | R (business view) | C (first pack) | I |
| FS/DS (-005) | R | A (independent review) | | |
| IQ and OQ protocols and execution (-006, -007) | R (writes, executes) | A (pre-approves expected results; reviews results) | C (class A, first pack) | |
| MDARIX PQ (-008) | A | R (executes as the business user) | | |
| RTM (-009) and validation figures | R (generator) | A (reviews every link) | | I |
| Deviation log (-010) | R (corrects, retests) | A (closes) | | I (customer-impacting ones) |
| Validation Summary Report (-011) | R | A | C (first pack) | I |
| Release approval record (-012) | R (prepares) | A (signs) | | I (change notice) |
| Supplier pack, GxP impact, shared responsibility (MDX-SUP-001, -002) | A (technical accuracy) | R | C | I |
| Part 11 / Annex 11 assessment (MDX-SUP-003) | C (evidence), then A | R | C (confirms) | I |
| Hosting assessment (-004), SOC 2 / ISO 27001 mapping (-005) | R | A | | I |
| Trust facts (-006) | R (evidence check) | A (claims owner) | | |
| SOPs (MDX-SOP-001 to -005) | R | A | C | I |
| Recovery record (MDX-OPS-001) | R (executes) | A | | I (summary) |
| Monthly health report (MDX-OPS-002) | R (generates) | A (reviews before sending) | | I |
| Customer templates (MDX-CUS-001 to -006) | C, then A | R | C | |
| Customer's filled UAT/PQ, migration report, periodic review | C (support) | C | | R (business users execute), A (their QA) |

## 7. Validation approach

The approach is risk-based: validation effort follows the effect of a failure on patient safety (through a missed or
late report, or a wrong conclusion) and on the integrity of regulated records (R2). ISO/TR 80002-2:2017 (R9) is the
main method for validating MDARIX as QMS software. GAMP 5 (R10) gives the software category (MDX-VAL-003) and the
basis for using supplier evidence. The FDA Computer Software Assurance guidance (R11) gives the assurance level per
risk class. PIC/S PI 011-3 (R12) is the cross-check of what an inspector looks for. Each reference is **to confirm
with your consultant**: edition, status and fit (MDX-VAL-013, question 9).

- **VMP-R14** Each function's validation activities shall be those set for its class in section 8.
- **VMP-R15** Each VSR shall state, for each reference R9 to R12, which of its expectations the release pack meets
  and which it does not.
- **VMP-R16** Platform software (operating system, PostgreSQL, container runtime, web server, file scanner, Python
  and Node runtimes) shall be used as supplied, with its version recorded in the IQ record.
- **VMP-R17** MDARIX shall test its own use of platform software, not the platform software itself.
- **VMP-R18** An automated test shall count as evidence for the scenario named in its `requirement` marker
  (`pytest.ini`) only when it ran on the tagged build and its JUnit output is kept in the release folder.

Whether such evidence counts as OQ evidence under CSA is **to confirm with your consultant** (MDX-VAL-013,
question 3).

- **VMP-R19** Libraries built into the application (for example FastAPI, SQLAlchemy, React) shall be treated as
  part of the product and listed by version in the release's software bill of materials.
- **VMP-R20** A change of such a library shall follow the change-impact rule (section 9.3).

## 8. Risk classes and assurance levels

The class of each function comes from MDX-VAL-002. The class is set by severity alone (owner decision B6b-D4).

| Class | Meaning | Assurance level |
|---|---|---|
| **A: High** (severity 4 or 5) | A failure could cause a missed or late authority report, a wrong regulatory conclusion, an undetected change to a signed record, a signature not bound to its record, lost regulated records, or one customer seeing another's data | Scripted testing with expected results approved before execution; negative tests (what must be refused); automated regression on every build; independent review of protocol and results; execution evidence kept; every class-A scenario of a touched function run in that release |
| **B: Medium** (severity 3) | A failure shows wrong or missing information that a trained person is expected to catch before signing, or delays work | Scenario testing: the scenario register row is the test, the tester records what was done and seen; automated tests where they exist; peer review |
| **C: Low** (severity 1 or 2) | Cosmetic or convenience; no record or decision effect | Automated build checks (lint, unit tests, build); the class-C rationale recorded in MDX-VAL-002 section 4; only failures recorded |

- **VMP-R21** A function's class shall be the class of its highest-severity failure mode in MDX-VAL-002.
- **VMP-R22** A function with no failure mode that can affect a record or a decision shall be class C, with its
  rationale recorded in MDX-VAL-002 section 4.
- **VMP-R23** A change that touches a class-A function shall be treated as class A for that release, whatever its
  size.

## 9. Lifecycle and per-release validation

### 9.1 Lifecycle

| Step | What happens | Output |
|---|---|---|
| 1. Intended use | State what the software is for and its limits | MDX-B10-001 (R4) |
| 2. Requirements | Each approved build spec lists its requirements as REQ-&lt;AREA&gt;-nnn with acceptance scenarios from the scenario register | URS: `requirements.csv` (MDX-VAL-004) |
| 3. Risk | Each requirement gets a class from the product risk assessment; new failure modes add rows | MDX-VAL-002, updated per release |
| 4. Specification | Each requirement is linked to its screen or route and its design | FS/DS (MDX-VAL-005) |
| 5. Protocols | Class A: scripted protocol per scenario group, expected results approved first. Class B: scenario row. Class C: none | IQ, OQ, PQ protocols (MDX-VAL-006 to -008) |
| 6. Execution | On a controlled environment at a tagged release (section 10) | Execution records, JUnit output, release-checks JSON |
| 7. Deviations | Every failure, blocked step or protocol error is a deviation | Deviation log (MDX-VAL-010) |
| 8. Traceability | Generated per release from requirements, scenarios, test markers and results | RTM (MDX-VAL-009) |
| 9. Report and approval | Results, deviations and figures reviewed | VSR (MDX-VAL-011); signed release approval record (MDX-VAL-012) |
| 10. Validated state | Change impact per release, periodic review, recovery validation, health report | Section 14 |
| 11. Retirement | Export, hand-back, readable retention and purge of each customer's records | Retirement plan (section 16.5) |

### 9.2 Per-release (agile) validation

MDARIX is released in small, frequent releases on one shared version for every customer. Once this plan is
approved, each release will be validated for MDARIX's own intended use by the steps below, instead of one large
validation at the end (section 9.4 sets when this starts).

- **VMP-R24** Each release spec shall list the REQ IDs and scenario IDs it adds or changes.
- **VMP-R25** Each release shall carry a change-impact assessment that sets which scenarios must be re-run (9.3).
- **VMP-R26** The automated suite shall run on the tagged build.
- **VMP-R27** The suite's JUnit output and the release-checks JSON shall be kept in
  `docs/validation/releases/<version>/`.
- **VMP-R28** Every class-A scenario named by the change impact shall be executed and recorded before release.
- **VMP-R29** A scenario's status in the register shall be one of PASS, FAIL, BLOCKED, NOT RUN, REQUIRES HUMAN
  DECISION.
- **VMP-R30** A BLOCKED or NOT RUN scenario shall not be counted as passed.
- **VMP-R31** A status recorded in the scenario register before the first release pack under this plan is a
  development result and shall not be cited as validation evidence.
- **VMP-R32** The validation evidence for a release shall be the results kept in its release folder (VMP-R27).
- **VMP-R33** The RTM and the validation figures shall be generated for each release, not written by hand.
- **VMP-R34** The quality approver shall sign the release approval record before every production deploy (owner
  decision B6b-D7).
- **VMP-R35** For an emergency fix, the quality approver's written OK shall be given before the deploy.
- **VMP-R36** For an emergency fix, the signed release approval record shall follow within 1 working day of the
  deploy.
- **VMP-R37** A change to a class-A function, a rule floor or a sub-processor shall be notified to customers at least
  10 working days before the deploy (owner decision B6b-D14).
- **VMP-R38** An emergency security fix shall be notified to customers after the deploy, within the period the
  change-control SOP (MDX-SOP-002) sets. (Testable once MDX-SOP-002 is written, B6b Part C.)
- **VMP-R39** A release folder holding a signed approval shall not be overwritten.
- **VMP-R40** A correction to a signed release record shall be a new version that names the one it replaces.

### 9.3 Change impact

| Change type | Minimum re-validation |
|---|---|
| Touches a class-A function or its data model | Re-run every class-A scenario of that function; full automated suite; independent review |
| New rule or question-set version, new floor version | The rule-register test rows of that market, the content-hash test, a signed rule change note |
| Migration that changes regulated tables | IQ migration check; restore of the previous backup into the new schema; audit-chain verification |
| Class B or C only | Automated suite; scenario rows of the changed screens |
| Hosting or configuration change (backup, TLS, keys, time zone) | IQ re-check of the changed item; restore drill if the backup changes |
| Dependency, operating-system or PostgreSQL upgrade | Full automated suite; IQ version record; class-A scenarios that use the changed component |
| Security fix | Regression for the fix and the related threat-model test (R7) |

### 9.4 Current status and transition

No release deployed to production before this plan is approved was released under it. Production runs the
releases of the free-trial phase (0.10.92 at the date of this draft); no VSR or release approval record exists for
them. The approach below is proposed in this draft; the owner confirms it and the consultant reviews it (OP-7).

- **VMP-R41** VMP-R24 to VMP-R40 shall apply from the first production release after this plan is approved as
  version 1.0.
- **VMP-R42** The first release pack under this plan shall execute every class-A scenario, not only those named by
  its change impact.
- **VMP-R43** The VSR of that first pack shall state that it is the retrospective validation of the functions
  already in production.
- **VMP-R44** Until that VSR is approved, any MDARIX statement of validation status shall read only: "Validation
  in progress; plan MDX-VAL-001 (draft)."

## 10. Environments (owner decision B6b-D16)

| Environment | Use | Data |
|---|---|---|
| Controlled local test environment: a clean test database built from the tagged commit on the build computer | Automated tests; IQ, OQ and MDARIX PQ execution until staging exists | Synthetic data only |
| Staging (not available yet) | IQ, OQ and PQ execution once it exists; penetration test | Synthetic or sample data; never production data |
| Production | IQ checks of the installed release only (version, health, configuration check, clock check) | No test data entered |

- **VMP-R45** Until staging exists, the identity of the controlled local environment (commit, migration head,
  versions of Python, Node and PostgreSQL) shall be recorded as an IQ of the test environment.
- **VMP-R46** Until staging exists, the VSR shall label every result "controlled local environment".
- **VMP-R47** No test data shall be entered in production.
- **VMP-R48** The GxP workflow check of a recovery shall run on a scratch copy of the backup, never in production
  (owner decision B6b-D15).

## 11. Deliverables

| ID | Deliverable | When | B6b part |
|---|---|---|---|
| MDX-VAL-000 | Document control and index | Once; updated with each new document | A |
| MDX-VAL-001 | This plan | Once; reviewed every 12 months | A |
| MDX-VAL-002 | Product risk assessment | Once; updated per release | A |
| MDX-VAL-003 | GAMP 5 category justification | Once | A |
| MDX-VAL-004 | URS (`requirements.csv` and its rendering) | Per release | B |
| MDX-VAL-005 | FS/DS | Per release | B |
| MDX-VAL-006 | IQ protocol and record | Per release | B |
| MDX-VAL-007 | OQ protocol and results log | Per release | B |
| MDX-VAL-008 | MDARIX PQ protocol and record | Per release | B |
| MDX-VAL-009 | RTM and validation figures | Per release | B |
| MDX-VAL-010 | Deviation log | Continuous | B |
| MDX-VAL-011 | Validation Summary Report | Per release | B |
| MDX-VAL-012 | Release approval record | Per release | B |
| MDX-SUP-001 to -006 | Supplier pack, GxP impact and shared responsibility, Part 11 / Annex 11 assessment, hosting assessment, SOC 2 / ISO 27001 mapping, trust facts | Before the first paid pilot; reviewed every 12 months | C |
| MDX-SOP-001 to -005 | SDLC, change control, incident response, backup and business continuity, access control | Before the first paid pilot | C |
| MDX-OPS-001 | Recovery record | At each quarterly restore drill | D |
| MDX-OPS-002 | Health report per organisation | Monthly from one month after go-live | D |
| MDX-CUS-001 to -006 | Customer templates | Before the first paid pilot | E |

## 12. Acceptance criteria for a release

- **VMP-R49** Every class-A scenario in scope shall be PASS, with evidence.
- **VMP-R50** No open deviation shall affect patient safety or data integrity.
- **VMP-R51** Every other open deviation shall have an acceptance rationale signed by the quality approver.
- **VMP-R52** The isolation tests shall show zero cross-organisation access, in both directions, on every surface
  tested (API, search, export, files, reports, background jobs).
- **VMP-R53** Every signed record in the test set shall verify (signature hash, snapshot hash).
- **VMP-R54** The audit chain of every organisation in the test set shall verify from start to end.
- **VMP-R55** Every legal clock in the test set shall match its pre-approved expected date and time, including
  weekends, holidays and daylight-saving changes.
- **VMP-R56** Every value in an authority-report file in the test set shall trace to the approved snapshot.
- **VMP-R57** Every FDA eMDR file in the test set shall validate against FDA's schemas.
- **VMP-R58** Every EU and GB MIR file in the test set shall validate against its form schema.
- **VMP-R59** The full automated suite shall pass on the tagged build.
- **VMP-R60** A critical failure shall block the release: cross-organisation access, an uncontrolled change to a
  record, missing audit evidence, an approval that cannot be reproduced, a wrong legal clock, wrong report data, a
  signature not bound to its version, or the sample clock moving a real record.

## 13. Deviations

Definitions used by the rules below:

| Term | Meaning |
|---|---|
| Critical | A failure of a type listed in VMP-R60, or any class-A acceptance criterion of section 12 not met |
| Major | Any other failure in a class-A function, or a class-B failure that leaves wrong information in a record |
| Minor | Any other failure: class C, or an error in a protocol or record that does not change a result |
| GxP risk high, medium, low | The severity of the failed function's worst failure mode in MDX-VAL-002: S4 or S5 is high, S3 medium, S1 or S2 low |
| Affects patient safety or data integrity | GxP risk high |

- **VMP-R61** Every failed step, blocked step or protocol error shall be recorded in the deviation log before any fix
  is made.
- **VMP-R62** Each deviation shall be assessed for its impact on patient, product and data integrity.
- **VMP-R63** Each deviation shall be given a GxP risk: high, medium or low.
- **VMP-R64** Each deviation shall be given a classification: critical, major or minor.
- **VMP-R65** A deviation shall be closed only with a retest result and the quality approver's approval.
- **VMP-R66** Each deviation shall record whether change control is needed.
- **VMP-R67** An open critical deviation shall block the release.

The log's columns and lifecycle are in Annex C. The log itself is MDX-VAL-010 (B6b Part B).

## 14. Maintaining the validated state

- **VMP-R68** The configuration baseline of each release (migration head, rule-register versions and content hashes,
  question-set versions, switches) shall be recorded in its IQ record.
- **VMP-R69** A recovery validation (database, audit chain, configuration, held outbox events) shall be run and
  recorded at each quarterly restore drill (MDX-OPS-001).
- **VMP-R70** This plan shall be reviewed every 12 months (owner decision B6b-D18).
- **VMP-R71** The product risk assessment (MDX-VAL-002) shall be reviewed every 12 months, in addition to its
  update in each release.
- **VMP-R72** The supplier assessment (MDX-SUP-001 and MDX-SUP-004) shall be reviewed every 12 months.
- **VMP-R73** The customer periodic review template (MDX-CUS-004) shall set a review every 12 months.
- **VMP-R74** MDARIX's own periodic review report shall list the incidents, complaints about MDARIX, MDARIX CAPAs
  and customer audit findings of the period, from the registers set up in B6b Part D.

## 15. AI

AI is off in every release under this plan, and AI helpers are out of scope.

- **VMP-R75** No AI helper shall be switched on for a customer before the AI release gate
  (`backend/app/ai_release_gate.py`) passes for it.
- **VMP-R76** No AI helper shall be switched on for a customer before an AI validation protocol, covering at least
  the items of Annex D, has been approved as a change to this plan.

## 16. Supporting controls

### 16.1 Tools that produce evidence

- **VMP-R77** Each tool that produces validation evidence (the test runner, the release-checks script, the RTM and
  figures generator) shall be recorded by version in the IQ record of the release.
- **VMP-R78** A tool MDARIX writes to produce evidence (the release-checks script, the validation-pack generator)
  shall have its own automated tests, including tests that it fails on bad input (B6b scenarios B6-47 to B6-51).
- **VMP-R79** A third-party test tool (for example pytest) shall be used as supplied.
- **VMP-R80** A new major version of such a tool shall be qualified by use: a test known to fail shall be seen to
  fail in the qualifying run.

### 16.2 Training

- **VMP-R81** Each person who executes or approves a protocol shall have read this plan and that protocol before
  executing or approving.
- **VMP-R82** Each VSR shall list who executed and who approved, with the date each read this plan and the protocol.
- **VMP-R83** Each person who executes or approves a protocol shall have a recorded qualification for that role
  (CSV or GxP training, or documented experience).
- **VMP-R84** Each VSR shall cite the qualification record of each executor and approver.

### 16.3 Good documentation practice for executed evidence

- **VMP-R85** Each executed step shall record the actual result, the executor, the date and time (UTC) and the
  evidence reference.
- **VMP-R86** A screenshot or file used as evidence shall be stored with its SHA-256 in the release folder.
- **VMP-R87** A correction to an executed record shall keep the original entry readable and record who corrected it,
  when and why.
- **VMP-R88** An expected result shall not be changed after execution has started; a needed change is a deviation.

### 16.4 Retention

- **VMP-R89** Validation records of a release shall be kept for at least 10 years after the release leaves the last
  customer.
- **VMP-R90** Where a customer makes implantable devices, the validation records of each release it used shall be
  kept for at least 15 years after the release leaves that customer.

Both periods are owner decision O1 (MDX-VAL-000 section 4), consultant to confirm. They count from a release leaving
the last customer; the audit-trail retention in `docs/compliance/DATA_RETENTION_SCHEDULE.md` counts 7 years from
each audit event, a different start.

### 16.5 Retirement of MDARIX or of a function

- **VMP-R91** Before a function or the product is retired, a retirement plan shall state how each customer's records
  are exported, handed back, kept readable for their retention period, and purged.
- **VMP-R92** The retirement plan shall be approved by the quality approver before the retirement starts.

## 17. Open points and blockers

| # | Point | Owner |
|---|---|---|
| OP-1 | No independent CSV consultant engaged. This plan stays DRAFT and is shared with no customer until the consultant has reviewed it (VMP-R11); brief and questions in MDX-VAL-013 | Srinivas |
| OP-2 | The company is not registered yet; the supplier documents need the legal entity and its signatory | Srinivas |
| OP-3 | No staging environment: formal execution on the controlled local environment until then (section 10) | Srinivas |
| OP-4 | `VERSION` (0.10.94) and the CHANGELOG section disagree; the release identity must be fixed before the first per-release pack | Sriharsha |
| OP-5 | MDX-B10-001, -002, -005 and -006 moved into this folder on 12 Nov 2026 (owner decision O2) and are still DRAFT; this plan is not approved before they are approved (VMP-R01) | Srinivas |
| OP-6 | Each reference R9 to R13 to be confirmed with the consultant | Srinivas |
| OP-7 | The transition approach for the releases already in production (section 9.4): the owner confirms it; the consultant reviews it (MDX-VAL-013, question 15) | Srinivas |
| OP-8 | Owner to decide what governs production deploys before this plan is approved as 1.0: a signed release approval record from the next deploy, or the current practice until then (MDX-VAL-000 section 4, B6b-D7) | Srinivas |

## Annex A: writing standard

The writing standard for every document under this plan is MDX-VAL-000 section 2.5.

## Annex B: audit-finding self-check (in every VSR)

- **VMP-R93** Every VSR shall answer each line below with yes or no and name the evidence.

1. The URS was not written by engineering alone.
2. QA reviewed every protocol and result independently.
3. PQ and UAT were executed by business users.
4. The periodic-review owner is named.
5. The security assessment (R7) is linked into the risk assessment.
6. Every requirement is traced to a test.

## Annex C: deviation log and lifecycle

The deviation log (MDX-VAL-010) is one CSV file across releases, `docs/validation/deviation-log.csv`.

| Column | Content |
|---|---|
| ID | DEV-&lt;release&gt;-nnn |
| Raised | Date and time (UTC) and by whom |
| Found in | IQ, OQ, PQ, automated suite, or production |
| Test or scenario ID; REQ ID | What was being tested |
| Expected and seen | Both written out |
| Documented first | Date and time the deviation was written down, before any fix |
| Impact | On patient, product and data integrity |
| GxP risk | High, medium or low |
| Classification | Critical, major or minor |
| Root cause; correction | What went wrong and what was changed |
| Retest | Retest ID and result |
| Change control | Needed yes or no, with reference |
| CAPA | Reference, where one is opened |
| Approved by; closed | Quality approver and date (UTC) |
| Status | Open, corrected, retested, closed |

Lifecycle: identify, document first, assess impact and GxP risk, correct, retest, approve and close, decide whether
change control is needed. VMP-R61 to VMP-R67 apply. Blocked or not run is never a pass.

## Annex D: AI validation items (for the protocol before switch-on)

The AI validation protocol required by VMP-R76 covers at least:

1. The intended use of each AI feature.
2. The GxP risk of each AI feature, added to MDX-VAL-002.
3. Qualification against the signed-off golden dataset (`docs/validation/AI_GOLDEN_DATASET_QUALIFICATION.md`, to be
   re-issued with a document ID before use, MDX-VAL-000 DC-R10), with
   pass criteria set before the run.
4. The provider and model version pinned and recorded (`docs/compliance/AI_PROVIDER_REGISTER.md`).
5. Human review and sign-off of every AI output before it reaches a record.
6. An audit trail of the prompt, model, output and reviewer.
7. Monitoring for drift, and re-qualification on any model change.

References for that protocol, **to confirm with your consultant**: GAMP 5 2nd edition (AI/ML appendix), FDA CSA,
Part 11 and Annex 11, ICH Q9, ALCOA+, and the EU draft GMP Annex 22 (AI).

## Annex E: how each rule is checked

| Rules (section) | Check | Evidence |
|---|---|---|
| Approval gate (3); roles and segregation of duties (6) | Pre-signature check of each document's header and signature block (MDX-VAL-000, DC-R31); VSR self-check lines 1 to 3 (Annex B) | Signed PDF; `signatures.csv` |
| Approach and tool use (7); classes (8) | The validation-pack generator fails a class-A requirement without a negative scenario and a requirement without a scenario (B6b Part B); RTM per class | RTM; VSR |
| Per-release validation and change impact (9.2, 9.3) | The release approval record lists each item; the generator refuses to overwrite a signed release folder | Release folder; release approval record |
| Transition (9.4) | The first VSR states its scope; the quality approver checks customer-facing wording before release | First VSR |
| Environments (10) | IQ record of the test environment; VSR label | IQ record; VSR |
| Acceptance criteria (12) | VSR results by class; release approval record | VSR; JUnit output; release-checks JSON |
| Deviations (13, Annex C) | Deviation log columns; the generator refuses a release approval while a critical deviation is open and a closure without retest and approver (B6-57, B6-58) | Deviation log |
| Validated state (14) | Periodic review report; recovery record at each drill | MDX-OPS-001; periodic review report |
| AI (15, Annex D) | AI release gate refuses AI in production without a passed evaluation (`backend/app/ai_release_gate.py`) | Gate test; change to this plan |
| Supporting controls (16) | IQ tool versions; VSR list of executors, approvers and qualifications; SHA-256 of evidence files | IQ record; VSR; release folder |
| Self-check (Annex B) | Answered in every VSR | VSR |

## Signatures

Unsigned. The signed PDF and its `signatures.csv` row are added after review (MDX-VAL-000 section 2.6).

| Role | Name | Meaning of signature | Signature | Date |
|---|---|---|---|---|
| Author (R), system owner | Sriharsha Telikicherla, Product & Engineering | I am responsible for this plan and reviewed every line of the draft. | | |
| Reviewer (C) | Independent CSV consultant | I reviewed this plan; my comments are recorded. | | |
| Approver (A), quality approver | Srinivas Telikicherla, QA/RA | I approve this plan for use. | | |
