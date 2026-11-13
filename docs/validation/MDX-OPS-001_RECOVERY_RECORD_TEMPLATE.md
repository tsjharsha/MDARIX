# MDX-OPS-001 Recovery record (template)

| Field | Value |
|---|---|
| Document ID | MDX-OPS-001 (template); each executed record is MDX-OPS-001-&lt;YYYYMMDD&gt; |
| Title | Recovery record: restore drill or recovery of production |
| Version | 0.1 |
| Status | DRAFT (template; no record executed yet) |
| Author (R) | Sriharsha Telikicherla, Product & Engineering, system owner (executes the recovery and fills the record) |
| Reviewer | Independent CSV consultant (first pack; not engaged yet) |
| Approver (A) | Srinivas Telikicherla, QA/RA, quality approver (signs each executed record) |
| Drafting | Drafted with software assistance; every line to be reviewed by Sriharsha Telikicherla (MDX-VAL-000, DC-R43) |
| Date | 14 Nov 2026 |
| Code baseline | Branch `feat/b6b-part-d` from `6b01eda5`; `scripts/recovery_check.py`; runbook `docs/runbooks/BACKUP_AND_RESTORE.md` sections 2 to 5 |

Change history

| Version | Date | Change | By |
|---|---|---|---|
| 0.1 | 14 Nov 2026 | First draft (B6b Part D, D5 template). The first executed record waits for the next quarterly drill on a production backup copy, with the owner | Sriharsha Telikicherla |

## 1. Purpose and scope

This record shows that a backup was restored and checked before the restored system was used: at every quarterly
restore drill (runbook section 2) and at every recovery of production (runbook section 3). It is the evidence for
REQ-BAK-001, REQ-BAK-003 and REQ-BAK-004 in a release pack, and the source of each customer's recovery summary.

## 2. Rules

- RR-01: The system owner shall execute the recovery and fill this record; the quality approver shall review and
  sign it. Nobody signs a record of their own execution as approver.
- RR-02: The recovery check (`scripts/recovery_check.py`) shall run on the restored database with the `background`
  service stopped, before anyone signs in. Its JSON and PDF shall be attached.
- RR-03: A FAIL in the recovery check shall stop the recovery; the record states the failure and the deviation
  raised (MDX-VAL-010).
- RR-04: Every FLAG shall have a written explanation in section 4 before the system opens.
- RR-05: A held notification shall be replayed only when the mail provider's log shows it as not sent; each replay
  shall be listed in section 5 with its log reference.
- RR-06: The GxP workflow check shall run on a scratch copy of the same backup, never as test data in production
  (owner decision B6b-D15).
- RR-07: A drill with a missing or wrong backup key shall be recorded as FAIL with a deviation, never as a pass
  (scenario PL-29).
- RR-08: The executed record shall be listed in the operations log (`RESTORE_DRILL` or `RECOVERY_RECORD` row,
  MDX-OPS-003) and, for a drill, in the runbook's Drill record.

## 3. Execution

| Item | Entry |
|---|---|
| Record ID | MDX-OPS-001-________ |
| Kind | Quarterly drill / recovery of production (strike one) |
| Backup used (folder, UTC) | |
| Where it came from | Off-site bucket / VM folder / provider snapshot |
| Restored into (database, server) | |
| Release (tag) and its backup image | |
| Key holder present, key mounted read-only | yes / no |
| Started (UTC) / finished (UTC) / duration | |
| Within the 4-hour RTO | yes / no |
| Backup age at restore (hours), within the 24-hour RPO stated today (B6b-D8) | |
| Grants and system token (runbook section 2, step 3) | done / not done |
| `background` service stopped throughout | yes / no |

## 4. Recovery check

Command: `python scripts/recovery_check.py --database ________ --backup-dir ________ --erasure-log ________`
Attach `recovery-check-<UTC>.json` and `.pdf`. Result (PASS / PASS WITH FLAGS / FAIL): ________

| Step | State | Explanation of every FLAG; deviation ID of every FAIL |
|---|---|---|
| manifest | | |
| worker_stopped | | |
| schema_head | | |
| row_level_security | | |
| row_counts | | |
| audit_chain (every organisation) | | |
| configuration (against the latest signed snapshot) | | |
| outbox_hold (events held: ____) | | |
| clock | | |
| erasures (pending: ____; re-applied with runbook section 4: yes / no) | | |

## 5. Held notifications replayed

| Event ID | Organisation code | Mail provider log reference | Not sent: replayed (UTC) | By |
|---|---|---|---|---|
| | | | | |

## 6. Sign-in and GxP workflow

| Check | Result | By |
|---|---|---|
| Sign-in with MFA: Platform Administrator | | |
| Sign-in with MFA: customer administrator | | |
| Sign-in with MFA: reviewer | | |
| Sign-in with MFA: regulatory reviewer | | |
| On the scratch copy `________`: create a complaint, assess one market, sign it | | |
| Restored files archive extracts (when files are stored locally) | | |
| Counts reconciled with the source, or each difference explained in section 4 | | |

## 7. Customer summaries

One summary PDF per organisation from the recovery check (that organisation's lines only: recovery window, its
checks, its held notifications). Sent to: ________ (codes) on ________ (UTC). For a drill on a backup copy no summary
is sent.

## 8. Result and signatures

Overall result (PASS / FAIL): ________. Deviations raised: ________.

| Role | Name | Meaning of signature | Signature | Date |
|---|---|---|---|---|
| Executed by (R), system owner | Sriharsha T. | I executed this recovery as recorded and attached the recovery check. | | |
| Approved by (A), quality approver | Srinivas T. | I reviewed this record, its explanations and its attachments, and approve the result. | | |

## Template signatures

Unsigned. The signed PDF of this template and its `signatures.csv` row are added after review (MDX-VAL-000
section 2.6).

| Role | Name | Meaning of signature | Signature | Date |
|---|---|---|---|---|
| Author (R), system owner | Sriharsha Telikicherla, Product & Engineering | I am responsible for this template and reviewed every line of the draft. | | |
| Reviewer (C) | Independent CSV consultant | I reviewed this template; my comments are recorded. | | |
| Approver (A), quality approver | Srinivas Telikicherla, QA/RA | I approve this template for use. | | |
