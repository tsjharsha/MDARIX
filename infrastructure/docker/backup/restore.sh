#!/usr/bin/env bash
# Restore one MDARIX backup part into a database (normally a fresh, empty one for a restore drill or a recovery).
#
#   mdarix-restore <backup dir> <part> <target libpq connection string>
#   e.g. mdarix-restore /backups/20261003T020000Z control "host=db port=5432 dbname=mdarix_restore user=owner"
#
# The age private key is read from MDARIX_BACKUP_AGE_KEY_FILE (mounted only for the drill, never kept on the server).
# The manifest is checked before anything is restored.
set -euo pipefail

dir="${1:?backup directory}"
part="${2:?part name, e.g. control or plane-acme}"
target="${3:?target connection string}"
: "${MDARIX_BACKUP_AGE_KEY_FILE:?mount the age private key and set MDARIX_BACKUP_AGE_KEY_FILE}"

(cd "${dir}" && sha256sum --check --quiet MANIFEST.sha256)
echo "Manifest verified"

age --decrypt --identity "${MDARIX_BACKUP_AGE_KEY_FILE}" "${dir}/${part}.dump.age" \
    | pg_restore --no-owner --no-privileges --exit-on-error --dbname="${target}"
echo "Restored ${part} into the target database"
echo "Next: run the migrate job against it (grants the application roles their privileges, which backups do not"
echo "carry), then the restore checks in docs/runbooks/BACKUP_AND_RESTORE.md"
