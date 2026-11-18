"""W1d, trust closure (WHIF demo, owner decisions of 17 Nov 2026).

- D03: no demo text states an unproven root cause as fact.
- D04: SAMPLE-CAPA-02's synthetic follow-up, labelled as such, shows once its check is planned; a person signs the
  result (effective, not effective or inconclusive) with password and authenticator code; "Did it work?" stays too
  early until then and shows the signed result after; the refresh stages the follow-up once and never on a signed check.
- D08: the sample evidence register's numbers are the trend check's and the records'; it reads only its own trial.

The module's DB tests share one trial and run in file order.
"""

from __future__ import annotations

import re
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant

ROOT = Path(__file__).resolve().parents[1]
REGISTER = "/api/v1/trial/sample-register"
STORY = "/api/v1/trial/one-story"
# An unproven cause stated as fact.
CAUSAL = re.compile(r"\bexplains? the\b|\broot cause is\b|\bmost likely cause\b|\bis the cause\b|\bcaused by\b", re.I)


# D03 ------------------------------------------------------------------------------------------------- wording guard


def _demo_texts() -> list[str]:
    from backend.app.trial import sample_ai, sample_decision, sample_follow_up, sample_register

    narrative = sample_decision.NARRATIVE
    texts = [
        narrative["problem_statement"],
        narrative["proposed_conclusion"],
        *narrative["recommended_actions"],
        *sample_decision.SAMPLE_CHALLENGE_ANSWERS.values(),
        *(item["statement"] for item in sample_decision.SAMPLE_HYPOTHESES),
        *(item["reason"] for item in sample_decision.SAMPLE_HYPOTHESES),
        *sample_decision.SAMPLE_CHAIN["nodes"],
        *(text for _, text in sample_ai.OBSERVATIONS),
        sample_ai.HYPOTHESIS,
        sample_follow_up.NOTICE,
        sample_follow_up.content_text(),
        *sample_follow_up.LIMITS,
        *sample_register.LIMITS,
    ]
    for path in (
        "frontend/e2e/flagship-journey.spec.ts",
        "frontend/src/features/workspace/sections/OneStory.tsx",
        "frontend/src/features/workspace/oneStory.ts",
        "frontend/src/features/workspace/sections/SampleRegister.tsx",
        "tests/test_w1_flagship.py",
        "tests/test_round3_decision.py",
    ):
        texts.append((ROOT / path).read_text(encoding="utf-8"))
    return texts


@pytest.mark.unit
def test_d03_no_demo_text_states_an_unproven_cause_as_fact():
    from backend.app.trial import sample_decision

    found = [match.group(0) for text in _demo_texts() for match in CAUSAL.finditer(text)]
    assert found == []
    conclusion = sample_decision.NARRATIVE["proposed_conclusion"]
    assert "time and lot association" in conclusion and "not yet confirmed" in conclusion


@pytest.mark.unit
def test_d04_the_follow_up_is_labelled_synthetic_and_its_figures_add_up():
    from backend.app.trial import sample_follow_up as follow_up

    after = follow_up.after()
    assert follow_up.LABEL == "Synthetic follow-up (sample)" and follow_up.NOTICE.startswith(follow_up.LABEL)
    assert "not real history" in follow_up.NOTICE and follow_up.content_text().startswith(follow_up.LABEL)
    assert after["source"] == follow_up.LABEL
    assert (
        after["complaints"]
        == sum(item["complaints"] for item in after["lots"])
        == sum(month["complaints"] for month in after["months"])
    )
    assert all(item["sensors_inspected"] == 32 for item in after["lots"])
    # 150 units x (80 + 50 + 20) days / 30 = 750 unit-months; 1 complaint -> 1.3 per 1,000.
    assert after["unit_months"] == 750 and after["per_1000_unit_months"] == 1.3


@pytest.mark.unit
def test_d04_inconclusive_is_a_result_a_person_can_sign():
    from backend.app.capa_effectiveness import rules
    from backend.app.human_decision.summary import worked

    assert rules.RESULTS == (rules.EFFECTIVE, rules.NOT_EFFECTIVE, rules.INCONCLUSIVE)
    assert all(len(code) <= 12 for code in rules.SIGNATURE_CODES.values())
    assert "does not yet show" in rules.signature_meaning("SAMPLE-CAPA-02", 1, rules.INCONCLUSIVE)
    assert rules.state_of(rules.INCONCLUSIVE, None, date(2026, 11, 17)) == rules.INCONCLUSIVE
    check = {"round": 1, "status": "INCONCLUSIVE", "planned_on": "2026-12-01", "signed_at": "2026-11-17T10:00:00"}
    outcome = worked([{"ref": "SAMPLE-CAPA-02", "check": {**check, "synthetic": True}}])
    assert outcome["state"] == "INCONCLUSIVE" and "signed inconclusive" in outcome["text"]
    assert "synthetic follow-up (sample)" in outcome["text"]
    planned = worked([{"ref": "SAMPLE-CAPA-02", "check": {**check, "status": "PLANNED", "signed_at": None}}])
    assert planned["state"] == "TOO_EARLY"


# The trial ---------------------------------------------------------------------------------------------------------


def _ok(response, status: int = 200):
    assert response.status_code == status, response.text
    return response.json()


def _purge(tenant_id) -> None:
    from backend.app.trial.retention import purge_trial

    with SessionLocal() as db:
        purge_trial(db, tenant_id, "test:w1d-cleanup")


@pytest.fixture(scope="module")
def trial():
    from tests.test_free_trial import _approved_trial_client

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id, "tenant_key": approval["tenant_key"]}
    finally:
        _purge(tenant_id)


def _flag(user) -> dict:
    return _ok(user.get(STORY))["flagship"]


def _check(user, capa_id: str) -> dict:
    return _ok(user.get(f"/api/v1/capas/{capa_id}/effectiveness"))


@pytest.mark.db
def test_d04_nothing_is_presigned_and_the_follow_up_waits_for_the_plan(trial):
    user = trial["user"]
    capa = _flag(user)["capa"]
    detail = _check(user, capa["id"])
    assert detail["rounds"] == [] and detail["synthetic_follow_up"] is None and detail["state"] != "EFFECTIVE"
    assert capa["follow_up"] is False and capa["check_status"] is None
    # The follow-up is one labelled evidence record, never a lot, a complaint or a trend row.
    from backend.app.db.models.foundation import Complaint, Evidence, LotBatch
    from backend.app.trial import sample_follow_up as follow_up

    tenant_id = trial["tenant_id"]
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        record = (
            db.query(Evidence)
            .filter(Evidence.tenant_id == tenant_id, Evidence.evidence_identifier == follow_up.EVIDENCE)
            .one()
        )
        assert record.title.startswith(follow_up.LABEL) and record.investigation_id is None
        lots = db.query(LotBatch).filter(LotBatch.tenant_id == tenant_id, LotBatch.lot_identifier.like("FU-LOT-%"))
        assert lots.count() == 0
        assert (
            db.query(Complaint)
            .filter(Complaint.tenant_id == tenant_id, Complaint.description.ilike("%synthetic%"))
            .count()
            == 0
        )


def _sign_decision(user) -> None:
    """The case's decision, signed with the password (the authenticator is set up after it)."""
    from tests.test_free_trial import PASSWORD

    case_id = _flag(user)["investigation"]["id"]
    # UX1: the sample reviewer has accepted the brief for decision; a person signs it.
    brief = _ok(user.get(f"/api/v1/investigations/{case_id}/decision"))["brief"]
    _ok(
        user.post(
            f"/api/v1/investigations/{case_id}/decision/sign",
            json={
                "brief_version_id": brief["id"],
                "brief_content_hash": brief["content_hash"],
                "outcome": "ACCEPT_CONCLUSION",
                "rationale": "The evidence shows a time and lot association after the supplier and inspection "
                "changes. We will start a CAPA and verify the supplier and inspection controls. The cause is not yet "
                "confirmed.",
                "root_cause_attribution": "DEVICE_RELATED",
                "root_cause_category": "MATERIAL",
                "residual_unknowns_acknowledged": True,
                "password": PASSWORD,
            },
        )
    )


@pytest.mark.db
def test_d04_planned_then_follow_up_then_a_person_signs_with_mfa(trial, monkeypatch):
    from auth import totp
    from tests.test_free_trial import PASSWORD

    user = trial["user"]
    _sign_decision(user)
    # From here signatures need an authenticator code (as MDARIX_REQUIRE_MFA_FOR_SIGNATURES sets in production).
    monkeypatch.setenv("MDARIX_REQUIRE_MFA_FOR_SIGNATURES", "true")
    started = _ok(user.post("/api/v1/auth/mfa/enroll"))
    _ok(user.post("/api/v1/auth/mfa/verify-enrollment", json={"code": totp.current_code(started["secret"])}))
    step = int(time.time() // 30)
    run = _flag(user)
    capa_id, case_id = run["capa"]["id"], run["investigation"]["id"]
    summary = f"/api/v1/investigations/{case_id}/decision/summary"
    today = date.today().isoformat()
    _ok(
        user.put(
            f"/api/v1/capas/{capa_id}/effectiveness/plan",
            json={
                "criteria": "No pressure-alarm complaint from lots made after the 32-unit inspection is restored.",
                "planned_on": today,
                "measured_from": today,
            },
        )
    )
    detail = _check(user, capa_id)
    follow = detail["synthetic_follow_up"]
    assert follow["label"] == "Synthetic follow-up (sample)" and follow["synthetic"] is True
    assert follow["after"]["per_1000_unit_months"] == 1.3 and follow["before"]["complaints"] > 0
    assert follow["before"]["lots"] == ["SAMPLE-ORBIT-300-LOT-003", "SAMPLE-ORBIT-300-LOT-004"]
    run = _flag(user)
    assert run["capa"]["follow_up"] is True and run["capa"]["check_status"] is None
    assert run["steps"][6]["note"].startswith("Did it work? Too early")
    # Too early until a person signs.
    assert _ok(user.get(summary))["worked"]["state"] == "TOO_EARLY"

    url = f"/api/v1/capas/{capa_id}/effectiveness/result"
    body = {
        "result": "INCONCLUSIVE",
        "summary": "One complaint in 750 unit-months on a short follow-up.",
        "plan_version": 1,
    }
    # The signature needs the person's password and, as signatures require it, a current authenticator code.
    assert user.post(url, json={**body, "password": "wrong-password-123"}).status_code == 403
    assert user.post(url, json={**body, "password": PASSWORD}).status_code == 403
    assert _check(user, capa_id)["rounds"][0]["status"] == "PLANNED"
    signed = _ok(
        user.post(url, json={**body, "password": PASSWORD, "mfa_code": totp.code_at(started["secret"], step + 1)})
    )
    assert signed["state"] == "INCONCLUSIVE" and signed["can_plan"] is True
    round_one = signed["rounds"][0]
    assert round_one["status"] == "INCONCLUSIVE" and round_one["signed_by"]
    assert round_one["evidence"]["synthetic_follow_up"]["label"] == "Synthetic follow-up (sample)"
    assert signed["synthetic_follow_up"] == round_one["evidence"]["synthetic_follow_up"]
    from backend.app.db.models.foundation import SignedApprovalRecord

    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        record = (
            db.query(SignedApprovalRecord)
            .filter(
                SignedApprovalRecord.tenant_id == trial["tenant_id"],
                SignedApprovalRecord.decision_type == "CAPA_EFFECTIVENESS",
            )
            .one()
        )
        assert record.decision == "INCONCLUSIVE" and record.content_fingerprint == round_one["content_fingerprint"]
    worked = _ok(user.get(summary))["worked"]
    assert worked["state"] == "INCONCLUSIVE" and "synthetic follow-up (sample)" in worked["text"]
    assert _flag(user)["capa"]["check_status"] == "INCONCLUSIVE"


# D08 ---------------------------------------------------------------------------------------------------- register


@pytest.mark.db
def test_d08_the_register_numbers_are_the_trend_checks_and_the_records(trial):
    from backend.app.db.models.foundation import Complaint, Product

    user = trial["user"]
    body = _ok(user.get(REGISTER))
    product_id = body["product"]["id"]
    assert body["product"]["ref"] == "SAMPLE-ORBIT-300"
    assert [row["version"] for row in body["product"]["versions"]] == ["Rev A", "Rev B"]
    assert body["change"]["ref"] == "SAMPLE-CHG-014" and "32 to 13" in body["change"]["description"]
    assert any(row["supplier"].startswith("NovaSense Components") for row in body["component"]["suppliers"])
    # The trend rows are the trend check's (the same computation as Trends and Home).
    trends = _ok(user.get(f"/api/v1/triage/trends?group=version&product_id={product_id}"))["items"]
    by_version = {(row["product_version"] or {}).get("version_identifier"): row for row in trends}
    for row in body["complaints"]["trend"]:
        source = by_version[row["version"]]
        assert (row["recent"], row["expected"], row["recent_days"], row["ratio"]) == (
            source["recent"],
            source["expected"],
            source["recent_days"],
            source["ratio"],
        )
        assert row["monthly"] == {
            "before": round(source["expected"] / source["recent_days"] * 30, 1),
            "after": round(source["recent"] / source["recent_days"] * 30, 1),
        }
    from backend.app.trial import flagship

    assert max(row["ratio"] or 0 for row in body["complaints"]["trend"]) == flagship.SIGNAL_RATIO
    # Counts are the records'.
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        product = db.query(Product).filter(Product.id == uuid.UUID(product_id)).one()
        on_product = db.query(Complaint).filter(Complaint.product_id == product.id)
        alarms = on_product.filter(Complaint.problem_code == "PRESSURE_ALARM").count()
        assert body["complaints"]["on_product"] == on_product.count()
    assert body["complaints"]["pressure_alarm"] == alarms == sum(lot["pressure_alarm"] for lot in body["lots"])
    lots = {lot["ref"]: lot for lot in body["lots"]}
    assert lots["SAMPLE-ORBIT-300-LOT-003"]["in_case"] and lots["SAMPLE-ORBIT-300-LOT-003"]["units"] == 150
    # The follow-up as the check shows it; the inspection steps name their sources.
    assert body["follow_up"]["label"] == "Synthetic follow-up (sample)" and body["follow_up"]["record"]["ref"]
    assert [row["units_per_lot"] for row in body["inspection"]] == [32, 13, 32]
    evidence = body["evidence"]
    assert {row["ref"] for row in evidence["records"]} == {"SAMPLE-EV-001", "SAMPLE-EV-002", "SAMPLE-EV-003"}
    assert all(row["recorded"] and row["source"] for row in evidence["records"])
    assert evidence["for"] and evidence["against"] and evidence["missing"]
    assert any("synthetic" in limit for limit in body["limits"])


@pytest.mark.db
def test_d08_and_d04_reads_stay_in_their_query_budget(trial):
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    from backend.app.capa_effectiveness import service
    from backend.app.trial import flagship, sample_register

    seen = {"count": 0}

    def count(*_args, **_kwargs):
        seen["count"] += 1

    with SessionLocal() as data:
        bind_tenant(data, trial["tenant_id"])
        case = flagship.find_case(data, trial["tenant_id"])
        from backend.app.db.models.foundation import Capa

        capa_id = (
            data.query(Capa.id)
            .filter(Capa.tenant_id == trial["tenant_id"], Capa.capa_identifier == "SAMPLE-CAPA-02")
            .scalar()
        )
        assert case is not None
        for read, budget in (
            (lambda: sample_register.register(data, trial["tenant_id"], date.today()), 30),
            (lambda: service.detail(data, None, trial["tenant_id"], capa_id), 20),
        ):
            seen["count"] = 0
            event.listen(Engine, "before_cursor_execute", count)
            started = datetime.now(timezone.utc)
            try:
                assert read() is not None
            finally:
                event.remove(Engine, "before_cursor_execute", count)
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            assert seen["count"] <= budget and elapsed < 0.5, (seen["count"], elapsed)


# Refresh and tenant isolation ------------------------------------------------------------------------------------


def _script():
    import importlib.util

    spec = importlib.util.spec_from_file_location("refresh_trial_story", ROOT / "scripts" / "refresh_trial_story.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.db
def test_d04_refresh_stages_the_follow_up_once_and_never_on_a_signed_check_and_reads_stay_in_their_trial(trial):
    from backend.app.db.models.foundation import Evidence
    from backend.app.trial import sample_follow_up as follow_up
    from tests.test_free_trial import _approved_trial_client

    script = _script()
    other, approval, _ = _approved_trial_client()
    tenant_id, key = uuid.UUID(approval["tenant_id"]), approval["tenant_key"]
    try:
        # Tenant isolation: the other trial reads its own register, and never the first trial's CAPA.
        mine, theirs = _ok(trial["user"].get(REGISTER)), _ok(other.get(REGISTER))
        assert mine["product"]["id"] != theirs["product"]["id"]
        assert other.get(f"/api/v1/capas/{mine['follow_up']['capa']['id']}/effectiveness").status_code == 404
        # An older trial: no follow-up record.
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            db.query(Evidence).filter(
                Evidence.tenant_id == tenant_id, Evidence.evidence_identifier == follow_up.EVIDENCE
            ).delete()
            db.commit()
        with SessionLocal() as db:
            planned = {item["tenant"]: item for item in script.refresh(db, apply=False)}[key]
        assert "SAMPLE-CAPA-02's synthetic follow-up (W1d)" in planned["sample"]
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            assert follow_up.has_record(db, tenant_id) is False  # dry run
        with SessionLocal() as db:
            script.refresh(db, apply=True)
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            mine_only = (Evidence.tenant_id == tenant_id, Evidence.evidence_identifier == follow_up.EVIDENCE)
            assert db.query(Evidence).filter(*mine_only).count() == 1
        with SessionLocal() as db:
            assert {item["tenant"]: item["result"] for item in script.refresh(db, apply=False)}[
                key
            ] == "already has the story"
    finally:
        _purge(tenant_id)
    # The module's trial signed its check: with the record gone, the refresh still owes nothing there.
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        db.query(Evidence).filter(
            Evidence.tenant_id == trial["tenant_id"], Evidence.evidence_identifier == follow_up.EVIDENCE
        ).delete()
        assert follow_up.signed_check(db, trial["tenant_id"]) is True
        assert follow_up.refresh(db, trial["tenant_id"], apply=False) == 0
        db.rollback()
