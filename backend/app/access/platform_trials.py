"""Trial organizations (TO-1): the Platform Administrator's one page for free trials.

Every route checks the Platform Administrator first (``_require_platform_admin``: PLATFORM_ADMIN or
MDARIX_ADMINISTRATOR only). The acting person comes only from the signed-in session; the body carries reasons, days,
plan and dates, never an actor. The trial is the path's tenant, re-checked to be a trial organization. The work is
in backend/app/trial/admin_actions.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.access.authz import _require_platform_admin
from backend.app.db.session import get_db
from backend.app.trial import admin_actions

router = APIRouter(prefix="/api/v1", tags=["Trial organizations"])

BASE = "/platform-admin/trial-organizations"


class ExtendRequest(BaseModel):
    days: int
    reason: str = Field(max_length=1000)


class EndRequest(BaseModel):
    reason: str = Field(max_length=1000)


class ConvertRequest(BaseModel):
    kind: str = Field(max_length=10)
    plan_id: uuid.UUID
    starts_at: str = Field(max_length=40)
    expires_at: str = Field(max_length=40)
    reason: str = Field(max_length=1000)


class DeleteDataRequest(BaseModel):
    confirm_name: str = Field(max_length=200)


def _moment(value: str, field: str) -> datetime:
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise admin_actions.TrialRefused(422, "INVALID_DATE", f"{field} must be an ISO date and time")
    if moment.tzinfo is None:
        raise admin_actions.TrialRefused(422, "INVALID_DATE", f"{field} must carry its time zone")
    return moment


def _audited(db: Session, tenant_id: uuid.UUID, admin, action: str, work):
    """Run ``work``; a refusal is audited ``TRIAL_ACTION_REFUSED`` in the trial's trail, then raised."""
    try:
        return work()
    except admin_actions.TrialRefused as refusal:
        admin_actions.audit_refusal(db, tenant_id, admin, action, refusal)
        raise


@router.get(f"{BASE}/summary")
def trial_organizations_summary(request: Request, db: Session = Depends(get_db)):
    """The header strip: waiting for review, active, ending within 7 days, ended with data kept, exit requests
    waiting, converted this month."""
    _require_platform_admin(request, db)
    return admin_actions.summary(db)


@router.get(BASE)
def trial_organizations(
    request: Request,
    page: int = 1,
    page_size: int = 50,
    sort: str = "",
    order: str = "",
    state: str = "",
    q: str = "",
    db: Session = Depends(get_db),
):
    """The Trials list, one page, filtered on the server by ``state`` (ACTIVE, ENDING_SOON, ENDED, ENDED_EARLY,
    DATA_DELETED, CONVERTED) and ``q``; by default the trials that need attention first."""
    _require_platform_admin(request, db)
    if state.strip() and state.strip().upper() not in admin_actions.LIST_STATES:
        raise HTTPException(
            422,
            detail={
                "code": "INVALID_TRIAL_STATE",
                "message": "state is one of " + ", ".join(admin_actions.LIST_STATES),
            },
        )
    return admin_actions.trial_list(db, page=page, page_size=page_size, sort=sort, order=order, state=state, q=q)


@router.get(BASE + "/{tenant_id}")
def trial_organization(tenant_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    """One trial (or a converted one, read-only) with what can be done now."""
    _require_platform_admin(request, db)
    return admin_actions.detail(db, tenant_id)


@router.post(BASE + "/{tenant_id}/extend")
def extend_trial(tenant_id: uuid.UUID, payload: ExtendRequest, request: Request, db: Session = Depends(get_db)):
    admin = _require_platform_admin(request, db)
    return _audited(
        db,
        tenant_id,
        admin,
        "EXTEND",
        lambda: admin_actions.extend(db, tenant_id, admin, days=payload.days, reason=payload.reason),
    )


@router.post(BASE + "/{tenant_id}/end")
def end_trial(
    tenant_id: uuid.UUID,
    payload: EndRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """MDARIX ends the trial now: an exit request "Ended by MDARIX", approved in the same step; data kept 30 days."""
    admin = _require_platform_admin(request, db)
    outcome = _audited(
        db, tenant_id, admin, "END", lambda: admin_actions.end_early(db, tenant_id, admin, reason=payload.reason)
    )
    outcome.pop("notify", None)
    return outcome


@router.post(BASE + "/{tenant_id}/convert")
def convert_trial(tenant_id: uuid.UUID, payload: ConvertRequest, request: Request, db: Session = Depends(get_db)):
    admin = _require_platform_admin(request, db)
    return _audited(
        db,
        tenant_id,
        admin,
        "CONVERT",
        lambda: admin_actions.convert(
            db,
            tenant_id,
            admin,
            kind=payload.kind,
            plan_id=payload.plan_id,
            starts_at=_moment(payload.starts_at, "starts_at"),
            expires_at=_moment(payload.expires_at, "expires_at"),
            reason=payload.reason,
        ),
    )


@router.post(BASE + "/{tenant_id}/delete-data")
def delete_trial_data(
    tenant_id: uuid.UUID, payload: DeleteDataRequest, request: Request, db: Session = Depends(get_db)
):
    """Delete a due trial's data now (30+ days after its end, no hold), with the organization's name typed."""
    admin = _require_platform_admin(request, db)
    return _audited(
        db,
        tenant_id,
        admin,
        "DELETE_DATA",
        lambda: admin_actions.delete_data(db, tenant_id, admin, confirm_name=payload.confirm_name),
    )
