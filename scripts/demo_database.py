"""The WHIF demo database: put it back to the demo's start state, or prove its backup restores.

    POSTGRES_DB=mdarix_whif_demo python scripts/demo_database.py reset
    POSTGRES_DB=mdarix_whif_demo python scripts/demo_database.py backup-check --out <folder>

Only a database whose name starts with ``mdarix_whif_`` is ever written, dropped or restored; every other name is
refused before any connection is made. Run with the database owner's credentials (the app's own settings).

``reset`` (idempotent, about 15 s once the template exists):

1. The template ``mdarix_whif_template`` holds what never changes between demos: the schema at the Alembic head, the
   runtime role's privileges and the published code lists (IMDRF, FDA, EMDN). It is built (about 2 minutes) only when
   it is missing or its schema is not at the head.
2. The demo database is dropped and created again from the template (a file copy inside PostgreSQL, about 2 s).
3. The platform organization, a Platform Administrator and the curated demo trial are created now, so every sample
   date, deadline and trial day reads as "day 0". The trial is approved through the product's own approval
   (``trial.service.approve_request``), which seeds the trial sample story; its invitation e-mail is never sent.
   With ``MDARIX_WHIF_DEMO_PASSWORD`` set, both demo accounts can sign in with it (never printed); otherwise they stay
   invited. The Platform Administrator sets up MFA at first sign-in, as on every server.
   With ``MDARIX_WHIF_DEMO_MFA_KEY`` set (the base32 key the presenter keeps in an authenticator app, never printed),
   the trial owner's authenticator is enrolled with it, so switching AI on and signing work on stage; otherwise the
   presenter sets one up under My Account › Security after the reset (turning AI on and signing need its code).

``backup-check``: ``pg_dump`` of the demo database into ``--out``, restored into ``mdarix_whif_restore``, row counts
compared table by table, the audit hash chain verified there, then ``mdarix_whif_restore`` (only) is dropped.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PREFIX = "mdarix_whif_"
TEMPLATE = "mdarix_whif_template"
RESTORE = "mdarix_whif_restore"
DEMO_ORGANIZATION = "Asteria Medical Systems (Demo)"
DEMO_TRIAL_EMAIL = "quality.lead@asteria-demo.example"
DEMO_ADMIN_EMAIL = "platform.admin@whif-demo.example"
DEMO_PROFILE = {"job_title": "Head of Quality and Regulatory (fictional)", "country": "India"}
PASSWORD_ENV = "MDARIX_WHIF_DEMO_PASSWORD"
MFA_KEY_ENV = "MDARIX_WHIF_DEMO_MFA_KEY"
# A fictional person, so the greeting and avatar read as a name ("Good morning, Asha", "AR").
DEMO_TRIAL_NAME = "Asha Rao (fictional)"


class Refused(SystemExit):
    pass


def guard(name: str | None) -> str:
    """The database name, when it is a WHIF demo database; anything else is refused (exit code 2)."""
    if not name or not name.startswith(PREFIX) or not name[len(PREFIX) :].replace("_", "").isalnum():
        raise Refused(f"Refusing {name!r}: this script only works on databases named {PREFIX}*")
    return name


def _admin_engine():
    from sqlalchemy import create_engine

    from backend.app.db.session import database_url

    return create_engine(database_url().set(database="postgres"), isolation_level="AUTOCOMMIT", future=True)


def _head() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini"))).get_current_head()


def _template_at_head(admin) -> bool:
    from sqlalchemy import create_engine, text

    from backend.app.db.session import database_url

    with admin.connect() as c:
        if not c.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEMPLATE}).first():
            return False
    engine = create_engine(database_url().set(database=TEMPLATE), future=True)
    try:
        with engine.connect() as c:
            return c.execute(text("SELECT version_num FROM alembic_version")).scalar() == _head()
    except Exception:
        return False
    finally:
        engine.dispose()


def _recreate(admin, name: str, template: str | None = None) -> None:
    from sqlalchemy import text

    guard(name)
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{name}"' + (f' TEMPLATE "{guard(template)}"' if template else "")))


def _run(database: str, *args: str) -> None:
    env = {**os.environ, "POSTGRES_DB": guard(database), "MDARIX_DB_HARDENING_APPLY": "1", "PYTHONPATH": str(ROOT)}
    subprocess.run([sys.executable, *args], cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)


def build_template(admin) -> None:
    _recreate(admin, TEMPLATE)
    _run(TEMPLATE, "-m", "alembic", "upgrade", "head")
    _run(TEMPLATE, "scripts/grant_runtime_privileges.py")
    _run(TEMPLATE, "scripts/load_code_lists.py", "--apply")


def _activate(db, user, password: str, now: datetime) -> None:
    from backend.app.auth_router import _set_password

    _set_password(db, user, password, now)
    user.status = "ACTIVE"
    user.email_verified = True


def _enrol_authenticator(user, key: str, now: datetime) -> None:
    """Enrol ``user``'s authenticator with ``key`` (base32, as an authenticator app shows it), as a finished set-up
    would: sign-in, turning AI on and signing then ask for its code."""
    from auth import totp

    key = key.replace(" ", "").upper()
    totp.code_at(key, 0)  # a key that is not base32 fails here, before anything is stored
    user.mfa_secret_encrypted = totp.encrypt_secret(key, str(user.id))
    user.mfa_pending_secret_encrypted = None
    user.mfa_last_step = None
    user.mfa_required = True
    user.mfa_enrolled_at = now


def seed_demo(db, now: datetime | None = None) -> dict:
    """The platform organization, its administrator and the curated demo trial, in the database ``db`` is bound to.
    The trial goes through the product's approval, so its sample story is the one every new trial gets. Commits."""
    from auth.service import _hash
    from backend.app.db.models.foundation import AuthUser, TenantMembership
    from backend.app.db.models.stage2 import OnboardingRequest
    from backend.app.support_access import ensure_platform_tenant
    from backend.app.trial import service

    now = now or datetime.now(timezone.utc)
    platform = ensure_platform_tenant(db, now)
    admin = db.query(AuthUser).filter(AuthUser.username == DEMO_ADMIN_EMAIL).first()
    if admin is None:
        admin = AuthUser(
            id=uuid.uuid4(),
            tenant_id=platform.id,
            username=DEMO_ADMIN_EMAIL,
            display_name="Demo Platform Admin (fictional)",
            company=platform.display_name,
            password_hash=_hash(secrets.token_urlsafe(32)),  # unusable until activated below or by an invitation
            role="PLATFORM_ADMIN",
            status="INVITED",
            email_verified=False,
            mfa_required=True,
            created_at=now,
            updated_at=now,
        )
        db.add(admin)
        db.flush()
        db.add(
            TenantMembership(
                id=uuid.uuid4(),
                tenant_id=platform.id,
                user_id=admin.id,
                status="ACTIVE",
                is_default=True,
                created_at=now,
                updated_at=now,
            )
        )
    request = OnboardingRequest(
        id=uuid.uuid4(),
        email=DEMO_TRIAL_EMAIL,
        display_name=DEMO_TRIAL_NAME,
        organization=DEMO_ORGANIZATION,
        status="PENDING_REVIEW",
        profile={**DEMO_PROFILE, "no_patient_data_confirmed": True},
        created_at=now,
        updated_at=now,
    )
    db.add(request)
    db.commit()
    # The demo never e-mails anyone: the invitation is recorded as not sent.
    real_send, service._send_invitation = service._send_invitation, lambda *a, **k: {"email_delivery": "NOT_SENT"}
    try:
        approval = service.approve_request(db, request.id, admin)
    finally:
        service._send_invitation = real_send
    password = os.getenv(PASSWORD_ENV, "")
    trial_user = db.query(AuthUser).filter(AuthUser.username == DEMO_TRIAL_EMAIL).one()
    if password:
        _activate(db, admin, password, now)
        _activate(db, trial_user, password, now)
    mfa_key = os.getenv(MFA_KEY_ENV, "")
    if mfa_key:
        _enrol_authenticator(trial_user, mfa_key, now)
    db.commit()
    return {
        "tenant_id": approval["tenant_id"],
        "tenant_key": approval["tenant_key"],
        "trial_user": DEMO_TRIAL_EMAIL,
        "platform_admin": DEMO_ADMIN_EMAIL,
        "accounts_active": bool(password),
        "trial_owner_authenticator": bool(mfa_key),
    }


def reset(name: str) -> dict:
    guard(name)
    started = time.monotonic()
    admin = _admin_engine()
    try:
        built = not _template_at_head(admin)
        if built:
            build_template(admin)
        template_s = time.monotonic() - started
        _recreate(admin, name, TEMPLATE)
    finally:
        admin.dispose()
    copied_s = time.monotonic() - started
    from backend.app.db.session import SessionLocal, engine, runtime_engine
    from backend.app.db.tenant_scope import bind_system

    for pool in (engine, runtime_engine):
        pool.dispose()  # pooled connections died with the old database
    db = SessionLocal()
    bind_system(db, "reset the WHIF demo database")
    try:
        result = seed_demo(db)
    finally:
        db.close()
    return {
        **result,
        "database": name,
        "template_built": built,
        "template_seconds": round(template_s, 1),
        "copy_seconds": round(copied_s - template_s, 1),
        "total_seconds": round(time.monotonic() - started, 1),
    }


def _counts(name: str) -> dict:
    from sqlalchemy import create_engine, text

    from backend.app.db.session import database_url
    from backend.app.db.tenant_scope import bind_connection_system

    engine = create_engine(database_url().set(database=guard(name)), future=True)
    try:
        with engine.connect() as c:
            bind_connection_system(c)  # forced row-level security: count every organization's rows
            tables = c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1")).scalars()
            return {t: c.execute(text(f'SELECT count(*) FROM "{t}"')).scalar() for t in list(tables)}
    finally:
        engine.dispose()


def _docker(*args: str, stdin=None, stdout=None) -> None:
    container = os.getenv("MDARIX_POSTGRES_CONTAINER", "mdarix-r1-postgres")
    user = os.environ["POSTGRES_USER"]
    subprocess.run(
        ["docker", "exec", "-i", container, *args[:1], "-U", user, *args[1:]], stdin=stdin, stdout=stdout, check=True
    )


def backup_check(name: str, out: Path) -> dict:
    """Dump ``name``, restore it into mdarix_whif_restore, compare row counts, verify the audit chain there, drop it."""
    from backend.app.db.session import database_url  # noqa: F401  (loads the owner's settings)

    guard(name)
    out.mkdir(parents=True, exist_ok=True)
    dump = out / f"{name}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.dump"
    started = time.monotonic()
    with dump.open("wb") as handle:
        _docker("pg_dump", "-Fc", "-d", name, stdout=handle)
    dumped_s = time.monotonic() - started
    admin = _admin_engine()
    try:
        _recreate(admin, RESTORE)
        with dump.open("rb") as handle:
            _docker("pg_restore", "--no-owner", "--exit-on-error", "-d", RESTORE, stdin=handle)
        restored_s = time.monotonic() - started - dumped_s
        source, copy = _counts(name), _counts(RESTORE)
        differ = {t: (source.get(t), copy.get(t)) for t in set(source) | set(copy) if source.get(t) != copy.get(t)}
        chain = _verify_chain(RESTORE)
    finally:
        from sqlalchemy import text

        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{guard(RESTORE)}" WITH (FORCE)'))
        admin.dispose()
    return {
        "dump": str(dump),
        "dump_bytes": dump.stat().st_size,
        "dump_seconds": round(dumped_s, 1),
        "restore_seconds": round(restored_s, 1),
        "tables": len(source),
        "rows": sum(source.values()),
        "tables_differing": differ,
        "audit_chain": chain,
        "restore_dropped": True,
    }


def _verify_chain(name: str) -> dict:
    """The audit hash chain of every organization in ``name``, verified as the product verifies it."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    from backend.app.audit_chain import verify_tenant_chain
    from backend.app.db.session import database_url
    from backend.app.db.tenant_scope import bind_system

    engine = create_engine(database_url().set(database=guard(name)), future=True)
    try:
        with Session(engine) as db:
            bind_system(db, "verify the restored demo database's audit chain")
            tenants = db.execute(text("SELECT DISTINCT tenant_id FROM audit_events")).scalars().all()
            results = [verify_tenant_chain(db, tenant) for tenant in tenants]
    finally:
        engine.dispose()
    return {
        "organizations": len(results),
        "events_checked": sum(r["checked"] for r in results),
        "all_valid": all(r["valid"] for r in results),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("reset", "backup-check"))
    parser.add_argument("--out", type=Path, help="backup-check: the folder for the dump file")
    args = parser.parse_args(argv)
    try:
        name = guard(os.getenv("POSTGRES_DB"))
    except Refused as exc:
        print(exc, file=sys.stderr)
        return 2
    if args.command == "reset":
        result = reset(name)
    else:
        if args.out is None:
            parser.error("backup-check needs --out")
        result = backup_check(name, args.out)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
