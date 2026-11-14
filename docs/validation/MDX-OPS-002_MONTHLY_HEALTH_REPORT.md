# MDX-OPS-002 Monthly service health report

| Field | Value |
|---|---|
| Document ID | MDX-OPS-002 |
| Title | Monthly service health report: content, sources and review |
| Version | 0.1 |
| Status | DRAFT |
| Author (R) | Sriharsha Telikicherla, Product & Engineering, system owner (generates the report) |
| Reviewer | Independent CSV consultant (first pack; not engaged yet) |
| Approver (A) | Srinivas Telikicherla, QA/RA, quality approver (reviews each report before it is sent) |
| Drafting | Drafted with software assistance; every line to be reviewed by Sriharsha Telikicherla (MDX-VAL-000, DC-R43) |
| Date | 14 Nov 2026 |
| Code baseline | Branch `feat/b6b-part-d` from `6b01eda5`; `scripts/health_report.py`; tests `tests/test_health_report.py` |

Change history

| Version | Date | Change | By |
|---|---|---|---|
| 0.1 | 14 Nov 2026 | First draft (B6b Part D, item D3) | Sriharsha Telikicherla |

## 1. Purpose and scope

Each customer organisation receives one report a month on the MDARIX service: availability, incidents, releases,
deviations, backups, recovery, time and the audit trail. This document says what the report holds, where each line
comes from and who checks it. The report is first needed one month after the first customer goes live.

## 2. Rules

- HR-01: The report shall be generated with `python scripts/health_report.py --customer CUS-nnn --month YYYY-MM
  --date <generation day>` from the registers of MDX-OPS-003 and `docs/validation/deviation-log.csv`, at the
  commit tagged for that month.
- HR-02: The report shall read no production data (owner decision B6b-D11, "if no answer" default; the owner has not
  approved a read-only production query list). Uptime shall come from the incident register.
- HR-03: The report shall hold no other organisation's data. A register row shall be used only when its `customers`
  field is `ALL` or names the customer; the generator refuses the report when its text names another customer code
  (scenario B6-56; `tests/test_health_report.py::test_a_health_report_holds_no_other_organisations_data`,
  `::test_register_text_naming_another_customer_refuses_the_report`).
- HR-04: The quality approver shall review each report and sign its review line before it is sent.
- HR-05: The same registers and generation day shall give the same files
  (`tests/test_health_report.py::test_the_same_registers_and_date_give_the_same_files`).
- HR-06: A report that shows the uptime target not met shall be sent with the incident references and their
  customer notices.

## 3. Content and sources

| Line | Source | Note |
|---|---|---|
| Uptime against 99.5 % | Incident register, `minutes_down` of incidents with `ALL` or the customer's code, opened in the month | Shortcuts (`scripts/health_report.py`, `shortcut:` comments): an incident's minutes count in the month it opened; overlapping incidents add up, capped at the month's minutes. A missing register, a time without its zone or minutes that are not whole numbers refuse the report. The 99.5 % target is the owner-approved SLO of 3 Nov 2026 |
| Downtime minutes | Same | |
| Incidents | Incident register, rows open at any time in the month | Shown as reaching "all customers" or "your organisation", never with other codes |
| Releases and change notices | Operations log, `RELEASE` rows in the month | The change notice reference is in `reference` |
| Open deviations | `deviation-log.csv`, rows not closed | Deviations are product-level and the log has no customer column: every open one is listed, with ID, classification, GxP risk and status only (to be narrowed to customer-affecting ones when the log records it) |
| Backups | Incident register, `BACKUP` rows; the fixed text on the daily backup and the 26-hour age alert | No backup log is read (HR-02) |
| Last restore drill, last recovery record, last clock check | Operations log, latest `RESTORE_DRILL`, `RECOVERY_RECORD`, `CLOCK_CHECK` row up to the month's end | |
| Audit trail chain | Fixed line: verified daily by the scheduler, result on request | B6b-D11 default; the scheduler's daily verification is `backend/app/audit_chain.py` (`verify_all`) |
| Planned changes | Operations log, `PLANNED_CHANGE` rows dated after the month | |

## 4. Output

`artifacts/health/health-<CUS-nnn>-<YYYY-MM>.json` and `.pdf` (the PDF from the product's PDF module, owner decision
B6b-D13). The files are not committed: they hold the customer code and are sent to the customer only.

## Signatures

Unsigned. The signed PDF and its `signatures.csv` row are added after review (MDX-VAL-000 section 2.6).

| Role | Name | Meaning of signature | Signature | Date |
|---|---|---|---|---|
| Author (R), system owner | Sriharsha Telikicherla, Product & Engineering | I am responsible for this document and reviewed every line of the draft. | | |
| Reviewer (C) | Independent CSV consultant | I reviewed this document; my comments are recorded. | | |
| Approver (A), quality approver | Srinivas Telikicherla, QA/RA | I approve this document for use. | | |
