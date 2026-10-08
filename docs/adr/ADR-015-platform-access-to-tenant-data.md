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
## Status
ACCEPTED (2026-10-08)
