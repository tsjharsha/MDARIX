"""WHIF front-end review 2, section 3: the backend fields the demo screens need. The tenant and the person always come
from the signed-in session; a trial's owner reads only their own trial."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from backend.app.db.models.foundation import AIExecution, AuthUser
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.conftest import authenticated_client
from tests.test_free_trial import _approved_trial_client

pytestmark = pytest.mark.db
TRIALS = "/api/v1/platform-admin/trial-organizations"


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, email = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    with SessionLocal() as db:
        bind_system(db, "test")
        person = db.query(AuthUser).filter(AuthUser.username == email).one()
        found = {"client": user, "tenant_id": tenant_id, "user_id": person.id, "name": person.display_name}
    yield found
    with SessionLocal() as db:
        purge_trial(db, tenant_id, "test:whif-review-fields-cleanup")


def test_the_ai_switch_says_whether_it_can_be_changed_now(trial, monkeypatch):  # F1
    monkeypatch.delenv("MDARIX_AI_TRIAL_CHAIN", raising=False)
    shown = trial["client"].get("/api/v1/admin/ai-settings")
    assert shown.status_code == 200, shown.text
    assert shown.json()["can_change"] is False and "free trial" in shown.json()["can_change_reason"]
    monkeypatch.setenv("MDARIX_AI_TRIAL_CHAIN", "freellmapi")
    shown = trial["client"].get("/api/v1/admin/ai-settings").json()
    assert shown["can_change"] is True and shown["can_change_reason"] is None


def test_the_trial_ai_people_list_marks_the_sample_author_and_who_gets_ai_now(trial, monkeypatch):  # F-T2
    from backend.app.trial.sample_decision import _author_email

    monkeypatch.setenv("MDARIX_AI_TRIAL_CHAIN", "freellmapi")
    items = authenticated_client().get(f"{TRIALS}/{trial['tenant_id']}/users/ai-access").json()["items"]
    owner = next(item for item in items if item["user_id"] == str(trial["user_id"]))
    # The organization's switch is off: nobody gets AI, whatever their own switch says.
    assert owner["active"] is True and owner["effective"] is False and owner["system_user"] is False
    with SessionLocal() as db:
        bind_system(db, "test")
        author = db.query(AuthUser).filter(AuthUser.username == _author_email(trial["tenant_id"])).one_or_none()
    if author is not None:
        assert next(item for item in items if item["user_id"] == str(author.id))["system_user"] is True


def test_a_sample_answer_is_not_counted_as_an_ai_run(trial):  # F-X2
    admin = authenticated_client()
    before = admin.get("/api/v1/platform-admin/console/ai-activity").json()
    with SessionLocal() as db:
        bind_system(db, "test")
        db.add(
            AIExecution(
                id=uuid.uuid4(),
                tenant_id=trial["tenant_id"],
                requestor_ref="sample",
                provider="sample-recorded",
                model_name="pre-recorded sample answer",
                model_version="sample",
                prompt_template_version="sample",
                orchestration_version="sample",
                context_refs={},
                evidence_refs={},
                structured_input={},
                structured_output={"summary": "Pre-recorded"},
                validation_status="COMPLETED",
                execution_timestamp=datetime.now(timezone.utc),
            )
        )
        db.commit()
    after = admin.get("/api/v1/platform-admin/console/ai-activity").json()
    assert after["total"] == before["total"]
    assert "sample-recorded" not in {row["provider"] for row in after["by_model"]}


def test_the_trial_owner_reads_the_trials_audit_trail_with_names_labels_and_the_chain(trial):  # F-E1
    client = trial["client"]
    trail = client.get("/api/v1/admin/audit-history")
    assert trail.status_code == 200, trail.text
    rows = trail.json()
    assert rows and all(row["tenant_id"] == str(trial["tenant_id"]) for row in rows)
    mine = [row for row in rows if row["actor_ref"] == str(trial["user_id"])]
    assert mine and mine[0]["actor_name"] == trial["name"]
    assert all(row["action_label"] and "_" not in row["action_label"] for row in rows)
    chain = client.get("/api/v1/admin/audit-chain")
    assert chain.status_code == 200, chain.text


# A trial colleague is refused both: test_authorization_matrix.py (TRIAL_OWNER_ADMIN_ROUTES).


def test_the_signed_records_list_opens_on_the_latest_signatures(trial):  # F-E2, F-E6
    listed = trial["client"].get("/api/v1/governance/signed-records")
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    stamps = [item["signed_at"] for item in items]
    assert stamps == sorted(stamps, reverse=True)
    for item in items:
        assert {"signer_name", "meaning", "signed_at", "mfa_verified", "training", "fingerprint_ok"} <= set(item)
        assert all({"code", "version", "current"} <= set(doc) for doc in item["training"])
    if items:  # the sample's signed decisions verify against what was signed
        assert all(item["fingerprint_ok"] is True for item in items)
