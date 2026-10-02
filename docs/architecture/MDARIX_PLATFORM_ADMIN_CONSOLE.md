# Platform Administrator Console

Status: implemented for Plans & Licensing, Identity & Access, Integrations, AI Control Center, Security and
Operations. Customers & Tenants is described in [MDARIX_CUSTOMER_TENANT_MODEL.md](MDARIX_CUSTOMER_TENANT_MODEL.md).
Data & Configuration is unchanged.

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

## Structure: 55 tabs became 24

| Area | Tabs | Data |
|---|---|---|
| Plans & Licensing | Plans · Subscriptions · Renewals · Reminders | `/platform-admin/plans`, `/platform-admin/customers`, `/platform-admin/console/renewals`, `/platform-admin/tenants/{id}/reminder-settings` |
| Identity & Access | Platform users · Roles & permissions · Effective access | `/admin/identity/users`, `/roles`, `/roles/{id}/permission-sets`, `/permission-sets`, `/users/{id}/effective-access` |
| Integrations | Connector catalog · Runs & failures · Reconciliation · Credentials · API & schemas | `/admin/mapping/*`, `/platform-admin/console/integration-runs`, `/admin/integrations/credentials` |
| AI Control Center | Overview · Evaluations · Executions · Agents & guardrails | `/platform-admin/ai/models`, `/platform-admin/console/ai-activity`, `/evaluations/golden/latest`, `/ai/agents/catalog` |
| Security | Overview · Audit trail · Support access · Retention | `/platform-admin/console/security`, `/platform-admin/console/audit`, `/platform-admin/console/support-access` |
| Operations | System health · Queues & jobs · Email & notifications · Developer API | `/platform-admin/console/operations`, `/health/ready`, `/platform-admin/api-contract` |

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
- **Support access:** Approve and Revoke work again. Each asks for a reason and refuses self-approval, as the
  server already did.

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
| Renewal reminder delivery | A worker that sends queued `SUBSCRIPTION_REMINDER` events with the tenant's template |
