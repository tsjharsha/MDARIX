# MDARIX backup and restore tools: pg_dump/pg_restore 16, age (encryption) and the AWS CLI (off-site copy).
FROM postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea
RUN apk add --no-cache age aws-cli bash coreutils
COPY infrastructure/docker/backup/backup.sh /usr/local/bin/mdarix-backup
COPY infrastructure/docker/backup/restore.sh /usr/local/bin/mdarix-restore
RUN chmod 0755 /usr/local/bin/mdarix-backup /usr/local/bin/mdarix-restore
USER postgres
ENTRYPOINT ["/usr/local/bin/mdarix-backup"]
