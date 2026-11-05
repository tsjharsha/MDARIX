# Background worker (outbox) and scheduler

Two long-running processes do the work that does not happen inside a web request: the **worker**
(`scripts/run_outbox_worker.py`) and the **scheduler** (`scripts/run_scheduler.py`). In `docker-compose.prod.yml`
both run in the one `background` service (`scripts/run_background.py` starts them, passes a stop signal to both,
and exits if either stops, so Docker restarts the container; its health check needs both heartbeats). Both refuse to start with an unsafe staging/production configuration
(`backend/app/config_check.py`), the same gate the API applies.

Below, `docker compose` means `docker compose -f docker-compose.prod.yml --env-file .env.production` (or plain
`docker compose` once the deploy user's profile exports `COMPOSE_FILE=docker-compose.prod.yml` and
`COMPOSE_ENV_FILES=.env.production`).

## 1. The outbox

When the application changes something that must be followed by work elsewhere (send an email, store a provider
record in the tenant's database, build a data export, email a reported problem to support), it adds a row to the
`event_outbox` table in the same transaction as the change. The change and the "to do" note are saved together or
not at all. The worker then delivers each row.

What the worker delivers (`publish` in `scripts/run_outbox_worker.py`):

| Event | Delivery |
|---|---|
| `PROVIDER_RECORD_RECEIVED` | Stored in the tenant's data plane (resolved from the registry, never from the event) |
| `TENANT_EXPORT_REQUESTED` | The export is built |
| `RECORD_EMBEDDINGS_REQUESTED` | An import's records are embedded for semantic search, after its signals are found (`retrieval/record_evidence.py`): about 20 s per delivery at a lower CPU priority, the rest handed to a follow-up event. A failure is retried on the schedule below; the scheduled embedding catch-up leaves the organization to this job while one is queued |
| `SUPPORT_PROBLEM_REPORTED` | The problem report is emailed to support |
| Notification events | Email through SMTP (`backend/app/notifications.py`) |
| Anything else | Acknowledged (`MDARIX_OUTBOX_PUBLISHER=noop`, the only supported value; any other value stops the worker at startup) |

Each cycle the worker also runs pending report jobs in every active data plane.

### How an event is claimed and delivered

1. Return abandoned claims to the queue (see *Stale claims*).
2. List up to `MDARIX_OUTBOX_BATCH_SIZE` due events, oldest first, without locking them.
3. For each one, in its own transaction: lock the row with `FOR UPDATE SKIP LOCKED` (a row another worker holds is
   skipped), deliver it, record the outcome, commit. One event, one commit: a worker killed mid-batch never re-sends
   what it already delivered.
4. Write the heartbeat (file and database), then wait `MDARIX_OUTBOX_INTERVAL_SECONDS`.

A stop signal (SIGTERM/SIGINT, e.g. `docker compose stop background`) is honoured between events: the event in hand is
finished, nothing new is started. Two workers can run side by side safely.

### Retry schedule

After a failed attempt the event waits `base x 2^(attempt-1)`, capped at the maximum delay (`outbox/worker.py`).
With the code defaults (12 attempts, 30 s base, 1 hour cap):

| After failure | Next attempt in |
|---|---|
| 1 | 30 s |
| 2 | 1 min |
| 3 | 2 min |
| 4 | 4 min |
| 5 | 8 min |
| 6 | 16 min |
| 7 | 32 min |
| 8, 9, 10, 11 | 1 hour each |
| 12 | Dead-lettered, no further attempts |

From the first attempt to the twelfth is about 5 hours, enough to ride out a mail provider outage. The error kept on
the event (`last_error`) is the error type and message with secret-like values redacted.

### Dead letters

After the last attempt the event is marked dead-lettered and kept. Nothing is retried automatically.

- The worker sends one alert per event: **"Event dead-lettered"** (event name, ID, attempts, error; no payload).
- The scheduler's `operations-alerts` job (every 5 minutes) sends **"Dead-letter queue grew"** when the count is
  higher than at its last run. This also catches events dead-lettered while alerting itself was broken.

Where to act: **Platform Admin > Operations > Queues & jobs > "Gave up after retries"**. Items are grouped by event
kind and organization, with the last error.

- **Retry**: fix the cause first (often SMTP). The items go back in the queue with a fresh set of attempts and are
  sent within seconds.
- **Discard**: for work that is not needed (for example test leftovers). The items are deleted from the queue.

Both ask for a reason (at least 10 characters). One audit record per organization is written before the change
(`OUTBOX_EVENTS_RETRIED` / `OUTBOX_EVENTS_DISCARDED`), naming every item (without payload) and the reason. If someone
else acted on part of the selection first, nothing is changed and the console asks you to reload.

Without the console, an operator can do the same for one event:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production exec api \n  python scripts/replay_outbox.py EVENT_UUID --reason "SMTP credentials fixed"
```

It replays only an event that is dead-lettered, gives it a fresh set of retries, and writes the same
`OUTBOX_EVENTS_RETRIED` audit record as the console (event name and reason, never the payload).

### Stale claims

A claim older than 300 seconds (hard-coded in `recover_stale_claims`) on an event that is neither delivered nor
dead-lettered is released at the start of every cycle: the event is due again at once and `last_error` reads
`STALE_WORKER_CLAIM_RECOVERED`.

### Worker heartbeat

| Signal | Written | Read by | Stale after |
|---|---|---|---|
| File `MDARIX_OUTBOX_HEARTBEAT_FILE` (compose sets `/tmp/mdarix-outbox-heartbeat.json`; no file when unset) | Every cycle | Compose health check | 60 s |
| Row in `worker_heartbeats` (one per worker instance) | Every cycle | Platform Admin > Operations, readiness (`worker` check), `operations-alerts` | 60 s (`backend/app/worker_status.py`) |

The worker is `RUNNING` when at least one instance wrote within 60 s, `STOPPED` when none did, `NOT_REPORTED` when
none ever did. Heartbeats of instances silent for a day are removed. The `operations-alerts` job sends **"Background
worker stopped"** once when the state turns `STOPPED` and **"Background worker recovered"** when it runs again, so
expect the alert up to about 6 minutes after the worker stops.

### Worker settings (names and defaults as the code reads them)

| Variable | Default | Effect |
|---|---|---|
| `MDARIX_OUTBOX_MAX_ATTEMPTS` | 12 | Attempts before dead-lettering (minimum 1) |
| `MDARIX_OUTBOX_BASE_DELAY_SECONDS` | 30 | First retry delay; doubles each time |
| `MDARIX_OUTBOX_MAX_DELAY_SECONDS` | 3600 | Cap on the retry delay |
| `MDARIX_OUTBOX_INTERVAL_SECONDS` | 5 | Pause between cycles |
| `MDARIX_OUTBOX_BATCH_SIZE` | 50 | Events per cycle |
| `MDARIX_REPORT_WORKER_BATCH_SIZE` | 10 | Report jobs per data plane per cycle |
| `MDARIX_OUTBOX_HEARTBEAT_FILE` | unset (no file) | Heartbeat file for the health check |
| `MDARIX_OUTBOX_PUBLISHER` | `noop` | Only `noop` is supported |

## 2. The scheduler

One loop (`backend/app/scheduler.py`). Every 30 seconds it runs each job whose interval has passed since it last
finished, checks for missed jobs and writes its heartbeat file. A cycle that fails (for example the database is
briefly unavailable) is logged and tried again on the next one.

| Job | Every | Purpose |
|---|---|---|
| `tenant-lifecycle` | 15 min | Apply scheduled tenant status changes |
| `subscription-lifecycle` | 1 h | Expiry, grace and renewal reminders |
| `trial-reminders` | 6 h | Email trial owners before and when the trial ends |
| `trial-retention` | 24 h | Delete trial data 30 days after the trial ends (held while its move into the MVP is requested) |
| `embedding-catch-up` | 15 min | Embed evidence that has no embedding yet |
| `operations-alerts` | 5 min | Alert on dead letters, a stopped worker, an outbox falling behind (lag over 15 min) and failing e-mail; ping `MDARIX_SCHEDULER_HEARTBEAT_URL` |
| `support-access-expiry` | 5 min | Close support access whose time ran out (`SUPPORT_ACCESS_EXPIRED` in the organization's audit trail) and queue `SUPPORT_ACCESS_ENDED` to its decision makers. Access itself ends at the second it expires, whether this has run or not |
| `export-expiry` | 1 h | Delete data exports after their download period |
| `connector-sync` | 15 min | Sync connections that have a sync schedule |
| `audit-chain-verification` | 24 h | Verify every organization's tamper-evident audit trail |
| `due-alerts` | 15 min | Raise reminders for items due soon and escalations for overdue ones (owner, backup, the escalation role), and resolve those whose item is done; in-app only, nothing is e-mailed (`DUE_ITEM_ESCALATED` in the audit trail) |
| `signature-settlement` | 10 min | Settle every signature a dedicated plane's signing left PENDING for over 2 minutes (a restart, a lost connection between its two commits): SIGNED with its audit events when the record it signs was saved, otherwise removed with `SIGNATURE_ABANDONED` (nothing was signed). The state machine is documented in `backend/app/signing_commit.py`; a PENDING signature is never shown as valid |
| `readiness-digest` | 6 h | Once per ISO week (from Monday 06:00 UTC): queue each organization's weekly readiness email (`READINESS_DIGEST`) to its quality leads |

Every run is recorded in `scheduler_runs` (status, result, error type, consecutive failures). Jobs run in system
scope and write their own audit events.

**Spare instance is safe.** Each job takes a Postgres advisory lock (`pg_try_advisory_lock`) for its run; a second
scheduler skips a job another one is running. The lock is held on one database session for the whole run, so connect
directly to the database, not through a transaction-mode pooler.

### Scheduler alerts

| Alert | When |
|---|---|
| `Scheduled job failing: <job>` | Exactly at the 3rd consecutive failure (not repeated on the 4th, 5th ...) |
| `Scheduled job recovered: <job>` | First success after 3 or more failures |
| `Scheduled job missed: <job>` | The job has not started or finished within 2 x its interval (another instance holding the lock, or a slow job starving the loop). Once per occurrence |
| `Scheduled job running again: <job>` | The missed job ran within its interval again |
| `Outbox falling behind` / `Outbox caught up` | The longest-waiting event that is due has waited over 15 minutes (the worker stopped, never started, or cannot keep up), and when it no longer has (0.10.88) |
| `E-mail delivery failing` / `E-mail delivery recovered` | E-mails the provider refused wait in the outbox to be retried (`EmailDeliveryError`, or a notification's `NotificationFailed`), and when none does (0.10.88) |
| `Signatures not settled` / `Signatures settled again` | The `signature-settlement` job could not settle a signature, or one has been PENDING for over 30 minutes, and when neither is true (0.10.88) |

Every alert goes to `MDARIX_ALERT_WEBHOOK` and/or `MDARIX_ALERT_EMAIL` (backend/app/alerts.py). Which channel, and
who is on call, is the owner's decision. The local e-mail drill of 0.10.88 showed why one channel should not be the
same SMTP provider as the customers' e-mail: with the provider down, the alert "Trial invitation not delivered" could
not be e-mailed either and reached only the log. A webhook to a phone or chat service is independent of it.

### Health signals (`/health/ready`)

| Check | Degraded when |
|---|---|
| `database` | Not ready (503): the database does not answer as the runtime role, or its schema is not this build's head |
| `worker` | No outbox worker heartbeat within 60 s (`STOPPED`), or none ever (`NOT_REPORTED`) |
| `outbox` | The longest-waiting due event has waited over 15 minutes (`LAGGING`); it reports `waiting`, `retrying`, `email_failing` and `lag_seconds` (0.10.88) |
| `scheduler` | `operations-alerts` has not finished within 15 minutes |
| `email` | SMTP is not configured, or e-mails the provider refused wait to be retried (`DELIVERY_FAILING`, 0.10.88) |
| `data_planes`, `object_storage` | A dedicated plane does not answer or is behind; the object store cannot be written |

Degraded keeps the API in rotation; `/health/status` says one word. The deploy's readiness gate,
`scripts/deploy_gate.py`, asks the same report from inside the new API container (DEPLOYMENT.md).
| `Trial data could not be deleted` | `trial-retention` could not purge an ended trial; nothing was changed for it |
| `Trial data held for a pilot request` | `trial-retention`: a trial kept because its pilot request asks to move its data is 7 days from the date it would otherwise have been deleted, or from the end of its 90-day hold. Once each; close the request (Identity & Access › Onboarding) or convert the trial |
| `Audit trail integrity check failed` | `audit-chain-verification` found a broken chain; follow [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md) |

### Is the scheduler alive?

A scheduler that has stopped cannot alert about itself. Three outside checks cover that:

1. **Heartbeat file**: `MDARIX_SCHEDULER_HEARTBEAT_FILE` (default `/tmp/mdarix-scheduler-heartbeat`) holds the time
   of the last cycle. The compose health check fails when it is older than 120 seconds.
2. **Dead-man's switch**: set `MDARIX_SCHEDULER_HEARTBEAT_URL` to a check at an outside monitor (healthchecks.io,
   Cronitor, ...). `operations-alerts` sends a GET to it every 5 minutes; configure the monitor to alert after about
   15 minutes without a ping. A failed ping is logged and never fails the job.
3. **Readiness**: the `scheduler` check fails when `operations-alerts` has not finished within 15 minutes, which turns
   `/health/status` to `degraded`.

### Commands

```bash
docker compose ps background
docker compose logs --since 1h background
docker compose exec background python scripts/run_scheduler.py --list   # each job, its interval, last status and time
docker compose exec background python scripts/run_scheduler.py --once   # run every due job once; exit 1 if any failed
```

`--once` runs only jobs that are due and skips any job another instance holds; it prints each outcome as JSON. The
job's last error is in `scheduler_runs.last_error` and in the scheduler log (full traceback).
