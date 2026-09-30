# Configuration Reference

## Core configuration

Use `.env.example` and `.env.test.example` as templates. Do not commit secrets.

Important configuration families include:

- `POSTGRES_*`: control-plane database connection.
- `MDARIX_ENV`: development/test/production behavior gates.
- `MDARIX_DATA_PLANE_*`: approved data-plane secret references and pool settings.
- `MDARIX_GENAI_*`: provider, model, endpoint, timeout and key configuration.
- `MDARIX_OUTBOX_*`: interval, batch, attempts, publisher, heartbeat and alert settings.
- SMTP/Resend variables: local email or provider delivery configuration.
- object-storage variables: local/S3-compatible endpoint, bucket and credential references.

Production credentials must come from an approved secret manager or deployment secret store.
