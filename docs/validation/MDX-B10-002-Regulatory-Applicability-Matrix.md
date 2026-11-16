# MDX-B10-002 Regulatory Applicability Matrix

| Field | Value |
|---|---|
| Document ID | MDX-B10-002 |
| Title | Regulatory Applicability Matrix |
| Version | 0.1 DRAFT |
| Owner | Srinivas Telikicherla (QA/RA) |
| Author | Drafted for review |
| Date | 8 Nov 2026 |
| Status | DRAFT |
| Code baseline | v0.10.92 |
| Approval | |

## 1. Purpose
This matrix shows, for each regulation and standard that touches MDARIX, who it applies to (MDARIX, the customer, or both), what triggers it, which MDARIX functions support it, which controls are needed, the evidence, the owner and the next review date. It is workstream W-E of the B10 plan.

It is not a compliance claim. MDARIX **supports** customer processes and **is designed to** meet the controls listed. The customer decides its own compliance.

## 2. Scope
MDARIX 1.0 and the free-trial edition, in both operating modes (Connect and Complete), hosted by MDARIX in India (Google Cloud, Mumbai). Markets: US, EU/NI, GB, India, Canada.

## 3. References
| Ref | Document |
|---|---|
| R1 | `MDARIX-planning/b10-assurance-plan.md` |
| R2 | MDX-B10-001 Intended Use Statement |
| R3 | `MDARIX-R1/docs/compliance/REGULATORY_DECISION_TABLES.md` (v0.10.92) |
| R4 | `MDARIX-R1/backend/app/reportability/markets.py` and `deadlines.py` (v0.10.92) |
| R5 | `MDARIX-R1/docs/runbooks/INCIDENT_RESPONSE.md` and `DATA_REQUESTS.md` (v0.10.92) |
| R6 | `MDARIX-R1/legal/SUBPROCESSORS.md`, `privacy.md`, `terms.md` (v0.10.92) |
| R7 | `MDARIX-R1/docs/compliance/WEBSITE_TRUST_CLAIMS_POLICY.md` (v0.10.92) |

**Citation rule:** every citation not checked against the official text in this draft is marked **(to confirm)**. All "(to confirm)" items are for the regulatory consultant or the lawyer.

## 4. How to read the "party" column
- **MDARIX:** binds MDARIX as a company or service provider.
- **Customer:** binds the device manufacturer. MDARIX functions help the customer meet it.
- **Both:** binds each party for its own part (for example, MDARIX as a data processor and the customer as controller).

## 5. The matrix
Review date for every row: **before Gate B (first paid pilot), then every 12 months, or sooner on a change in law, scope or hosting.**

| # | Regulation / standard | Jurisdiction | Party | Trigger | MDARIX functions | Required controls | Evidence | Owner | Review date |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **21 CFR Part 11** (Electronic records; electronic signatures): 11.10 controls for closed systems, 11.50 signature manifestation, 11.70 signature/record linking, 11.100, 11.200, 11.300 | US | Customer (uses records required by FDA predicate rules); MDARIX designs and evidences the controls | Customer keeps FDA-required records (803 MDR files, complaint files) or signs them in MDARIX | Signatures (password + authenticator per signing, meaning, name, time), version-bound snapshots, audit trail with hash chain, record export, access control, session timeout | Unique IDs; authentication; authority checks; SoD; audit trail that is secure, computer-generated and time-stamped; signature binding (no reuse); readable copies; retention; training records; customer e-signature certification letter to FDA (11.100(c)) | W-D verification report; OQ/PQ protocols for signatures and audit trail; audit-chain verification output; export samples; customer procedure templates | MDARIX: owner. Customer: its QA | Before Gate B; then yearly |
| 2 | **QMSR**: 21 CFR Part 820 as amended, incorporating ISO 13485:2016 by reference; effective 2 Feb 2026. Includes 820.35 records (complaint and servicing records) (to confirm clause numbers) | US | Customer | Customer is a US device manufacturer using MDARIX for complaint handling, MDR evaluation or CAPA records | Intake, complaint decision with rationale, MDR evaluation record, investigation, CAPA reference and effectiveness, trends | Validated software for its intended use (ISO 13485 4.1.6); complaint records with MDR evaluation; record retention | Customer validation package (W-F); MDARIX Validation Summary Report; traceability matrix | Customer; MDARIX supplies evidence | Before Gate B; then yearly |
| 3 | **FDA guidance "Computer Software Assurance for Production and Quality System Software"** (final guidance, Sept 2025) (to confirm date and status) | US | Customer (as the validating user); MDARIX follows it for its own assurance | Customer validates MDARIX under the QMSR | All functions, by risk class | Risk-based assurance: intended use, risk to process and patient, assurance activities by risk, records of the result | MDX-B10-003 Validation Plan; MDX-B10-004 risk assessment; execution records | MDARIX for the package; customer approves | Before Gate B; then yearly |
| 4 | **21 CFR Part 803** (Medical Device Reporting): 803.50 (30 calendar days), 803.53 (5 work days), 803.52 (report content, Form 3500A), 803.56 (supplemental reports), 803.12 and 803.20 (electronic submission, eMDR), 803.17 (written MDR procedures), 803.18 (MDR files, retention) (to confirm sub-clauses) | US | Customer | A US complaint with a death, serious injury or reportable malfunction | US question set (US Q1–Q6), legal clock in America/New_York, 3500A PDF and eMDR XML from the approved snapshot, supplement follow-up, MDR file in Records | Correct clock counting; Unknown never No; data only from the approved snapshot; nothing invented; customer submits through ESG/eSubmitter | DT-37 equivalence test; `tests/test_legal_deadlines.py`; `tests/test_fda_3500a_emdr.py` with FDA's example files; RG-01–RG-19 | Customer; MDARIX for function correctness | Before Gate B; then yearly |
| 5 | **EU MDR 2017/745** vigilance and PMS: Art. 2(64)–(66) definitions; Art. 83–86 (PMS system, plan, PMSR, PSUR); Art. 87 (serious incidents: 15 days; 2 days serious public health threat; 10 days death or unanticipated serious deterioration); Art. 88 (trend reporting); Art. 89; MDCG 2023-3 (to confirm current revision); MIR form 7.3.1 | EU and Northern Ireland | Customer | An incident in the EU/NI, or a device placed on the EU market | EU/NI question set, clock in Europe/Brussels, MIR draft, trend counting, PMS documents (generated drafts) | As row 4, plus trend-report support; MIR field mapping checked against the Commission's form | DT/RG scenarios for EU; MIR mapping review (`authority-forms-spec`) | Customer | Before Gate B; then yearly |
| 6 | **GB MDR 2002** as amended by the Medical Devices (Post-market Surveillance Requirements) (Amendment) (Great Britain) Regulations 2024, in force **16 Jun 2025** (SI 2024/1368) (to confirm SI number and timelines); MHRA MIR 7.2.1 | Great Britain | Customer | An incident in GB, or a device on the GB market | GB question set, clock in Europe/London (awareness day = day 1, conservative), GB MIR draft | As row 4; confirm the day-count rule | GB scenarios; consultant confirmation (T-B6) | Customer | Before Gate B; then yearly |
| 7 | **Canadian Medical Devices Regulations** (SOR/98-282): ss. 57–58 (complaint handling, distribution records), ss. 59–61.1 (mandatory problem reporting: 10 days death/serious deterioration; 30 days potential), s. 61.2 (to confirm sections and timelines) | Canada | Customer | An incident in Canada, or a device licensed in Canada | Canada market (from tr15), clock in the organisation's time zone, Health Canada form draft | As row 4; confirm Canada time-zone rule | Canada scenarios | Customer | Before Gate B; then yearly |
| 8 | **India Medical Devices Rules 2017** (Rules 3 and 26 per `markets.py`) and the **Materiovigilance Programme of India (MvPI)**, PSUR duties (to confirm rule numbers and the reporting timelines) | India | Customer | An incident in India, or a device registered/licensed in India | India question set, clock in Asia/Kolkata (awareness day = day 1, conservative) | As row 4; confirm timelines with CDSCO/IPC guidance | India scenarios; consultant confirmation | Customer | Before Gate B; then yearly |
| 9 | **ISO 13485:2016** clause 4.1.6 (validation of QMS software), 4.2.5 (control of records), 8.2.2 (complaint handling), 8.2.3 (reporting to regulatory authorities) | International (and US via QMSR) | Both: customer for its QMS; MDARIX for its own development if it seeks certification later | Customer uses MDARIX in its QMS | Complaint process, reporting, records | Validation for intended use, proportionate to risk; records protected and retrievable | MDX-B10-003; MDX-B10-008 supplier evidence | Customer; MDARIX supplies | Before Gate B; then yearly |
| 10 | **ISO 14971:2019** (risk management for medical devices) | International | Customer | Customer feeds post-production information into the risk file | Harm-severity scale (5 levels, ISO 14971-style), risk-review input, trend data, links to the risk file | Post-production information reaches the risk file; MDARIX does not own the risk file | Risk-input records; Product 360 | Customer | Before Gate B; then yearly |
| 11 | **EU GDPR** (Reg. 2016/679): Art. 4, 9 (health data), 28 (processor), 32 (security), 33 (breach: 72 hours to authority, by controller), 44–49 (transfers) | EU (extra-territorial for EU data subjects) | Both: customer = controller; MDARIX = processor | Customer data includes EU residents' personal data (reporters, patients, users) | Masking of names and phones, field policies, export, erasure, retention, India hosting | Art. 28 DPA; sub-processor list; transfer mechanism for EU→India (SCCs) (to confirm); breach notice to customer without undue delay | DPA; `legal/SUBPROCESSORS.md`; `DATA_REQUESTS.md`; incident runbook | Owner + lawyer | Before Gate B; then yearly |
| 12 | **India Digital Personal Data Protection Act 2023** and **DPDP Rules 2025** (notified Nov 2025; phased commencement) (to confirm commencement dates per rule); breach intimation (rule 7) | India | Both: MDARIX = Data Fiduciary for its own account data and website; Data Processor for customer content; customer = Data Fiduciary | Any digital personal data processed in India | Privacy notice, consent at sign-up, erasure, retention, breach runbook (§4.2) | Notice and consent; security safeguards; breach intimation to the Board and data principals; processor contracts; retention limits; grievance contact | `legal/privacy.md`; `INCIDENT_RESPONSE.md` §4.2; DPDP text review (owner priority list) | Owner + lawyer | Before Gate B; then yearly |
| 13 | **HIPAA** (45 CFR Parts 160 and 164): **applicability only** | US | Normally neither | Applies only if a customer is a covered entity or business associate and sends PHI to MDARIX as its business associate | None specific; masking and minimisation reduce PHI | Default position: device manufacturers are usually not covered entities; MDARIX does not sign BAAs in 1.0 and makes no HIPAA claim (R7) (to confirm with counsel) | Written applicability statement in the DPA / terms | Owner + lawyer | Before Gate B; then yearly |
| 14 | **ISO/IEC 27001:2022** (information security management) | International | MDARIX (voluntary) | Customer supplier audits and enterprise security reviews | Whole service | ISMS readiness; Annex A controls mapped to the policy set (MDX-B10-007) | Policy set; risk register; internal audit. Certification is Gate C roadmap only | Owner | Before Gate B; then yearly |
| 15 | **SOC 2** (AICPA Trust Services Criteria; security, availability, confidentiality) | Mainly US customers | MDARIX (voluntary) | US customer requests | Whole service | Same control set as row 14; Type I then Type II | Gate C roadmap only; no claim before a report exists | Owner | Before Gate B; then yearly |
| 16 | **EU GMP Annex 11** (computerised systems) | EU | Customer, **pharmaceutical GMP only** | Only where a customer uses MDARIX under pharmaceutical GMP (for example, a drug-device combination maker's pharma side). A revision is in consultation (to confirm status) | Same controls as row 1 | Never marketed as EU MDR support. Shown here so the boundary is clear | Reference only | Customer | Before Gate B; then yearly |
| 17 | **CERT-In Directions of 28 Apr 2022** under IT Act 2000 s.70B(6) (added; not in the brief's list) | India | MDARIX, once incorporated | A cyber incident of a listed type on MDARIX systems | Incident runbook §4.3 | Report within 6 hours; keep ICT logs for 180 days within India; point of contact; clock sync (to confirm details) | `INCIDENT_RESPONSE.md` §4.3; log-retention evidence (gap, see §6) | Owner | Before Gate B; then yearly |

## 6. Gaps found while preparing this matrix
| # | Gap | Rows | Effect |
|---|---|---|---|
| G-1 | No written medical-device qualification decision (MDX-B10-001 OP-1). | All | Underpins every row's "customer" assumption. |
| G-2 | Market question sets and clock rules are starter text until confirmed (T-B6). | 4–8 | Must be confirmed before Gate B for the pilot's markets. |
| G-3 | No DPA template; EU→India transfer mechanism not chosen. | 11, 12 | Gate B needs a DPA. |
| G-4 | Log retention: container logs rotate at 10 × 20 MB per service (`docker-compose.prod.yml`). That may hold far less than 180 days. | 17 | Possible gap against CERT-In; check volumes and add off-host log retention. |
| G-5 | Part 11 applicability assessment (W-D) not yet written. | 1 | Gate B item. |
| G-6 | `docs/compliance/COMPLIANCE_VALIDATION_PROTOCOL.md` still says passwords expire after 90 days; the code follows NIST SP 800-63B with no periodic expiry (`auth/service.py`), as the owner decided. | 1 | The document must be corrected before it is used as evidence. |

## 7. Open points
| # | Point | Owner |
|---|---|---|
| OP-1 | Consultant to confirm every "(to confirm)" citation, the GB SI number and the Canada and India sections and timelines. | Owner + consultant |
| OP-2 | Lawyer to confirm the GDPR and DPDP party roles and the HIPAA default position. | Owner + lawyer |
| OP-3 | Decide whether CERT-In (row 17) stays in the matrix. Recommended: yes. | Owner |
| OP-4 | Add IEC 62304 / IEC 82304-1 as "not applicable while MDARIX is not a device", if the consultant agrees. | Owner |
| OP-5 | Set a named owner per row once the team grows beyond the founders. | Owner |
