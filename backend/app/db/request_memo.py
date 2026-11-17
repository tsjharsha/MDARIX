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
@event.listens_for(Session, "after_rollback")
@event.listens_for(Session, "after_soft_rollback")  # a savepoint rolled back too
def _forget(session, *_) -> None:
    session.info.pop(_KEY, None)


@event.listens_for(Session, "after_transaction_end")
def _forget_at_commit(session, transaction) -> None:
    """The request's transaction ended (commit or rollback). A savepoint released by ``begin_nested()`` is not the end
    of one: it wrote nothing (a write flushes first, which drops the memo), so the memo stays; ``after_commit`` fires
    for savepoints too, which made a page that reads each section in a savepoint read its settings again each time."""
    if not transaction.nested:
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


def any_of(column, values):
    """``column`` is one of ``values``, sent as ONE array parameter (B6a run 3): an ``IN`` list binds one parameter
    per value, and the driver allows 65,535, which a full triage read of a large import can pass."""
    from sqlalchemy import any_, literal
    from sqlalchemy.dialects.postgresql import ARRAY

    return column == any_(literal(list(values), ARRAY(column.type)))
