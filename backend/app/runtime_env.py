"""Runtime environment, failing safe.

MDARIX_ENV selects development conveniences (tokens shown on screen, relaxed network checks, API docs). When it is
unset or unrecognised the application runs as production, with every protection on, so a missing setting can never
weaken a deployed server. Local machines and test runs set MDARIX_ENV explicitly.
"""

from __future__ import annotations

import os

DEVELOPMENT = "development"
TEST = "test"
STAGING = "staging"
PRODUCTION = "production"
_KNOWN = {DEVELOPMENT, TEST, STAGING, PRODUCTION}


def environment() -> str:
    value = os.getenv("MDARIX_ENV", "").strip().lower()
    return value if value in _KNOWN else PRODUCTION


def is_development() -> bool:
    return environment() == DEVELOPMENT


def is_local() -> bool:
    """Development or automated test runs on a developer or CI machine."""
    return environment() in {DEVELOPMENT, TEST}


def is_production_like() -> bool:
    return environment() in {PRODUCTION, STAGING}
