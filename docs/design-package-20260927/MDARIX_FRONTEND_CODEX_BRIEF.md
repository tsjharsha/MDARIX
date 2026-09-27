# MDARIX frontend redesign — Codex implementation brief

## Assignment

Implement this design in the existing MDARIX-R1 React/Vite frontend. Use the accompanying interactive prototype as a visual reference. This is an evolution of the current application: retain MDARIX branding, navy/teal identity, Product 360, investigation/evidence/decision concepts, and Administrator Control Plane terminology. Deliver working existing workflows, not a replacement static demo. The prototype has representative screens; secondary administration destinations illustrate a detail pattern rather than complete functionality.

Repository: https://github.com/stelikicherla-stack/MDARIX-R1
Design baseline reviewed: e6e809a3da24480e6c1bb22765092f3736158c5a, 26 September 2026.
Inspect the current checkout and AGENTS.md first. Preserve subsequent changes and user work. Do not reset to the reviewed commit.

## Product direction

An evidence-backed investigation workspace for MedTech quality teams. The primary journey is product context → investigation → evidence review → competing explanations and missing evidence → decision brief → authorized human review. Product marketing remains a separate experience; do not redesign website-next or public marketing pages in this task.

## Visual system

Use the prototype's compact Salesforce-inspired record structure without copying Salesforce branding. Avoid oversized heroes, decorative metrics, excessive nested cards, and promotional imagery in the authenticated workspace.

Light tokens: canvas #F3F6FA; surface #FFFFFF; primary text #183249; secondary text #52677A; border #DBE4EB; action teal #087B78; selected surface #E8F5F2. Dark equivalents: canvas #111C29; surface #182737; text #E0EDF6; muted #ACBFCE; border #354858; action #73D6CB; selected #203D40. Check contrast on all actual combinations, especially status labels and focus outlines. Use theme-aware variables. Navy remains the brand anchor; teal communicates navigation selection and primary actions.

Typography: Inter with system sans-serif fallback; no remote font dependency required. Body 14px with 1.5 line height; meaningful secondary text 12px minimum; page title 26px desktop / 23px mobile; panel titles 15–16px. Avoid serif fallback. Font weights 400/500/600/700 where appropriate.

Spacing: 4/8/12/16/24/32px scale. Desktop sidebar 216–240px (prototype compressed to 190px for its preview surface). Header 64px; content padding 24px; card radius 8px; control radius 6px. Restrained borders, minimal shadows. Content-first layout, not a full-page card grid.

At 1440px, use 2:1 main/detail columns for investigations and 2:1 main/attention on platform overview. At 1024px, use a compact sidebar. Below 768px, use a labeled collapsible navigation drawer and stack content. At 375px and 320px, no page-level horizontal scrolling; wide evidence tables may scroll in a labeled region. Do not scale desktop UI down to unreadable text. Essential mobile actions have 44px touch targets.

Use existing lucide-react icons. Do not add an icon library. Do not retain inline-prototype DOM rendering inside React.

## Shared shell and context

Header: MDARIX logo, workspace name, authenticated user name and current role, tenant/environment badge where applicable, and a profile menu with logout. Keep names and roles readable. Customer identity is never inferred from client-supplied tenant IDs.

Left navigation: current item highlighted using text, background and a left accent; compact groups; hide unauthorized destinations based on server capabilities. Hiding is UX only, never authorization enforcement.

Record header: breadcrumb; record title and identifier; owner/status/due date; one clear primary action. Below it, a persistent context bar includes tenant, product, version, investigation and temporal mode. Provide Current / Event as of / Known as of with accessible labels and date input when appropriate. Explain event date versus date learned in concise help text. No silently selected unrelated investigation. Clear dependent selections when parent scope changes and preserve valid scope in navigable URLs.

Use progressive detail: source drawers, tabbed related records and compact activity history. Never leave an empty shell while waiting for prerequisites: explain what to select and provide the permitted next action.

The prototype's workspace selector is a design-preview control only. Do not ship an unrestricted role or workspace switch. Any production switch must use authorized memberships/roles returned and verified by the backend.

## Information architecture and routes

Preserve existing paths, bookmarked routes, browser Back/Forward, and existing navigation policies. Detail routes below are proposed and must be added only after checking the current router.

| Area | Existing path | Design treatment |
|---|---|---|
| My workspace | /app | Assigned actions, investigations, decisions and recently used products |
| Product 360 | /app/products | Search/list plus selected product, version and timeline |
| Signals & Complaints | /app/signals | Retain as functional destination; source and linked investigation context |
| Investigations | /app/investigations | List and detail; Summary, Evidence, Hypotheses, Timeline, Activity |
| Evidence library | /app/evidence | Filterable source list and source detail drawer |
| Decision Center | /app/decision | Decision list, evidence package, readiness and signature flow |
| Ask MDARIX | /app/ask | Retain; context-aware questions, cited answers and limitations |
| Story View | /app/story | Retain; connected case chronology |
| Persona dashboard | /app/persona | Retain until its useful content is migrated without losing functionality |
| AI Assurance | /app/assurance | Real evaluation states and versions; no simulated PASS |
| Audit Trail | /app/audit | Retain dedicated permitted audit workspace |
| Platform administration | /app/admin | Administrator Control Plane only |
| Customer administration | /app/customer-admin | Tenant-scoped Customer Administration only |
| Mapping Studio | /app/admin/mapping-studio | Versioned mappings, preview, impact and controlled activation |

Preserve other existing admin routes in frontend/src/app/router.ts. The prototype's smaller primary menu does not authorize deletion of working routes. Use a secondary navigation group for less frequent destinations when necessary.

## Screen specifications

### 1. My workspace
Three meaningful counts at most: assigned investigations, evidence requests, decisions awaiting the user's review. Each count has a defined scope, real source and drilldown. Main column: task list with record, product/version, owner, due date and status. Narrow secondary column: contradictions needing review, missing evidence, overdue requests. Recent products follow. No invented percentage readiness or charts without data.

### 2. Product 360
Product identity, lifecycle status, selected revision and linked sources. Sections: overview, configuration/components/suppliers, changes, lots, complaints/investigations, evidence and timeline. Show applicability explicitly. Events and known-at timestamps remain distinct. Opening an investigation preserves the chosen product/version context. Provide clear no-data and no-applicable-record states.

### 3. Investigation workspace
Title/question and record metadata; persistent context; tabs Summary, Evidence, Hypotheses, Timeline, Activity. Summary emphasizes observations, evidence conflicts, missing information and next review steps. Right panel lists explicit checks (sources available, contradiction reviewed, comparison evidence missing, human decision status), not an unexplained trust score.

Hypotheses show supporting evidence, contradictory evidence, applicability, unknowns and human review state. Distinguish AI suggestion, source-attributed conclusion, verified observation and human decision. Graph relationship does not establish causality. Suggested external requests require human review and existing authorized sending flow.

### 4. Evidence library and detail
Columns: evidence ID/title, source/version, product applicability, event/received date, relationship to the selected investigation, review status. Filters: product, investigation, source, status; search only where backed by an actual data path. Detail drawer: source excerpt, precise source anchor, original document link, version, event/known timestamps, lineage, links and permitted actions. Conflicts must be described in words. Escape source text; never render untrusted HTML.

### 5. Decision Center
Proposed action, rationale, evidence package, alternatives, unknowns and review requirements. Human review is separate from AI suggestions. Approve/Reject invokes a secure dialog with read-only authenticated name, mandatory decision, mandatory trimmed remarks, current-password reauthentication and configured MFA when supported. Never store password in localStorage, analytics, URLs or logs. Clear it after submission/cancel/error. Server verifies authority, subscription, segregation of duties, object version and replay protection. Show stale-version conflict with re-review action. Never report success until committed server result. Provide signature history and permitted audit navigation.

### 6. Administrator Control Plane
Platform team only. Domains and subsections:
- Platform overview: real metrics, customer onboarding stages, compact attention queue.
- Customers & Tenants: directory, Customer 360, Tenant 360, onboarding, environments, initial customer administrators, tenant health.
- Plans & Licensing: plan definitions, entitlements, subscriptions, start/expiry dates, reminders, suspension/reactivation.
- Identity & Access: platform users, platform roles, permission sets, sessions, MFA/SSO configuration status.
- Data & Configuration: master data, canonical model, master mappings, mapping versions, configuration releases and impact review.
- Integrations: catalog, customer connections, schema discovery, webhooks, ingestion runs, failures and retry status.
- AI Control Center: models/configurations, prompts/agents, evaluations, guardrails, executions, release assurance.
- Security: tenant isolation, access reviews, retention, residency/encryption configuration and observed status.
- Operations: health, jobs/queues, storage, incidents and settings.

Use the exact title Administrator Control Plane. Remove the old Platform administration hero title and the “Govern the MDARIX platform” promotional section. Do not add “Controlled administration · Server-authorized · audit recorded” banners, a generic “Some sources are temporarily unavailable” hero message, “View sources,” or an “Audit evidence” overview card. Preserve real audit capture and dedicated audit routes. Report an actual service error locally in the affected panel with retry and correlation ID; do not conceal failure or replace unknown values with zero.

Make Requires attention the narrower column. The larger overview contains customer/configuration/integration operational information. Any charts must use real historical aggregates with period and denominator; no repeating decorative sparklines. If historical data is unavailable, use a genuine current-state breakdown or a clear not-available state.

Provisioning wizard: company → tenant/environment/region → subscription and limits → initial Customer Administrator → review → provision. Use idempotent existing backend workflow and show partial provisioning recovery, invitation status, validation errors and duplicate checks.

### 7. Customer Administration
Separate tenant-scoped shell. Overview, users/invitations, roles/personas, object/record/action/field permissions, approval authority, licensed usage, allowed integrations, tenant mapping overrides and configuration versions. Show current usage and capacity. Platform users never appear as ordinary tenant staff. Customer Admin cannot create platform roles or bypass plan limits. Entitlements define the maximum available features; user permissions narrow them.

### 8. Mapping Studio
Master mapping version, tenant pinned version and override status visible together. New master releases do not silently update tenants. Draft → validate → dry run → impact review → approved activation. Show changed fields, affected objects, errors, conflicts, preserved overrides, rollback/reference version and audit entries. Server-managed tenant fields cannot be manually mapped. Never present dry-run success without an actual result.

## Implementation structure

Work in frontend/, not website-next/. Reuse existing API client, router, navigation policy and UI utilities. Inspect frontend/src/main.tsx, styles.css, features/admin/PlatformAdminScreen.tsx, features/stage2/MappingStudio.tsx and existing administration/subscription components before edits. Extract incrementally; do not rewrite all behavior in one large commit.

Suggested modules (adapt to existing conventions):
- app/layout/AppShell.tsx, Sidebar.tsx, Header.tsx, WorkspaceContextBar.tsx
- app/design-tokens.css
- components/RecordHeader.tsx, StatusBadge.tsx, DataTable.tsx, DetailDrawer.tsx, AsyncPanel.tsx, EmptyState.tsx
- features/home/MyWorkspacePage.tsx
- features/products/Product360Page.tsx
- features/investigations/InvestigationWorkspace.tsx
- features/evidence/EvidenceDetailDrawer.tsx
- features/decisions/DecisionReviewPage.tsx, SignatureDialog.tsx
- existing features/admin and features/stage2 components updated in place

Do not introduce a second router or global state library without a concrete need. Use typed API view models. Inventory existing endpoints and clearly record gaps; do not invent endpoint paths or hardcode success responses. Preserve CSRF, cookies, error handling and correlation IDs in the existing client. Keep authorization server-side. If a backend prerequisite blocks a UI action, show a truthful unavailable state and document the exact gap.

## Required states and accessibility

Every data surface: loading, empty, ready, partial failure, full error, forbidden, expired session. Mutations additionally: pending, validation error, conflict, success confirmed, safe retry. Do not silently fall back to synthetic data. Seed/demo data requires a visible environment marker.

Semantic landmarks with one main element; no duplicate main regions. Real buttons/links; labeled inputs; aria-current for navigation; keyboard-operable tabs; modal focus trap and return focus; Escape close; meaningful heading order; visible focus; color plus text status; readable zoom at 200%; reduced-motion support. For destructive actions, explain scope and confirm appropriately. Toasts supplement persisted result states and never carry the only error message.

## Known engineering dependencies from review

Recheck before implementation because repository may have advanced. At the reviewed commit: hosted backend suite failed, evaluation default could PASS constructed outputs, governance bootstrap provisioned demo entitlements during requests, transaction-local tenant context was committed before downstream work, and per-user permission propagation needed review. These are backend issues; frontend styling must not claim to fix them. Do not weaken tests, authorization or release gates to deliver the redesign. Do not label release production-ready merely because build passes.

## Delivery sequence

1. Inspect current code and record a short route/component/API inventory; create an isolated branch if appropriate.
2. Introduce tokens and shared shell, preserve all current routes and behavior.
3. Implement My workspace, Product 360 and investigation layout.
4. Implement evidence drawer and Decision Center using real endpoints.
5. Refine Platform and Customer Administration, subscriptions and Mapping Studio.
6. Run build, existing frontend tests and focused browser flows; repair regressions introduced by changes.
7. Capture desktop and mobile screenshots, accessibility findings and a route/state checklist.

Proceed with authorized local implementation without repeatedly asking approval for routine component choices. Do not deploy, merge or send external communications as part of this frontend task. Deliver a reviewable diff and clear run instructions; distinguish complete UI work from blocked backend functionality.

## Acceptance gates

- Existing routes, browser navigation and login/logout work; record context survives appropriate navigation.
- A real authorized user can execute the supported investigation/evidence/decision journey; missing backend support is explicitly documented.
- Platform/Customer Administrator separation remains intact. Denied deep links and forbidden API responses are handled.
- Hidden/read-only field treatment aligns with server policy; UI hiding is never called security proof.
- Master mapping updates do not automatically overwrite tenant-pinned versions.
- No fake metrics, live indicators, trust percentages, approval successes or evaluation PASS results.
- No blocking privacy banner repeatedly obscures work; required notices use the existing acknowledged-state policy.
- Desktop 1440 and 1024, mobile 375 and 320 checked for clipping and keyboard accessibility.
- Run frontend build and existing unit tests; use meaningful E2E assertions on workflow outcomes rather than headings alone.
- Accessibility checks fail on serious/critical violations. Manual keyboard review includes drawer, dialog and tables.
- Report changed files, verification actually run, remaining failures, API gaps and screenshots. Never present existing failures as newly introduced without evidence.

## How to use this package

Open MDARIX-R1 in Codex. Attach this brief and the reference prototype. Ask: “Implement the attached MDARIX frontend redesign in my existing frontend. Follow the brief, preserve current backend contracts and authorization, and complete the phased implementation with build and browser verification. Use the prototype as the visual reference; do not copy its synthetic records into production.”

The prototype is a local interaction reference, not a production application. Its role selector switches mock screens only; it does not authenticate. Secondary administrator screens intentionally show design patterns. It makes no network calls, sends no messages and creates no real records or signatures.
