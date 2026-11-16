# MDX-B10-005 Traceability Structure

| Field | Value |
|---|---|
| Document ID | MDX-B10-005 |
| Title | Traceability Structure: requirement → risk → scenario → test → evidence |
| Version | 0.1 DRAFT |
| Owner | Srinivas Telikicherla (QA/RA) |
| Author | Drafted for review |
| Date | 8 Nov 2026 |
| Status | DRAFT |
| Code baseline | v0.10.92 |
| Approval | |

## 1. Purpose
This document sets how MDARIX traces each requirement to its risks, its scenarios, its tests and its evidence, so a traceability matrix can be produced for every release. The scenario register is the single backbone (B10 plan §1).

## 2. Scope
All requirements of MDARIX 1.0 from the approved specs (B2–B9, W1), starting with the high-risk functions of MDX-B10-004. The structure also feeds the customer validation package (W-F).

## 3. References
| Ref | Document |
|---|---|
| R1 | `MDARIX-planning/scenario-register.md` |
| R2 | MDX-B10-003 Validation Plan; MDX-B10-004 Software Risk Assessment |
| R3 | `MDARIX-R1/docs/compliance/CSA_REQUIREMENTS_TRACEABILITY.md`, `CSA_EVIDENCE_MANIFEST_TEMPLATE.json` (v0.10.92) |
| R4 | `MDARIX-R1/docs/handover/50_FEATURE_TRACEABILITY_MATRIX.md`, `51_TEST_TRACEABILITY_MATRIX.md` (v0.10.92) |
| R5 | Approved specs: `b2-case-design/spec.md`, `w1-product-supplier-360/spec.md`, `authority-forms-spec/spec.md`, `decision-tree-deep-dive/report.md` |

## 4. The chain
```
Intended use (MDX-B10-001)
  └─ REQ-<area>-nnn  (requirement, in the approved spec)
       ├─ RSK-nnn     (failure mode, MDX-B10-004; sets class A/B/C)
       ├─ Scenario ID (IN-, RG-, IV-, CP-, CI-, TR-, DT-, P360-, S360-, later RP-, RT-)
       │    └─ TEST    (automated test path::name, or protocol step OQ-/PQ-nnn)
       │         └─ EVD-<release>-nnnn  (execution record, screenshot, trace, SHA-256 in the manifest)
       └─ Deviation DEV-<release>-nnn (if any)
```
Rules:
1. Every requirement has at least one scenario. A class-A requirement has at least one **negative** scenario (something that must be refused).
2. Every class-A requirement has at least one RSK row.
3. A scenario can verify several requirements; a requirement can have several scenarios.
4. Evidence is per release. A PASS from an older release counts only if the change-impact assessment says the function was not touched.
5. BLOCKED and NOT RUN are never counted as PASS.

## 5. Requirement ID scheme
Format: **REQ-&lt;AREA&gt;-nnn**, three digits, never reused. A changed requirement keeps its ID and gets a new revision letter in the spec (REQ-CLK-002 rev B).

| Area | Meaning | Legacy IDs mapped in |
|---|---|---|
| INT | Intake and first contact | |
| AWR | Awareness | |
| TRG | Triage and escalation | |
| CLS | Service-vs-complaint and classification | |
| RPT | Reportability decision and question sets | |
| CLK | Legal clocks and deadlines | |
| SIG | Electronic signatures and authority | MDX-AUD-001 (part) |
| SOD | Segregation of duties | |
| AUD | Audit trail | MDX-AUD-001 |
| REC | Record versioning, snapshots, retention | MDX-DOC-001 (part) |
| ARD | Authority-report data (3500A/eMDR, MIR, HC) | |
| TEN | Tenant isolation and field protection | MDX-SEC-001, MDX-SEC-002 |
| IMP | Import, mapping, lineage | |
| SMP | Sample (trial) data and sample clock | |
| EXP | Export and inspection pack | |
| BAK | Backup, restore, recovery | MDX-OPS-001 (part) |
| OPS | Installation, health, worker, operations | MDX-OPS-001 |
| SEC | Authentication, sessions, uploads, platform security | |
| AI | AI helpers (2027) | MDX-AI-001 |
| INV | Investigation | |
| CPA | CAPA and effectiveness | |
| TRD | Trends and patterns | |
| PRD | Product 360 / Supplier 360 | |

Other ID formats: RSK-nnn (risk), OQ-/PQ-/IQ-nnn (protocol steps), DEV-&lt;release&gt;-nnn (deviation), EVD-&lt;release&gt;-nnnn (evidence), PT-nn (pen-test threats, MDX-B10-006).

## 6. How the matrix is generated per release
**Inputs (all text files under version control):**
1. `requirements.csv` (new, per spec or one register): REQ ID, revision, text, spec reference, risk IDs, class, scenario IDs.
2. `scenario-register.md`: scenario ID, status, release.
3. Test results: pytest JUnit XML and vitest output from the tagged build; each automated test names its scenario IDs in a marker or docstring (for example `@pytest.mark.scenario("TR-24")`).
4. Execution records from the validation package (class-A protocol runs), each naming scenario IDs and evidence IDs.
5. Evidence manifest (`CSA_EVIDENCE_MANIFEST_TEMPLATE.json` format) with SHA-256 of every artifact.

**Output:** one matrix per release (CSV and a readable PDF/HTML), with per row: REQ, class, RSK, scenarios, tests, latest result, evidence IDs, deviations, and a status: **Verified / Not verified / Failed / Blocked / Requires human decision.**

**Checks the generator must fail on:** a class-A REQ without a negative scenario; a REQ with no scenario; a scenario cited but not in the register; a PASS without evidence; a test that names an unknown scenario.

Until the generator exists (a B10-1 item), the matrix is kept by hand from the same inputs. Building the generator is engineering work for B10-1; this document only fixes its inputs, outputs and checks.

## 7. Seed rows (high-risk functions)
Requirement wording is a first draft from the specs and code; each will be confirmed when its spec is approved. "Tests" are existing automated tests at v0.10.92; none of these has a validation execution record yet.

| REQ | Requirement (short) | Class | RSK | Scenarios | Tests (existing) |
|---|---|---|---|---|---|
| REQ-RPT-001 | An Unknown answer is never treated as No; "not reportable" is refused while an Unknown could make the event reportable | A | 001 | RG-05, DT-06, DT-07, DT-08 | `tests/test_market_assessment_rules.py` |
| REQ-RPT-002 | Each market an event touches gets its own assessment and signed conclusion | A | 005 | RG-07, RG-08, RG-13, TR-12, DT-21 | `tests/test_market_assessment_api.py` |
| REQ-RPT-003 | Floor questions cannot be removed, reworded or lowered by organisation rules | A | 003, 006 | DT-01, DT-02, DT-03, DT-36 | (B4b, not built) |
| REQ-RPT-004 | A signed conclusion names the rule version used; a later version never changes it | A | 004 | RG-12, DT-17, DT-18, DT-20 | `tests/test_release_0_10_88_resign.py` |
| REQ-RPT-005 | Floor rules give the same outcome and report type as 0.10.92 for every Yes/No/Unknown combination | A | 003 | DT-37, DT-33 | (B4, to add) |
| REQ-CLK-001 | Deadlines are counted in the authority's time zone and the organisation's: the earlier of the two latest days, ending at the earlier end, also when awareness falls on different days in the two zones (rev B, owner decision O35, 14 Nov 2026; text in `requirements.csv`) | A | 002 | RG-10, RG-11, DT-16 | `tests/test_legal_deadlines.py` |
| REQ-CLK-002 | Every screen, export and reminder uses the same deadline | A | 002 | TR-12, RG-10 | `tests/test_one_deadline_api.py` |
| REQ-CLK-003 | No country known: every market's shortest clock applies | A | 005 | RG-06, TR-40 | `tests/test_intake_triage_api.py` |
| REQ-AWR-001 | Awareness is the earliest known first knowledge; linking keeps the earliest | A | 007 | RG-09, CI-06, TR-04 | `tests/test_intake_rules.py` |
| REQ-AWR-002 | Missing awareness gives a provisional clock and a clarification task | A | 008 | IN-08, TR-32 | `tests/test_intake_rules.py` |
| REQ-AWR-003 | Awareness later than the earliest known needs a signature and (outside trial) a second person | A | 007, 013 | TR-05, CI-08 | `tests/test_intake_triage_api.py` |
| REQ-TRG-001 | Death, serious injury, threat or harm words put the case on the fast track | A | 031 | IN-05, CI-13, TR-27–TR-31 | `tests/test_intake_triage_api.py`, `tests/test_signals_triage.py` |
| REQ-TRG-002 | New information that raises severity reopens triage with an alert | A | 031 | TR-02, TR-11, TR-19 | `tests/test_intake_triage_api.py` |
| REQ-CLS-001 | "Service only" is reachable only from the outcomes table row 2; no override reaches it | A | 033 | IN-03, IN-21, CI-19 | `tests/test_intake_rules.py` |
| REQ-CLS-002 | Complaint → service down-grade is refused; service → complaint keeps awareness | A | 033 | CI-24, CI-25 | `tests/test_intake_rules.py` |
| REQ-CLS-003 | Classification never sets a deadline, trigger or conclusion | A | 034 | IN-22 | `tests/test_complaint_disposition_rules.py` |
| REQ-SIG-001 | Every signing needs the password session plus a fresh authenticator code | A | 009 | DT-12 | `tests/test_signing_code_refusals.py`, `tests/test_mfa_mvp.py` |
| REQ-SIG-002 | A signature binds the exact record version and snapshot hash; verification recomputes both | A | 012 | DT-15, IV-16 | `tests/test_human_decision_unit.py` |
| REQ-SIG-003 | Two people signing the same record at once: the second is refused | A | 012 | CI-26, TR-24 | `tests/test_human_decision.py` |
| REQ-SIG-004 | A signature is valid only when both the record and the signature are saved | A | 010 | (new scenario needed) | `tests/test_signing_recovery.py` |
| REQ-SOD-001 | Outside a trial, the maker cannot approve the same record | A | 013 | CI-17, CI-34, CI-35, DT-12 | `tests/test_case_reviews.py` |
| REQ-SOD-002 | Administrators never approve regulated decisions | A | 014 | DT-13 | `tests/test_authorization_matrix.py` |
| REQ-AUD-001 | Audit rows cannot be updated or deleted | A | 016 | (new scenario needed) | `tests/test_day35_audit_immutability.py` |
| REQ-AUD-002 | The audit hash chain verifies daily and on demand; a break is reported | A | 017 | (new scenario needed) | `tests/test_audit_hash_chain.py` |
| REQ-REC-001 | A signed record is never edited; corrections supersede it | A | 019 | IV-16, CI-07, TR-02 | `tests/test_human_decision_unit.py` |
| REQ-REC-002 | A submitted report is never overwritten | A | 020 | RG-15, RG-16, RG-17 | `tests/test_authority_reports_rules.py` |
| REQ-ARD-001 | 3500A and eMDR values come only from the approved snapshot; nothing is guessed | A | 022, 024 | RG-19 | `tests/test_fda_3500a_emdr.py` |
| REQ-TEN-001 | No organisation can read or change another's data through any surface | A | 025 | P360-11, S360-14 | `tests/test_rls_coverage.py`, `tests/test_cross_tenant_routes.py`, `tests/test_tenant_security.py` |
| REQ-TEN-002 | Background jobs run in the scope of the event's organisation only | A | 026 | (new scenario needed) | `tests/test_outbox_resilience.py` (partial) |
| REQ-IMP-001 | Rows that fail checks go to quarantine with reasons; harm rows still reach triage | A | 027 | IN-13, TR-21, TR-36 | `tests/test_import_quarantine_unit.py` |
| REQ-SMP-001 | The sample clock moves sample records only, never customer records | A | 030 | CI-18, TR-16, P360-13 | `tests/test_sample_story_days.py` |
| REQ-EXP-001 | The organisation export holds every record, file and the verified audit head, with SHA-256 per entry | A | 035 | (new scenario needed) | `tests/test_day25_retention_export.py` |
| REQ-BAK-001 | A backup restores into an empty database; the audit chain verifies and erasures are re-applied | A | 037, 039 | (new scenario needed) | `tests/test_backup_retention.py` |

**Gaps found while seeding:** six requirements (SIG-004, AUD-001, AUD-002, TEN-002, EXP-001, BAK-001) have no scenario in the register. Proposed: add a **PL-xx (platform)** scenario group for audit, signature recovery, background jobs, export and restore.

## 8. Open points
| # | Point | Owner |
|---|---|---|
| OP-1 | Approve the area codes and the REQ format. | Owner |
| OP-2 | Approved by the owner on 12 Nov 2026 (MDX-VAL-000 section 4, O15): PL-01 to PL-45 drafted in the scenario register; the owner reviews each expected result. | Owner |
| OP-3 | Decide where `requirements.csv` lives (MDARIX-planning or the product repository). Recommended: the product repository, so it versions with the code. | Owner |
| OP-4 | Agree the test-marker convention (`@pytest.mark.scenario(...)`) before B2 tests are written. | Engineering |
| OP-5 | Handover 50/51 matrices predate the scenario register; retire or regenerate them. | Engineering |
