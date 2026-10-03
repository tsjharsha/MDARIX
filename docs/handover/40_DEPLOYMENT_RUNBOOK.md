# Deployment runbook

Follow [docs/runbooks/DEPLOYMENT.md](../runbooks/DEPLOYMENT.md): one Linux VM with Docker Compose and Caddy
(`docker-compose.prod.yml`), managed Postgres with point-in-time recovery, secrets in `.env.production` (template
`.env.production.example`, every variable in [ENVIRONMENT_VARIABLES.md](../runbooks/ENVIRONMENT_VARIABLES.md)).

Every start runs the `migrate` job first (migrations, runtime role, privileges, RLS system token, dedicated data
planes); the API refuses to start in staging or production while any setting is missing or unsafe
(`python -m backend.app.config_check` lists them all). Before promoting a release that changes AI behaviour, run the
**AI evaluation gate** workflow. CI proves production mode on every pull request (job "Production mode": TLS database,
startup checks, CSRF, `__Host-` cookies, MFA enrollment) and scans the production images (job "Production image scan").
