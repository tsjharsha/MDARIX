# Release 0.11.05 on production (mdarix.com): trial AI

Planned for 18 Nov 2026 (owner's go given on 17 Nov). Release 0.11.05 is the WHIF release: push 2 (trial AI chain,
loopback forwarders, `tr19`..`tr32` migrations) and the trial 2 line. AI goes ON only for the owner's demo trial
organization, on sample data, through FreeLLMAPI -> OmniRoute -> Groq.

Production facts this runbook relies on (GCP_DEPLOYMENT.md, DEPLOYMENT.md, the 0.10.92 upgrade script): VM
`mdarix-prod`, zone `asia-south1-a`, SSH only through IAP; checkout `/home/deploy/mdarix`, run as `deploy`; compose
files `docker-compose.prod.yml:docker-compose.staging-oracle.yml` with `.env.production` (exported in deploy's
`~/.profile`); PostgreSQL in the `postgres` service, database `mdarix`; the VM builds its own images
(`MDARIX_PUBLISH_IMAGES` off); running release v0.10.92, schema `tr18changereason`. The owner confirms each before
step 0 (the last section lists them).

**Who and what.** OWNER = Srinivas. CLAUDE = Claude, only through the owner's own terminal session and only after he
lifts the production pause for this release; otherwise the OWNER runs that step and pastes the output. READ-ONLY steps
change nothing; WRITES steps change the server.

Shorthands on the server (as `deploy`, in `~/mdarix`, after `sudo -iu deploy` so `~/.profile` is read):

```bash
cd ~/mdarix
dc() { docker compose "$@"; }                          # COMPOSE_FILE / COMPOSE_ENV_FILES come from ~/.profile
ro() { docker compose exec -T -u postgres -e PGOPTIONS='-c default_transaction_read_only=on' postgres \
         psql -X -A -v ON_ERROR_STOP=1 -d mdarix -c "$1"; }      # read-only SQL as the database's own superuser
```

Copy the two server scripts to the VM once (from the laptop, in the repository at this release):

```bash
gcloud compute scp scripts/install_trial_ai_gateways.sh scripts/enter_trial_ai_keys.sh mdarix-prod:/tmp/ \
  --zone asia-south1-a --tunnel-through-iap
```

## Checklist

| # | Step | Who | Kind |
|---|---|---|---|
| 0.1 | Owner's go recorded for this window | OWNER | - |
| 0.2 | Disk at least 8 GB free on `/`; memory headroom | CLAUDE | READ-ONLY |
| 0.3 | Release and Alembic revision check: must be v0.10.92 and `tr18changereason` | CLAUDE | READ-ONLY |
| 0.4 | Settings file copy `.env.production.pre-01105` | CLAUDE | WRITES (a copy) |
| 0.5 | Fresh backup, off-site copy, disk snapshot | OWNER | WRITES |
| 0.6 | Restore-verify the backup | OWNER + CLAUDE | READ-ONLY |
| 1 | Install FreeLLMAPI and OmniRoute (loopback), `--check` | CLAUDE | WRITES |
| 2 | Provider keys in both dashboards through an SSH tunnel; each gateway's access key | OWNER | WRITES (gateways only) |
| 3 | `enter_trial_ai_keys.sh` | OWNER | WRITES (settings file) |
| 4 | Check out v0.11.05 and build the images (nothing restarts) | CLAUDE | WRITES |
| 5 | **STOP: owner's OK**, then stop api and background, migrate, start | OWNER says go, CLAUDE runs | WRITES (database) |
| 6 | Refresh existing trials: dry run, owner's OK, apply | CLAUDE, OWNER decides | READ-ONLY, then WRITES |
| 7 | Smoke checks (outside and on the server) | CLAUDE + OWNER | READ-ONLY |
| 8 | AI on for the demo trial only; one Ask, one signal summary; usage check | OWNER | WRITES (one trial) |
| 9 | After recording: AI off; emergency off when needed | OWNER | WRITES |
| 10 | Rollback, only if needed | OWNER decides | WRITES |
| 11 | Old images removed by release name (after the release is accepted) | CLAUDE | WRITES |

## 0. Prerequisites

**0.1 (OWNER)** Give the go for this window, in writing, in the release thread. Nobody else is deploying.

**0.2 (CLAUDE, READ-ONLY)** The 0.10.47 build stopped on a full disk; a build needs at least 8 GB free.

```bash
df -hP / && df -Pk / | awk 'NR==2 { exit ($4 >= 8*1024*1024) ? 0 : 1 }' && echo DISK=OK || echo DISK=STOP
free -m          # the gateways may use up to 1.5 GB (unit limits) on top of the 5.25 GB compose limits and PostgreSQL
```

`DISK=STOP`: free space first (old `mdarix/*:v*` images other than v0.10.92, `docker builder prune`), never by
deleting backups. The gateways take about 1-2 GB on disk in step 1, so step 4 checks 8 GB again.

**0.3 (CLAUDE, READ-ONLY)** The running release and the database revision.

```bash
git -C ~/mdarix describe --tags --exact-match; grep -E '^MDARIX_RELEASE=' ~/mdarix/.env.production
ro "SELECT version_num FROM alembic_version;"
```

Expected: `v0.10.92`, `MDARIX_RELEASE=v0.10.92`, and exactly one row `tr18changereason`. If the revision is
`md64mergetrialtr18`, anything else, or more than one row: **STOP**, change nothing and tell the owner (0.11.05's
migrations were tested from `tr18changereason` only).

**0.4 (CLAUDE, WRITES a copy)** Keep the settings exactly as they are now; every rollback restores this copy.

```bash
cd ~/mdarix && [ -e .env.production.pre-01105 ] || cp -p .env.production .env.production.pre-01105; ls -l .env.production*
```

**0.5 (OWNER, WRITES)** A fresh backup on the running release, copied off-site at once, and a disk snapshot (the
quickest whole-server way back):

```bash
dc --profile backup run --rm backup; echo BACKUP=$?                       # on the VM, as deploy; must be 0
sudo /snap/bin/gcloud storage rsync --recursive /var/backups/mdarix gs://<PROJECT>-mdarix-backups/prod   # on the VM
```

```bash
# on the laptop
gcloud compute disks snapshot mdarix-prod --zone=asia-south1-a --snapshot-names=mdarix-pre-01105-$(date -u +%Y%m%d) \
  --storage-location=asia-south1
```

**0.6 (OWNER + CLAUDE, READ-ONLY) Restore-verify.** On the VM:

```bash
B=$(sudo ls -1 /var/backups/mdarix | tail -n 1); echo "$B"           # the folder just written (UTC timestamp)
sudo sh -c "cd /var/backups/mdarix/$B && sha256sum -c MANIFEST.sha256"   # every line OK
sudo ls -l /var/backups/mdarix/$B                                      # dump size close to the previous backups
gcloud storage ls -l gs://<PROJECT>-mdarix-backups/prod/$B/            # the off-site copy is there
```

Every manifest line `OK`, the size in line with the last backups (about 12 MB on 5 Nov), the off-site listing
present. A full restore needs the private `age` key, which never goes on the server: the owner decides whether to run
the restore drill of BACKUP_AND_RESTORE.md section 2 on his laptop now (7 min 19 s on 3 Nov) or rely on the manifest,
the off-site copy and the disk snapshot for this release. Record the choice.

## 1. Install FreeLLMAPI and OmniRoute on the VM (CLAUDE, WRITES)

What is installed (`scripts/install_trial_ai_gateways.sh`):

- **Node.js 24.15.0** (the laptop's version) in `/opt/mdarix-ai`, checked against nodejs.org's SHA-256 list.
- **FreeLLMAPI** at the laptop's commit `5127fee5` (tag v0.16.14), built with `npm ci` and `npm run build`.
- **OmniRoute 3.8.52**, exact version, with only its README's install-script allowlist.
- Two systemd services, `mdarix-freellmapi` (`HOST=127.0.0.1`, port 3011) and `mdarix-omniroute`
  (`OMNIROUTE_SERVER_HOST=127.0.0.1`, port 20128, access key required, cloud sync and telemetry off). Both run as
  the unprivileged user `mdarix-gw`, with write access only to their own folders and memory limits of 512 MB and
  1 GB.
- The `ufw` rule that lets only the `mdarix-ai` bridge reach `10.99.211.1:3011,20128`.

The host forwarder is push 2's compose service `ai-host-bridge`, not a systemd unit. It starts with release 0.11.05
in step 5 and listens only on `10.99.211.1`, the gateway of the `ai-host` bridge. A second forwarder here would
compete for the same address.

```bash
sudo bash /tmp/install_trial_ai_gateways.sh          # as the owner's sudo user; ends with CHECK=PASS
sudo ss -ltnp | grep -E ':(3011|20128|2013[0-9])\b'  # only 127.0.0.1 (10.99.211.1 appears after step 5)
sudo ss -ltnp | grep -E '0\.0\.0\.0:(3011|20128)|\[::\]:(3011|20128)|\*:(3011|20128)' && echo EXPOSED || echo NOT_EXPOSED
```

Expected: `CHECK=PASS`, `NOT_EXPOSED`. The run is idempotent: run it again to repair, or `--check` to verify only.

> **OmniRoute 3.8.52 carries a critical vulnerability** (Next.js remote code execution through its image API, from
> the laptop's `npm audit` on 17 Nov) and a critical DOMPurify flaw. Loopback binding is the control. **Never** bind it
> to `0.0.0.0`, open 20128 in ufw or the cloud firewall, put it behind Caddy, a tunnel service, ngrok or a port
> forward other than the owner's own SSH tunnel in step 2. Re-check when a release at least two weeks old ships
> Next.js 16.4.5 or later.

## 2. Provider keys in the dashboards (OWNER, WRITES in the gateways only)

From the laptop. Stop the laptop's own FreeLLMAPI and OmniRoute first, because they use the same local ports:

```bash
gcloud compute ssh mdarix-prod --zone asia-south1-a --tunnel-through-iap -- -L 3011:127.0.0.1:3011 -L 20128:127.0.0.1:20128
```

Keep that window open. While it is open:

1. **FreeLLMAPI**: open `http://127.0.0.1:3011`. Add the **Cloudflare** Workers AI key only. Create MDARIX's access
   key, scoped to the vetted models if the screen allows. Store it in KeePassXC.
2. **OmniRoute**: open `http://127.0.0.1:20128`. Set the dashboard password on first login. Add **Groq** and
   **Cloudflare** Workers AI only. Create one combo named **`mdarix-trial`**: the Groq model first, then Cloudflare.
   Create one access key (API Keys page), limited to that combo if possible. Store it in KeePassXC. Leave telemetry,
   Radar, cloud sync, tunnels and remote access off.
3. **OpenRouter is skipped** (owner decision). The register's OpenRouter row allows no model.

Close the tunnel when done.

## 3. Enter the keys (OWNER, WRITES the settings file)

```bash
sudo -u deploy -H bash /tmp/enter_trial_ai_keys.sh          # default file /home/deploy/mdarix/.env.production
```

It asks without echo for the FreeLLMAPI key, the OmniRoute key and the Groq key (empty answer = keep the current
value). It then sets these settings:

- `MDARIX_GENAI_FREELLMAPI_API_KEY`, `MDARIX_GENAI_OMNIROUTE_API_KEY`, `MDARIX_GENAI_GROQ_API_KEY`;
- `MDARIX_GENAI_OMNIROUTE_MODEL=mdarix-trial`;
- `MDARIX_AI_TRIAL_CHAIN=freellmapi,omniroute,groq`;
- `MDARIX_AI_FEATURES=ask,summaries,case_analysis,drafting,evidence_extraction,code_suggestions` (every feature
  `genai/features.py` offers; `decision_advisory` and `regulatory_drafting` are not offered).

It keeps `.env.production.pre-trial-ai-<UTC time>` (mode 600), replaces the file atomically (mode 600) and prints
only `set` or `unchanged` for each setting. Nothing reads the file until step 5, and no organization has AI switched
on, so these settings call no model before step 8.

## 4. Deploy the 0.11.05 images (CLAUDE, WRITES; the running services are not touched)

The tag `v0.11.05` must be on GitHub (the owner pushes it). A build does not restart containers.

```bash
cd ~/mdarix
df -Pk / | awk 'NR==2 { exit ($4 >= 8*1024*1024) ? 0 : 1 }' || { echo "STOP: under 8 GB free"; false; }
git fetch -q --tags && git rev-parse -q --verify refs/tags/v0.11.05 && git status --porcelain   # tag found, tree clean
git -c advice.detachedHead=false checkout -q v0.11.05 && cat VERSION                            # 0.11.05
sed -i 's|^MDARIX_RELEASE=.*|MDARIX_RELEASE=v0.11.05|' .env.production
(dc build && dc --profile backup build backup) > ~/build-01105.log 2>&1; echo BUILD=$?; tail -n 5 ~/build-01105.log
dc run --rm --no-deps api python -m backend.app.config_check --offline; echo CONFIG=$?           # prints nothing, 0
dc run --rm --no-deps api python -c "import backend.app.main"; echo IMPORT=$?                  # the API starts: 0
```

If the build, the offline check or the import fails, follow rollback **A** (0.11.05's first build passed the offline
check but its API did not start: the offline check does not import the API). The old release keeps serving.

## 5. Migrations (STOP: the OWNER says go; CLAUDE runs; WRITES the database)

**Ask the owner now and wait for his explicit OK.** The migrations go from `tr18changereason` to `tr32aiready`.
`tr23compositetenantfks` validates about 50 composite references in one transaction and makes writes to the
organization tables wait until it commits, so the API and the background service are stopped first. Expected time:
about 1 s for tr23 on 2,000 rows (measured 17 Nov). The whole migrate job (Alembic start, 15 migrations, roles,
grants) should take 1-3 minutes on production's size, which was not measured. The API is down for that time: the site
pages still load, while sign-in and the app return errors. Plan a 15-minute window at a quiet hour.

```bash
dc stop api background ai-loopback-api ai-loopback-background
time dc up -d --no-build --wait; echo UP=$?
dc ps -a                                                # migrate "Exited (0)"; api, background healthy; ai-* running
dc logs --no-log-prefix migrate | tail -n 20
ro "SELECT version_num FROM alembic_version;"           # tr32aiready
dc exec -T api python scripts/deploy_gate.py --release v0.11.05 --timeout 180 --require worker,scheduler   # DEPLOY_GATE=PASS
sudo bash /tmp/install_trial_ai_gateways.sh --check     # now also shows the forwarder on 10.99.211.1
```

Interrupted or failed migrate (`UP` not 0, `migrate` exit not 0): api and background do not start (they wait for
migrate). Read the revision and follow rollback **B**.

## 6. Refresh the existing trials (CLAUDE runs, the OWNER decides)

```bash
dc exec -T api python scripts/refresh_trial_story.py --counts      # READ-ONLY dry run: what would be added, per trial
```

Show the output to the owner. **Only with his OK:**

```bash
dc exec -T api python scripts/refresh_trial_story.py --apply       # WRITES sample records; each trial in its own commit
```

## 7. Smoke checks (READ-ONLY)

From outside (the laptop):

```bash
curl -fsS https://mdarix.com/health/status                          # {"status":"ok"} (or "degraded"), HTTP 200
curl -fsS https://mdarix.com/api/v1/public/version                  # 0.11.05
curl -s -o /dev/null -w '%{http_code}\n' https://mdarix.com/health/ready     # 404: readiness is not public
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' https://mdarix.in/health/live   # 301 to mdarix.com
```

On the server, readiness with its `trial_ai_chain` item and the gateways seen from inside the API container:

```bash
dc exec -T api python -c "from backend.app.readiness import readiness_report as r; import json; print(json.dumps(r(), indent=1))"
dc exec -T api python -c "
import urllib.error, urllib.request
for port in (3011, 20128):
    try:
        status = urllib.request.urlopen(f'http://127.0.0.1:{port}/v1/models', timeout=5).status
    except urllib.error.HTTPError as error:
        status = error.code
    print(port, status)"
```

Expected: status `ready`. `trial_ai_chain` has `state: ON`, `freellmapi` and `omniroute` usable and `reachable: true`,
none resting, and the six features. Both ports answer with any HTTP status (401 included). `trial_ai_chain` never
changes the overall status.

In the browser (OWNER):

- Sign in on `https://mdarix.com` as the Platform Administrator, with MFA.
- Open the demo trial. Its story loads: Getting started, the flagship case, and Complaints with the sample.

No e-mail storm (CLAUDE). Compare with the hour before the release, then again 30 minutes later:

```bash
ro "SELECT event_name, count(*) FROM event_outbox WHERE occurred_at > now() - interval '30 minutes' GROUP BY 1 ORDER BY 2 DESC;"
ro "SELECT count(*) AS unsent FROM event_outbox WHERE published_at IS NULL AND dead_lettered_at IS NULL;"
```

A few events are normal. Hundreds of e-mail events, or an unsent count that keeps growing, is a storm: stop
`background` (`dc stop background`; nothing is lost, the events wait in the outbox) and tell the owner. The owner
also checks the ZeptoMail sent count for the last hour.

## 8. AI on for the demo trial only (OWNER, WRITES for one organization)

1. **Platform Admin › Trial organizations › the demo trial › "AI for this trial"**. The gates read "Trial AI
   services: Ready" and "Organization: Not switched on".
2. As that trial's administrator: **Security › AI processing › Turn AI processing on**. Tick both acknowledgements
   (records may go to the provider shown; the trial acknowledgement: sample data only, free AI services, possibly
   outside India) and enter the password and authenticator code. Then turn on the features to demo (at least
   **Ask MDARIX** and **Summaries**), each with a reason.
3. Back in the AI panel: set each person's switch. **Active** only for the people who demo, each with a reason
   (audited `TRIAL_USER_AI_ACCESS_CHANGED`).
4. **One live Ask** on the sample case (a question under 300 characters). **One signal summary** on a sample signal.
   Each answer names its source records.
5. AI usage check (CLAUDE, READ-ONLY):

```bash
ro "SELECT created_at, feature, chain, provider, upstream_provider, upstream_model, outcome, input_tokens, output_tokens, latency_ms FROM ai_calls ORDER BY created_at DESC LIMIT 5;"
ro "SELECT t.name, c.organisation_type, count(*) FROM ai_calls c JOIN tenants t ON t.id = c.tenant_id WHERE c.created_at > now() - interval '1 day' GROUP BY 1, 2;"
ro "SELECT name, ai_features FROM tenants WHERE ai_processing_allowed ORDER BY name;"
```

Expected:

- Two calls, `chain = trial`, outcome `ANSWERED`, an upstream from the register (groq, cloudflare or cloudflare-ai);
- only the demo trial in the second query;
- the third query lists the demo trial and any paid organization that already had AI, and no other trial. The owner
  also sees the token use in the trial's AI panel (allowance 200,000 a month).

## 9. After recording: AI off, and the emergency off (OWNER, WRITES)

- **After recording.** Security › AI processing › **Turn AI processing off** for the demo trial. This takes effect
  at once: nothing more is sent. The settings may stay for the next demo.
- **Emergency off for every trial**, fastest first:
  1. In the UI, turn AI processing off for the trial or trials that have it (immediate).
  2. Empty the chain and recreate the two services. A plain `restart` does not re-read the settings file; `up` does:

     ```bash
     sed -i 's|^MDARIX_AI_TRIAL_CHAIN=.*|MDARIX_AI_TRIAL_CHAIN=|' ~/mdarix/.env.production
     dc up -d --no-build --wait api background
     dc up -d --force-recreate ai-loopback-api ai-loopback-background   # the sidecars follow the new containers
     ```

     A trial's switch-on is then refused with 409, and readiness shows `trial_ai_chain` `OFF`.
  3. Stop the gateways: `sudo systemctl stop mdarix-omniroute mdarix-freellmapi`. On its own this is **not** an off
     switch: Groq is called directly. Use it after 1 and 2, or when a gateway itself is the problem.

## 10. Rollback

**AI only (the release stays).** Step 9's emergency off. To also remove the keys, restore
`.env.production.pre-trial-ai-<time>` (`cp -p`), then run the same `up` and `--force-recreate` commands. Uninstalling
the gateways is not needed: stopped, they listen nowhere.

**A. Before step 5 (no migration ran).** Nothing in the database changed:

```bash
cd ~/mdarix && cp -p .env.production.pre-01105 .env.production && git -c advice.detachedHead=false checkout -q v0.10.92
dc ps    # the v0.10.92 containers kept running; if any was recreated: dc up -d --no-build --wait
```

**B. The migration failed or was interrupted.** Read the revision first:
`ro "SELECT version_num FROM alembic_version;"`.

- **`tr18changereason`** (the transaction rolled back): as A. The old release runs as before.
- **Between `tr19` and `tr32aiready`.** `tr24` builds indexes concurrently, so the migrations before it are
  committed. Find the cause in `dc logs migrate`.
  - If it is fixable now (for example a lock timeout), fix it and run `dc up -d --no-build --wait` again.
  - Otherwise go to C.

**C. Migrated, but 0.11.05 cannot serve.** v0.10.92 refuses to report ready on the newer schema (`SCHEMA_MISMATCH`),
so the schema must go back too. Decide by what was written since step 5:

1. **Nothing customer-made since step 5** (the usual case inside the window). Downgrade with 0.11.05's own migrate
   image, still checked out. This was tested on the 17 Nov copy of the 0.10.92 schema: every table's row count was
   identical after the downgrade.

   ```bash
   dc stop api background ai-loopback-api ai-loopback-background
   dc run --rm migrate alembic downgrade tr18changereason
   ```

   Then A (the old settings and v0.10.92), then `dc up -d --no-build --wait`. Rows written to the seven new tables
   are lost.
2. **Customer work since step 5, or the downgrade fails.** Restore. The owner decides:
   - the step 0.5 disk snapshot as a new boot disk (the whole VM back to before the release; GCP console: create a
     disk from the snapshot, stop the VM, swap the boot disk), or
   - the step 0.5 backup into the database (BACKUP_AND_RESTORE.md section 3; the private key comes from the laptop
     and is removed after use), then section 4, re-apply erasures, before anyone signs in.

   Either way, everything written since the backup is lost. Tell the trials affected.
3. Fixing forward (a 0.11.06) is often the smaller loss after the first hours. The owner weighs it against 2.

## 11. Old images (CLAUDE, WRITES; after the owner accepts the release)

By release name, never by date. Keep v0.11.05 and v0.10.92 (the rollback target), and any image a container uses:

```bash
in_use=$(docker ps -a --format '{{.Image}}' | sort -u)
for ref in $(docker images --format '{{.Repository}}:{{.Tag}}' | grep -E '^mdarix/(api|web|backup):v' | sort -u); do
  case "${ref#*:}" in v0.11.05 | v0.10.92) continue ;; esac
  printf '%s\n' "$in_use" | grep -qxF "$ref" || docker rmi "$ref"
done
docker image prune -f; docker builder prune -a -f --filter until=48h; df -hP /
```

## The owner confirms before step 0

- The settings file is `/home/deploy/mdarix/.env.production` (the default of `enter_trial_ai_keys.sh`). The compose
  files and `.env.production` are exported in deploy's `~/.profile`.
- The database is `mdarix`, in the `postgres` service.
- The deploy method is still the same as 0.10.92: tag checkout and a VM build (no pulled images).
- The tag `v0.11.05` will be pushed and contains this release.
- `ufw` is active on the VM.
- The VM has the memory for the gateways (`free -m`).
- The bucket name `<PROJECT>-mdarix-backups/prod`.
