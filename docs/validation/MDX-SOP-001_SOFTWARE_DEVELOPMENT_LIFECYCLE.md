# MDX-SOP-001 Software development lifecycle

| Field | Value |
|---|---|
| Document ID | MDX-SOP-001 |
| Title | Software development lifecycle |
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
| 0.1 | 14 Nov 2026 | First draft (B6b Part C, item C3) | Sriharsha Telikicherla |

## 1. Purpose and scope

This procedure sets how MDARIX software is specified, built, tested and released. It covers the product code in the
MDARIX repository, its database migrations, its infrastructure files and its release images. It does not cover a
customer's configuration (the customer controls that) or AI features (off; MDX-VAL-001 section 15).

How a change is approved and released is in MDX-SOP-002 (change control). How a release is validated is in
MDX-VAL-001 section 9.

## 2. Roles

| Role | Person | Does |
|---|---|---|
| System owner | Sriharsha Telikicherla, Product & Engineering | Writes specs' technical parts, builds, tests, prepares releases |
| Quality approver | Srinivas Telikicherla, QA/RA | Approves specs as owner, reviews protocols and results, signs the release approval record |

Nobody approves their own work (owner decision B6b-D1; MDX-VAL-001 section 6).

## 3. Procedure

### 3.1 Requirements and specification

- **SDLC-R01** Each build item shall start from a written spec that the owner approves before the build starts.
- **SDLC-R02** An approved spec shall be copied into `docs/specs/` and controlled there (owner decision O22;
  MDX-VAL-000 section 3.3).
- **SDLC-R03** Each spec shall list the REQ IDs and scenario IDs it adds or changes (MDX-VAL-001 VMP-R24).
- **SDLC-R04** Each new requirement shall be added to `docs/validation/requirements.csv` with its risk class.

### 3.2 Build

- **SDLC-R05** Each build item shall be built on its own branch, never on `main` directly.
- **SDLC-R06** Code shall follow the repository conventions in `AGENTS.md`, among them: the tenant and the acting
  user come only from the authenticated request context (`AGENTS.md:34`); authorization is enforced on the server
  (`AGENTS.md:39`); secrets and personal data are never committed (`AGENTS.md:40`).
- **SDLC-R07** Every database change shall come with a migration, and migrations shall be expand/contract so that the
  previous release keeps working on the new schema (`docs/runbooks/DEPLOYMENT.md:198`).
- **SDLC-R08** No production customer data shall be used in development or tests; test data is synthetic.

### 3.3 Test

- **SDLC-R09** Every behaviour change shall ship with a test that fails without the change (`AGENTS.md:66`).
- **SDLC-R10** A test that proves a scenario shall carry the `requirement(<scenario ID>)` marker (owner decision
  B6b-D21).
- **SDLC-R11** Before a change is merged, the linters, the formatters and the tests named in `AGENTS.md:67` shall pass.
- **SDLC-R12** The automated suite of a release shall run on the tagged build, and its JUnit output and the
  release-checks JSON shall be kept in the release folder (MDX-VAL-001 VMP-R26, VMP-R27; `scripts/release_checks.ps1`).

### 3.4 Review

- **SDLC-R13** Each change to a class-A function (MDX-VAL-002 section 4) shall be reviewed by a person other than
  its author before merge, and the review recorded in the pull request or the build record.

### 3.5 Secure development

- **SDLC-R14** Each pull request shall be scanned for secrets (`.github/workflows/ci.yml:768-790`, gitleaks).
- **SDLC-R15** Each release image shall be scanned before release; a high or critical finding not reviewed in
  `.trivyignore.yaml` stops the release (`.github/workflows/release.yml:2-4,43-50`).
- **SDLC-R16** Each release shall publish a software bill of materials per image (`.github/workflows/release.yml:4`).

### 3.6 Release

- **SDLC-R17** A release shall be a git tag `vX.Y.Z` equal to the `VERSION` file; the release workflow refuses a
  mismatch (`.github/workflows/release.yml:27-30`).
- **SDLC-R18** A release shall be validated per MDX-VAL-001 section 9 and approved per MDX-SOP-002 before it is
  deployed to production.

### 3.7 Records

| Record | Where |
|---|---|
| Approved specs | `docs/specs/` |
| Requirements and scenarios | `docs/validation/requirements.csv`, `docs/validation/scenario-register.md` |
| Code, reviews, tests | Git history and pull requests |
| Release evidence | `docs/validation/releases/<version>/` |

## 4. Where hosted CI does not run

When the hosted CI cannot run (for example a billing stop), the release checks run on the build laptop with
`scripts/release_checks.ps1` on a clean test database built from the tagged commit, recorded as an IQ of that
environment (owner decision B6b-D16).

- **SDLC-R19** A release built without hosted CI shall say so in its Validation Summary Report.

## 5. References

MDX-VAL-001 Validation Master Plan; MDX-SOP-002 change control; `AGENTS.md`; `docs/runbooks/DEPLOYMENT.md`.

## Signatures

Unsigned. The signed PDF and its `signatures.csv` row are added after review (MDX-VAL-000 section 2.6).

| Role | Name | Meaning of signature | Signature | Date |
|---|---|---|---|---|
| Author (R), system owner | Sriharsha Telikicherla, Product & Engineering | I am responsible for this document and reviewed every line of the draft. | | |
| Reviewer (C) | Independent CSV consultant | I reviewed this document; my comments are recorded. | | |
| Approver (A), quality approver | Srinivas Telikicherla, QA/RA | I approve this procedure for use. | | |
