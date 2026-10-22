#!/bin/sh
# Give Caddy's two volumes (/data: certificates, keys and the ACME account; /config: its saved configuration) to the
# user Caddy runs as. Run as root by the one-shot web-volumes service before every start of web
# (docker-compose.prod.yml), so volumes written by a release that ran Caddy as root (0.10.46 and earlier) become
# Caddy's own; nothing changes when they already are. With an argument ("0:0") it gives them back to root, for going
# back to such a release. Only the owner changes: no file is read, moved or removed, and permissions stay as they are.
set -eu
owner="${1:-10002:10002}"
case "$owner" in
  *[!0-9:]* | :* | *: | *:*:* | [!0-9]*) echo "usage: caddy-volumes.sh [uid:gid]" >&2; exit 2 ;;
esac
uid="${owner%%:*}"
gid="${owner##*:}"
for folder in /data /config; do
  [ -d "$folder" ] || { echo "caddy-volumes: $folder is not mounted" >&2; exit 1; }
done
changed=$(find /data /config \( ! -user "$uid" -o ! -group "$gid" \) -print | wc -l)
find /data /config \( ! -user "$uid" -o ! -group "$gid" \) -exec chown -h "$uid:$gid" {} +
echo "caddy-volumes: /data and /config belong to $uid:$gid ($changed changed)"
