#!/usr/bin/env bash
# Alert when the newest MDARIX backup is too old: a backup that silently stopped running (cron removed, VM rebuilt,
# credentials expired) is as dangerous as one that fails, and backup.sh can only report failures of runs that start.
#
# Looks at the off-site copies in MDARIX_BACKUP_S3_URI (the ones that survive losing the VM), or at /backups when no
# bucket is configured, and posts to MDARIX_ALERT_WEBHOOK when the newest is older than MDARIX_BACKUP_MAX_AGE_HOURS
# (26: a daily backup plus two hours' slack). Exits 1 when too old or none found. It runs inside the backup image,
# which has the AWS CLI and the bucket credentials (.env.migrate); host cron, an hour after the backup:
#
#   15 4 * * * cd /home/deploy/mdarix && docker compose -f docker-compose.prod.yml --env-file .env.production \
#       --profile backup run --rm --entrypoint mdarix-check-backup-age backup >> /var/log/mdarix-backup.log 2>&1
set -euo pipefail

MAX_AGE_HOURS="${MDARIX_BACKUP_MAX_AGE_HOURS:-26}"

# Backup folders are named by their UTC start time, e.g. 20261003T021500Z.
if [ -n "${MDARIX_BACKUP_S3_URI:-}" ]; then
    where="${MDARIX_BACKUP_S3_URI%/}/"
    newest="$(aws s3 ls "${where}" | awk '$1 == "PRE" {print $2}' | tr -d '/' | grep -E '^[0-9]{8}T[0-9]{6}Z$' | sort | tail -n 1 || true)"
else
    where="/backups/"
    newest="$(ls -1 /backups 2>/dev/null | grep -E '^[0-9]{8}T[0-9]{6}Z$' | sort | tail -n 1 || true)"
fi

alert() {
    echo "$1" >&2
    if [ -n "${MDARIX_ALERT_WEBHOOK:-}" ]; then
        local text
        text="$(printf '[MDARIX %s] Backups are not arriving\n%s' "${MDARIX_ENV:-production}" "$1" \
            | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | tr '\n' ' ')"
        curl --silent --show-error --max-time 10 --retry 2 -H 'Content-Type: application/json' \
            -d "{\"text\": \"${text}\"}" "${MDARIX_ALERT_WEBHOOK}" > /dev/null || echo "Alert webhook could not be reached" >&2
    fi
    exit 1
}

if [ -z "${newest}" ]; then
    alert "No backup found in ${where}. Check the backup cron job and its log (/var/log/mdarix-backup.log)."
fi

stamp="${newest:0:4}-${newest:4:2}-${newest:6:2}T${newest:9:2}:${newest:11:2}:${newest:13:2}Z"
taken="$(date -u -d "${stamp}" +%s)"
age_hours=$(( ($(date -u +%s) - taken) / 3600 ))
if [ "${age_hours}" -ge "${MAX_AGE_HOURS}" ]; then
    alert "The newest backup in ${where} is ${newest}, ${age_hours} hours old (limit ${MAX_AGE_HOURS}). Check the backup cron job and its log."
fi
echo "Newest backup ${newest} in ${where} is ${age_hours} hours old (limit ${MAX_AGE_HOURS})."
