# Changelog

All notable changes to MDARIX are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/).
The version being prepared is in `VERSION`; a release is the git tag `v<VERSION>` (`.github/workflows/release.yml`
builds, scans and publishes its images, and refuses a tag that does not match `VERSION`).

Every entry says what changed for the people who use or run MDARIX. Schema changes name their migration, so an
operator knows a release migrates the database.

## [Unreleased]

## [0.10.96] - not released yet (ships in the big-bang release)

B3: the US eMDR complete for manufacturers (initial report). No migration. The API and web images change.

### Tests

- FDA's "Manufacturer Follow-up" example and FDA's PDFs of the "Manufacturer Initial - Typical" and "Manufacturer
  Follow-up" examples (eMDR Implementation Package, files dated 5 Aug 2024) are kept byte-identical in
  `tests/fixtures/emdr_examples` with their SHA-256s. FDA's follow-up example validates against FDA's schema
  (`Con170227.xsd`), the one MDARIX validates with.

## [0.10.95] - not released yet (ships in the big-bang release)

Hardening: code-audit fixes 6-20 and the product-version audit (PV-1). No migration. The API image changes.

### Fixed

- Approving a report or signing a market conclusion re-reads the record after locking it, so a cancellation or edit
  made a moment earlier is no longer overwritten (a cancelled report can no longer turn back to approved).
- The old single reportability decision (before per-market assessment) is closed: a new "Not reportable" or "Reported"
  is refused and points to the market assessment (sign each market's conclusion; record a filed report with "Record
  the filing" on the signed reportable conclusion). Single decisions recorded earlier are still shown and still settle
  their complaint.
- FDA Form 3500A box H1 pre-fills "Death" only when the US assessment answers that the device caused or contributed
  to it (question 3), as it already did for "Serious injury".
- The awareness date on a report form (FDA box G3, and the same box on the EU, UK, India and Canada forms) is the
  organization's local day, as its own records show it, not the UTC day: an awareness at 07:00 IST prints that day
  for an organization in India. The deadline still counts from the market clock's day, which can be one day earlier.
- A complaint naming several countries counts each reporting window by the rule of the market that window covers, not
  the first country's (an India window on a "United States, India" complaint was one day late).
- A later import closes only the set-aside rows of the records it wrote (product version, bill-of-materials line,
  genealogy link, shipment), no longer every set-aside row that shares the first column.
- When one address refuses a notification email, the retry sends it to that address only; the others are no longer
  emailed again on every retry.
- An organization's file-storage quota counts only the files people upload, not the exports, reports and documents
  MDARIX makes; an upload over the quota is refused with "storage is full" (413) instead of a server error.
- A full data export has a size limit of 1 GB (`MDARIX_EXPORT_MAX_BYTES`): an organization whose files are larger is
  told so when it asks (413, "contact support to receive it in parts"), and an export whose zip is larger ends
  FAILED (`ExportTooLarge`) without retrying, instead of failing in memory after hours of retries.
- A password-reset or activation link used twice at the same moment works only once.
- A full data export writes binary columns (the stored copy of a submitted report) as base64 text that can be decoded
  back to the file, instead of Python byte text.
- A CSV import with a stray quote mark is refused with the line it is on ("Line 7: a quote mark ... is not closed"),
  instead of reading the rest of the file as one cell or failing with a server error.
- A Decision Brief's scope section shows how many complaints are in scope and how many are excluded (the
  screen read names the brief does not store, so these lines never appeared). Signed briefs are unchanged.

### Fixed: a record's version always belongs to its product (PV-1)

- Log a case refuses a lot of another product than the one chosen (422 `LOT_NOT_FOR_PRODUCT`); a lot given without a
  product gives the Case the lot's product, shown "(from the lot)". A lot with an unknown version is still taken.
  The identifier's source list offers "From the lot", so editing the Case later keeps that source.
- A case's workspace (and the AI context built from it) no longer picks a version: it uses the case's one version only
  when the scope names exactly one and every included complaint carries it. Otherwise it reads the whole product and
  says "no single known product version", with the scope's versions. The old decision record and the old brief store
  a version by the same rule (the old brief stored none, even for a one-version case).
- A complaints import refuses a row whose version is not its lot's version ("Lot L is of version Rev A, not 'Rev C'").
  A blank version cell no longer clears or replaces a stored version; a new complaint's version taken from its lot is
  shown "(from the lot)" in its searchable record. A re-upload cannot move a held complaint to another product (row
  error), and a version change of a complaint in a case is noted with the case, to check its scope.
- An investigations import refuses complaints of another product and a change of a held investigation's product; a
  CAPA naming an investigation must name the investigation's product. A re-upload that changes the product or version
  of a risk, requirement, investigation or CAPA is kept in the history of field changes, like a complaint's.
- A case scope refuses a lot of another product (422 `LOT_NOT_FOR_PRODUCT`; a lot with an unknown version is still
  allowed). Saving a scope warns "N included complaints have no product version", and the decision brief's scope
  section counts them (`unknown_version_count`, shown as "Complaints with no known version").
- A signal about one product version takes only complaints of that version (raising it or adding complaints:
  `COMPLAINT_NOT_FOR_VERSION`) and merges only signals of that version (`VERSION_MISMATCH`); a signal for the whole
  product still groups several versions.
- The trend check gives each product's "unknown version" group the age of that product's own first unknown-version
  complaint, not the organization's oldest: a product whose unknown-version complaints are new is SHORT_HISTORY
  instead of a significant rise.
- An open case covers a service-level recurrence or a complaint's recurrence trigger only for the versions its scope
  names (or for the whole product when it names none): an open Rev C case no longer hides three Rev D resolutions.
  The known-issue match says "another product version" when the case's scope does not cover the complaint's version.
- Ask, a stored AI interaction and the regulatory draft refuse a version of another product than the one named (or
  the case's), and a product other than the case's (422 `PRODUCT_VERSION_SCOPE_MISMATCH`, `PRODUCT_CASE_MISMATCH`),
  instead of storing or drafting from a contradictory pair.
- A version's story (Product 360, "The story of Rev B") lists the product's investigations that record no version, as
  "applies to the whole product", with their evidence, the same rule as the product's Overview; it no longer shows
  fewer investigations than the Overview.

### Security

- Files attached to an authority submission or its evidence (acknowledgements, receipts) are virus-scanned like every
  other upload; a file the scan refuses is not kept.
- A platform administrator who adds or replaces any Customer Administrator (another person or themselves) of an
  organization that already has an active one, or of a free trial, needs the People support access the customer
  approved; the use or the refusal is in the organization's audit trail. A new customer's first administrator is not
  asked.
- A Customer Administrator cannot reactivate an administrator that MDARIX support suspended (the suspension's audit
  record says who made it), by status or by membership; adding a membership is refused for their own account and is
  recorded in the audit trail (`MEMBERSHIP_GRANTED`).
- Under row-level security an organization could not read the MDARIX staff accounts named in its own records: its
  support-access requests and their activity showed no person, and its audit history showed a staff action as a bare
  account id instead of "MDARIX platform administrator". Staff accounts are now read apart in system scope, staff
  accounts only (another organization's accounts never). Tests run API requests under the runtime role (`SET ROLE`).
- A test reads the modules that build SQL with table or column names (data-plane lists, analytics, export, purge) and
  fails when a name could come from anything but a fixed list or the database catalogue, such as a request field.
- New tests ask, as one organization and under row-level security, for another organization's complaints,
  investigations, evidence and its download, CAPAs, exports, audit trail and signed decisions, by id, through list
  filters and through every export: each answer is a refusal or holds none of the other organization's data.
- New screen tests show that markup typed or imported into a complaint, an imported record or an evidence record's
  name appears as text on the complaint page, triage, the imported backlog and the case's evidence, never as markup;
  a test also fails if any screen starts writing raw HTML (the one reviewed, escaped exception is the public
  questions page's structured data).
- Uploads and imports, exports and downloads, and connector syncs are rate limited per person and per organization
  (per hour: 60 and 300 uploads, 60 and 300 exports, 20 and 60 syncs); past a limit the answer is 429 "Too many
  attempts. Please try again in …" with `Retry-After`.
- An independent alert channel: when no usual channel delivers an operational alert (for example the email provider
  is down), it is also posted to `MDARIX_ALERT_FALLBACK_WEBHOOK`. Optional; unset, nothing changes. Operators: add the
  setting where the alert settings are documented, and prove it with `scripts/send_test_alert.py`.

## [0.10.94] - not released yet (ships with 0.10.93 in the test release, late November)

Development cycle 1, item W1: Product 360 and Supplier 360. No migration. The API and web images change. Operator step:
`scripts/refresh_trial_story.py` adds the sample's supply chain where the sample exists.

### Added

- **Product 360** (Work › Products): one page per product with its versions, the product's own changes, six link
  tiles with a monthly series, and the lists of its complaints and investigations. A chosen version is respected in
  every section. The product list shows counts.
- **Supplier 360** (Work › Products, the Supplier 360 tab): the supplier list, a page per supplier with its complaints, its lots (in a free trial) and the
  pattern box. From a pattern, "Open an investigation" starts one with all its complaints ticked and keeps where it
  came from.
- A trend check card and an investigation open their product version on Product 360.
- The sample's supply chain (suppliers, parts and their lots), so a new trial shows both pages filled.

### Changed

- Both pages carry the hero design on their headers only; their operational parts are flat. Measured on 5,000
  complaints, every read stays under the 1 second budget (`docs/runbooks/LOAD_AND_FAILURE_DRILLS.md`).

## [0.10.93] - not released yet (ships with 0.10.94 in the test release, late November)

Development cycle 1, item B2: the Case, the first contact before anyone decides it is a complaint. Migration
`tr19casesescalation` (expand-only: new columns on the Case, the Case check, triage and alerts; three new tables
`triage_record_versions`, `case_addenda`, `record_ownership`, each with the tenant isolation policy). The API and web
images change. Operator steps: run `scripts/cases_0_10_93.py` (it only lists what the upgrade would change in the
trials' existing Cases; nothing is written until the owner approves the list), then `scripts/refresh_trial_story.py`
(adds SAMPLE-CASE-11 where the sample exists). A 0.10.92 image runs on the new schema (rollback).

### Added

- **The Case.** "Log a call" is now **Log a case**: the reporter's words, the channel and its reference, who knew
  first, the product with its version, lot, serial number, UDI, software, hardware and firmware (each "confirmed" or
  "unconfirmed" with where it came from; "Not sure" is allowed and never forced), the patients involved, what happened
  to the patient, what was tried on the call, and a service issue category. A Case has one state at a time (To check,
  Waiting for the reporter, Waiting for internal team, QA review, Closed, Complaint, Withdrawn), an owner, a next
  action, a due date and the information still missing.
- **Products and lots shipped to this hospital** (ID-2): when the caller's site matches a consignee in your shipment
  records (exact name or customer reference), Log a case offers the products, versions and lots shipped there as a
  quick picker; choosing one fills them as unconfirmed, source "Shipment record". No match: the usual picker, never
  blocked. The sample shows it: SAMPLE-CASE-11's hospital, Sample Lakeside Hospital, now has two PulseWatch
  shipments (lots 001 and 002); running trials get them through the refresh step.
- **The Cases list** (Complaints › Cases): pages on the server, views (My Cases, Unassigned, Needs more information,
  Critical or High, Overdue, Awaiting customer, Awaiting Quality, Service only, Potential complaints), search by
  reference, product, serial number or customer, and bulk assign. Measured at 5,000 Cases within the one-second budget.
- **The Case check.** The ten questions keep their numbers; each answer records the question's version. "Unknown",
  "Not applicable" and "not answered yet" are kept apart, and a changed answer keeps the earlier outcome in the
  history. Six classifications: Complaint, Complaint and service, Service only, Inquiry, Pending, Not a complaint.
- **Sign and escalate.** Signing a complaint makes the Case the complaint at once, with its facts and its first
  awareness carried over (the provisional clock never restarts); or attaches it to a complaint it duplicates. An
  urgent case ("Urgent: death or serious injury") is a complaint at once. The complaint page shows where it came from
  and a first card, "The case".
- **Triage at two speeds.** Fast track when harm is possible, with a named owner who acknowledges it within an hour
  (unacknowledged: escalated to the next role); routine one-click confirmation otherwise. Every triage change is a
  new version. A severity floor from the facts, "Not known yet", potential harm, containment, a backup owner, and
  automatic reopening when new facts arrive. A downgrade of a critical escalation needs a second person (outside the
  trial) and a refused attempt is recorded.
- **Alerts record their delivery**: channel, attempts, last attempt and result. A failed delivery never cancels the
  escalation and shows on screen.
- **The Service Desk role** ("Service Desk Agent"): logs and checks Cases. Every Case and triage action is checked on
  the server, and a refused action is recorded in the audit trail.
- **Customer contact on the Case**: shown only to those who need it, masked in exports by default, never a personal
  name in a trial, and erased 12 months after the Case closes.
- **Getting started, Part 1: from the first contact to the submission.** Ten steps on SAMPLE-CASE-11, the hospital's
  call behind SAMPLE-RV-11: review the case, classify service or complaint, triage, assess reportability, sign the
  conclusion, prepare the report, complete and approve, record the submission, review records, explore trends. Each
  step says what to do next, why, who does it and what evidence ticks it, and ticks only from saved records. A
  service-only, inquiry or "not a complaint" Case skips the reporting steps and goes to the QA review; a pending Case
  waits for the reporter with an owner and a due date. "More cases to try" lists the other sample Cases.
- **Your QMS triage on import.** The complaints template takes four optional columns: `triage_date`,
  `triage_severity`, `triage_owner`, `immediate_action`. A complaint with no harm flag is accepted as triaged in your
  QMS, with no click; one with a death, an injury, a malfunction or harm words shows "From your QMS: confirm" on the
  triage list, and a person checks it and presses **Confirm QMS triage** (one at a time). A re-upload never changes a
  triage a person saved.
- **Recent imported complaints on "To triage".** A complaint imported from this version on, with no harm flag and no
  triage from your QMS, now waits on "To triage" as routine (one click to confirm). Complaints imported before this
  version stay where they were. The complaint page shows "From your QMS · last synced" with the date of the import.
- **Imported backlog** (Complaints › More views): imported complaints known of more than 30 days before their import,
  with no harm flag and no triage yet. Routine triage, one click each, due 10 working days after the import (both
  organization settings). Read in full, oldest first, however large the import. Old imported complaints **with** a
  harm flag wait there too, listed first with their flags and the note "Imported: check the reportability decision
  in your QMS": the full triage form, the same 10-working-day target, and no regulatory clock shown overdue or
  alerted (the clock ran in your QMS). One that came with its QMS triage ("From your QMS: confirm") waits there too,
  with "Confirm QMS triage" on its card, and the complaint page shows the note and the backlog target in place of a
  market clock. Recent imports and Cases logged in MDARIX are unchanged.
- **Second look: "Closed without a reportability decision?"** A complaint closed in your QMS with a death or a
  serious injury and no signed market conclusion comes to the second look.

### Changed

- **"Case" now means only the first contact.** What was called a case is now an **investigation** everywhere in the
  app, the help and the generated documents: "Investigation evidence", "Investigation timeline", "Download
  investigation record". Old links and bookmarks still open the right tab.
- **Permissions:** an Investigator no longer classifies first contacts or triages; a Regulatory Reviewer may triage.
- A service-only Case is closed only with a resolution summary.
- A service record opened from an imported complaint shows its channel as **Imported service record**; the
  upgrade script gives the same channel to the service records your trial already has.
- Screen sentences no longer break in the middle with a long dash.
- Import: a QMS row carrying an escalated complaint's QMS ID updates that complaint instead of adding a second one.
- Authority report downloads: before approval, the worksheet PDF or DOCX downloads as a preview marked "DRAFT PREVIEW
  - NOT APPROVED"; the record copy and the eMDR XML come only from the approved version.
- **OmniRoute as an AI provider option** (`MDARIX_GENAI_PROVIDER=omniroute`, an OpenAI-compatible gateway; see
  `docs/runbooks/AI_PROVIDERS.md`). Code only: AI stays off in the trial. Staging and production still need the
  contracted-provider list and a retention clearance before any AI call.

### Fixed

- A CSV import stops reading at the row limit, with the same "too many rows" message as a spreadsheet.
- While a market assessment is still pending, its deadline is the earlier of your organisation's window and the
  report a "reportable" signature would start (for example the US 5-work-day report), so signing reportable later
  never lands on a date already past. The assessment, the watch, the report and the alerts show the same date.
- Until triage answers the question that decides a shorter report, the Case check's clock, the triage deadlines and
  their alerts show the earliest possible regulatory date with a plain note: EU/NI and GB "2 days unless a public
  health threat is ruled out", US "5 work days unless remedial action is ruled out", Canada "10 days unless death or
  serious deterioration is ruled out". Once triage is completed, the date of its tier applies.
- When a market conclusion is signed again with the same report type, the report's snapshots waiting for approval or
  approved on the old conclusion are replaced: the old text can no longer be submitted or approved by the new signer,
  and the report goes back to draft for a new snapshot. Recorded in the audit trail.

### Security

- Two-factor sign-in now follows every role a person holds, not only their account role: someone given Leader or
  Approver as an additional or custom role must set up an authenticator app. It applies to open sessions too: on
  their next step they are taken to the authenticator setup with "Your role requires two-factor sign-in", never
  locked out; a role taken away again lets them carry on. People who already use an authenticator see no change.
- Dependency updates: pypdf 6.21.4, pillow 13.0.0 (with fastembed 0.9.1, which allows it), filelock 4.2.1,
  certifi 2026.10.18; vite 8.3.7, now a development dependency only.

### Known limits

- The sample's earlier calls keep their SAMPLE-CALL references; SAMPLE-CALL-02 (signed before 0.10.93, never linked)
  is not escalated automatically.
- The full test suites and the browser journeys run once in the test release before the deploy; the Getting started
  journeys are rewritten for the new steps then.

## [0.10.92] - 2026-11-07

On the trial maintenance line (`release/0.10`): development cycle 1, step 1, the bug and trust fixes found while
recording the presentation videos. No migration. The API and web images change. No operator step. No sample number
changes; the sample author's hypotheses now carry the sample's source (new and restarted trials).

### Fixed: trust

- **The sample's times never change during the day** (owner decision on A1, 7 Nov 2026). The sample's clock moved
  every sample record every hour, so a signed time or an awareness time read twice in a session changed (16:33, then
  17:27). It now moves the sample only once a day, the first time the hourly job runs after midnight in the
  organization's time zone, by whole days: every time of day stays as seeded, and day 0, 7, 15 or 29 tells the same
  story. The sample's signatures and signed records say "Sample: dates follow your trial day"; the organization's own
  records never do. A sample target shorter than a day (a triage target) can come due late in the day, as on the day
  the sample was seeded.
- **The sample's clock never moves the organization's own records** (call intake H10, D11). The hourly move followed
  every link from sample records, so a call logged on a sample product had its awareness and times moved. It now
  moves only the sample's own records and what hangs off them. Logging a call, or signing, reviewing, escalating or
  completing a call or its triage, now stops the clock, as any other work on the sample does.
- **Records shows the sample's signatures** before a person signs anything: "Latest signed record" (who signed,
  when, what it means) instead of "No signed record yet". Verify a signature says an investigation has no signed
  decision yet, and where the signed conclusions and approved reports are.
- **The eMDR's contact office is asked for before approval.** A US report's G1 (the US responsible party, with an
  e-mail of up to 50 characters) is a thing to give while the report is a draft, so Send for approval waits for it;
  the e-mail can be given beside the field or in Settings › Products. Before, approval froze the report and only the
  eMDR XML then said it was missing. A typed G1 that differs from the responsible party is asked for too.

### Fixed: screens

- **Decision records** said "1 open. Next: null" for a finished event; it says "1 open, signed with its reason".
- **The decision form appears right after "Accept for decision"**, and the case's status changes with it, without a
  reload.
- **A direct link to an investigation** (`/app/investigations?case=…&step=Summary`) says it is opening instead of
  "No investigation open", and a link whose products cannot be read says so instead of waiting for ever.
- **A report sent back for correction says one status**: its chip, the first stage of its path and its next step all
  read "Draft: correction required", and Send for approval opens again once every mandatory field is filled.
- **The Complaints list** gives Incident country, Owner and Stage their headings, over their cells.
- **The administrator's Home** shows the Legal clocks, as the Regulatory Leader's does.
- **Trends** names the change recorded on a rising version under its lots (SAMPLE-CHG-014, the supplier change, for
  OrbitCare 300 Rev B).
- **Wording**: SAMPLE-RV-11's chapter asks "Is it reportable in the US, and by when?", as its walkthrough does; the
  lines a trial user reaches no longer send them to an administrator (a trial has none): invite a colleague in Team,
  import your data, or write to support@mdarix.in.
- **The new design's leftovers**: dropdowns take the field style with the design's chevron; every "Starter" label is
  one amber chip that reads in both themes; a legal clock's lane is amber only within seven days ("29 days left" is
  calm); the column-resize mark shows on the light and the dark heading.

### Tests

- The Getting started journey's helper answers each decision-tree question by its number, checks it took and waits
  for the outcome, instead of a fixed pause and a place in the list (the US tree once came out as a 5-day report). It
  gives the contact office's e-mail. Unverified until the next browser run.

## [0.10.91] - 2026-11-05

On the trial maintenance line (`release/0.10`), released together with 0.10.90: dark mode on the new navigation, and
one fix. Presentation only: no page's words, fields, numbers, steps or buttons change, and no API or rule changes. No
migration. Only the web image changes. No operator step. No sample number or label changes.

### Added: dark mode

- **Light, Dark or System** from a sun or moon on the top bar. System, the default, follows the device's setting
  and changes with it. Each person's choice is kept in their browser; a browser that refuses storage simply follows
  the system.
- The hero design's dark theme: deep navy grounds, the bright teal action colour, and the deadline, harm and lot
  colours tuned for a dark ground. Every text colour is 4.5:1 or more on its ground, focus stays visible, and status
  is still never shown by colour alone.
- Only the new navigation turns dark. The website, the sign-in pages and the classic navigation stay light.
- The application's last hard-coded colours (about 120, in the shared style sheets) now come from the design tokens,
  so no surface, chip, table, fold, form field or dialog stays light by accident.

### Changed: the owner's design decisions (5 Nov 2026)

- **Log a call** on Complaints and **Raise a trend** on the trend's hero are filled primary buttons (in the table of
  every group, Raise a trend stays secondary).
- **The complaint list's big count** ("27 complaints") leads its summary bar, as the design shows it.
- **The side menu's alerts are a dot, never a count**: Complaints while a complaint is overdue, Trends while a product
  is rising; on a phone the dot is on the slot, or on More. Screen readers hear "New items".
- **The browser journeys' keyboard check** keeps telling the end of a page from focus lost in the middle of it.
- **The report's Next step** with 0.10.89's eMDR file takes the design's next card in both themes: what the eMDR XML
  still needs is a callout beside the button it holds back, and that button stays legible while it waits.

### Fixed

- **Service work on the complaint page said its heading and its state twice** (since before 0.10.90): once in the
  card's fold and again above the form. It now says each once, above the form, on a desktop and on a phone.

## [0.10.90] - 2026-11-05

On the trial maintenance line (`release/0.10`): the owner-approved hero design (`mdarix-hero-ui.html`) on the new
navigation. Presentation only: no page's words, fields, numbers, steps or buttons change, and no API or rule changes.
No migration. Only the web image changes. No operator step. No sample number or label changes.

### Changed: the new navigation's shell

- **A left icon rail replaces the eleven tabs across the top.** The rail is dark, with the MDARIX mark, Getting
  started and its ten-step progress ring at the head (a trial only), the persona's destinations in two groups (Work:
  Home, Complaints, Decision trees, Reports, Investigations, Trends, Records; Plan: Team, Look ahead) and Next steps
  pinned at the foot. It folds to icons with its button, and by itself below 1240 px; every icon keeps its name for
  screen readers and as a tooltip. It lists only the persona's destinations, as the tabs did; a screen opened from
  Getting started or a link that the persona does not list shows as a marked rail item while it is open.
- **A slim, light top bar**: the organization with its trial status, Sample data, the search, Import your data,
  Viewing as, the bell, Help and the avatar. The MDARIX mark moves to the rail.
- **On a phone, a bottom bar of five**: Getting started, Home, Complaints, Trends and More, which opens the persona's
  other destinations above the bar.
- The classic navigation is unchanged.

### Changed: the design tokens and fonts

- `tokens.css` takes the hero design's palette (ink, surfaces, lines, the teal action colour, the deadline and harm
  colours, the rail and the dark monitor band), its type scale (12 to 64 px) and its radii (8, 12, 16, 20). Every text
  colour still meets 4.5:1 on its grounds (`tokens.test.ts`).
- The dark theme's tokens are written but switched off: nothing turns them on until the dark-mode release.
- **Archivo** (headings and big numbers) and **IBM Plex Mono** (references and codes) are self-hosted beside Inter,
  with their SIL Open Font Licence texts in `/fonts/`; no font is loaded from another site.

### Added: the shared visuals

- Clock rings, status and harm pills, flags (the United States, the United Kingdom, Canada, India, Germany, France, the
  European Union, and a coded tile for any other country), device icons (patient monitor, infusion pump, respiratory
  controller, and a generic device for imported products), stage dots, the ten-step progress arc, the dark monitor band
  with its ECG-paper grid, and four illustrations (a hospital bedside, a patient monitor, an infusion pump and a signed
  record's seal). Each has an accessible name, and no status is shown by colour alone. Motion stops for readers who
  ask for reduced motion.

### Changed: the pages

- **Home** opens on the dark band: the story (with its five moments once the sample is done, or its ten-step ring
  while it runs) beside the three counts, Overdue, Due this week and At risk, each with its icon. The next actions
  sit under a ten-day deadline ruler ("Now", the day names, the overdue stretch shaded), each with an icon in its
  deadline's colour; the reminders move beside them, under the trends card, which gains its device and the rise as
  one big figure.
- **Complaints**: each legal clock is a ring beside its words, with "Due soon" or "On track"; the row's edge takes the
  clock's colour. The reference reads in the mono face beside its problem; the product shows its device, the country
  its flag, the owner initials and the stage its dots, stacked in one column as the design shows. Above the list,
  one bar shows it by legal clock (7 days or less, more, no deadline) with the late communications and the deaths
  and serious injuries beside it, when the whole list is on the page.
- **Getting started**: the dark band with the ten-step ring, the count and the bedside illustration; the progress in
  ten segments; each step with its icon and "Step N"; the chosen step beside its icon, or the signed seal once all
  ten are done; picture tiles on "Explore at your own pace". Two columns of steps on a phone.
- **The complaint page**: the band with the reference, the reporter's words, the harm, the device and the legal clock
  as a large ring with its line and flag; the facts with icons and flags; the stages as a stepper; the one Next step
  under them. A report's and an investigation's header open on the same band.
- **Trends**: the verdict and the sentence beside the device, three figures, the observed bar split by lot with a
  legend, the expected hatched.
- **Every other page** on the new navigation (Decision trees, Reports, Investigations, Records, Team, Look ahead,
  Next steps, Settings, Account, Import your data, Help) takes the same headings in the display face, an emblem
  beside its question, and the design's cards, buttons, chips, tables, fields and folds; Next steps opens on the band.
- Getting started's ring on the rail is read a moment after the page's own data, so it never delays the page.
- Whatever is scrolled into view stops clear of the top bar and, on a phone, of the bottom bar, so neither covers it.
- The browser journeys' keyboard check tells the end of a page (the browser leaves it and the next Tab starts again
  at the top) from focus lost in the middle of it.

## [0.10.89] - 2026-11-05

A US report's two files: FDA's own Form 3500A, filled, and FDA's eMDR XML. No migration. The API and web images
change; the API image adds `pypdf` 6.21.2 (pinned with hashes). No operator step. Other markets (EU, GB, Canada,
India) keep their worksheet PDF unchanged.

### Added: the approved US report on FDA's Form 3500A, and as the eMDR XML (owner request, 5 Nov 2026)

- **"Generate the PDF" on an approved US report is FDA's own fillable Form FDA 3500A MedWatch (09/2025)**, filled
  from the approved snapshot block by block, then one page that is MDARIX's record, not part of FDA's form: who
  prepared it, who approved it and when, the snapshot's checksum, the records its values came from, and any approved
  value the form has no place for (with the reason). A box is ticked only for FDA's own choice ("Unknown" ticks
  Unknown, never No); a missing value stays blank. FDA's form is kept byte-identical in `data/fda_forms` with its
  edition and source. It is a static XFA form: MDARIX drops the XFA layer so Chrome, Edge and Acrobat all show the
  values. In a trial the record page says "Practice record: free trial".
- **"Download the eMDR XML"** (`GET /api/v1/reports/{id}/emdr.xml?snapshot=`): the same approved report as FDA's
  HL7 ICSR file, built as FDA's eMDR Implementation Package defines it and validated against its published schema
  before it is offered. One plain line says: MDARIX prepares it; you submit it through your own ESG or eSubmitter
  account and record the submission here. MDARIX never submits.
- **The file waits for what FDA requires**, and the report page names it ("The eMDR XML also needs: ..."): the
  report number in FDA's format (your CFN or FEI, the year and a number), the event description, the product code,
  the contact office's email, the type of reportable event and at least one FDA code of each H6 kind. The contact
  office and the manufacturer come from Settings (your organization's US responsible party) only while they read
  exactly as the approved report does. Values the file cannot carry (not one of FDA's choices, too long, an address
  FDA wants in parts) are listed, never dropped in silence.
- Sample: the flagship US report's PDF is now the filled form; its fields and the report page's numbers do not change.

### Fixed: "Adverse event" only for recorded harm (owner-approved, regulatory)

- **US B1 and India B2 ("Type of report / event: adverse event, product problem")** ticked "Adverse event" whenever a
  patient was involved, even with no harm recorded. Now "Adverse event" comes only from a recorded death or serious
  injury, and "Product problem" from a recorded malfunction. A patient merely involved, or an outcome not recorded,
  ticks neither; the field then stays empty for a person to give (and the eMDR XML waits for it). The worksheet, the
  filled Form 3500A and the eMDR XML read the same rule.
- Sample: SAMPLE-RV-11 (US, the flagship) and SAMPLE-RV-08 (US) read "Product problem" instead of "Adverse event;
  Product problem". Approved snapshots are never edited: a trial that already approved RV-11 keeps its approved
  values; its next report reads the new rule.

### Changed: browser journeys only

- `scripts/journey_api.py` raises the per-address limit on activation and reset links (`token:ip`, 20 an hour) to
  1,000 in its own process, so back-to-back journeys from 127.0.0.1 do not wait for the next window. The API's own
  limit, and production's, are unchanged.

## [0.10.88] - 2026-11-04

On the trial maintenance line (`release/0.10`): R3 of the external code review's plan, DEV-10 (the trial's journeys
and accessibility) and DEV-13 (performance, monitoring and recovery), with two owner decisions on the regulatory rules
(OD-2, OD-4). One migration, `tr18changereason` (a nullable column, `complaint_market_assessments.change_reason`;
the legacy-plane script carries it). The API, worker, scheduler, web and backup images change. Operator steps: the
off-site bucket's lifecycle rule (below, Operations); two more are recommended.

### Fixed: a step counted only when its screen loaded (P0 of the review of 0.10.87)

- **"Open sample complaint" no longer ticks step 1 when the complaint fails to load.** The main button of steps 1, 5,
  9 and 10 saved the step's mark as it opened the screen, whatever the screen then showed. The mark is now saved by
  the screen itself once its read succeeded for the story's record: the complaint page (step 1), the report page
  (step 5), Records' finished record (step 9) and the trend check of the story's product (step 10). A failed read (a
  server error, a lost connection, a record not found) ticks nothing, and Retry ticks it once. A refusal (step not
  yet in its turn, the story moved) is still said on Getting started. The trend check now reads the story's product
  from the first render, not all products first. The server is unchanged.

### Changed: two owner decisions on the regulatory rules

- **OD-2: "United Kingdom" is asked, Great Britain or Northern Ireland.** A complaint whose country is "United
  Kingdom" or "UK" is two markets: Great Britain follows UK MDR 2002, Northern Ireland the EU MDR (market EU_NI). The
  complaint page asks which, with a choice of the two, and until then every market's shortest clock runs,
  provisional; `PUT /api/v1/complaints/{id}/reporting-facts` refuses the whole-UK name (422 `COUNTRY_UK_PART_NEEDED`).
  "Great Britain", "GB", England, Scotland and Wales stay Great Britain. Decision tables MK-5, MK-5a and MK-5b.
- **OD-4: re-signing a market conclusion asks why it changes.** Signing a conclusion where a signed one stands now
  needs a change reason of at least 10 characters (422 `CHANGE_REASON_NEEDED` without it), asked as "Why the signed
  conclusion changes" wherever a conclusion is signed: the decision tree and the reportability watch's assessment. The reason is part of the signed material, stored with the new
  version (`change_reason`), in its audit event, and shown on its signed line. A first signature is unchanged.

### Fixed: what the browser journeys found (DEV-10)

- **Getting started's story on your own data no longer stops at Triage.** When the trial's most urgent imported
  complaint reports no harm and no malfunction (or the export has no such columns) it is not on the triage list and
  has no triage form; step 2 waited for a triage record that could never be made, its button opened the page already
  open, and the story could not finish. Step 2 now reads "Not needed: not flagged for triage". No sample number
  changes.
- **The walkthrough on your own data stays on its complaint until its last step.** With a second upload more urgent
  than a finished first complaint, the walkthrough moved to it (as it should), but concluding it "not reportable"
  closed its clock and sent the walkthrough back to the first complaint in the middle of the second's steps; there,
  steps 9 and 10 read as not done, because the steps opened were kept for one complaint per run. The walkthrough now
  keeps following the complaint under way until its Trends step, unless a complaint with more serious harm arrives,
  and the steps opened on each complaint are kept. Found by the uploaded-data journey.
- **Screen readers hear which steps are not needed** in Getting started's step list (after a "not reportable"
  conclusion, or a triage not needed).
- **A decision tree's outcome keeps up with quick answers.** Every answer queued a save of all the answers, one after
  another; answering the US tree at a normal pace left the outcome several saves behind, for seconds showing the
  result of answers already changed, with nothing saying so. A save still waiting when a newer one is asked for is now
  skipped, and the outcome says "updating from your answers…" until the newest is in. Signing was never affected.
- **A removed or mistyped record offers the way back.** Opening a complaint or an authority report that is not there
  showed "Unavailable" and a Retry that can never work; it now says "This complaint (report) could not be opened"
  with "Open the complaint list" ("All reports").
- **A save refused because the session ended says the change was lost.** The sign-in page said "continue where you
  left off" although what was typed was gone; it now says "your last change was not saved" and still returns to the
  same screen.
- **Inviting a colleague while e-mail is slow no longer invites twice.** With a slow e-mail provider the screen gave
  up after 15 s and said "Try again" while the invitation was being made and sent; it now waits up to 45 s, and if the
  answer is still lost says the invitation may have been sent and to check the list.
- **"Record the submission" puts the keyboard on the form** (it stayed on the rail's button, far from the form, and
  the form could be folded away).
- **Screen readers hear which items before Sign are done** ("Done:" / "To do:"; the ticks were hidden from them).

### Changed: speed (DEV-13)

- **Getting started's story on your own data, three times faster.** On a trial with 5,000 imported complaints the
  story took a minute or more a read; most of it was the same few market and country names being normalized millions
  of times. They are now normalized once.
- **Possible duplicates on the triage list** are paired by product and lot or serial number instead of comparing every
  record with every other (about 12 s to 3.8 s a read on 5,000 imported complaints, locally).
- **The complaint page** reads each colleague's permissions once instead of seven times (a trial at its cap of 50
  people paid it on every complaint opened).

### Operations (DEV-13)

- **New health signals** on `/health/ready`: `outbox` (events waiting, retrying, and the queue's lag; degraded over
  15 minutes) and `email` now degraded while e-mails the provider refused wait to be retried.
- **New alerts** (to `MDARIX_ALERT_WEBHOOK` and/or `MDARIX_ALERT_EMAIL`): the outbox falling behind and catching up,
  e-mail delivery failing and recovering, and a signature not settled or PENDING over 30 minutes (and when that
  clears).
- **A readiness gate for the deploy**, `scripts/deploy_gate.py`, run inside the new API container after `up`: the
  release named, the database at this build's schema, and the components named with `--require`. Recommended in the
  next upgrade script, beside `/health/live` (DEPLOYMENT.md).
- **Backup retention, 30 daily + 12 monthly** (owner decision, 5 Nov 2026): the backup job keeps every local backup
  of the last 30 days (a pre-upgrade one included), then the newest backup of each of 12 months, and always the newest
  of all; it kept 14 days before. New setting `MDARIX_BACKUP_KEEP_MONTHS` (12); `MDARIX_BACKUP_KEEP_DAYS` now defaults
  to 30. The backup image changes (it carries `retention.sh`). Operator step: set the off-site bucket's lifecycle rule
  to the same. Disk: about 42 backups of about 12 MB.
- **Recommended:** an alert webhook to a channel independent of the SMTP provider (with the provider down, an e-mail
  alert about it cannot arrive: seen in the local drill).
- Local drills recorded in `docs/runbooks/LOAD_AND_FAILURE_DRILLS.md`: worker, scheduler, e-mail, database, object
  store and the upgrade script's rollback branch; and a measurement of a trial against the approved targets
  (`tests/test_trial_load_measure.py`, opt-in).

### Tests and checks

- `frontend/e2e/getting-started-journey.spec.ts`: the browser acceptance test of Getting started's ten steps, through
  the real forms, on the sample (solo, with the practice approval) and on a team's own data (a second person
  approving on a phone; a "not reportable" conclusion); with the authenticator, a reload and a resume, a step opened
  out of turn (STEP_NOT_YET), a moved story (STORY_MOVED), an API error, and ticks checked in order after every step.
- `frontend/e2e/your-data-journey.spec.ts` (new): uploaded data from the file to the ten steps, at 1440 with a
  phone pass: a most urgent complaint without country or awareness date, both asked and entered (a lost save retried
  once), its complaint failing to load once (step 1 not ticked until Retry), a reload and resume, the reportable
  branch through the real forms with the authenticator, a colleague's approval on a phone and a real PDF (served as
  `application/pdf`, a non-empty `%PDF-` file); then a second upload's complaint concluded not reportable, steps 5 to
  8 "Not needed", no report for it and exactly one for the first. The story's helpers are shared in
  `frontend/e2e/support/story.ts`; the sample journey checks the failed screen too.
- `frontend/e2e/trial-journeys.spec.ts`: the trial's journeys at 1440 and 390 with captured e-mail
  (`scripts/journey_api.py`), axe-core, accessible names and keyboard on every screen, and the failure cases.

## [0.10.87] - 2026-11-04

On the trial maintenance line (`release/0.10`): security, privacy and evaluation (DEV-08, DEV-11), the regulatory
rules and controlled records (DEV-09), and Getting started v2 with the owner-approved duplication review. No migration.
The API, worker, scheduler and web images change. No operator step. Sample: four background complaints move from the
routine path to the standard path (their harm facts are not recorded).

### Changed: Getting started v2, one walkthrough and one next action (owner's specification, 5 Nov 2026)

- **Getting started is one white walkthrough card**, in place of the dark hero: "Getting started", "Follow one sample
  complaint from first call to reporting.", the practice line once ("Fictional data · Trial outputs are practice
  records · Human sign-off required"), then "Your sample walkthrough" with its Sample data badge, "X of 10 completed"
  and one progress bar. The ten steps are a list on the left; the step chosen is on the right with a small label, one
  heading, one instruction, a short summary of the complaint and one main button. On the trial's own data the same
  card runs on "Your data", without "Fictional data".
- **The complaint summary is read from the record**: its reference, the description's first sentence, the device, the
  reported harm and the service status. Harm the record does not state says "Not recorded", never "None reported".
  The one-story read (`GET /api/v1/trial/one-story`) now also returns each run's `product_name`, `harm` and
  `service_status`.
- **Picking a step on the list previews it**: it is marked "Preview", with the real next step named and one click
  back. Completion is unchanged: ticks come from the saved record, and steps 1, 5, 9 and 10 still count only when
  their main button opens the step's screen in its turn.
- **Under the card, "Explore at your own pace"**: Invite your team (the trial owner manages; a colleague sees who is
  on the trial), Explore other workflows (Choose a focus: the short stories, the ten chapters and the audit focus, on
  `Getting started › Other workflows`), and Guides & support (the guides, support, feedback, the one-to-one demo and
  Next steps, shown when asked for).
- **One collapsed "Sample data & trial settings"** at the foot of the page holds the sample's explanation and counts,
  the trial's dates and limits, and the trial owner's Restart the sample story, Remove the sample data and End my
  trial early, each with its confirmation as before. Old links to Getting started › About the sample data and ›
  Your trial open it.
- **Removed from the page**: the miniature screen previews, the second chapter wheel, the seven-step trial journey, the
  repeated first-call and report explanations, the duplicate demo and Next steps banners, the short-story tiles that
  repeated the short stories, and the restart control on the short stories. Every capability stays reachable.
- The walkthrough says when it is still reading, when its read failed (with Try again), when a role may not read it,
  and when there is no complaint to follow.

### Changed: Look ahead and Next steps are tabs of every free trial

- Every persona in a free trial now has **Look ahead** and **Next steps** as tabs, after its own; Getting started stays
  first. Pilots and paid organizations are unchanged.
- Help no longer repeats them on the new navigation; its "Short stories and your trial" entry is now "Short stories and
  other workflows" and opens the library.

### Changed: each trial page says each thing once (owner-approved duplication review)

New navigation only; the classic navigation is unchanged. No capability is removed, only repeated ways in.

- **Shell:** the trial badge opens Getting started's trial settings; the top bar's Sample data chip is left out on
  Getting started, and Import your data on its own page. Help no longer offers Try your own data, the sample-only
  Discuss a pilot or Next steps (the top bar and the tabs do), and calls the trial guide "The trial, step by step".
  The time-zone line shows only on pages with times. No chapter banners, and no story bar on Home. The avatar menu
  shows the name only. The investigation picker is gone, and the product picker shows on Trends only off the trend
  check.
- **Page heads:** one report and Next steps have only their own heading. Look ahead asks "What will your partners
  see?", and its panels name the party.
- **Getting started:** the third card is "Plan your next steps" (the demo and Next steps). The team card is left out
  for a persona whose tabs hold Team. Other workflows drops the four-step short story on SAMPLE-RV-11 (the walkthrough
  follows that complaint) and the second star rating, and lists "Workflows to try".
- **Home:** the date line drops the organization, a trial's Home drops its data eyebrow, and the At risk tile no
  longer names the product the Trends card names.
- **Complaints and a complaint:**
  - No import button on the list in a trial, and the list's title is its count.
  - Authority reports and Investigations views are offered only to personas without those tabs.
  - A complaint's crumb is the way back; its service line keeps to the service; missing facts read "Not recorded".
- **Decision trees and Reports:**
  - The trees' loading panel no longer repeats the question.
  - A report drops its Market and Due fields, and shows the meter chip once nothing is missing.
  - The practice-approval warning says only who you approve as.
  - "MDARIX never submits" is said once.
- **Investigations and Trends:** no second eyebrows. Investigations drops the header Lot impact button (its fold
  stays). Trends shows the Investigations button only for personas without that tab, and its fold drops the rise
  tiles the heroes say.
- **Records, Import your data, Settings, Account:**
  - Records and Import your data drop repeated sentences.
  - Settings' panels are named by topic, and Account's panel is "Profile".

### Fixed: sign-in steps and invitations (DEV-08)

- **An idle session can no longer set up an authenticator.** The two-factor steps skipped the idle timeout: a
  browser left signed in and unused could still bind an authenticator app to an account that had none. They now end
  an idle session as every other page does.
- **The two-factor steps follow the organization's access rules**: a suspended member, or a trial that has ended,
  sets up nothing (they answered as if access were open).
- **Two invitations of one email at the same moment make one account.** An administrator's or a trial owner's two
  quick clicks (or two people inviting one colleague) could create two accounts for one email in one organization.
- **The first-contact guide needs a session**, as the rest of the first-contact pages do (it answered anyone; it
  holds the starter guide text, no organization's records).

### Fixed: the evidence search and Ask MDARIX (DEV-11)

- **A question no record answers gets "not enough in your records", not the nearest unrelated records.** The search
  scored every record as a match on organization alone, so an unrelated question came back with five arbitrary
  records, and Ask (where AI is on) gave them to the AI. The search now abstains below a relevance floor set before
  qualification, and Ask then asks no AI to guess. In a free trial's Ask (AI off) the answer now says "No record is close enough in meaning to the question to count as an answer" instead of listing the nearest records as found by the search.
- **Evidence an investigation set aside is no longer offered to Ask for that investigation** (its review rejected,
  quarantined or superseded it), and a record's vector of earlier text is never ranked.
- **Text inside a record that reads like an instruction to the AI is named to the reader** ("contain text that reads
  like an instruction to the AI; it was given to the AI as data only").
- **The search log keeps questions without personal details** (the masker every AI request uses), and each result
  names the model revision and the relevance floor it was found with (search configuration `R1-retrieval-2`).
- **Evidence searches and Ask questions are limited per person** (60 in 5 minutes), on top of the monthly AI
  allowance.

### Tests and checks

- `tests/test_authorization_matrix.py`: the authorization and tenant-isolation matrix, generated from the route
  table (actors x actions x states; a new route is in it automatically).
- `evaluation/retrieval/local_retrieval_v1.json` and `tests/test_local_retrieval_evaluation.py`: a versioned
  evaluation of the local search with the pinned model, thresholds set before qualification, and its governance
  tested apart.

### Fixed: "not reportable" is never concluded on facts the record does not give (regulatory rules, DEV-09)

- **The routine path needs the facts its basis states.** It signs "not reportable" for every enabled market on the
  basis "no death, serious injury or malfunction recorded; patient outcome known", yet it was offered for a complaint
  that recorded none of those (an import without the harm columns). It is now offered only when the record says whether
  the device malfunctioned and either that no patient was involved or that there was no death and no serious injury;
  otherwise the complaint takes the standard path, and the screen says which facts are missing. In a new or running
  trial, four background sample complaints (SAMPLE-PULSE-410-CMP-005 and -006, SAMPLE-VENTRA-250-CMP-003 and -004) now
  read "Standard path" on Dispositions where they read "Routine path"; no other sample number changes.
- **A complaint on the watch because a patient's outcome is unknown asks for its country and awareness date** before
  its market conclusion is signed, like a complaint that reports harm. Before, it could be signed with no country and
  with its clock counted from the day MDARIX recorded it.

### Added: the regulatory decision tables

- `docs/compliance/REGULATORY_DECISION_TABLES.md` writes every branch of the starter rules as a table with its outcome:
  reportability for the US, EU and Northern Ireland, Great Britain, India and Canada; folded questions; the market of a
  country; the facts and the authority signing needs; deadlines across time zones, daylight saving and date-only
  awareness; escalation, recurrence and the routine path; late evidence, amendments and provenance; and the versions
  of rules, forms and assumptions. `tests/test_regulatory_decision_tables.py` runs every row, plus every Yes/No answer
  combination with Unknowns, so the tables cannot drift from the code. These are tests of MDARIX's starter rules, not a
  regulatory qualification: the regulatory expert's review is still pending.
- `tests/test_regulatory_records.py`: provenance from the complaint to the signed conclusion, the report, its approved
  snapshot and the PDF; the PDF against its text snapshot (`tests/snapshots/worksheet_us_3500a.txt`); an amended
  conclusion keeps the prior version with its rationale, signer, time and checksum.

## [0.10.86] - 2026-11-04

On the trial maintenance line (`release/0.10`): a reliability release from an external code review of 0.10.84. No
migration. The API, worker and scheduler images change, and the web image (the communications log's pages, the
Platform Admin retention lines). Operator steps: the scheduler runs one new job, `signature-settlement`; CI prepares
the pinned embedding model before the tests (`scripts/prepare_embedding_cache.py`).

### Fixed: nothing open falls behind a list's limit

- **The communications log shows every overdue and open request, however old.** It read the newest 500 entries and
  then put overdue ones first, so in a longer log an old overdue request vanished from the screen and from the counts.
  The log is now ordered overdue, open, then the rest in the database, one page at a time ("Entries 1–200 of 512",
  Newer and Older), and its open, overdue, unresolved and S4 numbers count the whole log.
- **The same fix where something waiting could be cut off:** the first-contact list (calls waiting to be signed, pending
  or waiting for QA review), the complaints waiting for a disposition, the dated reports and CAPAs on Due dates, and on
  the Platform Admin side pending early-exit requests and open pilot requests.

### Changed: Getting started's ten steps, in the owner's words, as a vertical list

- **Getting started is the ten-step story only.** "More ways to explore" is gone from it: the three short stories
  (a new urgent call, a rising problem, approving as a colleague), the ten chapters, the sample data and the trial's
  own page are in Help, Short stories and your trial (`GettingStarted.tsx`; `releaseD3085Story.test.tsx`).
- The steps read Review the call · Triage · Assess reportability · Sign conclusion · Prepare report · Complete details ·
  Approve report · Record submission · Review records · Explore trends, in a numbered list beside the step's card (the
  current step highlighted; on a phone the list sits above the card). What each step opens and when it ticks is
  unchanged (`trial/one_story.STEPS`; `tests/test_release_0_10_85.py`).

### Fixed: a step's progress lands only on the complaint opened, in its turn

- **A mark names the complaint the person's screen showed.** The story's complaint can move (a new urgent import
  while an old screen is open); the server took its current choice, so opening complaint A could mark complaint B.
  It now refuses a mark for another complaint (409 `STORY_MOVED`).
- **A step counts only in its turn.** Records or Trends opened before the steps ahead of them were done was kept and
  credited later; it is now refused (409 `STEP_NOT_YET`) and never credited.
- **A refused or failed mark is said, not dropped.** The screen still opens at once; Getting started shows why the
  step was not saved (`oneStory.openStep`; `tests/test_release_0_10_82.py`, `releaseD3085Story.test.tsx`).

### Fixed: a person's data export, and the management review's day

- **A person's export carries every sign-in event.** It kept only the newest 500, so a long-standing user's export
  under the DPDP Act was incomplete (`tenant_export_api.person_export`; `tests/test_person_export.py`).

- **The management review summary counts the organization's whole day.** Its period ended at the UTC midnight
  after the organization's today, so in the US evening anything signed that day was missing until the next day
  (`readiness_home/summary._bounds`; `tests/test_summary_period.py`).

### Operations

- The first production restore drill with steps 3 and 4 is recorded in `docs/runbooks/BACKUP_AND_RESTORE.md`
  (3 Nov 2026: restore 32 s, whole drill 7 min 19 s against the RTO of 4 h).

### Fixed: the row allowance holds when two imports run at once

- Two imports at the same moment could each count the same rows left and together go past the free trial's 5,000
  rows. Imports into one organization now take turns for the allowance; other organizations never wait.

### Fixed: one deletion date everywhere

- The trial status (Getting started), the trial-ended page, the trial e-mails, the Platform Admin trials overview, the
  trial requests queue and the pilot requests now give the same date: 30 days after the trial (or its grace
  extension) ends, later while a request to move the data is open. Before, the requests queue ignored grace and holds
  and the trial-ended page ignored the hold.
- **Under a legal hold no date is given** ("no date while a legal hold applies"); nothing is deleted until the hold is
  lifted. The deletion job checks each trial again just before deleting it.

### Fixed: signing on a dedicated data plane cannot leave half a signature

- When an organization's records are in their own database, a signature could be saved without the record it signs
  (or "signed" written in the audit trail) if the second save failed. Signing now saves the record first with a
  receipt, then completes the signature; an interrupted signing is completed, or undone with
  `SIGNATURE_ABANDONED` in the audit trail, by the new `signature-settlement` job (every 10 minutes) or the next read.
  A signature being completed is never shown as valid. Retrying the same decision returns the decision already
  signed, after the password and code are checked again. Organizations on the shared plane are unchanged.

### Fixed: the sample

- The sample hospital request's late call now counts as recorded outside MDARIX on every weekday (on some days it
  counted as inside, and the log showed no late message). New trials only.

### Tests and checks

- `unit` tests need no database (`MDARIX_TEST_NO_DATABASE=1 pytest -m unit`), and no test is both `unit` and `db`.
- The local embedding model is never downloaded at run time; tests that need it are marked `model` and skip, saying
  why, without it (`MDARIX_REQUIRE_LOCAL_MODEL=1` makes them required, as in CI).
- `ruff check`, `ruff format --check`, `prettier --check` and the frontend lint pass on the whole repository.

## [0.10.85] - 2026-11-04

On the trial maintenance line (`release/0.10`): round D3, "Polish to 9.5", of the approved redesign, on the new
navigation, with the owner's report on 0.10.84's Getting started first. No migration. The API and web images change. No
operator step: no sample record, deadline or count changes, and `refresh_trial_story.py` has nothing new to do (every
change below is read from the records as they are).

### Fixed: Getting started's story, for every persona

- **The ticks read as a story.** A step is ticked only once the steps before it are done or not needed; work the team
  did out of order (a tree signed before the triage) shows "Done earlier by your team" and ticks once the steps before
  it are done. "N of 10 done", the ticks and the current step now agree (a trial read "1 of 10 done" with step 3
  ticked). The call counts as read once later work exists; the form once its report is past "Created".
- **No dead click.** Each step's button opens its screen at once (it waited seconds for its mark to be saved). A screen
  the persona's tabs do not list (Executive, Investigator, Risk Reviewer, Complaint Handler) opens as a tab of its own,
  marked "opened from Getting started". A colleague whose role cannot open a step's screen is told who takes it, with
  the button disabled and its reason.
- **More ways to explore** is one compact card: a new urgent call, a rising problem, approve as a colleague, and one
  link to the chapters, your trial and the sample data on their own page (it opened the old 8,600 px page with six main
  buttons).

### Changed: the screens (new navigation)

- **Complaints:** every list view is in one order, overdue first, then the nearest legal deadline. The columns read
  Legal clock · What happened (its IMDRF term, or "No IMDRF term yet") · Product, version, lot · Incident country (or
  "Asked at the tree") · Owner · Stage; the whole row opens the complaint; the column choice sits under "More"; phone
  cards are half their height. "Reportability: decision needed" leaves out a complaint whose every market is signed,
  and its stage reads "Report".
- **The complaint page** is a record with a hero: the reporter's words, the harm, one clock line and one Next step; the
  checklist folds, and on a phone the rail's cards fold too (about half the page's length on a phone). The triage form
  folds while the story is on another step.
- **Records** always opens on "Your latest record" (who signed, when, what it means, its PDF), with inspection
  readiness under it.
- **Trends** answers "Is a product problem rising?" per group with observed, expected and the version before, "How we
  compared" folded; your data never shows the sample's rise and says what a short history can show. "Trends to
  review" and "Raise a trend"; no AI origin filter in a trial.
- **Page heads** ask their question and name the organization's time zone once; every time is shown in it, and each
  deadline label drops its zone.
- **Phone:** the current tab stays in view; Home's tiles keep one short line each.
- **Accessibility:** no serious or critical axe-core finding on any new-navigation screen at 1440 and 390; text 12 px
  or more; contrast 4.5:1 or more; 44 px touch targets on a phone; each tree question a fieldset; a skip link to the
  questions; a reason on the main disabled buttons.
- **Investigations:** the question is the heading, the reference the customer's own, lots read "003 · 004"; on your
  data, "Open one from the trend".
- **Log a call** opens in place on Complaints (Calls to check), with a shorter form and the time read back as "3 Nov
  2026, 23:57".
- **Search** finds a complaint by its service ticket, serial number or UDI as well, investigations by reference or
  question, and trends to review.
- **Words:** no internal ID or code where a name exists (readiness lists, guide versions, the scale note). Sign-in says
  what MDARIX does for a QA/RA team. The report's steps read one word each (Created · Complete · Approval · Approved ·
  Submitted · Acknowledged); the story's first step reads "Call"; one date-field width.

### Fixed: Records' readiness

- **"Reported in window" reads the shortest clock again.** Its watch passed a day where the triage list expects a
  moment; the read failed (logged, swallowed) since 0.10.82, so the check counted without it. On a fresh local trial
  the check reads 5 items needing attention where it read 4.

### Changed: speed

- The complaint list's work columns and the events list read each kind of record once per page (about a dozen queries
  per complaint before); the triage list is read once per request; the sample removal's preview asks a few batched
  queries (about 300 before). On the local stack: the open complaint list 198 -> 51 queries a request, the removal
  preview 220 -> 30, the story 93 -> 67.

## [0.10.84] - 2026-11-03

On the trial maintenance line (`release/0.10`): the fixes from the independent rating of rounds D1 (0.10.82) and D2
(0.10.83), on the combined build. No migration. The API and web images change. No operator step: no sample record,
count or deadline moment changes, and `refresh_trial_story.py` has nothing new to do.

### Fixed: one legal deadline, everywhere

- **Legal clocks show legal deadlines only.** An approval task's due date was read as a market's legal clock on the
  Regulatory Leader's Home ("United States · SAMPLE-RV-11 · Due Wed 4 Nov"; the deadline is Wed 2 Dec), in the Your
  data hero ("Its clock ends Wed 4 Nov") and in the complaint page's clock line. A task is never a legal clock now.
- **Once the incident country is known, the header shows that market's clock.** FIC-2001, imported with no country,
  kept "Shortest possible: … Mon 9 Nov" (Great Britain's) after its country was entered as the United States, while
  its triage table gave the US 30 days. The complaint page, Home and the story's hero now read the US date from the
  same triage calculation: "United States, provisional: … due …" while the awareness date is still asked (0.10.81's
  rule stays: a clock counted without the awareness date is never a market's firm deadline). "Shortest possible" only
  while the country is missing.
- **Every deadline a person reads is in the organization's time zone** (its working calendar in Settings), whichever
  market's it is. One clock read EST on the complaint page and GMT in its triage table. The moment, the latest day and
  the counting rules are unchanged. An organization in India keeps reading "23:59 IST"; an organization elsewhere reads
  the authority's end of day in its own time (an EU deadline for a New York organization: "18:59 EDT", not "23:59 CET").

### Fixed: the story

- **The story moves on after a save, with no reload.** After saving the triage, the "Step 2 of 10" pill and the rail's
  Next step stayed stale until a reload. Every saved change now reads the story again.
- **Step 3 opens the story complaint's own tree** with its questions, on the sample and on your data (checked on the
  combined build: D2 had already fixed it).
- **Step 9 opens the finished record in Records**: "The record you just finished", with the signed conclusion and
  who signed it (the conclusion's line now names its signer, on the complaint's Related tab too), the authority report,
  its approval and the decision record PDF. **Your data's step 10 opens your own product's trend**, not
  the sample's OrbitCare rise.
- **The story is the team's.** One step for every colleague, read from the shared record; a step any colleague opened
  from the story (the call, the report, Records, Trends) counts for everyone. A colleague's banner no longer says "Step
  5 of 10: Form" while the shared report waits for approval.
- **The finale says the trend check's own verdict with its numbers**: "PulseWatch 410 Rev A: in line with history · 3
  against 1.0 expected (3.0× expected) · p 0.076: within chance, not a rise", never "in line" alone beside 3 against
  0.99. Once the story is done, its preview is the finale; the last button offers a pilot once a colleague has joined.

### Fixed: Home, the complaint page, Import and Team

- **Home follows the Sample · Your data switch**: on Your data its Overdue and Due this week tiles, its next actions
  and its rising trends are your data's only (the sample's SAMPLE-RV-08 and OrbitCare were counted before), and the
  complaint its hero names is always in "Your next actions", first among those due at the same time. Each trend row
  now names its product's own identifier (`product.identifier` on `GET /api/v1/triage/trends`).
- **A complaint waiting for its country** says "Waits for the incident country" in its decision path and its market
  assessments, never "No market to assess"; while a clock waits for a fact, the rail no longer says "No legal clock
  running" for the market the header names.
- **A day-only awareness stays a date** in the triage form ("31 Oct 2026, time not recorded" offered "05:30 PM"), and a
  later awareness asks "Why is it later than the earliest known?" before saving, not after a refused save.
- **Import's checklist** shows what was just loaded at once, products a complaints file created included (the run's
  data-quality report keeps `also_created`).
- **Team**: the owner's control to change a colleague's personas says "Change", not a lock.
- **Smaller fixes**: Home's At risk tile and trend card open the trend check, where their count is; step 6 no longer
  promises "Most fields arrive filled"; on a phone the complaint header's clock chip wraps inside its card, and the
  privacy notice sits above a side drawer; the search's `aria-controls` names its results only while they are shown,
  and the cited line's link reaches 4.5:1 contrast; Getting started's type sizes are the scale's.

### Changed: the decision tree and the report page (D2's misses)

- **The tree while answering**: the Answer · Edit switch sits on the market row, the page head is shorter, the starter
  mark is said once, and the line under Sign gives the worked complaints only. Sign now ends about 95 px above the
  bottom of a 1440×900 screen on every market's tree, India included (it ended 28 px above).
- **The report header's starter chip** reads "Starter, for your consultant to confirm", the one starter wording, and
  its approval reasons say "You prepared this report: a second person must approve it", never "snapshot".

## [0.10.83] - 2026-11-03

On the trial maintenance line (`release/0.10`): round D2 "Decide and report" of the approved redesign, on the new
navigation. No migration. The API and web images change. No operator step: nothing stored is rewritten (signed
records keep their words).

### Changed: the decision tree is the questionnaire

- **Answer on the Decision trees tab.** Pick a complaint, then answer each question of its market's tree in place: Yes,
  No, Unknown or Not applicable. The complaints still to assess are listed, not only those already walked. The
  Complaints › Reporting side panel's address opens the tree.
- **Facts arrive as one line to confirm; judgements are never pre-filled.** "Serious injury" (21 CFR 803.3(w), and
  India's serious criteria alike) is now a judgement, with the record's words beside it.
- **Questions earlier answers make unnecessary fold into one grey line** saying why, and are not required to sign.
- **The outcome updates as you answer**: Reportable with its type, rule and due date, Not reportable, or Pending
  information, with "Why" chips. On a phone a sticky outcome bar below the first question carries Sign.
- **Signing takes about four actions**: the outcome and Sign in one card, "Follow the outcome" by default (an
  override needs a reason), a one-line reason for each judgement and each fact changed from the record shown as a short
  checklist, the training confirmation as one line under the password. After signing, each answer reads as text with
  its reason, with who signed, when and what it means. The real role decides who signs, never the persona.
- **The form for the incident's country** is named beside the outcome (US 3500A, India MDAE, EU/NI MIR, GB MHRA MIR,
  the Health Canada report) and opens once signed. Where another market's reporting may also apply, an advice-only
  flag, starter; it creates no second report.
- **Edit this tree on the same tab**: questions as read-only rows with a pencil, the regulation's text and clause
  locked, extra questions that never change the conclusion, one button to test against the worked complaints and send
  for approval, and an approver who sees only what changed, with password and authenticator code. Settings ›
  Reportability guides still works.

### Changed: the report and its approval

- **"N things to give (M fields)"**, grouped by who knows them: your product (enter once), your organization (enter
  once), this event. A product's or the organization's fact entered once on a report is saved on the product or as the
  market's responsible party and reused on every report for that product; it never overwrites a value already held.
  The full report folds away while anything is missing, and the field count is said once.
- **Approval in plain words**: "Approve the India report for SAMPLE-RV-10. Prepared by Asha. You confirm with your
  password." The approver reads "What you are approving", the values as frozen in the form's order with their sources,
  above the password and Approve; a success panel follows. The approval task reads the same way. No "snapshot",
  "fingerprint" or "checksum" on these screens (the PDF keeps the checksum).
- **Every signature shows the signer's full name, date and time, and its meaning** (signed reportable, prepared,
  approved for submission, or practice approval) on the report, the PDF and Records (21 CFR 11.50). A new approval's
  meaning says "version", not "snapshot".

### Fixed

- **One starter wording, on starter content only**: "Starter, for your consultant to confirm". An approved guide of your
  own is no longer marked "Starter text" in the assessment.
- Report field sources name the complaint by your reference and the market in words ("SAMPLE-RV-07 EU and Northern
  Ireland (EU MDR) v1 (signed)", not "CMP000035 EU_NI v1"); the tree's version line reads "approved 30 Oct 2026".

## [0.10.82] - 2026-11-03

On the trial maintenance line (`release/0.10`): round D1, "One story", of the approved redesign, for trials on the
new navigation. The classic navigation is unchanged. No migration. No sample record, deadline or count changes. The
API and web images change. No operator step: `refresh_trial_story.py` has nothing new to do.

### Changed: Getting started tells one story

- **One complaint, from the first call to the signed report.** Getting started opens on one hero and one rail of ten
  steps: the call, triage, the decision tree, reportable or not, the form for the country, fill what is missing,
  approval, PDF and submission, Records and Trends. Each step has one main button that opens the real screen with the
  record in place. A step is ticked from what was saved on the record (new read: `GET /api/v1/trial/one-story`);
  opening the call, the report, Records or Trends from the story is the person's own mark
  (`POST /api/v1/trial/one-story/marks`, kept on the trial's request, no business record changes).
- **The sample first, then your data.** The sample walks SAMPLE-RV-11. After step 10, "Do the same with your data"
  runs the same ten steps on the trial's own most urgent imported complaint: the most serious harm, then the shortest
  clock. Where the file lacks a fact, the step says so and the complaint page asks for it. The sample's last step shows
  the monitor's own trend, then the OrbitCare 300 Rev B rise.
- **Everything else folds under "More ways to explore"**: the shorter stories, the ten chapters, the trial journey,
  the sample data and your trial.

### Changed: the record pages, Home, Team and Import (new navigation)

- **One Next step, one progress indicator.** On the story's own complaint the rail's Next step is the story's step,
  and the story is a slim "Story · Step N of 10 · Back" pill. The complaint and report pages show one status line,
  "Stage 2 of 6 · …", in place of the chevrons; on the complaint page its steps are links (Market assessment opens the
  tree, Report the report).
- **The complaint page:** harm in words ("No harm reported", "Serious injury", "Not known yet"), with patient
  involvement on its own line; checklist lines name the step and its state, never a goal beside a state that denies it;
  each missing fact is asked once, in Details ("Asked below" elsewhere); one clock line in the header ("Shortest
  possible: 5 days left · due Sun 8 Nov").
- **"Shortest possible" is the true shortest deadline** (trials and pilots). While a complaint waits for its country or
  awareness date, its provisional clock is now the earliest per-market deadline its triage table shows, on the
  complaint page, Home, the story's hero and the reportability watch: one calculation. It read a later reporting
  window's date before (an imported serious injury with no country: Mon 9 Nov on the page, Sun 8 Nov for Great Britain
  in its own triage table).
- **Home, every persona:** a slim "Continue the story" banner on the sample; on your data, the most urgent complaint
  and what the file did not say; "Story complete" once done. The tiles say "Reading…" while loading and each opens the
  list it counts. Overdue is now the complaint list view "Overdue" (`GET /api/v1/complaints?view=overdue`), so the tile
  and the list are one number. The trend card draws observed and expected as bars.
- **All open complaints** lists the most urgent first: overdue, then the nearest clock, the undated last.
- **Team: several personas per colleague.** The owner ticks one or more personas (`personas` on
  `POST /api/v1/trial/team` and `POST /api/v1/trial/team/{id}/persona`). The first persona's role is the account role,
  the others additional roles, so the rights add up; nobody approves what they prepared. The colleague switches
  "Viewing as" between their own personas only; with one, it stays locked. Audited as TRIAL_PERSONA_ASSIGNED with the
  personas before and after. Pilot users keep their role's one persona.
- **Import your data:** one drop zone that detects which of the 18 objects a file is
  (`POST /api/v1/data/import/detect`, nothing saved), "Choose a file" as the main button, and the 7 core objects in
  loading order with what each unlocks and whether it is loaded ("More objects (11)" folded). A blank serious-injury
  cell is flagged in the rows to check: it is asked at the decision tree, never filled in.
- **Smaller fixes:** page heads name the section and the page's question, with the time zone once, on Home (U-15);
  the trend sentence names its 30-day window and an investigation's scope says it counts every linked complaint; a
  call's reference (SAMPLE-URG-01) opens as "a call, not a complaint yet", search finds calls, and Home's next action
  opens its triage card; on a phone the tab bar shows that more tabs exist; one avatar on the top bar; the colleague
  welcome links Getting started.

## [0.10.81] - 2026-11-03

On the trial maintenance line (`release/0.10`): the Critical, High and Medium findings of the functional review of
0.10.79, and selected findings of the usability, security and navigation reviews. Some of them gave wrong regulatory
deadlines on mdarix.com. No migration. The API and web images change.

**Operator step:** run `python scripts/refresh_trial_story.py` (a dry run: it lists what it would change), read the
list, then run it again with `--apply`. For every running trial, with or without its sample, it now adds the
reporting windows of every market the trial lacks, moves each open report (not yet submitted) to its market's latest
signed conclusion (report type, due date, provisional flag), recomputes draft assessments under the Unknown rule
below, and sets the sample US report's FDA product code. Everything it changes is audited; it never changes a signed
conclusion or a submitted report: those it lists, for a person to act on. A second run changes nothing (it lists
again only what a person must act on).

### Fixed: deadlines (trials and pilots)

- **Re-signing a conclusion moves its report** (F1). A report created as the 30-day 3500A stayed on its old date
  after the conclusion was signed again as the 5-work-day report. Every open report of the market now follows the
  latest signed reportable conclusion: report type, due date and provisional flag, with before and after in the
  audit trail. A snapshot approved for the old type is set aside and needs a new approval. A submitted report is
  never changed: its page says what the later conclusion says and suggests a follow-up (or final) report.
- **An Unknown answer keeps the shorter report** (F2). In the US, an Unknown on "remedial action" now gives the
  5-work-day report; in the EU and Great Britain an Unknown on "serious public health threat" gives the 2-day report,
  and one on "death" or "unanticipated" the 10-day report. A note says which question is Unknown and what a No would
  change it to (MDCG 2023-3 for the EU and GB). Starter rule, for your consultant to confirm. Canada is unchanged.
- **Every market has a reporting window in every trial** (F5). A trial started with windows for the US, the EU and
  India, so a Great Britain or Canada death had no assessment and no clock. New trials get every market's starter
  windows; running trials get them through the refresh.

### Fixed: missing facts are asked for, never guessed (trials and pilots)

- **No country, or one MDARIX does not know** (F3, U-01): the complaint is no longer "No market to assess". The
  complaint page and the market assessment ask for the country, with why and which rule needs it; until it is
  entered every market's shortest clock runs, provisional, Home lists "Enter the incident country", the checklist's
  market step waits, and no market conclusion can be signed. Countries are read by name or ISO code.
- **No awareness or received date** (F4): the clock is provisional (counted from the event date, else from when the
  record arrived), the awareness date is asked for the same way, and no conclusion is signed until it is entered. A
  time confirmed at triage becomes the complaint's awareness, so it is not asked twice.
- **A blank received date stays blank** (F10): an import no longer copies the event date into it; the watch says the
  clock counts from the "event date (no awareness or received date)". Complaints imported earlier keep theirs.
- **A day without a time is a day** (U-06): an imported awareness date is shown as "29 Oct 2026, time not recorded",
  and counted as that day in every time zone (the counting rule for a day without a time).
- **The import check flags rows** (F9) that import but need a look: no or an unknown country, no awareness or
  received date, an awareness before the event, a death or serious injury with no patient involved, a text row with
  fewer columns than its header. They are listed in the check and in the run's data-quality report ("Rows to check").

### Fixed: authority reports

- **Fields take what they are** (F6): a date field takes a date, a range field a date or "date to date", an IMDRF
  code field only codes from the code picker (on both navigations), the FDA product code and EMDN fields only codes
  of the loaded lists; G8 follows the front page's manufacturer report number. A value typed earlier that does not
  fit is flagged on the report and counts as missing; nothing is deleted.
- **The EU and GB MIR do not guess 1.2d or 3.2c** (F12): the reportability date and the device's current location
  are left for the person, each with a short note.
- **Cancelled reads Cancelled** (F11): a report cancelled by "not reportable" no longer reads MET, and once a new
  conclusion reopens it, the old cancellation note leaves the page (it stays in the audit trail).
- **A report sent back for correction** is not "Mandatory fields complete" and not "Submitted this month" (M3).
- **One report list on the new navigation** (M7): Complaints › Authority reports and › Reporting show the Reports
  tab's own list and words; a report link opens the Reports page; the complaint page's report step opens the report.

### Fixed: records, screens and security

- **Audit before and after** (F7) for report fields, a product's identity (UDI-DI, Basic UDI-DI, GMDN, EMDN), its
  registrations and the responsible parties, and for a cancelled report.
- **Trend check** (F8): a version's first day is counted in its history (it was left out, so "expected" was low).
- **Imported records are never "sample"** (M6).
- **The bell** (H1) opens Home, which now shows the reminders and escalations with Mark all read; the bell stays on
  a phone.
- **"Due this week" is one number** (M1): the complaints of the Complaints list view of that name, on Home and in
  Team overview; each Home tile opens its list.
- **Search** never opens `/app/reports?report=null` (M2).
- **Home while it reads** says so, never "Nothing past its time" or "No legal clock is running." (U-07).
- **"Invite two colleagues"** completes at two (U-05).
- **Downloads** whose file name has an en dash or any non-Latin letter no longer fail: every download sends an ASCII
  name and the UTF-8 one (security F3).
- **Trial invitations** are rate limited first, and an address with an account in another organization gets the
  same neutral answer as any address that cannot be invited (security F1).

### Sample numbers and labels that change

| Where | Before | After |
|---|---|---|
| Reporting windows | 4 (FDA 30, EU 15, EU 10, India 15) | 8 (adds MHRA 15 and 10, Health Canada 10 and 30) |
| Decision trees | Great Britain and Canada "not in your reporting windows" | enabled |
| A sample complaint's market assessment | US, EU / NI, India | the five markets |
| Triage panel, provisional clocks (e.g. SAMPLE-RV-11) | US, EU / NI, India | adds Great Britain and Canada "if also reportable" (GB 11 Nov, CA 12 Nov) |
| SAMPLE-CALL-03 (GB) | "No reporting window for the event's own market" | its Great Britain clock |
| Home, Due this week (Admin, day 0) | 11 (every dated item) | 4 (complaints, the list view) |
| Team overview | "Due soon, whole team" 2 | "Due this week, whole team" 4 |
| Sample US report, D2A | "SMP (sample: your FDA product code)" | FRN |
| SAMPLE-RV-07 EU MIR, 1.2d | the signing day ("From record") | empty, for the person |
| SAMPLE-RV-07 EU MIR, 3.2c | from "device returned" | empty, must have (the meter counts it) |
| SAMPLE-RV-10 India report | "Mandatory fields complete"; in Submitted this month | "Draft: correction required"; Open reports only |
| A cancelled report's deadline | "No deadline: not reportable" (state MET) | "Cancelled: not reportable" |

No sample deadline, trend figure or signal count changes on day 0 (the sample's versions are older than the trend
history's 180 days, so F8 does not move them).

### Tests

- pytest `tests/test_release_0_10_81.py` (new, 15), `tests/test_market_assessment_rules.py` (F2),
  `tests/test_signal_trend_rules.py` (F8); updated: `test_release_c3_0_10_75.py`, `test_release_c4_0_10_76.py`,
  `test_release_c5_0_10_77.py`, `test_approval_told_api.py` (fields filled by kind: `tests/report_fill.py`),
  `test_free_trial.py` (8 windows), `test_trial_import_reports.py` (row flags).
  `test_flagship_walkthrough.py` (the report step opens the report; fields filled by kind), `test_trial_self_admin.py`
  (CANNOT_INVITE).
- vitest `release0081.test.tsx` (new), `TrialGuidePage.test.tsx`, `releaseC5077.test.tsx`.
- Targeted pytest (this release, the reports, assessments, imports, intake, oversight, links, complaint page, trends,
  deadlines, decision guides, readiness, team, business permissions, alembic drift, the migration chain, free trial):
  427 passed; 1 fails as it did on 0.10.80 (`test_one_deadline_api.py::test_triage_shows_the_events_own_market_first...`,
  unchanged by this release). vitest: the 71 files that render or import a changed module, 638 passed.

## [0.10.80] - 2026-11-03

On the trial maintenance line (`release/0.10`): a trial's own data on the new navigation (owner request, 3 November
2026). No migration. The API and web images change. No operator step: `scripts/refresh_trial_story.py` has nothing new
to do (the sample does not change).

### Changed (trials on the new navigation; the classic navigation and pilots are unchanged)

- **Getting started is a tab, the first one, left of Home**, for every persona in a trial (it holds the guide and the
  stories). A pilot's tab bar has no Getting started.
- **The import leaves Getting started.** Its "Your data" tab is gone on the new navigation; the rest of Getting started
  (the sample event, the stories, the ten chapters, About the sample data, Your trial) stays.
- **Import your data is its own page, `/app/import`** (in the link table, as Decision trees and Reports are). The top
  bar's Import your data button, its avatar-menu item at narrow widths, the Complaints header's button and Help › Try
  your own data open it. Old links to Getting started › Your data (a data-quality report's `?report=` too) land on it;
  on the classic navigation `/app/import` opens Getting started › Your data, as before. The page holds the same upload,
  each import's data-quality report and what the data shows (Automatic insights). Once the organization's complaints
  are in, one main button, **See your complaints**, opens Complaints › All complaints on your data. Removing the sample
  is offered on the page, folded and optional, with its existing confirmation (the trial owner only).
- **A sample-only trial and a person who may not change records** see no Import button and no Help › Try your own
  data. Opening `/app/import` says plainly "This evaluation uses the sample only" (with Discuss a pilot) or "Import is
  not available to you"; the server refuses their imports as before.
- **The top bar's data, read from the server** (`/api/v1/trial/status`, read again after an import or the sample's
  removal): the sample alone shows the **Sample data** label and Import your data, as before; the sample and imported
  complaints together show a small choice, **Sample data · Your data**, the sample by default; once the sample is
  removed, neither (until now the label read "Practice records" then, and kept "Sample data" until a reload). At 1100 px
  and narrower the choice is in the avatar menu, as Import your data is.
- **The choice decides which data these show:** every complaint list and list view (Complaints, the All complaints
  filters: the Data filter steps aside while the top bar chooses), Trends › Trends to review, and Automatic insights on
  the Import page. Changing it opens the screen again on the chosen data. It is remembered per person and organization
  in this browser (a view, not a record).
- `GET /api/v1/trial/insights?source=MDARIX_SAMPLE|TRIAL_UPLOAD`: the insights of that data. Without it (or with any
  other value) the insights read as before: the imported data, else the sample. No new route.

### Not reached by the choice yet

Home's counts and next actions, Trends › Trend check, Over time and By resolution, Investigations, Decision trees,
Reports and Records, the Complaints work queues with their own screens (To triage, Calls to check, Due soon, Past
target, Second look, Dismissed, Reporting, Authority reports, Communications), the complaint page, and the top bar's
search. Each shows both datasets, as before.

### Sample numbers and labels that change

No sample record, deadline, signal, trend figure, Readiness value or count changes.

| Where | Before | After |
|---|---|---|
| Top bar (new navigation), sample removed | "Practice records" | no label |
| Top bar (new navigation), sample and imported complaints | "Sample data" | "Sample data · Your data" (Sample data chosen) |
| Tab bar (new navigation, trial) | Home first | Getting started, then Home |
| Getting started tabs (new navigation) | Your data, About the sample data, Your trial | About the sample data, Your trial |
| Getting started's fold (new navigation) | "Explore all capabilities: the ten chapters, your own data and your trial" | "… the ten chapters, the sample data and your trial" |
| The own-data chapter's data line (new navigation) | "…, under Your data below." | "…, on Import your data." |

### Tests

- pytest `tests/test_release_0_10_80.py` (new, 2): the insights read the chosen data and, without a choice, as before;
  the route's parameter is bounded.
- vitest `release0080.test.tsx` (new, 11): Getting started first in a trial's bar, never a pilot's; Getting started
  without the upload (new) and with it (classic); `/app/import`, the old links and every way in; the page's upload,
  reports, insights, its one main button and the folded removal; the bar's label, choice or nothing from the server's
  counts; the choice in the avatar menu, remembered per person; the complaint lists, list views, Trends to review and
  insights follow it; sample-only and no-rights people get the plain message and no Help item. Updated:
  `importOwnData.test.tsx` (the button opens the new page), `releaseC1073.test.tsx` (Getting started before the
  personas' tabs).
- Targeted pytest (this release, free trial, trial insights and status reads, business permissions, link targets,
  alembic drift policy, the migration chain, 0.10.79, import signals after the response): 77 passed. vitest: every
  file that renders the shell, Getting started, the complaint list, the signal inbox, Help or the link table, plus the
  import, insights and sample-removal files (38 files): 260 passed. tsc, ruff and prettier clean.
- Screens at 1440 and 390 in `MDARIX-videos/site-0.10.80-review` (`owner/`: the tab bar, Getting started without the
  import, the Import page before and after uploading six fictional complaints, an old Your data link landing there, See
  your complaints; `both/`: Sample data · Your data in both states, Complaints, Trends to review and the insights on
  your data, the avatar menu at 390; `removed/`: the bar after the sample is removed; `regulatory/`: a locked
  Regulatory Leader, "Import is not available to you"; `classic/`: unchanged).

## [0.10.79] - 2026-11-03

On the trial maintenance line (`release/0.10`): small owner-approved follow-ups to Release C. No migration. The API and
web images change.

**Operators:** `scripts/refresh_trial_story.py` (dry run), then `--apply`: adds the two new sample IMDRF links to
each running trial whose sample has none for those codes (`backend/app/trial/sample_0_10_79.py`). Idempotent; a code
the trial already links, the trial user's own link included, is left as it is.

### Changed

- **Settings › Products: the Regulatory Leader may change it.** A product's identity (UDI-DI, Basic UDI-DI, your own
  GMDN code and term, EMDN code), its registrations per market and the responsible parties are changed by people who
  may change records and now also by the Regulatory Reviewer role (the Regulatory Leader persona), through its
  business permission `regulatory.review` (the server's guard and the screen read the same rule). Nothing else is
  granted: the Risk Reviewer and View only stay read only, and proposing a code mapping still needs records.write.
  This holds in pilots too: a pilot's Regulatory Reviewer may change the same records. Every change is audited, as
  before.
- **Tenant 360** says beside Navigation: "“Viewing as” personas need New."
- **"Import your data" on the new navigation's top bar**, beside the trial's "Sample data" label (owner request). It
  opens the trial import that Help › Try your own data opens: Getting started › Your data (upload, the data-quality
  reports and what the data shows). Where the top bar hides the label (1100 px and narrower, a phone) it is in the
  avatar menu instead. The Complaints header offers the same button in a trial too (until now pilots only), opening the
  same flow; a pilot's still opens Import data. One rule everywhere, the Import data screen's: not in a sample-only
  trial, and only for people who may change records (a Regulatory Leader, Risk Reviewer or Executive colleague does
  not see it). The sample and its label are unchanged; the classic navigation is unchanged.

### Fixed

- **The triage panel's × closes it** (reported on mdarix.com). On the new navigation a complaint's page opens its
  triage panel by the complaint (`To triage?complaint=<id>`; a story by `ref=`). Closing cleared only `item=`, so the
  complaint or reference left in the address opened the panel again at once. Closing, and saving, now clear all three
  in one address change; Back still reopens it. The other drawers open by one address parameter and were not affected.
- Settings › Products on a phone: the Edit button beside a product broke into "E di t" (since 0.10.77).

### Changed: the sample's last two problem codes get their IMDRF terms

Looked up in IMDRF's own Release 2026 workbook
(`imdrf-tech-ae-terminologies-n43-ReleaseNumber2026-Annexes-revisedJune.xlsx`), the most specific Annex A term that
says what the complaint says (sample mappings, approved by the sample reviewer; `sample_imports.SAMPLE_IMDRF_LINKS`):

| Sample problem code | Complaint | Before | After (release 2026) |
|---|---|---|---|
| FLOW_ZERO_READING (SAMPLE-RV-07) | "Flow sensor showed zero flow for 40 seconds; staff switched to manual ventilation. No harm." | no link | A090808 Low Readings (level 3, under A0908) |
| SPO2_DROPOUT_HARM (SAMPLE-RV-01) | "Monitor's SpO2 reading dropped out overnight; the patient desaturated …" | no link | A090811 Unable to Obtain Readings (level 3, under A0908) |

NFF (No Fault Found) keeps no link: it is not a device problem.

### Sample numbers and labels that change

No deadline, signal, trend figure, Readiness value or record count changes.

| Where | Before | After |
|---|---|---|
| Problem code beside SAMPLE-RV-07 and SAMPLE-RV-01 (Complaints, the complaint page) | no IMDRF term | A090808 Low Readings; A090811 Unable to Obtain Readings |
| SAMPLE-RV-07's EU MIR, 3.2a IMDRF Annex A (new navigation) | empty, missing | "Suggested: A090808 Low Readings", still missing until the regulatory manager confirms or changes it |
| SAMPLE-RV-07's EU MIR meter | 8 of 24 | 8 of 24 (unchanged) |
| SAMPLE-RV-01 | no authority report | unchanged (no report) |
| Settings › Products, "Who can change this" | PMS / Signal Triage Lead, Quality Investigator, Quality Reviewer, Authorized Decision Maker, Leader (Quality Manager) or Customer Administrator | PMS / Signal Triage Lead, Quality Investigator, Quality Reviewer, Authorized Decision Maker, Leader (Quality Manager), Customer Administrator or Regulatory Reviewer; the Regulatory Leader reads "You can." and gets Edit and Add |

### Documentation

- `docs/release-notes/0.10.79-trial-owners.md` (new, not sent): colleagues invited before 0.10.73 keep the Quality
  Leader persona until the owner changes it in Team, and how.

### Tests

- pytest: `tests/test_release_0_10_79.py` (new, 2): a locked Regulatory Leader changes a product's identity, adds and
  removes a registration and sets and removes a responsible party; a Risk Reviewer and an Executive read and are
  refused every change (403); proposing a code mapping stays refused; a running trial gets the two links once (dry run,
  idempotent) and a trial user's own link is kept. Updated: `test_release_c5_0_10_77.py` (the sample links test covers
  the two new codes, word for word, at level 3; its refresh test turns back only 0.10.77's links; its audit check
  reads the events in order: it read them unordered and failed now and then).
- Targeted pytest run (this release, C5, C4, C3, C1, Release B, business permissions, alembic drift policy, the
  migration chain, free trial, flagship walk-through, complaint list, authority reports API, import reports, trial
  story reads): 134 passed.
- vitest: `release0079.test.tsx` (new, 4), `triageClose.test.tsx` (new, 3), and the files touched (releaseC5077,
  ImportReports, ImportExcel, importPrivacy, lotImpact, releaseA071, TenantPages, intake, linkTable, noCodes): 12
  files, 99 passed. `importOwnData.test.tsx` (new, 5: the owner's button opens Getting started › Your data; none for a
  sample-only trial or a colleague without records.write; the avatar menu item; the Complaints header in a trial and a
  pilot; classic unchanged) with the shell's tests (releaseA071, now expecting the trial's header button, C1, C2,
  B072, accessibility, complaints, workspaceStart, readiness, reportingCapa): 10 files, 92 passed. tsc, ruff and
  prettier clean.
- `scripts/refresh_trial_story.py` dry run on the local test database: runs, changes nothing.
- Screens at 1440 and 390 in `MDARIX-videos/site-0.10.79-review` (`regulatory/`: Settings › Products as a locked
  Regulatory Leader, editing a product's identity, setting a responsible party; `risk/`: the same, read only, as a Risk
  Reviewer; `admin/`: Tenant 360's Overview with the line beside Navigation; `topbar-owner/`: the top bar with Import
  your data, the avatar menu at 390, the flow it opens, the Complaints header; `topbar-sample-only/`: no button, no
  menu item).

## [0.10.78] - 2026-11-03

On the trial maintenance line (`release/0.10`): the trial's size, in words. Since 0.10.73 a trial holds up to 50
people (the safety cap `MDARIX_TRIAL_USER_CAP`); the website and the legal text still said 3. No migration and no
change to how the product behaves.

### Changed
- **Website:** the home page, the free trial page, the questions page and the search descriptions say "up to 50
  people" instead of "up to 3 users".
- **Free trial agreement** (`legal/trial-agreement.md`): "Users: up to 50 people from your organization", last
  updated 3 November 2026. Its SHA-256 changes, so sign-ups from now on record the new version
  (`onboarding_requests.legal_acceptance`); earlier acceptances keep the version they accepted.
- `legal/README.md`, the support runbook and the trial guide's team picture ("3 people · up to 50") say the same.
- The trial invitation e-mail already read the cap and is unchanged.

## [0.10.77] - 2026-11-03

On the trial maintenance line (`release/0.10`): part C5 of Release C, "Codes", built to the owner-approved design (the
report page's code fields). Codes change organizations on the **new** navigation (`tenants.navigation = new`); the
classic navigation, and every pilot on it today, keeps its 0.10.58 report rules (a mapped code there is still "From
record"). MDARIX never decides and never submits: the code the approved mapping suggests is confirmed or changed by the
regulatory manager, and nothing reaches a form or a PDF unconfirmed.

**Migration `tr16codelists`** (after `tr15canadamarket`; `tr03pmssources` stays reserved). It is expand-only:
`imdrf_codes.status` and `status_note`; two shared reference tables, `reference_codes` and `code_list_files` (the
runtime role only reads them); `products.basic_udi_di` and `emdn_code`; `product_registrations.risk_class`;
`market_responsible_parties.srn`. No stored row changes. On legacy dedicated organization databases, run
`scripts/add_workflow_tables_to_legacy_planes.py` (new step tr16). The API and web images change, and the image now
carries the published code lists in `data/code_lists`.

**Operators, in this order, each dry run first** (the code lists need the owner's explicit OK for production):

1. `docker compose -f docker-compose.prod.yml run --rm migrate python scripts/load_code_lists.py` (dry run: checks
   every file against `data/code_lists/manifest.json` and says what it would load), then the same with `--apply`. It
   runs as the database owner. A second run loads nothing.
2. `scripts/refresh_trial_story.py` (dry run), then `--apply`: re-records each running trial's sample IMDRF links to
   Release 2026 and records SAMPLE-RV-09's frozen 3500A codes as confirmed (`backend/app/trial/sample_0_10_77.py`).
   Idempotent.

### Added: the published code lists

Loaded only from the publishers' own files, byte for byte (`data/code_lists`, SHA-256 in `manifest.json`), by
`scripts/load_code_lists.py`. Each file is checked whole before anything loads (its SHA-256, its columns, every code
present and unique, every parent in the file) and a malformed file is refused. Nothing is ever deleted: a file that
leaves out a loaded code is refused; a new version loads beside the old one, so old reports keep their codes.

| List | Source | Version and date | Rows |
|---|---|---|---|
| IMDRF adverse event terminology, Annexes A-G | IMDRF, "Terminologies for Categorized Adverse Event Reporting (AER)" (imdrf.org), `imdrf-tech-ae-terminologies-n43-ReleaseNumber2026-Annexes-revisedJune.xlsx` | Release Number 2026; annexes approved January 2026; workbook revised June 2026 | A 491, B 34, C 160, D 45, E 812, F 82, G 307 (1,931; 15 retired, 31 headings "Not selectable") |
| FDA CDRH adverse event codes, with FDA's IMDRF code per row (FDA's FDA-IMDRF mapping) | NCI EVS `FDA-CDRH_NCIt_Terminology_Subsets.txt`, the file FDA's "MDR Adverse Event Codes" page points to | NCIt 26.08e, posted 2 Sep 2026 | 1,885: device problem 487, clinical 784, health impact 81, component 299, type of investigation 31, findings 160, conclusion 43; every one maps to a code of IMDRF Release 2026 |
| FDA product codes (product classification) | accessdata.fda.gov `foiclass.zip` | 2 Nov 2026 | 7,098 |
| EMDN | European Commission, `EMDN v2026_EN.xlsx` (health.ec.europa.eu, "Download EMDN") | v.2026, file dated 25 Sep 2026 | 8,516 |

- Annex E lists 202 terms a second time under another heading with the same code; each code is kept once, at its own
  heading (the one its code starts with), which carries IMDRF's latest wording.
- **GMDN is licensed and never loaded**: each product keeps the organization's own GMDN code.
- **ISO 3166 country codes were already in MDARIX** (the imports' 249 alpha-2 codes): not loaded again.

### Added: codes on reports (new navigation)

- A code the approved mapping supplies is **"Suggested from your approved mapping"**: it counts as missing in the
  mandatory-fields meter, Send for approval stays blocked, and it is **never frozen into a snapshot**, so it never
  reaches the form or the PDF, until the regulatory manager **confirms** it or **changes** it. The report records
  which (Confirmed, Changed from the suggestion, or Entered), what was suggested, who and when; the audit event names
  the codes.
- **The code picker**: search an annex by word (code, term or definition), or browse it heading by heading; each code
  shows its definition and its FDA code. Retired codes are not offered, and IMDRF's "Not selectable" headings cannot be
  chosen; a report that already holds a retired code keeps it.
- **One choice fills both**: on the FDA's form every IMDRF code carries its FDA code from FDA's published mapping, for
  example "A090807 High Readings (FDA 2459)".
- **Required codes per form and report type** (starter, for your consultant to confirm): an initial 3500A needs the
  device problem and both health effect codes (H6) and, as before, the conclusion code; the EU MIR needs Annex A, E and
  F on every report and B, C, D and G in a final one; the GB MIR a code from every annex. The MvPI MDAE and Health
  Canada's form have no code fields.
- Device problem codes come from the problem-code mapping. Health effect codes are suggested where an approved mapping
  of the assessment's harm code exists (none in the sample).

### Added: Settings › Products

- Each product's UDI-DI, **Basic UDI-DI**, GMDN code and term (your own), **EMDN code** (checked against the loaded
  EMDN, its term shown); its **registrations per market**: the FDA product code (checked against FDA's
  classification, its device name shown) with the 510(k), PMA or De Novo number, the notified or approved body and its
  number, the Health Canada licence, the CDSCO licence, and the **risk class** in that market (US I-III; EU, NI and GB
  I, IIa, IIb, III and IVD A-D; Canada I-IV; India A-D; starter, for your consultant to confirm).
- The organization's **responsible parties** per market and role, with their **SRN**.
- They fill the forms: the EU MIR's manufacturer SRN (1.3.2b), Basic UDI-DI (2.1c), nomenclature (2.2a/b: EMDN where
  set, else GMDN), notified body number (2.3p) and risk class (2.4); GB's risk class; the MDAE's device class (A1);
  Health Canada's device classification (C4 i).

### Changed: the sample's codes (checked against IMDRF's own Release 2026 file)

The addendum's check, against `imdrf-tech-ae-terminologies-n43-ReleaseNumber2026-Annexes-revisedJune.xlsx` (Release
Number 2026): all four earlier links exist with their terms word for word, but each was a broad heading where the file
holds the exact term, so each sample code now links to the most specific term that says what its complaint says, of
release 2026 (sample mappings, still approved by the sample reviewer; `sample_imports.SAMPLE_IMDRF_LINKS`):

| Sample problem code | Before (release 2025) | After (release 2026) |
|---|---|---|
| PRESSURE_ALARM | A16 Protective Measures Problem (level 1) | A1601 Device Alarm System (level 2) |
| UNDER_INFUSION_NO_ALARM | A14 Infusion or Flow Problem; A16 Protective Measures Problem (level 1) | A1407 Insufficient Flow or Under Infusion (level 2); A160102 No Audible Alarm (level 3) |
| FREE_FLOW_DOOR | A14 Infusion or Flow Problem (level 1) | A140502 Free or Unrestricted Flow (level 3) |
| ALARM_VOLUME_LOW | A16 Protective Measures Problem (level 1) | A160103 Low Audible Alarm (level 3) |
| SPO2_READING_HIGH (SAMPLE-RV-11) | A0908 Incorrect, Inadequate or Imprecise Result or Readings (level 2) | A090807 High Readings (level 3) |

FLOW_ZERO_READING (RV-07), SPO2_DROPOUT_HARM (RV-01) and NFF keep no link, as before. SAMPLE-RV-09's accepted 3500A
keeps the code it was approved with (A16), recorded as confirmed by the sample author; a new trial's RV-09 holds
A160103, confirmed by the sample author before its snapshot.

### Fixed

- The trend sentence counts each lot: "lots 003 (4), 004 (4), 005 (1)" (it read "lots 003, 004 and 005").

### Sample numbers and labels that change

No deadline, signal, Readiness value or record count changes.

| Where | Before | After |
|---|---|---|
| SAMPLE-RV-11's US report, once its US conclusion is signed reportable | 8 of 17 mandatory fields (9 to fill); H6 device problem code "A0908 …" from record | 7 of 19 (12 to fill): H6 "Suggested: A090807 High Readings (FDA 2459)", waiting to be confirmed; the two health effect codes now mandatory |
| SAMPLE-RV-09's 3500A (acknowledged) | 17 of 17 | 19 of 19 (H6 clinical and impact "Entered in eSubmitter from the IMDRF Annex E/F release (sample)", as its conclusion code; H6 problem "Confirmed") |
| SAMPLE-RV-07's EU MIR, SAMPLE-RV-10's MDAE | 8 of 24; 14 of 14 | unchanged |
| Problem code beside a complaint (Complaints, the complaint page) | PRESSURE_ALARM: A16 Protective Measures Problem; RV-11: A0908 …; RV-06: A14 …, A16 …; RV-08: A14 …; RV-09: A16 … | A1601 Device Alarm System; A090807 High Readings; A1407 Insufficient Flow or Under Infusion, A160102 No Audible Alarm; A140502 Free or Unrestricted Flow; A160103 Low Audible Alarm |
| Trend sentence (Home, Trends) | OrbitCare 300 Infusion Pump (Sample) Rev B: 9 complaints … lots 003, 004 and 005 | … lots 003 (3), 004 (4), 005 (2) |
| 3500A section H note | H6 codes come from your approved IMDRF mappings of the complaint's problem code (Records > Reference data). | H6 codes are suggested from your approved IMDRF mappings of the complaint's problem code; you confirm or change each one in the code picker (IMDRF and FDA codes). |
| A code field's status (new navigation) | From record | Suggested from your approved mapping · Confirmed · Changed from the suggestion · Entered by a person |
| Settings tabs | 7 | 8: Products |

### Tests

- pytest: `tests/test_release_c5_0_10_77.py` (new, 11): the four published files parse and a malformed file is refused
  (another SHA-256, a wrong header, a bad or misplaced code, a duplicate, a zip without foiclass.txt); the sample links
  are Release 2026's codes and terms word for word, at their levels; a suggestion counts as missing and is never frozen;
  the loaders load once and never delete (a second run finds 0 new, 0 changed; a file leaving out a loaded code is
  refused); the picker searches by word, browses the annex and leaves out retired codes; nothing is filed unconfirmed,
  one choice fills FDA and IMDRF, the approved PDF holds the confirmed code and the audit says confirmed, changed,
  confirmed; a retired code stays on its report and cannot be chosen again; the required codes per report type hold
  approval (EU MIR final: B, C, D); product identity is checked against the lists and fills the EU MIR; the trend
  counts each lot; a running trial is re-recorded once (dry run, idempotent; 0.10.72's step does not add A0908 back).
  Updated: `test_flagship_walkthrough.py` (it confirms the suggested code; still 21 main buttons, 44 actions),
  `test_authority_reports_api.py`, `test_trial_import_reports.py`, `test_release_b_0_10_72.py` (the new links).
- Targeted pytest run (this release, C1 to C4, Releases A and B, business permissions, alembic drift, the migration
  chain, free trial, authority reports API, approval told, the flagship walk-through, import reports, regulatory
  reference, import governance, record facts, trial story reads, sample story days, workspace trends): 181 passed.
- vitest: `releaseC5077.test.tsx` (new, 6) and the files touched (releaseC2-C4, releaseB072, releaseA071,
  ImportReports, authorityReports, linkTable, labels, tokens…): 13 files, 133 passed. tsc, ruff and prettier clean.
- The loader, locally only: dry run, `--apply`, and a second dry run (0 new, 0 changed) on the test database.
- Screens at 1440 and 390 in `MDARIX-videos/site-0.10.77-review` (`owner/`: Home's trend with lot counts, RV-11's
  3500A with the suggested code, only missing, the picker browsing and searching, the code confirmed, RV-07's EU MIR
  codes, RV-09's acknowledged 3500A, Settings › Products and adding a registration, RV-11's problem code; `colleague/`:
  a locked Regulatory Leader sees "Confirmed by Asha Quality" and chooses a health effect code in Annex E, and Settings ›
  Products read only; `classic/`: unchanged).

## [0.10.76] - 2026-11-03

On the trial maintenance line (`release/0.10`): part C4 of Release C, "New forms: EU MIR, Great Britain (MHRA) and
Canada", built to the owner-approved design (its Decision trees and Reports). The three new forms are **starters, for
your consultant to confirm**, on screen, in the PDF and here. They change organizations on the **new** navigation
(`tenants.navigation = new`) only; the classic navigation, and every pilot on it today, keeps the US and India
worksheets and its 0.10.58 report rules. MDARIX still never decides and never submits: a person signs each conclusion
and each approval, and submits the report through the authority's own channel (EUDAMED or the national authority,
MHRA's MORE portal, Health Canada).

**Migration `tr15canadamarket`** (after `tr14reportcancelled`; `tr03pmssources` stays reserved). It is expand-only: the
market check of `complaint_market_assessments` also allows `CA` (Canada). No stored row changes. On legacy dedicated
organization databases, run `scripts/add_workflow_tables_to_legacy_planes.py` (new step tr15). The API and web images
change. **Operators:** run `scripts/refresh_trial_story.py` (dry run first, then `--apply`) once after the upgrade: on
the new navigation it creates the report of each signed reportable conclusion that has none, now for EU / NI, Great
Britain and Canada too (`backend/app/trial/reports_0_10_75.py`). For the sample this is **SAMPLE-RV-07's EU MIR**
(one per trial; a second run finds nothing). A trial approved after the upgrade gets it when its sample is staged.

### Added: three forms, in the authority's own order (starters, for your consultant to confirm)

| Market | Form | Source followed (read 3 Nov 2026) | Report types |
|---|---|---|---|
| EU / NI | EU Manufacturer Incident Report (MIR) | European Commission, MIR form for Serious Incidents (MDR/IVDR) v7.3.1, build SB-11154 (6 May 2026; mandatory from 1 May 2026), and its help text v7.3.1 | Initial · Follow up · Combined initial and final · Final (Reportable incident) · Final (Non-reportable incident) |
| Great Britain | GB Manufacturer Incident Report (MHRA) | MHRA, GB MIR 7.2.1 (changelog 04/06/2025, its five GB schemas and help text), GB MIR and FSCA schema implementation guide (9 Jun 2025), Vigilance reporting requirements (5 Sep 2025) | the same five |
| Canada | Health Canada mandatory medical device problem report | Mandatory Medical Device Problem Reporting Form for Industry, HC Pub. 110180 (April 2018); Incident reporting for medical devices: Guidance document (2021); SOR/98-282 ss. 59-61.1 (current to 2026-10-19) | Preliminary · Update · Final · Preliminary & Final |

- Each form lists its sections and fields in the authority's numbering and order, its fixed lists (the report type,
  the classification of the incident, the device's location, the reporter's role, Canada's device class…), and
  **which fields are mandatory for which report type** (`Field.must_in`): for example the MIR's root cause, risk
  assessment and Annex B, C, D and G codes only in a final report; Canada's preliminary report every section but E2
  and E3, an update or final report only the starred fields (and E2, E3 in a final one). GB adds MHRA's own: the UK
  Responsible Person, the UK approved body numbers, GMDN only, and a code from every IMDRF annex on every report; it
  drops the EUDAMED numbers.
- A run of address lines (street, number, PO box, city, postal code, contact names, e-mail, phone) is one field in
  MDARIX. Patient and reporter fields keep their place and are never stored, as on the 3500A.
- **The report type is a field**: a report starts as the form's first type (Initial; Preliminary); the person chooses
  another, and the mandatory-fields meter follows it. A fixed list takes only one of its choices (422 `NOT_A_CHOICE`).
- Pre-filled from the records where MDARIX holds the value: dates, description, device, lot, UDI-DI, GMDN, IMDRF codes
  of your approved mapping, the classification of the incident from the signed conclusion's report type (2 days: a
  serious public health threat; 10 days: death or an unanticipated serious deterioration; 15 days: all other), the
  responsible parties and registrations of the market, and Canada's 10-day or 30-day classification.
- They use C3's whole path: **created when a reportable conclusion is signed**, the meter, Send for approval blocked
  until every mandatory field is filled, a second person's approval (or the practice label), **the PDF after approval
  in the form's order**, cancelled by a later "not reportable". The PDF and the report page say "Starter form, for your
  consultant to confirm" and the report's type.
- The routes: EUDAMED or the national competent authority (EU / NI); MHRA's MORE portal (GB: MHRA accepts no other
  route); Health Canada's Canada Vigilance by e-mail or fax.

### Added: Canada's decision tree

- A starter question set for **SOR/98-282 ss. 59-60** (`CA-starter-1`): sold in Canada; a failure, deterioration or
  labelling inadequacy; death or serious deterioration, or could do so if it recurred; in Canada, or abroad for a
  Class I device with corrective action intended or required. Report types: **10 days** (death or serious
  deterioration), **30 days** (could if it recurred), **foreign: as soon as possible**. While question 3 is Unknown the
  shorter 10 days applies (conservative). Calendar days, counted in your time zone, as the reporting windows already
  in MDARIX do.
- **Six worked complaints** in its test matrix: 6 of 6 pass. Intake's provisional clocks know Canada (10 or 30 days).
- Canada is a market of the per-market assessment, shown where an organization has a Health Canada reporting window.
- The EU / NI and GB trees were checked: unchanged, 5 of 5 worked complaints each pass.

### Changed: Decision trees and Reports

- **Decision trees shows every market's tree** (US MDR, EU / NI, Great Britain, India, Canada). A market outside the
  organization's reporting windows says so: "Not in your reporting windows". Each tree says which report a reportable
  outcome creates, and whether it is a starter form.
- Reports' "Forms MDARIX prepares" lists the five forms, the three new ones marked "Starter, for your consultant to
  confirm".
- On the new navigation a reportable EU / NI, GB or Canada conclusion opens its report worksheet (the "record where
  and when you reported" form stays on the classic navigation).

### Fixed (C3 follow-ups)

- "Waiting for my approval" listed the preparer's own report in a trial even when a colleague must approve it. It now
  holds a report only for a person who may approve it (the same rule as the approve button).
- An approval task about a report and Oversight's (and Home's) report deadline opened Complaints › Authority reports.
  They open the report itself: its page on the new navigation, its panel on the classic one.

### Sample numbers and labels that change

No deadline, trend figure, signal or Readiness value changes. One sample record is added in each trial on the new
navigation: SAMPLE-RV-07's EU MIR (its EU / NI conclusion was already signed reportable by the sample author).

| Where | Before | After |
|---|---|---|
| Reports, SAMPLE-RV-07 (new) | no report; the market read "Worksheet comes later" | EU Manufacturer Incident Report (MIR) worksheet, a sample report prepared by the sample author: Created from the decision tree, **8 of 24** mandatory fields (16 to fill: the authority, the submission date, the next report's date, the submitter, the manufacturer's SRN and contact, the authorised representative, the risk class, the IMDRF Annex A, E and F codes, the device's location, the reporter's role, the preliminary results) |
| Reports, Open reports (fresh trial) | 1 (SAMPLE-RV-10) | 2 (SAMPLE-RV-07, SAMPLE-RV-10) |
| Home and Oversight, SAMPLE-RV-07's EU item | EU and Northern Ireland (EU MDR): reportable, the report is not started | EU Manufacturer Incident Report (MIR) worksheet: draft; it opens the report (same deadline, same owner) |
| SAMPLE-RV-07's EU assessment (new navigation) | Filing reference and date | Open the report worksheet |
| SAMPLE-RV-07's page, Related › Authority reports | — | EU and Northern Ireland (EU MDR) · EU Manufacturer Incident Report (MIR) worksheet · draft |
| Decision trees, markets shown (sample) | US MDR, EU / NI, India | US MDR, EU / NI, Great Britain, India, Canada; Great Britain and Canada "Not in your reporting windows" |
| Decision trees, each tree | — | "A reportable outcome creates the …" with "(starter, for your consultant to confirm)" for EU, GB, Canada |
| Decision trees' footnote | … A reportable conclusion of the US or India creates its report. | … A reportable conclusion creates the market's report. |
| Reports › Forms MDARIX prepares | United States, India ("In MDARIX today"); "EU and Northern Ireland, Great Britain: record where and when you reported…" | five forms, each with its title and edition; EU, GB, Canada "Starter, for your consultant to confirm" |
| A report's highlights | — | "Initial report" (its type) and, for the new forms, "Starter form, for your consultant to confirm" |
| Triage clocks with no reporting window | US, EU / NI, GB, India | the same and Canada (30 days unflagged, 10 flagged) |
| Approval task for a report; Home and Oversight report items | open Complaints › Authority reports for the complaint | open the report itself |

### Tests

- pytest: `tests/test_release_c4_0_10_76.py` (new, 8): each form's order, report types, fixed lists and sources; the
  mandatory fields per report type (EU MIR, GB MIR, Canada); the EU, GB and Canada trees' worked complaints and
  Canada's conservative 10 days; SAMPLE-RV-07's EU MIR from staging through a type change, a refused choice, the meter's
  block, the practice approval and the PDF in the form's section order with its starter line; a signed reportable
  Canada conclusion creates the Health Canada report (Preliminary, "30-Day; Canadian"); every market's tree; the
  classic navigation keeps US and India (409 `NO_WORKSHEET` for EU) and the refresh adds RV-07's report once (dry run,
  idempotent); "Waiting for my approval" and the report links. Updated: `test_release_c3_0_10_75.py` (RV-07's own
  creation audit), `test_intake_rules.py` (Canada's clock), `test_approval_told_api.py` (its two RV-06 tests failed on
  0.10.75 already: C3's Send for approval waits for every mandatory field, so they fill them first; the bell line
  opens the report).
- Targeted pytest run (this release, C3, C2, C1, Releases A and B, authority reports API and rules, record facts,
  business permissions, alembic drift, the migration chain, free trial, market assessments, decision guides, intake
  rules, legal deadlines, link targets, approval told, Oversight, the flagship walk-through, standards, sample story
  days, trial story reads): all pass after the updates above (first run 210 passed, 4 failed; the 4 rerun green).
- vitest: `releaseC4076.test.tsx` (new, 4) and the files touched (releaseC3075, authorityReports, tasks, linkTable,
  marketAssessment, reportingCapa, flagshipWalk, clickPaths, labels, tokens…): all pass. tsc, ruff and prettier clean.
- Screens at 1440 and 390 in `MDARIX-videos/site-0.10.76-review` (`owner/`: the EU, GB and Canada trees, RV-07's EU
  and RV-11's Canada paths, the Reports list and its forms, RV-07's EU MIR sent for approval, RV-11's Health Canada
  report and its missing fields, RV-07's Related; `colleague/`: a locked Regulatory Leader's waiting list and the
  EU MIR's approval; `approved/`: the EU MIR approved, PDF ready, and the forms card; `classic/`: unchanged).

## [0.10.75] - 2026-11-03

On the trial maintenance line (`release/0.10`): part C3 of Release C, "Decision trees and Reports for the US and
India", built to the owner-approved design (its Decision trees, Reports and report page). It changes organizations on
the **new** navigation (`tenants.navigation = new`); the classic navigation, and every pilot on it today, keeps its
screens and its report rules. MDARIX still never decides and never submits: a person signs each conclusion and each
approval, and submits the report through the authority's own channel.

**Migration `tr14reportcancelled`** (after `tr13viewpersona`; `tr03pmssources` stays reserved). It is expand-only: the
state check of `report_obligations` also allows `CANCELLED`. No stored row changes. On legacy dedicated organization
databases, run `scripts/add_workflow_tables_to_legacy_planes.py` (new step tr14). The API and web images change.
**Operators:** run `scripts/refresh_trial_story.py` (dry run first, then `--apply`) once after the upgrade: on the new
navigation, each US or India conclusion signed reportable before the upgrade whose report was never started gets its
report, as signing now does (`backend/app/trial/reports_0_10_75.py`). The sample's own reports fit the new status path
as they are; nothing of the sample changes.

### Added: Decision trees

- **One tree per market** (US MDR, EU / NI, Great Britain, India: the markets the organization reports to), built from
  the decision guides: the version in use (the organization's approved version, else MDARIX's starter, "for your
  consultant to confirm"), its status (Approved or Starter), its **test matrix result** ("6 of 6 worked complaints
  pass") and its questions in order, each with its clause.
- **The path a complaint took:** each question with its answer (Yes, No, Unknown, Not applicable), its clause, then the
  outcome: the signed conclusion with its report type and who signed it, or what the answers point to so far, "not
  signed". The rail says what happens next and opens the report.
- **A complaint's page opens its path:** Details has a "Decision path" line with one link per market
  (`/app/decision-trees?market=US&complaint=<id>`).
- `GET /api/v1/decision-trees` (`?complaint_id=` adds the paths). Read only, open to every member, as the guides and
  assessments it reads.

### Added: Reports, and a report created when its conclusion is signed

- **Signing a market conclusion as reportable creates the market's report** (Form FDA 3500A for the US, the MvPI MDAE
  form for India), pre-filled from the complaint, the product, the organization and the tree, in the same transaction
  as the signature. **Only a signed conclusion**: saving answers creates nothing. **One report per market per
  complaint**: signing reportable again keeps it.
- **A later signed "not reportable" cancels a report not yet submitted** (a draft, a correction, or approved and not
  submitted): its state is "Cancelled: not reportable", its reason kept on the report and in the audit trail
  (`REPORT_CANCELLED`), its waiting approval tasks ended. It is never deleted; signing reportable again reopens it
  (`REPORT_REOPENED_BY_CONCLUSION`). A submitted report stays as recorded.
- **The status path:** Created from the decision tree · Mandatory fields complete · Sent for approval · Approved · PDF
  ready · Submitted by you · Acknowledged, from the existing states, snapshots, approval, submissions and evidence.
- **The mandatory-fields meter** comes from the form (its "must have before submission" fields, never a patient or
  reporter field): 17 on the 3500A, 14 on the MDAE form. "Show only missing", and each field says where its value
  comes from.
- **Send for approval stays disabled until every mandatory field is filled**, with the reason beside it ("2 mandatory
  fields missing"); the server refuses it too (422 `MANDATORY_FIELDS_MISSING`, naming the fields).
- **The PDF after approval:** "Generate the PDF" appears once approved: the form's field order, with the approval on
  its own last page (the existing worksheet export, stage 1's fonts). The server refuses a PDF or DOCX of a report not
  approved (409 `APPROVE_FIRST`).
- **The Reports tab:** List view (Open reports · Waiting for my approval · Submitted this month), six columns (Due ·
  Report · Status · Mandatory fields · Market · Open), cards on a phone, and the forms MDARIX prepares. A report opens
  on its own page in the record page's shape: the highlights (market, form, prepared by, due), the path, the form's
  fields in order, and the rail: the next step (one main button), the approval (with "Practice approval: in a pilot a
  colleague approves this" at its button when one approves alone), Generate the PDF, Who signs, and once "MDARIX never
  submits to an authority" with each authority's channel.
- On the new navigation, Complaints › Authority reports opens a report on that page and offers no working-draft
  download; the complaint page's Related opens its report.

### Fixed

- `test_business_permissions.py::test_a_viewer_is_refused_on_every_guarded_route` was red only when the tests ran with
  `MDARIX_FEATURE_SET=mvp`: the feature-set gate (since 13 Oct 2026) answers 404 for the parked routes before their
  guard runs. No route answered 2xx to a Viewer. The test now checks the guards themselves (the gate has its own tests).
- On a phone, a report's next step comes before its field list; on an approved report "Generate the PDF" is its one
  main button.
- On a phone, a list card's "What happened" (and an investigation's question) reads under its label at full width; it
  was squeezed into the card's second column.
- The complaint page's Related named a report by its form code ("FDA_3500A · draft"): it names the form.

### Sample numbers and labels that change

The sample data does not change. No deadline, trend figure, signal, Readiness value or record count changes.

| Where | Before | After |
|---|---|---|
| Decision trees tab | "One decision tree per market" (where the questions are today) | each market's tree, version, status, test result and a complaint's path |
| Reports tab | "Your reports are under Complaints › Reporting" | the list of reports with its three list views |
| Sample US report, SAMPLE-RV-09 | Accepted | Acknowledged (status path), state Accepted |
| Sample India report, SAMPLE-RV-10 | Draft: correction required | Mandatory fields complete (14 of 14), with "Draft: correction required" |
| SAMPLE-RV-11's US report, once its US conclusion is signed reportable (new) | — | Created from the decision tree, 8 of 17 mandatory fields (9 to fill) |
| Decision trees, the sample's US tree | — | Your version 2 · approved (the sample's own guide), 6 of 6 worked complaints pass; India: MDARIX starter, 3 of 3 |
| After a reportable US/India conclusion is signed (new navigation) | Home and Oversight: "United States (FDA): reportable, the report is not started"; Reports: Not started | "Form FDA 3500A worksheet (eMDR): draft" (the report exists); the next step "Complete the United States (FDA) report (draft)" |
| Complaint page, Related › Authority reports | United States (FDA) · FDA_3500A · draft | United States (FDA) · Form FDA 3500A worksheet (eMDR) · draft |
| Complaint page, Details | — | Decision path: one link per market |
| Decision trees guide line | One tree per market: the questions each complaint is walked through… | One tree per market. Each complaint is walked through it; a reportable outcome creates the report with its data. |
| Reports guide line | Every authority report: its mandatory fields, its approval and its PDF. | Created automatically when a decision tree concludes "reportable". You complete, approve and generate the PDF; you submit it through the authority's own channel. |

### Tests

- pytest: `tests/test_release_c3_0_10_75.py` (new, 20): signing reportable creates exactly one report, pre-filled with
  sources, and a draft creates none; Send for approval stays blocked until every mandatory field is filled; the PDF
  only after approval, and alone in a trial the practice label shows; a colleague approves a report someone else
  prepared (never the preparer); a "not reportable" re-sign cancels the unsubmitted report (approved, not submitted)
  with its reason and audit, and reportable reopens it; the sample's reports fit the path; the classic navigation
  keeps its rules and the refresh adds the report once (dry run, idempotent); the decision trees and a complaint's
  path; every state's place on the path; the approval on its own last page. Updated:
  `test_authority_reports_api.py` (its 0.10.58 lifecycle on the classic navigation),
  `test_flagship_walkthrough.py` (the report is created on signing; still 21 main buttons, 44 actions),
  `test_business_permissions.py` (the Viewer check).
- vitest: `releaseC3075.test.tsx` (new, 11).
- Screens at 1440 and 390 in `MDARIX-videos/site-0.10.75-review` (`owner/`: the trees for the US, India and EU / NI
  and SAMPLE-RV-11's path, the three report list views as Admin and as Regulatory Leader, the reports of RV-11
  (created), RV-06 (sent for approval), RV-09 (acknowledged) and RV-10 (correction), RV-11's Decision path and
  Related, the phone's complaint cards; `colleague/`: a locked Regulatory Leader's waiting list and approval;
  `approved/`: RV-06 approved, PDF ready; `classic/`: unchanged).

## [0.10.74] - 2026-11-03

On the trial maintenance line (`release/0.10`): part C2 of Release C, "List views and record pages", built to the
owner-approved design (its Complaints list, complaint record, Investigations and Records). It changes organizations on
the **new** navigation (`tenants.navigation = new`); the classic navigation keeps its screens. Pilots keep their
permissions; a pilot's Records also leads with the person's latest signed record.

**No migration.** The API and web images change. No operator step: `scripts/refresh_trial_story.py` has nothing new to
do (the sample does not change).

### Added: list views

- Every tab that lists records has one **List view** choice, the persona's own views first (the approved design's list)
  and every other view under **More views**: the persona narrows the first choice, never what the person may open.

  | Persona | Its list views on Complaints |
  |---|---|
  | Admin | All open complaints · Due this week · Second look · Reporting · Waiting for the reporter |
  | Quality Leader | All open complaints · Due this week · Past target · Second look |
  | Regulatory Leader | Reportability: decision needed · Authority reports · Legal clocks this week |
  | Complaint Handler | To triage · Calls to check · Second look · Waiting for the reporter |
  | Decision Maker | Waiting for my approval · Signed this month |

  A persona without a Complaints tab that reaches it by a link gets Admin's.
- Seven views are filters of the one complaint list, read on the server from the same dated items, reportability
  watch, open requests and signatures as the complaint page, Home and Oversight (`GET /api/v1/complaints?work=1&view=`:
  `open`, `due-week`, `legal-week`, `reportability`, `waiting-reporter`, `my-approval`, `signed-month`; an unknown
  view is refused, 422 `UNKNOWN_LIST_VIEW`). Each shows **six columns** (Urgency · What happened · Product, version,
  lot · Markets · Owner · Stage), **one row action** (Open) and **cards on a phone**, most urgent first ("Signed this
  month": newest first). Each says what it holds beside the choice.
  - Due this week: a deadline or target in the next seven days, not yet overdue (as Home counts it).
  - Legal clocks this week: a reporting deadline or report obligation in the next seven days, or already past.
  - Reportability: decision needed: a market whose reportability a person must still decide (the watch).
  - Waiting for the reporter: a question still open with the reporter or a partner.
  - Waiting for my approval: an authority report sent for approval that the person did not prepare; in a trial, their
    own too, as practice ("Practice approval: in a pilot a colleague approves this" stays at the approve button).
  - Signed this month: a market conclusion, disposition, report approval or ready to close signed since the first of
    the month in the organization's time zone.
- Stage 7's work queues (To triage, Calls to check, Due soon, Past target, Second look, Reporting, Authority reports,
  Communications, Investigations, Dismissed, All complaints) are views in the same choice and keep their own screens.
  Every former address still lands (`linkTable.json`: Complaints' views are its tabs).
- **Investigations** lists every investigation (Open investigations · Assigned to me · All investigations; Due ·
  Investigation · Product · Priority · Owner · Stage; Open). It opens on the list when no investigation is open; an
  investigation opens with "Investigations ›" to return. The Investigator, who has no Complaints tab, now reaches the
  list from their own tab. The list has its own address (`/app/investigations?step=All+investigations`).

### Changed: the record page

- **One complaint's page** in the approved design's shape:
  - "Complaints › SAMPLE-RV-11" to return to the list;
  - a **highlights panel**: the reference, product and version, what happened, the chips (harm, each market's
    deadline, its state), Owner, Markets, Lot and Also known as;
  - the **path**: the stage line (Triage · Market assessment · Investigation · Decision · Ready to close · Closed in the
    QMS) as chevrons, done, now, later or not needed;
  - **Details · Related · Activity**:
    - Details: what happened, harm, problem (with its IMDRF term), awareness, the status in the QMS and the service
      work; then each step with who signs it (open ones first), the owner, and Ready to close. Ready to close is
      revealed on request until it is the next step or signed, so the page has one main button;
    - Related: communications, market assessments, service work, investigation, authority reports and decision records,
      each in plain lines with one way to open it, then what was signed and its decision record (PDF);
    - Activity: the complaint's own audit events, newest first, in plain words, who and when; the record's received
      and awareness time last, marked "from the complaint record" (the sample was loaded without audit events).
      `GET /api/v1/oversight/events/{ref}/activity`; nothing but the time, the words, the person and the reason
      leaves the server.
  - a **right rail**: Next step (one main button), Legal clocks (a lane per market, its deadline in its own time zone,
    "Starter rules, for your consultant to confirm"), Who signs the next step (and "never the person who prepared it"
    where it applies) and the Service work.
  - Release A's short story and intake summary and Release B's inline triage are kept as they were.
  - The former sections' addresses open the section that holds them now: Summary and Decisions & actions on Details,
    Evidence on Related, History on Activity.
- **One investigation** has the same shape: highlights (the question, its product, the state, priority and due chips,
  Owner, Complaints in scope, Lots in scope, Blocking the decision), its four sections as the path with the next step's
  button, and the state changes beside them.

### Changed: Records

- Records leads with **the latest record the person signed**, for every organization, pilots included
  (`GET /api/v1/oversight/latest-signed`, from the signed approval records, not invalidated): what it is, when, the
  record it belongs to, its decision record to download and its page to open. In a trial, before the person signs
  anything, the short story's intake decision summary leads as before.
- After the short story is finished, its bar reads **"Story finished"** with "Back to the stories" (it read "Off the
  story's path" with "Resume SAMPLE-RV-11").

### Added: search on a phone

- At phone width the top bar shows a search icon that opens the same search (complaints, products, reports) as a bar
  under the top bar.

### Fixed

- `releaseB072.test.tsx` F2 read the source with its line endings and failed on a Windows (CRLF) checkout: it reads
  them as LF. No behaviour change.
- Font sizes on the design system's scale (`tokens.test.ts` failed on 0.10.73's Home: 11, 17, 22, 24, 26 and 30 px).

### Sample numbers and labels that change

The sample data does not change. No deadline, trend figure, signal, Oversight count, bell, Readiness value or record
count changes.

| Where | Before | After |
|---|---|---|
| Complaints, first view (new navigation) | To triage, for everyone | the persona's first: Admin and Quality Leader "All open complaints", Regulatory Leader "Reportability: decision needed", Complaint Handler "To triage", Decision Maker "Waiting for my approval" |
| Complaints, view chooser | a row of 9 view buttons | one "List view" choice, 18 views |
| Complaint page sections | Summary · Evidence · Decisions & actions · History | Details · Related · Activity |
| Complaint page header | "Needs attention · Owner · Due · Stage" and the next action button | highlights (Owner · Markets · Lot · Also known as), the path, and the rail's Next step |
| Complaint page, the stage list | "Stage by stage", revealed on request | the path, always shown |
| Complaint page, coding and record details | revealed on request | in Details |
| Investigations tab, no investigation open | "No investigation open · Open the investigations" | the list of investigations |
| Records, first card | the intake decision summary (trial, story finished) | the latest signed record, else the intake decision summary |
| Complaints' guide line | Choose a view: to triage, due soon, past target, reporting and more. | Choose a list view: your own views come first. |
| Investigations' guide line | One investigation in four sections: … | Every investigation in one list; each opens in four sections: … |
| Complaint page, triage as the next step | between the header and the sections | first in Details, beside the rail |
| Story bar after the short story, off its record | Off the story's path · Resume SAMPLE-RV-11 | Story finished · Back to the stories |

### Tests

- pytest: `tests/test_release_c2_0_10_74.py` (new, 6): for SAMPLE-RV-06, RV-08 and RV-11 the record page shows the
  same deadline, owner, stage and next step as the list views, Home's Oversight items and Oversight's event row, and
  Related's groups; each list view holds exactly the complaints its rule names, most urgent first, and an unknown view is
  refused; signing puts the complaint in "Signed this month", its Activity (plain words, newest first, nothing more) and
  the person's latest signed record; Activity and the latest record stay in their organization.
- vitest: `releaseC2074.test.tsx` (new, 11): each persona's views match the approved design, nothing lost; Complaints
  opens on the persona's first view; six columns, one action, the phone's card layout; the investigations list and its
  views; the record page's highlights, path, sections and rail agree with the work line; former addresses; Related and
  Activity; the investigation's highlights; Records' latest signed record (a pilot too); "Story finished"; the phone's
  search; the list's own address. Updated: `app/linkTable.test.ts`, `releaseB072.test.tsx`.
- Targeted pytest run (this release's tests, the complaint page and list, Oversight, business permissions, alembic drift,
  the migration chain, link targets, Releases A, B and C1, the flagship walk-through, free trial): 114 passed, 2 failed.
  Neither is this release's: `test_business_permissions.py::test_a_viewer_is_refused_on_every_guarded_route` fails the
  same way on 0.10.73 (nine routes answer 404 instead of 403, `POST /api/v1/regulatory/draft` first), and
  `test_complaint_page.py` (SAMPLE-RV-06) passed on its own rerun (a deadline crossing a state boundary during the
  11-minute run). vitest for the files touched: 33 files, 248 passed; tsc, ruff and prettier clean.
- Screens at 1440 and 390 in `MDARIX-videos/site-0.10.74-review` (`owner/`: each persona's Complaints, two list views,
  SAMPLE-RV-11, RV-06 and RV-08, Related, Activity, the investigations list and page, Records, the phone's search;
  `colleague/`: a locked Regulatory Leader; `signed/`: after a signed US conclusion, Records, Activity, Related and
  "Signed this month"; `classic/`: unchanged).

## [0.10.73] - 2026-11-03

On the trial maintenance line (`release/0.10`): part C1 of Release C, "The shell, personas and team", built to the
owner-approved design. Organizations on the **new** navigation (`tenants.navigation = new`, every trial approved since
0.10.71) get a new shell: a top bar with **Viewing as [persona]**, and a tab bar showing only that persona's
destinations. Organizations on the classic navigation keep their screens exactly as they were. Pilots keep their
permissions; a pilot user's tabs follow their real role.

**Migration `tr13viewpersona`** (after `tr12sampleservice`; `tr03pmssources` stays reserved). It is expand-only: one
nullable column, `auth_users.view_persona`. No existing row changes. On legacy dedicated organization databases, run
`scripts/add_workflow_tables_to_legacy_planes.py` (new step tr13). The API and web images change. **Operators:** run
`scripts/refresh_trial_story.py` (dry run first, then `--apply`) once after the upgrade. It changes the Free Trial
plan's description ("up to 3 users" to "up to 50 people") and its licensed-user limit (3 to 50). The sample data does
not change. New setting: `MDARIX_TRIAL_USER_CAP` (default 50; `docs/runbooks/ENVIRONMENT_VARIABLES.md`).

### Added: the shell on the new navigation

- **Top bar:** the MDARIX tile, the organization (in a trial: "Free trial · N days left"; it opens Getting started),
  **one search** across complaints, products and reports, **Viewing as [persona ▾]**, the bell, Help and the avatar.
  The avatar's menu holds Account, Settings, the admin console (customer administrators), Switch organization and Sign
  out. A phone shows the tile, the persona and the avatar; the tabs scroll sideways.
- **Tab bar:** Home, Complaints, Decision trees, Reports, Investigations, Trends, Records and Team, each persona showing
  its own (below). **My work is Home.** Decision trees (`/app/decision-trees`) and Reports (`/app/reports`) are new
  places. Until part C3 they say where the work is today: the reportability guides, and Complaints › Reporting.
  Reports says once that MDARIX prepares, gets approved and records, and never submits to an authority.
- **Every old address still lands** (`linkTable.json`). An address of a tab the persona does not show still opens: the
  persona narrows the bar, not what the server lets the person open. On the classic navigation, `/app/decision-trees`
  opens Complaints › Decision guides and `/app/reports` opens Complaints › Reports.
- A trial on the new navigation opens on **Home**, not on Getting started. The sample event card is on Admin's Home.
  Getting started stays one click away (the trial pill, Help, "More stories").

### Added: personas, "Viewing as"

| Persona | Tabs | Role behind it |
|---|---|---|
| Admin | all eight | the trial owner (role Leader, unchanged) |
| Quality Leader | Home, Complaints, Reports, Investigations, Trends, Records | Leader |
| Regulatory Leader | Home, Complaints, Decision trees, Reports, Records | Regulatory Reviewer |
| Complaint Handler | Home, Complaints | PMS / Signal Triage Lead |
| Investigator | Home, Investigations, Trends | Quality Investigator |
| Risk Reviewer | Home, Investigations, Records | Risk Reviewer |
| Decision Maker | Home, Complaints, Reports, Records | Authorized Decision Maker (Approver) |
| Executive | Home, Trends, Records | Viewer |

- **The persona changes what a person sees, never what they may sign.** Every route keeps its guard, and the persona
  never reaches the server as a permission. The menu says so: "Changes what you see, not what you may sign."
- **The trial owner's choice is kept on the server** (`auth_users.view_persona`). Their next sign-in, on any device,
  opens on it. `POST /api/v1/me/persona` (the trial owner only, audited as `PERSONA_VIEW_CHANGED`, with the role
  unchanged). Anyone else is refused with **403 `PERSONA_LOCKED`**.
- **An invited colleague's persona is their real role**, shown with a lock ("set by the trial owner"). A pilot user's
  persona follows their role (a customer administrator's is Admin).
- The session context gives `persona`, `persona_label`, `persona_locked`, `persona_tabs` and `persona_options`.
- The Regulatory Leader is a Regulatory Reviewer. That role already holds `regulatory.approve`, so the authority
  reports' DECIDERS rule (`require_any_permission(REGULATORY_REVIEW, REGULATORY_APPROVE)`) lets them approve. A report's
  approval still needs a second person: never its preparer (`standing`, unchanged).

### Added: Home per persona

- **Overdue · Due this week · At risk**, counted from the organization's own dated items (`/api/v1/oversight`, the
  persona's categories) and the trend check's rising groups.
- **Your next actions**, most urgent first, each with its reason, its owner and its deadline, opening its record.
- **One sentence per rising trend**, with its comparison basis.
- The Regulatory Leader's **legal clocks**, each market's deadline in its own time zone with a lane. The Executive's
  **readiness line** ("N of M inspection checks clear").
- Admin's Home (and the Quality Leader's) keeps Release A's **one-event card** with Release B's title and the short
  story's four steps, and "Resume SAMPLE-RV-11" while it is unfinished. All of My work (tasks, approvals, requests,
  queues, the team overview) stays below, revealed on request.

### Changed: the trial team

- **The 3-user limit is gone.** A trial has a **safety cap of 50 people** (`MDARIX_TRIAL_USER_CAP`). When the cap is
  reached, the owner is told so plainly: "Your trial has 50 people, its safety limit. Remove someone to invite
  another, or write to MDARIX support to raise it." (409 `TRIAL_USER_LIMIT_REACHED`, as before.)
- The invitation takes the colleague's name, work e-mail and **persona**, and **the persona sets the colleague's real
  role** (until now every colleague was a Leader). Admin is the owner's own (422 `PERSONA_NOT_FOR_COLLEAGUE`). A call
  with no persona keeps Leader, as before.
- The list shows each person's persona, locked for colleagues. The owner changes a colleague's persona, and with it
  their role, after a confirmation (`POST /api/v1/trial/team/{user_id}/persona`, owner only). Every assignment and
  change is audited as `TRIAL_PERSONA_ASSIGNED`, with the persona and role before and after.
- **Running trials:** colleagues invited before 0.10.73 keep the role Leader (the Quality Leader persona) until the
  owner changes their persona. Trial owners keep Leader. Nobody is made a Customer Administrator.
- Classic navigation: Getting started › Team offers the same persona choice, because the server gives the colleague
  that persona's role on either navigation.

### Sample numbers and labels that change

The sample data does not change. No deadline, trend figure, signal, Oversight count, bell, Readiness value or record
count changes.

| Where | Before | After |
|---|---|---|
| First screen of a trial on the new navigation | Getting started (the entrance), then My work | Home (Admin's: the sample event card) |
| Menu, new navigation | My work, Complaints, Trends, Records; Settings, Team, Account at the top right | tabs Home … Team per persona; Settings and Account in the avatar's menu |
| Guide paths, new navigation | My work › Team overview | Home › Team overview |
| Team panel's eyebrow | 2 of 3 users | 2 people · up to 50 |
| Invite button | Invite colleague | Send the invitation |
| Trial full | All 3 trial seats are in use… | Your trial has 50 people, its safety limit… |
| Sign-up and sign-in pages | up to 3 users and 5,000 uploaded rows | your whole team (up to 50 people) and 5,000 uploaded rows |
| Free Trial plan description | … up to 3 users. | … up to 50 people. |
| Trial status `limits.users`, team `limit` | 3 | 50 |
| Next steps, People | Up to 3 users | Up to 50 people, each with the persona you choose |

### Tests

- pytest: `tests/test_release_c1_0_10_73.py` (new, 8). The personas match the approved design, each persona is a real
  role. A fresh owner opens on Admin and the choice persists across sign-in, with the role and permissions unchanged
  and the change audited. A colleague's role follows the persona and they cannot change it (403), nor anyone's. A
  colleague invited without a persona keeps Leader. The owner's market sign route answers the same under all eight
  personas, and a View-only colleague is refused by the role until the owner gives them one that may sign. The 4th
  person is invited, the cap holds at its setting and is said plainly. The plan's refresh is idempotent. A pilot user
  is locked. Updated: `test_free_trial.py` and `test_trial_self_admin.py` (their full-trial paths use a cap of 3),
  `test_release_a_0_10_71.py` (the fresh sign-up opens on Admin), `test_business_permissions.py` (the new team route
  is a reviewed exemption), `test_free_trial.py`'s trials overview (a trial's user limit reads 50).
- Targeted pytest run (this release's tests, business permissions, alembic drift, the migration chain, free trial, the
  trial's self-administration, Releases A and B, link targets, e-mails): 109 passed. `scripts/refresh_trial_story.py`
  dry run on the test database names the plan's description and both entitlements' limit (3 -> 50).
- vitest: `releaseC1073.test.tsx` (new, 13). The tabs per persona, the shell for the owner and for a locked colleague,
  the classic navigation unchanged, the fresh trial on Home, the old addresses on the new shell, the switch, Home's
  rules, the team's persona. Updated: `app/linkTable.test.ts`, `app/newPathText.test.ts`, `app/clickPaths.test.ts`,
  `help/UserGuidePage.test.tsx`, `help/TrialGuidePage.test.tsx`.
- Screens at 1440 and 390 in `MDARIX-videos/site-0.10.73-review` (`owner/`: each persona's Home, the menus, search,
  Team, Decision trees, Reports; `colleague/`; `classic/`).

## [0.10.72] - 2026-11-02

On the trial maintenance line (`release/0.10`): Release B of the owner-approved "Simplicity and WoW" plan, "Show less,
by default": one obvious next action on each screen, every consequential open obligation in sight, the rest revealed
on request. No menu item or tab is added or moved. Organizations on the classic navigation keep their screens, except
the plain fixes marked below. Pilots are otherwise unchanged.

**No migration.** The API and web images change. **Operators:** run `scripts/refresh_trial_story.py` (dry run first,
then `--apply`) once after the upgrade: it gives SAMPLE-RV-11's problem code its IMDRF term and corrects the sample
guide's example text in running trials (below).

### Changed: the market assessment asks only for judgement (B1) — for the consultant to confirm

- The US and India assessments arrive with the **factual** answers the complaint record states, each with its source,
  for the person to **Confirm** or **Correct it**: did a death occur, each serious-injury part (the record says no
  serious injury), did the device malfunction; for India death and the serious criteria that mean a serious injury.
  **Causation, recurrence ("what if it recurs"), remedial action, "unexpected", hospitalisation, congenital anomaly
  and the market's conclusion are never pre-filled**, and the conclusion is no longer pre-selected: the suggestion is
  marked beside it. A field the record leaves empty suggests nothing: Unknown is never read as No. A serious injury on
  the record suggests no criterion (which one applies is a judgement). EU/NI and GB suggest nothing ("might have led
  to" is a judgement). Starter rules, for the consultant to confirm.
- Each answer keeps whether it was a **confirmed suggestion, a corrected suggestion or entered**, in the assessment's
  answers (`origin`, the suggested answer and its source): on the signed record's content, on the signed version
  ("Answers: 5 confirmed from the complaint record, 3 entered."), in the signature summary and in the audit trail
  (`answer_origins` on `COMPLAINT_MARKET_ASSESSMENT_SAVED` and `COMPLAINT_MARKET_CONCLUSION_SIGNED`).
- The training acknowledgements read in one line, "You have read: US guide v2, harm scale v1 · Read again", unless one
  is missing. Definitions (with "Why am I asked?" and the organization's own explanation), the full harm scale and the
  evidence ticks are behind **Show definition**, **Show scale** and **Show evidence**. The guide lock, the test matrix
  and the signature summary are unchanged.

### Changed: the investigation leads with what the decision rests on (B2)

- Summary opens on the **leading explanation, the evidence for and against it, and what blocks the decision**, each
  open item with its owner ("Investigation brief: waits for its quality review · Owner: A quality reviewer (not the
  author)"). The scope versions and the lot impact are revealed on request.
- One set of section controls: the progress line (the tabs repeated it).
- The empty parts of Decisions & actions fold into one line, "Not started yet: …"; the next step, the part a link
  asks for and a step that blocks the decision stay visible. An empty decision history, follow-ups and impact
  assessments say nothing until the decision is signed.
- The product, version, investigation and as-of selectors are behind **Change investigation** (on Trends: **Change
  product or version**).

### Changed: the complaint page (B3)

- **Triage is done on the page:** when the triage record is the next step, its panel is on the complaint page and
  stays there once saved. The next action reads "Complete the triage record" (it said "(on the triage list)").
- One action per "What needs attention" row: **Send to** a colleague is behind the row's **⋯**, shown only when a
  colleague may sign the step.
- The problem coding, awareness, QMS status and MDARIX ID are behind **Coding and record details**; the stage list
  behind **Stage by stage**. The legal clocks stay visible.

### Changed: My work (B4)

- **Your next step** says why it needs attention, its owner and its deadline. Below it, always visible: the reminders
  and escalations, and **every task due soon or overdue** with its deadline and one Open.
- Team numbers, and all my work (task views and filters, completed work, approvals, evidence requests, queues, team
  overview) are revealed on request; a link to a part of My work opens them.

### Changed: Trends (B5)

- The trend check leads with **one sentence per rising group** ("OrbitCare 300 Infusion Pump (Sample) Rev B: 9
  complaints against 1.0 expected (9.3×), lots 003, 004 and 005") and its comparison basis in one line, saying plainly
  "Units not imported: compared by calendar days" where lot quantities are missing. The tiles, every group, the
  grouping controls, the chart and the method are behind **All groups, the method and the chart**. The trend board
  lists each group's recent lots (`lots`).

### Changed: Records (B6)

- Once the short story reaches its intake decision summary, Records opens on **the work you just finished**: the
  intake decision summary of SAMPLE-RV-11, its decision record to **Download (PDF)**, and the summary to open and
  print. Inspection readiness, documents, decision and CAPA records, the audit trail, signature verification and
  exports are behind **All records**. With nothing just finished, Records opens as before.

### Fixed: the short story's two correctness faults (F1, F2)

- **F1:** "Confirm the route" saved the triage severity Negligible with no way to change it. Step 2 now shows "No harm
  was reported" as the reporter's statement and "Effect on treatment: Unknown: asked of the hospital in step 3"; the
  triage severity is an editable field with its proposal and basis, and nothing is saved until the person ticks "I
  confirm the triage severity" (or chooses another level). The step lists exactly what the click records.
- **F2:** step 3 took any later request with an owner and a reply date (a "When can the device be collected?" completed
  it), and the summary always said "Not known until the hospital answers". Step 3 is now the request the screen
  recorded, kept with the story (`POST /api/v1/trial/short-story/marks` `{"step": "question", "request_id": …}`, refused
  `409 NOT_THE_QUESTION` otherwise; a trial recorded before 0.10.72 is read by the question's own wording). The
  consequence follows that request: open, "Not known until the hospital answers"; answered, the answer and its date
  with "Reassess each market's answers with it"; closed unanswered, still not known.

### Fixed and added: the leftovers (addenda)

- The investigation's scope names complaints and lots by **your references** (a long list reads "14 complaints ·
  show") and hides empty lines (no more "None" under Markets, Failure modes, Period, Objectives). Plain fix: classic too.
- **One number per thing:** the report list's "24 filled" beside a meter of "16 from your records" now both read "16
  from your records · 8 entered"; the trend check's "the 2 groups checked" beside a "Groups checked 6" tile now says
  "assessed".
- **The same evidence listed twice**, and once as both supporting and contradicting, in a Decision Brief: the root
  cause was the brief merging the case's own judgement with every hypothesis's links. A brief now lists the evidence
  for and against the **leading** explanation, each piece once; an alternative's links stay on the alternative. Briefs
  composed before keep their stored content (versioned, hashed); the investigation's Summary reads them by the same rule.
- **Dates:** "1 Nov 2026" and "1 Nov 2026, 22:54" whatever the browser's language, as stage 5's rule says (an en-US
  browser showed "Nov 1, 2026, 10:54 PM" beside "Tue 1 Dec 2026, 23:59 IST").
- The organization's name in the top bar is in full from 1280 px; from 1280 to 1599 px the top-right buttons (Settings,
  Team, Account, Sign out) show their icons, their names kept as tooltips and for screen readers.
- The market tab reads "EU and Northern Ireland" (the label map), not "EU/NI"; an extra question reads "Extra 1".
- Sample wording: the guide's example for question 2c no longer starts "Sample examples:" ("Your examples: Sample
  examples: …"); the worksheet's front-page field reads "Manufacturer report number" ("Mfr report # Manufacturer report
  number"). Running trials: through the refresh, the published guide version's approval re-recorded on its new
  fingerprint. The sample's approved worksheet snapshots stay as frozen.
- The first card reads "A hospital sent a monitor for service. Should Quality review this too?". The sample is
  unchanged.
- On My work, while "Resume SAMPLE-RV-11" shows, "Your next step" is a secondary button: one main button.
- **Sample only on the approval:** the platform admin's approval dialog has a "Sample only" checkbox;
  `POST /api/v1/platform-admin/trial-requests/{id}/approve` takes `{"sample_only": true}` (no body: as before). It
  sets `tenants.sample_only` at creation; `TRIAL_REQUEST_APPROVED` records it.
- SAMPLE-RV-11's problem code SPO2_READING_HIGH maps to IMDRF Annex A **A0908** "Incorrect, Inadequate or Imprecise
  Result or Readings", the way the other sample codes are mapped (it showed raw).
- Once the short story's intake decision summary is reached it leads the complaint page, and the rest folds under
  **The full complaint record**.
- "Continue the full evaluation" counts its progress from SAMPLE-RV-11's own checklist and records (the same server
  response as the short story, `full_evaluation`), not from the screen that is open; off the record the bar still says
  "Off the story's path".

### The flagship walk-through

From the entrance to ready to close: **54 actions before, 44 now** (each main button, each answer entered: choose it
and type its rationale, two actions; each suggestion confirmed: one). 22 main buttons became 21 (triage on the
page); the US and India answers took 32 actions and now take 23 (9 factual answers confirmed, 7 judgement answers
entered).

### Sample numbers and labels that change

No deadline, trend figure, signal, Oversight count, bell, Readiness value or record count changes.

| Where | Before | After |
|---|---|---|
| Entrance card | A hospital asked for recalibration. Should Quality review this too? | A hospital sent a monitor for service. Should Quality review this too? |
| RV-11 market assessments | every answer empty | US 1, 2a, 2b, 2c, 4 and India 2a, 2b, 2d, 2f suggested from the record, to confirm |
| RV-11 conclusion radio | pre-selected to the suggestion | not selected |
| Market tab | EU/NI | EU and Northern Ireland |
| Extra US question | 1. | Extra 1. |
| RV-11 step 2 | Harm so far: Negligible: no harm was reported… | The reporter says "No harm was reported" · Effect on treatment: Unknown · Triage severity: Negligible (proposed, to confirm) |
| RV-11 next action | Complete the triage record (on the triage list) | Complete the triage record |
| RV-11 problem code | SPO2_READING_HIGH (raw) | mapped to A0908 |
| Sample guide, 2c examples | Sample examples: a cut closed with sutures… | A cut closed with sutures… |
| Worksheet front page | Mfr report # Manufacturer report number | Manufacturer report number |
| Report list line | e.g. 24 filled | 16 from your records · 8 entered |
| Trend check headline | Results allow for the 2 groups checked. | Results allow for the 2 groups assessed. |
| Trend check lead | (none) | OrbitCare 300 Infusion Pump (Sample) Rev B: 9 complaints against 1.0 expected (9.3×), lots 003, 004 and 005 |
| INV-001 scope | CMP000017, CMP000013, … (14 pills); LOT000003, LOT000004; None lines | 14 complaints · show (your references); SAMPLE-ORBIT-300-LOT-003, -004; no empty lines |
| INV-001 brief (new trials) | supporting 4 entries (EVD000001, EVD000002 twice each), contradicting 1 (EVD000002) | supporting 2, contradicting 0 |
| Dates (en-US browser) | Nov 1, 2026, 10:54 PM | 1 Nov 2026, 22:54 |

### Tests

- pytest: `tests/test_release_b_0_10_72.py` (new): the record's facts only, never a judgement question, never Unknown →
  No, confirmed vs corrected recorded; F2 (an unrelated request, the question open, the question answered) and the
  full evaluation's progress; the trend's lots and its one count; sample only on the approval; the sample corrections
  and the refresh (dry run, apply, idempotent, the guide's approval re-recorded). `test_flagship_walkthrough.py`: the
  walk with the record's suggestions confirmed, origins on the signed record and in the audit trail, the action count
  (44, below 54). `test_decision_brief_unit.py`: evidence for and against the leading explanation, each once.
- vitest: `releaseB072.test.tsx`, `releaseB072Screens.test.tsx` (new: each screen's default render, without its
  revealed parts and with its required ones), `marketAssessment.test.tsx`, `releaseA071.test.tsx` (F1, the full
  evaluation's bar), `app/dates.test.ts`, `scopeModel.test.ts`, `authorityReports.test.tsx`, `signalAi.test.tsx`,
  `entrance.test.tsx`.
- Screens at 1440 and 390, before and after, in `MDARIX-videos/site-0.10.72-review` (`before/`, `after/`).

## [0.10.71] - 2026-11-02

On the trial maintenance line (`release/0.10`): Release A of the owner-approved "Simplicity and WoW" plan, "The first
five minutes": one event, one decision, one next action. Pilots are unchanged except the visible release number.

**Migration `tr12sampleservice`** (after `tr11navigation`; `tr03pmssources` stays reserved). It is expand-only: it adds
`tenants.sample_only` (default false) and four nullable columns on `complaints` for the linked service work
(`service_reference`, `service_owner`, `service_status`, `service_status_at`). No existing row changes; the complaint
columns go with the complaint, so retention, sample removal and the purge already take them. On legacy dedicated
organization databases, run `scripts/add_workflow_tables_to_legacy_planes.py` (new step tr12). The API and web images
change. **Operators:** run `scripts/refresh_trial_story.py` (dry run first, then `--apply`) once after the upgrade: it
links SAMPLE-RV-11's service work in running trials.

### Changed: a new trial starts on the new navigation (A1)

- A free trial approved from now on is created on the new navigation (trial provisioning sets it; the column's default
  stays classic). Every existing organization keeps its navigation; pilots are unchanged. Tenant 360 still switches
  either way. A fresh sign-up (request, approval, activation e-mail, password, authenticator) lands on the new first
  screen with nobody switching anything.

### Added: sample-only trials (A2)

- **Tenant 360 › Edit details › Sample only** (platform administrators, with a reason, audited as `TENANT_UPDATED`), for
  an event or judge trial. While it is on, every route that brings records in answers **403 `SAMPLE_ONLY_TRIAL`**: "This
  evaluation uses the sample only. To try your own data, discuss a pilot." (the check and the import, every template
  including distribution, a set-aside row's fix and re-process, and the trial's `/trial/imports` aliases). The screens
  hide every upload and import action (the entrance, the Complaints header, Getting started, Help, Settings › Import
  templates) and offer **Discuss a pilot** (Next steps, from trial to pilot) instead.
- A normal trial keeps its upload under **Help › Try your own data**, no longer on the entrance or the Complaints header.
  A pilot keeps "Import your data" on the Complaints header.

### Added: the release number (A7)

- **Help › About** reads "MDARIX release v0.10.71". **`GET /health/version`** answers `{"release": "v0.10.71"}`, with no
  session and nothing else, so anyone can confirm the deployed build. `/health/live` is unchanged.

### Added: a complaint's linked service work (A5)

- On a complaint: the service work's reference in your service system (free text, such as the service ticket ID), its
  owner and its status (open, in progress, complete), with the date; audited as `COMPLAINT_SERVICE_RECORDED`. When the
  service is complete the complaint's header reads **"Service complete · Quality assessment open"**, with the quality
  owner and the next action. Completing the service never closes or advances the complaint, its market assessments or
  its readiness. Not a service-ticket system: no scheduling, parts or technicians.

### Changed: the first screen is one event (A3)

- A trial on the new navigation opens on one card: **"A hospital asked for recalibration. Should Quality review this
  too?"**, SAMPLE-RV-11's reporter words, **Review this sample event**, "Fictional manufacturer · Sample data only",
  4 steps. The other stories are under **More stories**, "Restart the sample story" under **More**; the
  inspection-readiness numbers left the entrance (they stay on the manager's My work).
- **No time claims anywhere:** "About 5 minutes" and "five-minute" are gone, and the free trial user guide's step times
  too, until stage 9 measures them. Step counts only.
- Every story starts on a named record: "A complaint just arrived" on SAMPLE-URG-01's triage panel, "Is a problem
  rising?" on the trend check for OrbitCare 300, the full evaluation on SAMPLE-RV-11's page.
- A returning person with unfinished story work sees **"Resume SAMPLE-RV-11 · step N of 4"** first, on the entrance and
  on My work.

### Added: the short story, ending in the intake decision summary (A4)

On SAMPLE-RV-11's page, four steps:

| Step | Screen | Main button | The saved action that completes it |
|---|---|---|---|
| 1 Read the call | Complaint page: the reporter's words, the phrases that make it a possible complaint marked, the known facts | Decide the route | The person's mark "read" (or a later step done) |
| 2 Decide the route | Complaint page: "Complaint, with linked service work", the fact it rests on, the complaint and service owners | Confirm the route | The triage record completed, and the service work's owner named |
| 3 Name the open question | Complaint page: the one question to the hospital, owner, reply date | Record the question | A request in the communications log with owner and reply date |
| 4 Intake decision summary | Complaint page: route, source fact, open question, service, "Market assessments (US, India): still open" with deadlines, who acts next, who prepared, may approve, approved; Print or save as PDF | Continue the full evaluation | The person's mark "summary", once steps 2 and 3 exist |

- **Progress comes from saved actions, never the screen.** Steps 2 and 3 are the organization's records; steps 1 and 4
  are the person's own marks, kept per person and organization on the server (the trial's request, tied to this
  SAMPLE-RV-11, so "Restart the sample story" starts them again). Refresh, another device and "Resume SAMPLE-RV-11" all
  return to the same step. New: `GET /api/v1/trial/short-story`, `POST /api/v1/trial/short-story/marks` (trial only).
- The story bar reads "Step N of 4: …" from the server, or "Off the story's path" with **Resume SAMPLE-RV-11**.
- "Unknown" stays unknown: the consequence reads "Not known until the hospital answers".

### Changed: separation of duties, shown honestly (A6)

- Where a solo trial owner approves their own practice work (a report snapshot, a decision guide version), the button
  says **"Practice approval: in a pilot a colleague approves this."**
- The intake decision summary and the complaint's decision record name **who prepared, who may approve and who
  approved** (beside the record: its fingerprint is unchanged).

### Sample numbers and labels that change

No deadline, trend figure, signal, Oversight count, bell, Readiness value or record count changes.

| Where | Before | After |
|---|---|---|
| A new trial's navigation | classic (switched in Tenant 360) | new |
| SAMPLE-RV-11, service work | none | In progress since its awareness · SVC-24-1107 (sample service ticket) · owner not named yet |
| Complaint page › Summary | (no line) | Service work: … or "No service work linked." |
| Entrance heading | Pick a five-minute story | A hospital asked for recalibration. Should Quality review this too? |
| Entrance tiles | 4 tiles, "About 5 minutes · 3/4/7 steps", own export "optional" | 1 event card (4 steps); More stories: 3 tiles, "3 steps", "4 steps", "7 steps"; no own-export tile |
| Entrance readiness numbers | Inspection readiness on the sample (4 numbers) | not on the entrance |
| Story 1 lede, start | An urgent call from a hospital…; the triage list | SAMPLE-URG-01, an urgent call from a hospital…; SAMPLE-URG-01's triage panel |
| Story 2 start | Trend check | Trend check on OrbitCare 300 |
| Story 3 lede | A PulseWatch 410 read SpO2 too high; nobody was harmed. Each market's questions, its clock and the report. | The full evaluation of SAMPLE-RV-11: each market's questions, its clock, the report, the decision and ready to close. |
| My work link | The five-minute stories: start one on the sample | The sample event and its stories |
| Menu line of Getting started | Five-minute stories on the sample | The sample event and its stories |
| Help (trial, new navigation) | Getting started and import templates | Try your own data (sample-only: Discuss a pilot); About · MDARIX release v0.10.71 |
| Complaints header (trial) | Log a call · Import your data | Log a call |
| Free trial user guide steps | 3 minutes, 5 minutes, 2 minutes, 45 to 60 minutes, 30 minutes, 3 minutes, 2 minutes | no times |

### Tests

- pytest: `tests/test_release_a_0_10_71.py` (new, 11): a fresh sign-up through the public flow (activation e-mail from a
  test mail sink, the authenticator) reaches the new navigation with no `TENANT_UPDATED`; existing organizations keep
  theirs; every import route carries the refusal; a sample-only trial is refused in plain words and audited, a normal
  one is not; completing the service leaves the complaint as it was; the refresh links RV-11's service once; the short
  story walked by its saved actions; each person's own marks; the practice line; the decision record's people.
  `test_business_permissions.py`: `/health/version` public and version only; the short story's marks a reviewed
  exemption. `test_link_targets.py`: a new trial starts on the new navigation.
- vitest: `releaseA071.test.tsx` (new), `entrance.test.tsx` (rewritten).
- Targeted pytest run (this release's tests, business permissions, alembic drift, the migration chain, free trial,
  the flagship walk-through, the complaint page, link targets, the sample story's days, oversight, the import paths,
  the production smoke test, site info): 135 passed.
- Screens at 1440 and 390 in `MDARIX-videos/site-0.10.71-review` (`walk1440/`, `walk390/`: the whole short story;
  `screens/`, `sample/`, `signup/`: the fresh sign-up on the local stack).

## [0.10.70] - 2026-11-02

On the trial maintenance line (`release/0.10`): "Polish before proof", the owner-approved round that fixes what stage 8
left before stage 9 starts. It applies to both navigations unless it says "new navigation".

No migration. The API and web images change. **Operators:** run `scripts/refresh_trial_story.py` (dry run first, then
`--apply`) once after the upgrade: it signs SAMPLE-RV-09's ready to close again in running trials (below).

### Fixed: the disposition's words and the escalation triggers (item 1)

- The disposition says "investigation", one word per thing: "Why the investigation is needed", "Escalate: open an
  investigation", "No open investigation holds…", "Known issue, linked to an open investigation". A branch closed by a
  met trigger reads "Closed: a trigger is met" (it read "Refused").
- A met trigger shows its name ("Reportable outcome", "New failure mode"), not its code (REPORTABLE,
  NEW_FAILURE_MODE), on the disposition and its signed version. Readiness's dispositions check names them in words
  ("Escalated: reportable outcome, new failure mode"). The triggers' facts and definitions say "investigation" and
  "trend" ("Open trend … no open investigation covers it"); the recurrence trigger is "Recurrence no investigation
  covers".
- An escalated investigation's question reads "… Escalated from complaint SAMPLE-RV-11 by the triggers reportable
  outcome, new failure mode." (it read "(escalated: trigger met: reportable outcome; new failure mode)").
- The complaint page's next step for an escalated complaint is "Sign the investigation's decision" ("… on the case").

### Changed: a problem code reads by its IMDRF term (item 2)

- The IMDRF term is the label and the customer's own code the small detail: "Infusion or Flow Problem; Protective
  Measures Problem · IMDRF A14, A16 · your code UNDER_INFUSION_NO_ALARM". The code is never altered or dropped; a code
  with no approved IMDRF link shows as it is, "your code; no IMDRF term mapped yet". One component
  (`sections/ProblemCode.tsx`) for the complaint list, the complaint page, the disposition, the second look, the
  problem-code filter and the authorised-representative preview.

### Fixed: one ID per complaint (item 3)

- A drawer, a toast and a card name a complaint by one ID, its own reference ("SAMPLE-RV-11: assess per market"; it read
  "CMP000038 (SAMPLE-RV-11)"); the MDARIX ID is under "Also known as" (the market assessment, the second look and the
  reportability watch cards, which showed "CMP000029 · Source ID SAMPLE-RV-01"). A disposition opened by its address
  names its complaint (it said "Complaint: disposition").

### Fixed: a finished sample event asked for work (item 4)

- **Root cause: the sample's seeding.** SAMPLE-RV-09's ready to close was signed "checklist clear" over an empty
  checklist, although its decision is not in MDARIX, and dated before its own US conclusion. So the event asked "Sign
  the disposition" and its checklist read as changed since signing. It is now signed as the product records it: with
  its one open item and the reason ("Decided in our QMS: the investigation and its decision are recorded there (sample
  QMS-INV-0909)"), the day after its US report was accepted.
- **Next-step rule:** an event closed in the QMS after its ready to close was signed, whose checklist is as it was
  signed, asks for no next step and has no current stage ("Closed in the QMS"); any change since signing asks again.
  Its header reads "Nothing: 1 item was signed open, with a reason".
- Every other sample record was checked: the closed-before-ready records (RV-01, RV-03 to RV-05 and the older closed
  records) keep their open items, as the readiness story intends; the OrbitCare complaints in SAMPLE-INV-001's scope
  asked "Sign the disposition" while their stage read "Investigation": their next step is now "Sign the investigation's
  decision", on that investigation. RT-01 to RT-05 are open and unchanged; RT-03 is ready to sign.

### Changed: one main button per drawer (item 5)

- On the new navigation, a drawer that ends with the complaint's next step has that step as its one main button: the
  market assessment's "Open the report worksheet" is secondary. When the next step is the drawer's own work (the
  assessment, the disposition, the report, the investigation's decision), it says so ("…: here, above.") instead of a
  second main button. On the investigation page, the progress line's "Next" is the main button; the state changes
  ("Put on hold") and the sections' other buttons read as secondary. Classic keeps its buttons.

### Fixed: the top bar on one line (item 6)

- At a computer's width the name and the role sit on one line, the role shortened ("Asha Quality · Leader"), the
  whole role in the tooltip; the "Sample data" chip and the trial badge no longer wrap. At 390 px the menu of stage 7
  is unchanged.

### Fixed: the story bar on another record (item 7)

- The story bar counts a step only on the story's own record: the flagship's complaint and its escalated
  investigation, SAMPLE-INV-001 for "Is a problem rising?". Elsewhere (SAMPLE-RV-06, INV000001 during the flagship) it
  reads "Off the story's path" with **Back to the story**, on every screen. After ready to close is signed, the
  receipt in History is still step 7.

### Fixed: the flagship's investigation context (items 9 and 10)

- Opening an investigation (a next step, a task, a link, the saved context) shows it on its own product version, the
  one its complaints carry: the flagship's escalated investigation is PulseWatch 410 **Rev A** (it read Rev B, the
  product's latest, on every route). The product's investigation list carries each investigation's version.
- An investigation opened a moment ago that is not yet in the product's list is read again, never replaced by the
  first in the list; meanwhile the page says "Opening the investigation…" (it showed a header with "No question
  recorded", "No owner recorded" and "No due date", and the context bar the first investigation).
- Wherever the India assessment of a US complaint appears (its market tab, the decision record), one sentence says
  why: "Assessed because your procedure asks every market where this device is sold to be assessed." marked "Starter
  wording, for your consultant to confirm." The complaint's Markets field stays United States.

### Fixed: what the stage 8 screenshots showed (item 8)

- **One word per thing:** "case" reads "investigation" and "signal" reads "trend" on the disposition and its board
  ("Open, in no investigation"; the tile "Escalated to an investigation"), the complaint page's step ("Escalated to an
  investigation: its decision is not signed"), the investigation's evidence count, documents line, decision note and
  Unknowns note, the lot impact suggestion ("2 of the investigation's 2 lots share it"), Readiness ("Trends waiting
  past their triage date"; "open in no trend or investigation"; "decided trends"; "in no investigation"; "escalations
  to an investigation") and the trend check's footnote.
- **No codes:** the market assessment numbers its questions "1.", "2a." (it read "US1.", "US2A."), names versions in
  words ("guide your version 2 · scale MDARIX starter, version 1"; it read "US-v2 · scale-starter-1"), also in its
  training heading and its sign hints ("Answer question 5"); the investigation's history names record kinds in words
  ("Investigation scope", "Decision brief version", "Workflow task"; they read "Investigationscope").
- **Doubled words and brackets:** a role after a name never nests brackets ("Asha Quality (Leader, Quality
  Manager)"); "All 1 piece of evidence are reviewed" reads "The piece of evidence is reviewed" (and the hypothesis);
  a worksheet value's source reads "From an initial report" ("From An …").
- **What is open, in words:** the complaint page's "Needs attention" says what is missing ("3 open: On the triage
  list: its triage record is not complete"; it read "3 open: Triage is complete"). The stage line shows
  "Investigation" as later, not "not needed", until the decision says whether one is needed (it read "Investigation:
  not needed" on a serious injury before any disposition).
- **Never claims more than it has read:** the investigation's progress line says "Reading where this investigation
  stands…" until its steps are read (it read "Every step is done: the decision is signed" on an investigation opened
  a moment ago); a loading panel says "Reading…" (it was an empty grey box: the decision panels load as they scroll
  into view; their data is there within a second).
- **One main button** (see item 5): also a disposition or an assessment not signed yet keeps its own Sign as the main
  button, with the next step secondary; the report's optional "Complete the obligation" and the complaint page's
  "Sign ready to close" header button are secondary where the form's own button is on screen.

### Sample numbers and labels that change

No deadline, trend figure, signal or record count changes.

| Where | Before | After |
|---|---|---|
| Disposition, question 1 | Why the case is needed | Why the investigation is needed |
| Disposition, trigger chips | REPORTABLE, NEW_FAILURE_MODE | Reportable outcome, New failure mode |
| Disposition, branches closed by a trigger | Refused: a trigger is met | Closed: a trigger is met |
| Disposition, other words | open a case; no open case holds…; linked to an open case; Link to the open case | open an investigation; no open investigation holds…; linked to an open investigation; Link to the open investigation |
| Trigger facts and definitions | Open signal … no open case covers it | Open trend … no open investigation covers it |
| Recurrence trigger | Recurrence no case covers | Recurrence no investigation covers |
| Escalated investigation's question | … (escalated: trigger met: reportable outcome; new failure mode). | … by the triggers reportable outcome, new failure mode. |
| Complaint page, escalated complaint's step | Sign the investigation decision on the case | Sign the investigation's decision |
| SAMPLE-RV-09 | next "Sign the disposition", stage Decision, "1 open: The decision is signed", signed Sep 22 "checklist clear" | no next step, stage "Closed in the QMS", "Nothing: 1 item was signed open, with a reason", signed Oct 21 (the day after its report's acceptance) "signed with items still open" with its reason |
| SAMPLE-ORBIT-300-CMP-005 to -018 (in SAMPLE-INV-001) | Sign the disposition | Sign the investigation's decision |
| Stage line before a decision (RV-06, RV-11 and others) | Investigation: not needed | Investigation (later) |
| Problem codes | UNDER_INFUSION_NO_ALARM · IMDRF A14 …; Problem code: SPO2_DROPOUT_HARM | Infusion or Flow Problem; Protective Measures Problem · IMDRF A14, A16 · your code UNDER_INFUSION_NO_ALARM; Problem: SPO2_DROPOUT_HARM · your code; no IMDRF term mapped yet |
| Assessment drawer title | CMP000038 (SAMPLE-RV-11): assess per market | SAMPLE-RV-11: assess per market (Also known as CMP000038) |
| Second look and watch cards | CMP000029 · Source ID SAMPLE-RV-01 | SAMPLE-RV-01 (Also known as CMP000029) |
| Readiness labels | Signals waiting past their triage date; open in no signal or case; decided signals … with no signal; in no case; escalations to a case; no open case covers | Trends waiting past their triage date; open in no trend or investigation; decided trends … with no trend to review; in no investigation; escalations to an investigation; no open investigation covers |
| Lot impact suggestion | 2 of the case's 2 lots share it | 2 of the investigation's 2 lots share it |
| Top bar | Asha Quality / Leader (Quality Manager) on 4 lines | Asha Quality · Leader, one line |

Every Readiness value, Oversight count (items, overdue, due soon), the bell and My work are the same on a fresh
trial before and after (measured on both builds).

### Tests

- pytest: `tests/test_polish_0_10_70.py` (new, 7: the triggers in words, the disposition's words, a new failure
  mode's fact, history kinds, the second look's problem-code value, the stage line, a finished event);
  `tests/test_flagship_walkthrough.py` (+2 tests and new checks: RV-09 finished and its re-record by the refresh, an
  OrbitCare complaint decided in its investigation, the escalated investigation's question, owner, due date and Rev A
  in the product's list, Markets stays US, Readiness in words). Updated wording: `test_complaint_disposition_rules.py`,
  `test_complaint_disposition_api.py`, `test_lot_impact_api.py`, `test_sample_story_days.py` (the stage is "later").
- vitest: `polish070.test.tsx` and `nextStepButtons.test.tsx` (new); updated `disposition.test.tsx`,
  `marketAssessment.test.tsx`, `complaints.test.tsx`, `complaintReview.test.ts`, `entrance.test.tsx`,
  `ImportReports.test.tsx`, `labels.test.ts`, `lotImpact.test.tsx`.
- Screens at 1440 and 390 in `MDARIX-videos/site-0.10.70-review` (`new/`, `classic/`, `walkthrough/`), and every
  route into the flagship's investigation (`routes-before/` on 0.10.69, `routes-after/`).

## [0.10.69] - 2026-11-02

On the trial maintenance line (`release/0.10`): stage 8 of the quality plan, "The investigation in 4 sections, the
five-minute entrance and the wow screens". It applies to organizations on the new navigation (`tenants.navigation =
new`); classic organizations keep today's screens, except the words and fixes said below.

No migration. The API and web images change. The sample data does not change, so `scripts/refresh_trial_story.py`
has nothing new to do; the story's chapter texts are code and change with the image.

### Changed: one investigation in four sections (8.1)

- On the new navigation an investigation is **Summary** (question, scope, lot impact, state), **Evidence** (its
  evidence and reviews, hypotheses, open unknowns, failure chain, the analysis workspace), **Decisions & actions**
  (risk and regulatory reviews, the Decision Brief, the decision, the CAPA recorded for your QMS, what follows the
  decision) and **History** (the record to download, the timeline, signatures and brief fingerprints), under **one
  progress line** with the next step as the main button. It had eleven tabs and a nine-step stepper.
- Every former tab's address opens its section and part (`linkTable.json`): links in e-mails, tasks and bookmarks
  keep working. Classic keeps its tabs.
- **24 investigation drawers have their own address** (`panel=<kind>:<id>`): Back closes one; refresh, a new tab or a
  link reopens it.
- **Words:** inside the investigation "case" reads "investigation", and in the trend inbox "signal" reads "trend".
  "Gaps" and "Unknowns" are one word, **Unknowns** (the readiness step, the check, the analysis tile). Tab names and
  signed or stored text are unchanged.
- **Path f** (from a trend to a signed decision): 10 steps (11 + 1 before).

### Added: "Why am I asked?" and the summary before signing (8.2, 8.3)

- One line under each question and step with its reason and clause: the complaint page's steps and ready to close,
  the investigation's steps, the first-contact questions, the triage record, the disposition's four questions. A
  market's question gives its decision guide's own note and locked clause.
- Before each signature: **what you sign**, then **what it rests on** (answers and guide version, harm level and
  clock; the worksheet's fields from your records and the snapshot's fingerprint; the brief and its fingerprint; the
  checklist, markets and the decision record's fingerprint), then "You decide and sign. MDARIX prepared this from your
  records; it never decides or submits." once.

### Added: the five-minute entrance (8.4)

- A trial on the new navigation opens on four tiles, each about five minutes: **"A complaint just arrived: what
  now?"**, **"Is a problem rising?"** (OrbitCare 300 Rev B), **"Is this reportable, and by when, in the US and India?"**
  (SAMPLE-RV-11) and **"Try it on your own export"** (optional). A tile opens its story on its record; a **story bar**
  shows the step and the way back. The four inspection-readiness numbers and "Restart the sample story" are on the
  entrance; the ten chapters are under "Explore all capabilities", your own data outside the count.
- A returning person (the entrance seen in this browser) starts on My work, with "The five-minute stories" one click
  away.

### Added: the eight wow screens (8.5)

In the design system's tokens; numbers in words beside every bar and marker, never colour alone; a table view beside
each chart. (1) The hidden complaint revealed (Second look). (2) Legal clocks, one lane per market, on the complaint
page. (3) The trend per unit against the earlier average (Trends › Trend check). (4) Lot impact as bars by lot and
by country. (5) The report worksheet's sticky "N of M fields filled from your records" meter, "Show only missing",
and "From <source>" under each value. (6) The decision record as a receipt. (7) The readiness ring: a state mark on
every station; "Signals triaged" reads "Trends triaged" (the weekly digest too). (8) The entrance tiles.

### Changed: nothing typed twice (8.6)

- The market assessment's harm level starts from the **triage record's severity** when the QMS severity maps to none
  ("From the triage record"); it was asked again for each market.
- Form FDA 3500A **G8** is the front page's manufacturer report number; it was typed twice.
- The disposition proposes the **user type** from the worksheet's report source (G2), with its source.
- An escalated complaint's investigation question carries the complaint's words and the trigger in words (it carried
  codes such as `NEW_FAILURE_MODE`), the **complaint's own record is linked as the investigation's first evidence**,
  and the Decision Brief's problem statement starts as the question with AI off too (it started empty).

### Changed: the next step, always (8.7)

- The market assessment, the report worksheet, the disposition and an investigation opened from one complaint end
  with that complaint's next action as the main button and its page one click away. A triaged complaint opens its
  page. In the flagship story, "Assess India (CDSCO) too" follows the signed US conclusion.
- **Fixed:** an escalated complaint's "Sign the investigation decision on the case" opened the list of
  investigations; it now opens that investigation's decision.
- **Fixed:** "Assess the United States (FDA) market" (and any market assessment link) opened Complaints › Reporting on
  the complaint's reports, with no assessment in sight; it now opens the complaint's assessment.
- The investigation's next step never names the analysis (it only warns in the brief's gate; with AI off it stays
  "not started"); none is named once the decision is signed.

### Changed (separate commit, for the owner to approve): Oversight lists an unassessed market's provisional clock

- Oversight lists the reportability watch's provisional deadline of a market not assessed yet (SAMPLE-RV-06 and
  SAMPLE-RV-11: FDA), so it says what Reporting and the complaint page say; once an assessment or a report dates the
  market, that line stands in for it. On a fresh trial: Oversight's items 14 -> 16 (overdue 1 -> 1, due soon 2 -> 2);
  the bell 3 -> 3, unchanged. Test: `tests/test_oversight_provisional.py`.

### Changed: texts (8.8)

The trial story's chapters (chapter 4: "Turn a rising trend into an investigation in one click"), About the sample
data, the user guide (the entrance; the four sections) and the website's step strips match the new screens.

### Sample numbers and labels that change

No deadline, trend figure, count or record changes.

| Where | Before | After |
|---|---|---|
| Story chapter 4 title | Turn a rising trend into a case in one click | Turn a rising trend into an investigation in one click |
| Story findings | "N open cases to investigate"; "N cases without a signed decision"; "N signals waiting for a decision or a case" | "N open investigations to work"; "N investigations without a signed decision"; "N trends waiting for a decision or an investigation" |
| Readiness ring, digest | Signals triaged | Trends triaged |
| Investigation step | Gaps and open questions; check "Open questions are answered" | Unknowns; "Unknowns are answered" |
| Analysis tile | Gaps | Unknowns |
| Case record download | Download case record | Download investigation record |
| Evidence source of sample records | MDARIX_SAMPLE | Sample data |
| About the sample data, lot impact button | Open the case scope | Open the lot impact |

### Tests

- pytest: `tests/test_flagship_walkthrough.py` (new): the flagship from its tile to ready to close by each screen's
  main button, with the field sources. Updated: `test_decision_brief.py` (the prefilled problem statement),
  `test_free_trial.py`, `test_import_signals_after_response.py`, `test_case_workflow_unit.py`,
  `test_case_intelligence_unit.py`, `test_readiness_digest_unit.py` (the words).
- vitest: `entrance.test.tsx`, `whyAsked.test.tsx`, `wowScreens.test.tsx`, `nextAfter.test.ts`,
  `flagshipWalk.test.ts` (new); `app/linkTable.test.ts` (every former investigation tab), `app/clickPaths.test.ts`
  (path f), `caseWorkflow.test.ts` (the progress line), and the tests whose words changed.

## [0.10.68] - 2026-11-02

On the trial maintenance line (`release/0.10`): stage 7 of the quality plan, "New navigation and the complaint page".
An organization switched to the new navigation sees four main screens, **My work, Complaints, Trends, Records**, with
**Settings, Help, Team and Account** at the top right, and one page per complaint. Every other organization keeps
today's menu: the default stays **classic**. A platform administrator switches an organization in Tenant 360.

No migration (stage 6's `tr11navigation` holds the setting). The API and web images change. The sample data does not
change, so `scripts/refresh_trial_story.py` has nothing new to do.

### Added: the navigation switch in Tenant 360

- Tenant 360 › Edit details offers **Navigation: Classic / New**, through the same edit as the other details, with a
  reason and the lock version, audited as `TENANT_UPDATED`. Platform administrators only. The overview shows it.

### Added: the new navigation (7.1)

- **Menu:** My work, Complaints, Trends, Records. **Top right:** Settings, Help, Team, Account. Getting started
  stays for trials (the trial badge and Help); Look ahead and Share feedback are in Help.
- **Every old place has a home** (`linkTable.json` `newHomes`): today's 12 menu items, 58 tabs and the nested audit
  trail views. E-mails already sent, bookmarks and the sample story's links open the new place. An address of the
  new navigation opened by a classic organization opens the classic place.
- New addresses: `/app/trends`, `/app/settings`, `/app/team`, and `/app/complaints/<ref>` for one complaint.
- On a phone, Settings, Team and Account are in the menu, so the header fits at 390 px.

### Added: My work (7.2)

- The **next step** first, as the screen's main button: the soonest task assigned to you, else your most urgent
  reminder, else the complaints to triage. "Log a call" sits beside it.
- **Tasks for me** (one list with views: assigned to me, role queues, waiting, returned, due soon, overdue,
  completed), **Approvals**, **Evidence requests**, **Queues** (calls to check, possible duplicates, ready to close as
  routine) and, for managers, **Team overview** (everything overdue or due soon, with its owner). Managers see the four
  inspection-readiness numbers and the team's overdue and due-soon counts above. Five tabs instead of ten; My AI
  conversations stays hidden while AI is off.
- **"I will be away"** is in Account › Away, linked from the reminders.

### Added: Complaints as one list with views (7.3, 7.5)

- Views: **To triage, Due soon, Past target, Second look, Reporting, Communications, Investigations, Dismissed** and
  **All complaints** (an extra view: the list itself, with its filters). Reporting is the one home of the
  reportability decisions and the authority reports. Due soon and Past target are the complaints against your
  target (the former Backlog). Dismissed lists the records decided as not complaints. A phone shows the views as one
  "View" choice.
- **Import your data** and **Log a call** are actions on the list's header; the templates are in Settings.
- **All complaints** has six columns: Urgency · What happened · Product, version, lot · Markets · Owner · Stage. A
  complaint opens its page; one visible action (Open) and the rest under ⋯. Cards at phone width.
- Each customer problem code shows its **IMDRF term** beside it, as recorded (`SPO2_DROPOUT_HARM` stays): the list,
  the complaint page, the problem-code filter.

### Added: one page per complaint, `/app/complaints/<ref>` (7.4, 7.8)

- The Oversight event checklist, promoted to a page and opened by the reference people read (the customer's own,
  else its MDARIX ID). Stage 6's addresses by id redirect to it.
- **Header:** what happened, what needs attention, owner, due (a deadline chip per market), stage, and one main
  button: the next action.
- **Sections:** Summary (what happened, the stage line, what needs attention) · Evidence (first contact, open
  questions, the communications log, the authority reports) · Decisions & actions (triage, market assessments,
  reports, disposition or decision, CAPA, owner, ready to close) · History (the signed decision record, the filing,
  the audit trail).
- **Who signs, before the work starts:** each step names the colleagues who may sign it (an authority report: never
  the person who prepared it). **Send to** puts the step in that colleague's My work as a task; only a colleague who
  may sign the step can receive it. Separation of duties is unchanged.
- Each step opens on its record, not on a list: the complaint's triage item, its market assessment, its disposition,
  its CAPA's check. A reminder of a reply due opens the request itself.
- The page also shows the **reportability watch's provisional deadline** of a market not assessed yet (SAMPLE-RV-06:
  FDA, Sun 8 Nov). Oversight lists a market's clock only once its assessment is started (an owner decision below).

### Added: Trends, Records, Settings and Team (7.6, 7.7)

- **Trends:** opens on the trend check; then the trends to review, complaints over time and by resolution; an
  Investigations button.
- **Records:** inspection readiness, documents, decision records, CAPA records, effectiveness checks, risk file
  input, the audit trail, verify a signature, and **Exports** (every export in one place).
- **Settings:** complaint review rules, reporting windows, reportability guides, working calendar, trend rules,
  contact attempts and import templates. Each says **who can change it**; others read it. On the new navigation the
  working calendar and the contact-attempts setting are no longer on daily screens.
- **Team:** a trial invites and manages colleagues here. In a pilot it says the team is managed in the admin console,
  and opens it for an administrator.

### Changed for everyone (classic too)

- Words: "Open case" is "Open an investigation" (Signals and the user guide). The event checklist's "Resolve" names
  the step's action ("Assess the United States (FDA) market").
- States: a disabled action says why beside it (`aria-describedby`): naming the event owner, signing ready to close,
  recording the filing, adding a holiday, saving the calendar, a task action, a supplier request, a reply, recording
  an absence. Empty task and complaint lists name their next action. Lists no longer say "Reading…" in their heading
  while their skeleton also says it is loading.
- The user guide opened from Help on the new navigation names the new places ("Complaints › Reporting").

### Sample numbers and labels that change

No deadline, trend figure, signal, count or record changes. Oversight's counts are unchanged.

| Where | Before | After |
|---|---|---|
| Signals, a signal's button | Open case / Open case with options… | Open an investigation / Open an investigation with options… |
| Dispositions, a known issue | Open case with the same problem or lot | Open investigation with the same problem or lot |
| Event checklist, an open item's button | Resolve | the step's action, e.g. "Assess the United States (FDA) market" |
| Triage, First contact, Second look, Backlog, Reports, Communications, Reminders, Oversight while loading | "Reading the triage list…" and the like | the list's name ("The triage list") |
| Problem-code filter | PRESSURE_ALARM · IMDRF A16 | PRESSURE_ALARM · IMDRF A16 Protective Measures Problem |

### Tests

- pytest: `tests/test_complaint_page.py` (new, 8): by reference, by id, another organization 404; SAMPLE-RV-06, -08,
  -11 show the same deadline, owner, stage and next action on the page, the list, Oversight and the reminders;
  SAMPLE-URG-01 (a call, not yet a complaint, so no page) has one triage target everywhere; who signs and Send to;
  Dismissed. `test_workflow_tasks_unit.py`: the new task type `COMPLAINT_STEP`.
- vitest: `app/linkTable.test.ts` (both navigations; every old place has a new home; the complaint address; no
  setting on a daily screen), `app/clickPaths.test.ts` (paths a–m), `app/newPathText.test.ts`,
  `workspace/nextStep.test.tsx` (the first screen's main button names the next action), Tenant 360's model test.

## [0.10.67] - 2026-11-02

On the trial maintenance line (`release/0.10`): stage 6 of the quality plan, "Navigation foundation". Every screen,
tab, record, open panel and filter now has its own address. Back, refresh, a new tab and signing in again keep the
exact screen. One table maps every old address and section name to its place, and a test proves that every link MDARIX
sends lands on a screen and tab that exist. Nothing on screen changes, except the browser's address and the links that
were broken (below). No menu item, tab or test id changes.

**Migration `tr11navigation`** (after `tr10setasidedismissed`; `tr03pmssources` stays reserved). It is expand-only:
it adds one column with a default, `tenants.navigation`, set to `classic` or `new` (default `classic`). Every
organization keeps today's menu. On legacy dedicated organization databases, run
`scripts/add_workflow_tables_to_legacy_planes.py` (new step tr11). The API and web images change. The sample data does
not change, so `scripts/refresh_trial_story.py` has nothing new to do.

### Changed: one address for every view (6.1, 6.2)

- An address names the screen and its tab, and the record, open panel or filter the tab shows, for example
  `/app/complaints?tab=Reports&complaint=<id>&report=<id>` or `/app/signals?tab=Signal+inbox&priority=HIGH`. The case
  page keeps `/app/investigations?case=INV000147&step=Decision`, now with what the step carries (a follow-up, a
  review, a view).
- **Opening a record or a panel adds a history entry, and changing a filter replaces it.** Back closes a panel
  without reloading the screen. Refresh, a new tab and sign-in (`returnTo`) reopen the same panel. The panels with an
  address are a triage item, a first-contact check, a disposition, a report, a communication, an Oversight event's
  checklist, a signal, a task, an evidence request and a CAPA's check. The filters with an address are the complaint
  list's and the signal inbox's. The same tab for a second record is now a different address.
- **Every section has a path:** `/app/getting-started`, `/app/import-data`, `/app/account`, `/app/feedback` and
  `/app/look-ahead`. An address with `?section=` (used until 0.10.66) still opens its screen and is rewritten to the
  path. A `?signal=` link stays in the address; it used to be removed at start.
- Under the hood there is one address module (`features/workspace/workspaceAddress.ts`). It replaces the separate
  parsing in each screen, which each screen did for its own tab only.

### Added: the old -> new link table (6.7)

- `frontend/src/app/linkTable.json` holds the screens and their tabs, and where each kind of record opens. It also
  maps every former address (`/app/decision`, `/app/risk-traceability`, `/app/audit` and the rest), former section
  name (Dashboard, Products, Evidence, Decisions, Intelligence, Trust & Audit) and former tab name to its place. It is
  applied when the workspace starts and on every navigation, and it is kept permanently, so e-mails already sent,
  bookmarks, videos and guides keep working. At this stage the places are today's screens; stage 7 changes them.
- `/app/story` now opens the case page. It opened the list of investigations, because its Story tab is parked.

### Changed: the server sends places, not strings (6.6)

- One server helper (`backend/app/links.py`) builds every server-sent target: Readiness checks, Oversight rows and
  alerts, each event's checklist and next action, report and guide approval tasks, and the trial story's chapters.
  Each target now carries a structured `opens.target` (`section`, `tab`, `record`, `panel`). It still carries the
  `opens.section` and `opens.tab` fields that screens read until 0.10.66, so a tab left open across the upgrade keeps
  working. One resolver in the app (`placeOf`) turns targets into places. Alerts raised before the upgrade still open.
- E-mails use the same addresses (`links.app_path`).

### Added: links to any record (6.5)

- A case's audit trail opens a complaint (its Oversight checklist), a report, a communication, a CAPA (its check) and
  a disposition. Opening any record from a case's timeline makes that case the context, even when the timeline shows
  another case than the one open.

### Fixed: links that went nowhere (6.4)

- The "risk review requested" e-mail linked Risk & Traceability (`/app/risk-traceability`), a screen the MVP parks.
  It now opens My Work, where the review task is.
- The "decision waiting for your approval" e-mail said "Open Decisions" and linked `/app/decision`, a parked section.
  It now says "Open the decision" and opens the case's Decision step (without a case: My Work › Approvals). The
  "decision signed" e-mail opens the Decision step too.
- The trial's support-access e-mail said "Open Getting started › Team" but opened `/app`, which lands on Your data. It
  now opens `/app/getting-started?tab=Team`.
- Investigations: a case of another product showed "Other product" and could not be opened. It now opens; its product
  is looked up.
- My Work › Approvals: a case of another product said "Choose … in the context bar above", but My Work has no context
  bar. It now opens the case.
- Records › Audit trail without a case said "Pick one in the context bar above", but Records has none. It now says
  "Open one in Investigations, then its Record step's timeline", with an Open Investigations button. A case link that
  cannot be opened now says "Open it from Investigations".
- A link to a tab that carries a record (`Dispositions?complaint=…`) opened Triage. It now opens the named tab.

### Added: the per-organization navigation switch (6.9)

- `tenants.navigation` is `classic` (the default) or `new`. A platform administrator sets it with the Tenant 360 edit
  (`PATCH /api/v1/platform-admin/tenants/{id}`, with a reason and the lock version; audited as `TENANT_UPDATED`); no
  new route. A trial owner cannot set it: in the existing permission model, editing an organization's record is
  platform-only. The session context names it (`navigation`). Nothing shows it yet; stage 7 builds behind it, demo
  trial first.

### Changed: saved column choices survive (6.8)

- Each screen keeps its lists' column choices under a stable view id (`linkTable.json` "viewIds"), so a screen that
  moves or is renamed in stage 7 keeps them. The choices kept under the section's name until 0.10.66 are carried
  over once. If storage is unavailable, the lists show their default columns.

### Inventory (6.3)

`docs/architecture/MDARIX_LINK_INVENTORY.md` lists every link source with its code, count and test. It covers about
41 server targets, 17 task types, 22 audit-trail record kinds, 58 literal `open()` calls, 11 tab builders, 60 "A › B"
guide paths, 13 e-mail links, `returnTo`, 24 former addresses, 15 former section rules and 3 former tab names. It
also notes the mvp-1.0 differences for the forward merge (`featureSet.ts`: `routeFor` now in `linkTable.ts` must use
`usesMvpScreens`; the pilot feature set's Records tabs; `UserWorkspace.tsx`; `Investigations.tsx`). It lists the
Playwright lines to update at stage 9 (5 specs); these were not run.

### Sample numbers and labels that change

No deadline, trend figure, signal, count or record changes. The labels below change, all where a link was broken:

| Where | Before | After |
|---|---|---|
| The approval e-mail's button | "Open Decisions" | "Open the decision" |
| The risk-review e-mail's button | "Open Risk & Traceability" | "Open My work" |
| Investigations, a case of another product | "Other product" | "Open workspace" |
| Records › Audit trail without a case | "… Pick one in the context bar above." | "… Open one in Investigations, then its Record step's timeline." (with a button) |
| Records › Audit trail, a case opened from a decision | "The context bar above still shows another case." | "Opened from a decision: not the case you have open." |
| A case link that cannot be opened | "Choose it in the context bar above." | "Open it from Investigations." |

### Proof that nothing else changed

- Every workspace section and tab, and the first panel of each, was shot at 1440 and 390 px on the same trial, with
  the 0.10.66 screens and with 0.10.67 (128 images each). 115 are identical in every pixel. Twelve differ only by
  animation frames (the readiness ring, the sample cards fading in) or a form's default "now" time. One difference is
  the fix above: the sample's own investigation INV000001 read "Other product" in Investigations › All
  investigations, and now reads "Open workspace". The screens are in `MDARIX-videos/site-0.10.67-review` (`before/`,
  `after/`, `diff/`, `compare.json`).
- A browser check (55 checks, all passed; `navigation-checks.json` there) covers three things:
  - Old addresses: `?section=`, `/app/decision`, `/app/risk-traceability`, `/app/audit`, `/app/products`,
    `/app/story` and `?signal=` each open their place.
  - Tabs and filters: a tab change is a history entry; refresh keeps the tab; a filter replaces the address, and
    refresh keeps it.
  - Panels: for eight panels (triage item, disposition, report, communication, first-contact check, Oversight event,
    CAPA check, task), opening gives the panel an address; refresh keeps it open; Back closes it on the same tab;
    Forward opens it again; and a new tab opens the same panel.

### Tests

- pytest: `tests/test_link_targets.py` (new, 7 tests). The server's places equal the browser's table. Every target a
  free trial receives (Readiness, Oversight, alerts, 44 events' checklists, the story) names an existing screen, tab
  and record, and its older fields agree with it. Every e-mail sender is called, and each of its links opens an
  existing screen and tab, never a parked one. The navigation setting is classic by default and only a platform
  administrator can set it.
- vitest: `app/linkTable.test.ts` (new, 13 tests). The places equal the tab constants. Every former address, section
  and tab redirects, and every `?section=` address is read and rewritten. Every task type, audit-trail record, built
  tab, literal `open()`, sample chapter and guide path lands on an existing tab, and the resolver reads both forms.
  `workspaceAddress.test.ts` is rewritten: the scheme, and refresh and a new tab keep 15 kinds of panel and filter,
  and Back. `tables/columnViews.test.ts` is new.
- Updated on purpose: the e-mail tests (`test_notifications_delivery.py`, `test_workflow_roles.py`: the new
  addresses), four tests that compared an "opens" dict whole (`test_free_trial.py`, `test_readiness_api.py`,
  `test_qms_documents_api.py`, `test_risk_file_api.py`), and two vitest mocks that gain the new hooks.
- **Stale tests, not defects** (each in its own commit):
  - `test_communications_api::test_a_request_moves_to_the_second_contact_and_ends_unresolved`. On a Monday,
    "sent 2 days ago" is a Saturday. The weekend is not working time, so in Monday's first hour in New York the log
    counted as made within one working hour. Its clock is now frozen on a Thursday.
  - `test_authority_reports_api::test_the_india_sample…`. It took the awareness day by its UTC date, but the product
    counts from the earlier of the IST and New York days (as `deadlines.py` documents). It now reads the day by that
    rule.
  - `test_complaint_disposition_api::test_another_organization_cannot_read_dispositions…`. **No cross-organization
    read:** the other organization gets 404, and the database's own isolation check passes. The test fails only when
    run alone, because its chapter count needs the dispositions signed by the file's earlier tests. The whole file
    passes, and it is left as is.
  - `test_sample_story_days::test_the_flagship…`. It looked for the triage item by its MDARIX ID; since 0.10.66 the
    item carries the complaint's own reference.

## [0.10.66] - 2026-11-02

On the trial maintenance line (`release/0.10`): stage 5 of the quality plan, "Design system and accessibility". The
application and the website share one set of design tokens and load the Inter font; deadlines, states and harm read
as three kinds of label; screens name things instead of showing codes, and a complaint shows one ID; lists become
cards on a phone; the "you decide and sign" line is said once, where a person signs; and the accessibility findings
of the review are fixed. No menu, tab or list column changes.

**No migration.** The API and web images change. **Operators:** run `scripts/refresh_trial_story.py` (dry run first,
then `--apply`) once after the upgrade: it rewords two kinds of older sample record in running trials (below).

### Changed: one style shared with the website (V14, V15)

- `frontend/src/tokens.css` holds every colour, type size (12/14/16/20/24/32), weight (400/600/700), spacing step
  (4 to 48), radius (6/10/14/999) and the two shadows. Every style sheet of the app and the website reads it: about
  550 distinct colours, 77 font sizes, 32 radii and 72 shadows now name a token. The five `:root` blocks that
  redefined names are gone. Muted text is #5c6d7c (it was 3.97:1 on the grey ground, now 4.93:1).
- **Inter is self-hosted** (woff2, 400/600/700, from the Inter 4.1 release the PDFs use; its licence at
  `/fonts/Inter-OFL.txt`). It was declared and never loaded, so Windows drew Segoe UI. No external font host.
- The workspace's top bar shows the M tile, as the website does; the website and sign-in pages drop their second
  tagline ("Product intelligence").

### Changed: labels that mean one thing (V1-V4)

- Three kinds of label: a **deadline** chip with an icon and words from the one time-left helper ("3 days left",
  "Due today", "6 h left", "2 days overdue"; red only when overdue), a neutral **state** chip, and an outlined
  **harm** chip with a shape (◆ death or critical, ▲ serious, ○ no harm or a malfunction). Status is never colour
  alone; "serious" is amber, not red.
- Triage cards lead with the triage target and the report deadline as chips; report cards and the report drawer show
  their state and deadline as chips; My Work's and Oversight's Due columns show the chip and the date.
- A time no longer carries "GMT+5:30"; each workspace screen says "Times are in India Standard Time." once.
  Signatures and audit records keep their UTC time.

### Changed: names, not codes; one ID per complaint (J18, V2)

- One label map per kind of code (`app/labels.ts`): markets ("EU and Northern Ireland", not EU_NI), escalation
  triggers ("New failure mode"), document versions ("MDARIX starter, version 1", "your version 2"), decision-guide
  questions by number ("2a", not US2A), time zones, and any other code in words ("Complaint threshold"). Used on
  Oversight, dispositions, detection rules, the market assessment, reports, decision guides and first contact.
- Server texts: Readiness ("escalated by the recurrence trigger"; the market's name on "against the scale" items),
  the approver's guide alert ("Approve the decision guide (your version 2)") and the management review summary's
  escalations by trigger.
- **A complaint shows one ID**: its own reference (SAMPLE-RV-08, or the imported complaint number) where it has one,
  else its MDARIX ID; the triage and report drawers say "Also known as CMP000036". Documents, exports and signed
  records keep the IDs they named; the complaint list keeps its two ID columns (columns change in stage 7). IDs do
  not break at a hyphen.

### Changed: tables, phones and forms (J20, V8, V10-V13)

- List headings are a light row, not the navy bar; rows are 44 px high.
- **At 640 px and below every list is a set of cards** (its first value as the title, each value under its heading,
  the actions last), including the import's file preview and rows set aside: no sideways scroll, no word on a line
  of its own.
- On a phone the section's tabs are one row that scrolls inside itself, the context bar is two columns and the count
  tiles are compact, so Triage's first card shows sooner. Quotes show three lines, not two cut at 34 characters.
- Form fields on one grid line up; Getting started has one primary button (the next chapter), not ten.
- No page is wider than a phone: panels, forms, fields and drawer sections are one column that shrinks with the
  screen (an auto column grew to its widest line: Reporting windows was 780 px wide at 390), grids and selects never
  ask for more room than there is, buttons wrap on a phone, a list that is not a card list keeps its own scroll box,
  and on a phone the M tile stands for the name in the top bar.

### Changed: fewer words, said once (V5, V6)

- "You decide and sign. MDARIX prepared this from your records; it never decides or submits." is said once, beside
  each place a person signs or records a submission; the disclaimers on the menu, page guides, heroes and notes are
  gone.
- A free trial shows one "Sample data" chip in the top bar ("Practice records" once the sample is removed) instead of
  practice notes on seven screens; the PDFs keep their PRACTICE RECORD watermark.
- Page guides are 25 words or fewer. A first contact's follow-up task says "Follow up SAMPLE-CALL-03 with the
  reporter: 8 open questions"; a reply-due task says "Reply due from Reporter of SAMPLE-RV-08 (ward nurse,
  fictional)" (it carried the MDARIX ID and the whole request). The questions and the request stay in the details.

### Changed: states and accessibility

- An empty list offers its next step (Triage: "Log a call or an urgent intake"; Reports: "Assess a complaint per
  market"). A predictable refusal is said beside the disabled control and read with it (aria-describedby). The
  notice after an action stays in view. "Discard this draft" asks for confirmation in the page.
- The sign-out button reads and is named "Sign out" (it read "Logout" and was named "Sign out of MDARIX"); a hero
  announces only its headline; chip filters are one Tab stop with arrow keys; touch targets are 44 px on phones and
  touch screens; drawer headings go from h2 to h3, at weight 600.

### Sample numbers and labels that change

No deadline, trend figure, signal, count or record changes. Labels that change:

- the sample's open request to SAMPLE-RV-08's reporter: "(US2A, US2B, US2C and US3 are Unknown in the US
  assessment)" becomes "(four US questions on harm are Unknown in the US assessment)";
- the first-contact follow-up tasks: "Follow up SAMPLE-CALL-03 with the reporter: ask about question 1, question 2,
  ... question 9" becomes "Follow up SAMPLE-CALL-03 with the reporter: 8 open questions"; "ask whether any
  deficiency is alleged" becomes "is a deficiency alleged?";
- the reply-due task and reminder for RV-08: "Reply due from Reporter of SAMPLE-RV-08 (ward nurse, fictional) on
  CMP000036: Ask the reporter: ..." becomes "Reply due from Reporter of SAMPLE-RV-08 (ward nurse, fictional)";
- cards and drawers show SAMPLE-RV-08 (each complaint's own reference), not CMP000036, as the complaint's ID.

`refresh_trial_story.py` rewords the first three in running trials, tasks and reminders already raised included
(`backend/app/trial/sample_words.py`; idempotent).

### Tests

- vitest: `tokens.test.ts` (every text, ground, fill and control token pair meets WCAG 2.1 AA; one token file; the
  type scale; Inter and its licence), `app/chips.test.tsx`, `app/labels.test.ts`, `test/noCodes.test.tsx` (the main
  screens and two drawers rendered with the sample's recorded API answers show no code, question code or raw id),
  `features/workspace/states.test.tsx`, `features/workspace/accessibility.test.tsx`.
- `frontend/scripts/check-phone.mjs` (`npm run check:phone`): every workspace section and tab and the website's main
  pages at 390 px; it fails on a page wider than the screen or a code on screen.
- pytest: `tests/test_sample_words_0_10_66.py` (new). Updated on purpose: `test_intake_triage_api.py` (the triage
  item by the complaint's own reference), `app/dates.test.ts` (no zone on a time), `disposition.test.tsx` (the
  decide-and-sign line, no practice line), `trialInsights.test.tsx` (cells carry their heading).
- Stale numbers, not defects: `test_complaint_list.py` (37 to 44 sample complaints, 17 to 18 on Rev B, three in
  Germany), `test_lot_impact_api.py` (43 to 44 complaints with the flagship), `standards.test.tsx` (33 standards with
  IVDR_82, and the flagship's pain).

## [0.10.65] - 2026-11-02

On the trial maintenance line (`release/0.10`): stage 4 of the quality plan, "Your Excel just works". A realistic Indian
complaint register imports on the first try with no edits to the file: a title row above the column names, the data on
a second sheet behind a hidden one, DD/MM/YYYY dates, "1,25,000", "Death (Y/N)" columns, a kit with two lots and
"India, Germany" in one cell. Every column the file holds is either used or named as not used. Getting started and
Import data share one upload screen and one server path, and a row set aside can be fixed or dismissed on screen.

**Migration `tr10setasidedismissed`** (after `tr09recordfacts`; `tr03pmssources` stays reserved), expand-only: the
status check of `import_quarantine_rows` also allows `DISMISSED` (no row changes), and one nullable column,
`import_quarantine_rows.resolution_note`. Legacy dedicated organization databases: run
`scripts/add_workflow_tables_to_legacy_planes.py` (new step tr10). The API and web images change. No sample data
changes, so `scripts/refresh_trial_story.py` has nothing new to do.

### Changed: one upload path (IA, "two uploaders")

- **Getting started › Your data and Import data show the same upload panel** and post to the same route,
  `/api/v1/data/import/{entity}` (and `/check`), with the same limits (a trial: 5,000 rows and 2 MB a file, shown on
  both), checks, set-aside rows and data-quality report. The panel reads its templates and limits itself from
  `GET /api/v1/data/import/templates`, which now also says the organization's usual date order and number format
  (`usual`).
- **`/api/v1/trial/imports/{entity}` and `/check` stay as thin aliases** of the same handlers (still answering only a
  free trial, 404 elsewhere), because the tests, the validation package (Document 1, FT-09-005; its evidence JSON) and
  older links still call them. No screen calls them any more.
- The audit records are unchanged: `TRIAL_DATA_IMPORTED` in a trial (written with the data, in one transaction, as its
  own route did), `DATA_IMPORTED` elsewhere. **A pilot's import behaves as before**, apart from the shared checks below.

### Changed: the file is understood (J4, J5, J6, J41, J42)

- **Dates.** "Dates in the file" starts at **From the file, else DD/MM/YYYY** (the organization's usual order): a
  column name such as "Event Date (DD/MM/YYYY)", or a date such as 14/03/2026 that can only be day first, decides; when nothing in the file tells, the organization's
  usual order is used and said back (DD/MM/YYYY everywhere but the United States, from the time zone in Settings).
  "14-Mar-2026", "Mar 14, 2026", two-digit years, a time after the date and Excel day numbers (46095) are read too;
  a workbook in the 1904 date system reads the right day (it was about four years out). The API's own default stays
  `date_format=ISO`; `AUTO` is new.
- **Impossible dates are refused in words:** "'03/04/2062' reads as 3 Apr 2062, a day still to come. Check the year,
  and the order of day and month." and "'03/04/1926' reads as 3 Apr 1926, before 1970: too early for a device in use
  today." A planned date (an expiry, a due date, a release date) may lie ahead.
- **Changing a choice checks the same file again** (dates, numbers, sheet, date column, rows with problems, personal
  details, the template), without picking the file again; and the same file can be picked again after it is fixed.
  Before, changing "Dates in the file" cleared the file while the button still showed it, and picking the same file
  again did nothing.
- **Column names below a title.** MDARIX finds the row with the column names among the first 20 rows ("The column names
  are on row 3: the rows above them are not data"); the row numbers it gives are the file's own. A CSV's separator is
  read from that row.
- **Workbook sheets.** A workbook is read from the visible sheet whose column names fit the template best (a hidden sheet
  is never read unless named); the check says which sheet was read, lists the others and offers "Sheet to read". A
  lots file from a register's "Batch Register" sheet is read from that sheet.
- **Header variants:** "Date of Complaint", "Complaint Received Date", "Received On", "Date of Receipt" -> received
  date; "Event Date (DD/MM/YYYY)", "Date of Incident" -> event date; "SW Version", "Firmware Version" -> version;
  "Batch/Lot No." -> lot; "Death (Y/N)", "Serious Injury (Y/N)", "Malfunction Y/N" -> the harm and outcome fields;
  "Batch Qty" -> a lot's quantity. A hint in brackets or a trailing "Y/N" or "DD/MM/YYYY" is not part of the name.
  Yes/no columns take Y, N, Yes, No, 1, 0 or blank; "NA", "-" and "Unknown" read as not known (never as No).
- **Columns not used are named, never dropped silently:** the check lists "Not used (not stored): Sr. No., Complaint
  Received Date (the same as Date of Complaint)", and the run's data-quality report keeps the list (new
  `quality_report.columns_not_used`; Checks: "Columns not used").
- **A complaints file without an event or received date column is not ready.** The check asks "Which column holds the
  date each complaint was received?" with the file's unused columns, or "None: date each complaint the day it is
  imported" (said back as a note). Before, every complaint was dated the import day, which read as a sudden rise. New
  query parameter `date_column` (a header, or `none`).
- **Numbers:** "1,25,000" and "1,250" are 125000 and 1250; "1250,00" and "1.250,00" are 1250, never 125,000. "Numbers in
  the file" (`number_format`: GROUP, the default, or DECIMAL_COMMA) decides only "1,250" and "1.250"; a value the other
  choice would read whole is refused with that choice named ("If it means 1,250, choose 'Numbers in the file:
  1.250,00'"). It starts at the organization's usual format (1.250,00 for most of Europe).
- **A software version such as "1.4.2+build" is accepted** (a "+" was refused).
- **"India, Germany" in one country cell is two markets:** India's (the event's own market, first) and the EU's; both
  are assessed and preselected, and a reporting window for either covers it. One country stays one ("United States").
- **Text without a byte-order mark** is read as UTF-8, else as Windows text: this already worked (the register's finding
  was the download), and is now tested with the register: "Cathéter" stays "Cathéter". **The rows-to-fix download now starts with a byte-order mark**, so Excel
  shows "Cathéter", not "CathÃ©ter" (J42).
- **The review shows every date in one format** ("14 Aug 2026"), in the check's preview and the rows set aside.
- **A kit's later lot needs no description of its own** (the complaint's first row gave it); stage 3's fix keeps it as
  the complaint's next lot.

### Changed: set-aside rows fixed on screen (J11)

- In the data-quality report, each row set aside has **Fix and process again**: the fields its reasons name (every field
  when they name none), the other values as stored, personal details still as placeholders. It goes through the same
  checks; what is still wrong is said beside the row ("Still not right, so the row stays set aside. ...") and the row
  stays open. **Dismiss** asks why (kept with the row, personal details masked, audited as
  `QUARANTINE_ROW_DISMISSED`); a dismissed row leaves the open rows and Triage. The report says "N still open · N
  processed again · N dismissed".
- **Importing the fixed file again closes the old set-aside row** (as processed again), so it no longer stays open and
  on Triage; if the new import sets the same record aside again, the newer row replaces the older one (dismissed, "Set
  aside again by a later import"). Only rows of the organization's own imports, never the sample's. The import's audit
  record lists them (`set_aside_closed`).
- API: new `POST /api/v1/data/import/quarantine/{id}/dismiss` (`reason`, 3 to 500 characters; records.write);
  `POST .../reprocess` takes only the corrected columns (a column the row does not have is refused, 422);
  `GET /api/v1/data/import/quarantine?status=DISMISSED`; every count adds `dismissed`; a row adds `resolution_note`.

### Changed: clear words (D)

- Each problem names its row (the file's own row number), the file's own column name ("Row 5 · Death (Y/N)"), the
  value and what to do: "'Maybe' is not a yes or no: use Y, N, Yes, No, 1 or 0, or leave it blank (or NA) when it is
  not known." (it read "Use Y or N."); an identifier or version names its value. The data-quality report reads new /
  updated / unchanged, set aside, and the columns not used.
- The user guide's "Import a file" says the same.

### Sample numbers and labels that change

None. The sample's import run and its two set-aside rows are seeded as before, with the same reasons; no deadline,
trend figure, signal, count or label of the sample changes. (A trial's own import report gains the "Columns not used"
line; the sample's run, recorded before, shows none.)

### Tests

- `tests/test_indian_register_import.py` (new, 13): the synthetic register in `tests/fixtures/indian_register` (an
  `.xlsx` with a hidden first sheet, the complaints on sheet 2 below a title and a blank row, and a batch sheet; the same
  as Windows-1252 and UTF-8 CSV files without a byte-order mark; its generator `make_register.py`) is read field by
  field from both; the sheet said and chosen; Indian numbers; impossible dates; the date order; a 1904 workbook and
  Excel day numbers; the date column asked; header variants and yes/no words; "1.4.2+build" and two markets; then end
  to end as an Indian trial through the one path (every field of every complaint, the lots' quantities and expiry, both
  markets preselected, the same CSV through the trial's alias changing nothing, the report's columns not used), and
  set-aside rows fixed, refused again, dismissed with a masked reason, closed by a re-import and off Triage, audited.
- Updated for the date column (a complaints file now gives one, or `date_column=none` where the test is about a file
  without dates) and the clearer yes/no message: `test_data_import_options.py`, `test_business_record_import.py`,
  `test_complaint_list.py`, `test_data_import_path.py`, `test_import_reupload.py`, `test_web_protections.py`,
  `test_import_quality_report_unit.py`, `test_import_real_exports_unit.py`, `test_free_trial.py` and others listed in the
  commit.
- vitest `ImportExcel.test.tsx` (new): the one path and its choices, the panel's starting choices, problems named by the
  file's column, "Not used", the sheet and date-column questions, dates in one format, the fix form's fields, the
  counts, the report's "Columns not used"; `importPrivacy.test.tsx` and `importExport.test.tsx` updated.

## [0.10.64] - 2026-11-02

On the trial maintenance line (`release/0.10`): stage 3 of the quality plan, "A sample that tells one story". A trial
opened on day 0, 7, 15 or 29 shows the same alerts, deadlines still ahead of the reader, the same trend label and the
same next steps; the trial owner can restart the sample story; the approver is told; a guide's regulation wording is
locked and tested; the flagship scenario "Is this reportable, and by when, in the US and India?" is in the sample; and
records carry a few more true facts (a CAPA's QMS reference, device category, lot expiry).

**Migration `tr09recordfacts`** (after `tr08lotimpact`; `tr03pmssources` stays reserved), expand-only: nullable
columns, no default, no row changed: `capas.qms_reference`, `lot_batches.expiry_date`, `products.device_category`,
`complaints.other_lots`. Legacy dedicated organization databases: run `scripts/add_workflow_tables_to_legacy_planes.py`
(new step tr09). The API, worker (new scheduler job `trial-sample-clock`) and web images change.

**Operators:** run `scripts/refresh_trial_story.py` (dry run first, then `--apply`) once after the upgrade: it gives
running trials the flagship complaint, a calm day 0, the device categories and lot expiry dates, and relocks the sample
guide draft. After that the hourly `trial-sample-clock` job keeps each trial's sample current. Two changes are in
commits of their own for the owner to approve: the single-use field and Readiness's day.

### Changed: the sample's clock, and "Restart the sample story" (J2)

- **The sample's events move with the trial's clock.** The sample is dated from the moment it is seeded (its anchor,
  kept with the trial request; a trial approved earlier uses its approval time). Every hour the new scheduler job
  `trial-sample-clock` (`backend/app/trial/sample_clock.py`) moves every sample record, and everything hanging off one,
  forward by the time since the anchor: times by the exact time passed, dates by the days passed on the organization's
  calendar. Deadlines stay ahead of the reader, triage targets stay due within the day, the OrbitCare rise stays in the
  trend check's last 30 days, and the alerts, labels and next steps stay the same. This was chosen over a trend read
  "as of" the sample's own date, which would have left every deadline and alert ageing. The audit trail and the
  organization's own records never move; dates written inside a record's text or a signed record's content stay as
  written.
- **Once a person works on the sample, its clock stops** (a signed disposition, market conclusion, decision, review or
  document, a question to MDARIX, a case from a signal, an effectiveness check; own uploads do not count), so signed
  practice records are never re-dated. Getting started › About the sample data then says so.
- **Restart the sample story** (Getting started › About the sample data, the trial owner only) removes the sample and
  everything done on it, then seeds it again dated now. The page asks first, in the page, and says what each choice
  removes; "Also remove my practice work" also removes the organization's own uploaded records and what was done with
  them. Audited as `TRIAL_SAMPLE_RESTARTED`; the chapters already tried stay counted. New route
  `POST /api/v1/trial/sample-data/restart` (`confirm`, `own`; the trial owner only, checked in the route);
  `GET /api/v1/trial/sample-data/removal` adds `own_records`, `sample_dated_at` and `clock_stopped`.

### Changed: day 0 is calm (J2, J29, J30, J31)

- **The sample author has already done what the story does not need open** (`backend/app/trial/sample_calm.py`): every
  flagged sample record has a finished triage record except the urgent intake SAMPLE-URG-01 and the flagship
  SAMPLE-RV-11; the sample's first-contact tasks are due two working days ahead (SAMPLE-CALL-02's QMS task read
  "overdue" and escalated on day 0); RV-09, the finished US report, was signed ready to close and its decision record
  filed before it was closed, so it is "Closed in the QMS", not "closed before it was ready".
- **The sample author's absence lasts to the trial's last day** (it ended on day 6).
- **The sample story's escalations go to the person who started the trial**, not to every Leader: an invited colleague
  does not inherit them. The organization's own items escalate as before.
- **One line per complaint (J31):** a reporting reminder task no longer shows beside the report or market line of the
  same complaint in the oversight view and the bell.
- **Steps never needed read "not needed" (J29):** an event's stage line shows triage, market assessment,
  investigation or decision with a dashed grey border and "not needed" when no check of that stage applies (it ticked
  them as done).
- **One number per thing (J19):** stage 2's counts were checked: the bell and My Work's reminder panel read the same
  alerts; Getting started's loading fallback, the trial guide and the user guide say ten chapters, as the story serves
  (a test now holds them together).

### Added: the flagship story (D)

- **SAMPLE-RV-11**, "suspected inaccurate measurement, no reported harm, service required": a PulseWatch 410 monitor
  (Rev A, lot 002) read SpO2 4 to 6 points high against a reference oximeter at a US hospital; nobody was harmed; the
  monitor is out of use for service. It runs through the existing screens: triage (due within the day), each market's
  questions (the third scenario, "Is this reportable, and by when, in the US and India?"), the case the US conclusion
  opens, the service work or the CAPA to raise in the QMS, ready to close.
- **Expected, from the starter guides:** US reportable, a 30-calendar-day malfunction report (21 CFR 803.50), due 30
  days after the awareness day in New York; India not reportable (no adverse event: nobody was harmed), no Indian
  deadline. Getting started's chapter 2 and "About the sample data" describe it.

### Changed (separate commit, for the owner to approve): Readiness is as of the organization's day

- Readiness, its summary, the weekly digest and Getting started's findings count "today" on the organization's
  calendar, the day stage 2's due times end on: an Indian organization reads 2 Nov from 00:00 IST (it read the UTC
  date, 1 Nov, until 05:30 IST).

### Sample numbers that change (A and D)

Measured on fresh trials signed up from the United States, seeded at 23:50 UTC on 1 Nov 2026, after the first visit.

- **Bell and My Work's reminders:** 12 (2 escalations: RV-08's reply and SAMPLE-CALL-02's QMS task, "overdue"; 10
  triage targets due soon: RV-01, RV-02, RV-06, RV-07, RV-08, RV-10, RT-05, CALL-03, RJ-02, URG-01) -> **3**: RV-08's
  overdue reply (escalated, to the trial owner) and the triage of SAMPLE-RV-11 and SAMPLE-URG-01, due soon. The same on
  day 7, 15 and 29 (before: from day 1 about ten escalations to every Leader; on day 7 RV-06 overdue).
- **Oversight view:** overdue 2 -> 1, due soon 10 -> 2. Events: not ready 3 -> 6 (complaints the sample author triaged
  are events now), closed before ready 3 -> 2 (RV-09 no longer), closed 0 -> 1 (RV-09). RV-08's next action "Complete
  the triage record" -> "Sign the United States (FDA) market assessment".
- **Triage:** to triage 10 -> 2 (SAMPLE-RV-11, SAMPLE-URG-01); triaged 0 -> 10 (RV-06's and RV-07's deadlines show
  under "Triaged").
- **Complaints:** 43 -> 44 sample complaints (Getting started's counts, the removal preview, the dashboard). The
  reportability watch adds SAMPLE-RV-11 (US, running, 29 days left). Chapter 1, "complaints waiting for a
  disposition": 12 -> 13.
- **Getting started's insights:** total 37 -> 38; "46% of complaints (17 of 37) concern OrbitCare 300 Rev B" -> "45%
  (17 of 38)"; the last three months average 8.3 -> 8.7 per month (up from 3.0); malfunctions 5 -> 6; "US has the most
  complaints (7 of 9 with a country)" -> "(8 of 10)"; the lot question "15 of 37" -> "15 of 38".
- **Trend check:** PulseWatch 410 Rev A "Fewer than 3 recent complaints: not assessed" -> "In line with its history"
  (the flagship is its third recent complaint). OrbitCare Rev B 9 against 0.96 expected, significant: unchanged, and
  the same on day 7, 15 and 29.
- **Readiness:** every check's value unchanged on day 0 (reporting clocks 3, 2 due soon).
- **My Work's task tabs:** unchanged (assigned 1, role queues 7, overdue 1).
- **The sample author's absence:** two days ago to day 5 -> two days ago to the trial's last day.

### Tests

- `tests/test_sample_story_days.py` (new): day 0 holds only the story's three alerts, and My Work, the bell, Triage,
  Reportability, Trends, Readiness, Oversight and the chapters say the same on day 7, 15 and 29 (time is moved by moving
  every stored time back, then the hourly jobs run); the flagship's expected result and deadline per market, its
  escalation trigger, the clock stopping once worked on, and the restart; the stage line's "not needed"; one chapter
  count. `tests/test_readiness_org_day.py` (new): Readiness's day. Updated for the calm sample and the flagship:
  `test_oversight_api.py`, `test_one_deadline_api.py`, `test_intake_triage_api.py`, `test_free_trial.py`,
  `test_trial_insights.py`. vitest `removeSample.test.tsx` (what each restart choice removes).

### Changed: the approver is told (J13)

- **A report snapshot or a decision guide version waiting for approval is a task in the approver's My Work.** Asking
  for approval gives each colleague who may approve (regulatory review or approval rights; never the preparer, the
  signer of the market conclusion, an editor of the guide version or an administrator) a "Regulatory review" task,
  "Approve snapshot 1 of the Form FDA 3500A worksheet (eMDR) for CMP000034" or "Approve decision guide version GB-v2",
  under Assigned to me. It is due at the end of the next working day, or at the report's legal deadline when that is
  sooner, so the reminders carry it: the bell shows it to the approver once it is due soon, escalates it when overdue,
  and the oversight view lists it (a line per approver). "Open" goes to the complaint's Reports, or to Decision guides. The task ends
  when the item is approved (completed), or withdrawn, returned to draft, discarded or replaced by a new snapshot
  (cancelled). No new task type, no new tab: the existing task list and its counts include them.
- **Before anyone types a password, the screen says who approves.** A person who may not approve sees, in place of the
  approve form, why and who: "You prepared this worksheet: a second person must approve the snapshot. A colleague
  with regulatory approval rights approves this: Rahul Colleague." Before approval is asked, the draft says who will
  get the task ("When ready, ask for approval: Rahul Colleague gets a task in My Work"). No more refusal after the
  password and code. With nobody else holding the rights, it says an administrator gives a colleague the Regulatory
  Reviewer, Authorized Decision Maker or Leader role.
- **Working alone in a trial, you approve your own practice report or guide version (T-B8).** Only in a trial, only
  when separation of duties is the only reason, and only when no colleague may approve: the screen says "In a pilot a
  colleague approves this; in the trial you may approve your own practice report as Leader (Quality Manager)", the
  approval is signed with password and code as always, and the signature record, the audit event
  (`same_person: true`) and the snapshot list ("same person (trial practice)") say so. A trial with a colleague who
  may approve keeps the second person. **A pilot is unchanged:** separation of duties is always enforced there, and an
  administrator never approves, in a trial either.
- **The RV-06 report and the India report to correct (RV-10) can now be finished by the trial owner alone**: sign
  RV-06's US conclusion, start the worksheet, ask for approval, approve it as the practice approval, record the
  submission; for RV-10, ask for approval of the correction and approve it. With a colleague, the colleague gets the
  task and approves.
- **A guide version waiting for approval can be withdrawn by its author** ("Withdraw it: back to draft"): it returns
  to draft with its content and test results kept, and the approvers' tasks end. Only the person who sent it for
  approval may (403 `NOT_THE_AUTHOR` otherwise).
- API: `GET /api/v1/reports/{id}` adds `approval` (`may_approve`, `same_person`, `approvers`, `message`) while the
  report is a draft, and `same_person` on each snapshot; `GET /api/v1/decision-guides/{market}/versions/{n}` adds
  `approval` and `you_asked` while a version waits; new `POST /api/v1/decision-guides/{market}/versions/{n}/withdraw`
  (regulatory review or approval rights, its author only). A task in `GET /api/v1/tasks` carries
  `details.complaint_id` (only that detail), so a task opens its complaint's screen.
- Getting started and the trial guide say who approves a report: a colleague, told by a task in My Work; working
  alone in the trial, you.

**Requirement text (T-G2b, T-G15, T-B8; J13):** a snapshot or guide version waiting for approval is a task in each
eligible approver's My Work and a reminder; the approval screen states who may approve before any credential is
asked; the trial records "same person" when one person prepares and approves, only where no colleague may approve;
the pilot enforces the second person; the author may withdraw a waiting guide version.

**Sample numbers that change:** none. The sample seeds no snapshot or guide version waiting for approval (RV-09's
snapshot and US-v2 are approved; RV-10 is "correction required"; US-v3 is a draft), so the sample's tasks, bell and
oversight counts are unchanged. Approval tasks appear only when a person asks for approval. A guide version already
waiting before this release (no task) still shows on the oversight view and the reminders as before.

**Tests:** `tests/test_approval_told_api.py` (6: the rule; alone in a trial RV-06 and RV-10 are finished and a guide
version is approved as "same person", each task in the owner's My Work; with a colleague the preparer is told who,
the colleague gets the task and the bell line, once; the author withdraws a waiting guide version, the colleague
cannot); vitest `authorityReports.test.tsx` (who approves in place of the form; the practice note above it),
`decisionGuides.test.tsx` (who approves and Withdraw), `tasks.test.ts` (an approval task opens Reports or Decision
guides).

### Changed: decision guide wording locked; a guide test matrix (this reverses 0.10.59 decision 1)

The locked wording, the organization's explanation and examples, and the test matrix are kept in each guide version's
existing data (`decision_guide_versions`, tr06).

**Requirement (for the trial requirements, T-G15, and the MVP's G15):**
- In a customer's own decision guide, each question that drives the conclusion keeps MDARIX's wording, locked: the
  question, the regulation's definition, MDARIX's note, the clause citation and its basis. The customer adds their own
  explanation and examples beside it. They cannot change or delete the locked text: the server refuses it, not only
  the screen. Versions approved before the lock stay exactly as they were signed; a new version made from one takes
  the locked wording back, and its old help text becomes its explanation.
- Every guide version has a test matrix: worked complaints, each with its answers and the outcome the market's guide
  must point to (reportable with its report type, not reportable, or pending information; a blank answer is Unknown,
  never No). MDARIX's starter worked complaints are in every version and cannot be removed or changed; the customer
  adds their own.
- A version can be sent for approval only when every worked complaint in its matrix passes on its current content.
- The approval screen runs the matrix again and shows the result. If any worked complaint gives a different answer
  now (for example after an MDARIX release changed the logic while the version waited), the approval is blocked
  before any password is asked, and the server refuses it too; its author changes the version and sends it again.

#### Changed

- **Complaints › Decision guides, a draft:** the questions that drive the conclusion show their wording, definition,
  clause and basis read-only, marked "The regulation's wording: locked", with two fields beside them: "Your
  explanation" and "Your examples". Extra questions are edited as before.
- **Test matrix:** "Test cases" is now "Test matrix: N worked complaints". Each row is marked "MDARIX starter" or
  "Your worked complaint"; only your own rows can be removed. "Add a test case" is now "Add a worked complaint";
  "Run the test cases" is now "Run the test matrix". A starter row left out of a save is put back.
- **Approval:** a version waiting for approval shows "Test matrix, run again now": either "All N worked complaints
  still give the expected answer", or the rows whose answer changed, and "Approve and publish" stays disabled.
- **Market assessments** show the organization's explanation and examples under each question ("Your explanation",
  "Your examples").
- **The PDF and DOCX for an audit** print the explanation and examples, head the tests "Test matrix: worked
  complaints", mark the organization's own rows, and print the matrix rule.
- The user guide's "Decision guides" section says the same. The publish-gate lines read "Run the test matrix on this
  version's current content" and "N of M worked complaints in the test matrix fail" (were "test cases"). A draft
  started before this release whose wording was changed shows "Question X was reworded before the wording was
  locked: save the draft to restore the regulation's wording".

#### Fixed

- A customer version could reword the regulation's definition and clause of a question that drives the conclusion,
  and could delete MDARIX's starter test cases (0.10.59). Both are now refused by the server.

#### Sample numbers and labels that change

- **US-v2** (the sample's own US guide, in use): the help text on the three serious-injury parts (procedure QP-08) is
  now the organization's explanation beside MDARIX's locked wording, and part (c) also carries examples ("a cut closed
  with sutures to prevent permanent scarring is part (c); a bruise that healed without treatment is not"). Its
  US2A, US2B and US2C were marked "Your wording"; now "Starter text". Question and test counts unchanged (9 questions,
  1 extra; 6 worked complaints, all pass).
- **US-v3** (the sample draft): unchanged story. It still cannot be sent for approval for one reason only: "1 of 7
  test cases fail: fix them, then run again" (its own worked complaint, "outcome unknown: expected not reportable").
- In trials approved before this release, `scripts/refresh_trial_story.py` brings the sample US-v3 draft up to date
  once (the locked wording back, the old help text as its explanation, the matrix run again), so it reads the same as
  in a new trial. US-v2 there stays as it was signed. No complaint, deadline or trend figure changes.

#### Tests

- `tests/test_decision_guides_api.py`: a core question's wording is locked and the explanation sits beside it; the
  starter worked complaints stay in every matrix; the server refuses a change to locked wording and keeps old versions
  as signed (a copy takes the lock and keeps the old help text); a changed answer in the matrix blocks the approval
  before any password; a sample draft seeded before the lock is brought up to date once (dry run, apply, idempotent).
- `frontend/src/features/workspace/decisionGuides.test.tsx`: a core question sends only the organization's own text;
  the draft shows the locked wording, the explanation field and the matrix marks; the approval shows the matrix run
  again and a changed answer disables "Approve and publish".

### Changed: small truths in the records (J22, J32)

- **A CAPA's QMS reference (J22).** "Record the CAPA to raise in your QMS" now takes an optional **QMS reference**: the
  number your QMS gave the CAPA. It can be added later, changed or cleared from the same follow-up ("Save QMS
  reference"). Wherever the CAPA shows it reads "QMS reference CAPA-0450", or "To raise in your QMS" while MDARIX holds
  it without one: the follow-up list and its drawer, Records › Effectiveness checks, the CAPAs list (new column "In your
  QMS"; a CAPA imported from the QMS reads "From your QMS"), the oversight view, a report worksheet's remedial action
  (US H7) and the CAPA log document. New route `POST /api/v1/follow-ups/{id}/capa/qms-reference`
  (`investigation.work`, audited `FOLLOW_UP_CAPA_QMS_REFERENCE_SET`); `qms_reference` on the CAPA create body and on
  every CAPA a follow-up or the effectiveness board returns. MDARIX still never raises or runs the CAPA: your QMS keeps
  it.
- **A product's device category (J32):** implant, single-use, reusable or capital equipment, software, IVD or kit. The
  products file takes an optional `device_category` column (also read as "Device category", "Category", "Device type",
  "Product type"; plain words such as "Single use", "capital equipment" or "SaMD" are understood, anything else is
  refused with the list). The Products section shows it ("Not set" when no file gave it); that section is parked in
  the trial and the MVP, so there the category shows through the worksheets and Help.
- **A lot's expiry date (J32):** the lots file takes an optional `expiry_date` column (also "Expiry date", "Expiration
  date", "Use by"); the Products section's lots list it as "Expires".
- **The report worksheets read them.** India MDAE: A8 *Software version* from the product version, for a software
  product or a version that reads as a version number ("2.1", "v1.4.2"; a hardware revision such as "Rev B" is not one);
  A13 *Expiration date* and FDA 3500A D4 *Expiration date* from the lot's expiry date; II *Implantable or
  non-implantable* and IV *Single use or reusable* from the device category. Each shows its source, for a person to
  confirm, as every worksheet value does.
- **A kit's second lot is not a duplicate (J32).** A complaints file may list a complaint once per lot (a kit, a
  procedure pack): a row of the same complaint with another lot is that complaint's next lot, kept on the complaint
  (`complaints.other_lots`) and listed in the worksheet's lot field ("L-1; L-2"). It read "Duplicate of row 2" and was
  set aside. The same lot again, or a second row without a lot, is still a duplicate. Lot impact reads the complaint's
  first lot only (in Help's "not covered yet").
- **Help › What MDARIX covers** (a new part of the step-by-step user guide, not a new tab): by device category, in the
  US, EU and Northern Ireland, Great Britain and India, which reporting clocks, report worksheets and checks apply, and
  what is not covered yet. Starter text, for the consultant to confirm.

#### Fixed

- **The IVDR citation reads the product the same way on the watch as in triage.** Stage 2's reportability watch (and a
  case's regulatory review clocks) recognised an in-vitro diagnostic from the product name only, while triage read its
  name, family, GMDN term and description: a product named "GlucoCheck" in the family "In-vitro diagnostics" cited EU
  MDR Art. 87 on the watch and EU IVDR Art. 82 in triage. Both now read one function
  (`reportability/markets.py product_is_ivd`).

#### Sample numbers that change

- **Device category:** the three sample products (OrbitCare 300, PulseWatch 410, VentraLink 250) are "Reusable or
  capital equipment" (one table, `SAMPLE_PRODUCT_FACTS` in `backend/app/trial/sample_data.py`).
- **Lot expiry:** every sample lot expires 1,826 days (five years) after it was made, so it moves with the trial's clock
  like the other sample dates (OrbitCare lot 001, made 200 days before the trial: expires in 1,626 days).
- **SAMPLE-RV-10 India MDAE worksheet** (live and its approved sample snapshot): II "Implantable or non-implantable"
  empty -> "Non-implantable device", IV "Single use or reusable" empty -> "Reusable", A13 "Expiration date" empty ->
  the lot's expiry date. The worksheet's summary: "21 filled · 36 may wait" -> "24 filled · 33 may wait".
  A8 stays empty (PulseWatch "Rev A" is a hardware revision).
- **SAMPLE-RV-06 and the finished RV-09 US 3500A worksheets:** D4 "Expiration date" empty -> the lot's expiry date (one
  more "From record").
- **Records › CAPAs:** new column "In your QMS": SAMPLE-CAPA-01 and -02 read "From your QMS". The oversight view's CAPA
  line is unchanged ("(in your QMS)").
- No trend figure, deadline, signal, alert or citation in the sample changes (no sample product is an IVD).

#### Tests

- `tests/test_record_facts_0_10_64.py` (new): category words; the worksheets' A8, expiry and category fields; a kit's
  second lot; the IVD read from the product's own words; the sample's facts and their fill-in for running trials; the
  products and lots files' new columns; the watch citing the IVDR for an IVD family.
- `tests/test_decision_followups.py`: a recorded CAPA keeps the number the QMS gave it (create, add later, refuse
  before the CAPA exists or without `investigation.work`, clear, audit).
- vitest: the follow-up's CAPA text and body, `capaQmsText`, and Help's "What MDARIX covers".


### Changed (separate commit, for the owner to approve): a single-use field with its use period

- **Products carry a single-use field and an optional use period** (products file: `single_use` Y/N, `use_period_days`
  1 to 36,500; migration tr09 then also adds `products.single_use` and `products.use_period_days`).
- **The trend check's single-use basis reads the product first (J27).** The single-use field decides; without it the
  device category (single-use, kit and IVD count as used up); without either, stage 2's word list, kept only as the
  fallback. A single-use product is counted per calendar day, or, with a use period, by the units still within that
  many days of their lot's release ("Single-use product with a 30-day use period: each lot's units count as in use for
  30 days after its release."). A product named "catheter" but marked reusable is now counted per unit in the field.
- **The IVDR citation reads the device category first**: an IVD cites EU IVDR Art. 82 (starter); a product with
  another category does not, whatever its words; the words decide only when no category is set.
- **US 3500A H5 "Labeled for single use?"** comes from the single-use field.
- Help › What MDARIX covers says so; docs/user-guide/PER_UNIT_TRENDS.md explains the order.
- **Sample:** the three sample products are marked not single-use. No trend figure, signal, citation or deadline
  changes (none of them matched the word list before).
- Tests: `tests/test_record_facts_0_10_64.py` (the fields before the words, the use period's unit-days, H5, the
  products file's two columns).

## [0.10.63] - 2026-11-02

On the trial maintenance line (`release/0.10`): stage 2 of the quality plan, "Clocks and numbers you can trust". A legal
deadline is now counted one way and reads the same on every screen, with its time zone; an organization and a call have
their own time zone; the trend check's statistics hold at any size; and screens, guides and the website quote the same
counts.

**No migration.** The API, worker and web images change. **Operators:** no new setting. The counting rules are starter
rules, marked so, for the regulatory consultant to confirm per market; until then the conservative reading applies.

### Changed: how a legal deadline is counted (every screen)

One computation (`backend/app/reportability/deadlines.py`) now counts every market clock: the reportability watch, a
market assessment, triage's provisional deadlines, a report obligation, the reportability reminders, the oversight view
and its alerts, worksheets and exports.

- **Awareness is taken in a time zone before its day is counted.** Before, the UTC date of awareness was day 0: an
  awareness at 21:00 in New York counted from the next day. The authority's time zones are: US FDA America/New_York,
  EU and Northern Ireland Europe/Brussels, Great Britain Europe/London, India Asia/Kolkata.
- **Great Britain and India count the awareness day as day 1** (the MVP's conservative rule). Their deadlines are one
  day earlier than before (India 15 days: awareness + 14). The US and the EU still count from the day after awareness.
- **A deadline ends at 23:59 in the authority's time zone or the organization's, whichever comes first**, on the earlier
  of the two days counted. Before, every deadline ended at midnight UTC (05:30 the next morning in India).
- **Every legal deadline shows its time zone**: "Sat 7 Nov 2026, 23:59 IST". The API adds `due_at`, `due_zone` and
  `due_label` beside `due_date` / `due_on` (watch clocks, market clocks, triage deadlines, report lists and details,
  oversight items and alerts, the oversight CSV's `due_label` column, the inspection pack's "Deadline ends" column).
- No weekend or holiday extension is applied (EU Regulation 1182/71 is left out); public holidays still count as work
  days for the US 5-work-day report. A market without an authority zone here (Canada, or another country) counts in
  the organization's time zone from the day after awareness.
- An in-vitro diagnostic (recognised from its product name, family, GMDN term or description) cites **EU IVDR
  Art. 82** (starter) where an EU clock cited MDR Art. 87, on the watch and in triage. New catalog entry `IVDR_82`.

### Fixed

- **Triage shows the event's own market first (J3).** It showed the earliest provisional deadline across every enabled
  market, so a US event read "EU MDR … 14 days overdue". Now the event's market comes first, the other enabled markets
  are marked "if also reportable", and a market with a signed conclusion shows that conclusion's deadline (or
  "Concluded not reportable") instead of its provisional one. Without a country, or when the event's own market has
  no reporting window, every enabled market shows and the screen says why. The reportability watch shows the
  awareness day where the reader is, as triage does.
- **The watch honours a signed shorter category (J14).** The binding clock is always the earliest of the window's
  clock and every market's own clock, so an EU 2-day serious public health threat binds while a 15-day window runs;
  Readiness's reporting check counts it overdue. **Signing a reportable conclusion gives every open initial report of
  that market its category's deadline** (a report started while the market was pending kept the provisional date).
- **One "time left" text everywhere (J40).** "3 days left", "1 day left", "5 h left", "Due today", "2 days overdue",
  "3 h overdue": one helper (`frontend/src/app/dates.ts` `timeLeft`) on the watch, market assessments, triage, Reports,
  the oversight view, reminders, case reviews and CAPA checks. Overdue comes from the server's state, so "1 h left"
  never stands beside "Overdue"; whole days count to the deadline's own day in its time zone. ("Due in 10 days" now
  reads "10 days left".)
- **The organization's time zone (J16).** A new trial's working calendar starts in the sign-up country's time zone
  before the sample is seeded (India Asia/Kolkata, United States America/New_York, United Kingdom Europe/London, and the
  other common countries; otherwise UTC). Existing organizations keep theirs. The time-zone list holds current names
  only ("Asia/Kolkata", never "Asia/Calcutta" or "US/Eastern" beside it); an old name sent by a browser is stored under
  its current one.
- **One end of day for MDARIX's own due times.** A reply due, a CAPA effectiveness reminder and a risk-file follow-up
  end at 23:59 on the organization's calendar (they ended at 23:59 UTC); a first-contact follow-up's reply day is its
  task's day on that calendar (it was the UTC date of the task's end: a day late west of Greenwich, "overdue since
  29 Oct" beside "Due 30 Oct"); a reply is overdue once its day ends there.
- **A call's time zone is chosen from a list and its times converted in it (J28).** Chicago 09:00 entered from India
  is 15:00 UTC in November (it was stored as 03:30 UTC, the browser's 09:00). The first-contact form offers the list
  and starts with the browser's zone; the server takes wall-clock times in the chosen zone and refuses an unknown zone
  (422 `TIME_ZONE_UNKNOWN`). `GET /api/v1/intake/guide` adds `zones` and `zone_aliases`.
- **One number per thing (J19).** The website and the user guide say eleven inspection checks (they said eight;
  Readiness has eleven) and the website's quality loop draws all eleven ("3 of 11 inspection checks clear",
  illustrative); Getting started says 10 chapters while the story loads (it said 9) and the website says ten (it said
  nine); the Readiness check that counts complaints past the disposition target is named "Dispositions past the 30-day
  target or to review" (it was "Complaints waiting for a disposition", beside a board whose "waiting" counts every
  complaint without one); My Work's reminder panel says "12 reminders for you, 12 unread", as the bell counts them;
  a legal deadline reads the same day on Reports and the oversight view (RV-08's read 28 Nov on one and 29 Nov,
  midnight UTC seen from India, on the other).

### Fixed: trend statistics

- **The chance no longer breaks on large numbers (S1).** With more than about 745 complaints expected in 30 days every
  group read "In line" whatever its count (2,000 against 800 expected was "in line"). The Poisson chance is now
  computed in log space, exact at any size.
- **An event reported from several records counts once (S2).** Complaints a person linked as one event (record links
  LINKED, complaint to complaint) count once, at the earliest record's event date, in the trend check and in the count
  rule; every record is still listed and linked to the signal as evidence. The board says "an event linked from
  several records counts once".
- **A version younger than 30 days is expected only the days it has existed (S3)** ("in the 11 days since its
  release"); it was expected a full 30 days of complaints, which hid an early rise.
- **Many groups at once (S4).** Results use the Benjamini–Hochberg adjusted chance across every group assessed on the
  board (one organization, one grouping), at the same 1% and 5% thresholds; the Chance column shows the adjusted value
  with the group's own beside it ("allowing for the N groups checked"). A signal's trend line, the product filter and
  Readiness's trend and risk-file checks read the same adjusted result.
- **Complaints dated in the future are not counted (S5)** in the trend check or the count rule until their day comes.
- **A rise since a version change stays visible (J26).** A version that replaced another is compared with its own
  history and with the version it replaced; the stronger comparison is shown and names the other. Before, once the
  version had 60 days of its own history, a rise lasting since its release became its "history" and read "in line".
- **Single-use and consumable products are counted by calendar days (J27).** Their units are used up, so counting
  every unit ever released as still in the field hid rises. Such products are recognised from words in the name,
  family, GMDN term or description (a word list until products carry a single-use field), and the row says "Per
  calendar day (single-use)".
- A chance below 0.0005 reads "under 0.001" in a signal's trend sentence (it read "0.000" beside "p < 0.001").
- **One multiple per screen (J19).** The trend check says "(9.3× expected)"; the Getting started trend card says
  "3.3× the earlier average" in its headline only (its peak callout no longer shows a second multiple). The two measure
  different things (one version's 30 days against the version it replaced; all complaints per month against the
  earlier average), and each is now labelled.

### Sample numbers that change

Measured on fresh trials seeded at 21:55 UTC on 1 Nov 2026 (03:25 on 2 Nov in India); the sample is dated from the
trial's start, so a trial seeded at another hour can differ by a day. No sample data changed.

- **A trial signed up from the United States** (calendar America/New_York, was UTC): every deadline now names its time
  zone ("Sat 28 Nov 2026, 23:59 EST"). SAMPLE-RV-10 (India): 8 Nov, 7 days left, running -> **Sat 7 Nov 23:59 IST,
  5 days left, due soon**. Triage's first deadline: RV-06 "EU 18 Oct, 14 days overdue" -> "US Sat 7 Nov, 6 days left";
  RV-07 "EU 30 Oct, 2 days overdue" -> "EU signed, Wed 4 Nov 23:59 CET, 3 days left"; RV-10 "EU 3 Nov" -> "India
  signed, Sat 7 Nov 23:59 IST"; RV-08 "EU 8 Nov" -> "US Sat 28 Nov 23:59 EST, 27 days left"; SAMPLE-URG-01 "EU 10 Nov"
  -> "US Mon 30 Nov"; SAMPLE-CALL-03 (GB, no GB window) now says no window for its own market. India report (RV-10):
  8 Nov, 7 days left -> Sat 7 Nov 23:59 IST, 5 days left. Readiness "Reporting clocks" and chapter 2: 2 (1 due soon)
  -> 3 (2 due soon). The overdue reply on RV-08: due 29 Oct 23:59 UTC -> 29 Oct 23:59 EDT.
- **A trial signed up from India** (calendar Asia/Kolkata, was UTC): every deadline ends at 23:59 IST, the earlier
  end. RV-07 (EU) 3 -> 2 days left; RV-06 (US) 6 -> 5 days left, now due soon; RV-08 (US) 27 -> 26 days left; RV-10
  (India) 8 Nov stays 8 Nov (awareness at 03:25 IST on 25 Oct is day 1), 7 -> 6 days left; the decided RV-09 -10 ->
  -11 days. Readiness "Reporting clocks" 2 -> 3. Due times of MDARIX's own work end at 23:59 IST (they read 05:29 IST
  the next day).
- **Labels:** the Readiness check "Complaints waiting for a disposition" (3) is "Dispositions past the 30-day target or
  to review" (3); "N days left" replaces "Due in N days"; triage's deadline column reads "Deadline" with each market's
  role; My Work's panel "12 items need you" reads "12 reminders for you".
- **Trend check:** OrbitCare Rev B 9 against 0.96 expected, ×9.3, significant; the pressure-alarm group 6 against 0.64,
  significant; 1 signal; boards 6 and 17 groups with 1 significant each: unchanged (one group tested, so the adjusted
  chance is the raw one). Getting started's trend card: "up from 3.3 before · 3.3×" -> "up from 3.3 a month before ·
  3.3× the earlier average"; its peak callout "Oct '26: 19 complaints · 5.7× the earlier average" -> "Oct '26: 19
  complaints".

### Tests

- A test that read the developer machine's date for an absence failed every night in India before 05:30; it now
  reads the organization's day. The reporting tests' complaints are aware at noon UTC, so a day count no longer
  depends on the hour the suite runs.

## [0.10.62] - 2026-11-01

On the trial maintenance line (`release/0.10`): stage 1 of the quality plan, "Safety and honesty". It removes the
defects that would lose a person's work, print the wrong characters, keep personal data, change records nobody asked
to change, or say what MDARIX does not do. It deploys together with 0.10.61.

**No migration.** The API, worker and web images change. **Operators:** a new signing error code (below), a new
environment setting (`MDARIX_SIGNUP_PER_ADDRESS_PER_HOUR`), and a script to run once at deploy with the owner's
approval (`scripts/mask_set_aside_rows.py`).

### Fixed

- **A wrong signing code no longer loses the form.** A wrong, blank or reused authenticator code at any signature
  (disposition, market assessment, first-contact check and QA review, report approval, guide approval, CAPA
  effectiveness, management review document, ready to close, lot impact, case decision, governed decision, regulatory
  document) answered 403 `MFA_REQUIRED`, the code for a sign-in that still owes its second factor, and the browser left
  for /mfa with everything typed lost. It now answers **403 `SIGNATURE_CODE_INVALID`** ("That code didn't match. Enter
  the current code from your authenticator app."); a signer without an authenticator gets **403
  `SIGNATURE_MFA_NOT_SET_UP`**. Each signing form shows the message in place and keeps what was typed; five wrong
  codes still lock signing for 15 minutes (429 `SIGNATURE_TEMPORARILY_LOCKED`), shown in place too. `MFA_REQUIRED`
  now means only an unfinished sign-in. The disposition form asks for the code before sending when the server needs
  it. Monitoring that counted `MFA_REQUIRED` on signing routes should count the two new codes.
- **PDFs print every character.** Signed documents, worksheets, the decision record, guide, lot-impact and readiness
  exports printed "?" for ≤ ≥ μ ™ € ₹ • … and Devanagari. The PDF writer now embeds Inter and Noto Sans Devanagari
  (SIL Open Font License, licence files in `reports/fonts`), so text prints and copies as written; hashes stay in a
  fixed-width font; every page has a short MDARIX brand line; long header and footer lines wrap instead of being cut.
  A document signed earlier keeps the PDF that was signed, and its hash still verifies. Known limit: Devanagari
  conjuncts show a visible virama (no shaping engine).
- **Set-aside import rows keep personal details only as placeholders.** A stored set-aside row was masked only where
  the second check flagged it ("Mr. John Smith", phone numbers, "67-year-old male at Riverside Hospital" were kept as
  sent). Every free-text value is now masked before it is stored, and a stored reason leaves out the words a check
  quoted. **`scripts/mask_set_aside_rows.py`** masks the rows stored since 0.10.56: a dry run by default (counts per
  organization), `--apply` to write, safe to run twice, one audit event `SET_ASIDE_ROWS_MASKED` per organization
  (counts only). Run it once per database that holds tenant data, at deploy, with the owner's approval.
- **Identifiers are read as identifiers.** `serial_number` and `udi` are checked as identifiers (a ten-digit serial is
  not a phone number); a UDI may start with "+" (HIBC) or "(" (GS1); a valid GTIN-14 is never a card number; product,
  family, component, supplier and site names are never read as a person's name ("Dr Trust BP monitor"). Every
  personal-data refusal quotes the words it found.
- **A re-upload changes only what its file holds.** A file without the lot, version, date or status column blanked
  those fields and reopened closed complaints (and reset CAPAs and investigations to open). Now a column the file
  leaves out, or a blank status, keeps the stored value, and "updated" counts only rows that changed a field; the
  data-quality report says new, updated and unchanged.
- **A value too long for its column is refused by the check** ("Keep this to 40 characters or fewer.") instead of a
  "ready" file failing with a server error.
- **An ended trial shows the trial-ended page**, not "Access to this organization is suspended": the hourly job no
  longer suspends free trials, an organization an earlier release suspended reads as ended, and renewing an expired
  subscription (a trial extended after its end) reactivates the organization its expiry suspended.
- **An empty workspace is not "Ready".** A Readiness check with no records to read says "Not set: no records yet".

### Changed

- **Team** (trial owner): an invite refusal says which case it is (`INVITATION_PENDING`, `ALREADY_ON_THE_TEAM`,
  `ACCOUNT_IN_ANOTHER_ORGANIZATION`); a removed colleague can be invited again (the same account; they set up their
  authenticator again); removing says it ends their access; an expired invitation reads "Invitation expired", with
  Resend.
- **Who helps**: a timed-out authenticator setup says so and how to start again; /mfa, My account and the empty
  Dashboard name who helps in a trial (the person who invited you; MDARIX support for the trial owner). Pilot wording
  stays.
- **Sign-up at a venue**: up to 30 sign-up requests per network address per hour (was 5), set by
  `MDARIX_SIGNUP_PER_ADDRESS_PER_HOUR`; a rate-limit refusal says the real wait ("Please try again in 12 minutes").
  The runbook says how staff set up judges' and evaluators' trials before an event.
- **Signed text names documents, never codes**: "I have read the complaint disposition rules, MDARIX starter, version
  1" (was "I have read version disposition-starter-1"); dispositions, market assessments and guide approvals name the
  rules, markets and versions in words. Only new signatures change; stored text is never rewritten.
- **Honest words**: "Record the CAPA to raise in your QMS" wherever the trial said MDARIX opens the CAPA; a free
  trial's supplier evidence request is saved, not e-mailed (status "Saved, not sent"; pilots unchanged); AI is off in
  the trial, so My Work hides "My AI conversations" while AI is off and the case page and chapter 5 say so; no more
  "continue with your data intact" (the trial-ended page and e-mails reuse the pilot's real-data notice), "Open the
  guided investigation", "Until the communications log arrives" or "Bring in CSV files"; the pilot guide points to
  today's screens; About the sample data lists what the sample holds now; a trial's import panel and set-aside view
  say that set-aside rows are kept with personal details masked and deleted with the trial.
- **Website**: supported markets read "US, EU/NI, GB and India (MvPI worksheet)" (Canada only as a reporting-window
  template); "Available today" no longer claims workflow roles and customer administration for the free trial (they
  are "In a pilot") and adds what shipped (routine close and logged calls, the US and India report worksheets,
  decision guides, the communications log, reminders and oversight, lot impact in the free trial); AI items read
  "Planned, after evaluation"; the older "your systems stay the record" wording is gone.
- Tests found stale and corrected: the sample import run's 44 rows (SAMPLE-RV-10 is added after it, so the code was
  right), the change-impact lot list (lots 006 to 008 since 0.10.61), the standards catalog count (CFR803_19 since
  0.10.59), the PDF dash test.

## [0.10.61] - 2026-11-01

On the trial maintenance line (`release/0.10`): lot impact on a case (T-G5, MVP G5, with G26's lot genealogy in
cases), in the free trial only: a pilot does not see it until the MVP plan schedules G5 (owner decision, 1 Nov 2026).
Once a signal is confirmed, the case answers "what else is out there?": every lot that shares the suspect part, how
many units it released, where they went and how many are still in stock. MDARIX lists; it recommends no recall and no
other field action, and the person decides any field action in the QMS. Still to come (MVP 1.1): the field action
itself (G13), field safety notices, consignee acknowledgements, Part 806 and FSCA drafts, and date ranges as a factor.

**Migration, expand-only:** `tr08lotimpact`, chained from `tr07oversight`: one new table (`lot_distributions`) with
tenant row-level security, and two new columns with defaults on `investigation_scope_versions` (`excluded_lots`,
`lot_impact`). The table is in the trial's retention list, sample removal, purge and export, and the legacy-plane
step. No existing row changes; the downgrade drops only what it added. On `mvp-1.0` the forward merge adds a merge
revision joining its head and `tr08lotimpact`. The API and web images change.

### Added

- **Distribution import** (Import data › Distribution): lot, consignee, country, units and ship date, with the
  consignee type and reference if the export has them. A consignee is an organization (a hospital, a distributor, a
  clinic); names of people are refused, as personal data is in every import. Countries are two-letter ISO codes;
  units are whole numbers of at least one. A row for a lot not loaded is set aside with its reason (0.10.56's
  set-aside rows, lineage and data-quality report); a lot whose units shipped exceed its units released is flagged in
  the data-quality report, never refused. A re-upload of the same shipment (lot, consignee, country, ship date)
  updates it. A pilot's import screen does not offer it.
- **Lot impact on a case** (Investigations › Scope, its own "Lot impact" section; one click from the case summary):
  the person chooses the suspect factor: a component lot (from the lot genealogy import), a supplier (a recorded
  supplier of a part the genealogy names) or a product version. MDARIX suggests the one most of the case's lots share
  and says why; the person chooses. MDARIX lists every lot that shares it, lots with complaints first (with their
  complaints and complaints per 1,000 units released), then lots without complaints yet, each with its units
  released, shipped by country and consignee, still in stock, and the genealogy row behind it. A lot with no
  distribution imported says "Distribution not imported", never zero units. Totals: lots, complaints, units released,
  shipped and in stock, and units shipped by country.
- **Leaving a lot out** needs a reason (at least 10 characters). "Keep this list with the case" writes a new version
  of the case scope: its lots become the lots kept, with the lots left out and their reasons; the scope view and its
  version comparison show them.
- **The signed list**: a person who signs decisions, reviews quality or approves regulatory content signs the kept
  list with password and authenticator code (the list read must be the list signed). The snapshot is kept, frozen,
  with a new version of the case scope and its signature manifestation and SHA-256 checksum. When the records change
  afterwards (a complaint, a shipment, a lot's units), the list shows "Changed since signed" and what changed; the
  person signs again if that is the list to keep.
- **Export** (data.export): the signed list, or the kept list as the records show it now, as a PDF and a CSV (one row
  per shipment), marked "Practice record" in a trial.
- **Trial insights**: "What do lots 003 and 004 have in common?" now reads the lot genealogy: both were built with
  the same sensor lot.
- **Sample data** (marked Sample, covered by sample removal; added once to earlier trials by
  `scripts/refresh_trial_story.py`): OrbitCare 300 Rev B's pressure sensor (NovaSense Components) comes from sensor lot
  NS-SL-2417 (Sample) in lots 003 and 004, the two lots with most pressure-alarm complaints, and in three new lots
  without complaints (006, 007, 008); lot 005 used NS-SL-2533 (Sample). Each lot also names its control board lot.
  Shipments go to fictional hospitals and distributors in India, the US, Germany, France and the Netherlands, with
  units still in stock; lot 008 has no distribution imported. The sample's distribution import run sets one row aside
  (a lot not loaded) and flags a PulseWatch lot that shipped 410 of its 400 units.

### Changed

- **Sample counts**: the sample has 18 lots (was 15); OrbitCare lot 005 releases 60 units (was 150) and lots 006 to
  008 30 each, all made the same day as lot 005, so Rev B still releases 450 units on the same days: the trend check's
  units in the field, the OrbitCare rise and its signal are unchanged (a fresh trial on 0.10.60 and on 0.10.61 gives
  the same trend board and signal), as are the 43 complaints. Lot 005's complaints per 1,000 units in Trial insights
  read 33.3 (was 13.3).
- A row set aside from a file other than complaints no longer offers "Triage": only a complaint can be one.
- Import data offers Distribution after Lots in a trial and says "Show only the first N data types".
- The tests carry the case scope's two new columns and the trial's new cleanup tables.

## [0.10.60] - 2026-11-01

On the trial maintenance line (`release/0.10`): reminders and escalation (T-G25, MVP G25), the Quality and Regulatory
Oversight view (T-G9, MVP G9), and the event owner, stage, closure readiness and event decision record (T-G28, MVP
G28), built once on the trial line for the trial and the pilot alike (D-T14). A deadline never passes silently: an
alert tells people in MDARIX and never closes or changes the item; no e-mail is sent about it in this release.
MDARIX never closes a complaint and never decides. Still to come: e-mails for alerts, the full
6.0 tiers (T1's half and three-quarter points, repeats every 4 hours or daily, T2's out-of-hours route), the head of
QA's deputy and named third contact, the weekly oversight sign-off (T22), decision record versions after a reopening,
and the QMS import of the closure.

**Migration, expand-only:** `tr07oversight`, chained from `tr06guidescomms`: four new tables (`oversight_settings`,
`user_absences`, `due_alerts`, `event_closures`), each with tenant row-level security, in the trial's retention list,
sample removal, purge and export, and the legacy-plane step. Nothing existing changes; the downgrade drops only these
tables. On `mvp-1.0` the forward merge adds a merge revision joining its head and `tr07oversight`. The API, worker and
web images change; the scheduler runs a new job, `due-alerts`, every 15 minutes.

### Added

- **Reminders and escalation**: every item with a date is read from its own record: the triage target (24 clock
  hours), an urgent intake's provisional reporting deadline, a market assessment's deadline whose report is not
  started, each report obligation not yet met, each reply due on the communications log, a guide version waiting for
  its second person (end of the next working day), and every My Work task with a due date. Before the due time (24
  hours by default) its owner is reminded; while the owner is away, their backup is. At the due time it escalates to
  the backup (the absent owner's, or the triage record's own) and to the people holding the organization's escalation
  role (Leader by default); a person already told is skipped; when nobody else can be reached, the owner is told so.
  An item with no owner, or whose owner can no longer sign in, goes to the escalation role at once. Alerts resolve
  themselves when their item is done; each escalation is in the audit trail (`DUE_ITEM_ESCALATED`).
- **My Work and the bell**: a panel above My Work's tabs lists escalations and overdue items one by one and groups the
  items due soon by kind, each opening where it is done, with read state ("Mark read", "Mark all read"). The bell in
  the header counts the unread ones.
- **Absences**: a person records their own absence (first and last day, the colleague who covers it, a note) and ends
  it with "I am back". The backup receives the reminders and escalations; ownership stays, and the backup gains no
  signing right.
- **The working calendar** (time zone, working weekdays, holidays) with the reminder hours and the escalation role,
  set by quality review or regulatory approval. MDARIX's own due times count on it: a first-contact follow-up, the
  QMS-complaint task and the QA review (0.10.57), a request's reply due date and the one-working-hour rule of S4
  (0.10.59). This replaces the UTC stopgap of 0.10.59. An authority's legal deadline keeps its own counting rule.
- **Readiness › Oversight**: one place for the head of QA/RA: tiles for overdue, due soon, events not ready to close,
  decision records not filed and complaints closed in the QMS before they were ready; every dated item with its kind,
  product, market, owner (and who covers while they are away), due time and hours left, and who it escalated to;
  filters by product, market and kind; CSV export (data.export) for the monthly product review; who is away; a
  staffing warning when only one person can receive alerts. IDs, owners, dates and states only, never patient or
  reporter data. CAPAs from the QMS with a due date are listed and raise no alert.
- **The event**: each complaint MDARIX has worked on has an event owner (named here, else the triage record's), a stage
  line read from the records (triage, market assessment, investigation, decision, ready to close, closed in the QMS; a
  summary, never a gate), a summary (product, market, awareness, nearest deadline, unresolved questions, next action)
  and a closure checklist: triage complete; the first-contact check signed; every relevant market assessed and signed,
  no reassessment open; every report obligation met; the disposition or the investigation decision signed; every
  information request answered or closed; no task on the event open. Open CAPAs are listed and do not block. Each open
  item says why and opens where it is resolved.
- **Ready to close in the QMS**: signed by the event owner with password and authenticator code (never an
  administrator): with the checklist clear, or with a written reason when items are still open. The checklist is kept
  as signed; a change afterwards shows "sign again".
- **The event decision record**: every signed decision on the event (first-contact check, triage, each market
  conclusion with its versions, the disposition, the investigation decision, report approvals, ready to close), each
  with the printed name, the date and time and the meaning, and a SHA-256 checksum; as a PDF to file in the QMS
  complaint record; then the QMS filing reference is recorded. Until then the event shows "decision record not filed".
- **Sample data** (marked Sample, covered by sample removal; added once to earlier trials by
  `scripts/refresh_trial_story.py`): the MDARIX sample author away for a week with the trial user as backup; SAMPLE-RV-08
  (not ready to close: its US assessment unsigned, the reporter's reply overdue and escalated, no decision) and
  SAMPLE-RT-03 (a service-level close whose checklist is clear) owned by the trial user. No complaint is added: the
  sample's counts (43 complaints) and the OrbitCare trend are unchanged.

### Changed

- Readiness has two tabs: Inspection checks (as before) and Oversight. The menu line reads "Inspection checks,
  oversight". The number of inspection checks is unchanged (11).
- The tests carry reviewed exemptions for a person's own alerts and absences.

## [0.10.59] - 2026-11-01

On the trial maintenance line (`release/0.10`): the organization's own decision guides (T-G15, MVP G15) and the
external communications log (T-G30, MVP G30), built once on the trial line for the trial and the pilot alike (D-T14).
A guide points to a conclusion; a person confirms or overrides it and signs. MDARIX never decides, never submits and
never sends anything to an external contact. Customer-defined conclusion logic, "not reportable on current evidence"
with its re-confirmation and end state (set 5), the first-contact guide on the same engine (G32), the customer's own
harm-severity scale and the oversight view (G9, 0.10.60) stay for later.

**Migration, expand-only:** `tr06guidescomms`, chained from `tr05authorityreports`: four new tables
(`decision_guide_versions`, `external_parties`, `communication_entries`, `communication_settings`), each with tenant
row-level security, in the trial's retention list, sample removal, purge and export, and the legacy-plane step.
Nothing existing changes; the downgrade drops only these tables. On `mvp-1.0` the forward merge adds a merge revision
joining its head and `tr06guidescomms`. The API and web images change.

### Added

- **Complaints › Decision guides**: each market's guide (US, EU/NI, GB, India) with the version in use and its
  history. Version 1 is MDARIX's starter, read-only. "Start a new version" copies the version in use into a draft:
  reword any question, its definition, its help text and its clause; give it its basis from the standards list; add
  extra questions (recorded and printed with the answers, never required, never part of the conclusion) and reorder
  them. The questions that drive the conclusion cannot be removed, and their conclusion logic stays fixed.
- **The publish gate**: every question needs its regulation clause and its basis; every version has test cases (a set
  of answers and the outcome it must point to: reportable, with its report type when given; not reportable; pending
  information; a blank answer is Unknown, never No). The starter versions ship with their tests. A version is sent for
  approval only when its tests pass on its current content; the results are kept with it.
- **Approval**: a colleague who did not edit the version (never an administrator) approves it with password and
  authenticator code; that publishes it. Assessments started afterwards use it; ones in progress keep theirs; each
  signed conclusion names its guide version. What a signer must have read (practice training) is the version in use.
- **Export for an audit**: a version as PDF and DOCX, with every question, its clause and basis, the test cases and
  their results, and the approval manifestation.
- **Complaints › Communications**: every message sent to or received from a reporter, distributor, hospital or service
  partner: direction, party, time, purpose (information request, update, response), owner, reply due date, every
  attempt (when, how, which contact, what happened, when it was logged), status (open, answered, unresolved after
  attempts, closed), evidence references and the QMS record ID of a formal response or field safety notice. Each party
  has a primary and a second contact; after the organization's number of unanswered attempts (default 3, a setting) a
  request moves to the second contact, then shows "unresolved after attempts". The reply is recorded as its own
  entry. Each message counts as recorded in MDARIX when logged before sending or within one working hour (S4).
- **Unknown answers raise a request**: a market assessment saved with an Unknown on a question that drives the
  conclusion raises one request to the reporter per market; a first-contact follow-up (0.10.57) is now also a request,
  linked to its dated task, which the request finishes with the same outcome. Follow-ups recorded earlier keep working.
- **Where open requests show**: the owner's My Work (a "Reply due from an external contact" task, overdue when the
  reply is late), the new Readiness check "Requests to external contacts", and the case's Decision Brief. Links from a
  complaint's market assessment and report open its log.
- **Sample data** (all marked Sample, covered by sample removal; added once to earlier trials by
  `scripts/refresh_trial_story.py`): US-v2, the sample organization's own US guide (its help text on the three
  serious-injury parts and a VMSR question, 21 CFR 803.19), approved by the sample approver and in use; a draft US-v3
  whose own test fails ("outcome unknown: expected not reportable"); a request to SAMPLE-RV-08's reporter for the
  patient's outcome with two unanswered attempts, overdue and owned by the trial user; an answered distributor question
  on SAMPLE-RV-03; a hospital request on SAMPLE-RV-01 unresolved after three attempts to each contact. No complaint is
  added: the sample's counts and the OrbitCare trend are unchanged.

### Changed

- The standards catalog adds 21 CFR 803.19 (starter text). Readiness has 11 checks (was 10).
- The tests carry the reviewed exemptions for the report worksheet reads of 0.10.58 (as on `mvp-1.0`).

## [0.10.58] - 2026-11-01

On the trial maintenance line (`release/0.10`): the report worksheets for the US (Form FDA 3500A, 09/2025 edition,
for eMDR) and India (the MvPI Medical Device Adverse Event Reporting Form, Version 1.2) (T-G2c, MVP G2c), and the
obligation lifecycle with its approved snapshot and complete submission record (T-G2b, MVP G2b), built once on the
trial line for the trial and the pilot alike (T-B11). MDARIX never submits: a person enters the report in the
authority's route and records what was done. India's Rule 26 licensing-authority notice comes later (D-T18); the
EU/NI and GB worksheets come with MVP set 5. Retention under D-10, G33's routing, the emergency route and the
QMS-ready package stay on `mvp-1.0`.

**Migration, expand-only:** `tr05authorityreports`, chained from `tr04intaketriage`: four new tables
(`report_obligations`, `report_snapshots`, `report_submissions`, `report_evidence`), each with tenant row-level
security, in the trial's retention list, sample removal, purge and export, and the legacy-plane step. Nothing
existing changes; the downgrade drops only these tables. On `mvp-1.0` the forward merge adds a merge revision joining
its head and `tr05authorityreports`. The API and web images change.

### Added

- **Complaints › Reports**: every report a market assessment says is owed (reportable, or pending information with
  its provisional deadline), nearest deadline first, with its state and next step. The path reads Triage, market
  assessment, worksheet, second-person approval, marked submitted.
- **The worksheets**, in each authority's section and field order as printed on the official forms: Form FDA 3500A
  (sections A to H; C and F are not filled by a device manufacturer) and the MDAE form Version 1.2 (primary
  information, reporter details, device category, sections A to F). Every field shows its value, where it came from
  (complaint, product, lot, market assessment, classification, case, CAPAs, triage record, registration, responsible
  party, IMDRF mapping) and its status: from record, entered by a person, confirmed, or missing (must have before
  submission, may be unknown in an initial report, follow up later). H6's device problem codes are the approved IMDRF
  mappings of the complaint's problem code (T-G2a). Patient and reporter fields keep their place: the sample shows
  fictional values; for any other data they read "Enter in the authority's route" and cannot be entered (T-B9).
  MDARIX never fills a judgement (the association, the root cause). Field order and mappings are starter text.
- **The lifecycle (G2b)**: draft; approved snapshot; submitted, acceptance pending; accepted (or submitted, no
  acknowledgement expected); follow-up due; complete. "Ask for approval" freezes the worksheet as a snapshot; a
  second person approves it with password and authenticator code, never the preparer, never the signer of the market
  conclusion and never an administrator (D-T19: enforced in the trial as in G2b). The submission is recorded at once:
  route, time, the submitted content (a file or a note) and the difference review (a material difference needs the
  draft reopened and approved again). Evidence follows as it arrives: FDA's Ack1 to Ack4, the MvPI e-mail, a reference,
  an acceptance, a rejection or a bounce. A receipt is not acceptance; an accepted initial report records the filing
  on the signed conclusion and settles the market on the reportability watch. A rejection returns the obligation to
  draft, "correction required", with its original deadline. A request for information after acceptance creates a
  separate response obligation with its own deadline. The follow-up after a submission follows G2b's decision table
  rows 1 to 4 (shown, no reminders until G25).
- **Exports**: the worksheet as PDF and DOCX, a working draft or an approved snapshot exactly as frozen, with the form
  version, "DRAFT - MDARIX NEVER SUBMITS", the starter-text mark, the practice-record label in a trial, every field's
  status and source, and the approval manifestation (21 CFR 11.50).
- **Entry points**: "Open the report worksheet" on a signed US or India conclusion; "Report worksheet" on the
  reportability watch; "Next: assess per market" and "Its reports" on a triage item; Getting started's "After a
  conclusion" card (not a chapter); the trial guide and the in-app user guide.
- **Sample data** (all marked Sample, covered by sample removal; added once to earlier trials by
  `scripts/refresh_trial_story.py`): SAMPLE-RV-09 gets a signed US conclusion and a finished 3500A report, approved by
  the sample approver, submitted by eMDR on day 27 and accepted (four sample acknowledgement files); a new complaint,
  SAMPLE-RV-10 (PulseWatch 410 Rev A, India, a probe burn reported four weeks after the event), gets a signed India
  conclusion and an MDAE report whose e-mail bounced: "correction required". India is enabled in the sample's own
  reporting windows. SAMPLE-RV-06 still waits for the trial user; its 3500A worksheet opens once its US conclusion is
  signed.

### Changed

- On a US or India market with a worksheet, the filing is recorded by the submission record: the direct "Record the
  filing" is refused there (EU/NI and GB keep it).
- The sample has 43 complaints (was 42) and four reporting windows (was three); the routine path signs "not
  reportable" for India too. OrbitCare 300 stays the only rising trend (RV-10's event is older than 30 days).
- `## [0.10.57]` is dated 2026-11-01, the day it was released.

## [0.10.57] - 2026-11-01

On the trial maintenance line (`release/0.10`): the first-contact check (T-G32, MVP G32), urgent intake with the
awareness rule and the triage flag (T-G19, G19), and duplicates with import history (T-G20, G20), built once on the
trial line for the trial and the pilot alike (T-B11). They behave as the MVP items; the trial's differences are its
data source (an Excel/CSV upload or the sample), its three seats (T-B8), practice records (T-B5) and starter text
(T-B6). Undoing a link after signed work (G20 set 5), reminders (G25) and the communications log (G30) are not in it:
until T-G30, a follow-up with the reporter is a dated task.

**Migration, expand-only:** `tr04intaketriage`, chained from `tr03amergemvpimports`: five new tables
(`intake_events`, `first_contact_checks`, `triage_records`, `record_links`, `record_field_changes`), each with tenant
row-level security, in the trial's retention list, sample removal, purge and export. Nothing existing changes; the
downgrade drops only these tables. On `mvp-1.0` the forward merge adds a merge revision joining its head and
`tr04intaketriage`. The API and web images change.

### Added

- **Complaints › First contact**: Log a call (the caller's words verbatim, product, lot or serial number, what was
  asked for, the times with their time zone) and the starter first-contact guide's ten questions
  (`first-contact-starter-1`, starter text). G32's outcomes table, fixed in code, gives complaint, service only, both,
  pending, or pending: confirm no deficiency. Unknown and Not stated are never No; "service only" is offered only by
  the table's row 2 and no override reaches it. The coordinator signs the classification (password and authenticator
  code): complaint or both raise the QMS-complaint task; service only needs a written reason and goes to the QA review
  (every service-only call in the trial; due in 5 working days, 1 when a fault or harm word matches); pending raises a
  dated follow-up with the caller. A reviewer who disagrees reclassifies it as a complaint, with the call's awareness
  time; the record shows "same person" when the reviewer signed it too. An imported inquiry or service record gets
  the same check from the second look (First-contact check), and its signed outcome is the second-look decision.
- **Urgent intake**: a complaint by definition, on the triage list at once, its QMS-complaint task raised. The times
  are kept apart (event, first knowledge by a distributor or service agent, receipt, awareness, arrival in MDARIX).
  Without an awareness time the clock runs from the earliest of first knowledge and receipt, shown as "Awareness
  unresolved: deadline provisional".
- **Complaints › Triage**, before every other queue (and the tab Complaints now opens on): urgent intakes, flagged
  calls, flagged imported complaints not yet taken up, and set-aside import rows that suggest harm (TA-R14.2). The
  flag reads death, serious injury, a malfunction, a patient involved with the outcome unknown, a serious severity,
  first-contact questions 4 to 6 and MDARIX's starter harm words (`harm-words-starter-1`, with "pt" and "ICU"; a
  directly negated mention such as "no harm" does not count). Both clocks: the 24-hour triage target from arrival in
  MDARIX, and each enabled market's provisional deadline from awareness in the shortest plausible category (MVP 5.1b,
  `provisional-starter-1`, shown as conservative). The triage record: severity, event owner, triage owner, a backup
  where there is a second person, the immediate action or why none is needed, and the confirmed awareness time.
  **Escalate to triage**, with a reason, from the second look, the backlog, dispositions, the reportability watch,
  rows set aside at import and first contact.
- **Possible duplicates** across uploads, the sample, calls and urgent intakes (same product and lot or serial number,
  events within 2 days, same site or country): link into one event or dismiss, with a reason; undo a link with a
  reason, its history kept. A link uses the earliest awareness of its sources: "Awareness conflict" on the triage list
  until a person confirms the time, and the reportability watch and market clocks recount from it ("an earlier linked
  source"). A link to an imported complaint closes the call's QMS-complaint task.
- **Import history**: re-uploading a complaints file keeps each field's change (before, after, the import), shown in
  that run's data-quality report (`GET /api/v1/intake/changes`). A QMS complaint ID entered by hand on a call shows
  "Awaiting import confirmation" until an upload brings it; then the call is linked and the task closed.
- **Getting started**: "Before a complaint: the first call and triage", with Log a call and Triage list. Not a
  chapter: the chapter count stays ten.
- **My Work**: the follow-ups, QMS-complaint tasks and QA reviews (`FIRST_CONTACT_FOLLOW_UP`, `QMS_COMPLAINT`,
  `SERVICE_ONLY_REVIEW`) open Complaints › First contact.
- **The sample** (`backend/app/trial/sample_intake.py`): SAMPLE-CALL-01 (an IFU request: service only, signed, QA
  review due), SAMPLE-CALL-02 (a battery shutdown during a patient transfer with a repair: both, signed nine days
  ago, its QMS complaint never linked, triaged), SAMPLE-CALL-03 (a loan monitor, harm unknown, "pt": pending and
  flagged), SAMPLE-CALL-04 (nothing wrong said, nothing asked: pending, confirm no deficiency) and SAMPLE-URG-01 (free
  flow at set-up, "pt" moved to "ICU", no awareness time). SAMPLE-CALL-02 and SAMPLE-RT-05 are the likely duplicate
  pair: linking them moves RT-05's awareness eight days earlier. No complaint, product or lot is added: every count
  quoted elsewhere stays, and OrbitCare stays the only rising trend. `scripts/refresh_trial_story.py` adds it, once,
  to running trials; removing the sample removes it.
- API: `/api/v1/intake` (guide, list, log, detail, check, sign, review, follow-up, QMS, from-complaint, duplicates,
  links, changes) and `/api/v1/triage` (list, escalate, record). Not part of `mvp-1.0`'s `_PILOT_API` gate.
- The in-app user guide and the trial guide describe the first call, urgent intake, triage and duplicates.

### Changed

- The set-aside rows' harm words are the one starter list of triage (`import_quarantine.HARM_WORDS` reads it).
- Complaints opens on Triage; the routine path stays chapter 1 and Dispositions stays one click away.

## [0.10.56] - 2026-11-01

On the trial maintenance line (`release/0.10`): the MVP's governed import (R14 stored quarantine, R16 row lineage, R17
data-quality report) and its regulatory reference data (G2a: UDI-DI and GMDN on products, IMDRF codes) come to the
free trial's Excel/CSV import path, with the screens a trial user sees. Ported from `mvp-1.0` (6072cdd, e753040,
da4a71a, 8ace582, 4549323, c01c277); the trial and the MVP now behave the same once the data is in. The pilot feature
set (R08) is not part of it.

**Migrations, expand-only:** `md49signinggrants` (table `signing_grants`), `md50importquarantine`
(`import_quarantine_rows`), `md51importlineage` (`import_lineage`), `md52regulatoryreference` (`products.udi_di`,
`gmdn_code`, `gmdn_term`; `product_registrations`, `market_responsible_parties`, `imdrf_codes`,
`imdrf_code_mappings`), identical to `mvp-1.0`'s, and the empty merge `tr03amergemvpimports`, which joins them with
`tr02complaintdispositions` into one head. New tables and nullable columns only: nothing is rewritten or dropped, and
0.10.55 runs on the migrated schema. The API and web images change.

### Added

- **A data-quality report for every import** (R17), under Getting started › Your data and under Import data: the
  file's name, when and by whom; rows read, written (new and updated) and set aside; and the checks: every row
  accounted for, rows that passed every check, personal details replaced. After an import, "See its data-quality
  report" opens it; Your data opens with a link to the reports. `GET /api/v1/data/import/runs` lists the latest runs;
  `GET /api/v1/data/import/runs/{import_ref}` now also reads a free trial's runs (`TRIAL_DATA_IMPORTED`) and names the
  file (`?file_name=` on an import, last part of the path, personal data masked, recorded on its audit event).
- **The rows set aside, with their reasons** (R14), in the report: rows that suggest harm first, each with its row
  number, reasons and values, personal details stored only as placeholders such as [PERSON]. The person fixes the file
  and imports it again. A free trial now stores its set-aside rows too (`TRIAL_POLICY.quarantine`), masked as the
  workspace import stores them; the rows-to-fix download stays.
- **Where this record came from** (R16) in a complaint's disposition: the file, the row and the import, with a link
  to that import's report; on products in Import data too. `GET /api/v1/data/import/origin/{entity}/{id}` for
  products, lots and complaints, by their MDARIX id.
- **Regulatory reference data** (G2a): a complaint's disposition shows its problem code's IMDRF codes (approved links
  only; `GET /api/v1/regulatory-reference/imdrf/links`), and the complaint list's problem-code filter names them.
  Import data › Products: UDI-DI and GMDN shows each product's UDI-DI, GMDN code and term, set there by people who may
  change records (G2a's check: a GMDN code is five digits). IMDRF terms are read from the release loaded with
  `scripts/load_imdrf_annex.py`; none is typed into MDARIX.
- **The sample shows each of them** (`backend/app/trial/sample_imports.py`): the import run "Sample complaints
  export.xlsx", whose rows are the sample complaints (lineage), with two rows set aside (SAMPLE-RJ-01 no description;
  SAMPLE-RJ-02 a caller's name and phone number, stored as placeholders, a date that does not exist, and harm, so it
  lists first) and a balanced report; UDI-DI and the GMDN term on the three sample products, with "sample" in place of the GMDN code until real codes are verified; the sample's alarm and flow
  problem codes linked to IMDRF Annex A (A14, A16). Its audit record carries no created or updated counts, and no
  complaint, product or lot is added: every count quoted elsewhere stays, and OrbitCare stays the only rising trend.
  `scripts/refresh_trial_story.py` adds it, once, to running trials; removing the sample removes it.
- The in-app user guide and the trial guide say where the report is.

### Changed

- The R11 schema (`signing_grants`, its erasure with a person's personal data) comes with the migration chain, but the
  trial line does not enforce R11: a trial has one administrator, and its owner gives colleagues the trial's role.

## [0.10.55] - 2026-10-31

On the trial maintenance line (`release/0.10`): a read-only preview of the distributor and EU authorised-representative
views (requirement T-G37P, TA-37P.1 to TA-37P.3; the trial plan calls this release "0.10.54"). Trial organisations
only: the pages and their routes (`/api/v1/trial/preview/...`) answer 404 outside a free trial, and MDARIX 1.0.1 brings
the real views (G14, G37). No AI, nothing submitted, nothing saved.

**No migration.** No new table, role or sign-in: the pages read the existing complaints, dispositions, market
assessments, case scopes and signals, and every opening is an audit event (`PARTY_VIEW_PREVIEW_OPENED`). The proactive
PMS tables (`tr03`) are not in this release. The API and web images change.

### Added

- **Look ahead** (trial menu, and a Look ahead card under the last chapter of Getting started; not a chapter), three
  pages, each opening with "Preview with sample data. In a pilot, your distributor or authorised representative signs
  in separately, with MFA and an access end date (from MDARIX 1.0.1).":
  - **How a distributor reports**: the distributor's intake form filled with the submission that became SAMPLE-RT-01
    (the reporter's words, product, lot, the distributor's first knowledge, its reference DIST-REF-2231). The fields
    are read-only and Send to the manufacturer is disabled.
  - **As your distributor sees it**: for Sample Distributor Europe (Sample), only the complaints whose reporter type is
    Distributor and which it filed, each with its reference, status (received, under assessment, closed), date
    received and date of last change, and the closing note the sample released once the complaint is closed. No
    patient data, conclusion, root cause or report.
  - **As your authorised representative sees it**: for Sample EU Authorised Representative (Sample), OrbitCare 300
    and VentraLink 250 (not PulseWatch 410): every complaint with its state, dates and EU/NI assessment; a High risk
    panel (a safety or injury trigger, a harm level at or above the EU threshold, or a reportable conclusion); a
    Recurring issues panel (open signals and recurring service-level matters); and the note "The authorised
    representative is not your PRRC. It has its own PRRC (MDR Art. 11 and 15(6))."
- `backend/app/party_views/service.py`: the submitter status and the authorised representative's panels, written once
  for a product set; the preview passes the fixed sample set, G37 will pass a mandate's product set. The high-risk
  panel reuses the disposition triggers (`complaint_disposition/triggers.py`), the recurring panel the Readiness rule.
- The sample parties' submissions, the distributor's words and the released closing note are fixed constants beside
  the sample parties (`trial/sample_dispositions.py`), so running trials show the preview without a refresh. No sample
  record is added or changed: every count quoted elsewhere stays.
- Next steps' "What changes from the trial to the pilot" gains a row for distributors and the authorised
  representative; the in-app user guide, the free trial user guide and the pilot guide describe the preview.

## [0.10.54] - 2026-10-31

On the trial maintenance line (`release/0.10`): the five ready-to-use documents, signed and exported as PDF and DOCX,
with their clauses and the management review report's PMS section (requirements T-G35, T-G35.1 to T-G35.5, T-MSG's
PMS framing and the third sentence's "signed documents", T-SAM chapter 9; the trial plan calls this release
"0.10.53"). Built once for the trial and the pilot: the new routes (`/api/v1/documents`) are not part of `mvp-1.0`'s
pilot-only gate. No AI anywhere in it: MDARIX fills the data sections and never writes a judgement section; it submits
nothing.

**No migration.** A document version is a `report_jobs` row (`report_code` the template's code, `status` DRAFT or
SIGNED, `context` the period, cut-off, template version, data sections, judgement texts with their writers, the
signature and the filing reference) and its signature a `signed_approval_records` row whose content fingerprint is the
signed PDF's SHA-256; the signed PDF is kept in object storage. **New runtime dependency:** `python-docx==1.2.0` (and
`lxml==6.1.3`), pinned with hashes in `requirements.txt` (owner decision D-T5). The API and web images change.

### Added

- Records › Reports › **Ready-to-use documents**, above the governed reports; the management review report also from
  Readiness ("Management review report"), the investigation report and the risk-review extract also from a case's
  Reviews step. Each is generated for a period (or a case or a change record) with the cut-off "now"; every row opens
  the records behind it (behind a toggle), and the PDF prints their IDs per row and a source list.
  - **Management review report** (`mrr-starter-1`, ISO 13485:2016 5.6.2 and 8.2.1), extending the readiness summary
    (`readiness_home/summary.py`), with the same figures as Readiness for the period: complaints by product version,
    problem code, use environment and user type; the second look; dispositions by branch and escalations by trigger;
    vigilance by market (reportable, filed, late, not reportable on the assessment or the routine basis, pending);
    signals, the trend check and service-level trends; post-market data against the risk file; CAPAs with their
    effectiveness checks; a **PMS section** (the reactive sources from the records: complaints, service-level
    resolutions, reportable events; the loop into risk management with each risk-control answer and risk file update,
    then the clinical evaluation, the PSUR and back to the PMS plan, which stay in the QMS). Its judgement sections
    "PMS conclusion" and "Actions decided" are written by the manufacturer. Proactive sources come with 0.10.55.
  - **CAPA log** (`capa-log-starter-1`): every imported CAPA with its QMS ID, the case and complaints it came from,
    status, due date and the effectiveness check signed in MDARIX.
  - **Investigation report** (`investigation-report-starter-1`, ISO 13485:2016 8.2.2, ISO 14971:2019 clause 10): the
    case's scope by version (complaints included and excluded, versions, lots, markets, dates), evidence, hypotheses
    with their support states, the root cause as recorded in the decision, its root-cause attribution and the signed
    decision's record and fingerprint; the root-cause category is written by the manufacturer.
  - **Risk-review extract** (`risk-extract-starter-1`, ISO 14971:2019 clause 10): the case's risk reviews, the
    risk-register entries named, each risk-control answer from 0.10.53 and each risk file update with its owner and
    due date, post-market data against the risk file for the product, the impact decisions with owners and states,
    and the closure; the conclusion is written by the manufacturer.
  - **Change-impact input** (`change-impact-starter-1`): for a change record (for example SAMPLE-CHG-014) the affected
    product versions (named, or through an affected component) and their lots, the risk and PMS impacts recorded in
    risk reviews and decisions, and the complaints whose market assessments may need review; "The change itself is
    run in your QMS."
- Each template prints the clauses it serves, each "pending approval" until the consultant confirms its wording, and
  the starter-text mark; in a trial every document carries the practice-record label. A data section cannot be
  edited ("Correct the record, then generate again"). Signing (password and authenticator code, quality review)
  needs every judgement section written; the signature manifestation shows the signer, role, time, meaning, template
  version, period, cut-off and the checksums, and "Writer of the judgement sections and signer: same person" where it
  is (allowed in a trial). A signed version is never edited: a new generation is the next version, both are listed,
  and the older one shows "superseded by version n" once the newer one is signed. Each signed version takes a QMS
  filing reference and the minutes spent.
- The PDF downloaded is the signed record, byte for byte; the DOCX says "Exported from signed version … (PDF SHA-256
  …); edits outside MDARIX are not part of this record". No complaint free text appears in a document.
- The governed `RISK_IMPACT` report lists the risk-control answers and the risk file updates required.

### Changed

- Chapter 9 is "File ready-to-use documents" (it opens Records › Reports and counts a signed document; exporting the
  readiness summary or the inspection pack no longer counts).
- "MDARIX works beside your QMS" gains its last part: "…, serious ones are assessed per market, and you get signed
  documents to file in your QMS", in every place it is said. The trial guide, the user guide, the pilot guide and the
  quality manager walk-through add the PMS framing: "Post-market surveillance gathers data reactively … The results
  feed one loop: PMS → risk management → clinical evaluation → PSUR → back to the PMS plan."
- ISO 13485 8.2.1 and 8.2.2 are marked starter text in the standards catalog.
- Sample removal also removes the document versions made on sample records, with their signature records.
- In the user guide: Ready-to-use documents.

## [0.10.53] - 2026-10-31

On the trial maintenance line (`release/0.10`): the complaint disposition with its escalation triggers, the routine
path, the trend of service-level matters, the classification screens, the root-cause attribution (disposition and case
decision) and the risk-control question in the case's risk review (requirements T-G36, T-G36T, T-G36R, T-U13, T-G39,
T-G1aR and T-SAM; the trial plan calls this release "0.10.52"). Built once for the trial and the pilot: the new routes
are not part of `mvp-1.0`'s pilot-only gate. No AI anywhere in it; MDARIX submits nothing.

**Migration `tr02complaintdispositions`** (`tr02_trial_complaint_dispositions.py`, chained from tr01; expand-only): one
new table, `complaint_dispositions` (a complaint's disposition, in signed versions), with tenant row-level security,
and two nullable columns on `decisions`, `root_cause_attribution` and `attribution_reason`. No existing row changes:
the signing route requires the attribution for new signatures only. After the forward merge, `mvp-1.0` needs a merge
revision joining its head and tr02. The production upgrade takes the usual backup and 8 GB disk check. The API and web
images change. Run `scripts/refresh_trial_story.py --apply` to give running trials the routine sample complaints.

### Added

- Complaints › **Dispositions** (the first Complaints tab): open complaints in no case that are waiting for a
  disposition, newest first, each marked Routine path or Standard path, and the signed dispositions. Each opens the
  decision tree, its four questions answered in order with the branch taken and the branches refused shown:
  1. **Is an escalation trigger met?** The starter triggers have the MVP's codes and are computed from fields the
     trial already has: `SAFETY` (death; harm level catastrophic), `INJURY` (serious injury Yes, or a patient involved
     with the outcome unknown; a harm level at or above a market's threshold), `REPORTABLE` (a market concluded
     reportable; US question 5 Yes; an earlier "reported" decision), `RECURRENCE` (an open signal, or a recurring
     service-level matter, on the same product and problem code that no open case covers) and `NEW_FAILURE_MODE` (a
     problem code never recorded before on the product, not covered by an open case). Each met trigger is shown and
     kept with its field, value and record; the other branches are refused and a case opens at once through the
     existing open-case path. A trigger met at signing that was not met when the screen opened refuses the signature.
  2. **Is it a known issue?** The open cases whose scope holds a complaint with the same product and problem code, or
     the same lot. The complaint joins the chosen case's scope as a contributing complaint through a new scope version;
     no case is opened.
  3. **Resolved at service level?** The troubleshooting, the correction (part replaced, setting corrected, user
     instructed, other), what was done, its result, the service ticket and why no investigation is needed (ISO
     13485:2016 clause 8.2.2), with the **root-cause attribution**: device-related, use-related, environment-related,
     or undetermined with a reason.
  4. Otherwise **escalated by choice**, with a reason: a case opens.
- One signature (password and authenticator code) per disposition, after a practice training acknowledgement on the
  disposition rules `disposition-starter-1` and the coding criteria `coding-starter-1` (free trials only, as for market
  conclusions). A signed disposition is never edited; a change is a new version with its reason, and the earlier one
  stays visible. A signed service-level or known-issue disposition takes the complaint off the Backlog.
- **The routine path**: for a complaint not on the reportability watch, with no open or confirmed second-look flag and
  no trigger met, one screen shows the summary in the reporter's words, the basis for each enabled market ("not on
  the reportability watch"), the classification and the disposition with service level pre-selected. The one
  signature also covers a "not reportable" conclusion per enabled market, recorded under question set `ROUTINE-BASIS`;
  the signature record lists every item it covers. The hands-on time from opening the screen to signing is recorded
  and shown against the ten-minute target.
- **Classification for trends** on the disposition screen: use environment and user type, proposed from the records
  and confirmed by the signature, under the coding criteria `coding-starter-1` (shown behind "Show the coding
  criteria"). A source value off the fixed lists stays Unknown with the source value shown; nothing is guessed. A
  change of a confirmed classification needs a reason and is a new version. The trial import reads optional "use
  environment" and "user type" columns as proposals.
- Signals › **By resolution**: service-level, known-issue and escalated dispositions beside the complaint counts, by
  product and problem code, lot, use environment, user type or attribution, filtered by the classification and the
  attribution; Unknown is its own group.
- Readiness checks **Complaints waiting for a disposition** (`DISPOSITIONS_DUE`: past the backlog target, dispositions
  to review because a trigger is met after signing, and the escalations of the last 30 days for every Leader) and
  **Recurring service-level matters** (`RECURRING_SERVICE_LEVEL`: two or more service-level resolutions on one product
  and problem code within 30 days that no open case covers; starter threshold). The management review summary counts
  the dispositions by branch and lists the escalations by trigger.
- The case decision is signed only with its **root-cause attribution** ("undetermined" only with a reason), bound into
  the signature through the decision's snapshot and shown on the signed decision record. Decisions signed before this
  release show "Recorded before root-cause attribution".
- The case's **risk review** asks, for each risk in the risk file it assessed, whether its risk control worked (yes, no
  or not assessable, with a reason); a "no" and each new failure mode or hazard not in the risk file need a risk file
  update with an owner and a due date. The review cannot be completed while a finding lacks its answer. The updates
  show under Records › Risk file input as open reassessments, and as overdue after their date (ISO 14971:2019 clause
  10). The answers sit in the review's `assessed` record; no migration.
- Sample data: SAMPLE-RT-01 to SAMPLE-RT-05 (a filter re-seated on the phone, filed by Sample Distributor Europe; two
  cable-wear repairs on PulseWatch 410, the earlier one signed at service level by the sample author three weeks ago;
  an OrbitCare 300 lot 4 pressure alarm that is a known issue of SAMPLE-INV-001; a VentraLink 250 battery shutdown
  that escalates by `NEW_FAILURE_MODE` and stays on the reportability watch), with proposed classifications on them
  and on SAMPLE-RV-01 to RV-09 (SAMPLE-RT-02's "Step-down unit" stays Unknown). The sample parties "Sample Distributor
  Europe (Sample)" and "Sample EU Authorised Representative (Sample)" are fixed constants. Sample removal removes them
  and every disposition, classification and market conclusion made on them; the user's own acknowledgements stay
  until the 30-day purge.

### Changed

- Getting started has ten chapters, routine first: 1 "Close a routine complaint in minutes" (new; it counts a signed
  disposition), 2 "Assess a serious complaint per market", 3 "Recover complaints hidden as cancellations or
  inquiries", then the trend, investigation, decision (now with its root-cause attribution), CAPA, risk file (now with
  the risk-control question), inspector and own-data chapters.
- SAMPLE-RT-01 and SAMPLE-RT-05 are VentraLink 250 Rev B complaints reported late: their events were 36 and 33 days
  ago (lot 4, made 68 days ago), their awareness 2 days and 1 day ago. The trend check flags only OrbitCare 300, by
  version, problem code or type, as the trial guide, the story and the videos say; RT-01 keeps the routine path and
  RT-05 the `NEW_FAILURE_MODE` escalation on the reportability watch, with running clocks (owner decision 1,
  `tests/test_free_trial.py`).
- On the Dispositions board, a complaint whose expected branch is a known issue (an open case with the same product
  and problem code, or the same lot) is marked "Known issue" and offers "Link to the open case"; "Routine path" and
  "Close on the routine path" stay for service-level candidates, "Decide the disposition" for trigger cases (owner
  decision 7). Its disposition screen opens with the known-issue branch and the matching open case pre-selected, not
  service level; a trigger still wins.
- The free trial end-to-end journey (`frontend/e2e/trial-journey.spec.ts`) follows the ten chapters: it closes
  SAMPLE-RT-01 on the routine path (practice training, service record, attribution, one signature), opens the second
  look from its tab, and signs the sample decision with its root-cause attribution.
- In the user guide: Dispositions, the routine path, the classification, the attribution and the risk-control
  question.

## [0.10.52] - 2026-10-31

On the trial maintenance line (`release/0.10`): seriousness and causation assessed per market, the harm-severity scale,
and practice training before signing (requirements T-G15S, T-G15H, T-G40P and T-G39's shared part; the trial plan
calls this release "0.10.51"). Built once for the trial and the pilot: the new routes are not part of `mvp-1.0`'s
pilot-only gate. No AI anywhere in it; MDARIX submits nothing.

**Migration `tr01marketassessments`** (`tr01_trial_market_assessments.py`, chained from md48; expand-only): three new
tables with tenant row-level security, `complaint_market_assessments` (one market's assessment of a complaint, in
versions: a draft, then signed conclusions), `complaint_classifications` (use environment and user type; no screen yet)
and `signer_training_records`. No existing table changes. After the forward merge, `mvp-1.0` needs a merge revision
joining its head (md52) and tr01. The production upgrade takes the usual backup and 8 GB disk check. The API and web
images change. Run `scripts/refresh_trial_story.py --apply` to give running trials the new sample answers.

### Added

- Complaints › Reportability › **Assess per market**: each market the organization enabled (it entered a reporting
  window for it: US, EU and Northern Ireland, Great Britain, India) gets its own assessment; the market of the event's
  country comes first. Starter question sets `US-starter-1`, `EU-starter-1`, `GB-starter-1` and `IN-starter-1`
  paraphrase 21 CFR 803.3, EU MDR Art. 2(64)–(66) with MDCG 2023-3, the UK MDR 2002 as amended by SI 2024/1368, and
  India MDR 2017 Rules 3 and 26. Every question shows its definition and its clause and is marked "Starter text —
  awaiting regulatory confirmation: check it against your own procedure."
- The US questions ask death, each serious-injury limb on its own, caused or contributed, malfunction, and whether the
  malfunction would be likely to cause or contribute to a death or serious injury if it recurred ("recurrence is
  presumed"; a No needs its reason). The 5-work-day report (803.53) is suggested only for remedial action to prevent an
  unreasonable risk of substantial harm or FDA's written request; otherwise a reportable event gets the
  30-calendar-day report (803.50).
- Each answer is Yes, No, Unknown or Not applicable, with a rationale and the evidence relied on. The answers point to
  a suggestion: reportable (with its report type and due date from the organization's window, or the regulation's
  period when no window matches), pending information, or not reportable. **Unknown is never No**: "not reportable"
  is refused while an Unknown could make the event reportable. A person confirms or overrides the suggestion with a
  reason and signs each market's conclusion with password and authenticator code; the signed record holds every
  answer, the harm level, the scale version and the question-set version. A change is a new version; the earlier one
  stays visible. The filing reference and date are recorded on the signed conclusion once the organization has
  reported.
- The harm-severity scale `scale-starter-1`: five levels with the IMDRF Annex F health-impact terms mapped to each and
  each market's serious threshold. The complaint's quality-system severity maps to a level ("Critical" → critical); a
  different level needs a reason, and death, life-threatening harm and permanent impairment cannot be lowered. An
  answer of "not serious" at or above a threshold needs a written reason, shown on the signed record and listed under
  Readiness › Reporting clocks. The scale never answers a question or changes a conclusion.
- Practice training before signing: a market conclusion is refused until the signer has acknowledged the current
  version of the market's question set and of the scale ("I have read version …"; in a trial, a practice record). The
  screen names the colleagues who hold a current acknowledgement. A new version makes earlier acknowledgements out of
  date. This rule binds free-trial organizations only (owner decision 6, 31 October): any other organization (the
  demo, a pilot on this line) may record an acknowledgement but is not refused without one; pilots get the full rule
  (G40) later.
- The assessment form is shorter (owner decision 7): each question's definition sits behind a "Show definition" button
  (collapsed at first; the question, its clause chips and the Starter text mark stay visible), and the evidence
  checkboxes are compact, on one line where they fit.
- Signed records made in a free trial carry "Practice record: made in a free trial with sample or de-identified data.
  Not your regulatory record."
- Sample data: SAMPLE-RV-07 has a signed EU/NI assessment by the sample author (with its acknowledgements) as a
  finished example; SAMPLE-RV-08 has a saved US assessment that stays pending information; SAMPLE-RV-06 waits for the
  user; the harm complaints carry a quality-system severity. Sample removal removes them and the work done on them;
  the user's own acknowledgements stay until the 30-day purge.
- Reporting-window template "India MDR 2017: serious adverse event (15 days)", marked starter text.
- The catalog of standards gains 21 CFR 803.3, EU MDR Art. 2(64)–(66), MDCG 2023-3, India MDR 2017 Rules 3 and 26
  and ISO 13485 6.2, each marked starter text.

### Changed

- Getting started, chapter 2 is "Assess a serious complaint per market" (same position; it counts a signed market
  conclusion as well as an earlier single decision).
- The watch settles a complaint when every required market is concluded (not reportable, or reportable with the
  filing recorded); each card lists its markets. The management review summary counts signed market conclusions; the
  inspection pack's reporting-clocks file gains a Markets column.
- Single reportability decisions recorded before this release stay as they were, readable and marked "Single
  decision, recorded before per-market assessment", and still settle their complaint. No row is moved; new decisions
  are made per market (the single-decision API stays for existing data).

## [0.10.51] - 2026-10-31

Fixes on the trial maintenance line (`release/0.10`) for what was seen while recording the trial videos on 16 October.
Each was checked against 0.10.50: four had been fixed in 0.10.17, and the checks that prove it still pass. No
migration: the schema stays at md48, and no stored record is rewritten. The API and web images change. The sample
data change reaches new trials only; existing trials keep their sample as it is.

### Fixed

- Ask MDARIX, with a case chosen and the search matching none of its evidence, no longer says "0 records found for
  your question" above the case's own records, or "No relevant tenant-scoped, context-valid evidence was retrieved"
  beside them. The summary counts the records the answer shows (its Sources), "From the case records: 2 records, with
  0 recorded facts, 2 supporting evidence links and 0 contradicting evidence links, and 0 open unknowns.", and
  Limitations says "No evidence record of this case matches the words of your question, so the answer shows what the
  case records hold.", with AI and without it. Without a case, the count is the same Sources count as before.
- An Ask MDARIX answer built without AI says once why AI was not used (for example "AI is off for free trials, so this
  answer comes from your records only."); it was said twice, the second time followed by "AI suggestions are advisory;
  a person decides."
- "Set up MFA" for someone who already has an authenticator app now also says where new recovery codes are made: "Only
  need new recovery codes? Keep your app: go back, open My Account › Security and choose Generate new recovery codes."
- Platform Admin › Trials and the demo requests read "1 day left" on a trial's last day (was "1 days left"); so does
  the email that tells the MDARIX team a trial asked for a demo.
- Sample data of new trials: every complaint is on a lot of its own version, made before the event it reports.
  PulseWatch 410's two Rev B complaints were on Rev A lots 001 and 002 (now lots 003 and 005), and three OrbitCare
  300 complaints were on lots made after their event; lots 002, 003 and 004 are now made 160, 75 and 68 days before
  the trial starts (were 140, 70 and 50). Complaint counts per product and version, and per OrbitCare lot, are
  unchanged.
- Sample wording: the OrbitCare pressure-alarm rate reads "0.8 a month in the 150 days before Rev B" (it said "on
  Rev A", which over Rev A's whole life is about 0.4), in the sample decision brief and the trend summary evidence;
  and the risk-file chapter says SAMPLE-RSK-03 (VentraLink 250) was not reassessed "since the malfunction
  complaints", as VentraLink has no harm complaint.

### Checked, already fixed

- Ask MDARIX with AI switched off while a provider is configured shows "Answer built from your records (AI not used)"
  and the records the answer used, not "No matching evidence found": fixed in 0.10.17, the grounding is recorded
  before the model is asked (`tests/test_grounded_ask.py`).
- Records › Risk file input reads "1 malfunction" and "1 risk assessed": fixed in 0.10.17 (`riskFile.test.tsx`,
  `tests/test_readiness_plurals_unit.py`).
- My Account › Security (and the administrator's Security page) has "Generate new recovery codes", after the current
  password and a code from the app; the earlier codes stop working, the new ones are shown once, and the change is
  audited (`MFA_RECOVERY_CODES_REGENERATED`) and emailed. "Set up MFA" for an enrolled account shows "Two-factor
  sign-in is on" with "Replace authenticator app" instead of an error. Both since 0.10.17
  (`tests/test_mfa_self_service.py`, `twoFactor.test.tsx`).
- The sample decision brief's "Restore incoming inspection to 32 units per lot for NovaSense pressure sensors"
  pre-ticks CAPA required in the case's Decision tab: fixed in 0.10.17 (`signalAi.test.tsx`).
- VentraLink 250 stays flat in a new trial's trend check: fixed in 0.10.17 (`tests/test_free_trial.py`).

### Not changed

- A trial has no customer administrator by design: its three people are workspace users, and the trial owner looks
  after the team in Getting started › Team (invite, remove, reset a colleague's MFA, support access); MDARIX support
  resets the owner's MFA (Platform Admin › Trials). Some sentences a trial user can read still say "ask your
  administrator" (the sign-in MFA step, My Account › Access, the empty dashboard); they are noted for a wording
  release.

## [0.10.50] - 2026-10-31

Wording only, on the trial maintenance line (`release/0.10`), requirement T-MSG: one message on what MDARIX is beside
a customer's systems, in the same words on the website, in the trial workspace, in the guides and in the docs:
"MDARIX works beside your QMS or complaint software. Your QMS keeps the complaint record, CAPA and change control."
It replaces the older "your systems stay the systems of record" lines. Nothing claims a feature that is not shipped.
No migration: the schema stays at md48, and no stored record is rewritten. No API change. The web image changes; the
usual upgrade script rebuilds all images. The Caddyfile is unchanged: the new question page is a pre-rendered file.

### Added

- `/questions/does-mdarix-replace-our-qms`: Does MDARIX replace our QMS or complaint software? The answer is the two
  sentences, then what stays in your QMS, what MDARIX adds, how your data gets in (trial uploads; mapped connections
  in a pilot) and what MDARIX does today. Pre-rendered with its own title and description, listed on `/questions`,
  on Resources and in `sitemap.xml` (29 pages, 28 before).

### Changed

- Website: the home page's first point reads "Works beside your QMS or complaint software" (was "Works above QMS,
  PLM, ERP and supplier systems"); the design-partner band, the Trust page (its lead, "Not Another QMS" and "Pilot
  boundary") and the Company page ("What MDARIX is not") carry the message; Integrations reads "Work beside the
  systems you already trust"; Company › After the trial says your QMS keeps the complaint record, CAPA and change
  control.
- Trial workspace: Getting started's story, the Free trial user guide and the step-by-step user guide open with the
  message. Next steps › How the pilot starts › Work on your real complaints adds "MDARIX keeps the decisions, and your
  QMS keeps the complaint record."; How your data is connected and "Who owns the data?" say your QMS keeps the
  complaint record, CAPA and change control.
- The pilot guide (`/help/pilot-guide`) and the quality manager walk-through
  (`docs/user-guide/QUALITY_MANAGER_WORKFLOW_WALKTHROUGH.md`) use the same words.
- The message lives once, in `frontend/src/features/help/besideYourQms.ts`; `besideYourQms.test.tsx` checks every
  place says it and that the older wording is gone.

## [0.10.49] - 2026-10-25

A security fix on the trial maintenance line (`release/0.10`), requirement R11: a custom role can no longer turn an
administrator into someone who signs. Before this release a Customer Administrator could create a custom role named
"Approver", activate it and assign it to their own account; an active custom role was read before the account role,
so the signing refusal for administrators no longer saw an administrator, and the account had an Approver's
permissions. A test confirmed it on 0.10.48 (`tests/test_custom_role_escalation.py`: 8 of its 10 checks fail on
0.10.48 and pass on 0.10.49). No migration: the schema stays at md48, and no stored record is rewritten; assignments
made before this release stay, and grant nothing (the upgrade log counts them). The API and web images change.

### Security

- An administrator account keeps its administrator role: an active custom-role assignment no longer replaces it
  (`permissions.role_of_user`), so administrators never sign or approve, whatever custom role they hold. This also
  covers any assignment made before 0.10.49.
- Nobody assigns a custom role to their own account, and an assignment switched off cannot be switched back on by the
  person it belongs to (`SELF_CHANGE_NOT_ALLOWED`, as for the account role and additional roles).
- A custom role is not assigned to an administrator account (`ADMINISTRATOR_ROLE_FIXED`): administrators stay outside
  the case workflow, as with additional roles.
- A custom role is never named or coded like an administrator role, by its code or any spelling of it ("Admin",
  "Customer Admin") or by the label people see ("Platform Administrator"): creating, renaming (Administration ›
  control plane) or assigning one is refused (`ADMINISTRATOR_ROLE_NOT_ASSIGNABLE`; platform-role spellings by a
  customer administrator stay `PLATFORM_ROLE_NOT_ALLOWED`). A role named so before 0.10.49 grants nothing.

### Changed

- Administration › Users › a person › Custom roles: on your own account the assign control is replaced by "Another
  administrator must change your roles.", and on an administrator's account by "An administrator's role is set on the
  account. Custom roles do not change it." Roles already listed can still be removed.
- "What they can access now" no longer lists custom roles on an administrator's account, since they grant nothing;
  they stay under Custom roles, where they can be removed.

## [0.10.48] - 2026-10-23

Free-trial requests from personal email addresses (Gmail, Outlook, Yahoo and the other known mail providers) are
approved automatically, as company emails are (owner decision), on the trial maintenance line (`release/0.10`). No
migration: the schema stays at md48, and no stored record is rewritten. The API and web images change; the upgrade
script rebuilds all images, now stops before anything changes when less than 8 GB is free on the server's disk, and
after a successful upgrade removes old release images by name (keeping this release's and the previous one's).
Nothing is set on the server: production does not set `MDARIX_TRIAL_AUTO_APPROVE`, so it gets the new default.
`MDARIX_TRIAL_AUTO_APPROVE=company-domains` in `.env.production` and `dc up -d --no-build --wait` go back to company
emails only, without a release.

### Added

- `MDARIX_TRIAL_AUTO_APPROVE=company-and-personal`, the new default (also when the setting is unset or empty): a
  request from a company email or from a personal address at a known mail provider (`PERSONAL_MAIL_DOMAINS` in
  `backend/app/trial/auto_approval.py`, or a subdomain of one) is approved right after sign-up. `company-domains`
  (personal addresses wait for review, as before) and `off` (every request waits) work as before; any other value is
  now read as `company-domains`, so a mistyped setting never approves more.
- `MDARIX_TRIAL_AUTO_APPROVE_PERSONAL_DAILY_MAX` (default 10): personal addresses have a daily cap of their own,
  counted like the company one (the request's UTC day, every earlier personal-address request, approved or not, so a
  burst beyond it is seen by a person). `MDARIX_TRIAL_AUTO_APPROVE_DAILY_MAX` (20) now counts company addresses only;
  neither cap uses up the other. Both documented in ENVIRONMENT_VARIABLES.md and `.env.production.example`.
- A second automatic-approval account, "Automatic approval (personal email)" (`automatic-approval-personal@mdarix.invalid`,
  disabled, in the platform organization, created at the first personal approval), approves personal addresses, so
  Platform Admin › Trial requests ("Approved: …") and the audit trail (`TRIAL_REQUEST_APPROVED`'s actor) say which rule
  approved a request. Company approvals keep "Automatic approval (company email)", and earlier approvals keep their
  name. No schema change: the request records who approved it, as before.
- `/api/v1/public/site-info` `trial.auto_approval` (the setting the server runs), `trial.personal_mail_domains` and
  `trial.disposable_mail_domains`. `trial.free_mail_domains` now lists the domains whose requests a person reviews in
  the current setting (the disposable ones by default), for a sign-up page opened before 0.10.48.

### Changed

- The free-mail list is split into real providers (`PERSONAL_MAIL_DOMAINS`: the 40 entries from gmail.com to hey.com,
  unchanged) and throwaway inboxes (`DISPOSABLE_MAIL_DOMAINS`: the 11 former entries from mailinator.com to maildrop.cc,
  and 21 more of the same services' and other well-known disposable domains, such as guerrillamail.net, grr.la,
  yopmail.fr, temp-mail.io and throwawaymail.com). A disposable address always waits for a Platform Administrator, in
  every setting (`DISPOSABLE`). Subdomains match as before.
- The one-trial-per-company rule no longer reaches across a personal provider: for a personal address the rule is one
  request per address, whatever its capitals (`ADDRESS_ALREADY_HAS_A_REQUEST`), so two people with Gmail addresses
  each get a trial. Sign-up already refuses an address that has an account or a request (409), as before. Company
  domains keep `COMPANY_ALREADY_HAS_A_REQUEST`.
- The platform organization's own addresses (FUN-14) are also matched whole: a staff account's or the support
  address's own Gmail or Outlook address waits for review, without holding back the provider's other users. The DNS
  check stays for personal addresses (the providers' domains resolve; a made-up subdomain of one does not, so its
  request waits). Reserved domains wait as `RESERVED_DOMAIN` (they were `FREE_MAIL`).
- Sign-up says what happens next as the server is set. By default, under the email field: "With a company or personal
  email, the trial is approved automatically and the activation link arrives within minutes (up to a daily limit of
  new trials). Requests from disposable addresses, and any beyond that limit, are reviewed by the MDARIX team, usually
  within one business day."; before sending, for a company or a personal address: "the trial is approved
  automatically and we email you the activation link within minutes (beyond the day's limit of new trials, the MDARIX
  team reviews it first, usually within one business day)."; a disposable address gets the note "This looks like a
  disposable address. The MDARIX team reviews requests from disposable addresses, usually within one business day.
  With your company or personal email, the activation link arrives within minutes." The frame's first point reads
  "Ready within minutes with a company or personal email, isolated from every other customer." With
  `company-domains` the wording before 0.10.48 stays; with `off` sign-up says that the MDARIX team reviews every
  request.
- The website, the questions page "Can I try complaint trending on my own data without a demo call?" and the free trial
  user guide say that a company or personal email is approved automatically, up to a daily limit, and that disposable
  addresses are reviewed. The trial agreement's 1.2 says so too: "A request from a company email address is approved
  automatically, usually within minutes, up to a daily limit of new trials; so is a request from a personal email
  address, for example Gmail or Outlook, while we offer this. Other requests, for example from a disposable email
  address, from a company email domain that already has a trial or a request, or beyond that daily limit, are reviewed
  by the MDARIX team first, usually within one business day." (Last updated 23 October 2026; its SHA-256, recorded
  with each new trial request, changes.) The privacy policy and the terms are unchanged.

## [0.10.47] - 2026-10-22

Keyrings for the MFA and file encryption keys, Caddy no longer runs as root, signal titles from before grouped counts
read grouped, Platform Admin can change an account's name, and the workspace fits a 320 px phone, on the trial
maintenance line (`release/0.10`). No migration: the schema stays at md48, and no stored record is rewritten. The API
and web images change; the upgrade script rebuilds all images. What the deploy changes on the server: the release,
the images, and the owner of Caddy's two volumes (the certificates and the ACME account become the `caddy` user's, by
the new one-shot `web-volumes` job; nothing in them is moved or deleted, so the certificates are reused). The deploy
rotates no key and sets none of the new key settings: with them unset, MFA secrets and files are sealed exactly as
before. Rotating the two keys is a separate step, taken later (KEY_ROTATION.md).

### Added

- MFA and file encryption keys can rotate without re-enrolment or lost files, as the connector key can
  (`security/keyring.py`). New settings, all empty by default: `MDARIX_MFA_ENCRYPTION_KEY_ID` and
  `MDARIX_OBJECT_STORAGE_ENCRYPTION_KEY_ID` (the current key's ID, such as `k2`) and `MDARIX_MFA_ENCRYPTION_KEYS` and
  `MDARIX_OBJECT_STORAGE_ENCRYPTION_KEYS` (older keys still readable, `k1:<base64>`). With a key ID set, a new MFA
  secret is sealed as `MDARIXMFA2` and a new file written as `MDARIXENC2`, each recording its key ID, which is also
  bound into what AES-GCM authenticates (with the account, or the file's object key, as before). Values sealed before
  (`MDARIXMFA1`, `MDARIXENC1`) still open, with the current key and then with each older key, so the key in use today
  becomes `k1` at the first rotation. Without a key ID nothing changes, byte for byte in format: 0.10.46 opens what
  0.10.47 seals.
- `scripts/reseal_mfa_secrets.py` (run in the migrate job) and `scripts/reencrypt_object_storage.py` (run in an API
  container, where the files are): dry run by default, listing counts only; `--apply` re-seals each secret or file
  with the current key, checks that it opens with that key alone before it replaces the old value (a file through a
  temporary file renamed over it, keeping its owner, permissions and modification time), reports what it cannot open
  and leaves it, and exits 1 if anything was left. Safe to run again.
- The configuration check refuses a malformed key ID, a malformed older key, an ID listed twice and the current key ID
  listed among the older keys, and warns (at start and in `python -m backend.app.config_check`) while older keys are
  still loaded. `scripts/move_tenant_to_cell.py` carries the new settings to the cell. KEY_ROTATION.md's "Rotate only
  with a plan" is now "Rotate with a keyring: MFA and file encryption keys" (backup, new keys as `k2` with the old as
  `k1`, restart, dry runs, apply, check an MFA sign-in and a download, remove `k1` a week later, keep old keys while
  backups made with them are kept); documented in `.env.production.example` and ENVIRONMENT_VARIABLES.md.
- Platform Admin › Identity & Access › Platform users: **Change name**, for each account of the administrator's own
  organization, one's own included. A dialog confirms the change, says what stays the same (email address, role,
  access) and checks the name as the server does: trimmed, inner spaces as one, 1 to 120 characters, changed; the
  result shows as "Name changed to …" and in the list. `PATCH /api/v1/admin/control-plane/users/{id}` now checks a
  `display_name` the same way (`422 DISPLAY_NAME_INVALID`; it took any value before) and its `USER_UPDATED` audit event
  records the name before and after.

### Changed

- Caddy runs as the user `caddy` (uid 10002) instead of root (SEC-10), with no capability: the `web` service drops
  `cap_add: NET_BIND_SERVICE` and sets `net.ipv4.ip_unprivileged_port_start=80` in its own network namespace (the
  host's setting is unchanged), so it still listens on 80 and 443 (HTTP/3 too) behind `no-new-privileges`. Before every
  start of `web`, the one-shot `web-volumes` job (root, only the `CHOWN` and `DAC_READ_SEARCH` capabilities, no network)
  gives `/data` and `/config` to `caddy`; once they are, it changes nothing. Tested with volumes written by the 0.10.46
  image: the new image served the same certificate, as uid 10002; `docker compose run --rm --no-deps web-volumes 0:0`
  gives the volumes back to root before going back to 0.10.46 (DEPLOYMENT.md), which then served it again.
- Signals raised by the threshold rule before 0.10.44 stored their titles with the count ungrouped ("2290 complaints:
  …"). The API now shows them grouped ("2,290 complaints: …") wherever a signal's title is returned: the Signal inbox
  and a signal, its triage task in My Work, Readiness's findings and the inspection pack, the decision brief's signals
  and the case audit trail. Only titles MDARIX wrote are touched (origin `THRESHOLD_RULE`, which no one can edit), and
  only their leading count; a title a person wrote, an imported one and a suggested one are shown as written. The stored
  title is not rewritten. A search for "2,290" also finds such a signal. No email quotes a signal's title.
- `/videos`: Video 1's summary no longer names warning letters: "What MDARIX does, the post-market problems it helps
  you catch early, what the 30-day trial gives you, and the quality loop." A test checks that no website source names
  warning letters or class actions (the legal documents excepted).
- In the workspace, the eight sentences that named warning letters now name FDA inspection findings instead: the
  Complaints › Second look note, five Readiness "why it matters" lines and two Getting started steps (for example
  "Recent FDA inspection findings include complaints cancelled or logged as inquiries…"). The facts are unchanged.

### Fixed

- The signed-in workspace on a phone: the top bar ran 13 px past a 360 px screen and 53 px past 320 px (the Sign out
  button was off the screen), and the whole page scrolled sideways. Below 640 px the top bar's spacing and its icon
  buttons are tighter, and with a free trial's badge the organization's name (an icon alone at that width) is left out
  below 400 px: the page heading names the organization. Getting started also ran past 360 and 320 px: the import
  options' selects (as wide as their longest choice), the "What were you cited for?" columns (280 px at least) and a
  long action button now fit, and a panel's title and actions take two lines when needed. Measured on Getting
  started, the complaint list and the Signal inbox at 390, 360 and 320 px: the page is as wide as the screen (before:
  28 and 68 px wider on Getting started, 13 and 53 px on the others). Wider screens are unchanged.

## [0.10.46] - 2026-10-22

A domain switch: the main address of MDARIX is **https://mdarix.com**, and `mdarix.in` and the other registered
domains redirect permanently to it, on the trial maintenance line (`release/0.10`). No migration: the schema stays at
md48, and no API change. The web image changes (the Caddyfile and the website's canonical address); the usual upgrade
script rebuilds all images. Email is unchanged: mail is still sent from `no-reply@mdarix.in` through ZeptoMail, and the
support, privacy and security addresses stay `@mdarix.in` (mail for mdarix.com is not set up yet).

### Added

- `MDARIX_REDIRECT_DOMAINS` (Caddy, `docker-compose.prod.yml` passes it to `web`): other host names, separated by
  spaces, that answer on the server only to redirect permanently (301) to `https://<MDARIX_DOMAIN>`, with the same
  path and query, so `https://mdarix.in/app/cases?tab=open` opens `https://mdarix.com/app/cases?tab=open`. The names
  join the main site's address list and the redirect runs before every other handler, so a redirect name never
  reaches the pages, the API or a private site's login; Caddy obtains a certificate for each name. Empty by default
  (the site answers `MDARIX_DOMAIN` alone, as before). `MDARIX_WWW_REDIRECT=on` keeps answering
  `www.<MDARIX_DOMAIN>` as before. Documented in `.env.production.example`, ENVIRONMENT_VARIABLES.md, DEPLOYMENT.md,
  STAGING_ORACLE.md (empty on staging) and GCP_DEPLOYMENT.md section 4.1 (the switch to mdarix.com).

### Changed

- The website's own address is `https://mdarix.com`: each page's canonical and `og:url`, the share image, the
  organization and website JSON-LD in `index.html`, `sitemap.xml` (every `<loc>`), the `Sitemap` line of `robots.txt`,
  the `Canonical` of `security.txt` (its `Contact` stays `mailto:support@mdarix.in`), the question pages' JSON-LD, the
  "Page not found" description, and the address bar in the free trial user guide's pictures. The production smoke
  check expects the new canonical. The legal documents are unchanged (their text and SHA-256, recorded with each trial
  request, stay the same; the only `mdarix.in` they name are email addresses).
- The deploy for this release changes, in `.env.production` (the previous file kept as `.env.production.pre-0146`),
  after checking that `mdarix.com` and `www.mdarix.com` resolve to the server: `MDARIX_DOMAIN=mdarix.com`,
  `MDARIX_WWW_REDIRECT=on`, `MDARIX_APP_URL=https://mdarix.com` (the trusted browser origin and the address in every
  email link), `MDARIX_REDIRECT_DOMAINS` (the names among `mdarix.in`, `mdarix.net`, `mdarix.online`, `mdarix.info`
  and their `www` that resolve to the server), and `https://mdarix.com` in place of `https://mdarix.in` in
  `MDARIX_ALLOWED_ORIGINS` when it is set. If `https://mdarix.com/health/live` does not answer within about three
  minutes, it puts the previous settings back and `mdarix.in` serves as before.
- `mdarix.in` keeps working through the redirect: every old link, bookmark and emailed link opens the same page on
  mdarix.com. Sessions belong to the host they were opened on, so people signed in on `mdarix.in` sign in again on
  `mdarix.com`; activation, invitation and password-reset links already sent keep working through the redirect.

## [0.10.45] - 2026-10-22

The website's home page leads with the problem it solves, and the website has questions and answers that search
engines and AI assistants can quote, on the trial maintenance line (`release/0.10`). Website only: no migration (the
schema stays at md48) and no API change. The web image changes; the usual upgrade script rebuilds all images. The
Caddyfile is unchanged: the new pages are pre-rendered files, served as built.

### Added

- Questions and answers: `/questions` and six question pages, each pre-rendered with its own title, description and
  canonical address and listed in `sitemap.xml` (28 pages, 21 before):
  - `/questions/how-to-trend-medical-device-complaints`: How do I trend medical device complaints?
  - `/questions/when-is-a-complaint-reportable`: When does a complaint become a reportable event?
  - `/questions/post-market-data-and-the-risk-file`: How should post-market data feed the risk file?
  - `/questions/complaint-signal-vs-trend`: What is the difference between a complaint signal and a trend?
  - `/questions/show-capa-effectiveness`: How do I show a CAPA was effective?
  - `/questions/try-complaint-trending-on-your-own-data`: Can I try complaint trending on my own data without a demo
    call?

  Each page puts a direct answer of two or three sentences under the question (the page's only H1), then a short
  explanation, then what MDARIX does about it today, and links to the free trial (`/signup`) and the other questions.
  The pages that state a reporting rule or a standard (21 CFR Part 803, EU MDR Article 87, ISO 14971:2019 clause 10)
  say that they are general information, not legal or regulatory advice. Each question page carries its question and
  answer as schema.org `FAQPage` JSON-LD; `/questions` carries the list of pages as a `CollectionPage`. A JSON-LD block
  is data that no browser runs, so the CSP (`script-src 'self'`) holds, as for the organization's block in
  `index.html`. The Resources page lists the questions, the footer links to them under Company, and the header marks
  Resources on them. An address under `/questions/` that is no question gets the "Page not found" page with a 404.

### Changed

- The home page's headline leads with the problem: "See the risk in your post-market data, not just collect it.", and
  its line under it ends "Try it on your own data today, no demo call needed." The inspection-readiness section's line
  no longer names warning letters: "Eight checks shaped by what FDA inspections cite and by the EU, UK and Canadian
  vigilance rules". The sitemap's `lastmod` of `/` and `/resources` is 22 October 2026.

## [0.10.44] - 2026-10-22

Counts read with thousands separators, the complaint list's filters fit a phone, Platform Admin no longer shows an
empty panel for website demo requests, and Getting started reads less right after an import, on the trial maintenance
line (`release/0.10`). No migration: the schema stays at md48. The API and web images change; the usual upgrade script
rebuilds all images. Measured with production's limits (2 CPUs shared by the API, the background service and
PostgreSQL) on the 4,994-row test file, the database restored to the same state before every run and the runs before
and after the change taken in turn: Getting started counts the new signals 2.7 to 7 s after the import answers in
three runs of four, 13.5 s in the fourth (6 to 17 s before), and 6 to 6.5 s with the Signal inbox open in a second tab
(11.5 to 16 s before; the inbox 7.5 s, 12 s before).

### Changed

- Right after an import, Getting started's status (`GET /api/v1/trial/status`) and Automatic insights
  (`GET /api/v1/trial/insights`) read less, with the same answers (compared byte for byte on every organization of
  the review database, three of them trials with 4,993 imported complaints). The status counts the sample's records, the
  organization's own and its uploaded rows in one statement (24 before; 44 statements in all became 21). The insights
  read only the complaint columns they use, each complaint's month worked out by the database, instead of every
  complaint as a whole record (about 40,000 timestamps parsed for an import of 5,000 complaints), and answer their
  JSON as it is. On a development machine the insights take 1.1 s instead of 3.7 s and the status 0.25 s instead of
  0.4 s. Right after an import, on the bench above: the insights 2.2 to 3.7 s (3.8 to 7.1 s before, up to 13 s on a
  busier database) and the status about 2 s (1.5 to 3 s, up to 6 s).
- After an import whose signals are being found, Getting started reads its story again once the small detection status
  says they are in, not at once: that read could only say "Finding signals", and right after a large import it took
  seconds and slowed the finding itself. Meanwhile the trend chapter says "Finding signals in the complaints you just
  imported…" until the new story is in, as before. A refused status read (403) reads the story at once; the wait ends
  after two minutes in any case.
- Counts are grouped the en-US way ("2,290"), as the import result groups them since 0.10.41 (DEV-025), whatever the
  browser's language: a new rule signal's title ("2,290 complaints: unspecified problem on Aster Pump Rev C in 30
  days"), the Signal inbox's Complaints column and status counts, a signal's Complaints and its split by version, the
  trend check's counts ("2,290 against 1,204.5 expected"), the record summary of a signal, the story's and Readiness's
  findings ("4,993 complaints open in no signal or case"), Automatic insights' headline numbers and sentences, and the
  tab and chip counts of the lists. A signal's title is stored text written when the signal is raised (detection adds
  complaints to an open signal without changing its title), so signals raised before keep their titles; no stored
  title is rewritten.

### Fixed

- Complaints › Complaint list: at 390 px (and 360 and 320) the filters ran up to 49 px past their panel (120 px at
  320) and the page scrolled sideways: a select is as wide as its longest choice, and in the panel's grid the widest
  one widened the whole filter bar. On a phone (640 px and narrower) each filter now takes the panel's width, one
  under the other; the Signal inbox's filters, which ran 10 px past at 390 px, and every other list's filter bar
  (`.ca-toolbar`, `.cc-toolbar`) do the same. Wider screens are unchanged.
- Platform Admin › Identity & Access › Onboarding showed an empty "Website visitors who asked for a demo" panel. The
  website has offered only the free trial since 0.10.5, and under `MDARIX_FEATURE_SET=mvp` (production)
  `POST /api/v1/public/demo-requests` answers 404. Website demo requests are now listed only where the website offers
  them and the feature set serves their route; the website offers them under neither feature set, so the panel, its
  wording in the section's heading ("Trial requests") and its line under Identity & Access no longer show under
  `full` either. The one-to-one demo a free trial books from Getting started is unchanged and still reaches the team:
  "Free trials that asked for a one-to-one demo" shows once a trial has booked one, with Mark contacted and Close.

## [0.10.43] - 2026-10-21

Getting started shows an import's new signals sooner and recovers by itself when a reload fails, and small fixes from
the review of 0.10.42, on the trial maintenance line (`release/0.10`). No migration: the schema stays at md48. The API
and web images change; the usual upgrade script rebuilds all images, the web image with the new
`infrastructure/docker/Caddyfile`. Measured with production's limits (2 CPUs shared by the API, the background service
and PostgreSQL) on the 4,994-row test file, on the same database as the runs before the change: Getting started counts
the new signals 9 to 13 s after the import answers for one person (20 to 25 s before), and 10 to 16 s with the
Signal inbox open in a second tab (26 to 27 s before). What the story shows is unchanged.

### Changed

- Getting started's story reads less (`GET /api/v1/trial/story`): Readiness's trend check and its risk file check read
  the trend board once between them, and the backlog check counts the open complaints from a few columns and reads
  whole records only for the complaints it lists. The same story, Readiness and backlog board as before (compared on
  the 11 organizations of the review database, five of them trials with about 5,000 imported complaints); the story's
  read takes about half as long (0.9 to 0.45 s on a development machine; 2.4 to 1.0 s right after a large import) and
  the timestamps parsed per read fell from about 35,000 to 8,000.
- The workspace's "Chapter done" notice reads only which chapters were tried
  (`GET /api/v1/trial/story?findings=false`: the same chapters and next step, every finding `NOT_SET`, Readiness not
  read), every half minute while the page is in sight and once when it comes back into sight, instead of the whole
  story every half minute in every open trial page.
- While an import's signals are being found, a screen waiting for them asks the small detection status every 1.5 s
  (3 s before), and reads its data again as soon as the status says they are in. No screen starts a background read
  while its own reload is under way: right after an import, Getting started read the insights twice at once.
- The complaint list is headed like the other lists, "Complaint list · 4,993": the count after "Complaints in your
  organization" read as a stray "· 4993", it had no thousands separator, and it counts the complaints the filters
  choose, not the whole organization. The Signal inbox's count gets the thousands separator too.

### Fixed

- Getting started kept the story from before an import when reading it again failed (a server error or no answer
  while the server was busy with the import), and never read it again. A failed read for a passing reason is now read
  again after 2, 4, 8 and 16 seconds, in the background, with the last story staying on screen and no error shown
  meanwhile; a refusal (403, 404) is not retried. After the last try the story shown stays as it was, or with none
  yet the page offers Try again, as before.
- A signal's highest severity no longer depends on the order its complaints are read in: between two severities of
  the same rank (two that MDARIX does not recognise, or SERIOUS and SEVERE) the first in alphabetical order is kept.
- Verify a signature showed "Decision version of" and the signed brief's 64-character fingerprint. It now says
  "Signed version: Decision Brief DBV000001 version 1" (the report's new `version_label`), and for an older approval
  the date the decision was last changed; never the fingerprint.
- List headings showed every word capitalized ("About The Request" in Platform Admin's trial requests): a global style
  for table headings capitalized them. Every list heading now reads as written, in sentence case.
- When MDARIX support resets the MFA of a free trial's owner or colleague in Platform Admin, that person is told by
  email, as after their owner's reset, with "MDARIX support" as the one who did it (never the staff member's name;
  the reason stays in the audit trail; the time in UTC). One `TEAM_CHANGE_NOTICE` outbox event, queued with the
  reset. Before, nobody was told.
- `https://mdarix.in/404.html` answered 200; it now answers 404 like any address that is no page. Every page, the
  application under `/app` and `/platform-admin`, the email link targets and the built files still answer 200
  (checked behind the new Caddyfile in a Caddy 2.11 container).

### Documentation

- STATUS.md no longer describes "Request a demo" as the website's current flow: the website has offered only the free
  trial since 0.10.5 (`/request-demo` opens the sign-up), and the demo requests Platform Admin lists are under
  Identity & Access › Onboarding.

## [0.10.42] - 2026-10-21

An import's signals show within seconds and the workspace stays responsive while the import's follow-up work runs,
and the Signal inbox gets the complaint list's Data filter. Trial maintenance line (`release/0.10`). No migration:
the schema stays at md48. The API image changes (its command and code); the background service runs the same image.
Measured with production's limits (2 CPUs shared by the API, the background service and PostgreSQL; the local
embedding model) on the 4,994-row test file: the new signals show in the Signal inbox about 7 s after the import
answers (47 to 61 s before) and on Getting started 11 to 24 s after (73 to 127 s before); meanwhile requests answer
in 0.3 to 0.7 s at the median and 6 s at worst (0.4 to 2.2 s at the median and up to 18 s before).

### Changed

- An import's embeddings for semantic search are made by the background service instead of the API. Once the
  import's signals are found the API queues one `RECORD_EMBEDDINGS_REQUESTED` outbox event; the outbox worker embeds
  the records about 20 seconds at a time, at a lower CPU priority, each slice queueing the next, so the worker's
  heartbeat and emails never wait long. A failure is retried by the outbox (30 s, doubling, then dead-lettered and
  alerted) and never touches the import. Until the embeddings are in (about 10 minutes for 5,000 complaints on a
  2-CPU server), search finds the new records by their text and links, as before. A connector's manual sync queues
  its embeddings the same way. The scheduled embedding catch-up leaves an organization to its queued job.
- The background service has a quarter of the default CPU weight (`cpu_shares: 256` in `docker-compose.prod.yml`):
  when the API, the database and the background service all want the CPU, the API and the database come first.
- The local embedding model runs on one CPU thread (it started one per physical core of the host, which competed
  for the CPU in a container limited to fewer: 19 texts a second instead of 12 in a 1.5-CPU container).
- Signal detection links an import's complaints to their signal in a few statements instead of one per complaint
  (6.6 s to 2.1 s for the test file); it finds the same signals.
- Log lines give the real numbers of each import's follow-up work (counts and times only): "Signals after trial
  import found in 2.6 s (4993 records imported, 1 signals created, 0 updated, tenant ...)" from the API, and
  "Embeddings after trial import finished in 485.0 s, 598.7 s after the import (4993 records imported, 4996 chunks
  embedded, tenant ...)" from the background service.

### Fixed

- Right after a large import, the Signal inbox, a signal's details, Getting started's story, Readiness and signal
  detection itself could take seconds to minutes: until PostgreSQL's autovacuum analyzes the tables, its statistics
  do not know the new organization's rows, and it read every complaint of the organization for each complaint
  linked to a signal. Those reads now look each complaint up by its key (for example the inbox's list 7.2 s to
  0.06 s, the backlog check behind the story and Readiness 10.5 s to 0.02 s, in that state).
- The API no longer restarts a busy worker after 5 seconds without an answer to uvicorn's health check, which dropped
  the requests it was serving, an import among them; it waits 30 seconds (`--timeout-worker-healthcheck 30`).

### Added

- Signal inbox: a Data filter, as on the complaint list, while the sample data is there: All data, Only your imported
  data, Only the sample data. A signal's data is that of the complaints linked to it: imported when at least one of
  them is from your import (a signal mixing imported and sample complaints is your data), sample when all of them are
  from the sample; a signal without complaints shows under All data only. The Open, New and All counts follow the
  filter. `GET /api/v1/triage/signals` takes `source_system` and returns `sources`.

## [0.10.41] - 2026-10-21

Small fixes from the free-trial validation and the pre-launch review, on the trial maintenance line
(`release/0.10`). No migration: every change reads data that is already stored. The API and web images change; the
usual upgrade script rebuilds all images, the web image with the new `infrastructure/docker/Caddyfile`.
Findings: UX-25, DEV-008, DEV-010, DEV-017, DEV-018, DEV-019, DEV-024, DEV-025, DEV-027, DEV-028, NEW-5, FUN-11,
FUN-14, SEC-08, WEB-14 to WEB-18.

### Security

- Only a Platform Administrator can start a golden evaluation (`POST /api/v1/evaluations/runs`; 403
  `PLATFORM_ADMIN_REQUIRED` for anyone else, SEC-08). A run reads the synthetic golden organization in system scope
  and keeps a CPU busy for minutes, and any role allowed to run AI could start it, a free trial's Leader included.
  Platform Admin › AI Control Center › Evaluations still offers the run; the workspace's Trust page shows the
  published result only. Reading the published result is unchanged.
- A free-trial request from an address of MDARIX's own organization (the domain of a platform account or of the
  support address) is never approved automatically; a Platform Administrator reviews it (FUN-14, reason
  `PLATFORM_ORGANIZATION`).
- The website publishes `/.well-known/security.txt` (RFC 9116): contact support@mdarix.in, expiry 21 September 2027
  (UTC; renew it before then), English, and its canonical address (WEB-17).

### Fixed

- A password change counts only the other sessions that were still open: "1 other session was signed out" no longer
  counts sessions that had expired or ended after 30 minutes without activity (NEW-5). They are still closed. The same
  count is what the audit trail records for a suspension, a reset password and an MFA reset.
- Signature verification names the signer and their role, "Meera Iyer (Leader)", also when it is the person reading it
  (it said "You (Leader)"; DEV-024). The report carries `signer_name`.
- Checking an import file without a single data row is refused with 422 `IMPORT_FILE_EMPTY` and a plain message, as
  importing it already was: "The file is empty.", "The file has a header but no data rows." or, for a file whose header
  lacks the required columns (a JSON body `{}`), "Required column 'complaint_id' (for example 'Complaint Id' or
  'Complaint Number') is missing." (DEV-018). Both the trial import and the workspace import. A file with rows still
  answers its report.
- Import results group their counts: "Imported complaints: 4,993 new, 0 updated, and 1 product, 1 version and 2 lots
  they name" (DEV-025), whatever the browser's language, as do the check, the row allowance and Platform Admin's view of
  a trial's imports.
- After complaints are imported on Getting started, Automatic insights no longer shows the sample's figures ("From
  sample data · 37 complaints") while it reads the imported ones. It read them again at once, as before, but kept the
  sample's figures on screen until the answer came, and a busy server (the import's signals and embeddings are worked
  out at the same time) can take long enough for that read to time out. It now says "Reading the complaints you just
  imported… The insights update by themselves." and reads again every few seconds until they are the imported data's.
- "How MDARIX checks AI output" says why it is empty while AI is off: "AI is off for free trials, so there is no AI
  output on this case to check." The sentence was folded away under the panel's heading (DEV-010); it now shows below
  it and in the step's summary ("No AI output to check").
- "Add hypotheses by hand" opens the case's Hypotheses with the form to add one already open (DEV-019).
- Drawers, toasts and related records name a record by its MDARIX ID with its number in the source system beside it
  (DEV-008): "CMP000029 (SAMPLE-RV-01): it is a complaint", "CMP000034 (SAMPLE-RV-06): reportability decision
  recorded.", "CHG000001 (SAMPLE-CHG-014)", "CAPA000002 (SAMPLE-CAPA-02)" in a signal's related records, and the
  reportability cards show "Source ID", as the second look's cards do. A review has no source number: its ID stays
  REV000001.
- Platform Admin › Onboarding shows when the legal texts were accepted to the second in UTC, each text's full SHA-256
  fingerprint (it wraps), and who approved or declined the request and when: a Platform Administrator, or "Automatic
  approval (company email)" (DEV-027; `reviewed_by_name` in the queue).
- A Platform Admin tenant tab refused for want of the customer's approval says so: "The customer's approval is
  needed", with what to request (DEV-028). It said "Not authorized — Your role cannot read this data". The same on
  every tenant tab that reads a customer's data (AI processing, Data, Activity and the others).
- The staff alerts for a new trial request and a website demo request named "Customers & Tenants > Onboarding"; they
  name "Identity & Access > Onboarding" (FUN-11). Their button, and the trial demo and pilot request alerts' buttons,
  now open Onboarding itself (`/platform-admin/onboarding`) instead of the Platform Admin home.
- Generated column headings read acronyms as acronyms: "MFA enrolled" (was "Mfa enrolled") in Platform Admin ›
  Identity & Access › Platform users, and AI, API, SSO, CAPA, UDI, URL and others wherever a list offers a field.

### Added

- Complaints › Complaint list has a data filter while the sample data is there: "All data", "Only your imported data"
  and "Only the sample data" (DEV-017; `sources` in `GET /api/v1/complaints`). The signal list has no such filter: a
  signal has no source of its own.
- Help in a trial workspace offers "Talk to us about the next step", which opens Next steps: from trial to pilot
  (UX-25; it was the entry "Next steps").
- "Finding signals" right after an import on the dashboard's Signal triage ("Finding signals in the complaints you
  just imported… The counts update by themselves when they are ready.") and on Readiness's trend check, as Getting
  started and the Signal inbox already did (`detection_pending` in `GET /api/v1/triage/summary` and
  `GET /api/v1/readiness`; the same light status read every 3 seconds, as background reads, for two minutes at most).
- A Platform Administrator's changes to a paying organization's administrators are emailed as an administrator's are
  (follow-on to NEW-2): suspending or restoring a Customer Administrator tells them and the organization's other active
  Customer Administrators, adding one tells the others (the invitation is its own email), and an MFA reset tells the
  person (and the administrators, for an administrator account). The one who made the change reads "MDARIX support",
  never the staff member's name: "MDARIX support suspended your MDARIX account for Northwind Infusion Systems",
  "MDARIX support suspended Ben Okafor, a Customer Administrator of Northwind Infusion Systems" (Changed by: MDARIX
  support), "If you did not expect this, contact support@mdarix.in." Nothing for a free trial, for MDARIX's own
  accounts or for an erasure. The same `TEAM_CHANGE_NOTICE` outbox events, retried per recipient.

### Changed

- The website's availability labels are "Available today", "In a pilot" and "Planned" everywhere (WEB-14): the
  capability labels said "With design partners" and the roadmap's badges "Live now", "Next" and "Planned". The
  sentences that named the stage say "in a pilot" (for example "Answers written by AI come in a pilot, once AI is
  validated and switched on."), and so do the roadmap's title ("Roadmap: available today, in a pilot, planned") and
  descriptions. "Design partner" still names the customers MDARIX builds with.
- "ProductVersion" is written "Product Version" in the website's menus and "product version" in its text (WEB-15).
- The website answers an address that is no page with its "Page not found" page and a real 404 status (WEB-17); it
  answered 200 with the application shell. Pre-rendered pages, files, the application (`/app`, `/platform-admin`),
  sign-in and account screens, the guides, former page addresses, `/api` and `/health` are served as before. The page
  is pre-rendered at build time (`dist/404.html`, never indexed). `/favicon.ico` is the site's icon (16, 32 and 48 px).
- The website's skip link no longer shows a 2 px edge above the page until it is focused (WEB-16). Its focus ring is
  dark teal on light grounds (at least 6.6:1) and bright teal on the navy panels (at least 7.7:1); it was bright teal
  everywhere, 1.6:1 on the light grounds (WEB-18). The legal pages' sections are headings of the second level under
  the page title (they jumped from h1 to h3), with the same look.

## [0.10.40] - 2026-10-21

Team-change emails for pilot organizations, retried team and support-access emails, and an import that answers
before its signals are found, on the trial maintenance line (`release/0.10`). No migration: the emails use the
existing outbox (`outbox_events`, its JSON payload) and the "finding signals" state is read from the existing audit
trail and signal rule rows. The API, worker and web images change; the usual upgrade script rebuilds all images.
Findings: NEW-2, NEW-4 (follow-up).

### Added

- A paying organization's people are told by email when a Customer Administrator changes their account (NEW-2), as a
  free trial's colleagues already were: removed ("Ada Fernandes removed you from MDARIX for Northwind Infusion
  Systems"), invitation withdrawn, suspended, active again (with a Sign in button), role changed (the role before and
  now, or the workflow and custom roles added and removed) and authenticator removed. Each says who made the change
  and when, in UTC. The words follow the trial's emails, without trial wording. An administrator's reason for an MFA
  reset stays in the audit trail, never in an email.
  - When the change concerns an administrator account (the person is a Customer Administrator, becomes one or stops
    being one), the organization's other active Customer Administrators are told too ("Ada Fernandes suspended Ben
    Okafor, a Customer Administrator of Northwind Infusion Systems": who, whom, when, a Review the users button). So
    is inviting a Customer Administrator. The administrator who made the change gets nothing.
  - The invitation names the administrator who sent it ("Ada Fernandes invited you to MDARIX for ..."). It is still
    sent at once, with its link, as before.
  - Covered: Customer Administration › Users (status, base role, workflow roles, custom roles, MFA reset, invite and
    reactivate) and the user edit (`PATCH /admin/control-plane/users/{id}`). Nothing for a free trial (its own emails
    stay), for a change made by or to an MDARIX staff account, or for an erasure.
- Outbox event `TEAM_CHANGE_NOTICE` (`backend/app/team_notices.py`): one event per email, with ids and codes only.

### Changed

- Team emails are retried (NEW-2). A free trial's team emails (colleague removed, invitation withdrawn, MFA reset:
  to the colleague, the owner and the MDARIX team) were sent once after the answer and only logged when the mail
  provider refused them. They and the new organization emails are now outbox events, queued with the change and
  delivered by the worker with its usual retries (about five hours, then a dead letter and an alert). Each email is
  its own event, so a failed address is retried alone and nobody gets an email twice. The wording is unchanged.
- Support access emails are retried per recipient. In 0.10.39 the owner's and the colleagues' emails about one
  access (approved, ended) were one event, so a retry after one colleague's address failed sent the owner's email
  again. Each recipient's email is now its own event (`recipient_user_id`), for the request too; a recipient who is no
  longer a decision maker or member when it is sent gets nothing. The emails are unchanged. Events queued before
  this release are delivered as before.
- An import answers before its signals are found (NEW-4 follow-up). Signal detection ran inside the import, so the
  browser waited for it, and for the insights the answer carried, after the records were saved. It now runs after
  the answer, as the embeddings already did, in a session of its own bound to the organization (row-level security
  as before; a failure is logged and the next scheduled run catches up). The answer no longer carries the insights:
  Getting started reads them from `GET /api/v1/trial/insights` at once, as it already did. Locally, in the browser,
  with the 4,993-row `ft-complaints-4994.csv` (two runs each, on the same machine and database): on Getting started
  the import result shows after 16 to 18 s instead of 31 to 32 s; the signals show in the story after 45 to 46 s, as
  before (43 s). With the Signal inbox opened as the import answers, the result shows after 11 to 18 s instead of 17
  to 31 s, and the signals after 26 to 37 s (27 to 64 s before). Detection itself takes 13 to 17 s after the answer;
  the time until the signals show is unchanged because the screens read them again while the background embeddings
  run.
  - The import result says "MDARIX is now finding signals in these complaints: they show in Signals in a moment."
    (`signals: "FINDING"` in the answer).
  - Until they are found, the Signal inbox says "Finding signals in the complaints you just imported…" and the
    story's trend chapter in Getting started reads "Finding signals in the complaints you just imported…" instead of
    a count. Meanwhile they ask a small status read every 3 seconds (`GET /api/v1/triage/detection`, one at a time,
    as background reads that do not keep the session alive, for two minutes at most), then read their data once more
    and show the signals without a reload (`detection_pending` in `GET /api/v1/triage/signals`, `signals_pending` in
    `GET /api/v1/trial/story`).
  - "See it on your own data" is ticked by the imported complaints, so as soon as the import answers, as before.
  - Both imports (`/api/v1/trial/imports/{entity}` and `/api/v1/data/import/{entity}`) work this way. A connector
    sync still detects signals at once.

## [0.10.39] - 2026-10-21

Full support access for free trials (NEW-1, owner decision 19 October: after the launch), on the trial maintenance
line (`release/0.10`). No migration: the new area and the new emails need no schema change. A new scheduler job
(`support-access-expiry`) runs in the existing scheduler container.

### Added

- Platform Admin › Customers & Tenants › Trials has a **Support access** column. **Request support access** opens the
  usual request form, pre-filled with the trial, the signed-in administrator, Quality records, People and Audit trail
  (read only, 4 hours) and a reason to complete. Full export and Configuration are ticked on purpose only. The column
  then says where the request stands ("waiting for a second MDARIX approval", "waiting for the trial owner", "Open to
  you until ...").
- A **read-only workspace** for Platform Admin (**Open read-only workspace**, on a trial whose owner approved access
  for you). Every page carries the banner "MDARIX support, read-only, access granted by <owner> until <time>". It
  shows only the pages of the areas granted: complaints, investigations, decisions and data imports (Quality records),
  the team (People), the audit trail (Audit trail), and the trial's chapters. Nothing in it can change the trial's
  data.
  - The server enforces it, not the screen (`backend/app/support_workspace.py`): GET routes only
    (`/api/v1/platform-admin/tenants/{id}/support-workspace[/complaints|investigations|decisions|imports|team|audit]`),
    each behind the customer-approved grant for its one area (403 `CUSTOMER_APPROVAL_REQUIRED` without it, audited as
    `SUPPORT_ACCESS_REFUSED`). Each answers named fields only: never a password, an authenticator secret, a recovery
    code, a token or a session. Platform staff have no session in the trial, so no workspace route acts on its data.
  - Each page read is a `SUPPORT_ACCESS_USED` event in the trial's own audit trail, with the address read.
  - `GET /api/v1/platform-admin/support-workspace/access`: where support access to each organization stands, for the
    Trials column.
- **Export data** in the read-only workspace, under a Full export grant. It is the organization's full export that
  Customer Administration already makes (`/platform-admin/tenants/{id}/exports`: credentials left out, a current
  authenticator code where MFA applies). Asking for it and downloading it are both checked against the grant and
  audited (`TENANT_EXPORT_REQUESTED`, `TENANT_EXPORT_DOWNLOADED` and a use of the grant); a download after the access
  ended is refused.
- A new support access area, **Quality records**: "complaints, investigations, decisions and data imports, to read"
  (`RECORDS` in `backend/app/support_access.py`). The four existing areas opened none of these records.
- The trial owner's Support access (Getting started › Team) shows each request's start, end and length, and its
  reason, and has **History**: the request, MDARIX's approval, the owner's decision, each page MDARIX support read and
  each export, and how it ended, in words, from the trial's audit trail (`GET /api/v1/trial/support-access/{id}/activity`).
- Emails to the people who decide (a trial's owner, or a customer's administrators) when an access is approved
  ("Support access to <organization> is approved", with who, until when and the areas; also a security notice) and
  when an approved access ends ("Support access to <organization> has ended": its time ran out, the organization
  revoked it, or MDARIX ended it). Outbox events `SUPPORT_ACCESS_GRANTED` and `SUPPORT_ACCESS_ENDED`.
- In a free trial, every other active member is told too (owner decision 21 October), for information only and with
  no button: "MDARIX support has read-only access to <organization>'s trial" (who, the areas, who approved it, until
  when, that each use is recorded in the trial's audit trail and that only the person who runs the trial decides) and
  "MDARIX support access to <organization>'s trial has ended". A paying customer's other users get nothing new; its
  administrators get the emails above.
- Scheduler job `support-access-expiry` (every 5 minutes): closes support access whose time ran out, writes
  `SUPPORT_ACCESS_EXPIRED` to the organization's audit trail and queues the ended email. Access itself ends at the
  second it expires, whether the job has run or not.

### Changed

- Support access for free trials is back (it waited for after the launch since 0.10.31). The trial's Getting started
  › Team shows Support access to its owner again; Request access offers free trials again; and
  `POST /platform-admin/support-access` no longer refuses a trial (`SUPPORT_ACCESS_TRIALS_LATER` and the
  `TRIAL_SUPPORT_ACCESS_ENABLED` switches are removed). The user guide describes it again.
- Who decides is checked in one place for every approval, denial and revocation (`require_decision_maker`): in a free
  trial its owner and only its owner. A colleague is refused, and so is any Customer Administrator account in a trial
  (`TRIAL_OWNER_REQUIRED`). Elsewhere, as before, a Customer Administrator.
- The email that MDARIX asks for support access now reaches a trial's owner (a trial has no Customer Administrators,
  so before it reached nobody), with a button to Getting started › Team. Customers' administrators get it as before.
- An MDARIX revocation is marked `source: PLATFORM_ADMIN` in the organization's audit trail.
- Read-only access names People as what it opens: "People: the user directory, to read", not "account recovery and
  erasure of personal data", which only a grant with changes allows. It reads so in the emails, the approve dialog
  (which now lists every area with what it covers), the lists of requests and the History (which shows what the
  request and the approval covered). With changes allowed the words are unchanged. No other area's words name a change.
- A support access History (the trial owner's, and a customer's in Customer Administration) names an MDARIX colleague
  whose account the organization cannot read "MDARIX support", never an account id, and says what each use opened.

### Legal

- Privacy policy, "How we protect it": a new paragraph on support access (who approves it, the areas, read-only unless
  changes are approved, 24 hours at most, each use in the audit trail, the emails, revocation). Its "Last updated" is
  21 October 2026, so a trial request sent from now on records the new date and SHA-256 (`legal_acceptance`); the
  sitemap's `lastmod` of `/privacy` is 21 October 2026. `legal/README.md` lists the facts. The terms and the trial
  agreement are unchanged: nothing in them contradicts it.

## [0.10.38] - 2026-10-20

A faster website on phones, keyboard access to the header menus, faster large imports, and "pilot" as the name of the
paid step after the free trial, on the trial maintenance line (`release/0.10`). No migration. The web image changes
(the build), so the web container must be rebuilt; the usual upgrade script rebuilds all images. Findings: WEB-06,
WEB-10, NEW-4, UX-09.

### Changed

- The website no longer downloads the signed-in application (WEB-06). A visitor to `/` downloaded one 2,090,800-byte
  script (562 KB compressed); it now downloads 568,902 bytes in six files (163 KB compressed), and 293 KB of
  stylesheets instead of 435 KB. The workspace, both administration consoles, the investigator screens, sign-in and
  the other account pages, the help guides and the demo request each load only on their own address
  (`React.lazy` in `frontend/src/app/App.tsx`; the signed-in application is `src/app/PrivateApp.tsx`). React is a
  script of its own, which a returning visitor's browser usually still holds after a release (`vite.config.ts`).
  - The website pages and the trial sign-up page stay in the first script, so a pre-rendered page (0.10.37, WEB-05) is
    replaced by the same page at once, with no blank or loading state in between. The application shows its
    "Checking your session" card while its script loads.
  - A screen whose script cannot be fetched (a new release replaced it, or the connection dropped) reloads the page
    once to fetch the current one.
  - The pre-render build is unchanged, and no inline script or style is added: the CSP (`script-src 'self'`) holds.
- The paid step after the free trial is called a pilot everywhere a customer reads it (UX-09): "From trial to
  pilot" in the workspace's navigation and on Next steps, "Request a pilot conversation", "Talk to us about a
  pilot", "Then a pilot on your real data." on the Company page, the free trial user guide, the pilot guide, the trial
  reminder emails ("What a pilot on your real data involves is in Next steps"), the messages of the pilot request
  form, and the Platform Admin's "Pilot requests". "MVP" stays an internal word: code, the `mvp` feature set, the
  `trial_mvp_requests` table and the `/mvp-request` API paths are unchanged.
  - The legal texts change the name only, with the same meaning. The privacy policy ("How long we keep it") and the
    free trial agreement (5.3) say "move your trial data into a pilot", not "an MVP". The trial agreement's "Last
    updated" is 20 October 2026 (the privacy policy's already was). Their SHA-256 changes, so a trial request sent from
    now on records the new versions (`legal_acceptance`, since 0.10.33). The terms of service are unchanged.
  - The sitemap's `lastmod` of `/trial-agreement` and `/accessibility` is 20 October 2026.

### Fixed

- The header menus of the website work with the keyboard in the order a reader expects (WEB-10, WCAG 2.4.3). Tab
  from an open menu's button moves to its first link; Shift+Tab from the first link returns to the button; Tab past
  the last link closes the menu and moves to the next item of the header; Escape closes it and puts the focus back on
  its button. The open menu's button names its panel (`aria-controls`) and says it is expanded. Opening a menu with
  the mouse works as before. The accessibility statement no longer lists this as a known gap, and its "Last updated"
  is 20 October 2026.
- A large import is about fifteen times faster, with the same result (NEW-4). Locally, checking and writing a free
  trial's 4,993-row complaints file took 358 s; it now takes 14 to 24 s, and a re-import that updates every row 35 s.
  In the browser, locally, the whole import with the signals and insights after it takes 37 s; on production it took
  166 s. Each row cost about 12 statements; the whole file now takes about 80.
  - The check and the import read the complaints a file names at once, not one by one, and each lot's version once.
  - The new complaints, their evidence rows, links and chunks are inserted in batches of up to 1,000 rows
    (`backend/app/db/bulk.py`), and the old links, chunks and embeddings of the records a file updates are deleted
    together (`retrieval/record_evidence.py` `upsert_record_evidences`, `EvidenceChunker.create_chunks_for_evidences`).
    A record is chunked again only when its text changed, as before. Investigations, CAPAs, changes, requirements,
    risks, failure modes and controls use the same batch. `upsert_record_evidence` for one record is unchanged.
  - The audit record, the uploaded-row count, the signals run after the import and the background embeddings are
    unchanged. `tests/test_trial_imports_0_10_38.py` imports and re-imports the same files one record at a time (as
    before) and in batches, and checks that both leave the same complaints, evidence, links and chunks.

## [0.10.37] - 2026-10-20

Search engines, and P2 findings of the pre-launch review, on the trial maintenance line (`release/0.10`). No
migration. The web image changes (Caddyfile and the build), so the web container must be rebuilt; the usual upgrade
script rebuilds all images.

### Added

- Every website page in the sitemap has its own HTML file, pre-rendered at build time (WEB-05). Its head carries the
  page's own title, description, canonical address, robots rule, `og:title`, `og:description` and `og:url`, from the
  same data the browser uses (`frontend/src/site/seo.ts`). Its body holds the page's text, so crawlers and link
  previews that run no JavaScript (LinkedIn, Slack, Teams, email) read the page itself, not the home page. `npm run
  build` now ends with `vite build --ssr src/site/prerender.tsx` and `node scripts/prerender.mjs`, which writes
  `dist/home.html` for `/` and `dist/<page>/index.html` for the 20 others, and stops the build if a page renders
  almost nothing. The web image runs the same `npm run build`.
  - The browser still mounts the app with `createRoot`, which replaces the pre-rendered markup with the same page, so
    nothing is hydrated and no mismatch can break a page. A page opened from its address keeps its scroll position.
  - The pages' inline styles become classes of one stylesheet (`/assets/prerender-<hash>.css`), since the CSP allows
    no inline style. No inline script is added; the JSON-LD block is unchanged.
  - Without JavaScript, the animated parts of the pages show complete (`/noscript.css`, linked inside `<noscript>`).
  - `/videos` lists the fourteen videos before `videos.json` answers, without calling any of them "Coming soon".
  - The privacy policy, terms and trial agreement are served live from `MDARIX_LEGAL_DIR`, so their text is not baked
    into the page: the pre-rendered page has the frame, and without JavaScript it says how to get the text.
- Platform Admin, Operations, **Problem reports** (FUN-07): every problem reported from the help menu, with its
  organization, reporter, words, page and reference, filtered by open, closed or all. **Reply by email** writes to the
  reporter; **Close** records what was done, which the customer's audit trail keeps.
- An invited colleague is greeted once, on their first screens: "Asha Rao invited you to Orbit Medical Devices' free
  trial." It closes with **Got it** and does not come back after the person's first 2 days (UX-26).
  `GET /api/v1/trial/status` names when the person first signed in and who invited them (`me`).

### Changed

- Caddy serves each website page its own file: `/` is `/home.html`, and `try_files {path} {path}/index.html
  /index.html` serves `/platform/index.html` for `/platform`. `/index.html` stays the plain application shell, with no
  page text and no canonical address, for the application, sign-in and every other address
  (`infrastructure/docker/Caddyfile`). `scripts/production_smoke.py --front-door` checks both.
- The sitemap's `lastmod` of `/privacy` is 20 October 2026.
- Privacy policy, "How long we keep it", and the data retention schedule: error reports sent before sign-in are
  deleted 90 days after they arrive (see Security). The privacy policy's "Last updated" is 20 October 2026, so a
  trial request sent from now on records the new date and SHA-256 of the policy (`legal_acceptance`, since 0.10.33).
- The feedback prompt waits until the person has had MDARIX for 2 days, and then, as before, until the trial is 3 days
  old or holds the organization's own data. A colleague invited on day 5 is no longer asked on their first screen
  (UX-26).
- Plain words where codes showed (UX-21). After a quality review the message reads "Decision Brief DBV000001 accepted
  for decision. Next: sign the decision on the Decision tab." (or "returned to its author for more evidence", and so
  on), not "DBV000001: accept for decision recorded.". The brief's Reviewers list reads "Quality review started" and
  "Accepted for decision", not "Quality · Start Review"; a risk review outcome reads "No new risk". "Established facts"
  is "What the evidence says", since its statements are often source assertions.
- A tried chapter of Getting started says "Tried", as the progress ring counts it. "Done N times" counted records: one
  import of 6 rows read "Done 6 times", and a chapter whose sample was removed read "Done 0 times" (UX-28).
- The left navigation panel reaches the bottom of the window on every page of the workspace and both consoles, at
  80%, 90% and 100% page scale (UX-14).
- The configuration check of a MULTI deployment (the one with free trials) requires `MDARIX_TRIAL_ALERT_EMAIL`. The
  alerts for a trial request waiting for review and for a trial asking to end early read only that key, so
  `MDARIX_DEMO_ALERT_EMAIL` alone left them unheard (FUN-09). Other deployments keep "one of the two". Production sets
  both, so it is not affected.

### Fixed

- Opening a case no longer logs browser console errors (UX-15). The case workspace reads the latest saved AI results
  with `?missing=empty`, and a step never run answers 200 with its field null and `persisted: false`. Without the
  parameter the routes answer 404 as before (`backend/app/saved_results.py`). Under the MVP feature set the workspace
  no longer asks for the parked counterfactuals.
- A reply to the support team's email about a problem report reaches the person who reported it: the email's
  Reply-To is the reporter, not the support address (FUN-07).

### Security

- Browser error reports sent before sign-in belong to no organization, so no purge reached them. They are now deleted
  90 days after they arrive, by the daily `trial-retention` job (`client_errors.delete_anonymous_reports`, NEW-3).
  Reports filed under an organization are deleted with its data, as before.

## [0.10.36] - 2026-10-20

P2 and P3 findings of the pre-launch review, on the trial maintenance line (`release/0.10`). No migration.

### Security

- Automatic trial approval needs the email's domain to exist: it must resolve in DNS (an A or AAAA record, looked up
  with a 2-second timeout). A domain that does not resolve, or a lookup that does not answer in time, sends the
  request to a Platform Administrator instead. The daily cap (20) now counts the day's company-email requests,
  approved or not, so made-up domains can no longer use up the day's approvals unseen (SEC-07). The new
  `MDARIX_TRIAL_DOMAIN_CHECK=off` skips the lookup on a development or test machine only; staging and production
  always look the domain up.
- The inspection pack's CSV files escape any cell a spreadsheet would run as a formula, as every other MDARIX export
  does (SEC-06; `backend/app/csv_safe.py`). The import now refuses every text that starts with `=`, `+`, `-` or `@`,
  as the export would escape it; a plain signed number such as `-5` is still accepted. Before, a `-` was refused only
  with a `(` in the first 40 characters, so `-2+3+cmd|...` went through.

### Fixed

- An extended trial gets its 7-day, 1-day and "trial has ended" emails again for the new end date. Each is still sent
  once per end date (FUN-04). Reminders sent before this release count for the end date they were sent for.
- Trial emails give the end of the trial and the earliest deletion date with the time and "UTC", for example
  "18 November 2026, 21:51 UTC": the reminders, the "trial has ended" emails and the invitations. A trial ends 30 days
  after the minute it was approved, so a bare UTC date was a day off in the Americas, and in India for an approval
  after 18:30 IST. The trial-ended page says the same (FUN-15).
- "Due in N days" on CAPA effectiveness checks and on reporting clocks counts from today where the person is. A
  90-day check planned just after midnight in India said "Due in 91 days" (validation finding DEV-020). The trial's
  "N days left" counts whole days to the end time, so it was not affected.
- Sign-up refuses an email without a dot in its domain or with two `@` (`name@company`, `x@@...`), with the same rule
  as a colleague's invitation, and a name or company that is only spaces (422 `NAME_REQUIRED` /
  `ORGANIZATION_REQUIRED`). The form takes the person back to the step with that field and shows the message
  (FUN-12).
- The trial's six import templates load in the order they are offered. The complaints template now holds the second
  complaint (`CMP-10022`) that the investigations template links, so investigations and CAPAs no longer fail
  (FUN-10).

### Changed

- The trial owner's invitation has the subject "Your MDARIX free trial is ready: activate your account" and says to
  have your phone ready for the authenticator app, as the colleague's invitation does (UX-13).
- My Account in a free trial shows no internal user or organization IDs, and no longer says to ask an administrator:
  it says to write to support@mdarix.in to change your name or email. Other organizations see it as before (UX-27).

## [0.10.35] - 2026-10-20

The P1 findings left after the free-trial launch. First release of the trial maintenance line (`release/0.10`).

### Security

- A name or organization that carries a web address, an email address or a bare domain (`secure-login.com`) is
  refused at sign-up (422 `NAME_HAS_LINK` / `ORGANIZATION_HAS_LINK`) and when a trial owner invites a colleague.
  Both names go into emails MDARIX sends to an address the requester chose, so such a name let anyone send a genuine
  MDARIX email carrying their own link (pre-launch review SEC-04; `backend/app/plain_names.py`). Dotted abbreviations
  such as "St. Jude" or "Co. Ltd" are still accepted.
- The public demo-request route (`POST /api/v1/public/demo-requests`) answers 404 under the MVP feature set: the
  website offers no demo request, and the route mailed the name a visitor typed to any address (SEC-04).

### Fixed

- Trial and subscription reminders count the days left rounded up, as every screen does: the day before the end the
  email says "ends tomorrow" (not "ends today"), and the 7-day reminder says "in 7 days" (not "in 6 days") (FUN-03).
- The welcome email no longer says that only administrators set up an authenticator app. A person whose role must
  use two-factor sign-in (trial users included) is told to have their phone ready for it at the first sign-in; anyone
  else is told nothing about it (FUN-13).
- The recovery codes shown right after setting up the authenticator can be copied or downloaded (**Copy all**,
  **Download**), as on My Account; the page no longer asks people to print them (UX-12).
- A used, withdrawn or expired activation or reset link says so as its page opens, with a link to request a new one,
  instead of showing the password form and refusing only after a password was typed (validation finding DEV-004).
  The page asks the new `POST /api/v1/auth/link-status` (`{token, kind}` → `{usable}`), which does not spend the link
  and names no account; when the check cannot be made, the form shows as before and the server still decides.

### Changed

- Website, Trust › Enterprise Administration: the "Available today" card no longer lists connections, mappings and
  plans as customer self-service; they are marked as configured with design partners (WEB-12).

## [0.10.34] - 2026-10-20

Fixes for what the free-trial validation run of 0.10.33 found (document MDARIX-FT-VER v1.0, interim).

### Fixed

- A trial page left open now signs out after the idle timeout. The "chapter done" banner reads the trial story every
  30 seconds, and every read counted as activity, in the browser and on the server, so an untouched trial page never
  timed out (DEV-006). Reads a page makes on its own now carry the header `X-MDARIX-Background: 1` (`apiClient`
  option `background`): the server answers them but neither restarts the idle window nor renews the session
  (`backend/app/request_context.py` `is_background_request`), and the browser's idle watch does not count them.
- A free trial no longer offers AI actions it cannot run. **Explain with AI** on the second-look cards,
  **Write an AI summary** on a signal, **Start from an AI draft** on the Decision Brief and **Generate AI Advisory**
  are hidden in a trial workspace (`useCanRunAi`); before, "Explain with AI" answered "No AI provider is set up yet"
  (DEV-007). The server refused these model calls for a trial either way.
- The case timeline names who superseded a decision: the entry "Decision superseded by a new decision" shows the
  signer of the decision that replaced it, not "Not recorded" (DEV-014).
- Records › **Verify a signature** works in the lightweight MVP and in free trials. It listed a case's decisions from
  the legacy Decision Center route, which the MVP parks (404 "This part of MDARIX is not offered in this
  deployment"); it now lists them from the decision screen (`GET /api/v1/investigations/{id}/decision`) (DEV-015).
  Its report shows each signature as a card with one fact per line, and names the signed outcome in words ("Accept
  with conditions", not "Accept Cond").
- A large import no longer stops waiting after 60 seconds: the page waits up to 10 minutes for a check or an import,
  so a trial's full allowance of 5,000 rows completes on screen. If it still times out, the page says that the import
  may still finish and that importing the same file again updates its rows, not that nothing was saved (DEV-016).

### Changed

- The signed decision record lists the two rules enforced when signing, read back from what was recorded:
  **Approval authority** (the decision records the approval authority the signer decided under) and **Segregation of
  duties** (the signer did not write, edit or submit the brief). A record whose signer wrote the brief verifies as
  Invalid (DEV-011).
- The meaning of a signature names the signer and the role they signed under: "I, Asha Rao, Leader (Quality Manager),
  have reviewed Decision Brief DBV000001 version 1 and decide: Accept the conclusion". The decision form shows the
  server's exact words for the chosen outcome, so what is shown is what is stored. Signatures made before keep their
  stored words; the meaning is not part of the signed fingerprint, so they still verify (DEV-011).

## [0.10.33] - 2026-10-19

### Added

- Sign-up records which legal texts a trial requester accepted, and when. Sending the request stores, with its time,
  the version of the Terms of Service, the Free Trial Agreement and the Privacy Policy the website served at that
  moment: each text's "Last updated" date and the SHA-256 of its exact text (`backend/app/site_info.py`
  `legal_versions`). The record names nobody, so it stays when the requester's personal data is erased. Platform
  Admin › Onboarding shows it under the request's answers. The consent line above **Request free trial** says that the
  versions are recorded. Migration `md48legalacceptance` adds the column `onboarding_requests.legal_acceptance`
  (nullable, empty for earlier requests; downgrade drops it).
- Invited people see the privacy policy before they activate: the **Activate your MDARIX account** page links it
  (in a new tab) and says what the account holds, and the activation and both trial invitation emails end with the
  privacy policy's address.
- An accessibility statement at `/accessibility`, linked from the footer and the legal pages: what was done, the gaps
  we know of (header menu keyboard order, focus outline contrast, legal page heading levels, burned-in video captions
  without a transcript) and how to report a problem. It claims no conformance.
- A trademark line in the website footer, the Terms (8.3) and the Privacy Policy: product names such as the
  complaint systems offered at sign-up belong to their owners, and MDARIX is not affiliated with them.
- `docs/compliance/LEGAL_DRAFTS_FOR_REVIEW.md`: drafts for the lawyer, not published, for a GDPR / UK GDPR section,
  a "not a medical device, no medical, legal or regulatory advice" clause, the contracting party and a role-based
  grievance contact, and a sanctions and export clause, each with its open questions.

### Changed

- AI stays off for free trials by a server rule, as the trial agreement, the terms and the privacy policy say. Turning
  AI on for an organization on the Free Trial plan is refused (409 `AI_OFF_FOR_FREE_TRIALS`), for its administrators
  and for a Platform Administrator, and every model request of a trial is refused whatever its switch says
  (`GENAI_OFF_FOR_FREE_TRIAL`, "AI is off for free trials during the product validation phase"). The trial's screens
  report AI as off. Platform Admin › tenant › AI shows "Free trial: AI stays off" and the **Turn AI on** button is
  disabled; turning AI off and the token allowance still work.
- Sign-up no longer lists Cuba, Iran, North Korea or Syria, and the server refuses those countries and the Crimea,
  so-called Donetsk People's Republic and Luhansk People's Republic regions, also when typed by name or sent another way
  (422 `COUNTRY_NOT_SERVED`).
- The deletion date in the trial reminder, trial-ended and ended-early emails, and on Getting started › Your trial,
  counts a grace extension and an open request to move the data into the MVP (`backend/app/trial/retention.py`
  `deletion_date`), and the emails say "Data deleted, at the earliest, on". The trial-ended screen says the same.
- The privacy policy now lists what was missing: server request logs (IP address, browser, page without its query
  string) and how long rotation keeps them; browser error reports and help-menu problem reports, and when they are
  deleted; the record of accepted texts; what is kept after a trial is deleted; and the time of last activity kept in
  the browser for automatic sign-out. The trial agreement (5.3) and the ended-early email say what is kept after
  deletion.
- The audit trail is described as it is kept: unchanged and never deleted while a customer's account exists, handed to
  the customer in the export at the end, and, for a free trial, deleted with the trial unless an export is asked for
  (privacy policy, terms 4.3, trial agreement 5.3, Customer Admin › Audit, `legal/README.md`). The "at least 7 years"
  promise is gone.
- Feedback: the texts say what a published quote is credited with (your job title and your company's name, or only
  your area of work when anonymous; never your own name), and so do the consent sentence and the choices in the
  feedback questionnaire.
- How trial requests are approved is said the same way everywhere: a company email is approved automatically, within
  minutes, up to a daily limit; personal email addresses, and requests beyond the limit, are reviewed by the MDARIX
  team, usually within one business day (trial agreement 1.2, sign-up, Company page, the acknowledgement email, the
  trial guide, the video summary).
- Passwords: "MDARIX never sees it" now reads "MDARIX stores only a salted hash of it, so no one at MDARIX can read it"
  on sign-up and in the guides.
- The home page says the eight inspection checks are shaped by what recent FDA warning letters and inspections cite
  and by the EU, UK and Canadian vigilance rules, instead of "drawn from 2026 FDA warning letters".
- The Security page and the privacy policy say which files are scanned for malware: every file MDARIX stores, such as
  evidence attachments; imported CSV and Excel files are read as data only, never stored, and macro workbooks are
  refused. Imports are still not scanned.
- The roadmap no longer lists "A dedicated database for each customer" as planned: every MVP already has a dedicated
  database run by MDARIX, and free trials share the platform (also on the Company page).
- Resources lists the FDA AI guidance under its official title, "Artificial Intelligence-Enabled Device Software
  Functions: Lifecycle Management and Marketing Submission Recommendations (draft guidance)".

### Fixed

- A legal page whose text cannot be loaded (no answer, or an error) no longer says "formal legal text pending
  approval". It says the document could not be loaded, offers **Try again** and **Email us for the text**, and keeps
  the pending summary only for a document the server reports as not provided.

The legal texts `legal/privacy.md`, `legal/terms.md` and `legal/trial-agreement.md` changed (Last updated: 19 October
2026); on the server they are live after the API restarts with the new `legal/` folder.

## [0.10.32] - 2026-10-19

### Fixed

- Free trial: trial data the organization asked to move into the MVP is no longer deleted while that is being
  arranged. While a request from Next steps that asks to move the trial data is open (new or contacted), and the data
  may still move (sample data removed, own data imported), the nightly `trial-retention` job keeps the trial and
  records `TRIAL_RETENTION_SKIPPED_MVP_REQUEST` in its audit trail. Closing the request lets the deletion resume 14
  days later at the earliest (`MVP_HOLD_GRACE_DAYS`), never the same night. The hold never lasts longer than 90 days
  after the trial ends (`MVP_HOLD_MAX_DAYS`). The MDARIX team gets an operations alert 7 days before the date the data
  would otherwise have been deleted and 7 days before the hold ends, once each (`TRIAL_RETENTION_MVP_HOLD_ALERTED`).
  Platform Admin shows the hold in Customers & Tenants › Trials, next to the request in Identity & Access ›
  Onboarding › MVP requests, and in **Delete expired trial data**, which lists held trials under "Kept for now". A
  request that does not ask to move the data, or data that cannot move, holds nothing; a legal hold works as before.
  The privacy policy (How long we keep it) and the trial agreement (5.3) say so; the retention schedule
  (`docs/compliance/DATA_RETENTION_SCHEDULE.md`) has the periods.
- Free trial: the 5,000-row allowance counts the rows of your files, as you count them. A 5,000-row complaints export
  now fits, although it also names products, versions and lots, which are added with it but are not rows. A 6-row
  file uses 6 rows, not 12. The file check says "6 rows ready to import (6 new rows of your 5,000)" and names what the
  complaints add besides. A file that does not fit says "This file adds 5,001 rows; your trial has 5,000 of 5,000 rows
  left.", with thousands separators. Getting started › Your trial › Uploaded rows and the Platform Admin trial
  overview count the same way, also for rows already uploaded. A row that only updates a record already there is not
  counted again.
- Getting started: chapter 4, **Open the guided investigation**, opens the sample case on its Workspace tab instead of
  the list of investigations (the list when the sample case is gone).
- Getting started: the first chapter's finding reads "1 of 5 records to recheck reports a death or serious injury"
  (also on Readiness), not "1 report a death or serious injury". A chapter not tried yet shows a neutral "To do" chip
  with an empty circle instead of a red cross and "Your turn".
- Signals: a signal's chart counts the signal's own complaints by product version, so it agrees with the signal (the
  sample signal showed 7 complaints for a signal of 5). Related records now include changes recorded against a
  component of the product, so the sample signal shows the supplier change SAMPLE-CHG-014.
- Decision tab: after a decision is signed, the case shows the signed decision. **Record a new decision (supersedes
  DEC000001)** is a secondary button that opens the form with the supersede explanation, and **Keep the signed
  decision** closes it again.
- Free trial sample data: the sample CAPA SAMPLE-CAPA-02 (restore incoming inspection for the NovaSense sensors) is
  opened when the trial starts, after the sample brief, and is due in 45 days with its effectiveness check 30 days
  later, instead of predating the case and being overdue. Applies to new trials.
- The **Include retired hypotheses** checkbox on a case's Intelligence › Hypotheses tab sits on one line beside its
  label instead of wrapping over three lines in a wide empty column (every checkbox in a toolbar).

### Added

- Help menu: **Watch the videos** opens the website's videos page in a new tab.

## [0.10.31] - 2026-10-19

### Added

- Free trial: when the trial owner removes a colleague, withdraws an invitation not yet accepted, or resets a
  colleague's MFA, everyone concerned is now told by email, once each, after the change is saved. The colleague learns
  who removed them (they can no longer sign in, were signed out, and what they did stays in the trial under their
  name), that their invitation was withdrawn (the earlier activation link no longer works), or that their
  authenticator was removed and they set up a new one at their next sign-in; the owner's reason for an MFA reset stays
  in the audit trail and is not in the email. The owner gets a confirmation of each change, with when, that also
  serves as a security notice ("If this was not you, change your password and contact support"). The MDARIX team gets
  a short "Trial team change" alert at the address of the MVP-request alert (`MDARIX_DEMO_ALERT_EMAIL`, else
  `MDARIX_TRIAL_ALERT_EMAIL`; none is sent when neither is set). A failed email is logged and never undoes the change.
  Platform Admin › Customers & Tenants › Trials lists each trial's latest **Team changes** under its people.
- A trial owner can reset colleagues' MFA up to 10 times a day (`team-mfa-reset:org`), like removals, so the new
  emails cannot be sent without end.

### Changed

- The Platform Admin menu no longer shows a number after each area's description (it was only the number of tabs in
  the area), and the dashboard's administration areas no longer say "N sections". The Customer Administrator and
  workspace menus had no such counts; tab counts of real work (support requests awaiting a decision, My Work) stay.
- Support access for free trials waits for after the launch (owner decision): a trial's Getting started › Team no
  longer shows Support access, Platform Admin › Security › Support access › Request access no longer offers free
  trials, and the server refuses such a request (422 `SUPPORT_ACCESS_TRIALS_LATER`, "Support access for free trials is
  not available yet."). One switch on each side brings it back (`TRIAL_SUPPORT_ACCESS_ENABLED` in
  `backend/app/support_access.py` and `frontend/src/app/featureSet.ts`). The trial's support-access API and any grant
  already made are unchanged: an open trial grant simply expires within 24 hours. The user guide no longer describes
  it.

## [0.10.30] - 2026-10-19

### Fixed

- The red confirm button in confirmation dialogs was invisible in the user workspace (white text on no background):
  for example **Remove from trial** when a trial owner removes a colleague, and every other confirmation that removes,
  withdraws or cancels something. The button was there and worked, but could not be seen. Its colour is now defined for
  every console (user workspace, platform administration and customer administration), not only the customer
  console, and a test keeps it that way.

## [0.10.29] - 2026-10-19

### Fixed

- Free trial: an invitation email that fails after a trial is approved (automatically or by the MDARIX team) is no
  longer silent. The approval stands; the request records what happened to its latest invitation (sent, not
  delivered, or email not set up) and when, and Platform Admin › Identity & Access › Onboarding shows **Invitation not
  delivered** next to **Resend invitation** until the owner activates. MDARIX sends a failed invitation again through
  the outbox (with the outbox's usual back-off, about five hours in all, then a dead-letter alert), alerts operations
  through the configured alert channels when an automatic approval's invitation fails (the request's MDARIX ID and
  the provider's error, never the address), and records `TRIAL_INVITATION_SENT` or
  `TRIAL_INVITATION_NOT_DELIVERED` in the audit trail. Migration `md47invitedelivery` adds the two columns to
  `onboarding_requests`.
- Getting started no longer stays on "Reading your trial's records…" when the trial's story cannot be read (a failed
  or timed-out request): it says the story could not be loaded and offers **Try again** and **Go to Investigations**,
  and a story already on screen stays there while it reloads.
- The sample case of a free trial now shows what MDARIX does differently: the sample author recorded by hand, with no
  AI, two competing hypotheses (the NovaSense sensors of supplier change SAMPLE-CHG-014, partially supported by the
  change record and the inspection of lots 003 and 004; and ward pressure-limit settings, which the same evidence
  speaks against), two open questions (the bench test of returned pumps; the wards' occlusion limits) and a failure
  chain with one link still unknown. The sample Decision Brief carries them as its leading and alternative hypotheses
  and open unknowns; signing the decision asks you to confirm you have read them. Removing the sample data removes
  them too. Applies to new trials.
- The sample case's progress counts its Decision Brief: "Investigation brief" reads "Decision Brief version 1: waits
  for its quality review" (and passes once the brief is approved for decision) instead of "No brief yet". The brief's
  own readiness scorecard no longer lists the brief and the decision as pending checks about itself. The sample case's
  owner shows as "MDARIX sample author", never as an address on sample.invalid (existing trials too).
- Ask MDARIX without AI answers the natural trial question. A question about lots, versions, a rise, harm, problem
  codes or countries gets the same fixed-rule answers as Getting started › Automatic insights, with their tables, next
  to the evidence the search found; the sample case's evidence is found from the first minute (new trials), also with
  a version chosen in the context bar. It never shows "Live GenAI provider is not configured": a free trial reads "AI
  is off for free trials, so this answer comes from your records only". The page offers questions to try and its
  introduction is in plain words.

### Changed

- The case Workspace tab speaks plainly. System codes (NO_CAUSAL_CONCLUSION, NO_DIRECT_EVIDENCE,
  NO_RELEVANT_EVIDENCE, ...) are shown as sentences ("MDARIX does not decide the root cause", "No evidence on this
  case yet", "No further matching records"), Context Health is "Case at a glance" (evidence and linked records),
  Retrieval & Guardrails is "What MDARIX checked", and the "Deterministic Trust Engine" panel is a folded "How MDARIX
  checks AI output". The codes stay in the API and the audit trail.
- With AI off, each AI step of the case Workspace tab shows why in a few words ("AI is off for free trials") and the
  step that does the same job by hand (**Record observations**, **Add hypotheses by hand**, **Record unknowns**,
  **Build a failure chain**, **Write the Decision Brief**) instead of a greyed-out button. `GET /api/v1/ai/status`
  tells a free trial so (`trial: true`). AI stays off.
- Privacy policy, "How long we keep it", and the data retention schedule: trial requests that do not lead to a trial
  lose the requester's personal details after 90 days (see Security).

### Security

- An Excel upload can no longer exhaust the API's memory. A workbook is refused before it is unpacked when its parts
  are too many, too large (20 MB unpacked in all for a free trial, 60 MB otherwise; 5 MB for the workbook, styles and
  relationship parts) or packed more than 100 times; the worksheet and its shared strings are read as a stream, and
  reading stops at the import's row limit plus 100 rows, or at a cap on cells and XML elements. The 60 KB "zip bomb"
  of the final review (59 MB of empty cells, 1.3 GB of memory before) is refused in milliseconds with "The workbook
  is too large to read. Save the sheet as CSV UTF-8 and upload that."; a sheet with too many rows says so.
- Invitation emails are rate-limited with the existing limiter: a free trial's owner can resend an invitation 3 times
  per address per hour and 10 times per organization per day, invite 10 colleagues per person and per organization
  per day, and remove 10 colleagues per organization per day (`invite-resend:address`, `invite-resend:org`,
  `invite:user`, `invite:org`, `team-remove:org` in `backend/app/rate_limit.py`). Over a limit the API answers 429
  with `Retry-After` and a sentence the Team tab shows; no email is sent.
- Free-trial requests that never became a trial are no longer kept for ever: 90 days after a request was declined, or
  after the invitation of an approved one expired unused, the daily `trial-retention` job erases the requester's
  name, email, job title, phone and free-text goal (pseudonymized as a purge does; the organization's name and its
  answers about the organization stay) and erases the never-activated account with it. Each erasure is written to
  `erasure_log` (TRIAL_REQUEST_ERASED, re-applied after a restore by `scripts/reapply_erasures.py`) and audited as
  `TRIAL_REQUEST_DATA_ERASED` without the data. Requests still waiting for review are not erased automatically.

## [0.10.28] - 2026-10-19

### Fixed

- Website, Security page: it said the database runs on a managed service with point-in-time recovery. It now says
  what is true during the validation phase: the database runs on MDARIX's own server in Mumbai, is backed up every
  day with an encrypted copy in Delhi and a daily snapshot of the server's disk kept in Mumbai, and restoring follows a
  written, rehearsed procedure. The subprocessor list, the retention schedule and the legal notes say the same. The
  Google Cloud runbook pins the daily disk snapshots to Mumbai (`--storage-location=asia-south1`), so they stay in
  India as the privacy policy promises.
- Website, Regulations page: it said reportability decisions are "signed". Reportability decisions are recorded by a
  named person with their reason; investigation decisions are signed electronically, with re-authentication. The
  Company page and the Trust page's search description say the same.
- Free trial: a trial approved at once for a company email now has its sample signal straight away, as a trial
  approved by the MDARIX team already had; the Signal inbox (chapter 3 of Getting started) was empty for up to an
  hour.
- Signing a decision no longer ends in a dead end. While no version of the Decision Brief is accepted for decision,
  the case's Decision tab says so and offers **Review the brief first**, which opens the Decision Brief tab at its
  quality review. The Decision Brief tab now offers **Start review** (and then **Record your review**) at the top, not
  only below the whole brief, and once you accept the brief for decision it offers **Next: sign the decision**.
- Sign-up: the Terms of Service, Free Trial Agreement and Privacy Policy links open in a new tab, so reading them no
  longer erases the form.
- A colleague invited to a free trial gets an invitation of their own: "Priya Raman invited you to the MDARIX free
  trial of Lumenvia Health Devices", one line on what MDARIX is, a note to have their phone ready for the
  authenticator app, and why they receive it (the trial's owner invited them). It mentions the sample investigation
  only while the trial still has it. The trial owner's own invitation is unchanged.
- Website homepage: the worked example's numbers now add up, and the Platform pages tell the same case: 42
  pressure-alarm complaints, from about 2 to 12 a month after Rev B, 30 of them in lots 003 and 004 and 2 without a
  lot; the case is INV-031 everywhere.
- Signals: "Recurring words" no longer counts words from what a complaint says did not happen ("no patient injury
  reported" was shown as "injury (5)"), clinical outcomes (they have their own line), "returned for evaluation" or lot
  numbers.
- Free trial sample data: OrbitCare 300's sample complaints carry the problem code PRESSURE_ALARM, so the sample signal
  reads "5 complaints: pressure alarm on OrbitCare 300 Infusion Pump (Sample) Rev B in 30 days" instead of "unspecified
  problem", and Automatic insights shows PRESSURE_ALARM as the problem code that rose. Applies to new trials; existing
  trials keep their data. A case opened from a threshold signal now starts from a question such as "Why did
  pressure-alarm complaints rise on OrbitCare 300 Infusion Pump (Sample) Rev B?".
- The free trial user guide's pictures show the address mdarix.in (they showed mdarix.com).

### Changed

- Website homepage: the hero says what MDARIX is: post-market surveillance and complaint handling for medical devices,
  with complaints, reporting clocks, trend signals, investigations and CAPA in one traceable place.
- Sign-up says before you send the request what happens next: with a company email the activation link arrives within
  minutes; a personal address (Gmail and similar) is reviewed by the MDARIX team, usually within one business day, and
  the form says so as soon as such an address is typed. It also says the trial comes with sample data and that AI is
  off. The list of personal mail domains is the one automatic approval uses, published in
  `/api/v1/public/site-info` (`trial.free_mail_domains`).

### Security

- The web server refuses a request body above 1 MiB (1,048,576 bytes, HTTP 413) when the API would read it as JSON
  (Content-Type `application/json` or `application/*+json` in any case, or no Content-Type at all), before it reaches
  the API: an anonymous oversized JSON body could tie up an API worker for about 40 seconds. Uploads (multipart, CSV,
  Excel) keep the 25 MB limit. The cap leaves a wide margin: the largest JSON the application sends is a case scope,
  at most about 650 KB with every field at its limit and usually under 150 KB; inbound webhooks are already capped at 1
  MiB by the API. Scripts that post CSV to the import endpoints must send `Content-Type: text/csv`, as the application
  does. Signed packages uploaded to a platform deployment (not used yet) must stay under 1 MiB.
- A request the API cannot read (HTTP 422) is answered field by field as before, but no longer echoes the submitted
  values back.

## [0.10.27] - 2026-10-18

### Fixed

- Website: labels in the animated pictures no longer run into each other or past the edge of their cards. Since
  0.10.24 the pictures raised their smallest labels so far that, on laptops the site draws at 80% (1,100 to 1,439 px
  wide at 125% display scaling or more), some no longer fit: on the Trust page "Re-authenticated · 15:20" and "Design
  partners: after validation" ran past their cards, a citation sat on top of "Most come from lots 003–004", "Human
  review required" ran into "Always", and the "Advises only" label crowded its heading. Labels are now at least 13 px
  on screen at 100% (from 14.5 px) and at least 12 px on those laptops (the smaller pictures two to a row on Solutions
  about 10.5 px there, from 11), and every picture is laid out to hold them: the AI assurance picture puts each
  citation before its statement, the Trust picture shows "Signed · 15:20" above "Re-authenticated", the signature
  stamp on Decisions has its own space, and the tenants, audit trail, investigation context, failure chain, reporting
  windows, scenario comparison and AI lifecycle pictures were rearranged or given shorter labels with the same
  meaning. Headings and large figures in the pictures show at their intended size again, and lines drawn to a label
  stop at its edge instead of crossing the text.

## [0.10.26] - 2026-10-18

### Added

- Free trial: **Next steps** (From trial to MVP), a page in the workspace menu of every free-trial organization, for
  everyone in it (`/app/next-steps`). It explains how the trial becomes an MVP: the MVP works only with your real data,
  in a dedicated MDARIX transactional database set up only for your organization and run by MDARIX; what changes from
  the trial (data, where it lives, how it gets in, people, start, length, cost, support); how the MVP starts, in five
  steps over at least 2 to 3 weeks of setup and validation; how your systems are connected through an approved mapping
  file; the Customer Administrator; what MDARIX needs from you; the price (a paid engagement of 3 months to 1 year,
  priced in a written proposal, with a discount for design partners; no figures are shown); and common questions.
  "Download this page as PDF" prints the page without the menu and buttons, with every answer open. Next steps is
  linked from Getting started (under the story's chapters), from End your trial early, and from the Help menu during
  a trial.
- Request an MVP conversation, from Next steps: what you expect from the MVP, the products, sites and systems you have
  in mind, and, if you like, a phone number and how and when to reach you. "Move our trial data into the MVP" is
  offered only when the organization has removed the sample data and imported its own; otherwise the form says why,
  and that the trial data is deleted 30 days after the trial ends. The server refuses the move in any other case. One
  open request per organization: asking again updates it. The answer is shown on screen, and Next steps then shows
  where the request stands. The MDARIX team is emailed each request and update (`MDARIX_DEMO_ALERT_EMAIL`, else
  `MDARIX_TRIAL_ALERT_EMAIL`; no new setting) and sees every request in Platform Admin > Identity & Access >
  Onboarding (Demo and trial requests), where it marks them contacted or closed. Audited as `TRIAL_MVP_REQUESTED`,
  `TRIAL_MVP_REQUEST_UPDATED` and `TRIAL_MVP_REQUEST_STATUS_CHANGED`. Migration `md46` adds `trial_mvp_requests`, a
  tenant table under row-level security like `trial_feedback`; it holds the requester's name and email and is deleted
  with the trial's data.
- The free trial user guide (`/help/trial-guide`) has a chapter "After your trial", in the same words as Next steps,
  and its "When the 30 days are over" now points to Next steps. The pilot guide (`/help/pilot-guide`) describes the
  five steps and the dedicated database run by MDARIX.
- Website: the Company page has an "After the trial" section below the free trial's steps: an MVP on your real data,
  a dedicated database run by MDARIX, 2 to 3 weeks of setup and validation, paid, with a design-partner discount. No
  prices are shown.

### Changed

- The trial reminder emails sent 7 days and 1 day before the trial ends link to Next steps.

## [0.10.25] - 2026-10-18

### Fixed

- Help, "Report a problem" opened with no background: the form showed through the page behind it and could hardly
  be read. It now opens as a normal dialog, white, above the page.
- Help, "Getting started and import templates" did nothing when Getting started was already open. It now opens the
  "Your data" tab, where the import templates are, and scrolls to it.

## [0.10.24] - 2026-10-18

### Changed

- Website: the Platform menu is four pages and an overview instead of 19 links: Product 360, Investigations,
  Decisions and Trust (`/platform/product-360`, `/platform/investigations`, `/platform/decisions`, `/platform/trust`).
  Each page holds its capabilities as sections, and every capability carries one of the roadmap's three labels,
  Available today, With design partners or Planned, with a line on what that means in the product today. The Product
  360 screen, the product reality graph, counterfactual analysis and the three AI capabilities (AI Challenger, AI
  Assurance, AI Provenance) are With design partners: the free trial reads products through Readiness, Complaints and
  Signals, and AI is off during the trial. The 19 former `/platform/<capability>` addresses, and the former
  `/platform#<section>` links, open the matching section of the page that now holds it.
- Website: the roadmap ("Know what is available today, and what comes next") has its own page, `/roadmap`, in the
  Product Lifecycle menu and the footer. Its first live item is now "Products, versions and lots"; the Product 360
  screen is listed under With design partners.
- Website: the standards ("Built around the evidence regulators ask for") have their own Regulations page,
  `/trust/regulations`, in the Trust menu and the footer, with the FDA, EU MDR, UK and Canada reporting windows and
  their basis from the standards catalog.
- Website: the home page is shorter (about 830 words and 5,500 px at 1,440 px wide, from 2,137 words and 11,335 px):
  the hero, the inspection checks, one worked example (the OrbitCare 300 Rev B pressure-alarm investigation, which
  replaces three overlapping story sections), "Your systems stay the record", a short trust strip with one line
  linking to the Regulations page ("Covers FDA, EU MDR, UK and Canada reporting"), and the closing call to action with
  what the free trial includes.
- Website diagrams are legible: no diagram or SVG label renders below 14 px on a 1,440 px screen (some were 6 to 10
  px), and every label has at least 4.5:1 contrast with what is behind it. A drawn scene raises its smallest labels to
  suit the size of its frame, scene pictures are drawn wider (two to a row on Solutions, one at a time on Resources),
  and coloured and muted labels use darker shades. The product reality graph, the cross-functional investigation and
  "Your systems stay the record" have an Enlarge button that opens them full-screen (Escape or Close returns to the
  button).

### Fixed

- The Contact page no longer says "Contact details are being configured" while it is loading, or when the server
  cannot be reached: it shows nothing while loading, falls back to the published support@mdarix.in and
  privacy@mdarix.in when the server is unreachable, and shows the notice only when the server answers with neither
  address.
- Website on a phone: an open menu (Platform, Solutions, Product Lifecycle, Trust) showed only its title; it now
  shows its links, and closing the menu closes it too.

## [0.10.23] - 2026-10-18

### Added

- The regulatory basis of every report and finding, from one catalog (`backend/app/standards.py`, mirrored for the
  web app in `frontend/src/features/shared/standards.json`; a test keeps the two identical): 26 clauses, sections and
  articles of ISO 13485, 21 CFR 820 (QMSR), 803 and 11, the EU MDR, ISO 14971, IEC 62304, IMDRF, the UK MDR 2002 and
  SOR/98-282, each with its short form, title and jurisdiction. Wherever a basis is shown, the page or report says
  once: "MDARIX organizes the evidence these ask for; it does not certify compliance. Your quality system and its
  validation stay yours."
- Readiness: each inspection check returns its `basis` and shows it as small chips under "Why it matters" (hidden
  complaints: ISO 13485 8.2.2 and 21 CFR 820.35; late reports: ISO 13485 8.2.3, 21 CFR 803.50 and 803.53, EU MDR
  Art. 87; trends without action: ISO 13485 8.4 and EU MDR Art. 88; CAPAs without a verified effect: ISO 13485
  8.5.2; risk file input: ISO 14971 clause 10; backlog and harm closed without an investigation: ISO 13485 8.2.2;
  signals past their triage date: ISO 13485 8.4).
- The management review summary (PDF and `GET /api/v1/readiness/summary`) names each check's basis and the reporting
  windows' basis, and ends with "8. Standards referenced": the standards the report uses, with title and jurisdiction.
  The PDF writer now prints en and em dashes and typographic quotes instead of a question mark.
- The inspection pack's `00-README.txt` lists the basis each file supports and the standards referenced;
  `02-inspection-checks.csv` has a Basis column.
- Reporting windows: each template carries its basis (FDA: 21 CFR 803.50 and 803.53; EU: EU MDR Art. 87; Great
  Britain: UK MDR 2002; Canada: SOR/98-282 ss. 59–61), kept by a window started from it and shown in Complaints ›
  Reporting windows and beside the window's name on each Reportability card. Windows saved before this release take
  their template's basis while they keep its name; a window entered by hand has none. No schema change: the basis is
  stored with the windows.
- Signals › Trend check and Records › Effectiveness checks name their basis (ISO 13485 8.4 and EU MDR Art. 88; ISO
  13485 8.5.2).
- The signed record of a decision, a signed CAPA effectiveness round and the signature verification screens say:
  "Records, as 21 CFR 11.50 and 11.70 call for, the date and time of signing, its meaning, and a link to the exact
  record signed." The signer is recorded by their account and their name is read from the user directory when the
  record is shown, so the sentence does not claim the name.

### Changed

- The trial's "What were you cited for?" themes and the sample data story take their references from the catalog
  where it has the exact entry (for example "ISO 13485 8.2.2; 21 CFR 820 (QMSR)"), and keep their wording where it
  has none (21 CFR 803 as a whole, ISO 13485 8.3 and 5.6).

## [0.10.22] - 2026-10-17

### Changed

- The website and the application are drawn smaller on laptops at 125–150% display scaling, where they looked
  oversized at 100% browser zoom: at 80% on screens that give the browser 1,100–1,439 px of width, and at 90% at
  1,440–1,799 px, as browser zoom would draw them. Only mouse-driven, high-density screens are scaled; phones, tablets,
  standard-density laptops and wide desktop screens are unchanged. Full-height panels (the app menu, the sign-in
  page) still fill the window, and dragging a list's column edge still follows the pointer.

## [0.10.21] - 2026-10-17

### Changed

- Website: every page now has the sign-in pages' backdrop (a very light med-tech photo under a white wash, fixed while
  the page scrolls); cards, the header and the navy panels sit on top of it. The signed-in application is unchanged.
- Website: the 45 photo illustrations are replaced by animated scenes drawn on the page (`frontend/src/site/scenes/`),
  each showing the idea of the text beside it with the illustrative OrbitCare 300 story: page heroes on a navy stage,
  section and card pictures on a light one, and simpler versions for the home page's small step frames. Each scene
  animates once as it scrolls into view, with at most a gentle loop, and is shown still for people who ask for reduced
  motion; its accessible name is the former picture's alt text.

## [0.10.20] - 2026-10-17

### Added

- Search engines and link previews. Each website page has its own title and description in the words medical
  device teams search with (complaint handling, post-market surveillance, MDR reportability, CAPA), its canonical
  address and an index rule (`frontend/src/site/seo.ts`); `/robots.txt` opens the website to crawlers and keeps
  sign-in, account screens, the application and the API out; `/sitemap.xml` lists the 14 public pages; the home page
  carries Organization and WebSite structured data (no personal name or address) and a 1200×630 share card
  (`/og-image.png`) for LinkedIn, email and chat previews. Sign-in, account and application screens, and the "not
  found" page, are marked noindex.

## [0.10.19] - 2026-10-17

### Changed

- Website, "What you get": the roadmap track says what each later stage adds and the running total ("+3 more · 12 in
  total", "+3 more · 15 in total"), so "With design partners" and "Planned" no longer read as if they held only three
  capabilities each.

## [0.10.18] - 2026-10-17

### Added

- A free trial's owner looks after the trial team in Getting started › Team. "Remove from trial" takes a colleague
  off the trial, or withdraws an invitation not yet accepted: they are signed out at once and can no longer sign in,
  everything they did stays under their name, and their seat is free for someone new. "Reset MFA" (with a reason)
  removes the authenticator of a colleague who lost it and their recovery codes: they are signed out and set up a new
  one at their next sign-in. The owner's own authenticator is still replaced in My Account › Security. Both are the
  owner's only, for people of their own trial, refused once the trial has ended, and audited
  (`TRIAL_COLLEAGUE_REMOVED`, `USER_MFA_RESET` with the source `TRIAL_OWNER`). API: `POST
  /api/v1/trial/team/{user_id}/remove`, `POST /api/v1/trial/team/{user_id}/mfa-reset`.
- When MDARIX support asks for access to a trial's data, the trial owner sees the request under Support access in
  the Team tab and chooses Approve (with a reason and an authenticator code), Deny or Revoke, with the same rules and
  audit events as a customer's administrators. API: `GET /api/v1/trial/support-access`, `POST
  /api/v1/trial/support-access/{grant_id}/approve|deny|revoke`.
- Platform Admin › Customers & Tenants › Trials lists each trial's people, with "Reset MFA" for those who have
  activated their account. A trial's people are MDARIX's to recover (a trial has no administrator, and nobody in it
  can reset its owner's MFA), so this needs no support access grant; it still needs a reason, never applies to one's
  own account, signs the person out and is audited in the trial's trail as `USER_MFA_RESET` marked `trial_user`.
  Other organizations keep the existing rule. The trials overview answer now carries each person's `id` and a
  `people` list.

### Changed

- The free trial request form says, before anything is sent, that every account uses two-factor sign-in (MFA) with
  an authenticator app on the phone, so people have one ready; the confirmation screen and the trial guide's first
  step say it too.
- Website, "What you get": a roadmap from Live now to Next to Planned that draws itself, with a line of explanation
  for each capability, the free trial's capabilities on their own card, and what each stage means for a customer.
- Website, Product lifecycle: the design and development phases picture is replaced by the same phases drawn on the
  page, each with the design-control records it leaves, the risk file beneath them and the feedback loop back from
  post-market. Both animations run once and not at all for people who ask for reduced motion.

### Fixed

- Platform Admin › Security: audit actions starting with "SOD" read "Segregation of duties" again (a regular
  expression held a control character instead of a word boundary).

## [0.10.17] - 2026-10-16

### Added

- The complaint list can be filtered by product version, lot, problem code and country, and is now also a tab of
  Complaints; Getting started › Automatic insights › "Open these complaints" opens it with the insight's filters
  applied.
- Two-factor sign-in you manage yourself. My Account › Security, and the administrator's Security page, show whether
  two-factor sign-in is on, since when, and how many recovery codes are left. "Generate new recovery codes" asks for
  your current password and the code your authenticator app shows now, then shows the new codes once to copy or
  download; the earlier codes stop working immediately. "Replace authenticator app" (for a new phone, or with a
  recovery code when the phone is lost) asks for your password and a current code, sets up the new app, issues new
  recovery codes and signs you out on your other devices. Both are audited, emailed to you, rate-limited and locked
  after repeated wrong attempts. API: `GET /api/v1/auth/mfa/status`; `POST /api/v1/auth/mfa/recovery-codes` and
  replacing an authenticator through `POST /api/v1/auth/mfa/enroll` now require both `password` and `mfa_code`.

### Fixed

- "Set up MFA" no longer ends in an error for someone who already uses an authenticator app.
- With AI switched off for the organization, Ask MDARIX says which records its answer was built from instead of
  "No matching evidence found".
- Counts of one read correctly in Records › Risk file input ("1 malfunction", "1 risk assessed") and the readiness
  summary ("1 check overdue", "1 record confirmed", "1 reassessment open").
- In a case's Decision tab, a brief that recommends restoring or tightening a quality control (for example, restoring
  incoming inspection) pre-ticks CAPA required, alongside the follow-ups already ticked from the brief.
- In new trials, the sample's VentraLink 250 stays flat as its explanation says, so the trend check flags only
  OrbitCare 300 Rev B; existing trials are unchanged.
- The feedback form names the screens the organization actually sees, and asks about AI only while AI answers.

### Changed

- Platform Admin › Trials › exit requests reads every request in four statements instead of four per request.

## [0.10.16] - 2026-10-16

### Fixed

- Platform Admin › Customers & Tenants › Trials no longer slows down as trials grow. It used to read each trial on
  its own (about 32 database queries per trial), so the page took over 20 seconds for 300 trials and stopped loading
  at about 90 active trials. It now reads every trial together in the same handful of queries whatever their number
  (about 0.15 seconds for 300 trials in our measurement).
- The trial request queue (Platform Admin › Identity & Access › Onboarding) no longer looks up each approved
  request's workspace one by one, and no longer stops at the newest 500 requests: the tab counts include every
  request.

### Changed

- Trials: the table shows 50 trials a page with Previous and Next, a search (organization, tenant key, MDARIX ID or
  the owner's email) and a trial-state filter (active, ending within 7 days, ended). The column headings Organization,
  Trial, Story, Last activity, Demo and Feedback sort every page. Without a sort the trials that need attention come
  first, as before. The figures at the top, the chapter funnel and "Who needs attention first" still cover every
  trial, whatever page or filter the table shows.
- Trial request queue: each tab (Pending, Approved, Declined) shows 50 requests a page with Previous and Next and a
  search (company, requester, email or request ID); the Request ID, Company, Requester and Requested headings sort
  every page.
- API: `GET /api/v1/platform-admin/trials` and `GET /api/v1/platform-admin/trial-requests` return one page and take
  `page`, `page_size` (default 50, at most 200), `sort`, `order` and `q`; the trials overview also takes `state` and
  returns `attention`, the request queue `status`. Both add `page`, `page_size`, `total` and `pages` to their answer.
  Platform Admin only, as before. No database migration.

## [0.10.15] - 2026-10-16

### Changed

- Privacy policy (updated 16 October 2026): if a personal-data breach affects the data MDARIX controls, it now says
  that we tell each affected person without delay, in their account or by email, what happened, what it may mean for
  them, what we are doing and what they can do, and who to contact; and that we tell the Data Protection Board of
  India without delay, with a detailed report within 72 hours. It also says how to identify yourself when you make a
  privacy request (write from the email address on your account), that we respond to a grievance within one month,
  that the policy is available on request in any language of the Eighth Schedule to the Constitution of India, and
  that we do not knowingly collect personal data of children.
- Terms of service and Free trial agreement (updated 16 October 2026): MDARIX is for professionals aged 18 or over,
  acting for their organization. The trial sign-up form says so above the agreement text.
- Incident runbook: steps for telling affected people and the Data Protection Board of India about a breach of the
  data MDARIX controls, the CERT-In 6-hour report that applies once the operating company is registered, and the
  180-day log retention it requires, recorded as a known gap (logs rotate by size today).
- Subprocessor list (internal): object storage, Sentry, inbound email (Resend) and AI providers are marked as not
  used in production today.

## [0.10.14] - 2026-10-16

### Changed

- Getting started › Automatic insights: "Complaints per month" is now a hero card in the Readiness page's navy and
  teal. The recent rate counts up ("8.3 a month now — up from 3.0 before · 2.8×", or "none before Aug 2026" for a
  version new in the recent months). A smooth area chart draws its line month by month, highlights the last three
  months as a band ("Rise since Aug '26"), shows the earlier average as a labelled dashed baseline, and calls out the
  peak ("Sep '26: 12 complaints · 4× the earlier average"). Hover, tap or the arrow keys show each month against the
  earlier average. Clicking a breakdown bar redraws the card for that filter. The table view remains, phones get
  shorter labels and fewer month ticks, and reduced-motion settings show everything at once.

### Fixed

- Personal details in uploaded files are now found in more formats, both when an import refuses them and when it
  replaces them: Indian mobile numbers written the usual ways (+91 98450 12345, +91-98450-12345, 098450 12345,
  98450 12345, +91 9845012345), any number that starts with + and a country code (+44 7700 900123,
  +33 6 12 34 56 78), national numbers that start with 0 (07700 900123, 030 12345678), and a person named after
  "Biomed contact", "site contact", "hospital contact" or "contact person". Lot numbers, serial numbers, dates,
  version numbers and record numbers stay as written.
- Refusing personal data (the default for uploads) now catches everything that replacing it would replace. Before,
  a complaint such as "Reported by Nurse Kavya Rao, phone +91 98450 12345: ..." passed the check and could be
  imported; it is now refused with "This looks like it contains a person's name and a phone number. Remove personal
  data and retry, or choose to mask it." The message names everything found. A hospital or care home named in the
  text ("at Riverside Hospital") is also refused now, as replacing has always replaced it.
- The same wider detection applies to what is masked before any text is sent to an AI model.

## [0.10.13] - 2026-10-16

### Added

- "A new version of MDARIX is available." A tab opened before a deploy keeps running the version it loaded; it now
  asks the server every 5 minutes, and when the tab is shown again, which version it runs, and when that is newer than
  its own it shows a small notice at the top right with a Reload button and a way to dismiss it for now. It never
  reloads by itself (you may be typing), stays silent offline or on an error, and the check does not keep an idle
  sign-in alive. The server answers at `GET /api/v1/public/version`; the web image now builds with the repository's
  `VERSION`, so both sides compare the same number.

### Changed

- "Ask MDARIX to look further" under an Automatic insights answer now opens Ask MDARIX with the question already in
  the question box, ready for you to press Ask MDARIX; it is no longer copied for you to paste. The link shows only
  while AI answers for your organization: without AI, Ask only finds matching evidence records and does not count
  complaints, so it could not look further into the counts the answer shows.
- When Ask MDARIX answers from your records without AI and nothing matches, it now says so plainly ("No evidence
  record matches this question. Ask MDARIX searched the evidence of all your cases and the records you uploaded.", or
  "No evidence record of this case matches this question." with a case chosen) and explains what it searched and that
  it does not count complaints, pointing to Getting started › Automatic insights for complaint counts. The badge reads
  "No matching evidence found".
- The sample data's supplier change (SAMPLE-CHG-014) is now linked to the OrbitCare 300 pressure sensor it concerns,
  so "What changed in OrbitCare 300 Infusion Pump (Sample) Rev B?" shows the change record. This applies to sample
  data added from now on; existing trials keep theirs as it is.
- Automatic insights answers read more naturally: "Complaints rose from 3.0 to 8.3 per month. Per 1,000 units
  released: OrbitCare 300 Infusion Pump (Sample) Rev B 37.8 (17 complaints from 450 units); ...", "since its first
  complaint in Aug 2026", "Lots A and B are both ... Rev B lots made at ...", "US has the most complaints (7 of 9 with a
  country; 3 countries in all)" and "No problem code rose in the last 3 months (...)". A change record's description is
  shown in full up to 240 characters.
- In the answers' tables every numeric column (counts, quantities, rates), heading and cells alike, is right-aligned.

## [0.10.12] - 2026-10-16

### Changed

- Getting started › Your data › Automatic insights is now interactive. At the top, five numbers count up when the
  panel appears: complaints, complaints reporting harm (death or serious injury), malfunctions, the top version's share
  and the recent rate (the last 3 months' average per month against the months before, with an up or down arrow).
  Below them, complaints per month as columns, months without complaints shown as zero, the last 3 months highlighted
  against a dashed line at the earlier average, with a table view and a text summary for screen readers. Nothing moves
  for people whose system asks for reduced motion.
- Breakdowns by version, by lot, by problem code and by country. Clicking a bar shows only its complaints across the
  whole panel (numbers, trend and the other tabs); filters on different tabs combine, a second bar on the same tab
  replaces the first, and a chip clears each one. "Open these complaints" opens Complaints and the filtered complaint
  IDs are listed under the panel (Complaints has no version or lot filter yet).
- "Questions to ask next" now answer themselves in place, computed by fixed rules from your own records (no AI): what
  changed in the version with the most complaints (against the product's other versions, its components and
  suppliers, and change records linked to the product or its components), what the two lots with the most complaints
  have in common, whether the rise holds per 1,000 units released, which complaints report harm or a malfunction,
  which problem codes rose, where complaints come from (country and reporter type) and what evidence open
  investigations still wait for. Each answer names the records it used and says plainly what the records lack to
  answer more. A question is asked only when your records hold what it needs, and products are named as people read
  them ("What do lots A and B have in common?", no longer "Which components and suppliers do lots A share?").
- The finding about a rising trend counts months without complaints as zero, the same months the trend shows, and the
  finding about the top version names the product rather than its identifier.

## [0.10.11] - 2026-10-16

### Fixed

- The web image builds again: the step-by-step user guide's test read the screens' source with Node's file API, which
  the production type check does not include, so the 0.10.10 web build stopped. The test now reads them through Vite
  (`?raw`), and checks the same 39 labels.

## [0.10.10] - 2026-10-16

### Added

- A step-by-step user guide at `/help/user-guide`: every screen of the workspace, task by task, with the names of its
  buttons and fields as they appear, who may do each task, and what you see when it worked. Seven parts (the basics,
  the home screens, complaints and signals, investigations, records, your data and account, feedback and the end of a
  trial) and a table of who can do what. It opens without signing in and saves as a PDF. A test checks that every
  button name it quotes still exists on its screen.
- Help menu and Getting started › Your trial journey offer both guides, told apart: "Step-by-step user guide" (every
  screen, task by task) and "Free trial user guide" (the trial in 7 steps). The step-by-step guide is in every
  organization's Help menu.

### Fixed

- My Account › Security said every session ends after 60 minutes; it ends after 12 hours at most (and after 30
  minutes without activity).

## [0.10.9] - 2026-10-15

### Changed

- Website: "Know what is available today" now matches the free trial. "Available today" lists what every workspace,
  the 30-day free trial included, can use (the second look, reporting clocks, signals and trend checks,
  investigations, signed decisions, CAPA effectiveness checks, risk-file input, the inspector summary, CSV import,
  roles and MFA). AI assistance moved to "With design partners": it is switched on once it is validated. A new "In your
  free trial" block under the columns says what the trial gives (30 days, 3 users, 5,000 uploaded rows, the nine-chapter
  sample story, fourteen videos) and that AI is off during the trial.
- Website `/product-lifecycle`: Signal Intelligence and CAPA Intelligence are shown as current capability, described as
  they work today; the current and future roadmap cards list what the product does now.
- Website: claims of AI as available now say it is switched on per organization and off in the free trial (home page,
  `/trust`, `/security`, the trial-agreement summary); the home hero says "Every finding links to its records".
- Website `/trust`: sessions are described as they work (sign-out after 30 minutes without activity, 12 hours at
  most); live connections and the Product 360 system handoff are described as built with design partners; `/company`
  no longer mentions regulatory drafts.
- Sign-in and sign-up pages: "Every finding cites its records" and "5,000 uploaded rows", as on the website.

## [0.10.8] - 2026-10-15

### Fixed

- Opening a case no longer starts its AI analysis while AI does not answer for the organization (switched off, no
  service available, or the allowance used up, as in every free trial). Before, the case page started a run by itself
  and the rules wrote an analysis, hypotheses, challenges and unknowns into the case under an "AI analysis" card. Now
  `POST /api/v1/investigations/{id}/ai-run` with `trigger=AUTO` answers `started: false` with reason `AI_NOT_READY`,
  and the case page shows no AI card until AI answers. A person can still run the steps by hand.
- The case AI run says "AI" for a step only when the language model wrote its result. Unknowns, which the rules always
  write, were shown as written by AI.
- Generating the investigation brief, and the counterfactual and scenario views, read the product from the
  organization's own data plane. On a server that enforces row-level security they failed with `PRODUCT_NOT_FOUND`.

## [0.10.7] - 2026-10-15

### Fixed

- Website `/videos`: the captions showed twice, once in the picture and once from the browser's caption track. The
  videos carry their English captions in the picture, so the page no longer adds a caption track, and `videos/README.md`
  no longer asks for a `.vtt` file.

## [0.10.6] - 2026-10-15

### Added

- Website: a "Free trial videos" page at `/videos` lists the fourteen-video series "MDARIX Free Trial, Step by Step".
  A ready video plays in its card with English captions (WebVTT); the others say "Coming soon". Linked from the home
  page ("Watch the videos"), the Resources page and the footer.
- Server: the web container serves the repository's `videos/` folder, mounted read-only, at `/media/videos/`
  (`docker-compose.prod.yml`, `infrastructure/docker/Caddyfile`). A video is published by copying its MP4, captions,
  poster and the `videos.json` list there, with no release (`videos/README.md`). The media files are not kept in git.

## [0.10.5] - 2026-10-15

### Changed

- Website: during the product validation phase only the 30-day free trial is offered, so the demo request is hidden:
  "Request a demo" in the header (now "Start free trial"), on the home page, the design-partner band, the contact page
  and the footer, and "Book a one-to-one demo" under the home page's quality loop. `/request-demo` opens the trial
  sign-up. One switch, `DEMO_REQUESTS_OFFERED` in `frontend/src/site/offer.ts`, brings them back. The in-trial
  "Book a one-to-one demo" (Getting started) is unchanged.
- Website menu: "Contact" under Company led to the demo request; it now opens the contact page.

## [0.10.4] - 2026-10-15

### Changed

- Legal pages (privacy policy, terms of service, free trial agreement): the operator is now described as MDARIX's
  founder, with their background in product and regulatory quality, instead of by name, and the contact sections give
  "MDARIX, Hyderabad, India" with the privacy and support addresses instead of a street address. "Last updated" is
  15 October 2026. Operators: set `MDARIX_COMPANY_LEGAL_NAME` and `MDARIX_COMPANY_ADDRESS` to match, since the
  footer, the contact page and every email show them.

## [0.10.3] - 2026-10-15

### Fixed

- Workspace: a free-trial user saw the Readiness screen for a moment after signing in, before Getting started. The
  first screen now waits for the trial status, showing "Opening your workspace…", and opens Getting started directly.

## [0.10.2] - 2026-10-14

### Fixed

- Sign-up: choosing a country put its dialling code in the optional phone field, and the form then refused to
  continue without a full number. A dialling code alone now counts as no phone, and nothing is sent.
- `VERSION` now says 0.10.2. The v0.10.0 and v0.10.1 tags were made with `VERSION` still at 0.9.0, so
  `release.yml` would refuse them and a server without `MDARIX_RELEASE` would report v0.9.0. The rehearsal server
  sets `MDARIX_RELEASE`, so it reported the right release.

## [0.10.1] - 2026-10-14

The validation-phase release: the approved legal texts, the start-up fix found on the first Google Cloud
rehearsal, and the Google Cloud runbook.

### Added

- `docs/runbooks/GCP_DEPLOYMENT.md`: MDARIX on Google Cloud in Mumbai for the validation phase (one VM with
  PostgreSQL, keyless off-site backups to Delhi, IAP-only SSH, uptime and heartbeat monitoring), the private
  rehearsal, go-live, and the move to Cloud SQL when design partners pay.

### Changed

- The privacy policy, terms of service and free trial agreement are final for the product validation phase,
  approved by the operator on 2026-10-14: operated by Srinivas Telikicherla while the company is registered,
  hosting and email in India (Google Cloud Mumbai and Delhi, Zoho), Indian law and the DPDP Act, Hyderabad courts,
  the trial as it works today (instant approval for company email, early exit). `legal/SUBPROCESSORS.md` names
  the providers.

### Fixed

- The API stopped at start-up when `MDARIX_GENAI_COST_PER_1K_TOKENS` was left empty, as the production template
  leaves it (found on the first Google Cloud rehearsal); empty AI cost, timeout and token settings now mean their
  defaults.

## [0.10.0] - 2026-10-14

The lightweight MVP and free trial release: five screens for trials and pilots, the free trial as a nine-chapter
story with its user guide, uploads as quality systems export them, and the end-to-end trial journey tested in a
browser. Migrations md40 to md45.

### Added

- Complaints › Second look: records cancelled or logged as inquiries or service records that carry a sign of a
  complaint (harm, a malfunction, a serious severity, a problem code or one of the organization's words), and No Fault
  Found or User Error codes that recur (3 or more on one product in 12 months), are listed most serious first, each
  with why it was flagged and its matched words marked. A person confirms or dismisses each with a reason, and may
  revise it; both are in the audit trail. MDARIX never changes the record in the source system.
- Complaints › Backlog: open complaints in no signal and no case, oldest first, against the organization's target
  (30 days by default), with past-target and due-soon counts and age bands; a record confirmed on the second look
  counts until it is closed.
- Complaints › Review settings: the backlog target and the second look's words, changed by a triage lead with a reason,
  versioned and audited. Migration `md40` adds the `complaint_settings` and `complaint_second_looks` tables (dedicated
  legacy databases: `scripts/add_workflow_tables_to_legacy_planes.py --apply`).
- Complaints › Reportability: every complaint that reports a death, a serious injury or a malfunction, or a patient
  whose outcome is unknown, with its reporting clocks against the windows the organization entered from its own
  procedure (per market, calendar or work days), most urgent first; missing answers flagged (patient outcome, country,
  awareness date); records cancelled or logged as inquiries with harm counted and sent to the second look. A person
  records the decision (reported, with the report's reference and filing day, or not reportable) with a rationale; its
  timeliness against the binding window is kept and audited. A case's completed regulatory review with no reportability
  concern settles its complaints. MDARIX never decides reportability and never submits a report.
- Complaints › Reporting windows: the organization's windows, started from FDA and EU templates to check against the
  procedure, changed with regulatory approval and a reason, versioned and audited. Nothing is set by default.
- Records › Effectiveness checks: every CAPA's effectiveness check, including CAPAs closed without one and check days
  imported from the quality system; a plan (criteria, check day, measurement start), re-planned with a reason; the
  complaint recurrence before and since on the CAPA's product and problem codes (observed counts, not a statistical
  test); and a signed result (effective or not effective) with password and authenticator code, recorded as a signed
  approval record with the fingerprint of what was signed. After a failed check the next round is planned.
- Reminders: the scheduler job `reporting_reminders` (every 6 hours) puts reporting clocks due soon or overdue in the
  regulatory reviewers' queue (task REPORTABILITY_DECISION, at most 50 new a run) and checks due within 14 days in the
  quality reviewers' queue (task EFFECTIVENESS_CHECK); each is completed by the decision or the signature.
- The demo workspace shows hidden complaints, a recurring No Fault Found, reporting clocks and CAPAs without a check
  from the first minute (after `scripts/demo_tenant.py reset`).
- Migration `md41` adds `reportability_settings`, `complaint_reportability` and `capa_effectiveness_checks` (dedicated
  legacy databases: `scripts/add_workflow_tables_to_legacy_planes.py --apply`).
- Signals › one click to a case: "Open case" on a signal records the triage decision "investigation required" (when
  still due, marked as a one-step decision with its reason) and opens the case with every complaint, their versions
  and lots, for the person clicking, in one transaction (`POST /api/v1/triage/signals/{id}/open-case`,
  investigation.create, so an investigator no longer waits for a triage lead); the case page opens straight away.
- Signals › Trend check: every product version (or version and problem code, or complaint type) compared with its
  own history: the last 30 days against up to 180 days before them (never before the release), with the exact
  Poisson probability; significant below 1%, higher than usual below 5%, not assessed under 3 complaints or 60 days
  of history. Every complaint counts whatever its status (records dismissed on the second look are left out). A
  check beside the count rule: it raises no signal by itself; a triage lead raises one from a notable group.
- Signals › what the complaints have in common: a summary from the records (period, harm, lots, markets, recurring
  words, No Fault Found codes), every sentence citing its complaints, with the signal's own trend check; and an AI
  summary on request (ai.run), kept sentence by sentence only when every cited complaint is the signal's and no
  causal wording is used, recorded as an AI run. With AI off the records summary stands, with the reason.
- The case's one AI run: the analysis, competing explanations, challenges, unknowns, failure chains and the
  investigation brief in a single background pass for one point in time, each step reusing the one before, started by
  itself the first time the case page opens (never repeated), followed step by step on the case page and run again
  on demand (`/api/v1/investigations/{id}/ai-run`). Each step records whether AI or the rules wrote it.
- The Decision Brief writes itself first: starting from the AI draft fills the problem statement from the case's
  question and the recommended actions from the AI's next steps (only where empty; the conclusion stays the
  author's), and flags a draft older than the case's latest evidence or scope. The decision form ticks the follow-ups
  the recommended actions name (CAPA, risk file, regulatory action, field action, product change) for the decision
  maker to confirm.
- A case's regulatory review shows each complaint's reporting clock against the organization's windows (and any
  decision recorded), with a link to the reportability watch.
- Readiness (the home of the lightweight MVP): what an FDA investigator or a notified-body auditor would find today,
  read from the organization's records (rules only): the four numbers (complaints to recheck, complaints past target,
  reporting clocks, trends without CAPA or risk review) and further checks drawn from 2025-2026 findings (harm
  complaints closed without an investigation, CAPAs without a verified effect, signals past their triage date); each
  says why it matters and opens the records behind it (`GET /api/v1/readiness`). Under the `mvp` feature set it
  replaces the Dashboard as home.
- The readiness summary for management review as a PDF (`GET /api/v1/readiness/summary.pdf`, data.export, audited),
  for 90 days to 3 years: readiness checks, complaint handling by product version, second-look outcomes,
  reportability decisions and their timeliness, signals and trend check results, CAPAs and effectiveness checks,
  organized by the management review inputs of ISO 13485:2016 clause 5.6.2.
- Reporting window templates for Great Britain (MHRA: 15 days for a serious incident, 10 for a death; Medical Devices
  Regulations 2002 as amended, regulation 44ZH) and Canada (Health Canada: 10 days for a death or serious
  deterioration, 30 days for an incident that could cause one if it recurred; SOR/98-282 section 60).
- Migration `md42` adds `case_ai_runs` (dedicated legacy databases: `scripts/add_workflow_tables_to_legacy_planes.py
  --apply`).
- Records › Risk file input (ISO 14971:2019 clause 10): for every product, what post-market data said in the period
  (complaints reporting harm or a malfunction, a rising trend, decided signals) beside what reached its risk file
  (completed risk reviews, the risks they assessed, the outcomes, reassessments open or overdue). Each product shows
  one state, most urgent first: post-market data not reviewed against the risk file, reassessment overdue,
  reassessment open, no risk register, reviewed or quiet; the product view lists each risk with the reviews that
  assessed it, never-assessed risks first (`GET /api/v1/post-market/risk-file`, `.../risk-file/{product_id}`, 90 days
  to 3 years, rules only, no new tables).
- Readiness: a check for products whose post-market data has not reached the risk file (critical when not reviewed or
  a reassessment is overdue), opening Records › Risk file input; the management review summary PDF gains section 5,
  "Post-market data and the risk file".
- The automatic trust check (policy `MDARIX_AI_TRUST_POLICY_R1_V2`, `trust_engine/auto.py`): every AI result is checked
  as it is saved, not only when the API is asked. It covers the case's AI run, signal summaries, model-drafted briefs
  and second-look explanations. The checks are: every cited source exists (the case's evidence, including linked
  records, the signal's complaints, the complaint's own fields); no stated root cause, causal proof, probability, or
  decision that belongs to people; no asserted certainty (a warning); provider and model recorded; the right
  organization. Only what the reader sees is checked, never what the feature's checks already removed. The verdict
  (passed, passed with limitations, blocked) is saved with the result (`assurance_results`, `assurance_checks`), and
  every case AI step, signal summary and second-look explanation shows it as a badge that opens its checks. Ask answers
  carry the same verdict, judged on the answer as shown. A model-drafted investigation brief is now saved as an AI
  result (`InvestigationBrief.ai_execution_id`), so it is checked too. `GET /api/v1/ai/trust-policy` describes the
  checks.
- Complaints › Second look › Explain with AI (`POST /api/v1/complaints/{id}/second-look/explain`, ai.run): at most
  three sentences on why a flagged record may meet the complaint definition (ISO 13485:2016, 3.4), each quoting the
  record's own fields word for word. A sentence is dropped when a quote is not in the record, when it says the record is
  or is not a complaint, is reportable or needs a recall, or when it states a cause. Saved as an AI result with its
  trust check and shown beside the rules' reasons; when AI is off or unavailable, the reasons stand alone and the screen
  says why. The record and the decision are never changed.
- The AI release gate (`backend/app/ai_release_gate.py`, `GET /api/v1/ai/release-gate`). It has four bars: a contracted
  provider with zero data retention; the golden dataset signed off by a named person; the full golden evaluation (15 of
  15, model-written) passed with the configured model; the automatic trust check. In production, switching AI on for an
  organization is refused (`AI_RELEASE_GATE_NOT_MET`) until all four are met. Administrators see the bars under
  Security › AI processing, and MDARIX staff see them, with what to do, in the AI Control Center.
  `scripts/qualify_ai_golden_dataset.py --human-sign-off --name --role --confirm` records a person's sign-off bound to
  the lock's hashes, refusing names that read as a tool or an agent. `scripts/run_real_evaluation.py --gate
  --require-model --release-record` writes `evaluation/AI_RELEASE_RECORD.json` only for a full pass on the signed-off
  dataset. Neither file exists yet: the dataset awaits a person's sign-off, and the evaluation awaits the contracted
  provider.

- The quality loop, an animated hero on Readiness, the Dashboard and Getting started. The inspection checks are
  drawn as stations on one closed loop, in the order a complaint travels: hidden complaints found, handled on time,
  reported in window, harm investigated, signals triaged, trends acted on, CAPAs proven, risk file fed. A pulse
  travels the loop and stations that need attention pulse; the weakest link is named. A list beside it says the same
  in words and opens each station's records. The picture is still and complete under reduced motion.
- The free trial's story (`GET /api/v1/trial/story`, `backend/app/trial/story.py`): nine chapters of the loop. Each
  shows what the trial's records hold, the 2026 inspection pain it answers, and whether the organization acted in it.
  A chapter counts only on a record the organization created (a second-look decision, a reporting decision, a case
  from a signal, an AI run or Ask answer, a signed decision, an effectiveness check, a completed risk review, a
  summary download, its own imported complaints), never on page views.
- Platform Admin › Customers & Tenants › Trials (`GET /api/v1/platform-admin/trials`): every free trial holding data,
  with its days left, users and rows against the limits, and how far into the story it went. Each row shows the
  chapter to try next, the last activity and the trial's feedback. Figures show active trials, those ending within 7
  days, those that acted, engaged and uploaded their own data. A per-chapter funnel shows where trials stop, and a
  list names who needs attention first. A tenant's AI processing panel now shows the AI release gate.
- New free trials get the rest of the sample story at approval (`seed_story_examples`): 9 complaints, 2 CAPAs, 3 risks
  and sample FDA and EU reporting windows, all marked `MDARIX_SAMPLE`. The complaints cover a cancelled record and an
  inquiry with harm or complaint signs, a recurring No Fault Found, harm and malfunction complaints with running
  reporting clocks, and a harm complaint closed without an investigation. One CAPA was closed without an effectiveness
  check, one has its check due. Complaints, Records and Readiness therefore show findings from the first minute.
  `scripts/refresh_trial_story.py [--apply]` adds the same records once to trials approved earlier. It never changes a
  trial's own records or reporting windows.

- The trend check counts per unit in the field (md43 `lot_batches.quantity`). When every lot of the versions compared
  has a quantity, the expected number follows unit-days (each lot counted from its release for its quantity), so a
  version shipped in growing numbers no longer looks like a rising trend for that reason alone. Without quantities it
  counts by calendar days and says so. The lot import takes an optional `quantity` (a whole number, checked before
  saving; synonyms such as lot size and qty are matched in mapping). Legacy dedicated databases get the column from
  `scripts/add_workflow_tables_to_legacy_planes.py`.
- A new version is compared with the version it replaced. Too young for its own history, it was "not assessed" before.
  Now its last 30 days are compared with the previous version's complaints over the 180 days before its release: is
  the new version worse than the one it replaced? Trend check shows what each group was compared with and how it was
  counted.
- Free trials: the sample lots carry quantities, and signal detection runs at approval, so the trend chapter has a
  finding from the first minute. OrbitCare 300 Rev B is significantly higher than Rev A per unit in the field, with its
  count-rule signal waiting. The trial story's trend chapter counts signals waiting for a decision or a case.
  `scripts/refresh_trial_story.py --apply` adds the quantities and runs detection for trials approved earlier.
- AI go-live tools. `scripts/ai_provider_preflight.py` checks every provider setting (provider, key, contract, zero
  data retention, price, production policy) and lists the release gate's bars; it sends nothing and changes nothing.
  `scripts/golden_review_pack.py` writes the reviewer's pack for the golden dataset sign-off: each of the 15
  scenarios with its evidence, expected findings, forbidden conclusions and adversarial check, then the sign-off
  statement and command.
- Readiness › Inspection pack (ZIP): the readiness summary PDF, the eight checks as a table, one CSV per check with
  every record behind it (with the source system's identifier), a README and a manifest with each file's SHA-256, for
  the day an inspector arrives (`GET /api/v1/readiness/inspection-pack.zip`, data export permission, audited as
  `READINESS_INSPECTION_PACK_EXPORTED`). A list that cannot be read is named in the pack instead of failing it. The
  trial story's "Show the inspector" chapter counts the pack as well as the PDF.
- The weekly readiness email: on Monday from 06:00 UTC each organization's quality leads (Leader and Reviewer) get
  their quality loop (the eight checks in story order), what changed since last week and the weakest link, with a
  link to Readiness. The scheduler job `readiness-digest` (every 6 hours) queues it once per organization and ISO
  week through the outbox, which holds no email addresses. My Account › Profile lets each person switch it off
  (`GET/PUT /api/v1/me/email-preferences`, audited as `EMAIL_PREFERENCES_CHANGED`).
- Per-unit trends from day one: Import data explains the key columns of each template, and the lots template says
  what `quantity` does; Trend check, when it counts by calendar days, says so and opens Import data. Guide:
  `docs/user-guide/PER_UNIT_TRENDS.md`.
- Free trials book a one-to-one demo from Getting started: times that suit, an optional phone number, the chapters to
  focus on and a note (`GET/POST /api/v1/trial/demo-request`, one open request per trial, audited as
  `TRIAL_DEMO_REQUESTED`). The MDARIX team sees it in Platform Admin › Onboarding, marked as from a trial with the
  organization and how far into the story it went, and by email (`MDARIX_DEMO_ALERT_EMAIL`, else
  `MDARIX_TRIAL_ALERT_EMAIL`). Platform Admin › Trials counts the trials that booked a demo and shows each one's.
- Website home: the quality loop, drawn with illustrative synthetic values and labelled so, and a "Start free trial"
  button beside "Request a demo".
- Migration `md44` adds `auth_users.email_preferences` and the demo request's source, trial, organization, preferred
  time and context (legacy dedicated databases: `scripts/add_workflow_tables_to_legacy_planes.py --apply`).
- Free trials, after a founder's review of the whole journey:
  - Upload a quality system's export as it comes: headers are matched by the names QMS exports use (Complaint Number,
    Product Code, Lot #...), columns the template does not know are left out and never stored, Excel workbooks
    (.xlsx) are read, Windows and UTF-16 text is read exactly, and the quality system's own complaint status is kept
    (so the second look works on the customer's own data). In a trial a complaints export alone is enough: the
    products, versions and lots it names are added.
  - The sample case's Decision Brief arrives written and submitted by a sample author (an account nobody signs in
    with): one trial user reviews it and signs; whoever writes a brief still never reviews or signs it.
  - Authenticator setup shows a QR code (a dependency-free encoder); activating an account goes straight on to sign-in
    and authenticator setup.
  - A company email's trial is approved at once (`MDARIX_TRIAL_AUTO_APPROVE`, `MDARIX_TRIAL_AUTO_APPROVE_DAILY_MAX`);
    free mail, a second request from the same company and anything over the day's cap wait for review.
  - Getting started in three parts: the loop with one next step, the journey and a compact chapter list (details on
    request), and tabs for data, team, the sample explained and the trial's dates. A "chapter done, next" banner
    follows the trial user anywhere; a one-click rating after three chapters.
  - "What were you cited for?": the warning letter, form 483 and notified body themes, each tied to the chapter that
    answers it; those chapters are marked and come first, and Platform Admin > Trials shows them.
  - The trial owner can remove the sample data once their own is in: the sample and the work done on it go (found by
    the database's own links), their own data, reporting windows and the chapters already tried stay; a preview says
    all of it first.
  - Reasons on the second look and the reportability watch offer sentence starters to finish in one's own words; a
    starter alone is never accepted.
  - AI honesty: while AI does not answer for the organization, the investigation chapter reads "Investigate with
    evidence you can trace" and counts only a person's own action, and the AI status says "no AI service here" before
    "switched off".
- Ending a free trial early: the person who started the trial asks from Getting started (End my trial early), with an
  optional reason and whether to delete the data (ticked by default), and may withdraw the request while it waits.
  Platform Admin (Customers & Tenants > Trials) approves, which ends the trial at once and, when chosen, purges its
  data (`tenant_purge`; a legal hold refuses), or declines with a note emailed to the owner. A trial ended with its data
  kept can have it deleted there before the usual 30 days. The owner is emailed that the trial has ended, whether the
  data is gone, and asked to reply with why they left; the MDARIX team is alerted to each request
  (`MDARIX_TRIAL_ALERT_EMAIL`). Migration `md45` adds `trial_exit_requests` (keyed by `trial_tenant_id`, no names or
  addresses, so the request and its reason remain after a purge). Audited as `TRIAL_EXIT_REQUESTED`,
  `TRIAL_EXIT_WITHDRAWN`, `TRIAL_ENDED_EARLY` and `TRIAL_EXIT_DECLINED`.
- Sign-in, account activation and password reset have a show/hide button on the password field. The free trial
  sign-up lists countries by name only (the dialing code still starts the phone number).
- The free trial user guide at `/help/trial-guide`: seven steps from requesting the trial to the one-to-one demo
  (request, activate and sign in, invite two colleagues, the sample data story, your own data, feedback, the demo),
  each with what to do, what you will see and an illustrated, animated picture of the screen (still under reduced
  motion and in print). It opens without signing in, saves as a PDF (`docs/user-guide/MDARIX_Free_Trial_User_Guide.pdf`
  is that PDF), and is linked from the sign-up confirmation, the trial's Help menu and Getting started.
- Getting started shows the trial journey: the guide's seven steps, each ticked from the trial's own records (two
  colleagues invited, three chapters tried, own data uploaded, feedback sent, demo requested), with a button for the
  next step. The decide-and-sign chapter's button says "Open the case decision".
- Getting started explains the sample data: what it holds (counted live), the pain point each part re-creates (hidden
  complaints, running reporting clocks, harm closed without an investigation, a trend after a supplier change, an
  investigation with its evidence, CAPAs without proof they worked, post-market data missing from the risk file), the
  requirement behind each (ISO 13485, 21 CFR 803, EU MDR, ISO 14971) with a button to the screen that shows it, and how
  the sample was made. The trial status counts the sample's lots, complaints, investigations, CAPAs and risks.

### Fixed

- A free trial's complaints upload said "9 new" for 4 complaints: the products and lots the file names are now
  told apart ("4 new, 0 updated, and 2 products and 3 lots they name"; the import answers `also_created`).
- The one-click rating in Getting started vanished as it was sent: its thank-you and "Tell us more" now stay in view.
- Browser tests: the sign-in helpers find the password field exactly (the show/hide button also names "password");
  a new trial-journey test runs the free trial end to end (`frontend/e2e/trial-journey.spec.ts`).
- Platform Admin > Trials named the sample author as a trial's owner when the sample decision is staged; it names
  the trial's own first person.
- A purge now also deletes the demo requests a free trial booked (they name the person who asked), and the trial
  reminders skip an organization whose data has been deleted.
- The AI release gate's first bar ("a contracted AI provider with zero data retention") is read from the contract
  settings themselves (`MDARIX_GENAI_CONTRACTED_PROVIDERS` and the provider's ZDR setting). Outside production the
  provider policy allows any provider, so a free development provider showed the bar as met.
- The readiness summary PDF no longer says the numbers of devices in use are unknown when lot quantities are
  imported; it says how the trends were counted (per unit in the field, by calendar days, or both).

### Changed

- The MVP is five screens. Under `MDARIX_FEATURE_SET=mvp`, and always in a free trial, the workspace menu is Readiness,
  Complaints, Signals, Investigations (the one case page), Records, My Work, Import data and My Account. Dashboard,
  Products, Evidence, Decisions, Intelligence and Trust & Audit are parked, and every link into them opens the screen
  that now holds the work: a case's evidence, Ask MDARIX, reviews and decision are steps of the case page; approvals
  are a My Work tab for people who may sign; the audit trail (with each case's timeline, replay, AI runs and
  integrity), reports and signature verification are Records tabs, each shown only to roles whose menu held the
  section. Customer administration parks Integrations and Data Mapping (no simulated source-system connection is
  shown) and the dashboard's connection and sync tiles. Platform administration parks Data & Integrations, Renewals,
  Reminders (a link opens Subscriptions), Tenant cells and Developer API. Under `full` nothing changes; the parked code
  and routes stay. `.env.production.example` now sets `mvp` for pilots.
- Getting started tells the trial as a story. The quality loop names the next chapter, and each chapter shows its
  live finding, why it matters and where to try it. Progress comes from the server (what the organization did), not
  from the browser. The import, insights and team panels are unchanged.
- Under the `mvp` feature set the template engines that only looked like AI are hidden. The case AI run skips the
  failure-chain step (a fixed two-link template) and says why; the investigation panel no longer generates template
  chains; the static agent catalog (`GET /api/v1/ai/agents/catalog`) is parked, and the AI Control Center shows the
  trust check's policy instead. Chains people build on the case, and the full product, are unchanged.

- Production runs one `background` service instead of `worker` and `scheduler`: `scripts/run_background.py` starts the
  outbox worker and the scheduler unchanged as two processes, passes a stop signal to both and exits when either
  stops, so Docker restarts the container; its health check needs both heartbeats (1.5 GB, 60 s stop period). After
  upgrading, `docker compose up -d --remove-orphans` removes the old containers; `dc exec background python
  scripts/run_scheduler.py --list` replaces `dc exec scheduler ...`.
- ClamAV reloads its signatures in place (`CLAMD_CONF_ConcurrentDatabaseReload: "no"`), so its limit drops from 2 GB to
  1.5 GB; scans pause for a few seconds during the daily update. The long-running services now need 5.25 GB (was
  6.75 GB), plus 1 GB while the backup runs.
- CI: a pull request runs the fast checks (backend, frontend, security, image scan, production compose and stack, the
  desktop browser profile); dedicated data planes, data-plane routing, deployment roles, container and simulator
  validation and the mobile browser profile run after every merge to main, nightly (was weekly security scans only) and
  on demand. The release gate accepts those as skipped only on a pull request.
- Dependabot proposes updates monthly (was weekly), grouped (Python and npm minor and patch updates, the base images,
  the GitHub Actions); security updates still arrive as soon as an advisory is published.

## [0.9.0] - 2026-10-12

The design-partner pilot readiness release.

### Added

- Production deployment for one VM with a managed PostgreSQL: `docker-compose.prod.yml` (Caddy with automatic HTTPS,
  API, worker, scheduler, ClamAV, one-shot migrate job, on-demand encrypted backups), with memory and CPU limits,
  graceful stop periods, health checks for every long-running service and bounded logs.
- Owner database credentials kept out of every long-running service: `.env.migrate` (template `.env.migrate.example`)
  is loaded only by the migrate and backup jobs, and the API, worker and scheduler refuse to start with the owner or
  backup password in their environment.
- Encrypted backups (age) of the control database, dedicated tenant databases and uploaded files, copied off-site, with
  a dedicated read-only `mdarix_backup` login (`scripts/configure_backup_role.py`), a failure alert, a success
  heartbeat, a backup-age check for cron (`scripts/check_backup_age.sh`) and restore of databases and files
  (`mdarix-restore`).
- Break-glass reset of a platform administrator's MFA (`scripts/reset_platform_admin_mfa.py`), audited.
- Public status endpoint `/health/status` (`ok`, `degraded` or `down`) for uptime monitors; readiness detail stays
  internal.
- Configuration gate (`python -m backend.app.config_check [--offline]`) covering alert destinations, staff alerts,
  MFA policy, database certificate verification, runtime role, placeholders, session limits, proxy hops and AI cost
  rates.
- Release pipeline: tagged releases build, scan (Trivy) and publish the api, web and backup images to GitHub Container
  Registry with their digests in the release notes; Dependabot for Python, npm, Docker images and GitHub Actions.
- CI: the full production stack started behind Caddy with a TLS database, the production smoke test, a scheduler run,
  a backup and a restore drill; data-plane routing tests against four tenant databases; migration downgrade/upgrade
  round trip; weekly security and image scans.
- Runbooks: incident response, outbox and scheduler, deployment hardening and monitoring; support ownership with
  response targets.
- Pilot readiness features: legal hold, client error and support problem reports, erasure log, seven-year audit
  retention by default, tamper-evident audit-chain verification, tenant exports, risk register and traceability,
  report content (migrations md23 to md25).
- Investigation workflow, phases 0 to 7: workflow roles, tasks and saved case context; signals, triage and detection;
  case scope and evidence review; intelligence judgements and structured Ask; risk and regulatory reviews with a
  controlled Decision Brief; the signed human decision, follow-ups, late evidence and closure; trust and audit of a
  case (migrations md26 to md33, human-readable business IDs in md26).
- Customer and organization lifecycle for Platform Administrators, platform accounts, redesigned dashboards for the
  platform, customer and workspace consoles, and shared tables with movable, resizable columns and server-side
  sorting.
- Imports keep the rows that pass, with a rejects file, and mask personal data instead of refusing the file.
- Deployment roles MULTI, PLATFORM and CELL from one codebase (ADR-013); tenant cells built from signed documents and
  licensed; the platform-cell link with enrollment, heartbeats, signed packages and licence grace (migrations md36,
  md37).
- Customer-approved support access: platform staff read an organization's data only after its administrator
  approves, for a limited time, and every use is audited (migrations md35, md38).
- A richer free-trial request: job title, country, phone in international format, company size, devices, markets,
  complaint system and volume, trial data and goal, and the confirmation that no patient data will be uploaded. Shown
  to the reviewers; the personal answers are erased with the organization (migration md39).
- A redesigned two-step sign-up page. An email that already has an account is told so, with Sign in and Reset password
  links; a repeated trial request is told it is still under review.
- Staging on an Oracle Cloud Always Free ARM server (`docker-compose.staging-oracle.yml`, ADR-017), private behind a
  login until the lawyer-approved legal texts exist (`MDARIX_SITE_ACCESS=private`,
  `MDARIX_PRIVATE_STAGING_ACKNOWLEDGED`).
- Optional `www.` redirect at Caddy (`MDARIX_WWW_REDIRECT=on`).
- Self-hosted GitHub Actions runners (`infrastructure/ci/self-hosted/`), chosen through the repository variables
  `CI_LINUX_RUNNER` and `CI_WINDOWS_RUNNER`; releases use the same runner.
- Draft privacy policy, terms of service and free trial agreement for the lawyer (`legal/`); runbooks for key and
  secret rotation.

### Changed

- AI processing is off for new organizations until an administrator enables it (migration md23).
- A contracted AI provider is refused in staging and production unless `MDARIX_GENAI_<NAME>_ZDR=true` (zero data
  retention confirmed) or `MDARIX_GENAI_ACCEPT_RETENTION=true`: add one before upgrading a server that uses a model.
- Servers split their settings into `.env.production` and `.env.migrate` and pass `--env-file .env.production` to
  every compose command; move `MDARIX_DB_OWNER_PASSWORD` into `.env.migrate` before upgrading.
- Administrator roles are stored in one canonical form (migration md25); ORM models and the schema are aligned
  (migration md24).
- The embedding model in the API image is pinned to one revision.
- GitHub Actions are pinned to commit SHAs; CI uses Node 22, as the web image does.
- Sign-up answers 409 for an email that already has an account (`EMAIL_ALREADY_REGISTERED`) or an earlier trial
  request (`TRIAL_ALREADY_REQUESTED`), instead of the same answer for every email. Rate limits still apply.
- The configuration check refuses draft legal documents (a DRAFT banner or a `[PLACEHOLDER]`) and, in production,
  requires encrypted off-site backups and outside monitors.
- Separation of duties: the last person to make a material edit to a decision cannot approve it.
- Large screens split into smaller files (case intelligence views, demo golden path); the older embedded platform
  administration screen is removed.

### Security

- The API image takes Debian's security updates at build time (fixes the libpcre2 finding); the backup image drops
  the unused `gosu` binary.
- Caddy no longer logs single-use tokens from links, marks API responses `no-store`, and sends
  `Cross-Origin-Resource-Policy: same-origin`.
- The web container runs read-only without Linux capabilities other than binding ports 80 and 443.
- Row-level security for organizations and customers, with every writer scoped (migration md34).
- Session cookie `SameSite=Strict`; invitation and activation links expire after 48 hours (was 72); a full export and a
  purge also need a current authenticator code; the API sets the same browser protections as Caddy.
- Image scans fail on every high or critical finding except the reviewed ones in `.trivyignore.yaml`.
- Caddy is built with `golang.org/x/net` v0.60.0 (CVE-2026-78669; Caddy v2.11.7 pins v0.59.0).
