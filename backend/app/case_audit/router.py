"""The trust and audit routes of one case (``/api/v1/investigations/{id}/trust``):

- ``GET /timeline`` (``types``, ``actor``, ``since``, ``until``, ``page``, ``page_size``): everything recorded about
  the case and its signals, merged, deduplicated and oldest first;
- ``GET /replay`` (``as_known_at`` or ``decision_id``): the case as known at a moment, by default when its current
  decision was signed;
- ``GET /ai-runs``: every AI run of the case with its model, versions, context hash, guardrails, human review and
  whether the signed decision disclosed it;
- ``GET /integrity``: the verification of the case's signatures, brief fingerprints and audit chain;
- ``GET /export`` (``format`` json | csv; ``data.export``): all of the above as a download, audited
  CASE_AUDIT_EXPORTED with the file's SHA-256.

Reading needs a signed-in session of the case's organization (another organization's case is "not found"). Nothing
is changed except the export's audit event.
"""

from __future__ import annotations

import hashlib
import io
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from backend.app.downloads import attachment
from backend.app.access.permissions import DATA_EXPORT, require_permission
from backend.app.case_audit import rules, service
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import Decision
from backend.app.db.session import get_db
from backend.app.decision_followups.common import error, load_case, tenant_of
from backend.app.enterprise_audit import make_audit_event
from backend.app.request_context import AuthenticatedRequestContext, get_request_context

router = APIRouter(prefix="/api/v1/investigations/{investigation_id}/trust", tags=["Case Trust and Audit"])
EXPORT_VERSION = "case-audit-1"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _case(db: Session, ctx: AuthenticatedRequestContext, investigation_id):
    return load_case(db, tenant_of(ctx), investigation_id)


@router.get("/timeline")
def case_timeline(
    investigation_id: uuid.UUID,
    types: str | None = Query(None, max_length=300),
    actor: str | None = Query(None, max_length=120),
    since: datetime | None = None,
    until: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(rules.PAGE_SIZE_DEFAULT, ge=1, le=rules.PAGE_SIZE_MAX),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """``{items, total, categories, page, page_size, incomplete_sources}``; ``categories`` counts, by category, the
    items that match every filter except ``types``."""
    case = _case(db, ctx, investigation_id)
    items, incomplete = service.timeline(db, control_db, case)
    # The category counts follow every filter but the categories themselves, so unselected ones still show theirs.
    unfiltered = rules.filter_items(items, actor=actor, since=since, until=until)
    matching = rules.filter_items(unfiltered, types=rules.parse_types(types))
    return {
        "investigation": {"business_id": case.business_id, "identifier": case.investigation_identifier},
        "items": [rules.public(entry) for entry in rules.page_of(matching, page, page_size)],
        "total": len(matching),
        "categories": rules.category_counts(unfiltered),
        "page": page,
        "page_size": page_size,
        "incomplete_sources": incomplete,
    }


@router.get("/replay")
def case_replay(
    investigation_id: uuid.UUID,
    as_known_at: datetime | None = None,
    decision_id: uuid.UUID | None = None,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The case as it was known at ``as_known_at`` (default: when ``decision_id``, else the current signed
    decision, was signed; else now)."""
    case = _case(db, ctx, investigation_id)
    decision = None
    if decision_id is not None:
        decision = (
            db.query(Decision)
            .filter(
                Decision.tenant_id == case.tenant_id, Decision.investigation_id == case.id, Decision.id == decision_id
            )
            .first()
        )
        if decision is None:
            raise error(404, "DECISION_NOT_FOUND", "This decision does not belong to this investigation")
    return service.replay(db, control_db, case, as_known_at=as_known_at, decision=decision, now=_now())


@router.get("/ai-runs")
def case_ai_runs(
    investigation_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    case = _case(db, ctx, investigation_id)
    return service.ai_runs(db, control_db, case)


@router.get("/integrity")
def case_integrity(
    investigation_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    case = _case(db, ctx, investigation_id)
    return service.integrity(db, control_db, case)


def _csv(rows: list[dict]) -> bytes:
    from backend.app.csv_safe import writer

    stream = io.StringIO()
    out = writer(stream, fieldnames=list(rules.TIMELINE_CSV_FIELDS), extrasaction="ignore")
    out.writeheader()
    out.writerows(rows)
    return stream.getvalue().encode("utf-8")


@router.get("/export", dependencies=[Depends(require_permission(DATA_EXPORT))])
def case_audit_export(
    investigation_id: uuid.UUID,
    format: str = Query("json", pattern="^(?i:json|csv)$"),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The case's timeline, AI runs and integrity results as a JSON or CSV download. Every export is audited
    CASE_AUDIT_EXPORTED with the SHA-256 of the file."""
    case = _case(db, ctx, investigation_id)
    now = _now()
    items, incomplete = service.timeline(db, control_db, case)
    timeline = [rules.public(entry) for entry in items]
    runs = service.ai_runs(db, control_db, case)
    checks = service.integrity(db, control_db, case)
    fmt = format.lower()
    if fmt == "csv":
        content = _csv(rules.csv_rows(timeline, runs["items"], checks))
        media_type = "text/csv; charset=utf-8"
    else:
        document = {
            "export_version": EXPORT_VERSION,
            "exported_at": now.isoformat(),
            "investigation": {"business_id": case.business_id, "identifier": case.investigation_identifier},
            "timeline": timeline,
            "incomplete_sources": incomplete,
            "ai_runs": runs,
            "integrity": checks,
        }
        content = json.dumps(document, indent=2, sort_keys=True, default=str).encode("utf-8")
        media_type = "application/json"
    digest = hashlib.sha256(content).hexdigest()
    control_db.add(
        make_audit_event(
            tenant_id=case.tenant_id,
            actor_ref=str(ctx.user_id),
            action="CASE_AUDIT_EXPORTED",
            entity_type="Investigation",
            entity_id=case.id,
            correlation_id=ctx.correlation_id,
            details={
                "investigation_id": str(case.id),
                "investigation_business_id": case.business_id,
                "format": fmt.upper(),
                "sha256": digest,
                "bytes": len(content),
                "counts": {
                    "timeline": len(timeline),
                    "ai_runs": runs["counts"]["total"],
                    "signatures": len(checks["signatures"]),
                },
                "export_version": EXPORT_VERSION,
            },
            created_at=now,
        )
    )
    control_db.commit()
    name = "".join(char for char in str(case.business_id or case.id) if char.isalnum() or char in "-_") or "case"
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": attachment(f"{name}-audit.{fmt}"),
            "X-Content-SHA256": digest,
            "Cache-Control": "no-store",
        },
    )
