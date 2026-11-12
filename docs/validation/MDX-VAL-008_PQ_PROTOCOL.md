# MDX-VAL-008 MDARIX performance qualification protocol

| Field | Value |
|---|---|
| Document ID | MDX-VAL-008 |
| Title | MDARIX performance qualification protocol |
| Version | 0.1 |
| Status | DRAFT |
| Author (R) | Srinivas Telikicherla, QA/RA, quality approver (executes as the business user) |
| Reviewer | Independent CSV consultant (first pack; not engaged yet) |
| Approver (A) | Sriharsha Telikicherla, Product & Engineering, system owner (MDX-VAL-001 section 6.3: PQ row) |
| Drafting | Drafted with software assistance; every line reviewed by Srinivas Telikicherla (MDX-VAL-000, DC-R43) |
| Date | 12 Nov 2026 |
| Code baseline | Branch `feat/b6b-validation-pack`; the release under test is named in the PQ record of each pack |

Change history

| Version | Date | Change | By |
|---|---|---|---|
| 0.1 | 12 Nov 2026 | First draft (B6b Part B, item B9) | Srinivas Telikicherla |

## 1. Purpose and scope

This protocol shows that MDARIX supports MDARIX's intended use (MDX-B10-001) end to end, in the hands of a business
user, on the sample story. It is MDARIX's own PQ. It is not a customer's PQ: each customer runs its own with the
customer template MDX-CUS-001.

## 2. Rules

- **PQ-R01** The PQ shall be executed by the quality approver acting as the business user, never by the person who
  wrote the code under test.
- **PQ-R02** The PQ shall run on the controlled local environment or staging (MDX-VAL-001 section 10), on the sample
  story, never on customer data.
- **PQ-R03** Each step shall be recorded with its result (PASS / FAIL / BLOCKED / NOT RUN), the executor, the date (UTC)
  and an evidence ID (screenshot or export with its SHA-256).
- **PQ-R04** A step with a result other than PASS shall be logged in the deviation log before any fix (MDX-VAL-010).
- **PQ-R05** The expected results below shall be approved by the system owner before the first execution.

## 3. Steps (the sample story, one persona per step)

| Step | Persona | Action | Expected result | Scenarios |
|---|---|---|---|---|
| PQ-001 | Complaint handler | Log a complaint call that alleges a device fault with a serious injury | Case created; fast track; awareness from the call; deadlines shown for each market | IN-05, TR-27, RG-10 |
| PQ-002 | Complaint handler | Record an awareness date later than the earliest known | Refused without a signature and, outside a trial, a second person | TR-05, CI-08 |
| PQ-003 | Triage reviewer | Confirm triage; open the deadline list | One deadline per market; overdue first; the same deadline on every screen | TR-12, B6-03 |
| PQ-004 | Regulatory reviewer | Answer the market questions with one Unknown | "Not reportable" refused; "Needs more information" shown | DT-06, DT-08 |
| PQ-005 | Regulatory reviewer | Complete the answers and sign the US conclusion | Signature asks for the password session and a fresh authenticator code; the rule version is named | B6-21, RG-12 |
| PQ-006 | Regulatory reviewer | Prepare the eMDR file and the EU MIR file | Values from the approved snapshot only; the file passes its schema check; the MIR XML is served only after approval | RG-19, B8-15 |
| PQ-007 | Quality approver | Try to approve a record made by the same person (outside a trial) | Refused | CI-17 |
| PQ-008 | Investigator | Submit an investigation with an open challenge question | Refused until it is answered or marked not applicable | B5-05 |
| PQ-009 | Quality approver | Sign the audit-trail review for the period | Flags shown; own flagged actions need a second reviewer; the signed review does not change | B6-28, B6-29, B6-31 |
| PQ-010 | Administrator of another organisation | Open the product, supplier and report addresses of step PQ-006 | 404; nothing of the first organisation is shown | P360-11, S360-14, B8-30 |
| PQ-011 | Quality approver | Export the organisation's records | Export holds every record and the verified audit head, with a SHA-256 per entry | (REQ-EXP-001; scenario to add) |

## 4. Acceptance

The PQ passes when every step is PASS, or a step that is not PASS has a closed deviation with a retest PASS.
A BLOCKED or NOT RUN step is never a pass.

## 5. Record

Each execution is kept in the release folder `docs/validation/releases/<release>/` as `pq-record.csv` (step, result,
executor, date UTC, evidence ID, deviation ID) and is summarised in the VSR (MDX-VAL-011).
