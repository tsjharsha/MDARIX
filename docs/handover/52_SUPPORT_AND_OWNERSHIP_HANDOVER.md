# Support and ownership handover

| Area | Owner | Where |
|---|---|---|
| Code, migrations, tests, CI | Engineering | This repository; CI must be green (release gate) before merge. |
| Deployment, secrets, databases, backups, monitoring, incidents | Platform operations | [DEPLOYMENT.md](../runbooks/DEPLOYMENT.md), [BACKUP_AND_RESTORE.md](../runbooks/BACKUP_AND_RESTORE.md), [39_OPERATIONAL_SUPPORT_RUNBOOK.md](39_OPERATIONAL_SUPPORT_RUNBOOK.md) |
| Data requests (export, erasure, deletion, legal hold) | Privacy contact (`MDARIX_PRIVACY_EMAIL`) with platform operations | [DATA_REQUESTS.md](../runbooks/DATA_REQUESTS.md) |
| Website claims, legal documents, trial terms | Product, with the company's lawyer | `legal/README.md`, `frontend/src/site/` |
| Customer systems: endpoints, mappings, credentials | The customer's administrator, with engineering during a pilot | [CUSTOMER_SYSTEM_INTEGRATION.md](../runbooks/CUSTOMER_SYSTEM_INTEGRATION.md) |

Customers reach support at `MDARIX_SUPPORT_EMAIL` (shown in the Help menu, on `/contact` and in every email).
Escalate with the request ID, the steps to reproduce and redacted evidence; never send customer records by email.
