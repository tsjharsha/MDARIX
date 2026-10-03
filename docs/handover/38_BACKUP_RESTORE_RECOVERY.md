# Backup, restore and recovery

The procedure, schedule and evidence are in [docs/runbooks/BACKUP_AND_RESTORE.md](../runbooks/BACKUP_AND_RESTORE.md):

- **Managed database:** point-in-time recovery for the control database and every dedicated data plane, plus daily
  snapshots.
- **MDARIX backup** (`docker compose --profile backup run --rm backup`, daily from cron): an encrypted (age) logical
  dump of every database and the uploaded files, with a SHA-256 manifest, copied off-site.
- **Keys** (connector, MFA, object storage, RLS system token, age identity) are backed up separately from the data.
- **Restore** with `infrastructure/docker/backup/restore.sh` into an empty database, then
  `scripts/grant_runtime_privileges.py`. A restore drill was recorded on 2026-10-03; repeat it before the first design
  partner signs in and every quarter.

Deleted data (trial retention, organization deletion, erasure) stays in backups until they expire and is never restored
into production; see [DATA_REQUESTS.md](../runbooks/DATA_REQUESTS.md).
