# B9: India MvPI, Canada mandatory problem reporting, US importer and user facility

Version 1, 11 Nov 2026. **DRAFT for the owner.** Nothing here is built. Per the owner's automatic chain (11 Nov), B9 starts when B4 is complete, on the recommendations in section 7 unless the owner changes them. Decisions marked **⚑** touch regulatory interpretation or signed records: they need the owner's explicit answer. Each ⚑ says what the build does **if no answer arrives** (always the safer path).

- **Sources:** `b4-rule-register/spec.md` (approved 11 Nov: engine, data format, floor F1–F12, effective dating, FG-2, R-D11), `master-sequence-proposal.md` (item 12), `development-cycle-1.md` (B9 row, step 6), `authority-forms-spec/spec.md` (§3, §6, §7, §8, §9 phases 3 and 6, D1–D18) and `spot-check.md`, `authority-forms-mapping.xlsx` (Counts sheet and US section F rows, read only), `other-country-reports/spec.md` (approved; B9b stays separate), `b3-emdr/B3-execution-plan.md` (report chain, numbers, frozen files, owner decisions 1–3).
- **Code read** (read-only): worktree `trial-094`, branch `feat/b3-emdr-0.10.96`. Every `file:line` is on that branch, under `backend/app/` unless shown. B7, B5 and B4 change some of these files on their own branches; step 0 re-checks every line on B4's tip.
- **Regulatory text:** only what the planning files and code already hold. Anything else is written **"to confirm with your consultant"**. Every new rule is starter text, as today.
- **Not in B9:** other countries (B9b), EU and GB MIR (B8), customer rule layers (B4b), Canada foreign risk notifications and summary reports, US voluntary malfunction summary reporting, India PSURs and Rule 38 foreign-action reports (all out per D18 or below).

---

## 1. Purpose, in plain words

**MDARIX prepares; the customer submits.** For every report below, MDARIX decides with the person whether a report is owed and by when, fills the authority's form from held data, freezes the files at approval, and records what the customer sent, when, by which route, and the authority's answer. MDARIX never submits on the customer's behalf (authority-forms spec §2.6). No decision here changes that.

| Market and report | Who files | What MDARIX prepares | What is signed | What is audited |
|---|---|---|---|---|
| **India, MvPI adverse event report** (Initial, Follow up, Final) | The manufacturing licence holder (and, to confirm, the importer) | The official MDAE form v1.2, filled; an ADRMS entry sheet in portal screen order; the 15-day clock | The India conclusion (existing e-signature, now with the floor code, B4 R-D14); the report snapshot (second-person approval, password + MFA, existing) | Conclusion signed; report created, approved, files frozen, submission recorded, follow-up/final created; route evidence |
| **Canada, mandatory problem report** (Preliminary, Update, Final, Preliminary & Final) | The manufacturer and the importer, or the importer for both after written notice (s.61.1) | The official form HC Pub. 110180, filled; the 10-day / 30-day clock; the Final draft created when the Preliminary is submitted, due on the promised date | Same as India | Same, plus "Final created from the Preliminary" |
| **US importer report** (Initial, Follow-up #n) | A tenant that imports the device into the US (21 CFR 803.40) | Form 3500A section F as eMDR XML + eSubmitter-layout PDF; the 30-day clock; who must receive it (FDA and/or the manufacturer) | Same as B3 (US conclusion; report snapshot; XML frozen in the signature) | Same as B3, plus each recipient's copy recorded |
| **US user facility report** (Initial, Follow-up #n) | A tenant that is a hospital or other user facility (803.30) | Form 3500A section F (eMDR XML, eSubmitter-layout PDF, and the official 09/2025 form for paper filing, 803.12(b)); the 10-work-day clock; the recipients | Same | Same |
| **US user facility annual report** (Form FDA 3419, 803.33, by 1 January) | User facility | **Not built** (D18). Optional aid only (step 22) | — | — |

**One new setting: "Your role in this market".** Manufacturer (today, the default), Importer, or User facility (US only). It picks which floor (rule set) applies to the tenant's assessments in that market. Nothing changes for a tenant that never sets it.

---

## 2. India: Materiovigilance Programme of India (MvPI)

### 2.1 Reportability (floor `IN-floor`)
| Item | Today | B9 |
|---|---|---|
| Questions | IN1 associated with device; IN2A–F serious criteria; IN3 unexpected (`reportability/markets.py:366-414`) | **Unchanged** |
| Logic | Reportable = IN1 and any IN2 criterion; IN3 only adds a note (`markets.py:569-573`; decision tables IN-1..IN-11) | **Unchanged** (B9-D2 ⚑) |
| Folding, pre-fill | `markets.py:637-642`, `:713-716` | Unchanged |
| **Legal period** | **None in code** (`markets.py:89-90`, days `None`). A Reportable conclusion takes the organisation's India window, any length 1–365 (`markets.py:1040-1045`, `reportability/rules.py:228-236`). Triage already uses 15 days (`intake/rules.py:463-467`). This is FG-2 (B4 §2) | **`IN-floor-2`**: `IN_SERIOUS_ADVERSE_EVENT` = 15 calendar days, citing MDR 2017 Rule 26(ii) "within fifteen days" (authority-forms spec §7.1). Starter, for your consultant to confirm (B9-D1 ⚑) |
| Counting | IST or the organisation's zone, earliest; awareness day is day 1 (`reportability/deadlines.py:36-42`) | Unchanged (OD-1 stays open) |

**What `IN-floor-2` changes, and nothing else.** Only the period of the one report type. Suggestions, report type, notes and folding stay identical (a test proves it over all 3^8 answer combinations). Effects:
- A Reportable India conclusion is due on the organisation's window only when it is exactly 15 calendar days; otherwise 15 days from the regulation (`market_clock`, `markets.py:1030-1038`, B4 F6). A longer window no longer gives a later date.
- A pending one takes the earliest of the windows and 15 days.
- The sample's India window is already 15 days (`trial/sample_reports.py:40`), so the sample's dates do not move.

**Effective dating (B4 R-D4).** `IN-floor-2` is a **correction** of MDARIX's own rule, not a law change (the Rules are older than MDARIX). It has the same period as `IN-floor-1` ("from the start") and replaces it at once for unsigned work. Signed India conclusions keep `IN-floor-1` and their due date. An unsigned draft gets `409 FLOOR_CHANGED` at signing and is saved again (B4 R-D6). An India report already created keeps its due date until a person re-signs (B4 §4.2).

### 2.2 Reports, deadlines, form
| Report | Trigger | Deadline | Output |
|---|---|---|---|
| Initial | Signed Reportable India conclusion (existing, `authority_reports/router.py:923-960`) | 15 days (`IN-floor-2`) | Official MDAE form v1.2 PDF, filled, + ADRMS entry sheet + today's worksheet PDF |
| Follow up | On demand: "Create follow-up" (D15, approved: no auto-create, no legal clock found) | Optional next-report date chosen by the user, labelled "No legal clock: your date" | Same files, type "Follow up", same MAH reference |
| Final | On demand: "Create final" | Same | Same, type "Final"; F3 root cause expected |
| Trend | **Not built** (to confirm with your consultant whether licence holders must file it) | — | — |

- **Who receives it.** MvPI by e-mail (mvpi-ipc@gov.in) or ADRMS web entry (existing routes, `forms.py:519-546`). Whether Rule 26 also needs a separate notice to the licensing authority is **to confirm with your consultant** (B9-D3 ⚑). The CDSCO circular of 15 May 2024 ("should also use the MvPI platform") was read only in secondary sources: to confirm.
- **No XML.** ADRMS has no import found (to confirm). Hence the entry sheet: the values in ADRMS screen order, marked with ADRMS's mandatory stars, for fast copying.
- **Chain without a migration** (B3 pattern): a follow-up or final is `kind = RESPONSE`, `form_code = MVPI_MDAE`, `parent_id` = the initial; its type sits in P2; the optional next-report date uses the existing `follow_up_due_on` column. One open follow-up at a time; a Final ends the chain.

### 2.3 Required fields mapped to MDARIX data
The paper form marks no field mandatory; ADRMS marks 16 (Counts sheet: 8 held, 7 derived, 1 held-else-ask; status 10 exist / 6 partly / 0 missing).

| ADRMS mandatory field | MDAE form field | MDARIX source | Today |
|---|---|---|---|
| Report type | P2 | Derived from the chain (Initial / Follow up / Final) | Always "Initial" (`authority_reports/worksheet.py:621`): **new** |
| Date of report | P1 | Day sent for approval (as B3 Q3) | Typed (`forms.py:354`): **change** |
| Serious case, reasons | B8 | IN2A–F answers (`worksheet.py:350-364`) | Exists |
| Patient involved | — | Derived Yes when death or serious injury is recorded; else asked | **New** (asked) |
| Reporter department, country, mobile | R3 | India responsible party (`worksheet.py:664`) | Partly (one text) |
| Reported by / primary reporter | R1 | The tenant's role in India (Manufacturer / Importer) | Typed (`forms.py:371`): **derive** |
| Device category | CAT1–CAT6 | CAT2, CAT4 held (`forms.py:387-389`); others asked once per product | Partly |
| Device name | A_COMMON, A_BRAND | Product (`forms.py:399-400`) | Exists |
| Device information | A1, A3, A4, A6, A7, A10, A11 | Risk class, CDSCO licence (`worksheet.py:659`), model, lot, serial, GMDN, UDI | Exists |
| Event date | B1 | Complaint event date | Exists |
| Adverse event category | B2 | Event type (`forms.py:430`) | Exists |
| Description | B12 | Complaint description | Exists |
| Patient outcome | C7 | Derived from death / serious injury; else asked at the step, report-only (D3 rule) | Personal, blank today (`forms.py:477`): **change** |

Other fields keep today's mapping (`forms.py:341-549`). Section C and D personal fields stay blank unless decision B9-D9 allows report-only entry.

### 2.4 India importer
The form and ADRMS accept importers. Rule 38 covers an importer's foreign regulatory actions (15 days); an importer's own serious-adverse-event duty is **to confirm with your consultant**. B9: an India importer uses the same `IN-floor` (same questions and 15 days); only R1 and A_IMPORTER change (B9-D4 ⚑). Rule 38 reports are not built.

---

## 3. Canada: mandatory medical device problem reporting

### 3.1 Reportability (floor `CA-floor`)
| Item | Today | B9 |
|---|---|---|
| Questions CA1–CA6, logic, folding | `markets.py:415-484`, `:574-584`, `:643-652`; tables CA-1..CA-10 | **Unchanged** in core B9 |
| Periods | CA_10_DAY (s.60(1)(a)(i)), CA_30_DAY (s.60(1)(a)(ii)), calendar, awareness is day 0, organisation's zone (`markets.py:92-104`, `deadlines.py:36-48`) | Unchanged |
| **Foreign incident** | CA_FOREIGN has no period (`markets.py:100-104`): a Reportable foreign conclusion falls back to the organisation's Canada windows (often 10 days). The guidance reads "as soon as possible" as 48 hours from the corrective-action decision (authority-forms spec §6.1) | Optional `CA-floor-2` (step 20, B9-D6 ⚑) |
| **OD-3** | CA5 Unknown gives 10 days (`markets.py:578-584`) | Stays unless B9-D6 is answered |

### 3.2 Reports, deadlines, form
| Report (form A5) | Trigger | Deadline | Output |
|---|---|---|---|
| Preliminary | Signed Reportable Canada conclusion (existing) | 10 or 30 days (existing) | Official HC Pub. 110180 PDF, filled (**new**), + today's worksheet PDF |
| Final | **Created automatically when the Preliminary is recorded as submitted** (D16, approved) | The "anticipated date for the final report" given in A5 of the Preliminary (s.60(2)(h), s.61; no fixed statutory clock) | Same, type Final; E2 root cause and E3 corrective actions required |
| Update | On demand: "Create update" | User's date, labelled | Same, type Update |
| Preliminary & Final | The user picks it on the first report when the investigation is complete | 10 or 30 days | Same; nothing created after it |

- **Route:** e-mail to Health Canada (existing `HC_EMAIL`, `forms.py:1577-1591`). The address differs between the form and Health Canada's pages: **to confirm** (owner checks with Health Canada). No XML or portal exists.
- **Chain without a migration:** as India (RESPONSE + `parent_id`, type in A5). Health Canada's file number (A4) from the acknowledgement is carried to every later report; A3 reporter file number is copied from the Preliminary; A5 "previous report date" is derived from the last submission.

### 3.3 Required fields mapped to MDARIX data
Counts sheet, Preliminary: 27 mandatory (11 held, 10 derived, 5 asked, 1 held-else-ask; status 12 exist / 9 partly / 6 missing).

| Field | Rule | MDARIX source | Today |
|---|---|---|---|
| A2 contact, A3 reporter file no., A5 type, A6 date submitted, B1 classification, C1 brand | Every report (*) | Responsible party; A3 typed once per chain; A5 from the chain; A6 day sent; B1 from the signed type (`worksheet.py:526-532`); brand | A2, B1, C1 exist (`forms.py:1434-1515`); A3, A6 typed; A5 chosen by hand |
| A4 Health Canada file no. | Updates and finals | From the acknowledgement, carried | Typed (`forms.py:1445-1453`) |
| A5 anticipated final date | Preliminary | Asked; becomes the Final's due date | Field exists (`forms.py:1455-1462`), not used for a clock: **new** |
| A1 reporter type; A7 manufacturer / importer | Preliminary | The tenant's role in Canada | Typed / party: **derive A1** |
| A8 HC company ID, A9 MDEL, s.61.1 notice | Once per organisation | "Your organization · enter once" group (`frontend/.../ReportBody.tsx:14`) | Not held: **ask once** |
| B2–B5, C2–C5, C9, D1, E1 | Preliminary | Held or derived (`forms.py:1494-1562`) | Exist / partly |
| C6 age of device, C7 time in use, C8 labelled sterile | Preliminary | Asked (C6 derivable from a manufacture date when held) | Asked |
| D2–D5 complainant name, address, contact | Preliminary | Personal: B9-D9 ⚑ | Never stored |
| E2 root cause, E3 corrective actions | Final, Preliminary & Final | E2 asked; E3 from the CAPAs (`forms.py:1563-1571`) | Exist as fields; not enforced per chain |

### 3.4 Canada importer
Form A1 offers Importer, with A1 ii/iii (`forms.py:1420-1433`). An importer tenant uses the same `CA-floor`; A1 and A7 follow the role; the s.61.1 written notice is recorded once per organisation (date and file). Whether the importer files its own report or relies on the manufacturer's is the customer's choice, recorded on the report.

---

## 4. US importer and user facility (beyond B3's manufacturer eMDR)

### 4.1 Reportability: two new floors, as data
B4 picks a floor by market and awareness day. B9 adds the tenant's role: `{market}-floor` for a manufacturer (today's code names, so nothing existing changes), `{market}-{ROLE}-floor` otherwise. Only the US needs role floors, because only US law differs by role in the planning files.

| | `US-IMP-floor-1` (importer, 803.40) | `US-UF-floor-1` (user facility, 803.30) |
|---|---|---|
| Questions | US1, US2A–C, US3, US4, US5 reused word for word (`markets.py:175-253`); US6 (5-day) not asked: "803.53 applies to manufacturers" | US1, US2A–C, US3 reused; US4–US6 not asked: "user facilities do not report malfunctions" |
| Logic | Same as the US manufacturer's death/injury and malfunction limbs | Death or serious injury, and US3 caused or contributed. Whether US3's wording matches 803.30's test is **to confirm with your consultant** |
| Report type | `US_IMP_30_DAY`: 30 calendar days (803.40) | `US_UF_10_WORK_DAY`: 10 work days (803.30) |
| Recipients (new data key `recipients`) | Death or serious injury: FDA, with a copy to the manufacturer. Malfunction: the manufacturer only | Death: FDA and the manufacturer. Serious injury: the manufacturer, or FDA if the manufacturer is unknown |
| Counting | US rule (America/New_York, from the day after awareness) | Same, work days |
| Triage tiers | 30 calendar for every tier (no 5-day) | 10 work days for every tier |
| Follow-up clock | **Not settled** (authority-forms spec §12): B9-D12 ⚑ | Same |
| Source catalog ids | `CFR803_3`, new `CFR803_40` | `CFR803_3`, new `CFR803_30` |

Both are version 1, "from the start", starter. A tenant that never sets a role keeps `US-floor-1`: the B4 equivalence suite covers it unchanged.

### 4.2 Reports and files
| Report | Trigger | Deadline | Output |
|---|---|---|---|
| Importer initial | Signed Reportable US conclusion under `US-IMP-floor` | 30 calendar days | eMDR XML (803.12(a): electronic) + eSubmitter-layout PDF + official form; F1 = Importer; G and H left out |
| Importer follow-up #n | B3's chain (`router.py:2276`, `:2338-2355`), on demand | B9-D12 | Same, F7 = Follow-up #n |
| User facility initial | Signed Reportable US conclusion under `US-UF-floor` | 10 work days | eMDR XML, eSubmitter-layout PDF, **and the official 09/2025 form as the paper route** (803.12(b), D2) |
| User facility follow-up #n | Same chain | B9-D12 | Same |
| User facility annual report (Form 3419) | — | 1 January (803.33) | **Not built** (D18); optional list aid, step 22 |

- **Same obligation, no new form code.** The obligation stays `form_code = FDA_3500A` (the eMDR route guard `router.py:2697` keeps working); `report_type` (`US_IMP_30_DAY` / `US_UF_10_WORK_DAY`) tells `emdr` which kinds apply (I-I, I-F, U-I, U-F). One INITIAL per complaint and market still holds (`db/models/authority_reports.py:134`): a tenant has one role per market.
- **Report numbers (F2, never with G8).** Importer: CFN or FEI, year, 5-digit sequence. User facility: 10-digit HCFA number, year, 4-digit sequence. Derived as B3 does (first number typed once, then the next; practice numbers start with 7; never reused) (`authority_reports/emdr.py:160`).
- **Recipients.** Each required recipient is a submission to record: "Sent to FDA" and "Sent to the manufacturer" (a new route `MFR_COPY` with its evidence). F11 and F13 (sent to FDA / to the manufacturer, with dates) are derived from those records. For an importer malfunction, the FDA route is not offered. How the copy reaches the manufacturer (e-mail, the same PDF) is the customer's procedure.

### 4.3 Required fields mapped to MDARIX data
FDA's rejection list (authority-forms spec §3.3; Counts sheet: importer 9 = 7 held / 2 derived, status 6 exist / 1 partly / 2 missing; user facility 4 = 2 held / 2 derived, status 1 / 1 / 2).

| Block | Importer | User facility | MDARIX source | Today |
|---|---|---|---|---|
| B5 describe event | Mandatory | Mandatory | Complaint description | Exists |
| D2 procode | Mandatory | — | Product registration | Exists |
| F1 user facility / importer | Mandatory | Mandatory | Derived from the role | **Missing** (section F empty, `forms.py:261-266`; empty XML block, `emdr.py:414-420`) |
| F2 report number | Mandatory | Mandatory | Generator above | **Missing** |
| F4 contact e-mail | Mandatory | Mandatory | US IMPORTER party (`regulatory_reference.py:24-31`); user facility profile (new `USER_FACILITY` party role) | Partly |
| F10 × 4 (clinical, impact, device problem, component) | Mandatory | Optional | Approved IMDRF mappings, "Confirm all codes" (B3 A7) | Exists |
| F7 type + follow-up number | Follow-ups | Follow-ups | Chain | **Missing** |
| F3, F5, F6, F9, F12, F14; F11/F13 | Required if known | Same | Party address and phone; awareness (F6); device age from H4 date or asked (F9); F12 asked; F14 manufacturer party; F11/F13 from recipients | Missing / partly |

The rows come from the workbook's US sheet (rows 115–155). Step 5 exports them to `authority_reports/rules/us_emdr.csv` as data, beside the 161 manufacturer rows.

---

## 5. Everything as rule-register data (B4)

| New or changed register entry | Kind | Held as | Notes |
|---|---|---|---|
| `IN-floor-2` | Reportability floor | Data | Correction of `IN-floor-1`; only `report_types.IN_SERIOUS_ADVERSE_EVENT` gains `days: 15, basis: CALENDAR` and its label |
| `US-IMP-floor-1`, `US-UF-floor-1` | Reportability floor, with `role` | Data | Questions by reference to the US set; `recipients` per rule; own triage tiers |
| `CA-floor-2` (optional) | Reportability floor | Data | Only if B9-D6 is answered |
| eMDR rule book version 2 | Report form rules | Data (CSV, hash pinned) | Adds I-I, I-F, U-I, U-F rows; the M-I and M-F rows stay byte-identical (test) |
| `mvpi-mdae-1.2`, `hc-mdpr-2018-04` | Report form edition | Data (form file + field map + hash) | Picked by the day sent for approval (B4 R-D3); a newer edition is a new version |
| `in-chain-1`, `ca-chain-1` | Report chain rules (what is created when, which fields are required per type) | Data | India: on demand. Canada: Final on Preliminary submission, due on A5 |
| `us-recipients-1` | Who must receive each US report | Data (inside the role floors) | 803.30, 803.40 |
| Catalog ids `CFR803_30`, `CFR803_40` | Sources | `standards.py` + `standards.json` | B4's loader refuses unknown ids |

**Engine changes (small):** (1) the floor name includes the role when not Manufacturer; (2) a floor may list `recipients` per rule, carried into `rules_applied`; (3) a floor's question list may reference another floor's questions (no copies to drift). No change to the Kleene logic, folding, counting or the floor guarantees F1–F12.

**B4 equivalence stays green.** US, EU/NI, GB and Canada `*-floor-1` files are untouched (content hash test). India `IN-floor-1` is still compared with `legacy_v1.py` explicitly at version 1 (B4: the oracle stays valid for version 1 only). The suite runs with every B9 switch on and off.

---

## 6. Gaps, build steps, migration, switches, cuts, sample

### 6.1 Gap table
| # | Gap | Evidence | Step |
|---|---|---|---|
| G1 | India has no legal period (FG-2) | `markets.py:89-90`, `:1040-1045` | 2 |
| G2 | India report type always "Initial"; no follow-up or final | `worksheet.py:621`; generic flag only (`router.py:2220-2237`) | 14 |
| G3 | India: worksheet PDF only, not the official form; no ADRMS sheet | `forms.py:341-549`; no MDAE file in `data/` | 12, 13 |
| G4 | Canada: worksheet PDF only, not the official form | `forms.py:1406-1597`; no HC file in `data/` | 10 |
| G5 | Canada: A5 chosen by hand; no Final created; A4 not carried | `forms.py:1454-1470` | 11 |
| G6 | Canada org facts (A8, A9, s.61.1 notice) not held | authority-forms spec §6.4 | 11 |
| G7 | No reporting role; every tenant is a manufacturer | No role field in `ReportabilitySettings` (`db/models/reportability.py:43-58`) | 3 |
| G8 | No US importer or user facility floor, report type or clock | `markets.py:80-82` | 4 |
| G9 | 3500A section F empty in the worksheet and the XML | `forms.py:261-266`; `emdr.py:414-420` | 6, 7 |
| G10 | eMDR rule book has manufacturer rows only | `emdr.py:153` (`required(kind="M-I")`), `rules/us_emdr.csv` | 5 |
| G11 | No `USER_FACILITY` party role (profile, HCFA number) | `db/models/regulatory_reference.py:24-31, 88` | 3 |
| G12 | No recipient routing (FDA vs manufacturer copy) | — | 8 |
| G13 | FDA's importer and user facility follow-up examples not in fixtures | `tests/fixtures/emdr_examples/` holds only "User Facility Initial.xml" of these | 6 |
| G14 | Catalog lacks 803.30 and 803.40 | `standards.py:79-95` | 1 |
| G15 | Canada foreign incident has no clock (optional) | `markets.py:100-104` | 20 |

### 6.2 Build steps
Three parts, built and shippable in this order: **A India** (the beachhead), **B Canada**, **C US importer and user facility**. Hours include targeted tests. "(db)" = database test; "(unit)" = no database.

| # | Step | Part | Hours | Targeted tests |
|---|---|---|---|---|
| 0 | Branch from B4's tip; one Alembic head `tr27ruleregister`; re-check this spec's lines; CHANGELOG; add scenarios B9-01..B9-30 to `scenario-register.md` | A | 2 | `alembic heads` = 1 |
| 1 | Catalog ids `CFR803_30`, `CFR803_40` in `standards.py` and `standards.json` | C | 1 | `test_standards_unit.py` (the two lists stay identical) |
| 2 | `IN-floor-2` data file (correction, same period) + decision-table rows | A | 4 | `test_b9_india_period.py` (unit): all 3^8 answer sets give the same suggestion, type, notes and folding under v1 and v2; Reportable with a 30-day window → 15 days from the regulation; a 15-day calendar window → the window; pending → earliest. (db) draft under v1 → `409 FLOOR_CHANGED` → re-save → v2; signed v1 unchanged byte for byte; triage dates unchanged |
| 3 | Reporting role: migration `tr28`; `PUT /reportability/roles` (Approver only, reason, audited `REPORTING_ROLE_SET`); engine picks `{market}-{ROLE}-floor`; `recipients` key | C | 8 | `test_b9_roles.py` (db): default Manufacturer; admin alone refused; change audited; a draft re-picks at next save; signed rows unchanged; RLS (`test_rls_coverage.py`); tr28 upgrade, downgrade, upgrade |
| 4 | `US-IMP-floor-1`, `US-UF-floor-1` data files; decision-table rows IMP-1..n, UF-1..n | C | 5 | `test_b9_us_role_floors.py` (unit): every Yes/No/Unknown set of the reused questions; Unknown never No; no 5-day for importers; no malfunction for user facilities; 10 work days counted per US rule |
| 5 | eMDR rule book v2: export I-I, I-F, U-I, U-F rows (workbook rows 115–155 and the shared ones) | C | 3 | `test_b9_rule_book.py` (unit): manufacturer rows byte-identical; FDA's lists (importer 9, user facility 4, follow-ups F1/F2/F7) enforced; register hash bumped with a new version |
| 6 | `emdr.build` section F (F1–F14), F2 generator (FEI/CFN-yyyy-5; HCFA-yyyy-4), F7 follow-up, G and H left out; copy FDA's Importer Initial / Follow-up and User Facility Follow-up examples into fixtures with SHA-256s | C | 10 | Rebuild FDA's examples block by block, XSD-valid; F2 and G8 never both set; numbers never reused; practice 7xxxx |
| 7 | Worksheet section F fields; eSubmitter-layout PDF and official 09/2025 form fill section F | C | 5 | PDF has FDA's F blocks in order; official form ticks F1 and F7; never says FDA generated it |
| 8 | Recipients: "Sent to FDA" and "Sent to the manufacturer" recorded separately (`MFR_COPY` route); F11/F13 derived; importer malfunction has no FDA route | C | 4 | Recipient table (death, serious injury, malfunction × importer, user facility, manufacturer unknown) |
| 9 | Importer and user facility follow-ups on B3's chain, clock per B9-D12 | C | 3 | Numbers 1, 2, 3 without gaps; one open at a time; due date per D12 |
| 10 | Canada official form fill (HC Pub. 110180 AcroForm, 94 fields, pypdf as `fda_3500a.py` does; form file + manifest + field map) | B | 8 | Read-back: every value lands in its named field; record page appended; same snapshot, same bytes |
| 11 | Canada chain: Final auto-created on Preliminary submission, due on A5; Update on demand; Preliminary & Final ends it; A3/A4/A5 carried; E2/E3 required on finals; A8/A9/s.61.1 once per organisation | B | 8 | (db) Preliminary submitted → one Final draft due on A5; none after a Final or P&F; Final refused without E2/E3; A4 carried; re-sign supersedes an unsent Final (fix 4 pattern) |
| 12 | India official MDAE v1.2 fill by position (172 generic field names; a field map checked once by a person against the printed form) | A | 10 | Read-back: each mapped value in its field; every map entry names a real field; record page appended |
| 13 | ADRMS entry sheet (PDF/text, ADRMS screen order, mandatory marks; values from the same snapshot) | A | 4 | All 16 ADRMS mandatory fields present or flagged "enter in ADRMS"; same values as the form |
| 14 | India chain: "Create follow-up" / "Create final", optional next-report date, P2 from the chain, F3 on follow-up and final; P1 = day sent | A | 5 | (db) no auto-create; follow-up and final linked; Final ends the chain; P2 correct; next date labelled "your date" |
| 15 | Screens: role per market (Settings, next to reporting windows); chain cards for India and Canada (reuse B3's `sections/FollowUps.tsx`); section F on the US report page; recipients; floor and role shown on the conclusion | A 4, B 2, C 4 | 10 | vitest per screen; `tsc --noEmit` |
| 16 | Sample: India SAMPLE-RV-10 gets the official form, the ADRMS sheet and a Final after the CAPA (6.6) | A | 4 | `test_sample_story_days.py`, `test_release_0_10_92.py` green; new `test_b9_india_sample_gives_form_and_sheet` |
| 17 | Switches (6.4) | A 1, B 1, C 1 | 3 | Off/on/off per switch: routes 404, buttons hidden, drafts still signable after re-save |
| 18 | Docs: decision tables (India period, IMP, UF tables), user guide, CHANGELOG | A 1, C 1 | 2 | Decision-table doc test |
| 19 | Targeted suites with all switches on and off, **including `test_b4_equivalence.py` and `test_rule_pins_unit.py`**, plus `test_regulatory_decision_tables.py`, `test_market_assessment_api.py`, `test_authority_reports_api.py`, `test_release_0_10_96*.py`, `test_legal_deadlines.py`, `test_intake_rules.py`; ruff; one independent read-only review; fixes | A 2, B 2, C 2 | 6 | All green both ways |
| | **Core total** (A 37, B 21, C 47) | | **105** | |
| 20 | *Optional, needs B9-D6 ⚑:* `CA-floor-2`: foreign incident clock and OD-3 | B | 5 | Decision-table rows; ED-style tests |
| 21 | *Optional:* Canada sample (the Indian sample maker exports to Canada: Preliminary → Final) | B | 3 | Sample tests |
| 22 | *Optional:* user facility annual list aid (the year's submitted reports, for Form 3419) | C | 4 | Year boundary test |
| 23 | *Optional:* next-number suggestion for India P4 and Canada A3 | A/B | 2 | Unit |
| | **Total with options** | | **119** | |

At about 7 build hours a day, the core is about 15 working days. Part A alone (37 h) can ship first and needs no migration.

### 6.3 Migration
**One small additive migration, Part C only: `tr28_trial_market_roles.py`, revision `tr28marketroles`, `down_revision = "tr27ruleregister"`.**
- `reportability_settings.reporting_roles JSONB NOT NULL DEFAULT '{}'` (market → `IMPORTER` / `USER_FACILITY`; absent = Manufacturer). Check: a JSON object.
- `market_responsible_parties` role check gains `USER_FACILITY` (the user facility profile: name, address, contact, HCFA number).
- No data step, no backfill. Downgrade drops the column and restores the check; it refuses while a `USER_FACILITY` party exists (no silent loss).
- **Parts A and B need no migration:** chains reuse `RESPONSE` + `parent_id` (B3 pattern); India's next-report date uses `follow_up_due_on`; frozen files go in `report_snapshots.fields`; the floor code is B4's `floor_code` column. The shared `FOLLOW_UP`/`FINAL` kinds stay for B8 (B3 Q1).
- If the owner wants no migration at all, Part C is cut (B9-D15).

### 6.4 On/off switches (the `feature_set.py` pattern, read on every call)
| Switch | Default | Off means |
|---|---|---|
| `MDARIX_B9_INDIA` | on | The register skips `IN-floor-2` (India back to `IN-floor-1`; drafts re-save, signed rows untouched); official form, ADRMS sheet and chain buttons hidden, their routes 404; today's worksheet stays |
| `MDARIX_B9_CANADA` | on | Official form and chain hidden, routes 404; no Final auto-created; worksheet stays |
| `MDARIX_B9_US_IMPORTER` | on | The Importer role is not offered; a tenant set to Importer is read as Manufacturer (the manufacturer floor asks more and is never later); section F routes 404 |
| `MDARIX_B9_US_USER_FACILITY` | **off** | Same for User facility. Off by default: no customer is a user facility (D4) |

### 6.5 What can be cut (in this order)
1. Step 22 (annual aid). 2. Step 21 (Canada sample). 3. Step 23 (number suggestion). 4. Step 20 (`CA-floor-2`). 5. User facility (the `US-UF-floor`, its PDF route and profile; keeps importer). 6. Importer and user facility follow-ups (step 9; the generic "follow-up due" flag stays). 7. All of Part C (then no migration).

**Never cut:** `IN-floor-2` with its effective-dating tests; B4 equivalence green; the switches; files frozen at approval; second-person approval; recipient routing when importer reports ship; "MDARIX never submits".

### 6.6 How it fits the sample story (India first)
The trial already has an India example: SAMPLE-RV-10, PulseWatch 410 Rev A, a probe that overheated and burned a finger, signed Reportable, MDAE worksheet approved, sent by e-mail, bounced, back for correction (`trial/sample_reports.py:8-14, 500-521`). B9 extends it, with the existing sample organisation "Orbit Medical Devices India (Sample)", Pune:
1. The conclusion shows "15 days (India MDR 2017 Rule 26, starter)" and the floor `IN-floor-2`.
2. The corrected report downloads as the **official MvPI form v1.2**, the **ADRMS entry sheet** and the record page.
3. After the sample CAPA, a **Final** report closes the chain.

This gives Indian makers the story they live: "Is it reportable in India, by when, and here is the form MvPI expects." Optional step 21 adds the same maker's Canadian export. The sample is refreshed in running trials the B3 way (`scripts/refresh_trial_story.py`, idempotent).

### 6.7 Scenarios to add (B9-xx)
India: B9-01 15-day clock from the regulation over a longer window; B9-02 exact 15-day window used; B9-03 draft on v1 refused at signing, re-saved; B9-04 signed v1 unchanged; B9-05 official form values in the right boxes; B9-06 ADRMS sheet lists all 16 mandatory fields; B9-07 follow-up and final on demand, never automatic; B9-08 Final ends the chain; B9-09 importer role changes R1 only. Canada: B9-10 official form filled; B9-11 Final created on Preliminary submission, due on A5; B9-12 none after Final or P&F; B9-13 Final needs E2/E3; B9-14 A4 carried; B9-15 importer A1/A7. US: B9-16 role set by an Approver, audited; B9-17 admin alone refused; B9-18 importer 30 days, no 5-day; B9-19 user facility 10 work days, no malfunction; B9-20 Unknown never No in both; B9-21 F2 formats and never with G8; B9-22 FDA examples rebuilt; B9-23 importer malfunction goes to the manufacturer only; B9-24 death goes to FDA and the manufacturer; B9-25 follow-up numbering; B9-26 user facility hidden while its switch is off. All: B9-27 another tenant's reports and role unseen; B9-28 each switch off/on keeps drafts signable; B9-29 B4 equivalence green; B9-30 routine path stores the role floor in force.

---

## 7. Owner decisions

⚑ = touches regulatory interpretation or signed records: **needs your explicit answer.** "If no answer" is what the build does meanwhile.

| # | Decision | Recommendation (safe) |
|---|---|---|
| B9-D1 ⚑ | India legal period | `IN-floor-2`: 15 calendar days (Rule 26(ii)), awareness day = day 1, as a correction "from the start"; signed records unchanged, drafts re-saved. *If no answer:* build it with the switch on in test only, off in production. |
| B9-D2 ⚑ | India "unexpected" (Rule 26 says suspected *unexpected* serious adverse event) | Keep today's conservative rule: every serious adverse event the device is suspected of is reportable; IN3 stays a note. Consultant to confirm. *If no answer:* unchanged. |
| B9-D3 ⚑ | India recipient | One India report; routes MvPI e-mail and ADRMS (existing), plus "Licensing authority (to confirm)" as a recordable route only; no second obligation until your consultant confirms. *If no answer:* the two existing routes only. |
| B9-D4 ⚑ | India importer | Same floor and 15 days as the licence holder; Rule 38 foreign-action reports not built. *If no answer:* India importer role hidden (manufacturer only). |
| B9-D5 | India follow-up and final | As approved D15: on demand, optional "your date", no legal clock. |
| B9-D6 ⚑ | Canada foreign incident clock and OD-3 | Build optional `CA-floor-2`: the foreign report is due by the end of the day after the corrective-action decision day (inside 48 hours), provisional from awareness until that date is entered; while "in Canada" is Unknown and CA6 is Yes, the foreign clock applies (floor F4, shortest not excluded). *If no answer:* `CA-floor-1` unchanged, step 20 not built. |
| B9-D7 | Canada Final | As approved D16: created when the Preliminary is submitted, due on the A5 date. |
| B9-D8 ⚑ | Who sets the reporting role, and its effect | Per market per tenant; default Manufacturer; set only by an Approver with a reason, audited; applies to drafts at their next save; signed records keep their floor. *If no answer:* Part C not built. |
| B9-D9 ⚑ | Personal data on the forms (Canada D2–D5, India C and D) | As D3: optional entry at the report step, kept only in that report's frozen snapshot, never used by AI or analytics, tenant setting default off; when off, the PDF leaves the boxes blank "enter before sending". *If no answer:* never stored, boxes blank. |
| B9-D10 ⚑ | US importer floor | Reuse US1–US5 word for word; 30 calendar days; no 5-day report; death or serious injury to FDA with a copy to the manufacturer, malfunction to the manufacturer only (803.40). *If no answer:* importer switch off. |
| B9-D11 ⚑ | US user facility floor | US1, US2A–C, US3; no malfunction; 10 work days; death to FDA and the manufacturer, serious injury to the manufacturer (FDA if unknown) (803.30); US3's wording against 803.30 to confirm. *If no answer:* stays off (its default). |
| B9-D12 ⚑ | Importer and user facility follow-up clock (not settled) | Apply the manufacturer's 30 calendar days from receipt of the information (803.56), labelled "starter: until your consultant confirms". *If no answer:* the same, labelled. |
| B9-D13 | Build user facility at all | Yes, last in Part C, switch off by default, cut first if late (D4). |
| B9-D14 | User facility annual report (Form 3419) | Not built (D18); optional list aid only if a user facility customer asks. |
| B9-D15 | Migration `tr28` (role setting, `USER_FACILITY` party role) | Yes, Part C only; Parts A and B need none. |
| B9-D16 ⚑ | Form editions in the register | Pin MvPI MDAE v1.2 and HC Pub. 110180 (April 2018) as form rules "from the start", picked by the day sent for approval (B4 R-D3); a newer edition is a new version. *If no answer:* the same (no older edition exists in MDARIX). |
| B9-D17 | Checking the filled forms | No new dependency: pypdf read-back tests, plus one visual check by you of each filled sample form per edition (screenshot kept with the release evidence). |
| B9-D18 | Switch defaults | India on, Canada on, US importer on, US user facility off. |
| B9-D19 | Sample story | Extend SAMPLE-RV-10 (official form, ADRMS sheet, Final); Canada sample optional. |
| B9-D20 | Build order | Part A India, then B Canada, then C US importer/user facility; each ships alone. |

**Needing your explicit answer:** B9-D1, D2, D3, D4, D6, D8, D9, D10, D11, D12, D16.

---

## 8. Documents to obtain (owner)

| For | Document | Why |
|---|---|---|
| India | The official **MvPI Medical Device Adverse Event Reporting Form, Version 1.2**, from ipc.gov.in, with its release date (the copy read came from nhsrcindia.org; ipc.gov.in did not answer) | The blank form vendored into `data/` and its edition pinned |
| India | **ADRMS User Manual for Stakeholders** (18 Aug 2025) and the **MDAE capture SOP** (3 Feb 2026), current copies; how a licence holder gets an ADRMS account; whether ADRMS accepts XML/E2B | The entry sheet's order and mandatory marks |
| India | The **CDSCO circular of 15 May 2024** (primary copy) and the current **MDR 2017** text of Rules 26 and 38 | B9-D1 to D4 |
| Canada | **Mandatory Medical Device Problem Reporting Form for Industry, HC Pub. 110180** (fillable PDF; confirm no newer edition) and **Incident reporting for medical devices: Guidance document (2021)**; the current submission e-mail address | Form fill, B9-D6, the route |
| US | From your FDA **eMDR Implementation Package** zip: the Importer Initial, Importer Follow-up and User Facility Follow-up example files (XML and PDF) | Step 6 fixtures (your 10 Nov permission for FDA's public examples covers them, please confirm) |
| US | **21 CFR 803.30, 803.32, 803.33, 803.40, 803.42** current text (ecfr.gov); **Form FDA 3419** only if step 22 is wanted | B9-D10 to D12, D14 |
| All | Your consultant's confirmation of each item marked "to confirm" (section 9) | Starter marks can then be lifted |

---

## 9. To confirm with your consultant
India: Rule 26 period and counting; "unexpected" (B9-D2); the recipient (MvPI, licensing authority, or both); the importer's duty outside Rule 38; whether "Trend" reports are owed; whether MvPI acknowledges and what counts as acceptance. Canada: the foreign 48-hour start event; the E1 note and C4 iii on the form; the e-mail address. US: US3's wording for user facilities (803.30); importer and user facility follow-up clocks; how a manufacturer cites a received importer or user facility report number; whether a malfunction-only importer report to the manufacturer uses Form 3500A.

## 10. What I did not check
- B4, B5 and B7 branches were not read; B4's engine and file names are taken from its approved spec. Step 0 re-checks every line here on B4's tip.
- The MvPI field map (172 generic names) and the Canada field names were not opened; the 10 h and 8 h estimates assume one person-checked map each.
- The workbook was read for the Counts sheet and US rows 115–155 only; India and Canada rows were taken from the spec's summary.
- No legal source was re-read; no database was queried. Hours are estimates from B3 and B4 steps of similar size.

---

## Owner approval (11 Nov 2026)
The owner replied **"approve B9 spec"**: every recommendation in section 7 is accepted as written, including all flagged decisions (B9-D1, D2, D3, D4, D6, D8, D9, D10, D11, D12, D16). In short:
- D1: `IN-floor-2`, 15 calendar days, awareness day = day 1, correction "from the start"; signed records unchanged, drafts re-saved.
- D2: today's conservative India rule kept; IN3 stays a note.
- D3: MvPI e-mail and ADRMS, plus "Licensing authority (to confirm)" as a recordable route only.
- D4: India importer uses the same floor and 15 days; Rule 38 not built.
- D6: optional `CA-floor-2` is built (step 20), after the core of Part B; it stays fourth in the cut order.
- D8: role per market per tenant, default Manufacturer, Approver with reason, audited, drafts re-pick at next save, signed rows keep their floor.
- D9: personal data optional at the report step, only in the frozen snapshot, never to AI or analytics, tenant setting default off; off = boxes blank "enter before sending".
- D10, D11, D12: US importer and user facility floors and follow-up clock as recommended, all marked starter.
- D16: MvPI MDAE v1.2 and HC Pub. 110180 (April 2018) pinned "from the start".
- Unflagged D5, D7, D13–D15, D17–D20 as recommended.
- Every legal citation stays "starter, for your consultant to confirm". Optional steps 21–23 only if time allows.
- Still for the owner (section 8): the official documents, and confirmation that his 10 Nov permission for FDA's public eMDR examples covers the importer and user facility examples. Until confirmed, step 6 uses only the files already in the fixtures plus the zip's examples for local tests, not shipped.

---

## Build status (run 1, 11 Nov 2026)

Branch `feat/b9-markets` in worktree `trial-093`, from B4's tip `76eebdde`. Local commits only, never pushed. CHANGELOG
section `## [0.11.00] - not released yet` (no 0.11 number existed in this repo). Scenarios B9-01..B9-30 added to
`scenario-register.md` (NOT RUN). One Alembic head: `tr27ruleregister` (Part A needs no migration).

**Part A (India): mostly built; NOT complete.**

| Step | Status |
|---|---|
| 0 | Done |
| 2 `IN-floor-2` | Done: data file (correction of IN-floor-1, carries `"switch": "MDARIX_B9_INDIA"`); decision-table text and VR-17; B4 equivalence still compares IN-floor-1 with `legacy_v1` at version 1 |
| 12 MvPI MDAE v1.2 fill | Done. Blank form = nhsrcindia.org copy (SHA-256 `eaf7d7c8…cb14`), to replace with the ipc.gov.in copy. **Field map made by position, NOT checked by a person (B9-D17)** |
| 13 ADRMS sheet | Done (`form=adrms`) |
| 14 India chain | Done (`POST /api/v1/reports/{id}/india-chain`; P2 from the chain, P1 = day sent; F3 enterable) |
| 15 India screens | **Not started** (role setting is Part C; India chain card, Official form / ADRMS buttons, floor shown on the conclusion) |
| 16 Sample | Part: SAMPLE-RV-10 downloads as the official form and the ADRMS sheet. **Not built:** the Final after the sample CAPA, and the refresh in running trials |
| 17 Switches (India) | Done: `feature_set.switched_on`, session `b9.*`, India chain route 404 when off |
| 18 Docs (India) | Part: CHANGELOG, decision tables. User guide not written |
| 19 (India) | Part: suites on and off (below), ruff on changed files. **Independent read-only review not run** |

**Parts B (Canada) and C (US importer / user facility): not started.** The HC Pub. 110180 download from canada.ca
failed (connection reset); try again or ask the owner for the file.

Tests seen passing (POSTGRES_DB=mdarix_b2_test):
- Unit, India on: `test_b9_india_period.py`, `test_b4_equivalence.py`, `test_rule_register_unit.py`, `test_b4_window_floor.py`, `test_rule_pins_unit.py`: 69 passed; `test_regulatory_decision_tables.py`: 183 passed (on and off); `test_b9_mvpi_form.py`: 6 passed.
- Unit, India off: `test_b4_equivalence.py test_rule_pins_unit.py test_rule_register_unit.py test_b4_window_floor.py test_regulatory_decision_tables.py test_legal_deadlines.py test_intake_rules.py test_market_assessment_rules.py`: 291 passed.
- DB: `test_b9_india_period_db.py` 2 passed; `test_b4_register_api.py` + `test_b4_effective_dating.py` 12 passed (on), register API 5 passed (off); `test_b9_india_chain.py` 3 passed; `test_b9_switches.py` + `test_b4_register_api.py` 8 passed; `test_b9_india_chain.py test_authority_reports_api.py test_release_0_10_96.py` 23 passed + chain fix.
- Story set: `test_sample_story_days.py test_release_0_10_92.py test_getting_started_part1.py test_flagship_walkthrough.py test_release_0_10_97.py`: 22 passed, 1 xfailed.
- Not run: `test_market_assessment_api.py`, `test_release_0_10_96*.py` other than `test_release_0_10_96.py`, vitest/tsc (no frontend change yet).

## Build status (run 2, 11 Nov 2026)

Branch `feat/b9-markets` (worktree `trial-093`), local commits only. Still one Alembic head `tr27ruleregister`; no migration in Parts A or B.

**Part A (India): complete except the sample Final (step 16 rest), which waits for the owner (question below).**

| Step | Status |
|---|---|
| Switch-leak fix | Done: India P1/P2 derivation and the 422 `FOLLOWS_CHAIN` follow `MDARIX_B9_INDIA` (off = typed, as before); off/on/off test |
| 15 India screens | Done: chain card (follow-up/final on demand, cancel while unsent) on the report page and the classic drawer; Official MvPI form and ADRMS sheet buttons; the conclusion reads its own floor's words (IN-floor-2: "15 days (India MDR 2017 Rule 26, starter)") |
| 16 Sample | Official form + ADRMS sheet done (run 1). **Final after a CAPA: not built** (owner question 1) |
| 18 Docs | Done: user guide (India form, ADRMS sheet, chain; the field map awaits one person's check), CHANGELOG |
| 19 Part A | Suites on and off, ruff, one independent read-only review: 5 findings, 4 fixed, 1 open (below) |

**Part B (Canada): built except step 10's form file; step 20 (`CA-floor-2`) not started.**
- Step 10: `hc_mdpr.py` + `data/hc_forms` (manifest with no file, empty field map). canada.ca download failed again (connection reset, 11 Nov). Route answers `409 FORM_FILE_NEEDED`; the button hides until the file is in place; read-back tests skipped.
- Step 11: Final made when the Preliminary is recorded as submitted (due on A5's date; a corrected Preliminary moves an unsent Final's date, audited); updates on demand, one open; nothing after a submitted Final or P&F; A4 carried from the chain's authority reference, A3 from the Preliminary, A5 previous date from the last submission; A6 = day sent; E2/E3 gate; Canada's Final cannot be cancelled (`FINAL_IS_OWED`). **Not built:** A8/A9/s.61.1 "once per organisation" (needs storage: no column exists, owner question 2); A1/A7 from the role (Part C).
- Canada screens and switch: done (`b9.canada`; off = no Final, routes 404, A4/A5 previous/A6 typed).

**Fixes found on the way:** India's P1 (MUST + filled at Send) blocked Send for approval on the new navigation: P1 and A6 are now INITIAL like FDA's B4. Audit fix 4 now reaches India and Canada children.

**Review findings (independent read-only agent, on the whole B9 diff):** fixed: (1) India conclusions signed before B4 (no floor code) now count and read by version 1, never IN-floor-2's 15 days (`assessments.signed_floor`, also in intake's signed clocks); (3) cancelled Canada Final could never come back: cancel refused; (4) Final's date stale after a corrected Preliminary: updated, audited; (5) ADRMS "Patient involved" now Yes only on death/serious injury (B8), else "enter in ADRMS". **Open (2, medium):** the official MvPI/HC PDFs are filled at download from today's blank form and map, not frozen at approval (spec §5 form-edition register entries `mvpi-mdae-1.2`, `hc-mdpr-2018-04` not built). Recommended next: at Send, store the rendered form's SHA-256 + edition + map version in `report_snapshots.fields` and refuse a mismatching re-render.

Tests seen (POSTGRES_DB=mdarix_b2_test): step 19 set (24 files incl. B4 equivalence, rule pins, decision tables, market assessment API, all 0.10.96, story set, B9 tests): **on 369 passed, 2 skipped, 1 xfailed**; **India+Canada off: 359 passed, 11 failed** — the 11 are B9 feature tests that assume the default (on) switch plus the c4 meter test (now made switch-aware); every non-B9 test passed off. vitest `authorityReports.test.tsx` 14, linkTable + UserGuidePage 27; `tsc --noEmit --noUnusedLocals` clean.

## Build status (run 3, 11 Nov 2026)

Branch `feat/b9-markets` (worktree `trial-093`), local commits only: `9a4446ac` (review finding 2), `223a65f6` (step 1),
`c56e7c87` (steps 3-4). One Alembic head: **`tr28marketroles`** (test DB `mdarix_b2_test` now at tr28).

**Review finding 2 (files frozen at approval): fixed.** Register entries `mvpi-mdae-1.2` (blank form SHA-256 + field
map hash) and `hc-mdpr-2018-04` (form file awaited: `file` null, map hash of today's empty map), kind REPORT_FORM, from
the start. At Send for approval the edition (picked by the organization's day) goes into the snapshot and its
fingerprint (`form_edition`). At approval (route and sample maker) the filled official PDF is kept in
`report_snapshots.fields` (`official_pdf` base64 + `official_sha256`) and the SHA-256 goes into the
`REPORT_SNAPSHOT_APPROVED` audit details. Downloads serve those bytes (a hash mismatch is `409
OFFICIAL_FORM_CHANGED`). Reports approved before this change (and any Canada report until the form file exists) keep
no frozen form: the official form is filled at download and marked "DRAFT - NOT THE APPROVED FILE" (record page header,
watermark, PDF title). `register.pin_problems` now also checks a form edition's blank file and field map. With India or
Canada off, report details return no `india_chain` / `canada_chain` and `/cancel` on a chain child answers 404.
Shortcut noted in code: the frozen PDF (~330 KB base64) sits in the snapshot JSONB.

**Part A: complete except step 16's sample Final (owner question, unchanged). Part B: complete except the HC form file
(owner), A8/A9/s.61.1 storage (owner) and step 20.**

**Part C (US importer / user facility): partly built.**

| Step | Status |
|---|---|
| 1 Catalog `CFR803_30`, `CFR803_40` | Done (both lists, starter) |
| 3 Reporting role | Done: `tr28marketroles` (upgrade, downgrade, upgrade run; downgrade refused while a USER_FACILITY party exists, with `row_security = off` so RLS can never hide one); `PUT /api/v1/complaints/reportability-roles` (regulatory-approve permission, reason >= 10, audited `REPORTING_ROLE_SET` old/new); settings show `reporting_roles` + `roles_offered`; roles offered: US Importer, US User facility (switch), India Importer, Canada Importer; a role behind an off switch reads as Manufacturer; the assessment save/sign picks `{market}-{ROLE}-floor` (via `seen["roles"]`), so a draft re-picks at next save (409 FLOOR_CHANGED at signing otherwise); USER_FACILITY party role accepted for US only while its switch is on. Legacy planes step tr28 added |
| 4 Role floors | Done: `US-IMP-floor-1`, `US-UF-floor-1` (switch-gated), questions by reference (`questions_from`), `recipients` per rule carried into `rules_applied`; decision tables IMP-1..6, UF-1..5, VR-19/20; role report types in `REPORT_TYPES` |
| 5 eMDR rule book v2 | **Not started** |
| 6 `emdr.build` section F, F2 generator, FDA examples in fixtures (owner's zip) | **Not started** |
| 7 Worksheet / PDFs section F | **Not started** |
| 8 Recipients (`MFR_COPY` route, F11/F13) | **Not started** (the floor data already names the recipients) |
| 9 Importer / user facility follow-ups | **Not started** |
| 11 rest: Canada A1/A7 and India R1 from the role | **Not started** (role now exists: add a worksheet source reading the role) |
| 15 Part C screens (role in Settings, section F, recipients) | **Not started** |
| 17 US switches | Part: role offered/read per switch; section F routes do not exist yet |
| 19 Part C review | **Not run** |
| 20 `CA-floor-2` | **Not started** |

Known limits (to handle in later steps): intake triage clocks and the watch's pending clocks still read the
manufacturer floor for a role tenant (safe direction: shorter or equal); a signed importer US conclusion creates an
FDA_3500A report whose section F is still empty (steps 6-7).

Tests seen (POSTGRES_DB=mdarix_b2_test):
- Finding 2: `test_b9_frozen_forms.py test_b9_mvpi_form.py test_b9_hc_form.py test_rule_pins_unit.py
  test_rule_register_unit.py`: 40 passed, 2 skipped (HC read-back, no form file). `test_b9_india_chain.py
  test_b9_canada_chain.py test_authority_reports_api.py test_release_0_10_96.py test_b9_switches.py
  test_b4_register_api.py test_sample_story_days.py test_release_0_10_92.py`: 49 passed, 1 xfailed.
- Step 1: `test_standards_unit.py` 15 passed.
- Steps 3-4 (defaults): `test_b9_roles.py test_b9_us_role_floors.py test_rule_register_unit.py test_rule_pins_unit.py
  test_regulatory_decision_tables.py`: 233 passed; `test_regulatory_reference_unit.py test_reporting_capa_api.py
  test_b4_effective_dating.py test_b4_register_api.py test_market_assessment_api.py test_b4_equivalence.py
  test_b4_window_floor.py test_intake_rules.py test_legal_deadlines.py`: 99 passed + 2 register-API failures, fixed
  (summary counted off-switch rules; expected floor list) and re-run: 5 passed (defaults) and 5 passed (importer off,
  user facility on).
- Flipped switches (MDARIX_B9_US_IMPORTER=off, MDARIX_B9_US_USER_FACILITY=on): `test_b4_equivalence.py
  test_regulatory_decision_tables.py test_rule_register_unit.py test_rule_pins_unit.py test_b9_us_role_floors.py
  test_b4_effective_dating.py test_market_assessment_api.py`: 272 passed.
- Not run this run: India/Canada-off variants of the finding-2 tests (the off checks are inside the new tests), vitest
  (no frontend change except `standards.json`), the step 19 suite as a whole.

## Build status (run 4, 11 Nov 2026)

Branch `feat/b9-markets` (worktree `trial-093`), local commits only: `83b57c29` (steps 5-6), `63b588c4` (steps 6-8, 11
rest), `825bef82` (step 9), `48d2e041` (step 15 Part C), `fab182b6` (review fix 1 + CHANGELOG). One Alembic head
`tr28marketroles` (no new migration).

**Part C (US importer / user facility): built, except step 20 and the items below.**

| Step | Status |
|---|---|
| 5 eMDR rule book v2 | Done: `emdr-rule-book-2` (correction of v1, from the start), `rules/us_emdr_v2.csv` (201 rows, LF via `.gitattributes`); manufacturer rows = v1 byte for byte; FDA's lists (I-I 9, U-I 4, I-F/U-F F1 F2 F7) |
| 6 eMDR section F, F2, F7 | Done: F1-F14 placed as FDA's examples, G/H left out, F2 per role never with G8, numbering per role (practice 7xxxx/7xxx). FDA's Importer Initial, Importer Follow-up, User Facility Follow-up XML in `tests/fixtures/emdr_examples` with SHA-256 (**local tests only; owner's permission still to confirm**). All four examples rebuilt block by block and XSD-valid |
| 7 Worksheet / PDFs | Done: section F on a role's report (G, H, front number dropped, 404 on their fields; F 404 on a manufacturer's); eSubmitter-layout PDF F1-F14; official 09/2025 form F1, F7, F11-F13 ticked, F2-F6, F9, F10, F14 filled |
| 8 Recipients | Done: `MFR_COPY` route; routes follow the signed rule's recipients (importer malfunction: no FDA route); each send recorded apart against the approved snapshot; state follows FDA's route. F11/F13 come from the recipients, dated the day sent for approval (the file is frozen at approval), not from the recorded sends |
| 9 Follow-ups | Done: share F2, F7 "Follow-up #n", send F1/F2/F7, no H2; clock 30 days labelled starter (B9-D12) |
| 11 rest | Done: India R1, Canada A1 from the role (typed again with the switch off) |
| 15 Part C screens | Done: role per market in Reporting windows (approver + reason); floor, role, recipients, follow-up clock on the report page. Not done: floor/role on the market-assessment conclusion card (report page only) |
| 17 US switches | Done: off = role read as Manufacturer (section F fields 404, no MFR_COPY, manufacturer file) |
| 19 Part C | Suites on/off run, ruff, one independent review (below) |
| 20 `CA-floor-2` | **Not started** |

**Review (independent read-only agent, Part C):** finding 1 (high, multi-recipient state: a sent report went back to
Approved; rejected resend blocked) fixed in `fab182b6`. Open, low/medium, for the owner or the next run:
(2) a manufacturer's US decision guide lists the role report types (`decision_guides/router.py:324`, `rules.py:245`);
(3) "FDA if the manufacturer is unknown" reads the organization's US MANUFACTURER party, not this device's maker
(inherited from B3's single-party D3; consultant view needed);
(4) routes read the live conclusion, not a recipient list frozen at Send; (5) switching a role off after approval
reads the report as a manufacturer's (spec 6.4 vs "importer malfunction never to FDA"); (6) F11/F13 dated the day
sent for approval (owner/consultant OK needed); (7) a typed F2 equal to an earlier manufacturer number is not refused;
(8) no paper route for user facilities (803.12(b)) beside EMDR. Run 3's limit unchanged: intake triage and watch
pending clocks still read the manufacturer floor for a role tenant (safe direction).

Tests seen (POSTGRES_DB=mdarix_b2_test): step 19 set (B4 equivalence, rule pins, register, decision tables, market
assessment API, authority reports API, all 0.10.96, legal deadlines, intake rules, story set, eMDR, B4 register/
effective dating/window floor, all `test_b9_*`): **all four on: 465 passed, 2 failed, 2 skipped, 1 xfailed**; **all
off: 418 passed, 4 failed, 1 xfailed**. Failures: `test_sample_story_days` day-0 (RV-09 -9 vs -10: run at 04:2x UTC,
when New York is still on 10 Nov; no deadline or sample code changed; re-run after 05:00 UTC); `test_b9_switches`
session test (on: the env forces user facility on; passes with defaults); off: the India route test (assumes the
default on, as run 2 noted) and my R1/A1 test (fixed, 9 passed off). After the review fix:
`test_b9_us_importer_report.py` 1 passed; authority API + 0.10.96 + 0.10.96 follow-ups + India/Canada chains 40 passed.
vitest `authorityReports.test.tsx` + `reportingCapa.test.tsx` 31 passed; `tsc --noEmit` clean.

**Is all of B9 complete apart from the owner's open items?** No: step 20 (`CA-floor-2`, approved B9-D6) is not built,
and review items 2-8 above are open. Owner items unchanged: India sample Final, Canada A8/A9/s.61.1 storage, HC form
file, permission for FDA's importer/user facility example files.

## Build status (run 5, 11 Nov 2026)

Branch `feat/b9-markets` (worktree `trial-093`), local commits only, from `fab182b6`: `af980194` (review 1-2),
`49c010e3` (review 3), `d91b2f15` (review 4), `aee6458d` (review 9), `87a2a1fa` (review 7), `017653ba` (review 8),
`fb30d94d` (review 5, step 15 rest), `ff307082` (step 20 + CHANGELOG), `79e6d3f9` (step 20 test fix). One Alembic head
`tr28marketroles` (no new migration).

| Item | Status |
|---|---|
| 1-2 Signed role and frozen recipients | Done: Send for approval stores `us_role` and `us_recipients` in the snapshot (and its fingerprint); past approval `us_role` reads the approved snapshot, routes and the recipient list read the frozen list; a follow-up reads its chain's role. Reports approved before this change: the type's role, live recipients (B9 unreleased, so test data only) |
| 3 F2 vs earlier numbers | Done: unique across the front-page number and F2; a generated number skips the other role's |
| 4 Decision guide types | Done: `decision_guides.rules.guide_types` leaves out the role floors' types (screen and test matrix) |
| 5 Floor and role on the conclusion card | Done: `floor_code` on every version; `role` on the signed one (US: from its floor; India/Canada: the organization's role in the market) |
| 6 Intake triage / watch pending clocks by role floor | **Not built (not small)**: needs a roles argument through `intake.rules.provisional_deadlines` / `_provisional` / `earliest_report`, `assessments.markets_summary` (5 callers: reportability service x2, assessment router x2, disposition router) and `trial/open_deadlines.py`. Safe direction unchanged (manufacturer floor is shorter or equal) |
| 7 Register pins on Linux | Done: `eol=lf` for `backend/app/rule_register/data/**`, `backend/app/authority_reports/rules/**`, `data/mvpi_forms/*.json`, `data/hc_forms/*.json`; text pins hashed with LF; `emdr-rule-book-1` re-pinned once: sha256 `05ee5b09…0c4f` → `a3208bb0…66c6`, content hash `sha256:326e8fdc…` → `sha256:3c76b467…`. No other register entry changed |
| 8 Switch-aware switch tests | Done (passes defaults, all on, all off) |
| 9 Story test day 0 at 04:2x UTC | Reproduced at 04:40 UTC on B4's tip (temporary worktree at `76eebdde`, removed) and on B9: **pre-existing**. Day 0: the code is right (RV-09 counted in New York, still the previous day before 05:00 UTC); the test now expects New York's count. With that fixed, day 29 also failed at 04:4x on both: the sample clock moved times by 24-hour days, so after the summer-time change an end-of-day deadline sat an hour early. Fixed in code (`trial/sample_clock.keep_current` moves whole days on the organization's wall clock) and the test ages the same way; seen passing at 04:47 UTC (the failing hour) |
| List only | User facility paper route (803.12(b)), for the consultant |
| 20 `CA-floor-2` | **Partly done**: data file (correction from the start, `MDARIX_B9_CANADA`, starter), foreign report 1 calendar day from awareness = provisional "end of the day after the corrective-action decision day", CA5 Unknown + CA6 Yes → foreign clock, decision table CA-11, VR-18, OD-3 text, effective-dating unit tests, signed CA-floor-1 rows keep version 1, B4 equivalence compares version 1 explicitly. **Not built:** entering the corrective-action decision day to re-anchor the clock (needs an input on the Canada assessment and a stored date; no column exists: JSONB on the assessment row or a new field, owner/next run) |

Tests seen (POSTGRES_DB=mdarix_b2_test, after 05:00 UTC unless noted):
- Step 19 suite (`scratchpad/step19-run5.sh` = run 4's set + `test_decision_guides_api.py`, `test_b9_signed_role.py`, `test_b9_number_reuse.py`, `test_b9_canada_foreign.py`): **all four on: 490 passed, 1 failed, 2 skipped, 1 xfailed** (the failure: `test_b9_us_role_floors` expected CA-floor-1 for a Canada importer; fixed in `79e6d3f9`, file re-run 7 passed with user facility on and with Canada off); **all four off: 446 passed, 1 xfailed, 0 failed**.
- Fails-without-fix checks: review 1-2 (`test_b9_signed_role.py` failed with the fix reverted), review 3 (`test_b9_number_reuse.py`), review 4 (guide test), review 9 code (story test failed at 04:47 UTC with the clock fix reverted).
- `test_sample_story_days.py test_release_0_10_92.py`: 10 passed, 1 xfailed at 04:48-04:50 UTC (the failing hour).
- Canada chain feature tests fail with Canada off (they assume the default on, as run 2 noted): not in the off set.
- vitest `marketAssessment.test.tsx` 13 passed; `tsc --noEmit` clean; ruff check/format clean on changed files.
- Scenarios B9-31..B9-37 added to `scenario-register.md` (NOT RUN).

**Is all of B9 complete apart from the owner's open items?** No: two things remain besides the owner's items: step 20's
corrective-action decision day entry, and review item 6 (role floor in intake triage and the watch's pending clocks).
Owner items unchanged: India sample Final; Canada A8/A9/s.61.1 storage; the HC form file; F11/F13 dates; "manufacturer
unknown"; permission for FDA's importer/user facility example files.

## Build status (run 6, 11 Nov 2026)

Branch `feat/b9-markets` (worktree `trial-093`), local commits only, from `79e6d3f9`: `d9143855` (review 6),
`40ebb91f` (step 20 decision day + CA-floor-2 label fix + CHANGELOG), `20f9d65f` (merge of the sample-clock fix from
the big-bang line), `ff09fb4b` (step 20 test with switches off). One Alembic head `tr28marketroles` (no new migration).

| Item | Status |
|---|---|
| Review 6: role floor in triage and the watch | **Done.** The tenant's roles (`reportability.service.reporting_roles`, switch-filtered) pass through `intake.rules.provisional_deadlines` / `_provisional` / `earliest_report`, `assessments.floor_at` and `markets_summary` (all 5 callers: watch list, `clocks_for`, assessment detail, sign, disposition), the triage list (`intake.service._deadline_context`), the Case check chip (`intake.router._case_clock`) and `trial/open_deadlines.py`. User facility: 10 work days (803.30) at every tier, pending or answered; importer: 30 days, never 5 work days; manufacturer unchanged; a role switched off reads as Manufacturer (today's clocks) |
| Step 20: corrective-action decision day | **Done.** Stored as its own audit event `CA_CORRECTIVE_ACTION_DAY_SET` (table `audit_events`, entity = the complaint; `reason` = why, `actor_ref`/`created_at` = who/when, `details.assessment_id` + `version` = the Canada conclusion it was entered on, `old_values`/`new_values` = the day). Pattern followed: a later fact recorded in the append-only, hash-chained audit trail and read back as a fact, as `signing_commit` reads its receipt event. The signed row is never written (test: byte-identical columns); a correction is a new event, the latest counts. Route `POST /api/v1/complaints/{id}/market-assessments/CA/corrective-action-day` (regulatory review or approve; reason ≥ 10; no future day; 409 `NOT_FOREIGN_REPORT` unless the signed conclusion is reportable `CA_FOREIGN`; 422 `NOTHING_TO_CHANGE`; 404 while `MDARIX_B9_CANADA` is off). Once entered the foreign clock counts from that day (due by the end of the next day) on the watch, triage and card, no longer provisional; an unsent (not submitted) Canada INITIAL report takes that date (`due_provisional` false). Screen: one date + reason on the Canada conclusion card, flat (G-2), "(provisional)" until entered. No migration |
| Found and fixed | `CA-floor-2`'s `CA_FOREIGN` label (185 chars) did not fit `complaint_market_assessments.window_name` (160): saving a Canada foreign assessment failed with a database error. Label shortened (the provisional words stay in the notes), content hash renewed (unreleased: `sha256:16a1548a…` → `sha256:375ae51b…`), and a unit test now checks every floor's labels fit |
| Sample-clock fix to the big-bang line | **Done.** `aee6458d` cherry-picked onto `release/bigbang-0.10.96` as `e52c120c`; `test_sample_story_days.py` there: 4 passed (06:0x UTC). Merged forward `--no-ff`: hardening `58b80e7d`, B7 `264f2aa7`, B5 `ab1eae92`, B4 `cc2470d4`, B9 `20f9d65f` (no conflict: B9 already held the identical change). **B3 (`feat/b3-emdr-0.10.96`, checked out in trial-094) not synced: to do when that worktree is free** |

Limits (for the owner/consultant, not blocking): the decision day is read from the audit trail, which has no
entity index (a `shortcut:` comment says when to add one); a conclusion re-signed after the day was entered keeps the
day (it is per complaint), but a re-sign resets an unsent report's date to the signed row's due date until the day is
entered again; a decision day before awareness is accepted (gives an earlier, overdue date).

Tests seen (POSTGRES_DB=mdarix_b2_test, 06:02–06:49 UTC, `scratchpad/step19-run6.sh` = run 5's set +
`test_b9_role_pending_clocks.py`, `test_b9_canada_decision_day.py`): **all four on: 501 passed, 2 skipped, 1 xfailed,
0 failed**; **all four off: 454 passed, 1 xfailed, 1 failed** (my decision-day refusal test assumed Canada on; fixed in
`ff09fb4b`, then the two new files with all off: 8 passed; the decision-day file with defaults: 3 passed). Fails
without the fix: review 6's triage/watch test failed (5 vs 10 work days) with the code reverted. vitest
`marketAssessment.test.tsx` 14 passed; `tsc --noEmit` clean; ruff check/format clean on changed files.

**Is all of B9 complete apart from the owner's open items?** **Yes.** Every core step (0-19), step 20 and the
review items are built and tested. Left for the owner only: India sample Final; Canada A8/A9/s.61.1 storage; the HC
form file; F11/F13 dates; "manufacturer unknown"; permission for FDA's importer/user facility example files; plus the
consultant list items (user facility paper route 803.12(b)). B3 line still needs the sample-clock merge.
