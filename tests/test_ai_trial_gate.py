"""Free-trial AI on sample data only, the per-person AI flag, the trial and feature switches, and the reserved sample
marker, against the test database. Every model request goes to a fake FreeLLMAPI (no AI service is ever called).

Owner amendment 14 Nov 2026 (AI-D14a, D2a, D19) and the per-person flag added the same day; trial-chain plan steps
N5, N7, C6 and C8.
"""

from __future__ import annotations

import io
import json
import uuid
from datetime import date

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
from tests.test_free_trial import PASSWORD, _approved_trial_client, _clean_trial_workspaces  # noqa: F401

pytestmark = pytest.mark.db

FREELLMAPI = "http://127.0.0.1:3011/v1/chat/completions"
REGISTER = {
    "version": 1,
    "warn_after_days": 183,
    "refuse_after_days": 365,
    "providers": [
        {"provider": "freellmapi", "kind": "gateway", "chain": "trial", "upstream_from": "header:x-routed-via"},
        {
            "provider": "cerebras",
            "kind": "upstream",
            "chain": "trial",
            "terms_link": "https://example.invalid/terms",
            "date_checked": date.today().isoformat(),
            "region": "US",
            "commercial_use": True,
            "trains_on_data": "no",
        },
    ],
}


class _Reply(io.BytesIO):
    def __init__(self):
        body = {"choices": [{"message": {"content": "From the sample."}}], "usage": {"prompt_tokens": 4}}
        super().__init__(json.dumps(body).encode())
        self.headers = {"x-routed-via": "cerebras/gpt-oss-120b"}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


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
    monkeypatch.setattr(vetted, "load", lambda path=None: REGISTER)
    sent = []

    def urlopen(req, timeout=None):
        sent.append(req.full_url)
        return _Reply()

    monkeypatch.setattr(provider_module.request, "urlopen", urlopen)
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


def test_only_a_platform_administrator_sets_a_persons_ai_flag(trial):
    url = f"/api/v1/platform-admin/tenants/{trial['tenant_id']}/users/{trial['user_id']}/ai-access"
    body = {"ai_access": "INACTIVE", "reason": "Trial person asked for no AI"}
    # The trial's own administrator is refused, on the single and the bulk endpoint.
    assert trial["client"].put(url, json=body).status_code == 403
    bulk = f"/api/v1/platform-admin/tenants/{trial['tenant_id']}/users/ai-access"
    assert trial["client"].put(bulk, json={**body, "user_ids": [str(trial["user_id"])]}).status_code == 403
    admin = authenticated_client()
    assert admin.put(url, json={"ai_access": "INACTIVE", "reason": "no"}).status_code == 422  # reason too short
    changed = admin.put(url, json=body)
    try:
        assert changed.status_code == 200, changed.text
        assert changed.json() == {"user_id": str(trial["user_id"]), "ai_access": "INACTIVE", "changed": True}
        with SessionLocal() as db:
            bind_system(db, "test")
            event = (
                db.query(AuditEvent)
                .filter(AuditEvent.action == "AI_USER_ACCESS_CHANGED", AuditEvent.entity_id == trial["user_id"])
                .order_by(AuditEvent.created_at.desc())
                .first()
            )
            assert event.old_values == {"ai_access": "ACTIVE"} and event.new_values == {"ai_access": "INACTIVE"}
            assert event.reason == body["reason"] and event.actor_ref and event.created_at
        listed = admin.get(bulk).json()["items"]
        assert {"user_id": str(trial["user_id"]), "ai_access": "INACTIVE"}.items() <= next(
            item for item in listed if item["user_id"] == str(trial["user_id"])
        ).items()
        back = admin.put(bulk, json={"ai_access": "ACTIVE", "reason": "Back on", "user_ids": [str(trial["user_id"])]})
        assert back.status_code == 200 and back.json()["items"][0]["changed"] is True
    finally:
        _set_user(trial["user_id"], "ACTIVE")


def test_the_person_flag_is_not_offered_for_a_paid_organization():
    admin = authenticated_client()
    with SessionLocal() as db:
        bind_system(db, "test")
        tenant = db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first()
        person = db.query(AuthUser).filter(AuthUser.tenant_id == tenant.id).first()
    response = admin.put(
        f"/api/v1/platform-admin/tenants/{tenant.id}/users/{person.id}/ai-access",
        json={"ai_access": "INACTIVE", "reason": "Not for paid organizations"},
    )
    assert response.status_code == 409 and response.json()["detail"]["code"] == "AI_USER_FLAG_TRIAL_ONLY"


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
    finally:
        _set_tenant(trial["tenant_id"], ai_processing_allowed=False)


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
