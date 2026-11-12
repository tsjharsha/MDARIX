# RCA tools: 5 Whys, fishbone, Pareto, context, work queue, dossier, harm-rate check

Version 1, 12 Nov 2026. **DRAFT for the owner.** Nothing here is built. The RCA tools item sits in **Lane 1 after B6a and B6b** (complete plan, two lanes, approved 11 Nov). It starts when the owner approves this spec and its ⚑ decisions. Decisions marked **⚑** touch signed records, the risk file or what a customer may read as a finding. Each ⚑ says what the build does **if no answer arrives** (always the safer path).

- **Scope (owner-approved 11 Nov):** complete plan step 5.5 (`complete-plan/MDARIX-complete-plan.md:90`) and v2.1 amendment B (`:174`); best-practice plan P3, P4, P8 (`post-whif-best-practices/plan.md:43,44,48`), A2 and A3 (complete plan `:90`); core methods 5 Whys, fishbone (people, process, method, material, machine, environment, plus software for SaMD), Pareto of confirmed causes, FMEA links to the product risk file.
- **Code read** (read-only, `git show` / `git grep` / `git ls-tree` only): branch `feat/b9b-other-countries` at `3dc55c0b`. Every `file:line` is on that branch, under `backend/app/` unless shown. B6a and B6b change some files on their own branches; step 0 re-checks every line on the joined line.
- **AI stays off.** Every RCA tool works with no AI call. Later, under AI-R's existing feature key `case_analysis` (`ai-ready/spec.md:94`), AI may *suggest* a next "why", fishbone causes or similar cases; a person always decides. No new AI key.
- **Rules in force:** signed records are never rewritten; a hypothesis is never silently promoted to a root cause; G-2 flat operational screens; no competitor names; no prices; v2.1 Definition of done (`complete-plan:169`).
- **Not in RCA tools:** components and BOM "as of the event date" from PLM (A4, step 6.10); E3 management review (reuses the Pareto, step 6.4); E6 predictive risk (Lane 2, builds on P3); P5/E9 outside data; P7 periodic-report tables; units sold per market (January 2027 sales-data item, `complete-plan:209`).

---

## 1. Purpose, in plain words

**MDARIX structures the investigation; a person finds and signs the cause.** The investigator gets the standard RCA methods on the case they already work in, the context they would otherwise hunt for, and one dossier a reviewer can return, approve and export. Nothing is decided by MDARIX.

| # | Who | Does what | Signed? | Audited |
|---|---|---|---|---|
| 1 | Investigator | Opens the case from a **work queue** ordered by risk, deadline and missing evidence (B). Each row says why it is where it is. | No | No (a read) |
| 2 | Investigator | Applies a **template** (B): it adds evidence requests and open questions; it never adds a cause. | No | `RCA_TEMPLATE_APPLIED` |
| 3 | Investigator | Reads the **context** (B): similar past investigations and their signed causes, the lot's other complaints and shipments, the device's service history. | No | No |
| 4 | Investigator | Reads the **version at the event date** and the intelligence overview (C): facts with sources, hypotheses with evidence for and against, contradictions, unknowns. | No | No |
| 5 | Investigator | Fills a **fishbone** (A): each possible cause is a hypothesis with a category; rules one out with a reason. Builds a **5 Whys** (A): each why cites evidence or stays "unknown". | No | Existing intelligence history (`db/models/intelligence.py:1-7`) |
| 6 | Brief author | Writes the brief; it now reads as the **12-section dossier** (D). Proposes the root cause by naming hypotheses. | No | Existing |
| 7 | Quality reviewer (≠ author) | Reviews; comments per section; returns for rework or approves (existing lifecycle, D). | Review action (exists) | Existing |
| 8 | Decision maker (≠ author) | Signs the decision and, **by ticking them**, the hypotheses accepted as root cause and their category (A). Only this makes a cause "confirmed". | **Yes** (exists) | Existing, plus the new fields in the signed snapshot |
| 9 | Anyone with access | Opens the **Pareto** of confirmed causes (A) and exports the **dossier** (D). | No | Export audited (existing document pattern) |
| 10 | Risk reviewer | Sees **observed vs estimated harm rate** per risk on the risk-file page (E). Decides any risk-file update. | Existing risk review | Existing |

---

## 2. What exists today (gap table)

### 2.1 Root cause, decision, brief, review

| # | Item | Exists today | Gap | Part |
|---|---|---|---|---|
| G1 | Root-cause attribution | Four codes DEVICE_RELATED, USE_RELATED, ENVIRONMENT_RELATED, UNDETERMINED (`db/models/complaint_disposition.py:43`). On the signed decision (`db/models/foundation.py:640-643`), required for new signatures, bound into the snapshot (`human_decision/router.py:599-603, :726`). On service-level dispositions (`db/models/complaint_disposition.py:59-61, :87`) | No cause **category** (fishbone), no link from the decision to the hypotheses it accepts. The investigation report says "under your own coding (until MDARIX codes it)" (`qms_documents/templates.py:101-116`) | A |
| G2 | Root-cause text | The decision `rationale` is printed as "Root cause as recorded in decision" (`qms_documents/content.py:386-392`) | Free text only; not countable | A |
| G3 | Hypotheses | Table with origin, `human_status`, draft rule (`foundation.py:477-501`); statuses PROPOSED … CONTRADICTED, RETIRED, **no root-cause or confirmed state** (`db/models/intelligence.py:21-29`; `case_intelligence/rules.py:1-7`); evidence links support/contradict (`foundation.py:1192`); routes `case_intelligence/router.py:431-737` | No category; no link to a failure mode (FMEA) | A |
| G4 | Leading hypothesis in the brief | "The hypothesis a person judged strongly (else partially) supported … never chosen from the AI's own status" (`decision_brief/compose.py:630-633`, `decision_brief/rules.py:407`) | Fine as is. RCA keeps it a proposal, never a cause | — |
| G5 | Failure chains | Human chains with nodes and edges, link states, adopt from AI (`foundation.py:529-547, 1218-1273`; `case_intelligence/router.py:1308-1650`); `node_type` has no check constraint; screen `caseIntelligence/FailureChain.tsx` | No 5 Whys form | A |
| G6 | Pareto | Disposition trend groups complaints by product, problem, lot, use environment, user type or attribution (`complaint_disposition/service.py:579-671`, route `complaint_disposition/router.py:339`); called by `frontend/src/features/workspace/disposition.ts`; **no backend test calls it** (git grep of `dispositions/trend` in `tests/`: none) | Service-level resolutions only; no confirmed investigation causes; no sort by size with cumulative share | A |
| G7 | Decision Brief lifecycle | Versions DRAFT → READY_FOR_REVIEW → UNDER_REVIEW → RETURNED / APPROVED_FOR_DECISION / SUPERSEDED; frozen with SHA-256 once submitted (`db/models/reviews.py:1-12, 66, 132-170`); review actions with comment, never updated (`reviews.py:172-195`); return for evidence, analysis, risk or regulatory review, escalate (`decision_brief/rules.py:49-76`); comment 10-5000 chars except accept (`rules.py:119-124`); segregation of duties (`rules.py:132`); routes `decision_brief/router.py:344-1162` | Comments are per action, not per section; no 12-section layout; no export | D |
| G8 | Brief content | investigation, product, signals, scope, established facts, evidence inventory, supporting and contradicting evidence, leading and alternative hypotheses, unknowns, failure chains, risk and regulatory reviews, AI assistance, readiness, context (`decision_brief/compose.py:618-654`); B5 challenge and Sources (`compose.py:655-660`, `case_challenge/brief.py:177`) | No chronology; product section lists versions only (`compose.py:62-81`); `context.as_of` is the composition time, not the event date (`compose.py:645-646`); no contradictions list, no regulatory considerations from market assessments and reports, no review history, no rule/configuration provenance | D, C |
| G9 | Signed decision snapshot | Holds brief id and hash, content, narrative, evidence-set hash, reviews, outcome, attribution (`human_decision/router.py:705-728`); supersede path (`human_decision/rules.py:197-198, 342`) | New fields must be bound the same way | A |
| G10 | Document export | Ready-to-use documents with data sections and person-written judgements, PDF/DOCX, signed PDF frozen (`qms_documents/router.py:13, 265-366, 409-425`); INVESTIGATION_REPORT template (`qms_documents/templates.py:101-116`, content `qms_documents/content.py:250-445`) | No dossier document | D |

### 2.2 Risk file, lots, service, signals, product version

| # | Item | Exists today | Gap | Part |
|---|---|---|---|---|
| G11 | Risk register | Risks, failure modes, controls, requirements imported from the QMS; FailureMode CAN_LEAD_TO Risk as relationship rows (`risk/service.py:1-12`); `risks` has description and status only (`foundation.py:411-426`); hazard, harm, severity, probability "not captured" (`risk/service.py:8-11, 39, 233-238`); risks import template `trial/business_imports.py:116` | **No estimated probability anywhere.** P3 cannot compare without it | E |
| G12 | Risk register screen | Route `/api/v1/risk` is **parked under the MVP** (`feature_set.py:56-57`) and a free trial always gets the MVP interface (`feature_set.py:11-12`) | P3 must live on a served page | E |
| G13 | Risk file per product (E10, partly built) | States NOT_REVIEWED, REASSESSMENT_OVERDUE/OPEN, NO_RISK_REGISTER, REVIEWED, QUIET from complaints, signals, trend rises and risk reviews (`post_market/risk_file.py:1-23`); routes `post_market/router.py:21,30`; screen tested (`frontend/src/features/workspace/riskFile.test.tsx:60`); `tests/test_risk_file_api.py` | No rate, no estimate | E |
| G14 | Denominators | Lot units released (`foundation.py:245-246`); shipments per consignee (`db/models/lot_impact.py:1-9, 48`); B5 ladder "shipped, else released, else counts only, never a partial denominator" (`closed_loop/rules.py:9-12, 75-91`); exact tests (`closed_loop/rules.py:93-112`) | **Units sold per market and period not held** (January sales-data item, `complete-plan:209`) | E |
| G15 | Harm per complaint | Signed market assessment holds `harm_level`, `harm_code` (`db/models/market_assessment.py:98-100`); complaint flags serious injury, death, malfunction (`foundation.py:315-317`) | No risk ↔ code mapping | E |
| G16 | Lot impact | Lots sharing a suspect factor, units released and shipped, complaints per 1,000 units, signed fingerprint (`lot_impact/service.py:1-15`; routes `lot_impact/router.py:185-442`) | Fine; P4 reuses it | B |
| G17 | B5 facts | Same-problem complaints outside the scope, lots with units and genealogy, changes, supplier pattern (`case_challenge/facts.py:1-11`); draft rules H-0..H-5, questions C-1..C-9, "Not a finding" (`case_challenge/rules.py:1-43`) | No similar **past investigations** with their causes | B |
| G18 | Service history | No service-history table. Pieces: complaint `serial_number`, `service_reference`, `service_status` (`foundation.py:310, 322-324`); service record on a service-level disposition (`complaint_disposition.py:59`; checks `complaint_disposition/rules.py:177-236`); intake kind SERVICE_RECORD (`db/models/intake.py:62`) | Not gathered per device | B |
| G19 | Investigator queue | "My open cases", most urgent first by priority then due date (`case_workflow/router.py:41, 92-134`); `frontend/src/features/workspace/caseWorkflow.ts:368`; evidence, request and unknown counts per case (`case_workflow/readiness.py:430-487`) | Own cases only; no reporting deadline; no harm; no "why here" | B |
| G20 | Templates | None (git grep `investigation_template`, `checklist` in investigations: none) | New | B |
| G21 | Version at a date | `Product360Service.select_version`: the latest version released on or before `as_of` (`product360/service.py:353-362`); route `/api/v1/products/{id}/product-360?as_of&mode` (`main.py:751-767`); version story route `stage3_router.py:251` (prefix `/api/v1`, `stage3_router.py:21`), screen `frontend/src/features/investigator/ProductVersionStory.tsx:13` | Not anchored to the complaint's event date; the caller must pass a date | C |
| G22 | Case intelligence screens | Hypotheses, Contradictions, Unknowns, FailureChain, Challenge, Observations, History (`frontend/src/features/workspace/sections/caseIntelligence/`) | Spread over tabs; no single overview with sources | C |
| G23 | R1 analysis panel on the case page | `InvestigationWorkspacePanel` under "The analysis workspace and Ask MDARIX" (`frontend/src/features/workspace/sections/CaseSections.tsx:220-232`). Its rules fallback uses **demo-tuned keywords** ("shutdown", "novacap", "rev b", "comp-pwr": `investigator/provider.py:219, 267-274`) on real tenant data | A customer can read keyword output as analysis | C ⚑ |
| G24 | Recurring service-level pattern | Starter threshold rule (`complaint_disposition/service.py:522`, text `:668-670`) | Fine | — |

### 2.3 The R1 investigation code (P8 audit, short)

All of it reads the tenant's real tables; RLS is forced on every table with `tenant_id` (`infrastructure/database/migrations/versions/ab44_database_hardening.py:47-57`). Routes are mounted and **not** switch-gated, except counterfactuals (parked under MVP, `feature_set.py:59-61`).

| Folder | Holds | AI? | Storage | Wired / tested | Reuse for RCA |
|---|---|---|---|---|---|
| `hypothesis_engine/` | Competing hypotheses with supporting, contradicting, contextual evidence, unknowns, falsification (`hypothesis_engine/schemas.py:40`); validator rejects PROVEN/ROOT_CAUSE and causal wording (`hypothesis_engine/validator.py:4-9`) | Rules fallback when no model (`hypothesis_engine/model_engine.py:66-69`) | `ai_executions` + copies into `hypotheses`, `hypothesis_evidence`, `unknowns` (`hypothesis_engine/service.py:212, 261-271`); reviewed rows kept on regeneration (`:224-249`) | `investigations/router.py:127-161`; ~9 test files | **Validator as a guard** on every RCA text that claims a cause; the schema shape |
| `unknowns/` | Unknowns radar, 17 categories (`unknowns/schemas.py:8`) | Rules only | `ai_executions` | `unknowns_failure_chain_router.py:46,68` | With work: crude keyword matching |
| `challenger/` | 16 challenge types incl. VERSION_MISMATCH, CONTRADICTORY_EVIDENCE (`challenger/schemas.py:8`) | Rules fallback | `ai_executions` | `challenger_router.py:39,103`; `MDARIX_CHALLENGE` does not gate `/challenges` (`feature_set.py:88-89`) | With work; B5 C-rules already cover the deterministic part |
| `failure_chain/` | Fixed 2-link template per hypothesis (`failure_chain/engine.py:19-49`) | Rules | `ai_executions` | `unknowns_failure_chain_router.py:85,149` | **Not reusable** (template text). The human chain *tables* are reused (G5) |
| `counterfactual/` | Fixed text (`counterfactual/service.py:81-141`) | Rules | `ai_executions`, `scenarios` | Parked under MVP | **Not reusable** |
| `evidence/` | Chunker, extractor, entity links, grounding (`evidence/services/evidence_service.py:63-136`) | Rules fallback | `evidence_chunks`, `evidence_observations`, `evidence_entity_links` | `evidence/router.py:13` | As-is for evidence provenance |
| `graph/` | Live graph, 14 node and 18 relationship types; "connectivity is not causality" (`graph/service.py:15-50, 253`); falls back to a synthetic tenant when none is given (`graph/service.py:12, 95-100`) | SQL only | none | Routes `main.py:603-680`; **no screen calls them** | Not now |
| `trust_engine/` | Checks grounding, restricted claims, certainty wording (`trust_engine/auto.py:1-24, 196`) | Checks AI output, calls none | `assurance_results`, `assurance_checks` | `trust_router.py:22-49` | As-is when AI is on later |
| `investigation_workspace/` | One bundle per case incl. evidence filtered by `as_of` (`investigation_workspace/service.py:85-97, 269-272`) | Rules | read-only | `investigations/router.py:51` | With work: anchor to event date |
| `investigator/` | Observations, contradictions, missing info, possible explanations (`investigator/service.py:75-88`) | Rules fallback | `ai_executions` | `investigations/router.py:77-162` | **Not reusable**: keyword rules are demo text (G23) |
| `ask_mdarix/` | Question interpreter with event/known "as of" modes (`ask_mdarix/interpreter.py:98-136`) | Rules | `investigation_sessions` | `POST /api/v1/ask` mounted; the date is only written to the audit (`backend/app/ask_router.py:95-104`), retrieval has no date field (`ask_mdarix/lifecycle_retrieval.py:30-39`) | Not used by RCA. Finding for the P8 audit, not fixed here |

**Reusable as-is:** case intelligence (hypotheses with evidence links, contradictions `case_intelligence/router.py:797`, unknowns, chains, history), evidence inventory and provenance (`evidence_workflow/inventory.py:248-624`), the brief lifecycle, Product 360 `select_version`, the B5 denominator ladder and exact tests, lot impact, the document export, `HypothesisValidator`, RLS everywhere. **Not reusable:** the R1 keyword rules, the failure-chain template, the counterfactual engine, the hard-coded validation summaries (`hypothesis_engine/service.py:92-97`, `challenger/engine.py:39-46`, `failure_chain/engine.py:101-108`).

---

## 3. Part A: 5 Whys, fishbone, confirmed causes, Pareto

### 3.1 5 Whys (no new table)
- A 5 Whys is a failure chain with `method = FIVE_WHYS` (new column, default `CHAIN`). Node 1 is the problem; each next node answers "why?". Two to seven whys.
- Each link keeps today's states (SUPPORTED … CONTRADICTED, UNKNOWN) and an optional evidence item (`foundation.py:1238-1273`). A why with no evidence is shown "Unknown: what would show it?" and creates an open question on request.
- The last why is **not** a root cause. It can be linked to a hypothesis ("this why is hypothesis HYP-x"). Nothing more.

### 3.2 Fishbone (a view of the case's hypotheses)
- Categories: People, Process, Method, Material, Machine, Environment, Software (shown only when the product is software or SaMD, or a person adds it). RCA-D3 asks about Measurement and Design.
- Each possible cause **is a hypothesis** with a new `cause_category`. Adding one is a one-line quick add (status PROPOSED, origin `human`). So every cause gets evidence for and against, unknowns, history and the brief, as today.
- Ruling out = today's CONTRADICTED or RETIRED with a reason (`intelligence.py:21-29`). Ruled-out causes stay visible, struck through, with the reason. Auditors ask what was considered.
- **FMEA link:** a cause may name a failure mode of the register (new `failure_mode_id`). The screen then shows the risks that failure mode can lead to (`risk/service.py:4-6`). A cause named in a signed decision with **no** failure mode shows "Not in your FMEA: consider a risk-file update" (a prompt to a person, never a change).
- G-2: on screen a flat grid, one column per category. No drawn diagram on screen. The PDF may draw one (optional, cut first).

### 3.3 A confirmed cause comes only from a signed decision
- At signing, the decision maker **ticks** the hypotheses they accept as the root cause (zero or more) and picks the category, or "Not determined" with a reason. Both go into the signed snapshot next to the attribution (`human_decision/router.py:726` pattern) and into two new decision columns.
- The brief author may *propose* them in the narrative; the proposal is shown as a proposal. Nothing is pre-ticked.
- A hypothesis row never changes status because of this. Screens derive "Named as root cause in decision DEC-x, signed by …" from the decision.
- Older signed decisions are never touched: they show "Not categorised". Re-categorising means a superseding decision (existing path). RCA-D1, RCA-D2.

### 3.4 Pareto of confirmed causes
- Unit: complaints. Each complaint counts once, under its **current** confirmed cause: the latest signed, not superseded decision of an investigation whose scope holds it; else its signed service-level disposition's attribution (`complaint_disposition/service.py:66`). Complaints with neither are one bar, "No confirmed cause yet", always shown.
- Group by cause category (default), attribution, product, version or problem code; period and product filters. Bars largest first, cumulative share line, the 80% mark. Counts only; never a rate.
- One service (`rca/pareto.py`), callable by E3 later (`complete-plan:112`). Each bar links to its complaints and decisions.

---

## 4. Part B: context (P4), templates and work queue (A2)

### 4.1 Context panel on the case (read only)
1. **Similar past investigations:** closed or decided cases on the same product family or problem code, plus similar wording when B6a's P1 helper ships (B6a-spec 6.2; cut item D2 there). Each shows its signed cause category, attribution, decision ID and date. At most 10, newest first. Without P1: product and problem code only.
2. **The lots:** each in-scope lot's other complaints (outside the case) and its shipments by country (reuse `lot_impact/service.py`). "Distribution not imported" is never shown as zero.
3. **Service history of the device:** by serial number: other complaints on the same serial (`foundation.py:310`), service-level dispositions with their service record (`complaint_disposition.py:59`), intake service records (`intake.py:62`), in date order. Without a serial: "No serial number recorded". RCA-D10 (index).

### 4.2 Templates (A2)
- Five starter templates, held as versioned data in code (like `case_challenge/rules.py:20` `RULE_VERSION`): alarm or false alarm; flow, pressure or occlusion; power and electrical; software and SaMD; labelling and use. Each lists evidence to request, questions to answer, and fishbone prompts per category.
- Applying one creates evidence requests (existing `evidence_workflow/requests.py`) and open questions (existing unknowns), each marked "From template T-n v1". It creates **no** hypothesis and no cause. Applying twice does not duplicate. Audited `RCA_TEMPLATE_APPLIED`.
- Suggested, not forced: the case page offers the template whose problem codes match. Customer-editable templates wait for B4b/B4c (RCA-D11).

### 4.3 Work queue (A2)
- Two views: **Mine** (extends `case_workflow/router.py:92`) and **Team** (Leaders and quality reviewers).
- Order, no hidden score: (1) risk: a death or serious injury in scope, then priority CRITICAL, HIGH; (2) the nearest deadline among the case due date (`foundation.py:371`), reporting due dates of in-scope complaints (`market_assessment.py:111`) and review due dates (`reviews.py:107`); (3) missing evidence: open requests, open questions, unreviewed evidence (`readiness.py:430-487`).
- Each row says why: "Serious injury in scope · EU report due in 3 days · 2 evidence requests open". RCA-D12.

---

## 5. Part C: investigation intelligence on the screens (P8 build)

1. **Version at the event date.** The case anchors on each in-scope complaint's event date (else awareness date). For each, it shows the version the complaint names and the configuration valid on that day (`product360/service.py:353-362`, components). If the complaint names no version, it stays "version unknown" (PV-1 rule, `case_challenge/facts.py:8`); nothing is borrowed. A named version released after the event date is flagged "Version released after the event: check".
2. **One overview** (flat, G-2): facts with their source (epistemic type FACT or SOURCE_ASSERTION, `intelligence.py:30`), hypotheses with evidence for and against and their category, open contradictions (`case_intelligence/router.py:797`), open unknowns, the 5 Whys, each line linking to its record. Read only; existing tabs stay for editing.
3. **"Trace this value"** links on dates and versions when B6a's G20 is built (B6a-spec 6.1); otherwise no link.
4. **The R1 keyword analysis (G23):** RCA-D13.

---

## 6. Part D: the investigation dossier with its review lifecycle (A3)

### 6.1 Twelve sections, built on the brief
The dossier **is** the Decision Brief version, laid out in 12 sections. No second document to keep in step. Locked versions, return for rework, escalation and segregation of duties already exist (G7).

| # | Section | Source | New? |
|---|---|---|---|
| 1 | Summary | Problem statement and proposed conclusion (narrative) | Exists |
| 2 | Chronology | Event, awareness, entry dates; version releases; changes; lots made and shipped; evidence received; reviews; reports; decisions. Each with its record | **New** |
| 3 | Product configuration at the event date | Part C 1 | **New** |
| 4 | Evidence inventory | `compose.py:193`, review states, provenance | Exists |
| 5 | Similar complaints and signals | Signals (`compose.py:84`), B5 same-problem complaints, Part B context | Part new |
| 6 | Hypotheses with evidence | `compose.py:264-335`, with category and FMEA link | Part new |
| 7 | Contradictions and unknowns | `case_intelligence/router.py:797`; `compose.py:385` | Part new |
| 8 | Risk and impact | Risk review (`compose.py:500`), signed lot impact, the P3 numbers of named risks (Part E) | Part new |
| 9 | Recommended actions | Narrative recommended actions; labelled **"Recommended, not yet approved"** | Exists, relabelled |
| 10 | Regulatory considerations | Regulatory review; per in-scope complaint: market, signed conclusion, report status and due date | **New** |
| 11 | Human review and decisions | Review actions with comments (`reviews.py:172-195`); the signed decision, its accepted causes, follow-ups, signatures. **Only here** do approved decisions appear | **New** |
| 12 | Provenance | Rule versions used (B5 H/C rules, rule-register floors, templates, P3 method), the configuration report reference when B6a G21 exists (B6a-spec 5.4), AI executions (`compose.py:541`) or "No AI was used" | **New** |

**Amendment B, made visible:** each line is tagged *Verified fact (source)*, *Hypothesis*, *Unknown or contradiction*, *Recommendation* or *Approved decision*. Sections 9 and 11 never mix.

### 6.2 Review
- A reviewer comment may name a section (new `section_key` on `brief_review_actions`). The author sees comments beside their section on the returned version.
- Reject and rework = today's return actions (`decision_brief/rules.py:49-76`). Rework is a new version; the old one stays frozen.
- Compare with the previous version: not in v1 (cut list).

### 6.3 Export
- New document type `INVESTIGATION_DOSSIER` in `qms_documents` (PDF and DOCX), built from a **frozen** brief version only.
- After signing, the export is built from the signed decision snapshot, never recomposed from live data. An unsigned export carries "Draft: not approved" on every page. RCA-D14.

---

## 7. Part E: observed vs estimated harm rate (P3)

1. **Estimate per risk** (new risk columns): hazard, harm, severity, estimated probability of the harm per unit, where it came from (imported, or entered in MDARIX), and the codes it covers (problem codes, harm codes). Import columns are added to the risks template (`trial/business_imports.py:116`). RCA-D6.
2. **Observed:** in the period, complaints on the risk's product (and version, when the risk names one) whose problem or harm code is mapped to the risk. Counted twice: *occurrences* (problem codes) and *harms* (harm code or harm level from the signed market assessment). RCA-D9.
3. **Denominator:** the B5 ladder: units shipped when every lot has shipments; else units released; else **counts only** (`closed_loop/rules.py:9-12`). Labelled "per unit shipped" or "per unit released", never "per unit sold". When the January sales-data item lands, units sold becomes the first rung. RCA-D8.
4. **Comparison:** observed rate with its exact 95% interval (Poisson; reuse `closed_loop/rules.py:93-131`). Words, never verdicts: "Above the estimate" (lower bound above), "Possibly above: too few to tell" (point above, bound not), "Within the estimate", "Counts only (units unknown)", "No estimate recorded". RCA-D7.
5. **Where:** a column on the post-market risk-file page (`post_market/router.py:21,30`, served in the MVP), not the parked risk register (G12). "Above the estimate" puts the product in the existing NOT_REVIEWED / reassessment flow (`post_market/risk_file.py:13-21`) and offers "Request a risk review". MDARIX never edits the risk file (ISO 14971 clause 10; FDA QMSR).

---

## 8. Build steps

"(db)" = database test; "(unit)" = no database. Hours include targeted tests.

| # | Step | Part | Hours | Targeted tests |
|---|---|---|---|---|
| 0 | Branch from the joined line after B6b; one Alembic head; re-check every line here; CHANGELOG; scenarios RCA-01..RCA-40 into `scenario-register.md` | all | 3 | `alembic heads` = 1 |
| 1 | Migration `tr3x_trial_rca_tools` (8.1) | A | 3 | (db) upgrade, downgrade, upgrade; downgrade refused while a categorised decision or an estimate exists; RLS coverage test |
| 2 | 5 Whys on chains: create, 2-7 whys, evidence per link, "Unknown" whys, link to a hypothesis | A | 6 | (db) 1 and 8 whys refused; whys never set a hypothesis status; another tenant's chain not found |
| 3 | Fishbone: `cause_category`, quick add, rule out with reason, `failure_mode_id`, grid read | A | 8 | (db) quick add is PROPOSED, origin human; rule-out needs a reason; failure mode of another tenant refused; HypothesisValidator refuses "root cause"/"proven" in a quick-add statement |
| 4 | Confirmed cause at signing: payload fields, checks (ticked ids are this case's, not RETIRED), snapshot binding, columns | A | 8 | (db) unticked → no cause; snapshot hash covers the ids and category; signed decision row unchanged byte for byte after later hypothesis edits; supersede re-categorises; old decisions "Not categorised" |
| 5 | Pareto service and route | A | 6 | (unit) one complaint counted once; latest decision wins; superseded ignored; disposition fallback; "No confirmed cause yet" bar; cumulative share sums to 100 |
| 6 | Screens A: 5 Whys, fishbone grid, signing fields, Pareto | A | 10 | vitest per screen; `tsc --noEmit` |
| 7 | Switch, guide text | A | 2 | Off/on/off |
| 8 | Risk estimate fields: import columns; entry by a risk reviewer with reason, audited (old and new values) | E | 6 | (db) import reads them; entry without reason refused; admin alone refused; audit holds old value |
| 9 | Code mapping and observed counts | E | 5 | (unit) occurrences vs harms; version-specific risk; cancelled and inquiry complaints excluded |
| 10 | Rate, interval, words; denominator ladder | E | 5 | (unit) partial units → counts only; zero events → upper bound only; each word at its boundary |
| 11 | Risk-file column, reassessment hook, "Request a risk review" | E | 5 | (db) "Above" makes the product NOT_REVIEWED until a review; MDARIX writes nothing to `risks` |
| 12 | Switch, guide | E | 3 | Off/on/off |
| 13 | Similar past investigations (with P1 helper if present) | B | 6 | (db) only decided or closed cases; another tenant unseen; without P1 same results by code |
| 14 | Lot context | B | 3 | (db) "distribution not imported" never zero |
| 15 | Service history by serial | B | 5 | (db) same serial only; date order; no serial message |
| 16 | Context panel screen | B | 4 | vitest |
| 17 | Five templates, apply, no duplicates, audit | B | 10 | (db) apply creates requests and questions only, no hypothesis; twice = no duplicates; template version recorded |
| 18 | Work queue Mine and Team, reasons | B | 10 | (db) order: harm, then deadline, then missing evidence; ties stable; Team needs the role; reasons text |
| 19 | Switch, guide | B | 2 | Off/on/off |
| 20 | Version at the event date (anchor, mismatch flag, PV-1) | C | 8 | (db) no version stays unknown; version released after the event flagged; event date absent → awareness |
| 21 | Intelligence overview screen | C | 8 | vitest; every line links to a record |
| 22 | R1 keyword analysis per RCA-D13 | C | 3 | (unit) keyword output never reaches the customer screen while AI is off (or carries the label) |
| 23 | Trace links (if G20 exists) and switch | C | 3 | Off/on/off |
| 24 | Dossier readers: chronology, configuration, contradictions, regulatory, review history, provenance, risk and impact, tags | D | 21 | (db) every line has a tag; sections 9 and 11 never mix; provenance names rule versions; "No AI was used" when none |
| 25 | 12-section layout; `section_key` comments | D | 6 | (db) comment on a section shows on the returned version; accept may have no comment |
| 26 | Dossier export PDF and DOCX, frozen versions only, draft marking | D | 10 | Signed export identical before and after live data changes; draft watermark on every page; export audited |
| 27 | Dossier screen and switch | D | 9 | vitest; off/on/off |
| 28 | Sample (8.6) | all | 6 | `test_sample_story_days.py`, sample decision tests green; new `test_rca_sample_story` |
| 29 | Targeted suites with every RCA switch on and off, plus `test_case_intelligence*.py`, `test_decision_brief*.py`, `test_human_decision*.py`, `test_b5_*.py`, `test_risk_file_api.py`, `test_lot_impact_api.py`, `test_qms_documents_rules.py`, `test_feature_set.py`; ruff; one independent read-only review; fixes | all | 8 | All green both ways |
| | **Core total** (step 0 3, A 43, E 24, B 40, C 22, D 46, sample 6, final 8) | | **192** | |
| 30 | *Optional:* one closed sample past investigation (PulseWatch cable, signed, category Material) so context and Pareto show history | B | 4 | Sample tests |
| 31 | *Optional:* fishbone diagram in the PDF | D | 4 | PDF read-back |
| | **Total with options** | | **200** | |

At about 7 build hours a day the core is about 28 working days. Each part ships on its own, in the order of RCA-D15.

### 8.1 Migration
**One additive migration: `tr3x_trial_rca_tools.py`, revision `trrcatools`, `down_revision` = the joined line's head at step 0** (today `tr31othercountries`; B6a adds `tr32auditentity` only if needed, B6a-spec:243; B6b unknown). Re-attached at merge under the one-head rule.
- `hypotheses.cause_category VARCHAR(20) NULL` (check: the category list); `hypotheses.failure_mode_id UUID NULL` (FK with `tenant_id` to `failure_modes`).
- `failure_chains.method VARCHAR(20) NOT NULL DEFAULT 'CHAIN'` (check: CHAIN, FIVE_WHYS).
- `decisions.root_cause_category VARCHAR(20) NULL`; `decisions.root_cause_hypothesis_ids JSONB NOT NULL DEFAULT '[]'` (check: a JSON array).
- `brief_review_actions.section_key VARCHAR(40) NULL`.
- Part E: `risks.hazard TEXT`, `risks.harm TEXT`, `risks.severity VARCHAR(40)`, `risks.estimated_probability NUMERIC NULL` (check `> 0 AND <= 1`), `risks.estimate_source VARCHAR(20) NULL` (IMPORTED, ENTERED), `risks.match_codes JSONB NOT NULL DEFAULT '{}'`. If Part E is cut, these columns are removed from the migration before merge.
- No new table, no data step, no backfill. Existing rows keep NULL or the default. Downgrade refuses while a decision has a category or a risk has an estimate (no silent loss).
- Templates are data in code; the queue, context and Pareto are reads; the dossier is the brief plus a document type.

### 8.2 Switches (the `feature_set.py` pattern, read on every call)
| Switch | Default | Off means |
|---|---|---|
| `MDARIX_RCA_METHODS` | on | 5 Whys, fishbone and Pareto routes 404, tabs hidden; signing does not offer the cause fields; signed categories stay readable |
| `MDARIX_RCA_HARM_RATE` | on | Risk-file page without the rate column; estimates stay stored |
| `MDARIX_RCA_CONTEXT` | on | Context panel, templates and Team queue hidden, routes 404; Mine keeps today's order |
| `MDARIX_RCA_INTELLIGENCE` | on | Overview and event-date context hidden; tabs as today |
| `MDARIX_RCA_DOSSIER` | on | Brief shown as today; dossier export 404; section comments shown as plain comments |

### 8.3 What can be cut (in this order)
1. Step 31 (fishbone diagram in the PDF). 2. Step 30 (sample past investigation). 3. Version-to-version compare (already out of v1). 4. Section comments (step 25 part; whole-version comments stay). 5. Templates beyond two (alarm, software). 6. Team queue (Mine keeps the new order). 7. Service history by serial (step 15). 8. The overview screen (step 21; event-date context stays). 9. Part E as a whole (then P3 waits for the January sales data, and Lane 2's E6 takes another item, `complete-plan:184`).

### 8.4 Never cut
- A confirmed cause exists only in a signed decision, ticked by a person; no hypothesis status ever changes because of it.
- Signed decisions, frozen brief versions and signed exports never rewritten; re-categorising only by superseding.
- Counts only when units are not known for every lot; never "per unit sold" before sales data exist.
- Sections 9 (recommended) and 11 (approved) never mixed; every dossier line tagged.
- Zero AI calls in every RCA route; the R1 keyword output never shown as analysis.
- RLS and cross-tenant tests on every new read; the switches; the downgrade guard.

### 8.5 Definition of done (v2.1, item 7)
Approved spec; implementation complete; targeted tests pass; permission tests including negative cases (who may tick a cause, enter an estimate, see the Team queue); regression suites both switch states; evidence and docs stored (CHANGELOG, user guide, decision-table doc for the P3 words); owner acceptance recorded. A screen existing is not "complete".

### 8.6 How it fits the sample story
The trial's case SAMPLE-INV-001: OrbitCare 300 Rev B, pressure alarms after the NovaSense sensor supplier change, concentrated in lots 003 and 004 (`trial/sample_data.py:1-6, 44-53`). The sample author already recorded two hypotheses (supplier PARTIALLY_SUPPORTED, ward settings WEAKLY_SUPPORTED), two open questions and a failure chain (`trial/sample_decision.py:63-128`). SAMPLE-CAPA-02 comes from it (`trial/sample_supply.py:12-14, 48`). Risks SAMPLE-RSK-01 and -02 are on OrbitCare (`trial/sample_data.py:250-252`).
1. **Fishbone:** the supplier hypothesis gets Material; a quick-added "incoming inspection cut from 32 to 13" gets Method; ward settings gets Environment, still weak, with EV-002 and EV-003 against it.
2. **5 Whys** from the existing chain: alarms → pump reads high → sensors 4-6% high in lots 003-004 → inspection cut → supplier change accepted with reduced sampling; the bench test stays "Unknown".
3. **Work queue:** SAMPLE-INV-001 sits first: malfunction complaints in scope and the CAPA's due date.
4. **Context:** lots 003 and 004 with their shipments (`trial/sample_lot_impact.py`); no past investigation unless optional step 30.
5. **Version at the event date:** Rev B for the clustered complaints; "Compare with Rev A" shows the sensor supplier change (W1 S1).
6. **Signing:** the trial user ticks the supplier hypothesis, category Material. The **Pareto** shows Material plus the service-level attributions (`trial/sample_dispositions.py:319`).
7. **P3:** SAMPLE-RSK-01 gets a synthetic estimate "(Sample)" mapped to PRESSURE_ALARM; sample lots have units (`trial/sample_data.py:593-598`), so the rate reads "Above the estimate" and the risk file asks for a review.
8. **Dossier:** the sample brief opens as 12 sections; the trial user reviews, accepts, signs, exports.

### 8.7 Scenarios (RCA-xx, acceptance criteria)
Methods: RCA-01 5 Whys with 2 to 7 whys; RCA-02 a why without evidence shows "Unknown" and can open a question; RCA-03 the last why never becomes a cause; RCA-04 fishbone quick add is a PROPOSED hypothesis; RCA-05 ruled-out cause stays visible with its reason; RCA-06 software category shown for SaMD; RCA-07 cause with a failure mode shows its risks; RCA-08 signed cause with no failure mode prompts "Not in your FMEA". Confirmed causes: RCA-09 nothing pre-ticked at signing; RCA-10 ticked causes and category are in the signed hash; RCA-11 a hypothesis status never changes on signing; RCA-12 old decisions "Not categorised", unchanged; RCA-13 supersede re-categorises; RCA-14 "Not determined" needs a reason. Pareto: RCA-15 each complaint once; RCA-16 latest decision wins; RCA-17 "No confirmed cause yet" bar shown; RCA-18 counts only, no rate. Context: RCA-19 similar past investigations show their signed causes; RCA-20 lot with no distribution never zero; RCA-21 service history by serial in date order. Templates and queue: RCA-22 a template adds requests and questions, no hypothesis; RCA-23 applying twice adds nothing; RCA-24 queue order harm, deadline, missing evidence with reasons; RCA-25 Team queue needs the role. Intelligence: RCA-26 no version stays unknown; RCA-27 version released after the event flagged; RCA-28 overview lines link to records; RCA-29 R1 keyword output not shown as analysis. Dossier: RCA-30 twelve sections, every line tagged; RCA-31 recommendations and approved decisions apart; RCA-32 section comment on a returned version; RCA-33 rework is a new version, old one frozen; RCA-34 signed export identical after live changes; RCA-35 draft export marked on every page. Harm rate: RCA-36 partial units → counts only; RCA-37 "Above" only when the lower bound is above; RCA-38 MDARIX writes nothing to the risk file. All: RCA-39 another tenant's cases, causes and estimates unseen; RCA-40 every switch off/on keeps signed records readable and drafts signable.

---

## 9. Owner decisions

⚑ = touches signed records, the risk file or what a customer may read as a finding: **needs your explicit answer.**

| # | Decision | Recommendation (safe) |
|---|---|---|
| RCA-D1 ⚑ | What makes a cause "confirmed" | Only a signed decision in which the signer ticks the accepted hypotheses and the category. No hypothesis status changes. *If no answer:* as recommended. |
| RCA-D2 ⚑ | Decisions signed before RCA | Never rewritten; "Not categorised" in the Pareto; re-categorising only by a superseding decision. *If no answer:* as recommended. |
| RCA-D3 | Fishbone categories | Your list: People, Process, Method, Material, Machine, Environment, Software (SaMD). Measurement and Design are common in device investigations: add them only if you say so. |
| RCA-D4 ⚑ | Category required at signing? | Required when the outcome accepts a conclusion (ACCEPT_CONCLUSION, ACCEPT_WITH_CONDITIONS), "Not determined" allowed with a reason; optional otherwise. *If no answer:* optional everywhere (no change to signing). |
| RCA-D5 | Pareto unit | Complaints, each once under its current confirmed cause; investigation count shown beside. |
| RCA-D6 ⚑ | Where risk estimates come from | Imported from your QMS (Connect) or entered in MDARIX by a risk reviewer with a reason, labelled "Entered in MDARIX: check against your risk file" (Complete). *If no answer:* import only; MDARIX never authors risk-file values. |
| RCA-D7 ⚑ | P3 flag rule | "Above the estimate" only when the 95% lower bound is above; a person decides any risk-file update; the product enters the existing reassessment flow. *If no answer:* numbers and words only, no reassessment hook. |
| RCA-D8 ⚑ | P3 denominator before sales data | Units shipped, else released, else counts only; labelled as such; never "per unit sold". *If no answer:* as recommended. |
| RCA-D9 ⚑ | What counts as an observed harm for a risk | A person maps problem and harm codes per risk; occurrences and harms counted apart. *If no answer:* occurrences only. |
| RCA-D10 | Serial-number lookups | No index first; add one in the RCA migration only if the read is above 500 ms at 5,000 complaints (B6a's load set). |
| RCA-D11 | Templates | Five starter templates in code, versioned, not customer-editable until B4b/B4c. |
| RCA-D12 | Queue order | Harm, then nearest deadline, then missing evidence; reasons on each row; no hidden score. |
| RCA-D13 ⚑ | The R1 keyword analysis on the case page (G23) | While AI is off, hide its "possible explanations" and "contradictions" and point to the B5 drafts and the RCA overview. Its tests stay. *If no answer:* keep it, labelled "General prompts, not drawn from your records' analysis". |
| RCA-D14 ⚑ | Dossier export | Frozen versions only; after signing, from the signed snapshot; drafts marked on every page. *If no answer:* as recommended. |
| RCA-D15 | Build order | **A → E → B → C → D.** E early because Lane 2's E6 builds on P3 (`complete-plan:184`); D last because it gathers the others. |
| RCA-D16 | Migration | One additive migration (8.1); Part E's columns dropped from it if E is cut. |

**Needing your explicit answer:** RCA-D1, D2, D4, D6, D7, D8, D9, D13, D14.

---

## 10. What I did not check
- B6a and B6b branches were not read. P1 (similar wording), G20 (trace) and G21 (configuration report) are taken from `b6-speed-evidence/B6a-spec.md`; B6b is not drafted. Step 0 re-checks every line on the joined line.
- Whether the case intelligence tabs and the R1 analysis panel are visible in the free trial's MVP interface (`feature_set.py:11-12`) was not checked screen by screen.
- The R1 folder audit used two read-only helper reads; I re-checked the claims this spec relies on. One helper said the version story route was missing; it exists (`stage3_router.py:21, 251`).
- `genai.grounding` and `search_evidence` date filtering, `briefs/`, `case_ai/`, `evidence_workflow/requests.py` internals were not read.
- No database was queried and nothing was run. Serial-number lookup speed and test counts are not measured. Hours are estimates from B5 and B9 steps of similar size.
- No regulatory text was re-read; ISO 14971 clause 10 and FDA QMSR are cited as the plans and code already cite them (`post_market/risk_file.py:3-7`).

---

## Owner approval (12 Nov 2026)
The owner replied **"approve RCA spec"**: every recommendation accepted (RCA-D1 a cause is confirmed only by a signed decision ticking accepted hypotheses and a category; D2 earlier decisions never rewritten, "Not categorised"; D4 category required on an accepted conclusion with "Not determined + reason"; D6 risk estimates imported or entered by a risk reviewer with a reason, labelled; D7 "Above the estimate" only when the 95% lower bound exceeds it, a person decides any risk-file update; D8 shipped, else released units, else counts only, never "per unit sold"; D9 a person maps problem and harm codes to each risk; D13 the R1 keyword analysis panel is hidden — done now as a separate fix before the cut-off; D14 export only from locked versions). Build order A → E → B → C → D in Lane 1 after B6b.

**Owner, 12 Nov 2026 ("accept R1 fix"):** RCA-D13 accepted (commits 1ffb3c4b, 505a1d10, d0ce04d4 and merges); MDARIX's own evaluation run (Platform Admin, synthetic golden tenant, saves nothing) stays open on purpose.
