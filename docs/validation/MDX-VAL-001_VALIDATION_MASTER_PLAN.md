# MDX-VAL-001 Validation Master Plan

| Field | Value |
|---|---|
| Document ID | MDX-VAL-001 |
| Title | MDARIX Validation Master Plan |
| Version | 0.1 |
| Status | DRAFT, for review and signature |
| Author (R) | Sriharsha Telikicherla, Product & Engineering, system owner |
| Reviewer | Independent CSV consultant (first version; not engaged yet) |
| Approver (A) | Srinivas Telikicherla, QA/RA, quality approver |
| Date | 12 Nov 2026 |
| Code baseline | Product code at `628c624a` (branch `feat/b6b-validation-pack` adds documents only); release in preparation 0.11.04 (`VERSION` file still 0.10.94) |

Change history

| Version | Date | Change | By |
|---|---|---|---|
| 0.1 | 12 Nov 2026 | First draft. Replaces MDX-B10-003 v0.1 (8 Nov 2026) and the MVP-1.0 CSA package (`docs/compliance/CSA_MVP_VALIDATION_PACKAGE.md`). Revised after an independent review: single-statement requirements, supporting controls (section 16), Annexes C and D | Sriharsha Telikicherla |

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
| The markets US, EU and Northern Ireland, Great Britain, India, Canada, and other countries recorded under B9b | AI helpers: AI is off; see section 15 |
| Hosting and configuration that affect records: backup, restore, recovery, time source, TLS, access, keys | The cloud provider's own infrastructure: covered by supplier assessment (MDX-SUP-004) |
| The free-trial edition, only where its behaviour differs (sample clock, same-person signing in a trial) | |

## 3. References

| Ref | Document | Note |
|---|---|---|
| R1 | MDX-VAL-000 Validation document control and index | This folder |
| R2 | MDX-VAL-002 Product risk assessment | This folder |
| R3 | MDX-VAL-003 GAMP 5 category justification | This folder |
| R4 | MDX-B10-001 Intended Use Statement, draft 8 Nov 2026 | `MDARIX-planning/b10/` (not under version control yet) |
| R5 | MDX-B10-002 Regulatory Applicability Matrix, draft 8 Nov 2026 | as R4 |
| R6 | MDX-B10-005 Traceability Structure, draft 8 Nov 2026 | as R4 |
| R7 | MDX-B10-006 Threat Model, draft 8 Nov 2026 | as R4 |
| R8 | Scenario register (master copy) | [scenario-register.md](scenario-register.md) |
| R9 | ISO/TR 80002-2:2017, validation of software for medical device quality systems | Main method. **To confirm with your consultant** |
| R10 | ISPE GAMP 5, A Risk-Based Approach to Compliant GxP Computerized Systems, 2nd edition (2022) | Software categories and supplier leverage. **To confirm with your consultant** |
| R11 | FDA guidance, Computer Software Assurance for Production and Quality Management System Software (final guidance, 2025) | Risk-based assurance. Title, date and status **to confirm with your consultant** |
| R12 | PIC/S PI 011-3, Good Practices for Computerised Systems in Regulated "GxP" Environments | The inspector's cross-check. **To confirm with your consultant** |
| R13 | ISO 13485:2016 clause 4.1.6 (validation of software used in the QMS); 21 CFR 820 as amended (QMSR) | The customer's obligation that this plan supports. **To confirm with your consultant** |
| R14 | 21 CFR Part 11; EU GMP Annex 11 | Assessed in MDX-SUP-003. Annex 11 is used as a benchmark only (owner decision B6b-D9) |

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
| Independent CSV consultant | To be engaged (B6b-D20) | Reviews the first full validation pack: this plan, the risk assessment, the GAMP justification, the class-A protocols and the first VSR |
| Customer QA/RA | Each customer | Approves its own intended use and its own validation |

### 6.2 Rules

- **VMP-R01** Nobody shall approve their own work. The approver (A) of a document or result shall be a different
  person from its author or executor (R).
- **VMP-R02** The quality approver shall independently review every protocol and every result that the system owner
  writes or executes.
- **VMP-R03** The system owner shall approve, as system owner, every document that the quality approver writes.
- **VMP-R04** Text drafted with software assistance shall have a named person as author (R).
- **VMP-R05** That author shall review every line before the text goes for approval.
- **VMP-R06** Software shall not be named as author, reviewer or signer.
- **VMP-R07** The independent CSV consultant shall review the first full validation pack before it is given to any
  customer.
- **VMP-R08** For a class-A control, the review or the execution shall be done by someone other than the developer
  of that control.
- **VMP-R09** No document under this plan shall be shared with a customer before the consultant has reviewed it.
  (Internal records, such as a release approval record, are approved under section 6.3 without waiting for the
  consultant.)

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
with your consultant**: edition, status and fit (B6b spec section 9, question 9).

- **VMP-R10** Each function's validation activities shall be those set for its class in section 8.
- **VMP-R11** Each VSR shall state, for each reference R9 to R12, which of its expectations the release pack meets
  and which it does not.
- **VMP-R12** Platform software (operating system, PostgreSQL, container runtime, web server, file scanner, Python
  and Node runtimes) shall be used as supplied, with its version recorded in the IQ record.
- **VMP-R13** MDARIX shall test its own use of platform software, not the platform software itself.
- **VMP-R14** An automated test shall count as evidence for the scenario named in its `requirement` marker
  (`pytest.ini`) only when it ran on the tagged build and its JUnit output is kept in the release folder. Whether
  this counts as OQ evidence under CSA is **to confirm with your consultant**.
- **VMP-R15** Libraries built into the application (for example FastAPI, SQLAlchemy, React) shall be treated as
  part of the product: listed by version in the release's software bill of materials and changed under the
  change-impact rule (section 9.3).

## 8. Risk classes and assurance levels

The class of each function comes from MDX-VAL-002. The class is set by severity alone (owner decision B6b-D4).

| Class | Meaning | Assurance level |
|---|---|---|
| **A: High** (severity 4 or 5) | A failure could cause a missed or late authority report, a wrong regulatory conclusion, an undetected change to a signed record, a signature not bound to its record, lost regulated records, or one customer seeing another's data | Scripted testing with expected results approved before execution; negative tests (what must be refused); automated regression on every build; independent review of protocol and results; execution evidence kept; every class-A scenario of a touched function run in that release |
| **B: Medium** (severity 3) | A failure shows wrong or missing information that a trained person is expected to catch before signing, or delays work | Scenario testing: the scenario register row is the test, the tester records what was done and seen; automated tests where they exist; peer review |
| **C: Low** (severity 1 or 2) | Cosmetic or convenience; no record or decision effect | Automated build checks (lint, unit tests, build); exploratory testing; only failures recorded |

- **VMP-R16** A function's class shall be the class of its highest-severity failure mode in MDX-VAL-002.
  A function with no failure mode that can affect a record or a decision is class C on the rationale recorded in
  MDX-VAL-002 section 4.
- **VMP-R17** A change that touches a class-A function shall be treated as class A for that release, whatever its
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

MDARIX is released in small, frequent releases on one shared version for every customer. Each release is validated
for MDARIX's own intended use by the steps below, instead of one large validation at the end.

- **VMP-R18** Each release spec shall list the REQ IDs and scenario IDs it adds or changes.
- **VMP-R19** Each release shall carry a change-impact assessment that sets which scenarios must be re-run (9.3).
- **VMP-R20** The automated suite shall run on the tagged build.
- **VMP-R21** The suite's JUnit output and the release-checks JSON shall be kept in
  `docs/validation/releases/<version>/`.
- **VMP-R22** Every class-A scenario named by the change impact shall be executed and recorded before release.
- **VMP-R23** A scenario's status in the register shall be one of PASS, FAIL, BLOCKED, NOT RUN, REQUIRES HUMAN
  DECISION.
- **VMP-R24** A BLOCKED or NOT RUN scenario shall not be counted as passed.
- **VMP-R25** The RTM and the validation figures shall be generated for each release, not written by hand.
- **VMP-R26** The quality approver shall sign the release approval record before every production deploy (owner
  decision B6b-D7).
- **VMP-R27** For an emergency fix, the quality approver's written OK shall be given before the deploy.
- **VMP-R28** For an emergency fix, the signed release approval record shall follow within 1 working day of the
  deploy.
- **VMP-R29** A change to a class-A function, a rule floor or a sub-processor shall be notified to customers at least
  10 working days before the deploy (owner decision B6b-D14).
- **VMP-R30** An emergency security fix shall be notified to customers after the deploy, within the period the
  change-control SOP (MDX-SOP-002) sets.
- **VMP-R31** A release folder holding a signed approval shall not be overwritten.
- **VMP-R32** A correction to a signed release record shall be a new version that names the one it replaces.

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

## 10. Environments (owner decision B6b-D16)

| Environment | Use | Data |
|---|---|---|
| Controlled local test environment: a clean test database built from the tagged commit on the build computer | Automated tests; IQ, OQ and MDARIX PQ execution until staging exists | Synthetic data only |
| Staging (not available yet, G4) | IQ, OQ and PQ execution once it exists; penetration test | Synthetic or sample data; never production data |
| Production | IQ checks of the installed release only (version, health, configuration check, clock check) | No test data entered |

- **VMP-R33** Until staging exists, the identity of the controlled local environment (commit, migration head,
  versions of Python, Node and PostgreSQL) shall be recorded as an IQ of the test environment.
- **VMP-R34** Until staging exists, the VSR shall label every result "controlled local environment".
- **VMP-R35** No test data shall be entered in production.
- **VMP-R36** The GxP workflow check of a recovery shall run on a scratch copy of the backup, never in production
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

- **VMP-R37** Every class-A scenario in scope shall be PASS, with evidence.
- **VMP-R38** No open deviation shall affect patient safety or data integrity. Every other open deviation shall have
  an acceptance rationale signed by the quality approver.
- **VMP-R39** The isolation tests shall show zero cross-organisation access, in both directions, on every surface
  tested (API, search, export, files, reports, background jobs).
- **VMP-R40** Every signed record in the test set shall verify (signature hash, snapshot hash).
- **VMP-R41** The audit chain of every organisation in the test set shall verify from start to end.
- **VMP-R42** Every legal clock in the test set shall match its pre-approved expected date and time, including
  weekends, holidays and daylight-saving changes.
- **VMP-R43** Every value in an authority-report file in the test set shall trace to the approved snapshot.
- **VMP-R44** Every FDA eMDR file in the test set shall validate against FDA's schemas.
- **VMP-R45** The full automated suite shall pass on the tagged build.
- **VMP-R46** A critical failure shall block the release: cross-organisation access, an uncontrolled change to a
  record, missing audit evidence, an approval that cannot be reproduced, a wrong legal clock, wrong report data, a
  signature not bound to its version, or the sample clock moving a real record.

## 13. Deviations

- **VMP-R47** Every failed step, blocked step or protocol error shall be recorded in the deviation log before any fix
  is made.
- **VMP-R48** Each deviation shall be assessed for its impact on patient, product and data integrity, and given a GxP
  risk (high, medium, low) and a classification (critical, major, minor).
- **VMP-R49** A deviation shall be closed only with a retest result and the quality approver's approval.
- **VMP-R50** Each deviation shall record whether change control is needed.
- **VMP-R51** An open critical deviation shall block the release.

The log's columns and lifecycle are in Annex C. The log itself is MDX-VAL-010 (B6b Part B).

## 14. Maintaining the validated state

- **VMP-R52** The configuration baseline of each release (migration head, rule-register versions and content hashes,
  question-set versions, switches) shall be recorded in its IQ record.
- **VMP-R53** A recovery validation (database, audit chain, configuration, held outbox events) shall be run and
  recorded at each quarterly restore drill (MDX-OPS-001).
- **VMP-R54** This plan shall be reviewed every 12 months (owner decision B6b-D18).
- **VMP-R55** The product risk assessment (MDX-VAL-002) shall be reviewed every 12 months, in addition to its
  update in each release.
- **VMP-R56** The supplier assessment (MDX-SUP-001 and MDX-SUP-004) shall be reviewed every 12 months.
- **VMP-R57** The customer periodic review template (MDX-CUS-004) shall set a review every 12 months.
- **VMP-R58** MDARIX's own periodic review report shall list the incidents, complaints about MDARIX, MDARIX CAPAs
  and customer audit findings of the period, from the registers set up in B6b Part D.

## 15. AI

AI is off in every release under this plan, and AI helpers are out of scope.

- **VMP-R59** No AI helper shall be switched on for a customer before the AI release gate
  (`backend/app/ai_release_gate.py`) passes for it.
- **VMP-R60** No AI helper shall be switched on for a customer before an AI validation protocol, covering at least
  the items of Annex D, has been approved as a change to this plan.

## 16. Supporting controls

### 16.1 Tools that produce evidence

- **VMP-R61** Each tool that produces validation evidence (the test runner, the release-checks script, the RTM and
  figures generator) shall be recorded by version in the IQ record of the release.
- **VMP-R62** A tool MDARIX writes to produce evidence (the release-checks script, the validation-pack generator)
  shall have its own automated tests, including tests that it fails on bad input (B6b scenarios B6-47 to B6-51).
- **VMP-R63** A third-party test tool (for example pytest) shall be used as supplied; it is qualified by use: a test
  known to fail shall be seen to fail in the run that qualifies a new major version of the tool.

### 16.2 Training

- **VMP-R64** Each person who executes or approves a protocol shall have read this plan and that protocol before
  executing or approving.
- **VMP-R65** Each VSR shall list who executed and who approved, with the date each read this plan and the protocol.

### 16.3 Good documentation practice for executed evidence

- **VMP-R66** Each executed step shall record the actual result, the executor, the date and time (UTC) and the
  evidence reference.
- **VMP-R67** A screenshot or file used as evidence shall be stored with its SHA-256 in the release folder.
- **VMP-R68** A correction to an executed record shall keep the original entry readable and record who corrected it,
  when and why.
- **VMP-R69** An expected result shall not be changed after execution has started; a needed change is a deviation.

### 16.4 Retention

- **VMP-R70** Validation records of a release shall be kept for at least 7 years after the release is retired from
  the last customer, matching the audit-trail retention in `docs/compliance/DATA_RETENTION_SCHEDULE.md`. (Owner to
  confirm the period.)

### 16.5 Retirement of MDARIX or of a function

- **VMP-R71** Before a function or the product is retired, a retirement plan shall state how each customer's records
  are exported, handed back, kept readable for their retention period, and purged.
- **VMP-R72** The retirement plan shall be approved by the quality approver before the retirement starts.

## 17. Open points and blockers

| # | Point | Owner |
|---|---|---|
| OP-1 | No independent CSV consultant engaged. This plan stays DRAFT and is shared with no customer until the consultant has reviewed it (VMP-R09) | Srinivas |
| OP-2 | The company is not registered yet; the supplier documents need the legal entity and its signatory | Srinivas |
| OP-3 | No staging environment (G4): formal execution on the controlled local environment until then (section 10) | Srinivas |
| OP-4 | `VERSION` (0.10.94) and the CHANGELOG section disagree; the release identity must be fixed before the first per-release pack | Sriharsha |
| OP-5 | MDX-B10-001, -002, -005 and -006 are drafts outside version control; move them into this folder or re-issue them | Srinivas |
| OP-6 | Each reference R9 to R13 to be confirmed with the consultant | Srinivas |

## Annex A: writing standard

The writing standard for every document under this plan is MDX-VAL-000 section 2.5.

## Annex B: audit-finding self-check (in every VSR)

- **VMP-R73** Every VSR shall answer each line below with yes or no and name the evidence.

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
change control is needed. VMP-R47 to VMP-R51 apply. Blocked or not run is never a pass.

## Annex D: AI validation items (for the protocol before switch-on)

The AI validation protocol required by VMP-R60 covers at least:

1. The intended use of each AI feature.
2. The GxP risk of each AI feature, added to MDX-VAL-002.
3. Qualification against the signed-off golden dataset (`docs/validation/AI_GOLDEN_DATASET_QUALIFICATION.md`), with
   pass criteria set before the run.
4. The provider and model version pinned and recorded (`docs/compliance/AI_PROVIDER_REGISTER.md`).
5. Human review and sign-off of every AI output before it reaches a record.
6. An audit trail of the prompt, model, output and reviewer.
7. Monitoring for drift, and re-qualification on any model change.

References for that protocol, **to confirm with your consultant**: GAMP 5 2nd edition (AI/ML appendix), FDA CSA,
Part 11 and Annex 11, ICH Q9, ALCOA+, and the EU draft GMP Annex 22 (AI).

## Signatures

Unsigned. The signed PDF and its `signatures.csv` row are added after review (MDX-VAL-000 section 2.6).

| Role | Name | Meaning of signature | Signature | Date |
|---|---|---|---|---|
| Author (R), system owner | Sriharsha Telikicherla, Product & Engineering | I wrote this plan and reviewed every line. | | |
| Reviewer (C) | Independent CSV consultant | I reviewed this plan; my comments are recorded. | | |
| Approver (A), quality approver | Srinivas Telikicherla, QA/RA | I approve this plan for use. | | |
