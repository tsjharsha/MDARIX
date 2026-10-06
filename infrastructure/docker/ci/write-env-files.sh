#!/usr/bin/env bash
# CI only: write a complete .env.production and .env.migrate for docker-compose.prod.yml, with fresh random secrets
# and CI-safe addresses (no real mailbox, domain or bucket), so the production stack can be validated and started.
#
#   infrastructure/docker/ci/write-env-files.sh <folder>
#
# Overridable through the environment: CI_DB_HOST (db), CI_DB_PORT (5432), CI_DB_NAME (mdarix_r1), CI_DB_OWNER
# (mdarix_app), CI_DB_OWNER_PASSWORD (mdarix_app), CI_DB_CA_DIR (./certs), CI_BACKUP_DIR (/tmp/mdarix-backups),
# CI_AGE_RECIPIENT (a syntactically valid placeholder), CI_RELEASE (ci).
set -euo pipefail

out="${1:?folder to write .env.production and .env.migrate into}"
mkdir -p "${out}"
token() { openssl rand -base64 48 | tr -d '\n/+='; }
key() { openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n'; }

umask 077
cat > "${out}/.env.production" <<ENV
MDARIX_ENV=production
MDARIX_RELEASE=${CI_RELEASE:-ci}
MDARIX_IMAGE_REPOSITORY=mdarix
MDARIX_DOMAIN=localhost
MDARIX_APP_URL=https://localhost
ACME_EMAIL=ops@mdarix-ci.test
POSTGRES_HOST=${CI_DB_HOST:-db}
POSTGRES_PORT=${CI_DB_PORT:-5432}
POSTGRES_DB=${CI_DB_NAME:-mdarix_r1}
POSTGRES_SSLMODE=verify-full
MDARIX_DB_CA_DIR=${CI_DB_CA_DIR:-./certs}
POSTGRES_SSLROOTCERT=/etc/mdarix/certs/db-ca.pem
POSTGRES_USER=mdarix_runtime
POSTGRES_PASSWORD=${CI_RUNTIME_PASSWORD:=ci-runtime-$(token)}
MDARIX_DB_RUNTIME_USER=mdarix_runtime
MDARIX_DB_RUNTIME_PASSWORD=${CI_RUNTIME_PASSWORD}
MDARIX_DB_OWNER_USER=${CI_DB_OWNER:-mdarix_app}
MDARIX_DB_POOL_SIZE=5
MDARIX_DB_MAX_OVERFLOW=10
MDARIX_RLS_SYSTEM_TOKEN=$(token)
MDARIX_MFA_ENCRYPTION_KEY=$(key)
MDARIX_CONNECTOR_ENCRYPTION_KEY=$(key)
MDARIX_OBJECT_STORAGE_ENCRYPTION_KEY=$(key)
MDARIX_OBJECT_STORAGE_SIGNING_SECRET=$(token)
MDARIX_DEMO_REQUEST_SALT=$(token)
MDARIX_RATE_LIMIT_SALT=$(token)
MDARIX_OBJECT_STORAGE_PROVIDER=local
MDARIX_CLAMD_HOST=clamav
MDARIX_SMTP_HOST=smtp.invalid
MDARIX_SMTP_PORT=587
MDARIX_SMTP_USERNAME=ci
MDARIX_SMTP_PASSWORD=ci-not-a-real-mailbox
MDARIX_SMTP_FROM=MDARIX CI <no-reply@mdarix-ci.test>
MDARIX_TRIAL_ALERT_EMAIL=sales@mdarix-ci.test
MDARIX_COMPANY_LEGAL_NAME=MDARIX CI Ltd
MDARIX_COMPANY_ADDRESS=1 Test Street, Test City
MDARIX_SUPPORT_EMAIL=support@mdarix-ci.test
MDARIX_PRIVACY_EMAIL=privacy@mdarix-ci.test
MDARIX_LEGAL_TEXT_APPROVED=true
MDARIX_LEGAL_DIR=/var/lib/mdarix/legal
MDARIX_GENAI_PROVIDER=controlled
MDARIX_ALERT_EMAIL=ops@mdarix-ci.test
MDARIX_LOG_LEVEL=INFO
MDARIX_SESSION_IDLE_MINUTES=30
MDARIX_TRUSTED_PROXY_HOPS=1
MDARIX_REQUIRE_MFA_ROLES=PLATFORM_ADMIN,CUSTOMER_ADMIN,LEADER,APPROVER
MDARIX_REQUIRE_MFA_FOR_SIGNATURES=true
MDARIX_BACKUP_DIR=${CI_BACKUP_DIR:-/tmp/mdarix-backups}
MDARIX_BACKUP_AGE_RECIPIENT=${CI_AGE_RECIPIENT:-age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p}
MDARIX_BACKUP_KEEP_DAYS=14
ENV

cat > "${out}/.env.migrate" <<ENV
MDARIX_DB_OWNER_PASSWORD=${CI_DB_OWNER_PASSWORD:-mdarix_app}
MDARIX_BACKUP_DB_USER=mdarix_backup
MDARIX_BACKUP_DB_PASSWORD=ci-backup-$(token)
ENV
echo "Wrote ${out}/.env.production and ${out}/.env.migrate"
