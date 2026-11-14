"""TLS for database connections (pg8000 takes an ``ssl.SSLContext``, not libpq's sslmode).

``POSTGRES_SSLMODE`` follows libpq's names:

* ``disable`` (default for local development): plain TCP; fine for a database on the same machine.
* ``require``: encrypted, the server certificate is not checked (protects against passive listening only).
* ``verify-ca``: encrypted, the certificate must be signed by ``POSTGRES_SSLROOTCERT`` (or the system CAs).
* ``verify-full``: as verify-ca, and the certificate must name the host. Use this with a managed database.

Staging and production refuse to start without ``require`` or stronger (``backend/app/config_check.py``).
"""

from __future__ import annotations

import os
import ssl


def ssl_mode() -> str:
    return os.getenv("POSTGRES_SSLMODE", "disable").strip().lower() or "disable"


def ssl_context() -> ssl.SSLContext | None:
    mode = ssl_mode()
    if mode in {"disable", "allow", "prefer"}:
        return None
    root = os.getenv("POSTGRES_SSLROOTCERT", "").strip() or None
    context = ssl.create_default_context(cafile=root)
    if mode == "require":
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    elif mode == "verify-ca":
        context.check_hostname = False
        context.verify_mode = ssl.CERT_REQUIRED
    elif mode == "verify-full":
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
    else:
        raise ValueError(f"Unsupported POSTGRES_SSLMODE: {mode}")
    return context


def socket_timeout() -> int:
    """Seconds pg8000 waits on the database socket (connect, and each read) before giving up (DB-1, DB-03).

    Above the runtime role's ``statement_timeout`` (configure_runtime_role.py, 60 s by default), so a slow statement is
    cancelled by the server first; an unreachable host fails within this time instead of the system's TCP timeout."""
    return int(os.getenv("MDARIX_DB_SOCKET_TIMEOUT_SECONDS", "75"))


def connect_args(*, request_path: bool = False) -> dict:
    """Keyword arguments for SQLAlchemy's ``create_engine(connect_args=...)`` with pg8000.

    ``request_path``: the engine serves requests and jobs (runtime role, data planes), so it gets the socket timeout.
    The owner engine (migrations, scripts) has none: an index build or a restore may run for a long time."""
    context = ssl_context()
    args: dict = {"ssl_context": context} if context is not None else {}
    if request_path:
        args["timeout"] = socket_timeout()
    return args
