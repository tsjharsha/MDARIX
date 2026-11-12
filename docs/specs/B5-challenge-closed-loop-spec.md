# B5 design spec: investigation challenge and the closed loop

Version 1, 10 Nov 2026. **DRAFT for the owner's approval.** Nothing here is built.

- **Plan:** B5 starts when all of B7 is built (B7a routine path, bulk import and export; B7b e-mail intake), on its own branch from B7's tip. Target January 2027. Its release number is given at build time (the backlog row said 0.10.98).
- **Why now:** every commercial review calls product-version investigation the flagship. The master sequence (10 Nov) puts B5 right after B7. It builds on W1 (Product 360, Supplier 360) and on the PV-1 fixes in 0.10.95.
- **AI:** off until 2027. Everything in B5 is rule-based. No AI part is added. The existing AI paths stay as they are, off in the trial.
- **Sources:** `development-cycle-1.md` (B5 row, C3, C5, Addenda A, B, C, H, J, K; E3, E6, E10), `master-sequence-proposal.md`, `reviewer-feedback-log.md` (theme D1), `operating-modes.md`, `pv-audit/report.md`, `w1-product-supplier-360/spec.md`, `b7-routine-path/spec.md`, `b3-emdr/B3-execution-plan.md`, `scenario-register.md` (IV, CP).
- **Code read:** worktree `trial-094` (branch `feat/b3-emdr-0.10.96`, which holds B2, W1, hardening 0.10.95 and B3). Read only; nothing was run, no database was queried. Paths start at `backend/app/` unless shown otherwise.
- **Not re-specified:** what B7 adds (Resolve and close, complaint close and reopen, known issue joining an open investigation) and what B3 adds (follow-up reports). B5 works at the level of the investigation and its signed decision.

---

## 0. B5 in one page

1. **Challenge.** On an open investigation, MDARIX drafts competing explanations from the records it already links (complaints, lots, versions, configuration and changes, suppliers, service records, the risk file). Each draft shows the records **for** it, the records **against** it, and what is **missing**. A person adopts or dismisses each draft. MDARIX then asks **challenge questions** (for example "Rev A has 3 pressure-alarm complaints without the new sensor: what explains them?"). The author answers them in the brief.
2. **A brief that cites everything.** The Decision Brief gets two new sections: the challenge (drafts, what was done with each, questions and answers) and **Sources**: every record the brief relies on, with its ID, origin and date. The decision maker signs that content, as today.
3. **Closed loop.** After the decision is signed, MDARIX links back to it: later complaints on the same product, versions and problem, the CAPA effectiveness checks, field actions and product changes the decision asked for. A **"Did it work?"** view compares before and after the action, by version and by lot, with units in the field as the denominator, or "units unknown".
4. **Reopen triggers.** When the numbers or records say the action may not have worked, MDARIX opens an **impact assessment** (exists today) for a person. It never reopens or changes a signed decision by itself.
5. **Size:** about **104 hours** in 14 steps. **One migration, `tr26`** (six nullable columns on two existing tables). It can ship in two parts: **B5a** challenge and brief (about 56 h) and **B5b** closed loop (about 48 h).

---

## 1. What the user gets, in plain words

### 1.1 The journey

| # | Who | Does what | Signed? | Audited |
|---|---|---|---|---|
| 1 | Investigator | Opens the investigation (exists). Saves the scope: versions, lots, complaints (exists). | No | Yes (exists) |
| 2 | Investigator | Opens **Challenge** (new view in the investigation's Intelligence part). Sees 1 to 5 rule drafts, each with for, against and missing. | No | `CHALLENGE_VIEWED` once per scope version |
| 3 | Investigator | **Adopts** a draft: it becomes a hypothesis marked "Drafted by rule H-n, adopted by <name>". The record facts they tick become evidence items ("record summary"), unreviewed, linked for or against. Or **dismisses** it with a reason. | No | `DRAFT_ADOPTED` / `DRAFT_DISMISSED` with rule, version, facts fingerprint |
| 4 | Investigator | Reviews the record summaries like any evidence (exists), judges each hypothesis (exists), answers open questions (exists). | No | Yes (exists) |
| 5 | Investigator (brief author) | Writes the brief (exists). Answers each **challenge question**, or marks it "not applicable" with a reason. Material questions block "Submit for review" until answered. | No | `CHALLENGE_ANSWERED` |
| 6 | Quality reviewer (≠ author) | Reviews the brief, now with the challenge and Sources sections. Accepts, returns or escalates (exists). | Review action (exists) | Yes (exists) |
| 7 | Decision maker (≠ author) | Signs the decision: outcome, root-cause attribution, follow-ups (exists). The signature covers the challenge answers and the Sources list, because both are in the brief content hash. | **Yes** (exists) | Yes (exists) |
| 8 | Follow-up owners | Complete follow-ups (exists). A field-action follow-up now records its reference, type, effective date and lots or versions covered. A product-change follow-up names the new version. | No | `FOLLOW_UP_COMPLETED` (exists) with the new fields |
| 9 | Quality reviewer | Plans and signs the CAPA effectiveness check (exists). The check now shows the before and after by version and lot. | **Yes** (exists) | Yes (exists) |
| 10 | Anyone with access | Opens **Did it work?** on the decision: later complaints, the before/after by version and lot, the effectiveness checks, field actions, the new version. | No | No (a read) |
| 11 | System, hourly | Checks the reopen triggers. When one fires: an impact assessment and its task for the investigation owner (exists). | No | `REOPEN_TRIGGER_FIRED` + the existing impact audit |
| 12 | Investigator | Completes the impact assessment: no impact, or material impact (exists). Material impact moves the investigation back to In progress; the next decision supersedes the old one (exists). | Completion (exists) | Yes (exists) |

### 1.2 What MDARIX must never do

1. **Never decide the root cause.** Drafts are explanations to test. A person adopts, judges and signs. No draft is ranked, scored or given a probability; drafts are listed in rule order.
2. **Label every rule output.** "Drafted by rule H-2 v1 from your records. Not a finding." The same for questions ("Question from rule C-3 v1") and for the before/after ("Counts from your records; not a verdict").
3. **Never borrow a version** (PV-1). A complaint with no version is counted as "version unknown", never put under the latest or most common version. A lot with no version stays "version unknown". The before/after never moves a complaint into a version it does not carry.
4. **Never a rate from partial units.** If units are unknown for any lot of a group, the group shows counts only and "units unknown for X of Y lots".
5. **Never say "confirmed", "proven", "effective" or "root cause".** Only a person's signed effectiveness result says "effective". The words MDARIX uses are "fewer", "more", "no change seen", "too early", "too few to tell".
6. **Never change a signed decision.** Triggers open an impact assessment; a new decision supersedes (exists, IV-16).
7. **Never attribute a change to events before it took effect** (IV-14). A complaint whose event came before a change's effective date counts against that change as a cause, never for it.
8. **Never open a CAPA, a field action or a report by itself.** It never recommends a recall (the Lot impact rule, `lot_impact/service.py:13`).
9. **Never hide contradicting records.** If records contradict the leading hypothesis and nothing contradicting is linked, the brief cannot be submitted without an answer.
10. **Never treat a supplier's statement as proof** (IV-09). It stays a source assertion.
11. **Never read evidence text as instructions** (IV-10). The rules read structured fields and codes only.
12. **Never mix sample data into customer numbers** (R6). Sample records stay labelled SAMPLE.

---

## 2. Investigation challenge

### 2.1 What exists today

| Piece | Where | State |
|---|---|---|
| Hypotheses, with a person's judgement apart from the origin's status | `db/models/foundation.py:471-490`; routes `case_intelligence/router.py:431` (list), `:460` (add), `:526` (judge), `:587` (link evidence) | Works. `origin` allows `ai`, `human`, `system` (`foundation.py:477`, check `:488`). No column says which rule drafted a hypothesis. |
| Evidence for and against a hypothesis | `hypothesis_evidence` (`foundation.py:1183-1206`): support, contradict, contextual, unresolved; withdrawal instead of deletion | Works. Links need an `evidence` row. |
| Contradictions view | `case_intelligence/router.py:797-950`; screen `frontend/src/features/workspace/sections/caseIntelligence/Contradictions.tsx` | Works: lists contradicting links and contradicting case evidence, and whether a person judged the hypothesis since. Shows only what people (or AI) linked; never finds a contradiction in the records. |
| Unknowns (open questions) | `case_intelligence/router.py:1023-1185`; `Unknowns.tsx` | Works; statuses open, in progress, resolved, accepted limitation, superseded. |
| Readiness checks | `case_workflow/readiness.py`: hypotheses present (`:232`), contradictions documented (`:252-276`, fact `:557-592`), unknowns (`:278-296`) | Works. Open unknowns and undocumented contradictions are **warnings**, not blocks (`decision_brief/rules.py:292` lists the blocking checks: scope, evidence reviewed, no blocking request, risk and regulatory review). |
| Decision Brief content | `decision_brief/compose.py:595-654`: investigation, product, signals, scope (with lots and unknown-version count), facts, evidence inventory, for and against, leading and alternative hypotheses, unknowns, chains, reviews, AI statement, readiness | Works. Cites evidence by ID. **Does not cite** the changes, suppliers, components, lot genealogy, units, service records, risks, trend result or rules behind the investigation. |
| Signed decision | `human_decision/`; `decisions` (`foundation.py:585-650`) bound to the brief content hash; root-cause attribution signed by the person (`:633`) | Works. |
| Old rule "hypothesis engine" and "challenger" | `hypothesis_engine/engine.py:78-129`, `challenger/engine.py:97-140`, run by `case_ai/runner.py` | **A fixed template, not analysis.** It writes "…contributed to the observed **shutdown** increase" (`engine.py:82`, `:101`, `:119`) whatever the case is about, by keyword matches on an analysis text. The trial hides the AI run (`frontend/src/features/workspace/workspaceContext.tsx:413-416`), so trial users never see it; the full edition does. |
| Correlated records | W1: `product360/service.py`, `product360/supplier_service.py` (P-1 `:55`, units `:327`); `lot_impact/service.py` (genealogy, units released and shipped, per 1,000, `:275-330`); `signals/insight.py` (lot releases `:153`, changes behind a version `:247`); `signals/trend_rules.py` (Poisson tail `:83`, unit-days `:113`); `post_market/risk_file.py`; service work on the complaint (`oversight/service_work.py`, complaint columns `service_*`) | Works, each on its own page. Nothing brings them together for one investigation. |
| Sample | `trial/sample_decision.py:65-118`: two hypotheses written by hand (supplier sensor; ward settings), two open questions, a chain | Works; B5 must read the same. |

### 2.2 Where the rules read from (the "facts" of an investigation)

One read, `case_challenge/facts.py`, builds the facts of an investigation from its **current scope** (`case_workflow/scope.py:275` `current_scope`):

| Fact | Source | PV-1 rule |
|---|---|---|
| Scope complaints: product, version, lot, problem code, event date, harm flags, country, service status, No Fault Found / user-error codes | `complaints` via the scope's included IDs | Unknown version kept as unknown; counted apart |
| Scope versions, their release dates and predecessors | `product_versions`; `signals/insight.py` `_previous_versions` | Only versions of the case's product |
| Lots of those versions: release date, units released, genealogy (component lots), units shipped with ship dates | `lot_batches`, `lot_components`, `lot_distributions` | A lot's version as recorded; none borrowed |
| Configuration per version, component suppliers, changes affecting a component or the product, with effective dates | `product_components`, `component_suppliers`, `reality_relationships` AFFECTS (the W1 join) | A change on the whole product applies to every version (as W1) |
| Same problem outside the scope: other versions and products sharing a supplier part | W1 P-1 inputs | Shown as "outside the scope", never added to it |
| Trend result per scope version | `signals/insight.py` `trend_for_signal` / trend board | As Trends shows it |
| Risk file: risks of the product and version, open reassessments | `post_market/risk_file.py` | Version-less risks apply to the whole product, said so |
| Linked evidence and its review | `evidence`, `investigation_evidence`, `hypothesis_evidence`, `evidence_entity_links` | — |
| Hypotheses, judgements, unknowns | case intelligence tables | — |

Every fact keeps its record IDs and origin (Sample, import with system and ID, MDARIX), so each sentence can cite them.

### 2.3 Draft explanations (rules H-1 to H-5, version 1)

A draft appears only when its condition is met. "Records for", "records against" and "missing" are lists of facts, each citing records. Thresholds are owner decision B5-D5.

| Rule | Drafted when | Records for | Records against | Missing |
|---|---|---|---|---|
| **H-1 Component or supplier change** | A change affecting a component of a scope version took effect before at least one scope complaint | Complaints per 1,000 unit-months before vs after the change on the affected versions; complaint lots built with the changed part (genealogy) | Same-problem complaints on versions or lots **without** the part; scope complaints whose event came **before** the change (IV-14) | Genealogy not imported for N lots; units unknown; no incoming-inspection evidence linked to the supplier or part |
| **H-2 Lot or manufacturing** | The top lots hold at least 60% of the scope complaints with at most 40% of the units (or, with units unknown, at least 60% of complaints in at most a third of the lots) | Per-lot counts and per 1,000 units; shared component lots among them | Complaints spread over lots in proportion to units | Lot unknown on N complaints; units unknown for N lots |
| **H-3 Design of the version** | A scope version's rate is higher than its predecessor's (the trend check's previous-version baseline), spread across its lots | The trend result; per-lot rates on the version | The predecessor shows the same rate; complaints concentrate in a few lots (points to H-2) | Predecessor has no units; version unknown on N complaints |
| **H-4 Use, setting or environment** | At least a third of scope complaints are coded No Fault Found or user error, **or** complaints cluster by country or site rather than by lot | Those codes; the cluster | Concentration by lot instead of by site; device faults found on return | Device not returned on N complaints; no service result |
| **H-5 Supplier part across products** | W1 rule P-1 finds the same problem on 2 or more versions that share a part of one supplier | P-1's counts, units, rates | Versions with the part and without the problem | Units unknown (P-1 wording) |
| **H-0 Not enough records** | None of H-1 to H-5 can be tested (fewer than 3 scope complaints, or every complaint lacks version and lot) | — | — | What is missing, in a list |

**Duplicates.** If a person already recorded a hypothesis about the same thing, the draft still shows, with "You may already have this: HYP-12". MDARIX never merges them.

**Sample (SAMPLE-INV-001), expected reading** (exact numbers fixed by the build's tests): H-1 (supplier change SAMPLE-CHG-014, NovaSense sensor on Rev B; against it: pressure-alarm complaints on Rev A with the Precision Sensors part), H-2 (lots 003 and 004), H-4 (ward settings; against it: the concentration by lot across the same wards). These match the two hypotheses the sample author wrote, so they show "You may already have this".

### 2.4 Challenge questions (rules C-1 to C-9, version 1)

Computed on read from the facts and the current hypotheses. **Material** questions block "Submit for review" until answered or marked not applicable with a reason (B5-D3). The others are shown as warnings.

| Rule | Asked when | Question (example) | Material |
|---|---|---|---|
| C-1 Unlinked contradiction | A draft's "against" facts contradict the leading hypothesis and no contradicting evidence is linked to it | "3 pressure-alarm complaints on Rev A have no NovaSense sensor. Does your leading explanation account for them?" | Yes |
| C-2 One explanation only | Only one hypothesis is still considered | "What else could explain this? Name one alternative and why the records speak against it." | Yes |
| C-3 Timing | Scope complaints happened before the suspected change took effect | "2 complaints happened before SAMPLE-CHG-014 took effect." | Yes |
| C-4 Unknowns in the data | More than 20% of scope complaints have no version or no lot, or units are unknown | "4 of 14 complaints have no version. Conclusions about Rev B cover 10 of 14." | Yes above 20%, else warning |
| C-5 Open question on the leading hypothesis (IV-15) | An unknown linked to the leading hypothesis is open | "The bench test is still open. Wait for it, or accept it as a limitation with a reason." | Yes |
| C-6 Supplier assertion (IV-09) | Evidence for the leading hypothesis is a source assertion from the supplier only | "Only the supplier's statement supports this. What independent evidence is there?" | No |
| C-7 Outside the scope | The same problem appears on versions or products outside the scope (P-1 or Product 360) | "Rev C also has 5 pressure-alarm complaints. Should the scope include it?" | No |
| C-8 Small numbers | Fewer than 5 scope complaints, or the rate rests on calendar days because units are unknown | "Is this enough to conclude?" | No |
| C-9 Strong words | The proposed conclusion says "root cause", "proven", "confirmed" or "definitely" while the leading hypothesis is not judged strongly supported | "Your conclusion says 'confirmed'; the hypothesis is judged partially supported." | No |

Investigators disagreeing (IV-08) is already kept: each judgement keeps who and why; the brief shows them. B5 adds nothing there.

### 2.5 The brief: challenge section and Sources

- **Challenge section** (new key in the brief content): the drafts offered at composition (rule, version, adopted as HYP-n / dismissed with reason / not acted on), and every question with its answer, who answered and when.
- **Answers** are kept in the brief narrative (`decision_brief_versions.narrative`, JSONB) as `challenge_answers`. The content hash covers the narrative (`decision_brief/rules.py:371` `content_hash`), so the signature covers the answers. **No migration.**
- **Sources section** (new key): every record the brief cites, grouped by type (complaints, lots, versions, components and suppliers, changes, evidence, service references, risks, CAPAs, signals, rules), each with its ID, origin (Sample / system and external ID / MDARIX) and the as-of time. The rules list names H-n, C-n, P-1 and the trend rule with their versions. A unit test fails if any statement in the challenge section has no source.
- **Screen:** the brief page (`CaseDecisionBrief.tsx`) shows both sections; the Sources list is collapsed with a count ("142 records, 6 rules"). The PDF and the case record download show the same.

### 2.6 The old template engine

The full edition's rule fallback writes "shutdown" hypotheses for any case (2.1). B5-D4 asks to replace it: when AI is off, the AI run's hypotheses step reads the H-rules instead. The trial is not affected (it hides the AI run).

---

## 3. The closed loop

### 3.1 What exists today

| Piece | Where | State |
|---|---|---|
| Follow-ups of a signed decision: CAPA, product change, field action review, risk reassessment, regulatory action | `decision_followups/followups.py`; model `db/models/decision_outcomes.py:51-83` | Works. A field action is only a follow-up with a note. No reference, no effective date, no lots covered. A product change does not name the new version. |
| CAPA from the decision, with QMS reference | `followups.py` (`/capa`, `/capa/qms-reference`); `capas` (`foundation.py:379-403`) | Works. |
| CAPA effectiveness check, signed EFFECTIVE / NOT_EFFECTIVE | `capa_effectiveness/`; recurrence `rules.py:86`, measure `service.py:248-268` | Works. Counts complaints **on the whole product** with the case's problem codes (`service.py:233-246`), by calendar, no units, no version, no lot. NOT_EFFECTIVE plans another round; it does **not** go back to the investigation. |
| Late evidence after the decision → impact assessment | `decision_followups/impact.py:69-170`; hourly sweep (`scheduler.py:299-303`) | Works (IV-06). `impact_assessments.trigger` is free text (`decision_outcomes.py:93`), so new triggers need no migration. |
| Later complaints linked to a case | `complaint_disposition/triggers.py:176` `covering_cases` | **Open cases only.** After the decision, later complaints are not linked back. B7 joins known-issue complaints to an **open** investigation only (RT-12). |
| Change before/after split | `product360/service.py:487-515` | Counts only, by event date, no units. |
| Denominators | `lot_batches.quantity` (units released), `lot_distributions` (units shipped, ship date); `trend_rules.unit_days` | Works for the trend check and Lot impact. |
| Quality loop picture | `frontend/.../sections/QualityLoop.tsx` | A hero picture of the loop stations; no before/after numbers. |

### 3.2 Linking back to the decision

The **decision's scope** is the scope stored in its signed brief (product, versions, lots, problem codes of the included complaints, markets). Links are computed on read, never stored, so the same read gives the same answer:

| Link | Rule |
|---|---|
| **Later complaints** | Same product; version in the decision's scope (or the new version of a product-change follow-up); problem code among the scope's codes; event date after the decision was signed. Complaints with no version: listed apart as "version unknown", never counted under a version. |
| **CAPA effectiveness** | CAPAs whose follow-up belongs to the decision, with every round and signed result. |
| **Field actions** | Field-action follow-ups of the decision, with their reference, type, effective date and lots or versions covered (new, 3.5). |
| **Product change** | The new version named on the product-change follow-up (new, 3.5). |
| **Impact assessments and superseding decisions** | Exists; shown in the same view. |
| **Authority reports** | Reports of the scope complaints; a material impact shows "a follow-up report may be needed" with a link (B3's follow-up suggestion). B5 creates no report. |

### 3.3 The "Did it work?" view

Where: the investigation's **Decisions & actions › Did it work?** (new tab), the same block on **Records › Effectiveness checks** for that CAPA, and a link from the Product 360 version (B5-D11). Flat design (rule G-2); the header may use the hero style.

For each **action date** (CAPA measurement start, field action effective date, new version release):

1. **By version.** For each version in the decision's scope: complaints with the scope's problem codes in the window before and the window after; exposure in each window; rate per 1,000 unit-months; the result word (3.4).
2. **By lot.** Two cohorts: lots released **before** the action and lots released **after** it, each with complaints per 1,000 unit-months over the same calendar period. This is the fair test for a CAPA that changes how new lots are made (for example restored incoming inspection): older lots in the field keep their fault. Each lot is listed with its own counts (trial-only rule, B5-D9).
3. **New version vs old.** After a product change: the new and the old version over the same calendar period, per unit-months.
4. **Version unknown.** "N later complaints have no version" (and lot unknown), never in a group.
5. **The records.** Every count opens its complaints; every rate shows its units and their source.

**Denominator, in this order (B5-D6):** units shipped with ship dates, when every lot of the group has distribution rows; else units released with release dates (`trend_rules.unit_days`); else **"units unknown"**: counts and per 30 days by calendar only, with "a change in units in the field can change these counts by itself". Single-use products count by calendar or by their use period, as the trend check does (`trend_rules.py` J27).

### 3.4 Statistics and their limits

- **Test.** Given the complaints in both windows, how surprising is the split if the rate per unit (or per day) had not changed? An exact conditional test: after-count ~ Binomial(n = before + after, p = exposure after ÷ total exposure). One-sided p in each direction. Reuses the log-space care of `trend_rules.poisson_tail`. Across the lots of one view, Benjamini-Hochberg, as the trend board does.
- **Windows.** Equal lengths, 90 to 365 days, by **event date**. The after window starts at the action date plus a settling period (default 0 days for a CAPA, 30 for a field action; B5-D5).
- **Result words, never verdicts:**

| Result | When |
|---|---|
| Too early | After window under 90 days |
| Too few to tell | Expected after-count under 5 if the rate had not changed |
| Fewer | p ≤ 0.05 towards fewer |
| More | p ≤ 0.05 towards more (a reopen trigger, 3.6) |
| No change seen | Otherwise |
| Counts only | Units unknown; same words but "by calendar days" and no rate per units |

- **Zero after.** With 0 complaints after, the view says "0 complaints; with this exposure the rate could still be up to X per 1,000 unit-months" (the 95% upper bound, about 3 ÷ exposure). Never "eliminated".
- **Limits shown on the view, always:** reporting lag (recent events may not be reported yet); a change in coding; seasonality; several actions at once (all action dates are marked); the person judges against the CAPA's criteria and signs. "Fewer" is not "effective"; only the signed check says that (CP-08).
- **Tests:** pure functions in `closed_loop/rules.py`, with the boundaries (89 vs 90 days, expected 4.9 vs 5, p exactly 0.05, all units unknown, one lot unknown).

### 3.5 Field action and product change, recorded lightly

FSCA as a workflow stays 2027 (`pms-coverage-map.md` item 6). B5 adds four optional fields to a decision follow-up (migration `tr26`), filled when it is completed:

- `action_reference` (the customer's number for the field action, CAPA step or change order);
- `action_kind` for a field action: correction, removal, advisory notice, software update, other;
- `action_effective_on` (date);
- `action_scope` (JSONB): lots and versions covered; for a product change, the new version.

Connect mode: the action lives in the customer's QMS; MDARIX records the reference and dates only. Complete mode: the same until the native CAPA (M5).

### 3.6 Reopen triggers

Checked by the existing hourly impact sweep (`decision_followups/impact.py` `run_for_all_tenants`). Each opens **one** impact assessment per decision, trigger and group (idempotent), with the task for the investigation owner. The person concludes; MDARIX never reopens by itself (B5-D7).

| Trigger | Fires when | Scenario |
|---|---|---|
| `CAPA_NOT_EFFECTIVE` | A CAPA from the decision is signed NOT_EFFECTIVE | CP-07 |
| `LATER_COMPLAINTS_MORE` | "More" on a version or lot cohort of the decision's scope | CP-09 |
| `RECURRENCE_AFTER_EFFECTIVE` | 2 or more later complaints after the CAPA was signed EFFECTIVE | CP-09 |
| `PROBLEM_ON_NEW_VERSION` | 2 or more complaints with the scope's problem on the new version of a product change | CP-10 |
| `COMPLAINT_ON_ACTIONED_LOT` | A complaint on a lot covered by a field action, with its event after the effective date | — |
| `LATER_SERIOUS_HARM` | A later linked complaint reports death or serious injury (B7 reopens the complaint; this asks about the decision) | IV-07 |

Labels are added to `decision_followups/rules.py:43` `TRIGGER_LABELS`. Evidence on the assessment: the counts and records as at firing, frozen in the audit event.

---

## 4. Decision Framework and operating modes

| Element | Challenge | Closed loop |
|---|---|---|
| Evidence | Record facts with their IDs; adopted facts become reviewed evidence | Later complaints, units, effectiveness rounds, field actions, each opening its records |
| Intelligence | Drafts H-1 to H-5, questions C-1 to C-9 | Before/after by version and lot, result words, triggers |
| Rules | Rule IDs and versions in the brief's Sources | Test, windows and thresholds printed on the view |
| Human judgement | Adopt or dismiss, judge, answer, review, sign | Sign the effectiveness check; conclude the impact assessment; a new decision supersedes |
| Traceability | All in the signed brief content hash | Computed from records, same read same answer; triggers audited with their numbers |

| | MDARIX Connect | MDARIX Complete |
|---|---|---|
| Complaints, lots, versions, units | Imported, read-only, origin shown | Kept in MDARIX |
| Investigation, challenge, brief, decision | Always MDARIX | Always MDARIX |
| CAPA, field action, change | In the QMS; MDARIX holds reference, dates, scope and the effectiveness check | The same until native CAPA (M5) |
| Did it work? and triggers | The same | The same |

---

## 5. Gaps, build steps, migration, cuts

### 5.1 Gap table

| # | Requirement | Exists today | Gap | Change |
|---|---|---|---|---|
| G1 | Drafts from correlated records | Template engine `hypothesis_engine/engine.py:78-129` (fixed "shutdown" text); hidden in trial | No record-based drafting anywhere | `case_challenge/facts.py` + `rules.py` H-0 to H-5 |
| G2 | Contradicting evidence found, not only linked | `case_intelligence/router.py:797` lists linked ones | Records that contradict are never found | "Against" facts per draft; C-1 |
| G3 | Missing evidence shown | Unknowns entered by hand (`router.py:1052`) | Data gaps (no version, no lot, no units, no genealogy) never listed | "Missing" facts; C-4 |
| G4 | Challenge prompts | Readiness warnings only (`readiness.py:252-296`) | No questions; open unknowns do not block (IV-15) | C-1 to C-9; material ones block submit |
| G5 | Rule tag on a hypothesis | `origin` only (`foundation.py:477`) | Which rule, which version | `tr26`: `hypotheses.draft_rule`, `draft_rule_version` |
| G6 | Brief cites every source | Evidence IDs and scope (`compose.py:109-166`, `:334-381`) | Changes, parts, suppliers, units, service, risks, rules not cited | `challenge` and `sources` sections in `compose()` |
| G7 | Later complaints linked to the decision | `covering_cases` open cases only (`triggers.py:176`) | Nothing after the decision | `closed_loop/service.py` links on read |
| G8 | Effectiveness by version and lot with units | Product-wide, calendar (`capa_effectiveness/service.py:233-268`) | No version, lot, denominator, test | `closed_loop/rules.py`; effectiveness detail shows it |
| G9 | Field actions linked | Follow-up type only (`decision_outcomes.py:35`) | No reference, date, lots | `tr26`: four follow-up columns |
| G10 | Loop back when it did not work | NOT_EFFECTIVE plans a new round only | No path back to the investigation (CP-07) | Triggers via impact assessments |
| G11 | "Did it work?" view | `QualityLoop.tsx` picture; effectiveness board | No before/after by version and lot | New tab + block |

### 5.2 Build steps (targeted tests per step; the full release gates once at the end)

| # | Step | Hours | Targeted tests |
|---|---|---|---|
| 0 | Branch from B7's tip; check one Alembic head (`tr25routinepath`); CHANGELOG section | 1 | `alembic heads` = 1 |
| 1 | Migration **tr26** + model fields | 3 | upgrade, downgrade, upgrade on the test DB; existing RLS test passes |
| 2 | Facts reader (2.2), PV-1 rules, one read per table | 8 | `test_b5_facts.py` (DB): unknown version kept apart; lot of another version never borrowed; change dates; units shipped vs released vs unknown; sample case reads |
| 3 | Draft rules H-0 to H-5 (pure) | 8 | `test_b5_draft_rules.py` (unit): each condition at its boundary; IV-14 timing; duplicates noted; no score field |
| 4 | Question rules C-1 to C-9 (pure) | 6 | `test_b5_questions.py` (unit): each rule fires and does not; material flag |
| 5 | API: `GET /investigations/{id}/challenge`; adopt (hypothesis + ticked record summaries as unreviewed derived-fact evidence + links); dismiss with reason; answer a question; audit | 8 | `test_b5_challenge_api.py` (DB): adopt, dismiss, answer, refusals on a closed case, cross-tenant 404, audit rows |
| 6 | Brief: challenge and Sources sections; material questions block submit; PDF and case record | 8 | `test_b5_brief.py` (DB): every statement has a source; unanswered material blocks; content hash changes with an answer; old briefs read |
| 7 | Screens: Challenge view (drafts, adopt/dismiss drawer, questions), brief sections | 14 | vitest `challenge.test.tsx`, `briefSources.test.tsx`; `tsc` |
| 8 | Closed-loop statistics (pure): windows, exposure, conditional test, BH, zero-after bound, result words | 8 | `test_b5_loop_rules.py` (unit): boundaries in 3.4 |
| 9 | Closed-loop reader: decision scope from the signed brief; later complaints; by version, lot cohorts, new vs old version | 10 | `test_b5_loop_api.py` (DB): units unknown → counts only; unknown version apart; superseded decision; Connect origin |
| 10 | Follow-up fields: reference, kind, effective date, scope; product change names the new version | 4 | `test_b5_followup_fields.py` (DB) |
| 11 | Reopen triggers in the hourly sweep; labels; idempotent | 6 | `test_b5_triggers.py` (DB): each trigger once; none on a superseded decision; none on sample data in customer numbers |
| 12 | Screens: Did it work? tab; effectiveness detail block; Product 360 link | 12 | vitest `didItWork.test.tsx`, `effectiveness` (existing) |
| 13 | Sample check (SAMPLE-INV-001 reads as 2.3; CAPA-02 "too early"); J2 story; scenario register rows; release gates | 8 | `test_sample_story_days.py`, `test_flagship_walkthrough.py`, `test_getting_started_part1.py` (regression) |
| | **Total** | **104** | B5a = steps 0–7 (56 h); B5b = steps 8–13 (48 h; step 13 shared) |

Performance budget (B6 targets): the challenge read and the Did it work? read each under 1.5 s on 5,000 complaints; at most 12 queries each. If missed, an expand-only index in `tr26` on `complaints (tenant_id, product_version_id, event_timestamp)` (the W1 fallback index, if W1 did not add it).

### 5.3 Migration

**One migration: `tr26_trial_challenge_loop.py`, revision `tr26challengeloop`, `down_revision` `tr25routinepath`** (B7's head; DB-1 uses tr21–tr24). Additive, nullable, no data moved:

| Table | Columns |
|---|---|
| `hypotheses` | `draft_rule` String(10), `draft_rule_version` Integer |
| `decision_follow_ups` | `action_reference` String(120), `action_kind` String(30), `action_effective_on` Date, `action_scope` JSONB |

Challenge answers live in the brief narrative and triggers in `impact_assessments.trigger` (free text): no columns. **mvp-1.0:** the forward merge adds a merge revision joining its head and `tr26challengeloop`, the md53–md66 pattern.

### 5.4 What can be cut (in this order; each cut stands alone)

1. Product 360 link to Did it work? (1 h).
2. Lot cohorts view; versions stay (about 4 h).
3. Triggers `COMPLAINT_ON_ACTIONED_LOT` and `PROBLEM_ON_NEW_VERSION` (about 2 h).
4. Questions C-6 to C-9 (about 2 h).
5. Adopt as record summaries: adopting creates the hypothesis only, without evidence items (about 3 h).
6. The whole of B5b ships later; B5a (challenge and brief) stands alone.

Never cut: the PV-1 rules, "units unknown", the labels, the material-question block, the Sources section.

### 5.5 Scenarios (acceptance criteria, `scenario-register.md`)

IV-01, IV-02, IV-03 (drafts, for and against), IV-04 (C-1 blocks submit), IV-05 (H-0 and missing list; the person sends evidence requests, exists), IV-06 (exists, regression), IV-07 (`LATER_SERIOUS_HARM`), IV-08 (exists, shown in brief), IV-09 (C-6), IV-10 (rules read fields only), IV-15 (C-5), IV-16 (exists, regression), CP-01 (decision outcome without CAPA, exists, shown in the loop), CP-07, CP-08, CP-09, CP-10. New: B5-01 units unknown for one lot → no rate for that group; B5-02 a complaint with no version after the decision → "version unknown", not in any version; B5-03 a change after the first complaint → that complaint counts against H-1.

### 5.6 How it fits the WHIF sample story

B5 ships after WHIF (11–12 Dec), so the WHIF demo does not change. It continues the same story for investor demos and pilots: OrbitCare 300 Rev B, SAMPLE-INV-001. Challenge shows three drafts that match what the sample author wrote, and it asks the hard question about the Rev A complaints and the open bench test. The signed brief lists every record. After the decision, Did it work? on SAMPLE-CAPA-02 says honestly "too early" (its check is planned for day +75), with the lot cohorts ready. No after-action complaints are seeded (B5-D10). Product 360 and Supplier 360 link to the same view.

### 5.7 Risks

| Risk | Effect | Answer |
|---|---|---|
| Thresholds wrong for a real customer | Too many or too few drafts or questions | Rules versioned; thresholds in one place; B4's rule register absorbs them later |
| Users read "fewer" as "effective" | Overclaiming | Labels, limits box, and only the signed check says effective |
| Sparse data on pilots (no lots, no units) | Most views say "units unknown" | That is the honest answer; C-4 and "missing" tell what to import |
| Brief content grows (Sources) | Heavier brief page | Collapsed with a count; capped lists as compose already does (`compose.py:26-33`) |

---

## 6. Owner decisions needed

| # | Decision | Recommendation |
|---|---|---|
| B5-D1 | Drafts are computed on read and stored only when a person adopts or dismisses them | **Yes**: no stale drafts, same read same answer |
| B5-D2 | Adopting a draft turns the facts the person ticks into unreviewed evidence items ("record summary") linked for or against | **Yes**: they then go through the normal evidence review |
| B5-D3 | Material questions (C-1, C-2, C-3, C-4 above 20%, C-5) block "Submit for review" until answered or marked not applicable with a reason | **Yes**; the rest warn only |
| B5-D4 | Replace the old "shutdown" template hypotheses (full edition, AI off) with the H-rules | **Yes**; the trial is unaffected |
| B5-D5 | Thresholds: H-2 60/40, C-4 20%, windows 90–365 days, minimum expected 5, p ≤ 0.05 one-sided with BH; settling period 0 days for CAPA, 30 for field action | **Yes as listed**, versioned as rule v1 |
| B5-D6 | Denominator order: units shipped → units released → "units unknown" (counts only); never partial | **Yes** |
| B5-D7 | Triggers open an impact assessment; MDARIX never reopens a decision by itself | **Yes** |
| B5-D8 | Field actions recorded lightly on the follow-up (reference, kind, effective date, lots and versions); the FSCA workflow stays 2027 | **Yes** |
| B5-D9 | Per-lot rows in Did it work? follow the 1 Nov rule for Lot impact and Supplier 360 lots (trial-only, hidden on paid pilots); versions and cohort totals show everywhere | **Yes for now**; lift all three together when you decide |
| B5-D10 | No seeded after-action complaints in the sample; CAPA-02 shows "too early" | **Yes**: keep the sample honest (as W1 OD-6) |
| B5-D11 | Did it work? lives on the investigation (Decisions & actions), on the effectiveness check, and is linked from Product 360 | **Yes** |
| B5-D12 | Getting started Parts 2 and 3 (Addendum B) | **A small item after B5**, not in B5 |
| B5-D13 | One migration `tr26` (six nullable columns) instead of hiding the rule tag and field-action data in free text | **Yes** |
| B5-D14 | Ship in two parts if needed: B5a (challenge, brief) then B5b (closed loop) | **Yes** |

---

## 7. What could not be verified

- Nothing was run; no database was read. Line numbers are from `trial-094` at the time of reading and may move with B7.
- **B7's final head** is assumed to be `tr25routinepath`; step 0 checks it.
- **Sample numbers** (Rev A pressure-alarm complaints, lots 003–004 counts, units) were not counted; the build's tests fix them.
- Whether every sample lot has a release date and units shipped was not checked; if not, the sample shows "units unknown" for those lots, which is acceptable.
- The reason behind the 1 Nov "lots trial-only" rule was not found in the files read; B5-D9 follows it unchanged.
- The statistics are standard (an exact conditional test for two Poisson rates; Benjamini-Hochberg), cited from knowledge, not from a text read for this spec.

## Owner approval (10 Nov 2026)
"approve B5 spec": all fourteen recommendations D1–D14 accepted. Build starts once all B7 development (B7a and B7b) is complete, on its own branch from the B7 tip; migration tr26challengeloop chained after B7's head (step 0 checks it). Ships after the WHIF freeze, as B5a then B5b if needed.

## Build status (11 Nov 2026, run 1)

Branch `feat/b5-challenge-loop` from `feat/b7-routine-path` (b6ad14c6), worktree `trial-093`. Local commits only; nothing pushed, tagged or deployed. AI stays off.

| Step | State | Commit |
|---|---|---|
| 0 Branch, one head (`tr25routinepath`), CHANGELOG `[0.10.98]` | Done | 05289625 |
| 1 Migration `tr26challengeloop` + models + legacy-plane step `tr26` | Done (upgrade, downgrade, upgrade and `alembic check` on `mdarix_b2_test`; one action-kind CHECK that allows NULL added) | 05289625 |
| 2 Facts reader `backend/app/case_challenge/facts.py` | Done | beb3e5fe |
| 3 Draft rules H-0..H-5 `case_challenge/rules.py` | Done | cb9a9b02 |
| 4 Question rules C-1..C-9 `case_challenge/questions.py` | Done | d5c31e0e |
| 5 API `case_challenge/router.py` + switch `MDARIX_CHALLENGE` (session `challenge`) | Done | 17b63ff6 |
| 6 Brief Challenge + Sources sections, material questions block submit, sample author's answers | Done, except the PDF and the case record download (they do not render the new keys yet) | ba4c1f7a |
| 7 Screens (Challenge view, brief sections), vitest, `tsc`, one Playwright spec | **Not started** | — |
| 8-13 (B5b) | Not started | — |

B5a is **not complete**: step 7 (screens) and the PDF/case-record rendering of step 6 remain.

What the sample reads (fixed by `test_b5_challenge_api.py`): drafts **H-1** (SAMPLE-CHG-014; "you may already have this" on the sample supplier hypothesis; against: Rev A same-problem complaints with the Precision Sensors part) and **H-2** ("lots 003 and 004"); questions **C-1** and **C-5** (material, answered by the sample author) and **C-7** (Rev A outside the scope).

Deviations and open points for the owner:
- **H-4 does not fire on the sample** (2.3 expected it): no sample scope complaint carries a No Fault Found / user-error code or a country, and the rules read fields only (IV-10). The sample settings hypothesis therefore shows no "you may already have this". Options: leave it (honest), or give some sample complaints a country/site in step 13.
- C-3 does not fire on the sample: every scope complaint's event is after SAMPLE-CHG-014.
- Drafts compute unit-months from units released with release dates (trend `unit_days`); the shipped-first denominator order (B5-D6) is applied in B5b's Did it work? reader, not in the drafts.
- Dismissed and adopted drafts are kept as `intelligence_events` rows (`object_type` CHALLENGE_DRAFT) with the audit event; no new table.
- "You may already have this" matches a considered hypothesis adopted from the same rule, or whose statement names the change ID, supplier, lot IDs or (H-4) use/setting words: a hint only, never a merge.
- B5-D4 (replace the old template engine in the full edition) is not built yet.

## Build status (11 Nov 2026, run 2)

Same branch and worktree; local commits only, nothing pushed, tagged or deployed. AI off.

| Step | State | Commit |
|---|---|---|
| 6 leftover: case record download (JSON/CSV/PDF) and investigation report document show Challenge and Sources | Done (new briefs only; brief questions now keep their cited records) | 12a6f8d5 |
| 7 Screens: Intelligence › Challenge, brief Challenge + Sources (collapsed), hidden unless session `challenge` is true; Playwright `frontend/e2e/challenge.spec.ts` written, NOT RUN | Done | 4719cf23 |
| 8 Closed-loop statistics `closed_loop/rules.py` | Done | 4c41e618 |
| 9 Reader + `GET /investigations/{id}/did-it-work`, own switch **`MDARIX_CLOSED_LOOP`** (session `closed_loop`) | Done | 9b6b238e |
| 10 Follow-up fields on completion (reference, kind, effective date, lots/versions, new version) | Done | 20d96174 |
| 11 Reopen triggers | **Not started** | — |
| 12 Screens (Did it work? tab, effectiveness block, Product 360 link) | **Not started** | — |
| 13 Sample check, J2 story, scenario rows, release gates | **Not started** | — |

**B5a is complete** (steps 0–7). B5b: steps 8–10 done, 11–13 left. CHANGELOG 0.10.98 has lines for all of it.

Performance (challenge GET, measured by `tests/test_b5_challenge_performance.py` on `mdarix_b2_test`): sample 0.13 s,
200 scope complaints 0.17 s (budget 1.5 s). Queries: 19 in the read itself (21 before this run; two of them are per
supplier in the P-1 check), 33 per request with sign-in and tenant checks; the count does not grow with complaints.
**Over the 12-query budget**; time is far inside it. Getting to 12 would mean merging distinct table reads (scope +
complaints, hypotheses + rule tags + links); not done.

Notes for the next run / owner:
- CAPA action date: a check's `measured_from`; with no check planned (SAMPLE-CAPA-02 today) the decision's signing date,
  marked `measured_from: "decision"`.
- Lot cohorts (lots released before vs after the action, same period) are tested only with units known; with units
  unknown they show "Counts only (units unknown)", untested (a calendar test between cohorts says nothing).
- Step 11 design point: `impact_assessments` has no group column; idempotency "per decision, trigger and group" needs
  either the group in the trigger text (40 chars) or a check against the `REOPEN_TRIGGER_FIRED` audit details.
- Fixed two stale assertions in `tests/test_qms_documents_api.py` ("Case" -> "Investigation", from B2 step 6).

## Build status (11 Nov 2026, run 3)

Same branch and worktree; local commits only, nothing pushed, tagged or deployed. AI off. No migration added (tr26 only).

| Step | State | Commit |
|---|---|---|
| 0 Story set re-run after steps 8-10 | Done: 22 passed, 1 xfailed (the xfail is in the existing set) | — |
| 11 Reopen triggers `closed_loop/triggers.py`, in the **hourly** late-evidence pass (`impact.run_for_all_tenants`; the scheduler has no 15-minute impact pass) | Done | b8d16ae2 |
| 12 Screens: Did it work? under Decisions & actions (new navigation) and the classic Decision tab; the CAPA-only block on Records › Effectiveness checks; "Did it work?" beside each investigation in a Product 360 version story; Playwright `frontend/e2e/did-it-work.spec.ts` written, NOT RUN | Done | 6e6d946e |
| 13 Sample check (SAMPLE-CAPA-02 "Too early", no later complaints), scenario rows B5-01..B5-19 in `scenario-register.md` (NOT RUN), user guide (Challenge, Did it work?), CHANGELOG 0.10.98 | Done | 8b3a0da9 |

**All of B5 (B5a steps 0-7 and B5b steps 8-13) is built**, with targeted tests only; the full release gates (full pytest, ruff, vitest, build) and the Playwright specs run in the ~24 Nov test release.

How step 11 works:
- One read of Did it work? per DECIDED or CLOSED case with a current signed brief decision; the six triggers are a pure function of that view (`triggers.fired`).
- De-duplication: one impact assessment per decision + trigger + group, checked against the `REOPEN_TRIGGER_FIRED` audit details (`decision_id`, `trigger`, `group`); the trigger code stays readable in `impact_assessments.trigger`. Groups: a CAPA round ("SAMPLE-CAPA-02 round 1"), "capa SAMPLE-CAPA-02 · Rev B" (an action and a version or the lot cohorts), a new version, a field action reference, a complaint.
- The audit event freezes the summary, the record refs (up to 50) and the rule version. The task title carries the summary. The assessment has no evidence (it is concluded as for late evidence). The case and the decision are never changed.
- R6: Did it work? (and so the triggers) no longer counts sample complaints on an investigation that is not a sample one.
- `RECURRENCE_AFTER_EFFECTIVE` counts version-unknown later complaints too (same product and problem); `LATER_COMPLAINTS_MORE` also fires on "More" in the new-vs-old version comparison. `COMPLAINT_ON_ACTIONED_LOT` is one per field action (not per lot).

Open points for the owner / next run:
- Owner decided (11 Nov): the sample challenge answers are approved as written, and H-4 stays not firing on the sample. Nothing changed for either.
- After a session restart Docker Desktop was not running, so the database tests could not run again at the end. The last database runs of this run (story set 22 passed / 1 xfailed; `test_b5_loop_api.py` 7 passed; `test_b5_triggers.py` 8 passed) came after the last backend change. The run after the restart: 37 passed, 27 errors, all of them `connection refused` on port 5433.
- The brief said "the existing 15-minute pass"; the impact sweep is hourly (spec 3.6 says hourly). Triggers ride the hourly pass; none fires on the event itself (a NOT_EFFECTIVE signature waits up to an hour).
- `src/app/linkTable.test.ts` "every A › B path in the user guide…" already fails on the branch before this run ("Open Settings › Alerts and files", B7 text). The new guide paths pass when that one is excluded. Not fixed here.
- The trigger sweep reads Did it work? for every decided case each hour (marked `shortcut:`); fine for trials and pilots.
- The new vs old version view and lot cohorts with units unknown remain untested against the database.

## Owner decisions on the sample (11 Nov 2026)
- "sample answers OK": the sample author's answers to C-1 and C-5 (`SAMPLE_CHALLENGE_ANSWERS`) are approved as written.
- "(2) leave": H-4 does not fire on the sample; no sample data is added for it.
