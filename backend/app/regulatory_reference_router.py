"""Regulatory reference data (G2a): product registrations, responsible parties, IMDRF codes and the organization's
code mappings (backend/app/regulatory_reference.py). Changes need records.write; a product's identity, its
registrations and the responsible parties also regulatory.review (0.10.79: the Regulatory Leader keeps them). Deciding
a mapping needs regulatory.approve and a different person from the one who proposed it. Every change is audited."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app import regulatory_reference as reference
from backend.app.access.permissions import RECORDS_WRITE, REGULATORY_APPROVE, REGULATORY_REVIEW, require_permission
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import AuditEvent
from backend.app.db.session import get_db
from backend.app.evidence_workflow.people import require_any_permission
from backend.app.request_context import AuthenticatedRequestContext, get_request_context

router = APIRouter(prefix="/api/v1/regulatory-reference", tags=["Regulatory reference"])
# Who changes a product's identity, its registrations and the responsible parties: whoever changes records, and the
# regulatory reviewer (the Regulatory Leader, 0.10.79). Nothing else is granted.
IDENTITY_EDITORS = Depends(require_any_permission(RECORDS_WRITE, REGULATORY_REVIEW))
# The code system of a complaint's own problem code (complaints.problem_code), as its IMDRF mappings name it.
PROBLEM_CODES = "problem_code"


def _tenant(ctx: AuthenticatedRequestContext) -> uuid.UUID:
    return uuid.UUID(str(ctx.tenant_id))


def _commit(data: Session, db: Session, ctx, action: str, details: dict, old: dict | None = None, new=None) -> None:
    """Save the change, then its audit record with the values before and after (0.10.81, F7: they fill the authority
    forms, and 21 CFR 11.10(e) asks that a change never obscures what was recorded before)."""
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
            old_values=old,
            new_values=new,
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
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    return reference.product_profile(data, _tenant(ctx), product_id, db)


@router.put("/products/{product_id}/identity", dependencies=[IDENTITY_EDITORS])
def set_identity(
    product_id: uuid.UUID,
    payload: dict = Body(...),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    before = _run(data, lambda: _identity(data, _tenant(ctx), product_id))
    result = _run(data, lambda: reference.set_identity(data, _tenant(ctx), product_id, payload, db))
    after = _identity(data, _tenant(ctx), product_id)
    changed = [column for column in after if after[column] != before[column]]
    _commit(
        data,
        db,
        ctx,
        "PRODUCT_IDENTITY_SET",
        {"product_id": str(product_id)},
        {column: before[column] for column in changed},
        {column: after[column] for column in changed},
    )
    return result


def _identity(data: Session, tenant_id, product_id: uuid.UUID) -> dict:
    product = reference._product(data, tenant_id, product_id)
    return {column: getattr(product, column) for column in reference.IDENTITY_COLUMNS}


@router.post("/products/{product_id}/registrations", dependencies=[IDENTITY_EDITORS])
def add_registration(
    product_id: uuid.UUID,
    payload: dict = Body(...),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    result = _run(data, lambda: reference.add_registration(data, _tenant(ctx), product_id, payload, db))
    _commit(
        data,
        db,
        ctx,
        "PRODUCT_REGISTRATION_ADDED",
        {"product_id": str(product_id), "registration": result["id"]},
        None,
        result,
    )
    return result


@router.delete(
    "/products/{product_id}/registrations/{registration_id}",
    status_code=204,
    dependencies=[IDENTITY_EDITORS],
)
def remove_registration(
    product_id: uuid.UUID,
    registration_id: uuid.UUID,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    before = reference.registration_view(data, _tenant(ctx), product_id, registration_id)
    _run(data, lambda: reference.remove_registration(data, _tenant(ctx), product_id, registration_id))
    _commit(
        data,
        db,
        ctx,
        "PRODUCT_REGISTRATION_REMOVED",
        {"product_id": str(product_id), "registration": str(registration_id)},
        before,
        None,
    )


@router.get("/responsible-parties")
def responsible_parties(
    ctx: AuthenticatedRequestContext = Depends(get_request_context), data: Session = Depends(get_data_plane_db)
):
    return {"parties": reference.responsible_parties(data, _tenant(ctx))}


@router.put("/responsible-parties", dependencies=[IDENTITY_EDITORS])
def set_party(
    payload: dict = Body(...),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    before = {party["id"]: party for party in reference.responsible_parties(data, _tenant(ctx))}
    result = _run(data, lambda: reference.set_party(data, _tenant(ctx), payload))
    old = before.get(result["id"])
    _commit(
        data,
        db,
        ctx,
        "RESPONSIBLE_PARTY_SET",
        {"party": result["id"], "market": result["market"], "role": result["role"]},
        old,
        result,
    )
    return result


@router.delete("/responsible-parties/{party_id}", status_code=204, dependencies=[IDENTITY_EDITORS])
def remove_party(
    party_id: uuid.UUID,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    before = {party["id"]: party for party in reference.responsible_parties(data, _tenant(ctx))}.get(str(party_id))
    _run(data, lambda: reference.remove_party(data, _tenant(ctx), party_id))
    _commit(data, db, ctx, "RESPONSIBLE_PARTY_REMOVED", {"party": str(party_id)}, before, None)


@router.get("/imdrf/releases")
def imdrf_releases(_ctx: AuthenticatedRequestContext = Depends(get_request_context), db: Session = Depends(get_db)):
    return {"releases": reference.releases(db)}


@router.get("/imdrf/codes")
def imdrf_codes(
    release: str | None = Query(default=None, max_length=20),
    annex: str | None = Query(default=None, pattern="^[A-Ga-g]$"),
    q: str | None = Query(default=None, max_length=100),
    pick: bool = False,
    parent: str | None = Query(default=None, max_length=20),
    _ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    """Search a release's codes. With ``pick`` (the code picker, 0.10.77): one annex of the newest full release
    unless named, searched by word or browsed by ``parent``, retired codes left out, each with its definition and
    FDA code."""
    if not pick:
        if not release:
            raise HTTPException(422, detail={"code": "RELEASE_REQUIRED", "message": "Name the IMDRF release"})
        return {"codes": reference.search_codes(db, release, annex, q)}
    release = release or reference.newest_release(db)
    if not release or not annex:
        return {"release": release, "codes": [], "fda_version": None}
    return {
        "release": release,
        "annex": annex.upper(),
        "fda_version": reference.newest_version(db, "FDA_CDRH"),
        "codes": reference.pick_codes(db, release, annex, q, parent),
    }


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
