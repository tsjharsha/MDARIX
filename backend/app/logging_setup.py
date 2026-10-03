"""Process-wide logging: one line per record, JSON in staging and production, with the request id attached.

``MDARIX_LOG_LEVEL`` (default INFO) and ``MDARIX_LOG_FORMAT`` (``json`` or ``text``; default json outside local
development) control the output. Every record logged while a request is being handled carries that request's id,
which the API also returns in the ``X-Request-ID`` header and in error bodies, so a customer's report can be matched
to the server log line.

When ``MDARIX_SENTRY_DSN`` is set and the ``sentry-sdk`` package is installed, unhandled errors are also reported to
Sentry, without request bodies, cookies, headers or user details.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import sys
from datetime import datetime, timezone

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("mdarix_request_id", default=None)

_configured = False


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None)
        if request_id:
            payload["request_id"] = request_id
        for key in ("method", "path", "status_code", "duration_ms", "tenant_id"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def _json_output() -> bool:
    from backend.app.runtime_env import is_local

    configured = os.getenv("MDARIX_LOG_FORMAT", "").strip().lower()
    if configured in {"json", "text"}:
        return configured == "json"
    return not is_local()


def _scrub_event(event, _hint):
    request = event.get("request") or {}
    for key in ("cookies", "data", "headers", "query_string", "env"):
        request.pop(key, None)
    event.pop("user", None)
    return event


def _init_sentry() -> None:
    dsn = os.getenv("MDARIX_SENTRY_DSN", "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk
    except ImportError:
        logging.getLogger(__name__).warning("MDARIX_SENTRY_DSN is set but sentry-sdk is not installed")
        return
    from backend.app.runtime_env import environment

    sentry_sdk.init(
        dsn=dsn,
        environment=environment(),
        send_default_pii=False,
        traces_sample_rate=float(os.getenv("MDARIX_SENTRY_TRACES_SAMPLE_RATE", "0") or 0),
        before_send=_scrub_event,
    )


def configure_logging() -> None:
    """Set up the root logger once per process (safe to call again)."""
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_RequestIdFilter())
    handler.setFormatter(
        JsonFormatter()
        if _json_output()
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s")
    )
    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(os.getenv("MDARIX_LOG_LEVEL", "INFO").strip().upper() or "INFO")
    # uvicorn's access log duplicates the request log line written by the API.
    logging.getLogger("uvicorn.access").propagate = False
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
    _init_sentry()
    _configured = True


_REQUEST_ID_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.:")


def accept_request_id(value: str | None) -> str | None:
    """A caller-supplied request id, only when it is short and plain (it is written to logs and audit records)."""
    candidate = (value or "").strip()
    if 8 <= len(candidate) <= 128 and set(candidate) <= _REQUEST_ID_CHARS:
        return candidate
    return None


def current_request_id(request=None) -> str:
    """The id of the request being handled (set by the API's request-id middleware), or a new one."""
    import uuid

    state = getattr(request, "state", None) if request is not None else None
    found = getattr(state, "request_id", None) if state is not None else None
    if found:
        return found
    found = request_id_var.get()
    if found:
        return found
    if request is not None:
        supplied = accept_request_id(request.headers.get("x-request-id") or request.headers.get("x-correlation-id"))
        if supplied:
            return supplied
    return uuid.uuid4().hex
