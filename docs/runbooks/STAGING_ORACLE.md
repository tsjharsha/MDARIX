# Staging on Oracle Cloud Always Free

MDARIX staging runs on one Oracle Cloud "Always Free" ARM server at no cost (ADR-017). It is the production stack of
[DEPLOYMENT.md](DEPLOYMENT.md) with one layer on top, `docker-compose.staging-oracle.yml`, for what this server needs
differently:

| Production | Staging on Oracle | Why |
|---|---|---|
| Managed PostgreSQL with point-in-time recovery | Postgres in a container on the server, TLS only, private network only | Oracle's free tier has no managed PostgreSQL |
| `clamav/clamav` image | `clamav/clamav-debian` image | The first is published for x86 only; the server is ARM |
| Images pulled from the release registry | Images built on the server | Released images are x86 |
| Files in an S3 bucket | Files on the server's disk, encrypted (`MDARIX_OBJECT_STORAGE_PROVIDER=local`) | Staging holds no customer data |
| Backups and their heartbeat required | Not required (the configuration check applies them in production only) | Same |

**Staging never holds customer data.** Design-partner pilots run on Azure with a managed database (ADR-017).

What staging proves, with the steps in section 8:
1. HTTPS with a real certificate, and database TLS checked by name.
2. Uploaded files are virus-scanned, and infected files are refused.
3. Alerts and outside monitors reach a person.
4. Two application instances share one database: a session opened on one is valid on the other, and signing out on
   one ends it on both.

## 0. Before you start: the legal pages

A staging server runs every production check (`backend/app/config_check.py`), including the legal ones. It refuses to
start until `MDARIX_LEGAL_TEXT_APPROVED=true`, `MDARIX_COMPANY_LEGAL_NAME` and `MDARIX_COMPANY_ADDRESS` are set, and
`legal/privacy.md`, `terms.md` and `trial-agreement.md` read as final (no DRAFT banner, no `[PLACEHOLDER]`). Staging is
on the public internet, so it would publish those pages.

Until the lawyer-approved texts exist, staging runs as a **private staging server** (ADR-017, decided 2026-10-12):
Caddy asks for a login before every page and API call, so the draft legal pages and the empty company details reach
only the people given that login. Only `/health/live` and `/health/status` stay open, for the uptime monitors. The
configuration check then skips the legal checks, and only when all of these hold:

| Setting | Value |
|---|---|
| `MDARIX_ENV` | `staging` (production never gets the exemption) |
| `MDARIX_SITE_ACCESS` | `private` |
| `MDARIX_SITE_LOGIN_USER` | a user name for the testers, e.g. `staging` |
| `MDARIX_SITE_LOGIN_HASH` | the bcrypt hash of a long random password, **in single quotes** (it contains `$`) |
| `MDARIX_PRIVATE_STAGING_ACKNOWLEDGED` | `true` |

Make the hash on any machine with Docker, and keep the password in your password manager:

```bash
docker run --rm caddy:2.11-alpine caddy hash-password      # type the password twice; prints $2a$14$...
```

```ini
MDARIX_SITE_LOGIN_HASH='$2a$14$...the whole line it printed...'
```

The browser asks for this login once per session, before the MDARIX sign-in page. Invitation and password-reset links
sent from staging open behind the same login, so give it to every tester. Once the lawyer-approved texts and the
company details are in place, set `MDARIX_SITE_ACCESS=public` and remove the acknowledgement.

## 1. What you need

| Item | Notes |
|---|---|
| An Oracle Cloud account | Sign up for the Free Tier. Oracle verifies a payment card but does not charge Always Free resources. |
| A host name for staging | An `A` record such as `staging.<your domain>` pointing at the server (section 2.4). Caddy obtains the Let's Encrypt certificate for it. |
| An SMTP account | Invitations and password resets are sent by email; staging refuses to start without one. Several email providers have free plans. |
| An alert destination | A Slack or Teams incoming webhook (`MDARIX_ALERT_WEBHOOK`) and/or an address (`MDARIX_ALERT_EMAIL`). |
| An uptime monitor and a heartbeat monitor | For example UptimeRobot or Better Stack (uptime) and Healthchecks.io (heartbeat); each has a free plan. |
| An SSH key pair, and your public IP address | SSH is opened to your address only. |

## 2. Create the server (Oracle console)

### 2.1 Account and home region

Sign up at oracle.com/cloud/free. The **home region** cannot be changed later, and Always Free resources exist only
there: choose one close to you that offers Ampere A1 (most commercial regions do).

### 2.2 Network

1. *Networking > Virtual cloud networks > Start VCN Wizard > Create VCN with Internet Connectivity*. Accept the
   defaults.
2. Open the VCN's **public subnet > Default Security List > Add Ingress Rules**:

   | Source CIDR | Protocol | Destination port | Purpose |
   |---|---|---|---|
   | `<your IP>/32` | TCP | 22 | SSH from your address only |
   | `0.0.0.0/0` | TCP | 80 | Let's Encrypt and the redirect to HTTPS |
   | `0.0.0.0/0` | TCP | 443 | HTTPS |
   | `0.0.0.0/0` | UDP | 443 | HTTP/3 (optional) |

   Remove any default rule that opens 22 to `0.0.0.0/0`.

### 2.3 The server

*Compute > Instances > Create instance*:

| Setting | Value |
|---|---|
| Image | Canonical Ubuntu 24.04 (Oracle offers the ARM build once the shape below is chosen) |
| Shape | Ampere, `VM.Standard.A1.Flex`, **2 OCPUs and 12 GB memory** |
| Networking | The public subnet above, *Assign a public IPv4 address* |
| SSH keys | Upload your public key |
| Boot volume | 100 GB (Always Free covers 200 GB of block storage in total) |

2 OCPUs and 12 GB is the Always Free allowance since Oracle reduced it in 2026 (from 4 and 24). The stack needs about
7.25 GB under its memory limits (API 2, background service 1.5, ClamAV 1.5, Postgres 2, Caddy 0.25), so it fits, with a
swap file for spikes. If your console still allows 4 and 24 at no cost, 2 and 12 is still enough.

**"Out of capacity"** means the region has no free ARM capacity at that moment. Try another availability domain, or
try again later.

**Idle servers are reclaimed.** Oracle may stop an Always Free server that stays idle for seven days, measured as
CPU, network and memory use all below 20 percent. Oracle sends a warning email first. Check Oracle's current Always
Free page for the exact rule. A running MDARIX stack normally uses more than 20 percent of the memory.

### 2.4 Host name

Create the `A` record for the staging host name pointing at the instance's public IP address. Without your own
domain, a wildcard DNS service that maps names to addresses (such as `<ip-with-dashes>.sslip.io`) also works with
Let's Encrypt.

## 3. Prepare the server

SSH in as `ubuntu`.

### 3.1 Firewall first, before Docker

Oracle's Ubuntu images ship their own `iptables` rules: they accept SSH and refuse everything else. Open 80 and 443
above the refusing rule, and save, **before installing Docker**. Saving later would also save Docker's own rules,
which Docker recreates itself when it starts.

```bash
sudo iptables -L INPUT -n --line-numbers        # note the number N of the "REJECT all" line
sudo iptables -I INPUT N -p tcp -m state --state NEW --dport 80 -j ACCEPT
sudo iptables -I INPUT N -p tcp -m state --state NEW --dport 443 -j ACCEPT
sudo iptables -I INPUT N -p udp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

Do not enable `ufw` on this server (DEPLOYMENT.md section 2.1 uses it on other providers). The Oracle security list of
section 2.2 is the outer firewall, and the image's rules are the inner one.

### 3.2 Packages, SSH, swap and the deploy user

As in DEPLOYMENT.md section 2.1, without `ufw`:

```bash
sudo apt-get update && sudo apt-get -y upgrade
sudo apt-get install -y docker.io docker-compose-v2 git fail2ban unattended-upgrades chrony openssl
sudo dpkg-reconfigure -plow unattended-upgrades
sudo sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/; s/^#\?PermitRootLogin .*/PermitRootLogin no/' /etc/ssh/sshd_config
sudo systemctl restart ssh
sudo systemctl enable --now fail2ban chrony
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
sudo adduser --disabled-password --gecos "" deploy && sudo usermod -aG docker deploy
```

## 4. Code and settings

As `deploy` (`sudo -iu deploy`):

```bash
git clone https://github.com/stelikicherla-stack/MDARIX-R1.git ~/mdarix && cd ~/mdarix
git checkout main                                     # or the release tag being staged
cp .env.production.example .env.production && cp .env.migrate.example .env.migrate
chmod 600 .env.production .env.migrate
cat >> ~/.profile <<'EOF'
export COMPOSE_FILE=docker-compose.prod.yml:docker-compose.staging-oracle.yml COMPOSE_ENV_FILES=.env.production
EOF
. ~/.profile                                          # from here on, plain "docker compose ..." uses both files
```

Fill `.env.production` and `.env.migrate` as described in their comments and in ENVIRONMENT_VARIABLES.md. These
values differ from production:

| Setting | Staging value |
|---|---|
| `MDARIX_ENV` | `staging` |
| `MDARIX_IMAGE_REPOSITORY` | `mdarix` (images built on this server) |
| `MDARIX_RELEASE` | a name for this build, e.g. `staging-2026-10-11` |
| `MDARIX_DOMAIN`, `MDARIX_APP_URL`, `ACME_EMAIL` | the staging host name, `https://` + that name, your email address |
| `POSTGRES_HOST` / `POSTGRES_PORT` / `POSTGRES_DB` | `postgres` / `5432` / `mdarix` |
| `POSTGRES_SSLMODE` | `verify-full` |
| `POSTGRES_SSLROOTCERT` | `/etc/mdarix/certs/db-ca.pem` (`MDARIX_DB_CA_DIR` stays `./certs`) |
| `MDARIX_DB_OWNER_USER` | `mdarix_owner` (its password, `MDARIX_DB_OWNER_PASSWORD`, goes in `.env.migrate`) |
| `MDARIX_OBJECT_STORAGE_PROVIDER` | `local`, with `MDARIX_OBJECT_STORAGE_ENCRYPTION_KEY` set; leave the bucket settings empty |
| `MDARIX_SCHEDULER_HEARTBEAT_URL` | the heartbeat monitor's ping address (section 8.3) |
| `MDARIX_WWW_REDIRECT` | `off` (the staging host name has no www record) |
| `MDARIX_REDIRECT_DOMAINS` | empty (no other names point at a staging server) |
| `MDARIX_SITE_ACCESS` and the login settings | as in section 0 |

The runtime role (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `MDARIX_DB_RUNTIME_USER`, `MDARIX_DB_RUNTIME_PASSWORD`) is set
as in production: the `migrate` job creates it.

## 5. The database

As `ubuntu` (the `deploy` user has no sudo), once:

```bash
sudo bash /home/deploy/mdarix/infrastructure/staging/prepare-database.sh   # admin password, TLS key and certificate, certs/db-ca.pem
```

Then as `deploy`:

```bash
docker compose up -d --wait postgres
docker compose exec -u postgres postgres psql
```

In `psql`, with the owner password from `.env.migrate` typed at the prompt (it never lands in the shell history):

```sql
CREATE ROLE mdarix_owner LOGIN CREATEROLE;
\password mdarix_owner
CREATE DATABASE mdarix OWNER mdarix_owner;
\c mdarix
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
\q
```

The database answers only on the private Docker network, and only over TLS with a password. Inside the container
the `postgres` user signs in over the socket (`infrastructure/staging/pg_hba.conf`).

## 6. Build the images on the server

```bash
docker compose build api web                          # ARM images: mdarix/api and mdarix/web, tagged MDARIX_RELEASE
```

The `migrate` and `background` services run the `api` image. The first build downloads the dependencies and
the embedding model, and takes a while on two cores.

## 7. Check the settings, start, and create the administrators

With the private-site settings of section 0 in `.env.production`:

```bash
docker compose run --rm --no-deps api python -m backend.app.config_check --offline   # prints nothing when ready
docker compose up -d --no-build --wait                # ClamAV's first signature download can take up to 15 minutes
docker compose ps -a                                  # all healthy; migrate "Exited (0)"
docker compose exec api python -m backend.app.config_check                           # the online checks too
curl -fsS https://<staging host>/health/status        # {"status":"ok"}: open, for the monitors
curl -s -o /dev/null -w '%{http_code}
' https://<staging host>/   # 401: the site asks for the login
```

Then invite two Platform Administrators (DEPLOYMENT.md section 2.5), with `docker compose run --rm migrate python
scripts/create_platform_admin.py ...`.

## 8. Close the four items

Keep each check's output with the date. It is the evidence that the item is closed.

### 8.1 TLS with real certificates

```bash
curl -sv https://<staging host>/health/status -o /dev/null 2>&1 | grep -E "SSL connection|subject:|issuer:|expire"
```

The issuer is Let's Encrypt and the subject is the staging host name. Then run the public test at
`https://www.ssllabs.com/ssltest/` for the host name: the grade should be A or better (HSTS is on).

The database connections are checked by name against the staging CA (`verify-full`). To see that every MDARIX
connection uses TLS:

```bash
docker compose exec -u postgres postgres psql -d mdarix -c \
  "select a.usename, s.ssl, s.version from pg_stat_ssl s join pg_stat_activity a using (pid) where a.usename like 'mdarix%'"
```

Every row shows `ssl = t`. A connection without TLS is refused by the database itself.

### 8.2 The malware scanner

The command below sends the industry-standard antivirus test file (EICAR, stored here in base64 so no file holds it)
to the scanner the API uses. It uses a temporary folder and stores nothing:

```bash
docker compose exec api python -c "import base64, tempfile; from object_storage.service import ObjectStorageService as S; t = base64.b64decode('WDVPIVAlQEFQWzRcUFpYNTQoUF4pN0NDKTd9JEVJQ0FSLVNUQU5EQVJELUFOVElWSVJVUy1URVNULUZJTEUhJEgrSCo='); s = S(root=tempfile.mkdtemp()); print('test virus refused:', not s.scan(t, 'text/plain')); print('ordinary text accepted:', s.scan(b'MDARIX scanner check', 'text/plain'))"
docker compose logs clamav | grep FOUND                # Eicar-Test-Signature FOUND
```

Both lines print `True`. Then, in the app, upload a file containing the same text as evidence: the upload is
refused.

### 8.3 Monitoring

```bash
docker compose exec api python scripts/send_test_alert.py --note "staging monitoring check"
```

The alert arrives in the webhook channel and/or the mailbox, and the script exits with 0. Then:
1. Point the uptime monitor at `https://<staging host>/health/status`. It should report `ok`.
2. Create a heartbeat check with a period of 5 minutes and a grace time of 5 minutes (the scheduler pings every 5
   minutes), and put its ping address in `MDARIX_SCHEDULER_HEARTBEAT_URL`. Restart with
   `docker compose up -d --no-build --wait`.
3. Drill: `docker compose stop background` (the outbox worker and the scheduler) and wait for the heartbeat
   monitor's alert. Then `docker compose start background` and wait for the recovery notice.

### 8.4 Two application instances on one database

Create a staging user whose role does not require an authenticator code (for example a Quality Reviewer in a test
organization), then run:

```bash
read -rp "Test user email: " MDARIX_TEST_EMAIL && read -rsp "Password: " DAY35_FIXTURE_PASSWORD && echo
export MDARIX_TEST_EMAIL DAY35_FIXTURE_PASSWORD
docker compose exec -e MDARIX_TEST_EMAIL -e DAY35_FIXTURE_PASSWORD api python scripts/verify_stage2_multi_instance.py
unset DAY35_FIXTURE_PASSWORD
```

The script starts two more application instances inside the API container, against the staging database. It
signs in on one, uses the session on the other, signs out on the second, and checks that the first refuses the
session. The required lines read `PASS`, and the last reads `PASS | required production-like checks`. Lines marked
`NOT_EXERCISED` or `NOT_CONFIGURED` are listed for information.

This proves several instances sharing one database. Instances on separate servers behave the same way, because
sessions are kept in the database. Two servers would need a second machine and a shared file store, which the free
allowance does not cover.

## 9. Updating staging

```bash
cd ~/mdarix && git pull                               # or check out the next tag
# compare .env.production / .env.migrate with the templates; set a new MDARIX_RELEASE
docker compose build api web
docker compose run --rm --no-deps api python -m backend.app.config_check --offline
docker compose up -d --no-build --wait
```

## 10. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| The site works on the server (`curl -k https://localhost -H "Host: <staging host>"`) but not from outside | The security list (section 2.2) or the image's firewall (section 3.1). `sudo iptables -L INPUT -n --line-numbers` must show the 80 and 443 rules above the REJECT line. |
| Caddy logs certificate errors | The host name does not point at the server yet, or port 80 is closed. |
| Postgres stops with "could not load private key file" | The key lost its owner or permissions: as `ubuntu`, run `sudo bash /home/deploy/mdarix/infrastructure/staging/prepare-database.sh` again, which restores them. |
| "certificate verify failed" in the API, worker or scheduler logs | `POSTGRES_HOST` must be `postgres`, the name in the certificate, and `certs/db-ca.pem` must be the CA that signed it (both come from the same run of the script). |
| A container restarts with exit code 137 | Out of memory: `docker stats`; check that swap is on (`swapon --show`). |
| The server was stopped by Oracle | It was idle (section 2.3). Start it again from the console; the data on its disk is kept. |
