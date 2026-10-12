# ADR-017: Hosting: Staging on Oracle Cloud Always Free, Pilots on Azure

## Context
Six infrastructure items remain open, and each needs a real hosted environment:
- point-in-time recovery;
- a production monitoring destination;
- TLS checked against real certificates;
- a key management service;
- a running malware scanner;
- hosted multi-server testing.

The hosting decision of 2026-10-03 (one Linux VM with Docker Compose, a managed PostgreSQL with point-in-time recovery)
names no provider. No budget is set yet. In October 2026 no provider's free offer covers that whole setup for long:
- AWS no longer gives new accounts free compute or databases, only credit.
- Google Cloud gives credit for 90 days and a 1 GB server.
- Oracle's Always Free tier includes an ARM server of 2 OCPUs and 12 GB with no end date, but no managed PostgreSQL.
- Azure's free account includes a managed PostgreSQL for 12 months, but no server large enough for the application.

## Decision
- **Staging runs on Oracle Cloud Always Free** (docs/runbooks/STAGING_ORACLE.md). One ARM server runs the production
  compose file plus `docker-compose.staging-oracle.yml`:
  - Postgres in a container, TLS only (its own CA, checked by name);
  - ClamAV from the ARM-capable Debian image;
  - images built on the server;
  - files encrypted on the server's disk.

  Staging closes the TLS, malware scanner, monitoring and multi-instance items. It never holds customer data, so it
  needs no point-in-time recovery.
- **Design-partner pilots run on Azure.** Azure Database for PostgreSQL Flexible Server is free for the first 12
  months (Burstable B1MS, 32 GB) and includes point-in-time recovery. A Linux VM of DEPLOYMENT.md's size and Azure
  Key Vault are paid from startup credits (Microsoft for Startups). The pilot environment closes point-in-time
  recovery and key management.

## Rationale
Staging at no cost lets four items be proven now on the same compose file as production. Customer data needs what a
free server cannot promise: a managed database with point-in-time recovery, an uptime commitment, and no risk of the
server being reclaimed when idle.

## Consequences
- Release images are built for x86 only, which suits Azure. Staging builds its ARM images on the server.
- The production compose file's ClamAV image is x86-only. Its comment no longer says otherwise, and staging
  replaces the image.
- `scripts/verify_stage2_multi_instance.py` now works outside development:
  - it uses the environment's own session cookie and sends it explicitly to each instance;
  - its sign-out names the app's origin;
  - it proves that the first instance accepted the session before the revocation.
- Before the pilot environment, three items must be built or decided:
  - **A Key Vault adapter**: `security/tenant_keys.py` is only a contract today, and keys come from environment
    variables.
  - **Uploaded files**: Azure Blob Storage does not speak the S3 API that `object_storage/service.py` and the
    off-site backup (`MDARIX_BACKUP_S3_URI`) use. Either support Azure Blob, or use the VM's disk plus an
    S3-compatible bucket elsewhere for the off-site copies.
  - **Server size**: the B1MS database (1 vCore, 2 GB) suits a first pilot only; growth is paid.

## Decision on the legal pages (2026-10-12): private staging

Option 1 below was chosen. `MDARIX_SITE_ACCESS=private` puts the whole site behind a login at Caddy (only
`/health/live` and `/health/status` stay open for the monitors), and `backend/app/config_check.py` skips the
legal checks only on a staging server with that login set and `MDARIX_PRIVATE_STAGING_ACKNOWLEDGED=true`.
Production is unchanged: it always needs the lawyer-approved texts and the company details.

## The options that were considered
Staging runs every production check, including the legal pages. It refuses to start until the texts are
lawyer-approved and final and the company name and address are set. Staging is public, so it would publish them.
The options:
1. **Recommended: a private staging server.** In staging only, accept unapproved legal texts when the whole site sits
   behind a login at Caddy and an explicit acknowledgement is set. This is a small change to
   `backend/app/config_check.py` and a staging Caddy setting. Production is unchanged.
2. Wait for the lawyer-approved texts before starting staging.
3. Use placeholder company details and texts with the approval flag set, as CI does. Not recommended: the public site
   would show them.

## Alternatives Considered
- AWS for staging: no free compute for new accounts.
- Google Cloud: credit for 90 days only, and its free server is too small.
- Oracle for pilots: no managed PostgreSQL and no point-in-time recovery; idle free servers can be reclaimed.
- Azure for both: the free server is too small for the application, so staging would not be free.

## Status
ACCEPTED (2026-10-11). Private staging chosen (2026-10-12).
