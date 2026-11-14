# MDX-OPS-003 Operational registers

| Field | Value |
|---|---|
| Document ID | MDX-OPS-003 |
| Title | Operational registers: incidents, operations log, complaints about MDARIX, MDARIX CAPA log, customer audit findings |
| Version | 0.2 |
| Status | DRAFT |
| Author (R) | Srinivas Telikicherla, QA/RA, quality approver |
| Reviewer | Independent CSV consultant (first pack; not engaged yet) |
| Approver (A) | Sriharsha Telikicherla, Product & Engineering, system owner, as the second person (MDX-VAL-000, DC-R42) |
| Drafting | Drafted with software assistance; every line to be reviewed by Srinivas Telikicherla (MDX-VAL-000, DC-R43) |
| Date | 14 Nov 2026 |
| Code baseline | Branch `feat/b6b-part-d` from `6b01eda5`; registers in `docs/validation/registers/`; read by `scripts/health_report.py` and by the generator (`validation/pack.py` `read_registers`, branch `feat/b6b-validation-pack`, 14 Nov 2026) |

Change history

| Version | Date | Change | By |
|---|---|---|---|
| 0.1 | 14 Nov 2026 | First draft (B6b Part D, item D4, `docs/specs/B6b-validation-pack-spec.md:230`): the register of complaints about MDARIX and the MDARIX CAPA log that the spec lists as missing (blocker 6); entries start empty except the restore drills already recorded in the runbook | Srinivas Telikicherla |
| 0.2 | 14 Nov 2026 | Section 4: the generator reads the registers for defect leakage and the post-go-live figures (G13) | Srinivas Telikicherla |

## 1. Purpose and scope

These registers record what happens to the MDARIX service after release: incidents, operational events, complaints
customers make about MDARIX itself, MDARIX's own corrective and preventive actions, and findings from customer
audits of MDARIX. They are the source of the monthly health report (MDX-OPS-002), the post-go-live figures of the
validation summary report (G13) and the customer's periodic review.

They do not hold customers' regulated records. Customers' own complaints about their devices stay in each
customer's MDARIX organisation.

## 2. Rules

- OR-01: Each register shall be a CSV file in `docs/validation/registers/`, committed to the product repository, so
  every change shows in git history.
- OR-02: A customer shall be named only by its code `CUS-nnn`. The key from code to customer name shall be kept
  outside the repository.
- OR-03: Free text (summary, finding, problem) shall not name a customer, a person outside MDARIX or a customer's
  device. The health report refuses to run when its text names another customer code
  (`scripts/health_report.py`, test `tests/test_health_report.py::test_register_text_naming_another_customer_refuses_the_report`).
- OR-04: The `customers` field shall be `ALL` or one or more customer codes separated by spaces.
- OR-05: Times shall be UTC: `YYYY-MM-DD` for a day, `YYYY-MM-DDTHH:MM:SSZ` for a moment.
- OR-06: A row shall be added within 1 working day of the event. A row is corrected by a new commit; the earlier
  version stays in git.
- OR-07: Identifiers shall be numbered per year without gaps: `INC-YYYY-NNN`, `OPS-YYYY-NNN`, `MCP-YYYY-NNN`,
  `MCAPA-YYYY-NNN`, `CAF-YYYY-NNN`.
- OR-08: An incident that affects a validated function, or a complaint classed as a defect, shall also be raised as a
  deviation in `deviation-log.csv` (MDX-VAL-010), and its ID written in `deviation_id` or `linked_deviation`.
- OR-09: The quality approver shall review the registers monthly, before the health reports are sent.

## 3. The registers

### 3.1 Incidents: `incidents.csv`

| Column | Content |
|---|---|
| incident_id | `INC-YYYY-NNN` |
| opened_utc, closed_utc | When the incident started and ended (closed empty while open) |
| category | `OUTAGE`, `DEGRADED`, `BACKUP`, `SECURITY`, `DATA`, `OTHER` |
| severity | `S1` (all customers, no service) to `S4` (no customer effect) |
| customers | `ALL` or the customer codes reached |
| minutes_down | Minutes the service was unavailable to those customers; counts against the 99.5 % uptime target |
| summary, root_cause | What happened and why, without customer names (OR-03) |
| deviation_id, capa_id | Links (OR-08) |
| customer_notice | Reference of the notice sent to the customers reached |
| status | `OPEN` or `CLOSED` |

A failed or late backup is an incident of category `BACKUP` (alert from `scripts/check_backup_age.sh` or
`infrastructure/docker/backup/backup.sh`). A recovery from a backup is an incident too, with its recovery record
(MDX-OPS-001).

### 3.2 Operations log: `operations-log.csv`

| Column | Content |
|---|---|
| entry_id | `OPS-YYYY-NNN` |
| date_utc | The day |
| type | `RELEASE`, `RESTORE_DRILL`, `RECOVERY_RECORD`, `CLOCK_CHECK`, `PLANNED_CHANGE`, `KEY_ROTATION`, `OTHER` |
| customers | `ALL` or the customer codes concerned |
| summary | What was done |
| result | `PASS`, `FAIL` or `n/a` |
| reference | The record: release tag and change notice, drill record row, recovery record, clock-check JSON |
| by | Who did it |

A `PLANNED_CHANGE` row is dated on the planned day and shows in the health reports of the months before it.

The four rows present on 14 Nov 2026 are the restore drills recorded in `docs/runbooks/BACKUP_AND_RESTORE.md`,
section 2, "Drill record" (3 Oct, 5 Oct, 16 Oct and 3 Nov 2026). The runbook does not record who ran them; the `by`
column says so.

### 3.3 Complaints about MDARIX: `mdarix-complaints.csv`

| Column | Content |
|---|---|
| complaint_id | `MCP-YYYY-NNN` |
| received_utc, customer, channel | When, from which customer code, by which channel (support e-mail, call, audit) |
| summary | The complaint, without names (OR-03) |
| classification | `DEFECT`, `USABILITY`, `SERVICE`, `DOCUMENTATION`, `OTHER` |
| defect | `yes` when MDARIX did not do what its requirements say (feeds defect leakage in G13) |
| linked_incident, linked_capa, linked_deviation | Links |
| response_utc, status, closed_utc | First response, `OPEN` or `CLOSED`, and when |

### 3.4 MDARIX CAPA log: `capa-log.csv`

| Column | Content |
|---|---|
| capa_id | `MCAPA-YYYY-NNN` |
| opened_utc, source | When, and the incident, complaint, audit finding or deviation it comes from |
| problem, root_cause, action | The problem, its cause and the action |
| owner, due_utc | Who and by when |
| effectiveness_check, effective | How effectiveness is checked, and the result (`yes`, `no`, empty while pending) |
| status, closed_utc | `OPEN` or `CLOSED`, and when |

### 3.5 Customer audit findings: `customer-audit-findings.csv`

| Column | Content |
|---|---|
| finding_id | `CAF-YYYY-NNN` |
| audit_date_utc, customer, audit_type | When, which customer code, and the type (supplier audit, questionnaire, remote) |
| requirement, finding, classification | The requirement audited, the finding, and `MAJOR`, `MINOR` or `OBSERVATION` |
| response, capa_id, due_utc | MDARIX's response, the CAPA when one is needed, the agreed date |
| status, closed_utc | `OPEN` or `CLOSED`, and when |

## 4. Use

- Monthly health report: `python scripts/health_report.py --customer CUS-nnn --month YYYY-MM` (MDX-OPS-002).
- Validation summary report (G13): the generator (`scripts/validation_pack.py`, `validation/pack.py`) reads these
  registers. Defect leakage: the release's deviations found in `production` over all its deviations (`found_in`), with
  the complaints classed a defect linked to them; a defect complaint without a linked deviation (OR-08) is a check
  failure. Post-go-live effectiveness: incidents (open, minutes down, `DATA` incidents), complaints about MDARIX
  (open, defects), CAPAs (open, effective), customer audit findings by class, restore drills and recoveries (failed),
  from all rows at the commit. A missing register file is refused. Tests: `tests/test_validation_pack.py`.
- Periodic review (customer template MDX-CUS, Part E): the customer asks for the rows with `ALL` or its code.

## Signatures

Unsigned. The signed PDF and its `signatures.csv` row are added after review (MDX-VAL-000 section 2.6).

| Role | Name | Meaning of signature | Signature | Date |
|---|---|---|---|---|
| Author (R), quality approver | Srinivas Telikicherla, QA/RA | I am responsible for this document and reviewed every line of the draft. | | |
| Reviewer (C) | Independent CSV consultant | I reviewed this document; my comments are recorded. | | |
| Approver (A), system owner | Sriharsha Telikicherla, Product & Engineering | I approve this document for use. | | |
