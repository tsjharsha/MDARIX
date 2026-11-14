# Free security scans (test release)

`scripts/security_scan.sh` runs the free scans one at a time from pinned Docker images and writes every report to
`security-reports/<release>/` (git-ignored; never committed or uploaded). `SUMMARY.md` in that folder is the one-page
summary kept as B10-1 evidence: counts per severity per tool, and every Critical and High with an empty decision line.

## What runs, against what

| Step | Tools | Target |
|---|---|---|
| `static` | Semgrep (community rules), Bandit, pip-audit, npm audit, Gitleaks (redacted, all branches), Trivy (built API image, Docker/compose config) | The repository |
| `dynamic` | ZAP baseline, ZAP API scan from `/openapi.json`, Schemathesis, Nuclei, the cross-tenant tests | The local test copy only |
| `public` | testssl.sh, Mozilla HTTP Observatory | `https://mdarix.com` only, read-only |
| `summary` | `scripts/security_scan_summary.py` | The report folder |

The local test copy is `infrastructure/security-scan/docker-compose.scan.yml`, started by the `stack-up` step as the
compose project `mdarix-scan`: its own PostgreSQL (127.0.0.1:15433) and API (127.0.0.1:18000), synthetic test fixtures,
random settings generated into the report folder. It never shares a port, container or volume with the development
stack (`mdarix-r1-postgres` on 5433). The attack-style tools reach it over its private Docker network and the script
refuses any other target. `stack-stop` runs `docker compose stop`; nothing is removed. The ports sit below Windows'
dynamic range on purpose: Windows reserves blocks there (`netsh interface ipv4 show excludedportrange protocol=tcp`)
and Docker cannot publish a reserved port; set `SCAN_DB_PORT` / `SCAN_API_PORT` if one is taken.

Semgrep, Bandit and the Trivy config scan read a snapshot of the committed HEAD (`git archive`), so commit before a run.

## How to run

From the repository root, in Git Bash or WSL, with Docker running, after the full suites and E2E of the test release
(ZAP is heavy: do not run it while another pytest run is going on):

```bash
bash scripts/security_scan.sh --release 0.10.96            # everything, then SUMMARY.md
bash scripts/security_scan.sh --release 0.10.96 static     # one group
bash scripts/security_scan.sh --release 0.10.96 zap-api summary   # single steps
```

On the self-hosted runner: Actions -> "Security scans (manual)" -> Run workflow, with the release name. The reports
stay on the runner in `~/security-reports/<release>/`.

Optional settings: `ZAP_AUTH_HEADER` and `ZAP_AUTH_HEADER_VALUE` for an authenticated API scan (also used by
Schemathesis), `ZAP_MAX_MINUTES` (30), `SCHEMATHESIS_MAX_EXAMPLES` (10), `SCAN_EXTRA_IMAGES` (more images for Trivy,
e.g. a built `mdarix/web` image), `PYTHON` (interpreter for the cross-tenant tests and the summary).

## After the run

1. Open `SUMMARY.md`. For each Critical or High, fill in the decision line (fix now, fix later with a date, false
   positive, accepted risk). The deploy-blocking rules are in the approved scan plan.
2. A reviewed false positive goes into `infrastructure/security-scan/allowlist.txt` once, with its reason, reviewer and
   date; then re-run `bash scripts/security_scan.sh --release <release> summary`.
3. A real secret found by Gitleaks is rotated first, then removed.
