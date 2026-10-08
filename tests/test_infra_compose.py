"""Static guarantees of the production deployment files (docker-compose.prod.yml, Caddyfile, images, workflows).

These read the files only (no Docker): CI's prod-compose-config and prod-stack jobs prove the same stack resolves and
runs. A change that quietly hands owner credentials to a long-running service, drops a health check or a resource
limit, or makes Caddy publish readiness detail fails here by name.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = yaml.safe_load((ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8"))
SERVICES = COMPOSE["services"]
LONG_RUNNING = ("api", "worker", "scheduler", "web", "clamav")
CADDYFILE = (ROOT / "infrastructure" / "docker" / "Caddyfile").read_text(encoding="utf-8")


def _env_files(service: dict) -> list[str]:
    value = service.get("env_file") or []
    return [value] if isinstance(value, str) else list(value)


def test_only_the_migrate_and_backup_jobs_load_the_owner_settings():
    for name, service in SERVICES.items():
        loads = ".env.migrate" in _env_files(service)
        assert loads == (name in {"migrate", "backup"}), name
    for name in ("api", "worker", "scheduler"):
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


@pytest.mark.parametrize("name,grace", [("api", "30s"), ("worker", "60s"), ("scheduler", "60s")])
def test_services_stop_gracefully(name, grace):
    assert SERVICES[name]["stop_grace_period"] == grace


@pytest.mark.parametrize(
    "name,memory",
    [("clamav", "2g"), ("api", "2g"), ("worker", "1536m"), ("scheduler", "1g"), ("web", "256m"), ("backup", "1g")],
)
def test_every_service_has_memory_and_cpu_limits(name, memory):
    assert SERVICES[name]["mem_limit"] == memory
    assert float(SERVICES[name]["cpus"]) > 0


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


def test_the_scheduler_health_check_reads_the_heartbeat_the_scheduler_writes():
    from backend.app.scheduler import DEFAULT_HEARTBEAT_FILE

    scheduler = SERVICES["scheduler"]
    assert scheduler["environment"]["MDARIX_SCHEDULER_HEARTBEAT_FILE"] == DEFAULT_HEARTBEAT_FILE
    test = " ".join(scheduler["healthcheck"]["test"])
    assert DEFAULT_HEARTBEAT_FILE in test and "< 120" in test


def test_the_web_container_is_locked_down():
    web = SERVICES["web"]
    assert web["read_only"] is True
    assert web["cap_drop"] == ["ALL"] and web["cap_add"] == ["NET_BIND_SERVICE"]
    assert "no-new-privileges:true" in web["security_opt"]
    assert any(item.startswith("/tmp") for item in web["tmpfs"])


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
    for name in ("migrate", "api", "worker", "scheduler", "backup"):
        assert any(str(volume).endswith(":/etc/mdarix/certs:ro") for volume in SERVICES[name]["volumes"]), name


def test_the_embedding_model_is_pinned_to_a_commit():
    dockerfile = (ROOT / "Dockerfile.api").read_text(encoding="utf-8")
    assert re.search(r"ARG EMBEDDING_REVISION=[0-9a-f]{40}\n", dockerfile)
    assert "apt-get upgrade" in dockerfile


def test_caddy_keeps_readiness_internal_and_publishes_the_status():
    assert "@internal_health path /health /health/ready" in CADDYFILE
    assert "handle /health/status {" in CADDYFILE
    assert 'header >Cache-Control "no-store"' in CADDYFILE
    assert 'Cross-Origin-Resource-Policy "same-origin"' in CADDYFILE
    # Single-use tokens in links never reach the access log.
    assert re.search(r"request>uri query \{\s*delete token\s*\}", CADDYFILE)


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
