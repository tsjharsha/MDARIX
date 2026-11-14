# MDX-SOP-002 Change control

| Field | Value |
|---|---|
| Document ID | MDX-SOP-002 |
| Title | Change control, re-test rules and customer change notice |
| Version | 0.1 |
| Status | DRAFT |
| Author (R) | Sriharsha Telikicherla, Product & Engineering, system owner |
| Reviewer | Independent CSV consultant (not engaged yet) |
| Approver (A) | Srinivas Telikicherla, QA/RA, quality approver |
| Drafting | Drafted with software assistance; every line reviewed by Sriharsha Telikicherla (MDX-VAL-000, DC-R43) |
| Date | 14 Nov 2026 |
| Code baseline | Product code at `6b01eda5` (tip of `feat/b6b-validation-pack`); B6b Part C changes no code; release in preparation 0.11.04 (`VERSION` file still 0.10.94) |

Change history

| Version | Date | Change | By |
|---|---|---|---|
| 0.1 | 14 Nov 2026 | First draft (B6b Part C, item C3). Sets the period for notifying an emergency security fix (MDX-VAL-001 VMP-R38) | Sriharsha Telikicherla |

## 1. Purpose and scope

This procedure controls every change to MDARIX in production: product code, database schema, rule content (question
sets, floor versions, harm scale, word lists), dependencies, the operating system, PostgreSQL, hosting and production
configuration (backup, TLS, keys, time zone). It sets how a change is requested, assessed, re-tested, approved,
notified to customers, deployed and checked.

Every customer on the shared plane runs the same version (MDX-VAL-001 section 9.2,
`MDX-VAL-001_VALIDATION_MASTER_PLAN.md:234`). A customer cannot stay on an older version there; it controls change
through the change notice (section 3.5) and its own assessment.

## 2. Roles

| Role | Person | Does |
|---|---|---|
| System owner | Sriharsha Telikicherla | Raises changes, assesses impact, re-tests, prepares the release approval record, deploys |
| Quality approver | Srinivas Telikicherla | Reviews the impact assessment, checks each reason given for a lower risk, signs the release approval record |

## 3. Procedure

### 3.1 Change request

- **CC-R01** Each change shall have a change request: a backlog item with its approved spec, or a fix reference
  with the defect or deviation it corrects.
- **CC-R02** A change to rule content shall be a new rule-register version with its own content hash, never an edit
  of a version in force (`backend/app/rule_register/register.py:79-82`).
- **CC-R03** A rule-register version shall not be approved by the person who built it; the check compares staff
  accounts (owner decisions O3 and O10; `backend/app/rule_register/register.py`).
- **CC-R04** A newer edition of an authority's report form shall be added as a new pinned folder and a new
  rule-register version, never as an edit of a pinned file (`docs/runbooks/DEPLOYMENT.md:168-172`).

### 3.2 Impact assessment

- **CC-R05** Each release shall carry a change-impact assessment in the form of MDX-VAL-010 section 3, kept in its
  release folder as `change-impact.md`.
- **CC-R06** The assessment shall set the risk of each change on its own (owner decision O11; MDX-VAL-001 VMP-R23).
- **CC-R07** The quality approver shall check each reason given for treating a change as lower than class A.

### 3.3 Re-test rules

- **CC-R08** Each change shall be re-tested at least as the row of MDX-VAL-001 section 9.3 for its change type
  requires.

The rows of MDX-VAL-001 section 9.3, summarised (that section governs):

| Change type | Minimum re-validation |
|---|---|
| Can alter a class-A function's records, decisions, clocks, signatures, reports or data model | Every class-A scenario of that function; full automated suite; independent review |
| Touches a class-A screen or code but cannot alter its behaviour (reason recorded) | Automated suite; scenario rows of the changed screens; the quality approver checks the reason |
| New rule or question-set version, new floor version | The rule-register test rows of that market, the content-hash test, a signed rule change note |
| Migration that changes regulated tables | IQ migration check; restore of the previous backup into the new schema; audit-chain verification |
| Class B or C only | Automated suite; scenario rows of the changed screens |
| Hosting or configuration change (backup, TLS, keys, time zone) | IQ re-check of the changed item; restore drill if the backup changes |
| Dependency, operating-system or PostgreSQL upgrade | Full automated suite; IQ version record; class-A scenarios that use the changed component |
| Security fix | Regression for the fix and the related threat-model test |

- **CC-R09** A change of hosting provider, region or sub-processor shall also need a new or updated provider
  assessment (MDX-SUP-004) before customer data moves.

### 3.4 Approval

- **CC-R10** The quality approver shall sign the release approval record (MDX-VAL-012) before every production
  deploy (owner decision B6b-D7; MDX-VAL-001 VMP-R34).
- **CC-R11** The release approval record shall name the change-impact assessment of the release.

### 3.5 Customer change notice (owner decision B6b-D14)

- **CC-R12** Customers shall be notified at least 10 working days before the deploy of a change to a class-A
  function, a rule floor or a sub-processor (MDX-VAL-001 VMP-R37).
- **CC-R13** Every release shall have release notes sent to every customer's change-notice recipients.
- **CC-R14** A change notice shall state: the release, the deploy date, what changes, the functions and markets
  affected, the risk class, whether the customer may need to re-test, and where the release pack can be obtained
  under the non-disclosure agreement (owner decision B6b-D19).

### 3.6 Emergency path

An emergency change is a fix that cannot wait 10 working days without risk to customers' records, deadlines or
security.

- **CC-R15** For an emergency fix, the quality approver's written OK shall be given before the deploy (MDX-VAL-001
  VMP-R35).
- **CC-R16** For an emergency fix, the signed release approval record shall follow within 1 working day of the deploy
  (MDX-VAL-001 VMP-R36).
- **CC-R17** An emergency security fix shall be notified to customers within 1 working day after the deploy
  (MDX-VAL-001 VMP-R38).
- **CC-R18** An emergency fix shall still be re-tested per section 3.3 before deploy; a re-test that cannot finish
  before the deploy shall be logged as a deviation (MDX-VAL-010).

### 3.7 Deploy and post-deploy check

- **CC-R19** A backup shall be taken immediately before the upgrade (`docs/runbooks/DEPLOYMENT.md:184`).
- **CC-R20** After the deploy, the readiness gate `scripts/deploy_gate.py` shall pass for the release, with the worker
  and scheduler required (`scripts/deploy_gate.py:1-9`; `docs/runbooks/DEPLOYMENT.md:209`).
- **CC-R21** A failed deploy shall be rolled back to the previous tag (`docs/runbooks/DEPLOYMENT.md`, section 4) and
  recorded as a deviation.
- **CC-R22** The deploy, its gate result and any rollback shall be recorded in the operations log (B6b Part D
  registers).

## 4. Records

Change request (backlog item, spec, fix reference); `change-impact.md` in the release folder; signed release approval
record; change notice and release notes with their sending date; deploy-gate output; operations log entry.

## Signatures

Unsigned. The signed PDF and its `signatures.csv` row are added after review (MDX-VAL-000 section 2.6).

| Role | Name | Meaning of signature | Signature | Date |
|---|---|---|---|---|
| Author (R), system owner | Sriharsha Telikicherla, Product & Engineering | I am responsible for this document and reviewed every line of the draft. | | |
| Reviewer (C) | Independent CSV consultant | I reviewed this document; my comments are recorded. | | |
| Approver (A), quality approver | Srinivas Telikicherla, QA/RA | I approve this procedure for use. | | |
