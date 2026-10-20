"""The "latest saved result" reads of a case's AI steps when nothing is saved yet.

``GET .../analysis/latest``, ``.../hypotheses``, ``.../challenges``, ``.../unknowns``, ``.../failure-chains`` and
``.../briefs/latest`` answer 404 while a step has never been run. That stays the default. The case workspace reads all
six whenever a case opens, so a new case filled the browser console with six 404s (UX-15, 0.10.37). It asks with
``?missing=empty`` instead and gets 200 with the step's field set to null and ``persisted: false``, which the workspace
reads as "nothing saved yet".
"""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

MISSING_PARAMETER = "missing"
EMPTY = "empty"


def nothing_saved(request: Request | None, field: str, code: str, message: str) -> JSONResponse:
    """The answer for a step with no saved result: 200 ``{field: null, "persisted": false}`` when the caller asked
    for it with ``?missing=empty``, else the 404 the route has always given. Raises the 404."""
    if request is not None and request.query_params.get(MISSING_PARAMETER) == EMPTY:
        return JSONResponse({field: None, "persisted": False})
    raise HTTPException(status_code=404, detail={"code": code, "message": message})
