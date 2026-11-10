"""``GET /api/v1/investigations/{investigation_id}/did-it-work`` (B5b): what happened after the investigation's signed
decision (closed_loop/service.py), a read for anyone who can open the investigation. Per-lot rows are a free trial's
only, like Lot impact and Supplier 360's lots (owner, 1 Nov; B5-D9); versions and cohort totals show everywhere.
Off with ``MDARIX_CLOSED_LOOP=off`` (feature_set.py)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.case_intelligence.router import _case, _tenant, now_utc
from backend.app.closed_loop.service import did_it_work
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.session import get_db
from backend.app.request_context import AuthenticatedRequestContext, get_request_context

router = APIRouter(prefix="/api/v1/investigations/{investigation_id}/did-it-work", tags=["Did it work?"])
# Per-lot rows for a free trial only (B5-D9); False offers them to pilots too.
LOTS_TRIAL_ONLY = True


@router.get("")
def read_did_it_work(
    investigation_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    from backend.app.signer_training.router import is_trial

    case = _case(db, _tenant(ctx), investigation_id)
    lot_rows = not LOTS_TRIAL_ONLY or is_trial(control_db, ctx.tenant_id)
    return did_it_work(db, case, now_utc().date(), lot_rows=lot_rows)
