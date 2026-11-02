"""Release B (0.10.72) of the "Simplicity and WoW" plan, "Show less, by default": the server half of each task.

B1: the market assessment's factual answers arrive from the complaint record, each with its source, for the person to
confirm or correct; judgement questions and the conclusion never do; Unknown is never read as No; each answer keeps
whether it was a confirmed suggestion, a corrected one or entered, on the signed record and in the audit trail.
"""

from __future__ import annotations

import pytest

from backend.app.reportability import markets

pytestmark = pytest.mark.unit

RV11 = {"death": False, "serious_injury": False, "malfunction": True, "patient_involved": True}


def test_b1_prefills_only_the_facts_the_record_states():
    assert markets.suggestions(markets.US_SET, RV11) == {
        "US1": {
            "answer": "NO",
            "source": "From the complaint record: no death was reported",
            "evidence": "Patient outcome fields",
        },
        **{
            key: {
                "answer": "NO",
                "source": "From the complaint record: no serious injury was reported",
                "evidence": "Patient outcome fields",
            }
            for key in ("US2A", "US2B", "US2C")
        },
        "US4": {
            "answer": "YES",
            "source": "From the complaint record: a malfunction was reported",
            "evidence": "Malfunction field",
        },
    }
    assert sorted(markets.suggestions(markets.IN_SET, RV11)) == ["IN2A", "IN2B", "IN2D", "IN2F"]
    # EU/NI and GB ask "might it have led to": a judgement, so nothing is suggested there.
    assert markets.suggestions(markets.EU_SET, RV11) == {} and markets.suggestions(markets.GB_SET, RV11) == {}


def test_b1_never_a_judgement_question():
    every = {"death": True, "serious_injury": False, "malfunction": False}
    for question_set in markets.QUESTION_SETS.values():
        assert not set(markets.suggestions(question_set, every)) & set(markets.JUDGEMENT_QUESTIONS)
    for question in ("US3", "US5", "US6", "IN1", "IN3"):
        assert question in markets.JUDGEMENT_QUESTIONS


def test_b1_unknown_is_never_turned_into_no():
    # The record silent (None) suggests nothing; a serious injury on the record suggests no criterion (a judgement).
    assert markets.suggestions(markets.US_SET, {"death": None, "serious_injury": None, "malfunction": None}) == {}
    assert (
        sorted(markets.suggestions(markets.US_SET, {"death": None, "serious_injury": True, "malfunction": None})) == []
    )
    found = markets.suggestions(markets.US_SET, {"death": True, "serious_injury": True, "malfunction": None})
    assert found == {
        "US1": {
            "answer": "YES",
            "source": "From the complaint record: a death was reported",
            "evidence": "Patient outcome fields",
        }
    }


def test_b1_confirmed_corrected_and_entered_are_recorded():
    offered = markets.suggestions(markets.US_SET, RV11)
    answers = {
        "US1": {"answer": "NO", "rationale": "x", "evidence": []},  # confirmed
        "US4": {"answer": "NO", "rationale": "x", "evidence": []},  # corrected (the record said Yes)
        "US2A": {"answer": "NO", "rationale": "x", "evidence": []},  # same as the record, but not confirmed: entered
        "US3": {"answer": "NO", "rationale": "x", "evidence": []},  # a judgement: entered
        "US5": {"answer": None, "rationale": "", "evidence": []},  # no answer: no origin
    }
    markets.mark_origins(answers, offered, {"US1"})
    assert markets.origins(answers) == {"US1": "CONFIRMED", "US4": "CORRECTED", "US2A": "ENTERED", "US3": "ENTERED"}
    assert answers["US4"]["suggested"] == "YES" and answers["US4"]["source"].startswith("From the complaint record")


# ------------------------------------------------------------------------------------------- F2: step 3's question

STORY = "/api/v1/trial/short-story"


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(scope="module")
def story_trial():
    from backend.app.db.session import SessionLocal
    from backend.app.trial.retention import purge_trial
    from tests.test_free_trial import _approved_trial_client

    user, approval, _ = _approved_trial_client()
    try:
        yield user
    finally:
        import uuid

        with SessionLocal() as db:
            purge_trial(db, uuid.UUID(approval["tenant_id"]), "test:release-b-story-cleanup")


def _request(user, complaint: str, party: str, owner: str, subject: str) -> dict:
    from datetime import date, datetime, timedelta, timezone

    return _ok(
        user.post(
            "/api/v1/communications",
            json={
                "complaint_id": complaint,
                "party_id": party,
                "direction": "SENT",
                "purpose": "INFORMATION_REQUEST",
                "subject": subject,
                "channel": "EMAIL",
                "occurred_at": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
                "owner_id": owner,
                "reply_due_on": (date.today() + timedelta(days=2)).isoformat(),
            },
        )
    )


@pytest.mark.db
def test_f2_step_3_is_the_consequence_question_and_the_summary_reads_its_state(story_trial):
    from datetime import datetime, timezone

    user = story_trial
    complaint = _ok(user.get(STORY))["complaint"]["id"]
    me = _ok(user.get("/api/v1/triage"))["people"][0]["id"]
    _ok(
        user.post(
            f"/api/v1/triage/COMPLAINT/{complaint}/record",
            json={"severity": "NEGLIGIBLE", "event_owner": me, "triage_owner": me, "immediate_action": "Out of use."},
        )
    )
    event = _ok(user.get("/api/v1/oversight/events/SAMPLE-RV-11"))
    _ok(
        user.put(
            f"/api/v1/oversight/events/{complaint}/service",
            json={"reference": event["service"]["reference"], "status": "IN_PROGRESS", "owner_id": me},
        )
    )
    assert _ok(user.get(STORY))["current"] == 2
    party = _ok(
        user.post(
            "/api/v1/communications/parties",
            json={"type": "HOSPITAL", "name": "Biomedical engineering (sample)", "complaint_id": complaint},
        )
    )["id"]

    # 1. An unrelated request does not complete step 3 (before 0.10.72 it did: any request with an owner and a date).
    _request(user, complaint, party, me, "When can the device be collected?")
    assert _ok(user.get(STORY))["current"] == 2

    # 2. The consequence question, kept with the story: step 3 done, the consequence unknown while it is open.
    asked = _request(user, complaint, party, me, "Did any treatment decision rely on the high SpO2 readings?")
    story = _ok(user.post(f"{STORY}/marks", json={"step": "question", "request_id": asked["id"]}))
    assert story["current"] == 3 and story["question"]["asked"]["id"] == asked["id"]
    assert (story["question"]["consequence_state"], story["question"]["consequence"]) == (
        "UNKNOWN",
        "Not known until the hospital answers",
    )
    # A later unrelated request changes nothing.
    _request(user, complaint, party, me, "Please confirm the service address.")
    assert _ok(user.get(STORY))["question"]["asked"]["id"] == asked["id"]

    # 3. Answered: the summary shows the answer and its date, and asks to reassess.
    _ok(
        user.post(
            f"/api/v1/communications/{asked['id']}/reply",
            json={
                "received_at": datetime.now(timezone.utc).isoformat(),
                "channel": "EMAIL",
                "summary": "No: oxygen was set from blood gases, not from the monitor",
            },
        )
    )
    question = _ok(user.get(STORY))["question"]
    assert question["consequence_state"] == "ANSWERED"
    assert question["answer"] == "No: oxygen was set from blood gases, not from the monitor"
    assert question["answered_on"] and question["consequence"].startswith(
        f"The hospital answered on {question['answered_on']}"
    )
    assert "Reassess" in question["consequence"]


@pytest.mark.db
def test_b5_a_rising_group_names_its_lots_from_one_count(story_trial):
    """B5: the lead sentence names the rising group's lots; the board's groups assessed is the one number the headline
    and the tile both read (addendum: "2 groups checked" beside a tile of 6)."""
    board = _ok(story_trial.get("/api/v1/triage/trends", params={"group": "version"}))
    rising = [item for item in board["items"] if item["result"] == "SIGNIFICANT"]
    assert [item["name"] for item in rising] == ["OrbitCare 300 Infusion Pump (Sample) Rev B"]
    # The sample's nine recent Rev B complaints come from lots 003 and 004, and one from 005.
    assert rising[0]["lots"] == ["SAMPLE-ORBIT-300-LOT-003", "SAMPLE-ORBIT-300-LOT-004", "SAMPLE-ORBIT-300-LOT-005"]
    assert (rising[0]["recent"], round(rising[0]["ratio"], 1)) == (9, 9.3)
    assert board["summary"]["groups_tested"] == 2 and board["summary"]["groups"] == 6


@pytest.mark.db
def test_addendum_2_sample_only_chosen_on_the_approval_is_set_at_creation_and_audited():
    import uuid

    from fastapi.testclient import TestClient

    from backend.app.db.models.foundation import AuditEvent, Tenant
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_system
    from backend.app.main import app
    from backend.app.trial.retention import purge_trial
    from tests.conftest import authenticated_client
    from tests.test_free_trial import PASSWORD, _activation_token, _request_id, _request_trial

    admin = authenticated_client()
    made = []
    try:
        for sample_only in (True, False):
            email = _request_trial()
            path = f"/api/v1/platform-admin/trial-requests/{_request_id(admin, email)}/approve"
            body = _ok(admin.post(path, json={"sample_only": True}) if sample_only else admin.post(path))
            made.append(uuid.UUID(body["tenant_id"]))
            with SessionLocal() as db:
                bind_system(db, "test: sample only on the approval")
                assert db.get(Tenant, made[-1]).sample_only is sample_only
                audit = (
                    db.query(AuditEvent)
                    .filter(AuditEvent.entity_id == made[-1], AuditEvent.action == "TRIAL_REQUEST_APPROVED")
                    .one()
                )
                assert audit.details["sample_only"] is sample_only
            if sample_only:
                user = TestClient(app)
                _ok(
                    user.post(
                        "/api/v1/auth/activate-account",
                        json={"token": _activation_token(body, email), "password": PASSWORD},
                    )
                )
                _ok(user.post("/api/v1/auth/signin", json={"email": email, "password": PASSWORD}))
                refused = user.post(
                    "/api/v1/data/import/complaints/check",
                    content=b"complaint_id,description\nX-1,Test\n",
                    headers={"Content-Type": "text/csv"},
                )
                assert refused.status_code == 403 and refused.json()["detail"]["code"] == "SAMPLE_ONLY_TRIAL"
    finally:
        with SessionLocal() as db:
            for tenant_id in made:
                purge_trial(db, tenant_id, "test:release-b-sample-only-cleanup")


@pytest.mark.db
def test_addenda_sample_corrections_new_trials_have_them_and_the_refresh_records_them_once(story_trial):
    """A new trial maps SPO2_READING_HIGH to IMDRF A0908 and its guide's examples read without "Sample examples:";
    a trial made before 0.10.72 is corrected by scripts/refresh_trial_story.py once (dry run first), the guide's
    approval re-recorded on the new fingerprint."""
    import uuid

    from backend.app.db.models.foundation import SignedApprovalRecord
    from backend.app.db.models.guides_communications import DecisionGuideVersion
    from backend.app.db.models.regulatory_reference import ImdrfCodeMapping
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_tenant
    from backend.app.decision_guides.router import _fingerprint
    from backend.app.human_decision.rules import signature_hash
    from backend.app.trial import sample_0_10_72

    user = story_trial
    tenant_id = uuid.UUID(_ok(user.get("/api/v1/session/context"))["tenant_id"])
    # The flagship's code shows its IMDRF term, as the other sample codes do.
    event = _ok(user.get("/api/v1/oversight/events/SAMPLE-RV-11"))
    assert event["event"]["problem_code"] == "SPO2_READING_HIGH"
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        links = db.query(ImdrfCodeMapping).filter(
            ImdrfCodeMapping.tenant_id == tenant_id, ImdrfCodeMapping.customer_code == "SPO2_READING_HIGH"
        )
        assert [row.imdrf_code for row in links] == ["A0908"]
        assert sample_0_10_72.refresh(db, tenant_id, apply=False) == 0  # a new trial has them
        # As a trial made before 0.10.72 had them: no link, and the old example text in the signed guide.
        links.delete()
        guide = (
            db.query(DecisionGuideVersion)
            .filter(DecisionGuideVersion.tenant_id == tenant_id, DecisionGuideVersion.content_fingerprint.is_not(None))
            .one()
        )
        guide.questions = [
            {**item, "examples": f"Sample examples: {item['examples']}"} if item.get("examples") else item
            for item in guide.questions
        ]
        db.flush()
        assert sample_0_10_72.refresh(db, tenant_id, apply=False) == 2
        assert links.count() == 0  # the dry run changes nothing
        assert sample_0_10_72.refresh(db, tenant_id, apply=True) == 2
        assert sample_0_10_72.refresh(db, tenant_id, apply=True) == 0  # idempotent
        assert [row.imdrf_code for row in links] == ["A0908"]
        assert not any(str(item.get("examples") or "").startswith("Sample examples") for item in guide.questions)
        record = db.get(SignedApprovalRecord, guide.signed_record_id)
        fingerprint = _fingerprint(guide.market, guide.code, guide.questions, guide.test_cases or [])
        assert guide.content_fingerprint == record.content_fingerprint == fingerprint
        assert record.signature_hash == signature_hash(fingerprint, record.signer_user_id, guide.code)
        db.commit()
