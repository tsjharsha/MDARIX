# MDX-VAL-012 Release approval record: interim template

| Field | Value |
|---|---|
| Document ID | MDX-VAL-012 (the template; each per-release record is MDX-VAL-012-&lt;release&gt;) |
| Title | Release approval record: interim template |
| Version | 0.4 |
| Status | DRAFT. To be signed by the owner before the big-bang deploy (owner decision O19); PDF for signature: `signing/MDX-VAL-012-template.pdf` (unsigned) |
| Author (R) | Sriharsha Telikicherla, Product & Engineering, system owner (prepares each record) |
| Reviewer | Independent CSV consultant (not engaged yet; MDX-VAL-013 question 24) |
| Approver (A) | Srinivas Telikicherla, QA/RA, quality approver (signs each record) |
| Drafting | Drafted with software assistance; every line reviewed by Sriharsha Telikicherla (MDX-VAL-000, DC-R43) |
| Date | 12 Nov 2026 |
| Code baseline | Branch `feat/b6b-validation-pack`; generator `scripts/validation_pack.py` (`validation/pack.py`, `INTERIM_CRITERIA`) |

Change history

| Version | Date | Change | By |
|---|---|---|---|
| 0.1 | 12 Nov 2026 | First draft, owner decision O13: an interim release approval template for the big-bang deploy, before MDX-VAL-001 is approved as 1.0 | Sriharsha Telikicherla |
| 0.2 | 12 Nov 2026 | After an independent rating: only criterion 3 may be marked accepted (VMP-R49); signature section number; filing of per-release records; section 5 cites the regression run | Sriharsha Telikicherla |
| 0.3 | 12 Nov 2026 | Each per-release record has its own ID, MDX-VAL-012-&lt;release&gt; (RA-T01, RA-T06). Owner decisions O17 to O19 of 12 Nov 2026: big-bang gate for the "Acceptable after verification" action rows (section 5); a risk acceptance covers only NOT RUN scenarios and Open rows, a failed class-A test always blocks (criteria 3 to 5, RA-T04); to be signed by the owner before the big-bang deploy | Sriharsha Telikicherla |
| 0.4 | 12 Nov 2026 | Criterion 9 checkable before signing: the post-deploy command and the rollback rule are in the record; the result goes into its post-deploy section (RA-T07) | Srinivas Telikicherla |

## 1. Purpose and scope

The quality approver signs a release approval record before every production deploy from the big-bang deploy onward
(owner decision B6b-D7; MDX-VAL-001 VMP-R34 to VMP-R36, VMP-R41). The Validation Master Plan is still a draft, so
this template sets what that record holds and what the approver checks until MDX-VAL-001 is approved as 1.0. It
then becomes the release approval record of the plan (section B.2 of the B6b spec), with the same fields.

The record approves a deploy. It does not state that the release is validated under the plan (VMP-R44).

## 2. How a record is made

- **RA-T01** The system owner shall generate the record with `scripts/validation_pack.py` for the release: it writes
  `MDX-VAL-012-release-approval` (JSON, Markdown, DOCX, PDF) into `docs/validation/releases/<release>/`, with the
  fields of section 3 and the criteria of section 4. This template is document MDX-VAL-012; each record made from it
  is document MDX-VAL-012-&lt;release&gt; (for example MDX-VAL-012-0.11.04).
- **RA-T02** The generator shall refuse to write the record while a check fails: a requirement without a scenario,
  a class-A requirement without a negative scenario, an open critical deviation, release checks that are not a full
  suite on the same commit, or a release that differs from `VERSION` (owner decision O16).
- **RA-T03** The system owner shall fill the blank fields of section 3 by hand before the approver signs.
- **RA-T04** The quality approver shall initial each criterion of section 4 as met or not met, and sign section 6.
  A criterion marked "not met" stops the deploy. Only criterion 3 may instead be marked "accepted", and only for a
  class-A scenario that is NOT RUN and listed in a signed risk acceptance under criterion 4 (VMP-R49a). A failed
  class-A test or scenario is never accepted (VMP-R50, owner decision O18).
- **RA-T05** For an emergency fix, the approver's written OK (e-mail or chat, quoted with its time) shall be given
  before the deploy and recorded in the field "Emergency fix: written OK"; the signed record follows within 1 working
  day (VMP-R35, VMP-R36).
- **RA-T06** The signed PDF shall be saved as `MDX-VAL-012-release-approval-signed.pdf` in the release folder and
  listed in `signatures.csv` under document MDX-VAL-012-&lt;release&gt;; the generator then never overwrites that
  folder (VMP-R39). A per-release record is filed
  in its release folder, not under `signed/` (generated records, MDX-VAL-000 section 3).
- **RA-T07** Right after the deploy the system owner shall run the command in section 4 of the record (post-deploy
  record) and write its result, time and name there; a failure starts the rollback. The approver checks before
  signing only that the command and the rollback rule are there (criterion 9), so every criterion can be checked
  before the signature.

## 3. Fields

| Field | Filled by | Content |
|---|---|---|
| Release, commit, tag, migration head | Generator | The release identity; the release must equal `VERSION` |
| Release checks (result, full suite, SHA-256) | Generator | From `release-checks-<release>.json` of the same commit |
| JUnit summary | Generator | Tests, passed, failed, skipped |
| RTM SHA-256; validation figures (G13) | Generator | From the generated RTM and `g13.json` |
| Open deviations, each with its acceptance rationale | Generator lists; system owner writes each rationale | From `deviation-log.csv` |
| Risk acceptances | System owner | Each Open MDX-VAL-002 row the release relies on that is class A or needs action: RSK ID, interim control, due date, reference of the signed acceptance (RA-R07, RA-R08) |
| Change-impact reference | System owner | The release's `change-impact.md` (MDX-VAL-010 section 3) |
| Customer change notice date | System owner | Where VMP-R37 needs one; "not needed" with the reason otherwise |
| Restore point and rollback plan | System owner | Backup or snapshot name taken before the deploy; how to roll back |
| Emergency fix: written OK | System owner | "Not an emergency fix", or the quoted OK with its time (RA-T05) |
| Post-deploy check | System owner, after the deploy | `deploy_gate.py` result on production |
| Basis | Generator | The interim statement of section 1 |
| Prepared by, date | System owner | |
| Approver, date, meaning | Quality approver | "I approve this release for production after the checks listed." |

## 4. Criteria the quality approver checks

| # | Criterion |
|---|---|
| 1 | Release identity: the release equals `VERSION`, the commit is the tagged commit, one migration head |
| 2 | Release checks: full suite on this commit, every step passed (release-checks JSON and its SHA-256) |
| 3 | Every class-A scenario named by the change-impact assessment is PASS with evidence, or NOT RUN and listed in a risk acceptance under criterion 4; none is FAIL (VMP-R49, VMP-R49a, VMP-R50) |
| 4 | Every Open MDX-VAL-002 row this release relies on, and every class-A scenario still NOT RUN, has a signed risk acceptance listed in this record (RA-R07, RA-R08, VMP-R49b) |
| 5 | No failed class-A test, no open critical deviation, no open deviation that affects patient safety or data integrity; every other open deviation has its acceptance rationale (VMP-R50, VMP-R50a, VMP-R51) |
| 6 | No critical failure of VMP-R60 (a risk acceptance never covers one) |
| 7 | Change-impact assessment reviewed; customer change notice given where VMP-R37 needs one |
| 8 | Restore point taken before the deploy and the rollback plan written |
| 9 | Post-deploy check ready before signing: the `deploy_gate.py` command for this release is in section 4 of the record, and a failure starts the rollback of criterion 8 |

The same nine lines are printed in each generated record (`validation/pack.py`, `INTERIM_CRITERIA`); a change to one
is a change to both.

## 5. For the big-bang deploy

The first record under this template is for the big-bang deploy. Expected at the date of this draft, so that nobody
is surprised on the day:

- Criterion 3 (owner decision O17; VMP-R50b, VMP-R50c): the class-A scenarios of the MDX-VAL-002 rows that need
  action and are marked "Acceptable after verification" (20 rows at 12 Nov 2026: RSK-001, -004 to -008, -022, -027,
  -029, -031, -033, -034, -039, -044, -050, -052 to -055, -066; RSK-037 also needs action after its re-score, O21)
  run in the full end-to-end run of 30 Nov 2026. Any still NOT RUN after it goes into one risk acceptance, signed by
  the quality approver before the deploy and listed under criterion 4. A FAIL in that run blocks the deploy until it
  is fixed and re-run (O18).
- Criterion 4: each Open row the deploy relies on needs its signed risk acceptance. The VSR is not yet approved, so
  MDARIX's statement of validation status stays "Validation in progress; plan MDX-VAL-001 (draft)" (VMP-R44).
- This template and MDX-VAL-000 section 4 are signed by the owner before the deploy (owner decision O19).
- Criterion 2: the full suite runs in the E2E test release (about 24 November 2026). The 22 failures seen in the
  first tagged run of 12 Nov 2026 (B6b spec, build status run 3) were stale tests, fixed on the B6a line and merged
  into this branch on 12 Nov 2026; every step must pass, as a logged deviation does not meet criterion 2.

## 6. Signatures

Unsigned. The signed PDF and its `signatures.csv` row are added after review (MDX-VAL-000 section 2.6).

| Role | Name | Meaning of signature | Signature | Date |
|---|---|---|---|---|
| Author (R), system owner | Sriharsha Telikicherla, Product & Engineering | I am responsible for this template and reviewed every line of the draft. | | |
| Reviewer (C) | Independent CSV consultant | I reviewed this template; my comments are recorded. | | |
| Approver (A), quality approver | Srinivas Telikicherla, QA/RA | I approve this template for release approval records until MDX-VAL-001 is approved as 1.0. | | |
