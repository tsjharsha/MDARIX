# MDX-SOP-005 Access control

| Field | Value |
|---|---|
| Document ID | MDX-SOP-005 |
| Title | Access control: MDARIX staff, support access and customer administrators |
| Version | 0.1 |
| Status | DRAFT |
| Author (R) | Sriharsha Telikicherla, Product & Engineering, system owner |
| Reviewer | Independent CSV consultant (not engaged yet) |
| Approver (A) | Srinivas Telikicherla, QA/RA, quality approver |
| Drafting | Drafted with software assistance; every line reviewed by Sriharsha Telikicherla (MDX-VAL-000, DC-R43) |
| Date | 14 Nov 2026 |
| Code baseline | Product code at `6b01eda5` (tip of `feat/b6b-validation-pack`); B6b Part C changes no code; release in preparation 0.11.04 (`VERSION` file still 0.10.94) |

Change history

| Version | Date | Change | By |
|---|---|---|---|
| 0.1 | 14 Nov 2026 | First draft (B6b Part C, item C3) | Sriharsha Telikicherla |

## 1. Purpose and scope

This procedure controls who can reach MDARIX's production systems and customers' data: MDARIX staff (servers,
cloud console, platform administration), MDARIX staff inside a customer's organisation (support access), and the
customer's own administrators and users. A customer's own periodic access review (G14) is the customer's control;
section 5 says what MDARIX provides for it.

## 2. MDARIX staff access

- **AC-R01** There shall be at least two platform administrators, each a named person
  (`docs/handover/52_SUPPORT_AND_OWNERSHIP_HANDOVER.md:14`).
- **AC-R02** Platform administrators, customer administrators, leaders and approvers shall use multi-factor
  authentication by default (`backend/app/mfa.py:35`); a server shall not run with that policy emptied
  (`backend/app/config_check.py:400-401`).
- **AC-R03** Server access shall be by SSH through the cloud provider's identity-aware proxy only; the default SSH
  and RDP firewall rules stay removed (`docs/runbooks/GCP_DEPLOYMENT.md:23`).
- **AC-R04** Production secrets shall be kept in a password manager and never committed (`AGENTS.md:40`).
- **AC-R05** A person who leaves MDARIX shall lose every production, cloud and platform account on their last
  working day.
- **AC-R06** Every 3 months, the quality approver shall review the list of people with server, cloud-console and
  platform-administrator access and record the review.

## 3. Support access to a customer's data (ADR-015)

- **AC-R07** MDARIX staff shall see or change an organisation's own data only under a support grant the customer
  approved (`backend/app/support_access.py:1-5`).
- **AC-R08** A grant shall name one colleague, the organisation, the areas, whether changes are allowed, the reason,
  and a window of at most 24 hours (`backend/app/support_access.py:6-7`).
- **AC-R09** A grant shall be approved for MDARIX by a platform administrator who is neither the requester nor the
  recipient (`backend/app/support_access.py:8`; `tests/test_support_access_sod.py::test_a_third_administrator_approves_support_access`).
- **AC-R10** A grant shall open only after one of the organisation's Customer Administrators approves it with their
  authenticator code (`backend/app/support_access.py:9-10`;
  `tests/test_support_access_customer_approval.py::test_customer_data_opens_only_after_the_customer_approves_and_every_use_is_theirs_to_see`).
- **AC-R11** Every use of a grant, and every refusal without one, shall be written to the organisation's own audit
  trail (`backend/app/support_access.py:13-17`).
- **AC-R12** The operational steps shall be those of `docs/runbooks/SUPPORT_ACCESS.md`.

## 4. Customer administrators and users

- **AC-R13** A customer's users and roles shall be created and changed only by that customer's administrators.
- **AC-R14** A Customer Administrator shall not approve a regulated decision (`MDX-B10-001-Intended-Use-Statement.md:66`).
- **AC-R15** Permissions shall be checked on the server for every protected action (`backend/app/access/permissions.py:210-225`).
- **AC-R16** Passwords shall follow NIST SP 800-63B: 12 to 128 characters, refused when breached, no periodic expiry
  (`auth/service.py:15-16`; owner decision O5).
- **AC-R17** Sign-in shall lock for 15 minutes after 5 failures (`backend/app/auth_router.py:70-71`).

## 5. Customer access review (G14)

MDARIX provides the signed access review (`backend/app/signed_reviews/access_review.py`;
`tests/test_b6a_signed_reviews.py::test_the_access_review`). The customer sets its interval, runs it and signs it
(MDX-SUP-002 section 3.2).

## 6. Records

Platform-administrator list; quarterly staff access reviews; support grants and their audit events; leaver records.

## Signatures

Unsigned. The signed PDF and its `signatures.csv` row are added after review (MDX-VAL-000 section 2.6).

| Role | Name | Meaning of signature | Signature | Date |
|---|---|---|---|---|
| Author (R), system owner | Sriharsha Telikicherla, Product & Engineering | I am responsible for this document and reviewed every line of the draft. | | |
| Reviewer (C) | Independent CSV consultant | I reviewed this document; my comments are recorded. | | |
| Approver (A), quality approver | Srinivas Telikicherla, QA/RA | I approve this procedure for use. | | |
