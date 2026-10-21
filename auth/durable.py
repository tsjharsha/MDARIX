"""Database-backed authentication sessions and one-time links (invitations and password resets).

Everything here lives in Postgres, so every API process sees the same sessions and links, and a restart signs no
one out. Raw tokens are random 256-bit values given to the browser or emailed once; only their SHA-256 is stored.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.app.db.models.stage2 import (
    AuthSession,
    PasswordResetRequest,
    UserInvitation,
)

SESSION_SECONDS = 3600
# An invitation or activation link works once and expires after 48 hours (a link sent on a Friday afternoon still
# works on Sunday); a person whose link expired asks for a new one or uses "Forgot password?".
INVITATION_SECONDS = 48 * 3600
RESET_SECONDS = 3600


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def persist_session(
    db: Session, raw: str, user_id, tenant_id, ttl: int = SESSION_SECONDS, mfa_state: str | None = None
):
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
            mfa_state=mfa_state,
        )
    )
    db.commit()


def new_session(db: Session, user_id, tenant_id, *, mfa_state: str | None = None, ttl: int = SESSION_SECONDS) -> str:
    """Create a session for an authenticated user and return its raw token (for the cookie)."""
    raw = new_token()
    persist_session(db, raw, user_id, tenant_id, ttl=ttl, mfa_state=mfa_state)
    return raw


def revoke_session(db: Session, raw: str):
    row = (
        db.query(AuthSession)
        .filter(AuthSession.session_hash == hash_token(raw), AuthSession.revoked_at.is_(None))
        .first()
    )
    if row:
        row.revoked_at = datetime.now(timezone.utc)
        db.commit()


def revoke_user_sessions(db: Session, user_id, tenant_id, keep_raw: str | None = None) -> int:
    """Revoke every session of one user not revoked yet, except ``keep_raw`` (caller commits), and return how many of
    them were still live: sessions that had already expired or gone idle are revoked too but not counted, so "2 other
    sessions were signed out" counts only sessions someone could still use (NEW-5).

    Used when access is suspended or removed, and when the password changes (a stolen session must not survive it).
    """
    from backend.app.request_context import session_is_live

    query = db.query(AuthSession).filter(
        AuthSession.user_id == user_id, AuthSession.tenant_id == tenant_id, AuthSession.revoked_at.is_(None)
    )
    if keep_raw:
        query = query.filter(AuthSession.session_hash != hash_token(keep_raw))
    rows = query.all()
    now = datetime.now(timezone.utc)
    live = sum(1 for row in rows if session_is_live(row, now))
    for row in rows:
        row.revoked_at = now
    return live


def _retire_open_links(db: Session, model, user_id, tenant_id, now: datetime) -> None:
    """A new link replaces the person's earlier unused ones, so only the latest email works."""
    db.query(model).filter(
        model.user_id == user_id, model.tenant_id == tenant_id, model.used_at.is_(None), model.expires_at > now
    ).update({"used_at": now}, synchronize_session=False)


def issue_invitation(db: Session, user_id, tenant_id, created_by=None, ttl: int = INVITATION_SECONDS):
    raw = new_token()
    now = datetime.now(timezone.utc)
    _retire_open_links(db, UserInvitation, user_id, tenant_id, now)
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


def issue_reset(db: Session, user_id, tenant_id, created_by=None, ttl: int = RESET_SECONDS):
    raw = new_token()
    now = datetime.now(timezone.utc)
    _retire_open_links(db, PasswordResetRequest, user_id, tenant_id, now)
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


def peek(db: Session, raw: str, kind: str) -> str:
    """The user a valid, unused link belongs to, without spending it (so a refused password keeps the link)."""
    model = UserInvitation if kind == "activation" else PasswordResetRequest
    row = (
        db.query(model.user_id)
        .filter(
            model.token_hash == hash_token(raw), model.used_at.is_(None), model.expires_at > datetime.now(timezone.utc)
        )
        .first()
    )
    if not row:
        raise ValueError(f"INVALID_{kind.upper()}_TOKEN")
    return str(row.user_id)


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
