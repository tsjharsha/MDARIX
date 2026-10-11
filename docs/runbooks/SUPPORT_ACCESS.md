# Support access: how MDARIX staff reach a customer's data

A customer's data is theirs (ADR-012, ADR-015). MDARIX staff run the platform: customers, organizations, plans,
onboarding, the fleet. They see or change an organization's own data only under **support access the customer
approved**. The code is `backend/app/support_access.py` (the rule and the gate), `backend/app/support_access_api.py`
(the customer's side) and the support-access routes in `backend/app/access/platform_tenants.py` (the platform's side).

## The four areas a customer can grant

| Area | What it opens |
|---|---|
| Configuration | Products and versions, integrations, data mappings, AI settings |
| Audit trail | Everything people and systems did in the organization |
| People | The user directory, account recovery, erasure of personal data |
| Full export | A copy of every record of the organization (creating it and downloading it) |

Every grant is **read-only unless it asks for changes**, names one platform colleague, and lasts at most 24 hours.

## The steps

1. **Request** (Platform console > Security > Support access > Request access): the organization, the colleague, the
   areas, read-only or with changes, why, and for how long.
2. **Approve for MDARIX**: a *different* platform administrator, neither the requester nor the colleague, approves it.
   The organization's Customer Administrators are emailed that a request waits for them.
3. **The customer decides** (Customer Administration > Security > Support access): approve with a reason **and their
   authenticator code**, or deny. Platform administrators can never decide for a customer, even in an organization
   their account belongs to.
4. **Use**: every request the colleague makes under the grant is written to the organization's own audit trail
   (`SUPPORT_ACCESS_USED`, with the area, whether it changed something, and the address opened). The customer sees
   each use under the request's *History*, and a count in the list.
5. **End**: either side revokes it at any moment; otherwise it expires on its own.

Without a grant the platform answers `403 CUSTOMER_APPROVAL_REQUIRED` (naming the area needed) and writes the refusal
to the organization's audit trail (`SUPPORT_ACCESS_REFUSED`). Lists that span organizations (the console's audit
trail, the customer-user directory, a customer's integrations and activity) simply leave out what is not granted
and say how many organizations they left out (`withheld`, or `complete: false` for one organization's audit trail).

Grants approved before this rule existed were approved by platform administrators only: migration md38 put them back
to *waiting for the customer*, so none opens anything until the customer approves it.

## What stays open to platform staff, and why

| Without a grant | Why |
|---|---|
| The platform's own organization | It is MDARIX's |
| The platform's records about an organization: registry, lifecycle, plan, subscription, limits, usage counts, environments, domain and identity provider | They are the platform's, not the customer's records |
| What MDARIX staff did inside an organization (in its audit trail) | Staff accountability: the platform never hides its own staff's actions from itself |
| Legal hold, and the final purge | Lifecycle duties with their own safeguards (password, authenticator code, typed organization key, an export or a recorded waiver) |
| Problem reports a customer sent to MDARIX support | The customer chose to send them |
| The Customer Administrator directory, inviting and replacing administrators | Provisioning the people who decide is the platform's duty |
| Recovering the authenticator of an organization's **only** active Customer Administrator, or activating its **first** one | Continuity: nobody inside the organization could do it. As soon as another active administrator exists, the organization does it, or approves People access |

## Offboarding

A full export needs the customer's approval like any other access. Hand the data back while the organization is
still active: the customer exports it themselves (Customer Administration > Audit) or approves *Full export* for
MDARIX. A suspended organization cannot sign in to approve; the purge then records a waiver.

## Checks

- `tests/test_support_access_rules.py`: the rule on its own (areas, read-only, person, organization, window, only the
  customer's approval opens anything).
- `tests/test_support_access_customer_approval.py`: the whole flow through the API, including the email, the
  authenticator code, read-only enforcement, every use recorded, revocation, denial, audit visibility without a grant
  and the continuity case.
