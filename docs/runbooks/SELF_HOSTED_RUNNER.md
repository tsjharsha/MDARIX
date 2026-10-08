# Self-hosted CI runners on a developer PC

GitHub-hosted runners stop when the account's Actions allowance is used up or a payment fails ("The job was not
started because recent account payments have failed or your spending limit needs to be increased"). This runbook
puts the same CI on a Windows PC: the Linux jobs run in an Ubuntu WSL distribution that uses Docker Desktop's engine,
the frontend job runs on Windows. Nothing in the workflows changes except where each job runs: every `runs-on` reads
the repository variables `CI_LINUX_RUNNER` and `CI_WINDOWS_RUNNER`, and falls back to GitHub's `ubuntu-latest` and
`windows-latest` when they are unset.

## What this PC must have

| Need | Why |
|---|---|
| Windows 11 with WSL 2 and Docker Desktop | Linux jobs, service containers, image builds and scans |
| 8 GB RAM or more, 15 GB free disk or more | One job at a time fits in 8 GB; the images, tool caches and the Ubuntu distribution take 6-8 GB over time |
| The PC switched on and signed in while CI runs | The runners are started by a logon task |
| **The development stack stopped during a CI run** | CI binds the same host ports (5432, 5433, 5541-5544, 8025, 8101-8104, 8000, 8007) as `docker-compose.yml` and the local servers |

## One-time setup (about 20 minutes)

1. **Install Ubuntu into WSL** (no window opens): `wsl --install -d Ubuntu --no-launch`
2. **Prepare it** (packages, the `runner` user with password-less sudo for jobs that use apt, the runner package with
   its checksum verified, `COMPOSE_PROJECT_NAME=ci` so CI never touches the developer's compose containers):
   `wsl -d Ubuntu -u root -- bash /mnt/c/Users/<you>/Srinivas/MDARIX-R1/infrastructure/ci/self-hosted/ubuntu-bootstrap.sh`
   It prints `BOOTSTRAP_OK <runner version>`.
3. **Give Ubuntu the Docker engine:** Docker Desktop → Settings → Resources → WSL integration → switch on **Ubuntu** →
   Apply & restart. Check from Ubuntu: `wsl -d Ubuntu -u runner -- docker ps` lists the containers.
   (Docker Desktop's restart stops containers whose restart policy is `no`; start the development stack again
   afterwards with `docker compose up -d` if it is needed.)
4. **Windows runner package (optional):** download `actions-runner-win-x64-<version>.zip` from
   https://github.com/actions/runner/releases, check its SHA-256 against the release notes, and unpack it into
   `C:\actions-runner`.
5. **Register both runners.** A repository administrator gets a registration token (valid one hour, used once):
   `gh api -X POST repos/stelikicherla-stack/MDARIX-R1/actions/runners/registration-token --jq .token`
   then
   `wsl -d Ubuntu -u runner -- env RUNNER_TOKEN=<token> bash /mnt/c/.../infrastructure/ci/self-hosted/register-linux.sh`
   and, with a second token, in PowerShell:
   `$env:RUNNER_TOKEN='<token>'; .\infrastructure\ci\self-hosted\register-windows.ps1`
   The runners appear under Settings → Actions → Runners with the labels `mdarix-linux` and `mdarix-windows`.
6. **Start them, now and at every sign-in:** run `infrastructure\ci\self-hosted\start-runners.ps1` once, and create the
   logon task shown in its header comment.
7. **Point CI at them:**
   `gh variable set CI_LINUX_RUNNER --body mdarix-linux` and `gh variable set CI_WINDOWS_RUNNER --body mdarix-windows`.
   From the next push every job, including CodeQL, runs on this PC. CodeQL follows `CI_LINUX_RUNNER` and falls back
   to GitHub's Ubuntu runner only when that variable is unset.

   If Windows Application Control does not permit the Windows runner, use the Linux runner for the frontend job as
   well: `gh variable set CI_WINDOWS_RUNNER --body mdarix-linux`. The frontend commands are deliberately
   cross-platform, so this does not reduce the test coverage. CodeQL also honors `CI_LINUX_RUNNER`, avoiding a
   GitHub-hosted billing dependency.

## Before each CI run

Stop the development stack and the local servers, or the jobs fail on their ports:
`docker compose stop` in the repository root, plus any other container on 5432 (`docker stop mdarix-postgres`) and the
local uvicorn (8007) and Vite (5177) processes. Start them again afterwards with `docker compose start`.

## Going back to GitHub's runners

`gh variable delete CI_LINUX_RUNNER` and `gh variable delete CI_WINDOWS_RUNNER`. The runners can stay registered;
idle runners cost nothing. To remove one: `./config.sh remove --token <removal token>` in its folder.

## Known limits

- One Linux job at a time (one runner). A full pipeline takes roughly 60-90 minutes on an 8 GB PC. Register a second
  Linux runner (another folder, another registration) only on a machine with 16 GB or more.
- The `prod-stack` job builds every production image and starts ClamAV; it is the heaviest job and the first to suffer
  when RAM or disk is short. `docker builder prune` reclaims build cache when disk runs low.
- Bind mounts from the Ubuntu distribution into containers (the TLS certificates, the backup keys, the Docker socket
  for the image scan) rely on Docker Desktop's WSL integration being switched on for Ubuntu (step 3).
- Secrets: a self-hosted runner on a private repository runs only this repository's workflows; pull requests from
  forks do not run on it. Keep it that way (Settings → Actions → General).
