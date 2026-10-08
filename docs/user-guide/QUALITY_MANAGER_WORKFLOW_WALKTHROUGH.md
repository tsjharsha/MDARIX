# How a case moves through MDARIX: a step-by-step walkthrough

This walkthrough is for anyone who wants to understand what happens in MDARIX from the moment complaint data arrives until a decision is signed and the case is closed. No quality or software background is needed.

It follows one **Quality Manager** through one example case. In MDARIX the Quality Manager holds the **Leader** role, which allows every step in the workflow. In a real team most steps are done by colleagues, and the Quality Manager oversees them, steps in when needed, and handles escalations. Each step below says who normally does it.

> **What MDARIX is, and is not.** MDARIX helps people investigate problems with medical devices. It collects the facts, keeps them organized and shows what is still unknown. It **never decides for you**: people decide, and authorized people sign. It does not replace your quality management system and does not send anything to a regulator.

---

## The example used throughout

*All names and data in this example are invented.*

> A company makes an infusion pump called **Aster Pump** (version 2.1). Over three weeks, hospitals report that the pump sounds a false "blockage" alarm and stops. The Quality Manager, **Maya**, must find out whether something is wrong with the pump, how serious it is, and what the company should do.

---

## The whole journey on one page

```
  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
  │ 1. DATA       │──►│ 2. SPOT A     │──►│ 3. OPEN A     │──►│ 4. COLLECT    │
  │ comes in      │   │ PROBLEM       │   │ CASE          │   │ THE FACTS     │
  │ (complaints,  │   │ (Signals)     │   │ (Investigation│   │ (Scope and    │
  │ products...)  │   │               │   │ is created)   │   │ Evidence)     │
  └──────────────┘   └──────────────┘   └──────────────┘   └──────┬───────┘
                                                                   │
  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────▼───────┐
  │ 8. CHECK THE  │◄──│ 7. DECIDE     │◄──│ 6. WRITE IT UP│◄──│ 5. WORK OUT   │
  │ FOLLOW-UP AND │   │ AND SIGN      │   │ AND GET IT    │   │ WHAT HAPPENED │
  │ CLOSE         │   │ (Decisions)   │   │ CHECKED       │   │ (Intelligence,│
  │ (Trust &      │   │               │   │ (Decision     │   │ risk and      │
  │ Audit)        │   │               │   │ Brief)        │   │ regulatory    │
  └──────────────┘   └──────────────┘   └──────────────┘   │ reviews)      │
                                                            └──────────────┘
```

The case's **status** changes as it moves along. The status is shown on every case:

```
  Open ──► In progress ──► Brief in review ──► Ready for decision ──► Decided ──► Closed
              │   ▲               │
              ▼   │               │ brief sent back for more work
            On hold ◄─────────────┘ (returns to "In progress")

  A case can also be Cancelled (for example, opened by mistake). Nothing is ever deleted.
```

---

## Who does what

| Person (role in MDARIX) | In plain words | Steps |
|---|---|---|
| **Customer Administrator** | Sets up the organization: user accounts, permissions, data connections. Never works on cases and never signs. | Before step 1 |
| **Signal Triage Lead** | Looks at incoming complaints and trends, and decides which ones need investigating. | 2, 3 |
| **Quality Investigator** | The "detective": collects the facts, works out what happened, writes the report. | 4, 5, 6 |
| **Risk Reviewer** | Checks how dangerous the problem is for patients. | 5 (when needed) |
| **Regulatory Reviewer** | Checks whether authorities must be told. | 5 (when needed) |
| **Quality Reviewer** | Checks that the report is complete and sound before anyone decides. | 6 |
| **Authorized Decision Maker** | Makes and signs the final decision. | 7 |
| **Quality Manager (Leader)** | Can do every one of the steps above, and receives escalated problems. | All |

**Two safety rules everyone must know:**
1. **Nobody checks or signs their own work.** Whoever wrote the report (the Decision Brief) cannot review it and cannot sign the decision on it, even if they are the Quality Manager.
2. **A signature needs two proofs:** the person's password **and** a code from the authenticator app on their phone.

So the smallest possible team is **two people plus an administrator**: one person collects the facts and writes the report, a second person checks it and signs.

---

## Before step 1: the organization is set up (Customer Administrator)

```
  Administrator                                Maya and colleagues
  ─────────────                                ───────────────────
  1. Sets up their own sign-in + phone code
  2. Invites colleagues, gives each a role ──► receive an email, choose a password,
                                               set up the phone code
  3. Decides whether AI may be used (off by default)
  4. Connects company systems, or lets people import files
```

AI is **switched off** when an organization starts. If the administrator switches it on, MDARIX shows exactly what will be sent and to whom. Personal details such as patient names are hidden before anything is sent.

---

## Step 1: Bring the data in

**Who:** Quality Manager, Quality Investigator, or anyone allowed to change records.
**Where:** *Import data* (or automatically, through a connection to the company's systems).

MDARIX needs to know the company's products and the complaints about them. Files are loaded in a fixed order, because later files refer to earlier ones:

```
  ① Products  ──►  ② Lots (batches)  ──►  ③ Complaints  ──►  ④ Everything else
  "Aster Pump       "Lot 2024-117 was      "Hospital X:       (parts, suppliers,
   version 2.1"      made in May"           false alarm,       changes, risks,
                                            lot 2024-117")     CAPAs...)
```

For each file:

```
  Download the template ──► Fill it from your own system ──► "Check file"
                                                                  │
                         ┌────────────────────────────────────────┤
                         ▼                                        ▼
               Problems found:                             No problems:
               MDARIX lists every one,                     "Import" saves the rows
               nothing is saved yet                        and records the import
                         │                                 in the audit trail
                         ▼
               Fix the file and check again, or choose
               "import the rows that pass" and download
               the rest to fix later
```

Personal details (names, phone numbers, emails, record numbers) should not be in the files. If they are, MDARIX refuses the file, or replaces them with placeholders such as **[PERSON]** if you choose that option.

> **Example:** Maya imports the Aster Pump product, its lots, and 40 complaints from the last quarter. Five of them describe a false blockage alarm.

---

## Step 2: Spot a problem (Signals)

**Who:** Signal Triage Lead (or the Quality Manager).
**Where:** *Dashboard* and *My Work* show what needs attention; *Signals* holds the list.

A **signal** means "something here may need attention". It is not yet a conclusion. Signals come from:
- single complaints, and
- **trends**: by default, three related complaints within 30 days automatically raise a signal.

> **Example:** The five blockage-alarm complaints arrive within three weeks, so MDARIX raises signal **SIG000012** for Aster Pump 2.1.

The triage lead opens the signal, sets how urgent it is (low, medium, high or critical), and decides what it needs:

```
                         ┌─► Monitor          keep watching, no case yet
                         ├─► No action        not a real problem, with a reason
  New signal ──► Triage ─┼─► Duplicate        same as another signal (linked, never deleted)
                         ├─► Investigate  ──► go to step 3
                         └─► Escalate         treated as critical
```

---

## Step 3: Open a case (Investigation)

**Who:** Signal Triage Lead or Quality Manager.
**Where:** from the signal, "Create investigation" (or *Investigations*, "Open an investigation").

The case gets a number, takes over the signal's urgency, and is given to a Quality Investigator. The signal stays linked to the case until the case closes.

> **Example:** Maya marks the signal "Investigate", priority **High**. Case **INV000031** is created and assigned to investigator Sam. Sam sees it in *My Work*.

From here on, the **context bar** at the top of each page (product, version, case) keeps every screen focused on Aster Pump 2.1 and INV000031.

---

## Step 4: Collect the facts (Scope and Evidence)

**Who:** Quality Investigator.
**Where:** the case in *Investigations* (Scope tab) and *Evidence*.

**4a. Scope: what does this case cover?**
Sam records which products, versions, lots and complaints belong to the case. Saving the first scope starts the case: its status becomes **In progress**. Every later change to the scope is saved as a new version with a reason, and the earlier versions are kept.

**4b. Evidence: what do we know?**
Sam links each piece of evidence (test reports, manufacturing records, supplier certificates, service logs) and gives each one a verdict:

```
  Each piece of evidence is marked as:
    Accepted  /  Accepted with a limitation  /  Rejected  /  Quarantined  /  Replaced by newer
  and as:
    Supports the explanation  /  Contradicts it  /  Only background
```

Evidence is never removed from a case. Rejected items stay visible with the reason.

**4c. Missing evidence: ask for it.**
Sam sends an **evidence request** to a colleague, a team, or a supplier. The answer comes back into the case and is reviewed like any other evidence. An urgent request that is still open blocks the report in step 6.

> **Example:** Sam links the pump's alarm log and the lot 2024-117 production record, and asks the supplier of the pressure sensor for its test certificate.

---

## Step 5: Work out what happened (Intelligence and reviews)

**Who:** Quality Investigator; Risk Reviewer and Regulatory Reviewer when needed.
**Where:** the case's *Intelligence* and *Reviews* tabs; *Ask MDARIX*.

**5a. Possible explanations.**
Sam writes down:
- **hypotheses**: possible causes, such as "the pressure sensor from the new supplier is too sensitive";
- **unknowns**: what we still do not know;
- the **failure chain**: what led to what;
- **observations**.

If AI is switched on, the AI's suggestions appear **beside** Sam's own notes, exactly as the AI wrote them, each pointing to its evidence. Sam records a judgement on each one (supported, contradicted, retired and so on). Nothing is ever marked as "confirmed" automatically.

**Ask MDARIX** answers questions such as "Which lots used the new sensor?" from the company's own records, and lists where each answer came from.

**5b. Extra reviews, when the problem could be serious.**

```
  Is a risk review needed?           yes, if the case is High or Critical,
                                     or a complaint mentions serious injury or death
  Is a regulatory review needed?     yes, if a complaint mentions death, serious injury
                                     or a malfunction, or the case is Critical
```

Sam requests the reviews. The Risk Reviewer and the Regulatory Reviewer complete them. If a reviewer asks for more evidence or raises a concern, the case waits until a new review is completed.

> **Example:** The case is High, so a risk review is required. Pumps that stop can delay a patient's medication, so the complaints count as malfunctions and a regulatory review is also required. Both reviewers complete their reviews.

---

## Step 6: Write it up and get it checked (Decision Brief)

**Who:** Quality Investigator writes; Quality Reviewer checks.
**Where:** the case's *Decision Brief* tab.

**6a. Sam writes the Decision Brief**, a short report with:
- the problem;
- the evidence;
- the explanations considered;
- what is still unknown;
- the proposed conclusion.

**6b. Sam submits it.** MDARIX first checks that nothing is missing:

```
  ✓ Scope is complete              ✓ No urgent evidence request is still open
  ✓ Evidence has been reviewed     ✓ Required risk and regulatory reviews are done
  ✓ Problem and proposed conclusion are filled in
```

If anything is missing, MDARIX says what it is. Once the brief is submitted, it is **frozen**: it cannot be changed without creating a new version, and MDARIX stores a digital fingerprint of its content. The case status becomes **Brief in review**.

**6c. A Quality Reviewer, who did not write it, checks it** and chooses one of four outcomes:

```
                       ┌─► Accept for decision   ──► status "Ready for decision", go to step 7
                       ├─► Return to the author   ──► Sam gets a task: "add evidence / analysis /
  Submitted brief ─────┤                              risk review / regulatory review"
                       ├─► Reject the conclusion  ──► back to work
                       └─► Escalate              ──► goes to the Leaders (the Quality Manager)
  Every outcome except "Accept" needs a written comment.
```

> **Example:** Reviewer Priya accepts the brief. It moves to the decision makers' queue.

---

## Step 7: Decide and sign (Decisions)

**Who:** Authorized Decision Maker, or the Quality Manager if they did not write or edit the brief.
**Where:** *Decisions*, under *Approvals*.

```
  ① Open the accepted brief and the case behind it
  ② Confirm you have read the remaining unknowns
  ③ Choose the outcome:
       • Accept the conclusion
       • Accept with conditions
       • Reject the conclusion (case goes back to work)
       • Close with no further action
  ④ Write your remarks
  ⑤ Sign with: password + code from your phone
```

MDARIX **refuses** the signature if:
- the person has no authority to sign;
- the person wrote or edited the brief;
- the brief changed after it was accepted.

Five wrong phone codes lock signing for 15 minutes.

The signature records **who** signed, **what** it means, **when**, which brief version, and a fingerprint of everything it covered. A signed decision is never edited; if needed, a later decision replaces it. The case status becomes **Decided**.

Anyone in the organization can use **Verify a signature** to confirm that what was signed has not changed since.

> **Example:** Maya did not write the brief, so she can sign. She chooses "Accept with conditions": replace the sensor in affected lots, and reassess the risk. She signs with her password and phone code.

---

## Step 8: Follow up, close, and keep the record (Trust & Audit)

**Who:** the people assigned to each follow-up; the Quality Manager oversees.
**Where:** *My Work*, the case's *CAPAs* tab, *Trust & Audit*.

```
  Signed decision
        │
        ├─► Follow-up tasks are created automatically for the right roles:
        │     CAPA (corrective action), product change, field action review,
        │     risk reassessment, regulatory action
        │
        ├─► New evidence arrives after the decision?
        │     MDARIX asks for an impact assessment.
        │     If the impact is material, the case is reopened.
        │
        └─► All closure checks pass ──► status "Closed"
```

**Trust & Audit** keeps the permanent record of every case:

| Tool | What it shows |
|---|---|
| Timeline | Every action, by whom and when |
| Replay | What was known at any moment in the past |
| AI runs | Every AI analysis, with its inputs and results |
| Integrity check | Proof that the record has not been tampered with |
| Export | A copy of the case record, and the export is itself recorded |

> **Example:** A CAPA task to replace the sensor goes to the quality team, and a risk reassessment task goes to the Risk Reviewer. Two months later the supplier's new certificate arrives. MDARIX asks for an impact assessment, and Sam records "no material impact". When all follow-ups are done, the case closes. An auditor can later replay exactly what Maya knew when she signed.

---

## The complete flow in one diagram

```
 ADMINISTRATOR  │ set up users, roles, phone codes, AI choice, data connections
 ───────────────┼──────────────────────────────────────────────────────────────────────
 ANYONE WHO     │ Import data: products → lots → complaints → others  (check, then import)
 CHANGES DATA   │                    │
 ───────────────┼────────────────────▼─────────────────────────────────────────────────
 TRIAGE LEAD    │ Signal raised ──► Triage ──► "Investigate" ──► Case opened, assigned
 ───────────────┼──────────────────────────────────────────────────────┬───────────────
 INVESTIGATOR   │ Scope ──► Evidence (+ requests) ──► Explanations ──► Decision Brief ──► Submit
                │                                         │                 ▲            │
 ───────────────┼─────────────────────────────────────────▼─────────────────┼────────────┼──
 RISK / REG.    │                              Risk / regulatory reviews     │            │
 REVIEWERS      │                              (only when needed)            │            │
 ───────────────┼───────────────────────────────────────────────────────────┼────────────▼──
 QUALITY        │                                               Return ◄────┴─ Quality review
 REVIEWER       │                                                                  │ Accept
 ───────────────┼──────────────────────────────────────────────────────────────────▼──────
 DECISION MAKER │                                          Decide + sign (password + phone code)
                │                                                                  │
 ───────────────┼──────────────────────────────────────────────────────────────────▼──────
 EVERYONE       │ Follow-up tasks (CAPA, risk, regulatory) ──► Closure ──► Trust & Audit
 ───────────────┴──────────────────────────────────────────────────────────────────────

 QUALITY MANAGER (Leader): can stand in at any lane, receives escalations,
                           but never reviews or signs a brief they wrote.
```

---

## Words used in this document

| Word | Meaning |
|---|---|
| **Complaint** | A report from a customer or hospital that something went wrong with a product. |
| **Signal** | A flag that something may need attention: one complaint, or several similar ones in a short time. |
| **Investigation / case** | The piece of work to find out what happened and what to do. |
| **Scope** | Which products, versions, batches and complaints the case covers. |
| **Lot** | A batch of products made together. |
| **Evidence** | Any record that helps explain the problem: tests, logs, certificates. |
| **Hypothesis** | A possible explanation, not yet proven. |
| **Decision Brief** | The short report that summarizes the case and proposes a conclusion. |
| **CAPA** | Corrective and Preventive Action: the fix for this problem, and the change that stops it happening again. |
| **Electronic signature** | A legally meaningful approval made in the software with a password and a phone code. |
| **Audit trail** | The permanent, tamper-evident record of who did what and when. |

---

## Three things MDARIX always guarantees

1. **People decide, not the software.** The AI suggests and shows its sources; it never concludes a cause or makes a decision.
2. **Nothing disappears.** Rejected evidence, earlier scopes, earlier brief versions and replaced decisions all stay in the record.
3. **No one approves their own work.** The author of a report never checks or signs it.
