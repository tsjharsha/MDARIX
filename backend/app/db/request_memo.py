"""One read per request (B6a run 3, spec 4.2 "a short per-request memo").

A value read from the database is kept on the database session until that session's next flush, commit or rollback,
so a page that asks for the same settings a dozen times reads them once. A session is one request (or one job's
loop), so nothing is kept across requests, and any write in the request drops what was kept before it is read again.
"""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.orm import Session

_KEY = "mdarix.request_memo"


@event.listens_for(Session, "after_flush")
@event.listens_for(Session, "after_commit")
@event.listens_for(Session, "after_rollback")
def _forget(session, *_) -> None:
    session.info.pop(_KEY, None)


def once(session, key: tuple, read):
    """``read()``, or what it returned for ``key`` earlier on this session since its last flush, commit or rollback."""
    info = getattr(session, "info", None)
    if not isinstance(info, dict):
        return read()  # a test double
    memo = info.setdefault(_KEY, {})
    if key not in memo:
        memo[key] = read()
    return memo[key]
