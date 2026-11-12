# B4c: Starter templates, Excel import and export, and regulatory change impact (E4)

Version 1, 11 Nov 2026. **APPROVED by the owner on 11 Nov 2026 (see "Approval record").** Nothing here is built. Per the owner's automatic chain (11 Nov), B4c starts after B4b is complete, and only once this spec is approved. Decisions marked **⚑** touch regulatory interpretation or signed records: they need the owner's explicit answer. Each ⚑ says what the build does **if no answer arrives** (always the safer path).

- **Sources:** `decision-tree-deep-dive/report.md` (approved 7 Nov: §3d, §3e, G3, G10, G11, D4, D8, DT-23..DT-26, DT-31), `development-cycle-1.md` (B4c row; E4 "fold into B4c"), `b4-rule-register/spec.md` (approved: R-D1 register as files, R-D4 law change vs correction, R-D12 training deferred to B4c/E4, optional step 14 not built), `b4b-questionnaire-config/spec.md` (draft: the organisation layer this builds on), `b9-markets/spec.md` (`IN-floor-2`, `CA-floor-2` corrections), `other-country-reports/STATE.md` (head `tr31othercountries`).
- **Code read** (read-only, `git show feat/b8-eu-gb-mir:<path>`, tip `d57c65a9`). Every `file:line` is on that branch, under `backend/app/`, except `sections/...` (under `frontend/src/features/workspace/`) and `customer-admin/...` (under `frontend/src/features/`). B4b is not built; its names are taken from its draft spec. Step 0 re-checks every line on B4b's tip.
- **Regulatory text:** only what the planning files and code already hold. Every citation stays **"starter, for your consultant to confirm"**.
- **Not in B4c:** floor exceptions (D4: none in the first release; B4c-D1 ⚑), new markets, E3/E9/B11/E7.

---

## 1. Purpose, in plain words

Three things, all about **change over time**:

1. **Starter templates per market.** MDARIX ships, per market, the floor plus a few recommended questions the customer may take. When MDARIX releases a new floor or template version, each organisation sees "MDARIX update available", can **see what changes**, and can **adopt it in a new draft**. Nothing is ever adopted for them, except that the floor itself applies by law date (D8).
2. **Excel export and import of a questionnaire.** A consultant can review a version offline. The file comes back **into a new draft only**, shown as a diff. A change to the floor in the file is refused. An import never publishes.
3. **Regulatory change impact (E4).** When a floor rule changes, MDARIX shows each organisation:
   - which markets;
   - which of its questionnaire versions;
   - which open work (drafts, signed conclusions on open complaints, reports);
   - whether each needs re-assessment;
   - who must approve and who must read the change.
   **A signed decision is never changed.** A re-assessment is always a new signed version with a reason (OD-4).

### What changes for users
| Who | Today | With B4c |
|---|---|---|
| Questionnaire author | Starts from MDARIX's starter only; no update notice (`decision_guides/service.py:32-37`; `decision_guides/rules.py:63-64`) | Picks a template; sees "MDARIX update available"; adopts into a draft; exports and imports Excel |
| Regulatory approver | No view of what a floor change does to their work | A **change impact review** per new floor version: the list, a decision per signed conclusion (re-assess or not, with reason), signed with password and code |
| Signer | Signs under a new floor with no notice of what changed | Reads "What changed" once per new floor version before the first signature under it (B4c-D4 ⚑) |
| Consultant | Gets a PDF or Word copy (`decision_guides/router.py:804-824`) | Gets an Excel workbook with the same content, and its fingerprint to match back |
| MDARIX staff | No dry run before shipping a floor version (B4 optional step 14 not built) | A script lists per organisation the counts a candidate floor would affect, before release |

---

## 2. What exists today

| Part | Today | Evidence |
|---|---|---|
| Register held as files | One JSON file per rule version; no write path; versions picked by day | `rule_register/register.py:30-32, 221-235`; B4 R-D1 |
| Kinds of rule | No template kind | `rule_register/register.py:35-47` |
| Change kinds | `INITIAL`, `LAW_CHANGE`, `CORRECTION` | `rule_register/register.py:48` |
| Version states | In force, Scheduled, Retired, Replaced | `rule_register/register.py:238-245` |
| Real corrections already shipped | `IN-floor-2` (India 15 days) and `CA-floor-2` (Canada foreign clock): both `CORRECTION`, "from the start", behind B9 switches | `rule_register/data/IN-floor-2.json`, `CA-floor-2.json` (`change.kind`) |
| Register API | List and one version, with the logic in words; **no diff between versions** | `rule_register/router.py:27-46, 71-135` |
| Guide export | PDF and Word only, for an audit | `decision_guides/router.py:804-824`; `decision_guides/render.py:1-4` |
| Excel reading | A guarded, standard-library reader (zip-bomb and size checks, no macros) | `trial/xlsx.py:1-12, 332` |
| Excel writing | **None**; no spreadsheet library in `requirements.txt` | search of `requirements.txt`, `requirements.in` |
| Export rate limit | `.xlsx` downloads already counted as exports | `rate_limit.py:98` |
| Recommended question example | The sample's VMSR question (21 CFR 803.19) | `trial/sample_guides.py:37-47` |
| A floor change and open drafts | Signing refused until re-saved (`409 FLOOR_CHANGED`) | `reportability/assessment_router.py:548-559` |
| Signed floor of old rows | Pre-B4 rows read as version 1 | `reportability/assessments.py:102` |
| Tasks | Free task types; a scheduler sweep per organisation | `db/models/workflow.py:116-154`; `reportability/reminders.py:1-10` |
| Signer re-acknowledgement | Deferred to B4c/E4 | `b4-rule-register/spec.md` R-D12 |

---

## 3. Design

### 3.1 Starter templates (register data)
- **New register kind `QUESTIONNAIRE_TEMPLATE`**, one file per version: `US-template-1`, `EU-template-1`, `GB-template-1`, `IN-template-1`, `CA-template-1`.
- **Content:** the floor rule it goes with; recommended own questions (each with clause, basis, answer type, plain line, starter mark); example test rows; optional example rules, **off unless ticked** (B4c-D9).
- **First content** (starter, consultant to confirm):
  - US: the VMSR question (803.19, from `trial/sample_guides.py:37-47`);
  - every market: "Was the device returned and evaluated?";
  - every market: "Does your procedure classify this device as implantable or life-supporting?" (One choice).
- **"Start from a template"** fills a new draft. Questions and rules are then the organisation's own.
- A template version is released like any register version: file, source, change note, approver, content hash (B4 step 7 pins it).

### 3.2 "MDARIX update available": see what changes, adopt
- **Banner** on the market's questionnaire when either is true:
  - a floor version newer than the one the in-use version was built on (`floor_code`, B4b) is in force or Scheduled (`rule_register/register.py:238-245`);
  - a newer template version exists.
  - Example: "MDARIX update available: India floor version 2 (from the start) · [See what changes] [Adopt in a new draft]".
- **See what changes:** one diff of two register versions, with citations:
  - questions added, removed or reworded;
  - rules, type rows, report types and periods;
  - counting (zone, day 1);
  - notes, folding, pre-fill;
  - the change note and kind (law change or correction).
  - New read-only route `GET /api/v1/rule-register/{code}/diff/{other}`.
- **Adopt in a new draft:**
  - the organisation layer is carried over;
  - the draft is built on the new floor (`floor_code` = new);
  - own rules that name a retired or reworded floor question are flagged;
  - tests and back-test run on the new floor;
  - effective date on or before the law's date is suggested;
  - then the normal B4b approval. Template questions are offered one by one, never added without a tick.
- **Not adopted by the law's date** (D8, approved): nothing waits. B4 already applies the floor in force at awareness, whatever the organisation layer. On that date, B4c:
  - suspends and lists own rules that name a retired question (B4b-D2);
  - sends a `FLOOR_UPDATE_NOT_ADOPTED` task to the organisation's authors and approvers.

### 3.3 Excel export and import
**Export** (`GET /api/v1/decision-guides/{market}/versions/{version}/questionnaire.xlsx`, `data.export`). One workbook per market and version:
| Sheet | Content |
|---|---|
| About | Market, version code and state, floor code and content hash, template code, effective from, the version's fingerprint, exported at and by, "Starter, for your consultant to confirm" |
| Questions | One row per question: ID, Source (MDARIX floor / Yours), Text, Plain line, Definition, Clause, Basis, Answer type, Options, Position, Pre-fill, Show only when, Required for Not reportable, Your explanation, Your examples, Retired |
| Logic | One rule per row: ID, Layer, IF (readable), THEN (Reportable · type / Needs more information), Your reference |
| Tests | ID, Name, Locked, Answers ("US1=Yes; X1=No"), Expected, Expected type, Last result |
| Floor | The floor's questions and rules, read-only, with its content hash |

- Written with the **standard library** (a minimal workbook writer, about 100 lines, beside `trial/xlsx.py`). No new dependency (B4c-D8).
- **Formula-injection guard:** a cell that starts with `=`, `+`, `-` or `@` is written as text with a leading apostrophe.
- PDF and Word stay for an audit and become reachable from the editor too.

**Import** (`POST .../import`, `questionnaire.author`; into a **new draft only**):
1. Read with the guarded reader (`trial/xlsx.py`) under the trial import size limits.
2. **Market check:** a file for another market is refused (DT-26).
3. **Floor check:** every floor row (Questions with Source = MDARIX floor, the Floor sheet, floor rules on Logic) is compared with the floor named in About. Any difference refuses the **whole file**, with the list (DT-25; B4c-D5).
4. **Readable rules are parsed** by a small grammar that is the exact inverse of the export's words (round-trip tested). A rule ending in Not reportable, or naming an unknown question, is refused.
5. **Validation** as in the editor (B4b step 2). Problems are listed by sheet and row.
6. **Diff before saving:** questions, rules and tests added, changed, removed. The author confirms; the draft is saved.
7. **Fingerprint:** "This file matches approved version 4" or "Changed since version 4 was exported" (the consultant's reviewed copy can be matched).
8. **Never publishes.** The draft then needs tests, back-test and approval (B4b).
9. Audited: `QUESTIONNAIRE_EXPORTED` (file hash) and `QUESTIONNAIRE_IMPORTED` (file hash, fingerprint match, counts).

### 3.4 Regulatory change impact (E4)
**Trigger.** A floor version with change kind `LAW_CHANGE` or `CORRECTION` that is offered (its switch on) and not yet reviewed by an organisation. The scheduler sweep creates one **change impact review** per organisation and market, idempotently. Markets the organisation never uses (no assessment, no window, no version) get none.

**First reviews at B4c's release (B4c-D6 ⚑):** `IN-floor-2` and `CA-floor-2` are real corrections already shipped by B9. B4c creates reviews for them too.

**What the review shows** (computed when opened; frozen when signed):
| Part | Content |
|---|---|
| What changed | The diff (§3.2), the citation, law date or "correction from the start" |
| Markets | The floor's market, and the role floors that follow it (US importer, user facility) |
| Your questionnaire versions | In use, Scheduled and draft versions of that market; the floor each was built on; own rules naming changed or retired questions; [Adopt in a new draft] |
| Open drafts | Unsigned assessments whose awareness day falls in the new version's period. They will be refused at signing until re-saved (B4 `409 FLOOR_CHANGED`). Listed with links; no decision needed |
| Signed conclusions | Those whose awareness falls in the new version's period: for a **law change**, aware on or after its date; for a **correction**, every one in the corrected period. Each is re-run with its stored answers under the new floor and its own organisation layer: "Same" or "Different" (outcome, form type, or due date) |
| Reports | Reports from those conclusions whose due date would now be earlier. The due date stays until a person re-signs (B4 §4.2) |
| Templates | Template versions released with the change |
| People | Who has signed in that market in the last 12 months; who has read "What changed" |

**Decisions** (B4c-D2 ⚑). For each "Different" signed conclusion:
- **Re-assess:** a `FLOOR_CHANGE_RECHECK` task to the regulatory reviewers. The re-assessment is a new signed version with a reason (OD-4). The old one is never changed.
- **No re-assessment:** a reason of at least 10 characters.

Which items must be decided, and which only listed:
- **Open complaints:** every "Different" must be decided.
- **Closed complaints:** listed only, **except** where the change would turn Not reportable into Reportable. That one must be decided, because it may be a missed report.

**Who approves** (B4c-D3 ⚑):
- A holder of `regulatory.approve`; never an administrator.
- Signs the review with password and authenticator code, as its own `SignedApprovalRecord`.
- The signed review freezes the list and the decisions under one fingerprint.
- A one-person trial is allowed and labelled.
- **Due:** the law's date for a law change; 5 working days from release for a correction. A reminder task comes from the sweep.

**Who must read it** (B4c-D4 ⚑): before their first signature under the new floor in that market, each signer reads "What changed" and confirms "I have read what changed". It is one click, audited, kept on the review, and not a signature.

**MDARIX side, before release** (from B4's optional step 14): a staff script runs a candidate floor file against every organisation and prints **counts only**:
- drafts affected;
- signed conclusions that would be different, open and closed;
- reports with an earlier date.
No names and no record content leave an organisation. It runs per organisation inside its own tenant context.

### 3.5 Floor exceptions
**Not built** (D4, approved: none in the first release; B4c-D1 ⚑). DT-31 is tested as "not available": no route, no screen. Optional step 15 holds the design if the owner reverses D4:
- applicability questions only;
- two signatures, a citation, a 12-month expiry;
- never for death, serious injury or deterioration, public health threat or malfunction recurrence.

### 3.6 How each decision meets the five (development cycle)
- **Facts:** the stored answers re-run.
- **Rules:** old and new floor codes and hashes, and the diff.
- **Human judgement:** the approver's decision per conclusion, and the signer's read confirmation.
- **Traceability:** the signed review with its fingerprint, tasks and re-assessments linked.
- **Evidence:** the frozen review and the audit events. Signed conclusions untouched.

---

## 4. Gap table
| # | Gap | Evidence | Step |
|---|---|---|---|
| C1 | No diff between register versions | `rule_register/router.py:71-135` (view and list only) | 1 |
| C2 | No templates; recommended questions only in the sample | `rule_register/register.py:35-47`; `trial/sample_guides.py:37-47` | 2 |
| C3 | No update banner or adoption flow | `decision_guides/service.py:16-37` (published or starter only) | 3 |
| C4 | No notice or suspension listing at a law date | B4 applies the floor by awareness (`reportability/assessment_router.py:172-175`), nothing more | 4 |
| C5 | No Excel export; PDF and Word only | `decision_guides/router.py:804-824` | 5 |
| C6 | No Excel writer and no library | `requirements.txt` (search) | 5 |
| C7 | No import; a guarded reader exists | `trial/xlsx.py:1-12, 332` | 6, 7 |
| C8 | No change impact view, decision or signature | B4 spec step 14 not built (Build status run 2) | 8, 9 |
| C9 | Corrections already shipped with no per-organisation review | `rule_register/data/IN-floor-2.json`, `CA-floor-2.json` | 8 |
| C10 | No signer read confirmation for a new floor | B4 R-D12 | 10 |
| C11 | No staff dry run | B4 spec §6.2 step 14 | 11 |

---

## 5. Build steps
Hours include targeted tests. "(db)" = database test; "(unit)" = no database. Part A (templates, update, Excel) is steps 1–7; Part B (E4) is steps 8–11; both share 0 and 12–15.

| # | Step | Part | Hours | Targeted tests |
|---|---|---|---|---|
| 0 | Branch from B4b's tip; one Alembic head `tr32questionnaires`; re-check every line here; CHANGELOG; add CI-01..CI-14 (below) to `scenario-register.md`; mark DT-23..26, 31 | — | 2 | `alembic heads` = 1 |
| 1 | Register diff (`register.diff`), route, words reuse `rule_register/router.py:27-46` | A | 5 | (unit) `IN-floor-1` → `IN-floor-2` shows only the period; `CA-floor-1` → `CA-floor-2`; a test-only `US-floor-2` with a removed question |
| 2 | Template kind and five `*-template-1` files; loader checks; content hash pin; "Start from a template" | A | 8 | `test_rule_register_unit.py` (kind, hash); (db) template questions land as own questions, unticked rules absent |
| 3 | Banner and adopt into a new draft; retired and reworded references flagged | A | 6 | (db) DT-23: layer carried, references flagged, floor code = new; template questions one by one |
| 4 | Law date not adopted: suspended rules listed; `FLOOR_UPDATE_NOT_ADOPTED` task | A | 4 | (db) DT-24 with the test-only `US-floor-2`: new floor applies at its date, layer unchanged, task once |
| 5 | Excel writer (standard library) and export route | A | 6 | (unit) workbook opens with `trial/xlsx.py`; every sheet; formula guard; (db) `data.export` needed; audited with file hash |
| 6 | Readable rule grammar: words ↔ condition | A | 5 | (unit) round trip on every own-rule shape and every floor rule; bad text gives row and column |
| 7 | Import into a new draft: market, floor and fingerprint checks; validation; diff; never publishes | A | 8 | (db) DT-25, DT-26; round trip export → import gives an identical draft; oversize and macro files refused |
| 8 | Migration `tr33floorreviews` (§6); sweep creates reviews (including `IN-floor-2`, `CA-floor-2`); impact computed per §3.4 | B | 12 | (db) law change vs correction periods; open, closed, pre-B4 rows; idempotent; another organisation never seen (RLS); `test_rls_coverage.py`; upgrade, downgrade, upgrade |
| 9 | Review decisions and signature: re-assess (task) or not (reason); closed Not reportable → Reportable must be decided; never an administrator; frozen with fingerprint; reminder at due date | B | 8 | (db) signed conclusions unchanged byte for byte; refused while a required decision is missing; trial labelled |
| 10 | Signer read confirmation before the first signature under a new floor (B4c-D4) | B | 3 | (db) first signature refused `422 READ_WHAT_CHANGED` until confirmed; once per signer and floor; audited |
| 11 | Staff dry-run script (counts only) | B | 4 | (db) counts match the review; output holds no names or record text |
| 12 | Screens: banner, "See what changes", adopt, template picker, Export/Import with diff (editor), Change impact review page (Decision trees › Rules › Changes; Customer Admin links to it) | A 8, B 6 | 14 | vitest per screen; `tsc --noEmit` |
| 13 | Switches (§7) | — | 2 | Off/on/off: routes 404, banner and reviews hidden, read confirmation not asked; signed reviews kept |
| 14 | Docs: decision tables (change impact rules), user guide, environment reference, CHANGELOG | — | 2 | Decision-table doc test |
| 15 | Targeted suites on and off, **including `test_b4_equivalence.py`, `test_rule_pins_unit.py`, the B4b property test**, `test_decision_guides_api.py`, `test_market_assessment_api.py`, B8, B9, B9b tests; ruff; vitest; `tsc`; one independent read-only review; fixes | — | 6 | All green both ways |
| | **Core total** (A 50, B 33, shared 12) | | **95** | |
| 16 | *Optional, only if B4c-D1 is reversed:* floor exceptions (applicability only, two signatures, citation, 12-month expiry, shown on every decision it touches; migration `floor_exceptions`) | — | 12 | DT-31 as allowed; never on the protected rules |
| 17 | *Optional:* the review's list as an Excel file for the approver's records | B | 2 | Render test |
| | **Total with options** | | **109** | |

At about 7 build hours a day, the core is about 14 working days. Part A can ship alone; Part B needs Part A's diff (step 1).

**CI scenarios (new):** CI-01 a correction lists every signed conclusion in its period; CI-02 a law change lists only events aware on or after its date; CI-03 open "Different" must be decided; CI-04 closed Not reportable → Reportable must be decided; CI-05 other closed differences listed only; CI-06 signed conclusions unchanged after the review; CI-07 "Re-assess" gives a task and the re-assessment supersedes with a reason; CI-08 an administrator cannot sign the review; CI-09 a report due date stays until re-signed; CI-10 signer must read before the first signature under the new floor; CI-11 `IN-floor-2` review made once at release; CI-12 dry run prints counts only; CI-13 import with a changed floor refused whole; CI-14 template rule unticked is not adopted.

---

## 6. Migration
**One additive migration, Part B only: `tr33_trial_floor_reviews.py`, revision `tr33floorreviews`, `down_revision = "tr32questionnaires"`** (B4b's head). If another item lands a migration first, step 0 re-chains to the single head. On mvp-1.0 a merge revision follows (md pattern).

New table `floor_change_reviews`, tenant-isolated with **FORCE ROW LEVEL SECURITY** and the standard tenant policy, as every tenant table:
| Column | Type | Content |
|---|---|---|
| `id` | `UUID` PK | |
| `tenant_id` | `UUID` FK `tenants.id` NOT NULL | |
| `market` | `String(10)` | |
| `floor_code`, `replaces_code` | `String(40)` | New and earlier version |
| `change_kind` | `String(20)` | `LAW_CHANGE` or `CORRECTION` (check) |
| `in_force_from` | `Date` null | Law date; null = from the start |
| `due_on` | `Date` | B4c-D3 |
| `state` | `String(20)` | `OPEN`, `SIGNED` (check) |
| `findings`, `decisions` | `JSONB` | Frozen at signing |
| `read_by` | `JSONB NOT NULL DEFAULT '[]'` | Signers who confirmed "I have read what changed" |
| `signed_by`, `signed_at`, `signed_record_id`, `content_fingerprint` | | The approver's signature |
| `created_at`, `updated_at` | `timestamptz` | |

- Unique `(tenant_id, market, floor_code)`.
- **No data step.** The sweep creates rows.
- **Downgrade** drops the table; it refuses while any `SIGNED` review exists (no silent loss of a signed record).
- Legacy dedicated organisation databases: `add_floor_reviews` in `scripts/add_workflow_tables_to_legacy_planes.py`.
- **Part A needs no migration:**
  - templates are register files;
  - the floor a version was built on is B4b's `floor_code`;
  - import makes an ordinary draft.

---

## 7. Switches, cuts, sample

### 7.1 Switches (the `feature_set.py` pattern, read on every call)
| Switch | Default | Off means |
|---|---|---|
| `MDARIX_B4C_TEMPLATES` | on | No banner, templates, diff route, Excel export or import (routes 404); B4b's editor unchanged |
| `MDARIX_B4C_IMPACT` | on | No new reviews, no read confirmation before signing, review routes 404; signed reviews stay stored and readable through the audit |

Both need `MDARIX_RULE_REGISTER` and `MDARIX_QUESTIONNAIRES` on.

### 7.2 What can be cut (in this order)
1. Optional steps 16, 17. 2. Step 11 (dry run: MDARIX checks by hand before a floor release). 3. Template example rules (questions only). 4. Step 10 (read confirmation: then "What changed" is shown, not required; needs B4c-D4 changed). 5. Excel import (step 7; keep export).

**Never cut:** signed decisions never changed; the floor check on import; import never publishes; the diff; the review's decisions for open complaints and for closed Not reportable → Reportable; the approver never an administrator; D8 (the floor applies by its date).

### 7.3 How it fits the sample story
The sample has India and Canada examples, and B9 shipped real corrections for both. So the sample shows E4 with real data, no fiction:
1. The sample organisation sees "MDARIX update available: India floor version 2".
2. "See what changes" shows one line: the serious adverse event report now has 15 calendar days (Rule 26(ii), starter).
3. The change impact review lists SAMPLE-RV-10 (India, signed under version 1) as **Same**: the sample's India window is already 15 days (`trial/sample_reports.py:40`, per the B9 spec), so no decision is needed. The sample approver signs the review.
4. The US questionnaire offers the US template's "Was the device returned and evaluated?"; the Excel export of US-v2 opens in Excel and imports back as an identical draft.

---

## 8. Owner decisions

⚑ = touches regulatory interpretation or signed records: **needs your explicit answer.** "If no answer" is what the build does meanwhile.

| # | Decision | Recommendation (safe) |
|---|---|---|
| B4c-D1 ⚑ | Floor exceptions (D4) | Keep **none**: not built, DT-31 tested as "not available"; the design is kept as optional step 16. *If no answer:* not built. |
| B4c-D2 ⚑ | Which signed conclusions a floor change puts in front of a person | Re-run every signed conclusion whose awareness falls in the new version's period (law change: on or after its date; correction: the whole corrected period). Each "Different" one on an **open** complaint needs a decision: re-assess (task, new signed version with reason) or not (reason). **Closed** complaints are listed only, except Not reportable → Reportable, which needs a decision (a possible missed report). Never an automatic change. *If no answer:* as recommended. |
| B4c-D3 ⚑ | Who approves the change impact review, and by when | A `regulatory.approve` holder, never an administrator, password and code, own signed record; due on the law's date (law change) or 5 working days from release (correction); one-person trial labelled. *If no answer:* as recommended. |
| B4c-D4 ⚑ | Signer read confirmation (B4 R-D12) | Required once per signer per new floor version in that market, before their first signature under it; one click, audited, not a signature. *If no answer:* required. |
| B4c-D5 | A floor change found in an imported file | Refuse the whole file and list each difference; never import "the rest". |
| B4c-D6 ⚑ | Reviews for corrections already shipped (`IN-floor-2`, `CA-floor-2`) | Create them at B4c's release, so a person checks open India and Canada work whose date would now be earlier. *If no answer:* create them. |
| B4c-D7 | Template updates | Offered, never automatic; each recommended question ticked one by one; floor updates still apply by date (D8). |
| B4c-D8 | Excel library | None added: a small standard-library writer; reading uses the existing guarded reader. |
| B4c-D9 | Template example rules | Shipped unticked; the organisation's rules stay their own procedure. |
| B4c-D10 | Where the register's impact data lives | The register stays files (B4 R-D1); only the per-organisation review is a table. |
| B4c-D11 | Staff dry run before each floor release | Yes, counts only, run inside each organisation's tenant context. |
| B4c-D12 | Switch defaults | Both on. |

**Needing your explicit answer:** B4c-D1, D2, D3, D4, D6.

---

## 9. Documents to obtain (owner)
| For | Document | Why |
|---|---|---|
| Templates | Your consultant's review of each recommended question (text, clause, basis) for the five markets | Template files carry them as starter |
| E4 | Your written procedure (or the consultant's) for acting on a regulation change: who decides, by when, training records | B4c-D2 to D4 should match it |
| Excel | Confirmation that a consultant may receive the workbook (it holds the organisation's procedure text, no complaint data) | Export contents |

## 10. To confirm with your consultant
- Whether a closed complaint that a correction would now call Reportable needs a late report, and how to record it (B4c-D2).
- Whether "I have read what changed" is enough as training evidence, or a training record is needed (ISO 13485 6.2, starter).
- Whether 5 working days for a correction review is right.
- The recommended questions and any example rules in the templates.
- Whether exporting and importing a questionnaire through Excel needs its own software validation note (ISO 13485 4.1.6).

## 11. What I did not check
- B4b is not built; its column and route names come from its draft spec. Step 0 re-checks them.
- All lines are on `feat/b8-eu-gb-mir`; B9b and B4b will move some. Step 0 re-checks.
- I did not open the `IN-floor-2` and `CA-floor-2` files beyond their change kind and switch; the diff content in §7.3 is from the B9 spec.
- I did not measure how many signed conclusions a correction re-run touches; the review computes on open, so a large organisation may need paging (noted for step 8).
- No legal source was re-read. Hours are estimates from B4 and B9 steps of similar size.

---

## Owner approval (11 Nov 2026)
The owner replied **"approve B4c spec"**: every recommendation is accepted as written, including all flagged decisions (D1 no floor exceptions; D2 every signed conclusion in the affected period re-run, open complaints with a different result need a person's decision, closed ones listed except Not reportable → Reportable which needs a decision, nothing changed automatically; D3 change-impact review signed by a regulatory.approve holder, never an administrator, password + MFA, due on the law's date or 5 working days after a correction; D4 "I have read what changed" once per new floor version before the first signature, audited, not a signature; D6 reviews created for IN-floor-2 and CA-floor-2 at release). Build starts in Lane 1 after B4b. Step 0 re-numbers the migration after the current head (one-head rule).

## Approval record

| Field | Value |
|---|---|
| Approved | 11 Nov 2026 |
| Approver | Srinivas Telikicherla, Founder & CEO, QA/RA (owner) |
| Approval words, as recorded | "approve B4c spec" |
| Where recorded | section "Owner approval (11 Nov 2026)" |
| Planning copy | `MDARIX-planning/b4c-templates-change-impact/spec.md` (reference only) |
| Form of approval | The owner's written reply, recorded in the spec on the day; not an electronic or wet signature. This section was added on 12 Nov 2026 (owner decision O29); the approved text above is otherwise unchanged, except that a DRAFT status line now reads APPROVED |
