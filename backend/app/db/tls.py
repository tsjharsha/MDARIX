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


def connect_args() -> dict:
    """Keyword arguments for SQLAlchemy's ``create_engine(connect_args=...)`` with pg8000."""
    context = ssl_context()
    return {"ssl_context": context} if context is not None else {}
