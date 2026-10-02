# Customer and Tenant Model

Status: accepted for MVP 1.0. Phase A is implemented; Phases B to D are proposed.

## The rule

**A Customer is the legal and commercial parent. A Tenant is the operational and data-isolation boundary.**

One customer owns one or more tenants. Every user membership, administrator, plan, integration, mapping,
business record and authorization decision resolves to exactly one tenant. Customer-level data is limited to who
MDARIX contracted with.

```text
CUSTOMER (customers)                      who MDARIX contracted with
  ├── contacts, domains                   legal and commercial relationship
  └── TENANT (tenants)  1 : N             where and how MDARIX operates
        ├── plan / subscription           tenant_plan_assignments, subscription_lifecycles
        ├── environments                  tenant_environments (one of each type)
        ├── Customer Administrators       auth_users.role = CUSTOMER_ADMIN, one tenant each
        ├── users, memberships, roles     tenant_memberships, role_assignments, ...
        ├── integrations, mappings        connector_configurations, tenant_mapping_versions
        ├── security, identity providers  identity_provider_configurations, support_access_grants
        └── business data and audit       every business table carries tenant_id (row-level security)
```

Rules that hold today:

- A tenant has exactly one customer (`tenants.customer_id` is NOT NULL, foreign key to `customers`).
- A tenant never moves between customers; there is no endpoint that changes `customer_id`.
- Customer and tenant identifiers (`CUS0001`, `TEN0001`) are platform-issued and immutable (database triggers).
- Tenant codes (`tenant_key`) are globally unique; tenant names are unique within a customer.
- Belonging to the same customer gives no access across tenants. Row-level security filters on `tenant_id`.
- Customers and tenants are suspended, terminated and archived, never deleted.
- Customer and tenant states are separate: a customer can be ACTIVE while one of its tenants is SUSPENDED.
  Suspending a customer suspends all of its tenants.

## Customer Administrators belong to a tenant

A Customer Administrator is created **for a tenant, not for a customer**. A customer with three tenants has
administrators for each, and each administrator manages only the users of their own tenant.

- `POST /api/v1/platform-admin/tenants/{tenant_id}/customer-admins` adds an administrator to one tenant.
- Adding a tenant to a customer requires that tenant's first administrator, so no tenant starts without one.
- The "last active administrator" rule is per tenant. The only active administrator of a tenant cannot be
  suspended, even if another tenant of the same customer has several.
- One account per email. Sign-in finds the account by email, so the same email cannot be an administrator of
  two tenants yet. Phase C removes this limit.

## Mapping the proposed objects to the current schema

| Proposed object | Current table(s) | State |
|---|---|---|
| customer_account | `customers` | Exists. Code is `customer_identifier`. Lifecycle is `lifecycle_status`. |
| customer_contact | `customer_contacts`, plus JSON contacts on `customers` | Exists. The JSON columns are legacy. |
| tenant | `tenants` | Exists. Has `customer_id`, code, regions and lifecycle. No `is_primary` flag. |
| tenant environment | `tenant_environments` | Exists. One of each type per tenant: PRODUCTION, VALIDATION, SANDBOX, UAT, DEMO. |
| plan | `plan_definitions` | Exists. |
| feature / plan_entitlement | `feature_entitlements`, keyed by plan | Exists. **Defect: see Phase B.** |
| tenant_subscription | `tenant_plan_assignments`, `subscription_lifecycles` | Exists and is per tenant. History is kept: SUPERSEDED rows. |
| tenant_entitlement_override | none | **Missing (Phase B).** |
| user_account | `auth_users` | Per tenant, not global (Phase C). |
| tenant_membership | `tenant_memberships` | Exists. Its foreign key ties it to the user's own tenant. |
| role / permission sets | `role_definitions`, `role_assignments`, `permission_set_definitions` | Exists and is per tenant. |
| tenant_security_profile | `identity_provider_configurations`, `support_access_grants` | Partial (Phase D). |
| integration_connection | `connector_configurations` | Exists and is per tenant. |
| tenant_mapping_version | `tenant_mapping_versions`, `tenant_mapping_overrides` | Exists and is per tenant. |
| tenant_retention_policy | none | Missing (Phase D). |
| customer_contract | none | Missing (Phase D). |

## Phase A: implemented

- **One customer row, many tenants.** `GET /api/v1/platform-admin/customer-accounts` lists each customer once.
  Its tenants appear beneath it, each with plan, data region and active administrators. The Customers screen
  uses it. The CSV export keeps its existing shape: one row per tenant.
- **Add a tenant to an existing customer.** `POST /api/v1/platform-admin/customer-records/{customer_id}/tenants`
  creates, in one transaction:
  - the tenant;
  - its plan assignment;
  - its first environment;
  - its first Customer Administrator, who is invited by email;
  - a `TENANT_ADDED` audit event.

  The request is refused cleanly in these cases:
  - the customer is not active;
  - the tenant code already exists;
  - the customer already has a tenant with that name;
  - the email is already used;
  - the plan is not published.

  The plan's shared limits are not modified.
- **Screens show the relationship.**
  - The customer page has an "Add tenant" button.
  - The tenant page names its customer and has an Administrators section.
  - Administrator lists show each administrator's tenant.
  - "Add administrator" always asks for the tenant.
  - The tenant directory shows the owning customer.
- Tests: `tests/test_platform_customer_tenants.py`.

## Phase B: per-tenant limits (proposed, needs a migration)

**Defect.** Creating a customer through `POST /platform-admin/customers` writes that customer's seat, admin and
connector limits into the shared plan's `feature_entitlements` row. Every customer on the same plan then gets the
last-written limits. The onboarding wizard also records `licensed_users_limit` at plan level (it inserts an
entitlement row for the plan), not on the tenant.

Fix:

1. Add `tenant_entitlement_overrides`:
   - columns: `tenant_id`, `feature_code`, `enabled`, `limits`, `reason`, `contract_reference`,
     `effective_from`, `effective_to`, `approved_by`, `created_at`;
   - row-level security on `tenant_id`.
2. Compute effective limits as: plan default, then the tenant override. Do this in `_active_plan_limits`.
3. Customer creation and onboarding write the requested limits as an override, not into the plan.
4. Show and edit the overrides on the customer's Subscription section, with a reason.

## Phase C: one person, several tenants (proposed, larger change)

Today `auth_users` holds one row per person per tenant, and sign-in picks the account by email. To let one person
administer several tenants (for example Apex India and Apex EU):

1. Introduce a global identity (`user_accounts`: email, name, identity-provider subject, MFA). Keep
   `auth_users` as the tenant-scoped account and link it to the identity.
2. At sign-in, list the tenants where the person has an ACTIVE membership. Then either choose one, or use the
   default membership.
3. Make tenant switching real. Today `POST /me/tenant-context` changes only an in-memory session. It must rotate
   the stored `auth_sessions.tenant_id` and recalculate permissions. Records from two tenants are never merged.
4. Make the email uniqueness check identical in every flow. Today the trial, onboarding, add-admin and
   user-invite flows check it differently.

## Phase D: later

- `customer_contracts`: one enterprise agreement covering several tenant subscriptions.
- A tenant security profile:
  - MFA required;
  - session timeouts;
  - export approval;
  - IP restriction.
- `tenant_retention_policies`: retention per data class; legal hold.
- `tenants.is_primary_tenant`, and a tenant purpose (production, validation, sandbox) separate from its
  environments.
- Cross-tenant reporting for a customer, only through an explicit, governed aggregation layer.
