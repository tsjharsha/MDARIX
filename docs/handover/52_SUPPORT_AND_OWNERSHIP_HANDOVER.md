# Support and ownership handover

Replace every `[PLACEHOLDER]` with a named person (name, email, phone) before the first design partner goes live, and
keep this table current. A role nobody holds is a gap, not a default.

## Named owners

| Role | Person | Responsible for |
|---|---|---|
| Primary on-call | `[PRIMARY ON-CALL]` | First response to every alert and outside monitor; incident lead until handed over |
| Backup on-call | `[BACKUP ON-CALL]` | Takes over when the primary does not acknowledge within 15 minutes, or is away |
| Engineering owner | `[ENGINEERING OWNER]` | Code, migrations, CI, releases and rollbacks; final escalation |
| Privacy contact | `[PRIVACY CONTACT]` (`MDARIX_PRIVACY_EMAIL`) | Data requests, breach assessment, approval of customer breach notifications |
| Platform administrators (at least two) | `[PLATFORM ADMIN 1]`, `[PLATFORM ADMIN 2]` | Console actions: dead letters, MFA resets, tenant suspension, legal hold |

## Areas

| Area | Owner | Where |
|---|---|---|
| Code, migrations, tests, CI | Engineering owner | This repository; CI must be green before merge. |
| Deployment, secrets, databases, backups, monitoring | Primary on-call, with the engineering owner | [DEPLOYMENT.md](../runbooks/DEPLOYMENT.md), [BACKUP_AND_RESTORE.md](../runbooks/BACKUP_AND_RESTORE.md), [39_OPERATIONAL_SUPPORT_RUNBOOK.md](39_OPERATIONAL_SUPPORT_RUNBOOK.md) |
| Incidents | Incident lead (primary on-call by default) | [INCIDENT_RESPONSE.md](../runbooks/INCIDENT_RESPONSE.md) |
| Background worker, dead letters, scheduled jobs | Primary on-call | [OUTBOX_AND_SCHEDULER.md](../runbooks/OUTBOX_AND_SCHEDULER.md) |
| Data requests (export, erasure, deletion, legal hold) | Privacy contact, with a platform administrator | [DATA_REQUESTS.md](../runbooks/DATA_REQUESTS.md) |
| Website claims, legal documents, trial terms | Product, with the company's lawyer | `legal/README.md`, `frontend/src/site/` |
| Customer systems: endpoints, mappings, credentials | The customer's administrator, with engineering during a pilot | [CUSTOMER_SYSTEM_INTEGRATION.md](../runbooks/CUSTOMER_SYSTEM_INTEGRATION.md) |

## Response targets

Time to a person acknowledging and starting work, around the clock unless it says business day.

| Signal | Severity | Target |
|---|---|---|
| Audit trail integrity check failed | SEV1 | 1 hour |
| Site down: `/health/status` answers `down` (503) or nothing | SEV1 | 1 hour |
| Background worker stopped (alert, or worker check failing in readiness) | SEV2 | 1 hour |
| Backup failed, or newest off-site backup older than 26 hours | SEV2 | Same business day |
| Dead-lettered events | SEV3 | Next business day |

## Paging route

1. The uptime monitor (on `/health/status`) and the `MDARIX_ALERT_WEBHOOK` channel notify the **primary on-call**.
   Outside heartbeat monitors (`MDARIX_SCHEDULER_HEARTBEAT_URL`, `MDARIX_BACKUP_HEARTBEAT_URL`) page the same person.
2. No acknowledgement within **15 minutes**: the **backup on-call** is paged.
3. Either on-call escalates to the **engineering owner** when the fix needs a code change, a rollback or a restore, or
   when a SEV1 is not contained within the hour.
4. Any suspected personal-data breach: the incident lead brings in the **privacy contact** at once (72-hour clock,
   [INCIDENT_RESPONSE.md](../runbooks/INCIDENT_RESPONSE.md)).

Configure the uptime monitor and the alert channel so they page phones, not only post to a channel nobody watches at
night.

## Weekly dead-letter review

Every Monday, the primary on-call (or a platform administrator they name):

1. Opens **Platform Admin > Operations > Queues & jobs > "Gave up after retries"**.
2. For each group (event kind and organization): reads the last error, decides **Retry** (cause fixed) or **Discard**
   (not needed), and enters the reason; the console writes it to that organization's audit trail.
3. Records in the operations log: date, reviewer, number of groups and items, decision per group, cause, and any
   follow-up ticket. An empty queue is recorded too.
4. Raises a ticket for the engineering owner when the same cause appears two weeks running.

## Customer support

Customers reach support at `MDARIX_SUPPORT_EMAIL` (shown in the Help menu, on `/contact` and in every email).
Escalate with the request ID, the steps to reproduce and redacted evidence; never send customer records by email.
