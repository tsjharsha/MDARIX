"""Regulatory reference data (G2a): product registrations, responsible parties, IMDRF codes and the organization's
code mappings (backend/app/regulatory_reference.py). Changes need records.write; deciding a mapping needs
regulatory.approve and a different person from the one who proposed it. Every change is audited."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app import regulatory_reference as reference
from backend.app.access.permissions import RECORDS_WRITE, REGULATORY_APPROVE, require_permission
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import AuditEvent
from backend.app.db.session import get_db
from backend.app.request_context import AuthenticatedRequestContext, get_request_context

router = APIRouter(prefix="/api/v1/regulatory-reference", tags=["Regulatory reference"])
# The code system of a complaint's own problem code (complaints.problem_code), as its IMDRF mappings name it.
PROBLEM_CODES = "problem_code"


def _tenant(ctx: AuthenticatedRequestContext) -> uuid.UUID:
    return uuid.UUID(str(ctx.tenant_id))


def _commit(data: Session, db: Session, ctx, action: str, details: dict) -> None:
    """Save the change, then its audit record (identifiers only; the values are the organization's records)."""
    try:
        data.commit()
    except Exception:
        data.rollback()
        raise
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=_tenant(ctx),
            actor_ref=str(ctx.user_id),
            action=action,
            entity_type="RegulatoryReference",
            details=details,
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()


def _run(data: Session, call):
    try:
        return call()
    except HTTPException:
        data.rollback()
        raise


@router.get("/products/{product_id}")
def product_profile(
    product_id: uuid.UUID,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    data: Session = Depends(get_data_plane_db),
):
    return reference.product_profile(data, _tenant(ctx), product_id)


@router.put("/products/{product_id}/identity", dependencies=[Depends(require_permission(RECORDS_WRITE))])
def set_identity(
    product_id: uuid.UUID,
    payload: dict = Body(...),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    result = _run(data, lambda: reference.set_identity(data, _tenant(ctx), product_id, payload))
    _commit(data, db, ctx, "PRODUCT_IDENTITY_SET", {"product_id": str(product_id)})
    return result


@router.post("/products/{product_id}/registrations", dependencies=[Depends(require_permission(RECORDS_WRITE))])
def add_registration(
    product_id: uuid.UUID,
    payload: dict = Body(...),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    result = _run(data, lambda: reference.add_registration(data, _tenant(ctx), product_id, payload))
    _commit(data, db, ctx, "PRODUCT_REGISTRATION_ADDED", {"product_id": str(product_id), "registration": result["id"]})
    return result


@router.delete(
    "/products/{product_id}/registrations/{registration_id}",
    status_code=204,
    dependencies=[Depends(require_permission(RECORDS_WRITE))],
)
def remove_registration(
    product_id: uuid.UUID,
    registration_id: uuid.UUID,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    _run(data, lambda: reference.remove_registration(data, _tenant(ctx), product_id, registration_id))
    _commit(
        data,
        db,
        ctx,
        "PRODUCT_REGISTRATION_REMOVED",
        {"product_id": str(product_id), "registration": str(registration_id)},
    )


@router.get("/responsible-parties")
def responsible_parties(
    ctx: AuthenticatedRequestContext = Depends(get_request_context), data: Session = Depends(get_data_plane_db)
):
    return {"parties": reference.responsible_parties(data, _tenant(ctx))}


@router.put("/responsible-parties", dependencies=[Depends(require_permission(RECORDS_WRITE))])
def set_party(
    payload: dict = Body(...),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    result = _run(data, lambda: reference.set_party(data, _tenant(ctx), payload))
    _commit(
        data,
        db,
        ctx,
        "RESPONSIBLE_PARTY_SET",
        {"party": result["id"], "market": result["market"], "role": result["role"]},
    )
    return result


@router.delete(
    "/responsible-parties/{party_id}", status_code=204, dependencies=[Depends(require_permission(RECORDS_WRITE))]
)
def remove_party(
    party_id: uuid.UUID,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    _run(data, lambda: reference.remove_party(data, _tenant(ctx), party_id))
    _commit(data, db, ctx, "RESPONSIBLE_PARTY_REMOVED", {"party": str(party_id)})


@router.get("/imdrf/releases")
def imdrf_releases(_ctx: AuthenticatedRequestContext = Depends(get_request_context), db: Session = Depends(get_db)):
    return {"releases": reference.releases(db)}


@router.get("/imdrf/codes")
def imdrf_codes(
    release: str = Query(..., max_length=20),
    annex: str | None = Query(default=None, pattern="^[A-Ga-g]$"),
    q: str | None = Query(default=None, max_length=100),
    _ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    return {"codes": reference.search_codes(db, release, annex, q)}


@router.get("/imdrf/links")
def imdrf_links(
    code: list[str] = Query(default=[]),
    customer_system: str = Query(default=PROBLEM_CODES, max_length=80),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    """The approved IMDRF codes, with their terms, of the organization's own codes (by default its complaints'
    problem codes): ``?code=PRESSURE_ALARM&code=NFF``."""
    return {"links": reference.approved_links(data, db, _tenant(ctx), customer_system, [c[:120] for c in code])}


@router.get("/imdrf/mappings")
def mappings(
    status: str | None = Query(default=None, pattern="^(PROPOSED|APPROVED|REJECTED)$"),
    customer_system: str | None = Query(default=None, max_length=80),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    data: Session = Depends(get_data_plane_db),
):
    return {"mappings": reference.mappings(data, _tenant(ctx), status, customer_system)}


@router.post("/imdrf/mappings", dependencies=[Depends(require_permission(RECORDS_WRITE))])
def propose_mapping(
    payload: dict = Body(...),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    result = _run(data, lambda: reference.propose_mapping(data, db, _tenant(ctx), payload, str(ctx.user_id)))
    _commit(data, db, ctx, "IMDRF_MAPPING_PROPOSED", {"mapping": result["id"]})
    return result


@router.post("/imdrf/mappings/{mapping_id}/review", dependencies=[Depends(require_permission(REGULATORY_APPROVE))])
def review_mapping(
    mapping_id: uuid.UUID,
    approve: bool = Body(..., embed=True),
    note: str | None = Body(default=None, embed=True),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    result = _run(
        data, lambda: reference.review_mapping(data, _tenant(ctx), mapping_id, approve, note, str(ctx.user_id))
    )
    _commit(data, db, ctx, f"IMDRF_MAPPING_{result['status']}", {"mapping": str(mapping_id)})
    return result
