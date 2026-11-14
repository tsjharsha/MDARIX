#!/usr/bin/env bash
# Free security scans for a test release (B10-1 evidence). Runs from Git Bash on Windows, WSL or Linux, with Docker.
# Every tool runs from a pinned Docker image, one at a time; nothing is installed on the machine.
#
#   scripts/security_scan.sh [--release NAME] [step ...]
#
# Steps (default: all, in this order):
#   static      = semgrep bandit pip-audit npm-audit gitleaks trivy
#   dynamic     = stack-up zap-baseline zap-api schemathesis nuclei cross-tenant stack-stop
#   public      = testssl observatory           (read-only, https://mdarix.com only)
#   summary     writes SUMMARY.md from the reports already in the release folder
#   all         = static dynamic public summary
# Single steps can be named too, e.g.: scripts/security_scan.sh --release 0.10.96 zap-baseline summary
#
# Reports go to security-reports/<release>/ (git-ignored, never committed or uploaded). Findings reviewed as false
# positives are listed once, with a reason, in infrastructure/security-scan/allowlist.txt.
#
# Target rules, enforced below:
#   - attack-style scans (ZAP, Schemathesis, Nuclei) reach only the local test copy started by "stack-up"
#     (docker compose project mdarix-scan, synthetic data, ports on 127.0.0.1), over its private Docker network;
#   - only testssl.sh and the Mozilla HTTP Observatory touch the public site, read-only, and only mdarix.com;
#   - the script never removes containers, volumes or images: "stack-stop" runs docker compose stop.
#
# Settings (environment): SCAN_API_PORT (18000), SCAN_DB_PORT (15433), SCAN_USER (the synthetic user the API scans
# sign in as), ZAP_AUTH_HEADER and ZAP_AUTH_HEADER_VALUE (an auth header to use instead), ZAP_MAX_MINUTES (30, active
# scan cap), SCHEMATHESIS_MAX_EXAMPLES (10), SCAN_EXTRA_IMAGES (more built images for Trivy, space separated), PYTHON
# (interpreter for the cross-tenant tests and the summary; default: the repository virtualenv, else python3).
set -uo pipefail

# Git Bash would rewrite container paths such as /zap/wrk into Windows paths.
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'

# ---- pinned tool images (exact versions; update deliberately, never to "latest") ----------------------------------
IMG_ZAP="ghcr.io/zaproxy/zaproxy:2.16.1"
IMG_SCHEMATHESIS="schemathesis/schemathesis:v4.1.4"
IMG_NUCLEI="projectdiscovery/nuclei:v3.4.10"
IMG_SEMGREP="semgrep/semgrep:1.131.0"
IMG_TRIVY="aquasec/trivy:0.57.0" # the version ci.yml and release.yml use
IMG_GITLEAKS="zricethezav/gitleaks:v8.28.0"
IMG_TESTSSL="ghcr.io/testssl/testssl.sh:3.2@sha256:a0b0f35dea9e129804eae31e47d310d5c15423c9e495b5c2826ec0b5e4494cc7"
IMG_PYTHON="python:3.13.7-slim-bookworm"
IMG_NODE="node:22.19.0-bookworm-slim"
BANDIT_VERSION="1.8.6"
PIP_AUDIT_VERSION="2.10.1" # as requirements-dev.txt

PUBLIC_HOST="mdarix.com" # the only public host any step may contact
SCAN_TARGET="http://scan-api:8000"
SCAN_PROJECT="mdarix-scan"
SCAN_NETWORK="${SCAN_PROJECT}_default"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}" || exit 2
COMPOSE_FILE_SCAN="infrastructure/security-scan/docker-compose.scan.yml"
ALLOWLIST="infrastructure/security-scan/allowlist.txt"

die() {
  echo "security_scan: $*" >&2
  exit 2
}

# A path Docker Desktop on Windows understands (C:/...), or the plain path on Linux and WSL.
host_path() { (cd "$1" && (pwd -W 2>/dev/null || pwd)); }

RELEASE=""
STEPS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --release) RELEASE="${2:?--release needs a name}"; shift 2 ;;
    -h | --help) sed -n '2,/^set -uo/p' "$0" | grep '^#'; exit 0 ;;
    *) STEPS+=("$1"); shift ;;
  esac
done
[ -n "${RELEASE}" ] || RELEASE="$(tr -d '[:space:]' < VERSION)-$(date +%Y%m%d)"
case "${RELEASE}" in *[!A-Za-z0-9._-]*) die "release name may hold letters, digits, dot, dash and underscore only" ;; esac
[ ${#STEPS[@]} -gt 0 ] || STEPS=(all)

REPORTS="${ROOT}/security-reports/${RELEASE}"
mkdir -p "${REPORTS}"
REPORTS_HOST="$(host_path "${REPORTS}")"
ROOT_HOST="$(host_path "${ROOT}")"
STATUS="${REPORTS}/status.tsv"
# Native Windows programs (docker compose, python.exe) get paths relative to the repository root: with path
# conversion off they cannot read Git Bash paths such as /c/Users/...
REPORTS_REL="security-reports/${RELEASE}"
STACK_ENV="${REPORTS_REL}/stack/scan.env"
API_IMAGE="mdarix-scan/api:${RELEASE}"

record() { # tool, status (ran | failed | skipped), note
  printf '%s\t%s\t%s\n' "$1" "$2" "${3:-}" >> "${STATUS}"
  echo "== $1: $2 ${3:-}"
}

# Refuse any attack-style target that is not the local test copy.
assert_local_target() {
  local url="$1"
  case "${url}" in *mdarix.com* | *mdarix.in* | *mdarix.net*) die "refusing to scan a public MDARIX host: ${url}" ;; esac
  case "${url}" in
    http://scan-api:8000 | http://scan-api:8000/*) ;;
    *) die "attack-style scans run only against the local test copy (${SCAN_TARGET}), not ${url}" ;;
  esac
  docker network inspect "${SCAN_NETWORK}" > /dev/null 2>&1 || die "the local test copy is not running: run the stack-up step first"
}

pick_python() {
  if [ -n "${PYTHON:-}" ]; then echo "${PYTHON}"; return; fi
  local venv
  for venv in "${ROOT}/.venv" "${ROOT}/../../../.venv"; do
    [ -x "${venv}/Scripts/python.exe" ] && { echo "${venv}/Scripts/python.exe"; return; }
    [ -x "${venv}/bin/python" ] && { echo "${venv}/bin/python"; return; }
  done
  command -v python3 || command -v python
}

compose_scan() {
  COMPOSE_PROJECT_NAME="${SCAN_PROJECT}" docker compose -p "${SCAN_PROJECT}" -f "${COMPOSE_FILE_SCAN}" \
    --env-file "${STACK_ENV}" "$@"
}

# ---- static checks -------------------------------------------------------------------------------------------------
# Semgrep, Bandit and the Trivy config scan read a snapshot of the committed HEAD (git archive): exactly what the release
# ships, without untracked local files, and readable in a container even from a git worktree.
SOURCE_SNAPSHOT=""
source_snapshot() {
  [ -n "${SOURCE_SNAPSHOT}" ] && return 0
  local dir="${REPORTS}/source"
  rm -rf "${dir}" && mkdir -p "${dir}"
  git archive HEAD | tar -x -C "${dir}" || die "could not export HEAD for the static scans"
  git rev-parse HEAD > "${REPORTS}/source-commit.txt"
  SOURCE_SNAPSHOT="$(host_path "${dir}")"
}

head_note() { echo "HEAD $(cut -c1-8 "${REPORTS}/source-commit.txt")"; }

run_semgrep() {
  source_snapshot
  docker run --rm -v "${SOURCE_SNAPSHOT}:/src:ro" -v "${REPORTS_HOST}:/out" -w /src "${IMG_SEMGREP}" \
    semgrep scan --metrics off --disable-version-check --quiet --json --output /out/semgrep.json \
    --config p/python --config p/javascript --config p/typescript --config p/react --config p/owasp-top-ten \
    --config p/dockerfile --config p/github-actions \
    --exclude 'docs' --exclude 'videos' --exclude 'artifacts' > "${REPORTS}/semgrep.log" 2>&1
  local rc=$?
  # 0 = no findings, 1 = findings; anything else is a tool error (including a run that scanned no file).
  if [ ${rc} -le 1 ] && [ -s "${REPORTS}/semgrep.json" ] && ! grep -q "^fatal:" "${REPORTS}/semgrep.log"; then
    record semgrep ran "$(head_note)"
  else
    record semgrep failed "exit ${rc}, see semgrep.log"
  fi
}

run_bandit() {
  source_snapshot
  docker run --rm -v "${SOURCE_SNAPSHOT}:/src:ro" -v "${REPORTS_HOST}:/out" "${IMG_PYTHON}" sh -c \
    "pip install --quiet --disable-pip-version-check --root-user-action=ignore bandit==${BANDIT_VERSION} >/dev/null \
     && bandit -r /src -q -f json -o /out/bandit.json -x /src/tests,/src/frontend,/src/artifacts,/src/docs,/src/videos" \
    > "${REPORTS}/bandit.log" 2>&1
  local rc=$?
  if [ ${rc} -le 1 ] && [ -s "${REPORTS}/bandit.json" ]; then record bandit ran "$(head_note), tests excluded"; else record bandit failed "exit ${rc}, see bandit.log"; fi
}

run_pip_audit() {
  # The lock is fully pinned with hashes, so pip-audit checks it as written without resolving or installing anything.
  docker run --rm -v "${ROOT_HOST}:/src:ro" -v "${REPORTS_HOST}:/out" "${IMG_PYTHON}" sh -c \
    "pip install --quiet --disable-pip-version-check --root-user-action=ignore pip-audit==${PIP_AUDIT_VERSION} >/dev/null \
     && pip-audit --disable-pip -r /src/requirements.txt --format json --output /out/pip-audit.json --progress-spinner off" \
    > "${REPORTS}/pip-audit.log" 2>&1
  local rc=$?
  if [ ${rc} -le 1 ] && [ -s "${REPORTS}/pip-audit.json" ]; then record pip-audit ran; else record pip-audit failed "exit ${rc}, see pip-audit.log"; fi
}

run_npm_audit() {
  # Reads frontend/package-lock.json only; no node_modules are needed or installed.
  docker run --rm -v "${ROOT_HOST}/frontend:/app:ro" -w /app "${IMG_NODE}" \
    npm audit --package-lock-only --json > "${REPORTS}/npm-audit.json" 2> "${REPORTS}/npm-audit.log"
  local rc=$?
  if grep -q '"vulnerabilities"' "${REPORTS}/npm-audit.json" 2> /dev/null; then record npm-audit ran; else record npm-audit failed "exit ${rc}, see npm-audit.log"; fi
}

run_gitleaks() {
  # The whole history of every branch, redacted: the report never holds a secret's value. In a git worktree the
  # history lives in the main repository's .git folder, so that repository is mounted (read-only).
  local common repo_host
  common="$(git rev-parse --path-format=absolute --git-common-dir)" || { record gitleaks failed "not a git checkout"; return; }
  repo_host="$(host_path "$(dirname "${common}")")"
  docker run --rm -v "${repo_host}:/repo:ro" -v "${ROOT_HOST}/.gitleaks.toml:/config/gitleaks.toml:ro" \
    -v "${REPORTS_HOST}:/out" -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0='*' \
    "${IMG_GITLEAKS}" git /repo --redact --no-banner --config /config/gitleaks.toml \
    --report-format json --report-path /out/gitleaks.json --exit-code 0 > "${REPORTS}/gitleaks.log" 2>&1
  local rc=$?
  if [ ${rc} -eq 0 ] && [ -f "${REPORTS}/gitleaks.json" ]; then record gitleaks ran "history of all branches, redacted"; else record gitleaks failed "exit ${rc}, see gitleaks.log"; fi
}

run_trivy() {
  # Built images (the scan copy's API image, plus SCAN_EXTRA_IMAGES) and the repository's Docker/compose config.
  local images=() image name rc ok=1
  docker image inspect "${API_IMAGE}" > /dev/null 2>&1 || docker build -q -f Dockerfile.api -t "${API_IMAGE}" . > "${REPORTS}/trivy-build.log" 2>&1
  docker image inspect "${API_IMAGE}" > /dev/null 2>&1 && images+=("${API_IMAGE}")
  for image in ${SCAN_EXTRA_IMAGES:-}; do images+=("${image}"); done
  [ ${#images[@]} -gt 0 ] || { record trivy failed "no image could be built, see trivy-build.log"; return; }
  : > "${REPORTS}/trivy.log"
  for image in "${images[@]}"; do
    name="$(echo "${image}" | tr '/:@' '___')"
    docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v mdarix-scan-trivy-cache:/root/.cache/trivy \
      -v "${ROOT_HOST}/.trivyignore.yaml:/review/.trivyignore.yaml:ro" -v "${REPORTS_HOST}:/out" "${IMG_TRIVY}" image \
      --scanners vuln,secret --ignorefile /review/.trivyignore.yaml --no-progress --format json \
      --output "/out/trivy-image-${name}.json" "${image}" >> "${REPORTS}/trivy.log" 2>&1 || ok=0
  done
  source_snapshot
  docker run --rm -v "${SOURCE_SNAPSHOT}:/src:ro" -v mdarix-scan-trivy-cache:/root/.cache/trivy -v "${REPORTS_HOST}:/out" \
    "${IMG_TRIVY}" config --format json --output /out/trivy-config.json /src >> "${REPORTS}/trivy.log" 2>&1 || ok=0
  if [ ${ok} -eq 1 ]; then record trivy ran "images: ${images[*]}; config"; else record trivy failed "see trivy.log"; fi
}

# ---- local test copy ------------------------------------------------------------------------------------------------
random_hex() { od -An -N"$1" -tx1 /dev/urandom | tr -d ' \n'; }
random_key() { head -c 32 /dev/urandom | base64 | tr '+/' '-_' | tr -d '\n'; }

stack_up() {
  mkdir -p "$(dirname "${STACK_ENV}")"
  if [ ! -s "${STACK_ENV}" ]; then
    # Random values for this throw-away copy only; the file sits in the git-ignored report folder.
    (
      umask 077
      cat > "${STACK_ENV}" << ENV
SCAN_RELEASE=${RELEASE}
SCAN_API_PORT=${SCAN_API_PORT:-18000}
SCAN_DB_PORT=${SCAN_DB_PORT:-15433}
SCAN_POSTGRES_DB=mdarix_scan_test
SCAN_POSTGRES_PASSWORD=scan-$(random_hex 18)
SCAN_FIXTURE_PASSWORD=ScanOnly-$(random_hex 9)-Aa1!
SCAN_RLS_SYSTEM_TOKEN=$(random_hex 32)
SCAN_MFA_KEY=$(random_key)
SCAN_CONNECTOR_KEY=$(random_key)
SCAN_OBJECT_KEY=$(random_key)
SCAN_SIGNING_SECRET=$(random_hex 32)
ENV
    )
  fi
  # The API runs as the least-privilege runtime role, as in production (row-level security applies).
  grep -q '^SCAN_RUNTIME_PASSWORD=' "${STACK_ENV}" || echo "SCAN_RUNTIME_PASSWORD=runtime-$(random_hex 18)" >> "${STACK_ENV}"
  docker image inspect "${API_IMAGE}" > /dev/null 2>&1 || compose_scan build scan-seed > "${REPORTS}/stack-build.log" 2>&1
  if compose_scan up -d --wait --wait-timeout 1200 scan-api > "${REPORTS}/stack-up.log" 2>&1; then
    record stack-up ran "local test copy on 127.0.0.1:${SCAN_API_PORT:-18000}, project ${SCAN_PROJECT}"
  else
    compose_scan logs --no-color scan-seed scan-api > "${REPORTS}/stack-logs.log" 2>&1
    record stack-up failed "see stack-up.log and stack-logs.log"
    return 1
  fi
}

stack_stop() {
  [ -s "${STACK_ENV}" ] || return 0
  compose_scan stop > "${REPORTS}/stack-stop.log" 2>&1 && record stack-stop ran "docker compose stop (nothing removed)"
}

# ---- attack-style checks, local test copy only ---------------------------------------------------------------------
# Unless an auth header was given, sign in a synthetic Investigator of the scan copy (fixture user; its random password
# is in scan.env) so the API scans also reach signed-in routes. The session cookie is never printed. Requests that
# would end or change that session are left out of the API scans (AUTH_EXCLUDE).
AUTH_EXCLUDE='/api/v1/auth/(signout|session|change-password|mfa/)'
SCAN_OWN_SESSION=0
scan_auth() {
  # A fresh session for each tool: an earlier tool's session may have expired (idle limit) or been ended by its requests.
  if [ ${SCAN_OWN_SESSION} -eq 0 ] && [ -n "${ZAP_AUTH_HEADER_VALUE:-}" ]; then
    SCAN_AUTH_NOTE="authenticated (${ZAP_AUTH_HEADER:-Authorization} header)"
    return 0
  fi
  SCAN_AUTH_NOTE="unauthenticated"
  unset ZAP_AUTH_HEADER ZAP_AUTH_HEADER_VALUE
  [ -s "${STACK_ENV}" ] || return 0
  local jar="${REPORTS_REL}/stack/session.cookies" body="${REPORTS_REL}/stack/signin.json" password port token
  password="$(sed -n 's/^SCAN_FIXTURE_PASSWORD=//p' "${STACK_ENV}")"
  port="$(sed -n 's/^SCAN_API_PORT=//p' "${STACK_ENV}")"
  (umask 077 && printf '{"email":"%s","password":"%s"}' "${SCAN_USER:-r1-user-02@synthetic.invalid}" "${password}" > "${body}")
  curl -s -o /dev/null -c "${jar}" -H 'Content-Type: application/json' --data-binary "@${body}" \
    "http://127.0.0.1:${port}/api/v1/auth/signin"
  rm -f "${body}"
  token="$(awk '$6 == "mdarix_session" {print $7}' "${jar}" 2> /dev/null)"
  if [ -n "${token}" ]; then
    export ZAP_AUTH_HEADER=Cookie ZAP_AUTH_HEADER_VALUE="mdarix_session=${token}"
    SCAN_OWN_SESSION=1
    SCAN_AUTH_NOTE="signed in as a synthetic Investigator"
  fi
}

run_zap_baseline() {
  assert_local_target "${SCAN_TARGET}"
  mkdir -p "${REPORTS}/zap" && chmod 777 "${REPORTS}/zap" 2> /dev/null
  docker run --rm --network "${SCAN_NETWORK}" -v "${REPORTS_HOST}/zap:/zap/wrk:rw" "${IMG_ZAP}" \
    zap-baseline.py -t "${SCAN_TARGET}" -J zap-baseline.json -r zap-baseline.html -I -s > "${REPORTS}/zap-baseline.log" 2>&1
  local rc=$?
  if [ -s "${REPORTS}/zap/zap-baseline.json" ]; then record zap-baseline ran "passive scan of ${SCAN_TARGET}"; else record zap-baseline failed "exit ${rc}, see zap-baseline.log"; fi
}

run_zap_api() {
  assert_local_target "${SCAN_TARGET}/openapi.json"
  mkdir -p "${REPORTS}/zap" && chmod 777 "${REPORTS}/zap" 2> /dev/null
  scan_auth
  local auth=()
  if [ -n "${ZAP_AUTH_HEADER_VALUE:-}" ]; then
    auth=(-e "ZAP_AUTH_HEADER=${ZAP_AUTH_HEADER:-Authorization}" -e ZAP_AUTH_HEADER_VALUE -e ZAP_AUTH_HEADER_SITE=scan-api)
  fi
  docker run --rm --network "${SCAN_NETWORK}" -v "${REPORTS_HOST}/zap:/zap/wrk:rw" "${auth[@]}" "${IMG_ZAP}" \
    zap-api-scan.py -t "${SCAN_TARGET}/openapi.json" -f openapi -J zap-api.json -r zap-api.html -I -s \
    -z "-config scanner.maxScanDurationInMins=${ZAP_MAX_MINUTES:-30} -config globalexcludeurl.url_list.url(0).regex=.*${AUTH_EXCLUDE}.* -config globalexcludeurl.url_list.url(0).enabled=true -config globalexcludeurl.url_list.url(0).description=keep-session" \
    > "${REPORTS}/zap-api.log" 2>&1
  local rc=$?
  if [ -s "${REPORTS}/zap/zap-api.json" ]; then record zap-api ran "active API scan from the OpenAPI file, ${SCAN_AUTH_NOTE}"; else record zap-api failed "exit ${rc}, see zap-api.log"; fi
}

run_schemathesis() {
  assert_local_target "${SCAN_TARGET}/openapi.json"
  mkdir -p "${REPORTS}/schemathesis" && chmod 777 "${REPORTS}/schemathesis" 2> /dev/null
  scan_auth
  local auth=()
  [ -n "${ZAP_AUTH_HEADER_VALUE:-}" ] && auth=(-H "${ZAP_AUTH_HEADER:-Authorization}: ${ZAP_AUTH_HEADER_VALUE}")
  docker run --rm --network "${SCAN_NETWORK}" -v "${REPORTS_HOST}/schemathesis:/out" "${IMG_SCHEMATHESIS}" \
    run "${SCAN_TARGET}/openapi.json" --checks all --max-examples "${SCHEMATHESIS_MAX_EXAMPLES:-10}" --request-timeout 30 \
    --exclude-path-regex "^${AUTH_EXCLUDE}" --report junit --report-dir /out --no-color "${auth[@]}" \
    > "${REPORTS}/schemathesis.log" 2>&1
  local rc=$?
  if ls "${REPORTS}"/schemathesis/*.xml > /dev/null 2>&1; then record schemathesis ran "exit ${rc}, ${SCAN_AUTH_NOTE}"; else record schemathesis failed "exit ${rc}, see schemathesis.log"; fi
}

run_nuclei() {
  assert_local_target "${SCAN_TARGET}"
  mkdir -p "${REPORTS}/nuclei" && chmod 777 "${REPORTS}/nuclei" 2> /dev/null
  # Download or refresh the community templates (from the template project on GitHub) into a named volume first.
  docker run --rm -v mdarix-scan-nuclei-templates:/root/nuclei-templates "${IMG_NUCLEI}" -ut -duc \
    > "${REPORTS}/nuclei-templates.log" 2>&1
  # -ni: no out-of-band interaction server, so no request leaves the machine to a third-party callback host.
  docker run --rm --network "${SCAN_NETWORK}" -v mdarix-scan-nuclei-templates:/root/nuclei-templates \
    -v "${REPORTS_HOST}/nuclei:/out" "${IMG_NUCLEI}" -u "${SCAN_TARGET}" -ni -duc -silent -etags dos \
    -rate-limit 50 -jsonl -o /out/nuclei.jsonl > "${REPORTS}/nuclei.log" 2>&1
  local rc=$?
  if [ ${rc} -eq 0 ]; then touch "${REPORTS}/nuclei/nuclei.jsonl"; record nuclei ran "community templates, dos excluded"; else record nuclei failed "exit ${rc}, see nuclei.log"; fi
}

run_cross_tenant() {
  [ -s "${STACK_ENV}" ] || { record cross-tenant skipped "the local test copy was never started"; return; }
  local py
  py="$(pick_python)" || { record cross-tenant skipped "no Python found (set PYTHON)"; return; }
  # The existing cross-tenant suite, against the scan copy's database (never mdarix_r1 or a shared *_test database).
  (
    set -a
    # shellcheck disable=SC1090
    . "${STACK_ENV}"
    set +a
    export POSTGRES_HOST=127.0.0.1 POSTGRES_PORT="${SCAN_DB_PORT}" POSTGRES_DB="${SCAN_POSTGRES_DB}" \
      POSTGRES_USER=mdarix_app POSTGRES_PASSWORD="${SCAN_POSTGRES_PASSWORD}" MDARIX_RLS_SYSTEM_TOKEN="${SCAN_RLS_SYSTEM_TOKEN}" \
      MDARIX_MFA_ENCRYPTION_KEY="${SCAN_MFA_KEY}" MDARIX_CONNECTOR_ENCRYPTION_KEY="${SCAN_CONNECTOR_KEY}" \
      MDARIX_OBJECT_STORAGE_ENCRYPTION_KEY="${SCAN_OBJECT_KEY}" MDARIX_OBJECT_STORAGE_SIGNING_SECRET="${SCAN_SIGNING_SECRET}" \
      MDARIX_DB_RUNTIME_USER=mdarix_runtime MDARIX_DB_RUNTIME_PASSWORD="${SCAN_RUNTIME_PASSWORD}"
    # Every tests/test_cross_tenant*.py (the runtime-role suite too, once merged) plus the tenant isolation suites.
    "${py}" -m pytest -q -p no:cacheprovider tests/test_cross_tenant*.py tests/test_tenant_security.py \
      tests/test_tenant_data.py tests/test_rls_coverage.py tests/test_outbox_payload_tenant.py \
      --junitxml "${REPORTS_REL}/cross-tenant.xml"
  ) > "${REPORTS}/cross-tenant.log" 2>&1
  local rc=$?
  if [ -s "${REPORTS}/cross-tenant.xml" ]; then record cross-tenant ran "pytest exit ${rc}: $(tail -1 "${REPORTS}/cross-tenant.log")"; else record cross-tenant failed "exit ${rc}, see cross-tenant.log"; fi
}

# ---- read-only checks of the public site (mdarix.com only) ---------------------------------------------------------
run_testssl() {
  mkdir -p "${REPORTS}/testssl" && chmod 777 "${REPORTS}/testssl" 2> /dev/null
  rm -f "${REPORTS}/testssl/testssl.json"
  docker run --rm -v "${REPORTS_HOST}/testssl:/out" "${IMG_TESTSSL}" --quiet --warnings off --color 0 \
    --jsonfile /out/testssl.json "https://${PUBLIC_HOST}" > "${REPORTS}/testssl.log" 2>&1
  local rc=$?
  if [ -s "${REPORTS}/testssl/testssl.json" ]; then record testssl ran "https://${PUBLIC_HOST}, read-only"; else record testssl failed "exit ${rc}, see testssl.log"; fi
}

run_observatory() {
  # Mozilla's service fetches the home page and reads its headers; this machine sends nothing to mdarix.com.
  if curl -sS -X POST --max-time 120 "https://observatory-api.mdn.mozilla.net/api/v2/scan?host=${PUBLIC_HOST}" \
    -o "${REPORTS}/observatory.json" 2> "${REPORTS}/observatory.log" && grep -q '"grade"' "${REPORTS}/observatory.json"; then
    record observatory ran "${PUBLIC_HOST}, read-only"
  else
    record observatory failed "see observatory.log"
  fi
}

run_summary() {
  local py
  py="$(pick_python)" || die "no Python found for the summary (set PYTHON)"
  "${py}" -I scripts/security_scan_summary.py "${REPORTS_REL}" --allowlist "${ALLOWLIST}" \
    --release "${RELEASE}" && echo "Summary: ${REPORTS}/SUMMARY.md"
}

# ---- step runner ---------------------------------------------------------------------------------------------------
expand() {
  case "$1" in
    all) expand static; expand dynamic; expand public; echo summary ;;
    static) echo semgrep bandit pip-audit npm-audit gitleaks trivy ;;
    dynamic) echo stack-up zap-baseline zap-api schemathesis nuclei cross-tenant stack-stop ;;
    public) echo testssl observatory ;;
    *) echo "$1" ;;
  esac
}

PLAN=()
for step in "${STEPS[@]}"; do
  for s in $(expand "${step}"); do PLAN+=("${s}"); done
done
echo "Release ${RELEASE}; reports in ${REPORTS}; steps: ${PLAN[*]}"
STACK_OK=1
for step in "${PLAN[@]}"; do
  case "${step}" in
    semgrep) run_semgrep ;;
    bandit) run_bandit ;;
    pip-audit) run_pip_audit ;;
    npm-audit) run_npm_audit ;;
    gitleaks) run_gitleaks ;;
    trivy) run_trivy ;;
    stack-up) stack_up || STACK_OK=0 ;;
    zap-baseline | zap-api | schemathesis | nuclei)
      if [ ${STACK_OK} -eq 0 ]; then record "${step}" skipped "the local test copy did not start"; continue; fi
      case "${step}" in
        zap-baseline) run_zap_baseline ;;
        zap-api) run_zap_api ;;
        schemathesis) run_schemathesis ;;
        nuclei) run_nuclei ;;
      esac
      ;;
    cross-tenant) run_cross_tenant ;;
    stack-stop) stack_stop ;;
    testssl) run_testssl ;;
    observatory) run_observatory ;;
    summary) run_summary ;;
    *) die "unknown step: ${step} (see --help)" ;;
  esac
done
