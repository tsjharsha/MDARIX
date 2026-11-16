# Load measurements and failure drills (DEV-13)

What 0.10.88 measured and drilled **locally**, against the targets the owner approved on 3 Nov 2026, and how to repeat
it. Nothing here touched production. These are command results on one developer machine, not a production
benchmark and not a certification.

## The targets

Uptime 99.5% a month. Page loads: LCP at most 2.5 s, INP at most 200 ms (95th percentile). Server reads at most
500 ms, writes (save, sign, approve) at most 1 s. A 5,000-row import in at most 60 s, a PDF in at most 10 s. Server
errors below 0.1%. RPO at most 24 h today (no point-in-time recovery), target 15 min with point-in-time recovery on pilot hosting (B6b-D8), RTO at most 4 h. Backups 30 daily + 12 monthly,
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

The final measurement, 5 Nov 2026, 01:13-01:20 IST, on 0.10.88's final code (commit dc4e8959), with no other test
suite running on the machine (CPU about 15-25 % before it started); `tests/test_trial_load_measure.py`, 1 passed in
6 min 35 s. The earlier figures were taken on 4 Nov while two other builds' suites ran, so part of the difference is
the machine, not the code. Same synthetic 5,000-row export (five products, forty lots, five countries).

| What | 4 Nov, before 0.10.88's fixes (shared machine) | 5 Nov, final (quiet machine) | Target | Meets |
|---|---|---|---|---|
| Getting started's story, 5,000 imported complaints (GET /trial/one-story) | 60-86 s a read | p50 5.6 s, p95 5.8 s, 143 queries | 500 ms | No |
| The short stories (GET /trial/story) | 7.3 s p50 (after the first fixes) | p50 2.0 s, p95 2.1 s | 500 ms | No |
| Trial status (GET /trial/status) | 0.30 s p50 | p50 100 ms, p95 115 ms | 500 ms | Yes |
| A complaint's page, SAMPLE-RV-11 (GET /oversight/events/{ref}) | - | p50 4.6 s, p95 5.1 s, 141 queries | 500 ms | No |
| Triage list (GET /triage) | - | p50 1.3 s, p95 1.5 s | 500 ms | No |
| Possible duplicates (GET /intake/duplicates) | about 12 s a read | p50 395 ms, p95 490 ms | 500 ms | Yes |
| Intake list (GET /intake) | - | p50 466 ms, p95 567 ms | 500 ms | No (p95) |
| Dispositions (GET /complaints/dispositions) | - | p50 956 ms, p95 985 ms, 235 queries | 500 ms | No |
| Readiness (GET /readiness) | - | p50 1.9 s, p95 2.1 s | 500 ms | No |
| Oversight alerts (GET /oversight/alerts) | - | p50 164 ms, p95 26.6 s (one cold read) | 500 ms | No (p95) |
| Communications, plain and with the provider down (502) | - | p50 102 ms / 153 ms | 500 ms | Yes |
| Team list at the cap of 50 people (GET /trial/team) | 3-7 s, 301 queries | p50 1.05 s, p95 1.11 s, 311 queries | 500 ms | No |
| Inviting a colleague (team of 50) | - | p50 211 ms, p95 229 ms | 1 s | Yes |
| A decision tree's answers saved (PUT market-assessments) | - | p50 227 ms, p95 286 ms | 1 s | Yes |
| 5,000-row import: check / import / after the answer | 12 s / 157 s | 2.8 s / 33.4 s / 0.5 s; peak Python memory 74.5 MB | 60 s | Yes |
| Four trials at once, eight threads, 72 reads | - | wall 54 s; p50 3.0 s, p95 13.2 s; no failures | 500 ms | No |
| Picking the trial's most urgent complaint (profiled) | 173 s, 5.7 million name normalizations | 59 s (4 Nov profile) | - | - |

No read answered with a server error. Production runs two uvicorn workers on a 2-CPU VM with a managed database: these
in-process numbers are not production numbers.

The remaining cost of the story and of every read that shows a complaint's work is the whole organization's due
items (the reportability watch and the triage list, the latter read twice), computed on each such read however few
complaints it asks about. It needs a restructure (DEV-12), not a local fix.

## B2 (0.10.93): the Cases list at 5,000 Cases (10 Nov 2026)

A5 and B2-15: `GET /api/v1/intake/cases`, the paged Cases list that replaced the old newest-500 contacts list on the
screens. Measured on 10 Nov 2026 at about 12:05-12:12 IST on the B2 branch (`feat/b2-cases-0.10.93`, after commit 6b8a0c26),
same laptop and topology as above, with the W1 build idle. `tests/test_case_load_measure.py` writes 5,000 Cases
straight into a new trial beside its sample (every live and finished state, a Case check version each, signed where
the state needs it, owners on half, "Not sure" lots on one in ten), then asks each read 10 times. Budget: p95 under
1 s a read; approved read target: 500 ms.

| Read (25 a page unless said) | p50 | p95 | Queries | Within 1 s | Within 500 ms |
|---|---|---|---|---|---|
| All | 201 ms | 374 ms | 26 | Yes | Yes |
| To check | 192 ms | 345 ms | 26 | Yes | Yes |
| Waiting for the reporter | 216 ms | 392 ms | 23 | Yes | Yes |
| Waiting for internal team | 194 ms | 249 ms | 24 | Yes | Yes |
| QA review | 220 ms | 496 ms | 23 | Yes | Yes |
| Became complaints (30 days) | 154 ms | 192 ms | 21 | Yes | Yes |
| Closed | 168 ms | 258 ms | 24 | Yes | Yes |
| Withdrawn | 206 ms | 225 ms | 24 | Yes | Yes |
| My cases | 250 ms | 321 ms | 24 | Yes | Yes |
| Unassigned | 170 ms | 265 ms | 25 | Yes | Yes |
| Needs more information | 155 ms | 189 ms | 23 | Yes | Yes |
| Critical or high | 194 ms | 216 ms | 25 | Yes | Yes |
| Overdue | 166 ms | 201 ms | 24 | Yes | Yes |
| Service only | 175 ms | 253 ms | 24 | Yes | Yes |
| Potential complaints | 224 ms | 553 ms | 25 | Yes | No (p95) |
| All, 100 a page | 327 ms | 388 ms | 26 | Yes | Yes |
| All, page 150 | 237 ms | 284 ms | 24 | Yes | Yes |
| Search by serial (SN-LOAD-04242) | 276 ms | 380 ms | 23 | Yes | Yes |
| Search by reference (CASE-LOAD-00042) | 214 ms | 273 ms | 23 | Yes | Yes |
| Search by typed product (LoadPump 3) | 234 ms | 418 ms | 24 | Yes | Yes |
| To check, search by lot (LOT-LOAD-7) | 162 ms | 218 ms | 21 | Yes | Yes |
| For comparison: the old contacts list, bounded (GET /intake, 2,000 Cases each read in full; 3 repeats) | 48.8 s | 49.7 s | 14,025 | No | No |

The test passed (1 passed in 4 min 9 s; 5,005 Cases in the trial, the sample's included). The old list is kept only for API clients and older tests (no screen reads it since step 5.3): bounded at 2,000 Cases it still reads each one in full (about seven queries a Case), so it should be retired once its last test callers move, not used for a screen.

Every read is within the 1 s budget; all but one p95 (Potential complaints, 553 ms, a single slow repeat against a
p50 of 224 ms) are within the 500 ms target. The query count does not grow with the page size (26 at 25 and at 100
rows): one batched read each for products, lots, complaints, checks, tasks, triage records and people, never one per
row. No read answered with a server error. Repeat:

```powershell
$env:POSTGRES_DB = "<a disposable test database>"; $env:MDARIX_TRIAL_LOAD_MEASURE = "1"
.\.venv\Scripts\python.exe -m pytest tests/test_case_load_measure.py -s
```

## Product 360 and Supplier 360 (0.10.94, W1), 10 Nov 2026

`tests/test_product_supplier_load_measure.py` (opt-in, same way to repeat with that file): a new trial with its sample,
the same synthetic 5,000-row export imported, then one part supplied by the sample's Precision Sensors linked to every
imported version, so that supplier's page covers 5,044 complaints. Ten reads each, in-process, on the W1 branch
(after commit 7a), no other test suite running at the start; 1 passed in 85 s. The budget of the W1 spec (6.5) is p95
under 1 s a read; the approved read target is 500 ms.

| Read | p50 | p95 | Queries | Under 1 s | Under 500 ms |
|---|---|---|---|---|---|
| Product list with counts (GET /products?counts=1) | 178 ms | 687 ms | 15 | Yes | No (p95) |
| Product 360, light, newest version | 130 ms | 202 ms | 24 | Yes | Yes |
| Product 360, light, Rev B | 171 ms | 230 ms | 24 | Yes | Yes |
| Six tiles and the monthly series, Rev B (GET /products/{id}/links) | 349 ms | 428 ms | 26 | Yes | Yes |
| Six tiles, every version | 172 ms | 602 ms | 23 | Yes | No (p95) |
| One list, complaints, 20 | 108 ms | 202 ms | 15 | Yes | Yes |
| One list, investigations, 20 | 85 ms | 122 ms | 17 | Yes | Yes |
| Supplier list | 136 ms | 190 ms | 15 | Yes | Yes |
| Supplier page, 5,044 complaints (Precision Sensors) | 272 ms | 342 ms | 25 | Yes | Yes |
| Supplier complaints, 20 | 213 ms | 275 ms | 15 | Yes | Yes |
| Supplier lots | 161 ms | 250 ms | 20 | Yes | Yes |
| Supplier page, one version (NovaSense) | 249 ms | 276 ms | 26 | Yes | Yes |

Every read is under the 1 s budget, so the fallback index migration (OD-7, `tr20p360indexes`) is not needed. Two reads
miss 500 ms at p95 only, their p50 being under 200 ms (a slower single read among ten). Query counts include the
request's own session and access statements, not only the reads of the spec's tables.

## B6a (0.11.03): the complaint page and the story at 5,000 complaints, 11 Nov 2026

`MDARIX_TRIAL_LOAD_MEASURE=1 MDARIX_TRIAL_LOAD_PAGES=1 [MDARIX_TRIAL_LOAD_PROFILE=<folder>] pytest
tests/test_trial_load_measure.py -s`: a new trial, its sample, the same synthetic 5,000-row export imported, then ten
calls each of the complaint page (`GET /oversight/events/SAMPLE-RV-11`), the story (`GET /trial/one-story`) and the
triage list (`GET /triage`), in-process, on the B6a branch, no other test suite running. With a profile folder it also
writes each page's profile and its SQL statements grouped by text (`queries-<page>.txt`). Local, in-process, not
production.

| Read, 5,000 imported complaints | Before B6a (73a668bd) | B6a run 2 (d6536102) | B6a run 3 | Target p95 | Met |
|---|---|---|---|---|---|
| Complaint page | p50 13.3 s, p95 15.1 s, 218 queries | 550 / 659 ms, 140 | **351 / 411 ms, 106** | 500 ms | Yes |
| Story | 45.1 s / 48.2 s, 232 queries | 1,033 / 1,109 ms, 208 | **587 / 634 ms, 129** | 500 ms | No |
| Triage list | - | - | 4.6 s / 4.9 s, 34 | 500 ms | No (reads all 5,000 now) |
| Complaint page, sample only | 790 / 990 ms, 189 | 603 / 842 ms, 148 | 383 / 809 ms, 106 | 500 ms | No (p95; one slow call of ten) |

What changed in run 3: the settings, open tasks and record links are read once per request
(`backend/app/db/request_memo.py`, dropped at the session's next flush, commit or rollback); one triage read serves the
open, done and whole lists and every narrower read of the same request; the complaint page reads its facts once. The
query count is flat with the organization's size: `tests/test_b6a_query_budget.py` (100 and 1,000 complaints: the same
count; budget 115 for the complaint page and 140 for the story).

Read cuts (owner decision, 11 Nov: no deadline may be hidden by a read cut): the triage list and the dated tasks now
read every open item. That makes the whole triage list slower at 5,000 imported complaints (it read only the newest
2,000 before, so the older ones were on no list); one page shows 100 events with "N more". The reportability watch
keeps its 20,000 cut; a complaint's own page reads its own clock without it, and Oversight and the deadline list say
"incomplete" when it is reached.

Open: the story (p95 634 ms) and the triage list (4.9 s) are above 500 ms. The story's remaining time is the clocks of
the 52 imported complaints with a serious injury (triage, watch and due items for them); the triage list's is the
provisional deadlines of every flagged imported complaint. Both are B9 work (spec 4.2: a precomputed watch needs an
owner decision). LCP on the production bundle (B4) is not measured yet (Playwright not run in this build).

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
- **Backup retention (30 daily + 12 monthly):** accepted by the owner on 5 Nov 2026 and applied in 0.10.88
  (`retention.sh`; BACKUP_AND_RESTORE.md). The off-site bucket needs the same lifecycle rule (an owner action).
- **The off-site copy:** verify on the server that the newest backup is in `MDARIX_BACKUP_S3_URI`, in another
  region, encrypted, and can be restored from there.
- **The deploy gate:** add `scripts/deploy_gate.py` to the next upgrade script, after `/health/live`.
