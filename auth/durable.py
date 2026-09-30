"""Database-backed authentication sessions and one-time links."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.app.db.models.stage2 import (
    AuthSession,
    PasswordResetRequest,
    UserInvitation,
)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def persist_session(db: Session, raw: str, user_id, tenant_id, ttl: int = 3600):
    if not hasattr(db, "add"):
        return
    now = datetime.now(timezone.utc)
    db.add(
        AuthSession(
            session_hash=hash_token(raw),
            user_id=user_id,
            tenant_id=tenant_id,
            expires_at=now + timedelta(seconds=ttl),
            created_at=now,
            last_seen_at=now,
        )
    )
    db.commit()


def revoke_session(db: Session, raw: str):
    row = (
        db.query(AuthSession)
        .filter(AuthSession.session_hash == hash_token(raw), AuthSession.revoked_at.is_(None))
        .first()
    )
    if row:
        row.revoked_at = datetime.now(timezone.utc)
        db.commit()


def revoke_user_sessions(db: Session, user_id, tenant_id) -> int:
    """Revoke every live session of one user (caller commits). Used when access is suspended or removed."""
    rows = (
        db.query(AuthSession)
        .filter(AuthSession.user_id == user_id, AuthSession.tenant_id == tenant_id, AuthSession.revoked_at.is_(None))
        .all()
    )
    now = datetime.now(timezone.utc)
    for row in rows:
        row.revoked_at = now
    return len(rows)


def issue_invitation(db: Session, user_id, tenant_id, created_by=None, ttl: int = 3600):
    raw = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    db.add(
        UserInvitation(
            user_id=user_id,
            tenant_id=tenant_id,
            token_hash=hash_token(raw),
            expires_at=now + timedelta(seconds=ttl),
            created_at=now,
            created_by=created_by,
        )
    )
    db.commit()
    return raw


def issue_reset(db: Session, user_id, tenant_id, created_by=None, ttl: int = 3600):
    raw = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    db.add(
        PasswordResetRequest(
            user_id=user_id,
            tenant_id=tenant_id,
            token_hash=hash_token(raw),
            expires_at=now + timedelta(seconds=ttl),
            created_at=now,
            created_by=created_by,
        )
    )
    db.commit()
    return raw


def consume(db: Session, raw: str, kind: str):
    model = UserInvitation if kind == "activation" else PasswordResetRequest
    row = (
        db.query(model)
        .filter(
            model.token_hash == hash_token(raw), model.used_at.is_(None), model.expires_at > datetime.now(timezone.utc)
        )
        .first()
    )
    if not row:
        raise ValueError(f"INVALID_{kind.upper()}_TOKEN")
    row.used_at = datetime.now(timezone.utc)
    db.commit()
    return str(row.user_id)
