"""Reviews the customer signs (B6a Part C), under ``/api/v1/reviews``. Switch ``MDARIX_B6_REVIEWS`` (on): off, every
route here is 404 (signed reviews stay in the audit trail and its export).

Who (owner D4, D5): the audit trail review is read by a Leader, a Quality Reviewer or a customer administrator and
signed by a Leader or Quality Reviewer only (an administrator account never holds quality review); a signer whose own
actions are among the flags needs a second reviewer's confirmation. The access review and the configuration snapshot
are read by a customer administrator or a Leader; the access review is signed by a customer administrator, the
configuration snapshot by a customer administrator or a Leader. The tenant and the person come only from the request
context; another organization's review is 404.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from backend.app import feature_set
from backend.app.access.permissions import QUALITY_REVIEW, effective_permissions
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import AuthUser
from backend.app.db.session import get_db
from backend.app.downloads import attachment
from backend.app.enterprise_audit import make_audit_event
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.role_codes import is_administrator_role, is_customer_admin_role, is_platform_admin_role, role_code
from backend.app.signed_reviews import access_review, audit_review, configuration, signing
from backend.app.signed_reviews.signing import error, sign

SWITCH = "MDARIX_B6_REVIEWS"
router = APIRouter(prefix="/api/v1/reviews", tags=["Signed reviews"])


def _on() -> None:
    if not feature_set.switched_on(SWITCH):
        raise error(404, "REVIEWS_OFF", "Signed reviews are switched off")


def _me(control_db: Session, ctx: AuthenticatedRequestContext) -> AuthUser:
    try:
        user_id = uuid.UUID(str(ctx.user_id))
    except (TypeError, ValueError):
        user_id = None
    user = (
        control_db.query(AuthUser).filter(AuthUser.id == user_id, AuthUser.tenant_id == ctx.tenant_id).first()
        if user_id
        else None
    )
    if user is None or user.status != "ACTIVE":
        raise error(401, "UNAUTHENTICATED", "Authentication required")
    return user


def _reviewer(control_db: Session, ctx) -> bool:
    return QUALITY_REVIEW in effective_permissions(control_db, ctx)


def _can_read(kind: str, control_db: Session, ctx, me: AuthUser) -> bool:
    if is_platform_admin_role(me.role):
        return False  # MDARIX staff never read an organization's signed reviews (review finding 9)
    if kind.startswith("audit-trail"):
        return _reviewer(control_db, ctx) or is_customer_admin_role(me.role)
    return is_customer_admin_role(me.role) or access_review.is_leader(control_db, me)


def _require_read(kind: str, control_db: Session, ctx) -> AuthUser:
    _on()
    me = _me(control_db, ctx)
    if not _can_read(kind, control_db, ctx, me):
        raise error(403, "REVIEW_ACCESS_REFUSED", "Your role does not open this review")
    return me


def _audit_signer_role(control_db: Session, ctx) -> str:
    """D4: a Leader or Quality Reviewer; never an administrator account (it holds no quality review)."""
    from backend.app.evidence_workflow.people import current_person

    person = current_person(control_db, ctx)
    role = person.role_for(QUALITY_REVIEW) if person.holds(QUALITY_REVIEW) else None
    if not role or is_administrator_role(role) or is_administrator_role(person.account_role):
        raise error(403, "REVIEW_SIGNER_REQUIRED", "A Leader or Quality Reviewer signs the audit trail review")
    return role_code(role)


class SignIn(BaseModel):
    findings: str = Field(min_length=1, max_length=4000)
    password: str | None = Field(default=None, max_length=200)
    mfa_code: str | None = Field(default=None, max_length=20)

    @field_validator("findings")
    @classmethod
    def _text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Write your findings, or 'none'")
        return value


class AuditSignIn(SignIn):
    period_from: date | None = None
    period_to: date | None = None
    corrects: uuid.UUID | None = None


class MarkIn(BaseModel):
    user_id: uuid.UUID
    mark: str
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("mark")
    @classmethod
    def _mark(cls, value: str) -> str:
        value = value.strip().upper()
        if value not in access_review.MARKS:
            raise ValueError("Mark Keep, Change or Remove")
        return value


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _last(control_db: Session, tenant_id, kind: str) -> dict | None:
    found = signing.signed_events(control_db, tenant_id, kind, limit=1)
    return (found[0].details or {}).get("material") if found else None


def _period(control_db, tenant_id, period_from: date | None, period_to: date | None) -> tuple[date, date]:
    start, end = audit_review.default_period(_last(control_db, tenant_id, "audit-trail"), _now())
    start, end = period_from or start, period_to or end
    if start > end or end > _now().date():
        raise error(422, "PERIOD_INVALID", "Choose a period that ends today or earlier and starts before it ends")
    return start, end


# ------------------------------------------------------------------------------------------ G1 audit trail review


@router.get("/audit-trail")
def audit_trail(
    period_from: date | None = Query(default=None, alias="from"),
    period_to: date | None = Query(default=None, alias="to"),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The flags of the period (default: since the last signed review), the chain checks, the last signed review."""
    me = _require_read("audit-trail", control_db, ctx)
    start, end = _period(control_db, me.tenant_id, period_from, period_to)
    content = audit_review.build(control_db, db, me.tenant_id, start, end)
    last = signing.signed_events(control_db, me.tenant_id, "audit-trail", limit=1)
    return {
        **content,
        "own_flags": audit_review.own_flags(content, me.id),
        "may_sign": _reviewer(control_db, ctx) and not is_administrator_role(me.role),
        "last_signed": signing.summary(last[0]) if last else None,
        "next_due": (
            (last[0].created_at + timedelta(days=audit_review.DUE_DAYS)).date() if last else _now().date()
        ).isoformat(),
        "awaiting_confirmation": _awaiting(control_db, me.tenant_id),
    }


def _awaiting(control_db: Session, tenant_id) -> list[dict]:
    """Signed audit trail reviews that need a second reviewer and have none yet."""
    signed = signing.signed_events(control_db, tenant_id, "audit-trail", limit=20)
    confirmed = {
        str(row.entity_id) for row in signing.signed_events(control_db, tenant_id, "audit-trail-confirmation", 200)
    }
    return [
        signing.summary(row)
        for row in signed
        if ((row.details or {}).get("material") or {}).get("content", {}).get("needs_second_reviewer")
        and str(row.entity_id) not in confirmed
    ]


@router.get("/audit-trail/events")
def audit_trail_events(
    period_from: date | None = Query(default=None, alias="from"),
    period_to: date | None = Query(default=None, alias="to"),
    offset: int = Query(default=0, ge=0, le=audit_review.READ_CAP),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Every event of the period, oldest first, with old and new values, paged."""
    me = _require_read("audit-trail", control_db, ctx)
    start, end = _period(control_db, me.tenant_id, period_from, period_to)
    return audit_review.page(control_db, db, me.tenant_id, start, end, offset, limit)


@router.post("/audit-trail/sign")
def sign_audit_trail(
    payload: AuditSignIn,
    request: Request,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Sign the review of the period. The content is rebuilt on the server at signing; when the signer's own actions
    are among the flags, the review records that a second reviewer must confirm them (D4)."""
    me = _require_read("audit-trail", control_db, ctx)
    role = _audit_signer_role(control_db, ctx)
    if payload.corrects is not None:
        earlier = signing.read(control_db, me.tenant_id, payload.corrects)  # 404 for another organization's
        if earlier["kind"] != "audit-trail":
            raise error(422, "CORRECTS_INVALID", "A correction names an earlier audit trail review")
    start, end = _period(control_db, me.tenant_id, payload.period_from, payload.period_to)
    content = audit_review.for_signing(audit_review.build(control_db, db, me.tenant_id, start, end))
    own = audit_review.own_flags(content, me.id)
    content["own_flags"] = own
    content["needs_second_reviewer"] = bool(own)
    # A period that does not start where the last signed review ended leaves days unreviewed: said in the review.
    last_to = ((_last(control_db, me.tenant_id, "audit-trail") or {}).get("content") or {}).get("period", {}).get("to")
    if last_to and start > date.fromisoformat(last_to) + timedelta(days=1):
        content["unreviewed_gap"] = {
            "from": (date.fromisoformat(last_to) + timedelta(days=1)).isoformat(),
            "to": (start - timedelta(days=1)).isoformat(),
        }
    if db is not control_db:
        db.rollback()  # nothing is written on the plane; end its read transaction
    return sign(
        control_db,
        ctx,
        kind="audit-trail",
        content=content,
        findings=payload.findings,
        password=payload.password,
        mfa_code=payload.mfa_code,
        signer_role=role,
        corrects=str(payload.corrects) if payload.corrects else None,
        request=request,
    ) | {"needs_second_reviewer": bool(own)}


@router.post("/audit-trail/{review_id}/confirm")
def confirm_audit_trail(
    review_id: uuid.UUID,
    payload: SignIn,
    request: Request,
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """A second Leader or Quality Reviewer confirms a review whose signer's own actions were flagged."""
    me = _require_read("audit-trail", control_db, ctx)
    role = _audit_signer_role(control_db, ctx)
    review = signing.read(control_db, me.tenant_id, review_id)
    if review["kind"] != "audit-trail":
        raise error(404, "REVIEW_NOT_FOUND", "No such audit trail review in your organization")
    if not (review["content"] or {}).get("needs_second_reviewer"):
        raise error(409, "NO_CONFIRMATION_NEEDED", "This review needs no second reviewer")
    if not review["intact"]:
        raise error(409, "REVIEW_NOT_INTACT", "This review's stored content no longer matches its signature")
    if len(review["signatures"]) > 1:
        raise error(409, "ALREADY_CONFIRMED", "A second reviewer has already confirmed this review")
    if review["signatures"][0]["signed_by"] == str(me.id):
        raise error(403, "SECOND_REVIEWER_REQUIRED", "Another Leader or Quality Reviewer confirms your own flags")
    return sign(
        control_db,
        ctx,
        kind="audit-trail-confirmation",
        content={"confirms": str(review_id), "own_flags": review["content"].get("own_flags")},
        findings=payload.findings,
        password=payload.password,
        mfa_code=payload.mfa_code,
        signer_role=role,
        review_id=review_id,
        version="2",
        request=request,
    )


# ------------------------------------------------------------------------------------------ G14 access review


@router.get("/access")
def access(control_db: Session = Depends(get_db), ctx: AuthenticatedRequestContext = Depends(get_request_context)):
    """One row per active user with the latest mark since the last signed access review."""
    me = _require_read("access", control_db, ctx)
    return {**access_review.rows(control_db, me, _now()), "may_sign": is_customer_admin_role(me.role)}


@router.post("/access/marks")
def mark_access(
    payload: MarkIn,
    request: Request,
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Mark one row Keep, Change or Remove (audited). Change and Remove are then done in user administration."""
    me = _require_read("access", control_db, ctx)
    users = access_review.active_users(control_db, me)
    target = access_review.target_of(users, payload.user_id)
    marker_role = access_review.check_marker(control_db, me, target, users)
    control_db.add(
        make_audit_event(
            tenant_id=me.tenant_id,
            actor_ref=str(me.id),
            action=access_review.MARKED,
            entity_type="AuthUser",
            entity_id=target.id,
            correlation_id=ctx.correlation_id,
            reason=(payload.note or "").strip() or None,
            details={"mark": payload.mark, "marker_role": marker_role},
            request=request,
        )
    )
    control_db.commit()
    return access_review.rows(control_db, me, _now())


@router.post("/access/sign")
def sign_access(
    payload: SignIn,
    request: Request,
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The customer administrator signs once every row is marked and their own row was marked by another person."""
    me = _require_read("access", control_db, ctx)
    if not is_customer_admin_role(me.role):
        raise error(403, "CUSTOMER_ADMIN_REQUIRED", "A customer administrator signs the access review")
    review = access_review.rows(control_db, me, _now())
    access_review.check_ready_to_sign(review, me)
    return sign(
        control_db,
        ctx,
        kind="access",
        content=review,
        findings=payload.findings,
        password=payload.password,
        mfa_code=payload.mfa_code,
        signer_role="CUSTOMER_ADMIN",
        request=request,
    )


# ------------------------------------------------------------------------------------------ G21 configuration


@router.get("/configuration")
def configuration_now(
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The configuration in force now (never a key or secret)."""
    me = _require_read("configuration", control_db, ctx)
    return configuration.snapshot(control_db, db, me, _now())


@router.post("/configuration/sign")
def sign_configuration(
    payload: SignIn,
    request: Request,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Sign the snapshot of the configuration in force (built on the server at signing)."""
    me = _require_read("configuration", control_db, ctx)
    content = configuration.snapshot(control_db, db, me, _now())
    if db is not control_db:
        db.rollback()
    role = "CUSTOMER_ADMIN" if is_customer_admin_role(me.role) else "LEADER"
    return sign(
        control_db,
        ctx,
        kind="configuration",
        content=content,
        findings=payload.findings,
        password=payload.password,
        mfa_code=payload.mfa_code,
        signer_role=role,
        request=request,
    )


@router.get("/configuration/compare")
def compare_configuration(
    before: uuid.UUID,
    after: str = "now",
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Two signed snapshots, or a signed one and now: each changed item, and who, when and why in between."""
    me = _require_read("configuration", control_db, ctx)
    first = signing.read(control_db, me.tenant_id, before)
    if after == "now":
        second = {"content": configuration.snapshot(control_db, db, me, _now()), "review_id": None}
    else:
        try:
            second = signing.read(control_db, me.tenant_id, uuid.UUID(after))
        except ValueError as exc:
            raise error(422, "SNAPSHOT_INVALID", "Compare with a signed snapshot or with now") from exc
    if first["kind"] != "configuration" or second.get("kind", "configuration") != "configuration":
        raise error(404, "REVIEW_NOT_FOUND", "No such configuration snapshot in your organization")
    start = datetime.fromisoformat(first["content"]["taken_at"])
    end = datetime.fromisoformat(second["content"]["taken_at"])
    if end < start:
        first, second, start, end = second, first, end, start
    events, incomplete = configuration.events_between(control_db, db, me.tenant_id, start, end)
    return {
        "incomplete": incomplete,
        "before": {"review_id": first["review_id"], "taken_at": first["content"]["taken_at"]},
        "after": {"review_id": second["review_id"], "taken_at": second["content"]["taken_at"]},
        **configuration.compare(first["content"], second["content"], events),
    }


# ------------------------------------------------------------------------------------------ signed reviews


@router.get("/{kind}/signed")
def signed_list(
    kind: str, control_db: Session = Depends(get_db), ctx: AuthenticatedRequestContext = Depends(get_request_context)
):
    if kind not in ("audit-trail", "access", "configuration"):
        raise error(404, "REVIEW_KIND_UNKNOWN", "No such review")
    me = _require_read(kind, control_db, ctx)
    return [signing.summary(row) for row in signing.signed_events(control_db, me.tenant_id, kind)]


def _signed(control_db: Session, ctx, review_id: uuid.UUID) -> tuple[AuthUser, dict]:
    _on()
    me = _me(control_db, ctx)
    review = signing.read(control_db, me.tenant_id, review_id)
    if not _can_read(review["kind"] or "", control_db, ctx, me):
        raise error(403, "REVIEW_ACCESS_REFUSED", "Your role does not open this review")
    return me, review


@router.get("/signed/{review_id}")
def signed_review(
    review_id: uuid.UUID,
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The stored, signed content and its signatures; ``intact`` says whether it still matches every signature."""
    return _signed(control_db, ctx, review_id)[1]


@router.get("/signed/{review_id}/download")
def download_signed(
    review_id: uuid.UUID,
    request: Request,
    output_format: str = Query(default="pdf", alias="format", pattern="^(pdf|json)$"),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The signed review as PDF (rendered from the stored content) or JSON (the stored content and signatures)."""
    from backend.app.stage3_workflow_router import _organization_name

    me, review = _signed(control_db, ctx, review_id)
    control_db.add(
        make_audit_event(
            tenant_id=me.tenant_id,
            actor_ref=str(me.id),
            action="SIGNED_REVIEW_DOWNLOADED",
            entity_type="SignedReview",
            entity_id=review_id,
            correlation_id=ctx.correlation_id,
            details={"kind": review["kind"], "format": output_format},
            request=request,
        )
    )
    control_db.commit()
    name = f"mdarix-{review['kind']}-review-{str(review_id)[:8]}"
    if output_format == "json":
        return Response(
            content=json.dumps(review, indent=1, sort_keys=True, ensure_ascii=False).encode("utf-8"),
            media_type="application/json",
            headers={"Content-Disposition": attachment(f"{name}.json")},
        )
    return Response(
        content=signing.as_pdf(review, _organization_name(control_db, me.tenant_id)),
        media_type="application/pdf",
        headers={"Content-Disposition": attachment(f"{name}.pdf")},
    )
