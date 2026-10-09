# The platform-cell link: enrollment, heartbeats, packages, licences

A tenant cell (docs/runbooks/CELL_INSTALL.md) reports to the MDARIX platform and fetches what the platform signed
for it. Everything runs **from the cell outward**: the platform never connects to a cell, holds no credential for a
cell's database, and receives metadata only (ADR-014). This runbook sets up the platform's side, enrolls a cell,
and explains what each side keeps.

## 1. On the platform, once

```
python scripts/cell_platform.py ca-init --out /etc/mdarix/platform-ca      # the authority for cell certificates
python scripts/cell_platform.py keygen --out platform-signing.key          # the package-signing key (if not done)
```

Settings of the PLATFORM deployment (`.env.production`):

```
MDARIX_DEPLOYMENT_ROLE=PLATFORM
MDARIX_PLATFORM_SIGNING_PUBLIC_KEY=<public key from keygen>
MDARIX_PLATFORM_CA_KEY_FILE=/etc/mdarix/platform-ca/platform-ca.key
MDARIX_PLATFORM_CA_CERT_FILE=/etc/mdarix/platform-ca/platform-ca.crt
```

The front door asks cells for their certificate and forwards its fingerprint to the API (the `header_up` line in
`infrastructure/docker/Caddyfile`). Add to the platform's site block, with the authority's certificate mounted into
the `web` container:

```
	tls {
		client_auth {
			mode verify_if_given
			trusted_ca_cert_file /etc/mdarix/platform-ca.crt
		}
	}
```

Browsers are not affected (`verify_if_given` only verifies a certificate when one is presented); the API requires
the fingerprint for the cell routes (`MDARIX_CELL_MTLS_REQUIRED`, on by default outside local development) and the
cell's credential on every call. Never expose the API without the front door: the fingerprint header is trusted
because the front door replaces it.

## 2. Issue a cell's documents

```
python scripts/cell_platform.py issue --tenant-key ACME --hosting-mode MDARIX_MANAGED \
    --admin-email admin@customer.example --admin-name "Jane Doe" \
    --private-key-file platform-signing.key --platform-url https://platform.mdarix.example --out ./acme
```

Besides the organization and its licence, the bundle now carries the platform's address and a **one-time
enrollment token** (its hash is kept in `cells`). The cell is registered as PROVISIONING with the licence it will
fetch. Hand the bundle over like a password.

## 3. In the cell

`scripts/cell_install.py` writes `MDARIX_PLATFORM_URL`, `MDARIX_CELL_ENROLLMENT_TOKEN` and `MDARIX_CELL_IDENTITY_DIR`
into `cell.env`. When the cell's scheduler starts, the `platform-sync` job (every 15 minutes, CELL only):

1. **Enrolls** once: generates a private key, sends a certificate signing request with the token, and keeps the
   signed certificate, the authority's certificate and the cell's credential in `MDARIX_CELL_IDENTITY_DIR`
   (`cell.key`, `cell.crt`, `ca.crt`, `credential`; never in the database). The token is spent; remove it from
   `cell.env` afterwards. A second enrollment needs a new bundle.
2. **Heartbeats**: software and schema versions, a health word, uptime, the outcome of each scheduled job (name,
   OK/FAILED/NEVER, error type), a few record counts and the state of each received package. The platform's schema
   refuses unknown fields and free text, so a heartbeat cannot carry a record even by mistake.
3. **Fetches the licence and packages**: everything is verified against `MDARIX_PLATFORM_SIGNING_PUBLIC_KEY`
   before it is stored. The licence is applied automatically (`backend/app/cell_licence.py`); reference-data,
   mapping-template and policy packages are stored as OFFERED for the Customer Administrator (adoption with an
   impact report is a later phase). Anything that does not verify is recorded as REJECTED and audited.

The cell **keeps serving when the platform is unreachable**: the job fails, the scheduler alerts after three
failures, nothing else changes.

### Licence end and grace (decision D6)

A licence's `valid_until` ends the plan assignment. For 30 days after it the cell runs as before (GRACE). After
that it is **read-only**: every screen and record stays available, exports work, but state changes answer
`423 LICENCE_EXPIRED` until a new licence arrives (one sync later). Nothing is ever deleted. The session context
carries the licence state (`licence.state`: VALID, GRACE, EXPIRED, SUSPENDED, NONE outside a cell). A SUSPENDED
licence suspends the organization; an ACTIVE one lifts that suspension.

## 4. Packages

The release pipeline signs a package and a platform administrator uploads it:

```
python scripts/cell_platform.py sign-package --kind REFERENCE_DATA --code IMDRF_CODES --version 2026.1 \
    --content imdrf-2026.1.json --private-key-file platform-signing.key --out imdrf-2026.1.package.json
curl -X POST https://platform.mdarix.example/api/v1/platform-admin/packages -H 'Content-Type: application/json' \
    --cookie "mdarix_session=..." --data @<(jq -n --slurpfile e imdrf-2026.1.package.json '{envelope: $e[0]}')
```

The platform verifies the signature with the same public key the cells pin, stores the envelope unchanged, and
offers it to every cell (`GET /api/v1/cells/packages`). A withdrawn package is no longer offered. The *Tenant cells*
page in the platform console (Operations) shows each cell's last contact, health, versions, failed jobs and package
states; `/platform-admin/packages` lists packages with how many cells applied or rejected each.

## 5. Releases

`release.yml` signs the three images with Sigstore (keyless, by the workflow's GitHub identity) and attaches each
image's software bill of materials (SPDX) to the release. Before upgrading a cell:

```
cosign verify --certificate-identity-regexp '^https://github.com/stelikicherla-stack/MDARIX-R1/' \
    --certificate-oidc-issuer https://token.actions.githubusercontent.com ghcr.io/stelikicherla-stack/mdarix-r1/api:vX.Y.Z
```

## What each side keeps

| Platform (`cells`, `cell_heartbeats`, `packages`, `cell_package_states`) | Cell (`received_packages`, `cell_licences`, identity files) |
|---|---|
| Hosting mode, enrollment, certificate fingerprint, credential hash, last heartbeat, package states, the licence it issued | Its key and certificate, its credential, every package as received and verified, every licence applied |
| Never: a cell's records, users, configuration or free text | Never: the platform's keys |
