# MDX-VAL-002 Product risk assessment

| Field | Value |
|---|---|
| Document ID | MDX-VAL-002 |
| Title | Product risk assessment |
| Version | 0.4 |
| Status | DRAFT |
| Author (R) | Sriharsha Telikicherla, Product & Engineering, system owner (proposes every rating) |
| Reviewer | Independent CSV consultant (confirms severities and scales; not engaged yet). The quality approver reviews every severity before approving |
| Approver (A) | Srinivas Telikicherla, QA/RA, quality approver |
| Drafting | Drafted with software assistance; every line reviewed by Sriharsha Telikicherla (MDX-VAL-000, DC-R43) |
| Date | 12 Nov 2026 |
| Code baseline | Product code at `628c624a`, plus two changes on branch `feat/b6b-validation-pack`: the SUPERSEDED banner in `validation/csa_package.py` and its test, and `cb75e8da` (the rule register refuses a version approved by its own builder, owner decision O3: `backend/app/rule_register/register.py` and its test); every file path below exists at `cb75e8da` |

Change history

| Version | Date | Change | By |
|---|---|---|---|
| 0.1 | 12 Nov 2026 | First draft. Replaces MDX-B10-004 v0.1 (8 Nov 2026): its 43 rows re-scored on 1-5 scales with detectability, plus 22 rows for the functions built in B2 to B9 and B6a. Revised after a software-assisted review, findings dispositioned by the author: privacy line in the severity scale, re-rated RSK-016, -023, -025, -029, -038, -039, -046, new RSK-065, numbered rules | Sriharsha Telikicherla |
| 0.2 | 12 Nov 2026 | After a second software-assisted review, findings dispositioned by the author: rules for an open class-A row and for the residual-risk values (section 3.5); two functions split by sub-function; RSK-002, -025, -030, -035, -040 marked Open and listed; RSK-065 per owner decision O3; RSK-036 and RSK-023 Open (verification); RSK-066 (purge, retention, legal hold) and RSK-067 (sign-in, sessions) added; residual-risk values in a table; RSK-065 closed by the refusal in `register.py` (re-rated O2, D1); re-rating of RSK-023, -029, -039 agreed by the owner (O4) | Sriharsha Telikicherla |
| 0.3 | 12 Nov 2026 | Owner answers of 12 Nov 2026: RSK-023 is class A by the late-report line of severity 5 (O4 confirmed); RSK-066 re-rated S5 (RPN 30, needs action under RA-R04), RSK-067 stays S4 (O6); 29 rows need action; REQ IDs from `requirements.csv` for the 34 rows without a seed (OP-3); editorial fixes after a third software-assisted review (code baseline names `cb75e8da`; cross-references) | Sriharsha Telikicherla |
| 0.4 | 12 Nov 2026 | Owner decisions of 12 Nov 2026 ("approve all B6b recommendations"): O7 severity 5 = permanent loss of regulated records, severity 4 = recoverable loss; every row citing either line re-checked (section 3.7): RSK-037 and RSK-040 raised to S5; O8 RSK-029 raised to S5 (RPN 40, needs action); O9 detection only at the quarterly restore drill is D4 (detectability scale), RSK-039 re-scored D4 (RPN 48) and RSK-040 D4 (RPN 40), both now need action; 32 rows need action; O10 RSK-065 control compares staff accounts, not typed names; O15 PL-xx scenarios named in the verification of RSK-023, -026, -036 | Sriharsha Telikicherla |

## 1. Purpose and scope

This assessment sets the GxP impact and the risk class of each MDARIX function, and lists how each function could
fail, the effect, the controls in the code, how each is verified and the residual risk. The class drives the
assurance level in the Validation Master Plan (MDX-VAL-001 section 8).

It covers every function of the MDARIX web application, API and background service at the code baseline, in both
operating modes and in the free-trial edition. It is a software process risk assessment in the CSA sense. It is not
the device manufacturer's ISO 14971 risk management file and it does not replace it.

The system owner proposes every rating. The quality approver reviews every severity before approving, and the
consultant confirms the severities and scales. The whole assessment is **to confirm with your consultant** (MDX-VAL-013, questions 1 and 7).

## 2. References

| Ref | Document |
|---|---|
| R1 | MDX-VAL-001 Validation Master Plan |
| R2 | MDX-B10-001 Intended Use Statement (draft, [MDX-B10-001-Intended-Use-Statement.md](MDX-B10-001-Intended-Use-Statement.md)) |
| R3 | MDX-B10-005 Traceability Structure, section 7 seed requirements REQ-&lt;AREA&gt;-nnn (draft, [MDX-B10-005-Traceability-Structure.md](MDX-B10-005-Traceability-Structure.md)) |
| R4 | MDX-B10-006 Threat Model: penetration-test threats PT-01 to PT-17 and gaps G-1 to G-12 (draft, [MDX-B10-006-Threat-Model.md](MDX-B10-006-Threat-Model.md)) |
| R5 | [scenario-register.md](scenario-register.md) (scenario IDs IN, CI, TR, RG, DT, RR, IV, B5, CP, RT, BK, EM, UA, B8, B9, OC, P360, S360, B6, PL) |

## 3. Method (owner decision B6b-D4)

### 3.1 Severity (S): the effect if the failure reaches a customer's record or decision

| S | Meaning |
|---|---|
| 5 | A reportable event is missed or reported late; a wrong regulatory conclusion is signed; wrong data goes to an authority; one customer's data, or personal data, reaches someone outside that customer; regulated records are permanently lost (no backup or copy can bring them back). Indirect effect on patient safety: a safety signal or report does not reach the authority in time |
| 4 | The integrity of a regulated record is lost: a signed or submitted record changes without trace; a signature is invalid or not bound to its record; audit history is lost or incomplete; regulated records are lost but can be recovered (from a backup or the source system); an unauthorised person approves. Or a security or privacy failure inside the customer: erased personal data comes back, or code runs on a user's computer |
| 3 | Wrong or missing information is shown, but a trained person is expected to catch it before signing; work is delayed or repeated |
| 2 | Inconvenience; management information wrong; no record or decision effect |
| 1 | Cosmetic |

### 3.2 Occurrence (O): with today's controls and their automated tests (formal validation runs are not credited)

| O | Meaning |
|---|---|
| 5 | Expected in normal use; no control |
| 4 | Plausible in normal use; control partial, or a known gap |
| 3 | Needs an unusual combination; control exists with some tests |
| 2 | Control enforced in code or by design, with automated tests |
| 1 | Control enforced in the database, with automated tests, and failure needs several independent faults |

### 3.3 Detectability (D): the chance the failure is caught before it affects a record or a report

| D | Meaning |
|---|---|
| 1 | Almost certain: the system refuses the action, or raises an error at once |
| 2 | High: an automatic check (daily verification, settlement job, backup-age check) finds it within a day |
| 3 | Moderate: a trained person sees it on a screen they review before signing |
| 4 | Low: found only by a periodic review, the quarterly restore drill, an audit or a customer's report (owner decision O9) |
| 5 | Very low: no known way to detect it before harm |

### 3.4 Class and priority

- **RA-R01** The risk class shall be set by severity alone: S4 and S5 give class A, S3 class B, S1 and S2 class C.
- **RA-R02** RPN = S × O × D (1 to 125) shall be used only to order the work within a class.
- **RA-R03** RPN shall not lower a class.

### 3.5 Action rule

- **RA-R04** A row shall be marked as needing action when RPN is 40 or more, or when S is 5 and D is 3 or more.
- **RA-R05** A row that needs action shall have its action done before the release that relies on it.
- **RA-R06** That action shall be the open item named in "Residual risk", or, where none is named, executing the
  row's class-A scenarios with pre-approved expected results.
- **RA-R07** A row marked Open that is class A or needs action, and that a production release relies on, shall have a risk acceptance signed by the
  quality approver, naming its interim control and a due date (consultant to confirm, MDX-VAL-013 question 16).
- **RA-R08** Each such acceptance shall be listed in the release approval record (MDX-VAL-012).
- **RA-R09** "Residual risk" shall hold one of the four values defined below; any note goes in "Verification".

| Residual risk | Meaning |
|---|---|
| Acceptable | The control is in place and its verification is named; nothing is left to do (used only where no validation run is needed, class C) |
| Acceptable after verification | The control is in place; the row is acceptable once its named verification passes in a release pack |
| Open | A control or a verification is missing; the missing item is named and listed in section 6 |
| Not applicable while AI is off | AI rows only (RSK-041 to -043); rated before AI is switched on (MDX-VAL-001 section 15) |

How these rules are checked: the quality approver checks each row against RA-R01 to RA-R09 before approving
(OP-1); the release approval record lists the Open rows the release relies on and their acceptances (RA-R07).

### 3.6 Conversion from MDX-B10-004

MDX-B10-004 used three levels. Its S3 rows are now S5 (report, conclusion or cross-organisation effect) or S4
(record-integrity effect); its S2 rows are S3. Its likelihood L1, L2, L3 became O2, O3, O4. Detectability is new. The conversion itself moved no row between classes. The re-rating after the first review moved RSK-023,
-029 and -039 from class B to class A (owner decision O4): RSK-023 because a rejected, therefore late, report is the
late-report line of severity 5; RSK-039 by the privacy line of severity 4; RSK-029 by the privacy line of severity 4, raised to severity 5 by owner
decision O8 (data can leave the organisation: the cross-organisation line of severity 5). RSK-066 is S5 by owner decision O6
(regulated records lost before their retention date). Owner decision O7 (12 Nov 2026) split the loss of regulated
records: permanent loss is S5, recoverable loss is S4. Every row that cites either line was re-checked (section 3.7).

### 3.7 Re-check under owner decision O7 (permanent vs recoverable loss)

| Row | Loss | Severity |
|---|---|---|
| RSK-016 | An audit row deleted: recoverable from the daily backup, and the chain check shows the gap | 4 (unchanged) |
| RSK-019 | A signed conclusion edited in place: the integrity line ("changes without trace"), not a loss | 4 (unchanged) |
| RSK-035 | Export misses records: the records stay in MDARIX until a separate purge (RSK-066), so the loss is recoverable | 4 (unchanged) |
| RSK-037 | A backup fails silently, then a disaster: no good copy, so the loss is permanent | 4 to 5 |
| RSK-038 | Up to 24 hours lost without point-in-time recovery: permanent | 5 (unchanged) |
| RSK-040 | Backup key lost: no restore possible, so the loss is permanent | 4 to 5 |
| RSK-056 | Notifications held or re-sent after a restore: no regulated record lost | 3 (unchanged) |
| RSK-066 | Purge: permanent | 5 (unchanged) |

## 4. GxP impact per function

Direct = creates or changes a GxP record, or decides a GxP outcome. Indirect = supports work that a trained person
checks before signing. None = no record or decision effect.

| Function | GxP impact | Class | Assurance approach (MDX-VAL-001 section 8) | Rationale | FMEA rows |
|---|---|---|---|---|---|
| Intake, Case, e-mail intake, back-entry after an outage | Direct | A | Scripted, negative tests, every touched release | Creates the complaint record and its awareness time, which start the legal clocks | RSK-007, -008, -044, -045 |
| Awareness, legal clocks, daily deadline list | Direct | A | Scripted, including weekends, daylight saving, time zones | A wrong clock gives a late report | RSK-002, -007, -008, -046 |
| Triage escalation | Direct | A | Scripted | Decides the fast track for death and serious injury | RSK-031, -032 |
| Complaint or service classification, routine path | Direct | A | Scripted | "Service only" removes the record from reportability assessment | RSK-033, -034, -052 |
| Reportability per market, rule register | Direct | A | Scripted; equivalence tests | Suggests the regulatory outcome a person signs | RSK-001, -003 to -006, -050, -054, -055, -065 |
| Authority report files (eMDR, EU and GB MIR, MvPI, Canada, other countries) | Direct | A | Scripted; schema validation; owner's by-eye check of each form | The customer submits these files to the authority | RSK-022 to -024, -053 to -055 |
| E-signatures, segregation of duties, signer training | Direct | A | Scripted, negative | Part 11 signature controls | RSK-009 to -015 |
| Audit trail, chain verification, reason for change | Direct | A | Scripted; tamper tests | Part 11 audit trail | RSK-016 to -018, -048 |
| Signed records, snapshots, never rewrite | Direct | A | Scripted | The signed record must stay as signed | RSK-019 to -021, -062 |
| Tenant isolation, roles, field protection | Direct | A | Negative tests both ways, every surface | Confidentiality of every customer's GxP data | RSK-025, -026, -036 |
| Import and migration, lineage, quarantine | Direct | A | Scripted; the seven interface checks | Creates regulated records from another system | RSK-027, -028 |
| Signed reviews: audit trail review, access review, configuration snapshot | Direct | A | Scripted | Evidence for the customer's own periodic controls | RSK-049 |
| Investigation: signed conclusion and challenge loop | Direct | A | Scripted | The conclusion is signed; an open challenge must stop the signature | RSK-051 |
| Investigation suggestions and display; CAPA effectiveness reminders | Indirect | B | Scenario test | Suggestions and due dates are checked by a person | RSK-061 |
| QMS documents (PMS drafts): signed version | Direct | A | Scripted | The signed version is a GxP record | RSK-062 |
| QMS documents (PMS drafts): data tables in a draft | Indirect | B | Scenario test | A person checks the draft before signing it | none (covered by RSK-059, -060 for the figures) |
| Export and exit | Direct | A | Scripted; manifest hashes | The customer's inspection pack and exit copy | RSK-029, -035, -036 |
| Backup, restore, recovery, time source | Direct | A | Restore drill and recovery record | Loss or wrong time of regulated records | RSK-037 to -040, -047, -056 |
| Platform administration, support access | Direct (access to GxP data) | A | Negative tests | Third-party access to customer records | RSK-014, -015 |
| Sample clock (free trial) | Direct if it fails (could move a real record) | A | Scripted | Must never touch a customer's own records | RSK-030 |
| Trace this value (read only) | Indirect | B | Scenario test | Shows where a value came from; changes nothing | RSK-057 |
| Trends and signals ("pattern to review"), Product 360, Supplier 360 | Indirect | B | Scenario test | A person decides whether a signal exists | RSK-059, -060 |
| Similar-wording duplicates, notifications and outbox | Indirect | B | Scenario test | Suggestions and reminders; a person decides and the record keeps its own clock | RSK-058, -063 |
| Value Centre, dashboards, Executive view | None to Indirect | C | Build checks; rationale only | Management figures; no record or decision is made from them in MDARIX | RSK-064 |
| Organisation purge, retention and legal hold | Direct | A | Scripted, negative | Purging the wrong records, or too early, loses regulated records | RSK-066 |
| Sign-in, sessions and account management | Direct (access to GxP records and signing) | A | Scripted, negative | A deactivated or idle account must not act | RSK-067 |
| Help, themes, layout, getting started, saved views | None | C | Rationale only | Change only how a screen looks or what help text says; no record is created, changed or decided. No FMEA row | none |
| AI helpers | n/a (off) | A when switched on | AI validation before switch-on (MDX-VAL-001 section 15) | AI output could reach a regulated record once switched on | RSK-041 to -043 |

## 5. FMEA

S, O, D, RPN and the action rule as in section 3 (column "Action": RA-R04). "Threats" are MDX-B10-006 identifiers (R4). "REQ (seed)" are the
requirements in `docs/validation/requirements.csv` (the URS source; seeded from MDX-B10-005 section 7, R3); the IDs of the
34 rows without a seed were assigned when that file was built (12 Nov 2026). The verification column names the scenarios and automated tests that will
give the evidence. It does not claim they have passed in a validation run: most scenario rows are NOT RUN today
(scenario register).

| ID | Area | Failure mode | Effect | S | O | D | RPN | Class | Action (RA-R04) | Controls (code) | Verification | Threats | REQ (seed) | Residual risk |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| RSK-001 | Reportability | An Unknown answer is treated as No, giving "not reportable" | Missed report | 5 | 2 | 3 | 30 | A | Yes | Unknown is never No; "not reportable" refused while an Unknown could make it reportable (`backend/app/reportability/markets.py`, `assessments.py`) | RG-05, DT-06 to DT-08; `tests/test_market_assessment_rules.py` | - | REQ-RPT-001 | Acceptable after verification |
| RSK-002 | Legal clocks | Wrong deadline: wrong time zone, day-0/day-1 counting, weekend, daylight saving | Late report | 5 | 3 | 4 | 60 | A | Yes | One deadline function for every screen; authority time zones; earlier of authority and organisation day (`backend/app/reportability/deadlines.py`) | RG-10, RG-11, DT-16; `tests/test_legal_deadlines.py`, `tests/test_one_deadline_api.py` | - | REQ-CLK-001, REQ-CLK-002 | **Open:** the GB, India day-1 and Canada counting rules to confirm with the consultant |
| RSK-003 | Reportability | Starter question set or floor rule wrong against the regulation | Wrong conclusion | 5 | 3 | 4 | 60 | A | Yes | Clause shown beside each question; floor locked and versioned; content hash per version | DT-01 to DT-03, DT-33, DT-37, RR rows; consultant review | - | REQ-RPT-003, REQ-RPT-005 | **Open** until the consultant confirms the question sets; the customer checks starter content against its own procedure |
| RSK-004 | Reportability | Rule changed after the incident; an old record is re-evaluated silently | Signed record altered | 4 | 3 | 4 | 48 | A | Yes | Version named on the signed record; a re-check task, never an automatic change (`backend/app/trial/open_deadlines.py`) | RG-12, DT-17, DT-18, DT-20 | - | REQ-RPT-004 | Acceptable after verification |
| RSK-005 | Reportability | A multi-market event is assessed for one market only | Missed report in another market | 5 | 3 | 3 | 45 | A | Yes | One row per market; country unknown uses every market's shortest clock | RG-06 to RG-08, RG-13, TR-12, TR-40, DT-21 | - | REQ-RPT-002, REQ-CLK-003 | Acceptable after verification |
| RSK-006 | Reportability | An organisation rule lowers the outcome or lengthens the clock | Missed or late report | 5 | 2 | 3 | 30 | A | Yes | Organisation layer can only raise; a "Not reportable" rule is not offered | DT-03, DT-04, DT-36 | - | REQ-RPT-003 | Acceptable after verification |
| RSK-007 | Awareness | Awareness recorded later than the true first knowledge (distributor, second channel) | Clock starts late | 5 | 3 | 4 | 60 | A | Yes | Awareness = recorded time, otherwise the earliest of first knowledge and receipt (`backend/app/intake/rules.py`); the earliest awareness wins when Cases are linked | IN-08, IN-09, RG-09, CI-06, CI-08, TR-04, TR-05, TR-32 | - | REQ-AWR-001, REQ-AWR-003 | Acceptable after verification |
| RSK-008 | Awareness | Missing awareness gives no clock | Clock never starts | 5 | 3 | 3 | 45 | A | Yes | Provisional clock and a clarification task | IN-08, TR-32 | - | REQ-AWR-002 | Acceptable after verification |
| RSK-009 | Signatures | Someone signs as another person, or without a second factor | Invalid signature | 4 | 2 | 4 | 32 | A | No | Fresh authenticator code per signing; MFA mandatory for signing roles; 5 wrong codes lock 15 min (`backend/app/mfa.py`, `auth/totp.py`); `config_check.py` refuses weaker production settings | B6-20, B6-21; `tests/test_signing_code_refusals.py`, `tests/test_mfa_mvp.py` | PT-05, PT-06 | REQ-SIG-001 | Acceptable after verification |
| RSK-010 | Signatures | Signature saved but record not saved, or the reverse | Orphan signature, or unsigned record shown as signed | 4 | 3 | 2 | 24 | A | No | Durable PREPARE, PENDING, SAVED, SIGNED states; PENDING never valid (`backend/app/signing_commit.py`); scheduler job `signature-settlement` | `tests/test_signing_recovery.py` | - | REQ-SIG-004 | Acceptable after verification |
| RSK-011 | Signatures | A person without signing authority or training signs | Unauthorised conclusion | 4 | 3 | 3 | 36 | A | No | Role permissions (`backend/app/access/permissions.py`); signer training on current document versions (`backend/app/signer_training/service.py`) | DT-13; `tests/test_authorization_matrix.py`, `tests/test_business_permissions.py` | PT-03 | REQ-SIG-005 | Acceptable after verification |
| RSK-012 | Signatures | Signature replayed onto a changed record version | Signature bound to the wrong content | 4 | 2 | 2 | 16 | A | No | Signature binds outcome, rationale, brief version, evidence fingerprint and snapshot hash; verification recomputes (`backend/app/human_decision/rules.py`); stale version refused (`seen_version`) | CI-26, TR-24, DT-15; `tests/test_human_decision_unit.py` | PT-05, PT-06 | REQ-SIG-002, REQ-SIG-003 | Acceptable after verification |
| RSK-013 | Segregation of duties | The maker approves their own work outside a trial | No independent check | 4 | 3 | 3 | 36 | A | No | Segregation checks (`backend/app/access/governance.py`, `backend/app/authority_reports/router.py`, `backend/app/case_reviews/rules.py`); same person allowed in a trial only, labelled | CI-17, CI-34, CI-35, TR-05; `tests/test_case_reviews.py` | PT-05 | REQ-SOD-001 | **Open:** a negative test that the trial allowance never applies to a pilot organisation |
| RSK-014 | Segregation of duties | An administrator approves a regulated decision | Unauthorised approval | 4 | 2 | 3 | 24 | A | No | Administrators never approve (migration `md03_retire_viewer_approval_authority.py`) | DT-13; `tests/test_authorization_matrix.py` | PT-03, PT-17 | REQ-SOD-002 | Acceptable after verification |
| RSK-015 | Platform administration | MDARIX staff change customer data | Untraceable third-party change | 4 | 2 | 3 | 24 | A | No | Customer-approved, time-limited support grants; requester, approver and recipient differ (`backend/app/support_access.py`, ADR-015) | `tests/test_support_access_sod.py`, `tests/test_support_access_customer_approval.py` | PT-17 | REQ-SEC-001 | Acceptable after verification |
| RSK-016 | Audit trail | An audit row is updated or deleted | Lost history | 4 | 1 | 1 | 4 | A | No | Database trigger rejects UPDATE and DELETE (migration `o31audit_immutability.py`) | `tests/test_day35_audit_immutability.py` | PT-14 | REQ-AUD-001 | Acceptable after verification |
| RSK-017 | Audit trail | The chain is rewritten by someone with database-owner rights | Undetected alteration | 4 | 3 | 4 | 48 | A | Yes | Hash chain per organisation (`md18_audit_chain.py`, `z45_audit_hash_chain.py`); daily verification with anchors (`backend/app/audit_chain.py`) | `tests/test_audit_hash_chain.py` | PT-14, G-3 | REQ-AUD-002 | **Open:** anchors and logs sit on the same server as the database; copy anchors off the server (threat model G-3) |
| RSK-018 | Audit trail | A change is not audited (old or new value, or reason, missing) | Incomplete trail | 4 | 3 | 4 | 48 | A | Yes | Audit with actor, time, reason, old and new values (`backend/app/enterprise_audit.py`); reason required on regulated edits (RSK-048) | CI-33, B6-36 | PT-14 | REQ-AUD-003 | **Open:** route-by-route audit completeness check |
| RSK-019 | Records | A signed conclusion is edited in place | History lost | 4 | 2 | 2 | 16 | A | No | A signed decision is never edited; a correction is a superseding version (`backend/app/human_decision/rules.py`) | IV-16, CI-07, CI-24, TR-02, TR-03 | PT-04 | REQ-REC-001 | Acceptable after verification |
| RSK-020 | Records | A submitted report is overwritten | Record differs from what was sent | 4 | 2 | 3 | 24 | A | No | Obligation lifecycle states; a follow-up after submission (`backend/app/authority_reports/rules.py`) | RG-15 to RG-17 | PT-04 | REQ-REC-002 | Acceptable after verification |
| RSK-021 | Records | An upgrade script changes signed records | Silent change | 4 | 3 | 2 | 24 | A | No | Upgrade scripts list, never change, signed conclusions; audited | CI-44; `tests/test_release_0_10_88_resign.py` | PT-04 | REQ-REC-003 | Acceptable after verification |
| RSK-022 | Authority reports | A value is placed in the wrong field or code list | Wrong report sent by the customer | 5 | 3 | 3 | 45 | A | Yes | Values only from the approved snapshot; a choice ticked only on FDA's exact wording; unplaced values listed (`backend/app/authority_reports/fda_3500a.py`); eMDR validated against FDA schemas (`emdr.py`) | RG-19; `tests/test_fda_3500a_emdr.py` (US; other markets: RSK-053, RSK-054) | - | REQ-ARD-001 | Acceptable after verification |
| RSK-023 | Authority reports | A missing required field is not flagged | Rejected, therefore late, report | 5 | 3 | 2 | 30 | A | No | `check` names every block FDA requires (`emdr.py`) | PL-15, PL-16 (drafted 12 Nov 2026, owner decision O15); test to add in `tests/test_fda_3500a_emdr.py` | - | REQ-ARD-002 | **Open (verification):** scenario and test to add |
| RSK-024 | Authority reports | Responsible-party details changed after approval appear on the report | Report differs from the approval | 5 | 2 | 3 | 30 | A | Yes | The party is used only while it still reads exactly as on the approved report (`emdr.py`) | Scenario to add (no test yet) | PT-04 | REQ-ARD-001 | **Open (verification):** add a scenario and a test |
| RSK-025 | Tenant isolation | One organisation reads another's record by ID, search, export, file or report | Data breach | 5 | 2 | 4 | 40 | A | Yes | Tenant from the server session only; forced row-level security with a secret system scope (`backend/app/db/tenant_scope.py`, migrations `md05_rls_system_scope.py`, `md15_rls_system_token.py`, `md34_rls_defence.py`) | P360-11, S360-14, B6-45; `tests/test_rls_coverage.py`, `tests/test_cross_tenant_routes.py`, `tests/test_tenant_security.py` | PT-01, PT-02, PT-16 | REQ-TEN-001 | **Open:** independent penetration test before the first paid pilot |
| RSK-026 | Tenant isolation | A background job runs with the wrong organisation scope | Cross-organisation write or e-mail | 5 | 3 | 4 | 60 | A | Yes | The worker claims one event at a time, each in its own transaction (`outbox/worker.py`); scope bound per session | PL-17 (drafted, O15); `tests/test_outbox_resilience.py` (partial) | PT-15 | REQ-TEN-002 | **Open:** a negative test of organisation scope per job type |
| RSK-027 | Import | A row is mis-mapped (for example a death column read as No) | Missed triage or report | 5 | 3 | 3 | 45 | A | Yes | Rows set aside in quarantine with reasons; harm rows reach triage while quarantined (`backend/app/import_quarantine.py`); lineage per row with mapping version (`backend/app/import_lineage.py`) | IN-13, IN-14, TR-21, TR-36 to TR-38; `tests/test_import_quarantine_unit.py`, `tests/test_import_lineage_unit.py` | - | REQ-IMP-001, REQ-IMP-003 | Acceptable after verification |
| RSK-028 | Import | A repeated import creates duplicate complaints | Double counting, conflicting conclusions | 3 | 3 | 2 | 18 | B | No | Duplicate external ID goes to reconciliation; a re-run is idempotent | IN-12, IN-14, CI-15, CI-31; `tests/test_import_reupload.py` | - | REQ-IMP-002 | Acceptable after verification |
| RSK-029 | Export | Formula injection in an exported CSV | Code runs on a user's computer; data can leave the organisation | 5 | 2 | 4 | 40 | A | Yes | `backend/app/csv_safe.py` on every CSV | `tests/test_csv_safe.py` | - | REQ-EXP-002 | Acceptable after verification |
| RSK-030 | Sample clock | The hourly sample-clock job moves a customer's own record dates | Real awareness or deadline changed | 5 | 2 | 4 | 40 | A | Yes | Moves only rows whose `source_system` is the sample's own value (`backend/app/trial/sample_source.py`, `sample_clock.py`); whole days only | CI-18, TR-16, P360-13; `tests/test_sample_story_days.py` | - | REQ-SMP-001 | **Open (verification):** a negative test that the job cannot run in a pilot organisation |
| RSK-031 | Triage | Death or serious injury is not fast-tracked | Late 2-, 5- or 10-day report | 5 | 3 | 3 | 45 | A | Yes | Triage flag on death, serious injury, harm words, Unknown on Q4 to Q6, manual escalation (`backend/app/intake/rules.py`) | IN-05, CI-13, TR-01, TR-19, TR-27 to TR-31; `tests/test_intake_triage_api.py`, `tests/test_signals_triage.py` | - | REQ-TRG-001, REQ-TRG-002 | Acceptable after verification |
| RSK-032 | Triage | Overdue triage is not escalated | Late action | 3 | 3 | 3 | 27 | B | No | Overdue alert, backup person, escalation role | TR-08, TR-09, CI-16 | - | REQ-TRG-003 | Acceptable after verification |
| RSK-033 | Classification | A complaint is recorded as "service only" | Complaint never assessed for reporting | 5 | 3 | 4 | 60 | A | Yes | Fixed outcomes table; "Service only" only from row 2, no override reaches it (`backend/app/intake/rules.py`); complaint-to-service down-grade refused | IN-02 to IN-04, IN-21, IN-22, CI-19 to CI-25, RT rows; `tests/test_intake_rules.py` | - | REQ-CLS-001, REQ-CLS-002, REQ-CLS-005 | Acceptable after verification |
| RSK-034 | Classification | Classification codes drive a deadline by mistake | Wrong clock | 5 | 2 | 3 | 30 | A | Yes | Classification never sets a deadline or conclusion (`backend/app/complaint_classification/rules.py`) | `tests/test_complaint_disposition_rules.py` | - | REQ-CLS-003 | Acceptable after verification |
| RSK-035 | Export and exit | The export misses records or versions | Incomplete inspection pack or exit copy | 4 | 3 | 3 | 36 | A | No | Tables discovered from the database; manifest with counts, SHA-256 and verified audit head (`backend/app/tenant_export.py`) | `tests/test_day25_retention_export.py`, `tests/test_export_purge_mfa.py` | - | REQ-EXP-001 | **Open (verification):** a readable export of record, versions, approvals, audit and rule versions to verify |
| RSK-036 | Export and exit | An export link is used after expiry or by another person | Data leak | 5 | 3 | 4 | 60 | A | Yes | Exports expire and are deleted; download streamed behind sign-in (`backend/app/tenant_export_api.py`) | `tests/test_tenant_data.py` (export expiry); download by another person: PL-23 (drafted, O15), threat-model test PT-13 to add | PT-11, PT-13 | REQ-EXP-003 | **Open (verification):** test PT-13, download by another person |
| RSK-037 | Backup and restore | A backup fails silently | Regulated records permanently lost at a disaster (no good backup) | 5 | 3 | 2 | 30 | A | No | Daily encrypted dump with SHA-256 manifest (`infrastructure/docker/backup/backup.sh`); backup-age check, 26 h (`scripts/check_backup_age.sh`); off-site copy (`docs/runbooks/GCP_DEPLOYMENT.md`) | `tests/test_backup_retention.py`, `tests/test_infra_backup_role.py`; restore drill | G-1, G-6 | REQ-BAK-001 | Acceptable after verification |
| RSK-038 | Backup and restore | Up to 24 hours of records lost (no point-in-time recovery; files on the server disk) | Lost complaints, signatures, awareness times; a report can be missed | 5 | 4 | 4 | 80 | A | Yes | Daily dump and daily disk snapshot only; the RPO is stated as 24 hours (owner decision B6b-D8) | Restore drill | G-1, G-2 | REQ-BAK-002 | **Open:** gap to the 15-minute target; closed by point-in-time recovery on pilot hosting. The recovery check (B6b Part D) shows each organisation the window to back-enter |
| RSK-039 | Backup and restore | A restore brings back erased personal data | Erased personal data back in use | 4 | 3 | 4 | 48 | A | Yes | Erasure log and `reapply_erasures` (`backend/app/tenant_purge.py`); restore runbook section 4 | Restore drill step (dry run recorded 3 Nov 2026) | - | REQ-BAK-001 | Acceptable after verification |
| RSK-040 | Backup and restore | A restore cannot be done (key lost) | Regulated records permanently lost (total loss) | 5 | 2 | 4 | 40 | A | Yes | The backup private key is kept off the server by the operator | Quarterly drill | G-7 | REQ-BAK-003 | **Open:** key custody needs a second holder (threat model G-7) |
| RSK-041 | AI (off) | An AI suggestion is accepted without review, or overrides a person | Wrong conclusion | 5 | n/a | n/a | n/a | A | n/a | AI release gate enforced in production (`backend/app/ai_release_gate.py`); advisory only | Golden evaluation before switch-on | PT-09 | (at switch-on) | Not applicable while AI is off |
| RSK-042 | AI (off) | Prompt injection from evidence files | Manipulated suggestion or data leak | 5 | n/a | n/a | n/a | A | n/a | Field allowlist for AI context (`backend/app/ai_boundary.py`); PII masking | Before switch-on | PT-09 | (at switch-on) | Not applicable while AI is off |
| RSK-043 | AI (off) | Customer data sent to a non-contracted provider | Privacy breach | 5 | n/a | n/a | n/a | A | n/a | Contracted-provider and retention checks (`genai/policy.py`, `genai/provider.py`) | `tests/test_ai_release_gate_unit.py` | PT-10 | (at switch-on) | Not applicable while AI is off |
| RSK-044 | E-mail intake | An e-mail to the intake address does not become a Case, or its received time is wrong | Missed or late complaint, clock starts late | 5 | 3 | 3 | 45 | A | Yes | Received = the server's own receipt time; unknown addresses refused at SMTP (EM-01); each accepted e-mail listed for a person to check | EM rows; `tests/test_mail_in.py`, `tests/test_email_intake_api.py`, `tests/test_mail_processing.py` | PT-08 | REQ-INT-001 | Acceptable after verification |
| RSK-045 | Back-entry after an outage | A Case entered after an outage counts its clock from the entry time, or is entered twice | Late report, or double counting | 5 | 2 | 2 | 20 | A | No | Clock counts from awareness, never from entry; a late-entry reason is required after 24 hours (422 `LATE_ENTRY_REASON_NEEDED`); possible duplicates shown before saving | B6-07 to B6-09; `tests/test_b6a_back_entry.py` | - | REQ-CLK-004 | Acceptable after verification |
| RSK-046 | Daily deadline list | The daily deadline list is not sent or is incomplete during an outage | Deadlines missed while MDARIX is down | 5 | 2 | 2 | 20 | A | No | An empty list is still sent, so a missing e-mail shows a problem; the last recipient cannot switch it off; CSV and PDF download | B6-01 to B6-06; `tests/test_b6a_deadline_list.py` | - | REQ-CLK-005 | Acceptable after verification |
| RSK-047 | Time source | The server clock drifts, so audit and signature times are wrong | Wrong times on regulated records | 4 | 2 | 2 | 16 | A | No | Clock check with a 1-second limit; degraded state and an operations alert (`scripts/clock_check.py`) | B6-10, B6-11; `tests/test_b6a_clock_unit.py` | - | REQ-OPS-001 | Acceptable after verification |
| RSK-048 | Reason for change | A regulated value is changed without a reason, or after signing without a flag | Unexplained change in the record | 4 | 2 | 1 | 8 | A | No | A reason is required on reporting-fact edits and on re-uploads behind a signed decision; a flag when facts change after signing; signed bytes unchanged | B6-36 to B6-38; `tests/test_b6a_change_reason.py`, `tests/test_b6a_reupload_reason.py` | PT-04 | REQ-AUD-004 | Acceptable after verification |
| RSK-049 | Signed reviews (audit trail, access, configuration) | A signed review does not reflect the true state, or changes after signing | Review evidence unreliable | 4 | 2 | 3 | 24 | A | No | Flags computed from the trail; every row marked before signing; own rows marked by another person; content fingerprint fixed at signing; configuration snapshot holds no secret (`backend/app/signed_reviews/`) | B6-28 to B6-35; `tests/test_b6a_signed_reviews.py` | PT-14 | REQ-AUD-005 | Acceptable after verification |
| RSK-050 | Rule register | The wrong rule version applies to an event (effective dating), or a new floor gives a different outcome from the one it replaces | Wrong conclusion or clock | 5 | 3 | 3 | 45 | A | Yes | Effective dating per version; equivalence tests against the previous floor; window floors (`backend/app/rule_register/`) | RR rows; `tests/test_b4_effective_dating.py`, `tests/test_b4_equivalence.py`, `tests/test_b4_window_floor.py`, `tests/test_b4_register_api.py` | - | REQ-RPT-005 | Acceptable after verification |
| RSK-051 | Investigation and challenge loop | An investigation conclusion is signed while a challenge or a changed fact is unanswered | Wrong conclusion signed | 4 | 3 | 3 | 36 | A | No | Challenge triggers and questions; facts and follow-up fields; the brief reflects open challenges | B5 rows; `tests/test_b5_loop_rules.py`, `tests/test_b5_loop_api.py`, `tests/test_b5_triggers.py` | - | REQ-INV-001 | Acceptable after verification |
| RSK-052 | Routine path | A routine (service or CAPA) path closes a complaint that needed a reportability assessment | Missed report | 5 | 3 | 3 | 45 | A | Yes | Routine path only after a signed Case check; urgent alert; switch per organisation | RT rows, UA rows; `tests/test_routine_rules_b7.py`, `tests/test_routine_path_switch.py`, `tests/test_urgent_alert_b7.py` | - | REQ-CLS-004 | Acceptable after verification |
| RSK-053 | EU and GB MIR files | A value is placed in the wrong MIR field, or the file is not valid against the form schema | Wrong report sent by the customer | 5 | 3 | 3 | 45 | A | Yes | MIR 7.3.1 and GB MIR 7.2.1 mappings; schema validation; file frozen at approval | B8 rows; `tests/test_b8_mir_xml.py`, `tests/test_b8_gb_mir_xml.py`, `tests/test_b8_mir_freeze.py`; owner's by-eye check of each form | - | REQ-ARD-003 | Acceptable after verification |
| RSK-054 | India, Canada, US roles | The wrong reporting role, form or clock is used for a market | Missed or late report | 5 | 3 | 3 | 45 | A | Yes | Rule book per market; role floors; frozen forms | B9 rows; `tests/test_b9_rule_book.py`, `tests/test_b9_india_chain.py`, `tests/test_b9_canada_chain.py`, `tests/test_b9_us_role_floors.py` | - | REQ-RPT-006 | Acceptable after verification |
| RSK-055 | Other countries | A country outside the five markets is not assessed or its report date is not tracked | Missed report in that country | 5 | 3 | 3 | 45 | A | Yes | Country recorded with its own conclusion; unsigned ones on the daily deadline list | OC rows; `tests/test_b9b_other_countries.py`, `tests/test_b9b_other_floor.py` | - | REQ-RPT-007 | Acceptable after verification |
| RSK-056 | Restore and outbox | After a restore, events delivered after the backup come back unsent and are sent again, or are lost | Duplicate or missing notifications | 3 | 4 | 4 | 48 | B | Yes | None in the restore runbook today | Recovery check (B6b Part D) | G-1 | REQ-BAK-004 | **Open:** the recovery check holds every unsent event older than the restore point (owner decision B6b-D10) |
| RSK-057 | Trace this value | The trace shows the wrong origin for a value | Wrong information shown | 3 | 2 | 3 | 18 | B | No | Read only; values of the traced field only; origin from the import line and the snapshot | B6-39, B6-40; `tests/test_b6a_trace.py` | - | REQ-REC-004 | Acceptable after verification |
| RSK-058 | Similar-wording duplicates | A duplicate is not suggested, or a wrong pair is suggested | Duplicate complaint not linked | 3 | 3 | 3 | 27 | B | No | Suggestion only; the person chooses attach or create; dismissed pairs not shown again | B6-41, B6-42; `tests/test_b6a_similar_wording.py`; known limit: typos are missed | - | REQ-INT-002 | Acceptable after verification |
| RSK-059 | Trends and signals | A pattern to review is missed or shown wrongly | Signal reviewed late | 3 | 3 | 4 | 36 | B | No | "Pattern to review", never a confirmed signal; statistics tests | `tests/test_signal_trend_rules.py`, `tests/test_trend_check_statistics.py` | - | REQ-TRD-001 | Acceptable after verification |
| RSK-060 | Product 360 and Supplier 360 | Counts by product, version, lot or supplier are wrong | Wrong information shown | 3 | 3 | 3 | 27 | B | No | Counts from the organisation's own records; links to the source records | P360 and S360 rows; `tests/test_supplier360_rules.py`, `tests/test_product360_links.py` | PT-16 | REQ-PRD-001 | Acceptable after verification |
| RSK-061 | CAPA effectiveness | An effectiveness check shows as done or not due when it is due | Late effectiveness check | 3 | 3 | 3 | 27 | B | No | CAPA reference and effectiveness check with due dates | CP rows; `tests/test_reporting_capa_rules.py`, `tests/test_reporting_capa_api.py` | - | REQ-CPA-001 | Acceptable after verification |
| RSK-062 | QMS documents | A signed PMS document version changes after signing | Signed record altered | 4 | 2 | 2 | 16 | A | No | A signed version is never edited; a new version supersedes it | `tests/test_qms_documents_rules.py`, `tests/test_qms_documents_api.py` | PT-04 | REQ-REC-005 | Acceptable after verification |
| RSK-063 | Notifications and outbox | A notification is lost or stays dead-lettered unseen | Late action | 3 | 2 | 2 | 12 | B | No | Dead-letter with reason; operations alerts; audited replay of one event (`scripts/replay_outbox.py`) | `tests/test_outbox_resilience.py`, `tests/test_replay_outbox_script.py` | PT-15 | REQ-OPS-002 | Acceptable after verification |
| RSK-064 | Value Centre and dashboards | A figure on the Value Centre or a dashboard is wrong | Wrong management information; no record or decision effect | 2 | 3 | 4 | 24 | C | No | Medians on known data; sample records excluded; no per-person numbers | B6-43, B6-44; `tests/test_b6a_value_centre.py` | - | REQ-PRD-002 | Acceptable |
| RSK-065 | Rule register | The same person builds and approves a rule version | No independent check of rule content | 4 | 2 | 1 | 8 | A | No | The register refuses a version unless its builder and approver are two different staff accounts (`approval.built_by_account`, `approval.approved_by_account`), the approver's account may approve rule content, and the names shown are the accounts' names; typed names are never compared (`backend/app/rule_register/register.py`, `STAFF_ACCOUNTS`; owner decisions O3, O10) | `tests/test_rule_register_unit.py` (refused and allowed cases); DT-12 and DT-14 cover the organisation layer | - | REQ-SOD-003 | Acceptable after verification |
| RSK-066 | Purge and retention | The wrong organisation's records are purged, or records are purged before their retention date or while under legal hold | Regulated records lost | 5 | 2 | 3 | 30 | A | Yes | Purge needs MFA and a completion job; legal hold blocks erasure (`backend/app/tenant_purge.py`, `backend/app/legal_hold_api.py`); the database refuses early deletion of audit events (trigger `audit_events_retention`, migration `md23_pilot_readiness.py`) | `tests/test_export_purge_mfa.py`, `tests/test_purge_completion_job.py`, `tests/test_customer_admin_erasure_hold.py` | - | REQ-REC-006 | Acceptable after verification |
| RSK-067 | Sign-in and sessions | A deactivated account, an expired session or a reset second factor still allows an action on a record | Unauthorised change or signature | 4 | 2 | 3 | 24 | A | No | Session lifecycle and permissions checked on each request (`backend/app/access/session.py`, `backend/app/auth_router.py`); lockout after wrong codes | `tests/test_auth_session_lifecycle.py`, `tests/test_session_permissions.py` | PT-05 | REQ-SEC-002 | Acceptable after verification |

## 6. Summary

- 67 failure modes: 57 class A, 9 class B, 1 class C. Three AI rows (RSK-041 to -043) are not rated while AI is off.
- Every rated row names its REQ IDs in `requirements.csv` (69 requirements: 59 class A, 9 class B, 1 class C); the 34
  rows without a seed got their IDs on 12 Nov 2026 (OP-3 closed). The three AI rows get theirs at switch-on.
- 32 rows need action under RA-R04: RSK-001 to -008, -017, -018, -022, -024 to -027, -029 to -031, -033, -034, -036,
  -038 to -040, -044, -050, -052 to -056, -066 (RSK-029, -039 and -040 added on 12 Nov 2026 by owner decisions O7 to O9). For most of them the action is to execute their class-A scenarios.
- **Open control gaps** (action named in "Residual risk"):
  - RSK-002: GB, India day-1 and Canada counting rules to be confirmed with the consultant.
  - RSK-003: question sets to be confirmed by the consultant.
  - RSK-013: negative test that the trial same-person allowance never applies to a pilot organisation.
  - RSK-017: audit-chain anchors to be copied off the server.
  - RSK-018: route-by-route audit completeness check.
  - RSK-025: independent penetration test before the first paid pilot.
  - RSK-026: negative test of organisation scope per background job type.
  - RSK-040: a second holder of the backup key (threat model G-7).
  - RSK-038: RPO 24 hours today; target 15 minutes with point-in-time recovery on pilot hosting.
  - RSK-056: outbox events held after a restore (recovery check, B6b Part D).
- **Verification gaps** (a test or check missing): RSK-024 (no scenario or test), RSK-026 (outbox test covers part
  only), RSK-023 (missing-block scenario and test), RSK-030 (job never runs in a pilot organisation), RSK-035 (readable export), RSK-036 (download by another
  person: threat-model test PT-13 to add).
- Each Open row a release relies on that is class A or needs action needs the signed acceptance of RA-R07 until it is closed.

## 7. Open points

| # | Point | Owner |
|---|---|---|
| OP-1 | Review every severity (quality approver) and the scales and action rule (consultant, MDX-VAL-013 question 7) | Srinivas |
| OP-2 | Occurrence and detectability are the system owner's judgement from reading the code; the consultant to sample-check them | Sriharsha |
| OP-3 | Closed 12 Nov 2026: REQ IDs assigned to the 34 rows in `requirements.csv`; the quality approver reviews each requirement text (URS approval) | Srinivas |
| OP-4 | Decide whether the customer's own ISO 14971 file references this assessment (a line in the customer templates) | Srinivas |
| OP-5 | Native CAPA lifecycle failure modes, when specified | Srinivas |

## Signatures

Unsigned. The signed PDF and its `signatures.csv` row are added after review (MDX-VAL-000 section 2.6).

| Role | Name | Meaning of signature | Signature | Date |
|---|---|---|---|---|
| Author (R), system owner | Sriharsha Telikicherla, Product & Engineering | I am responsible for every proposed rating and reviewed every line of the draft. | | |
| Reviewer (C) | Independent CSV consultant | I reviewed the severities, scales and ratings; my comments are recorded. | | |
| Approver (A), quality approver | Srinivas Telikicherla, QA/RA | I reviewed every severity and approve this assessment for use. | | |
