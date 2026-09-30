# Docker infrastructure

Compose defines the control PostgreSQL service, four tenant data planes, provider simulator databases/services, worker, MinIO and Mailpit. Port mappings and credentials are development-only. Confirm container health and database identity before running tests; do not substitute an unrelated local PostgreSQL instance.
