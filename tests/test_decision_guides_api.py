"""0.10.59, T-G15: the customer's own decision guide versions on the starter engine, through the API as two trial users
(migration tr06): the version history with MDARIX's starter as version 1, editing within the rules (core questions
reworded, never removed; extra questions never drive the conclusion), the clause and basis on every question, the test
gate, the second person's approval, assessments keeping their version, and the export for an audit."""

from __future__ import annotations

import io
import uuid

import pytest

from backend.app.db.models.foundation import Complaint
from backend.app.db.models.guides_communications import DecisionGuideVersion
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from backend.app.decision_guides import rules
from backend.app.reportability import markets
from tests.test_free_trial import PASSWORD, _approved_trial_client
from tests.test_reporting_capa_api import PASSWORD as COLLEAGUE_PASSWORD
from tests.test_reporting_capa_api import _client

pytestmark = pytest.mark.db

GUIDES = "/api/v1/decision-guides"


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    colleague = _client(tenant_id, "LEADER", "Rahul Colleague")
    try:
        yield {"user": user, "colleague": colleague, "tenant_id": tenant_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:decision-guides-cleanup")


def _market(body: dict, market: str) -> dict:
    return next(item for item in body["markets"] if item["market"] == market)


# --------------------------------------------------------------------------------------------- the rules


@pytest.mark.unit
def test_every_starter_guide_passes_its_own_tests():
    for market in markets.MARKETS:
        results = rules.run(market, rules.starter_tests(market))
        assert results and all(item["passed"] for item in results), market


@pytest.mark.unit
def test_a_core_question_cannot_be_removed_and_extras_get_their_ids():
    base = [rules.question_dict(question) for question in rules.starter(markets.US).questions]
    _, problem = rules.clean_questions(markets.US, base[1:])
    assert problem and "US1" in problem and "cannot be removed" in problem
    extra = {"text": "Is the device used at home?", "clause": "", "basis": []}
    cleaned, problem = rules.clean_questions(markets.US, [extra, *reversed(base), {**extra, "id": "X1"}])
    assert problem is None
    assert [item["id"] for item in cleaned][: len(base)] == [item["id"] for item in base]  # core order kept
    assert [item["id"] for item in cleaned][len(base) :] == ["X2", "X1"] and all(item["extra"] for item in cleaned[-2:])
    built = rules.build(markets.US, "US-v2", cleaned)
    assert built.questions[0].starter and not built.questions[-1].starter and built.questions[-1].extra


@pytest.mark.unit
def test_a_question_without_its_clause_or_basis_blocks_publication():
    questions = [rules.question_dict(question) for question in rules.starter(markets.IN).questions]
    questions.append({"id": "X1", "text": "Is the device imported?", "clause": "", "basis": [], "extra": True})
    tests = rules.starter_tests(markets.IN)
    problems = rules.publish_problems(questions, tests, None, "f")
    assert "Question X1 has no regulation clause" in problems
    assert "Question X1 has no basis from the standards catalog" in problems
    assert "Run the test cases on this version's current content" in problems


@pytest.mark.unit
def test_a_test_that_expects_no_from_an_unknown_fails():
    tests, problem = rules.clean_tests(
        markets.US,
        [{"name": "Outcome unknown", "answers": {"US2B": "UNKNOWN", "US3": "YES"}, "expected": "NOT_REPORTABLE"}],
    )
    assert problem is None
    [result] = rules.run(markets.US, tests)
    assert result["actual"] == markets.PENDING and not result["passed"]
    _, problem = rules.clean_tests(markets.US, [{"name": "Extra", "answers": {"X1": "YES"}, "expected": "REPORTABLE"}])
    assert problem and "drives the conclusion" in problem


# --------------------------------------------------------------------------------------------- through the API


def test_the_sample_publishes_us_v2_and_holds_a_v3_draft_whose_test_fails(trial):
    body = _ok(trial["user"].get(GUIDES))
    us = _market(body, "US")
    assert us["current"]["code"] == "US-v2" and us["current"]["approved_by"] == "MDARIX sample approver"
    assert us["current"]["extra_questions"] == 1
    assert [item["code"] for item in us["history"]] == ["US-v3", "US-v2", "US-starter-1"]
    assert us["history"][-1]["state"] == "SUPERSEDED" and us["history"][-1]["starter"]
    assert us["open"]["code"] == "US-v3" and any("fail" in problem for problem in us["open"]["problems"])
    v2 = _ok(trial["user"].get(f"{GUIDES}/US/versions/2"))
    vmsr = next(q for q in v2["question_set"]["questions"] if q["extra"])
    assert vmsr["clause"] == "21 CFR 803.19 (VMSR program)" and vmsr["basis"] == ["CFR803_19"]
    assert next(q for q in v2["question_set"]["questions"] if q["id"] == "US2A")["starter"] is False
    assert v2["signature"]["meaning"].startswith("I approve US-v2")
    assert v2["test_results"]["failed"] == 0 and v2["test_results"]["current"]
    # Every question of every version shows its clause.
    for market in markets.MARKETS:
        starter = _ok(trial["user"].get(f"{GUIDES}/{market}/versions/1"))
        assert starter["starter"] and all(q["clause"] and q["basis"] for q in starter["question_set"]["questions"])
    # The other markets still use MDARIX's starter.
    assert _market(body, "GB")["current"]["code"] == "GB-starter-1"


def test_assessments_started_after_publication_use_it_and_ones_in_progress_keep_theirs(trial):
    user = trial["user"]
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        ids = {
            row.complaint_identifier: str(row.id)
            for row in db.query(Complaint).filter(
                Complaint.tenant_id == trial["tenant_id"],
                Complaint.complaint_identifier.in_(["SAMPLE-RV-06", "SAMPLE-RV-08"]),
            )
        }
    pending = _ok(user.get(f"/api/v1/complaints/{ids['SAMPLE-RV-08']}/market-assessments"))
    us = next(item for item in pending["markets"] if item["market"] == "US")
    assert us["question_set"]["version"] == "US-starter-1" and us["question_set_current"] is False
    fresh = _ok(user.get(f"/api/v1/complaints/{ids['SAMPLE-RV-06']}/market-assessments"))
    us = next(item for item in fresh["markets"] if item["market"] == "US")
    assert us["question_set"]["version"] == "US-v2" and any(q["extra"] for q in us["question_set"]["questions"])
    # What a US signature relies on now is the organization's version.
    training = _ok(user.get("/api/v1/signer-training?documents=QUESTION_SET_US"))["documents"][0]
    assert training["version"] == "US-v2" and "your guide version US-v2" in training["title"]


def test_a_draft_is_edited_tested_and_approved_by_a_second_person(trial):
    user, colleague = trial["user"], trial["colleague"]
    draft = _ok(user.post(f"{GUIDES}/GB/drafts"))
    assert draft["version"] == 2 and draft["code"] == "GB-v2" and draft["state"] == "DRAFT"
    assert user.post(f"{GUIDES}/GB/drafts").status_code == 409  # one version prepared at a time
    questions = draft["question_set"]["questions"]
    questions[0] = {**questions[0], "note": "Our procedure: an incident includes a use error (sample)."}
    extra = {"text": "Was the unit placed on the GB market before 16 June 2025?", "clause": "", "basis": []}
    saved = _ok(
        user.put(
            f"{GUIDES}/GB/versions/2",
            json={"questions": [*questions, extra], "test_cases": draft["test_cases"]},
        )
    )
    assert "Question X1 has no regulation clause" in saved["problems"]
    refused = user.post(f"{GUIDES}/GB/versions/2/approval-request", json={"change_reason": "Our own help text."})
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "NOT_READY_TO_PUBLISH"
    extra = {**extra, "clause": "UK MDR 2002 as amended by SI 2024/1368 (placing on the market)", "basis": ["UK_MDR"]}
    saved = _ok(
        user.put(
            f"{GUIDES}/GB/versions/2",
            json={"questions": [*questions, extra], "test_cases": draft["test_cases"]},
        )
    )
    assert saved["problems"] == ["Run the test cases on this version's current content"]
    tested = _ok(user.post(f"{GUIDES}/GB/versions/2/tests"))
    assert tested["test_results"]["failed"] == 0 and tested["problems"] == []
    asked = _ok(
        user.post(
            f"{GUIDES}/GB/versions/2/approval-request",
            json={"change_reason": "Our own help text on question 1 and the placing-on-market question."},
        )
    )
    assert asked["state"] == "AWAITING_APPROVAL"
    mine = user.post(f"{GUIDES}/GB/versions/2/approve", json={"password": PASSWORD})
    assert mine.status_code == 403 and mine.json()["detail"]["code"] == "SECOND_PERSON_REQUIRED"
    assert "You edited this version" in mine.json()["detail"]["message"]
    wrong = colleague.post(f"{GUIDES}/GB/versions/2/approve", json={"password": "not-the-password"})
    assert wrong.status_code == 403
    approved = _ok(colleague.post(f"{GUIDES}/GB/versions/2/approve", json={"password": COLLEAGUE_PASSWORD}))
    assert approved["state"] == "PUBLISHED" and approved["approved_by"] == "Rahul Colleague"
    assert approved["signature"]["signer_name"] == "Rahul Colleague"
    gb = _market(_ok(user.get(GUIDES)), "GB")
    assert gb["current"]["code"] == "GB-v2" and gb["history"][-1]["state"] == "SUPERSEDED"
    # Published: never edited again.
    again = user.put(f"{GUIDES}/GB/versions/2", json={"questions": questions, "test_cases": draft["test_cases"]})
    assert again.status_code == 409


def test_editing_a_version_awaiting_approval_returns_it_to_draft(trial):
    user = trial["user"]
    draft = _ok(user.post(f"{GUIDES}/IN/drafts"))
    _ok(user.post(f"{GUIDES}/IN/versions/2/tests"))
    _ok(user.post(f"{GUIDES}/IN/versions/2/approval-request", json={"change_reason": "Adopting the starter as ours."}))
    saved = _ok(
        user.put(
            f"{GUIDES}/IN/versions/2",
            json={"questions": draft["question_set"]["questions"], "test_cases": draft["test_cases"][:1]},
        )
    )
    assert saved["state"] == "DRAFT" and saved["test_results"]["current"] is False
    assert _ok(user.post(f"{GUIDES}/IN/versions/2/discard"))["state"] == "DISCARDED"


def test_the_export_carries_every_question_clause_test_and_the_approval(trial):
    from docx import Document

    user = trial["user"]
    pdf = user.get(f"{GUIDES}/US/versions/2/guide.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    docx = user.get(f"{GUIDES}/US/versions/3/guide.docx")
    assert docx.status_code == 200
    text = "\n".join(paragraph.text for paragraph in Document(io.BytesIO(docx.content)).paragraphs)
    assert "21 CFR 803.19 (VMSR program)" in text and "FAILED" in text and "Not approved" in text
    assert "Practice record" in text
    assert user.get(f"{GUIDES}/US/versions/2/guide.txt").status_code == 404


def test_another_organization_reads_none_of_it(trial):
    other, _, _ = _approved_trial_client()
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        assert db.query(DecisionGuideVersion).filter(DecisionGuideVersion.tenant_id == trial["tenant_id"]).count()
    gb = _market(_ok(other.get(GUIDES)), "GB")
    assert gb["current"]["code"] == "GB-starter-1"
    assert other.get(f"{GUIDES}/GB/versions/2").status_code == 404
