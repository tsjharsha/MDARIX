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
SCRIPTS = ["run_outbox_worker.py", "run_scheduler.py", "create_platform_admin.py", "set_rls_system_token.py"]
# Names read from the environment: os.getenv / os.environ[...] / .get / .setdefault, or config_check's helpers.
NAME = re.compile(
    r"(?:getenv|environ(?:\.get|\.setdefault)?|_get|_problem|setenv)\s*[\[(]\s*[\"']((?:MDARIX|POSTGRES|RESEND)_[A-Z0-9_]+)[\"']"
)
FLAG = re.compile(r"_FLAG\s*=\s*[\"']((?:MDARIX)_[A-Z0-9_]+)[\"']")
# Names built at runtime (one per provider or plane) are documented by their pattern.
DYNAMIC_PREFIXES = ("MDARIX_GENAI_", "MDARIX_DATA_PLANE_", "MDARIX_CONNECTOR_SECRET_")


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
        if f"`{name}`" not in reference and name not in reference and not name.endswith("_")
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
    # config_check inspects every MDARIX_DATA_PLANE_*_OWNER variable dynamically;
    # ``MDARIX_DATA_PLANE_`` is a prefix, not a setting that can appear in an env file.
    required = {name for name in required if name not in DYNAMIC_PREFIXES}
    missing = sorted(name for name in required if f"{name}=" not in template)
    assert not missing, "Add to .env.production.example: " + ", ".join(missing)
