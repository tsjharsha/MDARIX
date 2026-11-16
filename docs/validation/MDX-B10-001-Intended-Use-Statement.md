# MDX-B10-001 Intended Use Statement

| Field | Value |
|---|---|
| Document ID | MDX-B10-001 |
| Title | MDARIX Intended Use Statement |
| Version | 0.1 DRAFT |
| Owner | Srinivas Telikicherla (QA/RA) |
| Author | Drafted for review |
| Date | 8 Nov 2026 |
| Status | DRAFT |
| Code baseline | v0.10.92 (tag, 7 Nov 2026) |
| Approval | |

## 1. Purpose
This document states what MDARIX is for, who uses it, how it is used, and what it is not. It is the starting point for the Validation Plan (MDX-B10-003), the software risk assessment (MDX-B10-004) and each customer's own validation. A customer writes its own intended use for its own processes. This statement describes the product, not any one customer's use of it.

## 2. Scope
- The MDARIX web application and its background service, release 1.0 (scope frozen 25 Oct 2026, with the 27–28 Oct changes), and the free-trial edition built from the same code.
- Both operating modes: MDARIX Connect and MDARIX Complete.
- Out of scope: MDARIX's website pages, marketing material and demo videos.

## 3. References
| Ref | Document |
|---|---|
| R1 | `MDARIX-planning/b10-assurance-plan.md` (approved 8 Nov 2026) |
| R2 | `MDARIX-planning/operating-modes.md` (decisions M1–M6, approved 7 Nov 2026) |
| R3 | `MDARIX-planning/scenario-register.md` |
| R4 | `MDARIX-R1/docs/compliance/WEBSITE_TRUST_CLAIMS_POLICY.md` (v0.10.92) |
| R5 | `MDARIX-R1/docs/adr/ADR-006-human-authority.md` (v0.10.92) |
| R6 | `MDARIX-R1/backend/app/ai_release_gate.py` (v0.10.92) |
| R7 | MDX-B10-002 Regulatory Applicability Matrix |

## 4. What MDARIX is
MDARIX is **post-market intelligence and decision-support software for medical device manufacturers**. It helps a manufacturer's quality and regulatory team handle complaints and vigilance from the first contact to the closed record, across markets.

### 4.1 What it does
| Function | What MDARIX does | What a person does |
|---|---|---|
| Case intake | Records the first contact (call, e-mail, service record, import). Keeps unknowns as unknown. Flags harm words and urgent cases. Detects possible duplicates. | Enters or confirms the facts. Decides complaint or service only. Signs. |
| Triage | Shows the triage flag, provisional clocks per market, and the fast track for serious cases. | Sets severity. Confirms awareness. Signs. |
| Per-market reportability | Shows each enabled market's question set (US, EU/NI, GB, India, Canada) with its clause. Suggests an outcome from the answers. Counts the legal clock from awareness. Unknown is never treated as No. | Answers the questions. Accepts or overrides the suggestion with a reason. Signs the conclusion. |
| Authority-report preparation | Fills the draft report (FDA 3500A and eMDR file, EU and GB MIR, Health Canada form) only from the approved snapshot. Lists what is missing. | Reviews, approves and **submits through the authority's own route**. Records the submission in MDARIX. |
| Investigation | Holds hypotheses, evidence with its source, unknowns and the decision brief. | Investigates, concludes and signs. |
| CAPA and effectiveness | Holds the QMS CAPA reference (Connect) and the effectiveness check. A native CAPA lifecycle is planned (decision M5). | Decides on CAPA, verifies, and judges effectiveness. |
| Trends | Counts complaints by product, version, lot and supplier. Shows a "pattern to review", never a confirmed signal. | Decides whether a signal exists and what to do. |
| Records and inspection pack | Keeps every version, signature and audit event. Verifies the audit hash chain. Exports a readable record set. | Retrieves records for an audit or inspection. |

### 4.2 Three fixed rules
1. **A person always decides and signs.** Every regulatory conclusion, report approval and closure needs a named person, a fresh authenticator code and a stated meaning.
2. **MDARIX never submits to an authority.** The customer submits through FDA ESG or eSubmitter, EUDAMED or the national route, MHRA, Health Canada or CDSCO/MvPI, and records what was done.
3. **AI is off today.** No AI output reaches any record in release 1.0. AI helpers come in 2027, only after the AI release gate (R6): a contracted provider, a signed-off golden dataset, a passed evaluation and an automatic trust check. AI output will then be a suggestion that a person accepts, edits or rejects.

## 5. Users and personas
Users are trained employees of a medical device manufacturer (or its authorised representative or importer). They are not patients or clinicians.

| Persona (screen name) | Role code | Typical work |
|---|---|---|
| Complaint Handler | TRIAGE_LEAD | Calls, intake, triage, second look |
| Quality Leader | LEADER | Complaints, investigations, CAPA, trends |
| Regulatory Leader | REGULATORY_REVIEWER | Reportability, legal clocks, authority reports |
| Investigator | INVESTIGATOR | Investigations and evidence |
| Risk Reviewer | RISK_REVIEWER | Risk reviews and risk-file input |
| Decision Maker | APPROVER | Approvals and signed decisions |
| Executive | VIEWER | Read only: what needs attention |
| Customer Administrator | CUSTOMER_ADMIN | Users, roles, settings, imports. Never approves a regulated decision. |
| MDARIX Platform Administrator | PLATFORM_ADMIN | Customers, organisations, plans. Reaches customer data only under a customer-approved, time-limited support grant (ADR-015). |

Source: `access_control/personas.py`. The minimum regulated team is two people plus an administrator, so that the maker and the checker differ. A one-person free trial is allowed and labelled "Same person (trial practice)". That is never allowed outside a trial.

## 6. Operating modes
One product and one codebase, set per organisation and per domain (R2).

| Mode | MDARIX's role | System of record |
|---|---|---|
| **MDARIX Connect** | A layer on the customer's QMS, complaint, ERP and service systems | The customer's systems own complaints, CAPA, products and service records. MDARIX keeps a reference copy (read-only master fields) and owns its own decisions, reports and signatures. |
| **MDARIX Complete** | A complete post-market surveillance (PMS) solution | MDARIX owns complaints, service records, vigilance, trends, investigation and (later) CAPA. |

In **both** modes MDARIX owns the reportability decisions, authority reports, trends and investigations. Validation scope grows with the mode: in Complete, MDARIX holds primary regulated records, so retention, archiving and Part 11 controls cover them all.

## 7. What MDARIX is NOT
| MDARIX is not | Reasoning |
|---|---|
| **A medical device** (to confirm with a regulatory consultant) | It has no medical purpose for an individual patient. It does not diagnose, prevent, monitor, treat or alleviate disease or injury, and it does not drive or influence a device. It processes manufacturers' quality and vigilance records. Under FDA's definition (FD&C Act section 201(h)) and the EU MDR (Article 2(1)), and following the MDCG 2019-11 decision steps, it is expected to be software used in the manufacturer's quality system, not a device. Under the QMSR it is quality-system software that the manufacturer must validate for its intended use (ISO 13485:2016 clause 4.1.6). The same is expected under the GB MDR 2002, the Canadian MDR (SOR/98-282) and India's MDR 2017. **To confirm with a regulatory consultant (US and EU), and recorded in MDX-B10-002.** |
| An eQMS | It does not do design control, document control, change control, training management, supplier management or internal audits. Those stay in the customer's QMS. It links to them by reference. |
| A submission gateway | It prepares report files. It never connects to an authority's gateway and never sends a report. |
| A decision maker | It suggests and counts. A person decides, and the signed record names that person. |
| A certified or "compliant" system | It is designed to support the customer's compliance with Part 11, the QMSR, the EU MDR and others. The customer's QMS, procedures and validation decide compliance. MDARIX claims no certification (R4). |
| A clinical or patient-facing tool | Patients and clinicians do not use it. Patient data is minimised and masked where possible. |

## 8. Limits of use
1. **Rule content is starter content.** Each market's question set, harm-severity scale, harm and fault word lists, and disposition and coding criteria are MDARIX starter text until the regulatory consultant confirms them. The customer must check them against its own procedure before use.
2. **Clock rules are conservative.** GB and India count the awareness day as day 1. Canada counts in the organisation's time zone. The customer confirms these against its procedure.
3. **Markets covered:** US, EU/Northern Ireland, Great Britain, India and Canada. Other markets are not assessed. A complaint from another country shows "may also apply" only.
4. **Data quality.** Trends and rates depend on imported units, lots and versions. Where units are unknown, MDARIX shows no rate.
5. **Free trial.** Synthetic sample data only, by the trial terms. The sample's dates move with the trial day (sample clock). It is not for real patient or customer data.
6. **Paid pilot.** Real data only after Gate B (R1 §3): validation of the pilot's scope, the independent assessment and pen test, Part 11 verification, a DPA, and the customer's own approval.
7. **No authority connectivity.** Submission status in MDARIX is what a person recorded.
8. **AI.** Off in release 1.0. Never used for a signed conclusion without a person accepting it (from 2027).
9. **Availability.** Target 99.5% monthly uptime (owner SLO, 3 Nov 2026). The customer must keep a procedure to meet legal deadlines if MDARIX is unavailable (for example, the authority's own forms).

## 9. Open points
| # | Point | Owner |
|---|---|---|
| OP-1 | Confirm "not a medical device" in the US, EU, GB, Canada and India with a regulatory consultant. Record the conclusion and its basis in MDX-B10-002. | Owner |
| OP-2 | Confirm the day-1 counting rules (GB, India) and Canada's time-zone rule (T-B6). | Owner + consultant |
| OP-3 | Decide whether the Executive (VIEWER) persona is in the validated scope or only "read-only, low risk". | Owner |
| OP-4 | Confirm whether authorised representatives and importers are named users in the 1.0 intended use, or manufacturers only. | Owner |
| OP-5 | Add the native CAPA lifecycle (M5) to this statement when it is specified. | Owner |
| OP-6 | Confirm the business-continuity line in §8.9 is acceptable wording for customers. | Owner |
