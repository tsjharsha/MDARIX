"""Round 2 of the WHIF demo work: the backend parts of the review's front-end gaps. The tenant and the person always
come from the signed-in session."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from backend.app.db.models.foundation import AuditEvent
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.test_free_trial import _approved_trial_client

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    yield {"client": user, "tenant_id": tenant_id}
    with SessionLocal() as db:
        purge_trial(db, tenant_id, "test:round2-ui-cleanup")


def test_the_organization_trail_hides_system_events_unless_asked(trial):  # G-03
    ids = {}
    with SessionLocal() as db:
        bind_system(db, "test")
        for action in ("REQUEST_MUTATION_COMPLETED", "PRODUCT360_TEMPORAL_RETRIEVAL", "DECISION_SIGNED"):
            ids[action] = uuid.uuid4()
            db.add(
                AuditEvent(
                    id=ids[action],
                    tenant_id=trial["tenant_id"],
                    actor_ref="test",
                    action=action,
                    entity_type="Test",
                    created_at=datetime.now(timezone.utc),
                )
            )
        db.commit()
    client = trial["client"]
    shown = {row["id"] for row in client.get("/api/v1/admin/audit-history").json()}
    assert str(ids["DECISION_SIGNED"]) in shown
    assert str(ids["REQUEST_MUTATION_COMPLETED"]) not in shown
    assert str(ids["PRODUCT360_TEMPORAL_RETRIEVAL"]) not in shown
    every = {row["id"] for row in client.get("/api/v1/admin/audit-history?include_system=true").json()}
    assert {str(value) for value in ids.values()} <= every
