#!/usr/bin/env bash
# Install the two free-trial AI gateways on the MDARIX server, loopback only (docs/runbooks/RELEASE_0.11.05.md, step 1):
#   FreeLLMAPI  127.0.0.1:3011   (the laptop's version: tag v0.16.14, commit 5127fee5)
#   OmniRoute   127.0.0.1:20128  (npm omniroute@3.8.52)
# each as a systemd service under its own unprivileged user, on a pinned Node.js whose download is checked against
# nodejs.org's SHA-256 list. Sample data only. OmniRoute 3.8.52 carries a critical Next.js flaw (remote code execution
# for anyone who can connect): it must never listen on anything but 127.0.0.1, and never sit behind a tunnel or proxy.
#
# The containers reach the gateways through push 2's forwarders in docker-compose.prod.yml: ai-host-bridge (host
# network) listens on 10.99.211.1, the gateway address of the ai-host bridge (mdarix-ai), and nowhere else. It is a
# compose service, not a systemd unit: a second forwarder here would fight it for the same address and ports.
#
#   sudo bash install_trial_ai_gateways.sh           install or repair (safe to run again), then --check
#   sudo bash install_trial_ai_gateways.sh --check   only verify: services up, every listener on loopback, firewall
set -euo pipefail

NODE_VERSION=24.15.0
FREELLMAPI_REPO=https://github.com/tashfeenahmed/freellmapi.git
FREELLMAPI_COMMIT=5127fee51ba97ad112915ebe227ba13df461a266
OMNIROUTE_VERSION=3.8.52
# The postinstall scripts OmniRoute's README (v3.8.52) lists for npm 11; nothing else may run install scripts.
OMNIROUTE_ALLOW_SCRIPTS=omniroute,keytar,onnxruntime-node,@parcel/watcher,@swc/core,protobufjs,esbuild
PREFIX=/opt/mdarix-ai
DATA=/var/lib/mdarix-ai
SERVICE_USER=mdarix-gw
UNIT_DIR=/etc/systemd/system
BRIDGE_ADDRESS=10.99.211.1
PORTS="3011 20128"
UNITS="mdarix-freellmapi mdarix-omniroute"

[ "$(id -u)" = "0" ] || { echo "STOP: run with sudo"; exit 1; }

fail=0
ok() { echo "OK    $*"; }
bad() { echo "FAIL  $*"; fail=1; }

check() {
  fail=0
  for unit in $UNITS; do
    if systemctl is-active --quiet "$unit"; then ok "$unit is running"; else bad "$unit is not running"; fi
  done
  listeners=$(ss -ltnpH)
  # Every listening socket of a gateway process (OmniRoute starts helpers on other ports) is on loopback.
  for unit in $UNITS; do
    procs="/sys/fs/cgroup/system.slice/$unit.service/cgroup.procs"
    [ -r "$procs" ] || continue
    for pid in $(cat "$procs"); do
      while read -r line; do
        [ -n "$line" ] || continue
        address=$(awk '{print $4}' <<<"$line")
        case "$address" in
          127.0.0.1:* | "[::1]:"*) ok "$unit pid $pid listens on $address" ;;
          *) bad "$unit pid $pid listens on $address (only 127.0.0.1 is allowed)" ;;
        esac
      done < <(grep -E "pid=$pid," <<<"$listeners" || true)
    done
  done
  # Nothing at all on the gateway ports except loopback and the compose forwarder on the bridge gateway.
  for port in $PORTS; do
    while read -r line; do
      [ -n "$line" ] || continue
      address=$(awk '{print $4}' <<<"$line")
      case "$address" in
        "127.0.0.1:$port" | "[::1]:$port") ;;
        "$BRIDGE_ADDRESS:$port") ok "forwarder on $address (ai-host bridge gateway only)" ;;
        *) bad "port $port is open on $address: $line" ;;
      esac
    done < <(awk -v p=":$port" 'substr($4, length($4) - length(p) + 1) == p' <<<"$listeners")
    status=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:$port/" || true)
    if [ "$status" != "000" ]; then ok "127.0.0.1:$port answers (HTTP $status)"; else bad "127.0.0.1:$port does not answer"; fi
  done
  if ip -4 addr show mdarix-ai >/dev/null 2>&1; then
    grep -qE "^$BRIDGE_ADDRESS:3011 " < <(awk '{print $4 " "}' <<<"$listeners") \
      && ok "the compose forwarder ai-host-bridge listens on $BRIDGE_ADDRESS" \
      || bad "the ai-host bridge exists but nothing listens on $BRIDGE_ADDRESS:3011 (docker compose ps ai-host-bridge)"
  else
    echo "INFO  the ai-host bridge (mdarix-ai) does not exist yet: it appears when release 0.11.05 starts"
  fi
  if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "^Status: active"; then
    rules=$(ufw status)
    grep -qE "^$BRIDGE_ADDRESS 3011,20128/tcp on mdarix-ai +ALLOW" <<<"$rules" \
      && ok "ufw lets only the mdarix-ai bridge reach $BRIDGE_ADDRESS:3011,20128" \
      || bad "ufw rule for the mdarix-ai bridge is missing"
    if grep -E "(^| )(3011|20128)([,/ ]|$)" <<<"$rules" | grep -vE "^$BRIDGE_ADDRESS 3011,20128/tcp on mdarix-ai " | grep -q .; then
      bad "ufw has another rule naming 3011 or 20128: remove it"
    else
      ok "ufw opens 3011 and 20128 nowhere else"
    fi
  else
    echo "INFO  ufw is not active: the cloud firewall must never allow 3011 or 20128"
  fi
  [ "$fail" -eq 0 ] && echo "CHECK=PASS" || echo "CHECK=FAIL"
  return "$fail"
}

if [ "${1:-}" = "--check" ]; then
  check
  exit $?
fi

as_user() { sudo -u "$SERVICE_USER" -H env PATH="$PREFIX/node/bin:/usr/bin:/bin" "$@"; }

# 1. Node.js, pinned and checked against the published SHA-256 list.
case "$(uname -m)" in
  x86_64) arch=x64 ;;
  aarch64) arch=arm64 ;;
  *) echo "STOP: unsupported machine $(uname -m)"; exit 1 ;;
esac
node_dir="$PREFIX/node-v$NODE_VERSION-linux-$arch"
install -d -m 755 "$PREFIX"
if [ ! -x "$node_dir/bin/node" ]; then
  work=$(mktemp -d)
  tarball="node-v$NODE_VERSION-linux-$arch.tar.xz"
  curl -fsSL -o "$work/$tarball" "https://nodejs.org/dist/v$NODE_VERSION/$tarball"
  curl -fsSL -o "$work/SHASUMS256.txt" "https://nodejs.org/dist/v$NODE_VERSION/SHASUMS256.txt"
  (cd "$work" && grep " $tarball\$" SHASUMS256.txt | sha256sum -c -) || { echo "STOP: Node.js checksum mismatch"; exit 1; }
  tar -xJf "$work/$tarball" -C "$PREFIX"
  rm -rf "$work"
fi
ln -sfn "$node_dir" "$PREFIX/node"
echo "node $("$PREFIX/node/bin/node" --version), npm $("$PREFIX/node/bin/npm" --version)"

# 2. The service user: no login, no sudo, owns only the gateways' folders.
id "$SERVICE_USER" >/dev/null 2>&1 \
  || useradd --system --home-dir "$DATA" --shell /usr/sbin/nologin --user-group "$SERVICE_USER"
install -d -m 750 -o "$SERVICE_USER" -g "$SERVICE_USER" "$DATA" "$DATA/omniroute" "$PREFIX/freellmapi" "$PREFIX/omniroute"

# 3. FreeLLMAPI at the laptop's commit.
if [ "$(git -C "$PREFIX/freellmapi" rev-parse HEAD 2>/dev/null || true)" != "$FREELLMAPI_COMMIT" ] \
  || [ ! -f "$PREFIX/freellmapi/server/dist/index.js" ]; then
  [ -d "$PREFIX/freellmapi/.git" ] || as_user git clone -q "$FREELLMAPI_REPO" "$PREFIX/freellmapi"
  as_user git -C "$PREFIX/freellmapi" fetch -q origin
  as_user git -C "$PREFIX/freellmapi" -c advice.detachedHead=false checkout -q "$FREELLMAPI_COMMIT"
  (cd "$PREFIX/freellmapi" && as_user npm ci --no-audit --no-fund && as_user npm run build)
fi

# 4. OmniRoute, exact version.
installed=$(as_user "$PREFIX/node/bin/node" -p "require('$PREFIX/omniroute/node_modules/omniroute/package.json').version" 2>/dev/null || true)
if [ "$installed" != "$OMNIROUTE_VERSION" ]; then
  [ -f "$PREFIX/omniroute/package.json" ] || as_user sh -c "echo '{\"private\": true}' > '$PREFIX/omniroute/package.json'"
  (cd "$PREFIX/omniroute" && as_user npm install --no-audit --no-fund --save-exact \
    --allow-scripts="$OMNIROUTE_ALLOW_SCRIPTS" "omniroute@$OMNIROUTE_VERSION")
fi

# 5. The services: loopback only, unprivileged, no write access outside their own folders.
write_unit() { # $1 name; the unit text on stdin; returns 0 when the file changed
  local new
  new=$(cat)
  if [ -f "$UNIT_DIR/$1" ] && [ "$(cat "$UNIT_DIR/$1")" = "$new" ]; then return 1; fi
  printf '%s\n' "$new" > "$UNIT_DIR/$1"
  chmod 644 "$UNIT_DIR/$1"
}
changed=""
write_unit mdarix-freellmapi.service <<'UNIT' && changed="$changed mdarix-freellmapi"
[Unit]
Description=FreeLLMAPI trial AI gateway for MDARIX (127.0.0.1 only, sample data only)
After=network-online.target
Wants=network-online.target

[Service]
User=mdarix-gw
Group=mdarix-gw
WorkingDirectory=/opt/mdarix-ai/freellmapi/server
Environment=HOST=127.0.0.1
Environment=PORT=3011
ExecStart=/opt/mdarix-ai/node/bin/node dist/index.js
Restart=on-failure
RestartSec=5
MemoryMax=512M
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/mdarix-ai/freellmapi /var/lib/mdarix-ai
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX

[Install]
WantedBy=multi-user.target
UNIT
write_unit mdarix-omniroute.service <<'UNIT' && changed="$changed mdarix-omniroute"
[Unit]
Description=OmniRoute trial AI gateway for MDARIX (127.0.0.1 only, sample data only; never expose it)
After=network-online.target
Wants=network-online.target

[Service]
User=mdarix-gw
Group=mdarix-gw
WorkingDirectory=/opt/mdarix-ai/omniroute
Environment=HOME=/var/lib/mdarix-ai
Environment=OMNIROUTE_SERVER_HOST=127.0.0.1
Environment=PORT=20128
Environment=DATA_DIR=/var/lib/mdarix-ai/omniroute
Environment=REQUIRE_API_KEY=true
Environment=CLOUD_URL=
Environment=NEXT_PUBLIC_CLOUD_URL=
Environment=NEXT_TELEMETRY_DISABLED=1
ExecStart=/opt/mdarix-ai/node/bin/node node_modules/omniroute/bin/omniroute.mjs serve --port 20128 --no-open --no-tray
Restart=on-failure
RestartSec=5
MemoryMax=1G
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/mdarix-ai/omniroute /var/lib/mdarix-ai
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
for unit in $UNITS; do
  systemctl enable -q "$unit"
  case " $changed " in
    *" $unit "*) systemctl restart "$unit" ;;
    *) systemctl start "$unit" ;;
  esac
done

# 6. Host firewall: only the ai-host bridge may reach the compose forwarder; 3011 and 20128 stay closed elsewhere.
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "^Status: active"; then
  ufw allow in on mdarix-ai to "$BRIDGE_ADDRESS" port 3011,20128 proto tcp >/dev/null
fi

echo "Waiting up to 90 s for both gateways to listen..."
for _ in $(seq 1 18); do
  curl -s -o /dev/null --max-time 2 http://127.0.0.1:3011/ && curl -s -o /dev/null --max-time 2 http://127.0.0.1:20128/ && break
  sleep 5
done
check
