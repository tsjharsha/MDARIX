# Operational support runbook

First collect correlation ID, timestamp, tenant/environment, route and redacted logs. Check health/readiness, database identity, worker heartbeat, outbox/dead letters, simulator health, Mailpit and object storage. Preserve audit IDs and evidence; never bypass tenant authorization or mutate production data manually.
