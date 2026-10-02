"""Daily series for the dashboards (platform and customer): a fixed window of days, zero-filled."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func


def window(days: int) -> tuple[int, object, datetime]:
    """(days clamped to 7..90, today, the first instant of the window) in UTC."""
    days = min(90, max(7, days))
    today = datetime.now(timezone.utc).date()
    since = datetime.combine(today - timedelta(days=days - 1), datetime.min.time(), tzinfo=timezone.utc)
    return days, today, since


def daily(rows, days: int, end) -> list[dict]:
    """[{date, ...counts}] for each of the last `days` days, zero-filled. `rows` are (date, key, count)."""
    start = end - timedelta(days=days - 1)
    series = {(start + timedelta(days=offset)).isoformat(): {} for offset in range(days)}
    for day, key, count in rows:
        bucket = series.get(day.isoformat() if hasattr(day, "isoformat") else str(day)[:10])
        if bucket is not None:
            bucket[key] = bucket.get(key, 0) + int(count)
    return [{"date": date, **counts} for date, counts in series.items()]


def run_outcome(status) -> str:
    """An integration run's status as completed, warnings or failed."""
    value = str(status or "").upper()
    if value in {"FAILED", "ERROR", "PARTIAL"}:
        return "failed"
    return "warnings" if "WARNING" in value else "completed"


def per_day(db, since: datetime, column, *conditions, key=None) -> list[tuple]:
    """(day, key, count) rows since `since`; key defaults to "count".

    Group on plain column expressions only: Postgres does not match bound values (literals) in GROUP BY, so callers
    label the groups in Python.
    """
    day = func.date(column)
    if key is None:
        rows = db.query(day, func.count()).filter(column >= since, *conditions).group_by(day).all()
        return [(row[0], "count", row[1]) for row in rows]
    return db.query(day, key, func.count()).filter(column >= since, *conditions).group_by(day, key).all()
