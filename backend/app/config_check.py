"""Refuse to start a staging or production server whose configuration is missing or unsafe.

``problems()`` lists every issue at once (so an operator fixes them in one pass); the API calls ``enforce()`` at
startup and exits when the list is not empty. Local development and test runs are never blocked: they use local
defaults on purpose. Run ``python -m backend.app.config_check`` on a server to see the list without starting it;
``--offline`` skips the checks that need the database, for the pre-flight check before the migrate job has run.
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from backend.app.runtime_env import PRODUCTION, environment, is_production_like

# Values that only ever appear in templates and examples; a server that still shows one was never configured.
PLACEHOLDER_MARKERS = ("example.com", "example.test", "changeme", "change-me", "change_me")
# A connector may reach a private address only when an operator has accepted that this removes the SSRF protection.
CONNECTOR_HOSTS_ACKNOWLEDGEMENT = "MDARIX_CONNECTOR_ALLOWED_HOSTS_ACKNOWLEDGED"


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


def _placeholder_problem(name: str) -> str | None:
    """Template values (example.com, changeme) mean the setting was copied, not filled in."""
    value = _get(name).lower()
    if value and any(marker in value for marker in PLACEHOLDER_MARKERS):
        return f"{name} still holds a placeholder value ({_get(name)})"
    return None


def _integer_problem(name: str, minimum: int, maximum: int | None = None, *, required: bool = False) -> str | None:
    value = _get(name)
    if not value:
        return f"{name} must be set" if required else None
    bounds = f"at least {minimum}" if maximum is None else f"between {minimum} and {maximum}"
    if not value.isdigit() or int(value) < minimum or (maximum is not None and int(value) > maximum):
        return f"{name} must be a whole number {bounds} (got {value!r})"
    return None


def problems(*, offline: bool = False) -> list[str]:
    """Every configuration problem that makes this server unsafe or broken for customers (empty when fine).

    ``offline`` skips the checks that need a database connection (the system-scope token and the runtime role),
    so the configuration can be checked before the migrate job has created either.
    """
    if not is_production_like():
        return []
    found: list[str] = []

    def add(problem: str | None) -> None:
        if problem:
            found.append(problem)

    app_url = urlparse(_get("MDARIX_APP_URL"))
    if app_url.scheme != "https" or not app_url.netloc:
        add("MDARIX_APP_URL must be the https address people use, e.g. https://app.example.com")
    for name in ("MDARIX_APP_URL", "MDARIX_DOMAIN", "MDARIX_SMTP_FROM", "MDARIX_SUPPORT_EMAIL", "MDARIX_PRIVACY_EMAIL"):
        add(_placeholder_problem(name))
    for origin in (item.strip() for item in _get("MDARIX_ALLOWED_ORIGINS").split(",") if item.strip()):
        if urlparse(origin).scheme != "https":
            add(f"MDARIX_ALLOWED_ORIGINS must list https origins only (got {origin})")

    if not _get("MDARIX_DB_RUNTIME_USER") or not _get("MDARIX_DB_RUNTIME_PASSWORD"):
        add("MDARIX_DB_RUNTIME_USER and MDARIX_DB_RUNTIME_PASSWORD must be set (row-level security needs them)")
    found.extend(_database_tls_problems())
    found.extend(_owner_credentials_problems())

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
    found.extend(_alerting_problems())

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
    found.extend(_session_and_mfa_problems())
    found.extend(_network_problems())

    from genai.policy import configuration_problems as ai_problems

    found.extend(ai_problems())
    add(_ai_cost_problem())
    if not offline:
        if _get("MDARIX_RLS_SYSTEM_TOKEN"):
            add(_database_token_problem())
        add(_runtime_role_problem())
    return found


def _database_tls_problems() -> list[str]:
    """Production verifies the database certificate and its host name; staging may settle for the CA alone."""
    found = []
    mode = _get("POSTGRES_SSLMODE").lower()
    if environment() == PRODUCTION:
        if mode != "verify-full":
            found.append("POSTGRES_SSLMODE must be verify-full in production (the database certificate is checked)")
    elif mode not in {"verify-ca", "verify-full"}:
        found.append("POSTGRES_SSLMODE must be verify-ca or verify-full in staging")
    root = _get("POSTGRES_SSLROOTCERT")
    if root and not os.access(root, os.R_OK):
        found.append(f"POSTGRES_SSLROOTCERT is set but {root} cannot be read (mount the CA bundle into the container)")
    return found


def _owner_credentials_problems() -> list[str]:
    """Owner credentials belong to the one-shot migrate and backup jobs (.env.migrate), never to a running service.

    A long-running service holding the owner password could bypass row-level security if any part of it were
    compromised, so the API refuses to start with it in reach. The same applies to the backup login and to the owner
    connection strings of dedicated customer databases.
    """
    found = []
    if _get("MDARIX_DB_OWNER_PASSWORD"):
        found.append(
            "MDARIX_DB_OWNER_PASSWORD must not be in a long-running service's environment: keep the owner "
            "credentials in .env.migrate, which only the migrate and backup jobs load"
        )
    if _get("MDARIX_BACKUP_DB_PASSWORD"):
        # The backup login reads every organization's rows (BYPASSRLS): it is no safer in reach than the owner's.
        found.append(
            "MDARIX_BACKUP_DB_PASSWORD must not be in a long-running service's environment: keep the backup "
            "credentials in .env.migrate, which only the migrate and backup jobs load"
        )
    owner_urls = sorted(
        name for name in os.environ if name.startswith("MDARIX_DATA_PLANE_") and name.endswith("_OWNER")
    )
    if owner_urls:
        found.append(f"{', '.join(owner_urls)} must not be in a long-running service's environment (.env.migrate)")
    runtime_user = _get("MDARIX_DB_RUNTIME_USER")
    owner_user = _get("MDARIX_DB_OWNER_USER")
    if runtime_user and owner_user and runtime_user == owner_user:
        found.append("MDARIX_DB_RUNTIME_USER must not be the schema owner (MDARIX_DB_OWNER_USER)")
    return found


def _alerting_problems() -> list[str]:
    """Operators must hear about dead letters and stopped workers; staff must hear about trial and demo requests."""
    found = []
    if not _get("MDARIX_ALERT_WEBHOOK") and not _get("MDARIX_ALERT_EMAIL"):
        found.append("Set MDARIX_ALERT_WEBHOOK and/or MDARIX_ALERT_EMAIL: operational alerts need a destination")
    if not _get("MDARIX_TRIAL_ALERT_EMAIL") and not _get("MDARIX_DEMO_ALERT_EMAIL"):
        found.append(
            "Set MDARIX_TRIAL_ALERT_EMAIL and/or MDARIX_DEMO_ALERT_EMAIL: nobody would hear about trial and demo requests"
        )
    return found


def _session_and_mfa_problems() -> list[str]:
    """The MFA policy and session limits may be tightened, never switched off, on a server."""
    found = []
    if "MDARIX_REQUIRE_MFA_ROLES" in os.environ and not _get("MDARIX_REQUIRE_MFA_ROLES"):
        found.append("MDARIX_REQUIRE_MFA_ROLES must not be empty: administrators must set up MFA (or unset it)")
    if _get("MDARIX_REQUIRE_MFA_FOR_SIGNATURES").lower() in {"0", "false", "no"}:
        found.append("MDARIX_REQUIRE_MFA_FOR_SIGNATURES must not be false: signatures need a fresh authenticator code")
    found.append(_integer_problem("MDARIX_SESSION_IDLE_MINUTES", 5, 120))
    return [item for item in found if item]


def _network_problems() -> list[str]:
    """Behind Caddy the client address comes from X-Forwarded-For; connectors may not reach private addresses."""
    found = []
    if environment() == PRODUCTION:
        found.append(_integer_problem("MDARIX_TRUSTED_PROXY_HOPS", 1, required=True))
    if _get("MDARIX_CONNECTOR_ALLOWED_HOSTS") and _get(CONNECTOR_HOSTS_ACKNOWLEDGEMENT).lower() != "true":
        found.append(
            "MDARIX_CONNECTOR_ALLOWED_HOSTS lets connectors reach private addresses (bypassing the SSRF block); "
            f"remove it, or set {CONNECTOR_HOSTS_ACKNOWLEDGEMENT}=true to accept that"
        )
    return [item for item in found if item]


def _ai_cost_problem() -> str | None:
    """With a real model, administrators see spend per organization; a zero cost rate would show nothing."""
    from genai.policy import NO_MODEL

    provider = (_get("MDARIX_GENAI_PROVIDER") or NO_MODEL).lower()
    if provider in {NO_MODEL, "none"}:
        return None
    raw = _get("MDARIX_GENAI_COST_PER_1K_TOKENS")
    try:
        cost = float(raw) if raw else 0.0
    except ValueError:
        cost = 0.0
    if cost <= 0:
        return "MDARIX_GENAI_COST_PER_1K_TOKENS must be above 0 when a model provider is configured (admins see cost)"
    return None


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


def _runtime_role_problem() -> str | None:
    """The role requests run as must be subject to row-level security: no superuser, no BYPASSRLS.

    Row-level security is what keeps one organization's data from another; a superuser or BYPASSRLS login would
    silently switch it off for every query, so the server refuses to start as one.
    """
    try:
        from sqlalchemy import text

        from backend.app.db.session import runtime_engine

        with runtime_engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT rolname, rolsuper OR rolbypassrls AS unrestricted FROM pg_roles WHERE rolname = current_user"
                )
            ).one()
    except Exception as exc:
        return f"Could not check the database role the server runs as ({type(exc).__name__})"
    if row.unrestricted:
        return (
            f"The database role {row.rolname} is a superuser or has BYPASSRLS: requests must run as the "
            "least-privilege runtime role (scripts/configure_runtime_role.py)"
        )
    owner_user = _get("MDARIX_DB_OWNER_USER")
    if owner_user and row.rolname == owner_user:
        return f"The server connects as the schema owner {owner_user}; set MDARIX_DB_RUNTIME_USER to the runtime role"
    return None


def enforce() -> None:
    """Raise SystemExit listing every problem when this staging/production server is not safe to start."""
    found = problems()
    if found:
        lines = "\n".join(f"  - {item}" for item in found)
        raise SystemExit(f"MDARIX will not start in {environment()}: fix the configuration first.\n{lines}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List configuration problems of a staging or production server.")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="skip the checks that need the database (before the migrate job has run)",
    )
    args = parser.parse_args(argv)
    issues = problems(offline=args.offline)
    if not is_production_like():
        print(f"MDARIX_ENV={environment()}: configuration checks apply to staging and production only.")
    elif args.offline:
        print("Offline check: the system-scope token and the runtime role are verified once the database is reachable.")
    for issue in issues:
        print(f"- {issue}")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
