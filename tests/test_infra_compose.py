"""Static guarantees of the production deployment files (docker-compose.prod.yml, Caddyfile, images, workflows).

These read the files only (no Docker): CI's prod-compose-config and prod-stack jobs prove the same stack resolves and
runs. A change that quietly hands owner credentials to a long-running service, drops a health check or a resource
limit, or makes Caddy publish readiness detail fails here by name.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = yaml.safe_load((ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8"))
SERVICES = COMPOSE["services"]
LONG_RUNNING = ("api", "background", "web", "clamav")
CADDYFILE = (ROOT / "infrastructure" / "docker" / "Caddyfile").read_text(encoding="utf-8")


def _env_files(service: dict) -> list[str]:
    value = service.get("env_file") or []
    return [value] if isinstance(value, str) else list(value)


def test_only_the_migrate_and_backup_jobs_load_the_owner_settings():
    for name, service in SERVICES.items():
        loads = ".env.migrate" in _env_files(service)
        assert loads == (name in {"migrate", "backup"}), name
    for name in ("api", "background"):
        assert _env_files(SERVICES[name]) == [".env.production"], name
    # Caddy needs no application settings at all.
    assert not _env_files(SERVICES["web"])


def test_no_service_names_the_owner_password_in_its_environment():
    text = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    for name, service in SERVICES.items():
        environment = service.get("environment") or {}
        assert "MDARIX_DB_OWNER_PASSWORD" not in environment, name
        assert "POSTGRES_PASSWORD" not in environment, name
    # The migrate job maps the owner's credentials itself, from its own env files (not compose interpolation, which
    # would need the owner password in .env.production).
    assert not re.search(r"(?<!\$)\$\{MDARIX_DB_OWNER_PASSWORD", text)  # "$${" is a literal for the shell
    entrypoint = " ".join(SERVICES["migrate"]["entrypoint"])
    assert 'POSTGRES_PASSWORD="$$MDARIX_DB_OWNER_PASSWORD"' in entrypoint


@pytest.mark.parametrize("name,grace", [("api", "30s"), ("background", "60s")])
def test_services_stop_gracefully(name, grace):
    assert SERVICES[name]["stop_grace_period"] == grace


@pytest.mark.parametrize(
    "name,memory",
    [("clamav", "1536m"), ("api", "2g"), ("background", "1536m"), ("web", "256m"), ("backup", "1g")],
)
def test_every_service_has_memory_and_cpu_limits(name, memory):
    assert SERVICES[name]["mem_limit"] == memory
    assert float(SERVICES[name]["cpus"]) > 0


def test_the_background_service_yields_the_cpu_to_the_api_and_a_busy_api_worker_is_not_killed():
    # An import's embeddings run in the background service (0.10.42): when both want the CPU, the API comes first.
    assert int(SERVICES["background"]["cpu_shares"]) < 1024 and "cpu_shares" not in SERVICES["api"]
    # uvicorn's default worker health check (5 s) restarted busy workers after a large import, dropping requests.
    command = json.loads(
        re.search(r"^CMD (\[.*\])$", (ROOT / "Dockerfile.api").read_text(encoding="utf-8"), re.M).group(1)
    )
    assert int(command[command.index("--timeout-worker-healthcheck") + 1]) >= 30


def test_every_service_keeps_bounded_logs():
    for name, service in SERVICES.items():
        logging = service.get("logging") or {}
        assert logging.get("driver") == "json-file", name
        assert logging["options"]["max-size"] and logging["options"]["max-file"], name


def test_every_long_running_service_has_a_health_check():
    for name in LONG_RUNNING:
        healthcheck = SERVICES[name].get("healthcheck")
        if name == "api":
            continue  # the image's HEALTHCHECK (Dockerfile.api)
        assert healthcheck and not healthcheck.get("disable"), name
    assert "HEALTHCHECK" in (ROOT / "Dockerfile.api").read_text(encoding="utf-8")


def test_the_background_health_check_needs_both_heartbeats():
    from backend.app.scheduler import DEFAULT_HEARTBEAT_FILE

    background = SERVICES["background"]
    environment = background["environment"]
    assert environment["MDARIX_SCHEDULER_HEARTBEAT_FILE"] == DEFAULT_HEARTBEAT_FILE
    test = " ".join(background["healthcheck"]["test"])
    assert DEFAULT_HEARTBEAT_FILE in test and "< 120" in test
    assert environment["MDARIX_OUTBOX_HEARTBEAT_FILE"] in test and "< 60" in test
    assert "worker and scheduler" in test


def test_one_background_service_runs_the_worker_and_the_scheduler():
    """The MVP slim-down: one container for the outbox worker and the scheduler (scripts/run_background.py)."""
    assert "worker" not in SERVICES and "scheduler" not in SERVICES
    background = SERVICES["background"]
    assert background["command"] == ["python", "scripts/run_background.py"]
    supervisor = _load("run_background")
    assert [path.name for _, path in supervisor.CHILDREN] == ["run_outbox_worker.py", "run_scheduler.py"]
    assert all(path.exists() for _, path in supervisor.CHILDREN)
    # Both loops' volumes: uploaded objects (scans, exports) and the report folder the API shares.
    volumes = [str(volume) for volume in background["volumes"]]
    assert any(volume.startswith("objects:") for volume in volumes)
    assert any(volume.startswith("reports:") for volume in volumes)
    assert supervisor.GRACE_SECONDS < 60  # inside the container's stop_grace_period


def test_clamav_reloads_its_signatures_without_a_second_copy_in_memory():
    assert SERVICES["clamav"]["environment"]["CLAMD_CONF_ConcurrentDatabaseReload"] == "no"


def _gigabytes(value: str) -> float:
    number, unit = re.fullmatch(r"(\d+)([mg])", value).groups()
    return int(number) / (1024 if unit == "m" else 1)


def test_the_long_running_services_fit_the_slim_server():
    """5.25 GB of memory limits for the services that always run, down from 6.75 GB (MVP slim-down plan); the nightly
    backup job's 1 GB comes on top and still leaves the operating system room on an 8 GB server."""
    total = sum(_gigabytes(SERVICES[name]["mem_limit"]) for name in LONG_RUNNING)
    assert total == pytest.approx(5.25)


def test_the_web_container_is_locked_down():
    web = SERVICES["web"]
    assert web["read_only"] is True
    # Caddy runs as a user, not root, with no capability (SEC-10, 0.10.47): its own network namespace lets it bind 80
    # and 443 instead of a file capability, which no-new-privileges would refuse to a non-root user.
    assert web["cap_drop"] == ["ALL"] and "cap_add" not in web
    assert web["sysctls"] == {"net.ipv4.ip_unprivileged_port_start": "80"}
    assert "no-new-privileges:true" in web["security_opt"]
    assert any(item.startswith("/tmp") for item in web["tmpfs"])
    dockerfile = (ROOT / "Dockerfile.web").read_text(encoding="utf-8")
    final_stage = dockerfile[dockerfile.rindex("\nFROM ") :]
    assert final_stage.rstrip().endswith("USER caddy")
    assert "adduser -S -D -H -u 10002 -G caddy" in final_stage and "setcap" not in final_stage


def test_caddys_volumes_become_caddys_before_it_starts_and_nothing_else_runs_as_root():
    # Volumes a root Caddy wrote (0.10.46 and earlier: the certificates and the ACME account) are given to the caddy
    # user by a one-shot job before every start of web; it may only change owners, and has no network.
    job = SERVICES["web-volumes"]
    assert SERVICES["web"]["depends_on"]["web-volumes"] == {"condition": "service_completed_successfully"}
    assert job["image"] == SERVICES["web"]["image"] and job["entrypoint"] == ["caddy-volumes"]
    assert job["user"] == "0:0" and job["network_mode"] == "none" and job["read_only"] is True
    assert job["cap_drop"] == ["ALL"] and job["cap_add"] == ["CHOWN", "DAC_READ_SEARCH"]
    assert "no-new-privileges:true" in job["security_opt"]
    assert sorted(job["volumes"]) == ["caddy_config:/config", "caddy_data:/data"]
    script = (ROOT / "infrastructure" / "docker" / "caddy-volumes.sh").read_text(encoding="utf-8")
    assert 'owner="${1:-10002:10002}"' in script and "chown -h" in script
    assert "rm " not in script and "chmod" not in script


def test_third_party_images_are_pinned_by_digest():
    assert re.fullmatch(r"clamav/clamav:[\d.]+@sha256:[0-9a-f]{64}", SERVICES["clamav"]["image"])
    for dockerfile in (
        "Dockerfile.api",
        "Dockerfile.web",
        "Dockerfile.worker",
        "infrastructure/docker/backup/Dockerfile",
    ):
        for line in (ROOT / dockerfile).read_text(encoding="utf-8").splitlines():
            if line.startswith("FROM "):
                assert "@sha256:" in line, f"{dockerfile}: {line}"


def test_the_database_ca_is_mounted_wherever_the_database_is_reached():
    for name in ("migrate", "api", "background", "backup"):
        assert any(str(volume).endswith(":/etc/mdarix/certs:ro") for volume in SERVICES[name]["volumes"]), name


def test_the_embedding_model_is_pinned_to_a_commit():
    dockerfile = (ROOT / "Dockerfile.api").read_text(encoding="utf-8")
    assert re.search(r"ARG EMBEDDING_REVISION=[0-9a-f]{40}\n", dockerfile)
    assert "apt-get upgrade" in dockerfile


def test_caddy_keeps_readiness_internal_and_publishes_the_status():
    assert "@internal_health path /health /health/ready" in CADDYFILE
    assert "handle /health/status {" in CADDYFILE
    # The release number is public (0.10.71): without this route the website answers /health/version with its 404.
    assert "handle /health/version {" in CADDYFILE
    assert 'header >Cache-Control "no-store"' in CADDYFILE
    assert 'Cross-Origin-Resource-Policy "same-origin"' in CADDYFILE
    # Single-use tokens in links and search terms never reach the access log: the query string is dropped whole.
    assert re.search(r'request>uri regexp "\\\?\.\*\$" ""', CADDYFILE)
    assert "request>headers>Referer delete" in CADDYFILE


def _fastapi_reads_as_json(content_type: str | None) -> bool:
    """FastAPI's own rule (fastapi/routing.py): no Content-Type, or application/json or application/*+json."""
    import email.message

    if not content_type:
        return True
    message = email.message.Message()
    message["content-type"] = content_type
    subtype = message.get_content_subtype()
    return message.get_content_maintype() == "application" and (subtype == "json" or subtype.endswith("+json"))


def test_caddy_caps_every_body_the_api_reads_as_json_at_1_mib_and_leaves_uploads_at_25_mb():
    """An anonymous oversized JSON body is refused at the front door, before it can tie up an API worker; files
    (multipart, CSV, Excel) keep the upload limit."""
    assert re.search(r"request_body \{\s*max_size 25MB\s*\}", CADDYFILE)
    matcher = re.search(r"@json_body header_regexp Content-Type (\S+)\n", CADDYFILE)
    assert matcher and re.search(r"request_body @json_body \{\s*max_size 1MiB\s*\}", CADDYFILE)
    assert "@no_content_type header !Content-Type" in CADDYFILE
    assert re.search(r"request_body @no_content_type \{\s*max_size 1MiB\s*\}", CADDYFILE)
    # The pattern (RE2 in Caddy; the same meaning in Python for this pattern) catches exactly what FastAPI parses.
    pattern = re.compile(matcher.group(1))
    for content_type in (
        "application/json",
        "application/json; charset=utf-8",
        "Application/JSON",
        " application/json",
        "application/problem+json",
        "application/vnd.api+json",
        "",
        "multipart/form-data; boundary=x",
        "text/csv",
        "text/csv; charset=utf-8",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/octet-stream",
        "text/plain",
        "application/x-www-form-urlencoded",
    ):
        assert bool(pattern.search(content_type)) == _fastapi_reads_as_json(content_type), content_type


def test_caddy_is_public_without_www_unless_told_otherwise():
    environment = SERVICES["web"]["environment"]
    # ":-" also replaces an empty value, which Caddy would read as a snippet name that does not exist.
    assert environment["MDARIX_SITE_ACCESS"] == "${MDARIX_SITE_ACCESS:-public}"
    assert environment["MDARIX_WWW_REDIRECT"] == "${MDARIX_WWW_REDIRECT:-off}"
    assert "import site_access_{$MDARIX_SITE_ACCESS:public}" in CADDYFILE
    assert "import www_redirect_{$MDARIX_WWW_REDIRECT:off}" in CADDYFILE
    assert re.search(r"\(site_access_public\) \{\s*\}", CADDYFILE)
    assert re.search(r"\(www_redirect_off\) \{\s*\}", CADDYFILE)


def test_a_private_site_asks_for_the_login_everywhere_but_the_monitors():
    private = re.search(r"\(site_access_private\) \{(.*?)\n\}", CADDYFILE, re.S).group(1)
    assert "@needs_login not path /health/live /health/status /health/version" in private
    assert "basic_auth @needs_login {" in private
    assert "{$MDARIX_SITE_LOGIN_USER} {$MDARIX_SITE_LOGIN_HASH}" in private
    redirect = re.search(r"\(www_redirect_on\) \{(.*?)\n\}", CADDYFILE, re.S).group(1)
    assert "www.{$MDARIX_DOMAIN} {" in redirect
    assert "redir https://{$MDARIX_DOMAIN}{uri} permanent" in redirect


def test_caddy_redirects_the_other_domains_to_the_main_one_and_none_by_default():
    environment = SERVICES["web"]["environment"]
    # Empty by default: the names join the site's own address list, so an empty value leaves MDARIX_DOMAIN alone.
    assert environment["MDARIX_REDIRECT_DOMAINS"] == "${MDARIX_REDIRECT_DOMAINS:-}"
    site = re.search(r"^\{\$MDARIX_DOMAIN\} \{\$MDARIX_REDIRECT_DOMAINS\} \{\n(.*?)\n\}", CADDYFILE, re.S | re.M)
    assert site, "the main site must list MDARIX_DOMAIN and then MDARIX_REDIRECT_DOMAINS"
    body = site.group(1)
    # Every name but the main domain is sent to it, with the path and the query (Caddy's {uri}), permanently; a
    # redirect name never reaches the pages, the API or the login of a private site.
    assert "@redirect_domain not host {$MDARIX_DOMAIN}" in body
    assert "redir @redirect_domain https://{$MDARIX_DOMAIN}{uri} permanent" in body
    lines = [line.strip() for line in body.splitlines() if line.strip() and not line.strip().startswith("#")]
    assert lines[:2] == [
        "@redirect_domain not host {$MDARIX_DOMAIN}",
        "redir @redirect_domain https://{$MDARIX_DOMAIN}{uri} permanent",
    ]
    # The only other site blocks are the snippets' (www redirect): no second definition of the main domain.
    assert len(re.findall(r"^\{\$MDARIX_DOMAIN\}", CADDYFILE, re.M)) == 1
    template = (ROOT / ".env.production.example").read_text(encoding="utf-8")
    assert re.search(r"^MDARIX_REDIRECT_DOMAINS=$", template, re.M)
    reference = (ROOT / "docs" / "runbooks" / "ENVIRONMENT_VARIABLES.md").read_text(encoding="utf-8")
    assert "`MDARIX_REDIRECT_DOMAINS`" in reference


def test_every_action_in_the_workflows_is_pinned_to_a_commit():
    for workflow in ("ci.yml", "codeql.yml", "release.yml"):
        text = (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
        for match in re.finditer(r"uses:\s*(\S+)", text):
            assert re.search(r"@[0-9a-f]{40}$", match.group(1)), f"{workflow}: {match.group(1)}"


def test_the_version_file_is_a_semantic_version():
    assert re.fullmatch(r"\d+\.\d+\.\d+\n?", (ROOT / "VERSION").read_text(encoding="utf-8"))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_runtime_role_script_names_only_attributes_it_must_remove():
    """PostgreSQL 16 lets only a superuser name SUPERUSER/BYPASSRLS in ALTER ROLE, so a clean role on a managed
    database (owner not a superuser) must get a statement without them."""
    runtime_role = _load("configure_runtime_role")
    clean = SimpleNamespace(rolsuper=False, rolbypassrls=False, rolcreatedb=False, rolcreaterole=False)
    assert runtime_role._removals(clean) == ""
    dirty = SimpleNamespace(rolsuper=True, rolbypassrls=True, rolcreatedb=False, rolcreaterole=True)
    assert runtime_role._removals(dirty) == "NOSUPERUSER NOBYPASSRLS NOCREATEROLE "


WORKFLOW = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
HEAVY_JOBS = ("dedicated-plane", "dataplane-tests", "deployment-roles", "container-validation", "integration")


def test_pull_requests_run_the_fast_checks_and_the_heavy_ones_run_after_merge_and_nightly():
    jobs = WORKFLOW["jobs"]
    triggers = WORKFLOW[True] if True in WORKFLOW else WORKFLOW["on"]
    assert triggers["schedule"] == [{"cron": "41 2 * * *"}]
    for name in HEAVY_JOBS:
        assert jobs[name]["if"] == "github.event_name != 'pull_request'", name
    for name in ("backend", "frontend", "browser", "security", "image-scan", "prod-compose-config", "prod-stack"):
        assert "if" not in jobs[name], name
    gate = " ".join(step.get("run", "") for step in jobs["release-report"]["steps"])
    for name in HEAVY_JOBS:
        assert f'heavy "${{{{ needs.{name}.result }}}}"' in gate, name
    assert 'test "${{ github.event_name }}" = pull_request && test "$1" = skipped' in gate
    browser = " ".join(step.get("run", "") for step in jobs["browser"]["steps"])
    assert "github.event_name == 'pull_request' && '--project=chromium'" in browser


def test_the_production_stack_job_starts_the_background_service():
    steps = " ".join(step.get("run", "") for step in WORKFLOW["jobs"]["prod-stack"]["steps"])
    assert "up -d --no-build --wait --wait-timeout 1200 api background web" in steps
    assert "exec -T background python scripts/run_scheduler.py --once" in steps


def test_dependabot_proposes_monthly_grouped_updates():
    config = yaml.safe_load((ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8"))
    assert all(update["schedule"] == {"interval": "monthly"} for update in config["updates"])
    grouped = {update["package-ecosystem"] for update in config["updates"] if update.get("groups")}
    assert {"pip", "npm", "github-actions"} <= grouped
