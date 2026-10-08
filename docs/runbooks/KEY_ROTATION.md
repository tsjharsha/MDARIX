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

## Rotate only with a plan: these keys have no keyring yet

Changing either of these keys makes what was encrypted with the old one unreadable. There is no tool yet to read with
the old key and write with the new one; until there is, rotate them only when the old key is known to have leaked,
and plan for the consequence.

- **`MDARIX_MFA_ENCRYPTION_KEY`** (authenticator secrets, `auth/totp.py`). After a change no stored authenticator can
  be read: every person who set one up must set it up again. Platform administrators are reset with
  `scripts/reset_platform_admin_mfa.py` (DEPLOYMENT.md, break-glass); customer administrators reset their people's MFA
  from the console. Tell everyone before you start.
- **`MDARIX_OBJECT_STORAGE_ENCRYPTION_KEY`** (stored files, local storage only, `object_storage/service.py`). After a
  change no stored file can be read. Do not change it on a server that holds files; restore from a backup taken with
  the old key if it was changed by mistake. With S3 storage the provider's key management (KMS) encrypts the files and
  rotates its own keys; this setting is not used.

Adding a keyring to these two (as connector keys have) is the follow-up that makes them rotatable without
re-enrolment or data loss.

## Backup encryption (age)

Backups are encrypted to `MDARIX_BACKUP_AGE_RECIPIENT` (BACKUP_AND_RESTORE.md). To rotate:

1. Create a new key pair offline (`age-keygen`), keep the private key in the password manager or offline storage.
2. Set the new public key as `MDARIX_BACKUP_AGE_RECIPIENT`; the next backup uses it. Run one now to check.
3. **Keep the old private key** for as long as any backup encrypted with it is kept (`MDARIX_BACKUP_KEEP_DAYS` on the
   server, and the bucket's retention off-site). Without it those backups cannot be restored. Destroy it only after
   the last of them has expired.
