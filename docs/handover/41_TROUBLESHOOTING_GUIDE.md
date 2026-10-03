# Troubleshooting guide

| Symptom | Likely cause | Fix |
|---|---|---|
| API exits at start with "MDARIX will not start in production" | A required setting is missing or unsafe | `python -m backend.app.config_check` lists every problem; fix them all, start again. |
| `/health/ready` says the schema is not at head | Migrations did not run | `docker compose -f docker-compose.prod.yml run --rm migrate`. |
| `DATA_PLANE_SCHEMA_OUTDATED` (503) for one customer | Their dedicated database is behind | `python scripts/migrate_data_planes.py --apply` (the migrate job runs it). |
| `DATA_PLANE_UNAVAILABLE` / `TENANT_DATA_NOT_AVAILABLE` | The organization has no ACTIVE data plane (retired, suspended or deleted) | Check `tenant_data_planes` for that organization; never point it at another organization's plane. |
| Platform administration shows nothing | The database does not hold this server's `MDARIX_RLS_SYSTEM_TOKEN` | `python scripts/set_rls_system_token.py`, then restart the API. |
| `CONNECTOR_CREDENTIAL_UNREADABLE` | The connector encryption key changed without a re-seal | Put the old key in `MDARIX_CONNECTOR_ENCRYPTION_KEYS`, run `scripts/reseal_connector_keys.py --apply`. |
| `CONNECTOR_CREDENTIAL_REF_NOT_FOR_TENANT` | A server secret name outside the organization's namespace | Name it `MDARIX_CONNECTOR_SECRET_<tenant identifier>_<NAME>`, or use the connection's own API key. |
| `INVALID_WEBHOOK_SIGNATURE` on inbound email | `RESEND_WEBHOOK_SECRET` is not the endpoint's signing secret (`whsec_…`), or the clock is off by more than five minutes | Copy the secret from Resend; check the server's time. |
| `GENAI_*` codes in logs (`NO_TENANT_SCOPE`, `DISABLED_FOR_ORGANIZATION`, `MONTHLY_BUDGET_REACHED`, `PROVIDER_NOT_ALLOWED`) | The AI controls refused a model call; the feature answered from rules | Expected behaviour; change the organization's AI settings or the contracted provider list if it should be allowed. |
| Frontend shows an old screen after a release | Browser cache | Hard refresh; the web image serves hashed assets, so this only affects the HTML shell. |

Record the cause, the environment and the request ID in the incident note.
