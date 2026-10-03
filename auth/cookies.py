"""The session cookie: one name, one set of flags, everywhere.

Outside local development the cookie is ``__Host-mdarix_session``: browsers accept that name only with ``Secure``,
``Path=/`` and no ``Domain``, so a neighbouring subdomain cannot plant or overwrite it. Local development over plain
HTTP keeps ``mdarix_session`` (``MDARIX_COOKIE_SECURE=true`` opts development into the secure cookie too).
"""

from __future__ import annotations

import os

from starlette.requests import Request
from starlette.responses import Response

from backend.app.runtime_env import is_development

SECURE_NAME = "__Host-mdarix_session"
LOCAL_NAME = "mdarix_session"
SESSION_SECONDS = 3600
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


def set_session_cookie(response: Response, token: str, max_age: int = SESSION_SECONDS) -> None:
    response.set_cookie(
        session_cookie_name(),
        token,
        max_age=max_age,
        path="/",
        secure=secure_cookies(),
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(session_cookie_name(), path="/", secure=secure_cookies(), httponly=True, samesite="lax")
