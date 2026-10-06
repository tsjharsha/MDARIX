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
    # A product lot is normally investigation context, but this one appears in the same
    # sentence as a named reviewer.  The approved privacy policy therefore masks the
    # potentially identifying person/lot pair while retaining the event date.
    assert "L24-0815" not in masked and "[LOT]" in masked and "2026-10-03" in masked


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


@pytest.fixture
def tenant():
    """An explicitly AI-enabled tenant whose original policy is restored afterwards.

    The shared fixture is deliberately conservative and may have AI disabled.  Provider,
    usage and budget tests must opt in rather than depending on whichever policy another
    test or seed script left behind.
    """
    db = SessionLocal()
    bind_system(db, "test")
    row = db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first() or db.query(Tenant).first()
    tenant_id = row.id
    saved = (row.ai_processing_allowed, row.ai_monthly_token_budget)
    row.ai_processing_allowed = True
    row.ai_monthly_token_budget = None
    db.commit()
    db.close()
    try:
        yield tenant_id
    finally:
        db = SessionLocal()
        bind_system(db, "test")
        db.query(Tenant).filter(Tenant.id == tenant_id).update(
            {"ai_processing_allowed": saved[0], "ai_monthly_token_budget": saved[1]}
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
            "Summarize: reported by Jane Doe, jane.doe@hospital.org.", {"reporter_phone": "617 555 0100", "lot": "L-7"}
        )
    body = json.dumps(groq[-1])
    assert "Jane Doe" not in body and "jane.doe@hospital.org" not in body and "617 555 0100" not in body
    assert "[EMAIL]" in body and "L-7" in body


def test_usage_is_counted_per_organization_and_month(groq, tenant):
    before = _usage(tenant)
    with governance.tenant_scope(tenant):
        GenAIProvider().complete("Summarize the record.", {"lot": "L-1"})
    after = _usage(tenant)
    assert after["requests"] == before["requests"] + 1
    assert after["tokens_used"] == before["tokens_used"] + 47


def test_an_organization_with_ai_switched_off_gets_no_model_call(groq, tenant):
    _set(tenant, ai_processing_allowed=False)
    before = _usage(tenant)["refused"]
    with governance.tenant_scope(tenant), pytest.raises(GenAIUnavailable, match="GENAI_DISABLED_FOR_ORGANIZATION"):
        GenAIProvider().complete("Summarize the record.", {})
    assert groq == [] and _usage(tenant)["refused"] == before + 1


def test_the_monthly_budget_stops_model_calls(groq, tenant):
    _set(tenant, ai_monthly_token_budget=_usage(tenant)["tokens_used"] + 10)
    with governance.tenant_scope(tenant), pytest.raises(GenAIUnavailable, match="GENAI_MONTHLY_BUDGET_REACHED"):
        GenAIProvider().complete("Summarize the record.", {})
    assert groq == []


def test_production_refuses_a_model_call_without_an_organization(groq, monkeypatch):
    monkeypatch.setenv("MDARIX_ENV", "production")
    monkeypatch.setenv("MDARIX_GENAI_CONTRACTED_PROVIDERS", "groq")
    with pytest.raises(GenAIUnavailable, match="GENAI_NO_TENANT_SCOPE"):
        GenAIProvider().complete("Summarize the record.", {})
    assert groq == []


def test_a_signed_in_request_applies_its_organizations_controls(groq, tenant):
    """End to end: the request context names the organization, so its switch and usage apply to Ask MDARIX."""
    client = authenticated_client()
    before = _usage(tenant)["requests"]
    response = client.post("/api/v1/stage3/interactions", json={"prompt": "What changed? Contact jane@x.org"})
    assert response.status_code == 200, response.text
    assert groq and "jane@x.org" not in json.dumps(groq[-1])
    assert _usage(tenant)["requests"] == before + 1

    _set(tenant, ai_processing_allowed=False)
    calls = len(groq)
    response = client.post("/api/v1/stage3/interactions", json={"prompt": "What changed?"})
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


def test_a_customer_administrator_switches_ai_off_for_their_organization_with_a_reason(tenant):
    from backend.app.db.models.foundation import AuditEvent
    from tests.test_business_permissions import _client_with_role

    admin = _client_with_role("CUSTOMER_ADMIN")
    shown = admin.get("/api/v1/admin/ai-settings")
    assert shown.status_code == 200, shown.text
    assert {"ai_processing_allowed", "monthly_token_budget", "tokens_used", "models"} <= set(shown.json())
    assert admin.put("/api/v1/admin/ai-settings", json={"ai_processing_allowed": False}).status_code == 422
    changed = admin.put(
        "/api/v1/admin/ai-settings", json={"ai_processing_allowed": False, "reason": "Pilot uses real complaints"}
    )
    assert changed.status_code == 200 and changed.json()["ai_processing_allowed"] is False
    db = SessionLocal()
    bind_system(db, "test")
    event = (
        db.query(AuditEvent)
        .filter(AuditEvent.tenant_id == tenant, AuditEvent.action == "AI_PROCESSING_SETTING_CHANGED")
        .order_by(AuditEvent.created_at.desc())
        .first()
    )
    db.close()
    assert event is not None and event.new_values == {"ai_processing_allowed": False}


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
