# ADR-015: No Standing Platform Access to Tenant Data

## Context
Today platform administrators can export a tenant, read and write its product configuration, read its mappings, AI settings, audit trail and console tabs, erase its users and reset their MFA (`backend/app/access/platform_tenants.py`, `platform_reference.py`, `platform_customer_admins.py`, `tenant_export_api.py`). Support-access grants are created and approved by platform administrators only, do not record the requester, and gate nothing.
## Decision
Platform staff have **no standing access** to any cell. Routes that reach tenant data are not mounted in the `PLATFORM` role; each capability belongs to the Customer Administrator in the cell (export, purge, product configuration, mappings, AI settings, audit, user administration). Support access requires a request created in the platform and **approved by the Customer Administrator in the cell** with a scope (read-only), a named person and a duration of at most 24 hours; the cell creates a temporary MFA-protected read-only account that expires automatically, audits every action with a support tag, and can be revoked at any time. A sole-administrator lockout is recovered by the cell operator with an audited script on the cell host. Until Phase 5 lands, the interim rule records the requester and requires approver, requester and target to differ.
## Rationale
Customer-approved, time-boxed, audited access is what enterprise customers and regulators expect; it is also what the two-tenant proof's scenario 7 tests.
## Consequences
Platform onboarding no longer configures a customer's products; the customer administrator does, or MDARIX staff through an approved grant. Problem reports from a cell carry a reference, page and error code; free text only with the user's consent.
## Alternatives Considered
Platform-approved grants with separation of duties between platform administrators: rejected, because the customer is not in the loop.
## Implementation (Phase 5, 2026-10-11)
For every deployment role, not only cells, platform staff reach an organization's data only under a grant its
Customer Administrator approved (`backend/app/support_access.py`, `backend/app/support_access_api.py`, runbook
`docs/runbooks/SUPPORT_ACCESS.md`):
- A grant names a colleague, an organization, **areas** (Configuration, Audit trail, People, Full export), read-only
  or with changes, a reason and a window of at most 24 hours. A second platform administrator approves it for MDARIX
  (requester and recipient excluded); then a Customer Administrator approves it **with their authenticator code**, or
  denies it. Either side revokes it at any time. Migration md38 returned every grant approved by platform staff alone
  to "waiting for the customer".
- One gate guards each platform route that reaches an organization's data; a refusal (`403 CUSTOMER_APPROVAL_REQUIRED`)
  and every use are written to the organization's own audit trail, and the customer sees every use of each grant.
  Lists spanning organizations leave out what is not granted and say how much they left out.
- Kept open without a grant: the platform's own organization and its records about an organization; what MDARIX staff
  did inside an organization (staff accountability); legal hold and the final purge; problem reports a customer sent;
  provisioning Customer Administrators; and continuity, where nobody inside could act (the only active Customer
  Administrator's authenticator, the first one's activation).
- Differs from the decision above in one respect: instead of a temporary account in the cell, the grant opens the
  named areas to the colleague's own platform account, which keeps one identity per person and every use attributable.
  In a CELL deployment platform routes are not served at all (ADR-013), so the grant model applies to MULTI and to the
  platform's own records until cells host support access themselves (Phase 7).

## Status
ACCEPTED (2026-10-08); IMPLEMENTED (2026-10-11)
