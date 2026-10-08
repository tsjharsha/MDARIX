"""Ask passes a GenAI refusal through with its code and a user message; decisions notify the right people."""

import uuid
from datetime import datetime, timezone

import pytest

from backend.app import notifications
from backend.app.db.models.foundation import Decision, Investigation, Tenant
from backend.app.db.session import SessionLocal
from genai.provider import GenAIProvider, GenAIUnavailable
from tests.reports_seed import PASSWORD, role_client


@pytest.mark.parametrize(
    "reason, code",
    [
        ("GENAI_DISABLED_FOR_ORGANIZATION", "GENAI_DISABLED_FOR_ORGANIZATION"),
        ("GENAI_PROVIDER_UNAVAILABLE: x", "GENAI_UNAVAILABLE"),
    ],
)
def test_ask_returns_the_refusal_code_and_message(monkeypatch, reason, code):
    def refuse(self, *args, **kwargs):
        raise GenAIUnavailable(reason)

    monkeypatch.setattr(GenAIProvider, "complete", refuse)
    response = role_client("INVESTIGATOR")[0].post("/api/v1/stage3/interactions", json={"prompt": "What changed?"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "REFUSED" and body["code"] == code and body["user_message"]
    assert body["response"]["limitations"] == [body["user_message"]]
    # The Ask page reads response.refusal (HANDOFF from ai-governance).
    assert body["response"]["refusal"] == {"status": "REFUSED", "code": code, "user_message": body["user_message"]}
    assert "temporarily unavailable" not in body["user_message"]


@pytest.fixture
def decision():
    with SessionLocal() as db:
        tenant = db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").one()
        case = db.query(Investigation).filter(Investigation.tenant_id == tenant.id).first()
        now = datetime.now(timezone.utc)
        row = Decision(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            investigation_id=case.id,
            decision_identifier=f"NOTE-{uuid.uuid4().hex[:8]}",
            decision_type="INVESTIGATION_REVIEW",
            disposition="REQUIRES_REVIEW",
            rationale="Notification test",
            decision_status="REQUIRES_REVIEW",
            authorized_by_ref="someone-else",
            updated_at=now,
            decision_timestamp=now,
            created_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        yield row, case.owner_ref
        db.query(Decision).filter(Decision.id == row.id).delete(synchronize_session=False)
        db.commit()


def test_a_signature_notifies_the_case_owner(monkeypatch, decision):
    row, owner = decision
    sent = []
    monkeypatch.setattr(notifications, "notify_signoff_completed", lambda db, **kw: sent.append(kw), raising=False)
    approver = role_client("APPROVER")[0]
    signed = approver.post(
        f"/api/v1/governance/decisions/{row.id}/sign",
        json={
            "decision": "APPROVE",
            "remarks": "Reviewed",
            "password": PASSWORD,
            "object_version": row.updated_at.isoformat(),
        },
    )
    assert signed.status_code == 200, signed.text
    assert sent and sent[0]["decision_id"] == row.id and sent[0]["owner_ref"] == owner
    assert sent[0]["decision"] == "APPROVE"
    # The case's business id travels with the notification so the email can link to the case.
    assert sent[0]["investigation_business_id"] == _case_business_id(row)


def test_a_material_change_notifies_the_approvers(monkeypatch, decision):
    row, _ = decision
    sent = []
    monkeypatch.setattr(notifications, "notify_review_pending", lambda db, **kw: sent.append(kw), raising=False)
    changed = role_client("INVESTIGATOR")[0].post(
        f"/api/v1/governance/decisions/{row.id}/material-change",
        json={"change_summary": "New evidence", "expected_updated_at": row.updated_at.isoformat()},
    )
    assert changed.status_code == 200, changed.text
    assert sent and sent[0]["decision_id"] == row.id
    assert sent[0]["investigation_business_id"] == _case_business_id(row)


def _case_business_id(row) -> str:
    with SessionLocal() as db:
        return db.query(Investigation.business_id).filter(Investigation.id == row.investigation_id).one()[0]


def test_a_missing_or_failing_notification_never_blocks_the_action(monkeypatch):
    from backend.app.governance_router import _notify

    monkeypatch.delattr(notifications, "notify_review_pending", raising=False)
    assert _notify("notify_review_pending", None, decision_id=1) is False

    def broken(db, **kw):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(notifications, "notify_review_pending", broken, raising=False)
    assert _notify("notify_review_pending", None, decision_id=1) is False


@pytest.mark.parametrize("role", ["CUSTOMER_ADMIN", "Customer Admin", "PLATFORM_ADMIN"])
def test_an_administrator_cannot_sign_even_with_an_authority_naming_their_role(decision, role):
    """An administrator can write approval rules, so no rule may let them sign (separation of duties)."""
    from backend.app.db.models.foundation import ApprovalAuthority

    row, _ = decision
    now = datetime.now(timezone.utc)
    authority = ApprovalAuthority(
        id=uuid.uuid4(),
        tenant_id=row.tenant_id,
        role_name=role,
        object_type="Decision",
        decision_type="INVESTIGATION_REVIEW",
        scope={},
        authority="AUTHORIZED",
        version=f"self-made-{uuid.uuid4().hex[:6]}",
        status="ACTIVE",
        effective_from=now,
        created_at=now,
        updated_at=now,
    )
    authority_id = authority.id
    with SessionLocal() as db:
        db.add(authority)
        db.commit()
    try:
        admin = role_client(role)[0]
        body = {"decision": "APPROVE", "remarks": "Self-approved", "password": PASSWORD}
        signed = admin.post(
            f"/api/v1/governance/decisions/{row.id}/sign", json={**body, "object_version": row.updated_at.isoformat()}
        )
        assert signed.status_code == 403 and signed.json()["detail"]["code"] == "ADMINISTRATOR_CANNOT_SIGN"
        # An approver of the organization still can.
        approver = role_client("APPROVER")[0]
        approved = approver.post(
            f"/api/v1/governance/decisions/{row.id}/sign", json={**body, "object_version": row.updated_at.isoformat()}
        )
        assert approved.status_code == 200, approved.text
    finally:
        with SessionLocal() as db:
            db.query(ApprovalAuthority).filter(ApprovalAuthority.id == authority_id).delete()
            db.commit()
