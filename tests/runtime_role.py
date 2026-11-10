"""API requests under the least-privilege runtime role, as in production, even where MDARIX_DB_RUNTIME_USER is not
configured locally (DB-14).

Every request session comes from ``RuntimeSessionLocal`` (``get_db``). Without a configured runtime user it falls
back to the owner connection, which row-level security does not filter. The fixture binds request sessions to an
owner connection that has switched to ``mdarix_runtime`` (``SET ROLE``), so Postgres applies the forced policies to
every route the test calls. Test setup keeps using ``SessionLocal`` (the owner).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event, text

from backend.app.db import session as db_session
from backend.app.db.tls import connect_args

RUNTIME_ROLE = "mdarix_runtime"


def _runtime_engine():
    engine = create_engine(
        db_session.engine.url, future=True, hide_parameters=True, pool_size=2, connect_args=connect_args()
    )

    @event.listens_for(engine, "connect")
    def _as_runtime_role(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute(f"SET ROLE {RUNTIME_ROLE}")
        cursor.close()
        dbapi_connection.commit()  # a SET inside a transaction that is rolled back would be undone

    return engine


@pytest.fixture
def runtime_role_requests():
    """Route every API request of the test through the runtime role; yields the engine requests use."""
    if db_session.runtime_role_active():
        yield db_session.runtime_engine
        return
    engine = _runtime_engine()
    db_session.RuntimeSessionLocal.configure(bind=engine)
    try:
        with engine.connect() as connection:
            flags = connection.execute(
                text("SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
            ).one()
        assert tuple(flags) == (RUNTIME_ROLE, False, False), "requests must run as the RLS-bound runtime role"
        yield engine
    finally:
        db_session.RuntimeSessionLocal.configure(bind=db_session.runtime_engine)
        engine.dispose()
