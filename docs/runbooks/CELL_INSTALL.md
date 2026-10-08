# Installing a tenant cell, licensing it, and moving an organization into it

A tenant cell (ADR-011, ADR-013) is one organization's own MDARIX: its own PostgreSQL database, its own keys, the
application running as `MDARIX_DEPLOYMENT_ROLE=CELL`. This runbook builds one from signed documents the platform
issues, and moves an existing organization out of the multi-tenant deployment into it. Nothing in it contacts the
platform over the network: the cell is installed from files, so it works for MDARIX-managed cells and for cells in
a customer's own cloud alike. The platform-to-cell link (enrollment, heartbeat, packages) is Phase 4.

## 0. Once: the platform's signing key

```
python scripts/cell_platform.py keygen --out platform-signing.key
```

The private key stays with the release pipeline (a CI secret or an offline vault), never in a cell. The printed
public key is what every cell pins as `MDARIX_PLATFORM_SIGNING_PUBLIC_KEY`.

## 1. On the platform: issue the organization's documents

Run against the platform (or today's MULTI) database:

```
python scripts/cell_platform.py issue --tenant-key ACME --hosting-mode MDARIX_MANAGED \
    --admin-email admin@customer.example --admin-name "Jane Doe" \
    --private-key-file platform-signing.key --out ./acme
```

This writes `acme/enrollment.json` (the organization, its customer, its first administrator, the hosting mode)
and `acme/licence.json` (the organization's active plan, features and limits; `--valid-until` for a fixed term),
registers the cell in `cells` as PROVISIONING and records the organization's deployment model as CELL. The
organization must have an active plan; licences are issued from it.

## 2. In the cell's environment: an empty database

A PostgreSQL 16 server with the `vector` and `pgcrypto` extensions available, an empty database, and an owner
login that can create roles (`CREATEROLE`) and extensions. For an MDARIX-managed cell this is a managed Postgres
instance per customer; for a customer-cloud cell it is the customer's instance.

## 3. Install the cell

```
python scripts/cell_install.py --database-url postgresql+pg8000://owner:pw@db-host:5432/mdarix_t_acme \
    --bundle acme/enrollment.json --licence acme/licence.json \
    --platform-public-key <public key from step 0> \
    --app-url https://acme.cell.example --env-out acme/cell.env
```

Without `--apply` it verifies both documents and reports what it would do. With `--apply` it migrates the schema
as the production migrate job does, gives the runtime role its login and grants, stores the cell's own system-scope
token, creates the organization exactly as the bundle names it, applies the licence, verifies the database holds
exactly that organization and no business records, invites the first Customer Administrator (the single-use
activation link is printed; send it securely) and writes `acme/cell.env`: the complete environment of the cell's
containers (deployment role, organization, database login, every key and secret, the pinned platform key).

Give `cell.env` to the `api`, `worker` and `scheduler` services as their environment file. Keep it as the cell's
secret: it is the only copy of the cell's keys.

## 4. Moving an existing organization into a cell

Install the cell **without** a licence and **without** the first administrator, since the move brings both the
licence and the organization's people:

```
python scripts/cell_install.py --database-url ... --bundle acme/enrollment.json --no-licence --no-admin-invitation \
    --platform-public-key ... --env-out acme/cell.env --apply
```

Then, from a machine configured for the source deployment (its `POSTGRES_*` settings and its keys in the
environment), first the plan:

```
python scripts/move_tenant_to_cell.py --tenant-key ACME \
    --target-url postgresql+pg8000://owner:pw@db-host:5432/mdarix_t_acme --target-env acme/cell.env \
    --licence acme/licence.json \
    --source-objects-root /var/lib/mdarix/objects --target-objects-root /var/lib/mdarix-acme/objects
```

and, once the counts look right, the same command with `--apply`. The tool:

- reads the source only (every source transaction is READ ONLY);
- copies every row of the organization in foreign-key order with the same ids, business ids and timestamps, the
  organization's and customer's rows, the customer's contacts and domains, the global rows the organization's rows
  point at, and the business-id counters;
- copies the audit trail verbatim with the chain trigger paused, then verifies the chain in the cell against the
  source's last sequence and hash; a mismatch fails the move;
- decrypts MFA secrets, connector credentials and stored files with the source's keys and encrypts them again
  with the cell's;
- applies the licence last, so it tops the audit chain;
- does **not** copy sign-in sessions, MFA challenges, invitation and reset links (people sign in again), the
  data-plane registry, export archives, the pending outbox, licensing and platform-operations records.

The copy runs in one target transaction: a failure leaves the cell as it was. The source is never changed; telling
the platform the organization has moved, and later deleting the source copy, are separate approved steps.

## 5. After the move

1. Start the cell's services with `cell.env`; `python -m backend.app.config_check` in the cell must pass (it
   checks the role, the organization, the pinned key and the database).
2. People sign in again at the cell's address; MFA codes keep working (the secrets were re-encrypted).
3. Verify a signature in *Decisions*: the audit chain and the signatures moved verbatim.
4. On the platform, mark the cell ACTIVE (Phase 4 automates this through enrollment).

## Limits of this phase

- Only local object storage is moved by the tool; an S3 prefix is copied with the provider's tools and the cell's
  bucket configured in `cell.env`.
- A licence's `valid_until` becomes the plan assignment's end; the grace period and read-only mode (decision D6)
  come with the platform link in Phase 4.
- The local development tenant databases built before migrations (`tenant-a..d`) cannot be cell targets.
