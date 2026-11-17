"""Free-trial AI on sample data only, the per-person AI flag, the trial and feature switches, and the reserved sample
marker, against the test database. Every model request goes to a fake FreeLLMAPI (no AI service is ever called).

Owner amendment 14 Nov 2026 (AI-D14a, D2a, D19) and the per-person flag added the same day; trial-chain plan steps
N5, N7, C6 and C8.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy.orm import make_transient

from backend.app.db.models.ai_records import AiCall
from backend.app.db.models.foundation import AuditEvent, AuthUser, Complaint, Tenant
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.trial.sample_source import SAMPLE_SOURCE
from genai import governance, sample_gate, vetted
from genai import provider as provider_module
from genai.provider import REFUSAL_MESSAGES, GenAIProvider, GenAIUnavailable
from tests.conftest import authenticated_client
from tests.fake_ai_gateway import FREELLMAPI, FREELLMAPI_CEREBRAS, Reply, answer, install, register
from tests.test_free_trial import PASSWORD, _approved_trial_client, _clean_trial_workspaces  # noqa: F401

pytestmark = pytest.mark.db


def _gateway_reply() -> Reply:
    return Reply(answer("From the sample."), FREELLMAPI_CEREBRAS)


@pytest.fixture(scope="module")
def trial():
    user, approval, email = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    with SessionLocal() as db:
        bind_system(db, "test")
        person = db.query(AuthUser).filter(AuthUser.username == email).one()
        sample = (
            db.query(Complaint)
            .filter(Complaint.tenant_id == tenant_id, Complaint.source_system == SAMPLE_SOURCE)
            .order_by(Complaint.complaint_identifier)
            .all()
        )
        unedited = [row for row in sample if sample_gate.matches_catalogue(row.description)]
        assert len(unedited) >= 2, "the trial sample has unedited complaints"
        return {
            "client": user,
            "tenant_id": tenant_id,
            "user_id": person.id,
            "ai_access": person.ai_access,
            "sample": [row.id for row in unedited[:2]],
        }


@pytest.fixture
def chain_on(monkeypatch, trial):
    """The trial chain switched on with one fake gateway; the organization and the summaries feature on."""
    provider_module._COOLDOWN_UNTIL.clear()
    monkeypatch.setenv("MDARIX_GENAI_SHARED_REST", "false")
    monkeypatch.setenv("MDARIX_GENAI_PROVIDER", "controlled")
    monkeypatch.setenv("MDARIX_AI_TRIAL_CHAIN", "freellmapi")
    monkeypatch.setenv("MDARIX_GENAI_FREELLMAPI_API_KEY", "test-key")
    monkeypatch.delenv("MDARIX_GENAI_FREELLMAPI_BASE_URL", raising=False)
    monkeypatch.setenv("MDARIX_AI_FEATURES", "summaries")
    monkeypatch.setattr(vetted, "load", lambda path=None: register())
    sent = install(monkeypatch, default=_gateway_reply)["sent"]
    _set_tenant(trial["tenant_id"], ai_processing_allowed=True, ai_features={"summaries": True})
    _set_user(trial["user_id"], "ACTIVE")
    yield sent
    _set_tenant(trial["tenant_id"], ai_processing_allowed=False, ai_features={})
    _set_user(trial["user_id"], "ACTIVE")


def _set_tenant(tenant_id, **values):
    with SessionLocal() as db:
        bind_system(db, "test")
        db.query(Tenant).filter(Tenant.id == tenant_id).update(values)
        db.commit()


def _set_user(user_id, value):
    with SessionLocal() as db:
        bind_system(db, "test")
        db.query(AuthUser).filter(AuthUser.id == user_id).update({"ai_access": value})
        db.commit()


def _calls(tenant_id) -> int:
    with SessionLocal() as db:
        bind_system(db, "test")
        return db.query(AiCall).filter(AiCall.tenant_id == tenant_id).count()


def _copy(complaint_id, **changes) -> uuid.UUID:
    """A copy of a sample complaint with some fields changed (a trial's own record, or a forged or edited one)."""
    with SessionLocal() as db:
        bind_system(db, "test")
        row = db.get(Complaint, complaint_id)
        db.expunge(row)
        make_transient(row)
        row.id = uuid.uuid4()
        row.business_id = None
        row.complaint_identifier = f"COPY-{uuid.uuid4().hex[:8]}"
        row.source_identifier = row.complaint_identifier
        for key, value in changes.items():
            setattr(row, key, value)
        db.add(row)
        db.commit()
        return row.id


def _summarize(trial, ids, *, evidence=None, user_text=None, user_id="default"):
    records = [{"table": "complaints", "id": str(item), "evidence_id": f"C{index}"} for index, item in enumerate(ids)]
    evidence = evidence if evidence is not None else [{"id": item["evidence_id"], "text": "x"} for item in records]
    with governance.tenant_scope(trial["tenant_id"], trial["user_id"] if user_id == "default" else user_id):
        return GenAIProvider().complete(
            "Summarize these complaints.",
            {},
            feature="summaries",
            records=records,
            evidence=evidence,
            user_text=user_text,
        )


def _refused(trial, sent, ids, code="GENAI_TRIAL_SAMPLE_ONLY", **kwargs) -> GenAIUnavailable:
    before = _calls(trial["tenant_id"])
    with pytest.raises(GenAIUnavailable) as refused:
        _summarize(trial, ids, **kwargs)
    assert refused.value.code == code
    assert sent == [], "a refused request reaches no AI service"
    assert _calls(trial["tenant_id"]) == before, "a refused request writes no call record"
    return refused.value


# ----------------------------------------------------------------------------------------- the sample gate (N5)


def test_unedited_sample_records_reach_the_trial_chain_and_the_call_is_recorded(trial, chain_on):
    result = _summarize(trial, trial["sample"])
    assert chain_on == [FREELLMAPI]
    assert result.output["answer"] == "From the sample."
    with SessionLocal() as db:
        bind_system(db, "test")
        row = db.get(AiCall, uuid.UUID(result.call_id))
        assert (row.provider, row.upstream_provider, row.upstream_model) == ("freellmapi", "cerebras", "gpt-oss-120b")
        assert (row.organisation_type, row.chain, row.outcome, row.feature) == (
            "TRIAL",
            "trial",
            "ANSWERED",
            "summaries",
        )
        assert row.user_ref == str(trial["user_id"]) and row.output_text == "From the sample."
        assert len(row.content_sha256) == 64 and "Summarize" not in json.dumps(row.records)
        assert {item["id"] for item in row.records} == {str(item) for item in trial["sample"]}


def test_a_non_sample_record_is_refused_with_ai_available_on_paid_plans(trial, chain_on):
    own = _copy(trial["sample"][0], source_system="TRIAL_UPLOAD")
    refused = _refused(trial, chain_on, [own])
    assert refused.user_message.startswith("AI available on paid plans")
    assert refused.user_message == REFUSAL_MESSAGES["GENAI_TRIAL_SAMPLE_ONLY"]


def test_one_non_sample_record_among_sample_ones_is_refused(trial, chain_on):
    own = _copy(trial["sample"][0], source_system="TRIAL_UPLOAD")
    _refused(trial, chain_on, [*trial["sample"], own])


def test_an_edited_sample_record_no_longer_counts_as_sample(trial, chain_on):
    edited = _copy(trial["sample"][0], description="Mrs Real Person fell at home in Pune when the alarm failed.")
    _refused(trial, chain_on, [edited])


def test_an_evidence_block_that_is_not_a_listed_record_is_refused(trial, chain_on):
    _refused(trial, chain_on, trial["sample"], evidence=[{"id": "C0", "text": "x"}, {"id": "UNLISTED", "text": "y"}])


def test_a_request_listing_no_records_is_refused(trial, chain_on):
    _refused(trial, chain_on, [], evidence=[])


def test_another_organizations_sample_record_is_refused(trial, chain_on):
    with SessionLocal() as db:
        bind_system(db, "test")
        other = db.query(Complaint.id).filter(Complaint.tenant_id != trial["tenant_id"]).first()
    assert other is not None
    _refused(trial, chain_on, [other.id])


def test_typed_text_over_300_characters_is_refused(trial, chain_on):
    _refused(trial, chain_on, trial["sample"], user_text="x" * 301)
    assert _summarize(trial, trial["sample"], user_text="What do these complaints share?").output["answer"]


# ------------------------------------------------------------------------------- per-person AI flag (owner, 14 Nov)


def test_a_new_trial_person_is_active_by_default(trial):
    assert trial["ai_access"] == "ACTIVE"


def test_an_inactive_person_makes_zero_calls_even_with_the_organization_on(trial, chain_on):
    _set_user(trial["user_id"], "INACTIVE")
    refused = _refused(trial, chain_on, trial["sample"], code="GENAI_USER_AI_INACTIVE")
    assert refused.user_message.startswith("AI is not enabled for your account")


def test_a_trial_request_without_a_person_is_refused(trial, chain_on):
    _refused(trial, chain_on, trial["sample"], code="GENAI_USER_AI_INACTIVE", user_id=None)


def test_with_the_organization_off_no_person_has_ai(trial, chain_on):
    _set_tenant(trial["tenant_id"], ai_processing_allowed=False)
    _refused(trial, chain_on, trial["sample"], code="GENAI_DISABLED_FOR_ORGANIZATION")


def test_the_feature_switched_off_for_the_organization_means_zero_calls(trial, chain_on):
    _set_tenant(trial["tenant_id"], ai_features={})
    _refused(trial, chain_on, trial["sample"], code="GENAI_FEATURE_OFF_FOR_ORGANIZATION")


def test_an_empty_trial_chain_means_zero_calls_for_a_trial(trial, chain_on, monkeypatch):
    monkeypatch.setenv("MDARIX_AI_TRIAL_CHAIN", "")
    monkeypatch.setenv("MDARIX_GENAI_PROVIDER", "groq")
    monkeypatch.setenv("MDARIX_GENAI_API_KEY", "dev-key")
    _refused(trial, chain_on, trial["sample"], code="GENAI_OFF_FOR_FREE_TRIAL")


TRIALS = "/api/v1/platform-admin/trial-organizations"


def _audits(tenant_id, action):
    with SessionLocal() as db:
        bind_system(db, "test")
        return (
            db.query(AuditEvent)
            .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.action == action)
            .order_by(AuditEvent.created_at.desc())
            .all()
        )


def test_only_a_platform_administrator_sets_a_users_ai_switch(trial):
    url = f"{TRIALS}/{trial['tenant_id']}/users/{trial['user_id']}/ai-access"
    bulk = f"{TRIALS}/{trial['tenant_id']}/ai-access"
    body = {"active": False, "reason": "Trial user asked for no AI"}
    # The trial's own administrator is refused, on the single and the bulk route.
    assert trial["client"].put(url, json=body).status_code == 403
    assert trial["client"].put(bulk, json=body).status_code == 403
    admin = authenticated_client()
    refusals = len(_audits(trial["tenant_id"], "TRIAL_ACTION_REFUSED"))
    short = admin.put(url, json={"active": False, "reason": "No AI pls"})  # 9 characters: at least 10
    assert short.status_code == 422 and short.json()["detail"]["code"] == "REASON_TOO_SHORT"
    assert len(_audits(trial["tenant_id"], "TRIAL_ACTION_REFUSED")) == refusals + 1
    changed = admin.put(url, json=body)
    try:
        assert changed.status_code == 200, changed.text
        assert changed.json() == {"user_id": str(trial["user_id"]), "active": False, "changed": True}
        event = next(
            e for e in _audits(trial["tenant_id"], "TRIAL_USER_AI_ACCESS_CHANGED") if e.entity_id == trial["user_id"]
        )
        assert event.old_values == {"ai_access": True} and event.new_values == {"ai_access": False}
        assert event.reason == body["reason"] and event.actor_ref and "bulk" not in event.details
        assert admin.put(url, json=body).json()["changed"] is False  # already Inactive: nothing audited
        listing = admin.get(f"{TRIALS}/{trial['tenant_id']}/users/ai-access").json()
        assert listing["organization_on"] is False and "trial_chain_on" in listing
        mine = next(item for item in listing["items"] if item["user_id"] == str(trial["user_id"]))
        assert mine["active"] is False
        back = admin.put(bulk, json={"active": True, "reason": "Back on for the whole trial"})
        assert back.status_code == 200 and back.json()["changed"] >= 1 and back.json()["active"] is True
        summary = _audits(trial["tenant_id"], "TRIAL_AI_ACCESS_BULK_CHANGED")[0]
        assert summary.details == {"count": back.json()["changed"], "value": True}
        assert _audits(trial["tenant_id"], "TRIAL_USER_AI_ACCESS_CHANGED")[0].details["bulk"] is True
    finally:
        _set_user(trial["user_id"], "ACTIVE")


def test_the_platform_admin_sees_a_trials_ai_use_chain_and_switch_changes(trial, chain_on):
    url = f"{TRIALS}/{trial['tenant_id']}/ai-metrics"
    assert trial["client"].get(url).status_code == 403
    admin = authenticated_client()
    before = admin.get(url).json()
    _summarize(trial, trial["sample"])
    switched = admin.put(
        f"{TRIALS}/{trial['tenant_id']}/users/{trial['user_id']}/ai-access",
        json={"active": False, "reason": "Metrics test switch change"},
    )
    try:
        assert switched.status_code == 200
        metrics = admin.get(url)
        assert metrics.status_code == 200, metrics.text
        body = metrics.json()
        assert body["organization_on"] is True
        assert body["calls"]["total"] == before["calls"]["total"] + 1
        assert body["calls"]["by_feature"]["summaries"] >= 1 and body["calls"]["by_outcome"]["ANSWERED"] >= 1
        assert body["usage"]["limit"] == governance.trial_monthly_budget(None)
        assert body["chain"] == [{"position": 1, "name": "freellmapi", "state": "READY", "resting_until": None}]
        latest = body["switch_events"][0]
        assert latest["action"] == "TRIAL_USER_AI_ACCESS_CHANGED" and latest["reason"] == "Metrics test switch change"
        assert latest["new_values"] == {"ai_access": False} and latest["actor"]
        # The person the switch changed, by name (the trial's AI panel: "<name>'s AI set Inactive").
        with SessionLocal() as db:
            bind_system(db, "test")
            assert latest["details"]["user_name"] == db.get(AuthUser, trial["user_id"]).display_name
        assert "Summarize" not in metrics.text, "metrics carry no prompt or record text"
    finally:
        _set_user(trial["user_id"], "ACTIVE")


def test_a_user_of_another_organization_is_refused_and_audited(trial):
    admin = authenticated_client()
    with SessionLocal() as db:
        bind_system(db, "test")
        stranger = db.query(AuthUser).filter(AuthUser.tenant_id != trial["tenant_id"]).first()
    refusals = len(_audits(trial["tenant_id"], "TRIAL_ACTION_REFUSED"))
    response = admin.put(
        f"{TRIALS}/{trial['tenant_id']}/users/{stranger.id}/ai-access",
        json={"active": False, "reason": "Not a user of this trial"},
    )
    assert response.status_code == 404 and response.json()["detail"]["code"] == "USER_NOT_FOUND"
    assert len(_audits(trial["tenant_id"], "TRIAL_ACTION_REFUSED")) == refusals + 1


def test_the_user_switch_is_not_offered_for_a_paid_organization():
    admin = authenticated_client()
    with SessionLocal() as db:
        bind_system(db, "test")
        tenant = db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first()
        person = db.query(AuthUser).filter(AuthUser.tenant_id == tenant.id).first()
    response = admin.put(
        f"{TRIALS}/{tenant.id}/users/{person.id}/ai-access",
        json={"active": False, "reason": "Not for paid organizations"},
    )
    assert response.status_code == 409 and response.json()["detail"]["code"] == "AI_USER_FLAG_TRIAL_ONLY"
    assert _audits(tenant.id, "TRIAL_ACTION_REFUSED")[0].details["code"] == "AI_USER_FLAG_TRIAL_ONLY"
    # The old route names are gone: one name only.
    old = admin.put(
        f"/api/v1/platform-admin/tenants/{tenant.id}/users/{person.id}/ai-access",
        json={"ai_access": "INACTIVE", "reason": "Not for paid organizations"},
    )
    assert old.status_code in (404, 405)


# ----------------------------------------------------------------------------------- trial and feature switch (C6)


def test_a_trial_admin_switches_ai_on_only_with_the_trial_acknowledgement(trial, monkeypatch):
    client = trial["client"]
    body = {"ai_processing_allowed": True, "acknowledgement": True, "reason": "Try AI on the sample data"}
    monkeypatch.delenv("MDARIX_AI_TRIAL_CHAIN", raising=False)
    refused = client.put("/api/v1/admin/ai-settings", json=body)
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "AI_OFF_FOR_FREE_TRIALS"
    monkeypatch.setenv("MDARIX_AI_TRIAL_CHAIN", "freellmapi")
    missing = client.put("/api/v1/admin/ai-settings", json=body)
    assert missing.status_code == 422 and missing.json()["detail"]["code"] == "AI_TRIAL_ACKNOWLEDGEMENT_REQUIRED"
    unsigned = client.put("/api/v1/admin/ai-settings", json={**body, "trial_acknowledgement": True})
    assert unsigned.status_code == 403  # switching on needs the password and authenticator code (C6)
    monkeypatch.setattr("backend.app.governance_router.verify_signing_credentials", lambda *args, **kwargs: None)
    try:
        switched = client.put("/api/v1/admin/ai-settings", json={**body, "trial_acknowledgement": True})
        assert switched.status_code == 200, switched.text
        assert switched.json()["ai_processing_allowed"] is True and switched.json()["trial_chain_on"] is True
        with SessionLocal() as db:
            bind_system(db, "test")
            event = (
                db.query(AuditEvent)
                .filter(
                    AuditEvent.tenant_id == trial["tenant_id"], AuditEvent.action == "AI_PROCESSING_SETTING_CHANGED"
                )
                .order_by(AuditEvent.created_at.desc())
                .first()
            )
            assert "sample data only" in event.details["trial_acknowledgement"]
        # The Platform Administrator's Trial Organizations page follows the real state (TO-1, demo step 2).
        admin, tenant = authenticated_client(), str(trial["tenant_id"])
        with SessionLocal() as db:
            bind_system(db, "test")
            owner = db.get(AuthUser, trial["user_id"]).display_name
        access = admin.get(f"{TRIALS}/{tenant}/users/ai-access").json()
        assert access["organization_on"] is True and access["organization_on_by"] == owner
        assert access["organization_on_at"] == event.created_at.isoformat()
        detail = admin.get(f"{TRIALS}/{tenant}").json()["ai"]
        assert detail["enabled"] is True and detail["people_active"] >= 1
        assert detail["line"].startswith("AI is on for this trial") and "off" not in detail["line"]
        row = next(item for item in admin.get(TRIALS, params={"q": tenant_key(tenant)}).json()["items"])
        assert row["ai_on"] is True and row["ai_people_active"] >= 1
    finally:
        _set_tenant(trial["tenant_id"], ai_processing_allowed=False)
    admin = authenticated_client()
    off = admin.get(f"{TRIALS}/{trial['tenant_id']}/users/ai-access").json()
    assert off["organization_on"] is False and off["organization_on_by"] is None and off["organization_on_at"] is None
    detail = admin.get(f"{TRIALS}/{trial['tenant_id']}").json()["ai"]
    assert detail == {"enabled": False, "people_active": 0, "line": "AI is not switched on for this trial."}
    row = admin.get(TRIALS, params={"q": tenant_key(str(trial["tenant_id"]))}).json()["items"][0]
    assert row["ai_on"] is False and row["ai_people_active"] == 0


def tenant_key(tenant_id: str) -> str:
    with SessionLocal() as db:
        bind_system(db, "test")
        return db.get(Tenant, uuid.UUID(tenant_id)).tenant_key


def test_a_feature_is_turned_on_only_when_allowed_and_after_re_authentication(trial, monkeypatch):
    client = trial["client"]
    body = {"ai_processing_allowed": False, "reason": "Turn on summaries", "features": {"summaries": True}}
    monkeypatch.setenv("MDARIX_AI_FEATURES", "")
    blocked = client.put("/api/v1/admin/ai-settings", json=body)
    assert blocked.status_code == 409 and blocked.json()["detail"]["code"] == "AI_FEATURE_NOT_ALLOWED"
    unknown = client.put("/api/v1/admin/ai-settings", json={**body, "features": {"root_cause": True}})
    assert unknown.status_code == 422
    monkeypatch.setenv("MDARIX_AI_FEATURES", "summaries")
    no_password = client.put("/api/v1/admin/ai-settings", json=body)
    assert no_password.status_code == 403
    assert _features(trial["tenant_id"]) == {}
    # With the signature-grade check passed (its own tests cover password and code), the switch is saved and audited.
    monkeypatch.setattr(
        "backend.app.governance_router.verify_signing_credentials", lambda *args, **kwargs: None, raising=True
    )
    try:
        saved = client.put("/api/v1/admin/ai-settings", json={**body, "password": PASSWORD, "mfa_code": "000000"})
        assert saved.status_code == 200, saved.text
        assert next(item for item in saved.json()["features"] if item["key"] == "summaries")["enabled"] is True
        assert _features(trial["tenant_id"]) == {"summaries": True}
        with SessionLocal() as db:
            bind_system(db, "test")
            event = (
                db.query(AuditEvent)
                .filter(AuditEvent.tenant_id == trial["tenant_id"], AuditEvent.action == "AI_FEATURE_SETTING_CHANGED")
                .order_by(AuditEvent.created_at.desc())
                .first()
            )
            assert event.details["feature"] == "summaries" and event.details["risk"] == "LOW"
            assert event.details["intended_use"] and event.new_values == {"enabled": True}
        # Turning a feature off needs no re-authentication.
        monkeypatch.undo()
        off = client.put("/api/v1/admin/ai-settings", json={**body, "features": {"summaries": False}})
        assert off.status_code == 200 and _features(trial["tenant_id"]) == {"summaries": False}
    finally:
        _set_tenant(trial["tenant_id"], ai_features={})


def _features(tenant_id) -> dict:
    with SessionLocal() as db:
        bind_system(db, "test")
        return dict(db.get(Tenant, tenant_id).ai_features or {})


# ------------------------------------------------------------------------------------- the reserved marker (N7)


@pytest.mark.parametrize("spelling", ["MDARIX_SAMPLE", " mdarix_sample "])
def test_no_request_can_write_the_sample_marker(spelling):
    admin = authenticated_client()
    run = admin.post(
        f"/api/v1/admin/configuration/connectors/{uuid.uuid4()}/execute",
        json={"records": [], "source_system": spelling},
    )
    assert run.status_code == 422 and "reserved" in run.text
    mapping = admin.post(
        "/api/v1/admin/configuration/mappings",
        json={"code": f"M-{uuid.uuid4().hex[:6]}", "source_system": spelling, "target_entity": "complaints"},
    )
    assert mapping.status_code == 422 and "reserved" in mapping.text
    connector = admin.post(
        "/api/v1/admin/configuration/connectors",
        json={
            "code": f"C-{uuid.uuid4().hex[:6]}",
            "connector_type": "REST",
            "configuration": {"source_object": spelling},
        },
    )
    assert connector.status_code == 422 and "reserved" in connector.text


def test_the_connector_gateway_refuses_the_sample_marker():
    from integration.gateway import CONNECTOR_STATES, ConnectorRun

    run = ConnectorRun("t", "c", "r", state=sorted(CONNECTOR_STATES)[0])
    with pytest.raises(ValueError, match="reserved"):
        run.ingest([], source_system="MDARIX_SAMPLE", required_fields=set())


def test_the_ai_status_of_a_trial_follows_the_chain_the_organization_and_the_person(trial, chain_on):
    status = trial["client"].get("/api/v1/ai/status").json()
    assert status["trial"] is True and status["enabled"] is True and status["sample_data_only"] is True
    assert status["reason_code"] is None and "sample data only" in status["message"]
    assert status["budget"]["limit"] == governance.DEFAULT_TRIAL_MONTHLY_TOKENS
    _set_user(trial["user_id"], "INACTIVE")
    inactive = trial["client"].get("/api/v1/ai/status").json()
    assert inactive["enabled"] is False and inactive["reason_code"] == "USER_AI_INACTIVE"
    assert inactive["message"].startswith("AI is not enabled for your account")


# ----------------------------------------------------------- every text column the prompts send (review S1)

TYPED = "Ann Roy, 12 Hill Road, Pune 411001, phone 98200 00000"


def _sample_row(tenant_id, table):
    model = sample_gate._model_for(table)
    with SessionLocal() as db:
        bind_system(db, "test")
        row = (
            db.query(model)
            .filter(model.tenant_id == tenant_id, model.source_system == SAMPLE_SOURCE)
            .order_by(model.id)
            .all()
        )
        return next(
            item.id
            for item in row
            if sample_gate._record_problem(db, tenant_id, {"table": table, "id": item.id}) is None
        )


@pytest.mark.parametrize(
    "table, column",
    [
        # Sent by the complaint explanation, the signal summary and the IMDRF code suggestions.
        ("complaints", "description"),
        ("complaints", "status"),
        ("complaints", "complaint_type"),
        ("complaints", "problem_code"),
        ("complaints", "severity"),
        ("complaints", "country"),
        ("complaints", "other_lots"),
        # Sent by case analysis and drafting.
        ("investigations", "investigation_question"),
        ("changes", "description"),
        # Sent by Ask and case analysis: the title and type of the record, the text of its search chunks.
        ("evidence", "title"),
        ("evidence", "evidence_type"),
        ("evidence", "content"),
        ("evidence_chunks", "text_content"),
    ],
)
def test_real_text_typed_into_any_sent_column_of_a_sample_record_is_refused(trial, table, column):
    from backend.app.db.models.evidence_intelligence import EvidenceChunk

    record_table = "evidence" if table == "evidence_chunks" else table
    record_id = _sample_row(trial["tenant_id"], record_table)
    model = EvidenceChunk if table == "evidence_chunks" else sample_gate._model_for(table)
    length = getattr(model.__table__.columns[column].type, "length", None) or len(TYPED)
    typed = [TYPED] if column == "other_lots" else TYPED[:length]
    key = model.evidence_id if table == "evidence_chunks" else model.id
    with SessionLocal() as db:
        bind_system(db, "test")
        before = {row.id: getattr(row, column) for row in db.query(model).filter(key == record_id)}
        assert before, f"the sample has a {table} row to edit"
        db.query(model).filter(key == record_id).update({column: typed}, synchronize_session=False)
        db.commit()
    try:
        found = sample_gate.problem(
            str(trial["tenant_id"]),
            records=[{"table": record_table, "id": str(record_id)}],
            evidence=[],
            user_text=None,
        )
        assert found and f"{table}.{column}" in found
    finally:
        with SessionLocal() as db:
            bind_system(db, "test")
            for row_id, value in before.items():
                db.query(model).filter(model.id == row_id).update({column: value}, synchronize_session=False)
            db.commit()


def test_unedited_sample_evidence_investigations_and_changes_pass_the_gate(trial):
    """The (Sample) title suffix, server-set codes such as MEDIUM and the chunk text of sample evidence all pass."""
    for table in ("evidence", "investigations", "changes"):
        record_id = _sample_row(trial["tenant_id"], table)
        assert (
            sample_gate.problem(
                str(trial["tenant_id"]), records=[{"table": table, "id": str(record_id)}], evidence=[], user_text=None
            )
            is None
        )


def _all_sample_ids(tenant_id, table: str) -> list:
    model = sample_gate._model_for(table)
    with SessionLocal() as db:
        bind_system(db, "test")
        query = db.query(model.id).filter(model.tenant_id == tenant_id, model.source_system == SAMPLE_SOURCE)
        if table == "complaints":  # not the edited copies other tests here make (_copy)
            query = query.filter(~model.complaint_identifier.like("COPY-%"))
        return [row_id for (row_id,) in query]


@pytest.mark.parametrize("table", ["complaints", "investigations", "evidence", "changes"])
def test_every_unedited_sample_record_passes_the_gate(trial, table):
    """Review G2: every sample record, including the bulk complaints whose description the loader builds from parts
    ("Customer reported {symptom} on {revision}, lot {lot}."), passes; 28 of 44 complaints were refused before."""
    ids = _all_sample_ids(trial["tenant_id"], table)
    if table == "complaints":
        assert len(ids) == 44, "the sample story has 44 complaints"
    assert ids
    refused = {}
    for record_id in ids:
        found = sample_gate.problem(
            str(trial["tenant_id"]), records=[{"table": table, "id": str(record_id)}], evidence=[], user_text=None
        )
        if found:
            refused[str(record_id)] = found
    assert refused == {}


def test_a_built_sentence_with_real_text_typed_into_a_part_is_refused():
    """The f-string's shape alone is not enough: each part filled in must be sample text or an identifier."""
    built = (
        "Customer reported pressure alarm during infusion on Rev B, lot SAMPLE-ORBIT-300-LOT-003. "
        "Device returned for evaluation; no patient injury reported."
    )
    assert sample_gate.matches_catalogue(built)
    assert not sample_gate.matches_catalogue(built.replace("pressure alarm during infusion", "Asha Rao, 98450 12345"))
    assert not sample_gate.matches_catalogue(built.replace("SAMPLE-ORBIT-300-LOT-003", "lot of a real patient"))
    assert not sample_gate.matches_catalogue(built + " Patient called back at home.")


def test_the_follow_up_lot_list_passes_only_while_every_lot_is_sample_text():
    """W1d's synthetic follow-up joins its lots with "; ": the list passes, a real-text item in it does not."""
    from backend.app.trial import sample_follow_up

    text = sample_follow_up.content_text()
    assert sample_gate.matches_catalogue(text)
    assert not sample_gate.matches_catalogue(text.replace("; FU-LOT-102", "; Asha Rao, 98450 12345; FU-LOT-102"))
    assert not sample_gate.matches_catalogue(text.replace("FU-LOT-103 built day", "Patient called back at home built"))


@pytest.fixture
def case_features_on(monkeypatch, trial, chain_on):
    """Ask and case analysis switched on for the trial (on top of chain_on)."""
    monkeypatch.setenv("MDARIX_AI_FEATURES", "summaries,ask,case_analysis")
    _set_tenant(trial["tenant_id"], ai_processing_allowed=True, ai_features={"ask": True, "case_analysis": True})
    return chain_on


def _sample_case(tenant_id):
    from backend.app.db.models.foundation import Investigation

    with SessionLocal() as db:
        bind_system(db, "test")
        return (
            db.query(Investigation.id)
            .filter(Investigation.tenant_id == tenant_id, Investigation.investigation_identifier == "SAMPLE-INV-001")
            .scalar()
        )


def test_ask_inside_the_sample_case_reaches_the_trial_chain(trial, case_features_on):
    """Review G3: Ask in a case listed no records, so a trial was always refused ("AI available on paid plans")."""
    response = trial["client"].post(
        "/api/v1/stage3/interactions",
        json={
            "prompt": "What changed before the pressure alarms rose?",
            "investigation_id": str(_sample_case(trial["tenant_id"])),
        },
    )
    assert response.status_code == 200, response.text
    assert case_features_on == [FREELLMAPI], response.json()


def test_the_case_advisory_lists_the_case_records_and_reaches_the_trial_chain(trial, case_features_on):
    from genai.grounding import advisory, build_authorized_context, context_records

    with SessionLocal() as db:
        bind_system(db, "test")
        grounded = build_authorized_context(
            db, tenant_id=trial["tenant_id"], investigation_id=_sample_case(trial["tenant_id"])
        )
    tables = {item["table"] for item in context_records(grounded)}
    assert {"investigations", "evidence"} <= tables
    with governance.tenant_scope(trial["tenant_id"], trial["user_id"]):
        result = advisory(workflow="INVESTIGATION_SYNTHESIS", deterministic_result={}, grounded_context=grounded)
    assert result.get("code") != "GENAI_TRIAL_SAMPLE_ONLY", result
    assert case_features_on == [FREELLMAPI]


def test_the_trial_settings_screen_shows_the_allowance_that_is_enforced(trial):
    """Review G9: the AI settings showed the paid default (2,000,000 tokens) while 200,000 was enforced."""
    _set_tenant(trial["tenant_id"], ai_monthly_token_budget=None)
    shown = trial["client"].get("/api/v1/admin/ai-settings")
    assert shown.status_code == 200, shown.text
    assert shown.json()["monthly_token_budget"] == governance.trial_monthly_budget(None) == 200_000
    with SessionLocal() as db:
        bind_system(db, "test")
        assert governance.usage(db, trial["tenant_id"])["monthly_token_budget"] == 200_000
