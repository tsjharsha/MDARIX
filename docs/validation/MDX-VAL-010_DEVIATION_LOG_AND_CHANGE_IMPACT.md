# MDX-VAL-010 Deviation log and change-impact template

| Field | Value |
|---|---|
| Document ID | MDX-VAL-010 |
| Title | Deviation log and change-impact template |
| Version | 0.1 |
| Status | DRAFT |
| Author (R) | Sriharsha Telikicherla, Product & Engineering, system owner |
| Reviewer | Independent CSV consultant (first pack; not engaged yet) |
| Approver (A) | Srinivas Telikicherla, QA/RA, quality approver |
| Drafting | Drafted with software assistance; every line reviewed by Sriharsha Telikicherla (MDX-VAL-000, DC-R43) |
| Date | 12 Nov 2026 |
| Code baseline | Branch `feat/b6b-validation-pack`; generator `scripts/validation_pack.py` |

Change history

| Version | Date | Change | By |
|---|---|---|---|
| 0.1 | 12 Nov 2026 | First draft (B6b Part B, item B10) | Sriharsha Telikicherla |

## 1. Purpose

This document fixes where deviations are logged, how the generator uses them, and the change-impact assessment
that each release carries (MDX-VAL-001 VMP-R25). The deviation lifecycle, the classification and the GxP-risk
definitions are those of MDX-VAL-001 section 13 and Annex C; they are not repeated here.

## 2. Deviation log

- **DL-R01** Every deviation shall be one row of [deviation-log.csv](deviation-log.csv), one file across releases,
  with the columns of MDX-VAL-001 Annex C in this order: `dev_id`, `raised_utc`, `raised_by`, `found_in`,
  `test_or_scenario`, `req_id`, `expected`, `seen`, `documented_first_utc`, `impact`, `gxp_risk`, `classification`,
  `root_cause`, `correction`, `retest_id`, `retest_result`, `change_control`, `capa_ref`, `approved_by`, `closed_utc`,
  `status`.
- **DL-R02** `dev_id` shall be `DEV-<release>-nnn`; the generator reads the rows of the release it builds by that
  prefix.
- **DL-R03** `status` shall be one of open, corrected, retested, closed.
- **DL-R04** A row with status closed shall have a retest result and an approver; the generator lists every row that
  does not (scenario B6-57).
- **DL-R05** While a critical deviation of the release is not closed, the generator shall produce no release approval
  record and shall list the deviation (scenario B6-58).
- **DL-R06** A row shall be added, never rewritten; a correction to a row is a later commit whose message names the
  row, so git history keeps both.

## 3. Change-impact assessment (template, one per release)

Kept in the release folder as `change-impact.md`; its ID is quoted in the release approval record.

| Field | Content |
|---|---|
| Release and commit range | From the last approved release to this one |
| Changes | Each merged change, with its spec or fix reference |
| Functions touched | From the per-function table of MDX-VAL-002 |
| Risk rows affected | RSK IDs, with any re-rating |
| Requirements affected | REQ IDs from `requirements.csv` (new, changed, unchanged) |
| Scenarios to re-run | Every class-A scenario of an affected requirement (VMP-R28); for the first pack, every class-A scenario (VMP-R42) |
| Re-test rule applied | The row of MDX-VAL-001 section 9.3 |
| Customer impact | Whether a change notice is needed, and its date |
| Prepared by / reviewed by | System owner / quality approver, with dates (UTC) |
