# Developer and quality tooling

What the repository has today. CI jobs are in `.github/workflows/ci.yml`; a tool listed as "in CI" fails the build
on its findings.

| Area | Tool | Status | Where |
|---|---|---|---|
| Browser tests and accessibility | Playwright + axe | In CI (`browser` job) | `frontend/playwright.config.ts`, `frontend/e2e/` |
| Frontend unit tests | Vitest | In CI (`frontend` job) | `npm --prefix frontend test` |
| Frontend type check | TypeScript (`tsc --noEmit --noUnusedLocals`) | In CI | `npm --prefix frontend run lint` |
| Frontend formatting | Prettier | In CI | `frontend/.prettierrc.json`, `npm --prefix frontend run format:check` |
| Frontend lint rules | ESLint | Not configured | The `lint` script is the TypeScript check above |
| Python lint and format | Ruff | In CI (`security` job) | `ruff.toml`; `ruff check .`, `ruff format --check .` |
| Python type check | mypy | Not configured | |
| Python dependencies | pip-audit | In CI | `pip-audit -r requirements.txt` |
| JavaScript dependencies | npm audit | In CI | `frontend` job, high and above |
| Secret scanning | Gitleaks | In CI (`security` job) | `gitleaks/gitleaks-action` |
| Container images | Trivy | In CI (`image-scan` job) and before each release | Production images: every high and critical finding, except reviewed ones in `.trivyignore.yaml` (each with its reason and an expiry) |
| Static analysis | CodeQL | Pull requests, `main` and weekly | `.github/workflows/codeql.yml` (Python, TypeScript) |
| Dependency updates | Dependabot | Weekly | `.github/dependabot.yml` (pip, npm, docker, github-actions) |
| Email capture (local) | Mailpit | In `docker-compose.yml` | Web UI `http://localhost:8025`, SMTP port 1025 |
| Object storage (local) | MinIO | In `docker-compose.yml` | S3 API port 9000, console 9001 |
| Load smoke | k6 | Script only, run by hand | `scripts/k6/mdarix-smoke.js` (non-production targets only) |
| Error tracking | Sentry | Optional | Set `MDARIX_SENTRY_DSN` (`backend/app/logging_setup.py`) |
| Web security scan | OWASP ZAP | Manual | Run against a local or staging stack with test accounts only |
| Metrics dashboards | Prometheus/Grafana | Not provided | Services log structured JSON; the worker logs its metrics every cycle |

Passing these tools does not prove production readiness. Real SMTP delivery, the managed database, backups and
monitoring are proven on the deployment itself ([DEPLOYMENT.md](DEPLOYMENT.md),
[BACKUP_AND_RESTORE.md](BACKUP_AND_RESTORE.md)).
