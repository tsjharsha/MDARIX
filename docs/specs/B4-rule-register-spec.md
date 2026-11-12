# B4: Rule register, rules as data, the MDARIX floor and effective dating

Version 1, 11 Nov 2026. **APPROVED by the owner on 11 Nov 2026 (see "Approval record").** Nothing here is built. Per the owner's automatic chain (11 Nov), B4 starts when B5 is complete, on the recommendations in section 7 unless the owner changes them. Decisions marked **⚑** touch regulatory interpretation or signed records: they need the owner's explicit answer before the build starts.

- **Sources:** `development-cycle-1.md` (B4, B4b, B4c rows; C4; E4; Addenda K), `master-sequence-proposal.md` (item 11), `decision-tree-deep-dive/report.md` (D1–D12, approved 7 Nov), `authority-forms-spec/spec.md` and `spot-check.md`, `other-country-reports/spec.md` (OC-D3, OC-D5), `b3-emdr/B3-execution-plan.md`, `b5-challenge-closed-loop/spec.md`, `b7-routine-path/spec.md`, `scenario-register.md` (DT, RG).
- **Code read** (read-only): worktree `trial-094`, branch `feat/b3-emdr-0.10.96`. Every `file:line` below is on that branch, under `backend/app/` unless shown. B7 and B5 change some of these files on their own branches; build step 0 re-checks the lines on B5's tip.
- **Scope:** the register, rules as data, the floor, effective dating. **Not in B4:** customer questionnaire configuration (B4b), templates, import/export and regulatory change impact (B4c, with E4), the answer-screen simplifications S1–S9 (move to B4b), evidence correlation (now in B5's facts reader and W1).

---

## 1. Purpose, in plain words

**One place lists every rule MDARIX applies.** For each rule: what it decides, the regulation and clause it comes from, its version, the dates it is in force (from, to), and who approved it. Rules include the reportability windows per market, the triage tiers, the routine-path rules, the report-field rules and the investigation challenge rules.

**The regulatory rules become data.** The reportability logic of the five markets (questions, when a report is owed, which report and its period, how days are counted, the triage tiers) moves out of hand-written code into versioned data files. One small engine reads them. New markets (B9 India MvPI, Canada, US importer and user facility; B8 EU and GB MIR; B9b other countries) are then added as data, not written in code twice.

**Version 1 changes nothing.** Version 1 of every rule is today's logic. A test runs every answer combination through the old code and through the new data and requires byte-for-byte identical results before the switch is turned on.

**Rules change by date, never backwards.** A rule version has an effective date. An event is judged by the rules in force on its awareness date. A signed record keeps the rule version it used. A rule change never rewrites a signed record.

### What changes for users
| Who | Today | With B4 |
|---|---|---|
| QA/RA reviewer | Sees a question set code ("MDARIX starter, version 1"); cannot see the logic behind the suggestion or its source in one place | A **Rules** tab lists every rule, its source and version. On a conclusion, "Rules used" shows the rules in force at awareness, today's rules, and what was decided |
| Approver / signer | Signs the questions, answers, suggestion and due date | Same, plus the floor version and the rules that applied are inside what is signed. Nothing extra to click |
| Auditor | Must trust that `US-starter-1` meant the same logic over time (it did not: the US Unknown rule changed in 0.10.81 under the same code) | Can see which exact rule version (with a content fingerprint) produced each signed conclusion, and which version was in force on any date |
| Customer admin | No change | No change. Customers cannot edit the floor (B4b adds their own stricter rules on top) |
| MDARIX | A rule change is a code change that may silently alter old meanings | A rule change is a new version file with source, dates and approver; a build test fails if content changes without a new version |

---

## 2. The MDARIX floor

The floor is the set of rules no customer setting can go below. Today it holds because customers cannot change the logic at all (`decision_guides/rules.py:1-20`). B4 writes it down, holds it in the register, and keeps it true when B4b lets customers add their own rules.

| # | Floor rule | Where it holds today |
|---|---|---|
| F1 | Floor questions are always asked. They cannot be removed, reordered, reworded or hidden. | `decision_guides/rules.py:31-33` (LOCKED), `:197-211` |
| F2 | Floor rules are always evaluated. A customer rule can only raise the outcome (Not reportable → Needs more information → Reportable) or pick a shorter legal report. Never lower, never longer. | By construction today (logic fixed); B4b raise-only |
| F3 | **Unknown is never No.** Unknown or blank is "undecided"; "Not reportable" cannot be signed while an Unknown could make it reportable. | `reportability/markets.py:491-498`, `:908-920` |
| F4 | While an answer that picks the report is Unknown, the shortest report the facts do not exclude applies. | `markets.py:541-584` (0.10.81) |
| F5 | Death, serious injury or deterioration, public health threat, malfunction that could harm on recurrence: never waivable. No exceptions in the first release (D4, approved). | Approved 7 Nov |
| F6 | The legal period is the longest clock. A Reportable conclusion uses the organisation's window only when it matches the legal period exactly; otherwise the regulation's. A pending one takes the earliest. | `markets.py:1010-1045` (code audit 3). Gap FG-1 below |
| F7 | Days are counted the conservative way: earliest of the authority's and the organisation's day; no weekend or holiday extension; GB and India count the awareness day as day 1. | `reportability/deadlines.py:36-42`, `:126-160` |
| F8 | Ask, never guess: no country or no awareness date blocks signing. | `reportability/facts.py:1-22` |
| F9 | Protected harm terms (death, life-threatening, permanent impairment) cannot be lowered. | `markets.py:805-808`, `:884` |
| F10 | Administrators never sign or approve; a guide version needs a second person (trial: same person, labelled). | `decision_guides/rules.py:330-337` |
| F11 | Signed records never change; a change is a new version with a reason. | `assessment_router.py:463-464`, OD-4 |
| F12 | The routine path's "not reportable" is offered only when every fact it rests on is recorded. | `complaint_disposition/rules.py:106-118` |

**How customer rules (B4b) will sit on top.** B4 stores the floor per market as data in one format: conditions over answers, the report types with precedence, notes and folding. B4b adds an organisation layer in the same format, stored per tenant on `decision_guide_versions` (D-report §6). The result is the higher of the two outcomes and the shorter of the two reports. Because the floor is always evaluated and the combination only takes the maximum, no organisation layer can lower an outcome or lengthen a clock. B4b proves it with the property test DT-36. **B4 builds no combination code** (nothing to combine yet); the format is chosen so B4b needs none of B4's code changed.

### Floor gaps found (carried unchanged in B4; decisions in section 7)
| # | Gap | Evidence | Recommendation |
|---|---|---|---|
| FG-1 | The reportability watch shows only the organisation's windows. A window longer than the law (for example 60 days for the US) shows a later deadline on the watch. The assessment clock and triage are correct. | `reportability/rules.py:393-429`; `service.py:200-217`; window limit 1–365 days `rules.py:47` | R-D10 |
| FG-2 | India has no legal period in code. A Reportable India conclusion uses the organisation's India window (which may be any length); triage uses 15 days. | `markets.py:89-90`; `intake/rules.py:465-469` | R-D11 |
| FG-3 | The routine path signs "not reportable" for every enabled market on one basis (no death, serious injury or malfunction recorded). It cites no regulation and does not cover the EU/GB threat or "incident" questions. | `complaint_disposition/rules.py:86-89`; `router.py:605, 684` | R-D11 |
| FG-4 | Open owner decisions carried in the logic: OD-1 (work-day windows in GB/India ignore day 1) and OD-3 (Canada: Unknown "in Canada" gives 10 days). | `docs/compliance/REGULATORY_DECISION_TABLES.md` §7 | R-D11 |
| FG-5 | Triage does not store the rule versions it used (`provisional-starter-1`, harm words): they are shown only. | `intake/service.py:874-875` | Later (triage is not a signed regulatory decision); listed in the register |
| FG-6 | Conclusions signed before 0.10.81 under `US-starter-1` used older logic. They keep what they signed (fingerprint), but cannot be re-run. | `markets.py:541-542`; commit 911bec72 | R-D5: never backfill |

---

## 3. Inventory of the rules in code today

49 rules. **9 become data in B4** (8 moved from code, 1 already data and now registered). The other 40 stay code and are listed in the register with their version and source. "Pinned" means a build test fails if the rule's code changes without a new register version (step 7).

### 3.1 Regulatory: reportability, deadlines, facts
| # | Rule | file:line | Market | What it decides | Versioned? | Source cited? | B4 |
|---|---|---|---|---|---|---|---|
| 1 | Question sets | `reportability/markets.py:175, 346, 356, 373, 423` (`QUESTION_SETS :485`) | US, EU/NI, GB, IN, CA | Questions, definitions, clauses, "serious" flags | Yes (`US-starter-1`…) | Yes, per question | **Data** |
| 2 | Report types and legal periods | `markets.py:80-105` | All | Label, days, calendar or work days | No | Yes, in the label | **Data** |
| 3 | When a report is owed, which report, Unknown notes (`evaluate`) | `markets.py:529-599` | Each | Suggestion, report type, notes | **No** (drifted in 0.10.81 under the same code) | Partly (notes) | **Data** |
| 4 | Questions folded away (`not_asked`) | `markets.py:602-653` | Each | Which questions earlier answers make unnecessary | No | No | **Data** |
| 5 | Pre-fill from the record and notes beside serious-injury questions | `markets.py:713-763` | US, IN | Death and malfunction offered as "Confirm"; SI shown as a note | No | No (0.10.83 D2) | **Data** |
| 6 | Authority time zones | `reportability/deadlines.py:36-41` | US, EU/NI, GB, IN | Zone a deadline is counted in | No | No | **Data** |
| 7 | Awareness day is day 1 | `deadlines.py:42` | GB, IN | Day counting start | No | No (starter; OD-1 open) | **Data** |
| 8 | Triage provisional tiers, US remedial 5 work days, "unless ruled out" | `intake/rules.py:42, 447-503` | All | Provisional deadline per tier | Yes (`provisional-starter-1`) | Yes, in labels | **Data** (in each market's floor) |
| 9 | US eMDR rule book (161 rows) | `authority_reports/rules/us_emdr.csv`, read at `authority_reports/emdr.py:64, 156` | US | Blocks FDA requires per report type | No version code | Yes (source column) | **Already data**: registered, hash pinned |
| 10 | Three-valued answers | `markets.py:491-511` | All | Yes = true; No, N.A. = false; Unknown, blank = undecided | No | No | Code: the engine's core, not market data |
| 11 | Answer completeness; US5 "No" needs own words | `markets.py:675-703` | All, US | Whether answers can be saved or signed | No | No | Code |
| 12 | Conclusion rules: no Not reportable while pending; override needs a reason | `markets.py:908-920` | All | What may be signed | No | No | Code, pinned (floor F3) |
| 13 | Harm scale, thresholds, QMS severity map, protected terms | `markets.py:787-836` | All | Harm level; serious threshold per market | Yes (`scale-starter-1`) | Partly (IMDRF Annex F) | Code: already versioned and signed |
| 14 | Harm level checks and scale disagreement | `markets.py:874-905` | All | Reasons needed | No | No | Code |
| 15 | Market of the incident country; UK named whole is asked | `markets.py:49-55, 926-959`; `rules.py:141-150` | All | Which market's rules apply | No | No (OD-2) | Code (B9b makes the market list data with its migration) |
| 16 | IVD cites the IVDR | `markets.py:964-979`; `intake/rules.py:477-479` | EU | Citation only | No | Starter | Code |
| 17 | Which clock a conclusion gets (window or regulation; pending earliest) | `markets.py:1010-1045` | All | Due date of an assessment | No | No | Code, pinned; reads periods from data |
| 18 | Counting algorithm (start day, work days, end of day) | `deadlines.py:66-160` | All | The latest day and its end | No | No | Code, pinned; reads zones and day 1 from data |
| 19 | "Due soon" | `deadlines.py:77` | All | Display state | No | No | Code |
| 20 | Facts needed before signing (country, awareness) | `reportability/facts.py:19-22` and `needed` | All | Blocks signing | No | Yes (rule texts) | Code, pinned |
| 21 | Awareness moment (earliest of awareness, received, recorded, linked) | `reportability/service.py:70-88` | All | Where every clock starts | No | No | Code, pinned |
| 22 | Reporting window templates | `reportability/rules.py:158` | All | Starting points the organisation may save | No | Yes (basis) | Code (organisation's choice; B4c templates) |
| 23 | Window limits | `rules.py:42-50`, `windows_problem :298` | All | What a window may be | No | No | Code (FG-1) |
| 24 | What goes on the watch | `rules.py:328, 454` | All | Death, SI, malfunction, unknown outcome | No | No | Code |
| 25 | Watch clocks per window; settling review outcomes | `rules.py:67, 393-429` | All | Watch deadlines and state | No | No | Code |
| 26 | "May also apply" advice | `decision_guides/trees.py:46-53` | All | Advice only | No | Partly | Code |
| 27 | Routine basis ("not reportable" for every market) | `complaint_disposition/rules.py:86-89, 106-118`; `router.py:605, 684` | All | A signed market conclusion without the tree | Code `ROUTINE-BASIS`, no number | **No** (FG-3) | Code, pinned; register code `routine-basis-1` |

### 3.2 Procedure: intake, triage, disposition, guides
| # | Rule | file:line | What it decides | Versioned? | Source? | B4 |
|---|---|---|---|---|---|---|
| 28 | First-contact guide and outcomes table | `intake/rules.py:39, 56-120, 270` | Complaint, service only, pending | Yes (`first-contact-starter-1`) | G32 | Code |
| 29 | Case check | `intake/case_rules.py:32, 148` | Case outcome | Yes (`case-check-starter-2`) | — | Code |
| 30 | Harm words, fault words | `intake/rules.py:40-41, 144, 187` | Triage flags | Yes (`harm-words-starter-1`, `fault-words-starter-1`) | — | Code |
| 31 | Triage flags | `intake/rules.py:338, 371` | Flagged or not | No | — | Code |
| 32 | Triage target and two speeds (fast hours, acknowledge in 1 h) | `intake/rules.py:46`; `intake/triage_rules.py:30, 99-134` | Fast or routine; due times | No | — | Code |
| 33 | Severity floor from the facts | `triage_rules.py:90-96` | Death = Catastrophic; SI = Serious | No | — | Code |
| 34 | Triage downgrade needs a second person; automatic reopen | `triage_rules.py:168-190` | Who approves; when it reopens | No | — | Code |
| 35 | Possible duplicates (2 days) | `intake/rules.py:47, 637` | Duplicate reasons | No | — | Code |
| 36 | Disposition tree | `complaint_disposition/rules.py:24, 49, 92` | Escalate, known issue, service level | Yes (`disposition-starter-1`; B7 makes `-2`) | ISO 13485 8.2.2 | Code |
| 37 | Escalation triggers; recurrence 2 in 30 days | `complaint_disposition/triggers.py:40-60, 311` | Escalation | No | — | Code |
| 38 | Classification coding criteria | `complaint_classification/rules.py:15` | Use environment, user type | Yes (`coding-starter-1`) | — | Code |
| 39 | Guide governance: locked wording, 10 extras, starter test rows, approval | `decision_guides/rules.py:31-37, 330-337, 490` | What a customer may change | Version per guide | — | Code |
| 40 | B7 routine-path rules: ticket rule, No fault found, reasons, customer told | B7 branch, `complaint_disposition/rules.py` | Routine close | Yes (`disposition-starter-2`) | ISO 13485 8.2.2 | Code |

### 3.3 Authority reports
| # | Rule | file:line | What it decides | Versioned? | Source? | B4 |
|---|---|---|---|---|---|---|
| 41 | Form field rules: 3500A, MDAE, EU MIR, GB MIR, Health Canada; response form | `authority_reports/forms.py` (3500A `:186-340`, MDAE `:341`, MIR `:560`, RESPONSE `:1601` `response-starter-1`) | Mandatory fields per report type | Form editions | Yes (`source_document`) | Code (B8 adds EU/GB rule-book CSVs like #9) |
| 42 | eMDR coded and text blocks required | `authority_reports/emdr.py:42, 59` | eMDR check | No | FDA list | Code |
| 43 | G2b follow-up after submission (rows 1–4), waits | `authority_reports/rules.py:62-63, 172-199` | When to check acceptance | No | G2b | Code |
| 44 | Report approval roles | `authority_reports/rules.py:131` | Who approves a snapshot | No | — | Code |

### 3.4 Quality analytics (not regulatory)
| # | Rule | file:line | What it decides | Versioned? | B4 |
|---|---|---|---|---|---|
| 45 | Trend rule (30 / 180 / 60 days; p 0.01 / 0.05) | `signals/trend_rules.py:54-59` | Trend result | Per tenant (`signals.py:88`) | Code |
| 46 | P-1 supplier part across products | `product360/supplier_service.py:24` | Pattern box | Yes (`RULE_VERSION = 1`) | Code |
| 47 | B5 drafts H-0 to H-5 | B5 branch (spec §2.3) | Draft explanations | v1, on the hypothesis (`tr26`) | Code |
| 48 | B5 challenge questions C-1 to C-9 | B5 branch (spec §2.4) | Questions; material ones block | v1, in the brief's Sources | Code |
| 49 | B5 before/after result words and reopen triggers | B5 branch (spec §3.4, §3.6) | "Did it work?" words; reopen | v1 | Code |

**Why the 40 stay code.** They are MDARIX procedure, analytics or algorithms, not market law; most are already versioned and stored on their records; and none is needed to add a market as data. The register still lists each one with its version, source, and "held in MDARIX's code". The regulatory ones (#12, #17, #18, #20, #21, #27) are pinned so they cannot change silently.

### 3.5 How signed records keep the rule version today
| Record | What is kept | What is missing |
|---|---|---|
| Market conclusion (`complaint_market_assessments`, `db/models/market_assessment.py`) | `question_set`, `scale_version`, `report_type`, `window_name`, `due_on`; the signed material holds every question's text and clause, answers, suggestion, conclusion, due date (`assessment_router.py:523-557`) | The logic version, the rules that applied, the awareness moment and how the date was counted |
| Disposition | `rules_version` in the material (`complaint_disposition/router.py:595`); `coding_criteria_version` column | — |
| Case check | `guide_version` column (`intake/router.py:1001`) | — |
| Guide version | `code`, `content_fingerprint`, signed approval | No effective date (`published_at` only) |
| Triage | Nothing (versions shown only) | FG-5 |

---

## 4. Effective dating

### 4.1 Which date picks the version
| Kind of rule | Date that picks the version | Why |
|---|---|---|
| Reportability floor (questions, logic, report types, periods, counting, triage tiers) | **Awareness day** of the event, in the authority's time zone (the organisation's for Canada, which has no authority zone in code) | D5 (approved 7 Nov): "the floor in force at the awareness date". The law that applies is the one in force when the manufacturer became aware |
| Report form and rule book (mandatory fields, form edition) | **Day the report is sent for approval** | Authorities take the form edition in use on submission; B3 Q3 already dates the report on that day. B4 records this; selection is built when a second edition exists (B8) |
| MDARIX procedure and analytics rules (#28–#49) | **Decision**: the version in force when the draft starts, kept until it is signed | Today's behaviour (T-G15: a draft keeps the version it started with) |
| Organisation layer (B4b) | When the assessment starts (D5) | B4b |

**Version 1 is in force "from the start"** (no lower date), so every past complaint, sample and import keeps today's outcome. The law's own date is shown as information (R-D7 ⚑).

**Choosing among versions.** Each version has `effective_from` (a date, or "from the start") and `effective_to` (a date, or open). For a day, the version used is the **highest version number whose period contains that day**.
- A **law change** is a new version from the law's date; the old version gets `effective_to` = that date. Events with an earlier awareness day keep the old one.
- A **correction** (MDARIX finds its own rule wrong) is a new version with the **same period** as the version it corrects. Being higher, it replaces it for that period at once (R-D4 ⚑).
- The register's build test refuses: overlapping versions of a different kind, gaps in coverage, an `effective_to` before `effective_from`, and a version whose content changed without a new number.

### 4.2 What happens to work in progress when a version changes
| Situation | Behaviour |
|---|---|
| Signed conclusion | **Never changes.** Its floor code, rules applied, due date and fingerprint stay as signed |
| Report created from a signed conclusion | Its due date stays. A person re-signs to change it (existing LE-4 rule) |
| Draft assessment | The floor is re-picked from the awareness day at every save and stored on the draft. At signing, if the floor picked now differs from the draft's (a correction arrived, or the awareness date was edited), signing is refused with `409 FLOOR_CHANGED`: "The rules for this event changed (US-floor-1 → US-floor-2): save the answers again to see the result." Answers are kept. This applies D6 (approved: signing on the old floor is refused) |
| Watch and triage provisional deadlines (not signed) | Computed live from the version at the awareness day. A **law change** does not move them (awareness is before the change). A **correction** moves them at the next read |
| Draft saved before B4 (no floor code) | Gets the floor code at its next save; never refused for having none |
| Signed before B4 | Floor code left empty; the screen says "Signed before the rule register" (R-D5 ⚑) |

**Awareness changes.** A corrected awareness date re-picks the version at the next save. A signed record keeps its own; changing it needs a re-sign with a reason (OD-4).

**Two markets.** Each market picks its own version by its own authority zone. A US change never touches EU/GB/IN/CA assessments.

### 4.3 Test cases (fixture register with a test-only US-floor-2 from 1 Mar 2027 and a correction)
| ID | Case | Expected |
|---|---|---|
| ED-1 | Awareness 28 Feb 2027 23:00 New York | US-floor-1 |
| ED-2 | Awareness 1 Mar 2027 00:00 New York | US-floor-2 |
| ED-3 | Awareness 1 Mar 2027 03:00 UTC (28 Feb in New York); organisation in Asia/Kolkata | US-floor-1 (the authority's day picks the version); the clock still counts by today's rule |
| ED-4 | A date-only awareness of 1 Mar 2027 | US-floor-2 |
| ED-5 | Signed under v1; v2 deployed | Record, columns and fingerprint unchanged byte for byte |
| ED-6 | Draft saved under v1; correction v3 (same period as v1) deployed; sign | `409 FLOOR_CHANGED`; re-save picks v3; sign succeeds with v3 |
| ED-7 | Draft awareness edited from 2 Mar to 27 Feb | Next save picks v1 |
| ED-8 | One complaint, US and EU assessments, US v2 only | EU unchanged; US by its own day |
| ED-9 | Report due date from a signed v1 conclusion; v2 shortens the period | Report due date unchanged |
| ED-10 | Triage provisional deadline, awareness before v2's date | Unchanged after v2 deploys |
| ED-11 | Same, after a correction v3 that shortens a tier | Moves to the earlier date at the next read |
| ED-12 | Register with overlapping versions, a gap, or `to` before `from` | Build test fails, naming the files |
| ED-13 | A future version (from 2027) before its date | Listed as "Scheduled"; never used for an awareness before its date |
| ED-14 | Awareness on 31 Mar 2027 (EU summer time starts 28 Mar) for an EU floor change on 1 Apr | EU-floor-1; Brussels day used |
| ED-15 | Routine path signs "not reportable" | Each market's row stores the floor in force at its awareness day, rules applied `routine-basis-1` |

---

## 5. Data model, migration and seeding

### 5.1 Where the register lives (R-D1)
**Versioned data files in the code, one file per rule version**, in `backend/app/rule_register/data/`. Not a database table.
- The files are the single source. They ship in a release, are reviewed as a code change, and work in unit tests without a database (the rule functions are called in many no-database tests today).
- Rows never change in production: there is no write path. "Who approved it" is recorded in the file and the CHANGELOG.
- Signed records name a version by its code (a string, as `question_set` does today), so no foreign key is needed.
- A database copy is added only if B4c's import/export or E4's impact queries need one.

**File format** (shortened; JSON):
```json
{
  "code": "US-floor-1", "rule": "US-floor", "version": 1,
  "kind": "REPORTABILITY_FLOOR", "market": "US", "held_as": "DATA",
  "title": "US medical device reporting: when a report is owed, which one, and by when",
  "plain": "Death or serious injury the device caused or contributed to, or a malfunction likely to harm if it recurred: report in 30 days, or 5 work days when remedial action is needed.",
  "source": [{"catalog": "CFR803_50", "clause": "21 CFR 803.50(a)(1)-(2)"}, {"catalog": "CFR803_53", "clause": "21 CFR 803.53"}],
  "effective_from": null, "effective_to": null, "law_in_force_from": "<the law's date, consultant to confirm>",
  "change": {"kind": "INITIAL", "reason": "Today's logic (0.10.81 onwards), moved to data"},
  "review": {"status": "STARTER", "note": "Starter, for your consultant to confirm."},
  "approval": {"approved_by": "<owner>", "approved_on": "2026-..", "built_by": "<builder>", "release": "0.10.9x"},
  "content": {
    "question_set": "US-starter-1", "questions": [ ... as markets.Question ... ],
    "report_types": {"US_30_DAY": {"label": "...", "days": 30, "basis": "CALENDAR"}, "US_5_WORK_DAY": { ... }},
    "precedence": ["US_5_WORK_DAY", "US_30_DAY"],
    "rules": [
      {"id": "F-US-1", "if": {"all": [{"any": ["US1", "US2A", "US2B", "US2C"]}, "US3"]}, "cite": "803.50(a)(1)"},
      {"id": "F-US-2", "if": {"all": ["US4", "US5"]}, "cite": "803.50(a)(2)"}
    ],
    "type_rows": [{"id": "T-US-1", "if": {"is_no": "US6"}, "type": "US_30_DAY"}, {"id": "T-US-2", "type": "US_5_WORK_DAY"}],
    "notes": [ {"if": ..., "text": "Question 6 is Unknown: until it is answered, ..."} ],
    "folding": [ {"if": ..., "fold": ["US3"], "why": "Not asked: no death and no serious injury"} ],
    "prefill": {"death": ["US1"], "malfunction": ["US4"], "injury_note": ["US2A", "US2B", "US2C"]},
    "counting": {"authority_zone": "America/New_York", "awareness_is_day_one": false},
    "provisional": {"THREAT": [5, "WORK", "5 work days (21 CFR 803.53)"], "FLAGGED": [30, "CALENDAR", "..."], "UNFLAGGED": [30, "CALENDAR", "..."], "remedial": [5, "WORK", "..."], "ruled_out": "remedial action is ruled out"}
  },
  "content_hash": "sha256 of the canonical content"
}
```
Code-held rules have a smaller file: `held_as: "CODE"`, `implementation` (module and function, for MDARIX staff only; not shown to customers), source, dates, approval, and for pinned ones a `code_hash` (step 7).

**The engine** (`rule_register/engine.py`, about 150 lines). Conditions are `"Q"` (a question, three-valued), `any`, `all`, `is_no`, `is_yes`, `is_unknown`, `maybe` (not No), and `ref` to another rule. Evaluation is today's Kleene logic (`markets.py:491-511`): suggestion Reportable if any rule applies, Pending if any could apply, else Not reportable; report type from the first matching type row; notes and folding in file order, first match wins (as `setdefault` today). The precedence list is what B4b will use to pick "the shorter report" when an organisation rule adds one.

### 5.2 Migration
**One migration: `tr27_trial_rule_register.py`, revision `tr27ruleregister`, `down_revision = "tr26challengeloop"`** (B5's head; DB-1 uses tr21–tr24, B7 tr25, B5 tr26). Step 0 checks there is exactly one head. On mvp-1.0 the forward merge adds a merge revision (md53–md65 pattern).

Three nullable columns on `complaint_market_assessments` (tenant-isolated already, FORCE RLS unchanged):
| Column | Type | Content |
|---|---|---|
| `floor_code` | `String(40)` | e.g. `US-floor-1`; set at every draft save and at signing; empty on rows signed before B4 (never backfilled) |
| `rules_applied` | `JSONB` | Rule IDs that applied or could apply, with their state, and the type row chosen; for the routine path `["routine-basis-1"]` |
| `date_calc` | `JSONB` | Awareness moment and its source, start day, days and basis, window or regulation, binding zone, counting rule code |

Downgrade drops the three columns. No data step. No other table changes: the register is files, and customer guide versions are untouched until B4b.

**Signed material** (`assessment_router.py:523-557`) gains `floor` (`code` and `content_hash`), `rules_applied` and `date_calc`, only when the switch is on. The signature meaning text is **unchanged** (R-D14 ⚑). The audit details of `COMPLAINT_MARKET_CONCLUSION_SIGNED` add `floor_code`. No new audit event: the register changes only through a release.

### 5.3 Seeding today's rules as version 1
- Step 3 writes the five floor files from today's constants and functions, and about 40 code-rule files with their existing version codes (never renaming a stored code: `US-starter-1`, `disposition-starter-1`, … keep their names; rules with no code get `<name>-starter-1`, for example `counting-starter-1`, `routine-basis-1`).
- Every source points to a catalog id in `backend/app/standards.py` (`CATALOG`: `CFR803_3`, `CFR803_50`, `CFR803_53`, `MDR_87`, `IVDR_82`, `UK_MDR`, `IN_MDR`, `CA_MDR` exist); any id still missing is added there and in `frontend/src/features/shared/standards.json` (an existing test keeps the two identical). The loader refuses an unknown id, where today `standards.known()` silently drops it.
- **Proof of no behaviour change: `tests/test_b4_equivalence.py`** (unit, no database). Every case runs through the old code path (kept, frozen, as `reportability/legacy_v1.py`) and through the engine on version 1, and the two results must be identical after `json.dumps(..., sort_keys=True)`:
  1. Every Yes/No/Unknown combination of every market's floor questions: US 3^8 = 6,561; India 6,561; Canada 729; EU/NI and GB 3^11 = 177,147 each. Compared: suggestion, report type, report type if reportable, notes, folded questions.
  2. Every Yes/No/Unknown/N.A./blank combination for Canada (5^6 = 15,625), and a fixed-seed 200,000 such combinations for the others.
  3. Every row of `docs/compliance/REGULATORY_DECISION_TABLES.md` (US, EU, GB, IN, CA, folding, deadline tables) and every MDARIX starter test row (`decision_guides/rules.py:490`).
  4. Question sets (`as_dict()`) and report types, per market, identical.
  5. Pre-fill and record notes for every record combination (death, malfunction, serious injury each True/False/None; three severities).
  6. Deadlines: a fixed-seed 100,000 awareness moments × markets × five organisation zones × 2/5/10/15/30 days × calendar and work days, plus every daylight-saving change in 2026–2028 ± 2 hours: identical latest day, end and zone.
  7. Triage provisional deadlines for every market × tier × remedial × answered × IVD.
  8. The existing targeted suites run with the switch on and off (step 12).
- `legacy_v1.py` stays as the oracle while version 1 is the only version of a market. When a market gets version 2, the oracle stays valid for version 1 only.

---

## 6. Screens, build steps, cuts and the switch

### 6.1 Screens (read-only)
**Recommendation: read-only for everyone. No editing screen in B4** (R-D2). MDARIX changes rules by a new version file in a release: one person writes it, the owner (or a named regulatory approver) approves it, both recorded in the file. Customers never edit the floor; B4b gives them their own layer.

1. **Decision trees › Rules** (new tab on the new navigation; classic: Complaints › Decision guides › Rules). Open to every signed-in member, like the guides.
   - Hero header: "49 rules · 5 markets · 9 held as data · all starter, for your consultant to confirm". Flat table below.
   - Columns: Rule (title and plain line), Kind (Reportability floor, Deadline counting, Triage, Routine path, Report form, Investigation, Analytics), Market, Version (in words, with the code), Source (catalog chips and clause), In force (from – to, or "from the start"; Scheduled; Retired), Approved by and on, Held as (Data / MDARIX code), Fingerprint (short).
   - Filters: market, kind, and **"As at" date**: shows which version applied on that day (for auditors).
   - Detail drawer: for data rules, the logic as readable "IF … THEN …" lines with each condition's question text; the report types and periods; how days are counted; the version history of that rule.
2. **"Rules used" panel** on a market conclusion (Decision trees › Answer and the watch's assessment drawer), three lines kept apart (C4):
   - **At the event:** the floor in force on the awareness day (code, date), the rules that applied.
   - **Today:** the floor in force now; "Same" or "Differs: not applied to this event (awareness before dd mmm)".
   - **Decided:** the signed conclusion, its date calculation and its fingerprint. "Signed before the rule register" for old rows.

### 6.2 Build steps
| # | Step | Hours | Targeted tests |
|---|---|---|---|
| 0 | Branch from B5's tip; one Alembic head `tr26challengeloop`; re-check this spec's lines on that tip; CHANGELOG section; add RR-01..RR-20 to `scenario-register.md` (covering DT-06, 07, 20, 21, 33, 34, 37 and RG-11, RG-12) | 2 | `alembic heads` = 1 |
| 1 | Register files, loader (once per process, cached), checks (schema, unique codes, no overlap or gap, catalog ids exist, content hash), `pick(rule, day)` | 6 | `test_rule_register_unit.py` |
| 2 | Engine: conditions, Kleene logic, rules, type rows, notes, folding, pre-fill | 8 | `test_rule_engine_unit.py`: truth tables per operator; first-match notes and folding |
| 3 | Version 1 files: five floors from today's code; about 40 code-rule files; catalog ids checked | 12 | Loader checks pass; `test_standards_unit.py` |
| 4 | Equivalence suite (5.3) | 8 | `test_b4_equivalence.py` |
| 5 | Wire in: `markets.evaluate`, `not_asked`, `suggestions`, `record_notes`, `QUESTION_SETS`, `REPORT_TYPES`, `deadlines.count` and `intake/rules.provisional_deadlines` read the floor picked by the awareness day (current floor where no awareness: guide test matrix, `earliest_report`); old code kept as `legacy_v1.py` behind the switch | 8 | Existing: `test_regulatory_decision_tables.py`, `test_market_assessment_rules.py`, `test_legal_deadlines.py`, `test_intake_rules.py`, `test_decision_guides_api.py` |
| 6 | Effective dating: floor code at every save, `409 FLOOR_CHANGED` at signing, migration tr27, signed material and audit details, routine path stores its floor | 10 | `test_b4_effective_dating.py` (DB, fixture register): ED-1..ED-15; tr27 upgrade, downgrade, upgrade; `test_rls_coverage.py` |
| 7 | Version pins: data content hash; `us_emdr.csv` hash; code hash (syntax tree without comments and docstrings) of the pinned regulatory functions (#12, #17, #18, #20, #21, #27) | 3 | `test_rule_pins_unit.py` (DT-33): change one byte, the test names the file |
| 8 | Read-only API: `GET /api/v1/rule-register` (filters: market, kind, as-at day), `GET /api/v1/rule-register/{code}`; no write route | 4 | `test_b4_register_api.py`: every member reads; tenant data never in the response; unknown code 404; switch off 404 |
| 9 | Screens: Rules tab, detail drawer, "Rules used" panel | 10 | `ruleRegister.test.tsx`; `tsc --noEmit` |
| 10 | Switch `MDARIX_RULE_REGISTER` (6.4) | 3 | Off: legacy path, routes 404, tab hidden, columns stay empty; on/off/on keeps drafts signable |
| 11 | Docs: decision tables §7 points to the register codes; environment variable doc; CHANGELOG | 2 | Decision-table doc test still passes |
| 12 | Targeted suites with the switch on and off (above, plus `test_market_assessment_api.py`, `test_release_c4_0_10_76.py`, `test_release_0_10_83.py`, `test_sample_story_days.py`, `test_complaint_disposition_api.py`, `test_authority_reports_api.py`); ruff; one independent read-only review; fixes | 6 | All green both ways |
| | **Core total** | **82** | |
| 13 | *Optional, needs R-D10:* FG-1: the watch shows the legal clock beside an organisation window that is longer, and saving such a window warns (never refuses existing windows) | 4 | `test_b4_window_floor.py` |
| 14 | *Optional:* re-check list: a staff script that re-runs the signed conclusions on open complaints under a candidate floor version and lists the differences (no change made) | 4 | `test_b4_recheck_script.py` |
| 15 | *Optional:* CSV export of the register "as at" a date | 2 | API test |
| | **Total with options** | **92** | |

**Parts.** Steps 0–7 and 10–12 (about 66 h) can ship alone: the engine, the register files, effective dating, the switch. Steps 8–9 (14 h) add the screens. B9 needs only the first part.

### 6.3 What can be cut (in this order)
1. Step 15 (CSV export). 2. Step 14 (re-check script: moves to B4c/E4). 3. Step 13 (FG-1: stays a known gap). 4. The classic-navigation entry. 5. The "Today: differs" line on the panel. 6. Code hashes in step 7 (keep the data and CSV hashes).

**Never cut:** the equivalence suite, the switch, the floor picked by awareness with the signing refusal, the migration and the signed material, the data content hash.

### 6.4 On/off switch (the `feature_set.py` pattern, as B7's `MDARIX_ROUTINE_PATH`)
- `MDARIX_RULE_REGISTER`: on unless `off`, read on every call (`feature_set.py`).
- **Off:** every rule function uses `legacy_v1.py` (today's code); `serves_path` returns 404 for `/api/v1/rule-register`; the session flag hides the Rules tab and the panel; `floor_code`, `rules_applied`, `date_calc` are not written and the signing check is skipped.
- **On:** the engine and register. Default **on**, because the equivalence suite proves identical outcomes; off is the way back without a rollback (R-D9).

---

## 7. Owner decisions

⚑ = touches regulatory interpretation or signed records: **needs your explicit answer before the build starts.**

| # | Decision | Recommendation (safe) |
|---|---|---|
| R-D1 | Where the register lives | Versioned data files in the code, one per rule version; no database table until B4c needs one. |
| R-D2 | Who may change rules, and where | No editing in the app. MDARIX changes ship as a new version file in a release, written by one person and approved by the owner or a named regulatory approver, both recorded in the file. |
| R-D3 ⚑ | Which date picks the floor version | The awareness day in the authority's time zone (the organisation's for Canada), as D5 approved; form editions by the day the report is sent for approval. |
| R-D4 ⚑ | Law change vs MDARIX correction | A law change applies to events aware on or after its date; a correction replaces the corrected version for the same period at once for unsigned work; signed records never change. |
| R-D5 ⚑ | Conclusions signed before B4 | Leave their floor code empty, never backfill; show "Signed before the rule register". |
| R-D6 ⚑ | A draft whose floor changed before signing | Refuse signing until the answers are saved again (`409 FLOOR_CHANGED`), keeping the answers (applies approved D6). |
| R-D7 ⚑ | Effective-from of version 1 | "From the start", so every past complaint keeps today's outcome; show the law's own date as information. |
| R-D8 | What becomes data in B4 | The five floors (questions, logic, report types and periods, counting zones and day 1, triage tiers, pre-fill) and the registered eMDR rule book; the other 40 rules stay code, listed, the regulatory ones pinned. |
| R-D9 | Switch default | On (outcomes proven identical); off returns to today's code without a rollback. |
| R-D10 ⚑ | FG-1: organisation window longer than the law on the watch | Build optional step 13: show the legal clock beside it and warn on save; never refuse or change saved windows. |
| R-D11 ⚑ | FG-2 India period, FG-3 routine basis, FG-4 OD-1 and OD-3 | Carry all unchanged into version 1 (identical outcomes), marked starter; fix each in B9 (India period as `IN-floor-2`) or by its own decision after the consultant's review. |
| R-D12 | Signer training for floor versions | No new training document for version 1 (same content as today's question set); whether a later version needs re-acknowledgement is decided in B4c/E4. |
| R-D13 | Where the register shows | Decision trees › Rules, read-only for every signed-in member, every rule shown with its starter mark. |
| R-D14 ⚑ | What new signatures cover | Add the floor code, its content hash, the rules applied and the date calculation to the signed material; keep the signature meaning text unchanged. |

**Needing your explicit answer:** R-D3, R-D4, R-D5, R-D6, R-D7, R-D10, R-D11, R-D14.

---

## 8. What I did not check
- B7's and B5's branches were not read; lines in those files may have moved, and B5's `tr26challengeloop` head is taken from its spec. Step 0 re-checks both.
- The equivalence counts and run time were not measured; the EU/GB exhaustive runs (177,147 each) may need the `slow` mark if they exceed a minute.
- No legal source was re-read: the law dates in the files (`law_in_force_from`) and every citation stay "starter, for your consultant to confirm".
- No database was queried; the number of existing drafts without a floor code is unknown (harmless: they get one at the next save).

## Owner approval (11 Nov 2026)
"approve B4 spec": all fourteen recommendations R-D1 to R-D14 accepted, including the flagged ones R-D3, R-D4, R-D5, R-D6, R-D7, R-D10 (with the optional FG-1 step 13), R-D11 and R-D14. Build starts automatically once B5 is complete. Every legal citation and law date stays "starter, for your consultant to confirm".

## Build status (run 1, 11 Nov 2026)

Branch `feat/b4-rule-register` in worktree `trial-093`, from `feat/b5-challenge-loop` at `3727e142` (B5 tip `8b3a0da9` plus the B7 guide-path fix merge). Local commits only; nothing pushed.

**B4 is not complete.** Core server work is done: steps 0 to 8, 10 (server), 11 and 12. **Left:** step 9 (screens: Decision trees › Rules tab, detail drawer, "Rules used" panel, `ruleRegister.test.tsx`, `tsc --noEmit`), the screen part of step 10 (hiding the tab and panel when the session's `rule_register` is false), step 12's independent read-only review, and optional step 13 (FG-1).

| Step | State | Commit |
|---|---|---|
| 0 | Done: one head `tr26challengeloop`; CHANGELOG `[0.10.99]`; RR-01..RR-20 in `scenario-register.md` | `19c0d837` |
| 1 | Done: register, loader checks, `pick`, floor by awareness day | `eba4d3fb` |
| 2 | Done: engine tests | `4169fe66` |
| 3 | Done: 5 floor files + 41 code-rule files (existing codes kept); eMDR CSV registered by file hash; no new catalog ids needed | `d9527092` |
| 4 | Done: equivalence suite; `legacy_v1.py` frozen | `1c34399d` |
| 5 | Done: wiring behind `MDARIX_RULE_REGISTER` | `0a19011a` |
| 6 | Done: `tr27ruleregister`, floor on save/sign, `409 FLOOR_CHANGED`, signed material, audit, routine path | `cc2c43ee` |
| 7 | Done: pins (6 functions by syntax-tree hash; eMDR CSV hash) | `eb787d10` |
| 8 | Done: read-only API | `7d9cb005` |
| 9 | **Not started** | |
| 10 | Server part done (switch, 404, session flag); screen part waits on step 9 | `72068d39` |
| 11 | Done: decision tables §7 (VR-14..18), environment reference, CHANGELOG | `0392222b` |
| 12 | Targeted suites run both ways; independent review **not done** | `15c8f6df` |
| 13 | Not started (optional, FG-1) | |

**Equivalence (the core proof).** `tests/test_b4_equivalence.py`: 25 tests, all passing. Covered: every Yes/No/Unknown combination (US and India 6,561 each; Canada 729; EU/NI and GB 177,147 each), every five-valued Canada combination (15,625), 200,000 fixed-seed five-valued combinations for each other market, every MDARIX starter test row, the question sets and report types, pre-fill and record notes, 100,000 deadlines plus every daylight-saving change 2026–2028, and triage provisional deadlines. The steps 1–4 part (16 tests, including all `slow` runs) took **73 s**. The slow 100,000-deadline run took 8 s. Without `slow`, the suite takes about 3 s.

**Migration.** `tr27ruleregister`: upgrade, downgrade and upgrade checked on `mdarix_b2_test`, which is now at `tr27ruleregister`.

**Pre-existing failures, also failing on B5's tip:**
- `test_standards_unit.py::test_signed_statements_and_meanings_name_documents_never_codes`: expects the "disposition rules, MDARIX starter, version 1" statement, but B7 moved to `disposition-starter-2`.
- `test_release_0_10_97.py::test_a_trial_made_before_0_10_97_gets_rt03_s_reply_once`: `MultipleResultsFound`.

The decision-table test VR-7 was fixed in step 11 by changing the document to `disposition-starter-2`. MDARIX_CHALLENGE and MDARIX_CLOSED_LOOP were added to the environment reference.

**Notes for the next run.**
- The code pins hash Python's syntax tree (`ast.dump`). Re-pin after a Python minor-version upgrade (marked `shortcut:`).
- `deadlines.end_of(day, …)` called without an awareness uses today's floor for the zone. This is the same with version 1 only, and needs attention before a version 2 changes a zone.
- Signed material gains `floor`, `rules_applied` and `date_calc` only while the switch is on. The signature meaning text is unchanged.

## Build status (run 2, 11 Nov 2026)

**B4 is complete** (steps 0 to 13; the optional steps 14 and 15 are not built; the classic-navigation entry for Rules is cut, as section 6.3 item 4 allows). Branch `feat/b4-rule-register` in `trial-093`, local commits only, nothing pushed.

| Item | State | Commit |
|---|---|---|
| B7 fix: signer statement test | Test was out of date (current document is `disposition-starter-2`; stored statements of version-1 records unchanged) | `95c32412` (B7) |
| B7 fix: RT-03 refresh `MultipleResultsFound` | Cause was the test's own lookup (no tenant filter; the test connection is not held to RLS). Product code already tenant-scoped and idempotent; no product change | `ff8a3dbd` (B7) |
| Merges forward | B7 into B5 `9743a818`; B5 into B4 `a94ec0c6` (both `--no-ff`) | |
| 9 Screens | Done: Decision trees › Rules (read-only mode, hero header, flat table, market/kind/As-at filters, detail drawer); "Rules used" panel on the answer rail and the watch's assessment drawer | `1249a290` |
| 10 Switch, screen part | Done: tab and panel hidden while the session's `rule_register` is false | `1249a290` |
| 12 Independent review | Done: one fresh reviewer (two passes). Fixes below | `f766247d`, `13e63495` |
| 13 FG-1 (R-D10) | Done: `longer_than_law` warning on the settings GET/PUT (never refused); the watch shows the latest date the law allows beside a longer window; off with the register | `442096b2`, `13e63495` |
| CHANGELOG 0.10.99 | Done | `650afdc4`, `5191ccca` |

**Review findings fixed:** (1) a draft saved with the register on and signed with it off kept stale floor columns: now cleared. (2) Live paths used today's floor: the watch clock, triage's earliest report and signed clocks, open-deadline and sample refreshes, pre-fill and record notes now use the floor at awareness (or the signed floor). (3) `floor_day` takes the zone from today's version: the loader now refuses floor versions with different authority zones (shortcut noted in code). (5) The routine path stored today's floor without awareness: now none, and it records `date_calc`. Follow-up: "At the event" showed "no rule applies" after signing (now the signed rules); FG-1 wording said "the law's deadline" for the longest period (now "latest date the law allows"); drawer counting text misstated F7 (now the floor's own words); FG-1 now off with the register.

**Review findings not fixed (with reasons):** (4) the deadline and triage equivalence checks compare switch on vs off, not against frozen old code: the reviewer checked the off paths by hand and found them identical to the old constants; freezing `count`/`provisional_deadlines` into `legacy_v1` is left for the test release. `markets.disagreement` still reads today's question set (its serious flags only; identical while version 1 is the only version).

**Next before a version 2 of any floor:** `deadlines.end_of` without `aware` (authority reports) and `disagreement` read today's floor; harmless while zones cannot change between versions (now enforced) and version 1 is the only version.

## Approval record

| Field | Value |
|---|---|
| Approved | 11 Nov 2026 |
| Approver | Srinivas Telikicherla, Founder & CEO, QA/RA (owner) |
| Approval words, as recorded | "approve B4 spec" |
| Where recorded | section "Owner approval (11 Nov 2026)" |
| Planning copy | `MDARIX-planning/b4-rule-register/spec.md` (reference only) |
| Form of approval | The owner's written reply, recorded in the spec on the day; not an electronic or wet signature. This section was added on 12 Nov 2026 (owner decision O29); the approved text above is otherwise unchanged, except that a DRAFT status line now reads APPROVED |
