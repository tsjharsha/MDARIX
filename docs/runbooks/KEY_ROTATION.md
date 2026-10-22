# Key and secret rotation

How to replace each secret MDARIX uses: on a schedule, when a person who knew it leaves, or at once when it may have
leaked. `dc` is `docker compose -f docker-compose.prod.yml --env-file .env.production` (DEPLOYMENT.md). Generate new
values with `openssl rand -base64 48` (tokens and salts) or `python -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"`
(encryption keys). Store every new value in the password manager before you change the server, and record each
rotation (what, when, who, why) in the operations log.

Rotate at least yearly and whenever someone who held the values leaves. If a value may have leaked, rotate it now and
follow INCIDENT_RESPONSE.md.

## Rotate any time (no data to re-encrypt)

| Secret | Steps | What people notice |
|---|---|---|
| `MDARIX_RLS_SYSTEM_TOKEN` (system scope) | Set the new value in `.env.production`, then `dc up -d --no-build --wait`: the migrate job stores its hash (`scripts/set_rls_system_token.py`) and the services restart with it. | Nothing; platform administration and scheduled jobs pause for the restart. |
| `MDARIX_DB_RUNTIME_PASSWORD` (the API's database login) | Set the new value in `.env.production`, then `dc up -d --no-build --wait`: the migrate job sets it (`scripts/configure_runtime_role.py`) before the services restart. | Nothing beyond the restart. |
| `MDARIX_DB_OWNER_PASSWORD` (migrations, scripts) | Change it at the database provider, then in `.env.migrate`; run `dc up -d --no-build --wait` to check the migrate job still connects. | Nothing. |
| `MDARIX_BACKUP_DB_PASSWORD` (the backup login) | Change it in `.env.migrate`, then `dc run --rm migrate python scripts/configure_backup_role.py`; run one backup (`dc --profile backup run --rm backup`) to check. | Nothing. |
| `MDARIX_OBJECT_STORAGE_SIGNING_SECRET` | Set the new value, `dc up -d --no-build --wait`. | Download links already handed out stop working; people open them again from the page. |
| `MDARIX_DEMO_REQUEST_SALT`, `MDARIX_RATE_LIMIT_SALT` | Set the new values, `dc up -d --no-build --wait`. | Duplicate-request detection and rate-limit counters start again from zero. |
| Provider credentials: `MDARIX_SMTP_PASSWORD`, `MDARIX_GENAI_*_API_KEY`, `RESEND_API_KEY`, `MDARIX_SENTRY_DSN`, AWS keys in `.env.migrate` | Create the new credential at the provider, put it in the settings file, `dc up -d --no-build --wait`, check (`dc exec api python scripts/send_test_alert.py` for email), then revoke the old one at the provider. | Nothing. |

Sessions have no key to rotate: session tokens are random and stored only as hashes. To sign everyone out (for
example after a leak of a database copy), revoke every open session with the owner login and each person signs in
again: `UPDATE auth_sessions SET revoked_at = now() WHERE revoked_at IS NULL;`

## Rotate with a keyring: connector API keys

`MDARIX_CONNECTOR_ENCRYPTION_KEY` encrypts the customers' system API keys that connectors store
(`access_control/connector_secrets.py`). Each sealed value records the key ID it was sealed with, so old and new keys
can be read side by side:

1. Generate a new key. Set it as `MDARIX_CONNECTOR_ENCRYPTION_KEY` with a new `MDARIX_CONNECTOR_ENCRYPTION_KEY_ID`
   (for example `k2`), and keep the old key readable: `MDARIX_CONNECTOR_ENCRYPTION_KEYS=k1:<old key>`.
2. `dc up -d --no-build --wait`. New and changed connections are sealed with the new key; old ones still open.
3. `dc run --rm migrate python scripts/reseal_connector_keys.py` (dry run: lists what would change), then again with
   `--apply`. A value that cannot be opened is reported and left unchanged: fix that connection before step 4.
4. Remove the old key from `MDARIX_CONNECTOR_ENCRYPTION_KEYS` and `dc up -d --no-build --wait`.

## Rotate with a keyring: MFA and file encryption keys

`MDARIX_MFA_ENCRYPTION_KEY` encrypts the authenticator secrets (`auth/totp.py`) and `MDARIX_OBJECT_STORAGE_ENCRYPTION_KEY`
the stored files when they are kept on the server's own volume (`MDARIX_OBJECT_STORAGE_PROVIDER=local`,
`object_storage/service.py`; with S3 storage the provider's key management encrypts the files and this key is not
used). Since 0.10.47 each has a keyring like the connector key (`security/keyring.py`):

- `<key>_ID` names the current key (`MDARIX_MFA_ENCRYPTION_KEY_ID`, `MDARIX_OBJECT_STORAGE_ENCRYPTION_KEY_ID`). While it
  is unset, secrets and files are sealed exactly as before 0.10.47, without a key ID. Once it is set, everything new
  records the key ID it was sealed with.
- `<key>S` lists the older keys still readable (`MDARIX_MFA_ENCRYPTION_KEYS`, `MDARIX_OBJECT_STORAGE_ENCRYPTION_KEYS`):
  `k1:<old key>`. What was sealed without a key ID is opened with the current key and then with each listed key, so
  the key used before the first rotation is simply listed as `k1`.

The configuration check refuses a malformed entry, an ID listed twice and the current ID listed among the old keys,
and warns while old keys are listed. Rotate both keys together, in a quiet hour:

1. **Back up first**: `dc --profile backup run --rm backup`, and check it finished without error. Keep a copy of
   `.env.production` readable by the deploy user only (`install -m 600 .env.production .env.production.pre-rotation`).
2. Generate two new keys (one per setting, the command at the top of this page) and store them in the password
   manager. In `.env.production`, for each of the two keys: the new key as `<key>`, `<key>_ID=k2`, and the old key,
   unchanged, as `<key>S=k1:<old key>`. (At the next rotation: the new key as `k3`, and `k2` in `<key>S`.)
3. `dc up -d --no-build --wait`. New secrets and files are sealed with `k2`; everything stored before still opens.
4. Dry runs, which list counts only and change nothing:
   `dc run --rm migrate python scripts/reseal_mfa_secrets.py` and
   `dc run --rm --no-deps api python scripts/reencrypt_object_storage.py` (the files are on the API's volume, so this
   one runs in an API container; the migrate job has no access to them). Then run both again with `--apply`. Each
   value or file is re-sealed with the current key and checked to open with it before it replaces the old one (a file
   through a temporary file renamed over it, keeping its owner and permissions). Anything that cannot be opened is
   reported, left unchanged, and the script exits 1: find out why before step 6. Both scripts are safe to run again;
   a second run reports everything as already on `k2`.
5. Check that people notice nothing: sign in with an authenticator code (a platform administrator), and open a stored
   file (an attachment or a report download).
6. A week later, remove the `k1` entries from both `<key>S` settings and `dc up -d --no-build --wait`; the
   configuration check stops warning. **Keep the old keys in the password manager** for as long as any backup made
   while they were in use is kept (`MDARIX_BACKUP_KEEP_DAYS` on the server, 14 days by default, and the off-site
   copy's retention, up to 90 days): a database backup holds MFA secrets sealed with the old MFA key, and a file
   backup holds files encrypted with the old file key. To restore such a backup, list the old key again as `k1` in
   `<key>S`, restore, then run step 4 again.

If something goes wrong before step 6, put the `.env.production` copy from step 1 back and `dc up -d --no-build
--wait`: the old key opens everything sealed before the rotation, and anything sealed with `k2` meanwhile (a new
authenticator, a new file) needs `k2` listed as `MDARIX_..._KEYS=k2:<new key>` to open.

## Backup encryption (age)

Backups are encrypted to `MDARIX_BACKUP_AGE_RECIPIENT` (BACKUP_AND_RESTORE.md). To rotate:

1. Create a new key pair offline (`age-keygen`), keep the private key in the password manager or offline storage.
2. Set the new public key as `MDARIX_BACKUP_AGE_RECIPIENT`; the next backup uses it. Run one now to check.
3. **Keep the old private key** for as long as any backup encrypted with it is kept (`MDARIX_BACKUP_KEEP_DAYS` on the
   server, and the bucket's retention off-site). Without it those backups cannot be restored. Destroy it only after
   the last of them has expired.
