# MDX-VAL-010 Deviation log and change-impact template

| Field | Value |
|---|---|
| Document ID | MDX-VAL-010 |
| Title | Deviation log and change-impact template |
| Version | 0.4 |
| Status | DRAFT |
| Author (R) | Sriharsha Telikicherla, Product & Engineering, system owner |
| Reviewer | Independent CSV consultant (first pack; not engaged yet) |
| Approver (A) | Srinivas Telikicherla, QA/RA, quality approver |
| Drafting | Drafted with software assistance; every line reviewed by Sriharsha Telikicherla (MDX-VAL-000, DC-R43) |
| Date | 14 Nov 2026 |
| Code baseline | Branch `feat/b6b-validation-pack`; generator `scripts/validation_pack.py` |

Change history

| Version | Date | Change | By |
|---|---|---|---|
| 0.1 | 12 Nov 2026 | First draft (B6b Part B, item B10) | Sriharsha Telikicherla |
| 0.2 | 12 Nov 2026 | Owner decision O11: each change carries its own risk, which sets its re-test rule (MDX-VAL-001 VMP-R23); DL-R06 keeps every version of a row in git; re-run scope as MDX-VAL-001 section 9.3; signature block | Sriharsha Telikicherla |
| 0.3 | 12 Nov 2026 | DL-R07 allowed `found_in` values, checked by the generator (owner, 12 Nov 2026) | Sriharsha Telikicherla |
| 0.4 | 14 Nov 2026 | Owner decision O36: column `customer_scope` (DL-R01) and rule DL-R08, checked by the generator and used by the health report | Sriharsha Telikicherla |

## 1. Purpose

This document fixes where deviations are logged, how the generator uses them, and the change-impact assessment
that each release carries (MDX-VAL-001 VMP-R25). The deviation lifecycle, the classification and the GxP-risk
definitions are those of MDX-VAL-001 section 13 and Annex C; they are not repeated here.

## 2. Deviation log

- **DL-R01** Every deviation shall be one row of [deviation-log.csv](deviation-log.csv), one file across releases,
  with the columns of MDX-VAL-001 Annex C in this order: `dev_id`, `raised_utc`, `raised_by`, `found_in`,
  `test_or_scenario`, `req_id`, `expected`, `seen`, `documented_first_utc`, `impact`, `gxp_risk`, `classification`,
  `root_cause`, `correction`, `retest_id`, `retest_result`, `change_control`, `capa_ref`, `approved_by`, `closed_utc`,
  `status`, then `customer_scope` (DL-R08).
- **DL-R02** `dev_id` shall be `DEV-<release>-nnn`; the generator reads the rows of the release it builds by that
  prefix.
- **DL-R03** `status` shall be one of open, corrected, retested, closed.
- **DL-R04** A row with status closed shall have a retest result and an approver; the generator lists every row that
  does not (scenario B6-57).
- **DL-R05** While a critical deviation of the release is not closed, the generator shall produce no release approval
  record and shall list the deviation (scenario B6-58).
- **DL-R06** Every change to a row (a status change or a correction) shall be its own commit whose message names
  the row, so git history keeps every earlier version of it; a row is never deleted.
- **DL-R07** `found_in` shall be one of IQ, OQ, PQ, automated suite, production (MDX-VAL-001 Annex C); a finding
  made while preparing a protocol is recorded under that protocol. The generator lists any other value.
- **DL-R08** `customer_scope` shall be `all` for a deviation that concerns every customer (MDARIX-wide), or the one
  customer code (`CUS-nnn`) it concerns (owner decision O36). The generator lists any other value, and the monthly
  health report (MDX-OPS-002) shows a customer only the deviations scoped `all` or to its own code.

## 3. Change-impact assessment (template, one per release)

Kept in the release folder as `change-impact.md`; its ID is quoted in the release approval record.

| Field | Content |
|---|---|
| Release and commit range | From the last approved release to this one |
| Changes | Each merged change, with its spec or fix reference |
| Functions touched | From the per-function table of MDX-VAL-002 |
| Risk of each change (VMP-R23) | Per change: can it alter a class-A function's records, decisions, clocks, signatures, reports or data model? Yes: class A. No: its own class, with the reason (for example "label wording only"). The quality approver checks each reason |
| Risk rows affected | RSK IDs, with any re-rating |
| Requirements affected | REQ IDs from `requirements.csv` (new, changed, unchanged) |
| Scenarios to re-run | Every class-A scenario of each function a class-A change can alter (MDX-VAL-001 section 9.3, VMP-R23, VMP-R28); for the first pack, every class-A scenario (VMP-R42) |
| Re-test rule applied | The row of MDX-VAL-001 section 9.3 |
| Customer impact | Whether a change notice is needed, and its date |
| Prepared by / reviewed by | System owner / quality approver, with dates (UTC) |

## Signatures

Unsigned. The signed PDF and its `signatures.csv` row are added after review (MDX-VAL-000 section 2.6).

| Role | Name | Meaning of signature | Signature | Date |
|---|---|---|---|---|
| Author (R), system owner | Sriharsha Telikicherla, Product & Engineering | I am responsible for this document and reviewed every line of the draft. | | |
| Reviewer (C) | Independent CSV consultant | I reviewed this document; my comments are recorded. | | |
| Approver (A), quality approver | Srinivas Telikicherla, QA/RA | I approve this document for use. | | |
