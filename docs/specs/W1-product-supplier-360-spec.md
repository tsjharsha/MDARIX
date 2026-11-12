# W1 design spec: Product 360 and Supplier 360 in the trial, for the WHIF demo

> **APPROVED by the owner on 7 Nov 2026** ("approve W1 spec"): OD-1 to OD-12 as recommended; added to the consolidated plan as W1 (0.10.94). The build waits for the owner's go (planned alongside B2 from 9 Nov).


**Version 1, 7 Nov 2026. Status: APPROVED by the owner on 7 Nov 2026 (see "Approval record").** No code is changed by this document.
**Release:** 0.10.94 (backlog item W1, capability C2). Built on its own branch, in parallel with B2 (0.10.93), merged after B2. Live before the 4 Dec freeze.
**Code read:** tag `v0.10.92` of `MDARIX-R1` (read only, with `git show`). Line numbers are at v0.10.92.

**Approved inputs this spec applies** (all in `MDARIX-planning/`):
- `development-cycle-1.md`: the W1 row; Addendum B (product direction, phase 8 "feedback to the product"); Addendum C (E1, E2, the MDARIX Decision Framework).
- `operating-modes.md`: M1–M6 (Connect / Complete; every record shows its origin).
- `pms-coverage-map.md` §3: the guardrails (denominators, lot traceability, one event model).
- `b2-case-design/spec.md`: read for conflicts only. W1 uses none of B2's new tables or columns.
- `scenario-register.md`: this spec adds P360-01 to P360-14 and S360-01 to S360-16.

**Words used here.**
- **Product 360**: one product's page, per version, with everything linked to it.
- **Supplier 360**: one supplier's page: its parts, where they are used, and what happened to the products that contain them.
- **"Part"**: a component a supplier is recorded as supplying (`component_suppliers`).
- **Origin**: where a record came from: the sample, an import, or created in MDARIX.

---

## Contents
1. What the user gets (one page)
2. What exists today, and the gaps
3. Product 360 in the trial
4. Supplier 360 (new)
5. The sample story for WHIF, the seed changes and the demo click path
6. Data and API
7. The Decision Framework
8. Operating modes
9. Scenarios
10. Build plan, B2 conflicts, estimate
11. Open decisions, with recommendations
12. What could not be verified

---

## 1. What the user gets (one page)

**The idea in three lines.**
- A new rail destination, **Work › Products**, with two tabs: **Products** and **Suppliers**.
- One product's page shows the version's configuration, lots and changes, and **links to every record** about it: complaints, investigations, trends, CAPAs and effectiveness checks, risks, authority reports. Every link goes both ways.
- One supplier's page shows its parts, the products and versions that use them, their lots, complaints, investigations, changes, inspection evidence and CAPAs, and a plain **"pattern to review"** box that never calls anything a confirmed signal.

**Before and after.**

| | 0.10.92 (today) | 0.10.94 (W1) |
|---|---|---|
| Product 360 in the trial | Hidden (`featureSet.ts` PARKED_SECTIONS: "Products") | Work › Products, hero design |
| Supplier view | None (suppliers only as a column of Product 360's Configuration) | Supplier list and one supplier's page |
| From a complaint to its product | Product name is text only | One click to the product, on the complaint's version |
| From an investigation or a trend card to the product | None | One click |
| Origin of master data | Not shown | Chip on every record: Sample · Your import (system, ID, loaded on) · Created in MDARIX |
| Rev A vs Rev B configuration (sample) | Rev A has no components; the supplier change is visible only in text | Side-by-side compare: pressure sensor Precision Sensors → NovaSense, change SAMPLE-CHG-014 |

**Click counts** (from the design, not timed): complaint → its product version: 1. Product → supplier: 1. Supplier → investigation covering its parts: 1. Trend card → product version: 1.

---

## 2. What exists today, and the gaps

| Piece | Where (v0.10.92) | State | Gap W1 closes |
|---|---|---|---|
| Product list API | `GET /api/v1/products` (`main.py:640`, paged) | Works, tenant-scoped | Add per-product counts for the cards |
| Product 360 API | `GET /api/v1/products/{id}/product-360` (`main.py:697`, `product360/service.py`) | Works; writes an audit event per read | **Returns every complaint of the version, unpaged, plus a timeline built from them**: too heavy for 5,000 complaints. **`changes()` returns every change in the organisation**, not the product's (bug). `failure_modes` and `controls` are organisation-wide, not product-scoped. |
| Version story API | `GET /api/v1/products/{id}/versions/{vid}/story` (`stage3_router.py:242`) | Works; capped at 50 rows | Restyle only |
| Product page UI | `sections/Products.tsx` (classic workspace; 7 tabs) | Uses the global product picker (`NeedsProduct`, `useWorkContext`) | New page addressed by URL (`?product=…&version=…`), hero design |
| Server-side parking | `backend/app/feature_set.py` `_PARKED_API` | Product routes are **not** parked; only the screen is | None needed |
| Lots sharing a supplier | `lot_impact/service.py` `matching()` / `build()` | Works: lots whose genealogy names a part of the supplier, with units, complaints, per 1,000 and the evidence line | **Reuse as is** for Supplier 360's Lots |
| Changes behind a trend | `signals/insight.py` `version_changes()` (0.10.92, A10) | Change → AFFECTS → component → version | Reuse its join for product-scoped changes |
| Supplier evidence requests | `supplier_evidence_requests` (stage3) | Exists, with `supplier_id` | List them on Supplier 360 |
| Complaint page payload | `oversight/router.py` `event_view` | Gives product **name**, version identifier, lot | Add `product_id`, `product_version_id` (2 keys) |
| Sample configuration | `trial/sample_data.py:418–445` | Components C1–C3 are linked **only to Rev B** of each product; NovaSense supplies only the OrbitCare Rev B pressure sensor | Seed Rev A configurations (section 5) |

---

## 3. Product 360 in the trial

### 3.1 Where it sits, and who sees it
- **Rail:** Work group, after Trends: Home · Complaints · Decision trees · Reports · Investigations · Trends · **Products** · Records. Icon: `Boxes`. On a phone it sits under "More".
- **One destination, two tabs:** **Products** and **Suppliers**. Section key `Product 360`, address `/app/product-360`. (A new section name, so the classic "Products" section, its parking and its old-link redirect stay untouched. Old "Products" links on the new navigation open it: a `newHomes` row.)
- **Persona tabs** (`access_control/personas.py`):

| Persona | Products on the rail | Why |
|---|---|---|
| Admin | Yes | Sees everything |
| Quality Leader | Yes | Trends, CAPA, supplier quality |
| Investigator | Yes | Evidence about versions, lots, parts |
| Risk Reviewer | Yes | Risks and changes per version |
| Executive (view only) | Yes | Read-only overview |
| Regulatory Leader, Complaint Handler, Decision Maker, Service Desk (B2) | No | Reach it from a complaint, report or investigation link; the rail then shows it as the "extra" tab while open (`shownTabs`, 0.10.85) |

- **Access on the server:** every member of the organisation may read, as for complaints today (`get_request_context` + the data-plane session). Nothing on these pages writes, except "Open an investigation" (section 4.3), which keeps its own permission check (`investigation_open_router.py`). Personas are views, never permissions.

### 3.2 The product list (tab "Products")
Cards in the hero style (the device art from `HeroVisuals.DeviceIcon`, as on the complaint page):
- Name, family, origin chip, version chips (Rev A · Rev B, the newest first).
- Four counts for the newest version, each a link: **open complaints**, **open investigations**, **trends to review** (a dot, as the rail shows), **open CAPAs**.
- Follows the trial's top-bar "Data shown" choice (sample / your data) where the complaint list does.
- Empty state: "No products yet. Import your products, lots and complaints in Import your data." (the same words as `NeedsProduct` for a trial).

### 3.3 One product's page
**Head (hero):** device art · product name · origin chip · lifecycle pill · the **version switcher** (segmented chips with release dates; "No versions recorded" when none) · button **"Compare with Rev A"** (any earlier version).

**Tabs:**

| Tab | Content | Source |
|---|---|---|
| **Overview** | Six "connected records" tiles: Complaints · Investigations · Trends to review · CAPAs and effectiveness checks · Risks · Authority reports. Each tile: the count for this version, the newest three items (each a link), "See all" (opens the Records tab on that list). Below: a small **complaints per month** chart for each version (12 months), with markers at each version release and each recorded change. Then **Data limitations** (exists). | New `links` endpoint (6.2) + the light Product 360 read |
| **Configuration** | Components of the version, each with its supplier(s) as links to Supplier 360, the date each supplier link took effect, and "2 recorded suppliers" when there are two. **Compare** mode: two columns (earlier version · this version); rows added, removed or with a different supplier are marked; a change record that affects a row is named beside it ("SAMPLE-CHG-014, effective 80 days ago"). | Product 360 `configuration`, read for both versions |
| **Lots** | The version's lots: made on, site, units released, complaints, complaints per 1,000 units (or "units not known"), the genealogy's component lots ("Pressure sensor lot NS-SL-2417"), distribution imported or not. Sorted with complaints first. | Product 360 `manufacturing` + one count query + one genealogy query |
| **Changes** | The **product's** changes only (fix of OD-11): those recorded as affecting a component of any of its versions, or the product itself. Each: ID, type, effective date, the components it affects, and **"Complaints on affected versions: before it took effect N · after M"**. The words "MDARIX lists what was recorded; it does not infer a cause." | `reality_relationships` AFFECTS, as `insight.version_changes()` |
| **Records** | The full lists, paged (20 at a time): complaints (with origin, status, problem code, lot, a link to the complaint page), investigations (state, version, owner), trends to review, CAPAs (QMS reference, due date, effectiveness check: planned / effective / not effective, round, signed by), risks, authority reports (market, form, state, submitted on, authority reference). | `links` endpoint, one list per call |
| **Version story** | The existing `ProductVersionStory`, restyled into hero cards | `/versions/{id}/story` (unchanged) |

Dropped from the new page (kept on the classic full product, OD-10): "Risks & controls" (controls and failure modes are organisation-wide, not this product's) and "Timeline" (built per complaint; too heavy at 5,000).

### 3.4 Links into Product 360, and back

| From | Link | Lands on |
|---|---|---|
| Complaint page head ("Complaint · PulseWatch 410 · Rev A") | The product and version become one link | Product 360, that version, Overview |
| Investigation summary (product and version line) | "OrbitCare 300 · Rev B" as a link | Product 360, the investigation's version (`investigation_versions()`: the version most of its complaints carry) |
| Trends › Trend check card (product · version line) | "Product 360" link beside it | Product 360, that version, Overview |
| Product 360 → each record | Complaint → complaint page; investigation → Investigations › Summary; trend → Trends › Trends to review?signal=; CAPA / effectiveness check → Records › Effectiveness checks?capa=; risk → Records › Risk file input; report → Reports?report= | The existing `newRecords` addresses (`linkTable.json`) |

New record kinds in `linkTable.json` `newRecords`: `product` → Product 360 › Products, param `product`; `supplier` → Product 360 › Suppliers, param `supplier`. Addresses use the identifiers people read (`?product=SAMPLE-ORBIT-300&version=Rev B`, as Trend check does since 0.10.71); the server also accepts the record ID or MDARIX ID.

### 3.5 Origin on every record
One rule, one backend function (`product360/origin.py`, from columns that exist today, no B2 column):

| `source_system` | Chip | Detail line |
|---|---|---|
| `MDARIX_SAMPLE` | **Sample** | "Fictional sample data" |
| `TRIAL_UPLOAD`, `CSV_IMPORT` | **Your import** | "Imported on <ingestion date> · ID <source_identifier>" |
| starts with `MDARIX` (other than the sample) | **Created in MDARIX** | "Created on <created date>" |
| anything else (a pilot's system name) | **From <system>** | "ID <source_identifier> · last loaded <ingestion date>" |

After B2 lands, complaints also carry `last_synced_at` and `record_owner`; showing "last synced" from them is a follow-up, not W1 (keeps W1 independent of B2).

---

## 4. Supplier 360 (new)

### 4.1 The supplier list (tab "Suppliers")
A table in the hero list style (the list view picker and cards on a phone): name · origin · parts · products / versions using them · complaints on those versions (last 90 days) · open investigations touching them. Click a row to open the supplier.

### 4.2 One supplier's page
**Head:** name · origin chip · status · "Recorded supplier since <first part link date>".

**Tabs:**

| Tab | Content |
|---|---|
| **Overview** | The **pattern box** (4.3) first. Then tiles: Parts · Products and versions · Lots · Complaints (90 days) · Investigations · Changes · Evidence · CAPAs. Then the **trend**: complaints per month for each version that contains its parts (12 months), with markers where each part link took effect and where each change affecting its parts took effect. |
| **Parts and products** | Each part: ID, name, revision, "supplied since", other recorded suppliers of the same part. Under it, every product and version using it (links to Product 360). |
| **Lots** | `lot_impact.build()` with the supplier as the factor: every lot whose genealogy names one of its parts, units released, complaints, per 1,000, shipped and in stock, and the evidence line ("Lot genealogy: built with Pressure Sensor lot NS-SL-2417; NovaSense Components is a recorded supplier of it"). When no genealogy is imported: "Lot genealogy not imported. Lots are shown by version instead" and the versions' lots are listed with the line "The lot's version contains this supplier's part." Loaded when the tab opens. |
| **Complaints and investigations** | Complaints on versions containing its parts, paged, each with the basis of the link ("on a version that contains its Pressure Sensor" or, stronger, "on a lot whose genealogy names its sensor lot NS-SL-2417"). Investigations that hold any of those complaints, with how many of them each holds. |
| **Changes and evidence** | Changes recorded as affecting its parts, with the before/after split (as 3.3). **Incoming-inspection and other evidence** linked to the supplier or its parts (`evidence_entity_links`), with title, source, reliability and the investigation that holds it. **Evidence requests** sent to the supplier (`supplier_evidence_requests`): title, sent on, due, status, answer received. |
| **CAPAs** | CAPAs from investigations that hold its complaints ("from SAMPLE-INV-001") and CAPAs on products using its parts ("on OrbitCare 300"), each with its effectiveness check state. |

A line at the foot of CAPAs: **"Supplier corrective action requests (SCAR): planned for a later release."** Nothing more: SCAR is not in W1.

### 4.3 The pattern box ("Signals" view)
**The rule (P-1, version 1; fixed in code, stated on screen):**
- Look at the last 90 days.
- For each part of this supplier, take the versions that contain it.
- A **pattern to review** is shown when the **same problem code** has **2 or more complaints on each of 2 or more of those versions** (of one product or several).

**What the box says, always plainly:**

| Case | Wording (exact) |
|---|---|
| Pattern found (an imported example, not the sample) | "Pattern to review: **pressure reading high** on **3 versions of 2 products** that contain Kestrel Sensors parts. PUMP-200 Rev D: 9 complaints, 450 units released (20.0 per 1,000). … This is a pattern to review, **not a confirmed signal**. Exposure, period and data completeness need a person's assessment." Buttons: **"Open an investigation"**, or **"Open INV-0042 (covers 12 of these complaints)"** when one exists. |
| One version only | "NovaSense parts are in **1 product version**: OrbitCare 300 Rev B. Complaints on it in the last 90 days: 14, of 450 units released (31.1 per 1,000). Trends: 1 trend to review on this version. SAMPLE-INV-001 is open on 14 of these complaints. **No other product or version uses these parts, so a cross-product pattern cannot be seen.**" |
| Below the rule | "No problem repeats on more than one version that contains these parts in the last 90 days." Counts per version still shown. |
| Units unknown | The rate is left out: "units not known for 2 of 5 lots". Never a rate from partial units. |
| No parts | "No parts are recorded for this supplier, so nothing can be linked to it." |

(The numbers above are illustrative, from the seed lists; the build's test fixes the real ones. See section 12.)

**"Open an investigation"** opens the existing open-investigation flow (`investigation_open_router.py`) pre-filled with the product, version and the listed complaints. A person confirms; the button never opens one by itself. The investigation records "Opened from Supplier 360: pattern P-1 v1" as its source.

---

## 5. The sample story for WHIF, the seed changes and the demo click path

### 5.1 The story the pages tell
- **Product 360, OrbitCare 300:** Rev A (released day −360) used Precision Sensors' pressure sensor. Rev B (day −75) uses NovaSense's, with change SAMPLE-CHG-014 (day −80: supplier changed, incoming inspection cut from 32 to 13 units per lot). Pressure-alarm complaints rose after Rev B, mostly on lots 003 and 004 (sensor lot NS-SL-2417). SAMPLE-INV-001 is open; its evidence includes the incoming inspection results (2 of 13 sensors in lot 003 read 4–6% high). SAMPLE-CAPA-02 restores inspection to 32 units; its effectiveness check is planned (day +75), not yet recorded.
- **Supplier 360, NovaSense Components:** one part (the Rev B pressure sensor), one version, lots 003–008 by genealogy, the complaint rise, SAMPLE-INV-001, the inspection evidence, CAPA-02. The pattern box says plainly that only one version uses its parts.
- **Precision Sensors Ltd** (the contrast): parts in all three products; complaints on all of them, but no problem repeats across versions, so **no pattern** is shown. A good demo of restraint.

### 5.2 Seed changes (new trials; running trials only on "refresh running trials")
All in a new module `trial/sample_supply.py`, called once from `sample_clock.seed_sample` after `stage_sample_lot_impact`. Every row is reached by `sample_removal.plan` through its foreign keys (components, versions, suppliers, evidence), so removal, restart and the sample clock's day move take it with no change there.

| # | Seed | Why | J2 / clock check |
|---|---|---|---|
| S1 | **Rev A configuration for all three sample products.** OrbitCare: a new component row `SAMPLE-ORBIT-300-C1`, revision **"Rev A"**, "Pressure Sensor (Sample)", supplied by **Precision Sensors** (effective day −360), linked to Rev A; the existing C2 and C3 also linked to Rev A. PulseWatch and VentraLink: their existing C1–C3 linked to Rev A too. | Rev A vs Rev B compare; the WHIF flagship complaint SAMPLE-RV-11 is on **PulseWatch Rev A**, whose product page would otherwise show "no components". | The new Rev A sensor has **no** AFFECTS link, so `version_changes()` and the trend cards show no change on any Rev A (checked: the join is change → component → version). No complaint, lot or quantity changes: the trend check, signals and the 0/7/15/29 story read the same. The unique key (tenant, identifier, revision) allows the second C1 row. |
| S2 | **Evidence links**: SAMPLE-EV-001 (supplier change record) and SAMPLE-EV-002 (incoming inspection) linked (`evidence_entity_links`) to the NovaSense supplier and to the Rev B pressure sensor. | Supplier 360's inspection evidence, traceable to its records. | Adds links only; evidence content and the signed decision brief are untouched. |
| S3 | **SAMPLE-CAPA-02 linked to SAMPLE-INV-001** (`capas.investigation_id`; today `None`, `sample_data.py:791`). | CAPA shows "from SAMPLE-INV-001" on both pages. | **Needs a check in the build:** Records › Effectiveness checks and the J2 story read this CAPA. OD-4. |
| — | **Not seeded:** a second product with NovaSense parts. | Would invent a cross-product pattern for show. The positive case is covered by tests (S360-06). OD-6. | — |
| — | **Not seeded:** Rev A lot genealogy. | Lots 001–002 stay "genealogy not imported": the honest empty state on stage. | — |

**Running trials** (`scripts/refresh_trial_story.py`, a 0.10.94 step after B2's 0.10.93 step): adds S1–S3 only where the sample exists and only where the rows are missing; idempotent; never touches the trial's own records; the sample clock rules of 0.10.92 apply unchanged (the new rows move with the sample only while the clock runs).

### 5.3 The demo click path (about 80 seconds)
Starting point: Home, Admin persona, sample data.

| t (s) | Click | What the audience sees |
|---|---|---|
| 0 | Rail **Products** | Three product cards. OrbitCare 300 shows a "trend to review" dot. |
| 8 | **OrbitCare 300** card | Rev B selected. Tiles: complaints, SAMPLE-INV-001, 1 trend to review, CAPA-02 with "effectiveness check planned", 2 risks. Origin chip "Sample". |
| 18 | **Compare with Rev A** | Configuration side by side: Pressure sensor, Precision Sensors → **NovaSense Components**; "SAMPLE-CHG-014: supplier changed; incoming inspection 32 → 13 units per lot". |
| 30 | **Lots** tab | Lots 003 and 004 on top: most complaints, the highest rate per 1,000; genealogy "sensor lot NS-SL-2417". |
| 40 | **NovaSense Components** (link in the compare row) | Supplier 360. The pattern box: one version, the counts and units, "not a confirmed signal", "SAMPLE-INV-001 is open on these complaints". |
| 55 | **Changes and evidence** tab | Incoming inspection results, lots 003–004 (2 of 13 read high), with its source; complaints before the change vs after. |
| 65 | **Open SAMPLE-INV-001** | The investigation; its product line links back to OrbitCare 300 Rev B. "Every record connects both ways." |
| 80 | End | |

For the main WHIF flow (one complaint, five decisions, on SAMPLE-RV-11): the complaint page's product line opens **PulseWatch 410 Rev A** in one click, with its configuration (S1), lots, the complaint, and "No risks recorded in MDARIX for this product" (the sample's deliberate risk-file gap).

---

## 6. Data and API

### 6.1 Principles
- **Reuse `product360`.** No new tables. **No migration** (6.6).
- Every query names `tenant_id = :tenant_id` on **every** table it joins, and runs on the data-plane session (`scoped_bind(get_data_plane_db)`, row-level security as today). A record of another organisation answers 404 "not found", never 403.
- IDs: the record ID, MDARIX ID (`business_id`) or the source identifier, resolved inside the tenant.
- Lists are paged with the existing `Page` dependency (`X-Total-Count`, `X-Next-Offset`).
- Reads write nothing, except Product 360's existing temporal-retrieval audit event (kept as it is).

### 6.2 Product 360 endpoints

| Endpoint | Change | Queries |
|---|---|---|
| `GET /api/v1/products` | Add `?counts=1`: one extra aggregate for the page's products (open complaints, open investigations, open signals, open CAPAs, newest version). | 3 |
| `GET /api/v1/products/{id}/product-360` | Add `?light=1`: skips the complaint rows, evidence, failure modes, controls and the timeline; returns their **counts** only. `changes()` becomes **product-scoped** (also without `light`: a bug fix). | 8 (light), +1 audit write |
| **New** `GET /api/v1/products/{id}/links?version=&kind=&offset=&limit=` | Without `kind`: the six tiles (count + newest 3 each) and the monthly series. With `kind=complaints|investigations|signals|capas|risks|reports`: that list, paged. | 9 (tiles), 2 (one list) |
| `GET /api/v1/products/{id}/versions/{vid}/story` | Unchanged | as today |

**Queries of `links` (tiles), all with `:t` = tenant, `:p` = product, `:v` = version (or all versions when none is chosen):**
1. Product and version resolve: `SELECT … FROM products WHERE tenant_id=:t AND (id=:ref OR business_id=:ref OR product_identifier=:ref)`; versions likewise.
2. Complaints: `SELECT id, business_id, complaint_identifier, event_timestamp, status, problem_code, lot_batch_id, source_system, source_identifier, count(*) OVER () AS total FROM complaints WHERE tenant_id=:t AND product_id=:p AND product_version_id=:v ORDER BY event_timestamp DESC NULLS LAST, complaint_identifier LIMIT 3`.
3. Monthly series: `SELECT product_version_id, date_trunc('month', event_timestamp) m, count(*) FROM complaints WHERE tenant_id=:t AND product_id=:p AND event_timestamp >= :since GROUP BY 1,2`.
4. Investigations: `product360.investigations()` + `investigation_versions()` (2 queries), filtered to `:v` in code.
5. Signals: `SELECT id, business_id, product_version_id, problem_key, status FROM signals WHERE tenant_id=:t AND product_id=:p AND status = ANY(:open)` (`OPEN_SIGNAL_STATUSES`).
6. CAPAs with the latest effectiveness check: `SELECT DISTINCT ON (k.id) k.id, k.business_id, k.capa_identifier, k.title, k.status, k.due_at, k.effectiveness_check_at, k.qms_reference, k.investigation_id, k.source_system, ec.status AS check_status, ec.round, ec.planned_on, ec.signed_by, ec.signed_at FROM capas k LEFT JOIN capa_effectiveness_checks ec ON ec.tenant_id=k.tenant_id AND ec.capa_id=k.id WHERE k.tenant_id=:t AND (k.product_id=:p OR k.investigation_id IN (SELECT id FROM investigations WHERE tenant_id=:t AND product_id=:p)) ORDER BY k.id, ec.round DESC NULLS LAST`.
7. Risks: `SELECT … FROM risks WHERE tenant_id=:t AND product_id=:p AND (product_version_id IS NULL OR product_version_id=:v)`.
8. Authority reports: `SELECT o.id, o.market, o.form_code, o.report_type, o.state, c.complaint_identifier, s.submitted_at, s.authority_reference, count(*) OVER () AS total FROM report_obligations o JOIN complaints c ON c.tenant_id=o.tenant_id AND c.id=o.complaint_id LEFT JOIN LATERAL (SELECT submitted_at, authority_reference FROM report_submissions WHERE tenant_id=:t AND obligation_id=o.id ORDER BY attempt DESC LIMIT 1) s ON true WHERE o.tenant_id=:t AND c.product_id=:p AND c.product_version_id=:v ORDER BY o.created_at DESC LIMIT 3`.

**Product-scoped changes** (replaces `changes()`): `SELECT DISTINCT ch.* , rr.target_entity_id FROM reality_relationships rr JOIN changes ch ON ch.tenant_id=rr.tenant_id AND ch.id=rr.source_entity_id WHERE rr.tenant_id=:t AND rr.source_entity_type='Change' AND rr.relationship_type='AFFECTS' AND ((rr.target_entity_type='Component' AND rr.target_entity_id IN (SELECT pc.component_id FROM product_components pc JOIN product_versions pv ON pv.tenant_id=pc.tenant_id AND pv.id=pc.product_version_id WHERE pc.tenant_id=:t AND pv.product_id=:p)) OR (rr.target_entity_type='Product' AND rr.target_entity_id=:p))`. The before/after split is one grouped count of complaints on the affected versions by `event_timestamp < effective_timestamp`.

### 6.3 Supplier 360 endpoints (new router `product360/supplier_router.py`, included in `main.py`)

| Endpoint | Returns | Queries |
|---|---|---|
| `GET /api/v1/suppliers?offset&limit` | Paged list with parts, products, versions, complaints (90 days), open investigations | 3 |
| `GET /api/v1/suppliers/{id}` | The page: head, parts and products, counts, pattern box, trend, changes, evidence, evidence requests, CAPAs, investigations, newest complaints | 12 |
| `GET /api/v1/suppliers/{id}/complaints?offset&limit` | Complaints on versions containing its parts, paged, with the basis of each link | 2 |
| `GET /api/v1/suppliers/{id}/lots` | `lot_impact.build(db, t, {"kind": SUPPLIER, "id": s}, [])`, or the by-version fallback | ≈6 |

**Queries of the supplier page** (`:t` tenant, `:s` supplier; `:c` its part IDs, `:v` the versions containing them, both from query 2):
1. Supplier resolve (ID, MDARIX ID or `supplier_identifier`), with `source_system`, `source_identifier`, `ingestion_timestamp`.
2. Parts, versions, products: `SELECT c.id, c.component_identifier, c.name, c.revision, cs.effective_timestamp AS supplied_from, pv.id AS version_id, pv.version_identifier, p.id AS product_id, p.name AS product_name, (SELECT count(*) FROM component_suppliers o WHERE o.tenant_id=:t AND o.component_id=c.id) AS suppliers FROM component_suppliers cs JOIN components c ON c.tenant_id=cs.tenant_id AND c.id=cs.component_id LEFT JOIN product_components pc ON pc.tenant_id=c.tenant_id AND pc.component_id=c.id LEFT JOIN product_versions pv ON pv.tenant_id=pc.tenant_id AND pv.id=pc.product_version_id LEFT JOIN products p ON p.tenant_id=pv.tenant_id AND p.id=pv.product_id WHERE cs.tenant_id=:t AND cs.supplier_id=:s`.
3. Complaints by version and problem (pattern box and tiles): `SELECT product_version_id, coalesce(problem_code,'') AS problem, count(*) AS n, count(*) FILTER (WHERE event_timestamp >= :since90) AS recent FROM complaints WHERE tenant_id=:t AND product_version_id = ANY(:v) GROUP BY 1,2`.
4. Units per version: `SELECT product_version_id, sum(quantity), count(*) FILTER (WHERE quantity IS NULL) FROM lot_batches WHERE tenant_id=:t AND product_version_id = ANY(:v) GROUP BY 1`.
5. Monthly trend: as 6.2 query 3, on `product_version_id = ANY(:v)`.
6. Newest complaints (5) with `count(*) OVER ()`.
7. Investigations holding those complaints: `SELECT i.id, i.business_id, i.investigation_identifier, i.status, i.opened_at, i.source_system, count(*) AS held FROM investigations i JOIN investigation_complaints ic ON ic.tenant_id=i.tenant_id AND ic.investigation_id=i.id JOIN complaints c ON c.tenant_id=ic.tenant_id AND c.id=ic.complaint_id WHERE i.tenant_id=:t AND c.product_version_id = ANY(:v) GROUP BY i.id`.
8. Changes affecting its parts: the 6.2 change join on `target_entity_type='Component' AND target_entity_id = ANY(:c)`, plus the before/after count.
9. Evidence: `SELECT e.id, e.business_id, e.evidence_identifier, e.title, e.evidence_type, e.reliability_status, e.source_reference, e.investigation_id, l.entity_type FROM evidence_entity_links l JOIN evidence e ON e.tenant_id=l.tenant_id AND e.id=l.evidence_id WHERE l.tenant_id=:t AND ((l.entity_type='Supplier' AND l.entity_id=:s) OR (l.entity_type='Component' AND l.entity_id = ANY(:c)))`.
10. Evidence requests: `SELECT business_id, title, status, created_at, due_at, responded_at FROM supplier_evidence_requests WHERE tenant_id=:t AND supplier_id=:s ORDER BY created_at DESC LIMIT 20`.
11. CAPAs: as 6.2 query 6, with `(k.investigation_id = ANY(:investigations) OR k.product_id = ANY(:products))`, each marked "from <investigation>" or "on <product>".
12. Open signals on `:v` (for "trends to review" in the box).

The pattern rule P-1 runs in Python on query 3's rows: no extra query. It is a pure function with its own unit tests.

### 6.4 Shapes (abridged)
- Every record row carries `origin: {kind: SAMPLE|IMPORTED|MDARIX|EXTERNAL, label, system, external_id, loaded_at}`.
- Every link row carries `basis`: a short sentence saying why it is linked ("on a version that contains its Pressure Sensor"; "lot genealogy names sensor lot NS-SL-2417"; "CAPA from SAMPLE-INV-001").
- The pattern box: `{rule: "P-1", rule_version: 1, window_days: 90, found: bool, versions: [{product, version, problem, recent, units, units_unknown_lots, per_1000}], investigations: [{ref, held}], text}`.

### 6.5 Performance budget
**Target:** p95 under 1 s per read, on the sample and on the runbook's synthetic 5,000-complaint export (five products, forty lots), measured in-process as `docs/runbooks/LOAD_AND_FAILURE_DRILLS.md` does; query counts recorded the same way.

| Read | Queries | Why it should fit | Risk |
|---|---|---|---|
| Product list with counts | 3 | Aggregates over ≤ 5,000 complaints | Low |
| Product 360, light | 8 + audit | No complaint rows, no timeline | Low |
| Product links, tiles | 9 | Each list `LIMIT 3` + window count; one monthly aggregate | Low |
| Supplier list | 3 | One aggregate per page of suppliers | Low |
| Supplier page | 12 | Aggregates on versions (≤ ~10 in a 5,000 import); lists capped | Medium: query 7 on investigations × complaints |
| Supplier lots | ≈6 | `lot_impact.build`, already used by Lot impact | Low |

- Product 360 is **not** in the runbook's table today. Its full read (all complaints + timeline) is the likely slow path; W1's pages use the light read only. The classic full product keeps the full read.
- The workspace's global product context (`useWorkContext`) still reads the full Product 360 on the classic navigation. W1 does not change that; the new navigation does not use it on these pages.
- **Indexes:** today only `complaints (tenant_id, product_id, event_timestamp)` exists. There is none on `complaints.product_version_id`, `complaints.lot_batch_id` or `lot_components.component_id`. At 5,000 rows a scan is a few milliseconds, so none is planned.

### 6.6 Migration
**None planned.** W1 adds no table and no column: the seed uses existing tables, origin uses existing columns.
If the 5,000-complaint measurement misses 1 s, the fallback is one expand-only index migration:
- `tr20_product_supplier_indexes.py`, revision `tr20p360indexes`, down_revision **`tr19casesescalation`** (B2's).
- Indexes: `complaints (tenant_id, product_version_id, event_timestamp)`, `lot_components (tenant_id, component_id)`.
- **Merge order:** B2 first (tr19), then W1 (tr20). On mvp-1.0: a merge revision `md66` after B2's `md65`, same pattern.
- This is OD-7.

---

## 7. The Decision Framework

Product 360 and Supplier 360 make **no decision**. They show the five elements of the decisions around a product or supplier, mostly as links.

| Element | Product 360 | Supplier 360 |
|---|---|---|
| **Evidence** | The version's complaints, lots, genealogy, changes, evidence count; each with its origin | The supplier's parts, the lots that contain them, inspection evidence, evidence requests and answers; each with its origin and the basis of the link |
| **Intelligence** | The Trends result for the version (link); Rev A vs Rev B compare; complaints per month by version; before/after each change | The pattern box (P-1), with counts, units and rates; complaints per month by version, marked at each part link and change |
| **Rules** | The trend rule and its version, as Trends shows it (link); the reportability rule on each linked report (link) | Rule P-1 v1, its window and thresholds printed in the box; "a pattern to review, not a confirmed signal" (CP-15) |
| **Human judgement** | Investigation conclusions, signed decisions, effectiveness checks (signed by, when) shown as links | "Open an investigation" is a person's action, confirmed; existing investigations named with their owners |
| **Traceability** | Every count opens its records; changes are listed with dates, never as causes (IV-14) | Every link says why it exists; the same read always gives the same answer (no stored state) |

---

## 8. Operating modes

| | MDARIX Connect (master data from the customer's ERP/PLM) | MDARIX Complete |
|---|---|---|
| Products, versions, components, suppliers, lots, changes | Imported; **read-only**; origin chip "From <system> · ID · last loaded"; note "Correct it in <system> and import again" | Kept in MDARIX by import today (native editing is later, operating-modes §3); read-only on these pages; origin "Your import" |
| Complaints, investigations, CAPAs, reports linked | Open on their own pages, with their own mode rules (B2 for complaints) | Same |
| What W1 adds | No edit button anywhere; origin everywhere; the same read in both modes | Same |

Both modes give the same pages and the same answers. Decisions never depend on where a record lives (operating-modes rule 4).

---

## 9. Scenarios (added to `scenario-register.md`)

**Product 360 (P360)**

| ID | Scenario | Expected behaviour | Test |
|---|---|---|---|
| P360-01 | Product with no complaints (imported, with versions and lots) | Tiles read 0; "No complaints recorded for this version"; no trend link; no error | D, vitest |
| P360-02 | Version with no lots | Lots tab: "No lots recorded for Rev X"; complaints still listed; rates "units not known" | D |
| P360-03 | Imported product without versions | Switcher "No versions recorded"; Configuration and Lots say a version is needed; complaints listed at product level; a data limitation shown | D |
| P360-04 | Change after the incident (IV-14) | The change is listed with its date; complaints before it are counted under "before" and never listed as related to it | D |
| P360-05 | Rev A vs Rev B compare (sample) | Pressure sensor row: Precision Sensors → NovaSense, SAMPLE-CHG-014 named; other rows unchanged | D, vitest |
| P360-06 | Origin on every record | Sample · Your import (date, ID) · Created in MDARIX · From <system>, per the 3.5 table | U |
| P360-07 | Connect: imported master data | No edit control; "Correct it in <system> and import again" | vitest |
| P360-08 | Links both ways | Complaint, investigation and trend card → product and version in one click; back to each record kind from Product 360 | vitest, link-target test |
| P360-09 | CAPA with an effectiveness check planned, not recorded | "Effectiveness check planned for <date>; not yet recorded"; never "effective" | D |
| P360-10 | Persona without the Products tab (Regulatory Leader, Complaint Handler, Decision Maker, Service Desk) | No rail entry; a link opens the page, shown as the extra tab; read-only | vitest, personas test |
| P360-11 | Another organisation's product ID | 404 "Product not found"; no counts leak | D (cross-tenant routes) |
| P360-12 | 5,000-complaint organisation | p95 < 1 s for the list, the light read and the links tiles; query counts as 6.2 | P (measured) |
| P360-13 | Sample removed, restarted, or read on day 0/7/15/29 | New seed rows removed and re-seeded; the page reads the same relative story | D (`test_sample_story_days.py`) |
| P360-14 | An old "Products" link on the new navigation | Opens Product 360 | U (link table) |

**Supplier 360 (S360)**

| ID | Scenario | Expected behaviour | Test |
|---|---|---|---|
| S360-01 | Supplier with no parts | "No parts are recorded for this supplier, so nothing can be linked to it"; counts 0; no pattern | D |
| S360-02 | One part used by several products | Each product and version listed under the part; P-1 evaluated across them | D |
| S360-03 | A lot with parts from two suppliers (sample lot 003: NovaSense sensor, Precision board) | The lot on both pages, each with its own genealogy line; its complaints counted on both as "on lots containing its parts", never "caused by" | D |
| S360-04 | A part with two recorded suppliers; genealogy does not name the supplier | Both suppliers listed on the part; the lot line says "<supplier> is a recorded supplier of it"; no attribution to one | D |
| S360-05 | Supplier change after the incident (IV-14) | Before/after split; complaints before the change never listed under it | D |
| S360-06 | Same problem on 2+ versions with its parts | Pattern box with counts, units, rates, "not a confirmed signal"; "Open an investigation" | U (P-1), D |
| S360-07 | Pattern already under investigation | "Open SAMPLE-INV-001 (covers N of these complaints)" instead of a new one | D |
| S360-08 | One version only, or below the threshold (CP-15) | No pattern statement; plain counts; the one-version wording | U |
| S360-09 | Units released unknown for some lots | No rate; "units not known for X of Y lots" | U |
| S360-10 | NovaSense sample story | The 5.1 story: one version, lots 003–008, SAMPLE-INV-001, inspection evidence, CAPA-02 | D |
| S360-11 | Inspection evidence and evidence requests | Linked evidence with source and reliability; requests with status and answer | D |
| S360-12 | SCAR | Not offered; the "planned for a later release" line only | vitest |
| S360-13 | Persona without the Products tab | As P360-10 | vitest |
| S360-14 | Another organisation's supplier ID | 404; no counts leak | D (cross-tenant routes) |
| S360-15 | 5,000-complaint organisation | p95 < 1 s for list, page, complaints and lots; query counts as 6.3 | P |
| S360-16 | Imported supplier (Connect) | Read-only; origin chip with system, ID and last loaded | vitest |

**30 scenarios.** Test kinds: U unit, D database (targeted pytest), vitest, P performance measurement.

---

## 10. Build plan

### 10.1 Commits, in order, with targeted tests
Owner's rule: targeted tests per commit; the full release gates once, on the final commit, only when the owner says.

| # | Commit | Targeted tests |
|---|---|---|
| 1 | **Product 360 backend.** `origin.py`; `light=1`; product-scoped `changes()` with the before/after split; `links` endpoint; `counts=1` on the list | New `tests/test_product360_links.py` (D: counts, paging, origin, IV-14 split, product-scoped changes); `tests/test_day7_product360_temporal.py` (regression); `tests/test_cross_tenant_routes.py` extended |
| 2 | **Supplier 360 backend.** `supplier_router.py`, service, P-1 as a pure function, lots via `lot_impact.build` | New `tests/test_supplier360_rules.py` (U: P-1 wording, thresholds, units unknown); new `tests/test_supplier360_api.py` (D: S360-01 to -05, -07, -11, -14); `tests/test_lot_impact_api.py` (regression); cross-tenant routes extended |
| 3 | **Seed.** `trial/sample_supply.py` (S1–S3), one call in `sample_clock.seed_sample`; the 0.10.94 step in `refresh_trial_story.py` | `tests/test_sample_story_days.py` (J2 unchanged); new `tests/test_sample_supply.py` (D: idempotent; Rev A has no change on its trend card; removal and restart take the rows; refresh adds only missing rows) |
| 4 | **Navigation.** Section `Product 360` (`workspaceContext.tsx`), rail key `products` (`HybridShell.tsx`: PERSONA_TABS, TAB_ICON, RAIL_GROUPS), persona tabs (`personas.py`), `linkTable.json` (newPlaces, newMenu, newRecords, newHomes), render line in `UserWorkspace.tsx` | `release0090Shell.test.tsx`, `releaseC1073.test.tsx` updated; `tests/test_link_targets.py`; `tests/test_release_c1_0_10_73.py` (persona tabs) |
| 5 | **Product 360 page** (hero): list, head, tabs, compare, Records lists | New `productHub.test.tsx` (vitest: empty states, compare, origin chips, no edit controls, links out) |
| 6 | **Supplier 360 page** (hero): list, head, tabs, pattern box, trend | New `supplierHub.test.tsx` (vitest: pattern wording, SCAR line, one-version wording) |
| 7a | **Links in, low conflict:** Trend check card, investigation summary | `Investigations.test.ts`, a Trend check test extended |
| 7b | **Links in, after B2 is merged (rebase first):** complaint page head; `event_view` gains `product_id`, `product_version_id` | `complaintPage.test.ts`; a DB test on the event payload |
| 8 | **Measurement** on the 5,000-complaint export; results added to `LOAD_AND_FAILURE_DRILLS.md`. If a read misses 1 s: OD-7 (tr20) | Measurement only |
| 9 | CHANGELOG, user guide, release notes, the demo click path | — |
| — | Release gates once on the final commit, then the owner's "approve" | Per the release flow |

### 10.2 Files touched, with B2 conflict risk

| File | W1 change | B2 touches it? | Risk | Handling |
|---|---|---|---|---|
| `backend/app/product360/service.py`, `schemas.py` | light read, changes fix | No | None | — |
| `backend/app/product360/origin.py`, `supplier_router.py`, `supplier_service.py` (new) | New | No | None | — |
| `backend/app/main.py` | links endpoint; include supplier router | Possibly (router includes) | Low | Keep W1's additions in one block |
| `backend/app/trial/sample_supply.py` (new) | Seed | No | None | — |
| `backend/app/trial/sample_clock.py` | One call line in `seed_sample` | Unclear (B2 seeds CASE-11; the spec says `worked_on` needs no change) | Low | One line, after `stage_sample_lot_impact` |
| `scripts/refresh_trial_story.py` | 0.10.94 step | **Yes** (0.10.93 step) | Medium | Append after B2's step at rebase |
| `access_control/personas.py` | "products" in five persona tuples | **Yes** (Service Desk persona; handler's sub-line "Calls" → "Cases") | Medium | W1 does not edit the handler line; resolve by keeping both |
| `frontend/src/app/linkTable.json` | New places and records | **Likely** (B2 renames "Calls to check" → "Cases" in `newHomes`) | Medium | Different blocks; re-run `test_link_targets.py` after merge |
| `frontend/src/features/workspace/HybridShell.tsx` | Rail key, icon, group | B2 says no rail change; may add a persona colour | Low | — |
| `frontend/src/features/workspace/workspaceContext.tsx`, `UserWorkspace.tsx` | One section | Possibly | Low | — |
| `frontend/src/features/workspace/sections/TrendCheck.tsx` | Product link | No | Low | Commit 7a |
| `frontend/src/features/workspace/sections/Investigations.tsx` | Product link | **Yes** (Case → Investigation rename) | Medium | Commit 7a, small; or move to 7b if the rename lands first |
| `frontend/src/features/workspace/sections/ComplaintPage.tsx` | Product link in the head | **Yes** (origin line, "The case", Service, stage line) | **High** | Commit 7b, written **after** B2 is merged |
| `backend/app/oversight/router.py` (`event_view`) | Two payload keys | **Yes** (origin, escalation) | **High** | Commit 7b, after B2 |
| CHANGELOG, user guide, release notes | Entries | **Yes** | Certain, trivial | At rebase |
| Migrations | None | B2: tr19 | None | If OD-7: tr20 after tr19 |

**mvp-1.0:** W1 adds no migration, so no merge revision. `git diff v0.10.92 mvp-1.0` shows differences in `main.py`, `oversight/router.py`, `sample_clock.py`, `UserWorkspace.tsx`, `ComplaintPage.tsx`, `Investigations.tsx` and `TrendCheck.tsx` (mvp-1.0 not yet carrying 0.10.92). The usual forward merge applies.

### 10.3 Estimate

| Commit | Days |
|---|---|
| 1 Product 360 backend | 1.5 |
| 2 Supplier 360 backend | 2 |
| 3 Seed and refresh | 1 |
| 4 Navigation | 0.5 |
| 5 Product 360 page | 2.5 |
| 6 Supplier 360 page | 2.5 |
| 7a + 7b Links in | 1 |
| 8 Measurement | 1 |
| 9 Docs, gates, fixes | 1.5 |
| **Total** | **13.5 working days** |

**Does it fit before 4 Dec?**
- With the green signal on 9–10 Nov and its own build stream, commits 1–7a and 8 finish around **27 Nov**.
- B2 targets **28 Nov**. W1 then rebases, does 7b and the gates: **1–2 Dec**. Live by **2–3 Dec**.
- **It fits, with about one day of slack.** It does not fit if B2 slips past 1 Dec, or if both items share one build stream.

**Minimal WHIF scope (fallback, about 10 days):**
- Product 360 in full (commits 1, 3, 4, 5, 7, 8).
- Supplier 360 **read-only and simpler**: no supplier list cards (a plain table), no trend chart, Changes and evidence folded into Overview, no version compare on Product 360.
- Keeps the demo click path except step 18 s (compare); the Configuration tab still shows NovaSense on Rev B and Precision on Rev A by switching versions.

**Checkpoint (recommended): 20 Nov.** If commits 1–4 are not done, switch to the minimal scope (OD-8).

---

## 11. Open decisions, with recommendations

| # | Decision | Options | Recommendation |
|---|---|---|---|
| OD-1 | Where Product 360 sits | Work › Products (own destination) · a tab under Trends | **Work › Products, after Trends, with tabs Products and Suppliers.** Under Trends hides it from personas without Trends and mixes two questions. |
| OD-2 | Personas with the Products tab | As 3.1 · everyone | **As 3.1** (Admin, Quality, Investigator, Risk, Executive). Others reach it by links. |
| OD-3 | Seed Rev A configurations (S1) | All three products · OrbitCare only · none | **All three**, so the flagship RV-11 (PulseWatch Rev A) opens a full page. |
| OD-4 | Link CAPA-02 to SAMPLE-INV-001 and the evidence to NovaSense (S2, S3) | Yes · evidence links only · no | **Yes, both**, subject to the build confirming Records and the J2 story read the same. Running trials only on "refresh running trials". |
| OD-5 | Pattern rule P-1 | As 4.3 (same problem, ≥ 2 complaints on each of ≥ 2 versions, 90 days) · other thresholds | **As 4.3**, fixed in W1; configurable later with the trend rules (B4). |
| OD-6 | A positive cross-product example in the sample | Add a NovaSense part to a second product · keep the data honest | **Keep it honest.** Precision Sensors shows the "no pattern" case; the positive case is tested (S360-06). |
| OD-7 | Index migration | None · tr20 now · tr20 only if measurement fails | **Only if the 5,000-complaint measurement misses 1 s.** Then tr20 after B2's tr19. |
| OD-8 | Scope | Full (13.5 days) · minimal (about 10) | **Full, with the 20 Nov checkpoint** to drop to minimal. |
| OD-9 | If B2 is not approved by 1 Dec | Hold W1 too · ship W1 first | **Ship W1 first** (it has no migration and no B2 dependency; 7b then targets the 0.10.92 complaint page). Release numbers swap. |
| OD-10 | The classic "Risks & controls" and "Timeline" tabs | Bring them · drop them on the new page | **Drop** on the new page: controls and failure modes are organisation-wide, and the timeline is too heavy at 5,000. Kept in the classic full product. |
| OD-11 | Fix Product 360's "Changes" (lists every change in the organisation) | Fix now · leave | **Fix now.** It also corrects the classic full product. |
| OD-12 | Release numbers | W1 = 0.10.94, B3 renumbered · other | **W1 = 0.10.94; B3 takes the next free number after WHIF.** The backlog lists both as 0.10.94 today. |

---

## 12. What could not be verified
- **Nothing was run.** No API call, page, query count or timing was measured. Query counts are counted from the design.
- **Product 360's current speed** at 5,000 complaints: not in the runbook; the risk in 6.5 is inferred from the code (unpaged complaints, per-complaint timeline, a JSON join to staged records for evidence).
- **Sample numbers** in 4.3 and 5.3 (14 pressure-alarm complaints on Rev B, 9 on lot 003 and 5 on lot 004, 450 units) are derived by hand from `sample_data.py` and the `sample_lot_impact.py` docstring. Routine complaints (`sample_dispositions.py`) may add to them. The build's tests fix the real figures.
- **Whether a trend to review (signal) exists** for OrbitCare Rev B at seed time, or only after the trend check runs: not checked.
- **S3 (CAPA-02 → INV-001):** not checked which screens and story ticks read `capas.investigation_id`.
- **The top bar's "Data shown" choice:** not checked whether it can filter master data the way it filters complaints.
- **Link-table order:** not checked whether `oldSections` ("Products" → Readiness) is applied before `newHomes` on the new navigation; `test_link_targets.py` will show it.
- **B2's code** does not exist yet. The conflict table is from B2's spec, not from its diff.
- **The hero components** (`DeviceIcon`, `StatusPill`, `heroPages.css`) were read by name only; their fit for cards and the compare view is a design assumption.
- **Production numbers:** in-process measurements only, as in the runbook.

## Design rule G-2 (owner approved 8 Nov 2026)
Operational parts of Product 360 and Supplier 360 (tabs, lists, tables, record panels) are flat: no decorative gradients, glass or glow. Hero styling only on the page header. Each W1 screen is checked against this rule before release.

## Owner decisions during the build (10 Nov 2026: "link CAPA, hide lots on pilots")
- **S3 seeded:** SAMPLE-CAPA-02 is linked to SAMPLE-INV-001; the closure check, Readiness, worksheets and the effectiveness check are verified with tests and the J2 story must read the same.
- **Supplier 360 lots are trial-only** (same rule as Lot impact, decision of 1 Nov): hidden on paid pilots, server-side and in the UI.


## Owner decisions, 10 Nov 2026 (after W1 run 2)
- The Work › Products tabs are named **"Product 360"** and **"Supplier 360"** (no clash with Settings › Products).
- PV-1: with a version chosen, investigations that record no version are listed under every version, marked "applies to the whole product" (never given a version they do not have). Confirmed.

## Approval record

| Field | Value |
|---|---|
| Approved | 7 Nov 2026 |
| Approver | Srinivas Telikicherla, Founder & CEO, QA/RA (owner) |
| Approval words, as recorded | "approve W1 spec" |
| Where recorded | the APPROVED note at the top of this spec |
| Planning copy | `MDARIX-planning/w1-product-supplier-360/spec.md` (reference only) |
| Form of approval | The owner's written reply, recorded in the spec on the day; not an electronic or wet signature. This section was added on 12 Nov 2026 (owner decision O29); the approved text above is otherwise unchanged, except that a DRAFT status line now reads APPROVED |
