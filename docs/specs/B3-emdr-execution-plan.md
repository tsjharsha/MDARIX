# B3: US eMDR complete for manufacturers. Execution plan

Prepared 10 Nov 2026. Plan only: no code was changed, no test was run, no database was read.

- **Scope.** The B3 row of `development-cycle-1.md` (step 3, items 3.1 to 3.6): the report chain, 3 clicks, the eSubmitter-layout PDF, follow-ups, and mandatory checks. Manufacturer reports only. Importer and user-facility reports are spec phase 3 (D4) and are out.
- **Sources.** `authority-forms-spec/spec.md` (phases 1 and 2, D1 to D9), `spot-check.md`, `code-audit/2026-11-09-high-risk-audit.md`, and the code of `MDARIX-R1`, branch `feat/hardening-0.10.95`. All line numbers below are from that branch.
- **Window.** Build 16 to 27 Nov on the new laptop. Build cut-off Fri 27 Nov, full E2E Sun 30 Nov, deploy 1 to 2 Dec, freeze 4 Dec. Release 0.10.96, inside the big-bang release.
- **Branch.** `feat/b3-emdr-0.10.96`, from the tip of `feat/hardening-0.10.95`, because fixes 4, 5, 6, 10, 11 and decision (a) change the same files. One commit per step, in the order below, so that a partial ship is a clean cut at a commit.

---

## 1. What exists today, and what B3 needs

Paths: `R` = `backend/app/authority_reports/router.py`, `E` = `emdr.py`, `F` = `fda_3500a.py`, `FM` = `forms.py`, `W` = `worksheet.py`, `M` = `backend/app/db/models/authority_reports.py`.

| # | Requirement | Exists today (evidence) | Gap | Change in B3 |
|---|---|---|---|---|
| 1 | **Report chain** (initial, then follow-up #1, #2 and so on, each linked to the initial with the same report number). Under 803.56 a "supplemental" report is the same thing as a follow-up. The US has no "final" report: FINAL comes with the EU build. | `kind` is INITIAL or RESPONSE (`M:61`). The database check `ck_report_obligations_kind_known` allows only these two (`tr05_trial_authority_reports.py:107`). `parent_id` exists (`M:102`). Only one INITIAL is allowed per complaint and market (`M:133-140`). `POST /follow-up` only sets FOLLOW_UP_DUE and a date (`R:1878-1897`). A request for information creates a RESPONSE child on the generic RESPONSE form (`R:1926-1972`). | There is no US follow-up report, no follow-up number and no ordering rule. | A US follow-up is a child of the initial report: `kind` RESPONSE, form FDA_3500A, `parent_id` set to the initial. This needs no migration (see section 3). The number is n = 1 + the follow-ups already sent for approval in the chain, taken under a lock on the initial row. One open follow-up at a time. The number is frozen in the snapshot at "Send for approval". |
| 2 | **Report number** is assigned at "Send for approval" and never reused (D5). | The number is typed in `MFR_REPORT` (`FM:175`), and G8 follows it (`FM:258-267`, `W:836-838`). Only the format is checked (`E:37`, `E:87-94`). | It is typed on every report. Nothing stops reuse. | At "Send for approval", a blank number is filled with the next number: the tenant's last CFN/FEI, the current year, then the last sequence + 1 (5 digits; 7xxxx in a trial). The first number ever is typed once, and that sets the starting sequence. Uniqueness is checked across every US obligation of the tenant, including cancelled ones, under an advisory lock (the pattern in `signals/detection.py:36`). A follow-up copies the initial's number and cannot change it. |
| 3 | **3 clicks** from "reportable" to both files: Confirm all codes, Send for approval, Approve. | Codes are confirmed one at a time (`Reports.tsx:982`, `R:977-1006`, `R:1008-1081`). Send for approval: `ReportsTab.tsx:~500`. After approval, "Generate the PDF" (`ReportsTab.tsx:525`) and "Download the eMDR XML" (`ReportsTab.tsx:538`) are two more clicks. B4 is a MUST field that the person types ("The day you submit", `FM:197`). The "enter once" groups already exist (`ReportBody.tsx:13-14`, 0.10.83). | There is no "Confirm all codes". The number and B4 are typed. Files are made on click. | Add `POST /{id}/codes/confirm`. It confirms every code field that has a suggestion and no entry, through the existing `_code_entry`, with one audit event per field. B4 is no longer asked: it is filled as the day the report is sent for approval (Q3). After approval, "Download PDF", "Download XML" and "Official Form 3500A (PDF)" are ready. The "Generate" step is removed. |
| 4 | **Files frozen with the snapshot** (D6). The approver signs exactly what is downloaded. | The XML is built at download time from the snapshot sections, but with the live responsible parties and the time of download (`R:2084-2095`). Missing blocks are found only at download (`EMDR_MISSING`, `R:2086-2088`). The snapshot fingerprint covers the sections only (`R:1234-1258`). | A change in Settings after approval changes or blocks the XML. A report can be approved whose XML FDA would refuse. | `request_snapshot` builds the XML, validates it against the schema, and stores the XML text, its SHA-256 and the G1/D3 party parts in `snapshot.fields`. All of these go into the fingerprinted material, so the approval signature covers the XML. A download serves the stored bytes. Snapshots approved before B3 have no stored XML: they keep today's build-at-download path. |
| 5 | **eSubmitter-layout PDF, rendered from the XML values.** The title follows D1 and never claims that FDA made it. | It does not exist. An approved US PDF is today the official form, filled (`R:2031-2036`, `F:341-368`). The house PDF writer is `reports/pdf.py`; it has no dates in the file, so its output is repeatable. FDA's own example PDFs are in the owner's package zip and are not in the repository. | Missing. | A new `emdr_pdf.py`. It reads the values back from the stored XML through FDA's XPaths. The `POINTERS` table moves from `tests/test_fda_3500a_emdr.py:264-326` into `emdr.py`, so the code and the tests use one table. Layout: the header (Mfr Report # / UF/Importer Report # / Form Code / Exemption Number), then blocks A to H with FDA's labels and in FDA's order, using [X] and ( ) marks and dd-mmm-yyyy dates, then "File Attachments: none". After that comes MDARIX's record page: preparers, sources, "approved values the file does not carry", the approval, and the XML's SHA-256. Title: "Form FDA 3500A – eMDR content, prepared by MDARIX". Text layout, not ruled boxes (Q4). |
| 6 | **The official 09/2025 fillable 3500A** stays as a second PDF (D2). | `F:21` (the form file), `F:341-368` (the fill), and `F:302-338` (the record page). It reads the live parties (`R:2034-2035`). G6 has no "Follow-up" choice (`F:62-69`), and H2 is never ticked. | It is the default PDF today. It reads live data. It cannot show a follow-up. | It becomes the second download. It reads the frozen parties. Add the G6 "follow-up" choice (C53579) with its number box, and the H2 boxes. |
| 7 | **Follow-up XML**: G6 says follow-up with its number, H2 is filled, only changed values are sent, and the narrative is appended. | `E:436-437` writes G6 from the choices only, so there is no follow-up code and no number. H2 (C53584) is never written. B5 is always the whole description (`E:245`). The H2 field is NOT_USED (`FM:276`), and its source returns None (`W:611`). | All missing. | `emdr.build(..., previous=, follow_up=)`: <br>• G6 = the clock code + C53579 with text n, as in FDA's "Manufacturer Follow-up". <br>• Each ticked H2 box is sent as C53584 with its code. <br>• A single value is sent only when it is new or changed against the merged values of the chain's submitted reports. <br>• Codes are sent only when new. <br>• B5 and H11 carry only the new text typed on the follow-up. <br>• Required parts of the schema get nullFlavor, as FDA's example does. <br>• A cleared value is listed as "FDA keeps the earlier value". <br>• H2 is required on a follow-up (MDARIX's rule, spec 3.3). |
| 8 | **Mandatory checks before approval**, per report type, read from the mapping sheet (D17). | `emdr.check` is hand-coded (`E:79-155`; `REQUIRED_CODES` `E:40`, `_REQUIRED_TEXT` `E:57`). Send for approval checks only the form's MUST fields (`R:1281`), and only on the new navigation (`R:1273`). | There is no rule-book CSV. The eMDR check is not part of approval. | Export the US sheet's manufacturer rows (initial and follow-up) to `authority_reports/rules/us_emdr.csv`, after applying spot-check fixes 1 and 3 (Q8). `emdr.check` reads the required blocks for the report type from it. Send for approval runs the check and the schema validation, and refuses with 422, naming each block. A test fails if any Mandatory row is not enforced. |
| 9 | **D7**: draft PDF preview; downloadable XML only from APPROVED. | A pending snapshot previews as DRAFT (`R:2004`). The XML needs a signature and APPROVED (`R:2081-2083`). | The rule must hold for the new files. | Keep the rule for all three files. The eSubmitter preview is available once the draft XML builds. A pending snapshot's stored XML renders the PDF marked "DRAFT – NOT APPROVED" for the approver, but the XML itself never downloads before approval. |
| 10 | **Audit fix 4** (re-signing supersedes approved snapshots) must cover the chain. | `follow_signed` (`R:876-917`) is called only for INITIAL rows (`reportability/assessment_router.py:145`, `trial/open_deadlines.py:131`). | An approved, unsubmitted follow-up would keep stale content after a re-sign, which is the bug fix 4 closed. | Both callers also pass the unsubmitted follow-ups of the same chain. |
| 11 | **Audit fix 5** (no download from a superseded or cancelled approval). | `_approved_only` (`R:80-87`) is used at `R:2005` and `R:2083`. | The new PDF route and the official-form route need it too. | Call `_approved_only` on every file route. A test covers each route. |
| 12 | **Audit fix 6** (lock, then read fresh). | `_obligation(lock=True)` uses `populate_existing` (fix 6, commit 2fdc810b). | Creating a follow-up and assigning a number must use it. | Lock the initial row with `populate_existing`, and check its state again after the lock. |
| 13 | **Fixes 10, 11 and decision (a)** (H1 Death needs US3; G3 is the organisation's local day). | Built on `feat/hardening-0.10.95`. | None. The XML freezes these values. | Keep `test_fda_h1_says_death_only_when_the_device_caused_or_contributed` and `test_the_awareness_box_prints_the_organizations_day_and_the_deadline_keeps_the_market_day` green. |
| 14 | **Follow-up suggestions** (D9). Manual, never created automatically. An FDA request becomes a follow-up with H2 "Response to FDA request". | Only `conclusion_changed` (`R:920-936`), a warning. | No change detection. A US request creates a generic RESPONSE. | Computed when a submitted report is read. It compares the last submitted values with a fresh worksheet and lists the changed blocks and the suggested H2 boxes. "Create follow-up #n" takes 1 click. The received date is prefilled with today and can be edited. The due date is 30 calendar days after it (803.56). For US, a request for information creates the follow-up with H2 = Response to FDA request. |
| 15 | **FDA's examples as tests** (3.6). | `tests/fixtures/emdr_examples/` holds "Manufacturer Initial - Typical.xml" and "User Facility Initial.xml" with SHA-256s. `test_fdas_manufacturer_initial_typical_example_is_reproduced_block_by_block` already passes. | "Manufacturer Follow-up.xml" and the two example PDFs are not in the repository. They are in the owner's `eMDR-Implementation-Package_0.zip` (Downloads). | Add them to the fixtures with their SHA-256s in `manifest.json`. |

---

## 2. Build steps, in order

Hours are build hours including targeted tests. Every test named below must fail without its step. "(db)" means a database test (`POSTGRES_DB=mdarix_b2_test`, as in the hardening runs). "(unit)" means no database.

### Group A: the initial report complete (ship as one block)

| Step | What | Hours | Targeted tests |
|---|---|---|---|
| A0 | Branch from the tip of `feat/hardening-0.10.95`. Add FDA's "Manufacturer Follow-up.xml" and the "Typical" and "Follow-up" PDFs to `tests/fixtures/emdr_examples` with their SHA-256s. Spike: check that FDA's own follow-up XML validates against `Con170227.xsd` before any build depends on it. CHANGELOG `[0.10.96]` section. | 1 | `test_the_examples_kept_here_are_fdas_files` (add the new names); `test_fdas_follow_up_example_validates_against_fdas_schema` (unit) |
| A1 | **Rule book.** Apply spot-check fixes 1 and 3 to the US sheet (Q8), and export the manufacturer rows to `rules/us_emdr.csv` (block, label, XPath, mandatory for M-I and M-F, source). `emdr.check(sections, parties, kind)` reads its required blocks from the CSV. | 3 | `test_b3_every_mandatory_us_row_is_enforced` (unit: for each Mandatory M-I row, a fixture without that block is named by `check`); `test_b3_a_follow_up_needs_only_g6_with_its_number_and_g8` (unit) |
| A2 | **The check before approval.** For a US report, Send for approval runs `emdr.check` plus a schema validation of the draft XML. The answer is 422 `EMDR_MISSING` or `EMDR_INVALID`, naming each block. `detail()` shows the result on the draft. | 3 | `test_b3_send_for_approval_is_refused_while_fda_would_refuse_the_file` (db); `test_b3_the_draft_shows_the_schema_result_and_no_xml_downloads` (db) |
| A3 | **Report number at Send for approval** (D5, Q2, Q5). | 4 | `test_b3_the_next_number_follows_the_last_and_restarts_each_year` (unit); `test_b3_a_practice_number_starts_with_7` (unit); `test_b3_two_reports_sent_at_once_get_different_numbers` (db, two threads, as in the fix 17 test); `test_b3_a_number_is_never_reused_even_after_a_cancellation` (db); `test_b3_the_first_number_is_asked_once` (db) |
| A4 | **Files frozen with the snapshot** (D6, fixes 4 and 5). The XML is built at Send for approval, with B4 = the day sent in the organisation's time zone (Q3) and the frozen G1/D3 parts. It is validated, then stored with its SHA-256 inside the fingerprinted material. `emdr.xml` serves the stored bytes only from APPROVED. Older snapshots keep today's path. | 5 | `test_b3_the_xml_downloaded_is_the_one_approved_byte_for_byte` (db: change the US party after approval; the bytes stay the same); `test_b3_the_approval_fingerprint_covers_the_xml` (unit); `test_b3_a_pending_or_superseded_snapshot_never_gives_its_xml` (db); `test_b3_a_snapshot_approved_before_b3_still_downloads` (db) |
| A5 | **eSubmitter-layout PDF** (D1). Move `POINTERS` into `emdr.py`. New `emdr_pdf.py` built on `reports/pdf.py`. Includes the draft preview and the record page with the XML SHA-256. | 8 | `test_b3_the_pdf_has_fdas_blocks_in_fdas_order` (unit: the block labels against the text of FDA's "Typical" PDF); `test_b3_every_value_in_the_xml_is_in_the_pdf` (unit: read via `POINTERS`); `test_b3_the_pdf_never_says_fda_generated_it` (unit); `test_b3_the_same_snapshot_renders_the_same_bytes` (unit); `test_b3_a_draft_pdf_is_marked_draft` (unit) |
| A6 | **Two PDFs** (D2, fix 5). The default `worksheet.pdf` for an approved US report is the eSubmitter layout. `?form=official` gives the filled 09/2025 form, which now reads the frozen parties. `_approved_only` is on every route. | 2 | `test_b3_the_default_pdf_is_the_esubmitter_layout_and_the_official_form_is_second` (db); `test_b3_neither_pdf_comes_from_a_superseded_snapshot` (db) |
| A7 | **Confirm all codes** (D8). | 3 | `test_b3_confirm_all_confirms_each_suggested_code_and_audits_each` (db); `test_b3_confirm_all_leaves_chosen_codes_and_fields_without_a_suggestion` (db); `test_b3_confirm_all_is_refused_on_a_non_draft` (db) |
| A8 | **The 3-click page** (`ReportsTab.tsx`): <br>• "Confirm all codes (n)" over the visible list; <br>• the eMDR check before Send; <br>• after approval, "Download PDF", "Download XML" and "Official Form 3500A (PDF)"; "Generate the PDF" is removed. <br>Classic drawer (`Reports.tsx`, `Downloads`): the same three downloads (Q7). Update `releaseC3075.test.tsx`, which uses "Generate the PDF". | 6 | vitest in `authorityReports.test.tsx`: "confirms every suggested code in one click and lists each"; "offers both files at once after approval, with no generate step"; "offers no XML before approval"; "reaches both files in 3 clicks from reportable" (the click-count test, spec phase 1) |
| A9 | **Sample and help.** The trial's sample US report downloads all three files through the A4 fallback. Help text: files at approval, and "MDARIX never submits". | 2 | `test_b3_the_sample_us_report_gives_both_pdfs_and_the_xml` (db); `test_the_sample_reports_fit_the_status_path` stays green |
| | **Group A total** | **37** | |

### Group B: follow-ups (ship only if B1, B2 and B3 are all done)

| Step | What | Hours | Targeted tests |
|---|---|---|---|
| B1 | **Follow-up chain** (backend). `POST /{id}/follow-ups` on a submitted US initial report. It creates a child (kind RESPONSE, form FDA_3500A) holding: the received date in `request_received_on`, "what is new" in `request_text`, `due_on` = received + 30 calendar days (`deadlines.count`), the H2 ticks, and the new narrative. One open follow-up at a time. The number is frozen at Send. G8 is copied. A follow-up may be sent after a later "not reportable" re-sign (it needs a signed conclusion, not a reportable one). For US, `POST /requests` creates this follow-up with H2 = Response to FDA request. Fix 4 callers are extended to the chain. List label: "Follow-up #n". | 8 | `test_b3_follow_up_numbers_run_1_2_3_without_gaps` (db); `test_b3_the_next_follow_up_waits_until_the_last_is_submitted` (db); `test_b3_a_follow_up_is_due_30_days_after_the_information_arrived` (unit); `test_b3_a_follow_up_keeps_the_initial_report_number` (db); `test_b3_a_follow_up_without_an_h2_tick_cannot_be_sent` (db); `test_b3_an_fda_request_becomes_a_follow_up_ticking_response_to_fda_request` (db); `test_b3_re_signing_supersedes_an_approved_follow_up` (db, fix 4 for the chain) |
| B2 | **Follow-up XML** (delta), plus the follow-up boxes on the official form. | 8 | `test_fdas_manufacturer_follow_up_example_is_reproduced_block_by_block` (unit); `test_b3_unchanged_values_are_left_out_and_narratives_never_repeat` (unit); `test_b3_g6_says_follow_up_with_its_number` (unit); `test_b3_h2_ticks_are_sent_as_fdas_codes` (unit); `test_b3_the_official_form_ticks_follow_up_and_h2` (unit) |
| B3 | **Follow-up page**: <br>• "Create follow-up #n" on a submitted report; <br>• the chain list (Initial, Follow-up 1, 2 …, with their states); <br>• the follow-up worksheet shows only the H2 boxes, the received date, the new narrative and the changed blocks; <br>• downloads for each report in the chain. | 4 | vitest: "shows the chain in order with each state"; "creates follow-up #n in one click with the received date prefilled"; "shows only what changed on a follow-up" |
| | **Group B total** | **20** | |

### Group C: suggestions (cut first)

| Step | What | Hours | Targeted tests |
|---|---|---|---|
| C1 | **Follow-up suggestions** (D9), computed when a report is read, never stored and never created automatically. The suggested H2 box for each trigger: <br>• a held value changed: Correction; <br>• a blank block now has a value: Additional information; <br>• H3 or the H6 investigation codes changed: Device evaluation; <br>• a request was recorded: Response to FDA request; <br>• the conclusion changed after submission: the existing warning, now with a "Create follow-up" button. | 5 | `test_b3_each_change_suggests_its_h2_box` (unit, one case per trigger); `test_b3_nothing_changed_suggests_nothing` (unit); `test_b3_a_suggestion_never_creates_a_report` (db) |

### Close

| Step | What | Hours | Tests |
|---|---|---|---|
| Z | Targeted suites: <br>• `test_fda_3500a_emdr.py`, `test_authority_reports_rules.py`, `test_authority_reports_api.py`, `test_release_c3_0_10_75.py`, `test_release_0_10_95.py`, `test_release_0_10_95_rules.py`, `test_market_assessment_api.py`, `test_approval_authority_roles.py`, and the new `test_release_0_10_96*.py`; <br>• vitest `authorityReports.test.tsx` and `releaseC3075.test.tsx`; <br>• ruff. <br>Then one independent read-only review, then fixes. The full gates run once, in the 30 Nov integration run. | 4 | as listed |

**Total: 37 (A) + 20 (B) + 5 (C) + 4 (Z) = 66 hours.** At about 7 build hours a day, that is about 9.5 days. The 10 working days from 16 to 27 Nov are shared with ID-2, check 3a, the ~24 Nov test release and the scans. **Group A (41 hours with Z) fits. Group B is at risk. Group C is likely to be cut.**

**Proposed days:**
- 16 Nov: laptop setup, A0, A1.
- 17 Nov: A2, A3.
- 18 Nov: A4, then A5 started.
- 19 Nov: A5, A6.
- 20 Nov: A7, A8.
- 23 Nov: A8, A9, and the group A review. **Gate: group A done.**
- 24 to 26 Nov: B1, B2, B3.
- 27 Nov: C1 if time allows, then Z.

**Cut-off rule applied:**
1. Cut C1 first. Without it, follow-ups are created by hand; that is still complete and safe.
2. If B1, B2 and B3 are not all done and green by 27 Nov, group B stays out as a whole. The branch is cut at the last group A commit, and today's "A follow-up is due" flag stays as it is. A follow-up record without its own XML would let a user approve a report that cannot be filed.
3. Inside group A, only A7 and A8's "Confirm all" part may be cut alone. The page then keeps per-code Confirm: not 3 clicks, but safe. A1 to A6 are the safety core and ship together or not at all.
4. If group A is not complete and green, B3 stays out entirely (owner's rule).

---

## 3. Migration

**None needed. None recommended.** B2's head stays `tr19casesescalation`.

How B3 avoids one:

- **Follow-ups.** A follow-up uses the existing `kind` value RESPONSE with `form_code = FDA_3500A`. The database check allows only INITIAL and RESPONSE (`tr05:107`).
  - It reuses `parent_id`, `request_received_on` (the date the information arrived), `request_text` (what is new) and `due_on`.
  - The spec already folds the US "response" into a follow-up with H2 = Response to FDA request, so the meaning holds.
  - The follow-up number is frozen in the snapshot. Its uniqueness comes from locking the initial row (fix 6 pattern) plus the one-open-follow-up rule. It is not a database index.
- **Report numbers.** They stay in `entries.MFR_REPORT`. The next number is read from the tenant's own numbers under an advisory lock. There is no new CFN/FEI column.
- **Frozen files.** The XML, its SHA-256 and the party parts go in `report_snapshots.fields` (JSONB).

**If the owner wants the database to enforce the chain**, the migration would be `tr20reportchain` (down_revision `tr19casesescalation`):
- add FOLLOW_UP and FINAL to the kind check;
- add `sequence smallint NULL`;
- add a unique index on (tenant_id, parent_id, sequence) where parent_id is not null;
- no backfill.

Cost: about 2 hours, plus an upgrade-script check, plus moving the existing US RESPONSE rows. DB-1's tr21 would then chain from tr20. **Without tr20, DB-1's first migration should take down_revision `tr19casesescalation`.** The shared FOLLOW_UP and FINAL kinds are better built with the EU build (B8), which needs FINAL anyway.

---

## 4. Open questions for the owner

| # | Question | Recommendation |
|---|---|---|
| Q1 | Add a migration (tr20) so the database enforces the follow-up chain? | No. Use a row lock now, and add the FOLLOW_UP and FINAL kinds with the EU build. |
| Q2 | Report number: derive it from the tenant's last number (the first one typed once), or add a new "FDA CFN/FEI" setting? | Derive it now. Add the setting with the importer reports (phase 3). |
| Q3 | B4 "Date of this report": the day the report is sent for approval (so the approver signs the exact file), or the day it is approved? | The day it is sent for approval. Sending again refreshes the date. |
| Q4 | eSubmitter-layout PDF: FDA's blocks, labels and order in MDARIX's clean text layout, or a box-by-box copy of FDA's look? | Text layout for B3. Boxes later, only if customers ask. |
| Q5 | Should practice (trial) reports use sequence numbers starting with 7, FDA's test numbers? | Yes. |
| Q6 | If follow-ups are not done by 27 Nov, ship group A alone (the initial report complete, 3 clicks, both PDFs, frozen XML)? | Yes. Follow-ups then go to the next release. |
| Q7 | Classic-navigation pilots: give them the same US files (frozen XML, eSubmitter PDF, official PDF, follow-ups)? | Yes for the files and follow-ups. The "Confirm all" and 3-click page stay on the new navigation only. |
| Q8 | May the build apply spot-check fixes 1 (H1 codes) and 3 (B4 rule) to the workbook's US sheet before exporting the CSV? (D17: the sheet first.) | Yes, with a CHANGELOG note. |
| Q9 | Only one open follow-up at a time per chain (follow-up n+1 waits until n is submitted)? | Yes. FDA rejects reports that arrive out of order. |

---

## 5. Risks to the 27 Nov cut-off

| Risk | Effect | Mitigation |
|---|---|---|
| 66 hours of work in 10 days that are shared with ID-2, check 3a, the 24 Nov test release, the scans and the integration merges | Group B or C misses the cut. | Group A first, with a gate on 23 Nov. Cut C, then B, by the rule in section 2. |
| New laptop on day 1 (test database, fonts, the clamd stub, node) | A lost day. | Set up on 15 Nov if possible. A0 is small. |
| `router.py` (2,117 lines) is changed by hardening fixes 4 to 7 and by B3 | Merge conflicts at integration. | Branch from the hardening tip. Keep the new logic in `emdr.py`, `emdr_pdf.py` and small route functions. Rebase daily. |
| Follow-up XML against FDA's schema (required parts in a delta report) | B2 takes longer. | The A0 spike validates FDA's own follow-up example on day 1. Copy its nullFlavor parts. |
| Workbook accuracy (the spot-check found 5 of 39 rows wrong; the US rows H1 and B4 are wrong) | The CSV enforces a wrong rule. | Q8 fixes first. The A1 test compares the CSV with FDA's "Required 3500A fields" list (12 M-I, 2 M-F). |
| Snapshots and sample reports approved before B3 have no frozen XML | Downloads break for trial users. | A4's fallback path and its test. A9 covers the sample. |
| A customer's own MDR sequence clashes with MDARIX's number | FDA Ack3 duplicate error. | The first number is typed once. Numbers are never reused, and uniqueness is checked across the tenant. Gaps after cancelled drafts are not proven acceptable to FDA (spec 12, to confirm). |
| A PDF that looks like FDA's output | Mistaken for an FDA record. | D1 title, and the A5 test that the text never says "FDA eSubmitter Generated". |
| Frontend tests and wording that rely on "Generate the PDF" (`releaseC3075.test.tsx`) | Red vitest at integration. | Updated in A8. No e2e journey clicks these buttons (checked). |
| Re-sign (fix 4) and cancel rules now reach follow-ups | A stale follow-up could be filed. | The B1 test `test_b3_re_signing_supersedes_an_approved_follow_up`. |

---

Not covered in this plan:
- The workbook was not opened. The CSV columns are planned from spec section 3 and the spot-check.
- Whether FDA's follow-up XML validates against `Con170227.xsd` is not yet known. This is the A0 spike.
- Hours are estimates from earlier builds of similar size.

## Owner approval (10 Nov 2026)
"approve B3 plan and start B3 now": all nine recommendations accepted (no tr20; report number derived from the organisation's last number; B4 = day sent for approval; eSubmitter PDF in a clean text layout with FDA's blocks, labels and order; practice numbers start with 7; group A may ship alone; classic-navigation pilots get the US files and follow-ups; spot-check fixes 1 and 3 applied with a CHANGELOG note; one open follow-up per chain). The owner allows copying FDA's public example files from `Downloads\eMDR-Implementation-Package_0.zip` into the test fixtures (step A0). Build starts 10 Nov in worktree trial-094; group A gate 23 Nov; build cut-off 27 Nov.

## Build status (run 1, 10 Nov 2026, worktree trial-094)

Branch `feat/b3-emdr-0.10.96` from `feat/hardening-0.10.95` (ecfdc05d). Local commits only; nothing pushed.

| Commit | Steps |
|---|---|
| 66e23cd0 | A0: FDA's Manufacturer Follow-up.xml (17,737 bytes), Manufacturer Follow-up.pdf (214,718), Manufacturer Initial - Typical.pdf (392,234) in `tests/fixtures/emdr_examples` with SHA-256s. Spike: FDA's follow-up XML **validates** against Con170227.xsd (G6 = C53577 + C53579 with text "1"; H2 = C53585, C53586). CHANGELOG [0.10.96] opened. |
| 1a48ad6e | A1: `rules/us_emdr.csv` (161 manufacturer rows) by `scripts/export_us_emdr_rules.py` (stdlib reader; openpyxl is not installed). Spot-check fixes 1 and 3 were **already in the sheet**: the workbook was not edited. `emdr.check(..., kind)` reads FDA's required blocks (12 M-I, 2 M-F). |
| 4ea9ac6e | A2 + A3 + A4 in one commit (they share `request_snapshot`). |

- **Last step finished: A4.** Not started: A5, A6, A7, A8, A9.
- **Changes beyond the plan text:** the new-navigation meter (`forms.CODES_REQUIRED`) now counts all seven H6 kinds, so the meter shows what Send refuses; B4 field is now source `sent_day` (not typed, PUT refused `FILLED_AT_SEND`); the eMDR gate at Send also applies on the classic navigation (Q7); the first number is asked with 422 `REPORT_NUMBER_FIRST` after the mandatory-field check.
- **B4 source column** in the sheet still says "date of approval (editable until submission)"; owner Q3 says the day sent for approval. Update the sheet's column G, then re-export.
- **Tests run (all green except one pre-existing):** unit `test_fda_3500a_emdr.py` + `test_release_0_10_96_emdr.py` 22 passed; db `test_release_0_10_96.py` 8 passed; `test_release_c3_0_10_75.py` + `test_authority_reports_api.py` + `test_release_0_10_95.py` 36 passed; `test_release_0_10_81.py` + `test_authority_reports_rules.py` + `test_release_0_10_95_rules.py` + unit files 52 passed, 1 failed (`test_f3_f4_f9_a_missing_country_or_awareness_date_is_asked_for_and_blocks_signing`, Oversight facts titles; fails the same at commit 1a48ad6e without B3 code).
- **Not run, likely affected** (they send US reports for approval or count the meter): `test_release_c4_0_10_76.py`, `test_release_c5_0_10_77.py`, `test_release_0_10_82.py`, `test_release_0_10_83.py`, `test_regulatory_records.py`, `test_approval_told_api.py`, `test_flagship_walkthrough.py`, `test_market_assessment_api.py`, `test_approval_authority_roles.py`, frontend tests that type B4. `tests/report_fill.py` now fills FDA-valid values, which should carry most of them.
- **Warning:** at 18:48 on 10 Nov another process wrote uncommitted changes into trial-094 (`backend/app/case_workflow/scope.py`, `backend/app/decision_brief/compose.py`, "lots in scope, owner decision 4"). They are not B3's and were left uncommitted, untouched.

## Build status (run 2, 10 Nov 2026, worktree trial-094)

Same branch, local commits only; nothing pushed.

| Commit | Steps |
|---|---|
| 1e6dc6f7 | A5: `emdr_pdf.py` (title "Form FDA 3500A – eMDR content, prepared by MDARIX"; FDA's blocks A to H, labels and order, read back from the XML through `emdr.POINTERS`, now in `emdr.py`; record page with the XML's SHA-256; DRAFT marks before approval; same file, same bytes). |
| 4e05b1a4 | A6: `worksheet.pdf` for US = the eSubmitter-layout PDF (stored XML; draft: the XML as it builds now; pre-B3 approval: XML built now, else the official form as before); `?form=official` = FDA's 09/2025 form with the G1 party frozen in the snapshot (409 `APPROVE_FIRST` before approval, 404 on other formats). Shared `snapshot_file()` for the XML route and the PDF. The snapshot also keeps `emdr_left_out`. `test_regulatory_records.py` updated (see below). |
| b960d58c | A7: `POST /{id}/codes/confirm` (one `REPORT_FIELD_SET` audit per field, `all_codes: true`; 409 `NOT_A_DRAFT`; 422 `NOTHING_SUGGESTED`). |
| 724f4d52 | A8: `ConfirmAllCodes` (ReportBody.tsx) over "things to give", listing each suggested code; after approval "Download PDF", "Download XML", "Official Form 3500A (PDF)"; "Generate the PDF" gone; classic `Downloads` gets the eMDR XML and the official form (Q7). The vitests are in `releaseC3075.test.tsx` (the report page's harness lives there), not `authorityReports.test.tsx`. |
| 910e2361 | Test fix: `test_release_c5_0_10_77.py::test_nothing_is_filed_unconfirmed...` chooses the three H6 codes the meter now counts (broken by run 1's A2 meter change). |

- **Last step finished: A8.** **A9 not started** (sample and help text).
- **A9 finding (decision needed in the next run):** the trial's sample US report (`backend/app/trial/sample_reports.py`, `US_ENTRIES`) uses non-FDA values: `MFR_REPORT`/`G8` "SAMPLE-0000000-2026-00001 (sample)", free-text H6 codes ("Entered in eSubmitter ... (sample)"), and a typed G1. Its snapshot is made with `request_snapshot(strict=False)`, so it keeps **no** XML: its XML download answers 409 `EMDR_MISSING` and its default PDF falls back to the official form. Recommendation: yes, give the sample FDA-valid values so the WHIF demo shows the new PDF and XML. What that needs: (1) a practice number such as `0000000-2026-7xxxx`, and `assign_number` must not take a trial user's first number from the sample's (exclude `SAMPLE_SOURCE` rows from the seed but keep them for uniqueness; else the "first number is typed once" step disappears in every trial); (2) real IMDRF codes with their FDA codes for H6 clinical, impact, component, type, findings and conclusions (problem is already confirmed from the mapping); (3) a US responsible party with an e-mail in the sample organization and G1/D3 not typed, so `emdr.office` matches; (4) FDA choices for B1 and H1. Then keep `test_sample_story_days.py` and `test_release_0_10_92.py` green and add `test_b3_the_sample_us_report_gives_both_pdfs_and_the_xml`.
- **Spot-check note** added to `authority-forms-spec/spot-check.md` (the B4 source column is outdated; CSV and code follow Q3).

- **Tests run in run 2 (all with `POSTGRES_DB=mdarix_w1_test`, targeted):**
  - unit `test_release_0_10_96_emdr.py` + `test_fda_3500a_emdr.py`: 27 passed.
  - db `test_release_0_10_96.py` (A2-A6): 10 passed. db `test_release_0_10_96_codes.py` (A7): 3 passed.
  - db `test_release_c3_0_10_75.py` + `test_authority_reports_api.py`: all passed (32 passed together with regulatory_records' first run, whose 5 failures were then fixed).
  - db `test_regulatory_records.py`: 5 passed after the update (run with `MDARIX_UPDATE_SNAPSHOTS=1`; snapshot diff reviewed: the report number is normalised, three more H6 codes are filled).
  - db not-run batch (`c4_0_10_76`, `c5_0_10_77`, `0_10_82`, `0_10_83`, `approval_told_api`, `flagship_walkthrough`, `market_assessment_api`, `approval_authority_roles`): 58 passed, 2 failed. c5's failure fixed in 910e2361 (re-run: 1 passed). **Still failing, not B3:** `test_release_c4_0_10_76.py::test_the_samples_rv07_has_its_eu_mir_and_it_goes_the_whole_way` expects an EU draft PDF to be refused (409 `APPROVE_FIRST`) but D7's draft preview returns 200; the EU path is untouched by B3 (inferred from the code, not re-run at ecfdc05d).
  - vitest `releaseC3075.test.tsx` + `authorityReports.test.tsx`: 26 passed; `releaseB072Screens.test.tsx` + `releaseD2083.test.tsx` (the other tests that type B4): 37 passed; `tsc --noEmit` clean.
- **`test_f3_f4_f9_a_missing_country...` (0.10.81):** likely cause is `5d30a1ce` "old flagged imports go to the Imported backlog" (`oversight/service.py` now skips watch items whose binding is `backlog`, so the imported F3/F4 rows get no ":facts" Oversight line). That commit came into hardening from the big-bang line (merge `edc06a9f`); it is not a hardening fix and not B3. Found by reading the code; not confirmed by running at `5d30a1ce^`.
- **Not run:** `test_sample_story_days.py`, `test_release_0_10_92.py` (A9 not started), full suites, Playwright.

## Build status (run 3, 10 Nov 2026, worktree trial-094)

Same branch, local commits only; nothing pushed.

| Commit | Steps |
|---|---|
| ac22d840 | A9: the trial's US example (SAMPLE-RV-09) is FDA-valid: practice number `0000000-<year>-70001`, real IMDRF codes with FDA codes in the six missing H6 kinds (E2203, F23, G0600101, B01, C1202, D0101; H6_PROBLEM stays the mapping's A160103), D2A `DQA` (Oximeter, was FRN infusion pump), G1/D3 from a sample US manufacturer with an e-mail, B4/G8 filled as at Send. `assign_number`: sample numbers count for uniqueness but never seed the first number. Running trials: `backend/app/trial/sample_0_10_96.py`, wired into `scripts/refresh_trial_story.py` (freezes the approved snapshot again at the same moment and re-records the sample approver's record on the new fingerprint, as 0.10.72 did; idempotent; left as it was if no file can be made). Help text: userGuide (files at approval, "MDARIX never submits", send the XML through the ESG), trialGuide, the Reports rail line. |
| a29f209f | A9 fix: the sample's US party is held in memory only (`request_snapshot(..., parties=)`), never stored, so a trial with its own US party is never read or changed and still gets the file. |
| 308bdd65 | B1 + B2 (one commit: they share router and test hunks). B1: `POST /{id}/follow-ups`; follow-up = RESPONSE + FDA_3500A + parent_id, starts from the initial's entries (minus MFR_REPORT, B4, B5, H11, H2, G8), number = 1 + follow-ups submitted before, one open per chain (409 `FOLLOW_UP_OPEN`), MFR_REPORT copied (422 `FOLLOWS_INITIAL`), G6 "30-day; Follow-up #n", due = received + 30 calendar days, H2 editable and required at Send (422 `H2_REQUIRED`), any signed conclusion; US `POST /requests` creates the follow-up with H2 "Response to FDA request"; `_settle_open_reports` passes unsent follow-ups on any signed conclusion to `follow_signed` (supersede only; their due date stays); detail/list give `follow_up` n. B2: `emdr.delta` (changed values only vs the chain's last submitted snapshot, new codes only, B5/H11 only as typed, "FDA keeps the earlier value" for a cleared value), G6 C53579 with text n, H2 as C53584; official form ticks repFollow/repFollowNum and the H2 boxes; eSubmitter PDF shows "Follow-up #: n". |

- **Group A closed (A9 done). Group B: B1 and B2 done; B3 (the follow-up page, frontend) NOT STARTED.** Group B must not ship until B3 is done (plan rule 2).
- **For B3 (next run):** backend is ready: `POST /authority-reports/{id}/follow-ups` body `{received_on, what_is_new, h2: [...], narrative}`; detail has `follow_up` (n) and `responses[]` with `follow_up`, `state`, `received_on`, `due_on`; list items have `follow_up`. H2 choices: Correction; Additional information; Response to FDA request; Device evaluation. "Shows only what changed": the draft's `emdr.left_out` lists cleared values; the changed blocks are not yet exposed as a list (compute from `emdr.delta` if the page needs it).
- **Changes beyond the plan text:** follow-ups cannot be cancelled by API (no cancel route exists); a cancelled one only arises from the database; the follow-up's file always carries B4 (FDA's example leaves it out).
- **Tests run in run 3 (all `POSTGRES_DB=mdarix_w1_test`, targeted; no Playwright, no full suites):**
  - db `test_release_0_10_96.py -k "first_number_is_asked_once or sample_us_report"`: 2 passed (A9).
  - db `test_sample_story_days.py` + `test_release_0_10_92.py` + `test_getting_started_part1.py` + `test_regulatory_records.py` (text snapshot compared for real, NOT updated: unchanged) + `test_release_c5_0_10_77.py::test_a_running_trial_is_re_recorded_once`: 23 passed, 1 xfailed (0.10.92's strict xfail).
  - vitest `newPathText`, `linkTable`, `UserGuidePage`, `TrialGuidePage`: 34 passed.
  - unit (`MDARIX_TEST_NO_DATABASE=1`) `test_release_0_10_96_emdr.py` + `test_fda_3500a_emdr.py` + `test_authority_reports_rules.py`: 38 passed.
  - db `test_release_0_10_96_follow_ups.py` (7 new) + `test_release_0_10_96.py` + `test_release_0_10_96_codes.py` + `test_authority_reports_api.py`: 32 passed.
  - db `test_market_assessment_api.py` + `test_release_c3_0_10_75.py` + `test_regulatory_records.py` + `test_release_0_10_95.py` + `test_approval_authority_roles.py` + `test_release_c5_0_10_77.py`: 55 passed.
- **Tests changed for intended changes:** `test_release_c5_0_10_77.py` (the sample now has six coded H6 fields: counts +3, H6_CLINICAL reads E2203), `test_authority_reports_api.py` (a US request becomes follow-up #1 on Form 3500A), `test_authority_reports_rules.py` (the stand-in obligation names `parent_id`/`form_code`).

## Build status (run 4, 10 Nov 2026, worktree trial-094)

Same branch, local commits only; nothing pushed, tagged or deployed. No migration.

| Commit | Steps |
|---|---|
| 9035b7b1 | Follow-up rules: `POST /authority-reports/{id}/cancel` (a US follow-up not yet submitted; reason >= 10 chars; audited `REPORT_CANCELLED`; pending/approved snapshot superseded and its approval task ended; label "Cancelled before it was sent"; initial 409 `NOT_A_FOLLOW_UP`, submitted 409 `ALREADY_SENT`; numbering stays gap-free). B4 on a follow-up: left out of the XML (effectiveTime nullFlavor NI, as FDA's "Manufacturer Follow-up"), never listed as cleared, "not used" on the worksheet, "Not applicable (follow-up)" on the eSubmitter PDF and "N/A" on the official form; the initial keeps B4 = day sent. Validated against FDA's schema in the example test. |
| 2ffdfac2 | Step B3, the follow-up page (new navigation, `sections/FollowUps.tsx`): chain card on a submitted US initial (Initial, Follow-up #1, #2 … with states, each opens), "Start follow-up #n" (received date prefilled with today, what is new, FDA's four H2 types, new B5); on a follow-up: what it follows, H2 ticked in place, "What changed since the last report sent" (new `emdr.prepare(...)["changed"]`, exposed as `detail.emdr.changed`), Cancel while unsent, same three downloads after approval (file names carry `-follow-up-n`); list shows "· Follow-up #n"; US request button reads "Start the follow-up for this request". Classic panel keeps its downloads (XML + official form) for all US reports incl. follow-ups; no follow-up start on the classic panel. |
| 91554d4e | Step Z review fixes (see below). |

- **Last step finished: Z. B3 is COMPLETE** (groups A and B; C1 cut per plan). The full gates still run in the 30 Nov integration run.
- **Independent review** (one fresh read-only software-assisted review, diff `feat/hardening-0.10.95...feat/b3-emdr-0.10.96`, three dots because hardening moved after the branch point): 3 medium, 4 low. Fixed: (1) the next follow-up waits until the last is *accepted* (or cancelled), not merely submitted — a pending one could be rejected, come back to correction and renumber the chain; (2) G6 on a follow-up is the chain's own (added to `FOLLOW_UP_OWN`, PUT refused 422 `FOLLOWS_CHAIN`), and "Follow-up #n" typed in an initial's G6 is refused (422 `NOT_A_FOLLOW_UP`); (3) a code removed on a follow-up is listed "removed here; FDA keeps the earlier value" (how FDA merges H6 codes across a chain is not confirmed: owner/consultant question); (4) `_chain_values` compares only with reports sent before the follow-up; (5) a follow-up's draft PDF lays out the changes-only file; (7) an approved frozen file's Download XML is no longer blocked by today's Settings. **Rejected (6):** the label "Start the follow-up for this request" only shows on an INITIAL report (the request block is `kind === "INITIAL"` only), so it never promises a chain follow-up on a follow-up. **Open, by design (Q9):** a US request for information while a follow-up is open is refused (409 `FOLLOW_UP_OPEN`), so the request and its date cannot be recorded until the open one is accepted or cancelled; the workaround is to tick H2 "Response to FDA request" on the open follow-up. Owner to decide if requests should be recordable meanwhile.
- **Tests run in run 4 (all `POSTGRES_DB=mdarix_w1_test`, targeted; no Playwright, no full suites), after the review fixes:**
  - unit (`MDARIX_TEST_NO_DATABASE=1 -m unit`) `test_release_0_10_96_emdr.py` + `test_fda_3500a_emdr.py` + `test_authority_reports_rules.py`: 39 passed.
  - db `test_release_0_10_96_follow_ups.py` + `test_release_0_10_96.py` + `test_release_0_10_96_codes.py` + `test_authority_reports_api.py` + `test_release_c3_0_10_75.py` + `test_release_0_10_95.py` + `test_release_0_10_95_rules.py`: 69 passed.
  - db `test_market_assessment_api.py` + `test_approval_authority_roles.py` + `test_regulatory_records.py` + `test_release_c5_0_10_77.py` + `test_release_c4_0_10_76.py` + `test_release_0_10_81.py` + `test_sample_story_days.py` + `test_release_0_10_92.py`: 61 passed, 1 xfailed, 2 failed — both the known pre-existing failures: `c4_0_10_76::test_the_samples_rv07_has_its_eu_mir_and_it_goes_the_whole_way` (EU draft PDF 200 vs expected 409 `APPROVE_FIRST`; B3's diff does not touch that refusal) and `0_10_81::test_f3_f4_f9_...` (Oversight facts line, see run 2).
  - vitest `releaseC3075` (5 new follow-up tests) + `authorityReports` + `releaseB072Screens` + `releaseD2083` + `UserGuidePage` + `TrialGuidePage` + `newPathText` + `linkTable`: 102 passed. `tsc --noEmit`: clean. ruff check/format and prettier on changed files: clean.
- **Integration note:** `feat/hardening-0.10.95` moved on after B3 branched (tip e5652cdd vs merge-base ecfdc05d): rebase B3 before the 30 Nov run; a two-dot diff shows hardening's newer changes reversed.

## Owner decisions after run 4 (10 Nov 2026, "approve 1, 2, 3")
1. A US FDA request that arrives while a follow-up is open is recorded anyway and attached to the open follow-up (H2 "Response to FDA request" ticked, the request date kept); no 409 FOLLOW_UP_OPEN for requests. To build (small; queued after B7 run 1, on feat/b3-emdr-0.10.96, before the 27 Nov cut-off).
2. How FDA merges H6 codes across a follow-up chain is confirmed with an eMDR consultant or FDA eMDR support before the first real customer files a follow-up. Not blocking the deploy.
3. Follow-ups are started on the new navigation only; the classic panel keeps the downloads (supersedes plan Q7 for follow-up creation).

## Build status (run 5, 10 Nov 2026, worktree trial-094)

Local commits and merges only; nothing pushed, tagged or deployed. No migration. Worktree left on `feat/b3-emdr-0.10.96`, clean.

| Commit | Branch | What |
|---|---|---|
| 2dfd8177 | feat/b3-emdr-0.10.96 | Decision 1: a US FDA request while a follow-up is open is recorded on that follow-up (no 409 `FOLLOW_UP_OPEN` for `POST /requests`; the follow-ups route keeps its 409). Kept in the follow-up's entries under `FDA_REQUESTS` (text, received, due, who, when, `h2_ticked`), shown in `detail.fda_requests` and on the follow-up page ("FDA requests recorded on this follow-up"). Draft/correction: H2 "Response to FDA request" ticked. Not yet sent (draft, correction, approved): due date becomes the earlier of the two. Approved or sent: the frozen file is not changed; the page says to reopen it or answer in the next follow-up. Audited `REPORT_REQUEST_ATTACHED` (old/new H2 and due) on the follow-up; the initial's `REPORT_INFORMATION_REQUESTED` carries `attached`. The open follow-up is re-read under its lock (if accepted or cancelled meanwhile, a new follow-up is made). Request button reads "Record it on follow-up #n" while one is open; chain card says a request meanwhile is recorded on it. CHANGELOG updated. |
| cbecf0e5 | fix/signing-routes-known-0.10.96 (from release/bigbang-0.10.96) | `test_every_signing_route_is_known` failed on release/bigbang-0.10.96 too (checked in a temporary detached worktree, removed). Six B2 routes registered in `SIGNING_ROUTES` after checking each: `/intake/{id}/void`, `/triage/{kind}/{id}/record`, `/exclude-threat`, `/triage/downgrades/{task}` refuse a wrong or missing code with `SIGNATURE_CODE_INVALID`, audit `SIGNATURE_MFA_FAILED` and change nothing (new `tests/test_triage_signing_refusals.py`, shown to fail when the code is not passed through); `/confirm-qms` saves through `/record`'s function; `/confirm` carries no credential and stops at 422 `SIGNATURE_NEEDED`. No route failed to refuse: no product code changed. |
| ea4f3c41 | release/bigbang-0.10.96 | merge of the fix branch. |
| f866764f | feat/hardening-0.10.95 | merge of release/bigbang-0.10.96. |
| 2e30a7ac | feat/b3-emdr-0.10.96 | merge of hardening. |

- **Tests run in run 5 (`POSTGRES_DB=mdarix_w1_test`, targeted):** db `test_release_0_10_96_follow_ups.py` + `test_authority_reports_api.py`: 20 passed (after decision 1). On release (temp worktree): `test_signing_code_refusals.py` + `test_triage_signing_refusals.py`: 5 passed. Final, on feat/b3-emdr-0.10.96 after all merges: `test_signing_code_refusals.py` + `test_triage_signing_refusals.py` + `test_release_0_10_96_follow_ups.py` + `test_authority_reports_api.py`: 25 passed. vitest `releaseC3075.test.tsx`: 23 passed (1 new). `tsc --noEmit` clean; ruff check/format and prettier clean on changed files.
- **Observed, not fixed (low):** in a trial (shared plane, the data and control sessions are one), a triage's first save that needs the one-person signature (a later awareness) creates the TriageRecord row before the signature check; a refused signature commits (to keep the refusal audit) and so keeps that empty, unfinished row. Harmless to the next save (it picks the row up), but not "nothing changed". B2 owner to decide.
- **Open for the owner:** decision 1 assumed a request on an approved-or-sent follow-up does not change the frozen file (no H2 tick); and that a DRAFT with a snapshot waiting for approval gets H2 ticked as a person's PUT would (the waiting snapshot does not include it: send for approval again).

## Approval record

| Field | Value |
|---|---|
| Approved | 10 Nov 2026 |
| Approver | Srinivas Telikicherla, Founder & CEO, QA/RA (owner) |
| Approval words, as recorded | "approve B3 plan and start B3 now"; later decisions "approve 1, 2, 3" (10 Nov 2026) |
| Where recorded | sections "Owner approval (10 Nov 2026)" and "Owner decisions after run 4" |
| Planning copy | `MDARIX-planning/b3-emdr/B3-execution-plan.md` (reference only) |
| Form of approval | The owner's written reply, recorded in the spec on the day; not an electronic or wet signature. This section was added on 12 Nov 2026 (owner decision O29); the approved text above is otherwise unchanged, except that a DRAFT status line now reads APPROVED |
