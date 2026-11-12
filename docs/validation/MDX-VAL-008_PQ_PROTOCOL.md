# MDX-VAL-008 MDARIX performance qualification protocol

| Field | Value |
|---|---|
| Document ID | MDX-VAL-008 |
| Title | MDARIX performance qualification protocol |
| Version | 0.4 |
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
| 0.2 | 12 Nov 2026 | Signature block added after an independent rating; PQ-011 cites PL-18 | Srinivas Telikicherla |
| 0.3 | 12 Nov 2026 | After the second rating: PQ-001, PQ-005 and PQ-006 cite the scenarios their steps exercise (TR-28 serious injury, TR-12 several markets; B6-20 code, RG-01 rule reference; PL-43 snapshot values, B8-16 same snapshot); PQ-R06 organisation type | Srinivas Telikicherla |
| 0.4 | 12 Nov 2026 | After the third rating: PQ-R07 to PQ-R10 (real time zone and markets, two people with their own accounts, a negative step per persona, coverage of the intended use); PQ-012 to PQ-017 (late entry, not-a-complaint path, facts changed after signing, signature manifestation, lockout, audit chain); section 3.1 coverage table | Srinivas Telikicherla |

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
- **PQ-R06** The PQ shall run in an organisation of the pilot type, not a free trial, so that the second-person rules
  of steps PQ-002 and PQ-007 apply; the sample story is loaded into it as synthetic data.
- **PQ-R07** The organisation's time zone shall be America/New_York and its markets US and EU, so that clock and
  daylight-saving behaviour is exercised under real conditions; the date of execution is recorded per step.
- **PQ-R08** At least two people shall take part (a second person for the four-eyes steps); each persona signs in with
  its own account and authenticator, never a shared one.
- **PQ-R09** Each persona shall have at least one negative step (an action the system must refuse); a negative step
  passes only when the refusal is seen and audited.
- **PQ-R10** The steps shall cover every function of the intended use (MDX-B10-001 section 4.1); the table in section
  3.1 shows the coverage. A function without a step is a gap recorded in the VSR.

## 3. Steps (the sample story, one persona per step)

| Step | Persona | Action | Expected result | Scenarios |
|---|---|---|---|---|
| PQ-001 | Complaint handler | Log a complaint call that alleges a device fault with a serious injury | Case created; fast track; awareness from the call; deadlines shown for each market | IN-05, TR-28, TR-12 |
| PQ-002 | Complaint handler | Record an awareness date later than the earliest known | Refused without a signature and, outside a trial, a second person | TR-05, CI-08 |
| PQ-003 | Triage reviewer | Confirm triage; open the deadline list | One deadline per market; overdue first; the same deadline on every screen | TR-12, B6-03 |
| PQ-004 | Regulatory reviewer | Answer the market questions with one Unknown | "Not reportable" refused; "Needs more information" shown | DT-06, DT-08 |
| PQ-005 | Regulatory reviewer | Complete the answers and sign the US conclusion | The signer re-enters the current password and a fresh 6-digit authenticator code; the rule version is named | B6-20, B6-21, RG-01 |
| PQ-006 | Regulatory reviewer | Prepare the eMDR file and the EU MIR file | Values from the approved snapshot only; the file passes its schema check; the MIR XML is served only after approval | PL-43, B8-16, B8-15 |
| PQ-007 | Quality approver | Try to approve a record made by the same person (outside a trial) | Refused | CI-17 |
| PQ-008 | Investigator | Submit an investigation with an open challenge question | Refused until it is answered or marked not applicable | B5-05 |
| PQ-009 | Quality approver | Sign the audit-trail review for the period | Flags shown; own flagged actions need a second reviewer; the signed review does not change | B6-28, B6-29, B6-31 |
| PQ-010 | Administrator of another organisation | Open the product, supplier and report addresses of step PQ-006 | 404; nothing of the first organisation is shown | P360-11, S360-14, B8-30 |
| PQ-011 | Quality approver | Export the organisation's records | Export holds every record and the verified audit head, with a SHA-256 per entry | (REQ-EXP-001; PL-18) |
| PQ-012 | Complaint handler | Enter a complaint more than 24 hours after awareness, first without a reason | Refused without a late-entry reason; with it, saved and shown "Entered late" | B6-07 |
| PQ-013 | Complaint handler | Close a call that is not a complaint (service only) | Signed "Service only" with a reason; QA review before closing; closed with a resolution summary | RT-01 |
| PQ-014 | Regulatory reviewer | Change the awareness date of the signed US conclusion of PQ-005, with a reason | The signed conclusion is unchanged and reads "Facts changed after signing: re-check" | B6-37 |
| PQ-015 | Quality approver | Print the signed US conclusion of PQ-005 | The print shows the signer's printed name, the date and time and the meaning of the signature | PL-47 |
| PQ-016 | Regulatory reviewer | Enter a wrong authenticator code five times when signing | The account locks for 15 minutes; the lock is in the audit trail; nothing is signed | PL-51, PL-52 |
| PQ-017 | Quality approver | Run the audit-chain verification for the organisation after PQ-001 to PQ-016 | Verified; the head is recorded as an anchor | PL-09 |

### 3.1 Coverage of the intended use (MDX-B10-001 section 4.1)

| Function | Steps |
|---|---|
| Record and route complaints | PQ-001, PQ-002, PQ-003, PQ-012, PQ-013 |
| Reportability decision per market, with deadlines | PQ-003, PQ-004, PQ-005, PQ-014 |
| Authority report files prepared for the customer to submit | PQ-006 |
| Investigation | PQ-008 |
| Signatures, reviews and audit trail | PQ-005, PQ-007, PQ-009, PQ-015, PQ-016, PQ-017 |
| Separation of organisations; export at exit | PQ-010, PQ-011 |


## 4. Acceptance

The PQ passes when every step is PASS, or a step that is not PASS has a closed deviation with a retest PASS.
A BLOCKED or NOT RUN step is never a pass.

## 5. Record

Each execution is kept in the release folder `docs/validation/releases/<release>/` as `pq-record.csv` (step, result,
executor, date UTC, evidence ID, deviation ID) and is summarised in the VSR (MDX-VAL-011).

## Signatures

Unsigned. The signed PDF and its `signatures.csv` row are added after review (MDX-VAL-000 section 2.6).

| Role | Name | Meaning of signature | Signature | Date |
|---|---|---|---|---|
| Author (R), quality approver | Srinivas Telikicherla, QA/RA | I am responsible for this document and reviewed every line of the draft. | | |
| Reviewer (C) | Independent CSV consultant | I reviewed this document; my comments are recorded. | | |
| Approver (A), system owner (MDX-VAL-000 DC-R42) | Sriharsha Telikicherla, Product & Engineering | I approve this document for use. | | |
