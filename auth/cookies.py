"""The session cookie: one name, one set of flags, everywhere.

Outside local development the cookie is ``__Host-mdarix_session``: browsers accept that name only with ``Secure``,
``Path=/`` and no ``Domain``, so a neighbouring subdomain cannot plant or overwrite it. Local development over plain
HTTP keeps ``mdarix_session`` (``MDARIX_COOKIE_SECURE=true`` opts development into the secure cookie too).

Session lifetime: a session is issued for one window (``SESSION_WINDOW_SECONDS``) and, while it is being used,
renewed by another window each time less than ``SESSION_RENEWAL_SECONDS`` of it remain, but never past
``SESSION_SECONDS`` after sign-in (the absolute limit). The idle timeout (``MDARIX_SESSION_IDLE_MINUTES``,
backend/app/request_context.py) ends an unused session well before any of these.
"""

from __future__ import annotations

import os

from starlette.requests import Request
from starlette.responses import Response

from backend.app.runtime_env import is_development

SECURE_NAME = "__Host-mdarix_session"
LOCAL_NAME = "mdarix_session"
# The absolute limit: no session lives longer than this after sign-in, however active it is.
SESSION_SECONDS = 12 * 3600
# The window a session is issued for, and the step each renewal adds (up to the absolute limit).
SESSION_WINDOW_SECONDS = 3600
# Renew when less than this remains of the current window and the session is in use.
SESSION_RENEWAL_SECONDS = 30 * 60
# A session that still owes its second factor may only use the MFA steps, and not for long.
PENDING_MFA_SECONDS = 600


def secure_cookies() -> bool:
    if not is_development():
        return True
    return os.getenv("MDARIX_COOKIE_SECURE", "false").strip().lower() == "true"


def session_cookie_name() -> str:
    return SECURE_NAME if secure_cookies() else LOCAL_NAME


def read_session_token(request: Request) -> str | None:
    """The raw session token from the request, or None. Only the cookie name of this environment is accepted."""
    value = request.cookies.get(session_cookie_name())
    return value or None


def set_session_cookie(response: Response, token: str, max_age: int = SESSION_WINDOW_SECONDS) -> None:
    response.set_cookie(
        session_cookie_name(),
        token,
        max_age=max_age,
        path="/",
        secure=secure_cookies(),
        httponly=True,
        # Strict: the browser sends the session only on requests MDARIX's own pages make (every API call); a link from
        # an email or another site opens the app without it, and the app's first call carries it.
        samesite="strict",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(session_cookie_name(), path="/", secure=secure_cookies(), httponly=True, samesite="strict")
