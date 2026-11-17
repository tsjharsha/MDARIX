"""Per-organization AI controls: personal data masked, switch, monthly budget, usage, shared provider rest periods."""

import json
import uuid

import pytest
from sqlalchemy import text

import genai.provider as provider_module
from backend.app.db.models.foundation import Tenant
from backend.app.db.models.stage2 import AiUsageMonthly
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from genai import governance
from genai.pii import mask, mask_text
from genai.provider import GenAIProvider, GenAIUnavailable
from tests.conftest import authenticated_client


@pytest.fixture(autouse=True)
def _ai_features_on_platform(monkeypatch):
    # These tests exercise the provider itself: every offered feature is on the platform list (genai/features.py).
    monkeypatch.setenv(
        "MDARIX_AI_FEATURES", "ask,summaries,case_analysis,drafting,evidence_extraction,code_suggestions"
    )


# ------------------------------------------------------------------------------------------------ masking


def test_personal_information_is_masked_and_investigation_facts_are_kept():
    text_in = (
        "Reported by Jane Doe (jane.doe@hospital.org, +1 617 555 0100). Patient: John Smith, DOB: 1961-04-02, "
        "MRN 004512. Address: 1 High Street, Leeds LS1 4AP; Dr. Alan Grant reviewed lot L24-0815 on 2026-10-03. "
        "Card 4111 1111 1111 1111, SSN 123-45-6789, client IP: 192.168.1.20."
    )
    masked = mask_text(text_in)
    for secret in (
        "Jane Doe",
        "jane.doe@hospital.org",
        "617 555 0100",
        "John Smith",
        "1961-04-02",
        "004512",
        "High Street",
        "Alan Grant",
        "4111",
        "123-45-6789",
        "192.168.1.20",
    ):
        assert secret not in masked
    # The lot and the event date are investigation facts. The reviewer beside them is staff, not a patient, so the
    # lot stays (a lot beside a patient-side identifier is masked: tests/test_pii_corpus.py).
    assert "L24-0815" in masked and "2026-10-03" in masked and "[LOT]" not in masked


def test_clinical_and_product_wording_is_not_mistaken_for_personal_data():
    sentence = (
        "The patient experienced a delayed alarm on OrbitCare 300 Rev B, lot SAMPLE-ORBIT-300-LOT-003, firmware "
        "2.10.3.4; the mobile app showed E-104 and we will address the issue in ECN-4471 (2 of 13 read 4-6% high)."
    )
    assert mask_text(sentence) == sentence
    assert mask({"patient_harm": "none", "patient_impact": "minor", "reporter_email": "a@b.co", "product": "X"}) == {
        "patient_harm": "none",
        "patient_impact": "minor",
        "reporter_email": "[PERSONAL_DATA]",
        "product": "X",
    }


# ------------------------------------------------------------------------------------------------ provider


class _Response:
    def __init__(self, text_out: str):
        self.text_out = text_out

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(
            {
                "choices": [{"message": {"content": self.text_out}}],
                "usage": {"prompt_tokens": 40, "completion_tokens": 7},
            }
        ).encode()


@pytest.fixture
def groq(monkeypatch):
    """A configured model whose requests are captured instead of sent."""
    provider_module._COOLDOWN_UNTIL.clear()
    for name, value in {
        "MDARIX_GENAI_PROVIDER": "groq",
        "MDARIX_GENAI_API_KEY": "test-key",
        "MDARIX_GENAI_MODEL": "openai/gpt-oss-120b",
        "MDARIX_GENAI_FALLBACKS": "",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("MDARIX_GENAI_BASE_URL", raising=False)
    monkeypatch.setattr(provider_module.time, "sleep", lambda seconds: None)
    sent = []

    def urlopen(req, timeout=None):
        sent.append(json.loads(req.data))
        return _Response("Answer from the model.")

    monkeypatch.setattr(provider_module.request, "urlopen", urlopen)
    yield sent
    provider_module._COOLDOWN_UNTIL.clear()


REAUTH = "backend.app.governance_router.verify_signing_credentials"


@pytest.fixture
def tenant(monkeypatch):
    """The synthetic tenant with AI switched on explicitly, its original policy restored afterwards.

    AI processing is off for new organizations (md23), so tests that need a model opt in the way an administrator
    does: the platform administrator's AI settings endpoint, with the acknowledgement and a reason. Nothing depends
    on whichever policy another test or seed script left behind.
    """
    db = SessionLocal()
    bind_system(db, "test")
    row = db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first() or db.query(Tenant).first()
    tenant_id = row.id
    saved = (row.ai_processing_allowed, row.ai_monthly_token_budget, dict(row.ai_features or {}))
    db.close()
    _set(tenant_id, ai_processing_allowed=False)  # so the switch below is a real "on" that needs the acknowledgement
    from tests.support_grants import grant_support_access

    grant_support_access(tenant_id, areas=("CONFIGURATION",))  # the customer approved Configuration access
    # Switching on is signature-grade (password + authenticator code); its own tests cover the check.
    with monkeypatch.context() as signed:
        signed.setattr(REAUTH, lambda *args, **kwargs: None)
        switched = authenticated_client().put(
            f"/api/v1/platform-admin/tenants/{tenant_id}/ai-settings",
            json={
                "ai_processing_allowed": True,
                "use_default_budget": True,
                "acknowledgement": True,
                "reason": "Tests switch AI on for the synthetic organization",
            },
        )
    assert switched.status_code == 200 and switched.json()["ai_processing_allowed"] is True, switched.text
    # The organization's switch for the feature these tests use (tenants.ai_features, genai/features.py).
    _set(tenant_id, ai_features={"ask": True})
    try:
        yield tenant_id
    finally:
        db = SessionLocal()
        bind_system(db, "test")
        db.query(Tenant).filter(Tenant.id == tenant_id).update(
            {"ai_processing_allowed": saved[0], "ai_monthly_token_budget": saved[1], "ai_features": saved[2]}
        )
        db.commit()
        db.close()


def _set(tenant_id, **values):
    db = SessionLocal()
    bind_system(db, "test")
    db.query(Tenant).filter(Tenant.id == tenant_id).update(values)
    db.commit()
    db.close()


def _usage(tenant_id) -> dict:
    db = SessionLocal()
    bind_system(db, "test")
    try:
        return governance.usage(db, tenant_id)
    finally:
        db.close()


def test_the_model_never_receives_personal_information(groq, tenant):
    with governance.tenant_scope(tenant):
        GenAIProvider().complete(
            "Summarize: reported by Jane Doe, jane.doe@hospital.org.",
            {"reporter_phone": "617 555 0100", "lot": "L-7"},
            feature="ask",
        )
    body = json.dumps(groq[-1])
    assert "Jane Doe" not in body and "jane.doe@hospital.org" not in body and "617 555 0100" not in body
    assert "[EMAIL]" in body and "L-7" in body


def test_usage_is_counted_per_organization_and_month(groq, tenant):
    before = _usage(tenant)
    with governance.tenant_scope(tenant):
        GenAIProvider().complete("Summarize the record.", {"lot": "L-1"}, feature="ask")
    after = _usage(tenant)
    assert after["requests"] == before["requests"] + 1
    assert after["tokens_used"] == before["tokens_used"] + 47


def test_an_organization_with_ai_switched_off_gets_no_model_call(groq, tenant):
    _set(tenant, ai_processing_allowed=False)
    before = _usage(tenant)["refused"]
    with governance.tenant_scope(tenant), pytest.raises(GenAIUnavailable, match="GENAI_DISABLED_FOR_ORGANIZATION"):
        GenAIProvider().complete("Summarize the record.", {}, feature="ask")
    assert groq == [] and _usage(tenant)["refused"] == before + 1


def test_the_monthly_budget_stops_model_calls(groq, tenant):
    _set(tenant, ai_monthly_token_budget=_usage(tenant)["tokens_used"] + 10)
    with governance.tenant_scope(tenant), pytest.raises(GenAIUnavailable, match="GENAI_MONTHLY_BUDGET_REACHED"):
        GenAIProvider().complete("Summarize the record.", {}, feature="ask")
    assert groq == []


def test_production_refuses_a_model_call_without_an_organization(groq, monkeypatch):
    monkeypatch.setenv("MDARIX_ENV", "production")
    # Groq is registered for the free-trial chain only (genai/vetted_providers.json), so the paid provider here is
    # another contracted one; the fixture still captures any request.
    monkeypatch.setenv("MDARIX_GENAI_PROVIDER", "cerebras")
    monkeypatch.setenv("MDARIX_GENAI_CONTRACTED_PROVIDERS", "cerebras")
    monkeypatch.setenv("MDARIX_GENAI_CEREBRAS_ZDR", "true")
    with pytest.raises(GenAIUnavailable, match="GENAI_NO_TENANT_SCOPE"):
        GenAIProvider().complete("Summarize the record.", {}, feature="ask")
    assert groq == []


def test_a_signed_in_request_applies_its_organizations_controls(groq, tenant):
    """End to end: the request context names the organization, so its switch and usage apply to Ask MDARIX.

    Asked from the golden investigation, so the model is always asked (with the case's records), whatever the
    evidence search finds: a question asked of the whole organization that no record answers gets no model since
    0.10.87 (DEV-11 abstention), and whether the search finds a record depended on what earlier tests left."""
    from backend.app.db.models.foundation import Investigation

    with SessionLocal() as db:
        bind_system(db, "test: the golden investigation")
        case = str(
            db.query(Investigation.id)
            .filter(Investigation.tenant_id == tenant, Investigation.investigation_identifier == "INV-001")
            .scalar()
        )
    client = authenticated_client()
    before = _usage(tenant)["requests"]
    asked = {"prompt": "What changed? Contact jane@x.org", "investigation_id": case}
    response = client.post("/api/v1/stage3/interactions", json=asked)
    assert response.status_code == 200, response.text
    assert groq and "jane@x.org" not in json.dumps(groq[-1])
    assert _usage(tenant)["requests"] == before + 1
    # The model's answer names its call, which a person accepts, edits or rejects (AI-D7).
    call_id = response.json()["response"]["ai_call_id"]
    reviewed = client.post(f"/api/v1/ai-outputs/{call_id}/review", json={"decision": "ACCEPTED"})
    assert reviewed.status_code == 200 and reviewed.json()["subject_type"] == "ai_call", reviewed.text

    _set(tenant, ai_processing_allowed=False)
    calls = len(groq)
    response = client.post("/api/v1/stage3/interactions", json={"prompt": "What changed?", "investigation_id": case})
    assert response.status_code == 200 and len(groq) == calls  # answered without a model


# ------------------------------------------------------------------------------------------------ rest periods


def test_a_rate_limited_provider_rests_for_every_process(monkeypatch):
    monkeypatch.setenv("MDARIX_GENAI_SHARED_REST", "true")
    name = f"test-{uuid.uuid4().hex[:8]}"
    try:
        provider_module._rest(name, 120, "RATE_LIMITED")
        provider_module._COOLDOWN_UNTIL.clear()  # another process has no local record of it
        assert provider_module._resting_until().get(name, 0) > 0
    finally:
        provider_module._COOLDOWN_UNTIL.pop(name, None)
        db = SessionLocal()
        db.execute(text("DELETE FROM genai_provider_rest WHERE provider = :name"), {"name": name})
        db.commit()
        db.close()


def test_usage_rows_are_private_to_their_organization(tenant):
    """Row-level security: another organization's session sees none of this organization's AI usage."""
    from backend.app.db.tenant_scope import bind_tenant

    with governance.tenant_scope(tenant):
        governance.record_usage(str(tenant), 1, 1, 0.0)
    from backend.app.db.session import RuntimeSessionLocal, runtime_role_active

    if not runtime_role_active():
        pytest.skip("needs the least-privilege runtime role")
    db = RuntimeSessionLocal()
    try:
        bind_tenant(db, tenant)
        assert db.query(AiUsageMonthly).filter(AiUsageMonthly.tenant_id == tenant).count() == 1
        db.rollback()
        bind_tenant(db, uuid.uuid4())
        assert db.query(AiUsageMonthly).filter(AiUsageMonthly.tenant_id == tenant).count() == 0
    finally:
        db.close()


# ------------------------------------------------------------------------------------------------ extractor


def test_a_long_document_is_cut_to_the_models_limit_and_the_cut_is_reported():
    from ai.extractor import AIEvidenceExtractor

    sent = []

    class Model(GenAIProvider):
        def health(self):
            return {"configured": True}

        def complete(self, prompt, context=None, **kwargs):
            sent.append(prompt)
            answer = json.dumps(
                {"observations": [], "entity_candidates": [], "limitations": [], "candidate_conflicts": []}
                | {"extraction_status": "COMPLETED", "warnings": []}
            )
            return provider_module.GenAIResult("groq", "m", "v", {"answer": answer}, 1, 1, 0.0, 1)

    extractor = AIEvidenceExtractor()
    extractor.provider_client = Model(max_input_tokens=4000)
    result = extractor._provider_extraction("EV-1", "Long report", "x" * 100_000, {}, False)
    assert len(sent[0]) <= 4000 * 4
    assert any("characters were analyzed" in warning for warning in result.warnings)


# ------------------------------------------------------------------------------------------------ settings API


def _latest_setting_event(tenant_id):
    return _latest_event(tenant_id, "AI_PROCESSING_SETTING_CHANGED")


def _latest_event(tenant_id, action):
    from backend.app.db.models.foundation import AuditEvent

    db = SessionLocal()
    bind_system(db, "test")
    try:
        return (
            db.query(AuditEvent)
            .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.action == action)
            .order_by(AuditEvent.chain_seq.desc())
            .first()
        )
    finally:
        db.close()


def test_a_customer_administrator_switches_ai_off_for_their_organization_with_a_reason(tenant):
    """The audit diff holds only what changed. (Before md23 the tenant was already off, so this "off" changed
    nothing and the diff was rightly empty: the stale part was the test, which now switches AI on first.)"""
    from tests.test_business_permissions import _client_with_role

    admin = _client_with_role("CUSTOMER_ADMIN")
    shown = admin.get("/api/v1/admin/ai-settings")
    assert shown.status_code == 200, shown.text
    assert {"ai_processing_allowed", "monthly_token_budget", "tokens_used", "models"} <= set(shown.json())
    assert {"provider_name", "masking"} <= set(shown.json()) and shown.json()["masking"] is True
    assert admin.put("/api/v1/admin/ai-settings", json={"ai_processing_allowed": False}).status_code == 422
    changed = admin.put(
        "/api/v1/admin/ai-settings", json={"ai_processing_allowed": False, "reason": "Pilot uses real complaints"}
    )
    assert changed.status_code == 200 and changed.json()["ai_processing_allowed"] is False
    event = _latest_setting_event(tenant)
    assert event is not None and event.new_values == {"ai_processing_allowed": False}
    assert "acknowledgement" not in (event.details or {})  # switching off needs no acknowledgement


def test_two_administrators_switching_at_once_the_second_is_told_to_refresh(tenant):  # review D3
    from tests.test_business_permissions import _client_with_role

    admin = _client_with_role("CUSTOMER_ADMIN")
    read = admin.get("/api/v1/admin/ai-settings").json()["lock_version"]
    body = {"ai_processing_allowed": False, "reason": "First administrator's change"}
    assert admin.put("/api/v1/admin/ai-settings", json={**body, "lock_version": read}).status_code == 200
    stale = admin.put(
        "/api/v1/admin/ai-settings", json={**body, "reason": "Second, on the old page", "lock_version": read}
    )
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "STALE_RECORD"
    assert admin.get("/api/v1/admin/ai-settings").json()["lock_version"] == read + 1


def signed_off(monkeypatch) -> None:
    """The signature-grade check passes (its own tests cover the password and the code)."""
    monkeypatch.setattr("backend.app.governance_router.verify_signing_credentials", lambda *args, **kwargs: None)


def test_switching_ai_on_needs_an_acknowledgement_that_the_audit_keeps(tenant, monkeypatch):
    from tests.test_business_permissions import _client_with_role

    _set(tenant, ai_processing_allowed=False)
    admin = _client_with_role("CUSTOMER_ADMIN")
    body = {"ai_processing_allowed": True, "reason": "Pilot agreed to AI processing"}
    refused = admin.put("/api/v1/admin/ai-settings", json=body)
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "AI_ACKNOWLEDGEMENT_REQUIRED"
    assert _usage(tenant)["ai_processing_allowed"] is False
    # Switching on is signature-grade: refused without the password and authenticator code (C6).
    unsigned = admin.put("/api/v1/admin/ai-settings", json={**body, "acknowledgement": True})
    assert unsigned.status_code == 403 and _usage(tenant)["ai_processing_allowed"] is False
    signed_off(monkeypatch)
    switched = admin.put("/api/v1/admin/ai-settings", json={**body, "acknowledgement": True})
    assert switched.status_code == 200, switched.text
    answer = switched.json()
    assert answer["ai_processing_allowed"] is True and answer["masking"] is True and "provider_name" in answer
    event = _latest_setting_event(tenant)
    assert event.new_values == {"ai_processing_allowed": True} and event.reason == body["reason"]
    assert event.details["acknowledgement"] is True and event.details["provider_name"] == (
        answer["provider_name"] or "none configured"
    )


def test_in_production_ai_is_switched_on_only_when_the_release_gate_is_met(tenant, monkeypatch):
    from backend.app import ai_release_gate
    from tests.test_business_permissions import _client_with_role

    _set(tenant, ai_processing_allowed=False)
    admin = _client_with_role("CUSTOMER_ADMIN")
    gate = admin.get("/api/v1/ai/release-gate")
    assert gate.status_code == 200 and gate.json()["total"] == 4 and gate.json()["ready"] is False
    assert admin.get("/api/v1/admin/ai-settings").json()["release_gate"]["bars"] == gate.json()["bars"]

    monkeypatch.setattr(ai_release_gate, "enforced", lambda: True)  # as MDARIX_ENV=production
    body = {"ai_processing_allowed": True, "reason": "Pilot agreed to AI processing", "acknowledgement": True}
    refused = admin.put("/api/v1/admin/ai-settings", json=body)
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "AI_RELEASE_GATE_NOT_MET"
    assert "The golden dataset signed off by a person" in refused.json()["detail"]["message"]
    assert _usage(tenant)["ai_processing_allowed"] is False
    platform = authenticated_client().put(
        f"/api/v1/platform-admin/tenants/{tenant}/ai-settings", json={**body, "use_default_budget": True}
    )
    assert platform.status_code == 409 and _usage(tenant)["ai_processing_allowed"] is False

    ready = {"ready": True, "met": 4, "total": 4, "enforced": True, "bars": [], "message": "ready"}
    monkeypatch.setattr(ai_release_gate, "status", lambda models=None, files=None: ready)
    signed_off(monkeypatch)
    switched = admin.put("/api/v1/admin/ai-settings", json=body)
    assert switched.status_code == 200 and switched.json()["ai_processing_allowed"] is True, switched.text
    # Switching off is never gated.
    monkeypatch.setattr(ai_release_gate, "status", lambda models=None, files=None: {**ready, "ready": False})
    off = admin.put("/api/v1/admin/ai-settings", json={"ai_processing_allowed": False, "reason": "Pilot paused AI"})
    assert off.status_code == 200 and off.json()["ai_processing_allowed"] is False


def test_a_new_organization_starts_with_ai_off_and_its_platform_switch_needs_the_acknowledgement(monkeypatch):
    platform = authenticated_client()
    code = f"AIOFF{uuid.uuid4().hex[:6].upper()}"
    created = platform.post(
        "/api/v1/platform-admin/customers",
        json={"company_name": f"AI Default {code}", "tenant_code": code, "plan_code": "STARTER"},
    )
    assert created.status_code == 200, created.text
    from tests.support_grants import grant_support_access

    grant_support_access(created.json()["id"], areas=("CONFIGURATION",))
    url = f"/api/v1/platform-admin/tenants/{created.json()['id']}/ai-settings"
    assert platform.get(url).json()["ai_processing_allowed"] is False
    body = {"ai_processing_allowed": True, "reason": "Customer signed the AI addendum"}
    refused = platform.put(url, json=body)
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "AI_ACKNOWLEDGEMENT_REQUIRED"
    assert platform.put(url, json={"monthly_token_budget": 1000, "reason": "Budget only"}).status_code == 200
    # The Platform Administrator's switch-on needs the password and an authenticator code too (owner, 16 Nov).
    unsigned = platform.put(url, json={**body, "acknowledgement": True})
    assert unsigned.status_code == 403 and unsigned.json()["detail"]["code"] == "INVALID_REAUTHENTICATION"
    assert platform.get(url).json()["ai_processing_allowed"] is False
    refusal = _latest_event(uuid.UUID(created.json()["id"]), "SIGNATURE_REAUTHENTICATION_FAILED")
    assert refusal.details == {"attempt": "AI_PROCESSING_SWITCH_ON"}
    monkeypatch.setattr(REAUTH, lambda *args, **kwargs: None)
    switched = platform.put(url, json={**body, "acknowledgement": True})
    assert switched.status_code == 200 and switched.json()["ai_processing_allowed"] is True
    event = _latest_setting_event(uuid.UUID(created.json()["id"]))
    assert event.details["source"] == "PLATFORM_ADMIN" and event.details["acknowledgement"] is True


def test_only_administrators_change_ai_settings(tenant):
    from tests.test_business_permissions import _client_with_role

    reviewer = _client_with_role("Investigator")
    assert reviewer.get("/api/v1/admin/ai-settings").status_code in (401, 403)
    body = {"ai_processing_allowed": False, "reason": "Should not be allowed"}
    assert reviewer.put("/api/v1/admin/ai-settings", json=body).status_code in (401, 403)
    assert reviewer.put(f"/api/v1/platform-admin/tenants/{tenant}/ai-settings", json=body).status_code in (401, 403)


def test_a_platform_administrator_sets_an_organizations_monthly_budget(tenant):
    platform = authenticated_client()
    url = f"/api/v1/platform-admin/tenants/{tenant}/ai-settings"
    changed = platform.put(url, json={"monthly_token_budget": 50_000, "reason": "Pilot allowance"})
    assert changed.status_code == 200, changed.text
    assert changed.json()["monthly_token_budget"] == 50_000 and changed.json()["budget_is_default"] is False
    reset = platform.put(url, json={"use_default_budget": True, "reason": "Back to the standard allowance"})
    assert reset.json()["budget_is_default"] is True
    assert platform.put(url, json={"monthly_token_budget": -1, "reason": "Negative"}).status_code == 422
    assert platform.get(f"/api/v1/platform-admin/tenants/{uuid.uuid4()}/ai-settings").status_code == 404


# ------------------------------------------------------------------------------------------------ evaluation gate


def test_the_release_gate_requires_every_scenario_and_the_model():
    from scripts.run_real_evaluation import gate_problems

    good = {"passed": 12, "total": 12, "passed_with_specific_expectations": 1, "with_specific_expectations": 1}
    assert gate_problems({**good, "model_written": 12}, None, True) == []
    assert len(gate_problems({**good, "passed": 8, "model_written": 12}, None, True)) == 1
    assert gate_problems({**good, "passed": 8, "model_written": 12}, 8, True) == []
    missed = {**good, "passed_with_specific_expectations": 0, "model_written": 12}
    assert any("specific expectations" in problem for problem in gate_problems(missed, None, False))
    assert any("written by the model" in problem for problem in gate_problems({**good, "model_written": 3}, None, True))


# ------------------------------------------------------------------------------------------------ budget alerts


def test_budget_alerts_fire_once_per_month_at_80_and_100_percent(tenant, monkeypatch):
    """Administrators hear at 80% and 100%, operators at 100%, each once a month (the marker is an audit event)."""
    import random
    from datetime import date, datetime, timezone

    import backend.app.alerts as alerts
    import backend.app.notifications as notifications

    notices, operator_alerts = [], []
    monkeypatch.setattr(
        notifications,
        "notify_ai_budget_threshold",
        lambda db, tenant_id, percent: notices.append((tenant_id, percent)),
        raising=False,
    )
    monkeypatch.setattr(alerts, "send_alert", lambda subject, body: operator_alerts.append(subject))
    # A month of its own (far future), so a re-run of the suite starts with no markers.
    month = date(random.randint(2200, 9000), random.randint(1, 12), 1)
    now = datetime(month.year, month.month, 15, tzinfo=timezone.utc)
    _set(tenant, ai_monthly_token_budget=1000)

    def use(tokens):
        db = SessionLocal()
        bind_system(db, "test")
        row = db.get(AiUsageMonthly, (tenant, month))
        if row is None:
            db.add(
                AiUsageMonthly(
                    tenant_id=tenant,
                    month=month,
                    requests=1,
                    refused=0,
                    input_tokens=tokens,
                    output_tokens=0,
                    estimated_cost=0,
                    updated_at=now,
                )
            )
        else:
            row.input_tokens = tokens
        db.commit()
        db.close()

    try:
        use(700)
        assert governance.check_budget_thresholds(str(tenant), now=now) == []
        use(850)
        assert governance.check_budget_thresholds(str(tenant), now=now) == [80]
        assert governance.check_budget_thresholds(str(tenant), now=now) == []  # once a month
        assert notices == [(tenant, 80)] and operator_alerts == []
        use(990)  # a request refused for the budget counts as the allowance being used up
        assert governance.check_budget_thresholds(str(tenant), budget_refused=True, now=now) == [100]
        use(1200)
        assert governance.check_budget_thresholds(str(tenant), now=now) == []
        assert notices == [(tenant, 80), (tenant, 100)] and operator_alerts == ["AI monthly allowance used up"]
    finally:
        db = SessionLocal()
        bind_system(db, "test")
        db.query(AiUsageMonthly).filter(AiUsageMonthly.tenant_id == tenant, AiUsageMonthly.month == month).delete()
        db.commit()
        db.close()


def test_a_model_call_past_80_percent_tells_the_administrators(groq, tenant, monkeypatch):
    import backend.app.notifications as notifications

    notices = []
    monkeypatch.setattr(
        notifications,
        "notify_ai_budget_threshold",
        lambda db, tenant_id, percent: notices.append(percent),
        raising=False,
    )
    monkeypatch.setattr(governance, "_record_thresholds", lambda tenant_id, refused, now: [(80, {})])
    with governance.tenant_scope(tenant):
        GenAIProvider().complete("Summarize the record.", {}, feature="ask")
    assert notices == [80]
