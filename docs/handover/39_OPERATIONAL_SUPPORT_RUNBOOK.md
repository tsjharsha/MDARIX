# Operational support runbook

Below, `docker compose` means `docker compose -f docker-compose.prod.yml --env-file .env.production`, run in the
deployment directory on the VM. Security incidents and personal-data breaches:
[INCIDENT_RESPONSE.md](../runbooks/INCIDENT_RESPONSE.md). Worker, dead letters and scheduled jobs:
[OUTBOX_AND_SCHEDULER.md](../runbooks/OUTBOX_AND_SCHEDULER.md).

## First response

1. Get the **request ID** (every API error returns `request_id`; responses carry `X-Request-ID`), the time, the
   organization and the screen. Search the JSON logs for that ID (`docker compose logs api | grep <id>`): every log
   line of the request carries it.
2. Check `https://<domain>/health/status` (public; the uptime monitor polls it):

   | Answer | HTTP | Meaning |
   |---|---|---|
   | `{"status":"ok"}` | 200 | Everything is ready |
   | `{"status":"degraded"}` | 200 | Serving, but a component needs attention (data planes, object storage, worker, scheduler or email) |
   | `{"status":"down"}` | 503 | The database does not answer or its schema is not the one this release needs |

3. For the detail, read readiness on the VM (`/health` and `/health/ready` answer 404 from the internet):
   ```bash
   docker compose exec api python -c "from backend.app.readiness import readiness_report as r; import json; print(json.dumps(r(), indent=1))"
   ```
   Each check (`database`, `data_planes`, `object_storage`, `worker`, `scheduler`, `email`) shows `ok` and, when
   failing, an `error`. Results are cached for 10 seconds.
4. `docker compose ps` shows which service is unhealthy; `docker compose logs --since 1h <service>` shows why.
5. Never bypass an organization's access controls, and never change production data by hand. Corrections go through
   the application so they are audited.

## Alerts

Sent to `MDARIX_ALERT_WEBHOOK` (Slack/Teams channel) and/or `MDARIX_ALERT_EMAIL`. Prove delivery after any change
with `docker compose exec api python scripts/send_test_alert.py`. Alerts carry counts, job names and error types,
never customer records.

| Alert | Meaning | What to do |
|---|---|---|
| Event dead-lettered / Dead-letter queue grew | Outbox events failed all 12 attempts (about 5 hours) | Platform Admin > Operations > Queues & jobs > "Gave up after retries": read the error, fix the cause (often SMTP), Retry. |
| Background worker stopped / recovered | No worker heartbeat for over a minute | `docker compose ps background`, then its logs. |
| Scheduled job failing / recovered: `<job>` | A job failed three times in a row | `docker compose exec background python scripts/run_scheduler.py --list` shows each job's last result; the scheduler log has the error. |
| Scheduled job missed / running again: `<job>` | A job has not run within twice its interval | Is the scheduler running? Is a second instance holding the lock, or one job running very long? |
| Trial data could not be deleted | A trial past its retention could not be purged completely; nothing was changed | Read the error (`ROWS_REMAIN:<tables>` names a table holding rows a foreign key keeps); fix and let the job retry. |
| Audit trail integrity check failed | An organization's hash chain no longer verifies (`CHAIN_BROKEN` or `ANCHOR_CHANGED`) | SEV1: preserve the database and logs, do not change data, follow [INCIDENT_RESPONSE.md](../runbooks/INCIDENT_RESPONSE.md). |
| Backup failed (webhook only) | The nightly backup job stopped at a stage named in the alert | Read `/var/log/mdarix-backup.log`; fix and run the backup again ([BACKUP_AND_RESTORE.md](../runbooks/BACKUP_AND_RESTORE.md)). |
| Backups are not arriving (webhook only) | `scripts/check_backup_age.sh` (host cron) found no off-site backup newer than 26 hours (`MDARIX_BACKUP_MAX_AGE_HOURS`) | As above; also check the cron entries and the off-site bucket credentials. |

Two failures cannot alert from inside MDARIX, so outside monitors must cover them:

| Outside monitor | Fires when | What to do |
|---|---|---|
| Uptime monitor on `/health/status` | `down` (503) or no answer | SEV1: [INCIDENT_RESPONSE.md](../runbooks/INCIDENT_RESPONSE.md). |
| Dead-man's switch at `MDARIX_SCHEDULER_HEARTBEAT_URL` | No ping from the scheduler (every 5 minutes) | `docker compose ps background`, then its logs. The scheduler also raises the worker and dead-letter alerts, so they are silent while it is down. |
| Dead-man's switch at `MDARIX_BACKUP_HEARTBEAT_URL` (optional) | No successful backup ping | As for "Backup failed". |

## Break-glass: platform administrator lost MFA

Normal path: another platform administrator resets it (`POST /api/v1/platform-admin/users/{user_id}/mfa-reset` with
a reason; nobody can reset their own). That is why at least **two** platform administrators must exist:

```bash
docker compose run --rm migrate python scripts/create_platform_admin.py person@yourcompany.com --name "Full Name"
```

If no other platform administrator can sign in, on the VM:

```bash
docker compose run --rm migrate python scripts/reset_platform_admin_mfa.py <email> --reason "<ticket / why>"
```

It runs with the owner credentials, clears that platform administrator's MFA enrolment so they enrol again at their
next sign-in, records an audit event under the `MDARIX_PLATFORM` organization and prints the result. Confirm the
person's identity out of band (call them on a known number) before running it, and put the ticket in `--reason`.

## Common customer questions

- **"AI answers say they come from rules."** The organization's AI processing is off (the default for new
  organizations), its monthly allowance is used up, or no contracted provider is configured. Platform Admin > tenant >
  AI processing shows which; the customer administrator sees the same under Security > AI processing.
- **"I cannot sign in."** Locked after repeated failures (wait, or reset the password), MFA device lost (Users > Reset
  MFA, by another administrator), or the trial ended (the sign-in page says so, with the deletion date).
- **"Please send us all our data / delete our data / delete my data."** Follow
  [docs/runbooks/DATA_REQUESTS.md](../runbooks/DATA_REQUESTS.md).
- **Email not arriving.** All outgoing email goes through SMTP (`MDARIX_SMTP_*`). Platform Admin > Operations > Email
  & notifications shows whether SMTP is configured; the trial requests queue shows whether an invitation was sent or
  failed. Failed sends retry and end in "Gave up after retries" (above).
