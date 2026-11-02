"""The Regulatory copilot drafts with the model from authorized records only, and approval re-authenticates."""

import uuid

import pytest
from sqlalchemy import text

from backend.app.db.session import engine
from genai.provider import GenAIProvider, GenAIResult, GenAIUnavailable
from tests.reports_seed import PASSWORD, cleanup, role_client, seed_case

DRAFT = "/api/v1/regulatory/draft"


@pytest.fixture(scope="module")
def seeded():
    seed = seed_case()
    yield seed
    cleanup(seed)


def _draft(client, **changes):
    body = {"document_type": "IFU", "document_identifier": f"REG-COP-{uuid.uuid4().hex[:8]}", **changes}
    response = client.post(DRAFT, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_without_a_configured_provider_the_draft_is_rules_only():
    body = _draft(role_client("INVESTIGATOR")[0])
    assert body["status"] == "RULES_ONLY" and body["reason_code"] == "GENAI_PROVIDER_NOT_CONFIGURED"
    assert body["human_review_required"] is True and body["authoritative"] is False
    assert body["user_message"]
    sections = [item for item in body["draft"]["sections"] if item.get("section_id")]
    assert sections and all("ai_draft" not in item for item in sections)


@pytest.mark.parametrize(
    "reason, code",
    [
        ("GENAI_DISABLED_FOR_ORGANIZATION", "GENAI_DISABLED_FOR_ORGANIZATION"),
        ("GENAI_MONTHLY_BUDGET_REACHED", "GENAI_MONTHLY_BUDGET_REACHED"),
        ("GENAI_PROVIDER_NOT_ALLOWED", "GENAI_PROVIDER_NOT_ALLOWED"),
        ("GENAI_PROVIDER_UNAVAILABLE: URLError", "GENAI_UNAVAILABLE"),
    ],
)
def test_a_refused_model_gives_the_layout_with_the_reason(monkeypatch, reason, code):
    def refuse(self, *args, **kwargs):
        raise GenAIUnavailable(reason)

    monkeypatch.setattr(GenAIProvider, "complete", refuse)
    body = _draft(role_client("INVESTIGATOR")[0])
    assert body["status"] == "RULES_ONLY" and body["reason_code"] == code
    assert "URLError" not in body["user_message"]


def test_the_model_drafts_from_the_case_and_its_citations_are_checked(monkeypatch, seeded):
    tag = seeded["tag"]
    seen = {}

    def answer(self, prompt, context=None, **kwargs):
        seen["prompt"], seen["context"], seen["evidence"] = prompt, context, kwargs.get("evidence")
        text_ = (
            "## intended_purpose\nThe pump delivers fluids [EV-" + tag + "-1].\n\n"
            "## warnings_and_precautions\nOcclusion alarms were reported [EV-NOT-GIVEN-9].\n\n"
            "## instructions\nThe drift caused the alarms."
        )
        return GenAIResult("test", "test-model", "1", {"answer": text_}, 10, 10, 0.0, 5)

    monkeypatch.setattr(GenAIProvider, "complete", answer)
    body = _draft(role_client("INVESTIGATOR")[0], investigation_id=seeded["investigation_id"], title="Pump IFU")
    assert body["status"] == "AI_DRAFTED" and body["authoritative"] is False and body["human_review_required"]
    sections = {item["section_id"]: item for item in body["draft"]["sections"] if item.get("section_id")}
    assert sections["intended_purpose"]["ai_draft"].startswith("The pump delivers fluids")
    assert sections["intended_purpose"]["ai_checks"]["flagged"] is False
    assert sections["warnings_and_precautions"]["ai_checks"]["unverified_citations"] == ["EV-NOT-GIVEN-9"]
    assert sections["instructions"]["ai_checks"]["causal_or_decision_wording"] is True
    assistance = body["draft"]["ai_assistance"]
    assert set(assistance["checks"]["flagged_sections"]) == {"warnings_and_precautions", "instructions"}
    assert f"EV-{tag}-1" in assistance["checks"]["evidence_available"]
    # The model saw only this organization's case: its evidence and the request, never another tenant's records.
    sent = str(seen["context"]) + str(seen["evidence"])
    assert f"EV-{tag}-1" in sent and "regulatory_draft" in seen["prompt"]


def test_a_case_of_another_organization_is_refused():
    response = role_client("INVESTIGATOR")[0].post(
        DRAFT, json={"document_type": "IFU", "investigation_id": str(uuid.uuid4())}
    )
    assert response.status_code == 404 and response.json()["detail"]["code"] == "INVESTIGATION_NOT_FOUND"


def _in_review(author):
    body = _draft(author)
    document_id = body["document_id"]
    moved = author.post(
        f"/api/v1/regulatory/documents/{document_id}/status",
        json={"status": "IN_REVIEW", "expected_lock_version": 1, "reason": "Ready"},
    )
    assert moved.status_code == 200, moved.text
    return document_id


def _approve(client, document_id, **credentials):
    return client.post(
        f"/api/v1/regulatory/documents/{document_id}/status",
        json={"status": "APPROVED", "expected_lock_version": 2, "reason": "Reviewed", **credentials},
    )


def _failures(user_id) -> int:
    with engine.connect() as connection:
        return (
            connection.execute(
                text("SELECT failure_count FROM login_throttles WHERE identifier = :key"), {"key": f"sign:{user_id}"}
            ).scalar()
            or 0
        )


def test_approval_needs_the_approvers_password(monkeypatch):
    author = role_client("INVESTIGATOR")[0]
    approver, approver_id = role_client("APPROVER")
    document_id = _in_review(author)
    missing = _approve(approver, document_id)
    assert missing.status_code == 403 and missing.json()["detail"]["code"] == "REAUTHENTICATION_REQUIRED"
    before = _failures(approver_id)
    wrong = _approve(approver, document_id, password="not the password")
    assert wrong.status_code == 403 and wrong.json()["detail"]["code"] == "INVALID_REAUTHENTICATION"
    assert _failures(approver_id) == before + 1
    approved = _approve(approver, document_id, password=PASSWORD)
    assert approved.status_code == 200 and approved.json()["status"] == "APPROVED"
    with engine.connect() as connection:
        actions = [
            row[0]
            for row in connection.execute(
                text("SELECT action FROM audit_events WHERE entity_id = :id ORDER BY created_at"), {"id": document_id}
            )
        ]
    assert "SIGNATURE_REAUTHENTICATION_FAILED" in actions and "REGULATORY_DOCUMENT_APPROVED" in actions


def test_approval_needs_an_authenticator_code_when_signatures_require_mfa(monkeypatch):
    monkeypatch.setenv("MDARIX_REQUIRE_MFA_FOR_SIGNATURES", "true")
    author = role_client("INVESTIGATOR")[0]
    approver = role_client("APPROVER")[0]
    document_id = _in_review(author)
    refused = _approve(approver, document_id, password=PASSWORD)
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "SIGNATURE_MFA_NOT_SET_UP"


def test_an_administrator_cannot_approve_a_regulatory_document():
    author = role_client("INVESTIGATOR")[0]
    document_id = _in_review(author)
    refused = _approve(role_client("PLATFORM_ADMIN")[0], document_id, password=PASSWORD)
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "ADMINISTRATOR_CANNOT_SIGN"
