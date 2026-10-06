#!/usr/bin/env bash
# Restore one MDARIX backup part: a database dump into a database (normally a fresh, empty one, for a restore drill
# or a recovery), or the uploaded-files archive into a folder.
#
#   mdarix-restore <backup dir> <part> <target>
#   e.g. mdarix-restore /backups/20261003T020000Z control "host=db port=5432 dbname=mdarix_restore user=owner sslmode=verify-full"
#        mdarix-restore /backups/20261003T020000Z plane-acme "postgresql://owner@db:5432/mdarix_acme_restore?sslmode=verify-full"
#        mdarix-restore /backups/20261003T020000Z objects /restore/objects
#
# The age private key is read from MDARIX_BACKUP_AGE_KEY_FILE (mounted only for the restore, never kept on the
# server). The manifest is checked before anything is restored. The target database must exist and already have the
# vector and pgcrypto extensions (created by the database's admin: a non-superuser owner cannot create them).
set -euo pipefail

dir="${1:?backup directory}"
part="${2:?part name: control, plane-<key> or objects}"
target="${3:?target connection string, or a folder for objects}"
: "${MDARIX_BACKUP_AGE_KEY_FILE:?mount the age private key and set MDARIX_BACKUP_AGE_KEY_FILE}"

(cd "${dir}" && sha256sum --check --quiet MANIFEST.sha256)
echo "Manifest verified"

if [ "${part}" = "objects" ]; then
    mkdir -p "${target}"
    if [ -n "$(ls -A "${target}" 2>/dev/null)" ]; then
        echo "${target} is not empty; restore the files into an empty folder (then swap it in)." >&2
        exit 1
    fi
    age --decrypt --identity "${MDARIX_BACKUP_AGE_KEY_FILE}" "${dir}/objects.tar.age" | tar -x -C "${target}"
    echo "Restored $(find "${target}" -type f | wc -l) uploaded files into ${target}"
    echo "Next: copy them into the objects volume (or bucket) the API reads, then the checks in BACKUP_AND_RESTORE.md"
    exit 0
fi

# Decrypted into a private temporary file (removed on exit) so pg_restore can select entries: the extension comments
# are skipped, because only an extension's owner may set them and the restoring account usually is not.
umask 077
work="$(mktemp -d "${TMPDIR:-/tmp}/mdarix-restore.XXXXXX")"
trap 'rm -rf "${work}"' EXIT
age --decrypt --identity "${MDARIX_BACKUP_AGE_KEY_FILE}" --output "${work}/${part}.dump" "${dir}/${part}.dump.age"
pg_restore --list "${work}/${part}.dump" | grep -v ' COMMENT - EXTENSION ' > "${work}/entries.list"
pg_restore --no-owner --no-privileges --exit-on-error --use-list="${work}/entries.list" --dbname="${target}" \
    "${work}/${part}.dump"
echo "Restored ${part} into the target database"
echo "Next: run the migrate job against it (it re-grants the application roles their privileges, which backups do"
echo "not carry, and stores the system-scope token), then the restore checks in docs/runbooks/BACKUP_AND_RESTORE.md"
