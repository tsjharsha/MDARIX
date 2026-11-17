"""Per-market seriousness and causation assessment through the API (T-G15S, T-G15H, T-G40P), with migration tr01's
tables: drafts, the practice training before signing, signing with password (and authenticator code when required),
versions, the filing, earlier single decisions, Readiness, tenant isolation, and the sample answers of a free trial
with their removal."""

from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.db.models.foundation import AuditEvent, Complaint, SignedApprovalRecord
from backend.app.db.models.market_assessment import (
    ComplaintClassification,
    ComplaintMarketAssessment,
    SignerTrainingRecord,
)
from backend.app.db.models.reportability import ComplaintReportability
from backend.app.db.models.stage2 import SubscriptionLifecycle
from backend.app.db.session import RuntimeSessionLocal, SessionLocal, runtime_role_active
from backend.app.db.tenant_scope import bind_system, bind_tenant
from backend.app.reportability import markets
from tests.test_reporting_capa_api import (
    PASSWORD,
    REASON,
    SETTINGS,
    TODAY,
    WATCH,
    _client,
    _complaint,
    _organization,
    _product,
)

pytestmark = pytest.mark.db

WHY = "Read from the complaint record and the nurse's report"
TRAINING = "/api/v1/signer-training"


def _answers(**values: str) -> dict:
    return {
        key: {"answer": value, "rationale": WHY, "evidence": ["Complaint description"]} for key, value in values.items()
    }


US_SERIOUS = dict(US1="NO", US2A="UNKNOWN", US2B="NO", US2C="YES", US3="YES", US4="YES", US5="YES", US6="NO")
US_NONE = dict(
    US1="NO", US2A="NO", US2B="NO", US2C="NO", US3="NOT_APPLICABLE", US4="NO", US5="NOT_APPLICABLE", US6="NO"
)


def _on_free_trial(tenant_id) -> None:
    """Put an organization on the Free Trial plan: its training records are practice acknowledgements."""
    from backend.app.trial.service import _free_trial_plan

    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        plan = _free_trial_plan(db, now)
        db.add(
            SubscriptionLifecycle(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                plan_id=plan.id,
                plan_version=plan.version,
                starts_at=now,
                expires_at=now + timedelta(days=30),
                status="ACTIVE",
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()


def _windows(client) -> None:
    settings = client.get(SETTINGS).json()
    saved = client.put(SETTINGS, json={"windows": settings["templates"][:3], "lookback_days": 365, "reason": REASON})
    assert saved.status_code == 200, saved.text


@pytest.fixture(scope="module")
def org():
    from backend.app.trial.retention import purge_trial

    tenant_id = _organization("MA")
    _on_free_trial(tenant_id)
    other_id = _organization("MB")
    clients = {
        "regulatory": _client(tenant_id, "REGULATORY_REVIEWER", "Rita Regulatory"),
        "approver": _client(tenant_id, "APPROVER", "Alex Approver"),
        "viewer": _client(tenant_id, "VIEWER"),
        "other": _client(other_id, "REGULATORY_REVIEWER"),
    }
    _windows(clients["regulatory"])
    try:
        yield {"tenant_id": tenant_id, "other_id": other_id, "product": _product(tenant_id), **clients}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:market-assessment-cleanup")
            purge_trial(db, other_id, "test:market-assessment-cleanup")


def _url(complaint_id: str, market: str | None = None, tail: str = "") -> str:
    base = f"/api/v1/complaints/{complaint_id}/market-assessments"
    return f"{base}/{market}{tail}" if market else base


def _market(detail: dict, market: str) -> dict:
    return next(item for item in detail["markets"] if item["market"] == market)


def _acknowledge(client, market: str = "US") -> None:
    for document in client.get(f"{TRAINING}?documents=QUESTION_SET_{market},HARM_SCALE").json()["documents"]:
        done = client.post(
            f"{TRAINING}/{document['code']}/acknowledge",
            json={"version": document["version"], "statement": document["statement"]},
        )
        assert done.status_code == 200, done.text


def _save(client, complaint_id: str, market: str, answers: dict, **harm) -> dict:
    saved = client.put(_url(complaint_id, market), json={"answers": answers, **harm})
    assert saved.status_code == 200, saved.text
    return _market(saved.json(), market)


def _sign(client, complaint_id: str, market: str, item: dict, conclusion: str, **extra):
    draft = item["draft"]
    body = {"conclusion": conclusion, "version": draft["version"], "saved_at": draft["saved_at"], "password": PASSWORD}
    # A re-signed market says why it changes (OD-4, 0.10.88; refused without one in test_release_0_10_88_resign.py);
    # a first signature ignores it.
    body["change_reason"] = "The answers changed after new information on the complaint."
    return client.post(_url(complaint_id, market, "/sign"), json={**body, **extra})


def test_a_serious_us_complaint_is_assessed_trained_signed_versioned_and_filed(org):
    regulatory = org["regulatory"]
    complaint = _complaint(
        org["tenant_id"],
        org["product"],
        country="US",
        patient_involved=True,
        serious_injury=True,
        death=False,
        malfunction=True,
        severity="Critical",
        aware_days_ago=24,
    )
    detail = regulatory.get(_url(complaint)).json()
    assert detail["enabled_markets"] == ["US", "EU_NI"] and detail["preselected"] == "US"
    assert detail["severity_level"] == "CRITICAL" and detail["scale"]["version"] == "scale-starter-1"
    us = _market(detail, "US")
    assert us["question_set"]["version"] == "US-starter-1" and us["threshold"]["level"] == "SERIOUS"
    assert all(q["clause"] and q["starter"] for q in us["question_set"]["questions"])
    assert detail["starter_mark"] == "Starter, for your consultant to confirm."
    assert [item["state"] for item in us["training"]] == ["MISSING", "MISSING"]
    assert us["clock"] is None and us["draft"] is None  # the complaint's own window clock binds until assessed

    assert org["viewer"].put(_url(complaint, "US"), json={"answers": {}}).status_code == 403
    item = _save(regulatory, complaint, "US", _answers(**US_SERIOUS), harm_level="CRITICAL")
    assert item["evaluation"]["suggested"] == "REPORTABLE" and item["evaluation"]["report_type"] == "US_30_DAY"
    assert item["draft"]["version"] == 1 and item["disagreement"] is None
    assert item["clock"]["state"] == "RUNNING" and item["clock"]["window"].startswith("FDA MDR")

    # The practice training on the current question set and scale comes first, with the reason and a way to it.
    untrained = _sign(regulatory, complaint, "US", item, "REPORTABLE")
    assert untrained.status_code == 409, untrained.text
    refused = untrained.json()["detail"]
    assert refused["code"] == "TRAINING_REQUIRED" and "US-starter-1" in refused["message"]
    assert {doc["code"] for doc in refused["missing"]} == {"QUESTION_SET_US", "HARM_SCALE"}
    wrong = regulatory.post(
        f"{TRAINING}/HARM_SCALE/acknowledge", json={"version": "scale-starter-1", "statement": "OK"}
    )
    assert wrong.status_code == 422 and wrong.json()["detail"]["code"] == "STATEMENT_REQUIRED"
    _acknowledge(regulatory)
    trained = regulatory.get(f"{TRAINING}?documents=QUESTION_SET_US,HARM_SCALE").json()["documents"]
    assert [doc["state"] for doc in trained] == ["CURRENT", "CURRENT"]
    assert trained[0]["method"] == "practice acknowledgement in a free trial"

    bad = _sign(regulatory, complaint, "US", item, "REPORTABLE", password="not the password")
    assert bad.status_code == 403 and bad.json()["detail"]["code"] == "INVALID_REAUTHENTICATION"
    stale = _sign(
        regulatory, complaint, "US", {"draft": {**item["draft"], "saved_at": "2020-01-01T00:00:00+00:00"}}, "REPORTABLE"
    )
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "DRAFT_CHANGED"
    signed = _sign(regulatory, complaint, "US", item, "REPORTABLE")
    assert signed.status_code == 200, signed.text
    us = _market(signed.json(), "US")
    current = us["current"]
    assert current["conclusion"] == "REPORTABLE" and current["report_type"] == "US_30_DAY"
    assert current["signed_by"] == "Rita Regulatory" and len(current["content_fingerprint"]) == 64
    assert current["answers"]["US2C"]["answer"] == "YES" and current["harm_level"] == "CRITICAL"
    assert current["due_on"] == (TODAY - timedelta(days=24) + timedelta(days=30)).isoformat()
    assert us["draft"] is None and signed.json()["practice_label"].startswith("Practice record")
    with SessionLocal() as db:
        bind_tenant(db, org["tenant_id"])
        record = db.get(SignedApprovalRecord, uuid.UUID(current["signed_record_id"]))
        assert record.object_type == "ComplaintMarketAssessment" and record.decision == "REPORTABLE"
        assert "with its questions, MDARIX starter, version 1" in record.signature_meaning
        assert "harm-severity scale, MDARIX starter, version 1" in record.signature_meaning

    # Reportable but not yet filed: still on the watch; the filing settles it.
    watched = next(item for item in regulatory.get(f"{WATCH}?show=all").json()["items"] if item["id"] == complaint)
    assert watched["state"] != "DECIDED" and watched["markets"][0]["state"] == "REPORTABLE"
    future = regulatory.post(
        _url(complaint, "US", "/filing"),
        json={"filing_reference": "MDR-2026-0042", "filed_on": (TODAY + timedelta(days=1)).isoformat()},
    )
    assert future.status_code == 422
    filed = regulatory.post(
        _url(complaint, "US", "/filing"), json={"filing_reference": "MDR-2026-0042", "filed_on": TODAY.isoformat()}
    )
    assert filed.status_code == 200, filed.text
    watched = next(item for item in regulatory.get(f"{WATCH}?show=all").json()["items"] if item["id"] == complaint)
    assert watched["state"] == "DECIDED" and watched["markets"][0]["filed"] is True

    # A signed version is never edited: a change is version 2, and version 1 stays visible as superseded.
    item = _save(regulatory, complaint, "US", _answers(**{**US_SERIOUS, "US6": "YES"}), harm_level="CRITICAL")
    assert item["draft"]["version"] == 2 and item["current"]["version"] == 1
    signed = _sign(org["approver"], complaint, "US", item, "REPORTABLE")
    assert signed.status_code == 409 and signed.json()["detail"]["code"] == "TRAINING_REQUIRED"
    assert signed.json()["detail"]["trained_colleagues"] == ["Rita Regulatory"]
    signed = _sign(regulatory, complaint, "US", item, "REPORTABLE")
    assert signed.status_code == 200, signed.text
    us = _market(signed.json(), "US")
    assert us["current"]["version"] == 2 and us["current"]["report_type"] == "US_5_WORK_DAY"
    assert [(row["version"], row["superseded"]) for row in us["history"]] == [(1, True)]
    with SessionLocal() as db:
        bind_system(db, "test: read the audit trail")
        actions = [
            row.action
            for row in db.query(AuditEvent)
            .filter(AuditEvent.entity_id == uuid.UUID(complaint))
            .order_by(AuditEvent.created_at)
        ]
    assert actions.count("COMPLAINT_MARKET_CONCLUSION_SIGNED") == 2
    assert "COMPLAINT_MARKET_ASSESSMENT_STARTED" in actions and "COMPLAINT_MARKET_FILING_RECORDED" in actions


def test_unknown_stays_pending_and_an_override_needs_a_reason(org):
    regulatory = org["regulatory"]
    _acknowledge(regulatory)
    complaint = _complaint(org["tenant_id"], org["product"], country="US", patient_involved=True, malfunction=True)
    pending = _answers(
        US1="NO", US2A="UNKNOWN", US2B="UNKNOWN", US2C="UNKNOWN", US3="UNKNOWN", US4="YES", US5="UNKNOWN", US6="UNKNOWN"
    )
    item = _save(regulatory, complaint, "US", pending, harm_level="MINOR")
    assert item["evaluation"]["suggested"] == "PENDING_INFORMATION"
    # Still counting: an unanswered question 6 keeps the 5-work-day report, the earliest (code audit 3, fix 3).
    assert item["clock"]["window"] == "5-work-day report (21 CFR 803.53)"
    refused = _sign(regulatory, complaint, "US", item, "NOT_REPORTABLE", override_reason="We are sure it is fine")
    assert refused.status_code == 422 and "Unknown is never No" in refused.json()["detail"]["message"]
    no_reason = _sign(regulatory, complaint, "US", item, "REPORTABLE")
    assert no_reason.status_code == 422 and "override" in no_reason.json()["detail"]["message"]
    signed = _sign(regulatory, complaint, "US", item, "REPORTABLE", override_reason="Report when unsure: QP-08 step 5")
    assert signed.status_code == 200, signed.text
    current = _market(signed.json(), "US")["current"]
    assert current["suggested_conclusion"] == "PENDING_INFORMATION" and current["conclusion"] == "REPORTABLE"
    assert current["override_reason"] == "Report when unsure: QP-08 step 5"


def test_question_5_no_needs_its_reason_and_an_answer_against_the_scale_needs_one_listed_on_readiness(org):
    from backend.app.readiness_home.service import reporting_clocks

    regulatory = org["regulatory"]
    _acknowledge(regulatory)
    complaint = _complaint(
        org["tenant_id"],
        org["product"],
        country="US",
        patient_involved=True,
        serious_injury=True,
        malfunction=True,
        severity="Critical",
    )
    no_reason = {**_answers(**US_NONE), "US5": {"answer": "NO", "rationale": "", "evidence": []}}
    item = _save(
        regulatory, complaint, "US", {**no_reason, "US4": {"answer": "YES", "rationale": WHY}}, harm_level="CRITICAL"
    )
    refused = _sign(regulatory, complaint, "US", item, "NOT_REPORTABLE")
    assert refused.status_code == 422 and refused.json()["detail"]["message"].startswith("Question US5 is No")

    item = _save(regulatory, complaint, "US", _answers(**US_NONE), harm_level="CRITICAL")
    assert "US serious injury threshold" in item["disagreement"]
    refused = _sign(regulatory, complaint, "US", item, "NOT_REPORTABLE")
    assert refused.status_code == 422 and "written reason" in refused.json()["detail"]["message"]
    lowered = regulatory.put(
        _url(complaint, "US"), json={"answers": _answers(**US_NONE), "harm_level": "MINOR", "harm_code": "DEATH"}
    )
    assert lowered.status_code == 422 and "cannot be lowered" in lowered.json()["detail"]["message"]
    item = _save(
        regulatory,
        complaint,
        "US",
        _answers(**US_NONE),
        harm_level="CRITICAL",
        scale_disagreement_reason="The QMS severity records the hazard, not this event: the patient was unharmed",
    )
    signed = _sign(regulatory, complaint, "US", item, "NOT_REPORTABLE")
    assert signed.status_code == 200, signed.text
    assert _market(signed.json(), "US")["current"]["scale_disagreement_reason"].startswith("The QMS severity")
    with SessionLocal() as db:
        bind_tenant(db, org["tenant_id"])
        check = reporting_clocks(db, org["tenant_id"], TODAY)
    assert any(entry["id"] == complaint and "against the scale" in entry["ref"] for entry in check["items"])
    assert check["scale_disagreements"] >= 1 and "against the harm-severity scale" in check["detail"]


def test_a_changed_version_makes_the_acknowledgement_out_of_date(org, monkeypatch):
    regulatory = org["regulatory"]
    _acknowledge(regulatory)
    complaint = _complaint(org["tenant_id"], org["product"], country="US", malfunction=True)
    newer = dataclasses.replace(markets.US_SET, version="US-starter-2")
    monkeypatch.setitem(markets.QUESTION_SETS, "US", newer)
    states = regulatory.get(f"{TRAINING}?documents=QUESTION_SET_US").json()["documents"]
    assert states[0]["state"] == "OUT_OF_DATE" and states[0]["held_version"] == "US-starter-1"
    item = _save(regulatory, complaint, "US", _answers(**{**US_NONE, "US4": "YES", "US5": "YES"}), harm_level="MINOR")
    refused = _sign(regulatory, complaint, "US", item, "REPORTABLE")
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "TRAINING_REQUIRED"
    assert [doc["version"] for doc in refused.json()["detail"]["missing"]] == ["US-starter-2"]


def test_the_training_rule_binds_every_organization_not_only_a_trial(org):
    """RSK-011 (owner, 12 Nov 2026, replacing decision 6): a non-trial organization's signer is refused until they
    record the current versions, with a clear message and the documents to confirm; then the signature goes through."""
    from backend.app.trial.retention import purge_trial

    complaint = _complaint(org["tenant_id"], org["product"], country="US", malfunction=True)
    trial = org["regulatory"].get(_url(complaint)).json()
    assert trial["training_required"] is True and trial["practice_label"]

    tenant_id = _organization("MN")  # no training record in the organization at all
    try:
        signer = _client(tenant_id, "REGULATORY_REVIEWER", "Nina Pilot")
        _windows(signer)
        complaint = _complaint(tenant_id, _product(tenant_id), country="US", malfunction=True)
        detail = signer.get(_url(complaint)).json()
        assert detail["training_required"] is True and detail["practice_label"] is None
        assert [entry["state"] for entry in _market(detail, "US")["training"]] == ["MISSING", "MISSING"]
        answers = _answers(**{**US_NONE, "US4": "YES", "US5": "YES"})
        item = _save(signer, complaint, "US", answers, harm_level="MINOR")
        refused = _sign(signer, complaint, "US", item, "REPORTABLE")
        assert refused.status_code == 409, refused.text
        detail_refused = refused.json()["detail"]
        assert detail_refused["code"] == "TRAINING_REQUIRED" and "practice" not in detail_refused["message"]
        assert detail_refused["message"].startswith("Before you sign, record your training on")
        assert "Signer training" in detail_refused["message"] and len(detail_refused["missing"]) == 2
        assert detail_refused["trained_colleagues"] == []
        _acknowledge(signer)
        states = signer.get(f"{TRAINING}?documents=HARM_SCALE").json()["documents"]
        assert states[0]["state"] == "CURRENT" and states[0]["method"] == "read and acknowledged in MDARIX"
        item = _market(signer.get(_url(complaint)).json(), "US")
        signed = _sign(signer, complaint, "US", item, "REPORTABLE")
        assert signed.status_code == 200, signed.text
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:market-assessment-cleanup")


def test_signing_needs_the_authenticator_code_when_signatures_require_it(org, monkeypatch):
    from backend.app import mfa

    regulatory = org["regulatory"]
    _acknowledge(regulatory)
    complaint = _complaint(org["tenant_id"], org["product"], country="US", malfunction=True)
    item = _save(regulatory, complaint, "US", _answers(**{**US_NONE, "US4": "YES", "US5": "YES"}), harm_level="MINOR")
    monkeypatch.setattr(mfa, "signatures_require_mfa", lambda: True)
    refused = _sign(regulatory, complaint, "US", item, "REPORTABLE")
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "SIGNATURE_MFA_NOT_SET_UP"


def test_only_watched_complaints_and_enabled_markets_and_the_single_decision_stays(org):
    regulatory = org["regulatory"]
    routine = _complaint(org["tenant_id"], org["product"], country="US", patient_involved=False)
    refused = regulatory.put(_url(routine, "US"), json={"answers": {}})
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "NOT_ON_WATCH"
    harm = _complaint(org["tenant_id"], org["product"], country="US", serious_injury=True)
    off = regulatory.put(_url(harm, "GB"), json={"answers": {}})
    assert off.status_code == 409 and off.json()["detail"]["code"] == "MARKET_NOT_ENABLED"
    assert regulatory.put(_url(harm, "XX"), json={"answers": {}}).status_code == 404
    # A new unsigned "not reportable" is refused (0.10.95, code audit 9): the signed market assessment concludes it.
    single = regulatory.post(
        f"/api/v1/complaints/{harm}/reportability", json={"decision": "NOT_REPORTABLE", "rationale": REASON}
    )
    assert single.status_code == 409 and single.json()["detail"]["code"] == "SIGNED_ASSESSMENT_REQUIRED"
    # An earlier single decision is still read, marked as such, and still settles the complaint.
    with SessionLocal() as db:
        bind_tenant(db, org["tenant_id"])
        db.add(
            ComplaintReportability(
                tenant_id=uuid.UUID(str(org["tenant_id"])),
                complaint_id=uuid.UUID(harm),
                decision="NOT_REPORTABLE",
                rationale=REASON,
                decided_by=str(uuid.uuid4()),
            )
        )
        db.commit()
    detail = regulatory.get(_url(harm)).json()
    assert detail["legacy_decision"]["note"] == "Single decision, recorded before per-market assessment"
    watched = next(item for item in regulatory.get(f"{WATCH}?show=all").json()["items"] if item["id"] == harm)
    assert watched["state"] == "DECIDED" and watched["decision"]["single_decision"] is True


def test_another_organization_cannot_read_the_new_tables(org):
    regulatory = org["regulatory"]
    _acknowledge(regulatory)
    complaint = _complaint(org["tenant_id"], org["product"], country="France", malfunction=True)
    _save(regulatory, complaint, "EU_NI", _answers(EU1="YES"))
    assert org["other"].get(_url(complaint)).status_code == 404
    assert org["other"].put(_url(complaint, "EU_NI"), json={"answers": {}}).status_code == 404
    with SessionLocal() as db:
        bind_system(db, "test: a classification row")
        db.add(
            ComplaintClassification(
                tenant_id=org["tenant_id"],
                complaint_id=uuid.UUID(complaint),
                coding_criteria_version="coding-starter-1",
                created_by="test",
            )
        )
        db.commit()
    # Row-level security under the runtime role every request uses: the other organization sees none of the rows.
    if not runtime_role_active():
        pytest.skip("MDARIX_DB_RUNTIME_USER is not configured")
    for tenant, expected in ((org["other_id"], 0), (org["tenant_id"], 1)):
        runtime = RuntimeSessionLocal()
        try:
            bind_tenant(runtime, tenant)
            for model in (ComplaintMarketAssessment, ComplaintClassification):
                assert runtime.query(model).filter(model.complaint_id == uuid.UUID(complaint)).count() == expected
            trained = runtime.query(SignerTrainingRecord).filter(SignerTrainingRecord.tenant_id == org["tenant_id"])
            assert (trained.count() > 0) == (expected == 1)
        finally:
            runtime.close()


def test_a_trial_holds_the_sample_answers_and_removing_the_sample_removes_them_and_the_work_on_them():
    from tests.test_free_trial import PASSWORD as TRIAL_PASSWORD
    from tests.test_free_trial import _approved_trial_client

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    watch = user.get(f"{WATCH}?show=all").json()["items"]
    by_ref = {item["complaint_identifier"]: item for item in watch}
    rv07, rv08, rv06 = by_ref["SAMPLE-RV-07"], by_ref["SAMPLE-RV-08"], by_ref["SAMPLE-RV-06"]
    eu = _market(user.get(_url(rv07["id"])).json(), "EU_NI")
    assert eu["current"]["conclusion"] == "REPORTABLE" and eu["current"]["sample"] is True
    assert eu["current"]["signed_by"] == "MDARIX sample author" and eu["current"]["report_type"] == "EU_15_DAY"
    assert eu["current"]["answers"]["EU3A"]["answer"] == "YES"
    # No window starts a clock from RV-07's fields (a malfunction without harm), but its EU conclusion does.
    assert rv07["state"] != "NO_WINDOW" and rv07["binding"]["window"] == "EU MDR: serious incident (15 days)"
    detail08 = user.get(_url(rv08["id"])).json()
    us = _market(detail08, "US")
    assert us["evaluation"]["suggested"] == "PENDING_INFORMATION" and us["current"] is None
    assert detail08["practice_label"].startswith("Practice record")
    detail06 = user.get(_url(rv06["id"])).json()
    assert _market(detail06, "US")["draft"] is None and detail06["severity_level"] == "CRITICAL"
    assert rv06["markets"][0]["state"] == "NOT_STARTED"

    # The trial user signs RV-06 after the practice training (a trial's method), then removes the sample.
    _acknowledge(user)
    states = user.get(f"{TRAINING}?documents=HARM_SCALE").json()["documents"]
    assert states[0]["method"] == "practice acknowledgement in a free trial"
    item = _save(user, rv06["id"], "US", _answers(**US_SERIOUS), harm_level="CRITICAL")
    draft = item["draft"]
    signed = user.post(
        _url(rv06["id"], "US", "/sign"),
        json={
            "conclusion": "REPORTABLE",
            "version": draft["version"],
            "saved_at": draft["saved_at"],
            "password": TRIAL_PASSWORD,
        },
    )
    assert signed.status_code == 200, signed.text
    story = user.get("/api/v1/trial/story").json()
    chapter = next(item for item in story["chapters"] if item["code"] == "REPORTING_CLOCKS")
    assert chapter["title"] == "Assess a serious complaint per market" and chapter["acted"]["count"] == 1
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        # The sample author's acknowledgements: the EU and Canada question sets and the scale, and (0.10.53) the
        # disposition rules and the coding criteria of the routine example.
        sample_records = db.query(SignerTrainingRecord).filter(
            SignerTrainingRecord.tenant_id == tenant_id, SignerTrainingRecord.source_system == "MDARIX_SAMPLE"
        )
        assert sample_records.count() == 5
    removed = user.post("/api/v1/trial/sample-data/removal", json={"confirm": True})
    assert removed.status_code == 200, removed.text
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        assert db.query(ComplaintMarketAssessment).filter(ComplaintMarketAssessment.tenant_id == tenant_id).count() == 0
        assert (
            db.query(SignedApprovalRecord)
            .filter(
                SignedApprovalRecord.tenant_id == tenant_id,
                SignedApprovalRecord.object_type == "ComplaintMarketAssessment",
            )
            .count()
            == 0
        )
        kept = db.query(SignerTrainingRecord).filter(SignerTrainingRecord.tenant_id == tenant_id).all()
        assert kept and all(row.source_system is None for row in kept)  # the user's own stay until the purge
        assert (
            db.query(Complaint)
            .filter(Complaint.tenant_id == tenant_id, Complaint.source_system == "MDARIX_SAMPLE")
            .count()
            == 0
        )
    from backend.app.tenant_export import _tables
    from backend.app.trial.retention import TRIAL_DATA_TABLES, purge_trial

    with SessionLocal() as db:
        bind_system(db, "test: tables an export and the purge cover")
        exported = {table for _, table in _tables(db)}
        assert {"complaint_market_assessments", "complaint_classifications", "signer_training_records"} <= exported
        assert {"complaint_market_assessments", "complaint_classifications", "signer_training_records"} <= set(
            TRIAL_DATA_TABLES
        )
        purge_trial(db, tenant_id, "test:market-assessment-trial-cleanup")
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        assert db.query(SignerTrainingRecord).filter(SignerTrainingRecord.tenant_id == tenant_id).count() == 0
