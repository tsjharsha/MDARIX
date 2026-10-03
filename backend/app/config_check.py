"""Refuse to start a staging or production server whose configuration is missing or unsafe.

``problems()`` lists every issue at once (so an operator fixes them in one pass); the API calls ``enforce()`` at
startup and exits when the list is not empty. Local development and test runs are never blocked: they use local
defaults on purpose. Run ``python -m backend.app.config_check`` on a server to see the list without starting it.
"""

from __future__ import annotations

import base64
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from backend.app.runtime_env import environment, is_production_like


def _get(name: str) -> str:
    return os.getenv(name, "").strip()


def _aes_key_problem(name: str) -> str | None:
    raw = _get(name)
    if not raw:
        return f"{name} is not set (URL-safe base64 of 32 random bytes)"
    try:
        key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    except (ValueError, TypeError):
        return f"{name} is not valid base64"
    if len(key) not in {16, 24, 32}:
        return f"{name} must decode to 16, 24 or 32 bytes"
    return None


def _secret_problem(name: str, minimum: int = 32) -> str | None:
    value = _get(name)
    if len(value) < minimum:
        return f"{name} must be a random value of at least {minimum} characters"
    if "change" in value.lower() or "example" in value.lower():
        return f"{name} still holds a placeholder value"
    return None


def _email_problem(name: str) -> str | None:
    value = _get(name)
    if "@" not in value or value.startswith("@") or value.endswith("@"):
        return f"{name} must be an email address"
    return None


def problems() -> list[str]:
    """Every configuration problem that makes this server unsafe or broken for customers (empty when fine)."""
    if not is_production_like():
        return []
    found: list[str] = []

    def add(problem: str | None) -> None:
        if problem:
            found.append(problem)

    app_url = urlparse(_get("MDARIX_APP_URL"))
    if app_url.scheme != "https" or not app_url.netloc:
        add("MDARIX_APP_URL must be the https address people use, e.g. https://app.example.com")

    if not _get("MDARIX_DB_RUNTIME_USER") or not _get("MDARIX_DB_RUNTIME_PASSWORD"):
        add("MDARIX_DB_RUNTIME_USER and MDARIX_DB_RUNTIME_PASSWORD must be set (row-level security needs them)")
    if _get("POSTGRES_SSLMODE").lower() not in {"require", "verify-ca", "verify-full"}:
        add("POSTGRES_SSLMODE must be require, verify-ca or verify-full")

    add(_secret_problem("MDARIX_RLS_SYSTEM_TOKEN"))
    from backend.app.db.tenant_scope import LOCAL_SYSTEM_TOKEN

    if _get("MDARIX_RLS_SYSTEM_TOKEN") == LOCAL_SYSTEM_TOKEN:
        add("MDARIX_RLS_SYSTEM_TOKEN must not be the public local-development value")
    add(_aes_key_problem("MDARIX_MFA_ENCRYPTION_KEY"))
    add(_aes_key_problem("MDARIX_CONNECTOR_ENCRYPTION_KEY"))
    add(_secret_problem("MDARIX_DEMO_REQUEST_SALT"))
    add(_secret_problem("MDARIX_RATE_LIMIT_SALT"))
    add(_secret_problem("MDARIX_OBJECT_STORAGE_SIGNING_SECRET"))
    provider = (_get("MDARIX_OBJECT_STORAGE_PROVIDER") or "local").lower()
    if provider == "s3":
        if not _get("MDARIX_OBJECT_STORAGE_BUCKET"):
            add("MDARIX_OBJECT_STORAGE_BUCKET must be set for the s3 provider")
    elif provider == "local":
        add(_aes_key_problem("MDARIX_OBJECT_STORAGE_ENCRYPTION_KEY"))
    else:
        add("MDARIX_OBJECT_STORAGE_PROVIDER must be s3 or local")
    if not _get("MDARIX_CLAMD_HOST") and not _get("MDARIX_MALWARE_SCANNER_COMMAND"):
        add("Uploaded files must be virus-scanned: set MDARIX_CLAMD_HOST (ClamAV) or MDARIX_MALWARE_SCANNER_COMMAND")

    for name in ("MDARIX_SMTP_HOST", "MDARIX_SMTP_USERNAME", "MDARIX_SMTP_PASSWORD"):
        if not _get(name):
            add(f"{name} must be set: without email no one can be invited or reset a password")
    add(_email_problem("MDARIX_SMTP_FROM"))
    add(_email_problem("MDARIX_SUPPORT_EMAIL"))
    add(_email_problem("MDARIX_PRIVACY_EMAIL"))
    for name in ("MDARIX_COMPANY_LEGAL_NAME", "MDARIX_COMPANY_ADDRESS"):
        if not _get(name):
            add(f"{name} must be set: it appears in the legal pages, the footer and every email")
    if _get("MDARIX_LEGAL_TEXT_APPROVED").lower() != "true":
        add("MDARIX_LEGAL_TEXT_APPROVED must be true once a lawyer has approved the privacy policy and terms")
    add(_legal_documents_problem())

    if _get("MDARIX_RATE_LIMITS_ENABLED").lower() in {"0", "false", "no"}:
        add("MDARIX_RATE_LIMITS_ENABLED must not be false")
    for name in ("MDARIX_ALLOW_LEGACY_AUTH_FALLBACK", "MDARIX_SIMULATE_DEPENDENCY_FAILURE"):
        if _get(name):
            add(f"{name} must not be set outside local development")
    scrypt = _get("MDARIX_PASSWORD_SCRYPT_LOG2_N")
    if scrypt and (not scrypt.isdigit() or int(scrypt) < 17):
        add("MDARIX_PASSWORD_SCRYPT_LOG2_N must be at least 17 (or unset)")
    if _get("MDARIX_ENABLE_API_DOCS").lower() == "true":
        add("MDARIX_ENABLE_API_DOCS must not be true")

    from genai.policy import configuration_problems as ai_problems

    found.extend(ai_problems())
    if _get("MDARIX_RLS_SYSTEM_TOKEN"):
        add(_database_token_problem())
    return found


def _legal_documents_problem() -> str | None:
    """The website must show the approved privacy policy, terms and trial agreement (backend/app/site_info.py)."""
    from backend.app.site_info import LEGAL_DOCUMENTS

    folder = _get("MDARIX_LEGAL_DIR")
    if not folder:
        return "MDARIX_LEGAL_DIR must be the folder holding the approved privacy.md, terms.md and trial-agreement.md"
    missing = [name for name in LEGAL_DOCUMENTS.values() if not (Path(folder) / name).is_file()]
    if missing:
        return f"MDARIX_LEGAL_DIR is missing {', '.join(missing)}"
    return None


def _database_token_problem() -> str | None:
    """The database must hold this server's system-scope token, or platform administration would see nothing."""
    try:
        from backend.app.db.session import runtime_engine
        from backend.app.db.tenant_scope import system_token_accepted

        with runtime_engine.connect() as connection:
            if system_token_accepted(connection):
                return None
    except Exception as exc:  # the database itself is checked by readiness; report what is known
        return f"Could not check MDARIX_RLS_SYSTEM_TOKEN against the database ({type(exc).__name__})"
    return "The database does not hold MDARIX_RLS_SYSTEM_TOKEN: run scripts/set_rls_system_token.py"


def enforce() -> None:
    """Raise SystemExit listing every problem when this staging/production server is not safe to start."""
    found = problems()
    if found:
        lines = "\n".join(f"  - {item}" for item in found)
        raise SystemExit(f"MDARIX will not start in {environment()}: fix the configuration first.\n{lines}")


if __name__ == "__main__":
    issues = problems()
    if not is_production_like():
        print(f"MDARIX_ENV={environment()}: configuration checks apply to staging and production only.")
    for issue in issues:
        print(f"- {issue}")
    sys.exit(1 if issues else 0)
