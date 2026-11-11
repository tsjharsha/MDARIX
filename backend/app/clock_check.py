"""Clock check (B6a G19): audit entries and signatures are timed by the application server's clock, so that clock must
agree with the database's and with the trusted time source (the host's chrony, B6a-D7).

- **App vs database:** the database's ``clock_timestamp()`` against the app's time at the middle of the round trip.
- **App vs NTP:** when ``MDARIX_NTP_SERVER`` is set, one standard-library SNTP query (no new dependency), cached five
  minutes so frequent readiness probes do not load the time server. Unreachable is ``unknown``, never ``ok``.
- **Limit:** 1 s (B6a-D7). Above it, or unknown, the readiness check is not ok and the operations alert fires once and
  once when it clears, naming the last good check: the audit entries and signatures made since then are the ones to
  look at. Records are never re-timed.

``scripts/clock_check.py`` prints and saves the same figures, plus ``chronyc tracking`` on the host, for the release IQ
and the restore drill.
"""

from __future__ import annotations

import os
import socket
import struct
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import text

LIMIT_SECONDS = 1.0
NTP_ENV = "MDARIX_NTP_SERVER"
NTP_CACHE_SECONDS = 300
NTP_TIMEOUT = 2.0
OK, DEGRADED, UNKNOWN = "ok", "degraded", "unknown"
_NTP_EPOCH = 2208988800  # seconds from 1900-01-01 (NTP) to 1970-01-01 (Unix)
_lock = threading.Lock()
_ntp_cache: tuple[float, str, float | None] | None = None


def database_offset(connection, clock=time.time) -> float:
    """Seconds the database clock is ahead of the app's (negative: behind), corrected for the round trip."""
    before = clock()
    database = float(connection.execute(text("SELECT extract(epoch FROM clock_timestamp())")).scalar_one())
    after = clock()
    return database - (before + after) / 2


def _ntp_time(value: bytes) -> float:
    seconds, fraction = struct.unpack("!II", value)
    return seconds - _NTP_EPOCH + fraction / 2**32


def sntp_offset(server: str, timeout: float = NTP_TIMEOUT, clock=time.time) -> float | None:
    """Seconds the time server is ahead of the app (RFC 4330 offset); None when it cannot be reached or answers
    nonsense."""
    host, _, port = server.partition(":")
    request = b"\x1b" + 47 * b"\0"  # version 3, client mode
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sent = clock()
            sock.sendto(request, (host, int(port or 123)))
            answer, _ = sock.recvfrom(512)
            received = clock()
    except (OSError, ValueError):
        return None
    if len(answer) < 48 or answer[1] == 0:  # stratum 0: a "kiss of death", no time
        return None
    server_received, server_sent = _ntp_time(answer[32:40]), _ntp_time(answer[40:48])
    return ((server_received - sent) + (server_sent - received)) / 2


def _ntp(now: float) -> tuple[str | None, float | None]:
    """The configured server and its offset, cached NTP_CACHE_SECONDS; (None, None) when no server is set."""
    global _ntp_cache
    server = os.getenv(NTP_ENV, "").strip()
    if not server:
        return None, None
    with _lock:
        if _ntp_cache and _ntp_cache[1] == server and now - _ntp_cache[0] < NTP_CACHE_SECONDS:
            return server, _ntp_cache[2]
        offset = sntp_offset(server)
        _ntp_cache = (now, server, offset)
        return server, offset


def assess(database: float | None, ntp: float | None, ntp_server: str | None, limit: float = LIMIT_SECONDS) -> dict:
    """The check's verdict from the measured offsets (seconds): degraded above the limit, unknown when a source could
    not be measured, ok otherwise."""
    measured = [abs(value) for value in (database, ntp) if value is not None]
    if any(value > limit for value in measured):
        state = DEGRADED
    elif database is None or (ntp_server and ntp is None):
        state = UNKNOWN
    else:
        state = OK
    return {
        "state": state,
        "limit_seconds": limit,
        "database_offset_seconds": None if database is None else round(database, 3),
        "ntp_server": ntp_server,
        "ntp_offset_seconds": None if ntp is None else round(ntp, 3),
    }


def check(connection) -> dict:
    """Measure and assess now (``connection``: a SQLAlchemy connection or session)."""
    try:
        database = database_offset(connection)
    except Exception:
        database = None
    server, ntp = _ntp(time.monotonic())
    return {**assess(database, ntp, server), "checked_at": datetime.now(timezone.utc).isoformat()}


def alert(state: dict, result: dict, send) -> None:
    """Tell operations once when the clock goes out of step (or cannot be checked) and once when it is back. ``state``
    is the scheduler job's kept state; ``send(title, body)`` sends the alert."""
    bad = result["state"] != OK
    since = state.get("clock_good_at") or "the last good check (none recorded)"
    if bad and not state.get("clock_bad"):
        figures = (
            f"database {result['database_offset_seconds']} s, NTP {result['ntp_offset_seconds']} s "
            f"({result['ntp_server'] or 'no time server set'}), limit {result['limit_seconds']} s"
        )
        send(
            "Clock out of step" if result["state"] == DEGRADED else "Clock cannot be checked",
            f"The application clock check is {result['state']}: {figures}. Check the audit entries and signatures made "
            f"since {since}; open a deviation if their times may be wrong. Records are never re-timed.",
        )
    elif not bad and state.get("clock_bad"):
        send(
            "Clock back in step", f"The application, database and time server agree within {result['limit_seconds']} s."
        )
    if not bad:
        state["clock_good_at"] = result["checked_at"]
    state["clock_bad"] = bad
