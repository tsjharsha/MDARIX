# MDX-SOP-004 Backup, recovery and business continuity

| Field | Value |
|---|---|
| Document ID | MDX-SOP-004 |
| Title | Backup, recovery and business continuity |
| Version | 0.1 |
| Status | DRAFT |
| Author (R) | Sriharsha Telikicherla, Product & Engineering, system owner |
| Reviewer | Independent CSV consultant (not engaged yet; MDX-VAL-013 questions 11 and 22) |
| Approver (A) | Srinivas Telikicherla, QA/RA, quality approver |
| Drafting | Drafted with software assistance; every line reviewed by Sriharsha Telikicherla (MDX-VAL-000, DC-R43) |
| Date | 14 Nov 2026 |
| Code baseline | Product code at `6b01eda5` (tip of `feat/b6b-validation-pack`); B6b Part C changes no code; release in preparation 0.11.04 (`VERSION` file still 0.10.94) |

Change history

| Version | Date | Change | By |
|---|---|---|---|
| 0.1 | 14 Nov 2026 | First draft (B6b Part C, item C3). Wraps the backup and restore runbook and the recovery validation of B6b Part D | Sriharsha Telikicherla |

## 1. Purpose and scope

This procedure keeps customers' records recoverable and the service available. It covers the daily backup, the
quarterly restore drill, recovery of production after a loss, the recovery validation of the GxP process after a
restore (G17), and what happens when MDARIX is unavailable or stops. It wraps the operational runbook
`docs/runbooks/BACKUP_AND_RESTORE.md`, which holds the commands.

## 2. Targets (owner decision B6b-D8)

- **BC-R01** Customers shall be told the recovery point in these words: "24 hours today (daily encrypted backup, no
  point-in-time recovery); target 15 minutes with point-in-time recovery on pilot hosting"
  (`docs/runbooks/BACKUP_AND_RESTORE.md:3-5`).
- **BC-R02** The recovery time objective shall be 4 hours (`docs/runbooks/BACKUP_AND_RESTORE.md:5`).
- **BC-R03** The availability target stated to customers shall be 99.5% a month (`MDX-B10-001-Intended-Use-Statement.md:100`).

## 3. Backup

- **BC-R04** An encrypted logical backup of every database, and of the stored files while they are kept on the
  server, shall run daily and be copied off-site (`docs/runbooks/BACKUP_AND_RESTORE.md:15,72-76`).
- **BC-R05** The backup's private key shall be kept offline, never on the server (`docs/runbooks/BACKUP_AND_RESTORE.md:41-46`).
- **BC-R06** A failed backup, a backup that did not run, and an off-site copy older than 26 hours shall each raise an
  alert (`docs/runbooks/BACKUP_AND_RESTORE.md:78-81`).
- **BC-R07** A backup alert shall be handled as a SEV2 incident (MDX-SOP-003;
  `docs/handover/52_SUPPORT_AND_OWNERSHIP_HANDOVER.md:37`).

**Known gap on today's production.** The off-site copy is made by a host cron job, and nothing alerts when that copy
fails (`docs/runbooks/GCP_DEPLOYMENT.md:170-171`). Until a check is added, BC-R06 is not met for the off-site copy.

- **BC-R07a** Until that check exists, the system owner shall check the off-site copy log and the bucket listing
  every working day and record a missing copy in the operations log.

## 4. Restore drill

- **BC-R08** A restore drill shall run every 3 months, and before the first design partner, as
  `docs/runbooks/BACKUP_AND_RESTORE.md` section 2 describes.
- **BC-R09** Each drill shall be recorded with its date, backup timestamp, duration and results
  (`docs/runbooks/BACKUP_AND_RESTORE.md:116,121-128`).
- **BC-R10** A drill whose duration exceeds the recovery time objective, or whose backup is older than the recovery
  point, shall be logged as a deviation (MDX-VAL-010).

## 5. Recovering production

- **BC-R11** Production shall be recovered as `docs/runbooks/BACKUP_AND_RESTORE.md` section 3 describes for the
  situation.
- **BC-R12** After any restore, erasures and purges made after the backup shall be re-applied before anyone signs in
  (`docs/runbooks/BACKUP_AND_RESTORE.md:146-148`).
- **BC-R13** After any restore, every outbox event not delivered at the backup time and older than the restore point
  shall be held (dead-lettered, audited), and only those the mail provider's log shows as not sent shall be replayed
  (owner decision B6b-D10). The automated control is the recovery check of B6b Part D; until it exists, a person
  keeps the background worker stopped and checks the outbox by hand.
- **BC-R14** After any restore, the audit chain of every organisation shall be verified before the service is
  announced as recovered (owner decision O25, RSK-037; `backend/app/audit_chain.py:26,54`).
- **BC-R15** The GxP workflow check of a recovery shall run on a scratch copy of the same backup, never as test data
  in production (owner decision B6b-D15).
- **BC-R16** Each recovery shall end in a recovery record (MDX-OPS-001, B6b Part D), executed by the system owner and
  signed by the quality approver, with a summary page for each affected customer.
- **BC-R17** Each affected customer shall be told its recovery window (backup time to recovery), so that it can
  back-enter records made in that window under its outage procedure.

## 6. Business continuity

- **BC-R18** While MDARIX is unavailable, customers shall follow their own outage procedure (G18) to meet legal
  deadlines; MDARIX shall tell them when the outage starts and ends (MDX-SOP-003, IR-R10).
- **BC-R19** The hosting account's billing status and end date shall be checked every month; a trial or credit end
  within 60 days shall be raised to the owner (MDX-SUP-004 section 4).
- **BC-R20** If MDARIX stops the service, each customer shall get its full organisation export with a manifest before
  any purge (`backend/app/tenant_export.py:1-14`; `backend/app/tenant_purge.py:550-557`).
- **BC-R21** The production settings files and encryption keys shall be kept in a password manager as well, so that a
  backup can be restored on a new server (`docs/runbooks/BACKUP_AND_RESTORE.md:82-84`).

## 7. Records

Backup logs and alerts; restore drill records; recovery records (MDX-OPS-001); operations log; deviations.

## Signatures

Unsigned. The signed PDF and its `signatures.csv` row are added after review (MDX-VAL-000 section 2.6).

| Role | Name | Meaning of signature | Signature | Date |
|---|---|---|---|---|
| Author (R), system owner | Sriharsha Telikicherla, Product & Engineering | I am responsible for this document and reviewed every line of the draft. | | |
| Reviewer (C) | Independent CSV consultant | I reviewed this document; my comments are recorded. | | |
| Approver (A), quality approver | Srinivas Telikicherla, QA/RA | I approve this procedure for use. | | |
