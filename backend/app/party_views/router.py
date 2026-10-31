"""The distributor and authorised-representative preview API (T-G37P): three read-only pages inside the trial user's
own session, for a free trial only (a pilot gets 404; 1.0.1 brings the real views, G14 and G37).

- ``GET /api/v1/trial/preview/intake``: the distributor's intake form, filled with a sample submission;
- ``GET /api/v1/trial/preview/distributor``: the sample distributor's own complaints and their status;
- ``GET /api/v1/trial/preview/authorised-representative``: the sample authorised representative's portfolio, its
  high-risk and recurring-issues panels and the PRRC note.

There is no write route: nothing on the pages can be sent or changed. Every opening is in the audit trail.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.party_views import preview
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.trial.service import trial_subscription

router = APIRouter(prefix="/api/v1/trial/preview", tags=["Distributor and authorised-representative preview"])

AUDIT_ACTION = "PARTY_VIEW_PREVIEW_OPENED"
PAGES = {
    "intake": preview.intake,
    "distributor": preview.distributor_status,
    "authorised-representative": preview.authorised_representative,
}


@router.get("/{page}")
def open_preview(
    page: str,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = uuid.UUID(ctx.tenant_id)
    if trial_subscription(control_db, tenant_id) is None:
        raise HTTPException(
            404, detail={"code": "NOT_A_TRIAL_WORKSPACE", "message": "This workspace is not on the free trial"}
        )
    build = PAGES.get(page)
    if build is None:
        raise HTTPException(404, detail={"code": "PREVIEW_NOT_FOUND", "message": "No such preview page"})
    body = build(db, tenant_id)
    control_db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action=AUDIT_ACTION,
            entity_type="PartyViewPreview",
            correlation_id=ctx.correlation_id,
            details={"page": body["page"], "party": body["party"]},
        )
    )
    control_db.commit()
    return body
