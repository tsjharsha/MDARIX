# B7 design spec: the routine complaint path, Case import and export, e-mail intake, the urgent alert

Version 1, 10 Nov 2026. **APPROVED by the owner on 10 Nov 2026 (see "Approval record").** Nothing here is built.

- **Plan:** B7 starts after the 27 Nov build cut-off, on its own branch, from the big-bang line (B2, W1, audit fixes, ID-2, hardening 0.10.95, B3). Building may go on during the 4–12 Dec freeze. B7 ships in the first release after the freeze; its number is given at build time.
- **Why now:** a reviewer said the product is "far too complex for day-to-day use; most issues won't go into investigation". Without a short daily path, users will not adopt MDARIX. The master sequence (10 Nov) moved B7 to the first item after B3.
- **Sources:** `development-cycle-1.md` (B7 row, step 4, Addenda A–K), `reviewer-feedback-log.md` (themes D1, D2), `b2-case-design/` (spec, final plan, gap matrix A–R), `call-intake-deep-dive/gap-report.md` (sections 5.1, 5.2, 6; D3, D4, D6, D13), `triage-deep-dive/gap-report.md` (section 7), `operating-modes.md`, `master-sequence-proposal.md`, `scenario-register.md`.
- **Code read:** worktree `trial-093` (branch `feat/hardening-0.10.95`, which holds B2). Read only; nothing was run. Paths start at `backend/app/` unless shown otherwise.
- **Not re-specified:** everything B2 built. That covers Cases, the Case check, escalation, two-speed triage, the one-click routine triage, the Service Desk role, the QMS import with triage columns, the imported backlog, bulk assign, addenda, fact correction, ID-1/ID-2 and the S-1–S-3 service fields. B7 builds on them.

---

## 0. B7 in one page

1. **The routine path becomes two signatures and one click.** Here is the path for a complaint that needs no investigation:
   - log the Case;
   - sign and escalate the Case check (exists);
   - confirm triage in one click (exists);
   - then one new screen, **"Resolve and close"**, pre-filled from the Case.
   One signature on that screen records the resolution, the problem code, the cause, the "customer told" entry and the routine "not reportable" conclusions. The same signature marks the complaint ready to close. In MDARIX Complete it also closes the complaint.
   Today the same work takes **three signatures**, an empty form and a separate "name yourself owner" step. Today nothing checks that the customer was told, and MDARIX never closes a complaint.
2. **The combinations matrix** (section 2) has **30 rows × 2 modes = 60 combinations**. Each row gives the path, who acts, what closes it and what must never happen. 17 rows exist today, 9 are partly built and 4 are new.
3. **Case import and export:** a "Cases" template for call-centre and CRM call logs, using the existing import engine. Exports are CSV, masked by default under OD-1, with an "export for QMS entry" for MDARIX Connect.
4. **E-mail intake, free to run:** each organisation gets its own address on an MDARIX subdomain. A small mail receiver of our own feeds an **"E-mail to check"** list. A person turns a message into a Case; **an e-mail is never a complaint by itself**. Every attachment is virus-scanned. There is no paid mail service.
5. **The urgent alert:** an opt-in e-mail saying only "an urgent case arrived, open MDARIX". It goes out at once, through the existing mail queue, with delivery tracked. SMS is left out because it is not free.
6. **Size:** about **106 hours** in 15 steps. **One migration, `tr25`.** It can ship in two parts: **B7a** (routine path, closure, import and export, alert; about 78 h) and **B7b** (e-mail intake; about 28 h).

---

## 1. The routine path, end to end

### 1.1 A reviewer's seven steps, mapped

| # | The reviewer's step | Where it happens in MDARIX | Today (code) | B7 |
|---|---|---|---|---|
| 1 | Description of the issue | **Log a case**: the reporter's words, channel, received time, product | Exists (B2: `intake/router.py:873` `log_intake`) | E-mail and import also create Cases (sections 3, 4) |
| 2 | Troubleshooting steps | Case: **"What was tried on the call"** | Exists (B2; `FirstContact.tsx:416`) | Pre-fills step 5 |
| 3 | Description of the problem | Case check (signed, escalates) + **problem code** | Case check exists. **No problem code on Case-made complaints**: escalation copies none (`intake/service.py:1642-1672`) | Problem code asked on "Resolve and close" (section 1.2) |
| 4 | Safety analysis | **Triage** (safety half) + **reportability** (regulatory half, routine basis or per-market tree) | Exists: routine triage is one click (B2). The routine basis exists (`complaint_disposition/rules.py:84-89`, `router.py:442-455`) | Unchanged; the routine basis is signed inside "Resolve and close" |
| 5 | Resolution and communication to the customer | Service-level record (troubleshooting, correction, result, ticket) + **customer told** | Service-level record exists but opens **empty** (`frontend/.../disposition.ts:168,188`). Service ticket is **always required** (`rules.py:160`). **No "customer told" check** | Pre-filled; ticket only when service work was done; customer told required |
| 6 | Issue data | Problem code, cause (attribution), where used, who used | Attribution and classification exist on the disposition | Pre-filled from the Case; the problem code added |
| 7 | Closure | **Ready to close** (signed). In Complete, **Closed** | Separate signature; the event owner must be named first (`oversight/router.py:1428`). **MDARIX never closes** (`oversight/closure.py:47`) | The same signature as step 5. In Complete it closes the complaint (OD-6 of B2, deferred to B7) |

### 1.2 The new screen: "Resolve and close"

This is the complaint's next step after triage. It is also the target of "Close on the routine path" on Complaints › Dispositions. One screen, in this order:

1. **What happened** (read only): the words, the product · version · lot, and the triage result.
2. **Problem:**
   - **Problem code** (required). The picker shows the organisation's own codes with their IMDRF term (existing `CodePicker`, `ProblemCode.tsx`).
   - A problem description (optional, masked like the Case words).
3. **Troubleshooting and resolution:**
   - **Troubleshooting:** pre-filled from "What was tried on the call".
   - **Correction:** User instructed · Setting corrected · Part replaced · **No fault found** (new) · Other. The default comes from the Case's "What they asked for": Information or Nothing → User instructed; Repair or Parts → Part replaced; Calibration or Maintenance → Setting corrected.
   - **Correction text** and **Result:** short text the person types.
   - **Service ticket:** pre-filled from the Case or the complaint's Service card. **Required only for Part replaced and Setting corrected.**
   - **Device returned:** Evaluated · Not returned after the set attempts · Not needed.
4. **Why no investigation** (ISO 13485:2016 clause 8.2.2). A choice:
   - single event, use-related, resolved by instruction;
   - known behaviour described in the instructions for use;
   - single random failure, no trend;
   - no fault found after evaluation;
   - reporter withdrew, no deficiency confirmed;
   - other (text).
   Beside the choice, MDARIX shows the facts it checked: "Similar complaints on this product and problem code in the last 12 months: N" and "Escalation triggers met: none". Free text is required only for Other (B7-D2).
5. **Cause:** Device-related · Use-related · Environment-related · Undetermined (with a reason). This exists today.
6. **Classification:** where it was used and who used it, pre-filled from the Case. This exists today.
7. **Customer told** (new, required):
   - How: Phone · E-mail · Letter · Through the distributor · In person.
   - When (now by default), and a note or a QMS letter ID.
   - Or **"Not possible"** with a reason: anonymous, or unreachable after the set attempts.
   - It writes an entry in the existing communications log (direction Sent, purpose Response) to the reporter party. MDARIX itself sends nothing to the customer (`communications/rules.py:50`).
8. **Reportability:** one of two lines.
   - "Not reportable for US, EU, India … on the routine basis". This shows when the routine path is offered: off the reportability watch, every fact recorded, no trigger.
   - Or the per-market conclusions already signed, e.g. "US: not reportable (signed 11 Nov)".
9. **Sign:** password and authenticator code. The button reads **"Resolve and close"** (Complete) or **"Resolve and mark ready to close in your QMS"** (Connect).

**When the screen is offered in full.** "Resolve and close" is offered only when the complaint passes **every** closure check except the ones this screen settles: decision, customer told, and markets on the routine basis.

- Triage must be complete, and no task or information request may be open.
- When anything else is open, the screen offers **"Resolve"** (the disposition alone) and lists what still blocks closing.
- **Signing over an open item with a reason is never offered here.** That stays on the normal Ready to close step.

**Who signs.** The same people as the disposition today: triage, opening investigations, or quality review (`complaint_disposition/router.py:56`). Administrators never sign. If someone else is the event owner, the screen asks "Take over as owner from <name>?" (one tick, audited). Ready to close keeps its rule that the owner signs.

### 1.3 What is signed, what is audited

| Moment | Signature | Signed records written | Audit events |
|---|---|---|---|
| Log a case | none | — | `INTAKE_LOGGED` (exists) |
| Sign and escalate the Case check | password + code | `FIRST_CONTACT_CHECK` (exists) | `FIRST_CONTACT_SIGNED`, `CASE_ESCALATED`, `COMPLAINT_CREATED_FROM_CASE` (exist) |
| Confirm triage (routine) | none | — | `TRIAGE_ROUTINE_CONFIRMED` (exists) |
| **Resolve and close** | **one** password + code | **Two records, each with its own meaning**, both shown in the event decision record (B7-D1): (1) `COMPLAINT_DISPOSITION`, covering the service-level branch, the routine market conclusions and the classification, as today; (2) `EVENT_READY_TO_CLOSE` | `COMPLAINT_DISPOSITION_SIGNED` (exists); the routine market conclusions (exist); the communications-log entry (exists); new `PROBLEM_CODE_SET` (old → new), `EVENT_OWNER_TAKEN_OVER`, `EVENT_READY_TO_CLOSE_SIGNED` (exists), and in Complete new **`COMPLAINT_CLOSED`** |
| Reopen (Complete) | none: reopening is the safe direction | — | new `COMPLAINT_REOPENED` (reason, trigger); the closure signature is superseded |

The disposition rules move to version `disposition-starter-2`: ticket rule, No fault found, the reasons list, the known-behaviour answer. In a trial, each signer acknowledges the new version once (existing practice training, T-G40P).

**The Decision Framework (Addendum C) on this screen:**
- **Evidence:** the words, triage, service record and attachments.
- **Intelligence:** the similar-complaint count and the triggers checked.
- **Rules:** the disposition rules version, the routine basis and the coding criteria.
- **Human judgement:** the signer and the signature's meaning.
- **Traceability:** the event decision record lists all of it.

### 1.4 Clicks for a routine complaint, from a signed Case

Counted from the design, not timed.

| | Today (B2 code) | B7 |
|---|---|---|
| Triage | 2 clicks (Next: Triage, Confirm triage) | 2 clicks (no change) |
| Resolution, reportability, issue data | Complaints › Dispositions, open the item; **7 empty fields typed**, 3 pickers, password and code (signature 2) | 1 click (Next: Resolve and close); pre-filled; **1 typed field** (result) + correction text; 4 picks (problem code, reason, cause, customer told) |
| Closure | Name yourself owner (2 clicks), Ready to close (1), password and code (signature 3) | **Same signature** |
| **Total** | **3 signatures, about 20 clicks, 7 typed fields** | **2 signatures, about 10 clicks, 2 typed fields** |

The existing routine target (under 10 minutes hands-on, `rules.py:85`) stays. B7 aims for under 3 minutes from triage to closed.

### 1.5 Routine path vs investigation path

| | Routine path | Investigation path |
|---|---|---|
| When | No escalation trigger. Off the reportability watch, or every relevant market signed not reportable | Any trigger: death, serious injury, reportable outcome, recurrence, new failure mode. Or a known issue, or escalation by choice |
| Disposition branch | Resolved at service level | Escalated (trigger or choice), or Known issue |
| Work | Resolve and close: one screen | Investigation (hypotheses, evidence, decision brief), decision signed with reviewer ≠ author, CAPA in the QMS if systemic |
| Reports | None (routine basis), or markets already signed not reportable | Per market (US eMDR in B3; EU/GB in B8; others in B9) |
| Closure | The Resolve and close signature | Ready to close after the investigation's decision; an open CAPA is listed and does not block (`closure.py:562-573`) |
| Switching | "Escalate by choice" is always open on the screen | No way back down. A new version of the disposition needs a reason |

### 1.6 Service work, complaint and CAPA: three different things

| | Service work (discrete) | Complaint | CAPA (systemic) |
|---|---|---|---|
| What it fixes | **This** device for **this** customer: instruct, adjust, repair, replace a part | Nothing by itself: it is the quality record of the allegation | The **product or process**, for every unit |
| Where it lives | Service card (ticket, owner, status), plus the correction on the service-level record | The complaint: triage, markets, disposition, customer told, closure | Raised from an investigation. In the QMS in both modes until the native CAPA (M5, after cycle 1); MDARIX holds the reference and the effectiveness check |
| What closes it | Service status Complete (Complete mode), or the service system (Connect) | The Resolve and close signature (Complete), or the QMS (Connect) | The QMS |
| Rules | **Service complete never closes or advances the complaint** (exists: `oversight/service_work.py:7`). One record: a service call alleging a deficiency **is** the complaint (B2). | **Never down-graded**: no fault found, withdrawal and a fix on the call all leave it a complaint | **Never opened by the routine path.** It never closes a complaint, and an open CAPA never blocks closure |

---

## 2. The combinations matrix

### 2.1 How to read it
- **Complaint:**
  - **N** = not a complaint (Service only, Inquiry, Not a complaint);
  - **?** = not sure (Pending);
  - **Y** = complaint.
- **Harm:**
  - **—** = neither harm nor malfunction;
  - **M−** = malfunction that could not cause serious harm if it recurred (Q6 No);
  - **M+** = malfunction that could (Q6 Yes or Unknown);
  - **H** = harm, minor (Q4 Yes, Q5 No);
  - **DSI** = death or serious injury;
  - **H?** = harm not known yet.
- **Service:** Y/N. **Rep(ortable):** Y/N, **P** = pending, **—** = no market to assess (off the watch).
- **Inv(estigation):** Y/N.
- **Roles:**
  - **SD** Service Desk;
  - **TL** Triage Lead (Complaint Handler);
  - **QR** Quality Reviewer;
  - **RR** Regulatory Reviewer;
  - **INV** Investigator;
  - **AP** Approver;
  - **owner** event owner.
- **Closes it:** what closes it in **Complete** · in **Connect**. Where only one is given, it is the same in both.
- **Today → B7:**
  - **Exists** (with evidence);
  - **Partly** (what B7 adds);
  - **New**.

### 2.2 What must never happen, on any row
1. **Service work never closes a complaint**, and completing it never advances one (`oversight/service_work.py:7`).
2. **An e-mail, an import or a bulk action never makes a complaint.** Only a person's signed Case check escalates. **Classifications are never signed in bulk** (B2, D12).
3. **A reportable complaint never takes the routine path.** The REPORTABLE trigger refuses it (`complaint_disposition/triggers.py`, `rules.py:180-181`).
4. **Death or serious injury never takes the routine path** (SAFETY and INJURY triggers).
5. **Unknown is never No.** The routine basis concludes only on recorded facts (`complaint_disposition/rules.py:106-118`). A complaint with a market pending never closes.
6. **A complaint is never down-graded or withdrawn.** No fault found, a fix on the call and a reporter's withdrawal all leave it a complaint.
7. **Awareness never moves later.** Imports and e-mails take the source's receipt time, never the time of the click.
8. **"Customer told" is never skipped silently:** a communications-log entry, or "Not possible" with a reason.
9. **MDARIX never closes a complaint the customer's QMS owns** (Connect). In Complete, it closes only by a signature.
10. **The routine path never opens or closes a CAPA.**

### 2.3 The matrix

| ID | Complaint | Harm | Service | Rep | Inv | Path | Who acts | Closes it | Must never happen | Today → B7 |
|---|---|---|---|---|---|---|---|---|---|---|
| RT-01 | N: Service only | — | Y | — | N | Case check signed "Service only" with a reason → QA review → Closed with a resolution summary | SD signs; QR reviews (a second person outside the trial) | QA review "Agree". Connect: the ticket closes in the service system | Closed without the QA review | **Exists** (B2: `intake/router.py:1554` review; S-2 resolution summary) |
| RT-02 | N: Inquiry | — | N | — | N | As RT-01 | SD, QR | QA review | As RT-01 | **Exists** (B2) |
| RT-03 | N: Not a complaint (no deficiency confirmed) | — | N | — | N | Follow-up answered "no deficiency" → sign → QA review | SD, QR | QA review | Reached by override | **Exists** (B2, D5) |
| RT-04 | N, then Y | any | any | any | any | A 30-day rescan or an addendum with a harm or fault word reopens it. QA "Reclassify as a complaint" escalates; the matching Y row follows | system; QR | As the matching Y row | Awareness moved to the reclassification date | **Exists** (B2 diagram 3.2) |
| RT-05 | ?: Pending, not flagged | unknown | any | P | — | Follow-up with the reporter due the next working day; a re-sign task follows | SD | Never closes as Pending: becomes RT-01–03 or a Y row | Sitting without an owner, due date and alert | **Exists** (B2, H3) |
| RT-06 | ?: Pending, flagged | H? | any | P | — | Fast triage **before** signing; the provisional clock shows (3a earliest date); follow-up | SD, TL | As RT-05 | Safety waiting for the classification | **Exists** (B2) |
| RT-07 | ?: Pending, confirm no deficiency | — | any | — | — | Answered "no deficiency" → RT-03. A deficiency → Y. Unresolved after the set attempts → Complaint | SD | As RT-05 | Pending for ever | **Exists** (call-intake 5.3 rule 5; B2) |
| RT-08 | Y | — | N | — | N | **The pure routine path:** sign and escalate → Confirm triage (1 click) → **Resolve and close** | SD or TL signs the Case; TL triages; TL or QR resolves | Complete: **closed by the signature**. Connect: ready to close signed; closed when the QMS closes it (filing reference) | Closed without customer told or without a problem code | **Partly.** Routine basis and ready to close exist as 3 signatures (`rules.py:84-89`, `router.py:442-455`, `oversight/router.py:1428`); the form opens empty (`disposition.ts:168`); no customer told; never closes (`closure.py:47`). **B7:** the combined screen |
| RT-09 | Y: Complaint and service | — | Y | — | N | As RT-08. The correction is the service fix (part replaced, setting corrected); the ticket is pre-filled from the Case | + service owner | As RT-08. Service completion is separate | Service complete closing the complaint | **Partly** (ticket required today, not pre-filled). **B7:** pre-fill |
| RT-10 | Y | — | Y/N | — | N | **No fault found** after evaluation: correction "No fault found", cause Undetermined with a reason. It counts toward the recurrence trigger | TL, QR | As RT-08 | No fault found undoing "Complaint" | **Partly** (no such correction code: `rules.py:69`). **B7:** add it |
| RT-11 | Y | — | N | — | N | **Device not returned:** return asked in the communications log; after the set attempts, evaluated on the description; "not returned" recorded | TL | As RT-08, after the attempts | Waiting for ever for a device | **Partly** (attempts exist: `communications/rules.py:47`). **B7:** "Device returned" field |
| RT-12 | Y | — | any | — | Y: known issue | Disposition "Known issue": joins the open investigation's scope; that investigation's decision decides it | TL; investigation team | Decision passes when the investigation's decision is signed; then ready to close | A second investigation for the same issue | **Exists** (`complaint_disposition/rules.py:9-10`) |
| RT-13 | Y | — | any | — | Y: trigger (recurrence, new failure mode) or by choice | Escalated → investigation → decision → CAPA in the QMS if systemic | INV; AP (reviewer ≠ author) | After the investigation decision; an open CAPA is listed, not blocking | The routine path offered while a trigger is met | **Partly.** The path exists (`triggers.py`, `closure.py:562-573`). **B7:** the problem code makes RECURRENCE and NEW_FAILURE_MODE work for Case-made complaints (today they never fire there: `triggers.py:281-285` needs a code); see B7-D4 |
| RT-14 | Y | — | any | P (a person started a market assessment) | N | The started assessment must be signed first | RR | The markets check blocks until it is signed | Closing with an assessment open | **Exists** (`closure.py:438-471`) |
| RT-15 | Y, reporter withdraws | — or M− | any | — | N | Withdrawal addendum. The screen asks "Is an investigation still needed?"; the reason "Reporter withdrew, no deficiency confirmed" is allowed only off the watch | TL, QR | As RT-08 | Withdrawal down-grading the complaint | **Partly** (addendum exists, B2 IN-18). **B7:** the reason |
| RT-16 | Y | M− | Y/N | — | N | Routine triage; routine path. **The signed basis names it:** "no malfunction that could cause serious harm if it recurred" | as RT-08 | as RT-08 | A signed basis saying "no malfunction recorded" when the Case says the device malfunctioned | **Partly.** Today's basis text says "no … malfunction recorded" (`rules.py:87-89`), while `complaints.malfunction` is set from Q6, not Q3 (`intake/service.py:1666`). **B7:** wording |
| RT-17 | Y | M+ | Y/N | N (every relevant market signed) | N | Fast triage → per-market trees signed "not reportable" → **Resolve and close**, showing the signed conclusions (no routine basis) | TL, RR, then TL or QR | As RT-08 | Closing before every market is signed | **Partly.** On the watch the routine path is not offered (`complaint_disposition/service.py:288-292`), so it is disposition + ready to close separately. **B7:** the combined screen (B7-D7) |
| RT-18 | Y | M+ (Q6 Unknown) | Y/N | P | — | Fast; earliest provisional clocks (3a); follow-up; tree "Needs more information" | TL, RR | Blocked until each market is signed | Unknown read as No | **Exists** (B2, 3a) |
| RT-19 | Y | M+ | Y/N | Y | Y (REPORTABLE trigger) | Report(s), investigation, CAPA if systemic, follow-ups | RR, AP, INV | Every obligation met + the investigation decision signed | A reportable complaint on the routine path | **Exists** (trigger) + B3 reports |
| RT-20 | Y | M+ | Y/N | N | Y (recurrence or by choice) | As RT-13, with the markets signed | INV, AP | As RT-13 | — | **Exists** |
| RT-21 | Y | H (minor) | Y/N | — | N | Fast triage (harm alleged). The routine path is offered (off the watch: outcome known, no death or serious injury) | TL, QR | As RT-08 | — | **Exists** (watch rule `reportability/rules.py:454-460`) + B7 screen |
| RT-22 | Y | DSI | Y/N | Y | Y | "Urgent: death or serious injury" or flagged → complaint at once, fast track 4 h, acknowledgement within 1 h, **urgent e-mail (B7)**, trees, reports, investigation, field-action decision through containment | anyone logs; TL; RR; AP; INV | All reports met; investigation decision signed; field action decided | The routine path; waiting for paperwork | **Exists** except the out-of-app alert (**B7**, section 5) |
| RT-23 | Y | DSI | Y/N | N (e.g. not device-related) | Y (INJURY trigger) | As RT-22 without a report; "not reportable" needs a causality rationale | RR, INV | Investigation decision signed | — | **Exists** |
| RT-24 | Y | H? | Y/N | P | ? | Fast; "Not known yet"; follow-up in 1 working day; the shortest clocks | TL | Blocked until the harm is known and the markets are signed | Closing on an unknown harm | **Exists** (B2, T-D3) |
| RT-25 | Y, imported (owned by the QMS) | — | any | — | N | The routine path works on imported complaints too (the disposition was built for them); master fields read only | TL, QR | Connect only: ready to close in your QMS + filing reference | MDARIX closing a QMS-owned complaint | **Exists** (dispositions, `oversight/router.py:1540` filing). **B7:** the combined screen, without closing |
| RT-26 | Y, closed, then new information (e.g. a death) | → DSI | any | any | any | Triage reopens on the fast track (T-D7). In Complete the complaint **reopens** and the closure signature is superseded; alert | system; TL | As the new row | New harm ignored on a closed complaint | **Partly** (triage reopens, B2; nothing to reopen because MDARIX never closes). **B7:** reopen |
| RT-27 | Y, anonymous reporter | any | any | any | any | Customer told = "Not possible: anonymous", with the Case's no-contact reason | TL | As its row | A blank customer-told | **New** |
| RT-28 | Y, two reporters, one event (attached Cases) | any | any | any | any | One complaint. Customer told **per reporter with a contact**; the others "not needed: same customer", with a reason | TL | As its row | A second reporter never told | **New** |
| RT-29 | Reply e-mail to an open Case | — | — | — | — | Offered "Add to CASE-…" as an addendum; one click to confirm | SD | — | A second Case created by itself | **New** (section 4) |
| RT-30 | Case imported from a call log, older than `backlog_days` | any | any | — | — | Imported backlog; no overdue alarms; the note "Imported: check what was decided in your source system" | SD, TL | As its row | Old calls flooding "overdue" | **New** (section 3; same rule as the owner's OD-12 decision) |

### 2.4 What changes by mode

The path is the same in both modes. Only these columns change.

| | MDARIX Complete | MDARIX Connect |
|---|---|---|
| Who closes the complaint | **MDARIX**, by the Resolve and close signature. Status `closed`, with `closed_at` and `closed_by` | **The QMS.** MDARIX signs "ready to close in your QMS"; the filing reference is recorded (exists) |
| Stage line, last stage | "Closed" | "Closed in your QMS" (exists) |
| Reopen | In MDARIX, with a reason; automatic on new harm | In the QMS; MDARIX reopens its triage (exists) |
| Problem code | Set on the Resolve and close screen | From the QMS import. Read only once the record is owned by the QMS; when empty, the screen says "your QMS sends none: recurrence checks cannot run" |
| Customer told | Communications-log entry | Communications-log entry, or the QMS letter ID |
| Service work | Service card in MDARIX | Service system reference on the Service card |
| CAPA | QMS reference (native CAPA is M5, later) | QMS reference |
| Contact (OD-1) | Held in MDARIX | "Contact: in your QMS"; none held by default |
| Getting the complaint into the QMS | — | **Export for QMS entry** (section 3), then the QMS import merges back. The open "Enter the QMS complaint ID" task blocks the routine screen until then: correct, because the QMS must hold the complaint |

### 2.5 Size
**30 rows × 2 modes = 60 combinations**:
- 17 rows **exist** (RT-01–07, 12, 14, 18–25; RT-22 lacks only the out-of-app alert);
- 9 are **partly built** (RT-08–11, 13, 15–17, 26; the routine core);
- 4 are **new** (RT-27–30).

The rows enter `scenario-register.md` as **RT-01 to RT-30**. That namespace is reserved for B7 there. The B2 run notes use "RT-05" for a story test; the build renames that local label.

---

## 3. Case bulk import and export

### 3.1 What B2 already covers (not repeated)
- **The complaints template** (`trial/imports.py:202-298`), with the QMS triage columns (T-D9), the imported backlog (OD-12), merge by QMS ID (TA-20.4), the IN-14 set-aside, routine routing of new imports (Q3), and the CSV row-limit fix.
- The whole import engine:
  - every batch checked before anything is written;
  - `on_problems=skip` with a rejects file;
  - personal data refused or masked (`imports.py:390-497`);
  - dates, zones and number formats;
  - Excel reading with the standard library (`trial/xlsx.py`);
  - lineage, the quality report, and re-upload change tracking.
- **Bulk assign** of up to 200 Cases (`intake/router.py:3150`).
- **OD-1 masking in the organisation export** (`tenant_export.py:54-74`, `masked_row`).
- CSV formula escaping (`csv_safe.py`).

### 3.2 What B7 adds: the "Cases" template (call logs from a call centre or CRM)

| Part | Rule |
|---|---|
| Required columns | `case_id`, `received_at`, `words` |
| Optional columns | `received_zone` (or one zone for the file), `channel`, `channel_ref`, `reporter_type`, `site`, `reporter_country`, `country`, `product_id` or `product_name` (kept as typed when unknown), `version`, `lot_id` (unknown: kept as typed, flagged), `serial_number`, `udi`, `software_version`, `hardware_revision`, `firmware_version`, `event_date`, `first_knowledge_at`, `first_knowledge_party`, `first_knowledge_basis`, `requested`, `troubleshooting`, `service_ticket`, `issue_category` (S-1), `patients`, `qms_ref` |
| Never accepted | **Contact columns** (name, phone, e-mail). The column is refused with "Contacts stay in your source system" (OD-1). **The ten answers**: a person answers at the Case check (B7-D14) |
| Identifiers | ID-1 shape: each one "unconfirmed, source: Imported" |
| Personal data | **Masked by default** for `words` and `troubleshooting`: call text is full of names, so refusing would refuse most rows. What masking cannot remove is refused. The report gives counts, never values |
| Times | A time without a zone needs the file's zone. Awareness follows H1: first knowledge, when given and acting for you, else the receipt. An event date in the future is refused (IN-10). The late-entry reason is set to "Imported from <file> on <date>" |
| Key and re-upload | Key = source + `case_id` (stored as `source_system = CASE_IMPORT` and `source_identifier`, unique per organisation). A re-upload fills only empty facts. **It never changes the words or the received time**: those rows are set aside with the reason. Every change goes to `record_field_changes` |
| Duplicates | Against Cases: by the key. Against complaints: B2's duplicate rule. Shown on "Possible duplicates"; **never merged by the import** |
| After import | Each row is a Case "To check", unsigned. The flags run at once: a flagged recent Case is triaged fast before signing (B2 rule). **A Case received more than `backlog_days` before the import** joins the imported backlog: no overdue alarms, with the note (RT-30) |
| Limits | The trial counts Cases in its 5,000-row allowance and 2 MB file (`trial/service.py:47-48`). Workspaces: **5,000 rows per Case file** (not 50,000), because each row runs flags and duplicate checks. Measured against R2: preview under 10 s, import under 30 s |
| Rights and audit | `records.write` plus `case.log`. Run lineage (R16), quality report (R17), audit `CASES_IMPORTED` (counts by state, flagged, set aside) |
| Signing | **None.** No route signs or classifies in bulk |

### 3.3 What B7 adds: export

| Export | Content | Rules |
|---|---|---|
| **Cases (CSV)** | One row per Case: reference; received and awareness with zones and their source; channel; the masked words; product · version · lot (with the not-in-master-data flag); identifiers and their status; state; owner; due; classification, signer, signed time, override reason, QA review; complaint reference; QMS ID; triage speed and severity; issue category | Filters are the Cases list's views + dates, channel, product, state, flagged. **Contacts masked by default** ("Contact held: yes", `tenant_export.masked_row`). Unmasked only with `data.export` and a reason, audited per export. **A trial is always masked.** The raw e-mail is never exported, only "Original e-mail held: yes" |
| **Export for QMS entry (CSV), Connect** | The complaints made from Cases with no QMS ID, in the complaints template's column order, plus an `mdarix_ref` column | The QMS enters them. On the next complaints import, a row carrying `mdarix_ref` **merges into that complaint** and fills its QMS ID (a small addition to the existing merge). This bridges to the QMS until a connector exists |
| Both | UTF-8 with BOM (opens in Excel), formula cells escaped (`csv_safe`). At most **20,000 rows** per file ("narrow the filter"). Permission `data.export`. Audit `CASES_EXPORTED` / `QMS_ENTRY_EXPORTED` (filter, row count, SHA-256 of the file). The file name carries the export ID | Same pattern as `oversight/router.py:657` |

**Excel files.** Import already reads `.xlsx`. Export writes CSV, which opens in Excel. An `.xlsx` writer would be new code (no library for it is installed). Recommended: later (B7-D13).

---

## 4. E-mail intake (free to run)

### 4.1 What exists today
- An **inbound webhook stub** for a hosted mail provider (`stage3_workflow_router.py:1060-1115`, `communication/email/inbound.py:83-101`). It stores event metadata only (`inbound_email_events`) and never creates a Case. The tenant is found through `inbound_provider_mappings` (`db/models/stage3.py:69-90`, control database).
- **Outbound mail goes through SMTP** (`communication/email/__init__.py:1`).
- **ClamAV** runs in production (`docker-compose.prod.yml` service `clamav`). `ObjectStorageService.scan` refuses any file without a clean verdict (`object_storage/service.py:233-275`).
- The attachment checks exist for evidence uploads: permitted types (PDF, text, CSV, PNG, JPEG), 10 MB per file, the organisation quota, content matching its type, and safe file names (`stage3_workflow_router.py:143-145`; `evidence_workflow/requests.py:905-950`).
- **Not on a Case today:** e-mail intake, attachments, threading, a translation.

### 4.2 Choice of route (B7-D8)

| Option | How | Cost | For | Against |
|---|---|---|---|---|
| **A. Our own receiver (recommended)** | An MX record for a subdomain, e.g. `intake.mdarix.com`, points at the production server. A small SMTP receiver runs as a new service, `mail-in`, from the same app image, using the open-source `aiosmtpd` library. The company's own mail stays where it is | Free; one small new dependency | No third party holds complaint e-mails; data stays on our server; full control of limits | Opens port 25 on the server (inbound only; we never send from it); we run one more service |
| B. Poll a mailbox (IMAP) | One mailbox at the existing mail host, with sub-addresses `intake+<token>@…`. The worker polls it with the standard library (`imaplib`) | Free **if** the host's plan allows IMAP and sub-addressing (**to verify**) | No open port, no new dependency | Depends on the mail host's plan, storage and limits; a mailbox password to keep as a secret; the host reads every complaint mail |
| C. The hosted webhook (the stub) | The provider receives and posts to us | Not free beyond small limits | Code partly exists | A third party sees every complaint; paid |

**Recommendation: A.** Fall back to B only if port 25 cannot be opened on the host. The existing stub stays as it is, unused.

### 4.3 The address
- **One address per organisation**, made of an unguessable token: `cases-7f3k9q2m@intake.mdarix.com`. It never contains the organisation's name, so it does not reveal the customer and cannot be guessed.
- Stored in the existing control table `inbound_provider_mappings`: provider `MDARIX_MAIL`, account = the token, tenant, status. **No new table.**
- **Settings › Complaints › "E-mail intake"** (Customer Admin):
  - the address, with Copy;
  - on/off;
  - **Rotate**: the old address keeps working for 30 days, then is refused;
  - an optional list of allowed sender domains (off by default);
  - how to auto-forward a complaints mailbox. Many mail systems block forwarding to outside addresses until an administrator allows it. Many also send a confirmation message first, which appears in "E-mail to check" as a setup message.

### 4.4 From the message to a Case

1. **Receive** (the `mail-in` service):
   - The recipient must be an active token. Anything else is refused during the SMTP conversation (550), so nothing is stored and no bounce is sent.
   - Size limit 25 MB. TLS is offered (opportunistic).
   - The raw message goes to object storage under the tenant, encrypted like other files.
   - A row is added to `inbound_messages`, and a job to the existing outbox.
2. **Process** (worker, standard-library `email` parser):
   - **Each attachment** gets the type, size, content and quota checks, then the **ClamAV scan**.
   - An **infected** file is never stored. The raw message is re-stored **without that part**, and its name (masked), hash and "virus found" are recorded. The person sees "1 attachment refused: virus found".
   - A type not accepted, or a file too large, is listed as refused with the reason.
   - Small inline images (under 20 KB: logos) are ignored.
3. **Thread and duplicates:**
   - The same `Message-ID` twice is stored once.
   - `In-Reply-To` or `References` matching a message already on a Case, or a Case reference in the subject, means the message is offered as **"Add to CASE-…"** (an addendum). It never becomes a new Case by itself (RT-29).
   - The same body hash within 7 days shows "possible duplicate of …".
4. **Draft** (rule-based, no AI):
   - The words are the message body, with HTML reduced to text, the signature block cut, and personal data masked.
   - The subject is masked. Only the sender's **domain** is kept on the draft.
   - Product, lot, serial and UDI are matched against master data and the GS1 pattern. Each is **"unconfirmed, source: E-mail"** (ID-1).
   - The site comes from the sender's domain when it matches a known site, as a suggestion.
   - The harm and fault words run (with the B7 fixes in step 12).
   - "May not be English" is flagged.
5. **The list "E-mail to check"** (a new view under Cases):
   - Each card shows the received time, the sender domain (marked **unverified**), the masked subject and first lines, flag chips, attachments, and a possible Case match.
   - Due by the end of the same working day. Overdue messages go to the escalation role (existing sweep).
   - A message with death or serious-injury words raises an in-app alert at once, and the urgent e-mail when that is switched on (section 5).
6. **A person decides** (one card at a time; no bulk):
   - **"Make it a case":** opens Log a case pre-filled. Channel is E-mail, the channel reference is the `Message-ID`, and **Received is the time our server received the message, not the time of the click**. On Save the Case exists, unsigned "To check", and the clean attachments move to the Case.
   - **"Add to CASE-…":** an addendum ("said by the reporter").
   - **"Not a case":** a reason (spam · auto-reply · setup message · internal · duplicate of … · other). **On a message with a harm or fault word, only a quality reviewer may choose it**, and outside the trial not the person who opened it. Like every downward decision in B2, it is audited with the reason.
   - Auto-replies and bounces (`Auto-Submitted`, `Precedence: bulk`, empty sender) go straight to "Not a case" with the reason. **Nothing is ever deleted silently.**
7. **Awareness:**
   - Received = our server's receipt time.
   - An earlier date in a forwarded message's headers is shown as **"possibly known earlier: <time>"**, for the person to record as first knowledge (H1).
   - Awareness is never set later than the receipt.

**The rule that never bends: an e-mail never becomes a complaint.** It becomes, at most, a Case that a person classifies and signs.

### 4.5 Spam and abuse limits
- Only known addresses are accepted. **No relay** (the receiver delivers nowhere else).
- **Rate limits:** per sending IP, 30 messages an hour; per address, 200 a day (organisation setting). Over the limit, the sender gets a temporary refusal (451) and retries later. The Customer Admin is told once a day.
- At most 10 attachments; 10 MB per attachment; 2 MB of text.
- **No automatic reply to senders** (B7-D10). This means no backscatter and no way to use MDARIX to send mail.
- An optional allowlist of sender domains per organisation.
- Rotate the address when it attracts spam.
- **SPF, DKIM and DMARC are not checked in B7.** The sender is shown as "unverified" and nothing trusts it, because a person decides every message.

### 4.6 Privacy (OD-1)

| Data | Where it lives | Who sees it | Kept |
|---|---|---|---|
| The raw message (headers, sender address, signature, attachments) | Object storage, quarantined | Only the OD-1 contact roles (Service Desk, Triage Lead, Quality Reviewer, Regulatory Reviewer, Leader). **Each raw view is audited**, unlike plain views | **As long as the Case record** when it became a Case (it is the original complaint communication). **30 days** after "Not a case" (B7-D11) |
| The Case words and the subject | The Case, masked | Every member, as today | With the Case |
| The sender's address as a contact | Not copied by itself. In Complete, the button **"Use the sender as the contact"** fills the OD-1 contact fields. In Connect, none (OD-1) | OD-1 rules | OD-1 rules |
| AI | **Never.** Raw messages and contacts stay outside every AI context (OD-1) | — | — |
| Exports | The raw message is never exported | — | — |

**Free trials (B7-D9).** No real intake address, because a trial promises no personal data. A **SAMPLE e-mail** in "E-mail to check" shows the flow. Real addresses are for pilots and paying organisations.

### 4.7 Operations
- DNS: one MX record for the intake subdomain.
- Firewall: inbound port 25. Most clouds block only outbound 25; **to verify on the production host**.
- TLS: a certificate for STARTTLS. A self-signed one is enough for opportunistic TLS; **to verify** with a test from two common mail systems.
- `mail-in` runs as a non-root, read-only container, like `api`, with a health check.
- If it is down, senders queue and retry for days, so nothing is lost in a short outage. The H1 independent alert channel reports it.

### 4.8 Out of scope in B7
- Connecting the customer's own mailbox (Microsoft 365, Google; D4: for paying customers later).
- Replies sent from MDARIX.
- SPF/DKIM/DMARC checks.
- AI extraction (2027, after evaluation).
- Machine translation. B7 offers a **"Translation" addendum** a person writes; the original is always kept (IN-15).
- A web form or portal.
- SMS.
- Encrypted mail (S/MIME, PGP), which lands as "cannot be read: encrypted".
- Distributor sign-in.

---

## 5. The urgent alert (old step 4.5, D6)

| | B2 already does | B7 adds |
|---|---|---|
| Urgent Case | "Urgent: death or serious injury" makes the complaint at once and puts it on the fast track (4 h) (`intake/router.py:1013`) | — |
| Acknowledgement | A named owner acknowledges within 1 h. Otherwise it is overdue, and the 15-minute sweep escalates to the backup and the escalation role (B2 A1) | One reminder e-mail when the acknowledgement is overdue |
| Delivery | In-app alerts with channel, attempts, result and retries. **A failed notice never cancels the escalation** (B2 A2; `db/models/oversight.py:151-156`) | Channel `EMAIL` on the same rows |
| Out-of-app notice | **None.** In-app only | **An opt-in e-mail**, per organisation (Settings › Oversight, "Urgent e-mail alert", off by default; audited). It is queued **at once**, not at the next sweep, through the existing notifications outbox (`notifications.py`; SMTP; retries and dead-letter exist). The outbox holds identifiers only |
| What triggers it | — | An urgent Case; any item reaching the fast track with a death or serious injury (including an automatic reopening, RT-26); an e-mail draft with death or serious-injury words |
| Who gets it | — | People holding the organisation's escalation role, plus Triage Leads, who have an e-mail address. Once per item per person |
| What it says | — | Subject "MDARIX: urgent case received". Body: "An urgent case (URG-…) was received at 14:20 Asia/Kolkata. Open MDARIX to see it: <link>". **No product, no words, no patient data.** The link needs sign-in and MFA |
| SMS | — | **Not in B7:** there is no free SMS route (B7-D12) |

Scenarios: UA-01 to UA-06 (section 6.5).

---

## 6. Gaps, build steps, migration, cuts

### 6.1 Gap table

| # | Requirement | Exists today (file:line) | Gap | Change |
|---|---|---|---|---|
| G1 | One screen and one signature from triage to closure | Disposition sign (`complaint_disposition/router.py:377-455`); ready to close (`oversight/router.py:1428-1537`) | Three signatures and an owner step | `POST /complaints/{id}/resolve-and-close`: both signed records in one transaction, one credential check |
| G2 | Pre-filled resolution | Case `troubleshooting`, `service_ticket` (B2); complaint `service_reference` (`intake/service.py:1667`) | The form opens empty (`disposition.ts:168,188`) | The screen reads them; defaults from `requested` |
| G3 | Service ticket only when service work was done | Always required (`complaint_disposition/rules.py:160`; `disposition.ts:225`) | Blocks "user instructed" cases | Required only for Part replaced and Setting corrected |
| G4 | No fault found ending | Corrections list (`rules.py:69`) | No code | Add `NO_FAULT_FOUND` (JSON, no schema change) |
| G5 | Structured "why no investigation" | 20-character free text (`rules.py:162-165`) | Typing every time | Reason list + facts shown; text only for Other (B7-D2) |
| G6 | Problem code on Case-made complaints | Imported only; escalation copies none (`intake/service.py:1642-1672`) | Recurrence, new-failure-mode and known-issue matching never see Case-made complaints (`triggers.py:281-285`; `service.py:194-222`) | Required on the screen; audited `PROBLEM_CODE_SET`; the new-failure-mode answer (B7-D4) |
| G7 | Customer told at closure | Communications log exists (`communications/router.py`); no closure check (`closure.py:387-576`) | Never checked (call-intake M13) | New check `CUSTOMER_TOLD`: Done (an entry per reporter with a contact) · Not needed with a reason · Open |
| G8 | Native closure (Complete) | "MDARIX never closes" (`closure.py:47-50`; stage "Closed in the QMS", `closure.py:36-43`) | OD-6 deferred to B7 | Complete: the signature sets status `closed` and `event_closures.closed_at/by`; stage "Closed" |
| G9 | Reopen a closed complaint | Triage reopens (B2, T-D7) | Nothing to reopen | Manual reopen with a reason; automatic on the T-D7 triggers; the closure is superseded |
| G10 | Routine basis wording | `ROUTINE_BASIS` (`rules.py:87-89`) | Says "no malfunction" when Q3 is Yes | "no malfunction that could cause serious harm if it recurred" |
| G11 | Combined screen for on-watch complaints with every market signed not reportable | Routine not offered on the watch (`service.py:288-292`) | Extra steps for RT-17 | Offer Resolve and close with the signed conclusions (B7-D7) |
| G12 | Case import | Complaints template only (`trial/imports.py:174-300`) | No call-log import (call-intake M2, D13) | "Cases" template (section 3.2) |
| G13 | Case export, OD-1 masked | Organisation export masked (`tenant_export.py:54-74`); oversight CSV pattern (`oversight/router.py:657`) | No Case export (M3) | Cases CSV + export for QMS entry (section 3.3) |
| G14 | QMS round trip by MDARIX reference | Merge by `qms_ref` (B2 TA-20.4) | The QMS never knows the Case reference | Optional `mdarix_ref` column in the complaints import |
| G15 | Case attachments | None on a Case (`intake/router.py`, no upload route); checks exist (`stage3_workflow_router.py:143-145`; `evidence_workflow/requests.py:905-950`) | No photos or logs (M7) | `case_attachments`: upload, list, download, scan, need-to-know |
| G16 | E-mail intake | Webhook stub, metadata only (`stage3_workflow_router.py:1060-1115`) | Everything (M1) | Section 4 |
| G17 | Urgent out-of-app alert | In-app only; delivery columns exist (`db/models/oversight.py:151-156`) | D6 not built | Section 5 |
| G18 | Harm words | `intake/rules.py:136-199` | "patient not harmed" flags harm; "passed away" missed; English only (M9) | Negation, synonyms, a non-English flag |
| G19 | Translation (IN-15) | Addenda kinds checked (`tr19`, `ck_case_addenda_kind_known`) | No translation kind | Kinds `TRANSLATION`, `EMAIL` |
| G20 | Device not returned | Attempts in the communications log (`communications/rules.py:47`) | Not recorded on the resolution | "Device returned" field (JSON) |

### 6.2 Build steps (targeted tests per step; full release gates once at the end)

| Step | Work | Hours | Targeted tests |
|---|---|---|---|
| 0 | Gap check on the branch base (big-bang line + hardening, head tr24); add RT, BK, EM and UA to the register | 3 | — |
| 1 | Migration **tr25** + models + legacy-plane function (6.3) | 4 | upgrade/downgrade on the test DB; RLS on the two new tables |
| 2 | Pure rules: ticket rule, No fault found, reasons, wording, customer-told rule, when the combined screen is offered, known-behaviour answer | 4 | `test_routine_rules_b7.py` (unit): every branch × correction × watch state |
| 3 | Resolve and close route: two signed records; routine conclusions or signed markets; communications entry; problem code; owner take-over; closure check `CUSTOMER_TOLD`; native close and reopen (Complete); automatic reopen hook; Connect unchanged | 14 | `test_resolve_and_close.py` (DB): RT-08–11, 15–17, 21, 25–28; refused when a trigger appears meanwhile, when anything else blocks, when an administrator signs; Connect never closes; reopen supersedes |
| 4 | Screens: Resolve and close (pre-filled, flat per G-2), next step on the complaint page, the Dispositions link, Reopen, mode wording | 12 | `resolveClose.test.tsx`, `complaintPage.test.ts` and `dispositions` (vitest) |
| 5 | Case import ("Cases" template, writes, re-upload, backlog marker, `mdarix_ref` match in the complaints import) | 10 | `test_case_import_b7.py` (DB): BK-01–09, 12, 13 |
| 6 | Case export + export for QMS entry (masking, audit, limits) | 5 | `test_case_export_b7.py`: BK-10–12 |
| 7 | Case attachments (upload, list, download; scan; need-to-know) | 5 | `test_case_attachments.py`: clean, infected, wrong type, quota, other tenant |
| 8 | `mail-in` receiver: `aiosmtpd`, known recipients only, size and rate limits, TLS, compose service, health | 8 | `test_mail_in.py` with local SMTP sessions: EM-01, 10, 14, 16, 18. **No real mailbox, no real send**; a guard fails any test that sets a real mail host |
| 9 | Processing: parse, quarantine, scan, strip infected parts, threading, duplicates, draft extraction, flags | 10 | `.eml` fixtures: EM-02–09, 11, 13, 17 |
| 10 | Screens: "E-mail to check", Make it a case / Add to case / Not a case, Settings address (rotate, allowlist); retention purge on the 15-minute pass | 10 | vitest `emailIntake.test.tsx`; DB: EM-12, 15, purge after 30 days |
| 11 | Urgent e-mail alert (setting, outbox event at once, delivery rows, overdue reminder) | 5 | `test_urgent_alert_b7.py`: UA-01–06 |
| 12 | Harm words (negation, synonyms, non-English flag) + translation addendum | 4 | `test_intake_rules.py` extended |
| 13 | Help, user guide, CHANGELOG. A routine sample complaint and a SAMPLE e-mail ("More cases to try"); refresh step for running trials; day-story tests re-run | 6 | `test_sample_story_days.py`, `test_getting_started_part1.py` |
| 14 | Scenario run (RT, BK, EM, UA), then the full gates once (backend suite, ruff, lint, format, vitest, build, journeys) | 6 | register updated with PASS / FAIL / NOT RUN |
| | **Total** | **106** | **B7a** (steps 0–7, 11–14) about **78 h**; **B7b** (steps 8–10) about **28 h** |

### 6.3 Migration
**One migration: `tr25_trial_routine_path.py`, revision `tr25routinepath`.** Its `down_revision` is the single head on the branch base: DB-1's last revision (tr24), checked at step 0. B2's head is `tr19casesescalation`; DB-1 uses tr21–tr24.

It is expand-only, with forced RLS on the new tables and composite foreign keys (db-audit §7):

| Table | Change |
|---|---|
| ✚ `inbound_messages` | id, tenant_id, message_id, in_reply_to, references (jsonb), subject_masked, from_domain, received_at, header_dates (jsonb), body_sha256, raw_object_key, raw_size, attachments (jsonb: masked name, type, size, sha256, scan result, object key or null), flags (jsonb), draft (jsonb), state (`NEW`, `MADE_CASE`, `ADDED_TO_CASE`, `NOT_A_CASE`, `PURGED`), reason, intake_event_id (composite FK), decided_by, decided_at, purge_after, version, created_at. Unique (tenant_id, message_id); index (tenant_id, state, received_at) |
| ✚ `case_attachments` | id, tenant_id, intake_event_id (composite FK), inbound_message_id, object_key, filename_masked, content_type, size, sha256, usable, unusable_reason, source (`EMAIL`, `UPLOAD`), created_by, created_at. Index (tenant_id, intake_event_id) |
| `event_closures` | ✚ `closed_at`, `closed_by`, `reopened_at`, `reopened_by`, `reopen_reason` |
| `oversight_settings` | ✚ `urgent_email` bool NOT NULL default false; ✚ `mail_allowed_domains` jsonb NOT NULL default `[]`; ✚ `mail_daily_limit` int NOT NULL default 200 |
| `case_addenda` | Widen `ck_case_addenda_kind_known`: + `TRANSLATION`, `EMAIL` |
| `intake_events` | Partial unique index (tenant_id, source_identifier) WHERE source_system = 'CASE_IMPORT'. No existing row has that source, so no pre-check is needed |

- **Code only, no schema:** correction `NO_FAULT_FOUND`, the reasons, "device returned" and the known-behaviour answer (all in the disposition's `service_record` and `answers` JSON); ID-1 source `EMAIL`; the closure check `CUSTOMER_TOLD`; addresses in the existing `inbound_provider_mappings`.
- **mvp-1.0:** the forward merge adds a merge revision joining its head and `tr25routinepath`, the md53–md65 pattern.
- **One new dependency:** `aiosmtpd`, open source. It goes into `requirements.in` with hashes and pip-audit, and only in B7b.

### 6.4 What could be cut (in this order; each cut is self-contained)
1. **E-mail intake (steps 8–10, 28 h)** → ship as B7b in the next release. B7a still gives the routine path, closure, import and export, and the alert.
2. Export for QMS entry and `mdarix_ref` (about 3 h). Connect users then type the QMS ID, as today.
3. Upload of attachments by hand (about 2 h of step 7). E-mail attachments still need the table.
4. Harm-word improvements and translation addendum (step 12, 4 h).
5. The routine sample complaint and the sample e-mail (about 3 h of step 13).
6. Automatic reopening of a closed complaint (about 2 h); manual reopen stays.

**Never cut:** customer told; the refusal to close over an open item; the triggers that keep reportable, death and serious-injury complaints off the routine path; OD-1 masking; the virus scan; "an e-mail never becomes a complaint".

### 6.5 Scenarios to add to the register

**RT-01 to RT-30:** the matrix rows (section 2.3).

**BK (bulk import and export):**
- **BK-01:** download the template.
- **BK-02:** names in the words are masked; the report shows counts.
- **BK-03:** contact columns are refused.
- **BK-04:** a re-upload duplicates nothing and fills empty facts.
- **BK-05:** a re-upload that changes the words is set aside.
- **BK-06:** an unknown lot is kept and flagged.
- **BK-07:** a recent row with a death word goes to fast triage.
- **BK-08:** an old row goes to the backlog with no alarms.
- **BK-09:** an over-limit file is refused whole.
- **BK-10:** the export is masked by default; unmasking needs a reason and is audited; a trial is always masked.
- **BK-11:** formula cells are escaped, and the SHA-256 is in the audit.
- **BK-12:** the QMS round trip merges by `mdarix_ref`.
- **BK-13:** no route signs in bulk.

**EM (e-mail intake):**
- **EM-01:** an unknown address is refused at SMTP and nothing is stored.
- **EM-02:** a normal mail becomes a draft; received = server time.
- **EM-03:** "Make it a case" carries the channel, the `Message-ID`, the masked words and the attachments.
- **EM-04:** a reply offers "Add to case".
- **EM-05:** the same `Message-ID` is stored once.
- **EM-06:** the same body shows "possible duplicate".
- **EM-07:** an infected attachment is never stored.
- **EM-08:** a wrong type or a file too large is refused with the reason.
- **EM-09:** an auto-reply goes to the bin and is purged after 30 days.
- **EM-10:** the rate limits answer 451.
- **EM-11:** a death word raises the alert.
- **EM-12:** "Not a case" on a fault word needs a quality reviewer.
- **EM-13:** a non-English message is flagged; a translation addendum can be added.
- **EM-14:** after rotation the old address works 30 days.
- **EM-15:** a raw view is audited and need-to-know.
- **EM-16:** receiver down, senders retry, the health check shows it.
- **EM-17:** a forwarded earlier date becomes a first-knowledge candidate.
- **EM-18:** an organisation's token never writes into another organisation.

**UA (urgent alert):**
- **UA-01:** opted in, the e-mail is sent at once with no patient data.
- **UA-02:** opted out, in-app only.
- **UA-03:** an SMTP failure is shown; the escalation stays; no duplicate e-mails.
- **UA-04:** an overdue acknowledgement gets one reminder.
- **UA-05:** reopening with a death sends the alert.
- **UA-06:** a person with no address or a deactivated account is skipped and recorded.

### 6.6 Risks

| Risk | Handling |
|---|---|
| New problem codes make the first complaint of each code escalate (NEW_FAILURE_MODE), so most new organisations see few routine closures at first | B7-D4: a signed "known behaviour, documented in <reference>" answer |
| Port 25 or the mail host behaves unexpectedly | Option B fallback; B7b can slip without holding B7a |
| The combined signature changes how Part 11 reviewers read the record | Two signed records with their own meanings, one credential check in one session; shown in the event decision record |
| Retention of raw e-mails holds personal data for years | Restricted roles, audited views, OD-1 erasure; B7-D11 for the owner |
| Performance of the new closure check and the trend count on the screen | One query per complaint (product + problem code, 12 months, existing index on product); measured in step 14 |

---

## 7. Owner decisions needed

| # | Decision | Recommendation |
|---|---|---|
| B7-D1 | One "Resolve and close" signature writes the disposition and ready-to-close records (and closes in Complete) | **Yes.** One credential check, two signed records with their own meanings |
| B7-D2 | "Why no investigation": a reason list plus the facts checked, with free text only for "Other" | **Yes**; the 20-character text stays for "Other" |
| B7-D3 | Service ticket required only for Part replaced and Setting corrected | **Yes** |
| B7-D4 | A new problem code on a product (NEW_FAILURE_MODE) may be answered "known behaviour, documented in <IFU or risk-file reference>" inside the signature, instead of forced escalation | **Yes.** RECURRENCE and the other triggers unchanged |
| B7-D5 | "Customer told" is a closure check: one entry per reporter with a contact, or "Not possible" with a reason; Connect accepts a QMS letter ID | **Yes** |
| B7-D6 | Complete closes natively; reopening needs a reason but no signature; automatic reopening on new harm | **Yes** |
| B7-D7 | Resolve and close is also offered for complaints on the watch once every relevant market is signed not reportable and no trigger is met | **Yes** |
| B7-D8 | E-mail route: our own receiver on `intake.mdarix.com` (free, port 25) vs polling a mailbox | **Own receiver**; mailbox polling only as a fallback |
| B7-D9 | E-mail intake in free trials | **Sample e-mail only**; real addresses for pilots and paying organisations |
| B7-D10 | Automatic acknowledgement e-mail to senders | **None in B7** (no backscatter, no misuse) |
| B7-D11 | Raw e-mail retention | **With the Case record** when it became a Case; **30 days** for "Not a case" |
| B7-D12 | Urgent alert channel and scope | **E-mail only, opt-in per organisation**, sent at once to the escalation role and Triage Leads, for urgent Cases, any death or serious injury on the fast track, and e-mails with those words. No SMS (not free) |
| B7-D13 | Export format | **CSV only** (opens in Excel); `.xlsx` later |
| B7-D14 | The ten answers in the Case import | **Not accepted**: a person answers at the Case check |
| B7-D15 | Ship in two parts if needed | **Yes:** B7a (routine path, closure, import and export, alert), then B7b (e-mail) |
| B7-D16 | Attachment quota (100 MB per organisation today, `stage3_workflow_router.py:144`) with e-mail photos | **Keep it for trials; make it an organisation setting** for pilots, with the H1 quota fix (code-audit item 15) |

---

## 8. What could not be verified
- **No code was run.** No test, database or browser. Every behaviour cited is from reading the code on `feat/hardening-0.10.95` (worktree `trial-093`). Line numbers may move with the hardening and B3 builds before B7 starts.
- **Click counts** are counted from the design, not timed.
- **Mail infrastructure:**
  - Not checked: whether the production host allows inbound port 25.
  - Not checked: whether common senders accept a self-signed certificate for opportunistic TLS.
  - Not checked: whether the existing mail host's plan offers IMAP and sub-addressing (option B).
- **Regulatory text was not re-read.** The basis for "customer told" (complaint records include the reply to the complainant) and for the no-investigation justification (ISO 13485:2016 8.2.2; US QMSR by reference) is cited from the planning files and knowledge: **to confirm**.
- **Retention values** (raw e-mail with the record; 30 days for "Not a case") are proposals, not checked against DPDP rules or a customer's SOP.
- **Effect of B7-D4:** how often NEW_FAILURE_MODE would fire on a real organisation's data was not measured.
- **The trend count on the screen** assumes the existing per-product complaint index is enough; not measured.

## Owner approval (10 Nov 2026)
"approve B7 spec": all sixteen recommendations B7-D1 to B7-D16 accepted. Build starts as soon as B3's build is complete (owner, 10 Nov: no need to wait for 27 Nov), on its own branch, not in the big-bang deploy; ships in the first release after the WHIF freeze (as B7a, then B7b if needed). The malfunction-flag wording bug found here is fixed earlier, in hardening 0.10.95. Before B7b: confirm the production host accepts inbound mail (port 25).

## Build status (run 1, 10 Nov 2026)

Branch `feat/b7-routine-path` from `feat/b3-emdr-0.10.96` (worktree `trial-093`), local only, not pushed. CHANGELOG section `[0.10.97] - not released yet (after the WHIF freeze)`.

| Step | State | Commit |
|---|---|---|
| 0 Gap check + register | Done. Register: RT-01..30, BK-01..13, EM-01..18, UA-01..06 appended to `scenario-register.md` (all NOT RUN). Gap check: the head is `tr19casesescalation` (no B3 migration; DB-1 not built). G10 (routine basis wording) was settled by hardening 0.10.95 (malfunction from Q3), so no wording change; RT-16 now follows RT-17. | (planning files, no repo commit) |
| 1 Migration tr25 + models + legacy plane | Done. `tr25routinepath`, down_revision `tr19casesescalation`, DB-1 note at the top. Upgrade, downgrade, upgrade run on `mdarix_b2_test`; `test_rls_coverage.py` 4 passed. | ed3fd0ff |
| 2 Pure rules | Done. `disposition-starter-2`; ticket rule; NO_FAULT_FOUND; reasons list; device returned; default correction; customer-told rule; known-behaviour answer; combined offer. `test_routine_rules_b7.py` + `test_complaint_disposition_rules.py`: 49 passed. | 65f51f8f |
| 3 Resolve and close, closure, reopen | Done (backend). `complaint_disposition/resolve.py`; `sign()` shared with the disposition route; closure check CUSTOMER_TOLD; native close in Complete; manual reopen; automatic reopen hook in `intake.service.reopen_raised`. `test_resolve_and_close.py` 4 passed. | d68644b2 |
| 4 Screens | Not started (only the disposition form's ticket rule changed in `disposition.ts`). | - |
| 5-7, 11-13 | Not started. | - |
| B7b 8-10 | Not started (after B7a). | - |

**Tests run (targeted, `POSTGRES_DB=mdarix_b2_test`):** `test_routine_rules_b7.py` + `test_complaint_disposition_rules.py` 49 passed (unit); `test_complaint_disposition_api.py` 9 passed; `test_resolve_and_close.py` 4 passed; `test_oversight_api.py` 7 passed (after the sample records its customer told); `test_flagship_walkthrough.py` 4 passed (it now logs the reply before ready to close); WHIF story `test_sample_story_days.py`, `test_release_0_10_92.py`, `test_getting_started_part1.py` passed (20 passed, 1 xfailed together with the walkthrough's first run); `test_rls_coverage.py` 4 passed. `test_signing_code_refusals.py::test_every_signing_route_is_known` FAILS: the extra routes it lists are B2's triage and intake routes (not B7's); not checked against the base commit.

**Not done or not tested in step 3:** the optional problem description (masked) is not stored; the automatic reopen hook is wired but not tested end to end (whether the triage list still includes a closed complaint is not checked); RT-28's "not needed: same customer" per reporter is not separate (one told record covers all reporters; a reply is logged to each reporter with a contact); the new resolve route is not detected by the signing-route scan (it reaches `verify_signing_credentials` through `router.sign`, another module).

**Behaviour changes to note:** CUSTOMER_TOLD now blocks every ready-to-close, the investigation path included (B7-D5), until a reply is in the communications log or a customer-told entry is signed. Running trials' existing events will show it as open; step 13's refresh should cover them. Mode: Complete only when the complaint's `record_owner` is MDARIX (or empty on an MDARIX-made complaint in an organization whose complaints are owned by MDARIX); everything else is Connect and never closes.

## Build status (run 2, 10 Nov 2026)

Branch `feat/b7-routine-path` (worktree `trial-093`), local only, not pushed. Tip `117f05f2`.

| Step | State | Commit |
|---|---|---|
| Merge B3 | Done, no conflict (git merged `intake/router.py`, `CHANGELOG.md`, `test_signing_code_refusals.py` by itself). `test_signing_code_refusals.py` + `test_triage_signing_refusals.py` + `test_resolve_and_close.py`: 10 passed. | fbad7d2b |
| Signing-route scan + refusal test | Done. The scan follows helpers imported from other `backend.app` modules (adds exactly `/complaints/{id}/resolve-and-close`, nothing else). New refusal test: wrong and missing code both `SIGNATURE_CODE_INVALID`, both audited `SIGNATURE_MFA_FAILED` (attempt `COMPLAINT_DISPOSITION_SIGN`), nothing saved. **Bug found and fixed:** a refused signature left the chosen problem code on the complaint (the refusal audit's commit on the shared trial plane saved it); `complaint_disposition/router.sign`'s refusal now rolls back first, as the intake routes do. | d24c67f3 |
| Run 1 gaps | Done. Optional problem description stored, masked (`service_record.problem_description`). Automatic reopen tested end to end on a Case-made complaint. **Bug found and fixed:** the triage list skipped closed complaints, so the hook could never reopen one; a complaint MDARIX closed now stays on the list (done). Note: words alone in an addendum ("the patient died") flag "harm not known" only and do **not** reopen; re-answering the Case check with Q5 Yes does (B2 rule, unchanged). The sample SAMPLE-RT-01 has no triage record, so it never auto-reopens. | 556964fc |
| 4 Screens | Done. `sections/ResolveClose.tsx` + `resolveClose.ts`: the drawer opens Resolve and close first unless a trigger other than NEW_FAILURE_MODE is met, an open investigation matches, or a disposition is signed; "Use the full decision tree" one click away; a code new on the product asks for the known-behaviour reference ("Escalate instead"); "Resolve" only with the blocking list; closed → Reopen panel. Event next step reads "Resolve and close" (Connect wording) when no trigger; complaint page shows "Closed in MDARIX" + Reopen. API adds `problem_codes`, `product_codes`, `closed_at`; event view `ready.closed_at`. | 117f05f2 |
| 5-7, 11-13 | Not started. | - |
| B7b 8-10 | Not started. | - |

**Tests run (targeted, `POSTGRES_DB=mdarix_b2_test`):** `test_resolve_and_close.py` + `test_signing_code_refusals.py` + `test_complaint_disposition_api.py` 18 passed; `test_resolve_and_close.py` 6 passed (after the reopen test); `test_triage_two_speeds_api.py` + `test_intake_triage_api.py` 25 passed; `test_resolve_and_close.py` + `test_oversight_api.py` + `test_flagship_walkthrough.py` 17 passed. Vitest `resolveClose.test.tsx` (new, 9) + `disposition.test.tsx` + `complaintPage.test.ts` + `nextStepButtons.test.tsx`: 22 passed. `tsc --noEmit --noUnusedLocals`: clean. WHIF story `test_sample_story_days.py` + `test_release_0_10_92.py` + `test_getting_started_part1.py`: 17 passed, 1 xfailed (at tip `117f05f2`; `test_flagship_walkthrough.py` passed above).

**Open for run 3:** step 5 next (Case import), then 6, 7, 11, 12, 13. The UI's "new code" check does not know about an open investigation that covers the code (the server's NEW_FAILURE_MODE does), so it may ask for a known-behaviour reference the server would not need; harmless, noted.

## Build status (run 3, 10 Nov 2026)

Branch `feat/b7-routine-path` (worktree `trial-093`), local only, not pushed.

| Step | State | Commit |
|---|---|---|
| Merge B3 (hardening run 6) | Done, no conflict (git merged `CHANGELOG.md` and `test_signing_code_refusals.py` by itself). `test_signing_code_refusals.py` + `test_resolve_and_close.py` + `test_triage_signing_refusals.py`: 14 passed. | bb641634 |
| 5 Case import | Done. "Cases (call logs)" template on the import engine (`intake/case_import.py`); masked always; contact headers not read (note "Contacts stay in your source system"); 5,000 rows; trial allowance counts Cases; `records.write` + `case.log`; `CASES_IMPORTED`; re-upload by `case_id`; RT-30 backlog (no check due, no overdue alarm, note; a flagged one stays on the triage list as backlog work, like an imported complaint); `mdarix_ref` merge in the complaints import. `test_case_import_b7.py` 6 passed. | 31621de7 |
| 6 Case export | Done. `GET /api/v1/intake/cases/export.csv`, `GET /api/v1/intake/qms-entry/export.csv` (`intake/case_export.py`). `test_case_export_b7.py` 3 passed. | e22109a9 |
| 7 Case attachments | Done. `intake/case_attachments.py`; quota is `oversight_settings.attachment_quota_mb` (**added to the unreleased tr25**, default 100, B7-D16), evidence + supplier + Case files counted together; `PUT /api/v1/oversight/settings/alerts-and-files` (quota; a trial keeps 100 MB; also `urgent_email`). tr25 downgrade/upgrade re-run on `mdarix_b2_test`. `test_case_attachments.py` 4 passed. | 2230b575 |
| 11 Urgent e-mail alert | Done. `oversight/urgent_alert.py`; outbox events `URGENT_CASE_ALERT` / `URGENT_CASE_REMINDER` (identifiers only), handler in `notifications.py`, `emailer.send_urgent_case_alert`. Sent for an urgent Case, a Case escalated with Q5 Yes, a triage reopening on DEATH/SERIOUS_INJURY; once per item per person; no-address people recorded in `URGENT_EMAIL_QUEUED`; the sweep queues one reminder on an overdue acknowledgement. **Deviation:** delivery is tracked on the outbox event (attempts, retries, dead-letter), not as `DueAlert` rows with channel EMAIL (those rows share a unique key with the in-app alerts and the sweep would resolve them). `test_urgent_alert_b7.py` 4 passed. UA-05 (automatic reopening) and UA-06 (no address, deactivated) are wired but NOT TESTED. | 32f86f9b |
| 12 Harm words + translation | Done. Synonyms, negation ("not"/"never" before harmed/injured/hurt/burned/hospitalised/killed; "nobody was", "no one was", "without any", "no sign of"), `may_not_be_english()` shown as the Case's `language_note`; TRANSLATION addendum offered; EMAIL addenda refused on the typed route. The B2 unit test that said "not never negates" now follows G18. `test_intake_rules.py` 21 passed (unit), `test_case_addenda_api.py` 12 passed, `tsc --noEmit` clean. | 0e5eb491 |
| 13 Help, sample, refresh | **Not started.** See "Open for run 4". | - |

**Deviations to note:** times without a zone in a Cases file are read in the organization's zone (said in a note), not refused; the Cases template always masks (no "refuse" choice); unknown versions are refused (unknown product and lot are kept as typed); the backlog Cases are not in the complaint-only "Imported backlog" view (they carry the note on the Cases list and the backlog flag on the triage list).

**Sample story after steps 5-12:** `test_sample_story_days.py` + `test_release_0_10_92.py` + `test_getting_started_part1.py` + `test_flagship_walkthrough.py`: 21 passed, 1 xfailed (tip `0e5eb491`).

**"New code" check (UI vs server):** no change needed. The server's "covered by an open investigation" needs a complaint in that investigation with the same product and code, which is already in the screen's `product_codes`; they differ only when the complaint itself is the only one with the code, and such a complaint is not on the routine path.

**Open for run 4 (finish B7a):**
1. Step 13: help and user guide (Resolve and close, Cases import/export, files on a Case, urgent e-mail, translation); a routine sample complaint in "More cases to try"; the SAMPLE e-mail belongs to B7b. **Refresh for running trials:** their SAMPLE-RT-03 disposition was signed without `customer_told`, so CUSTOMER_TOLD shows open on day 0. Do not edit the signed `service_record`; add a sample communications entry (Sent, Response, through the distributor, at the disposition's signed time) to the complaint's reporter party (closure counts `responses`), as a new `trial/sample_0_10_97.py` `refresh()` wired into `scripts/refresh_trial_story.py` (pattern: `sample_0_10_96.py`, test in the style of `test_release_0_10_96.py`). Then re-run the day-story tests.
2. Settings screen: `PUT /api/v1/oversight/settings/alerts-and-files` has no UI yet (urgent e-mail switch, file storage). The Import screen lists the "cases" template from `/templates` without UI changes (not checked in a browser).
3. Pre-existing failure, not B7: `tests/test_import_row_limit.py::test_an_over_limit_csv_is_refused_without_reading_every_row` (its fake `csv.reader` has no `line_num`, used since commit 621f5dad).

## Owner decisions on B7 run 3 choices (11 Nov 2026, "approve B7 choices")
1. `oversight_settings.attachment_quota_mb` (default 100, 1–10,240) added to the unreleased tr25 for B7-D16: accepted.
2. Urgent-alert delivery tracked on the notifications outbox event (attempts, retries, dead-letter), not as in-app alert rows: accepted.
3. A time without a zone in a Cases file is read in the organisation's zone and the check says so (instead of refusing the row): accepted.
4. Case import always masked (no 'refuse personal data' choice); unknown version refused, unknown product or lot kept as typed; old imported Cases carry the note on the Cases list and the backlog flag on the triage list: accepted.

## Build status (run 4, 11 Nov 2026)

Branch `feat/b7-routine-path` (worktree `trial-093`), local only, not pushed. Tip `10d6f177`.

| Item | State | Commit |
|---|---|---|
| 13 Refresh for running trials | Done. `trial/sample_0_10_97.py` `refresh()`: when SAMPLE-RT-03's signed disposition has no `customer_told` and the log has no reply, a Sent/Response entry (channel OTHER = through the distributor, at the disposition's signed time, by its signer, `MDARIX_SAMPLE`) goes to the complaint's reporter party (made, fictional, when none exists). The signed record is never edited; idempotent. Wired into `scripts/refresh_trial_story.py` (dry run lists "SAMPLE-RT-03's reply to its reporter (0.10.97)"). `tests/test_release_0_10_97.py`. | 20cf4ffd |
| 13 Routine sample complaint | Done. "More cases to try" lists SAMPLE-RT-01 last ("Routine: resolve and close" / "Resolved" / "Closed in MDARIX"), opening `Complaints › Dispositions?complaint=<id>` (its Resolve and close drawer). No new sample record, so day 0 stays as it was. | 20cf4ffd |
| Settings screen | Done. Settings › **Alerts and files** (new tab in `linkTable.json`): urgent e-mail switch (off by default), file storage in MB (a trial shows 100 MB, read only). Permissions follow the route (`quality.review` or `regulatory.approve`, not "admin": the route's SETTERS). | 20cf4ffd |
| Screens for steps 6-7 (found missing) | Done. The routes had no screen: Cases list gets "Export these cases (CSV)" and "Export for QMS entry (CSV)" (only with `data.export`; masked; no unmask-with-reason in the UI, the API keeps it); the Case check drawer gets a **Files** section (list, download, upload). | 34b3ef04 |
| 13 Help, user guide, CHANGELOG | Done. User guide: Resolve and close, Reopen, closure wording (QMS-owned vs MDARIX-owned), Cases import/export, files, translation, urgent e-mail. CHANGELOG 0.10.97 updated. | c96dee38 |
| Tests left from run 3 | Done: UA-05 (triage reopened on a death queues the alert for the complaint), UA-06 (no address named in `URGENT_EMAIL_QUEUED.no_address`; a deactivated person gets nothing, event done), unmasked Cases export outside a trial (reason ≥ min, audited UNMASKED; executive without `data.export` 403); template test re-run; vitest for FirstContact (language and backlog notes). | c0c55bae, 20cf4ffd |
| Browser journey | Written, **NOT RUN**: `frontend/e2e/resolve-and-close.spec.ts` (log → sign and escalate → Confirm triage → Resolve and close → Closed in MDARIX → Reopen). Type-checks except the missing `@types/node` (the same for every existing spec in this checkout). Selectors are from the source and may need fixing on 30 Nov. | 10d6f177 |
| On/off switch | **Not built: large.** The pattern exists (`backend/app/feature_set.py`: env read per call, `serves_path` 404s parked API routes, session `feature_set` hides screens). A B7a switch would need: a new env flag, the B7a routes in `serves_path`, a session flag, and gating in about eight places (Dispositions drawer opening Resolve and close first, next-step label from the server's event view, Reopen panel, Cases exports, Files, Settings tab, More cases, the Cases import template), and a decision on the CUSTOMER_TOLD closure check when off. Estimate 3-4 h with tests. Owner to decide whether it is needed. | - |

**B7a is complete** (steps 0-7, 11-13), except the optional on/off switch above. Step 14 (scenario run and full gates) belongs to the 24 Nov test release.

**Tests run (targeted, `POSTGRES_DB=mdarix_b2_test`):** `test_release_0_10_97.py` 1 passed; `test_urgent_alert_b7.py` + `test_case_export_b7.py` + `test_import_triage_b2.py::test_the_template_offers_the_qms_triage_columns` 11 passed; story set `test_sample_story_days.py` + `test_release_0_10_92.py` + `test_getting_started_part1.py` + `test_flagship_walkthrough.py` + `test_release_0_10_97.py` 22 passed, 1 xfailed (tip `10d6f177`). Vitest: `b7aSettings.test.tsx` (new) + `caseCheck.test.tsx` + `releaseA071.test.tsx` + `linkTable.test.ts` 51 passed, then `b7aSettings` + `caseCheck` 14 passed after the export and files tests; `casesList`, `intake`, `logCase`, `releaseD3085Pages`, `whyAsked`, `reportingCapa` 50 passed; `src/features/help` 17 passed. `tsc --noEmit`: clean.

**B7b (steps 8-10):** not started (stopped at a clean boundary for context). Before it: the owner confirms the production host accepts inbound mail (port 25); `aiosmtpd` goes into `requirements.in` with hashes.

## Owner decisions on B7 run 4 questions (11 Nov 2026)
1. Build one on/off switch for B7a (feature_set pattern; default ON; ~3–4 h) after B7b, so B7a can be turned off in production without a rollback. Decide in the build: when OFF, the CUSTOMER_TOLD closure check does not apply (the old closing path behaves as before B7).
2. Settings › Alerts and files stays as built: quality review or regulatory approve rights may change it.
3. "Unmask contacts with a reason" on the export screen: later (the API offers it).

## Build status (run 5, 11 Nov 2026): B7b e-mail intake

Branch `feat/b7-routine-path` (worktree `trial-093`), local only, not pushed. Tip `dff4a452`. **B7b ships switched OFF**: `MDARIX_EMAIL_INTAKE=on` turns it on (off: the receiver exits without listening, `/api/v1/email-intake/*` answers 404, the session's `email_intake` is false and no screen shows). Production mail (inbound port 25, MX record for `intake.mdarix.com`, STARTTLS certificate) is still an operations task.

| Step | State | Commit |
|---|---|---|
| Merge B3 (row-limit test fix, hardening run 7) | Done, no conflict. `test_import_row_limit.py` + `test_signing_code_refusals.py` 8 passed. | af551e74 |
| 8 `mail-in` receiver | Done. `backend/app/mail_in/` (`receiver.py`, `addresses.py`); `aiosmtpd==1.4.6` in `requirements.in`, lock regenerated with `uv pip compile ... --generate-hashes` (adds `aiosmtpd`, `atpublic`, `attrs` only), pip-audit on the three: no known vulnerabilities. Known tokens only (550; other domains 550, no relay), 25 MB (552), opportunistic STARTTLS when `MDARIX_MAIL_IN_CERT`/`KEY` are set, 451 over 30/h per IP (in memory, one container) or the organisation's `mail_daily_limit`, sender allowlist `mail_allowed_domains` (550). Raw message stored encrypted (`internal=True`), `inbound_messages` row, outbox job `INBOUND_MAIL_RECEIVED`; same Message-ID kept once (a missing one becomes a hash). A storage failure answers 451 so the sender retries. Addresses in `inbound_provider_mappings` (provider `MDARIX_MAIL`, states ACTIVE / OFF / ROTATED (30 days) / RETIRED; no new table). Compose service `mail-in` under the `mail-in` profile (port 25 → 2525, non-root, read-only, health check NOOP). Env vars documented. | 44b6719e |
| 9 Processing | Done. `mail_in/processing.py`, dispatched in `scripts/run_outbox_worker.py`. Auto-reply/bounce → NOT_A_CASE (30 days); attachments: evidence checks + scan, infected never stored and stripped from the raw message (re-stored as `...-clean`), refused ones recorded with the reason, logos < 20 KB ignored, max 10; threading by In-Reply-To/References (message on a Case, or a Case's `channel_ref`) or a Case reference in the subject → "Add to"; same body hash within 7 days → possible duplicate; masked words (HTML reduced, quotes and signature cut); product (name), lot (identifier), serial, GS1 UDI unconfirmed source EMAIL; harm/fault/non-English flags; forwarded Date/Sent lines earlier than receipt → `header_dates`; PGP/S-MIME → "Cannot be read: encrypted". Oversight item `mail:<id>` (TRIAGE, due end of the working day; with harm words due on receipt, sweep run at once → in-app alert) + `urgent_alert.queue` when opted in. | cd7bdbc4 |
| 10 Screens and API | Done except the address screen. `mail_in/router.py`: list, add-to-case (EMAIL addendum, files move, `_new_information` hook), not-a-case (reasons; harm/fault words need `quality.review`, refusal audited `EMAIL_NOT_A_CASE_REFUSED`), raw view (OD-1 `CONTACT_READERS`, audited `EMAIL_RAW_OPENED` / `_REFUSED`), purge on the 15-minute pass (`run_for_all_tenants`; row kept as PURGED, raw and files deleted), Customer Admin settings API (GET/PUT, rotate; a trial gets 409 `TRIAL_NO_ADDRESS`). Make it a case = `POST /api/v1/intake` with `inbound_message_id` (channel EMAIL, `channel_ref` = Message-ID, Received = server receipt; payload values for these are overridden). Trial SAMPLE e-mail created on first list (fictional CityCare/PulseWatch, no harm words). Screen: `EmailToCheck.tsx` panel on Cases › First contact (flat cards), Log a case drawer pre-filled with a note. Playwright `frontend/e2e/email-to-case.spec.ts` written, NOT RUN (type-checks except the missing `@types/node`, as every spec). | dff4a452 |

**Tests run (targeted, `POSTGRES_DB=mdarix_b2_test`):** `test_mail_in.py` 7 passed (EM-01, 05, 10, 14, 16, 18, allowlist, 552); `test_mail_processing.py` 8 passed (EM-02, 04, 06, 07, 08, 09, 11, 13, 17, encrypted); `test_mail_processing.py` + `test_oversight_api.py` + `test_outbox_resilience.py` 24 passed; `test_email_intake_api.py` + `test_mail_processing.py` 15 passed (EM-03, 12, 15, purge, sample, switch off); `test_infra_compose.py` + `test_environment_reference.py` 36 passed, 1 failed (pre-existing: `MDARIX_ALERT_FALLBACK_WEBHOOK` and `MDARIX_EXPORT_MAX_BYTES` from the hardening merge are undocumented; not B7). Vitest `emailIntake.test.tsx` (new, 4) + `caseCheck.test.tsx` 12 passed; `tsc --noEmit` clean. Story set `test_sample_story_days.py` + `test_release_0_10_92.py` + `test_getting_started_part1.py` + `test_flagship_walkthrough.py` + `test_release_0_10_97.py`: 22 passed, 1 xfailed (tip `dff4a452`). `test_case_addenda_api.py` + `test_case_attachments.py` 16 passed.

**Not built / deviations (for the owner):**
1. **Settings screen for the intake address** (copy, on/off, rotate, allowlist, forwarding help): the API exists and is tested; no screen. Customer Admin is not a business permission, so it needs a place in the Customer Admin area (about 2 h).
2. "Not a case" on harm/fault words: only a quality reviewer may choose it, but "not the person who opened it" is not enforced (no record of who opened a message).
3. Site suggestion from the sender's domain: not built.
4. "The Customer Admin is told once a day" when a limit is reached: only logged by the receiver.
5. Polling fallback (B7-D8 option B): not built (only if port 25 cannot be opened).
6. Shortcuts marked in code: per-IP limit per process; a processing job lost between the two commits leaves a message "Being checked" (re-queue from the sweep if seen).
7. Operations before turning it on: inbound port 25, MX record, certificate in `MDARIX_MAIL_IN_CERT_DIR`, `MDARIX_EMAIL_INTAKE=on` on api, background and mail-in, `docker compose --profile mail-in up -d`.

**B7b is complete except the address Settings screen (item 1); B7 as a whole is therefore not quite complete.** Left: that screen, then the B7a on/off switch the owner asked for after B7b (owner decisions on run 4, item 1), then step 14 in the 24 Nov test release.

## Build status (run 6, 11 Nov 2026): B7 closed

Branch `feat/b7-routine-path` (worktree `trial-093`), local only, not pushed. Tip `b6ad14c6`.

| Item | State | Commit |
|---|---|---|
| 0 Merge B3 (environment-doc fix) | Done, no conflict. `test_environment_reference.py` + `test_infra_compose.py` 37 passed (the run-5 failure is gone). | d65a6352 |
| 1 Intake address screen | Done. Customer administration › **Organization** › "E-mail intake" panel (`customer-admin/sections/EmailIntake.tsx`), shown only when the session's `email_intake` is true: the address with Copy, state, old address with its last day, Turn on/off, Rotate (confirm: old address works 30 days), allowed sender domains, messages a day, how to forward a mailbox. A trial sees "no real address, try the SAMPLE e-mail". Flat (G-2). Placed in Organization (not parked under `mvp`, organisation-level), not in Integrations (parked under `mvp`). | b3f1db2e |
| 2 "Not a case" opener rule | Done. The first person to list a NEW message to check is recorded as its opener (`inbound_messages.flags.opened_by` / `opened_at`; no new column). On harm/fault words, outside a trial, the opener is refused: 403 `SAME_PERSON`, audited `EMAIL_NOT_A_CASE_REFUSED` (`why: SAME_PERSON`). | e19623b9 |
| 3 B7a on/off switch | Done. `MDARIX_ROUTINE_PATH` (on unless `off`) in `feature_set.py`; `serves_path(path, method)` 404s resolve-and-close (GET/POST), both Cases exports, POST attachments, alerts-and-files. Session `routine_path`; screens: Dispositions drawer reads the plain `/disposition` (no Resolve and close), no exports, no upload (existing files readable), no Alerts and files tab, no routine sample in More cases, server next step not "Resolve and close"; Cases import template not offered; no urgent e-mail queued; closure checklist has no CUSTOMER_TOLD. Documented in `ENVIRONMENT_VARIABLES.md`. | c922d757 |
| CHANGELOG 0.10.97 | Done. | b6ad14c6 |

**Deviation (for the owner):** with B7a off, `POST /complaints/{id}/reopen` stays served and the complaint page keeps "Closed in MDARIX" + Reopen, so a complaint MDARIX already closed can still be reopened (otherwise it would be stuck closed). The Files list (GET) also stays, because B7b e-mails move files onto Cases.

**Tests run (targeted, `POSTGRES_DB=mdarix_b2_test`):** `test_environment_reference.py` + `test_infra_compose.py` 37 passed (twice); `test_email_intake_api.py` 8 passed; `test_routine_path_switch.py` (new) 4 passed; story set `test_sample_story_days.py` + `test_release_0_10_92.py` + `test_getting_started_part1.py` + `test_flagship_walkthrough.py` + `test_release_0_10_97.py` 22 passed, 1 xfailed; `test_resolve_and_close.py` + `test_email_intake_api.py` + `test_urgent_alert_b7.py` + `test_case_import_b7.py` + `test_case_attachments.py` + `test_case_export_b7.py` 34 passed. Vitest `customer-admin/emailIntake.test.tsx` (new) 4 passed; `b7aSettings.test.tsx` 7 passed (OFF case added); `releaseA071` + `resolveClose` + `disposition` + `caseCheck` + `workspace/emailIntake` + `customer-admin/emailIntake` 49 passed. `tsc --noEmit` clean.

**All of B7 is complete** (B7a steps 0-7, 11-13 and the switch; B7b steps 8-10 and the address screen). Step 14 (scenario run, Playwright journeys `resolve-and-close.spec.ts` and `email-to-case.spec.ts`, full gates) belongs to the 24 Nov test release. Still open from run 5 (not in this brief): site suggestion from the sender's domain, the once-a-day Customer Admin notice on a reached limit, the polling fallback, user-guide pages for B7b (none exist yet), and the operations to turn e-mail intake on.

**Risk to note:** "opened" is "first to see it in the list". In a team with one quality reviewer, if that reviewer lists the messages before anyone else, they cannot mark a harm/fault-word message "Not a case": it must become a Case (the safe direction) or another quality reviewer decides.

## Build status (leftovers run, 11 Nov 2026): B7b open items 3, 4 and the B7b user guide

Worktree `trial-093`, local only, not pushed. On `feat/b7-routine-path`, then merged `--no-ff` B7 -> `feat/b5-challenge-loop` (`f200fac9`) -> `feat/b4-rule-register` (`0a78ce95`). No migration.

| Item | State | Commit |
|---|---|---|
| Site suggestion from the sender's domain (run 5 item 3) | Done. Processing keeps `draft.site` (`mail_in/processing.py site_suggestion`): an organization party that is not a reporter (hospital, distributor, service partner) with a non-erased contact address at the sender's exact domain, else the reporter site of the newest Case made from an e-mail of that domain; none for personal mail providers (the trial sign-up's `PERSONAL_MAIL_DOMAINS`). Marked `UNCONFIRMED`, source `EMAIL_DOMAIN`; the list returns it as `site_suggestion`. Log a case (from an e-mail) opens Customer and shows "Suggested from the sender's domain (unconfirmed): ... Use it"; the field is never filled by itself. | 5e6d8295 |
| Daily notice to the Customer Admin on a reached limit (run 5 item 4) | Done. The receiver's 451 over the organization's daily limit calls `notify_mail_intake_limit`: outbox event `MAIL_INTAKE_LIMIT_REACHED`, at most one per organization and UTC day (checked first; the event id is `uuid5(tenant, day)` so two receiver threads cannot both queue it). Delivered to the customer administrators (`send_mail_intake_limit_notice`). A failure to queue is logged and never changes the refusal. The per-IP limit (30/h) sends no notice (it is not the organization's limit). | 9d0923fb |
| User-guide pages for B7b | Done. "Turn an e-mail into a case: E-mail to check" (Complaints section: the list and its chips, Make it a case with the site suggestion, Add to CALL-..., Not a case and the quality-reviewer/opener rule, Open the original for the contact roles, intake off until the address is set up, 30-day purge, SAMPLE e-mail) and "Set up the e-mail intake address (customer administrators)" (Team section: Admin console Organization > E-mail intake, Turn on, Copy, forwarding, allowlist, messages a day and its once-a-day e-mail, Rotate, Turn off). The guide-path test counts `Organization` as an Admin console section, like Users and Security. CHANGELOG 0.10.97. | 7964a1cc |

**Tests run (targeted, `POSTGRES_DB=mdarix_b2_test`):** on B7: `test_mail_processing.py` + `test_mail_in.py` 16 passed (new: site suggestion; EM-10 extended: one notice however often refused); `test_notifications_delivery.py` + `test_email_intake_api.py` 27 passed (new: limit notice once a day to the customer administrators; wording test). Vitest `workspace/emailIntake.test.tsx` + `linkTable.test.ts` + `logCase.test.tsx` + `src/features/help`: 7 files, 50 passed; `tsc --noEmit` clean. On `feat/b4-rule-register` after all merges: story set (`test_sample_story_days.py`, `test_release_0_10_92.py`, `test_getting_started_part1.py`, `test_flagship_walkthrough.py`, `test_release_0_10_97.py`) 22 passed, 1 xfailed; `test_complaint_page.py` + `test_mail_processing.py` + `test_mail_in.py` + `test_notifications_delivery.py` 45 passed; vitest `linkTable.test.ts` + `workspace/emailIntake.test.tsx` 27 passed.

**Still open from run 5:** the polling fallback (only if port 25 cannot be opened) and the operations to turn e-mail intake on. **Limits:** the site match is the exact sender domain (a sub-domain such as `ward.hospital.example` does not match `hospital.example`); "once a day" is the UTC day.

## Approval record

| Field | Value |
|---|---|
| Approved | 10 Nov 2026 |
| Approver | Srinivas Telikicherla, Founder & CEO, QA/RA (owner) |
| Approval words, as recorded | "approve B7 spec"; later choices "approve B7 choices" (11 Nov 2026) |
| Where recorded | sections "Owner approval (10 Nov 2026)" and "Owner decisions on B7 run 3 choices" |
| Planning copy | `MDARIX-planning/b7-routine-path/spec.md` (reference only) |
| Form of approval | The owner's written reply, recorded in the spec on the day; not an electronic or wet signature. This section was added on 12 Nov 2026 (owner decision O29); the approved text above is otherwise unchanged, except that a DRAFT status line now reads APPROVED |
