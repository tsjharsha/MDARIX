#!/bin/bash
# Prepare an Ubuntu WSL distribution to host the Linux GitHub Actions runner for this repository.
# Run as root inside the distribution:  wsl -d Ubuntu -u root -- bash infrastructure/ci/self-hosted/ubuntu-bootstrap.sh
# Idempotent: safe to run again. See docs/runbooks/SELF_HOSTED_RUNNER.md.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
RUNNER_VERSION="${RUNNER_VERSION:-2.338.0}"
# Published with the release: https://github.com/actions/runner/releases/tag/v${RUNNER_VERSION}
RUNNER_SHA256="${RUNNER_SHA256:-af4b794c1bc41d73d40535e3fe092a39f9679cd8d965954c2aca25a05ca41d32}"

apt-get update -q
apt-get install -y -q curl ca-certificates git jq sudo tar unzip openssl

# The runner never runs as root. Jobs use sudo for apt (Playwright's browser dependencies, the TLS certificate owner).
if ! id runner >/dev/null 2>&1; then
  useradd -m -s /bin/bash runner
fi
echo 'runner ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/runner
chmod 440 /etc/sudoers.d/runner
# Docker Desktop's WSL integration gives this group the engine socket.
groupadd -f docker
usermod -aG docker runner

cat > /etc/wsl.conf <<'EOF'
[user]
default=runner
[boot]
systemd=false
EOF

install -d -o runner -g runner /home/runner/actions-runner
cd /home/runner/actions-runner
if [ ! -x ./run.sh ]; then
  curl -fsSL -o runner.tar.gz "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
  echo "${RUNNER_SHA256}  runner.tar.gz" | sha256sum -c -
  tar xzf runner.tar.gz
  rm runner.tar.gz
fi
# CI jobs that start docker-compose.yml services get their own project, so they never touch the developer's
# containers or volumes of the same compose file (they still need the developer's stack stopped: same host ports).
echo 'COMPOSE_PROJECT_NAME=ci' > .env
chown -R runner:runner /home/runner/actions-runner
./bin/installdependencies.sh >/dev/null
echo "BOOTSTRAP_OK $(./bin/Runner.Listener --version)"
