"""Signals and AI end to end: one click from a signal to its case (triage recorded in the same step, the case with
every complaint, version and lot, for the person opening it), the statistical trend check per product version (every
complaint counted, dismissed records left out), the signal's records summary and its AI summary checked sentence by
sentence, the case's one AI run (started by itself once, followed step by step), permissions and isolation.

Everything runs in fresh organizations of their own (on the shared plane), deleted at the end.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from auth.durable import persist_session
from auth.service import _hash
from backend.app.db.models.case_scope import InvestigationScopeVersion
from backend.app.db.models.complaint_review import ComplaintSecondLook
from backend.app.db.models.foundation import (
    AuthUser,
    Complaint,
    InvestigationComplaint,
    LotBatch,
    Product,
    ProductVersion,
    TenantMembership,
)
from backend.app.db.models.signals import Signal, SignalEvent
from backend.app.db.models.workflow import WorkflowTask
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from backend.app.main import app

PASSWORD = "Signals and AI 2026!"
REASON = "Recorded for the audit trail in this test"
NOW = datetime.now(timezone.utc)


def _organization(label: str):
    from backend.app.customer_lifecycle import build_customer_tenant

    with SessionLocal() as db:
        customer, tenant = build_customer_tenant(
            db=db,
            tenant_key=f"SIGAI_{label}_{uuid.uuid4().hex[:6].upper()}",
            name=f"Signals and AI {label}",
            status="ACTIVE",
            now=NOW,
        )
        db.add(customer)
        db.add(tenant)
        db.commit()
        return tenant.id


def _client(tenant_id, role: str, name: str | None = None) -> tuple[TestClient, str]:
    with SessionLocal() as db:
        user = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            username=f"sigai-{role.lower()}-{uuid.uuid4().hex[:8]}@example.invalid",
            display_name=name or f"{role.title()} Sigai",
            company="Test",
            password_hash=_hash(PASSWORD),
            role=role,
            status="ACTIVE",
            email_verified=True,
            created_at=NOW,
            updated_at=NOW,
        )
        db.add(user)
        db.flush()
        db.add(
            TenantMembership(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                user_id=user.id,
                status="ACTIVE",
                is_default=True,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        db.commit()
        token = secrets.token_urlsafe(32)
        persist_session(db, token, user.id, tenant_id)
        user_id = str(user.id)
    client = TestClient(app)
    client.cookies.set("mdarix_session", token)
    return client, user_id


@pytest.fixture(scope="module")
def org():
    from backend.app.trial.retention import purge_trial

    tenant_id = _organization("A")
    other_id = _organization("B")
    people = {
        "lead": _client(tenant_id, "TRIAGE_LEAD"),
        "investigator": _client(tenant_id, "INVESTIGATOR", "Ivy Investigator"),
        "viewer": _client(tenant_id, "VIEWER"),
        "other": _client(other_id, "INVESTIGATOR"),
    }
    try:
        yield {"tenant_id": tenant_id, "other_id": other_id, **people}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:signals-ai-cleanup")
            purge_trial(db, other_id, "test:signals-ai-cleanup")


def _product(tenant_id, *, released_days_ago: int = 400) -> dict:
    tag = uuid.uuid4().hex[:8].upper()
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        product = Product(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            product_identifier=f"SA-P-{tag}",
            name=f"Signal Pump {tag}",
            created_at=NOW,
            updated_at=NOW,
        )
        db.add(product)
        db.flush()
        version = ProductVersion(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            product_id=product.id,
            version_identifier="Rev B",
            release_timestamp=NOW - timedelta(days=released_days_ago),
            created_at=NOW,
            updated_at=NOW,
        )
        db.add(version)
        db.flush()
        lots = []
        for index in range(2):
            lot = LotBatch(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                lot_identifier=f"SA-L-{tag}-{index}",
                product_version_id=version.id,
                created_at=NOW,
                updated_at=NOW,
            )
            db.add(lot)
            lots.append(str(lot.id))
        db.commit()
        return {"product": str(product.id), "version": str(version.id), "lots": lots, "name": product.name}


def _complaint(tenant_id, item: dict, *, days_ago: int, lot: int | None = 0, **fields) -> str:
    moment = NOW - timedelta(days=days_ago)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = Complaint(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            complaint_identifier=f"SA-C-{uuid.uuid4().hex[:10].upper()}",
            product_id=uuid.UUID(item["product"]),
            product_version_id=uuid.UUID(item["version"]),
            lot_batch_id=uuid.UUID(item["lots"][lot]) if lot is not None else None,
            event_timestamp=moment,
            complaint_timestamp=moment,
            description=fields.pop("description", "Occlusion alarm during infusion; line found clear"),
            problem_code=fields.pop("problem_code", "OCCLUSION"),
            status=fields.pop("status", "open"),
            created_at=moment,
            updated_at=moment,
            **fields,
        )
        db.add(row)
        db.commit()
        return str(row.id)


def _signal(org, item: dict, complaints: list[str]) -> str:
    client, _ = org["lead"]
    made = client.post(
        "/api/v1/triage/signals",
        json={
            "title": "Occlusion alarms on Rev B",
            "product_id": item["product"],
            "product_version_id": item["version"],
            "complaint_ids": complaints,
        },
    )
    assert made.status_code == 201, made.text
    return made.json()["id"]


# ------------------------------------------------------------------------------------------- one click to a case


def test_one_click_triages_and_opens_the_case_for_the_investigator(org):
    tenant = org["tenant_id"]
    item = _product(tenant)
    complaints = [_complaint(tenant, item, days_ago=days, lot=days % 2) for days in (3, 5, 8)]
    signal_id = _signal(org, item, complaints)
    path = f"/api/v1/triage/signals/{signal_id}/open-case"
    body = {"investigation_question": "Why do occlusion alarms rise on Rev B?"}
    viewer, _ = org["viewer"]
    assert viewer.post(path, json=body).status_code == 403
    assert org["investigator"][0].get(f"/api/v1/triage/signals/{signal_id}").json()["actions"]["can_open_case"]

    client, user_id = org["investigator"]
    opened = client.post(path, json=body)
    assert opened.status_code == 201, opened.text
    result = opened.json()
    assert result["triaged"] is True
    assert result["investigation"]["complaints_linked"] == 3
    assert result["investigation"]["owner"] == {"id": user_id, "name": "Ivy Investigator"}
    assert result["signal"]["status"] == "INVESTIGATION_OPEN"
    case_id = uuid.UUID(result["investigation"]["id"])
    with SessionLocal() as db:
        bind_tenant(db, tenant)
        events = (
            db.query(SignalEvent)
            .filter(SignalEvent.signal_id == uuid.UUID(signal_id))
            .order_by(SignalEvent.created_at)
            .all()
        )
        triage = next(event for event in events if event.event_type == "DISPOSITIONED")
        assert triage.to_status == "INVESTIGATION_REQUIRED" and triage.details["one_click"] is True
        assert triage.actor_role == "INVESTIGATOR"
        assert events[-1].event_type == "INVESTIGATION_CREATED"
        scope = db.query(InvestigationScopeVersion).filter(InvestigationScopeVersion.investigation_id == case_id).one()
        assert sorted(scope.lot_ids) == sorted(item["lots"])
        assert scope.product_version_ids == [item["version"]]
        linked = db.query(InvestigationComplaint).filter(InvestigationComplaint.investigation_id == case_id).count()
        assert linked == 3
        triage_tasks = (
            db.query(WorkflowTask)
            .filter(WorkflowTask.task_type == "SIGNAL_TRIAGE", WorkflowTask.source_entity_id == uuid.UUID(signal_id))
            .all()
        )
        assert all(task.status != "NEW" for task in triage_tasks)
        case_task = (
            db.query(WorkflowTask)
            .filter(WorkflowTask.task_type == "INVESTIGATION", WorkflowTask.investigation_id == case_id)
            .one()
        )
        assert str(case_task.assigned_user_id) == user_id


def test_one_click_on_a_triaged_signal_opens_the_case_without_a_second_triage(org):
    tenant = org["tenant_id"]
    item = _product(tenant)
    signal_id = _signal(org, item, [_complaint(tenant, item, days_ago=4)])
    lead, _ = org["lead"]
    decided = lead.post(
        f"/api/v1/triage/signals/{signal_id}/disposition",
        json={"disposition": "INVESTIGATION_REQUIRED", "reason": REASON},
    )
    assert decided.status_code == 200
    opened = org["investigator"][0].post(
        f"/api/v1/triage/signals/{signal_id}/open-case",
        json={"investigation_question": "Why does this alarm occur?", "assign_to_me": False},
    )
    assert opened.status_code == 201, opened.text
    assert opened.json()["triaged"] is False and opened.json()["investigation"]["owner"] is None

    closed_id = _signal(org, item, [_complaint(tenant, item, days_ago=4)])
    lead.post(f"/api/v1/triage/signals/{closed_id}/disposition", json={"disposition": "NO_ACTION", "reason": REASON})
    refused = org["investigator"][0].post(
        f"/api/v1/triage/signals/{closed_id}/open-case", json={"investigation_question": "Why does this alarm occur?"}
    )
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "SIGNAL_STATE_CONFLICT"
    with SessionLocal() as db:
        bind_tenant(db, tenant)
        assert db.query(Signal).filter(Signal.id == uuid.UUID(closed_id)).one().status == "NO_ACTION"
    other = org["other"][0].post(
        f"/api/v1/triage/signals/{signal_id}/open-case", json={"investigation_question": "Why does this alarm occur?"}
    )
    assert other.status_code == 404


# ------------------------------------------------------------------------------------------- trend check


def test_the_trend_check_compares_each_version_with_its_own_history(org):
    tenant = org["tenant_id"]
    rising = _product(tenant)
    for days in (40, 70, 100, 130, 160, 190):  # 6 in the history (expected 1 in 30 days)
        _complaint(tenant, rising, days_ago=days)
    for days in (2, 5, 9, 14, 20, 25):  # 6 in the last 30 days
        _complaint(tenant, rising, days_ago=days)
    dismissed = _complaint(tenant, rising, days_ago=3, status="Cancelled")
    with SessionLocal() as db:
        bind_tenant(db, tenant)
        db.add(
            ComplaintSecondLook(
                tenant_id=tenant,
                complaint_id=uuid.UUID(dismissed),
                decision="DISMISSED",
                reason="Not a complaint: a training question",
                decided_by="test",
            )
        )
        db.commit()
    young = _product(tenant, released_days_ago=50)
    for days in (1, 2, 3, 4):
        _complaint(tenant, young, days_ago=days)

    viewer, _ = org["viewer"]
    board = viewer.get("/api/v1/triage/trends", params={"product_id": rising["product"]}).json()
    assert board["grouping"] == "version" and board["recent_days"] == 30
    item = board["items"][0]
    assert (item["recent"], item["history"], item["history_days"]) == (6, 6, 180)
    assert item["result"] == "SIGNIFICANT" and item["p_value"] < 0.01 and item["expected"] == 1.0
    assert item["name"] == f"{rising['name']} Rev B"
    assert "chance of at least this many if nothing changed" in item["sentence"]
    young_board = viewer.get("/api/v1/triage/trends", params={"product_id": young["product"]}).json()
    assert young_board["items"][0]["result"] == "SHORT_HISTORY"
    by_problem = viewer.get(
        "/api/v1/triage/trends", params={"product_id": rising["product"], "group": "problem"}
    ).json()
    assert by_problem["items"][0]["problem"] == "OCCLUSION" and by_problem["items"][0]["recent"] == 6
    assert viewer.get("/api/v1/triage/trends", params={"group": "everything"}).status_code == 422
    other = org["other"][0].get("/api/v1/triage/trends").json()
    assert all(entry["product"]["id"] not in (rising["product"], young["product"]) for entry in other["items"])


# ------------------------------------------------------------------------------------------- signal summary


def test_the_signal_summary_cites_its_complaints_and_ai_is_checked(org):
    from backend.app.signals import insight

    tenant = org["tenant_id"]
    item = _product(tenant)
    complaints = [
        _complaint(
            tenant, item, days_ago=2, lot=0, country="US", death=True, description="Occlusion alarm; patient died"
        ),
        _complaint(tenant, item, days_ago=4, lot=0, country="US", malfunction=True),
        _complaint(tenant, item, days_ago=6, lot=1, country="Germany", problem_code="NFF"),
    ]
    signal_id = _signal(org, item, complaints)
    viewer, _ = org["viewer"]
    insight_body = viewer.get(f"/api/v1/triage/signals/{signal_id}/insight").json()
    summary = insight_body["summary"]
    assert summary["author"] == "RECORDS" and summary["complaints"] == 3
    texts = [sentence["text"] for sentence in summary["sentences"]]
    assert texts[0].startswith("3 complaints about")
    assert "1 report a death; 1 a malfunction." in texts
    assert any(text.startswith("2 of the 3 complaints that name a lot name lot") for text in texts)
    assert any(text.startswith("2 from US") for text in texts)
    assert "1 coded No Fault Found or User Error." in texts
    assert all(sentence["complaints"] for sentence in summary["sentences"])
    assert insight_body["trend"] is not None

    # AI off (no provider in tests): the records summary stands, with the reason.
    lead, _ = org["lead"]
    assert viewer.post(f"/api/v1/triage/signals/{signal_id}/summary").status_code == 403
    off = lead.post(f"/api/v1/triage/signals/{signal_id}/summary")
    assert off.status_code == 200 and off.json()["author"] == "RECORDS" and off.json()["ai"]["status"] != "COMPLETED"

    # A model reply: only sentences citing the signal's own complaints, without a cause, are kept.
    with SessionLocal() as db:
        bind_tenant(db, tenant)
        signal = db.query(Signal).filter(Signal.id == uuid.UUID(signal_id)).one()
        refs = [
            row.business_id for row in db.query(Complaint).filter(Complaint.id.in_([uuid.UUID(c) for c in complaints]))
        ]
        reply = {
            "sentences": [
                {"text": "Two complaints describe an occlusion alarm with a clear line.", "complaints": refs[:2]},
                {"text": "One complaint cites a record that is not in the signal.", "complaints": ["CMP999999"]},
                {"text": "The alarm was caused by the sensor firmware.", "complaints": refs[:1]},
            ]
        }
        import json

        fake = SimpleNamespace(
            complete=lambda *args, **kwargs: SimpleNamespace(
                provider="test",
                model="test-model",
                model_version="1",
                output={"status": "PROVIDER_COMPLETED", "answer": json.dumps(reply)},
                latency_ms=5,
            )
        )
        result = insight.ai_summary(db, signal, actor_ref="test", provider=fake)
        db.commit()
    assert result["author"] == "AI"
    assert [sentence["text"] for sentence in result["sentences"]] == [
        "Two complaints describe an occlusion alarm with a clear line."
    ]
    assert {item["reason"] for item in result["ai"]["dropped"]} == {
        "CITES_UNKNOWN_COMPLAINT",
        "CAUSAL_OR_DECISION_CLAIM",
    }
    assert result["ai"]["ai_execution_id"]


# ------------------------------------------------------------------------------------------- the case AI run


def test_the_case_ai_run_starts_by_itself_once_and_reports_each_step(org):
    tenant = org["tenant_id"]
    item = _product(tenant)
    complaints = [_complaint(tenant, item, days_ago=days) for days in (3, 6)]
    client, _ = org["investigator"]
    case = client.post(
        "/api/v1/investigations",
        json={
            "product_id": item["product"],
            "investigation_question": "Why do occlusion alarms rise on Rev B?",
            "complaint_ids": complaints,
        },
    )
    assert case.status_code in (200, 201), case.text
    path = f"/api/v1/investigations/{case.json()['id']}/ai-run"
    assert client.get(path).json()["run"] is None
    assert org["viewer"][0].post(path, json={"trigger": "AUTO"}).status_code == 403

    started = client.post(path, json={"trigger": "AUTO"})
    assert started.status_code == 202, started.text
    assert started.json()["started"] is True and started.json()["run"]["trigger"] == "AUTO"
    run = client.get(path).json()["run"]  # the test client runs the background task before answering again
    assert run["status"] == "COMPLETED", run
    assert all(step["status"] == "DONE" for step in run["steps"]), run["steps"]
    assert [step["step"] for step in run["steps"]] == [
        "ANALYSIS",
        "HYPOTHESES",
        "CHALLENGES",
        "UNKNOWNS",
        "FAILURE_CHAINS",
        "BRIEF",
    ]
    assert run["steps"][0]["status"] == "DONE" and run["steps"][0]["author"] == "RULES"
    assert run["steps"][0]["ai_execution_id"]

    again = client.post(path, json={"trigger": "AUTO"})
    assert again.status_code == 200 and again.json()["started"] is False
    manual = client.post(path, json={"trigger": "MANUAL"})
    assert manual.status_code == 202 and manual.json()["run"]["trigger"] == "MANUAL"
    assert org["other"][0].get(path).status_code == 404
    assert client.get(path).json()["run"]["id"] == manual.json()["run"]["id"]


# ------------------------------------------------------------------------------- the automatic trust check (Phase 6)


def _fake_summary(reply: dict):
    import json

    return SimpleNamespace(
        complete=lambda *args, **kwargs: SimpleNamespace(
            provider="anthropic",
            model="claude-sonnet-5-5",
            model_version="1",
            output={"status": "PROVIDER_COMPLETED", "answer": json.dumps(reply)},
            latency_ms=5,
        )
    )


def test_every_saved_ai_result_gets_its_trust_check_as_it_is_saved(org):
    from ai.execution import record_ai_execution
    from backend.app.db.models.foundation import AssuranceCheck, AssuranceResult
    from backend.app.signals import insight
    from trust_engine import auto

    tenant = org["tenant_id"]
    item = _product(tenant)
    complaints = [_complaint(tenant, item, days_ago=days, malfunction=True) for days in (2, 5)]
    signal_id = _signal(org, item, complaints)
    with SessionLocal() as db:
        bind_tenant(db, tenant)
        signal = db.query(Signal).filter(Signal.id == uuid.UUID(signal_id)).one()
        refs = [
            row.business_id for row in db.query(Complaint).filter(Complaint.id.in_([uuid.UUID(c) for c in complaints]))
        ]
        reply = {"sentences": [{"text": "Both complaints report a malfunction.", "complaints": refs}]}
        result = insight.ai_summary(db, signal, actor_ref="test", provider=_fake_summary(reply))
        db.commit()
        trust = result["ai"]["trust"]
        assert trust["status"] == auto.STATUS_PASS and trust["policy"] == auto.POLICY and trust["author"] == auto.AI
        assert {check["check"] for check in trust["checks"]} >= {
            "EVIDENCE_GROUNDING",
            "RESTRICTED_CLAIMS",
            "PROVENANCE",
        }
        assert "Written by anthropic claude-sonnet-5-5." in [check["message"] for check in trust["checks"]]
        saved = db.query(AssuranceResult).filter(AssuranceResult.id == uuid.UUID(trust["id"])).one()
        assert saved.ai_execution_id == uuid.UUID(result["ai"]["ai_execution_id"])
        assert saved.output_type == "SIGNAL_SUMMARY" and saved.trust_policy_version == auto.POLICY
        assert db.query(AssuranceCheck).filter(AssuranceCheck.assurance_result_id == saved.id).count() == 5
        assert auto.latest(db, tenant, result["ai"]["ai_execution_id"])["status"] == auto.STATUS_PASS

        # A result saved with a source that does not exist is blocked, and the block is saved with it.
        execution = record_ai_execution(
            db,
            tenant,
            provider=auto.SIGNAL_SUMMARY,
            model_name="claude-sonnet-5-5",
            evidence_refs={"complaints": refs},
            structured_output={
                "sentences": [{"text": "A complaint reports a leak.", "complaints": ["CMP-NOT-HERE"]}],
                "model": {"provider": "anthropic", "model": "claude-sonnet-5-5"},
            },
        )
        db.commit()
        assert execution.trust["status"] == auto.STATUS_BLOCKED
        assert auto.latest(db, tenant, execution.id)["status"] == auto.STATUS_BLOCKED
        # The trust check is the organization's own: another organization never reads it.
        assert auto.latest(db, org["other_id"], execution.id) is None


def test_each_case_ai_run_step_carries_its_trust_check_and_the_mvp_skips_template_chains(org, monkeypatch):
    from trust_engine import auto

    tenant = org["tenant_id"]
    item = _product(tenant)
    complaints = [_complaint(tenant, item, days_ago=days) for days in (3, 8)]
    client, _ = org["investigator"]
    case = client.post(
        "/api/v1/investigations",
        json={
            "product_id": item["product"],
            "investigation_question": "Why do occlusion alarms rise on Rev B?",
            "complaint_ids": complaints,
        },
    )
    assert case.status_code in (200, 201), case.text
    path = f"/api/v1/investigations/{case.json()['id']}/ai-run"
    monkeypatch.setenv("MDARIX_FEATURE_SET", "mvp")
    assert client.post(path, json={"trigger": "AUTO"}).status_code == 202
    run = client.get(path).json()["run"]
    assert run["status"] == "COMPLETED", run
    steps = {step["step"]: step for step in run["steps"]}
    assert steps["FAILURE_CHAINS"]["status"] == "SKIPPED"
    assert "fixed template" in steps["FAILURE_CHAINS"]["notice"]
    assert "trust" not in steps["FAILURE_CHAINS"]
    for code in ("ANALYSIS", "HYPOTHESES", "CHALLENGES", "UNKNOWNS"):
        trust = steps[code]["trust"]
        assert steps[code]["status"] == "DONE" and trust is not None, steps[code]
        # No model in tests: the rules wrote every step, and every source they cite resolves.
        assert trust["author"] == auto.RULES and trust["status"] in (auto.STATUS_PASS, auto.STATUS_LIMITED), trust
        assert trust["policy"] == auto.POLICY
    # The rules brief is not an AI result, so it has no trust check of its own.
    assert steps["BRIEF"]["status"] == "DONE" and steps["BRIEF"]["trust"] is None

    monkeypatch.setenv("MDARIX_FEATURE_SET", "full")
    manual = client.post(path, json={"trigger": "MANUAL"})
    assert manual.status_code == 202
    run = client.get(path).json()["run"]
    assert run["status"] == "COMPLETED" and all(step["status"] == "DONE" for step in run["steps"]), run["steps"]
