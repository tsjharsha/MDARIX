# MDX-SUP-005 SOC 2 and ISO/IEC 27001 control mapping

| Field | Value |
|---|---|
| Document ID | MDX-SUP-005 |
| Title | SOC 2 and ISO/IEC 27001:2022 control mapping |
| Version | 0.1 |
| Status | DRAFT |
| Author (R) | Sriharsha Telikicherla, Product & Engineering, system owner |
| Reviewer | Independent CSV consultant (MDX-VAL-013 question 14; not engaged yet) |
| Approver (A) | Srinivas Telikicherla, QA/RA, quality approver |
| Drafting | Drafted with software assistance; every line reviewed by Sriharsha Telikicherla (MDX-VAL-000, DC-R43) |
| Date | 14 Nov 2026 |
| Code baseline | Product code at `6b01eda5` (tip of `feat/b6b-validation-pack`); B6b Part C changes no code; release in preparation 0.11.04 (`VERSION` file still 0.10.94) |

Change history

| Version | Date | Change | By |
|---|---|---|---|
| 0.1 | 14 Nov 2026 | First draft (B6b Part C, item C6): the theme-level mapping of the security policy outline (MDX-B10-007 section 6, planning draft) taken to control level | Sriharsha Telikicherla |

## 1. Purpose and scope

A customer's security reviewer often asks how MDARIX's controls relate to ISO/IEC 27001:2022 Annex A and to the
SOC 2 Trust Services Criteria. This document maps each control and criterion to what MDARIX does today.

**Wording.** Each control is **mapped**: MDARIX states what it has and what it does not. MDARIX holds no ISO/IEC 27001
certificate and no SOC 2 report, and nothing here says or implies that MDARIX is certified, compliant or aligned with
either. A mapping is not an audit.

Shared under a non-disclosure agreement only (owner decision B6b-D19).

## 2. Status words

| Status | Meaning |
|---|---|
| MDARIX control | MDARIX has a control; the evidence column names it |
| Inherited | The hosting provider runs the control; MDARIX relies on it, to confirm from the provider's reports (MDX-SUP-004 section 3) |
| Partly | Some of the control exists; the gap is named |
| Gap | No control today |
| Not applicable | The reason is given |

- **MAP-R01** Each ISO/IEC 27001:2022 Annex A control and each SOC 2 criterion in scope (CC1 to CC9, A1, C1) shall
  have one row with one status from section 2.
- **MAP-R02** Each row with status "MDARIX control" or "Partly" shall name its evidence.
- **MAP-R03** This mapping shall be reviewed every 12 months and when a gap is closed (owner decision B6b-D18).

Common evidence references used below: **SOP-1** to **SOP-5** = MDX-SOP-001 to -005; **HA** = MDX-SUP-004;
**P11** = MDX-SUP-003.

## 3. ISO/IEC 27001:2022 Annex A

### 3.1 Organisational controls (5.1 to 5.37)

| Control | Title | Status | MDARIX control and evidence |
|---|---|---|---|
| 5.1 | Policies for information security | Gap | A security policy set is outlined in a planning draft, not yet issued |
| 5.2 | Information security roles and responsibilities | Partly | System owner and quality approver (owner decision B6b-D1; MDX-VAL-001 section 6); on-call and privacy roles to be named (`docs/handover/52_SUPPORT_AND_OWNERSHIP_HANDOVER.md:3-14`) |
| 5.3 | Segregation of duties | MDARIX control | Nobody approves their own work (MDX-VAL-001 section 6); support grants need a second administrator and the customer (`backend/app/support_access.py:6-11`); rule versions not approved by their builder (owner decisions O3, O10) |
| 5.4 | Management responsibilities | Partly | Owner decisions recorded (MDX-VAL-000 section 4); no management review procedure yet |
| 5.5 | Contact with authorities | Partly | CERT-In and the Data Protection Board routes (`docs/runbooks/INCIDENT_RESPONSE.md` sections 4.2, 4.3); CERT-In point of contact after registration |
| 5.6 | Contact with special interest groups | Gap | none |
| 5.7 | Threat intelligence | Partly | Threat model (MDX-B10-006); dependency and image scans (SOP-1 SDLC-R15) |
| 5.8 | Information security in project management | MDARIX control | Specs approved before build; security rules in `AGENTS.md:34-40` (SOP-1) |
| 5.9 | Inventory of information and other associated assets | Partly | Sub-processor list (`legal/SUBPROCESSORS.md`); asset list of the threat model (MDX-B10-006 section 4.1); no full asset register |
| 5.10 | Acceptable use of information and other associated assets | Gap | none |
| 5.11 | Return of assets | Gap | none (no employees beyond the founders yet) |
| 5.12 | Classification of information | Gap | Data classes proposed in a planning draft, not approved |
| 5.13 | Labelling of information | Gap | none |
| 5.14 | Information transfer | Partly | HTTPS only (`infrastructure/docker/Caddyfile:1-2`); exports need the current authenticator code (`tests/test_export_purge_mfa.py::test_a_customer_administrators_own_export_needs_the_current_code`) |
| 5.15 | Access control | MDARIX control | SOP-5; server-side permission checks (`backend/app/access/permissions.py:210-225`) |
| 5.16 | Identity management | MDARIX control | One account per e-mail address per organisation (`backend/app/access/platform_customer_admins.py:216`); accounts by id (P11 row 11.100(a)) |
| 5.17 | Authentication information | MDARIX control | Password rules and breached-password check (`auth/service.py:15-16`); authenticator secrets encrypted (`auth/totp.py:1`) |
| 5.18 | Access rights | MDARIX control | Customer administrators manage roles; signed access review (`backend/app/signed_reviews/access_review.py`); staff access review every 3 months (SOP-5 AC-R06) |
| 5.19 | Information security in supplier relationships | Partly | Hosting assessment (HA); provider evidence to obtain |
| 5.20 | Addressing information security within supplier agreements | Gap | Provider data-processing terms to obtain (HA E-6, E-11) |
| 5.21 | Managing information security in the ICT supply chain | Partly | Image scans and SBOM (`.github/workflows/release.yml:2-4`); pinned action versions (`.github/workflows/ci.yml:790`) |
| 5.22 | Monitoring, review and change management of supplier services | Partly | Yearly re-assessment (HA HA-R03); not yet done once |
| 5.23 | Information security for use of cloud services | Partly | HA; keyless backup copy by the VM's service account (`docs/runbooks/GCP_DEPLOYMENT.md:7-8`) |
| 5.24 | Information security incident management planning and preparation | MDARIX control | SOP-3; `docs/runbooks/INCIDENT_RESPONSE.md` |
| 5.25 | Assessment and decision on information security events | MDARIX control | Severity SEV1 to SEV3 (`docs/runbooks/INCIDENT_RESPONSE.md:25-35`) |
| 5.26 | Response to information security incidents | MDARIX control | SOP-3 IR-R06 to IR-R11 |
| 5.27 | Learning from information security incidents | MDARIX control | Review within 5 business days (SOP-3 IR-R12); trend review (IR-R19) |
| 5.28 | Collection of evidence | Partly | Incident record with UTC times (SOP-3 IR-R01, IR-R02); hash-chained audit trail (`backend/app/audit_chain.py:1-12`); no forensic procedure |
| 5.29 | Information security during disruption | Partly | SOP-4; no disruption exercise yet |
| 5.30 | ICT readiness for business continuity | Partly | Restore drills (`docs/runbooks/BACKUP_AND_RESTORE.md:121-128`); single VM (HA H-2) |
| 5.31 | Legal, statutory, regulatory and contractual requirements | Partly | Regulatory applicability matrix (MDX-B10-002); legal texts with the lawyer |
| 5.32 | Intellectual property rights | Gap | none |
| 5.33 | Protection of records | MDARIX control | Audit trail kept 7 years, immutable (P11 row 11.10(c)); legal hold (`backend/app/legal_hold_api.py:1-10`) |
| 5.34 | Privacy and protection of PII | Partly | Personal-data erasure and purge (`docs/compliance/DATA_RETENTION_SCHEDULE.md:22-32`); customer contacts masked in exports by default (`backend/app/tenant_export.py:54`); DPA with the lawyer |
| 5.35 | Independent review of information security | Gap | Independent penetration test planned before the first paid pilot (`MDX-B10-001-Intended-Use-Statement.md:97`) |
| 5.36 | Compliance with policies, rules and standards for information security | Partly | Server refuses insecure settings at start (`backend/app/config_check.py:1-4`) |
| 5.37 | Documented operating procedures | MDARIX control | Runbooks in `docs/runbooks/`; SOP-1 to SOP-5 |

### 3.2 People controls (6.1 to 6.8)

| Control | Title | Status | MDARIX control and evidence |
|---|---|---|---|
| 6.1 | Screening | Gap | No employees beyond the founders; company not registered |
| 6.2 | Terms and conditions of employment | Gap | As 6.1 |
| 6.3 | Information security awareness, education and training | Partly | Qualification records for executors and approvers (MDX-VAL-001 VMP-R83); no security training programme |
| 6.4 | Disciplinary process | Gap | As 6.1 |
| 6.5 | Responsibilities after termination or change of employment | Partly | Leavers lose access on their last day (SOP-5 AC-R05) |
| 6.6 | Confidentiality or non-disclosure agreements | Partly | Supplier and release packs shared under NDA (owner decision B6b-D19); staff NDAs after registration |
| 6.7 | Remote working | Gap | none |
| 6.8 | Information security event reporting | Partly | Alerts page the on-call person (`docs/handover/52_SUPPORT_AND_OWNERSHIP_HANDOVER.md:40-48`) |

### 3.3 Physical controls (7.1 to 7.14)

| Control | Title | Status | MDARIX control and evidence |
|---|---|---|---|
| 7.1 to 7.6 | Perimeters, entry, offices, monitoring, environmental threats, secure areas | Inherited | Provider data centres (HA section 5; HA E-1, E-4) |
| 7.7 | Clear desk and clear screen | Gap | none |
| 7.8 | Equipment siting and protection | Inherited | Provider data centres |
| 7.9 | Security of assets off-premises | Gap | Build laptops: no written rule |
| 7.10 | Storage media | Partly | Backup key kept offline in two places (`docs/runbooks/BACKUP_AND_RESTORE.md:41-46`); provider media inherited |
| 7.11 to 7.13 | Supporting utilities, cabling, equipment maintenance | Inherited | Provider data centres |
| 7.14 | Secure disposal or re-use of equipment | Inherited | Provider media disposal (to confirm, HA E-4) |

### 3.4 Technological controls (8.1 to 8.34)

| Control | Title | Status | MDARIX control and evidence |
|---|---|---|---|
| 8.1 | User endpoint devices | Gap | Build laptops: no written rule |
| 8.2 | Privileged access rights | MDARIX control | Platform administrators with MFA (`backend/app/mfa.py:35`); customer data only under a customer-approved grant (`backend/app/support_access.py:1-17`); server access through the identity-aware proxy (`docs/runbooks/GCP_DEPLOYMENT.md:23`) |
| 8.3 | Information access restriction | MDARIX control | Forced row-level security on every tenant table (`tests/test_rls_coverage.py::test_every_table_with_a_tenant_id_has_forced_row_level_security`); no cross-organisation access (`tests/test_cross_tenant_routes.py::test_tenant_a_never_sees_tenant_b_records_through_any_business_route`) |
| 8.4 | Access to source code | Partly | Private repository; secret scan on every pull request (`.github/workflows/ci.yml:768-790`); account MFA not recorded |
| 8.5 | Secure authentication | MDARIX control | Lockout (`backend/app/auth_router.py:70-71`); MFA (`backend/app/mfa.py:35`); idle timeout (`backend/app/request_context.py:32`) |
| 8.6 | Capacity management | Partly | Memory limits per service (`docs/runbooks/GCP_DEPLOYMENT.md:18`); no capacity review |
| 8.7 | Protection against malware | MDARIX control | Uploaded files scanned by ClamAV (`docs/runbooks/GCP_DEPLOYMENT.md:5`) |
| 8.8 | Management of technical vulnerabilities | MDARIX control | Automatic security updates (`docs/runbooks/DEPLOYMENT.md:58-59`); release images scanned (`.github/workflows/release.yml:43-50`); code scanning (`.github/workflows/codeql.yml`) |
| 8.9 | Configuration management | MDARIX control | Server refuses insecure settings (`backend/app/config_check.py:1-4`); customer configuration snapshot (`backend/app/signed_reviews/configuration.py:73`) |
| 8.10 | Information deletion | MDARIX control | Organisation purge after hand-back, never under hold (`backend/app/tenant_purge.py:547,550-557`); exports deleted after 7 days (`backend/app/tenant_export.py:42`) |
| 8.11 | Data masking | Partly | Customer contacts masked in exports by default (`backend/app/tenant_export.py:54`) |
| 8.12 | Data leakage prevention | Partly | Credentials never exported (`backend/app/tenant_export.py:7-8`); no DLP tool |
| 8.13 | Information backup | MDARIX control | SOP-4; `docs/runbooks/BACKUP_AND_RESTORE.md:10-15` |
| 8.14 | Redundancy of information processing facilities | Gap | One VM in one zone (HA H-2) |
| 8.15 | Logging | MDARIX control | Audit trail (`backend/app/db/models/foundation.py:676-696`); request logs (`docs/compliance/DATA_RETENTION_SCHEDULE.md:41`) |
| 8.16 | Monitoring activities | MDARIX control | Uptime check every 5 minutes (`docs/runbooks/GCP_DEPLOYMENT.md:25`); daily audit-chain verification (`backend/app/audit_chain.py:54`) |
| 8.17 | Clock synchronization | MDARIX control | chrony (`docs/runbooks/DEPLOYMENT.md:57`); clock check, 1 s limit (`scripts/clock_check.py:1-8`) |
| 8.18 | Use of privileged utility programs | Partly | Scripts that change data need owner credentials and are recorded in the operations log (`docs/runbooks/BACKUP_AND_RESTORE.md:141,165`) |
| 8.19 | Installation of software on operational systems | MDARIX control | Release images from a tagged build only (SOP-1 SDLC-R17; SOP-2) |
| 8.20 | Networks security | MDARIX control | Firewall: web ports only; SSH through the proxy (`docs/runbooks/GCP_DEPLOYMENT.md:23,50-52`) |
| 8.21 | Security of network services | Partly | HTTPS with certificates renewed automatically (`infrastructure/docker/Caddyfile:1-2`); database over TLS `verify-full` (`docs/runbooks/GCP_DEPLOYMENT.md:19`) |
| 8.22 | Segregation of networks | Partly | Database not exposed to the internet (firewall, `docs/runbooks/GCP_DEPLOYMENT.md:23`); one VM |
| 8.23 | Web filtering | Not applicable | No staff browsing from production systems |
| 8.24 | Use of cryptography | MDARIX control | AES-GCM for stored files and authenticator secrets (`object_storage/service.py:8`; `auth/totp.py:1`); encrypted backups (`docs/runbooks/BACKUP_AND_RESTORE.md:41-46`); key rotation (`docs/runbooks/KEY_ROTATION.md`) |
| 8.25 | Secure development life cycle | MDARIX control | SOP-1 |
| 8.26 | Application security requirements | MDARIX control | Threat model (MDX-B10-006); security rules in `AGENTS.md:34-40` |
| 8.27 | Secure system architecture and engineering principles | MDARIX control | Architecture decisions in `docs/adr/` (for example ADR-015 platform access to tenant data) |
| 8.28 | Secure coding | MDARIX control | Linters and tests before merge (`AGENTS.md:66-67`) |
| 8.29 | Security testing in development and acceptance | Partly | Negative and cross-organisation tests (8.3 row); independent penetration test not yet run (5.35 row) |
| 8.30 | Outsourced development | Not applicable | No outsourced development |
| 8.31 | Separation of development, test and production environments | Partly | Separate test databases; no staging environment (owner decision B6b-D16) |
| 8.32 | Change management | MDARIX control | SOP-2 |
| 8.33 | Test information | MDARIX control | Synthetic test data only (SOP-1 SDLC-R08) |
| 8.34 | Protection of information systems during audit testing | Partly | Read-only checks on production; the GxP workflow check of a recovery runs on a scratch copy (owner decision B6b-D15) |

## 4. SOC 2 Trust Services Criteria

| Criterion | Topic | Status | MDARIX control and evidence |
|---|---|---|---|
| CC1.1 | Integrity and ethical values | Gap | No code of conduct yet |
| CC1.2 | Oversight by a board | Gap | Company not registered |
| CC1.3 | Structures, reporting lines, authorities | Partly | Roles and RACI (MDX-VAL-001 section 6) |
| CC1.4 | Commitment to competence | Partly | Qualification records (MDX-VAL-001 VMP-R83) |
| CC1.5 | Accountability | Partly | Signed release approval record (SOP-2 CC-R10) |
| CC2.1 | Relevant, quality information | MDARIX control | Hash-chained audit trail; release evidence in `docs/validation/releases/` |
| CC2.2 | Internal communication | Partly | Paging route (`docs/handover/52_SUPPORT_AND_OWNERSHIP_HANDOVER.md:40-48`) |
| CC2.3 | External communication | MDARIX control | Change notice (SOP-2 CC-R12 to CC-R14); incident notice (SOP-3 IR-R07) |
| CC3.1 | Objectives | Partly | Intended use (MDX-B10-001); SLO targets (`MDX-B10-001-Intended-Use-Statement.md:100`) |
| CC3.2 | Risk identification and analysis | MDARIX control | Product risk assessment (MDX-VAL-002); threat model (MDX-B10-006) |
| CC3.3 | Fraud risk | Gap | none |
| CC3.4 | Changes that affect internal control | MDARIX control | Change-impact assessment (SOP-2 CC-R05) |
| CC4.1 | Ongoing and separate evaluations | Partly | Restore drills; daily audit-chain verification; no internal audit |
| CC4.2 | Communicating deficiencies | MDARIX control | Deviation log (MDX-VAL-010); MDARIX CAPA log (B6b Part D) |
| CC5.1 | Control activities | MDARIX control | SOP-1 to SOP-5 |
| CC5.2 | General controls over technology | MDARIX control | ISO rows 8.2 to 8.32 |
| CC5.3 | Policies and procedures | Partly | SOPs; security policy set not issued (ISO 5.1) |
| CC6.1 | Logical access security | MDARIX control | ISO rows 8.2, 8.3, 8.5 |
| CC6.2 | Registration and authorisation of new users | MDARIX control | Customer administrators create accounts (SOP-5 AC-R13) |
| CC6.3 | Role-based access, change and removal | MDARIX control | ISO row 5.18 |
| CC6.4 | Physical access | Inherited | ISO rows 7.1 to 7.6 |
| CC6.5 | Disposal of protected assets | Partly | Purge and export expiry (ISO row 8.10); media inherited |
| CC6.6 | Threats from outside the system boundary | MDARIX control | ISO rows 8.20, 8.21 |
| CC6.7 | Transmission, movement and removal of information | MDARIX control | ISO rows 5.14, 8.24 |
| CC6.8 | Unauthorised or malicious software | MDARIX control | ISO rows 8.7, 8.19 |
| CC7.1 | Detecting configuration changes and vulnerabilities | MDARIX control | ISO rows 8.8, 8.9 |
| CC7.2 | Monitoring for anomalies | MDARIX control | ISO row 8.16; lockouts audited (`tests/test_auth_audit_events.py::test_sign_in_success_failure_lockout_and_sign_out_are_audited`) |
| CC7.3 | Evaluating security events | MDARIX control | ISO row 5.25 |
| CC7.4 | Responding to incidents | MDARIX control | ISO row 5.26 |
| CC7.5 | Recovering from incidents | MDARIX control | SOP-4 |
| CC8.1 | Change management | MDARIX control | SOP-2 |
| CC9.1 | Risk mitigation for business disruption | Partly | SOP-4; single VM (HA H-2) |
| CC9.2 | Vendor and business-partner risk | Partly | HA; provider evidence to obtain |
| A1.1 | Capacity | Partly | ISO row 8.6 |
| A1.2 | Environmental protection, backup and recovery infrastructure | Partly | Backups and drills (SOP-4); environment inherited |
| A1.3 | Testing recovery | MDARIX control | Quarterly restore drill (SOP-4 BC-R08); recovery record (B6b Part D) |
| C1.1 | Identifying and keeping confidential information | Partly | Tenant isolation (ISO row 8.3); no classification scheme (ISO 5.12) |
| C1.2 | Disposing of confidential information | MDARIX control | ISO row 8.10 |

## 5. Summary of gaps

The main gaps are organisational: no issued security policy set (5.1), no data classification (5.12, 5.13), supplier
agreements not on file (5.20), people controls that wait for the company's registration (6.1, 6.2, 6.4, CC1.2), no
independent penetration test yet (5.35), no redundancy beyond one VM (8.14) and no staging environment (8.31). Each is
an input to the security programme; none is closed by this document.

## Signatures

Unsigned. The signed PDF and its `signatures.csv` row are added after review (MDX-VAL-000 section 2.6).

| Role | Name | Meaning of signature | Signature | Date |
|---|---|---|---|---|
| Author (R), system owner | Sriharsha Telikicherla, Product & Engineering | I am responsible for this document and reviewed every line of the draft. | | |
| Reviewer (C) | Independent CSV consultant | I reviewed this document; my comments are recorded. | | |
| Approver (A), quality approver | Srinivas Telikicherla, QA/RA | I approve this mapping for use under a non-disclosure agreement. | | |
