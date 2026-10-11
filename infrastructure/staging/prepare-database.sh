#!/usr/bin/env bash
# Staging only (docker-compose.staging-oracle.yml, docs/runbooks/STAGING_ORACLE.md): what the Postgres container on
# the staging server needs before its first start. Run it once, with sudo, as a user that has sudo (the deploy user
# has none); it finds the checkout from its own path:
#
#   sudo bash /home/deploy/mdarix/infrastructure/staging/prepare-database.sh
#
# It writes, and never prints:
#   staging-secrets/postgres-admin-password   the database administrator's password (used once, when the database
#                                             is created); kept if it already exists
#   staging-secrets/db-tls/server.key, .crt   the database's TLS key and certificate (name "postgres", the service
#                                             name the application connects to), signed by a new private CA
#   certs/db-ca.pem                           that CA's certificate, which the application trusts
#                                             (POSTGRES_SSLMODE=verify-full, POSTGRES_SSLROOTCERT=/etc/mdarix/certs/db-ca.pem)
#
# The CA's private key exists only while this script runs: nothing can sign another certificate afterwards. The
# server certificate lasts 825 days; to replace it run the script again with --renew, then restart everything:
#   sudo bash /home/deploy/mdarix/infrastructure/staging/prepare-database.sh --renew
#   docker compose up -d --force-recreate --no-build --wait        (as deploy)
#
# Key and password files belong to uid 999, the postgres user of the pgvector/pgvector image, which refuses a key
# that others can read.
set -euo pipefail

POSTGRES_UID=999
RENEW=false
case "${1:-}" in
    "") ;;
    --renew) RENEW=true ;;
    *) echo "usage: sudo bash <checkout>/infrastructure/staging/prepare-database.sh [--renew]" >&2; exit 2 ;;
esac

if [ "$(id -u)" != "0" ]; then
    echo "Run with sudo: the key and password files must belong to the database container's user (uid ${POSTGRES_UID})." >&2
    exit 1
fi
command -v openssl >/dev/null || { echo "openssl is not installed (sudo apt-get install -y openssl)." >&2; exit 1; }

cd "$(dirname "$0")/../.."
if [ ! -f docker-compose.staging-oracle.yml ]; then
    echo "Run this from an MDARIX checkout (docker-compose.staging-oracle.yml not found)." >&2
    exit 1
fi

SECRETS=staging-secrets
TLS="${SECRETS}/db-tls"
install -d -m 755 "${SECRETS}" "${TLS}" certs

# 1. The administrator's password: random, written once.
if [ -s "${SECRETS}/postgres-admin-password" ]; then
    echo "Kept the existing ${SECRETS}/postgres-admin-password."
else
    ( umask 077 && openssl rand -base64 33 | tr -d '\n' > "${SECRETS}/postgres-admin-password" )
    echo "Wrote ${SECRETS}/postgres-admin-password."
fi
chown "${POSTGRES_UID}:${POSTGRES_UID}" "${SECRETS}/postgres-admin-password"
chmod 600 "${SECRETS}/postgres-admin-password"

# 2. TLS: a private CA, and a certificate for the host name "postgres" signed by it.
if [ -s "${TLS}/server.crt" ] && [ "${RENEW}" != "true" ]; then
    echo "Kept the existing database certificate (${TLS}/server.crt); pass --renew to replace it."
    exit 0
fi

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT
chmod 700 "${WORK}"

cat > "${WORK}/ca.cnf" <<'EOF'
[req]
distinguished_name = dn
x509_extensions = ca
prompt = no
[dn]
CN = MDARIX staging database CA
[ca]
basicConstraints = critical, CA:TRUE, pathlen:0
keyUsage = critical, keyCertSign, cRLSign
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always
EOF

cat > "${WORK}/server.ext" <<'EOF'
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature
extendedKeyUsage = serverAuth
subjectAltName = DNS:postgres
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always
EOF

openssl req -x509 -new -config "${WORK}/ca.cnf" -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes \
    -days 3650 -keyout "${WORK}/ca.key" -out "${WORK}/ca.crt" 2>/dev/null
openssl req -new -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -subj "/CN=postgres" \
    -keyout "${WORK}/server.key" -out "${WORK}/server.csr" 2>/dev/null
openssl x509 -req -in "${WORK}/server.csr" -CA "${WORK}/ca.crt" -CAkey "${WORK}/ca.key" \
    -set_serial "0x$(openssl rand -hex 16)" -days 825 -extfile "${WORK}/server.ext" -out "${WORK}/server.crt" 2>/dev/null
openssl verify -CAfile "${WORK}/ca.crt" "${WORK}/server.crt" >/dev/null

install -m 600 -o "${POSTGRES_UID}" -g "${POSTGRES_UID}" "${WORK}/server.key" "${TLS}/server.key"
install -m 644 -o root -g root "${WORK}/server.crt" "${TLS}/server.crt"
install -m 644 -o root -g root "${WORK}/ca.crt" certs/db-ca.pem

echo "Wrote ${TLS}/server.key and ${TLS}/server.crt (valid until $(openssl x509 -enddate -noout -in "${TLS}/server.crt" | cut -d= -f2))."
echo "Wrote certs/db-ca.pem. In .env.production: POSTGRES_HOST=postgres, POSTGRES_SSLMODE=verify-full,"
echo "POSTGRES_SSLROOTCERT=/etc/mdarix/certs/db-ca.pem."
