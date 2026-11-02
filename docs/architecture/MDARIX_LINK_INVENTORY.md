# Every link in MDARIX, and where it lands (0.10.67, quality plan stage 6)

Stage 6 gives every screen, tab, record, open panel and filter its own address, and keeps one table of where every
link lands. This is the inventory of link sources (task 6.3). Each row names the source, its code, what it sends and
the test that proves each link opens a screen and tab that exist.

The places are in `frontend/src/app/linkTable.json`. That is the one link table: the screens, their tabs, where each
kind of record opens, and every former address, section and tab name. The browser applies it in
`frontend/src/app/linkTable.ts`, and the server copies its places in `backend/app/links.py`. A test holds the two
copies to the same values.

## The address scheme

| Address | What it holds |
|---|---|
| `/app/<screen>` | A screen. Its path is in `linkTable.json` "places". |
| `?tab=<tab>` | The screen's tab. |
| `&<record>=<id>` | A record the tab shows or filters to (`complaint`, `report`, `communication`, `capa`, `signal`, `request`, `event`, `item`, `check`, `task`). |
| `&<filter>=<value>` | A list's filters: the complaint list's `q`, `product_id`, `version`, `lot`, `problem_code`, `country`, `status`, `source_system`; the signal inbox's `status`, `priority`, `product_id`, `origin`, `owner`, `q`, `sort`, `overdue`, `review_due`, `source`. |
| `/app/investigations?case=<INV…>&step=<step>` | The case page: its case and step, and what the step carries (`follow_up`, `assessment`, `review`, `view`). |

These rules apply under the MVP feature set, which every trial and pilot runs:

- Opening a record or panel adds a history entry; changing a filter replaces it.
- Back closes a panel without reloading the screen.
- Refresh, a new tab and sign-in (`returnTo` keeps the path and query) reopen the screen with its record, panel and
  filter.

Code: `features/workspace/workspaceAddress.ts` (`addressFor`, `locationFromAddress`, `restoreKind`) and the hooks in
`features/workspace/workspaceContext.tsx` (`useReportedTab`, `useTabParam`, `useTabFilters`).

## Sources

| # | Source | Code | Count | What it sends | Proved by |
|---|---|---|---|---|---|
| 1 | Readiness checks | `backend/app/readiness_home/service.py` | 11 | `links.target(section, tab)` | `tests/test_link_targets.py` (every target of a trial) |
| 2 | Oversight rows and alerts | `backend/app/oversight/service.py` | 9 | `links.target`; a report's or a reply's carries its complaint (`record=("complaint", id)`) | same |
| 3 | An event's checklist and next action | `backend/app/oversight/closure.py` | 9 | same | same |
| 4 | Report and guide approval tasks | `backend/app/authority_reports/router.py`, `backend/app/decision_guides/router.py` | 2 | same, kept in the task's details | same |
| 5 | Trial story chapters | `backend/app/trial/story.py` | 10 | same | same, and `test_the_story_chapters_open_existing_screens` |
| 6 | Sample-data chapters ("About the sample data") | `frontend/src/features/workspace/sampleStory.ts` | 9 | `{section, tab}` | `app/linkTable.test.ts` |
| 7 | Task types (My Work "Open") | `features/workspace/tasks.ts` `taskDestination` | 17 types × 6 sources | section and tab | `app/linkTable.test.ts` (every type, every source, with and without a case) |
| 8 | A case's audit trail ("Open" on an event's record) | `features/workspace/caseAudit.ts` `objectTarget` | 22 kinds | section and tab. New: complaint, report, communication, CAPA, disposition (6.5). Opening one makes the timeline's case the context. | `app/linkTable.test.ts` |
| 9 | Literal `open("…")` calls | `features/**` (not the administrator consoles) | 58 | section, tab | `app/linkTable.test.ts` (reads every source file) |
| 10 | Tabs that links build | `communicationsTab`, `reportsTab`, `recordsTab`, `signalsTab`, `decisionTab`, `reviewsTab`, `intelligenceTab`, `trustTab`, `documentLink`, `complaintListTab`, `eventTab` | 11 builders | a tab with its record or filter | `app/linkTable.test.ts` |
| 11 | "A › B" paths in the user guide | `features/help/userGuide.ts` | 60 (51 on workspace screens) | words | `app/linkTable.test.ts` (each names a screen and one of its tabs) |
| 12 | E-mail links | `auth/emailer.py` (40 senders) | 13 workspace links | `links.app_path(...)`: the browser's own addresses | `tests/test_link_targets.py` (every sender called; every link opens a screen and tab that exist) |
| 13 | `returnTo` after sign-in | `app/apiClient.ts` | 1 | the path and query | keeps the full address, so the panel comes back |
| 14 | Former addresses `/app/<view>` | `linkTable.json` "oldViews" | 24 | section, tab | `app/linkTable.test.ts` |
| 15 | Former section names (Dashboard, Products, Evidence, Decisions, Intelligence, Trust & Audit) | `linkTable.json` "oldSections" (moved from `featureSet.ts` routeFor) | 15 rows | place | `app/linkTable.test.ts` |
| 16 | Former tab names | `linkTable.json` "oldTabs" | 3 | tab | `app/linkTable.test.ts` |
| 17 | `?section=<name>` addresses (used until 0.10.66) | `workspaceAddress.ts` | 18 sections | read as the screen, rewritten to its path | `app/linkTable.test.ts`, browser check below |
| 18 | `?signal=<id>` links | `workspaceAddress.ts` | 1 | kept in the address (it was removed at start) | `workspaceAddress.test.ts` |
| 19 | Saved column choices | `features/tables/columnViews.ts` | per screen | a stable view id (`linkTable.json` "viewIds"); old keys carried over once | `tables/columnViews.test.ts` |

## Broken links found and fixed (6.4)

| Link | Before | Now |
|---|---|---|
| E-mail: risk review requested (`emailer.py` `send_risk_review_requested_notice`) | `/app/risk-traceability`, a screen the MVP parks | My Work, where the review task is |
| E-mail: a decision waiting for approval | "Open Decisions", `/app/decision` (a parked section) | "Open the decision": the case page's Decision step; without a case, My Work › Approvals |
| E-mail: a decision signed | `/app/decision?case=` | the case page's Decision step |
| E-mail: support access in a trial, "Open Getting started › Team" | `/app`, which lands on Your data | `/app/getting-started?tab=Team` |
| Investigations: "Other product" rows | could not be opened ("choose its product in the context bar") | open: the case's product is looked up |
| My Work › Approvals, a case of another product | "Choose … in the context bar above", which My Work does not have | opens: the case's product is looked up |
| Records › Audit trail without a case | "Pick one in the context bar above" (Records has none) | "Open one in Investigations", with a button |
| A case link that cannot be opened right now | "Choose it in the context bar above" | "Open it from Investigations" |
| `/app/story` (a former address) | Investigations › All investigations (its Story tab is parked) | the case page (Workspace) |
| A tab carrying a record (`Dispositions?complaint=…`) | Complaints opened Triage: the tab's exact name did not match | the tab's name chooses the tab |

## Server targets: fields kept for older tabs (6.6)

Every server target now has this shape, built by `links.target` and read in the app by `placeOf`:

```
"opens": {"section": "Complaints", "tab": "Reports?complaint=<id>",
          "target": {"section": "Complaints", "tab": "Reports", "record": {"kind": "complaint", "id": "<id>"}, "panel": null}}
```

`section` and `tab` are what screens read until 0.10.66, so a tab left open across the upgrade still works. Alerts
raised before 0.10.67 store only those two fields, and `placeOf` reads them too.

## For the forward merge into mvp-1.0

These four files differ on mvp-1.0:

- **`frontend/src/app/featureSet.ts`.** mvp-1.0 adds the `pilot` feature set and `usesMvpScreens()`. `routeFor` has
  moved to `app/linkTable.ts`, and its `featureSet !== "mvp"` must become `!usesMvpScreens(featureSet)`. Otherwise a
  pilot gets no redirects. The same applies in `UserWorkspace.tsx` (`addressed`, the address sync and the popstate
  listener, all `featureSet === "mvp"`).
- **The pilot feature set.** Pilots turn CAPA effectiveness checks off (`mvpRecordsTabs`). `linkTable.json` lists
  Records › Effectiveness checks, and the `capa` record opens there. For a pilot the `capa` place needs another tab
  (the case's CAPAs step). `linkTable.test.ts` "places equal the tab constants" then needs the pilot's tab list.
- **`frontend/src/features/workspace/UserWorkspace.tsx`.** `VIEW_TO_SECTION` is now `OLD_VIEWS` from the link table.
  `step`/`reportStep` became `shown`/`reportTab` (`reportStep` stays as an alias).
- **`frontend/src/features/workspace/sections/Investigations.tsx`.** mvp-1.0 changes the tabs line. Here the
  "Other product" rows and the first step report changed.

## Browser tests to update at stage 9 (not run now)

| Spec | Lines | What changes |
|---|---|---|
| `e2e/browser-evidence.spec.ts` | 63–66, 283–284, 327–335, 370 | Under the MVP, old addresses (`/app/decision`, `/app/ask`, `/app/evidence`, `/app/assurance`, `/app/audit`) now redirect to their place, so the address changes after load. |
| `e2e/browser-evidence.spec.ts` | 407, 412 | After sign-in, `returnTo=/app/signals` opens `/app/signals?tab=Signal+inbox` under the MVP; `toHaveURL(/\/app\/signals$/)` needs the tab. |
| `e2e/golden-path.spec.ts` | 64, 92 | `/app/${view}?case=` old view links; tab name matching. |
| `e2e/trial-journey.spec.ts` | 124, 133, 330–337, 421, 471, 512, 575–587, 609 | `/app` start and the Getting started, Complaints and case-page tab selectors (stage 7 moves the tabs). |
| `e2e/pilot-features.spec.ts` | 62–76 | Risk & traceability, Traceability and Reports tabs. |
| `e2e/deep-crawl.spec.ts` | 90, 132 | Its start-address comparison: the address now gains `?tab=`, so the crawl reopens the start page before each step. |

## Stage 7 (0.10.68): the new navigation

- **Where the new places are.** `linkTable.json` `newPlaces` (screens, tabs and My work's views), `newMenu`,
  `newRecords` (a complaint opens `/app/complaints/<ref>`), `newHomes` (every classic screen and tab, the nested ones
  included, and its new home; a row may keep the link's parameters, rename one: `event` -> `ref`, or add the view a
  former tab is now) and `classicHomes` (an address of the new navigation opened on the classic one). `routeFor`
  takes the organization's navigation (`tenants.navigation`, session `navigation`); classic organizations route as
  in 0.10.67. Tests: `app/linkTable.test.ts` (both navigations), `app/clickPaths.test.ts` (paths a-m),
  `app/newPathText.test.ts` (the guide's paths), `tests/test_complaint_page.py`.
- **Server targets open records.** The complaint checklist (`closure.py`) and Oversight rows (`oversight/service.py`)
  name the complaint, the communication or the CAPA, not only the list.
- **Code names classic places.** Screens call `open()` with classic names wherever one exists ("Complaints",
  "Triage"); the table moves them. A place only the new navigation has (Queues, Team overview, Account › Away) is
  opened only from new-navigation screens; the test checks it there.

### For the forward merge (stage 7)

- `UserWorkspace.tsx` picks the new screens with `fresh` (new navigation under `featureSet === "mvp"`); on mvp-1.0
  this becomes `usesMvpScreens(featureSet)`, so a pilot can be switched too.
- The pilot feature set parks CAPA effectiveness checks: `newPlaces.Records.tabs` lists "Effectiveness checks" and
  "CAPA records"; for a pilot, `NewRecordsSection` must drop the first (as `mvpRecordsTabs` does) and the `capa`
  record must open on "CAPA records".
- `Investigations.tsx` exports `Capas` (Records › CAPA records); mvp-1.0 changes the same file's tab line.
- New task type `COMPLAINT_STEP` ("Send to" from the complaint page) and the route
  `POST /api/v1/oversight/events/{id}/send` (WRITERS).

## Stage 8 (0.10.69): the investigation in four sections, drawers with addresses, the entrance

- **The investigation's sections.** On the new navigation `newPlaces.Investigations.tabs` is Summary, Evidence,
  Decisions & actions and History. `newHomes` maps every former tab to its section and part: Workspace -> Summary,
  Scope -> Summary `part=scope`, Intelligence -> Evidence `part=intelligence` (its `view` kept), Ask MDARIX -> Evidence
  `part=ask`, Reviews -> Decisions & actions `part=reviews` (its `review` kept), Decision Brief -> `part=brief`,
  Decision -> `part=decision` (its `follow_up`/`assessment` kept), Record -> History. `classicHomes` opens Summary,
  Decisions & actions and History on Workspace, Decision and Record. `newRecords.case` opens Summary. Tests:
  `app/linkTable.test.ts` ("maps every former investigation tab"), `app/clickPaths.test.ts` (path f: 10 steps).
- **Drawer addresses.** 24 investigation drawers carry `panel=<kind>:<key>` in the step's address
  (`workspaceContext.tsx` `usePanelState`, `usePanelFlag`): add-hypothesis, judge, link-evidence, withdraw-link,
  record-observation, add-unknown, unknown-status, request-evidence, build-chain, chain-link, review, request-review,
  review-evidence, provenance, link-evidence-records, new-request, request, follow-up, impact, decision-record,
  return-brief, submit-brief, state-change, ai-run. Back closes one; refresh and a new tab reopen it.
- **A server target names a case.** The checklist's "Sign the investigation decision on the case" carries
  `record=("case", <id>)` on Investigations › Decision (`closure.py`); `useOpenTarget` makes that case the context
  first (`/workspace/context/resolve` now also takes an id). Test: `tests/test_flagship_walkthrough.py`.
- **The entrance and its stories** (`features/workspace/entrance.ts`): each story starts on a place of the new
  navigation and its steps are places too. Test: `entrance.test.tsx`, `flagshipWalk.test.ts`.
