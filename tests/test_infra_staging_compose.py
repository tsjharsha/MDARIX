"""Static guarantees of the Oracle staging layer (docker-compose.staging-oracle.yml, docs/runbooks/STAGING_ORACLE.md).

Like tests/test_infra_compose.py these read the files only (no Docker). Staging runs its own Postgres, so a change
that publishes the database, lets it accept a connection without TLS or a password, hands its administrator password
to another service, or loses a limit, a health check or bounded logs fails here by name.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
STAGING = yaml.safe_load((ROOT / "docker-compose.staging-oracle.yml").read_text(encoding="utf-8"))
PRODUCTION = yaml.safe_load((ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8"))
POSTGRES = STAGING["services"]["postgres"]
PREPARE = (ROOT / "infrastructure" / "staging" / "prepare-database.sh").read_text(encoding="utf-8")
PG_HBA = [
    line.split()
    for line in (ROOT / "infrastructure" / "staging" / "pg_hba.conf").read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.lstrip().startswith("#")
]


def _settings() -> dict[str, str]:
    """The ``-c name=value`` settings of the postgres command."""
    command = POSTGRES["command"]
    return dict(command[i + 1].split("=", 1) for i, word in enumerate(command) if word == "-c")


def test_staging_only_adds_the_database_and_adjusts_existing_services():
    assert set(STAGING["services"]) - set(PRODUCTION["services"]) == {"postgres"}


def test_third_party_images_are_pinned_by_digest_and_built_for_arm():
    assert re.fullmatch(r"pgvector/pgvector:pg16@sha256:[0-9a-f]{64}", POSTGRES["image"])
    # The Debian-based ClamAV image is the one published for ARM (clamav/clamav is x86-64 only).
    assert re.fullmatch(r"clamav/clamav-debian:[\d.]+@sha256:[0-9a-f]{64}", STAGING["services"]["clamav"]["image"])


def test_the_database_is_private():
    assert "ports" not in POSTGRES and "expose" not in POSTGRES
    assert POSTGRES["networks"] == ["internal"]


def test_the_database_requires_tls_and_reads_the_staging_access_rules():
    settings = _settings()
    assert settings["ssl"] == "on"
    assert settings["ssl_min_protocol_version"] in {"TLSv1.2", "TLSv1.3"}
    assert settings["hba_file"] == "/etc/mdarix-db/pg_hba.conf"
    assert settings["password_encryption"] == "scram-sha-256"
    mounts = {volume.split(":")[1]: volume.split(":")[0] for volume in POSTGRES["volumes"] if volume.startswith("./")}
    assert mounts[settings["ssl_cert_file"]] == "./staging-secrets/db-tls/server.crt"
    assert mounts[settings["ssl_key_file"]] == "./staging-secrets/db-tls/server.key"
    assert mounts[settings["hba_file"]] == "./infrastructure/staging/pg_hba.conf"
    assert all(volume.endswith(":ro") for volume in POSTGRES["volumes"] if volume.startswith("./"))


def test_network_connections_need_tls_and_a_password():
    methods = {(rule[0], rule[-1]) for rule in PG_HBA}
    assert ("local", "peer") in methods
    assert {rule[-1] for rule in PG_HBA if rule[0] == "hostssl"} == {"scram-sha-256"}
    assert {rule[-1] for rule in PG_HBA if rule[0] == "hostnossl"} == {"reject"}
    assert not [rule for rule in PG_HBA if rule[0] == "host"], (
        "a plain 'host' rule would accept connections without TLS"
    )
    assert not [rule for rule in PG_HBA if rule[-1] in {"trust", "password", "md5"}]


def test_only_the_database_receives_its_administrator_password():
    assert POSTGRES["environment"]["POSTGRES_PASSWORD_FILE"] == "/run/secrets/postgres_admin_password"
    assert "POSTGRES_PASSWORD" not in POSTGRES["environment"]
    assert STAGING["secrets"]["postgres_admin_password"]["file"] == "./staging-secrets/postgres-admin-password"
    holders = [name for name, service in STAGING["services"].items() if service.get("secrets")]
    assert holders == ["postgres"]
    assert not any(service.get("secrets") for service in PRODUCTION["services"].values())


def test_the_database_has_limits_bounded_logs_and_a_health_check():
    assert POSTGRES["mem_limit"] and POSTGRES["cpus"]
    assert POSTGRES["logging"]["options"]["max-size"] and POSTGRES["logging"]["options"]["max-file"]
    # Run as the postgres user: the socket rule is "peer", so as root every check would log a failed login.
    assert POSTGRES["healthcheck"]["test"][:3] == ["CMD", "gosu", "postgres"]
    assert "pg_isready" in POSTGRES["healthcheck"]["test"]
    assert POSTGRES["security_opt"] == ["no-new-privileges:true"]


def test_the_schema_job_waits_for_the_database():
    assert STAGING["services"]["migrate"]["depends_on"]["postgres"] == {"condition": "service_healthy"}


def test_the_prepare_script_writes_what_compose_and_the_application_read():
    # The certificate names the host the application connects to (POSTGRES_HOST=postgres, verify-full) ...
    assert "subjectAltName = DNS:postgres" in PREPARE
    # ... and the files land where compose mounts them and where the application trusts the CA.
    for path in (
        "staging-secrets/postgres-admin-password",
        '"${TLS}/server.key"',
        '"${TLS}/server.crt"',
        "certs/db-ca.pem",
    ):
        assert path in PREPARE, path
    assert 'TLS="${SECRETS}/db-tls"' in PREPARE and "SECRETS=staging-secrets" in PREPARE
    # The key belongs to the image's postgres user, which refuses a key that others can read.
    assert "POSTGRES_UID=999" in PREPARE
    assert 'install -m 600 -o "${POSTGRES_UID}" -g "${POSTGRES_UID}" "${WORK}/server.key"' in PREPARE


def test_staging_secrets_never_reach_git():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "/staging-secrets/" in ignored and "/certs/" in ignored
