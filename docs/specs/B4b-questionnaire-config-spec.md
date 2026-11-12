# B4b: Reportability questionnaire configuration

Version 1, 11 Nov 2026. **APPROVED by the owner on 11 Nov 2026 (see "Approval record").** Nothing here is built. Per the owner's automatic chain (11 Nov), B4b starts after B9b, and only once this spec is approved. Decisions marked **⚑** touch regulatory interpretation or signed records: they need the owner's explicit answer. Each ⚑ says what the build does **if no answer arrives** (always the safer path).

- **Sources:** `decision-tree-deep-dive/report.md` (approved 7 Nov: §3a–3f, G1–G13, S1–S9, D1–D12, DT-01..DT-38), `development-cycle-1.md` (B4b row), `b4-rule-register/spec.md` (approved 11 Nov: engine, floor F1–F12, effective dating, R-D1..R-D14, "Build status" runs 1–2), `b9-markets/spec.md` (role floors, `IN-floor-2`, `CA-floor-2`), `other-country-reports/STATE.md` and `b8-eu-gb-mir/STATE.md` (migration heads), `scenario-register.md` (DT, RG).
- **Code read** (read-only, `git show feat/b8-eu-gb-mir:<path>`, tip `d57c65a9`). Every `file:line` is on that branch, under `backend/app/`, except `sections/...` (under `frontend/src/features/workspace/`) and `customer-admin/...` (under `frontend/src/features/`). B9b's branch (`feat/b9b-other-countries`) was read only for its register and migration. Step 0 re-checks every line on B9b's tip.
- **Regulatory text:** only what the planning files and code already hold. Every citation stays **"starter, for your consultant to confirm"**.
- **Not in B4b:** MDARIX templates and their update flow, Excel import/export, floor exceptions, regulatory change impact for MDARIX floor changes (all B4c, with E4). The "Other country" tree (B9b) is not configurable.

---

## 1. Purpose, in plain words

**Each customer can set their own reportability questionnaire per market, on top of a floor they cannot weaken.**

- The **MDARIX floor** stays as B4 built it: locked questions and rules, cited, versioned, picked by the awareness day.
- The **organisation layer** is new. It holds the customer's own questions, answer types, pre-fill, help text, order, rules and required reasons.
- Customer rules can only **raise**: to Reportable (with one of the market's legal report types) or to Needs more information. They can never lower an outcome or lengthen a clock. This holds by construction and is proven by a property test.
- Every version is tested, back-tested, approved by a second person (never an administrator), and given an effective date.
- The answer screen gets simpler (S1–S9): fewer clicks, one-sentence result, one answer screen, one editor.

### What changes for users
| Who | Today | With B4b |
|---|---|---|
| Customer Admin | No questionnaire screen; cannot author (`access/permissions.py:98`; `decision_guides/router.py:58`) | Customer Admin › Reportability questionnaires: prepares drafts. Still never approves (`decision_guides/rules.py:344-351`) |
| Trial Leader | Settings › Reportability guides and Decision trees › Edit this tree: two editors (`sections/Settings.tsx:35, 62`; `sections/DecisionTrees.tsx:37`) | One editor, Settings › Reportability questionnaires; "Edit this tree" opens it |
| Regulatory reviewer / approver | Approves extra questions that "never change the conclusion" (`sections/TreeAnswer.tsx:458`) | Approves real rules, with tests, a 12-month back-test, a diff and an effective date |
| Signer | 17 clicks and 5 typed entries on RV-11 (report §2.2) | 10 clicks and 4 typed entries; one-sentence result with its basis |
| Signer concluding Not reportable against a Reportable outcome | Alone, with a 10-character reason (`reportability/markets.py:846-858`) | A second person (regulatory approver) must agree outside the trial; the clock keeps running (D7) |
| Auditor | Sees the guide code only | Sees floor version, organisation version, the rules that applied (floor and organisation), and why |

---

## 2. What exists today (and what B4 already gives)

| Part | Today | Evidence |
|---|---|---|
| Customer guide versions | Table `decision_guide_versions`: questions, tests, results, editors, fingerprint, approval; states Draft, Waiting, Published, Superseded, Discarded; one open and one published per market | `db/models/guides_communications.py:79-130`; `decision_guides/rules.py:41-55` |
| What a customer may change | Explanation and examples beside locked floor questions; up to 10 extra questions that never count | `decision_guides/rules.py:1-20, 30-35, 142-211` |
| Test matrix | Starter rows locked; customer rows only on core questions; 30 rows at most; run against the fixed logic | `decision_guides/rules.py:223-234, 270-311` |
| Approval | Second person, never an editor, never an administrator; password and authenticator code; publishes at once | `decision_guides/rules.py:344-351`; `decision_guides/router.py:657-665, 673-700` |
| Approval signature text | "Assessments started after publication use it" | `decision_guides/rules.py:354-359` |
| Version an assessment uses | The published version when it starts; kept after | `decision_guides/service.py:1-3, 32-56` |
| Questions shown | Built from **today's** floor question set, not the floor at awareness | `decision_guides/rules.py:63-64, 117-139` |
| Floor engine (B4) | Kleene three-valued logic over data; operators `any`, `all`, `ref`, `is_yes`, `is_no`, `is_unknown`, `maybe`, `type`; no negation, no choice test | `rule_register/engine.py:1-17, 23, 49-112` |
| Floor at awareness (B4) | Picked at every save; signing refused with `409 FLOOR_CHANGED` if it moved | `reportability/assessment_router.py:172-175, 242-251, 548-559` |
| Rules applied (B4) | Floor rules only, stored per draft | `reportability/assessment_router.py:250`; `rule_register/engine.py:115-131` |
| Signed material (B4) | Floor code and hash, rules applied, date calculation | `reportability/assessment_router.py:673-685` |
| Readable logic (B4) | Floor conditions rendered in words | `rule_register/router.py:27-46` |
| Answers | Yes, No, Unknown, Not applicable only | `reportability/markets.py:39-40` |
| Pre-fill | Death and malfunction, US and India; injury as a note | `reportability/markets.py:656-703` |
| Triage threat and remedial action | Booleans, default false (B2's "Not known yet" not built for these two) | `db/models/intake.py:294-295` |
| Override rule | Not reportable refused while pending; any override needs a 10-character reason; one signer | `reportability/markets.py:846-858` |
| Label | "Pending information" | `reportability/markets.py:65-69` |
| Duplicate screens | `DecisionGuides` in Settings and classic Complaints; the watch's own drawer | `sections/Settings.tsx:20, 35, 62`; `sections/Complaints.tsx:40, 140`; `sections/ReportabilityWatch.tsx:45, 218` |
| Permissions | Business permissions come from roles only; permission sets in Roles & Access do not grant them | `access/permissions.py:1-10, 78-99, 205-207`; `customer-admin/sections/Access.tsx:10` |
| Additional roles | Workflow roles a person may hold besides their account role | `role_codes.py:45-54` |
| Tasks | `WorkflowTask.task_type` is free text (no check), so a new task type needs no migration | `db/models/workflow.py:116-154` |
| Scheduler sweep | Reminders run per organisation by the scheduler | `reportability/reminders.py:1-10` |

---

## 3. Design

### 3.1 The organisation layer (stored on the guide version)
- **Questions.** The floor questions in the floor's order, with the customer's explanation and examples (as today). Then the customer's own questions (`X1`…), each with:
  - text, definition, clause, basis (as today);
  - **answer type** (D9, approved): Yes/No/Unknown, Yes/No/Unknown/N.A., One choice (2–10 options) usable in rules; Date, Number, Short text recorded only;
  - **position**: after any floor question (floor questions keep their order);
  - **show only when**: a condition on earlier answers (own questions only);
  - **pre-fill**: a record fact (§3.5), as "Confirm" only;
  - **required to conclude Not reportable** (Short text only). This is how the organisation's **required not-reportable reasons** work (21 CFR 803.18 basis, starter). No separate setting is needed (B4b-D10).
  - **retired**: kept on old versions, absent from new ones; refused while a rule uses it (DT-29).
- **Limits:** 20 own questions (today 10, `decision_guides/rules.py:35`), 20 own rules, 50 test rows (today 30).
- **Rules.** `{id: "O-1", if: <condition>, outcome: "REPORTABLE" | "NEEDS_MORE_INFORMATION", type: <market report type, Reportable only>, reference: "QP-08 §4"}`.
  - Conditions: a question is Yes; is No; is Unknown; a choice equals an option; any of; all of; one level of brackets.
  - "Is No" is three-valued (Unknown stays undecided: floor F3). "Is Unknown" is decided. Two new engine operators: `not` (Kleene negation) and `eq` (choice; unanswered is undecided).
  - There is **no "Not reportable" outcome** (D3). The builder does not offer one; the server refuses one.
- **Floor pre-fill switched off.** The organisation may switch off a floor pre-fill (more work, never less safe). It may not add one to a floor judgement question (DT-27).
- **Floor the version was built on:** `floor_code` (information; the floor that applies is still picked by awareness).

### 3.2 How the two layers combine (the engine)
New function `engine.combined(floor_content, layer, answers)`. The floor's `evaluate` is unchanged (B4 equivalence stays green).

1. **Outcome.** Order: Not reportable < Needs more information < Reportable.
   - Reportable if the floor says Reportable, or any own Reportable rule applies.
   - Else Needs more information if the floor says so, or any own rule applies or could apply.
   - Else Not reportable.
2. **Report type on the form** (B4b-D1 ⚑). When the floor's rules apply or could apply, the form carries the floor's type (today's type rows). Only when the floor says Not reportable does an own rule's type go on the form (the first in the market's precedence among own rules that apply or could apply).
3. **Due date.** The earliest of: the floor's clock (today's `market_clock`, `reportability/markets.py:991-1000`), and the legal period of each own Reportable rule that applies or could apply, counted the floor's way. When an own rule makes the date earlier, the screen says "Earlier by your rule O-1".
4. **Rules applied.** `rules_applied` keeps the floor's entries as B4 does, plus own rules with `"layer": "ORG"`, their state, and any rule suspended (point 6).
5. **Folding.** The floor's folding rows stay as they are (proven in B4). A floor question that an own rule uses is **never folded**; it shows "Asked because your rule O-1 uses it". Own questions hide only when their "show only when" is decided false.
6. **A rule that names a question the floor does not have** (an older floor at awareness, a role floor such as `US-IMP-floor-1` without US6, or a retired question): the rule is **suspended** for that assessment, listed on the result and in the signed material (B4b-D2 ⚑).

**Why it can never weaken the floor.** The floor is always evaluated in full. The combination only takes the higher outcome and the earlier date, and never changes the floor's form type. A property test proves it (DT-36): for each market, 20,000 random own layers (fixed seed) over random answer sets, the combined outcome is never lower, the due date never later, and the form type is the floor's whenever the floor is not Not reportable. An empty layer gives B4's results byte for byte.

### 3.3 Which version applies (D5, approved; B4 R-D3)
- **Floor:** the version in force on the awareness day (B4, unchanged).
- **Organisation layer:** the version in use when the assessment starts, stored as today in `question_set` (`db/models/market_assessment.py:92`).
- **Questions shown:** the floor's questions **at awareness**, with the layer's explanations laid over them by question id, then the own questions. Today they are built from today's floor (`decision_guides/rules.py:63-64`); B4b fixes this.

### 3.4 Versions, effective dates and approval
- **Effective from** (G7): date, time and the organisation's zone, chosen when the draft is sent for approval. It is part of the fingerprint, so the approver approves that date. It cannot be in the past. Empty means "at approval".
- **New state `SCHEDULED`** between approval and the effective moment. At most one scheduled version per market.
- **In use** = the scheduled version once its moment has passed, else the published one. Reads compute it, so there is no gap if the sweep is late. The reminders sweep (`reportability/reminders.py`) then marks it Published and the earlier one Superseded, and runs the re-check (§3.6).
- **Send for approval** needs: every test row passing (starter, RG and own rows), the back-test run, and a change reason (as today, `decision_guides/router.py:573-587`).
- **Approval** as today: second person, never an editor, never an administrator, password and authenticator code; one-person trial allowed and labelled (`decision_guides/router.py:673-700`). The approver sees the diff, tests, back-test and effective date.
- **Signature meaning** (B4b-D4 ⚑): "I approve version N of the {market} reportability questionnaire for use: its questions, rules, clauses and test results as shown. Assessments started on or after {date, time, zone} use it. Its rules can only add scrutiny to the MDARIX floor; a person concludes and signs." Signed approvals already made keep their text.

### 3.5 Tests and back-test
- **Rows:** MDARIX starter rows (locked, `decision_guides/rules.py:223-234`), the market's RG rows (RG-01 to RG-05, RG-10, RG-12, RG-13; locked; new), and own rows that may use own questions. Expected: Reportable (with type), Needs more information, Not reportable.
- **Run against** the floor in force at the version's effective date, and also today's floor when they differ.
- **Back-test (D10, approved):** the version re-runs every signed conclusion of that market in the last 12 months (by signing date), each under its own signed floor (pre-B4 rows read as version 1, as `reportability/assessments.py:102` does). Shown: "212 same · 3 different · 40 need your new question". The last group are differences that rest only on own questions that were never asked. Information, not a block. Stored with the version's results.

### 3.6 Re-check when a new organisation version comes into use (D6, G10)
- **Open draft assessment** on an older layer: banner "Version 5 is now in use: [Re-check with it] (see what changes) or [Continue on version 4] (a reason, kept with your signature)". The reason goes in a new column and in the signed material.
- **The floor never waits:** B4's `409 FLOOR_CHANGED` still applies.
- **Signed conclusion on an open complaint** that version 5 would decide differently: a `QUESTIONNAIRE_RECHECK` task to the regulatory reviewers, never an automatic change. Which differences make a task: B4b-D6 ⚑.
- **Closed complaints:** in the version's impact list only (G10, approved).
- The task closes when a new signed version exists, or with "No re-check needed" and a reason (audited).

### 3.7 Pre-fill (S3)
- MDARIX keeps a fact catalogue: death, malfunction, serious injury (note only), incident country, product registered in a market (Settings › Products), device class, IVD, triage severity, triage threat, triage remedial action.
- Every pre-fill is a **"Confirm"** answer, never automatic. A floor judgement question never gets one (0.10.83).
- **New floor pre-fills (B4b-D5 ⚑)**, kept in a separate MDARIX procedure file `prefill-starter-2` (the floors' own `prefill` stays unchanged, so B4 equivalence holds and no draft gets `409 FLOOR_CHANGED`):
  - recorded death → EU2, GB2, CA3: **Yes only** ("might have led to": "no death" never pre-fills No);
  - incident country → Canada CA5 ("in Canada"), and GB vs NI;
  - product registered in Canada → CA1;
  - triage threat → EU/GB threat question, **Yes only**;
  - triage remedial action → US6, **Yes only**.
  - The last two are Yes only because the triage fields are booleans that default to false (`db/models/intake.py:294-295`): false cannot mean "not known".
- Own questions may map to any fact.

### 3.8 Downgrade override (D7, approved; mechanics B4b-D3 ⚑)
- Outside the trial, signing **Not reportable when the outcome is Reportable** saves the signature as **"Awaiting a second person"**.
- Until the second person agrees, the Reportable outcome governs:
  - the report draft is created, as for a signed Reportable conclusion;
  - its clock runs and shows on the watch.
- **Second person:** holds `regulatory.approve`; is not the first signer; is not an administrator. Password and authenticator code. Their agreement is its own `SignedApprovalRecord`. Then the existing "signed Not reportable cancels an unsubmitted report" follows (`authority_reports/router.py:1134`).
- **If refused:** the first signature stays on record, marked "Not agreed by {name}: {reason}". The signer must sign again (a new version, OD-4).
- **What changes on the signed row:** only status columns (as `superseded_by` today, `db/models/market_assessment.py:114`). The signed material and fingerprint never change.
- **Trial:** allowed and labelled "Same person (trial practice)".
- **Not affected:** an upgrade (Not reportable → Reportable), and the routine path (it never signs against a Reportable outcome, floor F12).

### 3.9 Simpler answering (S1, S2, S4–S9)
- **S1** "Confirm the N facts from the record": one button; each fact still listed with its source; changing one still needs a reason.
- **S2** "None of these" on a criteria group: stores No for each criterion with one shared reason. Disabled when a fact says Yes (DT-38).
- **S4** Progress: "4 of 6 answered · 2 can still change the outcome". The count is computed by trying each answer for each open question. Floor questions are hidden only by the floor's own folding (B4b-D9).
- **S5** One-sentence result with its basis, built from the rules that applied (floor and own).
- **S6** An MDARIX plain one-liner above each floor question, from a data file `plain-words-1` (starter, reviewed with the citations). The legal text stays one click away and is what is signed (D11, approved).
- **S7** "Conclude not reportable instead" / "Conclude reportable instead" replace "Override it" (`sections/TreeSign.tsx:248-259`).
- **S8** One answer screen and one editor: the watch's drawer opens the tree answer screen; `DecisionGuides` and `TreeEdit` give way to the one editor.
- **S9** "Needs more information" replaces "Pending information" on screen (`reportability/markets.py:67`). The stored value `PENDING_INFORMATION` does not change.

### 3.10 Where it lives and who (D1, D2, approved)
- **Classic and full:** Customer Admin › "Reportability questionnaires", after Data Mapping (`customer-admin/CustomerAdminControlPlane.tsx:43-94`). Description "Questions and logic per market".
- **Trial:** Settings › "Reportability questionnaires" (renames "Reportability guides"). Settings › Reporting windows stays beside it.
- **Layout:** market tabs; header "US · Version 4 in use since … · Version 5 draft (yours) · MDARIX floor US-floor-1"; tabs Questions | Logic | Tests | Versions (report §3a). Flat operational screens (G-2): tables, no cards inside cards.
- **Authoring:** new permission `questionnaire.author`. Held by Customer Admin, Leader and Platform Admin, and by today's editors (`regulatory.review`, `regulatory.approve`). Others get it through a new additional workflow role "Questionnaire author" in Users (B4b-D8).
- **Approval:** `regulatory.approve` only; never an editor of the version, never an administrator (unchanged).
- **Everyone else:** read only (DT-35).

### 3.11 Operating modes (Connect and Complete)
- Same questionnaire and outcome for an owned and an imported complaint (DT-34).
- The "Confirm" line names the origin ("From the QMS import, 6 Nov · CMP-123").
- **Optional step 20:** in Connect, when a confirmed fact changes at the source, an open draft shows "The record changed: confirm again" and a signed conclusion gets a re-check task (DT-28).

### 3.12 How each decision meets the five (development cycle)
- **Facts:** answers with origin (confirmed, corrected, entered).
- **Rules:** floor code and hash, organisation version and fingerprint, rules applied by layer, suspended rules.
- **Human judgement:** the signer; for a downgrade, the second person.
- **Traceability:** version history, diff, tests, back-test, approval and effective date, all audited.
- **Evidence:** the signed material holds all of the above.

---

## 4. Gap table
| # | Gap | Evidence | Step |
|---|---|---|---|
| G1 | Customer logic cannot change the outcome; extra questions never count | `decision_guides/rules.py:1-20, 292-311`; `sections/TreeAnswer.tsx:458` | 2, 3 |
| G2 | No place for rules, answer types, fact map or effective date on a version | `db/models/guides_communications.py:79-105` | 1 |
| G3 | Approval publishes at once; no scheduled state | `decision_guides/router.py:657-665`; `decision_guides/rules.py:41-47` | 8 |
| G4 | No combination of floor and own rules; no negation or choice test | `rule_register/engine.py:23, 101-112` | 3 |
| G5 | Questions built from today's floor, not the floor at awareness | `decision_guides/rules.py:63-64, 117-139` | 5 |
| G6 | Tests use core questions only; 30 rows; no RG rows; no back-test | `decision_guides/rules.py:35, 270-311` | 6, 7 |
| G7 | Answer types fixed | `reportability/markets.py:39-40` | 2, 5 |
| G8 | Customer Admin cannot author; permission sets grant no business permission | `decision_guides/router.py:58`; `access/permissions.py:98, 205-207` | 10 |
| G9 | No Customer Admin section | `customer-admin/CustomerAdminControlPlane.tsx:43-94` | 13 |
| G10 | No re-check prompt or task when a version changes | `decision_guides/service.py:1-3` | 9 |
| G11 | Downgrade needs one signer and 10 characters | `reportability/markets.py:846-858` | 11 |
| G12 | Pre-fill thin; triage threat and remedial action unusable as "not known" | `reportability/markets.py:656-703`; `db/models/intake.py:294-295` | 12 |
| G13 | Duplicate answer screens and editors | `sections/Settings.tsx:20, 35, 62`; `sections/Complaints.tsx:40, 140`; `sections/ReportabilityWatch.tsx:45, 218` | 15 |
| G14 | Approval signature text says "after publication" | `decision_guides/rules.py:354-359` | 8 |
| G15 | "Pending information" wording | `reportability/markets.py:67` | 14 |

---

## 5. Build steps
Hours include targeted tests. "(db)" = database test; "(unit)" = no database. Part A (server) is steps 0–12 and 16–19 (95 h). Part B (screens) is steps 13–15 (39 h).

| # | Step | Hours | Targeted tests |
|---|---|---|---|
| 0 | Branch from B9b's tip; one Alembic head `tr31othercountries`; re-check every line here; CHANGELOG section; add QC-01..QC-12 (below) to `scenario-register.md` and mark DT rows for B4b | 2 | `alembic heads` = 1 |
| 1 | Migration `tr32questionnaires` (§6); legacy-plane function `add_questionnaires` | 5 | (db) upgrade, downgrade, upgrade; `test_rls_coverage.py` |
| 2 | Layer model and checks (`decision_guides/layer.py`): answer types and options, position, show-when, pre-fill, required-for-Not-reportable, retire; rules raise-only; references exist and are not retired; readable words for own rules (reuse `rule_register/router.py:27-46`) | 8 | `test_b4b_layer_unit.py`: DT-01, 02, 03, 27, 29, 30; a "Not reportable" rule refused; a report type of another market refused; limits |
| 3 | Engine: `not`, `eq`; `combined`; own rules in `applied` with layer; suspended rules; floor questions used by own rules never folded | 8 | `test_b4b_engine_unit.py`: truth tables for `not` and `eq`; DT-04, 05, 08; suspended rule on `US-IMP-floor-1` (no US6); B4b-D1 form type |
| 4 | Proofs: empty layer = B4 results byte for byte (reuse `test_b4_equivalence.py` inputs); property test DT-36 (20,000 random layers per market, fixed seed) | 6 | `test_b4b_monotonic_unit.py` (`slow` mark if over 60 s) |
| 5 | Wire into assessments: questions from the floor at awareness plus the layer; answers per type (`markets.clean_answers`); combined result on save and sign; required reasons at Not reportable; signed material adds `layer` (code, fingerprint, rules applied by layer, suspended, `layer_reason`) | 10 | (db) `test_b4b_assessments.py`: DT-06, 07, 08, 20, 21, 22, 34; signed rows from before B4b unchanged byte for byte |
| 6 | Tests tab server: RG rows per market (locked), own rows with own questions, 50 rows, run against the floor at the effective date and today's | 5 | DT-09, 10, 11; starter and RG rows put back when removed |
| 7 | Back-test (§3.5) | 5 | (db) counts on a seeded 12 months: same, different, needs your new question; pre-B4 rows read as version 1 |
| 8 | Effective date, `SCHEDULED`, "in use" read, sweep promotion, fingerprint covers the date, new signature text | 6 | (db) DT-15, 16 (past refused; midnight and daylight saving in the organisation's zone); in use without the sweep; one scheduled per market |
| 9 | Re-check (§3.6): open-draft prompt and continue-with-reason; tasks per B4b-D6; impact list; task closing | 6 | (db) DT-17, 18, 19; no task for a closed complaint; a second run makes no second task |
| 10 | Permissions: `questionnaire.author`; additional role "Questionnaire author"; route guards; approval unchanged | 3 | `test_business_permissions` (new routes listed); DT-12, 13, 14, 35 |
| 11 | Downgrade override (§3.8): awaiting state, report draft and clock kept, second-person route, refusal, trial label | 8 | (db) DT-32: draft report exists while awaiting; second person cancels it; first signer, editor-only and admin refused; refusal keeps the first record; trial labelled |
| 12 | Pre-fill: `prefill-starter-2` (B4b-D5), own-question facts, floor pre-fill off-switch | 6 | (unit) every fact × True/False/None: never No from empty, death Yes only, triage Yes only; DT-27 |
| 13 | Screens: the one editor (Questions, Logic with a rule builder, Tests with back-test, Versions with diff and effective date) in Customer Admin and trial Settings; "Edit this tree" opens it | 20 | vitest per tab; `tsc --noEmit` |
| 14 | Answer screen: S1, S2, S4, S5, S6, S7, S9; own question inputs per type; "Awaiting a second person" card; re-check banner | 14 | vitest: RV-11 click count 10 (S1/S2), DT-38, override words; `tsc --noEmit` |
| 15 | S8: the watch's drawer opens the answer screen; `DecisionGuides` removed from Settings and classic Complaints | 5 | vitest: watch → answer screen; no route left to the old editor |
| 16 | Switch `MDARIX_QUESTIONNAIRES` (§7) | 3 | Off/on/off: own rules ignored, routes 404, drafts still signable after re-save, pending downgrades stay pending |
| 17 | Sample: US-v3 draft gains O-1 (implant and malfunction → Reportable 30 days) and an own test row; back-test shows the sample's signed decisions | 3 | `test_sample_story_days.py`, `test_release_0_10_92.py` green |
| 18 | Docs: decision tables (combination rule, B4b-D1), user guide, environment reference, CHANGELOG | 3 | Decision-table doc test |
| 19 | Targeted suites with the switch on and off, **including `test_b4_equivalence.py`, `test_rule_pins_unit.py`**, `test_regulatory_decision_tables.py`, `test_decision_guides_api.py`, `test_market_assessment_api.py`, `test_authority_reports_api.py`, the B8, B9 and B9b tests; ruff; vitest; `tsc`; one independent read-only review; fixes | 8 | All green both ways |
| | **Core total** | **134** | |
| 20 | *Optional:* Connect re-confirm and re-check on a changed source fact (DT-28) | 5 | (db) changed fact → banner on draft, task on signed |
| 21 | *Optional:* back-test result exported with the approval PDF/Word | 2 | Render test |
| | **Total with options** | **141** | |

At about 7 build hours a day, the core is about 19 working days.

**QC scenarios (new):** QC-01 an own rule with a shorter type when the floor applies: form type stays the floor's, due date earlier, labelled. QC-02 an own Reportable rule when the floor says Not reportable: own type on the form. QC-03 an own rule naming US6 on an importer: suspended and listed. QC-04 a floor question used by an own rule is not folded. QC-05 required reason blank at Not reportable: refused. QC-06 a Short text question in a rule: refused. QC-07 "Continue on version 4" without a reason: refused; with one: signed with it. QC-08 back-test "needs your new question" group. QC-09 scheduled version in use before the sweep. QC-10 downgrade refused by the second person. QC-11 Customer Admin authors, cannot approve. QC-12 switch off: own rules ignored, pending downgrade still pending.

---

## 6. Migration
**One additive migration: `tr32_trial_questionnaires.py`, revision `tr32questionnaires`, `down_revision = "tr31othercountries"`** (B9b's head). If another item lands a migration first, step 0 re-chains to the single head. On mvp-1.0 the forward merge adds a merge revision (md pattern).

`decision_guide_versions` (tenant-isolated already; no new table, RLS unchanged):
| Column | Type | Content |
|---|---|---|
| `floor_code` | `String(40)` null | Floor the version was built and tested on |
| `rules` | `JSONB NOT NULL DEFAULT '[]'` | Own rules |
| `fact_map` | `JSONB NOT NULL DEFAULT '{}'` | Own-question facts; floor pre-fills switched off |
| `effective_from` | `timestamptz` null | Null = at approval |
| `back_test` | `JSONB` null | Last back-test result |
| state check | adds `SCHEDULED` | `published_signed` check also covers `SCHEDULED`; new unique index: one `SCHEDULED` per tenant and market |

Answer types, options, position, show-when and the required flag live inside the existing `questions` JSONB (no column).

`complaint_market_assessments`:
| Column | Type | Content |
|---|---|---|
| `layer_reason` | `Text` null | Why the draft continued on an older organisation version |
| `downgrade_state` | `String(20)` null | `AWAITING_SECOND`, `AGREED`, `NOT_AGREED` |
| `second_signed_by`, `second_signed_at`, `second_record_id` | `String(255)`, `timestamptz`, `UUID` null | The second person's agreement or refusal |

- **No data step, no backfill.** Existing customer versions get `rules = []`: no own rules, identical outcomes. The sample's US-v2 and US-v3 keep working.
- **Downgrade** drops the columns and restores the checks. It refuses while any `SCHEDULED` version, any version with own rules, or any `AWAITING_SECOND` row exists (no silent loss).
- Legacy dedicated organisation databases get the same through `scripts/add_workflow_tables_to_legacy_planes.py` (`add_questionnaires`), as `tr30`/`tr31` do.

---

## 7. Switch, cuts, sample

### 7.1 On/off switch (the `feature_set.py` pattern)
- `MDARIX_QUESTIONNAIRES`: on unless `off`, read on every call. Needs `MDARIX_RULE_REGISTER` on.
- **Off:** own rules, own answer types and the new pre-fill are ignored (floor only, as B4); the new routes answer 404; the editor shows today's screen; scheduled versions wait. **Pending downgrades stay pending; D7 stays in force** (B4b-D7 ⚑).
- **On (default):** everything above. An empty layer gives B4's results, so turning it on changes nothing until a customer approves rules.

### 7.2 What can be cut (in this order)
1. Optional steps 20, 21. 2. Step 15 (S8: keep the old screens beside the new). 3. S6 plain one-liners. 4. Step 7 (back-test: then approval shows "not run"; D10 not met). 5. Step 12's new floor pre-fills (keep own-question facts). 6. The trial-only Settings tab (Leader uses "Edit this tree" opening the editor).

**Never cut:** raise-only by construction and its property test; B4 equivalence green; the floor at awareness; second-person approval never by an administrator; effective dates; re-check tasks (never automatic change); the downgrade second person (D7); the switch; signed records unchanged.

### 7.3 How it fits the sample story
- The sample organisation's **US-v2** (published, VMSR question, `trial/sample_guides.py:1-10`) stays.
- Its **US-v3 draft** gains O-1 "Implant and malfunction → Reportable 30 days" and an own test row. It still fails its sample row ("outcome unknown: expected not reportable") on purpose, to show the gate (DT-11).
- **RV-11** (pulse oximeter, no harm, malfunction) shows the simpler path: "Confirm the 3 facts", "None of these", one sentence: "Reportable to FDA in 30 calendar days (21 CFR 803.50(a)(2)): the device malfunctioned and a recurrence would be likely to cause or contribute to a serious injury." 10 clicks.

---

## 8. Owner decisions

⚑ = touches regulatory interpretation or signed records: **needs your explicit answer.** "If no answer" is what the build does meanwhile.

| # | Decision | Recommendation (safe) |
|---|---|---|
| B4b-D1 ⚑ | Form report type when an own rule names a shorter type than the floor's (for example US 5-day while the floor says 30-day) | The form keeps the **floor's** type whenever the floor's rules apply or could apply; the own rule only makes the **due date earlier**, labelled "Earlier by your rule O-1". An own type goes on the form only when the floor says Not reportable. This narrows "the shorter of the two reports" (B4 §2) to the date, so MDARIX never files a report type the law did not call for. *If no answer:* as recommended. |
| B4b-D2 ⚑ | An own rule that names a question the floor at awareness does not have (older floor, role floor, retired question) | Suspend that rule for that assessment; list it on the result and in the signed material; never treat the missing answer as No. A floor question an own rule uses is never folded. *If no answer:* as recommended. |
| B4b-D3 ⚑ | Downgrade override mechanics (D7 approved) | First signature held "Awaiting a second person"; the report draft is created and its clock runs until the second person (regulatory approver, not the first signer, not an administrator, password and code) agrees; a refusal keeps the first record marked "Not agreed" and needs a new signature; trial allowed and labelled. *If no answer:* as recommended (the safer path). |
| B4b-D4 ⚑ | Approval signature text for questionnaire versions | New text naming the rules, the effective date and zone, and "can only add scrutiny to the MDARIX floor" (§3.4); approvals already signed keep theirs. *If no answer:* today's text with "Assessments started on or after {date, time, zone} use it" in place of "after publication". |
| B4b-D5 ⚑ | New floor pre-fills (S3) | In a separate MDARIX procedure file `prefill-starter-2`, "Confirm" only: death → EU2, GB2, CA3 Yes only; incident country → CA5 and GB/NI; product registration → CA1; triage threat → EU/GB threat Yes only; triage remedial → US6 Yes only (the triage fields are booleans). Floors unchanged. Consultant to confirm. *If no answer:* no new floor pre-fills; own-question facts only. |
| B4b-D6 ⚑ | Which differences make a re-check task when a new organisation version comes into use | A task for a signed conclusion on an **open** complaint when the answers already given decide differently (outcome, form type or an earlier date). Differences that rest only on new, never-asked own questions are listed, with no task. Closed complaints listed only (G10). *If no answer:* a task for every difference on an open complaint. |
| B4b-D7 ⚑ | What the switch-off does | Off = floor only (own rules ignored), editor back to today's, scheduled versions wait; pending downgrades stay pending and D7 stays in force. *If no answer:* as recommended. |
| B4b-D8 | How authoring is granted | New permission `questionnaire.author` for Customer Admin, Leader, Platform Admin and today's editors; others through a new additional role "Questionnaire author" in Users. Not a permission set: permission sets grant no business permission today (`access/permissions.py:205-207`). |
| B4b-D9 | S4 "only questions that can still change the outcome" | A count and an order ("2 can still change the outcome"); floor questions hide only by the floor's proven folding; own questions by their own "show only when". |
| B4b-D10 | Required Not-reportable reasons | As own Short text questions marked "required to conclude Not reportable"; no separate setting. |
| B4b-D11 | Limits | 20 own questions, 20 own rules, 50 test rows per market. |
| B4b-D12 | Effective date | Chosen at "Send for approval", part of what is approved; past refused; in use as soon as its moment passes, the sweep only tidies states. |
| B4b-D13 | "Other country" (B9b) | Not configurable in B4b; its generic floor stays as shipped. |
| B4b-D14 | One editor and one answer screen (S8) | Yes; the old editor and drawer are removed in step 15 (cut 2nd if late). |
| B4b-D15 | Wording | "Needs more information" on screen; stored value unchanged. |
| B4b-D16 | Switch default | On (an empty layer changes nothing). |

**Needing your explicit answer:** B4b-D1, D2, D3, D4, D5, D6, D7.

---

## 9. Documents to obtain (owner)
| For | Document | Why |
|---|---|---|
| S6 | Your consultant's review of the MDARIX plain one-liners for every floor question (five markets plus the US role floors) | D11: they are MDARIX-reviewed text above the legal wording |
| B4b-D5 | Consultant's view on each new pre-fill (especially "death → EU2/GB2/CA3 Yes") | Pre-fill sits next to legal judgements |
| Gate | Current text of 21 CFR 803.17 and 803.18, ISO 13485:2016 clauses 4.1.6 and 8.2.3, MDCG 2023-3 | Cited as the basis for own procedure steps, required reasons and the test gate |

## 10. To confirm with your consultant
- Whether an own rule may only make the date earlier while the form keeps the floor's type (B4b-D1).
- Whether "Awaiting a second person" with the report draft kept meets their procedure for a downgrade (B4b-D3).
- Whether continuing an open draft on an older organisation version with a reason is acceptable.
- Whether the test gate plus back-test is enough software validation for a customer's own rules (ISO 13485 4.1.6), or a customer validation step must be added.
- The plain one-liners and the RG rows chosen as locked tests.

## 11. What I did not check
- B9b's tip was read only for its register and migration; every other line is on `feat/b8-eu-gb-mir` and may move. Step 0 re-checks.
- I did not check that the Customer Admin console can call the data-plane decision-guide routes (Data Mapping suggests it can). Step 0 confirms; if not, step 13 grows by about 4 h.
- Click counts come from the deep-dive report (read from code at v0.10.92), not a browser.
- The property test's run time was not measured.
- No database was queried; the number of existing customer versions is unknown (harmless: they get no own rules).
- No legal source was re-read. Hours are estimates from B4 and B9 steps of similar size.

---

## Owner approval (11 Nov 2026)
The owner replied **"approve B4b spec"**: every recommendation is accepted as written, including all flagged decisions (D1 legal report type kept, a stricter customer rule only makes the due date earlier; D2 rule suspended when its question is missing, never treated as No; D3 downgrade needs a second person, clock keeps running; D4 new signature wording, signed approvals keep their text; D5 new pre-fills in a separate file, confirm-only; D6 re-check tasks only where given answers decide differently; D7 switch off = floor only). Build starts in Lane 1 after B6a, B6b, the RCA tools item and the Q2 benchmark run. Step 0 re-numbers the migration after the current head (one-head rule).

## Approval record

| Field | Value |
|---|---|
| Approved | 11 Nov 2026 |
| Approver | Srinivas Telikicherla, Founder & CEO, QA/RA (owner) |
| Approval words, as recorded | "approve B4b spec" |
| Where recorded | section "Owner approval (11 Nov 2026)" |
| Planning copy | `MDARIX-planning/b4b-questionnaire-config/spec.md` (reference only) |
| Form of approval | The owner's written reply, recorded in the spec on the day; not an electronic or wet signature. This section was added on 12 Nov 2026 (owner decision O29); the approved text above is otherwise unchanged, except that a DRAFT status line now reads APPROVED |
