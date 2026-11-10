"""Which features this deployment offers: everything, or the lightweight MVP.

``MDARIX_FEATURE_SET``:

- ``full`` (the default): every screen and route, as built. Development, CI and every existing deployment run this
  way, so nothing changes until a deployment chooses ``mvp``.
- ``mvp``: the lightweight MVP (docs: MDARIX Final Lightweight MVP Plan). Areas the MVP parks are hidden from the
  interface (the session context names the feature set) and their API routes answer 404 here, before any handler
  runs. Parked code is kept, with its tests, and comes back by setting ``full``.

A free trial always gets the MVP interface (``for_tenant``), whatever the deployment's setting: a trial shows the five
screens the MVP is built around, not every screen as built. Its API routes follow the deployment's setting.

A route is parked only when no screen the MVP keeps calls it. The failure-chain route, for example, stays served:
the investigation panel's "unknowns and chain" step still calls it. The value is read from the environment on every
call, so a process never caches a wrong answer and tests can set it.

``MDARIX_ROUTINE_PATH`` (B7a, owner decision 11 Nov): on unless ``off``. Off, the B7a routes answer 404 (Resolve and
close, the Cases exports, adding a file to a Case, the alerts-and-files setting), the session's ``routine_path`` is
false so its screens and next-step wording hide, and the closure checklist has no CUSTOMER_TOLD item (closing behaves
as before B7). Records already signed stay readable, and a complaint MDARIX closed can still reopen.
"""

from __future__ import annotations

import os
import re

FULL = "full"
MVP = "mvp"
FEATURE_SETS = frozenset({FULL, MVP})

# API routes of the parked areas, refused under ``mvp``. Each one is called only by a screen the MVP hides.
_PARKED_API = tuple(
    re.compile(pattern)
    for pattern in (
        # Regulatory copilot and the eSTAR preparation package.
        r"^/api/v1/regulatory(/|$)",
        # The Risk & Traceability workspace (the risk review inside a case is a different route and stays).
        r"^/api/v1/risk(/|$)",
        # Counterfactual and scenario engines (fixed-text "what if" output).
        r"^/api/v1/investigations/counterfactuals(/|$)",
        r"^/api/v1/investigations/[^/]+/counterfactuals(/|$)",
        r"^/api/v1/investigations/[^/]+/scenarios(/|$)",
        # The legacy Decision Center (the current decision is /investigations/{id}/decision and /decisions/...).
        r"^/api/v1/investigations/decisions(/|$)",
        r"^/api/v1/investigations/[^/]+/(decisions|decision-context|decision-advisory)(/|$)",
        # Public demo requests: the website offers none (frontend/src/site/offer.ts), and the route mailed the name a
        # visitor typed to any address they chose (pre-launch review SEC-04).
        r"^/api/v1/public/demo-requests/?$",
        # The static agent catalog (fixed text describing "agents"); the trust policy (/api/v1/ai/trust-policy)
        # shows what every AI result is checked for instead.
        r"^/api/v1/ai/agents/catalog/?$",
    )
)


# B7a routes refused while MDARIX_ROUTINE_PATH is off: (method or None for every method, path).
_ROUTINE_PATH_API = tuple(
    (method, re.compile(pattern))
    for method, pattern in (
        (None, r"^/api/v1/complaints/[^/]+/resolve-and-close/?$"),
        (None, r"^/api/v1/intake/(cases|qms-entry)/export\.csv$"),
        ("POST", r"^/api/v1/intake/[^/]+/attachments/?$"),
        (None, r"^/api/v1/oversight/settings/alerts-and-files/?$"),
    )
)


def routine_path() -> bool:
    """B7a is on unless ``MDARIX_ROUTINE_PATH=off`` (read on every call)."""
    return os.getenv("MDARIX_ROUTINE_PATH", "").strip().lower() not in ("off", "0", "false", "no")


def feature_set() -> str:
    """The configured feature set, ``full`` when unset. An unknown value is refused here (and reported by
    config_check)."""
    value = os.getenv("MDARIX_FEATURE_SET", "").strip().lower() or FULL
    if value not in FEATURE_SETS:
        raise RuntimeError(f"MDARIX_FEATURE_SET must be one of {', '.join(sorted(FEATURE_SETS))}, not {value!r}")
    return value


def is_mvp() -> bool:
    return feature_set() == MVP


def for_tenant(db, tenant_id) -> str:
    """The feature set a tenant's interface shows: ``mvp`` where the deployment runs it, and for a tenant on the Free
    Trial plan; otherwise the deployment's setting."""
    configured = feature_set()
    if configured == MVP or tenant_id is None:
        return configured
    from backend.app.trial.service import trial_subscription

    return MVP if trial_subscription(db, tenant_id) is not None else configured


def serves_path(path: str, method: str = "GET") -> bool:
    """Whether this deployment's feature set serves the request path: always under ``full``; under ``mvp``,
    everything except the parked routes; with B7a off, nothing of B7a's."""
    if not routine_path() and any(
        pattern.match(path) and verb in (None, method.upper()) for verb, pattern in _ROUTINE_PATH_API
    ):
        return False
    if not is_mvp():
        return True
    return not any(pattern.match(path) for pattern in _PARKED_API)
