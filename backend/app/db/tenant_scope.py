"""Bind each database session to one tenant, or to an explicit system scope, for row-level security.

Postgres policies (migrations md05 and md15) show a tenant-owned row only when app.tenant_id matches it, or when the
transaction runs in system scope: app.rls_bypass holds the secret MDARIX_RLS_SYSTEM_TOKEN, which the database checks
against a hash the runtime role cannot read (``mdarix_system_scope()``). So SQL sent by the application role alone
can never widen its scope. The scope is stored on the SQLAlchemy session and applied at the start of every
transaction, so it survives commits within a request. A session with no scope sees no tenant-owned rows at all.

- bind_tenant: a signed-in request, after the server has resolved the session's tenant.
- bind_system: platform-administrator actions and pre-authentication steps (sign-in, activation, password reset)
  that must read across tenants before a tenant is known. Every call names its reason for review.
"""

from __future__ import annotations

import os
from contextlib import contextmanager

from sqlalchemy import event, text
from sqlalchemy.orm import Session

_TENANT_KEY = "mdarix_tenant_id"
_SYSTEM_KEY = "mdarix_system_reason"
# The settings the current transaction already holds (dropped when it ends and on any rollback, a savepoint's too).
_APPLIED_KEY = "mdarix_scope_applied"
_APPLY = text("SELECT set_config('app.tenant_id', :tenant, true), set_config('app.rls_bypass', :bypass, true)")


# Stored by migration md15 when MDARIX_RLS_SYSTEM_TOKEN is not set; local development and tests use it.
LOCAL_SYSTEM_TOKEN = "mdarix-local-development-rls-system-scope"


def system_token() -> str:
    """The secret that opens system scope (staging/production refuse to start without their own)."""
    from backend.app.runtime_env import is_local

    configured = os.getenv("MDARIX_RLS_SYSTEM_TOKEN", "").strip()
    if configured:
        return configured
    return LOCAL_SYSTEM_TOKEN if is_local() else ""


def _values(session: Session) -> dict:
    return {
        "tenant": session.info.get(_TENANT_KEY) or "",
        "bypass": system_token() if session.info.get(_SYSTEM_KEY) else "",
    }


def _apply_now(session: Session) -> None:
    # A transaction already in progress keeps its settings until it ends, so update it immediately too.
    if hasattr(session, "in_transaction") and session.in_transaction():
        values = _values(session)
        session.execute(_APPLY, values)
        session.info[_APPLIED_KEY] = values


def bind_tenant(session: Session, tenant_id) -> None:
    if not hasattr(session, "info"):
        return  # test doubles
    session.info[_TENANT_KEY] = str(tenant_id) if tenant_id else ""
    session.info.pop(_SYSTEM_KEY, None)
    _apply_now(session)


def bind_system(session: Session, reason: str) -> None:
    if not hasattr(session, "info"):
        return
    session.info[_SYSTEM_KEY] = reason
    _apply_now(session)


def bind_connection_system(connection) -> None:
    """System scope for a raw Connection used without a Session (operator scripts, ingestion). The setting is
    transaction-local, so call it first in each transaction that reads or writes tenant-owned rows."""
    connection.execute(_APPLY, {"tenant": "", "bypass": system_token()})


def scope_of(session: Session) -> dict:
    return {"tenant_id": session.info.get(_TENANT_KEY), "system_reason": session.info.get(_SYSTEM_KEY)}


@event.listens_for(Session, "after_begin")
def _apply_scope_on_begin(session: Session, transaction, connection) -> None:
    if session.info.get(_TENANT_KEY) or session.info.get(_SYSTEM_KEY):
        values = _values(session)
        # A SAVEPOINT runs inside a transaction that already holds these settings (they last until it ends): applying
        # them again cost one statement per savepoint. After any rollback they are applied again, as before.
        if getattr(transaction, "nested", False) and session.info.get(_APPLIED_KEY) == values:
            return
        connection.execute(_APPLY, values)
        session.info[_APPLIED_KEY] = values


@event.listens_for(Session, "after_soft_rollback")
def _forget_applied_on_rollback(session: Session, _previous) -> None:
    session.info.pop(_APPLIED_KEY, None)


@event.listens_for(Session, "after_transaction_end")
def _forget_applied_at_end(session: Session, transaction) -> None:
    if not transaction.nested:
        session.info.pop(_APPLIED_KEY, None)


class _SessionConnectionSource:
    """Engine-like adapter for services that call ``.connect()``: hands out the session's own connection, so the
    queries run inside the session's transaction and keep its tenant scope (a fresh engine connection would not)."""

    def __init__(self, session: Session):
        self._session = session

    @contextmanager
    def connect(self):
        yield self._session.connection()


def scoped_bind(session: Session) -> _SessionConnectionSource:
    return _SessionConnectionSource(session)


def system_token_accepted(connection) -> bool:
    """True when the database accepts this server's system token (both sides hold the same secret)."""
    try:
        connection.execute(text("SELECT set_config('app.rls_bypass', :token, true)"), {"token": system_token()})
        return bool(connection.execute(text("SELECT public.mdarix_system_scope()")).scalar())
    finally:
        connection.rollback()  # the setting was transaction-local; nothing else was done
