"""Lot impact on a case (T-G5, MVP G5 with G26's lot genealogy in cases), for a free trial only (a pilot gets 404
until the MVP plan schedules G5; owner decision, 1 Nov 2026).

- ``GET /api/v1/investigations/{id}/lot-impact``: the factors to choose from and the suggestion, the list for the
  saved factor (or, with ``kind``, ``ref`` and ``lot``, a preview for another), and the signed list with "changed
  since signed";
- ``PUT .../lot-impact``: keep the factor and the lots left out (each with a reason) as a new version of the case
  scope: the scope's lots become the lots kept in the list;
- ``POST .../lot-impact/sign``: the person signs the list with password and authenticator code; the frozen snapshot
  is kept with a new version of the case scope;
- ``GET .../lot-impact/list.csv`` and ``list.pdf``: the signed list (or ``?list=current``), "Practice record" in a
  trial.

Reading is open to every signed-in member, like the scope; saving needs investigation.work, signing a decider
(decision.sign, quality.review or regulatory.approve), the export data.export. MDARIX lists; it recommends no field
action and submits nothing.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.access.permissions import (
    DATA_EXPORT,
    DECISION_SIGN,
    INVESTIGATION_WORK,
    QUALITY_REVIEW,
    REGULATORY_APPROVE,
    require_permission,
)
from backend.app.case_workflow import scope, states
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import Investigation, SignedApprovalRecord
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.evidence_workflow.people import current_person, require_any_permission
from backend.app.lot_impact import service
from backend.app.request_context import AuthenticatedRequestContext, get_request_context

logger = logging.getLogger("mdarix.lot_impact")
router = APIRouter(prefix="/api/v1/investigations", tags=["Lot impact"])

OBJECT_TYPE, DECISION_TYPE = "LotImpactList", "LOT_IMPACT_LIST"
DECIDERS = Depends(require_any_permission(DECISION_SIGN, QUALITY_REVIEW, REGULATORY_APPROVE))
SAMPLE_NAMES = {"system:trial-sample": "MDARIX sample data"}


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _trial_case(db, control_db, ctx, investigation_id, *, lock: bool = False) -> Investigation:
    """The case, in a free trial only (404 elsewhere: the lot impact list is hidden on a pilot)."""
    from backend.app.signer_training.router import is_trial

    tenant_id = uuid.UUID(str(ctx.tenant_id))
    if not is_trial(control_db, tenant_id):
        raise _error(404, "NOT_A_TRIAL_WORKSPACE", "This workspace is not on the free trial")
    query = db.query(Investigation).filter(Investigation.id == investigation_id, Investigation.tenant_id == tenant_id)
    case = (query.with_for_update() if lock else query).first()
    if case is None:
        raise _error(404, "INVESTIGATION_NOT_FOUND", "Investigation not found")
    return case


def _open(case) -> None:
    if states.case_state(case) in states.CLOSED_STATES:
        raise _error(409, "INVESTIGATION_CLOSED", "This investigation is closed; reopen it first")


def _saved_factor(current: dict) -> dict | None:
    factor = (current.get("lot_impact") or {}).get("factor") or {}
    return service.clean_factor(factor.get("kind"), factor.get("id"), factor.get("lot"))


def _working(db, tenant_id, current: dict) -> dict | None:
    """The list for the saved factor and the lots left out, as the records show it now."""
    factor = service.resolve(db, tenant_id, _saved_factor(current))
    return service.build(db, tenant_id, factor, current["excluded_lots"]) if factor else None


def _names(control_db, tenant_id, refs) -> dict[str, str]:
    from backend.app.complaint_review.service import people

    return {**SAMPLE_NAMES, **people(control_db, tenant_id, [ref for ref in refs if ref])}


def _signature(control_db, tenant_id, signed: dict, names: dict) -> dict:
    record = control_db.get(SignedApprovalRecord, uuid.UUID(signed["record_id"]))
    return {
        "signer_name": names.get(signed["signed_by"]) or "A colleague",
        "signer_role": (signed.get("signed_role") or "").replace("_", " ").title(),
        "signed_at": signed["signed_at"],
        "meaning": signed["meaning"],
        "record_id": signed["record_id"],
        "record_business_id": record.business_id if record is not None else None,
        "content_fingerprint": signed["fingerprint"],
        "scope_version": signed.get("scope_version"),
    }


def _practice(control_db, tenant_id) -> str | None:
    from backend.app.reportability.markets import PRACTICE_LABEL
    from backend.app.signer_training.router import is_trial

    return PRACTICE_LABEL if is_trial(control_db, tenant_id) else None


def view(db, control_db, ctx, case, preview: dict | None = None) -> dict:
    tenant_id = case.tenant_id
    current = scope.current_scope(db, case)
    lot_impact = current.get("lot_impact") or {}
    options = service.options(db, tenant_id, case.product_id, service.in_scope_lots(db, tenant_id, current))
    saved = service.resolve(db, tenant_id, _saved_factor(current))
    working = service.build(db, tenant_id, saved, current["excluded_lots"]) if saved else None
    suggestion = options["suggestion"]
    shown, source = working, "saved"
    if preview is not None and (saved is None or preview != _saved_factor(current)):
        factor = service.resolve(db, tenant_id, preview)
        if factor is None:
            raise _error(404, "FACTOR_NOT_FOUND", "No such component lot, supplier or product version")
        shown, source = service.build(db, tenant_id, factor, []), "preview"
    elif working is None and suggestion is not None:
        factor = service.resolve(
            db, tenant_id, service.clean_factor(suggestion["kind"], suggestion["id"], suggestion["lot"])
        )
        shown, source = (service.build(db, tenant_id, factor, []), "suggested") if factor else (None, None)
    elif working is None:
        source = None
    signed = lot_impact.get("signed")
    names = _names(control_db, tenant_id, [lot_impact.get("saved_by"), (signed or {}).get("signed_by")])
    signed_view = None
    if signed:
        changes = service.changes(signed["snapshot"], working) if working else ["The saved factor is no longer found"]
        signed_view = {
            "list": signed["snapshot"],
            "signature": _signature(control_db, tenant_id, signed, names),
            "changed": working is None or working["fingerprint"] != signed["fingerprint"],
            "changes": changes,
        }
    return {
        "investigation": {
            "id": str(case.id),
            "business_id": case.business_id,
            "closed": states.case_state(case) in states.CLOSED_STATES,
        },
        "never_decides": service.NEVER_DECIDES,
        "not_imported": service.NOT_IMPORTED,
        "practice_label": _practice(control_db, tenant_id),
        "reason_min": service.REASON_MIN,
        "options": options["items"],
        "suggestion": suggestion,
        "case_lots": options["case_lots"],
        "genealogy": options["genealogy"],
        "saved": (
            {
                "factor": {key: saved[key] for key in ("kind", "id", "lot", "label", "kind_label")},
                "scope_version": lot_impact.get("saved_version"),
                "saved_at": lot_impact.get("saved_at"),
                "saved_by_name": names.get(lot_impact.get("saved_by") or "") or None,
            }
            if saved
            else None
        ),
        "source": source,
        "list": {**shown, "factor": {**shown["factor"], "kind_label": service.KIND_LABELS[shown["factor"]["kind"]]}}
        if shown
        else None,
        "signed": signed_view,
    }


@router.get("/{investigation_id}/lot-impact")
def get_lot_impact(
    investigation_id: uuid.UUID,
    kind: str | None = Query(default=None, max_length=20),
    ref: uuid.UUID | None = None,
    lot: str | None = Query(default=None, max_length=120),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The case's lot impact list. With ``kind`` and ``ref`` (and ``lot`` for a component lot), a preview of the list
    for that factor; nothing is saved."""
    case = _trial_case(db, control_db, ctx, investigation_id)
    preview = None
    if kind or ref:
        preview = service.clean_factor(kind, ref, lot)
        if preview is None:
            raise _error(422, "FACTOR_INVALID", "Choose a component lot, a supplier or a product version")
    return view(db, control_db, ctx, case, preview)


class FactorIn(BaseModel):
    kind: str = Field(pattern="^(COMPONENT_LOT|SUPPLIER|PRODUCT_VERSION)$")
    id: uuid.UUID
    lot: str | None = Field(default=None, max_length=120)


class ExcludedIn(BaseModel):
    lot_id: uuid.UUID
    reason: str = Field(default="", max_length=service.REASON_MAX * 2)


class SaveIn(BaseModel):
    factor: FactorIn
    excluded: list[ExcludedIn] = Field(default_factory=list, max_length=service.LOTS_MAX)


@router.put("/{investigation_id}/lot-impact", dependencies=[Depends(require_permission(INVESTIGATION_WORK))])
def save_lot_impact(
    investigation_id: uuid.UUID,
    payload: SaveIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Keep the factor and the lots left out as a new version of the case scope (nothing is written when nothing
    changed). Each lot left out needs a reason; the scope's lots become the lots kept in the list."""
    from backend.app.workflow.people import acting_role

    case = _trial_case(db, control_db, ctx, investigation_id, lock=True)
    _open(case)
    tenant_id = case.tenant_id
    factor = service.resolve(
        db, tenant_id, service.clean_factor(payload.factor.kind, payload.factor.id, payload.factor.lot)
    )
    if factor is None:
        raise _error(422, "FACTOR_NOT_FOUND", "No such component lot, supplier or product version")
    listed = service.build(db, tenant_id, factor, [])
    names = {row["id"]: row["lot_identifier"] for row in listed["lots"]}
    excluded = scope.excluded_lots(item.model_dump() for item in payload.excluded)
    for item in excluded:
        if item["lot_id"] not in names:
            raise _error(422, "LOT_NOT_IN_LIST", "Only a lot in the list can be left out")
        if len(item["reason"]) < service.REASON_MIN:
            raise _error(
                422,
                "EXCLUSION_REASON_REQUIRED",
                f"Say in at least {service.REASON_MIN} characters why {names[item['lot_id']]} is left out",
            )
        item["reason"] = item["reason"][: service.REASON_MAX]
    current = scope.current_scope(db, case)
    left_out = {item["lot_id"] for item in excluded}
    kept = [row["id"] for row in listed["lots"] if row["id"] not in left_out]
    factor_data = {key: factor[key] for key in ("kind", "id", "lot", "label")}
    previous = current.get("lot_impact") or {}
    if (
        (previous.get("factor") or {}) == factor_data
        and current["excluded_lots"] == excluded
        and current["lot_ids"] == kept
    ):
        return view(db, control_db, ctx, case)
    now = _now()
    role = acting_role(control_db, tenant_id, ctx.user_id, INVESTIGATION_WORK)
    reason = f"Lot impact: {factor['label']} ({factor['kind_label'].lower()}); {len(kept)} lots kept" + (
        f", {len(excluded)} left out with a reason" if excluded else ""
    )
    current.update(
        lot_ids=kept,
        excluded_lots=excluded,
        change_reason=reason,
        reviews_must_restart=False,
        conclusions_invalidated=False,
    )
    current["lot_impact"] = {
        **previous,
        "factor": factor_data,
        "saved_by": str(ctx.user_id),
        "saved_at": now.isoformat(),
    }
    row = scope.write_version(db, case, current, actor_ref=str(ctx.user_id), actor_role=role, now=now)
    row.lot_impact = {**row.lot_impact, "saved_version": row.version}
    case.updated_at = now
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=str(ctx.user_id),
            action="INVESTIGATION_SCOPE_CHANGED",
            entity_type="Investigation",
            entity_id=case.id,
            correlation_id=ctx.correlation_id,
            reason=reason,
            details={
                "version": row.version,
                "lot_impact": "SAVED",
                "factor_kind": factor["kind"],
                "lots_kept": len(kept),
                "lots_left_out": len(excluded),
                "actor_role": role,
            },
            created_at=now,
        )
    )
    states.start_case(
        db,
        case,
        actor_ref=str(ctx.user_id),
        reason=f"Scope version {row.version} recorded",
        correlation_id=ctx.correlation_id,
    )
    db.commit()
    return view(db, control_db, ctx, case)


class SignIn(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    mfa_code: str | None = Field(default=None, max_length=12)
    # The list the person read (its fingerprint): a list that changed since is not signed.
    fingerprint: str = Field(min_length=64, max_length=64)


@router.post("/{investigation_id}/lot-impact/sign", dependencies=[DECIDERS])
def sign_lot_impact(
    investigation_id: uuid.UUID,
    payload: SignIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The person signs the saved list with password and authenticator code. The list as signed is frozen with a new
    version of the case scope; a later change of the data shows as "changed since signed"."""
    from backend.app.governance_router import verify_signing_credentials
    from backend.app.human_decision.rules import signature_hash

    case = _trial_case(db, control_db, ctx, investigation_id)
    _open(case)
    tenant_id = case.tenant_id
    working = _working(db, tenant_id, scope.current_scope(db, case))
    if working is None:
        raise _error(409, "NOTHING_TO_SIGN", "Choose the suspect factor and keep it with the case first")
    if working["fingerprint"] != payload.fingerprint:
        raise _error(409, "LIST_CHANGED", "The list changed a moment ago; read it again before you sign")

    def refused(action: str) -> None:
        control_db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=ctx.user_id,
                action=action,
                entity_type=OBJECT_TYPE,
                entity_id=case.id,
                correlation_id=ctx.correlation_id,
                details={"attempt": "LOT_IMPACT_SIGN"},
            )
        )

    # Re-authenticate first: a refusal commits the control session, so nothing else may be pending in it yet.
    verify_signing_credentials(
        control_db, ctx, password=payload.password, mfa_code=payload.mfa_code, record_refusal=refused
    )
    case = _trial_case(db, control_db, ctx, investigation_id, lock=True)
    current = scope.current_scope(db, case)
    working = _working(db, tenant_id, current)
    if working is None or working["fingerprint"] != payload.fingerprint:
        raise _error(409, "LIST_CHANGED", "The list changed a moment ago; read it again before you sign")
    me = str(ctx.user_id)
    person = current_person(control_db, ctx)
    role = person.role_for(
        next((p for p in (DECISION_SIGN, QUALITY_REVIEW, REGULATORY_APPROVE) if person.holds(p)), None)
    )
    now = _now()
    meaning = service.signature_meaning(
        case.business_id or str(case.id), working["factor"]["label"], working["totals"]["lots"]
    )
    version = str(int(current.get("version") or 0) + 1)
    record = SignedApprovalRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        object_type=OBJECT_TYPE,
        object_id=case.id,
        object_version=version,
        decision_type=DECISION_TYPE,
        decision="SIGNED",
        remarks=f"Lot impact list, scope version {version}",
        signer_user_id=me,
        signer_role=role or "UNKNOWN",
        signature_meaning=meaning,
        content_fingerprint=working["fingerprint"],
        signature_hash=signature_hash(working["fingerprint"], me, version),
        status="SIGNED",
        signed_at=now,
        created_at=now,
    )
    control_db.add(record)
    control_db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="LOT_IMPACT_SIGNED",
            entity_type="Investigation",
            entity_id=case.id,
            correlation_id=ctx.correlation_id,
            details={
                "scope_version": int(version),
                "signature_id": str(record.id),
                "fingerprint": working["fingerprint"],
                "lots": working["totals"]["lots"],
            },
            created_at=now,
        )
    )
    current.update(
        change_reason=f"Lot impact list signed: {working['totals']['lots']} lots sharing {working['factor']['label']}",
        reviews_must_restart=False,
        conclusions_invalidated=False,
    )
    current["lot_impact"] = {
        **(current.get("lot_impact") or {}),
        "signed": {
            "snapshot": working,
            "fingerprint": working["fingerprint"],
            "record_id": str(record.id),
            "signed_by": me,
            "signed_role": role,
            "signed_at": now.isoformat(timespec="seconds"),
            "meaning": meaning,
            "scope_version": int(version),
        },
    }
    scope.write_version(db, case, current, actor_ref=me, actor_role=role, now=now)
    case.updated_at = now
    if db is control_db:
        control_db.commit()
    else:
        control_db.commit()
        try:
            db.commit()
        except Exception:
            logger.exception("Signature %s was saved but the lot impact list of %s was not", record.id, case.id)
            raise
    return view(db, control_db, ctx, case)


MEDIA = {"csv": "text/csv; charset=utf-8", "pdf": "application/pdf"}


@router.get("/{investigation_id}/lot-impact/list.{kind}", dependencies=[Depends(require_permission(DATA_EXPORT))])
def export_lot_impact(
    investigation_id: uuid.UUID,
    kind: str,
    which: str = Query(default="signed", alias="list", pattern="^(signed|current)$"),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The signed list (else, or with ``list=current``, the saved list as the records show it now) as CSV or PDF."""
    from backend.app.lot_impact import render
    from backend.app.stage3_workflow_router import _organization_name

    kind = kind.lower()
    if kind not in MEDIA:
        raise _error(404, "FORMAT_NOT_SUPPORTED", "Download the CSV or the PDF")
    case = _trial_case(db, control_db, ctx, investigation_id)
    screen = view(db, control_db, ctx, case)
    signed = screen["signed"]
    if which == "signed" and signed is not None:
        listed, label = signed["list"], f"signed {signed['signature']['signed_at']}"
        if signed["changed"]:
            label += " (changed since signed)"
    elif screen["saved"] is not None:
        which, listed, label = "current", screen["list"], "as the records show it now; not signed"
    else:
        raise _error(404, "NO_LOT_IMPACT_LIST", "Choose the suspect factor and keep it with the case first")
    listed = {**listed, "factor": {**listed["factor"], "kind_label": service.KIND_LABELS[listed["factor"]["kind"]]}}
    export = {
        "investigation": screen["investigation"],
        "practice_label": screen["practice_label"],
        "list": listed,
        "which": which,
        "which_label": label,
        "signature": signed["signature"] if signed else None,
        "changed": bool(signed and signed["changed"]),
        "changes": signed["changes"] if signed else [],
    }
    body = (
        render.render_csv(export)
        if kind == "csv"
        else render.render_pdf(export, organization=_organization_name(control_db, case.tenant_id))
    )
    db.add(
        make_audit_event(
            tenant_id=case.tenant_id,
            actor_ref=ctx.user_id,
            action="LOT_IMPACT_EXPORTED",
            entity_type="Investigation",
            entity_id=case.id,
            correlation_id=ctx.correlation_id,
            details={"format": kind.upper(), "list": which, "lots": listed["totals"]["lots"]},
        )
    )
    db.commit()
    ref = case.business_id or str(case.id)
    return Response(
        content=body,
        media_type=MEDIA[kind],
        headers={"Content-Disposition": f'attachment; filename="mdarix-lot-impact-{ref}.{kind}"'},
    )
