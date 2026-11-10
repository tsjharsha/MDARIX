"""0.10.93 (B2, spec 9.3): "Signed before 0.10.93: escalate".

SAMPLE-CALL-02 was signed "Complaint and service" before signing escalated, and was never linked. It is not escalated
by the upgrade; its Case check offers the escalation with the duplicate choice pre-set to SAMPLE-RT-05. The signed
check stands (nothing is signed again); its old QMS task is completed "Not needed: owned in MDARIX" in a trial.
"""

from __future__ import annotations

import uuid

import pytest

from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.test_free_trial import _approved_trial_client

pytestmark = pytest.mark.db

INTAKE = "/api/v1/intake"


def _ok(response, status: int = 200):
    assert response.status_code == status, response.text
    return response.json()


def _ids(tenant_id) -> dict:
    from backend.app.db.models.foundation import Complaint
    from backend.app.db.models.intake import IntakeEvent

    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        events = dict(
            db.query(IntakeEvent.reference, IntakeEvent.id)
            .filter(IntakeEvent.tenant_id == tenant_id, IntakeEvent.reference.in_(["SAMPLE-CALL-02", "SAMPLE-CASE-11"]))
            .all()
        )
        rt05 = (
            db.query(Complaint.id)
            .filter(Complaint.tenant_id == tenant_id, Complaint.complaint_identifier == "SAMPLE-RT-05")
            .scalar()
        )
    return {**{ref: str(value) for ref, value in events.items()}, "SAMPLE-RT-05": str(rt05)}


def _qms_tasks(tenant_id, event_id: str) -> list[tuple[str, str | None]]:
    from backend.app.db.models.workflow import WorkflowTask
    from backend.app.intake import service

    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        rows = (
            db.query(WorkflowTask)
            .filter(
                WorkflowTask.tenant_id == tenant_id,
                WorkflowTask.source_entity_id == uuid.UUID(event_id),
                WorkflowTask.task_type == service.QMS,
            )
            .all()
        )
        return [(row.status, row.completion_outcome) for row in rows]


def test_a_case_signed_before_0_10_93_is_escalated_with_the_duplicate_choice():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        ids = _ids(tenant_id)
        call02, case11, rt05 = ids["SAMPLE-CALL-02"], ids["SAMPLE-CASE-11"], ids["SAMPLE-RT-05"]
        before = _ok(user.get(f"{INTAKE}/{call02}"))
        assert before["escalate_signed"] is True and before["signed"]["classification"] == "BOTH"
        assert before["complaint_id"] is None and before["status"] != "ESCALATED"
        # The duplicate choice is pre-set to RT-05: the only match, or the only one on the call's event day.
        likely = before["likely_complaints"]
        same_day = [item["ref"] for item in likely if item.get("same_day")]
        assert [item["ref"] for item in likely] == ["SAMPLE-RT-05"] or same_day == ["SAMPLE-RT-05"]

        # An unsigned Case has nothing to escalate; a likely duplicate needs the choice.
        assert _ok(user.get(f"{INTAKE}/{case11}"))["escalate_signed"] is False
        assert _ok(user.post(f"{INTAKE}/{case11}/escalate", json={}), 409)["detail"]["code"] == "NOTHING_TO_ESCALATE"
        refused = _ok(user.post(f"{INTAKE}/{call02}/escalate", json={}), 422)["detail"]
        assert refused["code"] == "DUPLICATE_CHOICE_NEEDED"

        after = _ok(user.post(f"{INTAKE}/{call02}/escalate", json={"attach_to": rt05}))
        assert after["status"] == "ESCALATED" and after["escalation"] == "ATTACHED"
        assert after["complaint_ref"] == "SAMPLE-RT-05" and after["escalate_signed"] is False
        # The signed check stands: the same signed version, nothing signed again.
        assert after["signed"]["version"] == before["signed"]["version"]
        assert after["signed"]["id"] == before["signed"]["id"]
        from backend.app.db.models.workflow import OPEN_TASK_STATUSES

        # Its old "Awaiting import" task (seeded open) is completed: a trial owns the complaint in MDARIX.
        tasks = _qms_tasks(tenant_id, call02)
        assert tasks and not [status for status, _ in tasks if status in OPEN_TASK_STATUSES]
        assert ("COMPLETED", "NOT_NEEDED") in tasks
        # Twice is refused, never a second escalation.
        assert _ok(user.post(f"{INTAKE}/{call02}/escalate", json={"attach_to": rt05}), 409)["detail"]["code"] == (
            "NOTHING_TO_ESCALATE"
        )
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:case-signed-before-cleanup")
