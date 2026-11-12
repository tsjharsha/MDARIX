# Other countries: decision tree and "Other Regulatory Report" (APPROVED)

Version of 9 Nov 2026. Requirement from the owner (9 Nov 2026). **APPROVED by the owner on 9 Nov 2026** ("approve OC spec"; OC-D3: no second-person approval; OC-D5: B9b). Development starts only on the owner's green signal when B9b's turn comes.

## 1. The requirement (owner's words, condensed)
- Today MDARIX supports five markets: US, EU (with Northern Ireland), Great Britain, Canada and India.
- For **any other country**, add an **"Other country" decision tree**: the user picks the country, and reportability is decided by that tree's logic.
- When reportability is **Yes**, MDARIX creates a record named **"Other Regulatory Report"**. There is **no form to fill**. The customer attaches the report they already made, with the **Report ID** and **Status**.
- When the authority's **acknowledgement** arrives, the customer updates the status.
- If a **follow-up** is needed, the customer creates a follow-up and attaches the follow-up report, with its own ID and status.

## 2. What exists today (code at v0.10.92) and is reused
| Need | Existing part | Reuse |
|---|---|---|
| Per-market decision with Yes / No / Unknown / N/A answers, a rationale per answer, a suggested conclusion that a person confirms and signs; Unknown is never No | `reportability/markets.py` (starter question set per market, versioned) | Add one more question set, `OTHER`, with a country chosen per assessment |
| One record per report owed, with a due date | `report_obligations` (`market`, `kind`, `parent_id`, `form_code`, `form_version`, `state`, `due_on`) | `form_code = "ATTACHED"` (no form), market `OTHER` plus a country code |
| Submission with the authority's reference and a result | `report_submissions` (`authority_reference`, `result` PENDING / ACCEPTED / REJECTED / NO_ACK_EXPECTED, `route`, `late`) | Report ID = `authority_reference`; acknowledgement = `result` |
| Attached files: the report itself, the receipt, the acknowledgement | `report_evidence` (outcomes CONTENT / RECEIPT / ACCEPTED / REJECTED), ClamAV scan | The customer's report = CONTENT; acknowledgement = ACCEPTED or REJECTED |
| Follow-up as a child of the first report | `parent_id` on `report_obligations` (today `kind` is INITIAL or RESPONSE) | Add `kind = FOLLOW_UP` |

So no new tables. One small additive migration: a `country` column (ISO 3166 code) on the market assessment and the obligation, and `FOLLOW_UP` in the kind check.

## 3. Design
### 3.1 The "Other country" decision tree
- **Country picker:** every ISO 3166 country **except** those covered by the five markets (the EU 27 and Northern Ireland go to the EU tree; England, Scotland and Wales to GB). Countries are stored as codes (existing code lists).
- **Questions:** one generic starter set built on the criteria common to most regulators (IMDRF / GHTF style): death; serious deterioration in health; could have led to death or serious deterioration if it happened again; serious public health threat; device malfunction or deterioration; use error; whether the device is marketed in that country. The wording is starter text until the regulatory consultant confirms it, as for the other markets.
- **Same rules as the five markets:** Yes / No / Unknown / N/A with a rationale; Unknown is never No ("Needs more information"); a person confirms the conclusion and signs; the MDARIX floor is raise-only.
- **Per-country tightening (later, with B4/B4b):** the customer can add questions or lower thresholds for a specific country (for example Australia, Switzerland, Japan) without changing the generic floor.

### 3.2 Due date
There is no built-in reporting window for other countries. The customer enters the window once per country (days, and whether day 0 or day 1 counts) in the reporting-window settings that already exist for the five markets. If no window is set, the user enters a due date on the record, and it shows **"Due date entered by the customer"**. Deadline alerts and the Overdue filter treat it like any other report.

### 3.3 The "Other Regulatory Report" record
| Status | What the user does | What MDARIX requires |
|---|---|---|
| **To be submitted** | Created automatically when the country's conclusion is Reportable | Owner and due date shown on the Case/complaint |
| **Submitted** | Attaches the report file and enters the **Report ID** (the authority's or their own reference) and the submission date | File + date mandatory; Report ID mandatory or "Not issued yet"; the person who records it signs |
| **Acknowledged** / **Rejected by authority** | Attaches the acknowledgement and enters its date and reference | Acknowledgement file or a note saying none was received |
| **Follow-up required** | Creates a **Follow-up report** (child record) | — |
| **Closed** | Closes when no follow-up is open | A reason if closed without an acknowledgement |

A **Follow-up report** has the same fields and statuses (file, Report ID, status, acknowledgement) and stays linked to the first report. Several follow-ups are allowed.

**Files:** scanned on upload (ClamAV, as today); never overwritten (a new file is a new version, the old one stays); any common type (PDF, Word, image, XML). A corrupt file is marked unusable as evidence (B2 rule A7).

**Audit:** every status change, file and reference is in the audit trail with who, when and why. The record shows "Report prepared outside MDARIX; MDARIX holds the copy as attached".

### 3.4 Where it shows
- On the complaint's **Reportability** tab: the Other-country assessment next to the five markets.
- In **Authority reports**: listed with the others, filter "Other countries", with the country name.
- In the Cases list filters and the deadline dashboard (Overdue, Due this week).
- In the inspection pack and record exports.

## 4. Scenarios to add to the register (OC-xx)
OC-01 a country outside the five markets can be chosen, and an EU or GB country is redirected to its own tree. OC-02 Reportable creates one Other Regulatory Report. OC-03 Unknown never gives Not reportable. OC-04 Submitted needs a file and a date. OC-05 Report ID "Not issued yet" is allowed and can be filled in later. OC-06 an acknowledgement updates the status and keeps the file. OC-07 a follow-up is linked to its parent and has its own ID and status. OC-08 several follow-ups. OC-09 Closed is refused while a follow-up is open. OC-10 a due date from the country window and from manual entry, with its label. OC-11 overdue alerts. OC-12 a file is never overwritten. OC-13 an infected or corrupt file is refused or marked unusable. OC-14 another organisation's record cannot be seen or changed. OC-15 the inspection pack lists the reports and files.

## 5. Placement and effort (estimate)
- **Release:** after **B9** (Canada, India, US importer and user facility), as **B9b "Other countries"**, so the five built-in markets are finished first. It does not depend on B4 (rules engine), and the per-country tightening arrives with B4/B4b.
- **Not before the WHIF freeze** (4–12 Dec).
- **Effort (estimate, not measured):** about 6–8 developer days: migration and models (1); the question set and country picker (1.5); the record, statuses, follow-ups and files (2); screens and filters (1.5); tests and scenarios (1–2).
- **Migration name:** next free `tr2x…` after DB-1 (`tr21`–`tr24`), and follows the 8 Nov database rules (composite tenant keys, indexes, timestamps with time zone).

## 6. Decisions (approved 9 Nov 2026)
| # | Decision | Recommendation |
|---|---|---|
| OC-D1 | One generic question set for all other countries (with per-country tightening later) or a separate tree per country | **One generic set now**; per-country tightening with B4/B4b |
| OC-D2 | Who sets the due date | **Customer sets a window per country once**; otherwise a manual due date, labelled |
| OC-D3 | Does recording "Submitted" need a second person's approval, as the built-in forms do | **APPROVED: no second-person approval.** The person recording it signs. No organisation option is built |
| OC-D4 | Is the Report ID mandatory at Submitted | **Mandatory or "Not issued yet"**, to be filled in later |
| OC-D5 | Release | **B9b, after B9**, not before WHIF |
