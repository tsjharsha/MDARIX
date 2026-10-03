#!/usr/bin/env bash
# Encrypted logical backup of everything MDARIX keeps: the control database, every dedicated tenant database and
# the uploaded files. Each part is encrypted to MDARIX_BACKUP_AGE_RECIPIENT (an age public key; the private key is
# kept offline, so a compromised server cannot read its own backups), written to /backups/<timestamp>/ with a
# SHA-256 manifest, copied to MDARIX_BACKUP_S3_URI when set, and backups older than MDARIX_BACKUP_KEEP_DAYS are
# removed locally. The managed database's point-in-time recovery is the first line of defence; this is the second,
# independent of the provider.
#
#   docker compose -f docker-compose.prod.yml --profile backup run --rm backup
set -euo pipefail

: "${MDARIX_BACKUP_AGE_RECIPIENT:?set MDARIX_BACKUP_AGE_RECIPIENT (age public key)}"
: "${POSTGRES_HOST:?}" "${POSTGRES_DB:?}" "${MDARIX_DB_OWNER_USER:?}" "${MDARIX_DB_OWNER_PASSWORD:?}"
KEEP_DAYS="${MDARIX_BACKUP_KEEP_DAYS:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="/backups/${STAMP}"
mkdir -p "${TARGET}"
umask 077

sslmode="${POSTGRES_SSLMODE:-require}"
encrypt() { age --encrypt --recipient "${MDARIX_BACKUP_AGE_RECIPIENT}" --output "$1"; }

dump() { # $1 name, $2 libpq connection string
    echo "Backing up $1"
    pg_dump --format=custom --no-owner --no-privileges --dbname="$2" | encrypt "${TARGET}/$1.dump.age"
}

export PGPASSWORD="${MDARIX_DB_OWNER_PASSWORD}"
dump "control" "host=${POSTGRES_HOST} port=${POSTGRES_PORT:-5432} dbname=${POSTGRES_DB} user=${MDARIX_DB_OWNER_USER} sslmode=${sslmode}"
unset PGPASSWORD

# Dedicated tenant databases: MDARIX_DATA_PLANE_<NAME>_DATABASE_URL=postgresql+pg8000://user:pass@host:port/db
while IFS='=' read -r name value; do
    plane="${name#MDARIX_DATA_PLANE_}"
    plane="${plane%_DATABASE_URL}"
    url="${value/postgresql+pg8000:/postgresql:}"
    dump "plane-${plane,,}" "${url}?sslmode=${sslmode}"
done < <(env | grep -E '^MDARIX_DATA_PLANE_[A-Z0-9_]+_DATABASE_URL=' || true)

if [ -d /objects ] && [ -n "$(ls -A /objects 2>/dev/null)" ]; then
    echo "Backing up uploaded files"
    tar -C /objects -cf - . | encrypt "${TARGET}/objects.tar.age"
fi

(cd "${TARGET}" && sha256sum ./* > MANIFEST.sha256)
echo "Backup written to ${TARGET}"

if [ -n "${MDARIX_BACKUP_S3_URI:-}" ]; then
    aws s3 cp --recursive --only-show-errors "${TARGET}" "${MDARIX_BACKUP_S3_URI%/}/${STAMP}/"
    echo "Copied off-site to ${MDARIX_BACKUP_S3_URI%/}/${STAMP}/"
fi

find /backups -mindepth 1 -maxdepth 1 -type d -mtime "+${KEEP_DAYS}" -exec rm -rf {} +
echo "Done"
