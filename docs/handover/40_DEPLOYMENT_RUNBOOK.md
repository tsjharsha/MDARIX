# Deployment runbook

Build and scan immutable images, inject secrets through the approved manager, run migrations with a controlled identity, verify health/readiness, worker heartbeat, database role/TLS, storage and notification dependencies, then run smoke and rollback checks. Production deployment is not proven by local Compose.
