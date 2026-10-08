# Incident response

For anything that threatens the availability, integrity or confidentiality of MDARIX or of customer data. Owners,
response targets and the paging route are in
[52_SUPPORT_AND_OWNERSHIP_HANDOVER.md](../handover/52_SUPPORT_AND_OWNERSHIP_HANDOVER.md).

Below, `docker compose` means `docker compose -f docker-compose.prod.yml --env-file .env.production`, run in the
deployment directory on the VM.

The first person on the incident is the **incident lead** until they hand it over by name. Open an incident record
(a ticket or a shared document) at once, give it a reference number (`INC-YYYY-NNN`) and write every action in it with
the time (UTC).

## 1. Detect

| Source | Example |
|---|---|
| Alerts (`MDARIX_ALERT_WEBHOOK` channel / `MDARIX_ALERT_EMAIL`) | Worker stopped, job failing or missed, dead letters, backup failed or too old |
| Uptime monitor on `https://<domain>/health/status` | `down` (HTTP 503) or no answer |
| Outside heartbeat monitors | `MDARIX_SCHEDULER_HEARTBEAT_URL` or `MDARIX_BACKUP_HEARTBEAT_URL` not pinged |
| Audit-chain verification | Alert "Audit trail integrity check failed" (`CHAIN_BROKEN` or `ANCHOR_CHANGED`) |
| Customer report | Support email, Help menu problem report |
| Security notices | Dependency or image advisories (CI, Dependabot), provider notices, a report from a researcher |

## 2. Triage

| Severity | Meaning | Examples |
|---|---|---|
| **SEV1** | Customer data exposed or at risk, data integrity in doubt, or the service is down for everyone | Suspected breach or cross-organization access, audit-chain failure, `/health/status` = `down`, lost data |
| **SEV2** | A major function is broken for one or more customers; no data at risk | Worker stopped, email not sending, backups failing, `/health/status` = `degraded` for over an hour |
| **SEV3** | Limited impact or a workaround exists | A few dead-lettered events, one failing connector |

When unsure, pick the higher severity. Any SEV1 that may involve personal data starts the clock in section 4: write
down when you became aware.

## 3. Contain

Do only what limits the damage. Do not change or delete data by hand.

1. **Preserve evidence before changing anything.**
   - Logs: `docker compose logs --since 48h --timestamps > INC-<ref>-logs.txt` (api, worker, scheduler, web). The
     JSON log driver keeps about 200 MB per service, so do this early.
   - Database: take a manual snapshot in the managed database console, named with the incident reference. Note the
     time: point-in-time recovery can go back to just before the incident while it is inside the retention window.
   - Store both outside the VM with restricted access.
2. **Rotate what may be exposed** (each one: new value in `.env.production` or `.env.migrate`, then redeploy as in
   [DEPLOYMENT.md](DEPLOYMENT.md); see [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) for each variable).
   - `MDARIX_RLS_SYSTEM_TOKEN`: the migrate job stores the new hash (`scripts/set_rls_system_token.py`); then
     recreate api, worker and scheduler so they use the new token.
   - `MDARIX_DB_RUNTIME_PASSWORD`: the migrate job sets it (`scripts/configure_runtime_role.py`). Owner and backup
     passwords: change them in the managed database, then in `.env.migrate`.
   - SMTP credentials (`MDARIX_SMTP_PASSWORD`): rotate at the mail provider first.
   - Connector encryption key: new `MDARIX_CONNECTOR_ENCRYPTION_KEY`, old key kept in
     `MDARIX_CONNECTOR_ENCRYPTION_KEYS`, then `python scripts/reseal_connector_keys.py --apply`, then remove the old
     key. Customer system credentials are rotated by the customer's administrator.
3. **Cut off access.**
   - One user: the customer administrator suspends them (Users); this ends their sessions. A customer administrator:
     a platform administrator suspends them (Platform Admin, tenant page, "Customer administrators"). A whole
     organization: "Suspend tenant" on its tenant page.
   - Everyone: `docker compose stop web` takes the site off the internet (Caddy is the only public entry). Start it
     again with `docker compose start web`.
4. **Hold data.** If evidence must outlive normal deletion, set a legal hold on the organization:
   `PUT /api/v1/platform-admin/tenants/{tenant_id}/legal-hold` with `{"hold": true, "reason": "INC-<ref> ..."}`
   (platform administrator with a completed MFA sign-in; there is no console button yet). Purge, erasure and trial
   retention then refuse for that organization. See [DATA_REQUESTS.md](DATA_REQUESTS.md).

## 4. Notify

If personal data may have been accessed, changed, lost or disclosed without authorization, notify each affected
customer **without undue delay and no later than 72 hours after becoming aware**. Customer contracts and data
processing agreements may set shorter deadlines; the shortest one applies. Do not wait for the full picture: send what
is known and follow up.

Whether a regulator or the people concerned must be notified is the customer's decision as controller, or for the
company's own data the company lawyer's. Do not advise customers on that beyond the facts.

**Notification to a customer** (one per affected organization, sent to its administrators and contract contact):

| Field | Content |
|---|---|
| Reference | `INC-<ref>` |
| What happened | Plain description, no speculation |
| When | When it started (if known) and when we discovered it |
| Data and organizations affected | Categories of data, the organization, approximate number of records and people |
| Likely consequences | For the customer and the people concerned |
| Measures taken | Containment so far, and what is still in progress |
| What the customer should do | For example reset passwords, review the audit trail, rotate their system credentials |
| Contact point | Name and email of the incident lead and `[PRIVACY CONTACT]` |

**Sign-off before sending:** the incident lead and `[PRIVACY CONTACT]` both approve the text. Record in the incident
record who approved, when, what was sent to whom, and the reasons for any decision not to notify.

## 5. Recover

- Fix the cause, then restore service: `docker compose up -d`, then check `/health/status` and readiness
  ([39_OPERATIONAL_SUPPORT_RUNBOOK.md](../handover/39_OPERATIONAL_SUPPORT_RUNBOOK.md)).
- Data loss or corruption: restore or recover to a point in time as in
  [BACKUP_AND_RESTORE.md](BACKUP_AND_RESTORE.md). Never overwrite the production database before the restored copy is
  verified.
- Retry dead-lettered events once the cause is fixed ([OUTBOX_AND_SCHEDULER.md](OUTBOX_AND_SCHEDULER.md)).
- Lift the legal hold and the suspensions only when the incident lead decides, and record it.
- Tell the affected customers that service is restored.

## 6. Review

Within **5 business days** of closing a SEV1 or SEV2, hold a blameless review and add to the incident record:

- Timeline (detection, each decision, containment, notification, recovery), in UTC.
- Root cause and why it was not caught earlier.
- Actions, each with an owner and a due date, tracked to completion.
- What to change in this runbook, the alerts or the monitors.
