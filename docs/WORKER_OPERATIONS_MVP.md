# Worker/outbox MVP operations

The MDARIX worker uses a durable transactional outbox with retry, dead-letter,
replay, row locking, worker claims, heartbeat metrics, and stale-claim
recovery. Migration `z44outboxclaims` adds `claimed_by` and `claimed_at` so a
crashed process can be recovered without duplicate claiming.

Local MVP evidence covers retry/dead-letter/replay, concurrent claim locking,
graceful shutdown, metrics, and the stale-claim recovery contract. Hosted
worker deployment, production queue metrics/alerts, and production-scale
embedding/document parsing require deployed infrastructure and are not claimed
by local tests.
