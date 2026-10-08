#!/usr/bin/env bash
# Encrypted logical backup of everything MDARIX keeps: the control database, every dedicated tenant database and
# the uploaded files on the local "objects" volume. Each part is encrypted to MDARIX_BACKUP_AGE_RECIPIENT (an age
# public key; the private key is kept offline, so a compromised server cannot read its own backups), written to
# /backups/<timestamp>/ with a SHA-256 manifest, copied to MDARIX_BACKUP_S3_URI when set, and backups older than
# MDARIX_BACKUP_KEEP_DAYS are removed locally. The managed database's point-in-time recovery is the first line of
# defence; this is the second, independent of the provider.
#
#   docker compose -f docker-compose.prod.yml --env-file .env.production --profile backup run --rm backup
#
# Row-level security is forced on every tenant table, for the owner too, so a plain owner login cannot dump them.
# The dump therefore logs in either as a role with BYPASSRLS (MDARIX_BACKUP_DB_USER, created by
# scripts/configure_backup_role.py; plain pg_dump) or, where the provider does not allow BYPASSRLS, as a role that
# opens the application's system scope with MDARIX_RLS_SYSTEM_TOKEN, under which every policy shows every row
# (pg_dump --enable-row-security). The script checks which applies before dumping and refuses to write a dump that
# could silently miss rows.
#
# A failure posts to MDARIX_ALERT_WEBHOOK; a success pings MDARIX_BACKUP_HEARTBEAT_URL (both optional), so a backup
# that fails and a backup that never runs are both noticed.
set -euo pipefail

STAGE="starting"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

json_escape() { sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | tr '\n' ' '; }

alert() { # $1 message; best effort, never fails the script
    local webhook="${MDARIX_ALERT_WEBHOOK:-}"
    [ -n "${webhook}" ] || return 0
    local text
    text="$(printf '[MDARIX %s] Backup failed\n%s' "${MDARIX_ENV:-production}" "$1" | json_escape)"
    curl --silent --show-error --max-time 10 --retry 2 -H 'Content-Type: application/json' \
        -d "{\"text\": \"${text}\"}" "${webhook}" > /dev/null || echo "Alert webhook could not be reached" >&2
}

on_exit() {
    local status=$?
    if [ "${status}" -ne 0 ]; then
        echo "Backup ${STAMP} FAILED while ${STAGE} (exit ${status})" >&2
        # An incomplete folder must not pass for the newest backup (scripts/check_backup_age.sh, a restore).
        [ -n "${TARGET:-}" ] && rm -rf "${TARGET}"
        alert "Backup ${STAMP} failed while ${STAGE} (exit ${status}). Read the backup log on the server."
    fi
}
trap on_exit EXIT

STAGE="checking the configuration"
: "${MDARIX_BACKUP_AGE_RECIPIENT:?set MDARIX_BACKUP_AGE_RECIPIENT (age public key) in .env.production}"
: "${POSTGRES_HOST:?}" "${POSTGRES_DB:?}"
# The backup login (.env.migrate), else the schema owner (MDARIX_DB_OWNER_USER in .env.production, its password in
# .env.migrate).
if [ -n "${MDARIX_BACKUP_DB_PASSWORD:-}" ]; then
    DB_USER="${MDARIX_BACKUP_DB_USER:-mdarix_backup}"
    DB_PASSWORD="${MDARIX_BACKUP_DB_PASSWORD}"
else
    DB_USER="${MDARIX_DB_OWNER_USER:-}"
    DB_PASSWORD="${MDARIX_DB_OWNER_PASSWORD:-}"
fi
: "${DB_USER:?set MDARIX_BACKUP_DB_USER and MDARIX_BACKUP_DB_PASSWORD in .env.migrate, or the owner credentials}"
: "${DB_PASSWORD:?set MDARIX_BACKUP_DB_PASSWORD (or MDARIX_DB_OWNER_PASSWORD) in .env.migrate}"
KEEP_DAYS="${MDARIX_BACKUP_KEEP_DAYS:-14}"

if [ ! -d /backups ] || [ ! -w /backups ]; then
    echo "/backups is not writable by uid $(id -u). On the host: sudo install -d -o 70 -g 70 -m 700 ${MDARIX_BACKUP_DIR:-/var/backups/mdarix}" >&2
    exit 1
fi
TARGET="/backups/${STAMP}"
umask 077
mkdir -p "${TARGET}"

# libpq TLS settings: the same mode as the application, with its CA bundle; without one, verify against the system's
# public CAs (sslrootcert=system, libpq 16+) rather than libpq's default ~/.postgresql/root.crt.
SSLMODE="${POSTGRES_SSLMODE:-require}"
SSLROOTCERT="${POSTGRES_SSLROOTCERT:-}"
if [ -z "${SSLROOTCERT}" ] && [[ "${SSLMODE}" == verify-* ]]; then
    SSLROOTCERT="system"
fi
tls_params() { # libpq keyword=value pairs
    printf 'sslmode=%s' "${SSLMODE}"
    [ -n "${SSLROOTCERT}" ] && printf ' sslrootcert=%s' "${SSLROOTCERT}"
    return 0
}
with_tls_query() { # $1 URI -> URI with sslmode/sslrootcert merged into its query string (existing values win)
    local uri="$1" extra=""
    [[ "${uri}" == *sslmode=* ]] || extra="sslmode=${SSLMODE}"
    if [ -n "${SSLROOTCERT}" ] && [[ "${uri}" != *sslrootcert=* ]]; then
        extra="${extra:+${extra}&}sslrootcert=${SSLROOTCERT}"
    fi
    if [ -z "${extra}" ]; then
        printf '%s' "${uri}"
    elif [[ "${uri}" == *\?* ]]; then
        printf '%s&%s' "${uri}" "${extra}"
    else
        printf '%s?%s' "${uri}" "${extra}"
    fi
}

encrypt() { age --encrypt --recipient "${MDARIX_BACKUP_AGE_RECIPIENT}" --output "$1"; }

dump() { # $1 part name, $2 libpq connection string (keyword=value or URI)
    local name="$1" conninfo="$2" unrestricted scope
    STAGE="checking access to ${name}"
    unrestricted="$(psql --no-psqlrc --tuples-only --no-align --dbname="${conninfo}" \
        -c "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")"
    if [ "${unrestricted}" = "t" ]; then
        echo "Backing up ${name} (login bypasses row-level security)"
        STAGE="dumping ${name}"
        pg_dump --format=custom --no-owner --no-privileges --dbname="${conninfo}" | encrypt "${TARGET}/${name}.dump.age"
        return
    fi
    # No BYPASSRLS: every policy also admits the system scope, which the token opens for this session only.
    : "${MDARIX_RLS_SYSTEM_TOKEN:?the backup login has no BYPASSRLS and MDARIX_RLS_SYSTEM_TOKEN is not set}"
    scope="$(PGOPTIONS="-c app.rls_bypass=${MDARIX_RLS_SYSTEM_TOKEN}" psql --no-psqlrc --tuples-only --no-align \
        --dbname="${conninfo}" -c "SELECT public.mdarix_system_scope()" 2>/dev/null || true)"
    if [ "${scope}" != "t" ]; then
        echo "${name}: the login has no BYPASSRLS and the database does not accept MDARIX_RLS_SYSTEM_TOKEN;" \
            "a dump would silently miss every tenant's rows. Run scripts/configure_backup_role.py, or" \
            "scripts/set_rls_system_token.py against this database." >&2
        return 1
    fi
    echo "Backing up ${name} (through the system scope)"
    STAGE="dumping ${name}"
    PGOPTIONS="-c app.rls_bypass=${MDARIX_RLS_SYSTEM_TOKEN}" \
        pg_dump --format=custom --no-owner --no-privileges --enable-row-security --dbname="${conninfo}" \
        | encrypt "${TARGET}/${name}.dump.age"
}

export PGPASSWORD="${DB_PASSWORD}"
dump "control" "host=${POSTGRES_HOST} port=${POSTGRES_PORT:-5432} dbname=${POSTGRES_DB} user=${DB_USER} $(tls_params)"
unset PGPASSWORD

# Dedicated tenant databases: MDARIX_DATA_PLANE_<KEY>_DATABASE_URL (runtime) and, in .env.migrate,
# MDARIX_DATA_PLANE_<KEY>_DATABASE_URL_OWNER, both postgresql+pg8000://user:password@host:port/db. The owner's is used
# when present; the runtime login works too, through the system scope.
STAGE="listing dedicated databases"
planes="$(env | sed -n -E 's/^MDARIX_DATA_PLANE_([A-Z0-9_]+)_DATABASE_URL(_OWNER)?=.*/\1/p' | sort -u)"
for plane in ${planes}; do
    owner_var="MDARIX_DATA_PLANE_${plane}_DATABASE_URL_OWNER"
    runtime_var="MDARIX_DATA_PLANE_${plane}_DATABASE_URL"
    url="${!owner_var:-${!runtime_var:-}}"
    [ -n "${url}" ] || continue
    url="${url/postgresql+pg8000:/postgresql:}"
    dump "plane-${plane,,}" "$(with_tls_query "${url}")"
done

if [ -d /objects ] && [ -n "$(ls -A /objects 2>/dev/null)" ]; then
    echo "Backing up uploaded files"
    STAGE="archiving uploaded files"
    tar -C /objects -cf - . | encrypt "${TARGET}/objects.tar.age"
fi

STAGE="writing the manifest"
(cd "${TARGET}" && sha256sum ./*.age > MANIFEST.sha256)
echo "Backup written to ${TARGET}"

if [ -n "${MDARIX_BACKUP_S3_URI:-}" ]; then
    STAGE="copying off-site"
    aws s3 cp --recursive --only-show-errors "${TARGET}" "${MDARIX_BACKUP_S3_URI%/}/${STAMP}/"
    echo "Copied off-site to ${MDARIX_BACKUP_S3_URI%/}/${STAMP}/"
fi

STAGE="removing local backups older than ${KEEP_DAYS} days"
find /backups -mindepth 1 -maxdepth 1 -type d -name '20*Z' -mtime "+${KEEP_DAYS}" -exec rm -rf {} +

if [ -n "${MDARIX_BACKUP_HEARTBEAT_URL:-}" ]; then
    curl --silent --show-error --max-time 10 --retry 2 "${MDARIX_BACKUP_HEARTBEAT_URL}" > /dev/null \
        || echo "Backup heartbeat URL could not be reached" >&2
fi
STAGE="done"
echo "Done"
