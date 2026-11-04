# MDARIX backup and restore tools: pg_dump/pg_restore/psql 16, age (encryption), the AWS CLI (off-site copy) and curl
# (failure alert and success heartbeat). Base image pinned by digest; its Alpine packages take the security fixes
# published since (CI scans the result with Trivy).
FROM postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea
# gosu is only used by the postgres server's own entrypoint, which this image never runs; its Go runtime is the base
# image's main source of scanner findings, so it is removed.
RUN apk upgrade --no-cache && apk add --no-cache age aws-cli bash coreutils curl && rm -f /usr/local/bin/gosu
COPY infrastructure/docker/backup/backup.sh /usr/local/bin/mdarix-backup
COPY infrastructure/docker/backup/retention.sh /usr/local/bin/mdarix-backup-retention
COPY infrastructure/docker/backup/restore.sh /usr/local/bin/mdarix-restore
COPY scripts/check_backup_age.sh /usr/local/bin/mdarix-check-backup-age
RUN chmod 0755 /usr/local/bin/mdarix-backup /usr/local/bin/mdarix-backup-retention /usr/local/bin/mdarix-restore /usr/local/bin/mdarix-check-backup-age
# uid 70: the host backup folder is created for it (install -d -o 70 -g 70 -m 700 /var/backups/mdarix).
USER postgres
ENTRYPOINT ["/usr/local/bin/mdarix-backup"]
