#!/bin/bash
# Register the Linux runner with the repository. Run as the runner user inside Ubuntu:
#   wsl -d Ubuntu -u runner -- env RUNNER_TOKEN=... bash infrastructure/ci/self-hosted/register-linux.sh
# RUNNER_TOKEN is a registration token (valid for one hour), obtained by a repository administrator with
#   gh api -X POST repos/<owner>/<repo>/actions/runners/registration-token --jq .token
# The label mdarix-linux is what the CI_LINUX_RUNNER repository variable points at.
set -euo pipefail
: "${RUNNER_TOKEN:?set RUNNER_TOKEN}"
REPO_URL="${REPO_URL:-https://github.com/stelikicherla-stack/MDARIX-R1}"
cd /home/runner/actions-runner
./config.sh --unattended --url "$REPO_URL" --token "$RUNNER_TOKEN" \
  --name "$(hostname)-linux" --labels mdarix-linux --work _work --replace
echo "REGISTERED $(hostname)-linux"
