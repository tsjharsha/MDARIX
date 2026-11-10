"""A case's evidence: what it holds (linked, recorded on the case, or accepted from an evidence request), how each
piece is judged, and where it came from.

- ``GET  /api/v1/investigations/{id}/evidence-inventory``: every piece of evidence of the case with its review.
- ``POST /api/v1/investigations/{id}/evidence-links``: link evidence of the organization (``evidence.review`` or
  ``investigation.work``). Idempotent; nothing is ever unlinked (mark it SUPERSEDED or UNRELATED instead).
- ``POST /api/v1/investigations/{id}/evidence/{evidence_id}/review`` (``evidence.review``): its review status and
  relationship, with the reason or limitation the status needs. Every change is kept (evidence_review_events).
- ``GET  /api/v1/investigations/{id}/evidence/{evidence_id}/provenance``: source, document, request, review history.

Everything is limited to the signed-in organization: another organization's case or evidence is "not found". Writes
lock the case row, refuse a CLOSED or CANCELLED case (409) and are audited (EVIDENCE_LINKED, EVIDENCE_REVIEWED).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.access.permissions import EVIDENCE_REQUEST, EVIDENCE_REVIEW, INVESTIGATION_WORK, require_permission
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.case_scope import EvidenceReviewEvent
from backend.app.db.models.foundation import Evidence, Investigation, InvestigationEvidence
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.evidence_workflow.people import Person, current_person, require_any_permission
from backend.app.evidence_workflow.rules import (
    UNREVIEWED,
    EvidenceLinkPayload,
    EvidenceReviewPayload,
    case_closed,
    evidence_counts,
    relationship_label,
    review_status_label,
)
from backend.app.request_context import AuthenticatedRequestContext, get_request_context

logger = logging.getLogger("mdarix.evidence_workflow")

router = APIRouter(prefix="/api/v1/investigations", tags=["Investigation Evidence"])


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def error(status: int, code: str, message: str, **extra) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message, **extra})


def load_case(db: Session, tenant_id, investigation_id, *, lock: bool = False) -> Investigation:
    query = db.query(Investigation).filter(Investigation.id == investigation_id, Investigation.tenant_id == tenant_id)
    if lock:
        query = query.with_for_update()
    case = query.first()
    if case is None:
        raise error(404, "INVESTIGATION_NOT_FOUND", "Investigation is not available")
    return case


def refuse_closed(case: Investigation) -> None:
    if case_closed(getattr(case, "workflow_state", None), case.status):
        raise error(409, "CASE_CLOSED", "The investigation is closed; its evidence can no longer change")


def evidence_view(ev: Evidence) -> dict:
    return {
        "id": str(ev.id),
        "business_id": ev.business_id,
        "evidence_identifier": ev.evidence_identifier,
        "title": ev.title,
        "evidence_type": ev.evidence_type,
        "source_system": ev.source_system,
        "source_identifier": ev.source_identifier,
        "source_reference": ev.source_reference,
        "source_timestamp": _iso(ev.source_timestamp),
        "recorded_timestamp": _iso(ev.recorded_timestamp),
        "ingestion_timestamp": _iso(ev.ingestion_timestamp),
        "reliability_status": ev.reliability_status,
        "fact_type": ev.fact_type,
        "has_document": bool(ev.document_ref),
    }


def _name(names: dict[str, str], ref) -> str | None:
    from backend.app.business_ids import as_uuid

    key = as_uuid(ref)
    if key is not None:
        return names.get(str(key))
    return "MDARIX" if str(ref or "").startswith("system") else None


def link_view(link: InvestigationEvidence | None, names: dict[str, str]) -> dict:
    if link is None:
        # Evidence recorded on the case itself that nobody has reviewed yet.
        return {
            "linked": False,
            "review_status": UNREVIEWED,
            "review_status_label": review_status_label(UNREVIEWED),
            "relationship": UNREVIEWED,
            "relationship_label": relationship_label(UNREVIEWED),
            "review_reason": None,
            "limitation": None,
            "reviewed_by_name": None,
            "reviewed_at": None,
            "linked_by_name": None,
            "created_at": None,
        }
    return {
        "linked": True,
        "review_status": link.review_status,
        "review_status_label": review_status_label(link.review_status),
        "relationship": link.relationship,
        "relationship_label": relationship_label(link.relationship),
        "review_reason": link.review_reason,
        "limitation": link.limitation,
        "reviewed_by_name": _name(names, link.reviewed_by),
        "reviewed_at": _iso(link.reviewed_at),
        "linked_by_name": _name(names, link.linked_by),
        "created_at": _iso(link.created_at),
    }


def inventory_items(
    db: Session, control_db: Session | None, tenant_id, case: Investigation, evidence_ids=None
) -> list[dict]:
    """The case's evidence (its links, and evidence recorded on the case without a link), newest first. With
    ``evidence_ids`` only those of them."""
    from backend.app.db.models.stage3 import SupplierEvidenceRequest
    from backend.app.workflow.people import names_by_id

    wanted = set(evidence_ids) if evidence_ids is not None else None
    link_query = db.query(InvestigationEvidence).filter(
        InvestigationEvidence.tenant_id == tenant_id, InvestigationEvidence.investigation_id == case.id
    )
    direct_query = db.query(Evidence.id).filter(Evidence.tenant_id == tenant_id, Evidence.investigation_id == case.id)
    if wanted is not None:
        if not wanted:
            return []
        link_query = link_query.filter(InvestigationEvidence.evidence_id.in_(list(wanted)))
        direct_query = direct_query.filter(Evidence.id.in_(list(wanted)))
    links = {link.evidence_id: link for link in link_query.all()}
    ids = set(links) | {row[0] for row in direct_query.all()}
    if not ids:
        return []
    rows = db.query(Evidence).filter(Evidence.tenant_id == tenant_id, Evidence.id.in_(list(ids))).all()
    requests = {
        evidence_id: {"id": str(request_id), "business_id": business_id}
        for request_id, business_id, evidence_id in db.query(
            SupplierEvidenceRequest.id,
            SupplierEvidenceRequest.business_id,
            SupplierEvidenceRequest.resolved_evidence_id,
        ).filter(
            SupplierEvidenceRequest.tenant_id == tenant_id,
            SupplierEvidenceRequest.resolved_evidence_id.in_(list(ids)),
        )
    }
    names = (
        names_by_id(
            control_db,
            tenant_id,
            [ref for link in links.values() for ref in (link.reviewed_by, link.linked_by)],
        )
        if control_db is not None
        else {}
    )
    items = []
    for ev in rows:
        link = links.get(ev.id)
        if ev.id in requests:
            origin = "REQUEST"
        elif ev.investigation_id == case.id:
            origin = "DIRECT"
        else:
            origin = "LINKED"
        items.append(
            {
                "evidence": evidence_view(ev),
                "link": link_view(link, names),
                "origin": origin,
                "request": requests.get(ev.id),
                "_sort": (link.created_at if link is not None else None) or ev.created_at,
            }
        )
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    items.sort(key=lambda item: (item["_sort"] or epoch, item["evidence"]["evidence_identifier"] or ""), reverse=True)
    for item in items:
        item.pop("_sort", None)
    return items


def case_actions(person: Person, case: Investigation) -> dict[str, bool]:
    open_case = not case_closed(getattr(case, "workflow_state", None), case.status)
    return {
        "can_link": open_case and person.holds_any(EVIDENCE_REVIEW, INVESTIGATION_WORK),
        "can_review": open_case and person.holds(EVIDENCE_REVIEW),
        "can_request": open_case and person.holds(EVIDENCE_REQUEST),
    }


def review_event(
    db: Session,
    *,
    tenant_id,
    case_id,
    evidence_id,
    event_type: str,
    actor: Person,
    permission: str,
    from_status=None,
    to_status=None,
    from_relationship=None,
    to_relationship=None,
    reason: str | None = None,
    details: dict | None = None,
    now: datetime,
) -> EvidenceReviewEvent:
    event = EvidenceReviewEvent(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        investigation_id=case_id,
        evidence_id=evidence_id,
        event_type=event_type,
        from_review_status=from_status,
        to_review_status=to_status,
        from_relationship=from_relationship,
        to_relationship=to_relationship,
        reason=reason,
        actor_ref=actor.user_id,
        actor_role=actor.role_for(permission),
        details=dict(details or {}),
        created_at=now,
    )
    db.add(event)
    return event


@router.get("/{investigation_id}/evidence-inventory")
def evidence_inventory(
    investigation_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    case = load_case(db, tenant_id, investigation_id)
    items = inventory_items(db, control_db, tenant_id, case)
    return {
        "items": items,
        "counts": evidence_counts(items),
        "actions": case_actions(current_person(control_db, ctx), case),
    }


@router.post(
    "/{investigation_id}/evidence-links",
    dependencies=[Depends(require_any_permission(EVIDENCE_REVIEW, INVESTIGATION_WORK))],
)
def link_evidence(
    investigation_id: uuid.UUID,
    payload: EvidenceLinkPayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Link evidence of the organization to the case. Evidence already linked is left as it is."""
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    person = current_person(control_db, ctx)
    case = load_case(db, tenant_id, investigation_id, lock=True)
    refuse_closed(case)
    found = {
        row[0]
        for row in db.query(Evidence.id).filter(
            Evidence.tenant_id == tenant_id, Evidence.id.in_(list(payload.evidence_ids))
        )
    }
    missing = [str(item) for item in payload.evidence_ids if item not in found]
    if missing:
        raise error(404, "EVIDENCE_NOT_FOUND", "Evidence is not available in your organization", evidence_ids=missing)
    existing = {
        row[0]
        for row in db.query(InvestigationEvidence.evidence_id).filter(
            InvestigationEvidence.tenant_id == tenant_id,
            InvestigationEvidence.investigation_id == case.id,
            InvestigationEvidence.evidence_id.in_(list(found)),
        )
    }
    now = now_utc()
    created = []
    permission = EVIDENCE_REVIEW if person.holds(EVIDENCE_REVIEW) else INVESTIGATION_WORK
    for evidence_id in payload.evidence_ids:
        if evidence_id in existing:
            continue
        link = InvestigationEvidence(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            investigation_id=case.id,
            evidence_id=evidence_id,
            relevance=payload.reason,
            created_at=now,
            review_status=UNREVIEWED,
            relationship=payload.relationship,
            linked_by=person.user_id,
        )
        db.add(link)
        db.flush()
        review_event(
            db,
            tenant_id=tenant_id,
            case_id=case.id,
            evidence_id=evidence_id,
            event_type="LINKED",
            actor=person,
            permission=permission,
            to_status=UNREVIEWED,
            to_relationship=payload.relationship,
            reason=payload.reason,
            now=now,
        )
        db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=person.user_id,
                action="EVIDENCE_LINKED",
                entity_type="InvestigationEvidence",
                entity_id=link.id,
                correlation_id=ctx.correlation_id,
                reason=payload.reason,
                details={
                    "investigation_id": str(case.id),
                    "evidence_id": str(evidence_id),
                    "relationship": payload.relationship,
                    "actor_role": person.role_for(permission),
                },
                created_at=now,
            )
        )
        created.append(evidence_id)
    db.commit()
    # Evidence reaching a decided case asks for an impact assessment; the signed decision never changes. Never blocks
    # or undoes the link (backend/app/decision_followups/impact.py).
    from backend.app.decision_followups.impact import after_late_evidence

    after_late_evidence(
        db,
        control_db,
        tenant_id,
        investigation_id,
        created,
        trigger="EVIDENCE_LINKED",
        actor_ref=person.user_id,
        correlation_id=ctx.correlation_id,
    )
    return {
        "linked": len(created),
        "already_linked": len(payload.evidence_ids) - len(created),
        "items": inventory_items(db, control_db, tenant_id, case, evidence_ids=payload.evidence_ids),
    }


@router.post(
    "/{investigation_id}/evidence/{evidence_id}/review", dependencies=[Depends(require_permission(EVIDENCE_REVIEW))]
)
def review_evidence(
    investigation_id: uuid.UUID,
    evidence_id: uuid.UUID,
    payload: EvidenceReviewPayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Record the case's review of one piece of evidence: linked to the case, or recorded on it (its link is
    created now)."""
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    person = current_person(control_db, ctx)
    case = load_case(db, tenant_id, investigation_id, lock=True)
    refuse_closed(case)
    ev = db.query(Evidence).filter(Evidence.tenant_id == tenant_id, Evidence.id == evidence_id).first()
    if ev is None:
        raise error(404, "EVIDENCE_NOT_FOUND", "Evidence is not available in your organization")
    link = (
        db.query(InvestigationEvidence)
        .filter(
            InvestigationEvidence.tenant_id == tenant_id,
            InvestigationEvidence.investigation_id == case.id,
            InvestigationEvidence.evidence_id == ev.id,
        )
        .with_for_update()
        .first()
    )
    now = now_utc()
    if link is None:
        if ev.investigation_id != case.id:
            raise error(404, "EVIDENCE_NOT_IN_CASE", "Link the evidence to the investigation before reviewing it")
        link = InvestigationEvidence(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            investigation_id=case.id,
            evidence_id=ev.id,
            created_at=now,
            review_status=UNREVIEWED,
            relationship=UNREVIEWED,
            linked_by=person.user_id,
        )
        db.add(link)
        db.flush()
    before = {
        "review_status": link.review_status,
        "relationship": link.relationship,
        "review_reason": link.review_reason,
        "limitation": link.limitation,
    }
    link.review_status = payload.review_status
    link.relationship = payload.relationship
    link.review_reason = payload.reason
    link.limitation = payload.limitation
    link.reviewed_by = person.user_id
    link.reviewed_at = now
    review_event(
        db,
        tenant_id=tenant_id,
        case_id=case.id,
        evidence_id=ev.id,
        event_type="REVIEWED",
        actor=person,
        permission=EVIDENCE_REVIEW,
        from_status=before["review_status"],
        to_status=payload.review_status,
        from_relationship=before["relationship"],
        to_relationship=payload.relationship,
        reason=payload.reason,
        details={"limitation": payload.limitation} if payload.limitation else None,
        now=now,
    )
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=person.user_id,
            action="EVIDENCE_REVIEWED",
            entity_type="InvestigationEvidence",
            entity_id=link.id,
            correlation_id=ctx.correlation_id,
            reason=payload.reason,
            old_values=before,
            new_values={
                "review_status": payload.review_status,
                "relationship": payload.relationship,
                "review_reason": payload.reason,
                "limitation": payload.limitation,
            },
            details={
                "investigation_id": str(case.id),
                "evidence_id": str(ev.id),
                "actor_role": person.role_for(EVIDENCE_REVIEW),
            },
            created_at=now,
        )
    )
    db.commit()
    # A request's review task ends when the evidence it produced is reviewed. Never undoes the review.
    from backend.app.evidence_workflow.hooks import on_evidence_reviewed

    on_evidence_reviewed(db, control_db, tenant_id, ev.id, actor_user_id=person.user_id)
    # Evidence reviewed on a decided case asks for an impact assessment (once per decision and evidence). Never blocks
    # or undoes the review (backend/app/decision_followups/impact.py).
    from backend.app.decision_followups.impact import after_late_evidence

    after_late_evidence(
        db,
        control_db,
        tenant_id,
        investigation_id,
        [evidence_id],
        trigger="EVIDENCE_REVIEWED",
        actor_ref=person.user_id,
        correlation_id=ctx.correlation_id,
    )
    return inventory_items(db, control_db, tenant_id, case, evidence_ids=[ev.id])[0]


# ------------------------------------------------------------------------------------------------------ provenance


def _optional(db: Session, name: str, read):
    """An optional lookup inside a SAVEPOINT: a table a plane lacks never fails the provenance view."""
    try:
        with db.begin_nested():
            return read()
    except Exception:
        logger.warning("Evidence provenance: %s could not be read", name, exc_info=True)
        return None


def _source(db: Session, tenant_id, ev: Evidence) -> dict:
    from backend.app.db.models.foundation import SourceRecord

    source = {
        "system": ev.source_system,
        "record_identifier": ev.source_identifier,
        "record_version": None,
        "reference": ev.source_reference,
        "source_timestamp": _iso(ev.source_timestamp),
        "effective_timestamp": _iso(ev.effective_timestamp),
        "recorded_timestamp": _iso(ev.recorded_timestamp),
        "ingestion_timestamp": _iso(ev.ingestion_timestamp),
        "checksum": None,
        "data_quality_status": None,
        "ingestion_run": None,
        "connector_run": None,
        "mapping_version": None,
    }
    if ev.source_record_id is None:
        return source
    record = _optional(
        db,
        "source record",
        lambda: (
            db.query(SourceRecord)
            .filter(SourceRecord.tenant_id == tenant_id, SourceRecord.id == ev.source_record_id)
            .first()
        ),
    )
    if record is None:
        return source
    source.update(
        {
            "system": source["system"] or record.source_system,
            "record_identifier": source["record_identifier"] or record.source_record_id,
            "record_version": record.source_record_version,
            "checksum": record.checksum,
            "data_quality_status": record.data_quality_status,
            "source_timestamp": source["source_timestamp"] or _iso(record.source_timestamp),
            "effective_timestamp": source["effective_timestamp"] or _iso(record.effective_timestamp),
            "ingestion_timestamp": source["ingestion_timestamp"] or _iso(record.ingestion_timestamp),
        }
    )

    def ingestion():
        from backend.app.db.models.ingestion import IngestionRun, StagedSourceRecord

        staged = (
            db.query(StagedSourceRecord.ingestion_run_id, StagedSourceRecord.mapping_version)
            .filter(
                StagedSourceRecord.tenant_id == tenant_id,
                StagedSourceRecord.source_system == record.source_system,
                StagedSourceRecord.source_record_id == record.source_record_id,
            )
            .order_by(StagedSourceRecord.created_at.desc())
            .first()
        )
        if staged is None:
            return None
        run = (
            db.query(IngestionRun)
            .filter(IngestionRun.tenant_id == tenant_id, IngestionRun.id == staged.ingestion_run_id)
            .first()
        )
        return {
            "mapping_version": staged.mapping_version,
            "run": (
                {
                    "id": str(run.id),
                    "status": run.status,
                    "source_type": run.source_type,
                    "started_at": _iso(run.ingestion_started_at),
                    "completed_at": _iso(run.ingestion_completed_at),
                    "mapping_version": run.mapping_version,
                    "configuration_version": run.configuration_version,
                }
                if run is not None
                else None
            ),
        }

    def connector():
        from backend.app.db.models.enterprise import ConnectorRun, ConnectorSourceRecord

        found = (
            db.query(ConnectorSourceRecord.connector_run_id)
            .filter(
                ConnectorSourceRecord.tenant_id == tenant_id,
                ConnectorSourceRecord.source_system == record.source_system,
                ConnectorSourceRecord.source_record_id == record.source_record_id,
            )
            .order_by(ConnectorSourceRecord.created_at.desc())
            .first()
        )
        if found is None:
            return None
        run = (
            db.query(ConnectorRun)
            .filter(ConnectorRun.tenant_id == tenant_id, ConnectorRun.id == found.connector_run_id)
            .first()
        )
        if run is None:
            return None
        return {
            "id": str(run.id),
            "connection_id": run.connection_id,
            "run_type": run.run_type,
            "status": run.status,
            "started_at": _iso(run.started_at),
            "completed_at": _iso(run.completed_at),
        }

    traced = _optional(db, "ingestion run", ingestion)
    if traced:
        source["ingestion_run"] = traced["run"]
        source["mapping_version"] = traced["mapping_version"]
    source["connector_run"] = _optional(db, "connector run", connector)
    return source


@router.get("/{investigation_id}/evidence/{evidence_id}/provenance")
def evidence_provenance(
    investigation_id: uuid.UUID,
    evidence_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Where one piece of evidence came from and how this case has judged it. Read-only."""
    from backend.app.db.models.evidence_intelligence import EvidenceObservation
    from backend.app.db.models.foundation import Hypothesis, HypothesisEvidence
    from backend.app.db.models.stage3 import EvidenceAttachment, SupplierEvidenceRequest
    from backend.app.workflow.people import names_by_id

    tenant_id = uuid.UUID(str(ctx.tenant_id))
    case = load_case(db, tenant_id, investigation_id)
    ev = db.query(Evidence).filter(Evidence.tenant_id == tenant_id, Evidence.id == evidence_id).first()
    if ev is None:
        raise error(404, "EVIDENCE_NOT_FOUND", "Evidence is not available in your organization")
    request = (
        db.query(SupplierEvidenceRequest)
        .filter(SupplierEvidenceRequest.tenant_id == tenant_id, SupplierEvidenceRequest.resolved_evidence_id == ev.id)
        .order_by(SupplierEvidenceRequest.created_at.desc())
        .first()
    )
    document = None
    if request is not None:
        attachments = (
            db.query(EvidenceAttachment)
            .filter(EvidenceAttachment.tenant_id == tenant_id, EvidenceAttachment.request_id == request.id)
            .order_by(EvidenceAttachment.created_at, EvidenceAttachment.id)
            .all()
        )
        chosen = next((item for item in attachments if item.object_key == ev.document_ref), None) or (
            attachments[0] if attachments else None
        )
        if chosen is not None:
            document = {
                "available": True,
                "attachment_id": str(chosen.id),
                "request_id": str(request.id),
                "filename": chosen.filename,
                "content_type": chosen.content_type,
                "checksum": chosen.checksum,
                "size": chosen.size,
                "download_path": f"/api/v1/evidence-requests/{request.id}/attachments/{chosen.id}",
            }
        else:
            document = {
                "available": False,
                "attachment_id": None,
                "request_id": str(request.id),
                "filename": None,
                "content_type": None,
                "checksum": None,
                "size": None,
                "download_path": None,
            }
    events = (
        db.query(EvidenceReviewEvent)
        .filter(
            EvidenceReviewEvent.tenant_id == tenant_id,
            EvidenceReviewEvent.investigation_id == case.id,
            EvidenceReviewEvent.evidence_id == ev.id,
        )
        .order_by(EvidenceReviewEvent.created_at, EvidenceReviewEvent.id)
        .all()
    )
    names = names_by_id(
        control_db, tenant_id, [event.actor_ref for event in events] + ([request.requested_by] if request else [])
    )
    observations = (
        _optional(
            db,
            "observations",
            lambda: (
                db.query(func.count(EvidenceObservation.id))
                .filter(EvidenceObservation.tenant_id == tenant_id, EvidenceObservation.evidence_id == ev.id)
                .scalar()
            ),
        )
        or 0
    )
    hypotheses = (
        db.query(func.count(func.distinct(HypothesisEvidence.hypothesis_id)))
        .join(
            Hypothesis,
            (Hypothesis.id == HypothesisEvidence.hypothesis_id)
            & (Hypothesis.tenant_id == HypothesisEvidence.tenant_id),
        )
        .filter(
            HypothesisEvidence.tenant_id == tenant_id,
            HypothesisEvidence.evidence_id == ev.id,
            Hypothesis.investigation_id == case.id,
        )
        .scalar()
        or 0
    )
    link = (
        db.query(InvestigationEvidence)
        .filter(
            InvestigationEvidence.tenant_id == tenant_id,
            InvestigationEvidence.investigation_id == case.id,
            InvestigationEvidence.evidence_id == ev.id,
        )
        .first()
    )
    in_case = link is not None or ev.investigation_id == case.id
    return {
        "evidence": {
            **evidence_view(ev),
            "effective_timestamp": _iso(ev.effective_timestamp),
            "in_case": in_case,
            "review_status": link.review_status if link is not None else (UNREVIEWED if in_case else None),
            "relationship": link.relationship if link is not None else (UNREVIEWED if in_case else None),
        },
        "source": _source(db, tenant_id, ev),
        "document": document,
        "request": (
            {
                "id": str(request.id),
                "business_id": request.business_id,
                "kind": request.request_kind,
                "title": request.title,
                "requested_by_name": _name(names, request.requested_by),
                "responded_at": _iso(request.responded_at),
            }
            if request is not None
            else None
        ),
        "review_history": [
            {
                "event_type": event.event_type,
                "from_review_status": event.from_review_status,
                "to_review_status": event.to_review_status,
                "from_relationship": event.from_relationship,
                "to_relationship": event.to_relationship,
                "reason": event.reason,
                "limitation": (event.details or {}).get("limitation"),
                "actor_name": _name(names, event.actor_ref),
                "actor_role": event.actor_role,
                "created_at": _iso(event.created_at),
            }
            for event in events
        ],
        "used_by": {"observations": int(observations), "hypotheses": int(hypotheses)},
    }
