# Changelog

All notable changes to MDARIX are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/).
The version being prepared is in `VERSION`; a release is the git tag `v<VERSION>` (`.github/workflows/release.yml`
builds, scans and publishes its images, and refuses a tag that does not match `VERSION`).

Every entry says what changed for the people who use or run MDARIX. Schema changes name their migration, so an
operator knows a release migrates the database.

## [Unreleased]

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
