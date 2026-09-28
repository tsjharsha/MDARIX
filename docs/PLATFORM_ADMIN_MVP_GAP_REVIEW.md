# Platform Administrator frontend — MVP 1.0 gap review

Reviewed against `frontend/src/features/admin/PlatformAdminScreen.tsx` and the
agreed synthetic MVP scope.

## Complete or substantially complete

- Customers & Tenants: directory search, saved views, server filters,
  pagination, sorting, column selection, CSV import/export, lifecycle actions,
  Customer 360/Tenant 360 navigation, onboarding/provisioning entry points.
- Data & Configuration: Configuration 360, Mapping 360, mapping wizard,
  canonical model, transformation library, validation/data quality, baselines,
  releases, configuration health, and mapping-related record surfaces.
- Shared shell: one control-plane navigation model, responsive layout, refresh,
  loading/error/empty states, authenticated identity, and explicit server-data
  boundaries.

## Partial / generic areas

- Plans & Licensing: plan, entitlement, subscription, expiry, and reminder
  surfaces exist; deeper timeline, recipient, grace-period, and plan-transition
  workflows depend on dedicated durable APIs.
- Identity & Access: users, roles, permission sets, effective permissions,
  sessions, MFA/SSO, and access review entry points exist; MFA/SSO evidence and
  full record actions require authenticated execution.
- Integrations: connector catalog, registry, schema registry, API contract,
  health, and failure surfaces exist; durable run/reconciliation/credential
  detail records must be populated by simulator execution.
- AI Control Center: previously rendered as a generic summary. It now has a
  dedicated control-center layout with provider, model, execution,
  evaluation, and guardrail review checks.
- Security: previously rendered as a generic summary. It now has dedicated
  isolation, event, encryption, retention, and access-review cards, while
  production claims remain explicitly deferred.
- Operations: previously rendered as a generic summary. It now has dedicated
  queue, failed-job, dead-letter, worker, storage, and notification cards.

## Remaining MVP validation gaps

- Run authenticated browser validation for every subsection and capture desktop,
  mobile, keyboard, and screen-reader evidence.
- Confirm every subsection's backend source returns live authorized data; empty
  or unavailable states must be recorded rather than filled with demo values.
- Complete API-backed detail actions for subscription transitions, integration
  runs/reconciliation, AI execution history, security controls, and operational
  incidents where those records are not yet durable.
- Run the focused admin regression after frontend changes.

## Out of MVP scope / not closable by frontend code alone

- Production monitoring and alerting.
- Hosted multi-instance validation.
- Production PostgreSQL TLS, backups, PITR, and runtime-role proof.
- Real customer connector credentials and production operational data.

## Design decision

Customers/Tenants and Data/Configuration remain the record-management areas.
Plans/Licensing, Identity/Access, Integrations, AI, Security, and Operations
now use control-center layouts with evidence cards and domain-specific checks,
so the administrator can distinguish platform posture from individual records.

