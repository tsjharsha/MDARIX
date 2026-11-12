# Q2: Investigation benchmark ("QMS only" vs "QMS + MDARIX")

Version 1, 11 Nov 2026. **DRAFT for the owner.** Nothing here is built or run. Q2 runs in Lane 1 right after the RCA tools item (owner-approved 11 Nov). Decisions marked **⚑** touch claims, people or signed records: they need the owner's explicit answer. Each ⚑ says what happens **if no answer arrives** (always the safer path).

- **Sources:** `post-whif-best-practices/plan.md` (Q2 row, line 54; M8 line 34; P8 line 48; timeline lines 64-66), `complete-plan/MDARIX-complete-plan.md` (step 4.4 line 80, RCA tools 5.5 line 90, step 5.6 with A8 line 91, lanes line 183), `scenario-register.md` (IV-01..IV-16, lines 87-104), `b6-speed-evidence/B6a-spec.md` (P1 similar wording, P2 baselines), `b9-markets/spec.md` (format).
- **Code read** (read-only): branch `feat/b9b-other-countries`, tip `3dc55c0b`. Every `file:line` is on that branch. Step 0 re-checks every line on the release under test.
- **Regulatory content:** none is decided here. Every reportability answer and deadline in the answer key comes from the outside adjudicator, not from MDARIX's rules (that would be circular).
- **Not in Q2:** an AI arm (only if the owner switches AI on later, as a separate arm); real customer or patient data; the pilot case story Q1 (that needs a pilot); P2's live outcome numbers (those come from a customer's own data).

---

## 1. Purpose, in plain words

Q2 measures, honestly, what MDARIX adds to a quality team's investigation work. QA/RA professionals prepare investigations on synthetic complaints, half with only a typical QMS export, half with the same export plus MDARIX. Outside experts score the outputs against an answer key written and signed before anyone starts.

**No number is published until it is measured.** The targets below are goals for the build team. They are never claims. A missed target is reported as missed.

| Target goal (never a claim) | Measure |
|---|---|
| 100% product-version accuracy on the benchmark cases | M3 |
| >= 99% correct evidence citation on accepted outputs | M4b |
| Zero critical unsupported conclusions in accepted outputs | S1 |
| >= 30% less preparation time, subject to the measured baseline | M1 |

---

## 2. What exists today, and the gaps

### 2.1 What we reuse
| Asset | What it gives Q2 | Evidence |
|---|---|---|
| AI golden dataset `r1-ai-golden-v2` | The pattern: three layers (source, canonical, evaluation-only ground truth), deterministic seed, hash lock, named human sign-off. **The dataset itself stays untouched** (it is locked for AI evaluation) | `docs/validation/AI_GOLDEN_DATASET_QUALIFICATION.md:5-11, 28-44, 49-61`; `data/golden/README.md`; `data/golden/GOLDEN_DATASET_MANIFEST.json` |
| Ground-truth format | Per scenario: expected evidence, contradictions, unknowns, prohibited conclusions, anomalies, acceptance criteria. Q2 extends it | `evaluation/ground_truth/VS001/ground_truth.json` |
| Golden scenario ideas | VS001 supplier change, VS002 false correlation, VS003 missing evidence, VS004 conflicting evidence, VS005 wrong timeline, VS007 premature closure, VS011 multiple causes, VS012 correct abstention: re-written for Q2 with markets and deadlines | `evaluation/ground_truth/VS0xx/ground_truth.json` (titles) |
| Validated imports | The loader uses the same import path a customer uses: products, lots, complaints (with country, awareness date, harm flags), components, suppliers, BOM, lot genealogy, distribution, changes, risks, failure modes, controls, investigations, evidence, CAPAs | `backend/app/trial/imports.py:179-240, 308`; `backend/app/trial/business_imports.py:40-168` |
| Personal-data guard on imports | Any name, phone, e-mail or record number in synthetic text is refused, so the pack is checked for personal data by the product itself | `backend/app/trial/imports.py:1-10` |
| Free-trial workspace | One fresh workspace per participant; AI cannot be switched on in a free trial (409), which guarantees the AI-off arm | `backend/app/trial/service.py:1-5`; `backend/app/ai_settings.py:116-119` |
| Trial limits | 5,000 rows and 2 MB per file: enough for the pack | `backend/app/trial/service.py:47-48`; `imports.py:85-94` |
| Sample removal | The trial sample is removed before loading, so it cannot help or confuse | `backend/app/trial/sample_removal.py:1-15, 148, 241` |
| Sample story patterns | Lot genealogy, distribution, regulatory identity and import-run lineage show how to build realistic synthetic records | `trial/sample_data.py:1-6`; `sample_lot_impact.py:1-16`; `sample_imports.py:1-16`; `sample_supply.py:1-15` |
| Investigation intelligence | Hypotheses, unknowns, contradictions, failure chains, linked evidence; the B5 challenge drafts, every sentence citing records | `case_intelligence/__init__.py:1-2`; `db/models/foundation.py:477-503, 1192`; `case_challenge/rules.py:1-10` |
| Duplicates (rule) | Same product + same lot or serial + events within 2 days + same site or country | `intake/rules.py:23-24, 49, 721-743` |
| Markets and approvals | Five markets in code; a second person approves report snapshots with password and authenticator code | `reportability/markets.py:44`; `authority_reports/router.py:11, 2214` |
| Scenario register | Status rules (NOT RUN, PASS, FAIL, BLOCKED); a blocked or unexecuted scenario is never a pass | `scenario-register.md:5-13` |

### 2.2 Gap table
| # | Gap | Evidence | Step |
|---|---|---|---|
| G1 | No benchmark scenario set. The golden dataset is AI-focused and locked; its complaints have no country, harm or awareness date | `data/golden/source/qms/complaints.csv:1` (header) | 1-3 |
| G2 | Ground truth has no fields for version at event date, reportability per market, deadlines, duplicates, required approvals, lots at risk | `evaluation/ground_truth/VS001/ground_truth.json` | 5 |
| G3 | No "QMS export" form of the data (complaint form PDFs, CSV lists, attachments) for the QMS-only arm | — | 4 |
| G4 | No loader that puts a whole scenario pack into a fresh workspace with dates relative to the load day | — | 7 |
| G5 | Evidence imports carry text and a product, not a link to a complaint; files on records exist only on Cases (B7). Whether imported complaints can carry files is unknown | `business_imports.py:152-168`; `intake/case_attachments.py`; `main.py:500` | 0, 7 |
| G6 | No service-history import. Service records exist only inside a complaint's disposition | `complaint_disposition/router.py:64, 87` | 3 (service reports loaded as evidence documents) |
| G7 | The sample clock moves every `MDARIX_SAMPLE` record daily; sample removal deletes them. Benchmark records must never carry that source | `trial/sample_clock.py:1-10`; `trial/sample_source.py` | 7 |
| G8 | In a free trial one person may prepare and approve a report ("practice approval"). That must not count as a captured approval | `authority_reports/router.py:2274` | 9 |
| G9 | Version "as of" a date picks the latest version **released** before that date, not the version built into the unit. A unit built before a release but used after it would show the wrong version | `product360/service.py:353-362` | Q2-02 tests it; P8 audit to check |
| G10 | Duplicates by wording (P1) are not built on this branch; only the rule above | `b6-speed-evidence/B6a-spec.md` (P1 row) | Run needs B6a |
| G11 | No scoring script, rater workbook, consent form, output form or timing sheet | — | 8, 9 |

---

## 3. Design

### 3.1 The two arms
- **QMS only.** The participant gets the fictional maker's QMS export as a folder: complaint forms (PDF), complaint, lot, distribution and change lists (CSV/XLSX), attachments (photos described in text, e-mails, test reports, service reports), the risk file extract (PDF) and the maker's complaint-handling SOP extract with reporting timelines. Any desktop tool is allowed (search, spreadsheet). MDARIX is not opened.
- **QMS + MDARIX.** The same folder, **plus** a MDARIX workspace holding the same records, loaded through the normal imports. AI is off (free trial: `ai_settings.py:116-119`).
- **Same data in both arms** (Q2-D5). Both arms see the maker's full history (about 300 background complaints over two years), not only the scenario's records. Finding the relevant records is part of the job.
- **Same output in both arms.** Both arms fill the same neutral output form (3.6). Copying from MDARIX into the form counts as MDARIX time. This is conservative: it can only make MDARIX look slower.
- **Release under test:** fixed and tagged **before** the answer key is locked. No product change between lock and the last session. A bug found during the run goes to the next release and does not change any score.

### 3.2 The fictional maker
A new fictional maker, "Q2 Benchmark Devices (Synthetic)", not the golden dataset's or the trial sample's company. Reason: prospects and reviewers have seen the trial sample and the videos; a new maker removes recall. Four products, each in two or three versions with build dates, a BOM with effective dates, two suppliers per key component, about 40 lots with genealogy and distribution to the US, EU, GB, India, Canada and one other country. Device risk bands: lower, middle and higher risk, plus one IVD. **The exact class per market is set by the adjudicator**, not by this spec. Every file and record carries "SYNTHETIC: Q2 benchmark, not for clinical or regulatory use".

### 3.3 Scenarios and coverage matrix
16 scenarios in four blocks (A-D) of four. Each block has one simple case, one multi-market case, one evidence-heavy case and one data-quality case, so blocks are of similar difficulty. 12 are written by the scenario author; **4 hold-outs (one per block, marked H) are written by the outside adjudicator** and are not seen by the build team before the release under test is frozen. Hold-outs are also reported separately.

| ID | Block | Short description | Markets | Risk band | Harm | Dup or lookalike | Version change | Contradiction | Missing info | Late / backlog | Lots at risk |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Q2-01 | A | Control: complete malfunction complaint, one version, no harm. MDARIX should add little | US | Middle | None | | | | | | |
| Q2-02 | A | Complaint says Rev B; the serial was built as Rev A before Rev B's release and used after it (tests G9) | US, EU | Middle | Serious injury | | Yes | | | | |
| Q2-03 | A | Same event reported by the hospital and by a distributor in different words, 3 days apart, one with a typo in the lot | EU, GB | Higher | Serious deterioration | Yes | | | | | |
| Q2-04 H | A | Adjudicator's hold-out | Adjudicator | | | | | | | | |
| Q2-05 | B | Supplier change looks guilty, but the failures started before the change (VS001/VS002 idea) | US, India | Middle | Malfunction, could cause harm | | Yes | Yes | | | Yes |
| Q2-06 | B | India serious adverse event; lot and patient outcome unknown; the right output is unknowns and evidence requests | India | Higher | Serious injury | | | | Yes | | |
| Q2-07 | B | Indian maker's export: the same lot fails in India and Canada; Canada 10-day vs 30-day | India, Canada | Higher | Serious injury | Yes | | | | | Yes |
| Q2-08 H | B | Adjudicator's hold-out | Adjudicator | | | | | | | | |
| Q2-09 | C | Death; the returned device passes all tests; the service record shows a repair a month before | US, Canada | Higher | Death | | | Yes | | | |
| Q2-10 | C | Backlog: 20 old complaints entered late; one buried event is reportable and already overdue | EU, GB, India | Lower | Mixed | Yes | | | | Yes | |
| Q2-11 | C | Shared component lot across three finished lots, shipped to four markets; which lots and markets are exposed | US, EU, GB, Canada | Middle | Malfunction | | Yes | | | | Yes |
| Q2-12 H | C | Adjudicator's hold-out | Adjudicator | | | | | | | | |
| Q2-13 | D | Looks frightening but is user error with no malfunction; the right answer is "not reportable" with a rationale | US, EU | Lower | Minor injury | | | Yes | | | |
| Q2-14 | D | IVD false-low result and delayed treatment; reportability needs judgement | EU, India | IVD | Serious injury (to confirm) | | | | Yes | | |
| Q2-15 | D | Two mechanisms at once (VS011 idea); one repaired unit in the service history | GB, other country | Middle | Serious injury | | Yes | Yes | | | |
| Q2-16 H | D | Adjudicator's hold-out | Adjudicator | | | | | | | | |

**Coverage check (the 12 authored cases):** US 6, EU 6, GB 4, India 5, Canada 3, other country 1; harm from none to death; duplicates or lookalikes 3; version change 4; contradiction 4; missing information 2; late entry 1; lots at risk 3. The adjudicator aims the four hold-outs at the thinnest cells (other country, late entry, missing information, lower risk), and at cases where MDARIX may not help at all.

Two extra **practice cases** (Q2-P1, Q2-P2) are used in training only and never scored.

### 3.4 The answer key (one file per scenario)
The golden ground-truth fields, plus:
- `version_at_event`: product, version and the key configuration items (component revision, supplier) at the event date, with the records that prove it.
- `required_evidence`: evidence IDs needed for the investigation; `missing_evidence`: items that should be requested.
- `contradictions`, `unknowns` (each with an ID), `prohibited_conclusions` (each one counts as critical if asserted).
- `hypotheses`: the plausible causes with supporting and contradicting evidence IDs.
- `duplicates`: the true duplicate set; `related_not_duplicate`: lookalikes that are not.
- `reportability`: per market, the decision (reportable / not / needs more information), the report type, the due date as an offset from the load day, and `acceptable_alternatives` where experts may reasonably differ, each with a reason.
- `lots_at_risk`: lots and markets exposed.
- `approvals_required`: who must sign what before closure and before submission.
- `material_findings`: the statements a good output should make, each with its evidence IDs.

Dates are stored as offsets from the load day ("D-40"). The loader turns them into real dates, so deadlines stay ahead of the participant, as the sample clock does for the trial (`sample_clock.py:1-10`).

### 3.5 Adjudication protocol (nobody adjudicates their own work)
| Step | Who | What |
|---|---|---|
| 1 | Scenario author (Sriharsha, Q2-D1) | Writes the 12 authored scenarios and their draft keys |
| 2 | Outside adjudicator (a QA/RA consultant, never the author) | Writes the 4 hold-outs and their keys |
| 3 | Adjudicator | **Cold-solves** each authored scenario from the QMS export alone, without the key: checks it is solvable in the QMS-only arm and gives a pilot time |
| 4 | Author and adjudicator | Compare the cold solve with the draft key. Each difference is resolved in writing. Unresolved: the owner decides, with the reason recorded |
| 5 | Adjudicator | Checks every reportability decision and deadline against the regulation text. **The key wins over MDARIX's starter rules.** A difference is logged as a finding for the product, not "fixed" in the key |
| 6 | Owner | Signs the lock: SHA-256 of every key file, the analysis plan (section 4) and the release tag, as the golden lock does (`AI_GOLDEN_DATASET_QUALIFICATION.md:38-41`). **Before the first session** |
| 7 | — | After the lock, a key change needs a written reason and the owner's signature; the report then shows scores under both the old and the new key |

The author never rates participant outputs. Participants never rate. The owner signs but does not rate. The build team never sees the hold-outs before the release is frozen.

### 3.6 The neutral output form (both arms)
One form per case, the same in both arms (a spreadsheet with fixed sections):
1. Product, version and configuration at the event date, with record IDs.
2. Evidence used (IDs) and evidence still needed.
3. Possible duplicates and related complaints (IDs).
4. Hypotheses: each with supporting IDs, contradicting IDs and a status (open, supported, ruled out).
5. Unknowns.
6. Findings: numbered statements, each with its evidence IDs.
7. Reportability per market: decision, report type, due date.
8. Lots and markets possibly affected.
9. Approvals required before closure and before submission.
10. Recommended next actions.

The same record IDs appear in the export and in MDARIX, so citations can be scored mechanically.

### 3.7 Participants
- **How many:** 8 (minimum 6) QA/RA professionals (Q2-D2).
- **Profile:** at least 2 years of complaint handling or vigilance work in a device maker or a consultancy. At most 2 from one company. Nobody who has seen the build, our families, advisers or the adjudicator.
- **Recruitment:** the validation prospects list (MDARIX-outreach), LinkedIn using the approved outreach template, the consultant network and hackathon contacts. The invitation states the purpose plainly: "help us measure honestly; the result may be that MDARIX does not help".
- **Consent:** written consent before session 0: purpose, voluntary, stop at any time without reason, what is recorded (times, forms, optional screen recording), anonymous codes (P01-P08), no name or employer used anywhere without a separate written OK (Q2-D14), how long data is kept. A privacy notice under India's DPDP Act (and GDPR for an EU participant).
- **Thank-you:** Q2-D3.
- **Product comments** from participants are product feedback: they are appended to `reviewer-feedback-log.md` as they arrive (owner rule).

### 3.8 Counterbalancing
Each participant does **two blocks (8 cases): one block in each arm.** Slots are assigned by a recorded random draw.

| Slot | MDARIX arm | QMS-only arm |
|---|---|---|
| P01 | A | B |
| P02 | B | A |
| P03 | C | D |
| P04 | D | C |
| P05 | A | C |
| P06 | C | A |
| P07 | B | D |
| P08 | D | B |

Each block is done by 4 people, 2 in each arm, so each scenario has 2 observations per arm. Nobody sees a scenario twice. Case order inside a person's 8 cases is random (seed recorded), with 2 cases of each arm in each session, so fatigue and learning fall on both arms. With only 6 participants, slots P07 and P08 are dropped and blocks B and D have 1 observation per arm (reported as such). With 12 scenarios (cut, Q2-D9): 3 blocks, 6 participants on pairs AB, BA, AC, CA, BC, CB.

### 3.9 Sessions and timing
- **Session 0 (about 75 min):** consent; the same recorded MDARIX walkthrough for everyone (the screens the arm needs, nothing more); the export folder; the output form; practice case Q2-P1 with MDARIX and Q2-P2 without. Not scored.
- **Sessions 1 and 2 (about 2.5 h each):** 4 cases each, a 10-minute break in between. Remote, video call, screen shared.
- **Debrief (10 min):** a short questionnaire (effort felt, would you use this output) and free comments.
- **Timing:** the facilitator logs start (case card opened) and stop (form submitted) on a timing sheet, to the minute. Breaks are logged as pauses. Optional screen recording backs the sheet. Time includes reading, searching and writing in both arms; it excludes training and loading.
- **Cap:** 60 minutes per case (Q2-D10). A capped case is scored as submitted and its time recorded as 60 with a flag.
- **Facilitator:** follows a fixed script, answers only process questions, never content. Sessions are recorded with consent so anyone can audit for coaching (Q2-D11).
- **Loading is not prep time.** Each pack is loaded before session 1. The loader's own time is reported separately, per scenario pack, so the M8 calculator can add a one-off import effort honestly (Q2-D12).

### 3.10 Blinding
- Participants and facilitator cannot be blind to the arm.
- **Raters are blind.** Before rating, a third person (the facilitator) removes arm clues from the forms with a fixed find-list (product and screen names, "exported from"), gives each form a random code, and sends raters the forms per scenario in random order. The arm is joined back only after all ratings are locked.
- The scoring script is blind by design (it reads IDs and dates).

### 3.11 Data handling and loading
- **Synthetic only.** No real customer, patient, reporter or product. Names of fictional people are avoided altogether; roles are used instead ("the ward nurse"). The product's own import guard refuses personal data (`imports.py:1-10`), which checks the pack.
- **One fresh free-trial workspace per participant** (Q2-D4), so nobody sees another person's work on the same scenario. Marked "Q2 benchmark" in the trial request so it is left out of trial statistics.
- **Loader order:** approve the trial → remove the sample (`sample_removal.plan` then `remove`) → set time zone, reporting windows and market roles from the maker's profile → import in dependency order through the trial's governed import (`TRIAL_POLICY`, `imports.py:85-94`) → attach files where step 0 finds a route (G5) → check counts. Dates come from offsets (3.4). The loader refuses a workspace that holds anything else.
- **Never** the `MDARIX_SAMPLE` source (G7). **Never** the answer key in a workspace or an export: an isolation test checks this, as the golden qualification does (`AI_GOLDEN_DATASET_QUALIFICATION.md:22-24, 28-29`).
- **Where files live:** generator, pack and key on a branch in `MDARIX-R1` (`data/benchmark/q2/`, `evaluation/benchmark_q2/`). Participant data (consent register with names and e-mails) is kept apart from results, offline, in `MDARIX-validation/q2-benchmark/private/`. Results use P-codes only.
- **Retention:** workspaces deleted after scoring. Screen recordings deleted after the report is approved. Consent register kept until 90 days after the report, then names deleted unless the person agrees otherwise.

---

## 4. Measures and scoring

### 4.1 Measures
**Primary** (pre-registered, locked with the key): M1, M2, M3, W1, W2, S1. All others are secondary.

| ID | Measure | Definition | Scored by |
|---|---|---|---|
| M1 | Preparation time | Minutes from opening the case to submitting the form | Timing sheet |
| M2 | Evidence found | Recall: key `required_evidence` IDs cited / all of them. Precision also reported | Script |
| M3 | Product-version accuracy | 1 if version **and** every key configuration item at the event date are right, else 0 | Script |
| M4a | Findings linked to evidence | Share of material findings in the form that cite at least one ID | Script + rater |
| M4b | Correct evidence citation | Share of citations where the cited record really supports the statement | Two raters |
| M5 | Hypothesis quality | Rubric 4.2, 0-12 | Two raters |
| M6 | Unknowns detected | Key unknowns matched / all key unknowns (raters map free text to key IDs) | Two raters |
| M7 | Expert acceptance | "Accept as is" / "accept with minor edits" / "not acceptable". Accepted = first two | Two raters |
| A8a | Duplicate-detection precision | True duplicates flagged / all flagged. Recall also reported | Script |
| A8b | Evidence completeness | (Required evidence cited + missing evidence correctly requested) / all required items | Script |
| A8c | Required approvals captured | Key approvals named and routed / all key approvals. A same-person practice approval does not count (G8) | Script + rater |
| W1 | Reportability per market | Per (case, market): decision and report type right, or inside the key's acceptable alternatives | Script |
| W2 | Deadline correctness | Per reportable (case, market): due date right to the day; overdue flagged when it is | Script |
| W3 | Lots at risk | Exposed lots and markets found / key set; extra lots reported | Script |
| S1 | Critical unsupported conclusion | Per form: any prohibited conclusion asserted, or a root cause, "not reportable" or safety statement without supporting evidence. Either rater's flag goes to the adjudicator | Two raters + adjudicator |

### 4.2 Hypothesis quality rubric (M5)
Each dimension 0-3. Raters read the anchors before rating and rate the two practice cases first to calibrate.

| Dimension | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| Coverage | None of the key causes | One key cause | Most key causes | All key causes, nothing implausible |
| Grounding | No evidence cited | Supporting only, some wrong | Supporting and contradicting, minor slips | Supporting and contradicting, all right |
| Calibration | Asserts a cause as fact against the evidence | Overconfident | Mostly matched to the evidence | Confidence matches the evidence; unknowns stated |
| Next step | None | Vague ("investigate further") | Concrete for some | A concrete test or evidence request for each open hypothesis |

**Rater agreement:** the two scores are averaged when they differ by 1 or less per dimension; a bigger gap is discussed and the agreed score recorded. Exact and within-1 agreement are reported.

### 4.3 Statistics for a small sample
- Per measure and arm: **median, minimum and maximum, and n.** No means as headline figures.
- **Time saved:** for each participant, their median MDARIX time divided by their median QMS-only time; report the median of these ratios, the range, and "k of n participants were faster with MDARIX".
- **Per scenario:** every observation shown in a table, so nobody needs to trust a summary.
- **No p-values, no confidence intervals, no "significant".** The sample is too small for them to mean much.
- **Nothing is dropped.** Capped cases, withdrawals and protocol slips are listed with their reason. Hold-outs are shown separately and inside the totals.
- **System-only figures** (4.4) are reported apart from people's figures, never merged.

### 4.4 System-only arm (no people)
A script runs MDARIX's own deterministic parts on a loaded workspace and compares them with the key: version at the event date, duplicate suggestions (rule and P1), and the report type and due date when the key's answers to each market's questions are entered. It is cheap and repeatable. It becomes a per-release regression check and feeds **B6b G13 validation figures**. It says nothing about time or human judgement.

### 4.5 AI arm (later, only if the owner switches AI on)
A third arm on separate workspaces, after the people arms are reported. Same key, same raters, separate report. The Q2 scenarios may be added to the AI golden dataset only **after** the run (as a new reviewed version), so the AI is never tuned on the key before it is tested.

---

## 5. Threats to validity, and what we do about them

| Threat | Effect | Mitigation |
|---|---|---|
| The author knows MDARIX and may write cases that suit it | Overstates MDARIX | 4 hold-outs by the adjudicator; control case Q2-01; cases where MDARIX may not help (Q2-13, Q2-14); adjudicator's cold solve checks the QMS arm is fair |
| Product tuned to the key | Overstates MDARIX | Release frozen and tagged before the lock; no change during the run |
| Participants are prospects and may want to please | Overstates acceptance | Objective measures scored by script; raters blind; raters are not participants |
| A new tool against a familiar folder | Understates MDARIX | Same training for all; one practice case per arm |
| The export folder is harder or easier than a real QMS | Either way | Adjudicator confirms the folder looks like a typical export; full history in both arms |
| Copying into the neutral form | Understates MDARIX | Accepted; stated in the report |
| Loaded data is cleaner than real customer data | Overstates MDARIX | Data-quality cases (aliases, lot typos, late entries); loader time reported separately |
| Small sample, 2 observations per scenario per arm | Noisy | Medians and ranges only; every observation shown; no general claims |
| Facilitator is from the team | Coaching risk | Fixed script; recordings; process questions only |
| Raters guess the arm from writing style | Weakens blinding | Find-list cleaning; random order; rated per scenario |
| Synthetic cases are not real cases | Limits generality | Stated in every use of a number |
| Starter regulatory rules in MDARIX | Wrong deadlines counted as MDARIX errors | Correct: they are errors. Logged as product findings for the consultant |

---

## 6. What may be said afterwards (Q2-D6)

**May be said, after the owner approves the report, in this form only:** "In a benchmark on N synthetic complaint scenarios adjudicated by an outside QA/RA expert, with P QA/RA professionals, median preparation time was X minutes with MDARIX and Y minutes with a QMS export alone (ranges ...). Release R, month year. Method: [link]." Each figure keeps its sample size, the word "synthetic", the release and the date.

**Never said:** real-world or customer savings; "validated", "proven", "clinically", "significant"; any figure without its sample size; any figure from the AI arm as a people figure; any comparison with a named product; a target as if it were a result; anything about a participant or their employer without their written OK.

**A missed target is reported as missed,** with what we will change. The build team fixes product findings in a later release; the benchmark is re-run before any new figure is used.

---

## 7. The evidence pack

Kept in `MDARIX-validation/q2-benchmark/` (results, anonymous) and the repository branch (generator, pack, key, scripts):
1. Method note: this spec as approved, the analysis plan and the release tag.
2. Signed key lock: hashes, the owner's signature, the adjudication log (cold solves, differences, resolutions).
3. Scenario pack and QMS export (synthetic).
4. Raw data: timing sheets, forms (coded), rater sheets, script output. No names.
5. Results report: all tables in 4.1, the per-scenario table, rater agreement, threats, deviations, product findings.
6. One-page summary with the allowed wording (section 6).
7. **Feeds:**
   - **M8 time-saved calculator:** per-case medians and ranges for both arms and the loader time, labelled "benchmark" until a customer's own P2 figures exist (`plan.md:34`).
   - **Case story and investor narrative:** only the approved wording; the benchmark is described as a benchmark, never as a customer result.
   - **B6b G13 validation figures:** the system-only arm (4.4) per release.
   - **Defect log (B6b G16):** every MDARIX error found.
   - **Scenario register:** Q2-01..Q2-16 with PASS / FAIL / BLOCKED from the system-only arm.

---

## 8. Build steps

"Ours" = the build team's hours. People's time is in 8.2. Code goes on a branch `feat/q2-benchmark` only after this spec is approved.

### 8.1 Steps (ours)
| # | Step | Hours | Check |
|---|---|---|---|
| 0 | Fix the release under test and its tag; re-check every line cited here on it; confirm in a trial workspace that every screen the MDARIX arm needs is on (P8 screens, A3 dossier, P1, G20, B8, B9, B9b); find a route for files on imported complaints (G5); add Q2-01..Q2-16 to `scenario-register.md` | 3 | Checklist signed by the author |
| 1 | Coverage matrix final and 12 scenario briefs; brief to the adjudicator for the 4 hold-outs | 6 | Adjudicator agrees the matrix |
| 2 | Fictional maker generator (products, versions with build dates, BOM with effective dates, suppliers, lots, genealogy, distribution, ~300 background complaints, risk extract, SOP extract); deterministic seed; SYNTHETIC marks | 10 | Same seed, same bytes; counts as planned |
| 3 | Records for 16 scenarios and 2 practice cases (complaints, attachments, service reports as evidence documents, test records, e-mails, late entries); hold-outs entered from the adjudicator's text | 24 | Every key ID exists in the pack |
| 4 | QMS export renderer: per-block zip with complaint form PDFs, CSV/XLSX lists, attachments, risk extract, SOP extract | 8 | Same IDs in export and import files |
| 5 | Draft keys for the 12 authored scenarios in the extended format (3.4) | 12 | Schema check |
| 6 | Lock and qualification, reusing the golden pattern: hash lock, structure check, key isolation test, personal-data and secret scan | 6 | Tamper test fails the lock |
| 7 | Loader (3.11) with date offsets and settings; refuses a non-empty workspace; run twice on a local trial workspace | 10 | Import counts match; no `MDARIX_SAMPLE` row; no key text in the database |
| 8 | Session kit: output form, timing sheet, facilitator script, consent and privacy notice, recorded walkthrough, debrief questionnaire | 12 | Dry run (step 11) |
| 9 | Scoring script (M2, M3, A8a-c, W1-W3), rater workbook (M4-M7, S1), blinding step (find-list, random codes), agreement figures | 12 | Script scores the key itself as 100%; a planted wrong form scores as expected |
| 10 | System-only arm script (4.4) | 6 | Runs on the dry-run workspace |
| 11 | Dry run with one outside person who will not take part; fix the kit; re-lock if a case changes (before any real session) | 8 | Dry-run times inside the 60-minute cap |
| | **Build subtotal** | **117** | |
| 12 | After the run: analysis, results report, evidence pack, allowed wording | 12 | Independent read of the report |
| | **Total (ours)** | **129** | About 18-19 working days at 7 h a day |

### 8.2 People's time (not ours)
| Who | Work | Hours |
|---|---|---|
| Outside adjudicator | 4 hold-outs with keys (12); cold solve of 12 cases (9); reconciliation (3); regulatory check of all keys (4) | ~28 |
| Second rater (outside QA/RA) | ~64 forms at ~12 min, plus calibration | ~14 |
| Adjudicator as first rater | Same | ~14 |
| Participants | 8 × (session 0 1.25 h + two sessions 5 h + debrief 0.25 h) | ~52 (6.5 each) |
| Facilitator | 8 × 6.5 h of sessions, scheduling, blinding | ~62 |
| Dry-run person | One full run | ~6 |
| Owner | Decisions (1), key lock review and signature (4), report and wording approval (2) | ~7 |

**Calendar, if recruitment is done in parallel:** build 3-4 weeks; adjudication 2 weeks (overlapping); sessions 3 weeks; rating 1 week; report 1 week. About 8 weeks from start to approved report.

### 8.3 What can be cut (in this order)
1. System-only arm (step 10) moves to B6b. 2. Hold-outs from 4 to 2. 3. Scenarios from 16 to 12 (3 blocks, 6 participants). 4. Recorded walkthrough replaced by a live, scripted one.

**Never cut:** the outside adjudicator; the signed lock before session 1; the frozen release; blind rating; reporting every observation; the publication rule.

### 8.4 Dependencies and order
- **Can start now (no code):** recruitment of the adjudicator, second rater and participants; consent text; coverage matrix; hold-out briefs.
- **Needs the RCA tools item released:** the run (P8 screens, A2 templates, A3 dossier). B6a's P1 and G20 must be in the release under test.
- **Needs the release tag:** the lock, the loader run, sessions.

---

## 9. Owner decisions

⚑ = touches claims, people or signed records: **needs your explicit answer.** "If no answer" is what happens meanwhile.

| # | Decision | Recommendation (safe) |
|---|---|---|
| Q2-D1 ⚑ | Who writes and who adjudicates the key | Sriharsha authors the 12 scenarios and draft keys; an outside QA/RA consultant writes 4 hold-outs, cold-solves, checks regulatory answers and adjudicates; you sign the lock. Sriharsha never rates outputs. *If no answer:* Sriharsha drafts; the run stays **BLOCKED** until an outside adjudicator is named. Never self-adjudicated. |
| Q2-D2 ⚑ | Participants | 8 (minimum 6), 2+ years of complaint or vigilance work, at most 2 per company, recruited from the prospects list, LinkedIn (approved template) and consultants. *If no answer:* recruit 8 that way; run with 6 at least. |
| Q2-D3 ⚑ | Thank-you to participants | A certificate of participation and the summary report; any other thank-you is your call. *If no answer:* certificate and summary only. |
| Q2-D4 ⚑ | Where it runs | One fresh free-trial workspace per participant on production (the product the figures describe), marked "Q2 benchmark", left out of trial statistics, deleted after scoring. *If no answer:* the same; synthetic data only. |
| Q2-D5 | Data given to each arm | Both arms get the maker's full history and the same SOP extract with reporting timelines. *If no answer:* as recommended. |
| Q2-D6 ⚑ | Publication | Nothing leaves the team before you approve the report; then only the wording in section 6; missed targets reported as missed. *If no answer:* internal use only. |
| Q2-D7 | AI | Off for the benchmark. A separate AI arm only after you switch AI on, on separate workspaces, in a separate report. *If no answer:* no AI arm. |
| Q2-D8 ⚑ | Consent and ethics | Written consent and a DPDP privacy notice from each participant; no ethics committee, as no patient or patient data is involved; your consultant to confirm. *If no answer:* written consent, minimal data, no ethics review. |
| Q2-D9 | Number of scenarios | 16 in 4 blocks (12 authored, 4 hold-outs). *If no answer:* 16. |
| Q2-D10 | Time cap | 60 minutes per case; capped cases flagged and scored as submitted. *If no answer:* as recommended. |
| Q2-D11 ⚑ | Facilitator | Sriharsha or you, with a fixed script and recorded sessions; process questions only. *If no answer:* Sriharsha, with recordings (consent permitting). |
| Q2-D12 | Import effort | Data pre-loaded; loader time reported separately, never inside preparation time. *If no answer:* as recommended. |
| Q2-D13 | Primary measures | M1, M2, M3, W1, W2, S1, locked with the key. *If no answer:* as recommended. |
| Q2-D14 ⚑ | Naming participants or employers | Anonymous by default; named only with a separate written OK for a named use. *If no answer:* anonymous. |

**Needing your explicit answer:** Q2-D1, D2, D3, D4, D6, D8, D11, D14.

---

## 10. To confirm with your consultant
The exact device class per market for each fictional product; every reportability decision and deadline in the key; acceptable alternatives where experts may differ (Q2-14 IVD especially); the "other country" case's local rule; whether an ethics review is needed for a study with professionals only.

## 11. What I did not check
- The P8 audit has not happened and the RCA tools (P8 build, A2, A3) are not built: the MDARIX arm's screens are assumed from their plan rows.
- B6a's P1 and G20 are specs only on this branch. The duplicate figures depend on them.
- Whether an imported complaint can carry files (G5), and whether every feature is on in a free-trial workspace: step 0.
- Whether the investigation screens use `select_version` (G9) or the unit's build record: left to the P8 audit; Q2-02 tests it either way.
- How MDARIX handles IVD reportability: not read. Q2-14 is kept because it may show a gap.
- The outreach list, the consent wording under DPDP and the sessions' tooling were not opened or checked. No person was contacted.
- Hours are estimates from B9 and B6a steps of similar size; people's times are from a planned 35-minute average case, not measured.

---

## Owner approval (12 Nov 2026)
The owner replied **"approve Q2 spec"**: every recommendation accepted (Q2-D1 Sriharsha authors, an outside QA/RA consultant writes the hold-outs and adjudicates, the owner signs the hash-locked key; D2 8 participants (min 6), >= 2 years, <= 2 per company; D3 certificate + summary report; D4 marked free-trial workspaces, excluded from trial statistics, deleted after scoring; D6 internal until the owner approves the report, then fixed wording only, missed targets reported as missed; D8 written consent + DPDP notice, no ethics committee (consultant to confirm); D11 Sriharsha or the owner facilitates from a fixed script, sessions recorded; D14 anonymous unless separate written permission) and D5, D7, D9, D10, D12, D13 as defaults. Runs in Lane 1 after the RCA tools item. Recruiting, consent text and the coverage matrix may start earlier without code.
