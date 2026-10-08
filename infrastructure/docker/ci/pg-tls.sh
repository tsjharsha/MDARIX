#!/usr/bin/env bash
# CI only: start a pgvector PostgreSQL 16 that requires TLS with a certificate signed by a throw-away CA, so the
# production checks (POSTGRES_SSLMODE=verify-full) run against a real certificate and host-name check.
#
#   CERT_DIR=/tmp/pgtls PG_CONTAINER=pg PG_PORT=5432 CERT_HOSTS="DNS:localhost,DNS:db,IP:127.0.0.1" \
#       infrastructure/docker/ci/pg-tls.sh
#
# Writes $CERT_DIR/db-ca.pem (the CA to trust: POSTGRES_SSLROOTCERT). The superuser is $PG_USER/$PG_PASSWORD on
# database $PG_DB. Certificates are copied into the container (docker cp), so this also works where bind-mounted
# files cannot be given to the postgres user.
set -euo pipefail
export MSYS_NO_PATHCONV=1

CERT_DIR="${CERT_DIR:?folder for the certificates}"
PG_CONTAINER="${PG_CONTAINER:-pg}"
PG_PORT="${PG_PORT:-5432}"
PG_USER="${PG_USER:-mdarix_app}"
PG_PASSWORD="${PG_PASSWORD:-mdarix_app}"
PG_DB="${PG_DB:-mdarix_r1}"
CERT_HOSTS="${CERT_HOSTS:-DNS:localhost,DNS:db,IP:127.0.0.1}"
PG_IMAGE="${PG_IMAGE:-pgvector/pgvector:pg16}"

mkdir -p "${CERT_DIR}"
cd "${CERT_DIR}"
# Python 3.13 verifies strictly (VERIFY_X509_STRICT): the CA needs its key usage and the server certificate its key
# identifiers, as a managed provider's certificates have them.
openssl req -x509 -new -nodes -days 2 -newkey rsa:2048 -subj "/CN=MDARIX CI database CA" \
    -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign" \
    -addext "subjectKeyIdentifier=hash" -keyout ca.key -out db-ca.pem 2> /dev/null
openssl req -new -nodes -newkey rsa:2048 -subj "/CN=db" -keyout server.key -out server.csr 2> /dev/null
printf '%s\n' "subjectAltName=${CERT_HOSTS}" "basicConstraints=critical,CA:FALSE" \
    "keyUsage=critical,digitalSignature,keyEncipherment" "extendedKeyUsage=serverAuth" \
    "subjectKeyIdentifier=hash" "authorityKeyIdentifier=keyid,issuer" > server.ext
openssl x509 -req -in server.csr -CA db-ca.pem -CAkey ca.key -CAcreateserial -days 2 -extfile server.ext \
    -out server.crt 2> /dev/null
chmod 644 db-ca.pem

docker create --name "${PG_CONTAINER}" -p "${PG_PORT}:5432" \
    -e POSTGRES_USER="${PG_USER}" -e POSTGRES_PASSWORD="${PG_PASSWORD}" -e POSTGRES_DB="${PG_DB}" \
    --entrypoint bash "${PG_IMAGE}" -c 'mkdir -p /tls && cp /certs-src/server.crt /certs-src/server.key /tls/ \
        && chown postgres:postgres /tls/server.crt /tls/server.key && chmod 600 /tls/server.key \
        && exec docker-entrypoint.sh postgres -c ssl=on -c ssl_cert_file=/tls/server.crt -c ssl_key_file=/tls/server.key' \
    > /dev/null
mkdir -p src && cp server.crt server.key src/
docker cp src/. "${PG_CONTAINER}:/certs-src" > /dev/null
rm -rf src ca.key server.csr server.ext
docker start "${PG_CONTAINER}" > /dev/null
for _ in $(seq 1 60); do
    # pg_isready over TCP only answers once the server accepts connections (not during initdb's temporary start).
    if docker exec "${PG_CONTAINER}" pg_isready -h 127.0.0.1 -U "${PG_USER}" -d "${PG_DB}" > /dev/null 2>&1; then
        echo "PostgreSQL with TLS is ready on port ${PG_PORT} (CA: ${CERT_DIR}/db-ca.pem)"
        exit 0
    fi
    sleep 2
done
docker logs "${PG_CONTAINER}" >&2
exit 1
