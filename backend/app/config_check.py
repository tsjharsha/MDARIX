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
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from backend.app.runtime_env import PRODUCTION, STAGING, environment, is_production_like

# Values that only ever appear in templates and examples; a server that still shows one was never configured.
PLACEHOLDER_MARKERS = ("example.com", "example.test", "changeme", "change-me", "change_me")
# Text left for the lawyer in a legal document: the draft banner, or a [PLACEHOLDER] in square brackets (no lower-case
# letters, so a Markdown link such as [Privacy policy](/privacy) or [text][ref] never matches).
LEGAL_DRAFT_BANNER = re.compile(r"\bDRAFT\b")
LEGAL_PLACEHOLDER = re.compile(r"\[(?=[^\]\n]*\S)[^\]\na-z]+\](?![(\[])")
# A connector may reach a private address only when an operator has accepted that this removes the SSRF protection.
CONNECTOR_HOSTS_ACKNOWLEDGEMENT = "MDARIX_CONNECTOR_ALLOWED_HOSTS_ACKNOWLEDGED"
# Production keeps an off-site backup copy in a bucket, unless an operator states that copies leave the server another
# way (for example the managed database's own backups and point-in-time recovery).
BACKUP_OFFSITE_ACKNOWLEDGEMENT = "MDARIX_BACKUP_OFFSITE_ACKNOWLEDGED"
# A private staging server (ADR-017) may run before the lawyer-approved legal texts and the company details exist: the
# whole site sits behind a login at Caddy (MDARIX_SITE_ACCESS=private), so nothing reaches the public, and an operator
# states it with this acknowledgement. Production never gets the exemption.
PRIVATE_STAGING_ACKNOWLEDGEMENT = "MDARIX_PRIVATE_STAGING_ACKNOWLEDGED"
SITE_ACCESS_VALUES = ("public", "private")
# What "caddy hash-password" prints. A hash cut short (a "$" in .env.production read as a variable when the value is not
# in single quotes) would lock everyone out, so it is checked here, where the problem is named.
BCRYPT_HASH = re.compile(r"\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}")


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

    found.extend(_deployment_role_problems())
    add(_feature_set_problem())
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
    found.extend(_site_access_problems())
    if not private_staging():
        for name in ("MDARIX_COMPANY_LEGAL_NAME", "MDARIX_COMPANY_ADDRESS"):
            if not _get(name):
                add(f"{name} must be set: it appears in the legal pages, the footer and every email")
        if _get("MDARIX_LEGAL_TEXT_APPROVED").lower() != "true":
            add("MDARIX_LEGAL_TEXT_APPROVED must be true once a lawyer has approved the privacy policy and terms")
        add(_legal_documents_problem())
    found.extend(_alerting_problems())
    found.extend(_backup_and_monitoring_problems())

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
    add(_embedding_model_problem())
    if not offline:
        if _get("MDARIX_RLS_SYSTEM_TOKEN"):
            add(_database_token_problem())
        add(_runtime_role_problem())
        if not _deployment_role_problems():
            add(_cell_tenant_problem())
    return found


def _feature_set_problem() -> str | None:
    """MDARIX_FEATURE_SET (backend/app/feature_set.py): full (the default) or mvp."""
    from backend.app import feature_set as sets

    value = _get("MDARIX_FEATURE_SET").lower() or sets.FULL
    if value not in sets.FEATURE_SETS:
        return f"MDARIX_FEATURE_SET must be full or mvp (got {_get('MDARIX_FEATURE_SET')})"
    return None


def _deployment_role_problems() -> list[str]:
    """MDARIX_DEPLOYMENT_ROLE (backend/app/deployment_role.py) and what each role needs: a CELL names the one
    organization it serves and has no second database; the PLATFORM names no cell organization."""
    from backend.app import deployment_role as roles

    value = _get("MDARIX_DEPLOYMENT_ROLE").upper() or roles.MULTI
    if value not in roles.ROLES:
        return [f"MDARIX_DEPLOYMENT_ROLE must be MULTI, PLATFORM or CELL (got {value})"]
    found: list[str] = []
    if value == roles.CELL:
        if roles.cell_tenant_id() is None:
            found.append("MDARIX_CELL_TENANT_ID must be the UUID of the one organization this cell serves")
        if not roles.cell_tenant_key():
            found.append("MDARIX_CELL_TENANT_KEY must be the key of the one organization this cell serves")
        planes = sorted(
            name for name in os.environ if name.startswith("MDARIX_DATA_PLANE_") and "_DATABASE_URL" in name
        )
        if planes:
            found.append(f"A cell has one database: remove {', '.join(planes)}")
        from backend.app.cell_packages import platform_public_key, public_key_problem

        # A cell trusts only documents the platform signed (licences, packages): the public key is pinned here.
        if problem := public_key_problem(platform_public_key()):
            found.append(problem)
        url = urlparse(_get("MDARIX_PLATFORM_URL"))
        if url.scheme != "https" or not url.netloc:
            found.append("MDARIX_PLATFORM_URL must be the https address of the MDARIX platform this cell reports to")
    elif _get("MDARIX_CELL_TENANT_ID") or _get("MDARIX_CELL_TENANT_KEY"):
        found.append(f"MDARIX_CELL_TENANT_ID and MDARIX_CELL_TENANT_KEY are for a CELL, not a {value} deployment")
    if value == roles.PLATFORM:
        from backend.app.cell_packages import platform_public_key, public_key_problem
        from backend.app.cell_pki import platform_ca_problem

        # The platform verifies uploaded packages with the key the cells pin, and signs cell certificates.
        if problem := public_key_problem(platform_public_key()):
            found.append(problem.replace("in a CELL", "on the PLATFORM"))
        if problem := platform_ca_problem():
            found.append(problem)
    return found


def _cell_tenant_problem() -> str | None:
    """A cell's database must hold the organization it is configured for, under that key, on the shared plane (the
    cell's own database is that plane)."""
    from backend.app import deployment_role as roles

    if not roles.is_cell():
        return None
    try:
        from backend.app.db.data_plane import SHARED_CONTROL_DATA_PLANE
        from backend.app.db.models.customer_lifecycle import TenantDataPlane
        from backend.app.db.models.foundation import Tenant
        from backend.app.db.session import SessionLocal
        from backend.app.db.tenant_scope import bind_system

        with SessionLocal() as db:
            bind_system(db, "configuration check: the cell's organization")
            tenant = db.query(Tenant).filter(Tenant.id == roles.cell_tenant_id()).first()
            if tenant is None:
                return "The database does not hold the organization MDARIX_CELL_TENANT_ID names"
            if tenant.tenant_key != roles.cell_tenant_key():
                return f"MDARIX_CELL_TENANT_KEY does not match the organization's key ({tenant.tenant_key})"
            plane = (
                db.query(TenantDataPlane)
                .filter(TenantDataPlane.tenant_id == tenant.id, TenantDataPlane.status == "ACTIVE")
                .first()
            )
            if plane is None or plane.connection_secret_ref != SHARED_CONTROL_DATA_PLANE:
                return "A cell's organization lives in the cell's own database: its data-plane registry row must be the shared plane"
    except Exception as exc:
        return f"Could not check the cell's organization against the database ({type(exc).__name__})"
    return None


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
    # Free trials exist on a MULTI deployment only. There, the alerts for a request waiting for review and for a trial
    # that asks to end early read MDARIX_TRIAL_ALERT_EMAIL alone (auth_router.py, trial/router.py), and the demo and MVP
    # alerts fall back to it, so it must be set: MDARIX_DEMO_ALERT_EMAIL alone left the first two unheard (FUN-09).
    if _deployment_role_is_multi():
        if not _get("MDARIX_TRIAL_ALERT_EMAIL"):
            found.append(
                "Set MDARIX_TRIAL_ALERT_EMAIL: nobody would hear about trial requests waiting for review or trials that "
                "ask to end early (MDARIX_DEMO_ALERT_EMAIL covers demo and MVP requests only)"
            )
    elif not _get("MDARIX_TRIAL_ALERT_EMAIL") and not _get("MDARIX_DEMO_ALERT_EMAIL"):
        found.append(
            "Set MDARIX_TRIAL_ALERT_EMAIL and/or MDARIX_DEMO_ALERT_EMAIL: nobody would hear about trial and demo requests"
        )
    return found


def _deployment_role_is_multi() -> bool:
    """True for a MULTI deployment (the default), the one that offers free trials. An unknown role counts as MULTI
    here; _deployment_role_problems reports it."""
    from backend.app import deployment_role as roles

    try:
        return roles.deployment_role() == roles.MULTI
    except RuntimeError:
        return True


def _https_url_problem(name: str, purpose: str) -> str | None:
    value = _get(name)
    if not value:
        return f"{name} must be set in production: {purpose}"
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        return f"{name} must be an https:// address"
    return None


def _backup_and_monitoring_problems() -> list[str]:
    """Production backups are encrypted, leave the server, and an outside monitor notices when they or the scheduler
    stop (docs/runbooks/BACKUP_AND_RESTORE.md). The backup job reads the same .env.production."""
    if environment() != PRODUCTION:
        return []
    found = []
    recipient = _get("MDARIX_BACKUP_AGE_RECIPIENT")
    if not recipient:
        found.append(
            "MDARIX_BACKUP_AGE_RECIPIENT must be set in production: the age public key backups are encrypted to"
        )
    elif not recipient.startswith(("age1", "ssh-ed25519 ", "ssh-rsa ")):
        found.append("MDARIX_BACKUP_AGE_RECIPIENT must be an age public key (age1...) or an SSH public key")
    bucket = _get("MDARIX_BACKUP_S3_URI")
    if bucket and not bucket.startswith("s3://"):
        found.append("MDARIX_BACKUP_S3_URI must be an s3:// address")
    elif not bucket and _get(BACKUP_OFFSITE_ACKNOWLEDGEMENT).lower() != "true":
        found.append(
            "Backups must leave the server: set MDARIX_BACKUP_S3_URI (off-site bucket), or set "
            f"{BACKUP_OFFSITE_ACKNOWLEDGEMENT}=true if copies leave another way (e.g. managed database backups)"
        )
    found.append(_https_url_problem("MDARIX_BACKUP_HEARTBEAT_URL", "an outside monitor must notice when backups stop"))
    found.append(
        _https_url_problem("MDARIX_SCHEDULER_HEARTBEAT_URL", "an outside monitor must notice when the scheduler stops")
    )
    return [item for item in found if item]


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


def _embedding_model_problem() -> str | None:
    """Evidence search embeds text with a model shipped in the image; a server never downloads weights. The pinned
    model must be present and unchanged (retrieval/embedding_provider.py)."""
    if (_get("MDARIX_EMBEDDING_PROVIDER") or "local").lower() == "deterministic":
        return None
    from retrieval.embedding_provider import local_model_problem

    return local_model_problem()


def _site_login_set() -> bool:
    return bool(_get("MDARIX_SITE_LOGIN_USER")) and bool(BCRYPT_HASH.fullmatch(_get("MDARIX_SITE_LOGIN_HASH")))


def private_staging() -> bool:
    """A staging server whose whole site is behind Caddy's login, acknowledged by an operator: it may run with draft
    legal texts and without the company details (ADR-017)."""
    return (
        environment() == STAGING
        and (_get("MDARIX_SITE_ACCESS") or "public").lower() == "private"
        and _site_login_set()
        and _get(PRIVATE_STAGING_ACKNOWLEDGEMENT).lower() == "true"
    )


def _site_access_problems() -> list[str]:
    """MDARIX_SITE_ACCESS, read by Caddy too (infrastructure/docker/Caddyfile): public, or private behind a login."""
    found = []
    access = (_get("MDARIX_SITE_ACCESS") or "public").lower()
    if access not in SITE_ACCESS_VALUES:
        found.append(f"MDARIX_SITE_ACCESS must be public or private (got {_get('MDARIX_SITE_ACCESS')!r})")
    if access == "private":
        if not _get("MDARIX_SITE_LOGIN_USER"):
            found.append("MDARIX_SITE_LOGIN_USER must be set when MDARIX_SITE_ACCESS is private")
        if not BCRYPT_HASH.fullmatch(_get("MDARIX_SITE_LOGIN_HASH")):
            found.append(
                "MDARIX_SITE_LOGIN_HASH must be the whole bcrypt hash from 'caddy hash-password', in single quotes in "
                ".env.production (a $ outside quotes is read as a variable and cuts the hash short)"
            )
    if _get(PRIVATE_STAGING_ACKNOWLEDGEMENT).lower() == "true":
        if environment() != STAGING:
            found.append(f"{PRIVATE_STAGING_ACKNOWLEDGEMENT} applies to a staging server only: remove it in production")
        elif access != "private":
            found.append(
                f"{PRIVATE_STAGING_ACKNOWLEDGEMENT} needs MDARIX_SITE_ACCESS=private (the site behind a login)"
            )
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
    # The approval flag alone would publish a draft: each document must also read as final.
    unfinished = []
    for name in LEGAL_DOCUMENTS.values():
        try:
            text = (Path(folder) / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            unfinished.append(f"{name} (cannot be read as UTF-8 text)")
            continue
        reasons = []
        if LEGAL_DRAFT_BANNER.search(text):
            reasons.append("the DRAFT banner")
        placeholders = LEGAL_PLACEHOLDER.findall(text)
        if placeholders:
            reasons.append(f"{len(placeholders)} [PLACEHOLDER] text(s), first {placeholders[0][:40]}")
        if reasons:
            unfinished.append(f"{name} ({' and '.join(reasons)})")
    if unfinished:
        return f"Legal documents still hold draft text (publish the lawyer-approved wording): {'; '.join(unfinished)}"
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
