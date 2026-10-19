# Data retention schedule

How long MDARIX keeps each kind of data, what deletes it, and where that is enforced. This is the one statement of
the policy: the legal documents (`legal/README.md` gives the lawyer the facts), the data-request runbook
(`docs/runbooks/DATA_REQUESTS.md`) and the backup runbook (`docs/runbooks/BACKUP_AND_RESTORE.md`) all point here.
Engineering keeps it current; a change to a period below is a change to code or infrastructure first.

"Organization purge" means Platform Admin > tenant > Data > Delete all data (`backend/app/tenant_purge.py`): every
table holding the organization's rows, its audit trail and every stored file are deleted, after an export has been
handed back or a waiver recorded, and never while a legal hold is set.

## Customer data (MDARIX is the processor)

| Data | Kept | Deleted by | Enforced in |
|---|---|---|---|
| Quality records (products, complaints, investigations, evidence, CAPAs, risks, reports) and uploaded files | For the subscription term | Organization purge at the end of the contract or on the customer's instruction | `tenant_purge.py` |
| Audit trail and electronic signatures | For the life of the account, and at least until each event's `retention_until`: **7 years** after the event, set by the database when the application leaves it empty (migration md23). Never changed or deleted while the account exists | The organization purge deletes the whole trail after it was handed back in the export (the export includes every event and the chain's verified head); the customer, as manufacturer, keeps it for its own regulatory period | DB trigger `audit_events_retention`; immutability trigger; `scripts/archive_expired_audit_events.py` archives expired events but never deletes them |
| Free-trial workspaces | Trial period (30 days), then **30 days** after the trial ends | Scheduler job `trial-retention` (organization purge) | `backend/app/trial/retention.py` |
| Full data exports | **7 days** after they are prepared | Scheduler job `export-expiry` | `tenant_export.py` (`EXPORT_DAYS`) |
| AI requests and responses held by an AI provider | As set out per provider in `docs/compliance/AI_PROVIDER_REGISTER.md` (contracted providers only; no training on customer content) | The provider, under its agreement | `MDARIX_GENAI_CONTRACTED_PROVIDERS` allowlist; AI is off for new organizations |

## People (accounts and personal data)

| Data | Kept | Deleted by | Enforced in |
|---|---|---|---|
| Account (name, email, role, authenticator secret) | While the account is in use | Personal-data erasure on request (pseudonymized: name, email and credentials replaced) or the organization purge | `erase_person` in `tenant_purge.py` |
| Free-trial requests that did not lead to a trial: declined, or approved with an invitation that expired unused (name, email, job title, phone, free-text goal) | **90 days** after the decline, or after the last invitation expired unused (`REQUEST_RETENTION_DAYS`). Requests still waiting for review are not erased automatically (open item) | Scheduler job `trial-retention` (`erase_trial_request`: pseudonymized like a purge; the organization's name and its answers about the organization stay; the never-activated account is erased with `erase_person`; logged in `erasure_log` as TRIAL_REQUEST_ERASED) | `backend/app/trial/retention.py`, `tenant_purge.py` |
| Sessions, sign-in history, invitations, password-reset requests | While the account exists (no time-based deletion yet) | Erasure of the person or the organization purge | as above |
| Pseudonymized account and trial-request rows | For the life of the platform, as the record of the contract and of consent; they identify nobody | Not deleted | `tenant_purge.py` (`KEEP_TABLES`) |
| Published trial feedback | While the person's consent stands | Unpublishing (withdrawal of consent), then erasure or purge | Platform Admin > Trial feedback |
| Erasure log (`erasure_log`) | For the life of the platform: needed to repeat erasures after a restore. Holds ids, counts and the stated reason only | Not deleted | `tenant_purge.py`; `scripts/reapply_erasures.py` |
| Personal values inside audit rows | Audit payloads name people by account id. Rows written before this rule, and free-text reasons typed by administrators, may still contain a name or address; they stay for the audit period above, because audit rows cannot be changed | Organization purge | — |

## Operational data

| Data | Kept | Deleted by |
|---|---|---|
| Support problem reports | No automatic deletion yet | Organization purge (they belong to the organization) |
| Website demo requests (the form is parked; requests made before it was) | No automatic deletion yet (open item) | Deleted with the trial when booked from inside one |
| Browser error reports | No automatic deletion yet; reports sent before sign-in carry no organization and are not removed by a purge | Not yet defined (open item) |
| Application logs | As set by the host's log rotation (infrastructure) | Log rotation |

## Backups

| Layer | Kept |
|---|---|
| Daily snapshot of the server's disk (database and uploaded files; validation phase, stored in Mumbai) | **14 days** (snapshot schedule `mdarix-daily`, docs/runbooks/GCP_DEPLOYMENT.md) |
| MDARIX encrypted backup (all databases and uploaded files) | **14 days** on the server (`MDARIX_BACKUP_KEEP_DAYS`) and **up to 90 days** off-site (bucket lifecycle rule) |
| Uploaded files on a versioned bucket | Deleted files keep a noncurrent version until the bucket's noncurrent-version expiry rule removes it (set it to 30 days) |

Erased or purged data therefore **remains in backups for up to 90 days** after the erasure. Backups are encrypted,
never read for any other purpose, and a backup is never restored into production without re-applying the erasures:
every erasure and purge is written to `erasure_log`, and after a restore `scripts/reapply_erasures.py` (first
importing the log rows newer than the backup) repeats each one whose subject has personal data again
(`docs/runbooks/BACKUP_AND_RESTORE.md`).

## Legal hold

A legal hold on an organization (Platform Admin, recorded with its reason, `LEGAL_HOLD_SET` in the audit trail)
suspends every deletion above for that organization: purge, erasure, trial retention, completion of an unfinished
purge and re-application after a restore. The periods resume when the hold is cleared (`LEGAL_HOLD_CLEARED`).
