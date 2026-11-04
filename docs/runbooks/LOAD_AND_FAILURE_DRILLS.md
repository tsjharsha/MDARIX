# Load measurements and failure drills (DEV-13)

What 0.10.88 measured and drilled **locally**, against the targets the owner approved on 3 Nov 2026, and how to repeat
it. Nothing here touched production. These are command results on one developer machine, not a production
benchmark and not a certification.

## The targets

Uptime 99.5% a month. Page loads: LCP at most 2.5 s, INP at most 200 ms (95th percentile). Server reads at most
500 ms, writes (save, sign, approve) at most 1 s. A 5,000-row import in at most 60 s, a PDF in at most 10 s. Server
errors below 0.1%. RPO at most 24 h (15 min before paid pilots), RTO at most 4 h. Backups 30 daily + 12 monthly,
off-server in another region, encrypted. Restore drill quarterly, rollback drill once, failure drills (worker,
scheduler, e-mail) twice a year. Uptime checked every minute, an alert within 5 minutes by e-mail and phone.

## Hardware and topology of the measurement

- Windows 11 laptop, 8 logical CPUs, shared during the run with two other builds and their test suites: the timings
  are noisy and higher than on an idle machine. PostgreSQL 16 (pgvector) in Docker on the same machine.
- The measurement (`tests/test_trial_load_measure.py`) runs the API in-process (FastAPI's TestClient: one Python
  process, no network, no Caddy). Production runs two uvicorn workers behind Caddy on a 2-CPU VM with a managed
  database; its numbers will differ, and no production measurement was taken (owner decision 4 in the 0.10.88
  report).
- The browser journeys (`frontend/e2e/trial-journeys.spec.ts`) ran against one uvicorn process
  (`scripts/journey_api.py`) and the Vite dev server: development builds, so page-load numbers from them are not
  LCP evidence.

Repeat:

```powershell
$env:POSTGRES_DB = "<a disposable test database>"; $env:MDARIX_TRIAL_LOAD_MEASURE = "1"
$env:MDARIX_TRIAL_LOAD_REPORT = "load.json"          # written as it goes
.\.venv\Scripts\python.exe -m pytest tests/test_trial_load_measure.py -s
```

## Results

See the 0.10.88 delivery report for the full JSON. Before and after the 0.10.88 fixes, same machine, same synthetic
5,000-row export (five products, forty lots, five countries):

| What | Before 0.10.88 | After | Target |
|---|---|---|---|
| Getting started's story, 5,000 imported complaints (GET /trial/one-story) | 60-86 s a read | about 25 s (p50) | 500 ms |
| Picking the trial's most urgent complaint (profiled) | 173 s, 5.7 million name normalizations | 59 s | - |
| Possible duplicates (GET /intake/duplicates) | about 12 s a read | 3.8 s | 500 ms |
| The complaint page's "who may sign": each person's permissions read | 7 times | once (at most twice) | - |
| Team list at the cap of 50 people (GET /trial/team) | 3-7 s, 301 queries | unchanged (reported) | 500 ms |
| 5,000-row import: check / import with its after-answer work | 12 s / 157 s | see the report | 60 s |

The remaining cost of the story and of every read that shows a complaint's work is the whole organization's due
items (the reportability watch and the triage list, the latter read twice), computed on each such read however few
complaints it asks about. It needs a restructure (DEV-12), not a local fix.

## Failure drills (local, 4 Nov 2026)

Run with `scripts/journey_api.py`'s e-mail capture so no message left the machine, the real outbox worker loop
(`scripts/run_outbox_worker.py` main) and the scheduler's job functions.

| Drill | What happened | Result |
|---|---|---|
| Worker never started | `/health/ready`: worker `NOT_REPORTED`, outbox `LAGGING` (oldest due event 7,890 s). No "worker stopped" alert (a worker that never reported is not "stopped"); the new "Outbox falling behind" alert was sent | Seen within one operations-alerts run (5 min) |
| Worker running again | 7 waiting events published within the first cycles; lag 1 s; "Outbox caught up" alert | Recovered |
| Worker stopped after running | "Background worker stopped", then "Background worker recovered" when it ran | Alerted both ways |
| E-mail provider down at sign-up | The trial was approved, its invitation refused, recorded as FAILED, a retry queued in the outbox, and "Trial invitation not delivered" raised; that alert's own e-mail failed too (same provider) and reached only the log | Actionable (Platform Admin shows it; Resend), but the alert channel must not be the same provider |
| E-mail provider back | The outbox retried the invitation and it was delivered | Recovered with no person acting |
| Scheduler silent | `operations-alerts` last run moved 20 minutes back: readiness `scheduler` failing; fresh again: ok | As designed |
| Database unreachable (wrong port) | `scripts/deploy_gate.py`: `not_ready`, `DEPLOY_GATE=FAIL database` | The gate refuses the release |
| Object store unwritable | `object_storage` failing, `DEPLOY_GATE=FAIL object_storage` with `--require object_storage` | Degraded, named |
| Upgrade script rollback branch | `rollback()` of upgrade-0186.sh with Docker, Git and the network stubbed: environment file restored, previous tag checked out and started, `ROLLBACK=1` with the reason; the "previous release does not answer" and "no previous release recorded" outcomes reported as written | Logic verified; a drill on real containers needs a non-production server (DEPLOYMENT.md, section 4) |

Not drilled locally: the database going away while requests are in flight (the shared database serves other
builds), a restore (the quarterly drill passed on 3 Nov 2026: BACKUP_AND_RESTORE.md), and the off-site copy (it
needs production settings, which this build may not read).

## Owner actions and decisions

- **Alert destination and on-call person:** set `MDARIX_ALERT_WEBHOOK` to a channel independent of the SMTP provider
  (a phone or chat service) and `MDARIX_ALERT_EMAIL`, and name who acknowledges within 1 hour.
- **Backup retention (30 daily + 12 monthly):** `MDARIX_BACKUP_KEEP_DAYS` stays 14 by default in this release; the
  change is prepared for the owner's decision (backup.sh keeps 30 days and the newest backup of each of the last 12
  months; the off-site bucket needs the same lifecycle rule).
- **The off-site copy:** verify on the server that the newest backup is in `MDARIX_BACKUP_S3_URI`, in another
  region, encrypted, and can be restored from there.
- **The deploy gate:** add `scripts/deploy_gate.py` to the next upgrade script, after `/health/live`.
