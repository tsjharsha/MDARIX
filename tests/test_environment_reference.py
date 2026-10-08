"""Every environment variable the server code reads is documented in docs/runbooks/ENVIRONMENT_VARIABLES.md."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE = [
    "backend",
    "auth",
    "genai",
    "ai",
    "ask_mdarix",
    "retrieval",
    "outbox",
    "object_storage",
    "communication",
    "reports",
    "integration",
    "access_control",
    "security",
    "evidence",
    "hypothesis_engine",
    "challenger",
    "trust_engine",
    "briefs",
]
SCRIPTS = [
    "run_outbox_worker.py",
    "run_scheduler.py",
    "create_platform_admin.py",
    "set_rls_system_token.py",
    "configure_runtime_role.py",
    "configure_backup_role.py",
    "reset_platform_admin_mfa.py",
    "validate_production_operations.py",
]
# Names read from the environment: os.getenv / os.environ[...] / .get / .setdefault, config_check's helpers
# (_get, _secret_problem, _integer_problem, ...) and typed readers such as outbox/worker.py's _env_int.
NAME = re.compile(
    r"(?:getenv|environ(?:\.get|\.setdefault)?|_get|_[a-z_]*problem|_env_[a-z]+|setenv)"
    r"\s*[\[(]\s*[\"']((?:MDARIX|POSTGRES|RESEND)_[A-Z0-9_]+)[\"']"
)
FLAG = re.compile(r"_FLAG\s*=\s*[\"']((?:MDARIX)_[A-Z0-9_]+)[\"']")
# Names built at runtime (one per provider or plane) are documented by their pattern.
DYNAMIC_PREFIXES = ("MDARIX_GENAI_", "MDARIX_DATA_PLANE_", "MDARIX_CONNECTOR_SECRET_")


def _is_prefix(name: str) -> bool:
    """``MDARIX_DATA_PLANE_`` in ``name.startswith("MDARIX_DATA_PLANE_")`` is the start of a family of names, not a
    setting: it can neither be documented as a row nor appear in an env file."""
    return name.endswith("_")


def _read_names() -> set[str]:
    files = [path for folder in CODE for path in (ROOT / folder).rglob("*.py")]
    files += [ROOT / "scripts" / name for name in SCRIPTS]
    names = set()
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "getenv" not in text and "environ" not in text and "_get(" not in text:
            continue
        names.update(NAME.findall(text))
        names.update(FLAG.findall(text))
    return names


def test_every_variable_the_code_reads_is_documented():
    reference = (ROOT / "docs" / "runbooks" / "ENVIRONMENT_VARIABLES.md").read_text(encoding="utf-8")
    missing = sorted(
        name
        for name in _read_names()
        if f"`{name}`" not in reference and name not in reference and not _is_prefix(name)
    )
    undocumented = [name for name in missing if not (name.startswith(DYNAMIC_PREFIXES) and name.count("_") > 3)]
    assert not undocumented, "Document these in docs/runbooks/ENVIRONMENT_VARIABLES.md: " + ", ".join(undocumented)


def test_the_production_template_names_every_required_setting():
    from backend.app import config_check

    template = (ROOT / ".env.production.example").read_text(encoding="utf-8")
    source = Path(config_check.__file__).read_text(encoding="utf-8")
    required = set(re.findall(r"\"((?:MDARIX|POSTGRES)_[A-Z0-9_]+)\"", source)) - {
        "MDARIX_RATE_LIMITS_ENABLED",
        "MDARIX_ALLOW_LEGACY_AUTH_FALLBACK",
        "MDARIX_SIMULATE_DEPENDENCY_FAILURE",
        "MDARIX_PASSWORD_SCRYPT_LOG2_N",
        "MDARIX_ENABLE_API_DOCS",
        "MDARIX_MALWARE_SCANNER_COMMAND",
        "MDARIX_OBJECT_STORAGE_BUCKET",
    }
    # config_check also refuses settings that must NOT be in this file (owner and backup credentials belong in
    # .env.migrate), and inspects families of names by prefix (MDARIX_DATA_PLANE_..._OWNER).
    required -= {"MDARIX_DB_OWNER_PASSWORD", "MDARIX_BACKUP_DB_PASSWORD"}
    required = {name for name in required if not _is_prefix(name)}
    missing = sorted(name for name in required if f"{name}=" not in template)
    assert not missing, "Add to .env.production.example: " + ", ".join(missing)


def _settings(path: Path) -> set[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return {line.split("=", 1)[0] for line in lines if "=" in line and not line.startswith("#")}


def test_owner_and_backup_secrets_live_only_in_the_migrate_template():
    """.env.production feeds every long-running service, which refuses these (config_check); .env.migrate feeds only
    the migrate and backup jobs (docker-compose.prod.yml)."""
    production = _settings(ROOT / ".env.production.example")
    migrate = _settings(ROOT / ".env.migrate.example")
    secrets = {"MDARIX_DB_OWNER_PASSWORD", "MDARIX_BACKUP_DB_PASSWORD", "AWS_SECRET_ACCESS_KEY"}
    assert not secrets & production, "Move to .env.migrate.example: " + ", ".join(sorted(secrets & production))
    assert secrets <= migrate, "Add to .env.migrate.example: " + ", ".join(sorted(secrets - migrate))
    # Names only: both templates leave every secret empty.
    for line in (ROOT / ".env.migrate.example").read_text(encoding="utf-8").splitlines():
        if line.split("=", 1)[0] in secrets:
            assert line.endswith("="), line


def test_every_backup_setting_is_documented():
    reference = (ROOT / "docs" / "runbooks" / "ENVIRONMENT_VARIABLES.md").read_text(encoding="utf-8")
    scripts = [ROOT / "infrastructure" / "docker" / "backup" / "backup.sh", ROOT / "scripts" / "check_backup_age.sh"]
    names = set()
    for script in scripts:
        names.update(re.findall(r"\$\{((?:MDARIX|AWS)_[A-Z0-9_]+)", script.read_text(encoding="utf-8")))
    missing = sorted(name for name in names if name not in reference and not name.startswith("MDARIX_DATA_PLANE_"))
    assert not missing, "Document these in docs/runbooks/ENVIRONMENT_VARIABLES.md: " + ", ".join(missing)
