# Platform Administrator Console

Status: implemented for Plans & Licensing, Data & Configuration, Identity & Access, Integrations, AI Control Center,
Security and Operations. Customers & Tenants is described in
[MDARIX_CUSTOMER_TENANT_MODEL.md](MDARIX_CUSTOMER_TENANT_MODEL.md).

## Principles

- Every tab shows its own real data. A tab is not shown if the backend has nothing behind it, and generic
  placeholder pages are not used.
- Plain language. A tenant is chosen from a list by its customer and name, never typed as an identifier. Statuses
  are shown as words and colours, and dates as dates.
- Platform-wide, metadata only. The platform views span every tenant, but they return only tenant, status,
  counts, timings, actions and actors. AI inputs and outputs, record contents, and audit old/new values never
  leave the tenant.
- The screens state what is not connected. For example, renewal reminders are queued, but sending them by email
  is not connected yet, and the page says so.

## Structure: 80 tabs became 29

| Area | Tabs | Data |
|---|---|---|
| Plans & Licensing | Plans · Subscriptions · Renewals · Reminders | `/platform-admin/plans`, `/platform-admin/customers`, `/platform-admin/console/renewals`, `/platform-admin/tenants/{id}/reminder-settings` |
| Data & Configuration | Data model · Mappings · Releases · Rules & reference data · Customer configuration | `/admin/mapping/canonical/*`, `/admin/configuration/mappings` (+ `/data-mappings`, `/versions`, `/release`, `/release-action`), `/admin/mapping/validate`, `/admin/mapping/transforms`, `/validation-rules`, `/override-policies`, `/platform-admin/reference-data`, `/platform/product-configuration/{tenant}` |
| Identity & Access | Platform users · Roles & permissions · Effective access | `/admin/identity/users`, `/roles`, `/roles/{id}/permission-sets`, `/permission-sets`, `/users/{id}/effective-access` |
| Integrations | Connector catalog · Runs & failures · Reconciliation · Credentials · API & schemas | `/admin/mapping/*`, `/platform-admin/console/integration-runs`, `/admin/integrations/credentials` |
| AI Control Center | Overview · Evaluations · Executions · Agents & guardrails | `/platform-admin/ai/models`, `/platform-admin/console/ai-activity`, `/evaluations/golden/latest`, `/ai/agents/catalog` |
| Security | Overview · Audit trail · Support access · Retention | `/platform-admin/console/security`, `/platform-admin/console/audit`, `/platform-admin/console/support-access` |
| Operations | System health · Queues & jobs · Email & notifications · Tenant cells · Developer API | `/platform-admin/console/operations`, `/health/ready`, `/platform-admin/console/cells`, `/platform-admin/api-contract` |

The code is in:
- `frontend/src/features/admin/areas/`: one file per area.
- `areas/sections.ts`: the tab lists, and where old tab names land.
- `backend/app/access/platform_console.py`: the platform-wide views (tests: `tests/test_platform_console.py`).

Old tab names still work as links. For example, "Reminder rules" opens Reminders and "Security events" opens
Audit trail.

## Behaviour changes

- **Reminder schedule:** the subscription lifecycle run uses each tenant's newest active reminder schedule
  (`reminder_schedules`). A tenant without one keeps 60, 30 and 7 days, with the same stage names as before.
- **Reminder email templates:** the screen offers only the variables the server accepts: `customer_name`,
  `expiry_date`, `days_remaining` and `activation_link`. The previous screen sent other names, so every save
  failed.
- **Support access:** Approve and Revoke work again. Each asks for a reason. The server refuses approval by the
  administrator who requested the access and by the one who would receive it (md35 records the requester), so a
  third platform administrator approves.

### Data & Configuration (25 tabs became 5)

- **Data model:** the MDARIX records, their fields, who may change each field (MDARIX only, customer with approval,
  customer), and the records a field links to. It replaces Canonical data model and the "Canonical Object 360" and
  "Schema 360" placeholders.
- **Mappings:** the mapping list and each mapping's field rules, a "Check mapping" (can it import records as
  written?), and its versions. The 3-step **New mapping** wizard (what to connect, fields, check and save) is shared
  with the Customer Administrator's Data Mapping screen. It saves the format the connector import reads, fills the
  required fields by matching names, and checks the mapping before saving it as a draft. See
  [CUSTOMER_SYSTEM_INTEGRATION.md](../runbooks/CUSTOMER_SYSTEM_INTEGRATION.md). This tab replaces Data mapping, Mapping versions,
  Validation & data quality, Configuration 360 / Mapping 360 and Configuration sets.
- **Releases:** the pipeline Draft → Waiting for approval → Approved → Released → Rolled back. Each mapping shows
  its one next step, every step asks for a reason, and approval must come from a different administrator (the
  server enforces this). A history panel shows who did what. It replaces Configuration releases, Configuration
  Release 360, Dependencies & impact, Change requests and Deployments.
- **Rules & reference data (read-only):**
  - transformations, validation and data-quality rules, and lookup rules;
  - value sets with their values;
  - countries, units, time zones and jurisdictions;
  - customer change policies.

  The new `GET /api/v1/platform-admin/reference-data` and `/reference-data/value-sets/{code}` read the seeded
  `md_master` tables.
- **Customer configuration:** choose a tenant to see and edit its products (new
  `PATCH /api/v1/platform/product-configuration/{tenant}/products/{product}`, audited; the identifier never
  changes), add versions, and see its connections and mapping versions. It replaces Master data, Customer
  baselines/overrides, Customer Configuration 360 and Upgrade center.

Fixed along the way:
- A mapping saved by the wizard listed as one field reading "[object Object]".
- Checking "ProductVersion" returned 404; a record is now found by its code or its name.
- Editing a product always failed.
- Release statuses offered buttons the server refused.

## Not shown yet (no backend)

These tabs come back when their backend exists:

| Capability | What is missing |
|---|---|
| Sessions | An endpoint that lists and revokes `auth_sessions` |
| MFA & SSO posture per user | MFA fields in the user list; a platform view of identity providers |
| Access reviews | A model and workflow |
| Webhooks | An admin registry of outbound webhooks |
| Prompts | A prompt registry (only `PROMPT_VERSION` exists) |
| Guardrail definitions | Endpoints for `AIGuardrailDefinition` (the agent limits are shown) |
| AI incidents, Revalidation | Models and workflow |
| Platform incidents | Endpoints for `PlatformIncident` |
| Storage, API monitoring | Metrics collection |
| Platform releases, Feature rollouts, System settings, MCP | No backend at all |
| Configuration change requests, deployments, import/export, upgrade campaigns | No backend; releases cover approval and roll-back |
| Configuration health (drift) | Scheduled schema-drift checks over connected systems |
| Renewal reminder delivery | A worker that sends queued `SUBSCRIPTION_REMINDER` events with the tenant's template |
