# MDX-SOP-003 Incident response and complaints about MDARIX

| Field | Value |
|---|---|
| Document ID | MDX-SOP-003 |
| Title | Incident response and complaints about MDARIX |
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
| 0.1 | 14 Nov 2026 | First draft (B6b Part C, item C3). Wraps the incident runbook as a controlled procedure and adds complaints about MDARIX | Sriharsha Telikicherla |

## 1. Purpose and scope

This procedure covers anything that threatens the availability, integrity or confidentiality of MDARIX or of customer
data (an incident), and every complaint a customer makes about MDARIX itself (for example a wrong clock or a wrong
report field). It wraps the operational runbook `docs/runbooks/INCIDENT_RESPONSE.md`, which holds the commands; this
procedure sets the controlled steps, time limits and records.

It does not cover complaints about a customer's medical devices: those are the customer's records, handled in
MDARIX by the customer.

## 2. Roles

| Role | Who | Does |
|---|---|---|
| Incident lead | The first person on the incident, until handed over by name (`docs/runbooks/INCIDENT_RESPONSE.md:10-12`) | Runs the incident, keeps the record |
| Privacy contact | Named in `docs/handover/52_SUPPORT_AND_OWNERSHIP_HANDOVER.md:13` (to fill before the first pilot) | Breach assessment; approves customer breach notices |
| Quality approver | Srinivas Telikicherla | Assesses the effect of a defect on customers' regulatory obligations; closes the incident review |
| System owner | Sriharsha Telikicherla | Contains, fixes, recovers |

## 3. Incidents

### 3.1 Record

- **IR-R01** Each incident shall get a record with a reference `INC-YYYY-NNN` when it is first noticed
  (`docs/runbooks/INCIDENT_RESPONSE.md:10-12`).
- **IR-R02** Each action on an incident shall be written in its record with the time in UTC.
- **IR-R03** Each incident shall be entered in the incident register (`docs/validation/registers/`, set up by B6b
  Part D), with customers named by code.

### 3.2 Triage

- **IR-R04** Each incident shall be given a severity SEV1, SEV2 or SEV3 as defined in
  `docs/runbooks/INCIDENT_RESPONSE.md:25-35`; when unsure, the higher one.
- **IR-R05** A person shall acknowledge and start work within the response target of
  `docs/handover/52_SUPPORT_AND_OWNERSHIP_HANDOVER.md:28-38` (for example 1 hour for an audit-trail integrity failure
  or the site down).

### 3.3 Contain, notify, recover

- **IR-R06** The incident lead shall contain the incident as `docs/runbooks/INCIDENT_RESPONSE.md` section 3 describes.
- **IR-R07** Each customer whose personal data may have been accessed, changed, lost or disclosed without
  authorisation shall be notified without undue delay and no later than 72 hours after MDARIX becomes aware; a shorter
  contractual deadline wins (`docs/runbooks/INCIDENT_RESPONSE.md:72-76`).
- **IR-R08** Notifications to the authority for personal data MDARIX controls (DPDP Rules 2025) shall follow
  `docs/runbooks/INCIDENT_RESPONSE.md` section 4.2.
- **IR-R09** Once the operating company is registered, a reportable cyber incident shall be reported to CERT-In within
  6 hours of noticing (`docs/runbooks/INCIDENT_RESPONSE.md:126-139`).
- **IR-R10** Each customer affected by a SEV1 or SEV2 outage shall get a status update at the start, at least every
  4 hours while it lasts, and at recovery.
- **IR-R11** Recovery from a restore shall follow MDX-SOP-004.

### 3.4 Review

- **IR-R12** Each SEV1 and SEV2 shall have a blameless review within 5 business days of closing, added to its record
  (`docs/runbooks/INCIDENT_RESPONSE.md:158-165`).
- **IR-R13** An incident whose cause is a defect in MDARIX shall be logged as a deviation (MDX-VAL-010) or a CAPA in
  the MDARIX CAPA log (B6b Part D registers).

## 4. Complaints about MDARIX

- **IR-R14** Each complaint about MDARIX shall be entered in the register of complaints about MDARIX (B6b Part D,
  `docs/validation/registers/`) with date received, customer code, function and risk class.
- **IR-R15** The quality approver shall assess, within 1 working day of receipt, whether the complaint can affect a
  customer's report, deadline or record.
- **IR-R16** When a complaint can affect a customer's report or deadline, that customer shall be told the same
  working day the assessment finds it, with what is known.
- **IR-R17** A defect in a class-A function (MDX-VAL-002 section 4) shall be handled as an incident of at least SEV2.
- **IR-R18** Each complaint shall be closed only with its root cause, the fix or the reason none is needed, and the
  release that carries the fix.

## 5. Trend review

- **IR-R19** Every 3 months, the quality approver shall review the incident register, the complaints register and
  the deviation log for repeated causes, and open a CAPA for any systemic cause.

## 6. Records

Incident records (`INC-YYYY-NNN`); the incident register; the register of complaints about MDARIX; the MDARIX CAPA
log; the deviation log; review notes. Kept for at least as long as the validation records (owner decision O1).

## Signatures

Unsigned. The signed PDF and its `signatures.csv` row are added after review (MDX-VAL-000 section 2.6).

| Role | Name | Meaning of signature | Signature | Date |
|---|---|---|---|---|
| Author (R), system owner | Sriharsha Telikicherla, Product & Engineering | I am responsible for this document and reviewed every line of the draft. | | |
| Reviewer (C) | Independent CSV consultant | I reviewed this document; my comments are recorded. | | |
| Approver (A), quality approver | Srinivas Telikicherla, QA/RA | I approve this procedure for use. | | |
