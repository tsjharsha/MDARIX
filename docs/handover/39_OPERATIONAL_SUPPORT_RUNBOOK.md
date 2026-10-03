# Operational support runbook

## First response

1. Get the **request ID** (every API error returns `request_id`; responses carry `X-Request-ID`), the time, the
   organization and the screen. Search the JSON logs for that ID: every log line of the request carries it.
2. Check `GET /health/ready`: database, schema at head, dedicated data planes (reachable and at head), object storage,
   worker heartbeat and email. `not_ready` (503) names the failing component.
3. Never bypass an organization's access controls, and never change production data by hand. Corrections go through
   the application so they are audited.

## Alerts (webhook and/or email, `MDARIX_ALERT_WEBHOOK` / `MDARIX_ALERT_EMAIL`)

| Alert | Meaning | What to do |
|---|---|---|
| Events could not be delivered | Outbox events were dead-lettered after their retries | Platform Admin > Operations (dead-lettered events): read the error, fix the cause (often email), retry. |
| Background worker stopped / recovered | No worker heartbeat for a minute | `docker compose -f docker-compose.prod.yml ps worker`, then its logs. |
| Scheduled job failing / recovered | A scheduler job failed three times in a row | `python scripts/run_scheduler.py --list` shows each job's last result and error. |
| Trial data could not be deleted | A trial past its retention could not be purged completely; nothing was changed | Read the error (`ROWS_REMAIN:<tables>` names a table holding rows a foreign key keeps); fix and let the job retry. |
| Audit trail integrity check failed | An organization's hash chain no longer verifies (`CHAIN_BROKEN` or `ANCHOR_CHANGED`) | Treat as a security incident: preserve the database and logs, do not change data, escalate. |

## Common customer questions

- **"AI answers say they come from rules."** The organization's AI processing is off, its monthly allowance is used
  up, or no contracted provider is configured. Platform Admin > tenant > AI processing shows which; the customer
  administrator sees the same under Security > AI processing.
- **"I cannot sign in."** Locked after repeated failures (wait, or reset the password), MFA device lost (Users > Reset
  MFA, by another administrator), or the trial ended (the sign-in page says so, with the deletion date).
- **"Please send us all our data / delete our data / delete my data."** Follow
  [docs/runbooks/DATA_REQUESTS.md](../runbooks/DATA_REQUESTS.md).
- **Email not arriving.** The Platform Admin dashboard shows the SMTP status; the trial requests queue shows whether an
  invitation was sent or failed, with Resend.
