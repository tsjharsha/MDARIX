"""Longer database timeouts for the background service (DB-1, owner decision 4, 14 Nov 2026).

The runtime role's own defaults (scripts/configure_runtime_role.py) stay as the application's: 60 s for a statement
and for an idle transaction, and a 75 s socket timeout (``tls.socket_timeout``). A scheduled job or an outbox event
(a retention purge, an embedding catch-up, a report) may run longer, so the scheduler and the outbox worker call
``use_background_timeouts()`` first thing: from then on every new connection of that process (the control engine and
every data-plane engine) runs ``SET statement_timeout`` and ``SET idle_in_transaction_session_timeout`` to
``MDARIX_DB_JOB_STATEMENT_TIMEOUT`` (300 s by default) as it opens, and waits on the socket for
``MDARIX_DB_JOB_SOCKET_TIMEOUT_SECONDS`` (330 s, above the statement timeout so the server cancels first) where the
engine sets a socket timeout at all. The API process never calls it, so requests keep 60 s.
"""

from __future__ import annotations

import os
import re

from sqlalchemy import event
from sqlalchemy.engine import Engine

_VALUE = re.compile(r"^\d+(ms|s|min)?$")
_installed: dict = {}


def job_statement_timeout() -> str:
    value = os.getenv("MDARIX_DB_JOB_STATEMENT_TIMEOUT", "300s").strip()
    if not _VALUE.match(value):
        raise ValueError("MDARIX_DB_JOB_STATEMENT_TIMEOUT must be a number with ms, s or min (for example 300s)")
    return value


def job_socket_timeout() -> int:
    return int(os.getenv("MDARIX_DB_JOB_SOCKET_TIMEOUT_SECONDS", "330"))


def _on_connect(dbapi_connection, _record) -> None:
    value = _installed["statement"]
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute(f"SET statement_timeout = '{value}'")
        cursor.execute(f"SET idle_in_transaction_session_timeout = '{value}'")
    finally:
        cursor.close()
    dbapi_connection.commit()  # a SET outside a transaction block: end the one the driver opened


def _on_do_connect(_dialect, _record, _cargs, cparams) -> None:
    if "timeout" in cparams:  # request-path engines only; the owner engine has no socket timeout
        cparams["timeout"] = max(int(cparams["timeout"]), _installed["socket"])


def use_background_timeouts(target=Engine) -> str:
    """Give every connection ``target`` opens from now on the background timeouts (``target``: every engine of the
    process, or one engine in a test). Idempotent; returns the statement timeout."""
    if target not in _installed.get("targets", ()):
        _installed["statement"] = job_statement_timeout()
        _installed["socket"] = job_socket_timeout()
        event.listen(target, "do_connect", _on_do_connect)
        event.listen(target, "connect", _on_connect)
        _installed.setdefault("targets", []).append(target)
    return _installed["statement"]


def stop_background_timeouts(target=Engine) -> None:
    """Undo ``use_background_timeouts`` for ``target`` (tests)."""
    if target in _installed.get("targets", ()):
        event.remove(target, "do_connect", _on_do_connect)
        event.remove(target, "connect", _on_connect)
        _installed["targets"].remove(target)
