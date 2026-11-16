"""AI code suggestions (AI-R part D, step 10; WHIF story step 5), against the database, on the fake gateway only.

A trial's US report on its sample flagship complaint: the model's IMDRF proposals are kept only when the code is in the
loaded release, in an annex the form asks for, with a confidence and the complaint's own words; nothing is entered on
the report until a person enters one code through its field, audited with the run it came from; "Confirm all codes"
never enters an AI suggestion; with the feature switched off no AI service is called.
"""

from __future__ import annotations

import json
import uuid

import pytest

from backend.app.db.models.ai_records import AiCall
from backend.app.db.models.authority_reports import ReportObligation
from backend.app.db.models.foundation import AuditEvent, Complaint, Tenant
from backend.app.db.models.regulatory_reference import ImdrfCode
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.regulatory_reference import newest_release, selectable
from genai import provider as provider_module
from genai import vetted
from tests.code_lists import ensure_loaded
from tests.fake_ai_gateway import FREELLMAPI, FREELLMAPI_CEREBRAS, Reply, answer, install, register
from tests.test_free_trial import _approved_trial_client
from tests.test_release_c3_0_10_75 import REPORTS, _flagship, _ok, _purge, _reports, _sign_us

pytestmark = pytest.mark.db


def _fields(detail: dict) -> dict:
    return {item["id"]: item for section in detail["sections"] for item in section["fields"]}


@pytest.fixture(scope="module")
def trial():
    ensure_loaded()
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    complaint = _flagship(user)
    try:
        _ok(_sign_us(user, complaint, "REPORTABLE"))
        (report,) = _reports(user, complaint)
        with SessionLocal() as db:
            bind_system(db, "test")
            description = db.get(Complaint, uuid.UUID(complaint)).description
            release = newest_release(db)
            codes = [
                row
                for row in db.query(ImdrfCode).filter(ImdrfCode.release == release, ImdrfCode.annex == "A")
                if selectable(row.status)
            ]
        yield {
            "user": user,
            "tenant_id": tenant_id,
            "report": report["id"],
            "quote": " ".join(description.split()[:4]),
            "codes": [row.code for row in codes[:3]],
        }
    finally:
        _purge(tenant_id)


def _set_tenant(tenant_id, **values):
    with SessionLocal() as db:
        bind_system(db, "test")
        db.query(Tenant).filter(Tenant.id == tenant_id).update(values)
        db.commit()


@pytest.fixture
def ai_on(trial, monkeypatch):
    """The trial chain on one fake gateway; the organization and its code-suggestion switch on."""
    provider_module._COOLDOWN_UNTIL.clear()
    monkeypatch.setenv("MDARIX_GENAI_SHARED_REST", "false")
    monkeypatch.setenv("MDARIX_GENAI_PROVIDER", "controlled")
    monkeypatch.setenv("MDARIX_AI_TRIAL_CHAIN", "freellmapi")
    monkeypatch.setenv("MDARIX_GENAI_FREELLMAPI_API_KEY", "test-key")
    monkeypatch.delenv("MDARIX_GENAI_FREELLMAPI_BASE_URL", raising=False)
    monkeypatch.setenv("MDARIX_AI_FEATURES", "code_suggestions")
    monkeypatch.setattr(vetted, "load", lambda path=None: register())
    first, second, _ = trial["codes"]
    reply = {
        "suggestions": [
            {"annex": "A", "code": first, "confidence": 0.82, "quote": trial["quote"]},
            {"annex": "A", "code": second, "confidence": 0.4, "quote": trial["quote"]},
            {"annex": "A", "code": "A9999Z", "confidence": 0.9, "quote": trial["quote"]},
            {"annex": "A", "code": first, "confidence": 0.7, "quote": "words the complaint never says"},
            {"annex": "A", "code": second, "confidence": 1.7, "quote": trial["quote"]},
            {"annex": "Q", "code": first, "confidence": 0.5, "quote": trial["quote"]},
        ]
    }
    state = install(monkeypatch, default=lambda: Reply(answer(json.dumps(reply)), FREELLMAPI_CEREBRAS))
    _set_tenant(trial["tenant_id"], ai_processing_allowed=True, ai_features={"code_suggestions": True})
    yield state
    _set_tenant(trial["tenant_id"], ai_processing_allowed=False, ai_features={})


def _suggest(trial):
    return trial["user"].post(f"{REPORTS}/{trial['report']}/codes/ai-suggestions")


def test_proposals_come_from_the_loaded_release_with_confidence_and_quote_and_enter_nothing(trial, ai_on):
    before = _fields(_ok(trial["user"].get(f"{REPORTS}/{trial['report']}")))
    response = _suggest(trial)
    assert response.status_code == 200, response.text
    body = response.json()
    first, second, _ = trial["codes"]
    assert [(item["code"], item["confidence"]) for item in body["suggestions"]] == [(first, 0.82), (second, 0.4)]
    assert all(item["quote"] == trial["quote"] and item["term"] and item["field_ids"] for item in body["suggestions"])
    assert {item["reason"] for item in body["ai"]["dropped"]} == {
        "NOT_IN_RELEASE",
        "QUOTE_NOT_IN_COMPLAINT",
        "NO_CONFIDENCE",
        "ANNEX_NOT_ON_FORM",
    }
    assert body["ai"]["label"].startswith("AI suggestion") and ai_on["sent"] == [FREELLMAPI]
    # Nothing is stored as a code: every field reads as before.
    after = _fields(_ok(trial["user"].get(f"{REPORTS}/{trial['report']}")))
    assert {key: item["value"] for key, item in after.items()} == {key: item["value"] for key, item in before.items()}
    with SessionLocal() as db:
        bind_system(db, "test")
        call = (
            db.query(AiCall).filter(AiCall.tenant_id == trial["tenant_id"]).order_by(AiCall.created_at.desc()).first()
        )
        assert (call.feature, call.outcome, call.organisation_type) == ("code_suggestions", "ANSWERED", "TRIAL")


def test_confirm_all_codes_never_enters_an_ai_suggestion(trial, ai_on):
    body = _suggest(trial).json()
    field = body["suggestions"][0]["field_ids"][0]
    user, report = trial["user"], trial["report"]
    cleared = _fields(_ok(user.put(f"{REPORTS}/{report}/fields/{field}", json={"clear": True})))[field]
    mapped = cleared.get("suggestion")  # the approved mapping's suggestion, if any
    confirmed = user.post(f"{REPORTS}/{report}/codes/confirm")
    if mapped:
        assert confirmed.status_code == 200, confirmed.text
    else:
        assert confirmed.status_code == 422 and confirmed.json()["detail"]["code"] == "NOTHING_SUGGESTED"
    assert _fields(_ok(user.get(f"{REPORTS}/{report}")))[field]["value"] == (mapped or None)
    with SessionLocal() as db:
        bind_system(db, "test")
        assert "origin" not in (db.get(ReportObligation, uuid.UUID(report)).entries or {}).get(field, {})


def test_a_person_enters_one_suggested_code_through_its_field_and_it_is_audited(trial, ai_on):
    body = _suggest(trial).json()
    run = body["ai"]["ai_execution_id"]
    chosen = body["suggestions"][0]
    field = chosen["field_ids"][0]
    user, report = trial["user"], trial["report"]
    path = f"{REPORTS}/{report}/fields/{field}"
    # A code that run did not propose is refused when it claims to come from the run.
    other = next(code for code in trial["codes"] if code not in {item["code"] for item in body["suggestions"]})
    refused = user.put(path, json={"codes": [other], "ai_execution_id": run})
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "NOT_AI_SUGGESTED"
    entered = _fields(_ok(user.put(path, json={"codes": [chosen["code"]], "ai_execution_id": run})))[field]
    assert chosen["code"] in entered["value"]
    with SessionLocal() as db:
        bind_system(db, "test")
        entry = db.get(ReportObligation, uuid.UUID(report)).entries[field]
        assert (entry["origin"], entry["ai_execution_id"]) == ("AI_SUGGESTION", run)
        assert entry["confidence"] == {chosen["code"]: chosen["confidence"]}
        event = (
            db.query(AuditEvent)
            .filter(AuditEvent.tenant_id == trial["tenant_id"], AuditEvent.action == "REPORT_FIELD_SET")
            .order_by(AuditEvent.chain_seq.desc())
            .first()
        )
        assert event.details["ai_suggestion"] is True and event.details["ai_execution_id"] == run
        assert event.details["field"] == field and chosen["code"] in event.details["codes"]


def test_with_the_feature_switched_off_no_ai_service_is_called(trial, ai_on):
    _set_tenant(trial["tenant_id"], ai_features={})
    response = _suggest(trial)
    assert response.status_code == 200
    assert response.json() == {
        "suggestions": [],
        "ai": {
            "status": "REFUSED",
            "reason": "GENAI_FEATURE_OFF_FOR_ORGANIZATION",
            "message": response.json()["ai"]["message"],
        },
    }
    assert ai_on["sent"] == []
