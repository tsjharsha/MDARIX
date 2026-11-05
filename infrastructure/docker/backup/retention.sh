#!/usr/bin/env bash
# Which local backups backup.sh removes (owner decision, 5 Nov 2026: 30 daily + 12 monthly; 0.10.88).
#
#   source retention.sh; expired_backups /backups 20261105 30 12     # prints the folders to remove, one per line
#
# Kept: every backup of the last KEEP_DAYS days (any taken before an upgrade among them), the newest backup of each of
# the KEEP_MONTHS months before those days, and always the newest backup of all, however old (a rollback needs the one
# taken just before the last upgrade). Only folders named like a backup (20261103T151005Z) are ever listed. The names
# are UTC timestamps, so the decision reads the names, not file times a copy could have changed.

expired_backups() { # $1 folder, $2 today (YYYYMMDD), $3 days kept, $4 months kept
    local folder="$1" today="$2" days="$3" months="$4" cutoff path
    cutoff="$(date -u -d "${today} -${days} days" +%Y%m%d)"
    # Plain globbing: the backup image's find is BusyBox's, without -printf.
    for path in "${folder}"/20*Z; do
        if [ -d "${path}" ]; then basename "${path}"; fi
    done |
        { grep -E '^20[0-9]{6}T[0-9]{6}Z$' || true; } |
        sort -r |
        awk -v cutoff="${cutoff}" -v months="${months}" -v folder="${folder}" '
            NR == 1 { next }                                  # the newest backup of all
            substr($0, 1, 8) > cutoff { next }                # the last days: every backup
            {
                month = substr($0, 1, 6)
                if (!(month in seen)) {                       # the newest of its month
                    seen[month] = 1
                    if (++kept <= months) next
                }
                print folder "/" $0
            }'
}
