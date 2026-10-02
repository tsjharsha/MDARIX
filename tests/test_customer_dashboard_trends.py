"""The customer administrator's dashboard: daily activity of their own tenant only, counts and never content."""

import uuid
from datetime import datetime, timezone

from backend.app.db.models.foundation import AuditEvent, Tenant
from backend.app.db.session import SessionLocal
from tests.test_business_permissions import _client_with_role

PATH = "/api/v1/admin/dashboard-trends"
SECRET = "CONFIDENTIAL-AUDIT-DETAIL"


def _today(series):
    return series[-1]


def _audit(tenant_id, action):
    return AuditEvent(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        action=action,
        entity_type="Test",
        details={"narrative": SECRET},
        created_at=datetime.now(timezone.utc),
    )


def test_the_dashboard_counts_only_the_administrators_own_tenant():
    admin = _client_with_role("CUSTOMER_ADMIN")
    before = admin.get(PATH)
    assert before.status_code == 200, before.text
    body = before.json()
    own = uuid.UUID(admin.get("/api/v1/session/context").json()["tenant_id"])
    with SessionLocal() as db:
        other = db.query(Tenant.id).filter(Tenant.id != own).first()[0]
        db.add_all(
            [
                _audit(own, "TEST_DASHBOARD_EVENT"),
                _audit(own, "TEST_DASHBOARD_DENIED"),
                *[_audit(other, "TEST_DASHBOARD_DENIED") for _ in range(3)],
            ]
        )
        db.commit()
    after = admin.get(PATH).json()
    assert _today(after["audit_events"]).get("events", 0) - _today(body["audit_events"]).get("events", 0) == 2
    assert _today(after["audit_events"]).get("refused", 0) - _today(body["audit_events"]).get("refused", 0) == 1
    # The administrator's own sign-in is counted today.
    assert _today(after["sign_ins"]).get("sign_ins", 0) >= 1
    assert SECRET not in admin.get(PATH).text


def test_the_window_is_one_row_per_day_and_bounded():
    admin = _client_with_role("CUSTOMER_ADMIN")
    body = admin.get(PATH, params={"days": 14}).json()
    assert body["days"] == 14 and body["scope"]["tenant_scoped"] is True
    for key in ("sign_ins", "new_users", "integration_runs", "ai_runs", "audit_events"):
        assert len(body[key]) == 14
    assert admin.get(PATH, params={"days": 5000}).json()["days"] == 90
    assert isinstance(body["investigations_by_status"], list)


def test_users_who_are_not_administrators_cannot_read_it():
    assert _client_with_role("VIEWER").get(PATH).status_code == 403
