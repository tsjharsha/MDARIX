"""B7b (spec section 4): e-mail intake on our own receiver, ``mail-in``.

Switched OFF unless ``MDARIX_EMAIL_INTAKE=on``: production mail (port 25, the MX record for the intake subdomain, a
certificate for STARTTLS) is an operations task not yet done. Off, the receiver does not listen, the API routes answer
404 and no screen shows. An e-mail is never a complaint by itself: at most it becomes a Case that a person classifies
and signs.
"""

from __future__ import annotations

import os

PROVIDER = "MDARIX_MAIL"  # inbound_provider_mappings.provider for an intake address (no new table)
DEFAULT_DOMAIN = "intake.mdarix.com"


def enabled() -> bool:
    """Read on every call, like the feature set, so a process never caches a wrong answer and tests can set it."""
    return os.getenv("MDARIX_EMAIL_INTAKE", "").strip().lower() in ("1", "on", "true", "yes")


def domain() -> str:
    return os.getenv("MDARIX_INTAKE_DOMAIN", "").strip().lower() or DEFAULT_DOMAIN
