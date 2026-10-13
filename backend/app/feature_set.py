"""Which features this deployment offers: everything, or the lightweight MVP.

``MDARIX_FEATURE_SET``:

- ``full`` (the default): every screen and route, as built. Development, CI and every existing deployment run this
  way, so nothing changes until a deployment chooses ``mvp``.
- ``mvp``: the lightweight MVP (docs: MDARIX Final Lightweight MVP Plan). Areas the MVP parks are hidden from the
  interface (the session context names the feature set) and their API routes answer 404 here, before any handler
  runs. Parked code is kept, with its tests, and comes back by setting ``full``.

A route is parked only when no screen the MVP keeps calls it. The failure-chain route, for example, stays served:
the investigation panel's "unknowns and chain" step still calls it. The value is read from the environment on every
call, so a process never caches a wrong answer and tests can set it.
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
    )
)


def feature_set() -> str:
    """The configured feature set, ``full`` when unset. An unknown value is refused here (and reported by
    config_check)."""
    value = os.getenv("MDARIX_FEATURE_SET", "").strip().lower() or FULL
    if value not in FEATURE_SETS:
        raise RuntimeError(f"MDARIX_FEATURE_SET must be one of {', '.join(sorted(FEATURE_SETS))}, not {value!r}")
    return value


def is_mvp() -> bool:
    return feature_set() == MVP


def serves_path(path: str) -> bool:
    """Whether this deployment's feature set serves the request path: always under ``full``; under ``mvp``,
    everything except the parked routes."""
    if not is_mvp():
        return True
    return not any(pattern.match(path) for pattern in _PARKED_API)
