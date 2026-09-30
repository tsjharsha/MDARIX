# Backend architecture

FastAPI routers expose authentication, administration, business, AI, reports, integrations and simulator-facing APIs. SQLAlchemy/Alembic provide persistence; request context and access-control modules enforce identity, tenant membership and role rules. Workers use durable outbox/job patterns with retries, dead letters and replay foundations.

The data-plane dependency resolves a tenant registry entry to a tenant database. Migration is service-by-service: control-plane routes must continue using the control session, while product/investigation/evidence/search/export/AI/attachment/worker routes are migrated deliberately and tested.

Operational boundary: local Docker validation is not production deployment evidence.
