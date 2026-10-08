"""Investigation evidence without a database: review rules, request validation, request statuses and their labels,
overdue, the actions a person may take, inventory counts, the new task type and source, and hooks that never raise."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.app.evidence_workflow import hooks
from backend.app.evidence_workflow.people import Person
from backend.app.evidence_workflow.rules import (
    REVIEWED_RELATIONSHIPS,
    REVIEWED_STATUSES,
    EvidenceLinkPayload,
    EvidenceRequestPayload,
    EvidenceReviewPayload,
    ReasonPayload,
    RequestReviewPayload,
    RespondPayload,
    case_closed,
    evidence_counts,
    is_overdue,
    relationship_label,
    request_actions,
    review_problem,
    review_status_label,
    status_label,
    task_source_type,
)

pytestmark = pytest.mark.unit

REASON = "The batch record contradicts the complaint date"


def _future(days: int = 3) -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=days)


# ------------------------------------------------------------------------------------------------- evidence review


def test_a_review_decides_quality_and_meaning_and_explains_setting_evidence_aside():
    assert "UNREVIEWED" not in REVIEWED_STATUSES and "UNREVIEWED" not in REVIEWED_RELATIONSHIPS
    assert review_problem("ACCEPTED", "SUPPORTING", None, None) is None
    assert review_problem("UNREVIEWED", "SUPPORTING", None, None)
    assert review_problem("ACCEPTED", "UNREVIEWED", None, None)
    for status in ("REJECTED", "QUARANTINED", "SUPERSEDED"):
        assert review_problem(status, "UNRELATED", None, None)
        assert review_problem(status, "UNRELATED", "too short", None)
        assert review_problem(status, "UNRELATED", REASON, None) is None
    assert review_problem("ACCEPTED_WITH_LIMITATION", "CONTEXTUAL", None, None)
    assert review_problem("ACCEPTED_WITH_LIMITATION", "CONTEXTUAL", None, "Only lot 7 was sampled") is None


def test_review_payload_normalizes_codes_and_enforces_the_rules():
    review = EvidenceReviewPayload(review_status=" accepted ", relationship="supporting", reason="  ")
    assert (review.review_status, review.relationship, review.reason) == ("ACCEPTED", "SUPPORTING", None)
    for body in (
        {"review_status": "REJECTED", "relationship": "UNRELATED"},
        {"review_status": "REJECTED", "relationship": "UNRELATED", "reason": "short"},
        {"review_status": "ACCEPTED_WITH_LIMITATION", "relationship": "SUPPORTING", "limitation": "   "},
        {"review_status": "UNREVIEWED", "relationship": "SUPPORTING"},
        {"review_status": "ACCEPTED", "relationship": "MAYBE"},
        {"review_status": "ACCEPTED", "relationship": "SUPPORTING", "reason": "x" * 2001},
    ):
        with pytest.raises(ValidationError):
            EvidenceReviewPayload(**body)
    limited = EvidenceReviewPayload(
        review_status="ACCEPTED_WITH_LIMITATION", relationship="CONTEXTUAL", limitation=" Only lot 7 "
    )
    assert limited.limitation == "Only lot 7"


def test_link_payload_defaults_to_unreviewed_and_links_each_piece_once():
    first, second = uuid.uuid4(), uuid.uuid4()
    payload = EvidenceLinkPayload(evidence_ids=[first, second, first])
    assert payload.relationship == "UNREVIEWED" and payload.evidence_ids == [first, second]
    assert EvidenceLinkPayload(evidence_ids=[first], relationship="contextual").relationship == "CONTEXTUAL"
    with pytest.raises(ValidationError):
        EvidenceLinkPayload(evidence_ids=[])
    with pytest.raises(ValidationError):
        EvidenceLinkPayload(evidence_ids=[first], relationship="RELEVANT")
    with pytest.raises(ValidationError):
        EvidenceLinkPayload(evidence_ids=[uuid.uuid4() for _ in range(101)])


def test_labels_counts_and_closed_cases():
    assert review_status_label("ACCEPTED_WITH_LIMITATION") == "Accepted with limitation"
    assert relationship_label("CONTRADICTING") == "Contradicting" and relationship_label(None) is None
    items = [
        {"link": {"review_status": "UNREVIEWED", "relationship": "UNREVIEWED"}},
        {"link": {"review_status": "ACCEPTED", "relationship": "SUPPORTING"}},
        {"link": {"review_status": "REJECTED", "relationship": "UNRELATED"}},
        {"link": {"review_status": "ACCEPTED_WITH_LIMITATION", "relationship": "CONTRADICTING"}},
    ]
    counts = evidence_counts(items)
    assert counts["total"] == 4 and counts["unreviewed"] == 1
    assert counts["accepted"] == counts["rejected"] == counts["accepted_with_limitation"] == 1
    assert counts["supporting"] == counts["unrelated"] == counts["contradicting"] == 1
    assert counts["quarantined"] == counts["superseded"] == counts["contextual"] == counts["unresolved"] == 0
    assert evidence_counts([])["total"] == 0
    assert case_closed("CLOSED") and case_closed("CANCELLED") and case_closed("OPEN", "closed")
    assert not case_closed("IN_PROGRESS", "open") and not case_closed(None)


# ---------------------------------------------------------------------------------------------- evidence requests


def test_request_statuses_have_the_labels_people_read():
    assert status_label("PENDING_DELIVERY") == status_label("SENT") == "Sent"
    assert status_label("REPLIED") == status_label("RECEIVED") == "Answered"
    assert status_label("OPEN") == "Open" and status_label("ACKNOWLEDGED") == "Acknowledged"
    assert status_label("CANNOT_PROVIDE") == "Cannot provide" and status_label("CANCELLED") == "Cancelled"
    assert status_label("REVIEWED") == "Reviewed" and status_label(None) is None
    assert task_source_type("INTERNAL") == "EvidenceRequest"
    assert task_source_type("SUPPLIER") == task_source_type(None) == "SupplierEvidenceRequest"


def test_overdue_means_past_due_and_still_waiting():
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    for status in ("OPEN", "ACKNOWLEDGED", "SENT", "PENDING_DELIVERY"):
        assert is_overdue(status, past)
    for status in ("RECEIVED", "REPLIED", "REVIEWED", "CANNOT_PROVIDE", "CANCELLED"):
        assert not is_overdue(status, past)
    assert not is_overdue("OPEN", _future()) and not is_overdue("OPEN", None)
    assert is_overdue("OPEN", past.replace(tzinfo=None))  # a stored naive time is UTC


def _actions(status, kind="INTERNAL", **who):
    flags = {"is_requester": False, "is_recipient": False, "can_assign": False, "can_review_evidence": False}
    return request_actions(kind=kind, status=status, **{**flags, **who})


def test_the_recipient_answers_and_the_requester_cancels_and_reviews():
    recipient = _actions("OPEN", is_recipient=True)
    assert recipient["can_acknowledge"] and recipient["can_respond"] and recipient["can_cannot_provide"]
    assert not recipient["can_cancel"] and not recipient["can_review"] and recipient["can_attach"]
    acknowledged = _actions("ACKNOWLEDGED", is_recipient=True)
    assert not acknowledged["can_acknowledge"] and acknowledged["can_respond"]
    requester = _actions("OPEN", is_requester=True)
    assert requester["can_cancel"] and not requester["can_respond"] and not requester["can_acknowledge"]
    assert _actions("OPEN", can_assign=True)["can_cancel"]
    answered = _actions("RECEIVED", is_requester=True)
    assert answered["can_review"] and not answered["can_cancel"]
    assert _actions("RECEIVED", can_review_evidence=True)["can_review"]
    assert not any(_actions("REVIEWED", is_requester=True, is_recipient=True, can_assign=True).values())
    assert not any(_actions("OPEN").values())  # someone else sees nothing to do


def test_a_supplier_request_is_answered_by_email_not_in_mdarix():
    supplier = _actions("SENT", kind="SUPPLIER", is_recipient=True, is_requester=True)
    assert not supplier["can_acknowledge"] and not supplier["can_respond"] and not supplier["can_cannot_provide"]
    assert supplier["can_cancel"] and supplier["can_attach"]
    assert _actions("REPLIED", kind="SUPPLIER", is_requester=True)["can_review"]


def _internal(**changes) -> dict:
    return {
        "kind": "INTERNAL",
        "title": "Lot KS-5521 batch record",
        "requested_items": ["Batch record", "Sterilization certificate"],
        "recipient_role": "INVESTIGATOR",
        **changes,
    }


def test_an_internal_request_names_a_colleague_or_a_role():
    made = EvidenceRequestPayload(**_internal(kind="internal", priority="high", requested_items=[" a ", "", "b"]))
    assert made.kind == "INTERNAL" and made.priority == "HIGH" and made.requested_items == ["a", "b"]
    assert EvidenceRequestPayload(**_internal(recipient_role=None, recipient_user_id=str(uuid.uuid4())))
    for changes in (
        {"recipient_role": None},
        {"supplier_id": str(uuid.uuid4())},
        {"recipient": "quality@supplier.example"},
        {"title": "Lo"},
        {"title": "    x    "},
        {"requested_items": []},
        {"requested_items": ["   "]},
        {"requested_items": [f"item {n}" for n in range(21)]},
        {"requested_items": ["x" * 241]},
        {"priority": "URGENT"},
        {"kind": "EMAIL"},
        {"due_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()},
        {"rationale": "x" * 2001},
    ):
        with pytest.raises(ValidationError):
            EvidenceRequestPayload(**_internal(**changes))


def test_a_supplier_request_names_the_supplier_and_its_address_only():
    body = {
        "kind": "SUPPLIER",
        "title": "Certificate of conformance",
        "requested_items": ["Certificate"],
        "supplier_id": str(uuid.uuid4()),
        "recipient": "quality@supplier.example",
    }
    assert EvidenceRequestPayload(**body).kind == "SUPPLIER"
    # The frontend names the address recipient_email; both names are accepted.
    aliased = {key: value for key, value in body.items() if key != "recipient"}
    assert EvidenceRequestPayload(**aliased, recipient_email="qa@supplier.example").recipient == "qa@supplier.example"
    assert EvidenceRequestPayload(**{**body, "title": "CoC"}).title == "CoC"  # three characters are enough
    for changes in ({"supplier_id": None}, {"recipient": None}, {"recipient_role": "INVESTIGATOR"}):
        with pytest.raises(ValidationError):
            EvidenceRequestPayload(**{**body, **changes})


def test_a_due_date_without_a_zone_is_utc():
    naive = (datetime.now(timezone.utc) + timedelta(days=2)).replace(tzinfo=None)
    made = EvidenceRequestPayload(**_internal(due_at=naive.isoformat()))
    assert made.due_at.tzinfo is not None and made.due_at.replace(tzinfo=None) == naive


def test_answers_reasons_and_reviews_are_validated():
    assert RespondPayload(note="  Batch record attached ").note == "Batch record attached"
    for note in ("", "   ", "x" * 5001):
        with pytest.raises(ValidationError):
            RespondPayload(note=note)
    assert ReasonPayload(reason=f"  {REASON}  ").reason == REASON
    for reason in ("short", "          x          ", "x" * 2001):
        with pytest.raises(ValidationError):
            ReasonPayload(reason=reason)
    accepted = RequestReviewPayload(accept=True, review_status="accepted", relationship="supporting")
    assert accepted.review_status == "ACCEPTED" and accepted.evidence_type is None
    assert (
        RequestReviewPayload(
            accept=True, review_status="ACCEPTED", relationship="CONTEXTUAL", evidence_type="lab report"
        ).evidence_type
        == "LAB_REPORT"
    )
    rejected = RequestReviewPayload(accept=False, reason=REASON)
    assert rejected.review_status is None
    for body in (
        {"accept": True},
        {"accept": True, "review_status": "REJECTED", "relationship": "UNRELATED"},
        {"accept": True, "review_status": "ACCEPTED_WITH_LIMITATION", "relationship": "SUPPORTING"},
        {"accept": False},
        {"accept": False, "reason": "too short"},
        {"accept": True, "review_status": "ACCEPTED", "relationship": "SUPPORTING", "evidence_type": "lab/report"},
    ):
        with pytest.raises(ValidationError):
            RequestReviewPayload(**body)


# --------------------------------------------------------------------------------------- people, tasks and hooks


def test_a_person_acts_under_the_role_granting_the_permission():
    me = uuid.uuid4()
    person = Person(
        user_id=str(me),
        user_uuid=me,
        tenant_id=uuid.uuid4(),
        permissions=frozenset({"evidence.review", "evidence.request"}),
        roles=["VIEWER", "Risk Reviewer"],
        account_role="VIEWER",
    )
    assert person.role_codes == {"VIEWER", "RISK_REVIEWER"}
    assert person.role_for("evidence.review") == "RISK_REVIEWER"
    assert person.role_for("decision.sign") == "VIEWER"
    assert person.holds_any("investigation.work", "evidence.review") and not person.holds("investigation.work")
    assert person.is_user(str(me)) and not person.is_user(None) and not person.is_user(str(uuid.uuid4()))


def test_the_evidence_response_task_and_its_source_are_known_to_my_work():
    from backend.app.workflow.labels import MANUAL_COMPLETION_TYPES, SOURCE_LABELS, TASK_TYPES, task_type_label
    from backend.app.workflow.router import _source_models

    assert TASK_TYPES["EVIDENCE_RESPONSE"].permission == "evidence.request"
    assert TASK_TYPES["EVIDENCE_RESPONSE"].queue_role == "INVESTIGATOR"
    assert task_type_label("EVIDENCE_RESPONSE") == "Provide evidence"
    # Answering finishes it, never the task's complete button.
    assert "EVIDENCE_RESPONSE" not in MANUAL_COMPLETION_TYPES
    assert SOURCE_LABELS["EvidenceRequest"] == "Evidence request"
    assert _source_models()["EvidenceRequest"].__tablename__ == "supplier_evidence_requests"


def test_the_new_routes_are_registered():
    from backend.app.main import app

    paths = app.openapi()["paths"]
    for path, method in (
        ("/api/v1/investigations/{investigation_id}/evidence-inventory", "get"),
        ("/api/v1/investigations/{investigation_id}/evidence-links", "post"),
        ("/api/v1/investigations/{investigation_id}/evidence/{evidence_id}/review", "post"),
        ("/api/v1/investigations/{investigation_id}/evidence/{evidence_id}/provenance", "get"),
        ("/api/v1/investigations/{investigation_id}/evidence-requests", "post"),
        ("/api/v1/evidence-requests", "get"),
        ("/api/v1/evidence-requests/{request_id}", "get"),
        ("/api/v1/evidence-requests/{request_id}/acknowledge", "post"),
        ("/api/v1/evidence-requests/{request_id}/respond", "post"),
        ("/api/v1/evidence-requests/{request_id}/cannot-provide", "post"),
        ("/api/v1/evidence-requests/{request_id}/cancel", "post"),
        ("/api/v1/evidence-requests/{request_id}/attachments", "post"),
        ("/api/v1/evidence-requests/{request_id}/attachments/{attachment_id}", "get"),
        ("/api/v1/evidence-requests/{request_id}/review", "post"),
    ):
        assert method in paths.get(path, {}), path


def test_attachment_uploads_are_refused_by_declared_size_like_supplier_uploads():
    from backend.app.evidence_workflow.requests import router
    from backend.app.stage3_workflow_router import _DeclaredSizeLimitedRoute

    (upload,) = [route for route in router.routes if route.path.endswith("/attachments") and "POST" in route.methods]
    assert isinstance(upload, _DeclaredSizeLimitedRoute)


class _BrokenSession:
    def __init__(self):
        self.rolled_back = False

    def begin_nested(self):
        raise RuntimeError("database unavailable")

    def rollback(self):
        self.rolled_back = True


def test_evidence_task_hooks_never_raise(caplog):
    row = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        business_id="EVR000001",
        title="Batch record",
        request_kind="INTERNAL",
        investigation_id=uuid.uuid4(),
        requested_by=str(uuid.uuid4()),
        recipient_user_id=None,
        recipient_role="INVESTIGATOR",
        priority="HIGH",
        due_at=None,
    )
    session = _BrokenSession()
    actor = str(uuid.uuid4())
    with caplog.at_level(logging.ERROR, logger="mdarix.workflow"):
        hooks.on_internal_request_created(session, None, row, actor_user_id=actor)
        hooks.on_supplier_request_scheduled(session, row)
        hooks.on_request_acknowledged(session, None, row, actor_user_id=actor)
        hooks.on_request_responded(session, None, row, actor_user_id=actor)
        hooks.on_request_cannot_provide(session, None, row, actor_user_id=actor)
        hooks.on_request_cancelled(session, None, row, actor_user_id=actor, reason=REASON)
        hooks.on_request_reviewed(session, None, row, actor_user_id=actor, accepted=True)
        hooks.on_evidence_reviewed(session, None, row.tenant_id, uuid.uuid4(), actor_user_id=actor)
    assert session.rolled_back
    assert "Workflow task hook" in " ".join(record.getMessage() for record in caplog.records)
