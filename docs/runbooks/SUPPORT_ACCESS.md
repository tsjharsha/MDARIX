# Support access: how MDARIX staff reach a customer's data

A customer's data is theirs (ADR-012, ADR-015). MDARIX staff run the platform: customers, organizations, plans,
onboarding, the fleet. They see or change an organization's own data only under **support access the customer
approved**. The code is `backend/app/support_access.py` (the rule and the gate), `backend/app/support_access_api.py`
(the customer's side) and the support-access routes in `backend/app/access/platform_tenants.py` (the platform's side).

## The five areas a customer can grant

| Area | What it opens |
|---|---|
| Configuration | Products and versions, integrations, data mappings, AI settings |
| Audit trail | Everything people and systems did in the organization |
| People | The user directory, account recovery, erasure of personal data (read only: the user directory, to read) |
| Quality records | Complaints, investigations, decisions and data imports, to read (the read-only support workspace; since 0.10.39) |
| Full export | A copy of every record of the organization (creating it and downloading it) |

Every grant is **read-only unless it asks for changes**, names one platform colleague, and lasts at most 24 hours.

## The steps

1. **Request** (Platform console > Security > Support access > Request access): the organization, the colleague, the
   areas, read-only or with changes, why, and for how long.
2. **Approve for MDARIX**: a *different* platform administrator, neither the requester nor the colleague, approves it.
   The organization's Customer Administrators are emailed that a request waits for them.
3. **The customer decides** (Customer Administration > Security > Support access): approve with a reason **and their
   authenticator code**, or deny. Platform administrators can never decide for a customer, even in an organization
   their account belongs to. In a **free trial** the trial owner decides, and only the owner
   (Getting started > Team > Support access; `require_decision_maker` in `backend/app/support_access_api.py`): a
   colleague, or any Customer Administrator account in a trial, is refused (`TRIAL_OWNER_REQUIRED`). The decision
   makers (the Customer Administrators, or the trial owner) are emailed when MDARIX asks, when they approve, and when an
   approved access ends (revoked by either side, or expired). In a free trial every other active member is also told
   when it is approved and when it ends, for information only (no button: only the owner decides).
4. **Use**: the colleague's use of the grant is written to the organization's own audit trail
   (`SUPPORT_ACCESS_USED`, with the area, whether it changed something, and the address opened). Every change is
   written; repeated reads of the same address within 10 minutes are written once, so paging through a list (or the
   audit trail itself) is one use. The customer sees each use under the request's *History*, and a count in the
   list.
5. **End**: either side revokes it at any moment; otherwise it expires on its own. Access ends at the second it is
   revoked or expires; the scheduler's `support-access-expiry` (every 5 minutes) then records `SUPPORT_ACCESS_EXPIRED`
   and queues the email.

## Free trials: the read-only support workspace (0.10.39)

1. **Request** from Platform Admin > Customers & Tenants > Trials > **Request support access**: the request form,
   pre-filled with the trial, the signed-in administrator, Quality records, People and Audit trail (read only) and a
   reason to complete. Full export and Configuration are ticked on purpose only.
2. **Approve for MDARIX** as above (a second platform administrator), then the trial owner decides.
3. **Open read-only workspace** appears on the trial once the access is open to you. Every page carries the banner
   "MDARIX support, read-only, access granted by <owner> until <time>". It shows only the pages of the areas granted:
   complaints, investigations, decisions and imports (Quality records), the team (People), the audit trail (Audit
   trail), and the trial's chapters. **Export data** appears under a Full export grant and uses the organization's
   full export (`/platform-admin/tenants/{id}/exports`), with the administrator's authenticator code where MFA applies.
4. The workspace reads through `backend/app/support_workspace.py`: GET routes only, one area each, behind
   `require_customer_approved_access`; named fields only (never a password, an authenticator secret, a recovery code,
   a token or a session). Platform staff have no session in the trial, so no workspace route can act on its data for
   them. Each page read and each export is a `SUPPORT_ACCESS_USED` event in the trial's audit trail, and the owner sees
   it, in words, under the request's **History**.

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
- `tests/test_trial_support_workspace.py`: free trials: only the owner decides, every workspace page refused and
  audited without a grant, only the granted areas readable, no route that changes anything, no credential in any
  answer, the export only under a Full export grant, revocation and expiry ending access at once, and the emails.
