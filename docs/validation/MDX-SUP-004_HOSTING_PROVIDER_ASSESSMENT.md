# MDX-SUP-004 Hosting-provider assessment (G8)

| Field | Value |
|---|---|
| Document ID | MDX-SUP-004 |
| Title | Hosting-provider assessment: Google Cloud and Zoho (e-mail) |
| Version | 0.1 |
| Status | DRAFT |
| Author (R) | Sriharsha Telikicherla, Product & Engineering, system owner |
| Reviewer | none named (B6b spec section 3: R system owner, A quality approver) |
| Approver (A) | Srinivas Telikicherla, QA/RA, quality approver: the named approver of the decision in section 6 |
| Drafting | Drafted with software assistance; every line reviewed by Sriharsha Telikicherla (MDX-VAL-000, DC-R43) |
| Date | 14 Nov 2026 |
| Code baseline | Product code at `6b01eda5` (tip of `feat/b6b-validation-pack`); B6b Part C changes no code; production hosting as described in `docs/runbooks/GCP_DEPLOYMENT.md` and `legal/SUBPROCESSORS.md` on that commit |

Change history

| Version | Date | Change | By |
|---|---|---|---|
| 0.1 | 14 Nov 2026 | First draft (B6b Part C, item C5) | Sriharsha Telikicherla |

## 1. Purpose and scope

MDARIX runs on services from other companies. This document assesses the ones that hold or process customer data
in production today, records what MDARIX inherits from them and what it does not, and states a decision with a
named approver (MDX-B10-008 section 4.3, steps 1 to 3).

In scope: Google Cloud (application server, database on that server, disk snapshots, off-site backup storage,
administrator access, uptime monitoring) and Zoho (transactional e-mail and mailboxes). Out of scope here: services
that hold no customer data (domain registrar, certificate authority, heartbeat monitor), source hosting and CI, and
any AI provider (AI is off; `legal/SUBPROCESSORS.md:18`). Pilot hosting on another provider (ADR-017,
`docs/adr/ADR-017-hosting-staging-and-pilots.md:29-30`) needs its own assessment before it receives customer data
(MDX-SOP-002, CC-R09).

## 2. Services, data and regions

| Provider | Service | Data | Region | Evidence |
|---|---|---|---|---|
| Google Cloud (Google Cloud India Private Limited) | Compute Engine VM `e2-standard-2`, Ubuntu 24.04, Shielded VM; runs the web server, API, worker, scheduler, virus scanner and PostgreSQL 16 | All customer content and account data; audit trail | Mumbai, `asia-south1`, zone `asia-south1-a` | `docs/runbooks/GCP_DEPLOYMENT.md:4-6,18-19,48`; `legal/SUBPROCESSORS.md:12-13` |
| Google Cloud | Persistent disk snapshots, daily, 14 days | Database and stored files (disk image) | Mumbai (`--storage-location=asia-south1`) | `docs/runbooks/GCP_DEPLOYMENT.md:21` |
| Google Cloud | Cloud Storage bucket for off-site backups: versioning, 30-day retention policy, deleted after 89 days | Encrypted backups; the key is never held by the provider | Delhi, `asia-south2` | `docs/runbooks/GCP_DEPLOYMENT.md:22`; `legal/SUBPROCESSORS.md:15` |
| Google Cloud | Identity-Aware Proxy for SSH; firewall rules | none | n/a | `docs/runbooks/GCP_DEPLOYMENT.md:23,51-52` |
| Google Cloud | Cloud Monitoring uptime check on `/health/status` every 5 minutes, e-mail alert | none (status only) | n/a | `docs/runbooks/GCP_DEPLOYMENT.md:25` |
| Zoho ZeptoMail (Zoho Corporation Private Limited) | Transactional e-mail (`smtp.zeptomail.in`) | Recipient name and e-mail address; e-mail content (no quality records) | India (Zoho's Indian data centres) | `legal/SUBPROCESSORS.md:16` |
| Zoho Mail (Zoho Corporation Private Limited) | Operator mailboxes (support, privacy) | Whatever people write to them | India (Zoho's Indian data centres) | `legal/SUBPROCESSORS.md:17` |

## 3. Provider evidence

The provider's own audit reports are **not** quoted or summarised here from memory. Each is to be downloaded from the
provider's compliance portal, which needs a sign-in, and filed with this assessment.

| # | Item | Provider | Where | Status |
|---|---|---|---|---|
| E-1 | ISO/IEC 27001 certificate (Google Cloud) | Google Cloud | Compliance Reports Manager | To obtain (owner, provider compliance portal) |
| E-2 | ISO/IEC 27017 certificate (Google Cloud) | Google Cloud | Compliance Reports Manager | To obtain (owner, provider compliance portal) |
| E-3 | ISO/IEC 27018 certificate (Google Cloud) | Google Cloud | Compliance Reports Manager | To obtain (owner, provider compliance portal) |
| E-4 | SOC 2 Type II report (Google Cloud), latest period | Google Cloud | Compliance Reports Manager | To obtain (owner, provider compliance portal) |
| E-5 | SOC 3 report (Google Cloud) | Google Cloud | Compliance Reports Manager | To obtain (owner, provider compliance portal) |
| E-6 | Cloud Data Processing Addendum, as accepted for the MDARIX billing account, with its breach-notice clause | Google Cloud | Cloud console, account terms | To obtain (owner, provider compliance portal) |
| E-7 | Data-location commitment for Compute Engine, persistent disk snapshots and Cloud Storage in `asia-south1` and `asia-south2` (service-specific terms) | Google Cloud | Account terms | To obtain (owner, provider compliance portal) |
| E-8 | Free-trial terms and the trial end date of the MDARIX billing account | Google Cloud | Cloud console, Billing | To obtain (owner, provider compliance portal) |
| E-9 | ISO/IEC 27001 certificate (Zoho) | Zoho | Zoho compliance page | To obtain (owner, provider compliance portal) |
| E-10 | SOC 2 Type II report (Zoho), latest period | Zoho | Zoho compliance page, on request | To obtain (owner, provider compliance portal) |
| E-11 | Zoho Data Processing Addendum, with its breach-notice clause and data-centre region for ZeptoMail and Zoho Mail | Zoho | Zoho account | To obtain (owner, provider compliance portal) |

- **HA-R01** Each item E-1 to E-11 shall be filed (date downloaded, report period, file SHA-256) before the decision
  in section 6 is signed for customer data.
- **HA-R02** A report whose period ended more than 12 months before its review shall be replaced by the newer one.

## 4. Risks and what MDARIX does about them

| # | Finding | Effect | MDARIX control or plan | Evidence |
|---|---|---|---|---|
| H-1 | **Free-trial billing account.** Production runs on the provider's free trial; a trial account's resources stop when the trial ends. The 90-day trial and the build of 14 Oct 2026 put its end at about 11 Jan 2027 (exact date: E-8) | Service and data stop if not upgraded in time | Upgrade to a full account, or move, before the end date; billing status checked monthly (MDX-SOP-004 BC-R19) | `docs/runbooks/GCP_DEPLOYMENT.md:27-29,39` |
| H-2 | **One VM in one zone** (`asia-south1-a`) | A zone or VM failure stops the service until it is rebuilt | Rebuild from runbook; restore from backup; recovery time objective 4 hours | `docs/runbooks/GCP_DEPLOYMENT.md:48`; `docs/runbooks/BACKUP_AND_RESTORE.md:5,136` |
| H-3 | **PostgreSQL on the VM, no point-in-time recovery** | Up to about a day of records can be lost (recovery point 24 hours) | Daily encrypted backup and daily disk snapshot; stated to customers per owner decision B6b-D8; managed database with point-in-time recovery planned for pilots | `legal/SUBPROCESSORS.md:13`; `docs/runbooks/GCP_DEPLOYMENT.md:172-174,205`; `docs/runbooks/BACKUP_AND_RESTORE.md:3-5` |
| H-4 | **Stored files on the VM disk** | Up to 24 hours of uploads at risk with the VM | Daily backup copies them off-site | `docs/runbooks/GCP_DEPLOYMENT.md:20`; `docs/runbooks/BACKUP_AND_RESTORE.md:34-35` |
| H-5 | **No alert when the off-site copy fails** | A silent backup gap | Daily manual check until an alert exists (MDX-SOP-004 BC-R07a) | `docs/runbooks/GCP_DEPLOYMENT.md:170-171` |
| H-6 | Provider's audit reports and data-processing terms not yet on file | Assessment incomplete | Section 3 | this document |

## 5. What MDARIX inherits, and what it does not

| Area | Inherited from the provider (to confirm in E-1 to E-5) | MDARIX's own responsibility |
|---|---|---|
| Physical and environmental security of data centres | Yes | none |
| Hardware, hypervisor, provider network | Yes | none |
| Encryption of disks at rest by the provider | Yes | Application-level encryption of stored files and authenticator secrets (`object_storage/service.py:8`; `auth/totp.py:1`); encryption of backups with a key the provider never holds (`docs/runbooks/BACKUP_AND_RESTORE.md:41-46`) |
| Operating system, Docker, PostgreSQL, application | No | Patching (`docs/runbooks/DEPLOYMENT.md:58-59`), configuration, validation |
| Backups, restore, recovery | Partly (snapshot storage) | Backup, drills, recovery (MDX-SOP-004) |
| Access to the server | Partly (identity-aware proxy) | Who has access (MDX-SOP-005) |
| Availability of one VM | No provider availability commitment is relied on | Recovery per MDX-SOP-004 |

## 6. Decision

Proposed decision, which takes effect only when the approver signs:

**Approved with conditions**, for the free-trial phase, in which customers use synthetic sample data only
(`MDX-B10-001-Intended-Use-Statement.md:96`).

**Not approved for a paid pilot's real data** until:

1. E-1 to E-11 are on file and reviewed (HA-R01);
2. H-1 is closed: the account is upgraded or production is moved, with this assessment updated;
3. the pilot hosting is assessed (managed database with point-in-time recovery, ADR-017), or this assessment is
   updated to cover the pilot on this provider;
4. the legal entity that contracts with the provider is named: [legal entity: to be added on registration].

- **HA-R03** This assessment shall be repeated every 12 months (owner decision B6b-D18), and on a change of the
  provider's terms, region or certifications, or a provider incident that affects MDARIX.

## Signatures

Unsigned. The signed PDF and its `signatures.csv` row are added after review (MDX-VAL-000 section 2.6).

| Role | Name | Meaning of signature | Signature | Date |
|---|---|---|---|---|
| Author (R), system owner | Sriharsha Telikicherla, Product & Engineering | I am responsible for this document and reviewed every line of the draft. | | |
| Approver (A), quality approver | Srinivas Telikicherla, QA/RA | I approve the decision in section 6 with its conditions. | | |
