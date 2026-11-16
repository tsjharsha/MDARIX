"""A person accepts, edits or rejects every AI output (AI-R 4.4; owner decision AI-D7).

- ``POST /api/v1/ai-outputs/{output_id}/review`` (``ai.run``): one decision on one AI output, ``ACCEPTED``,
  ``EDITED`` (the person's text, with a reason) or ``REJECTED`` (with a reason). The output is a saved AI result
  (``ai_executions``) or an AI call (``ai_calls``, for an answer that is not saved as a result, such as Ask). A later
  review supersedes an earlier one; nothing is deleted (``ai_output_reviews`` is append-only). Audited
  ``AI_OUTPUT_REVIEWED``. The reviewer comes from the signed-in request only.
- ``GET /api/v1/ai-outputs/{output_id}/reviews``: the decisions, newest first.

Downstream use: ``usable_output`` decides whether a saved result may feed the Decision Center's readiness, the
Decision Brief, reports, codes or observations. A result a language model wrote is usable only after a person
accepted it (or edited it: the edited content is used and the model's stays in history); a rejected or unreviewed
one is not. Results the rules wrote (MDARIX's own engines) need no review.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from backend.app.access.permissions import AI_RUN, require_permission
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.ai_records import AiCall, AiOutputReview
from backend.app.db.models.foundation import AIExecution
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from genai.call_record import sha256

router = APIRouter(prefix="/api/v1", tags=["AI review"])

SUBJECT_EXECUTION = "ai_execution"
SUBJECT_CALL = "ai_call"
USABLE_DECISIONS = ("ACCEPTED", "EDITED")
# Saved results whose provider is one of MDARIX's own engines were written by rules, not by a language model.
RULE_PROVIDER_PREFIXES = ("mdarix-", "deterministic-")
NOT_A_MODEL = frozenset({"", "none", "controlled", "external-none"})
UNREVIEWED_LABEL = "AI proposal, not reviewed"


class ReviewRequest(BaseModel):
    decision: str = Field(pattern="^(ACCEPTED|EDITED|REJECTED)$")
    edited_text: str | None = Field(default=None, max_length=50_000)
    reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _complete(self):
        if self.decision in ("EDITED", "REJECTED") and len((self.reason or "").strip()) < 5:
            raise ValueError("An edit or a rejection needs a reason of at least 5 characters")
        if self.decision == "EDITED" and not (self.edited_text or "").strip():
            raise ValueError("An edit needs the edited text")
        if self.decision != "EDITED" and self.edited_text is not None:
            raise ValueError("Only an edit carries edited text")
        return self


def model_authored(provider: str | None) -> bool:
    """Whether a saved result came from a language model (not from MDARIX's rules)."""
    name = str(provider or "").strip().lower()
    return name not in NOT_A_MODEL and not name.startswith(RULE_PROVIDER_PREFIXES)


def latest_reviews(db: Session, tenant_id, subject_type: str, subject_ids) -> dict[str, AiOutputReview]:
    """The newest review of each subject (a later review supersedes an earlier one)."""
    ids = [str(item) for item in subject_ids]
    if not ids:
        return {}
    rows = (
        db.query(AiOutputReview)
        .filter(
            AiOutputReview.tenant_id == tenant_id,
            AiOutputReview.subject_type == subject_type,
            AiOutputReview.subject_id.in_(ids),
        )
        .order_by(AiOutputReview.created_at.asc())
        .all()
    )
    return {row.subject_id: row for row in rows}


def unreviewed_executions(db: Session, tenant_id, execution_ids) -> set[str]:
    """The ids among these saved results that a language model wrote and no person accepted or edited yet (AI-D7):
    what they produced is shown as "AI proposal, not reviewed" and is not used downstream."""
    ids = {str(item) for item in execution_ids if item}
    if not ids:
        return set()
    rows = db.query(AIExecution.id, AIExecution.provider).filter(
        AIExecution.tenant_id == tenant_id, AIExecution.id.in_([uuid.UUID(item) for item in ids])
    )
    by_model = {str(row.id) for row in rows if model_authored(row.provider)}
    reviews = latest_reviews(db, tenant_id, SUBJECT_EXECUTION, by_model)
    return {item for item in by_model if item not in reviews or reviews[item].decision not in USABLE_DECISIONS}


def usable_output(db: Session, row: AIExecution) -> tuple[bool, dict | None, str]:
    """(usable downstream, the output to use, its review state) for one saved result."""
    output = row.structured_output or {}
    if not model_authored(row.provider):
        return True, output, "RULES"
    review = latest_reviews(db, row.tenant_id, SUBJECT_EXECUTION, [row.id]).get(str(row.id))
    if review is None:
        return False, None, "NOT_REVIEWED"
    if review.decision == "REJECTED":
        return False, None, "REJECTED"
    if review.decision == "EDITED":
        try:
            edited = json.loads(review.edited_text or "")
        except ValueError:
            edited = None
        return True, edited if isinstance(edited, dict) else {**output, "edited_text": review.edited_text}, "EDITED"
    return True, output, "ACCEPTED"


def _subject(data_db: Session, control_db: Session, tenant_id: uuid.UUID, output_id: uuid.UUID):
    """(subject type, the session that holds it, the linked AI call id, the output text) or 404."""
    execution = (
        data_db.query(AIExecution).filter(AIExecution.tenant_id == tenant_id, AIExecution.id == output_id).first()
    )
    if execution is not None:
        return SUBJECT_EXECUTION, data_db, None, json.dumps(execution.structured_output or {}, default=str)
    call = control_db.query(AiCall).filter(AiCall.tenant_id == tenant_id, AiCall.id == output_id).first()
    if call is not None and call.outcome == "ANSWERED":
        return SUBJECT_CALL, control_db, call.id, call.output_text or ""
    raise HTTPException(404, detail={"code": "AI_OUTPUT_NOT_FOUND", "message": "Not found in your organization"})


@router.post("/ai-outputs/{output_id}/review", dependencies=[Depends(require_permission(AI_RUN))])
def review_output(
    output_id: uuid.UUID,
    payload: ReviewRequest,
    request: Request,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    subject_type, session, call_id, original = _subject(db, control_db, tenant_id, output_id)
    now = datetime.now(timezone.utc)
    edited = payload.edited_text if payload.decision == "EDITED" else None
    review = AiOutputReview(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        ai_call_id=call_id,
        subject_type=subject_type,
        subject_id=str(output_id),
        decision=payload.decision,
        edited_text=edited,
        edited_text_sha256=sha256(edited) if edited is not None else None,
        reason=(payload.reason or "").strip() or None,
        reviewer=str(ctx.user_id),
        created_at=now,
    )
    session.add(review)
    session.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=str(ctx.user_id),
            action="AI_OUTPUT_REVIEWED",
            entity_type="AiOutput",
            entity_id=output_id,
            details={
                "subject_type": subject_type,
                "decision": payload.decision,
                "output_sha256": sha256(original),
                "edited_text_sha256": review.edited_text_sha256,
            },
            request=request,
            reason=review.reason,
            created_at=now,
        )
    )
    session.commit()
    return _view(review)


@router.get("/ai-outputs/{output_id}/reviews", dependencies=[Depends(require_permission(AI_RUN))])
def output_reviews(
    output_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    subject_type, session, _, _ = _subject(db, control_db, tenant_id, output_id)
    rows = (
        session.query(AiOutputReview)
        .filter(
            AiOutputReview.tenant_id == tenant_id,
            AiOutputReview.subject_type == subject_type,
            AiOutputReview.subject_id == str(output_id),
        )
        .order_by(AiOutputReview.created_at.desc())
        .all()
    )
    return {"items": [_view(row) for row in rows], "state": rows[0].decision if rows else "NOT_REVIEWED"}


def _view(row: AiOutputReview) -> dict:
    return {
        "id": str(row.id),
        "subject_type": row.subject_type,
        "subject_id": row.subject_id,
        "decision": row.decision,
        "edited_text": row.edited_text,
        "reason": row.reason,
        "reviewer": row.reviewer,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
