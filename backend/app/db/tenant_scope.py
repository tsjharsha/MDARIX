"""Bind each database session to one tenant, or to an explicit system scope, for row-level security.

Postgres policies (migration md05) show a tenant-owned row only when app.tenant_id matches it, or when the
transaction runs in system scope (app.rls_bypass = 'on'). The scope is stored on the SQLAlchemy session and applied
at the start of every transaction, so it survives commits within a request. A session with no scope sees no
tenant-owned rows at all.

- bind_tenant: a signed-in request, after the server has resolved the session's tenant.
- bind_system: platform-administrator actions and pre-authentication steps (sign-in, activation, password reset)
  that must read across tenants before a tenant is known. Every call names its reason for review.
"""

from __future__ import annotations

from contextlib import contextmanager
from sqlalchemy import event, text
from sqlalchemy.orm import Session

_TENANT_KEY = "mdarix_tenant_id"
_SYSTEM_KEY = "mdarix_system_reason"
_APPLY = text("SELECT set_config('app.tenant_id', :tenant, true), set_config('app.rls_bypass', :bypass, true)")


def _values(session: Session) -> dict:
    return {
        "tenant": session.info.get(_TENANT_KEY) or "",
        "bypass": "on" if session.info.get(_SYSTEM_KEY) else "off",
    }


def _apply_now(session: Session) -> None:
    # A transaction already in progress keeps its settings until it ends, so update it immediately too.
    if hasattr(session, "in_transaction") and session.in_transaction():
        session.execute(_APPLY, _values(session))


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


def scope_of(session: Session) -> dict:
    return {"tenant_id": session.info.get(_TENANT_KEY), "system_reason": session.info.get(_SYSTEM_KEY)}


@event.listens_for(Session, "after_begin")
def _apply_scope_on_begin(session: Session, _transaction, connection) -> None:
    if session.info.get(_TENANT_KEY) or session.info.get(_SYSTEM_KEY):
        connection.execute(_APPLY, _values(session))


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
