# B8: EU MIR and GB MIR for exporters. Execution plan

Version 1, 11 Nov 2026. **APPROVED by the owner on 11 Nov 2026 (see "Approval record").** Plan only: no code was changed, no test was run, no database was read. Per the owner's automatic chain (11 Nov: B9 → **B8** → B9b → B6), B8 starts when B9 is complete, and only after the owner approves this plan. Decisions marked **⚑** touch regulatory interpretation or signed records: they need the owner's explicit answer. Each ⚑ says what the build does **if no answer arrives** (always the safer path).

- **Sources:** `authority-forms-spec/spec.md` (§4 EU, §5 GB, §8, §9 phases 4 and 5, §10, D10–D14, D17; decisions D1–D18 approved 6 Nov, `development-cycle-1.md` line 7), `authority-forms-mapping.xlsx` (sheets "EU MIR 7.3.1", "GB MIR 7.2.1", "Counts", read with a small standard-library reader), `b3-emdr/B3-execution-plan.md` (chain, frozen files, 3 clicks, owner decisions), `b4-rule-register/spec.md` (approved; rules as data, R-D3 form editions by the day sent for approval), `b9-markets/spec.md` (approved; format, switches, D9 personal data), `master-sequence-proposal.md` (item 13, line 90).
- **Code read** (read-only, `git show` / `git grep`): branch `feat/b4-rule-register` (tip `76eebdde`). Every `file:line` below is on that branch, under `backend/app/` unless shown. B9 is being built on `feat/b9-markets` (5 commits at the time of writing); section 2.3 lists what it adds that B8 uses. Step 0 re-checks every line on B9's tip.
- **Regulatory text:** only what the planning files and code already hold. Every legal citation is **"starter, for your consultant to confirm"**.
- **Not in B8:** EUDAMED (vigilance module not live), EU/GB FSCA and trend reports (D18), periodic summary reports, national NCA web portals, MHRA's MORE API, Canada, India and US work (B9), other countries (B9b).

---

## 1. Purpose, in plain words

A manufacturer that sells in Europe or Great Britain must report a serious incident to the authority of the country where it happened. The EU uses the Commission's **Manufacturer Incident Report (MIR) 7.3.1**. Great Britain uses MHRA's **GB MIR 7.2.1**, entered only through MHRA's MORE portal. Northern Ireland uses the EU form, also through MORE.

Today MDARIX gives a filled **worksheet PDF** for both. The person then retypes every value into the official PDF (EU) or into MORE (GB). There is one report per market, the report type is picked by hand, and nothing follows it.

**B8 gives the customer the files the authorities take:**
- **EU:** the MIR **XML**, valid against the Commission's schema for its report type, plus a **PDF in MIR section order**. The XML imports into the official MIR PDF (D10, approved).
- **GB:** the **GB MIR XML** for upload into MORE, plus a **PDF record copy**. MHRA does not accept a PDF (D11, approved).
- **A report chain:** Initial, then Follow-up reports, then a Final, all linked and sharing one reference. When an Initial or a Follow-up is recorded as submitted, MDARIX **creates the next Follow-up draft automatically**, due on the date the report itself promised (1.2f) (D14, approved).

**MDARIX prepares; the customer submits.** For every report: MDARIX fills the form from held data, asks only for what it does not hold, freezes both files at approval, and records what the customer sent, when, by which route, and the authority's answer. MDARIX never submits (authority-forms spec §2.6).

| Report | Who files | What MDARIX prepares | What is signed | What is audited |
|---|---|---|---|---|
| **EU MIR** (Initial; Follow up; Combined initial and final; Final (Reportable incident); Final (Non-reportable incident)) | The manufacturer, or its EU authorised representative | MIR 7.3.1 XML per type (SB-11252 schemas) + MIR-layout PDF; the NCA from the incident country; the next Follow-up draft on submission | The EU conclusion (existing e-signature, with B4's floor code); the report snapshot, including the XML's SHA-256 (second-person approval, password + MFA) | Conclusion signed; report created; files frozen; approved; submission recorded; next report created automatically; type changed |
| **GB MIR** (same five types) | The manufacturer, or its UK Responsible Person | GB MIR 7.2.1 XML per type, for MORE upload + PDF record copy | Same | Same |
| **Northern Ireland** | Same as EU | EU MIR XML + PDF; route "MHRA MORE (EU form)" | Same | Same |

---

## 2. What exists today

### 2.1 Reportability (unchanged by B8)
| Item | Evidence | B8 |
|---|---|---|
| EU/NI and GB floors as register data | `rule_register/data/EU-floor-1.json`, `GB-floor-1.json`; `rule_register/register.py:57` (`FLOOR_RULES`) | **Unchanged.** Content hashes stay; B4 equivalence stays green |
| EU and GB report types and periods (2, 10, 15 days) | `reportability/markets.py:85-93` | Unchanged |
| Northern Ireland belongs to the EU market | `markets.py:42-55` (`EU_NI` with "Northern Ireland", "NI"); EU parties are read as market `EU` (`authority_reports/router.py:1272`) | Unchanged; B8 only adds the MORE route for NI |
| The UK named whole is asked, never guessed | `reportability/rules.py:141-150` | Unchanged |

### 2.2 Authority reports
Paths: `F` = `authority_reports/forms.py`, `W` = `authority_reports/worksheet.py`, `R` = `authority_reports/router.py`, `M` = `db/models/authority_reports.py`.

| Item | Exists today (evidence) | Gap |
|---|---|---|
| EU MIR worksheet form | `EU_MIR` (`F:1028-1234`): every MIR field in order, `must_in` per report type, the five types (`F:558-560`), type field `1_2E` (`F:1073`); starter, new navigation only (`F:1626`, `F:1645`) | No XML. Mandatory rules are hand-coded, not a rule book |
| GB MIR worksheet form | `GB_MIR` (`F:1236-1391`): GB fields (UKRP choice `F:1289`, issuing entity `F:1358`, GMDN only), Annex B–G codes MUST for every GB type (`F:835-836`), route MORE only (`F:1381-1385`) | No XML. Some `must_in` differ from the workbook (2.3 below) |
| Shared MIR sections | `_mir_device` `F:613`, `_mir_incident` `F:731`, `_mir_analysis` `F:833` | — |
| Derived values | 1.2g classification from the signed report type (`W:509-523`); GB 1.1a = MHRA (`W:710`); parties, AR, UKRP (`W:699-706`); NB number, CE/UKCA certificates (`W:707-708`, `W:737`); reporter role, operator (`W:721-733`); investigation (`case`) and CAPAs (`capas`) for 4.1a, 4.1c, 4.2g | 1.1a (EU), 1.1c, 1.2a, 1.2d, 1.2f, 1.3.1a, 1.3.1b, 3.2c, 4.2b are typed (`F:1042-1080`, `F:1098`, `F:1106`) |
| Report type | A new report starts as the form's first type, "Initial" (`W:857-861`); a person may change `1_2E` to any of the five on the one obligation (test `tests/test_release_c4_0_10_76.py:147-170`) | Each type is not its own report; a Final can replace an Initial on the same record |
| Report chain | Only US follow-ups: `is_follow_up` and `_follow_ups` test `form_code == FDA_3500A` (`R:211-226`); `create_follow_up` refuses non-US (`R:2276-2280`); `kind` is INITIAL or RESPONSE (`M:61`, `M:129`); one INITIAL per complaint and market (`M:134`) | No EU/GB chain. The generic `POST /follow-up` only sets FOLLOW_UP_DUE (`R:2219-2238`) |
| Frozen files | US only: `request_snapshot` builds and validates the eMDR XML at Send (`R:1531-1546`); `snapshot_material` puts `emdr_sha256` and `emdr_parties` in the fingerprint (`R:1490-1502`); `emdr.xml` serves stored bytes from APPROVED only (`R:2683-2697`) | No MIR file to freeze |
| Draft preview | A draft PDF is marked "DRAFT PREVIEW - NOT APPROVED" (`tests/test_release_c4_0_10_76.py:181-184`) | Keep for the new PDFs |
| Submission | `record_submission` (`R:1942-2002`), routes `EU_NCA` (`F:1223`) and `MHRA_MORE` (`F:1381`) | The hook for "create the next report on submission" |
| A later "not reportable" conclusion | Cancels an unsubmitted INITIAL (`R:965-992`); a submitted one shows "consider a final report that says so" (`R:1049`) | B8 turns this into "Start the Final (Non-reportable incident)" |
| Responsible party | `market_responsible_parties`: `address` one text, `contact_name` one text (`db/models/regulatory_reference.py:77-78`) | The MIR schemas want street, city, postcode, country and first/last name in parts |
| Products | `udi_di`, `basic_udi_di`, `emdn_code` (`db/models/foundation.py:157-162`) | No UDI issuing entity |
| Vendored official files | FDA files with a manifest (`data/fda_forms/manifest.json`, `Con170227.xsd`) | **No MIR file, XSD or help text in the repository** |
| Rule register | `emdr-rule-book-1` (data, CSV hash pinned); `form-fields-starter-1` (EU/GB form rules held in code) | No EU/GB rule book |
| Catalog | `MDR_87`, `IVDR_82`, `MDCG_2023_3`, `UK_MDR` (`standards.py:109-135`) | No `MDR_89` (final report, Art. 89(5)) or IVDR equivalent |

### 2.3 What B9 adds that B8 builds on (seen on `feat/b9-markets`, 5 commits)
- **Switches:** `feature_set.switched_on(name)` with a defaults table `B9_SWITCHES` (`feature_set.py`, B9 commit `22e8fe02`). B8 adds its two switches to the same table.
- **Register versions behind a switch:** `register.offered(entry)` (B9 diff of `rule_register/register.py`): a version with `"switch"` is picked only while the switch is on. B8's rule books use it.
- **Official form files with a manifest and SHA-256:** `data/mvpi_forms/manifest.json` (B9 step 12). B8 copies the pattern for `data/mir_forms/`.
- **Extra files on the export route:** `form=official` / `form=adrms` via a small table (`INDIA_FILES`, B9 diff of `router.py` near `R:2537`). B8 adds its downloads the same way.
- **Not yet visible (B9 steps still to come):** the generalised chain for India and Canada (B9 steps 11 and 14), the personal-data setting (B9-D9), migration `tr28marketroles` (B9 step 3). Step 0 checks each. If B9's chain helpers exist, B8 reuses them; if not, step 3 generalises `is_follow_up` and `_follow_ups` itself (included in its hours).

### 2.4 Workbook versus code (to settle in step 2, sheet first, D17)
| Field | Workbook | Code today |
|---|---|---|
| GB 4.2i final comments | Mandatory C, FR (help text); XSD minOccurs O | Not mandatory for GB (`F:958-963`, `must_in=() if gb`) |
| GB 4.3.3d how similar incidents were found | Mandatory C, FR | Not mandatory for GB (`F:1006-1013`) |
| GB 2.4 risk class | Mandatory, all types | `INITIAL` for GB, "optional in MHRA's schema (to confirm)" (`F:687-694`) |
| GB 1.3.3 AR/UKRP | Conditional (corrected after the spot-check) | MUST (`F:1316-1324`) |
| GB 1.2g in Follow-up and Combined | Mandatory (XSD M) | Mandatory, note "to confirm" (`F:1272-1282`) |

Rule for B8 (B8-D6 ⚑): per type, **the stricter of the XSD and the help text**.

---

## 3. Gap table

| # | Gap | Evidence | Step |
|---|---|---|---|
| G1 | No MIR schemas, help texts or changelogs in the repository | `data/` holds only `fda_forms`, `mvpi_forms` (B9), `code_lists` | 1 |
| G2 | No EU/GB rule book; mandatory rules in code only | `F:558-566`, `form-fields-starter-1.json` | 2, 13 |
| G3 | No EU/GB report chain; one report changes type by hand | `R:211-226`, `R:2276-2280`, `W:857-861` | 3 |
| G4 | Nothing created after submission | `R:1942-2002` | 4 |
| G5 | 1.1a (EU), 1.1c, 1.2a, 1.2d, 1.2e, 1.3.1a, 1.3.1b, 4.2b typed or chosen by hand | `F:1042-1106` | 5 |
| G6 | Party address and contact name not in parts; no UDI issuing entity | `regulatory_reference.py:77-78`; `foundation.py:157-162` | 6 |
| G7 | No EU MIR XML | — | 7 |
| G8 | No frozen MIR file in the approval | `R:1490-1502`, `R:1531` (US only) | 8 |
| G9 | No MIR-layout PDF (only the generic worksheet render) | `authority_reports/render.py` | 9 |
| G10 | 4.3 similar incidents is one free-text field; the schema wants a table per period and region | `F:996-1004` | 10 |
| G11 | No GB XML; no GB record copy | — | 14, 15 |
| G12 | Northern Ireland has no MORE route | Note only, `F:1226-1228` | 16 |
| G13 | No catalog id for the final report (MDR Art. 89(5)) | `standards.py:107-125` | 2 |

---

## 4. Design

### 4.1 The chain (EU and GB alike)
- **No new kind, no migration for the chain** (as B3 and B9). The first report is the existing INITIAL obligation. Each later report is a child: `kind = RESPONSE`, `parent_id` = the initial, `form_code` = `EU_MIR` or `GB_MIR`. Its type sits in `1_2E`.
- **Which types each position may take** (the form's own rule, spec §4.2):

| Position | Types offered | What follows |
|---|---|---|
| First report | Initial, or Combined initial and final (only when the person picks it) | Initial: a Follow-up draft is created when it is recorded as submitted. Combined: nothing; the chain ends |
| Later report | Follow up; Final (Reportable incident); Final (Non-reportable incident) | Follow up: the next Follow-up draft on submission. Final: nothing; the chain ends |
| After a Final | "Updated final report" on demand only (type Final again) | Nothing |

- **One open report at a time.** The next report can be sent for approval only when the last one is accepted, or recorded with no acknowledgement expected (B3's order rule, `R:2283-2288`).
- **Values carry forward, they are not copied.** A child holds only what a person types on it. Every other value comes from the records (as today) or, for typed fields, from the chain's last approved report. A correction to an earlier report therefore never leaves a stale copy.
- **Carried references.** 1.3.1b (manufacturer's reference) is the complaint's business ID, the same on every report. 1.1c (the authority's reference) comes from the initial's recorded submission, else "Unknown" (help text).
- **Auto-created Follow-up** (D14, approved). When an Initial or a Follow-up is recorded as submitted, MDARIX creates the next Follow-up draft in the same transaction. Its due date is the 1.2f date of the report just submitted, labelled "Your date (1.2f): no fixed legal period" (Art. 89(5) has none). It is audited `REPORT_FOLLOW_UP_CREATED` with `automatic: true`. Recording a second attempt never creates a second draft.
- **Switching to a Final.** On the draft, one choice changes the type. The mandatory set changes to that type's schema at once.
- **A later conclusion** (B8-D5 ⚑). A re-signed EU "not reportable" conclusion never cancels a child: the open draft is offered as "Final (Non-reportable incident)", with 4.2b prefilled from the signed rationale, and a person chooses. Reports already sent never change (`R:994-1038`).

### 4.2 Files
- **XML first, PDF from it** (spec §2.4). At "Send for approval" MDARIX builds the XML for the report's type, validates it against that type's vendored XSD, and refuses with 422 `MIR_MISSING` or `MIR_INVALID`, naming each block, if the authority would refuse it.
- **Frozen in the approval.** The XML, its SHA-256 and the party parts go in `report_snapshots.fields` and in the fingerprinted material, as B3 does for eMDR (`R:1490-1502`). The approver signs exactly what is downloaded. A download serves the stored bytes, only from an APPROVED snapshot (`_approved_only`, `R:80`).
- **PDF titles** (B8-D18): "EU MIR 7.3.1 content, prepared by MDARIX" and "GB MIR 7.2.1 content, prepared by MDARIX. Record copy: MHRA takes reports only through MORE." Never "generated by the Commission" or "by MHRA". A record page follows: preparers, approval, the XML's SHA-256.
- **Reports approved before B8** keep their worksheet PDF and get no XML (B8-D10 ⚑).

### 4.3 Values (from the workbook; spec §4.5)
| Field | B8 source |
|---|---|
| 1.1a NCA (EU) | From the incident country, through a vendored NCA list (data file with source and SHA-256). If the XSD lists the NCAs as a code list, that list is used |
| 1.1a (NI) | B8-D4 ⚑ |
| 1.1c | Carried from the initial's recorded submission; "Unknown" otherwise |
| 1.2a date of report | The organisation's day the report is sent for approval (B8-D1 ⚑) |
| 1.2d awareness of reportability (EU only) | B8-D2 ⚑ |
| 1.2e type | From the chain position and the person's choice (4.1) |
| 1.2f next report date | Asked on Initial and Follow up; becomes the next draft's due date |
| 1.2g classification | Exists (`W:509-523`) |
| 1.3.1a submitter | Asked on the first report, carried |
| 1.3.1b reference | Complaint business ID |
| 1.3.2, 1.3.3 parties | Settings, now in parts (step 6) |
| 2.1a/2.1c issuing entity | B8-D11 ⚑ |
| 2.5 market distribution | Suggested from the product's registrations; a person confirms |
| 3.3b–f, 3.4b–n personal data | B9-D9 setting (B8-D9 ⚑) |
| 4.2b (Final, non-reportable) | The signed "not reportable" rationale, editable |
| 4.3 similar incidents | Asked, as a table (step 10; B8-D7 ⚑) |

### 4.4 Everything as rule-register data (B4)
| Entry | Kind | Held as | Notes |
|---|---|---|---|
| `eu-mir-rule-book-1` | REPORT_FORM | Data: `authority_reports/rules/eu_mir.csv`, hash pinned | One row per MIR block: label, XML path, mandatory per type (I, FU, C, FR, FNR), source |
| `gb-mir-rule-book-1` | REPORT_FORM | Data: `rules/gb_mir.csv`, hash pinned | Same, GB |
| `eu-mir-7.3.1-SB-11252` | REPORT_FORM (form edition) | Data: vendored files + SHA-256 | Picked by the day sent for approval (B4 R-D3). A newer build is a new version (B8-D8 ⚑) |
| `gb-mir-7.2.1` | REPORT_FORM (form edition) | Same | Same |
| `mir-chain-1` | REPORT_FORM | Data | The position and "what follows" table of 4.1 |
| Catalog `MDR_89`, `IVDR_84` | Sources | `standards.py` + `standards.json` | Starter, for your consultant to confirm |

**B4 equivalence stays green.** No floor file changes. `form-fields-starter-1` stays as the code-held list; the new CSVs become the single source for the MIR `must_in`, and a test proves `forms.py` and the CSV agree for every row and type.

---

## 5. Build steps

Two parts, built and shippable in this order: **A. EU MIR and the shared chain**, **B. GB MIR and Northern Ireland**. Hours include targeted tests. "(db)" = database test; "(unit)" = no database. Every named test must fail without its step.

### Part A: EU MIR and the chain
| # | Step | Hours | Targeted tests |
|---|---|---|---|
| 0 | Branch from B9's tip (B4's if B9 is not merged); one Alembic head; re-check every line of this plan; CHANGELOG section; add B8-01..B8-32 to `scenario-register.md` | 2 | `alembic heads` = 1 |
| 1 | **Vendor the official files** in `data/mir_forms/eu-7.3.1-SB-11252/` (the five per-type XSDs, the PDFgeneric XSD and the XSLs from the SB-11252 zip; help text v7.3.1; changelog; form PDF SB-11154 as reference only) with `manifest.json` (file, SHA-256, source URL, date read, edition). Spike: a minimal Initial and a minimal Final (Reportable) validate; note whether `ncaName` and 2.4 are code lists | 4 | `test_b8_vendored_files_match_their_manifest` (unit); `test_b8_each_eu_xsd_loads` (unit) |
| 2 | **Rule book.** Settle 2.4 in the sheet first (D17, B8-D6); export the EU sheet to `rules/eu_mir.csv`; register entries (4.4); catalog ids; `forms.py` `must_in` read from or checked against the CSV | 5 | `test_b8_every_mandatory_eu_row_is_enforced` (unit: per type, a fixture without that block is named); `test_b8_forms_and_rule_book_agree` (unit); `test_rule_register_unit.py`, `test_standards_unit.py`, `test_rule_pins_unit.py` |
| 3 | **Chain** (4.1): child = RESPONSE + parent + MIR form; types by position (422 `NOT_THIS_POSITION`); one open at a time (409 `PREVIOUS_NOT_ACCEPTED`); Combined/Final end it; "Updated final report" on demand; 1.1c and 1.3.1b carried; values carried from the chain's last approved report; fix 4 (re-sign supersedes approvals of unsent reports in the chain); generalise `is_follow_up` / `_follow_ups` unless B9 did | 9 | (db) `test_b8_an_initial_offers_initial_or_combined_only`; `test_b8_a_child_offers_follow_up_or_a_final`; `test_b8_nothing_follows_a_combined_or_final_report`; `test_b8_the_next_report_waits_until_the_last_is_accepted`; `test_b8_the_reference_and_ncas_number_carry_to_every_report`; `test_b8_a_correction_to_an_earlier_report_reaches_the_open_draft`; `test_b8_re_signing_supersedes_an_approved_unsent_follow_up`; `test_b3_*` follow-up tests stay green |
| 4 | **Next report on submission** (D14): created in `record_submission` for Initial and Follow up; due on 1.2f; audited; idempotent; a later "not reportable" re-sign keeps the open draft and offers Final (Non-reportable) with 4.2b prefilled (B8-D5) | 5 | (db) `test_b8_recording_an_initial_creates_one_follow_up_due_on_1_2f`; `test_b8_a_second_attempt_creates_no_second_draft`; `test_b8_a_not_reportable_re_sign_never_cancels_a_chain_draft`; `test_b8_switching_the_draft_to_a_final_changes_what_is_mandatory` |
| 5 | **Derived and asked values** (4.3): NCA list data file; 1.2a day sent; 1.2d per B8-D2; 1.3.1a asked once per chain; 4.2b; 2.5 suggestion; issuing entity per B8-D11; personal fields through B9-D9's setting | 6 | (unit) `test_b8_the_nca_follows_the_incident_country`; `test_b8_1_2a_is_the_day_sent_in_the_organisations_zone`; `test_b8_1_2d_is_never_filled_without_a_person`; `test_b8_an_ambiguous_udi_never_gets_an_issuing_entity`; (db) `test_b8_personal_fields_stay_blank_while_the_setting_is_off` |
| 6 | **Party parts** (migration `tr29`, 6.1): street, city, postcode, country, contact first and last name on the responsible party; UDI issuing entity on the product. Settings › Products shows the parts; "Finish the report" asks once and saves them (the `PUT /once` path, `R:1276-1374`) | 6 | (db) tr29 upgrade, downgrade, upgrade; `test_rls_coverage.py`; `test_b8_parts_entered_once_reach_every_report`; vitest Settings parts form |
| 7 | **EU XML builder** `mir_xml.py`: one builder, five types, root `<incident>` with `xsi:noNamespaceSchemaLocation`, `sCreateTimeStamp` (the moment sent), `sFormLanguage`; reads the frozen sections and parties; validates against the type's XSD | 12 | (unit) `test_b8_each_type_validates_against_its_own_xsd` (minimal and maximal fixture per type); `test_b8_blank_stays_blank_never_unknown_unless_the_help_text_says_so`; `test_b8_the_same_snapshot_builds_the_same_bytes` |
| 8 | **Freeze at Send for approval**: build, check per type from the CSV, validate, store XML + SHA-256 + parties in the snapshot and fingerprint; `GET /{id}/mir.xml` from APPROVED only; reports approved before B8 keep their PDF (B8-D10) | 6 | (db) `test_b8_send_is_refused_while_the_authority_would_refuse_the_file`; `test_b8_the_xml_downloaded_is_the_one_approved_byte_for_byte` (change Settings after approval: same bytes); `test_b8_the_fingerprint_covers_the_xml`; `test_b8_no_xml_before_approval_or_from_a_superseded_snapshot`; `test_b8_a_report_approved_before_b8_still_downloads_its_pdf` |
| 9 | **MIR-layout PDF** `mir_pdf.py` on `reports/pdf.py`: read back from the XML; sections 1 to 5 with the help text's labels; record page with the SHA-256; DRAFT marks; same snapshot, same bytes | 8 | (unit) `test_b8_every_value_in_the_xml_is_in_the_pdf`; `test_b8_the_pdf_never_says_the_commission_made_it`; `test_b8_a_draft_pdf_is_marked_draft`; `test_b8_same_snapshot_same_pdf_bytes` |
| 10 | **4.3 similar incidents** as a table: periods N to N-3 (start, end), for the incident country, EEA + CH + TR, and the world: similar incidents and devices on the market; basis (4.3.3a), criteria (4.3.3b), method (4.3.3d). Stored as one structured entry; every number entered by a person (B8-D7) | 4 | (unit) `test_b8_a_final_needs_every_period_and_region`; `test_b8_the_table_lands_in_the_xml_in_order`; vitest table entry |
| 11 | **Screens** (new navigation): chain card for EU (reuse `sections/FollowUps.tsx`, today US-only at its line 42); type choice limited by position; "Finish the report" groups; the 4.3 table; after approval "Download PDF" and "Download XML (MIR 7.3.1)"; help line "Import the XML into the official MIR PDF if your authority asks for it" (D10); "Start the Final (Non-reportable incident)" in place of the text at `R:1049` | 10 | vitest: "shows the chain in order with each state"; "offers only the types this position allows"; "both files ready after approval, in 3 clicks from reportable"; "no XML before approval"; `tsc --noEmit` |
| 12 | **Sample** (6.4): RV-07's EU report gets the sample parties' parts held in memory only (the B3 A9 pattern, commit `a29f209f`), so the XML builds; RV-07 stays waiting for the trial user. Update `tests/test_release_c4_0_10_76.py:147` (the Initial no longer accepts "Final") | 4 | `test_b8_the_sample_eu_report_gives_the_pdf_and_the_xml` (db); `test_sample_story_days.py`, `test_release_0_10_92.py` green |
| | **Part A total** | **81** | |

### Part B: GB MIR and Northern Ireland
| # | Step | Hours | Targeted tests |
|---|---|---|---|
| 13 | Vendor the GB files in `data/mir_forms/gb-7.2.1/` (the five GB XSDs, GB help text, changelog, implementation guide, with manifest); GB rule book `rules/gb_mir.csv` with the stricter-of rule (B8-D6), the Annex B–G rule (B8-D3); register entries | 3 | `test_b8_every_mandatory_gb_row_is_enforced` (unit); manifest test |
| 14 | **GB XML**: the same builder with GB differences (UKRP as submitter, GMDN only, UKAB fields, issuing entity; no 1.2d, EUDAMED, PMCF or height); per-type GB XSD | 8 | (unit) `test_b8_each_gb_type_validates_against_its_own_xsd`; `test_b8_eu_only_elements_are_never_in_a_gb_file` |
| 15 | GB PDF record copy (title per B8-D18); route MORE only (exists, `F:1381`); help: "Upload the XML in MORE" | 3 | (unit) `test_b8_the_gb_pdf_says_it_is_a_record_copy` |
| 16 | **Northern Ireland**: an EU_NI report whose incident country is Northern Ireland offers the route "MHRA MORE (EU form)" and builds the EU XML; 1.1a per B8-D4 | 3 | (db) `test_b8_a_northern_ireland_incident_routes_to_more_with_the_eu_form`; `test_b8_an_eu_incident_never_offers_more` |
| 17 | GB and NI screens (shared components, GB labels) | 2 | vitest: "GB report shows MORE as its only route" |
| | **Part B total** | **19** | |

### Close
| # | Step | Hours | Tests |
|---|---|---|---|
| 18 | Switches (6.2) | 3 | Off/on/off per switch: routes 404, no automatic draft, today's worksheet back, drafts still sendable |
| 19 | Docs: user guide (files at approval, "MDARIX never submits", import the XML, upload in MORE), environment reference, CHANGELOG; a line in the release checklist: compare the Commission's and MHRA's pages with the pinned builds before each release | 2 | Doc tests |
| 20 | Targeted suites with both switches on and off: **`test_b4_equivalence.py`, `test_rule_pins_unit.py`**, `test_release_c4_0_10_76.py`, `test_authority_reports_api.py`, `test_authority_reports_rules.py`, `test_release_0_10_96*.py`, `test_regulatory_records.py`, `test_signing_code_refusals.py`, `test_market_assessment_api.py`, B9's new tests; vitest `releaseC3075`, `authorityReports`; ruff; one independent read-only review; fixes | 6 | All green both ways |
| | **Close total** | **11** | |

**Core total: 81 (A) + 19 (B) + 11 = 111 hours.** At about 7 build hours a day, about 16 working days. Part A with the close (about 92 h) can ship alone.

### Optional
| # | Step | Hours | Needs |
|---|---|---|---|
| 21 | 4.3 helper: count MDARIX complaints with the same product and Annex A code per period and region, shown as a suggestion with its method; a person confirms each number | 4 | B8-D7 |
| 22 | GB sample: the GB intake call SAMPLE-CALL-03 (`trial/sample_intake.py:100-125`) carried to a GB report | 4 | — |
| 23 | 1.3.1c: list the other MIRs of the same complaint (several devices) | 2 | — |
| | **Total with options** | **121** | |

---

## 6. Migration, switches, cuts, sample

### 6.1 Migration
**One small additive migration: `tr29_trial_party_parts.py`, revision `tr29partyparts`, `down_revision = "tr28marketroles"`** (B9's Part C). If B9 ships without Part C, `down_revision = "tr27ruleregister"`; step 0 checks there is one head.
- `market_responsible_parties`: `street`, `city`, `postcode`, `country_code` (ISO 3166 alpha-2), `contact_first_name`, `contact_last_name`, all nullable. The existing `address` and `contact_name` stay and are still shown.
- `products`: `udi_issuing_entity` nullable, check GS1 / HIBCC / ICCBBA / IFA.
- No data step, no backfill, nothing guessed from the old text.
- Downgrade drops the columns; it refuses while any of them holds a value (no silent loss).
- **The chain needs no migration** (RESPONSE + `parent_id`, B3 Q1 and B9). Frozen files go in `report_snapshots.fields`.
- **Without tr29** (B8-D12): the parts are asked on every report's "Finish the report" screen and carried along the chain only. It works, but breaks "enter once".

### 6.2 On/off switches (B9's `switched_on` pattern, read on every call)
| Switch | Default | Off means |
|---|---|---|
| `MDARIX_B8_EU_MIR` | on | EU and NI reports work as today: one worksheet, type chosen by hand, worksheet PDF. `mir.xml` answers 404; no draft is created on submission; the EU rule-book version is not offered; chains already made stay readable |
| `MDARIX_B8_GB_MIR` | on | The same for GB |

### 6.3 What can be cut (in this order)
1. Steps 21, 22, 23 (options).
2. Step 16, Northern Ireland: NI keeps today's EU worksheet and the MORE note (`F:1226-1228`).
3. Part B as a whole: GB keeps today's worksheet PDF; the GB Annex B–G question waits.
4. Step 4's automatic draft: replaced by a "Create follow-up" button. This misses D14, so it needs the owner's word.

**Never cut:** schema validation before approval; files frozen at approval and covered by the signature; second-person approval; one open report at a time; the 4.3 table (a Final needs it); vendored files with SHA-256; both switches; B4 equivalence green; signed records never rewritten; "MDARIX never submits".

### 6.4 How it fits the sample story (exporters)
The trial already has the EU case: **SAMPLE-RV-07**, VentraLink 250 Rev B, in a French intensive care unit. The flow sensor showed zero flow for 40 seconds and staff switched to manual ventilation; no harm (`trial/sample_data.py:153-168`). The sample author signed the EU conclusion Reportable (15 days) (`trial/sample_assessments.py:3-6`), and its EU MIR worksheet waits for the trial user (`trial/reports_0_10_75.py:13-16`, `trial/sample_oversight.py:4`). The sample manufacturer is outside the EU ("Orbit Medical Devices (Sample), Springfield, US", `trial/sample_reports.py:113`), and VentraLink 250 has the sample EU authorised representative (`trial/sample_dispositions.py:35`, `:50`).

That is the exporter's story: **a maker outside Europe, an incident in France, an authorised representative, and a 15-day clock.** With B8:
1. The report says "France: ANSM" (1.1a), "All other reportable incidents" (1.2g), and fills the AR block.
2. The trial user finishes the report (1.2f, 3.2c, 4.1a), confirms the codes, sends it, approves it (practice approval) and downloads the **PDF and the MIR XML**.
3. They record the e-mail to ANSM. The **Follow-up draft appears**, due on their 1.2f date.
4. After the CAPA, they switch it to **Final (Reportable incident)** and fill the 4.3 table.

GB has an intake call from a British ward (SAMPLE-CALL-03) but no GB report; optional step 22 adds one.

### 6.5 Scenarios to add (B8-xx)
EU chain: B8-01 an initial offers Initial or Combined only; B8-02 recording an Initial creates one Follow-up due on 1.2f; B8-03 recording a Follow-up creates the next; B8-04 nothing after Combined or Final; B8-05 the next report waits until the last is accepted; B8-06 a draft switched to Final changes the mandatory set; B8-07 1.1c carried, "Unknown" when none; B8-08 1.3.1b the same on every report; B8-09 a "not reportable" re-sign keeps the chain draft and offers Final (Non-reportable) with 4.2b; B8-10 a re-sign supersedes an approved unsent report; B8-11 "Updated final report" on demand only. Files: B8-12 each EU type valid against its XSD; B8-13 Send refused while the file would be refused; B8-14 the downloaded XML is the approved one, byte for byte; B8-15 no XML before approval; B8-16 every XML value is in the PDF; B8-17 the PDF never claims the authority made it; B8-18 a report approved before B8 keeps its PDF. Values: B8-19 NCA from the country; B8-20 1.2a the day sent; B8-21 1.2d never filled without a person; B8-22 address parts entered once reach every report; B8-23 personal fields blank while the setting is off; B8-24 4.3 table complete for a Final. GB and NI: B8-25 each GB type valid; B8-26 no EU-only element in a GB file; B8-27 Annex B–G required on every GB type; B8-28 NI goes to MORE with the EU form; B8-29 an EU incident never offers MORE. All: B8-30 another tenant's chain unseen; B8-31 each switch off/on keeps drafts sendable; B8-32 B4 equivalence green.

---

## 7. Owner decisions

⚑ = touches regulatory interpretation or signed records: **needs your explicit answer.** "If no answer" is what the build does meanwhile. Approved D10 (EU PDF), D11 (GB XML + record copy), D12 (NI path), D13 (1.2d) and D14 (auto follow-up) stand; B8-D2 and B8-D4 only settle what the code check found.

| # | Decision | Recommendation (safe) |
|---|---|---|
| B8-D1 ⚑ | 1.2a "date of report submission" in the frozen file | The organisation's day the report is sent for approval (as B3 Q3), so the approver signs the exact file. If the customer submits on a later day, the submission record keeps the real day and the difference review lists it. *If no answer:* the same; the field's note says "the day sent for approval; record the real day at submission". |
| B8-D2 ⚑ | 1.2d "awareness date of reportability". Approved D13 says: derive it from the day the EU conclusion was signed Reportable. The 0.10.81 fix F12 says: not the signing day (`F:1070`) | Offer the signing day as a **suggestion** that a person confirms or changes (as codes are confirmed); never filed unconfirmed. When 1.2d differs from 1.2c, add the explanation line to section 5 (MDCG 2023-3 Q15, starter). *If no answer:* asked, blank, the signing day shown as a hint only (today's F12). |
| B8-D3 ⚑ | GB Annex B, C, D and G codes on every GB report type: the GB help text says Y; the GB changelog of 31 Oct 2025 says "fix minOccurs=0" | Keep them mandatory on every GB type (today's code, the stricter reading), with MHRA's fallback codes for no fit. *If no answer:* the same. |
| B8-D4 ⚑ | Northern Ireland: which EU MIR version MORE accepts, and what goes in 1.1a | EU MIR 7.3.1 XML and PDF, route "MHRA MORE (EU form)"; 1.1a asked until MHRA confirms. *If no answer:* the same, and the route says "version to confirm with MHRA before your first upload". |
| B8-D5 ⚑ | The chain after a later signed conclusion | A "not reportable" re-sign never cancels a chain draft: it is offered as Final (Non-reportable incident) with 4.2b from the signed rationale, and a person chooses. A re-sign with another report type changes 1.2g on unsent reports only. Sent reports never change. *If no answer:* the same. |
| B8-D6 ⚑ | Where the XSD and the help text disagree on what is mandatory (2.4 above) | Per type, the stricter of the two. *If no answer:* the same. |
| B8-D7 ⚑ | 4.3 similar incidents and devices on the market | Every number is entered by a person; denominators are always asked (MDARIX holds no distribution data). The optional count helper (step 21) only suggests, with its method. *If no answer:* asked only; step 21 not built. |
| B8-D8 ⚑ | Form editions | Pin EU MIR 7.3.1 schemas SB-11252 and the latest GB 7.2.1 file set "from the start", picked by the day sent for approval (B4 R-D3). A newer build is a new register version. Before each release, compare the Commission's and MHRA's pages with the pins. *If no answer:* the same. |
| B8-D9 ⚑ | Personal data (EU 3.3b–f, 3.4b–n; GB the same) | As approved B9-D9: optional at the report step, kept only in that report's frozen snapshot, never used by AI or analytics, tenant setting default off. *If no answer:* never stored, boxes blank. |
| B8-D10 ⚑ | EU and GB reports approved before B8 | Keep their worksheet PDF; never rebuild them as XML; a later report in their chain gets the XML. *If no answer:* the same. |
| B8-D11 ⚑ | UDI issuing entity (2.1a, 2.1c, GB 2.1) | Derive it only from an unambiguous format (GS1: 14 digits with a valid check digit; HIBCC: starts with "+"; ICCBBA: starts with "="); else ask once per product. IFA is never derived. *If no answer:* always asked once per product. |
| B8-D12 | Migration `tr29` (party parts, issuing entity) | Yes. Without it, parts are asked on every report. |
| B8-D13 | Chain without new kinds | Yes: RESPONSE + `parent_id`, as B3 and B9. |
| B8-D14 | Switch defaults | EU on, GB on. |
| B8-D15 | Build order | Part A (EU and the chain), then Part B (GB and NI); each ships alone. |
| B8-D16 | Vendoring the Commission's and MHRA's public files (XSDs, XSLs, help texts, changelogs, form PDF) with SHA-256 | Yes, as for FDA's files. |
| B8-D17 | Classic navigation | No change: EU and GB stay on the new navigation only (`F:1626`). |
| B8-D18 | PDF titles | As in 4.2: "… content, prepared by MDARIX"; GB says "record copy". |

**Needing your explicit answer:** B8-D1 to B8-D11.

---

## 8. Documents to obtain (owner)

| For | Document | Why |
|---|---|---|
| EU | **MIR 7.3.1 XSD/XSL package, build SB-11252** (10 Jun 2026), the **help text v7.3.1**, the **changelog SB-11252**, and the **MIR form PDF SB-11154** (6 May 2026), from the Commission's PMSV reporting forms page (links in authority-forms spec §4.1). Check that no newer build is listed | Vendored and pinned (step 1, B8-D8) |
| EU | **MDCG 2023-3 Rev.2** (current copy) | 1.2c/1.2d, day counting (B8-D2) |
| EU | The Commission's list of **national competent authority vigilance contacts** (name per country, e-mail) | The NCA data file (1.1a) |
| GB | **GB data-requirement files**: the five GB MIR 7.2.1 XSDs, the GB help text, the changelog (the 31 Oct 2025 entry), and the **GB MIR and FSCA schema implementation guide** (gov.uk) | Vendored and pinned (step 13, B8-D3) |
| GB | MHRA's answer, or MORE guidance, on: which XSD version MORE validates; Annex B–G on initial reports; which EU MIR version MORE takes for Northern Ireland | B8-D3, B8-D4 |
| GB | A MORE test account, if MHRA offers one | One trial upload of a sample XML before the first customer |
| All | Your consultant's answers (section 9) | Starter marks can then be lifted |

---

## 9. To confirm with your consultant

EU: 1.2d versus the signing day (B8-D2); whether 1.2a may be the day sent for approval; whether NCAs take MDARIX's MIR-layout PDF with the XML, or want the official PDF; when "Combined initial and final" may be used; when 1.3.3 (authorised representative) is mandatory; whether "Updated final report" is a Final again; the 4.3 method and the "EEA + CH + TR" region; one MIR per device when several devices are involved (1.3.1c); IVDR devices (same form, Art. 82 and 84). GB: Annex B–G on every type; which schema MORE validates; Northern Ireland's EU version and 1.1a; 1.2g in Follow-up and Combined; UK Responsible Person versus AR in 1.3.1; how MHRA questions (3 UK working days) should be recorded. Both: whether an auto-created Follow-up due on the customer's own 1.2f date is the right clock.

## 10. What I did not check

- **The schemas themselves.** No MIR XSD is in the repository or on this machine; the workbook's XSD notes (minOccurs per type) were taken as read. Whether `ncaName` or 2.4 are code lists, and how 4.3 is structured, is the step 1 spike.
- **B9's later steps.** Only B9's first five commits were seen (switches, `IN-floor-2`, MvPI form, ADRMS sheet). Its chain helpers, personal-data setting and `tr28` are taken from its approved spec.
- **The Commission's and MHRA's pages** were not re-read; the builds named here come from the authority-forms spec (re-checked there on 9 Nov). The GB changelog date (31 Oct 2025) and `forms.py`'s "04/06/2025" differ: to settle when the files are obtained.
- The workbook was read for the EU, GB and Counts sheets only. The EU Counts row reads 29 mandatory (16 held, 12 derived, 1 asked), the spec's table says 28 + 2 attributes: the same rows counted differently.
- `render.py`, `reports/pdf.py` and the frontend report page were not opened beyond file names and `FollowUps.tsx:42`.
- No legal source was re-read; no database was queried. Hours are estimates from B3 and B9 steps of similar size; the EU XML builder (12 h) carries the most risk.

---

## Owner approval (11 Nov 2026)
The owner replied **"approve B8 plan"**: every recommendation is accepted as written, including all flagged decisions D1–D11. D2 in particular: the EU conclusion's signing day is shown only as a hint; a person confirms the 1.2d date (this settles the D13 / 0.10.81 F12 conflict in favour of F12). B8 starts automatically when B9 is complete (auto-chain B9 → B8 → B9b → B6).
- **Still open:** the owner's OK to download the official MIR files (EU SB-11252 XSD/XSL package, help text, changelog; GB 7.2.1 files) from the European Commission and MHRA pages and vendor them with SHA-256. Step 1 waits for it; steps that do not need the files may go first.
- **Owner, 11 Nov 2026:** "GB files from MHRA: yes download them from those official pages and add them to the project." GB 7.2.1 files: download only from MHRA's official pages (gov.uk), vendor with SHA-256 and the page date; never from any other site. **EU files (European Commission SB-11252 package, help text, changelog): not yet answered.**
- **Owner, 11 Nov 2026:** "Yes" to the EU files too. EU SB-11252 XSD/XSL package, help text and changelog: download only from the European Commission's official MIR page (health.ec.europa.eu, the URLs in `authority-forms-spec/spec.md`), vendor with SHA-256 and the page date; never from any other site. No file permission remains open for B8.

---

## Build status (run 1, 11 Nov 2026)
Branch `feat/b8-eu-gb-mir` in `trial-093`, from B9's tip `ff09fb4b`; local commits only, never pushed. CHANGELOG section **[0.11.01]**. Scenarios B8-01..B8-32 added to `scenario-register.md` (NOT RUN).

| Step | State | Commit |
|---|---|---|
| 0 | Done: one head `tr28marketroles`; plan lines re-checked (forms.py shifted ~+74 lines on B9's tip; EU_MIR now `F:1102`, GB_MIR `F:1310`) | `d404ea1b` |
| 1 | Done: EU SB-11252 (5 XSDs, PDFgeneric, 2 XSLs, help text, changelog, form PDF for reference) and GB 7.2.1 (5 MIR XSDs, help text xlsx, changelog, implementation guide) in `data/mir_forms/` with `manifest.json` (SHA-256, source URL, page date). Downloaded only from health.ec.europa.eu and gov.uk / assets.publishing.service.gov.uk. GB date settled: 04/06/2025. Spike: all XSDs load; MHRA's 5 MIR examples validate (local only); `ncaName` free text; 2.4 optional in XSD | `42546e7b` |
| 2 | Done: `rules/eu_mir.csv` (88 blocks; stricter-of rule; XSD never stricter than the help text); register `eu-mir-rule-book-1`, `eu-mir-7.3.1-SB-11252` (switch `MDARIX_B8_EU_MIR`); catalog `MDR_89`, `IVDR_84`; forms.py checked against the CSV (4.3.1a made mandatory in C, FR) | `bbf6c77e` |
| 3 | Done: chain, types by position, one open at a time, previous-accepted rule, Combined/Final end it, Updated final on demand, carried values (not copied), 1.3.1b / 1.1c, fix 4 | `bfc0c791` |
| 4 | Done: next Follow-up on submission (D14), once only, audited automatic; D5 offer of Final (Non-reportable) with 4.2b | `bfc0c791` (shared with 3) |
| 5–12, 13–17, 19–20 | Not started | — |
| 18 | Partly: switches exist and gate the chain, types and auto-draft; off/on/off suite not written | — |

**Tests run (all seen passing):**
- `MDARIX_TEST_NO_DATABASE=1 python -m pytest -m unit tests/test_b8_rule_book.py tests/test_b8_mir_files.py tests/test_rule_register_unit.py tests/test_standards_unit.py tests/test_rule_pins_unit.py tests/test_b9_switches.py` → 56 passed, 1 deselected.
- `POSTGRES_DB=mdarix_b2_test python -m pytest tests/test_b8_mir_chain.py tests/test_release_c4_0_10_76.py::test_the_mandatory_fields_follow_the_report_type` → 14 passed.
- `POSTGRES_DB=mdarix_b2_test python -m pytest tests/test_release_c4_0_10_76.py tests/test_release_c5_0_10_77.py tests/test_b9_india_chain.py tests/test_b9_canada_chain.py tests/test_b8_rule_book.py tests/test_b8_mir_files.py` → 38 passed, 1 failed (C4 `test_the_mandatory_fields_follow_the_report_type`: B9's `_role_reporter` KeyError on the test's empty context; fixed in the test helper, then passed in the run above).
- `POSTGRES_DB=mdarix_b2_test python -m pytest tests/test_authority_reports_api.py tests/test_authority_reports_rules.py tests/test_b4_equivalence.py tests/test_rule_pins_unit.py tests/test_b9_switches.py` → 54 passed.
- ruff check / format: clean on every changed file. No vitest (no frontend change).

**Notes for run 2:** start at step 5. Step 7 builder: the XSD tree walker used in run 1 (scratchpad, not in the repo) printed every path with minOccurs; root `<incident>` no namespace; `admin_info/contact_info` is a choice of `reporterMfr` / `reporterAR` / `reporterOther`. The test `test_release_c4_0_10_76.py` already uses a Combined first report (step 12's planned update done early).

---

## Build status (run 2, 11 Nov 2026)
Branch `feat/b8-eu-gb-mir` in `trial-093`; local commits only, never pushed. Worktree clean at `e49ea335`. One head `tr29partyparts`; test DB `mdarix_b2_test` at tr29.

| Step | State | Commit |
|---|---|---|
| Run-1 limit | Done: a later report carries the typed values (entered, confirmed, changed) of each earlier report's **last approved snapshot**; a reopened earlier report's draft never reaches the open child; once re-approved, it does | `3e504234` |
| 5 | Done: 1.1a from the Commission's vigilance contact points (Sep 2026 PDF vendored with SHA-256 and page date in `data/mir_forms/eu-nca-2026-09/source.json`; `rules/eu_nca.csv` derived, hash pinned; NI and unlisted countries asked); 1.2a = day sent for approval (`sent_day`, never typed, never counted missing); 1.2d asked with the signing day as a hint only; 2.5 hint from registered markets; `udi_issuing_entity()` per B8-D11; personal fields stay refused (no B9-D9 setting exists) | `b1375563` |
| 6 | Done: `tr29partyparts` (upgrade, downgrade, upgrade run on `mdarix_b2_test`); models; Settings › Products parts form + "parts to enter" line; `PUT /once` takes `party_parts` and `udi_issuing_entity`, never overwriting | `e49ea335` |
| 7–12 | Not started. **Part A is not complete.** | — |

**Tests run (all seen passing):**
- `POSTGRES_DB=mdarix_b2_test python -m pytest tests/test_b8_mir_chain.py` → 14 passed (step 0 fix); the two new tests failed without the fix (2 failed, checked by reverting the router change).
- `MDARIX_TEST_NO_DATABASE=1 python -m pytest -m unit tests/test_b8_values.py tests/test_b8_mir_files.py tests/test_b8_rule_book.py tests/test_rule_pins_unit.py tests/test_rule_register_unit.py` → 45 passed.
- `POSTGRES_DB=mdarix_b2_test python -m pytest tests/test_b8_mir_chain.py tests/test_release_c4_0_10_76.py tests/test_release_c5_0_10_77.py tests/test_authority_reports_api.py tests/test_authority_reports_rules.py` → 51 passed (step 5).
- `POSTGRES_DB=mdarix_b2_test python -m pytest tests/test_b8_mir_chain.py tests/test_rls_coverage.py tests/test_regulatory_reference_unit.py tests/test_release_0_10_79.py tests/test_release_0_10_81.py tests/test_alembic_drift_policy.py tests/test_day35_migration_chain.py` → 48 passed, 1 failed (the new parts test assumed a stored EU party; the sample holds none); test rewritten to set its own party, then `-k parts_entered` → 1 passed.
- `alembic upgrade head` / `downgrade -1` / `upgrade head` on `mdarix_b2_test` → all OK, one head.
- vitest `src/features/workspace/release0079.test.tsx` → 5 passed. `tsc --noEmit` NOT RUN (planned at step 11).
- ruff check / format clean on every changed Python file; prettier on the two changed frontend files.

**Notes for run 3:** start at step 7. The NCA download: the Commission's site rate-limits scripted downloads (429); the PDF was fetched once through the web reader and its bytes checked (`%PDF-1.7`, metadata author COMM/SANTE/D3, title `20260921__vigilance_contact_points`). An XSD tree walker is in run 2's scratchpad (`b8tools/walk.py`), not in the repo.

---

## Build status (run 3, 11 Nov 2026)
Branch `feat/b8-eu-gb-mir` in `trial-093`; local commits only, never pushed. Worktree clean at `6b0a68c0`. No migration (head `tr29partyparts`). **Part A (EU MIR and the chain, steps 0–12) is complete**; Part B (13–17) and the close (18–20) remain.

| Step | State | Commit |
|---|---|---|
| Run-2 loose ends | Done: run 2's last regression set re-run (49 passed); 1.2a rule proved to touch only derived fields (unit test over every form and type) | `d1a9c033` |
| 7 | Done: `mir_xml.py`, one builder for five types, schema-ordered from each XSD, validated, `MirRefused` names blocks; never a partial file; personal fields never written | `fa520d10` |
| 8 | Done: freeze at Send (MIR_MISSING / MIR_INVALID), XML + SHA-256 + type + parties' parts in snapshot and fingerprint; `GET /{id}/mir.xml` from APPROVED only; pre-B8 keeps PDF | `d9f09c9b` |
| 9 | Done: `mir_pdf.py` read back from the XML, B8-D18 title, record page with SHA-256, DRAFT mark, same bytes | `d9f09c9b` |
| 10 | Done: 4.3.3c one structured entry (`forms.TABLE`), every number a person's, complete table required, XML in order | `d9f09c9b` |
| 11 | Done: chain card for EU (MarketChain "mir"), types by position, Final (Non-reportable) offer, 4.3.3c table, MIR needs line, "Download XML (MIR 7.3.1)" after approval | `6b0a68c0` |
| 12 | Done: RV-07 reads the sample's EU parties held in memory (B3 A9); `tests/report_fill.py` gives 2.4 a class | `d9f09c9b` |

**Tests run (all seen passing):**
- `POSTGRES_DB=mdarix_b2_test python -m pytest tests/test_b8_mir_chain.py tests/test_rls_coverage.py tests/test_regulatory_reference_unit.py tests/test_release_0_10_79.py tests/test_release_0_10_81.py tests/test_alembic_drift_policy.py tests/test_day35_migration_chain.py` → 49 passed (before any run-3 change).
- `MDARIX_TEST_NO_DATABASE=1 python -m pytest -m unit tests/test_b8_values.py tests/test_b8_mir_xml.py tests/test_b8_mir_pdf.py tests/test_b8_similar_table.py tests/test_b8_mir_files.py tests/test_b8_rule_book.py tests/test_rule_pins_unit.py tests/test_rule_register_unit.py` → 70 passed (final code).
- `POSTGRES_DB=mdarix_b2_test python -m pytest tests/test_b8_mir_freeze.py tests/test_authority_reports_api.py tests/test_authority_reports_rules.py tests/test_b4_equivalence.py tests/test_release_0_10_96_emdr.py` → 64 passed (final code).
- `POSTGRES_DB=mdarix_b2_test python -m pytest tests/test_release_c4_0_10_76.py tests/test_sample_story_days.py tests/test_release_0_10_92.py tests/test_b8_mir_chain.py` → 35 passed, 1 xfailed (after step 12; before it, the C4 sample test failed with MIR_MISSING, which step 12 fixes).
- `POSTGRES_DB=mdarix_b2_test python -m pytest tests/test_b8_mir_chain.py tests/test_release_c4_0_10_76.py tests/test_release_c5_0_10_77.py tests/test_authority_reports_api.py tests/test_authority_reports_rules.py tests/test_b4_equivalence.py` → 76 passed, 1 failed (the C4 sample test, before step 12).
- vitest `b8MirScreens.test.tsx authorityReports.test.tsx release0079.test.tsx releaseC4076.test.tsx releaseC3075.test.tsx` → 53 passed; `tsc --noEmit` → clean. ESLint NOT RUN (not in the junctioned node_modules). ruff check/format clean; prettier on changed frontend files.
- "Fails without the step": the step 8–12 tests call routes, keys and fields that did not exist before (mir.xml, `mir`, MIR_MISSING, TABLE); no separate revert run was made.

**Notes for run 4:** start at step 13 (GB rule book; GB files vendored in step 1, trees in run-2 scratchpad `gb-*-tree.tsv`). `mir_xml.py` is EU-specific (FOLDER, FILES, `_block` reads the EU rule book): for GB, parameterise by form (folder, files, rule book) rather than copy. Limits: 1.3.4 parts not held; 1.3.1c/d one text; 2.4 free text (bare class read as MDR/IVDR); sample product has no EU risk class.

---

## Build status (run 4, 11 Nov 2026)
Branch `feat/b8-eu-gb-mir` in `trial-093`; local commits only, never pushed. Worktree clean at `f420e358`. No migration (head `tr29partyparts`). **Part B (steps 13–17) and step 18 are complete.** Open: personal data at the report step, step 19, step 20.

| Step | State | Commit |
|---|---|---|
| Run-4 step 0 | Done: 2.4 a fixed list of the classes the schemas take (MDR I–III, Is/Im/Ir as class I + type flag; IVDR A–D; MDD/AIMDD/IVDD; before the directives; EU only "legislation unknown"); old text mapped when clear, else "Choose again from the list" (counts as missing, never changed). Also: the sample's EU report reads the org's own EU parties once any exist (fixes `test_release_c5_0_10_77` product-identity test, broken by step 12) | `c93f5cc1` |
| 13 | Done: `rules/gb_mir.csv` (84 blocks) from MHRA's files (GB XSD minOccurs + GB help text's differences) with the GB form where stricter; B8-D3 Annex B/C/D/G mandatory on every type; rows where the EU help text alone is stricter marked "to confirm"; register `gb-mir-rule-book-1`, `gb-mir-7.2.1` | `03b83886` |
| 14 | Done: `mir_xml` parameterised by form (`form=`), GB XSDs, UKRP submitter + `reporterDetails`, `udiIssueEntity`, UKAB, `pmcfpmpfId`; EU-only places refused; UKRP needed outside the UK; GB 3.4h added, GB 1.2a = day sent | `ee3ad8d0` |
| 15 | Done: `mir_pdf.form_of`; GB title "… Record copy: MHRA takes reports only through MORE." | `ee3ad8d0` |
| 16 | Done: route `MHRA_MORE_EU` only for an NI incident ("version to confirm with MHRA"), EU incidents never offer MORE; switch off: today's route | `ee3ad8d0` |
| 17 | Done: `MirFiles`/`MirNeeds` GB label, MORE note, GB schema wording | `c074271d` |
| 18 | Done: switch suite (EU db off/on/off; GB unit) | `f420e358` |
| Personal data (B9-D9/B8-D9) | Not started: needs the owner's answer on storage (no tenant column; plan names no migration) | — |
| 19, 20 | Not started | — |

**Tests run (all seen passing, final code):**
- `MDARIX_TEST_NO_DATABASE=1 python -m pytest -m unit tests/test_b8_values.py tests/test_b8_mir_xml.py tests/test_b8_mir_pdf.py tests/test_b8_rule_book.py` → 48 passed (step 0).
- `POSTGRES_DB=mdarix_b2_test python -m pytest tests/test_b8_mir_freeze.py tests/test_release_c5_0_10_77.py tests/test_release_c4_0_10_76.py` → 25 passed (step 0; before the sample-parties fix: 1 failed, C5 product identity).
- `MDARIX_TEST_NO_DATABASE=1 python -m pytest -m unit tests/test_b8_rule_book.py tests/test_b8_mir_files.py tests/test_rule_register_unit.py tests/test_rule_pins_unit.py tests/test_standards_unit.py` → 61 passed (step 13).
- `MDARIX_TEST_NO_DATABASE=1 python -m pytest -m unit tests/test_b8_gb_mir_xml.py tests/test_b8_mir_xml.py tests/test_b8_mir_pdf.py tests/test_b8_rule_book.py tests/test_b8_values.py tests/test_rule_pins_unit.py` → 77 passed (steps 14–15; GB file 12 passed alone).
- `POSTGRES_DB=mdarix_b2_test python -m pytest tests/test_b8_northern_ireland.py tests/test_b8_mir_freeze.py tests/test_b8_mir_chain.py tests/test_authority_reports_api.py tests/test_authority_reports_rules.py tests/test_release_c4_0_10_76.py` → 49 passed (steps 14–16).
- vitest `b8MirScreens.test.tsx authorityReports.test.tsx` → 23 passed; `tsc --noEmit` → clean (step 17).
- `POSTGRES_DB=mdarix_b2_test python -m pytest tests/test_b8_switches.py` → 2 passed (step 18).
- ruff check/format clean on every changed Python file; prettier on the changed frontend files. ESLint NOT RUN.

**Notes for run 5 (personal data design, to build once storage is answered):** a tenant setting `report_personal_data` (default off) shown in `settings_of` and set by `PUT /api/v1/complaints/reportability-personal-data {on, reason}`, Customer Admin only (`is_customer_admin_role`), audited `REPORT_PERSONAL_DATA_SET` with the reason; screen in Settings › Reporting windows beside `RolesBody`. Values typed at the report step travel in the body of `POST /reports/{id}/snapshots` (`personal: {field: value}`) and are written only into that snapshot's sections (never `obligation.entries`); `router.py:1356` refuses PUT of personal fields today (keep it). `mir_xml` then maps personal fields (3.3b-f, 3.4b-g, 3.4i-n) to their elements; India/Canada already read them from the snapshot (`mvpi_mdae.py`, `hc_mdpr.py`, B9-D9). Tests: off -> boxes blank "enter before sending" and Send refuses `personal`; on -> only the snapshot holds them; AI context and exports (`oversight/record_page.py`, `trial/retention.py`, the exports routes) never contain a planted value.

**Owner, 11 Nov 2026 ("(A) and follow MHRA"):**
- Personal-data setting (B9-D9 / B8-D9) gets its own small migration: `tr30personaldata` (down_revision `tr29partyparts`), one tenant-level on/off setting, default off. B9b's planned migration therefore becomes `tr31othercountries`.
- GB rows where only the EU help text is stricter (SRN, 2.1b–c, 2.3p, 2.4, 4.2i, 4.3.1a, 4.3.3d): follow MHRA's own GB files — optional, a non-blocking warning when empty, marked "to confirm with your consultant". 3.4h stays mandatory (MHRA's schema needs it with 3.4a).

## Build status (run 5, 11 Nov 2026)
Branch `feat/b8-eu-gb-mir` in `trial-093`; local commits only, never pushed. Worktree clean at `bb4961b8`. No migration (head `tr29partyparts`). **B8 is complete apart from the personal-data setting (tr30) and the GB "warning when empty" rows (owner's answer, run 6).**

| Step | State | Commit |
|---|---|---|
| GB end to end (DB, API, not the sample report) | Done: a Great Britain complaint, GB conclusion signed reportable, GB MIR report, Send for approval, approval: `mir.xml` = frozen bytes, SHA-256 matches, valid against MHRA's GB Initial XSD, no EU-only element, recorded on MORE. Plus a Northern Ireland complaint's EU report: route MHRA_MORE_EU only, EU file valid. **Found and fixed:** the incident country went into the GB file as "Great Britain" (MHRA's schema refused it); the GB refusal named the Commission's schema | `73470fc5` |
| 19 | Done: user guide Reports (EU MIR, the MIR chain, GB MIR for MORE, Northern Ireland), coverage note corrected; `ENVIRONMENT_VARIABLES.md` rows for both switches; `DEPLOYMENT.md` Upgrading: compare the Commission's and MHRA's pages with `data/mir_forms/manifest.json` before each release; guide label test extended | `cd379cc1` |
| 20 review | ONE independent read-only review of `feat/b9-markets...feat/b8-eu-gb-mir`: 7 findings (2 medium, 5 low); nothing on XSD validity, frozen files, D1/D2/D5/D7/D10, GB vs EU, Northern Ireland or personal data. Fixed 1–5 and 7; rejected 6 (below) | `b0d38e6f` |
| 20 suites | B8 on: 1 failure (register text said "implementation", fixed `1000aa61`); B8 off: only B8 feature tests that assume the switch on, plus the C4 sample test (made switch-aware `bb4961b8`) | `1000aa61`, `bb4961b8` |

**Review findings:** (1) medium, fixed: a typed "Unknown" 1.1c carried over the recorded authority reference. (2) medium, fixed: the position rule was checked only when typed; now also at Send for approval, and an updated final report stays a Final. (3) low, fixed: GB 1.1c / 1.3.1b had no source (not carried). (4) low, fixed: "Ask for an updated final report" on the chain card (was API only). (5) low, fixed: a cancelled automatic follow-up was made again on a second attempt. (6) low, **rejected**: with a switch off, 4.3.3c stays a table, 2.4 a list, 1.2a filled at send. Reason: plan 6.2 defines off as the file, chain, route and rule-book version; the entry rules stay valid either way, and switching a field's kind would read one stored value two ways (known limit: a stored table prints as JSON text in the off worksheet PDF). (7) low, fixed: the screen counted a sent report awaiting receipt as open.

**Tests run (all seen, final code):**
- `POSTGRES_DB=mdarix_b2_test python -m pytest tests/test_b8_gb_end_to_end.py` → 2 passed (1 failed before the country fix).
- `MDARIX_TEST_NO_DATABASE=1 python -m pytest -m unit tests/test_b8_gb_mir_xml.py tests/test_b8_mir_xml.py` → 37 passed.
- `POSTGRES_DB=mdarix_b2_test python -m pytest tests/test_b8_mir_freeze.py tests/test_b8_northern_ireland.py` → 8 passed.
- `POSTGRES_DB=mdarix_b2_test python -m pytest tests/test_b8_mir_chain.py tests/test_b8_gb_end_to_end.py` → 22 passed; the 3 new review tests fail without the fixes (3 failed).
- Step 20 (`b8-step20.sh`: B9 step-19 set, story set, B4 equivalence, register, c4/c5, rules, all `test_b9_*`, all `test_b8_*`): **B8 on: 644 passed, 1 failed, 2 skipped, 1 xfailed** (the register text, fixed; `test_b4_register_api.py test_rule_pins_unit.py test_rule_register_unit.py` → 33 passed after). **B8 off: 619 passed, 26 failed, 2 skipped, 1 xfailed**: 25 are B8 feature tests that assume the switch on (`test_b8_mir_chain`, `_freeze`, `_northern_ireland`, `_gb_end_to_end`), 1 the C4 sample test, made switch-aware → 8 passed on and 8 passed off.
- vitest `releaseC3075 authorityReports b8MirScreens release0079 UserGuidePage` → 57 passed; `tsc --noEmit` clean; ruff check/format clean on all 32 B8 Python files. ESLint NOT RUN (no ESLint config in the frontend).

## Build status (run 6, 11 Nov 2026)
Branch `feat/b8-eu-gb-mir` in `trial-093`; local commits only, never pushed. Worktree clean at `d1b2fca2`. One Alembic head `tr30personaldata`. **B8 is complete apart from owner/consultant items.** B9b's migration is `tr31othercountries`.

| Step | State | Commit |
|---|---|---|
| 1 Personal data at the report step (B9-D9 / B8-D9) | Done: `tr30personaldata` (`reportability_settings.report_personal_data`, default off; downgrade refuses while on; legacy-plane step tr30). `PUT /api/v1/complaints/reportability-personal-data {on, reason}`: Customer Admin only (a trial's owner in their place), reason >= 10, audited `REPORT_PERSONAL_DATA_SET`; Settings › Reporting windows beside the roles. On: boxes say "Optional: type it at Send for approval"; values travel only in `POST .../snapshots {personal}` and are written only into that snapshot's sections and files (EU/GB MIR XML places; 3.3c from each schema's gender list; India/Canada read the snapshot). Never on the draft, audit (ids only), AI, search, masked export. Off: today's behaviour, Send refuses typed details | `18d2db44` |
| 2 GB rows to confirm (follow MHRA) | Done: SRN, 2.1b–c, 2.3p, 2.4, 4.2i, 4.3.1a, 4.3.3d optional on GB, non-blocking "To confirm with your consultant" warning when empty in the types the EU help text names (`mir_rules.to_confirm`); 3.4h mandatory | `18d2db44` |
| 2b Run 5's risk | Done: 4.3.3c prints as lines in the worksheet PDF/Word and as a table on the approval page, whatever the switch | `18d2db44` |
| 3 Close | Suites both ways, ONE independent review, fixes | `92c94fc0`, `0ee2736c`, `d1b2fca2` |

**Review findings (one fresh read-only agent on this run's diff):** (1) high, fixed: masked export kept the frozen India/Canada official PDF (`official_pdf`), which prints the personal boxes. (2) medium, fixed: approval page drew an empty grid for 4.3.3c text typed before the table. (3) medium, fixed: EU weight/height with decimals refused by the integer schema, and a non-number age failed at the schema; now numbers are checked at Send and EU values rounded. (4) low, fixed: a later MIR chain report read the previous report's personal values into its entries (not written, but one refactor from a leak); now excluded, and the screen says to type them again. (5) low, **owner item**: an unmasked export (non-trial, data.export, reason, audited) also holds snapshot personal values with the contacts. (6) low, fixed: table lines italic in the Word file. (7) low, fixed: the audit named boxes the sample ignored; now only boxes frozen as typed.

**Tests run (all seen, final code unless said):**
- alembic on `mdarix_b2_test`: upgrade tr29->tr30, downgrade -1, upgrade: clean; `alembic heads` = `tr30personaldata` only.
- `MDARIX_TEST_NO_DATABASE=1 python -m pytest -m unit tests/test_b8_*.py tests/test_rule_pins_unit.py tests/test_rule_register_unit.py tests/test_standards_unit.py` → 125 passed (before review fixes); `tests/test_b8_personal_data_unit.py` → 11 passed (after).
- Step 20 (`b8-step20.sh`) at `0ee2736c`: **B8 on: 658 passed, 2 skipped, 1 xfailed, 0 failed. B8 off: 632 passed, 26 failed**: the 25 B8 feature tests that assume the switch on (as run 5) + `test_b8_personal_data` (read the GB file with the switch off), made switch-aware `d1b2fca2` → 2 passed on and 2 passed off.
- `test_business_permissions.py test_tenant_data.py test_dedicated_plane.py` → 19 passed, 2 failed: both name only B7b's email-intake routes (`/api/v1/email-intake/settings`, `/rotate`, `/messages/{id}/add-to-case`), not B8; the new PUT is in the reviewed exemptions.
- Earlier targeted DB set (personal data, permissions, roles, tenant data, dedicated plane, authority reports API, MIR freeze, c4/c5, GB end to end) → 69 passed, 2 failed (the same two email-intake items).
- vitest `b8PersonalData b8MirScreens authorityReports releaseC3075 release0079 UserGuidePage` → 62 passed; `tsc --noEmit` clean; ruff check/format clean on every changed Python file; prettier on changed frontend files. ESLint NOT RUN (no config).

**Owner, 11 Nov 2026 ("tick-box"):** a full (unmasked) export leaves out the patient and reporter details held in frozen report snapshots and official files **by default**. An option "Include patient and reporter details from submitted reports" (off by default) includes them; it needs the export right and a reason and is audited as its own event (e.g. `EXPORT_PERSONAL_DATA_INCLUDED`). The exit hand-back export (account closing) always includes everything. Masked exports never include them (already built). Build: small follow-up run after B9b run 2, on the tip of the chain, with tests (default off, on with reason, audit event, exit export complete, masked unchanged).

**Owner, 11 Nov 2026 ("accept (a) and (b)"):** the export tick-box is accepted (Definition of done item 7) with both interpretations: (a) ticking "include patient and reporter details" also unmasks customer contacts in that export (same right, reason and audit); (b) an export made while the organisation is suspended or terminated (exit hand-back) always includes everything, contacts included.

## Approval record

| Field | Value |
|---|---|
| Approved | 11 Nov 2026 |
| Approver | Srinivas Telikicherla, Founder & CEO, QA/RA (owner) |
| Approval words, as recorded | "approve B8 plan" |
| Where recorded | section "Owner approval (11 Nov 2026)" |
| Planning copy | `MDARIX-planning/b8-eu-gb-mir/B8-execution-plan.md` (reference only) |
| Form of approval | The owner's written reply, recorded in the spec on the day; not an electronic or wet signature. This section was added on 12 Nov 2026 (owner decision O29); the approved text above is otherwise unchanged, except that a DRAFT status line now reads APPROVED |
