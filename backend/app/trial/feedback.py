"""Customer feedback: the questionnaire any signed-in user fills in, and what may be shown on the MDARIX website.

Feedback is open to every organization, trial or paying (the tables and routes keep their original "trial" names).
A user answers questions about the product and their experience and chooses how their words may be used:
with their company's name (NAMED), without it (ANONYMOUS) or not at all (PRIVATE). The exact consent wording they saw
is stored with the answer. Nothing is public until a Platform Administrator publishes it; an anonymous quote that
names the company is refused, and the person can withdraw consent at any time, which unpublishes it at once.
Each response is announced to the MDARIX team by email (``FEEDBACK_SUBMITTED``, backend/app/notifications.py).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.access.authz import _require_platform_admin
from backend.app.db.models.foundation import AuditEvent, AuthUser, Tenant
from backend.app.db.models.stage2 import TrialFeedback
from backend.app.db.session import get_db
from backend.app.db.tenant_scope import bind_system
from backend.app.notifications import notify_feedback_submitted
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.trial.team import trial_request

router = APIRouter(prefix="/api/v1", tags=["Trial feedback"])

ROLE_AREAS = {
    "QUALITY": "Quality",
    "REGULATORY": "Regulatory affairs",
    "POST_MARKET": "Post-market surveillance",
    "ENGINEERING": "Engineering",
    "MANUFACTURING": "Manufacturing",
    "SUPPLIER_QUALITY": "Supplier quality",
    "LEADERSHIP": "Leadership",
    "OTHER": "Other",
}
# The parts of MDARIX a person may say they used: the full product's, and the lightweight MVP's screens (Getting
# started, Readiness, Complaints, Records; the form offers the set the organization sees).
FEATURES = {
    "PRODUCT_360",
    "SIGNALS",
    "INVESTIGATIONS",
    "ASK_MDARIX",
    "EVIDENCE",
    "DECISIONS",
    "CSV_IMPORT",
    "AUDIT_TRAIL",
    "GETTING_STARTED",
    "READINESS",
    "COMPLAINTS",
    "RECORDS",
}
ADOPTION = {"YES", "MAYBE", "NO", "NOT_MY_DECISION"}
ANONYMOUS_ATTRIBUTION = "medical-device company"
PER_USER_PER_DAY = 5


def consent_wording(choice: str, organization: str) -> str:
    """The exact sentence the person agrees to; the page shows the same words and the server stores them."""
    if choice == "NAMED":
        return (
            f"MDARIX may show my quote on its website and in its materials with my company's name, {organization}, "
            "after review. I can withdraw this consent at any time."
        )
    if choice == "ANONYMOUS":
        return (
            "MDARIX may show my quote on its website and in its materials without my name or my company's name "
            f'(as "a {ANONYMOUS_ATTRIBUTION}"), after review. I can withdraw this consent at any time.'
        )
    return "My feedback is for the MDARIX team only and is never shown publicly."


Rating = int


class FeedbackIn(BaseModel):
    role_area: str | None = Field(default=None, max_length=40)
    job_title: str | None = Field(default=None, max_length=120)
    rating_overall: Rating = Field(ge=1, le=5)
    rating_ease: Rating | None = Field(default=None, ge=1, le=5)
    rating_usefulness: Rating | None = Field(default=None, ge=1, le=5)
    rating_ai_trust: Rating | None = Field(default=None, ge=1, le=5)
    rating_speed: Rating | None = Field(default=None, ge=1, le=5)
    rating_import: Rating | None = Field(default=None, ge=1, le=5)
    recommend_score: int | None = Field(default=None, ge=0, le=10)
    features_used: list[str] = Field(default_factory=list, max_length=len(FEATURES))
    liked: str | None = Field(default=None, max_length=2000)
    improve: str | None = Field(default=None, max_length=2000)
    missing: str | None = Field(default=None, max_length=2000)
    adoption: str | None = Field(default=None, max_length=40)
    quote: str | None = Field(default=None, max_length=400)
    publish_consent: Literal["NAMED", "ANONYMOUS", "PRIVATE"]
    contact_ok: bool = False


class PublicationChange(BaseModel):
    action: Literal["PUBLISH", "HIDE"]


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def _text(value: str | None) -> str | None:
    """One line of text with runs of spaces and line breaks collapsed; None when empty."""
    return " ".join((value or "").split()) or None


def _user(db: Session, ctx: AuthenticatedRequestContext) -> AuthUser:
    user = db.query(AuthUser).filter(AuthUser.id == uuid.UUID(str(ctx.user_id))).first()
    if user is None:
        raise _error(401, "UNAUTHENTICATED", "Authentication required")
    return user


def _organization(db: Session, tenant_id: uuid.UUID) -> str:
    request = trial_request(db, tenant_id)
    if request is not None and request.organization:
        return request.organization.strip()
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    return (tenant.display_name or tenant.name) if tenant else "Your organization"


# Common words in company names that do not identify one.
_GENERIC = {
    "medical",
    "devices",
    "device",
    "health",
    "healthcare",
    "systems",
    "technologies",
    "technology",
    "group",
    "corp",
    "company",
    "solutions",
    "international",
    "global",
    "trial",
    "sciences",
    "diagnostics",
    "surgical",
    "limited",
}


def _names_company(quote: str, organization: str) -> bool:
    """True when the quote contains the company name or a distinctive word of it."""
    words = [word for word in organization.lower().replace(",", " ").replace(".", " ").split() if len(word) > 3]
    text = quote.lower()
    return organization.lower() in text or any(word in text for word in words if word not in _GENERIC)


def attribution(row: TrialFeedback) -> str:
    """How a published quote is credited: the company only with NAMED consent."""
    role = row.job_title if row.publish_consent == "NAMED" and row.job_title else ROLE_AREAS.get(row.role_area or "")
    if row.publish_consent == "NAMED":
        return f"{role}, {row.organization_name}" if role else row.organization_name
    who = f"{role} lead" if role and role not in {"Other", "Leadership"} else (role or "Customer")
    return f"{who}, {ANONYMOUS_ATTRIBUTION}"


def _mine(row: TrialFeedback) -> dict:
    return {
        "id": str(row.id),
        "business_id": row.business_id,
        "created_at": row.created_at.isoformat(),
        "rating_overall": row.rating_overall,
        "publish_consent": row.publish_consent,
        "publication_status": row.publication_status,
        "quote": row.quote,
    }


def _audit(db: Session, tenant_id, actor, action: str, row: TrialFeedback, details: dict, now: datetime) -> None:
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_ref=str(actor),
            action=action,
            entity_type="TrialFeedback",
            entity_id=row.id,
            details={"feedback_id": str(row.id), **details},
            created_at=now,
        )
    )


# ------------------------------------------------------------------------------------------- Trial user


@router.get("/trial/feedback")
def my_feedback(ctx: AuthenticatedRequestContext = Depends(get_request_context), db: Session = Depends(get_db)):
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    user = _user(db, ctx)
    organization = _organization(db, tenant_id)
    rows = (
        db.query(TrialFeedback)
        .filter(TrialFeedback.tenant_id == tenant_id, TrialFeedback.user_id == user.id)
        .order_by(TrialFeedback.created_at.desc())
        .all()
    )
    return {
        "organization_name": organization,
        "consent_wording": {
            choice: consent_wording(choice, organization) for choice in ("NAMED", "ANONYMOUS", "PRIVATE")
        },
        "anonymous_attribution": ANONYMOUS_ATTRIBUTION,
        "role_areas": ROLE_AREAS,
        "submissions": [_mine(row) for row in rows],
    }


@router.post("/trial/feedback")
def submit_feedback(
    payload: FeedbackIn,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    user = _user(db, ctx)
    now = datetime.now(timezone.utc)
    recent = (
        db.query(func.count(TrialFeedback.id))
        .filter(TrialFeedback.user_id == user.id, TrialFeedback.created_at >= now - timedelta(days=1))
        .scalar()
    )
    if recent >= PER_USER_PER_DAY:
        raise _error(429, "FEEDBACK_LIMIT", "You have sent several responses today. Thank you; please try tomorrow.")
    if payload.role_area and payload.role_area not in ROLE_AREAS:
        raise _error(422, "FEEDBACK_INVALID", "Choose your area from the list")
    if payload.adoption and payload.adoption not in ADOPTION:
        raise _error(422, "FEEDBACK_INVALID", "Choose an answer from the list")
    unknown = set(payload.features_used) - FEATURES
    if unknown:
        raise _error(422, "FEEDBACK_INVALID", "Choose features from the list")
    quote = _text(payload.quote)
    organization = _organization(db, tenant_id)
    if payload.publish_consent != "PRIVATE" and not quote:
        raise _error(422, "FEEDBACK_QUOTE_REQUIRED", "Write the quote we may show, or keep your feedback private")
    if payload.publish_consent == "ANONYMOUS" and quote and _names_company(quote, organization):
        raise _error(
            422,
            "FEEDBACK_QUOTE_NAMES_COMPANY",
            "Your quote mentions your company. Remove the name to stay anonymous, or choose to be named.",
        )
    row = TrialFeedback(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user.id,
        organization_name=organization,
        role_area=payload.role_area,
        job_title=_text(payload.job_title),
        rating_overall=payload.rating_overall,
        rating_ease=payload.rating_ease,
        rating_usefulness=payload.rating_usefulness,
        rating_ai_trust=payload.rating_ai_trust,
        rating_speed=payload.rating_speed,
        rating_import=payload.rating_import,
        recommend_score=payload.recommend_score,
        features_used=sorted(set(payload.features_used)),
        liked=(payload.liked or "").strip() or None,
        improve=(payload.improve or "").strip() or None,
        missing=(payload.missing or "").strip() or None,
        adoption=payload.adoption,
        quote=quote,
        publish_consent=payload.publish_consent,
        consent_text=consent_wording(payload.publish_consent, organization),
        consent_at=now,
        contact_ok=payload.contact_ok,
        publication_status="NOT_REQUESTED" if payload.publish_consent == "PRIVATE" else "PENDING",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    _audit(db, tenant_id, user.id, "TRIAL_FEEDBACK_SUBMITTED", row, {"consent": row.publish_consent}, now)
    notify_feedback_submitted(db, tenant_id, feedback_id=row.id)
    db.commit()
    return _mine(row)


@router.post("/trial/feedback/{feedback_id}/withdraw-consent")
def withdraw_consent(
    feedback_id: uuid.UUID,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    user = _user(db, ctx)
    row = (
        db.query(TrialFeedback)
        .filter(TrialFeedback.id == feedback_id, TrialFeedback.tenant_id == tenant_id, TrialFeedback.user_id == user.id)
        .with_for_update()
        .first()
    )
    if row is None:
        raise _error(404, "FEEDBACK_NOT_FOUND", "Feedback not found")
    now = datetime.now(timezone.utc)
    previous = row.publish_consent
    row.publish_consent = "PRIVATE"
    row.consent_text = consent_wording("PRIVATE", row.organization_name)
    row.consent_at = now
    row.publication_status = "NOT_REQUESTED"
    row.updated_at = now
    _audit(db, tenant_id, user.id, "TRIAL_FEEDBACK_CONSENT_WITHDRAWN", row, {"from": previous}, now)
    db.commit()
    return _mine(row)


# ------------------------------------------------------------------------------------------- Platform Admin


def _tenant_references(db: Session, tenant_ids) -> dict:
    """Tenant id -> (tenant key, tenant business id), read in one query."""
    tenant_ids = set(tenant_ids)
    if not tenant_ids:
        return {}
    return {
        tenant_id: (tenant_key, business_id)
        for tenant_id, tenant_key, business_id in db.query(Tenant.id, Tenant.tenant_key, Tenant.business_id).filter(
            Tenant.id.in_(tenant_ids)
        )
    }


def _admin_row(row: TrialFeedback, tenants: dict) -> dict:
    tenant_key, tenant_business_id = tenants.get(row.tenant_id, (None, None))
    return {
        **{
            column: getattr(row, column)
            for column in (
                "organization_name",
                "role_area",
                "job_title",
                "rating_overall",
                "rating_ease",
                "rating_usefulness",
                "rating_ai_trust",
                "rating_speed",
                "rating_import",
                "recommend_score",
                "features_used",
                "liked",
                "improve",
                "missing",
                "adoption",
                "quote",
                "publish_consent",
                "consent_text",
                "contact_ok",
                "publication_status",
            )
        },
        "id": str(row.id),
        "business_id": row.business_id,
        "tenant_key": tenant_key,
        "tenant_business_id": tenant_business_id,
        "attribution": attribution(row) if row.publish_consent != "PRIVATE" else None,
        "consent_at": row.consent_at.isoformat(),
        "created_at": row.created_at.isoformat(),
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
    }


@router.get("/platform-admin/feedback")
def list_feedback(request: Request, db: Session = Depends(get_db)):
    _require_platform_admin(request, db)
    rows = db.query(TrialFeedback).order_by(TrialFeedback.created_at.desc()).limit(500).all()
    tenants = _tenant_references(db, (row.tenant_id for row in rows))
    scores = [row.recommend_score for row in rows if row.recommend_score is not None]
    promoters = sum(1 for score in scores if score >= 9)
    detractors = sum(1 for score in scores if score <= 6)

    def average(column: str):
        values = [getattr(row, column) for row in rows if getattr(row, column) is not None]
        return round(sum(values) / len(values), 1) if values else None

    return {
        "items": [_admin_row(row, tenants) for row in rows],
        "summary": {
            "responses": len(rows),
            "overall": average("rating_overall"),
            "ease": average("rating_ease"),
            "usefulness": average("rating_usefulness"),
            "ai_trust": average("rating_ai_trust"),
            "speed": average("rating_speed"),
            "import": average("rating_import"),
            "nps": round(100 * (promoters - detractors) / len(scores)) if scores else None,
            "nps_responses": len(scores),
        },
    }


@router.post("/platform-admin/feedback/{feedback_id}/publication")
def change_publication(
    feedback_id: uuid.UUID, payload: PublicationChange, request: Request, db: Session = Depends(get_db)
):
    admin = _require_platform_admin(request, db)
    row = db.query(TrialFeedback).filter(TrialFeedback.id == feedback_id).with_for_update().first()
    if row is None:
        raise _error(404, "FEEDBACK_NOT_FOUND", "Feedback not found")
    if payload.action == "PUBLISH":
        if row.publish_consent == "PRIVATE":
            raise _error(409, "FEEDBACK_NOT_CONSENTED", "This person did not agree to their feedback being shown")
        if not row.quote:
            raise _error(409, "FEEDBACK_NO_QUOTE", "There is no quote to show")
        if row.publish_consent == "ANONYMOUS" and _names_company(row.quote, row.organization_name):
            raise _error(409, "FEEDBACK_QUOTE_NAMES_COMPANY", "The quote names the company but consent is anonymous")
    now = datetime.now(timezone.utc)
    previous = row.publication_status
    row.publication_status = "PUBLISHED" if payload.action == "PUBLISH" else "HIDDEN"
    row.reviewed_by = admin.id
    row.reviewed_at = now
    row.updated_at = now
    _audit(
        db,
        admin.tenant_id,
        admin.id,
        f"TRIAL_FEEDBACK_{'PUBLISHED' if payload.action == 'PUBLISH' else 'HIDDEN'}",
        row,
        {"from": previous, "tenant_id": str(row.tenant_id)},
        now,
    )
    db.commit()
    return _admin_row(row, _tenant_references(db, [row.tenant_id]))


# ------------------------------------------------------------------------------------------- Website


@router.get("/public/testimonials")
def public_testimonials(db: Session = Depends(get_db)):
    """Published quotes only, credited as the person agreed; nothing else about the response leaves the server."""
    bind_system(db, "website: published customer quotes")
    rows = (
        db.query(TrialFeedback)
        .filter(TrialFeedback.publication_status == "PUBLISHED", TrialFeedback.publish_consent != "PRIVATE")
        .order_by(TrialFeedback.reviewed_at.desc())
        .limit(12)
        .all()
    )
    return {
        "items": [
            {"quote": row.quote, "attribution": attribution(row), "rating": row.rating_overall}
            for row in rows
            if row.quote
        ]
    }
