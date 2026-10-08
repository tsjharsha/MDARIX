"""The trust and audit views of a case, end to end (backend/app/case_audit): a case with history from several sources
(opening, a signal, evidence links, a risk review, an AI run reviewed by a person, a signed brief decision with its
context snapshot, a legacy signed decision) gives one chronological timeline with business ids and no secrets; the
replay at signing tells the evidence known then from evidence linked later; the AI runs list the run the decision
disclosed; the integrity check finds a changed signature INVALID; the export needs data.export and is audited with
its SHA-256; another organization's case is not found.

Records the signing step and the AI engines would write are written directly, so the tests do not depend on those
screens or on a model. Everything runs in fresh organizations (on the shared plane), deleted at the end.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from auth.durable import persist_session
from auth.service import _hash
from backend.app.case_audit import rules
from backend.app.case_workflow import states
from backend.app.db.models.foundation import (
    AIExecution,
    AuditEvent,
    AuthUser,
    Decision,
    Evidence,
    HumanReview,
    Hypothesis,
    Investigation,
    Product,
    SignedApprovalRecord,
    TenantMembership,
)
from backend.app.db.models.intelligence import IntelligenceEvent
from backend.app.db.models.reviews import CaseReview, DecisionBriefVersion
from backend.app.db.models.signals import InvestigationSignal, Signal, SignalEvent
from backend.app.db.models.stage3 import ContextSnapshot
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from backend.app.decision_brief import rules as brief_rules
from backend.app.human_decision import rules as decision_rules
from backend.app.main import app

PASSWORD = "Case audit 2026!"
QUESTION = "Why do occlusion alarms rise after release C?"
SECRET_MARKER = "sk-case-audit-secret-0000"
LEGACY_REMARKS = "Approved after the bench test"


def _organization(prefix: str):
    from backend.app.customer_lifecycle import build_customer_tenant

    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        customer, tenant = build_customer_tenant(
            db=db, tenant_key=f"{prefix}_{uuid.uuid4().hex[:8].upper()}", name="Case audit", status="ACTIVE", now=now
        )
        db.add(customer)
        db.add(tenant)
        db.commit()  # registers the organization on the shared plane (migration md20)
        return tenant.id


def _purge(tenant_id) -> None:
    from backend.app.trial.retention import purge_trial

    with SessionLocal() as db:
        purge_trial(db, tenant_id, "test:case-audit-cleanup")


def _client(tenant_id, role: str, name: str) -> tuple[TestClient, str, str]:
    with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        user = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            username=f"case-audit-{role.lower()}-{uuid.uuid4().hex[:8]}@example.invalid",
            display_name=f"{name} Audit",
            company="Test",
            password_hash=_hash(PASSWORD),
            role=role,
            status="ACTIVE",
            email_verified=True,
            created_at=now,
            updated_at=now,
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
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        token = secrets.token_urlsafe(32)
        persist_session(db, token, user.id, tenant_id)
        user_id = str(user.id)
    client = TestClient(app)
    client.cookies.set("mdarix_session", token)
    return client, user_id, token


def _product(tenant_id) -> str:
    now = datetime.now(timezone.utc)
    tag = uuid.uuid4().hex[:8].upper()
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        product = Product(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            product_identifier=f"CA-P-{tag}",
            name=f"Audit Pump {tag}",
            created_at=now,
            updated_at=now,
        )
        db.add(product)
        db.commit()
        return str(product.id)


def _open(client, product_id: str) -> dict:
    made = client.post(
        "/api/v1/investigations",
        json={"product_id": product_id, "investigation_question": QUESTION, "assign_to_me": True},
    )
    assert made.status_code == 201, made.text
    return made.json()


def _evidence(tenant_id, title: str, ingested_at: datetime) -> tuple[str, str]:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = Evidence(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            evidence_identifier=f"CA-E-{uuid.uuid4().hex[:10].upper()}",
            evidence_type="SERVICE_REPORT",
            title=title,
            source_system="test",
            ingestion_timestamp=ingested_at,
            recorded_timestamp=ingested_at,
            created_at=ingested_at,
            updated_at=ingested_at,
        )
        db.add(row)
        db.commit()
        return str(row.id), row.business_id


def _link(client, case_id: str, evidence_id: str) -> None:
    linked = client.post(
        f"/api/v1/investigations/{case_id}/evidence-links",
        json={"evidence_ids": [evidence_id], "reason": "Service report relevant to the alarms"},
    )
    assert linked.status_code == 200, linked.text


def _legacy_signature(decision_id: str, signer: str) -> dict:
    material = {
        "decision_id": decision_id,
        "version": "1",
        "type": "INVESTIGATION_DECISION",
        "decision": "APPROVE",
        "remarks": LEGACY_REMARKS,
    }
    fingerprint = hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()
    return {
        "content_fingerprint": fingerprint,
        "signature_hash": hashlib.sha256((fingerprint + signer + "1").encode()).hexdigest(),
    }


def _history(tenant_id, case_id: str, investigator: str, approver: str, e1: str) -> dict:
    """A signal, a completed risk review, an AI run reviewed by a person, a hypothesis judged after the decision,
    a signed brief decision (with its context snapshot) disclosing the AI run, and a legacy decision signed the
    way the governance signature does."""
    now = datetime.now(timezone.utc)
    case_uuid = uuid.UUID(case_id)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        case = db.query(Investigation).filter(Investigation.id == case_uuid).one()
        signal = Signal(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            title="Occlusion alarms above threshold",
            origin="MANUAL",
            status="INVESTIGATION_OPEN",
            created_by=investigator,
            created_at=now - timedelta(days=5),
            updated_at=now - timedelta(days=5),
        )
        db.add(signal)
        db.flush()
        db.add(
            SignalEvent(
                tenant_id=tenant_id,
                signal_id=signal.id,
                event_type="TRIAGE_STARTED",
                actor_ref=investigator,
                actor_role="INVESTIGATOR",
                from_status="NEW",
                to_status="TRIAGE",
                details={"password": "Hunter2!", "note": "first look"},
                created_at=now - timedelta(days=5),
            )
        )
        db.add(
            InvestigationSignal(
                tenant_id=tenant_id, investigation_id=case_uuid, signal_id=signal.id, created_by=investigator
            )
        )
        db.add(
            CaseReview(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                investigation_id=case_uuid,
                review_type="RISK",
                status="COMPLETED",
                requested_by=investigator,
                reviewer_user_id=uuid.UUID(investigator),
                reviewer_role="RISK_REVIEWER",
                outcome="RISK_CONTROL_REVIEW_REQUIRED",
                rationale="The alarm threshold control needs a second look",
                completed_at=now - timedelta(minutes=30),
                created_at=now - timedelta(hours=2),
                updated_at=now - timedelta(minutes=30),
            )
        )
        run = AIExecution(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            investigation_id=case_uuid,
            requestor_ref=investigator,
            provider="mdarix-controlled-hypothesis-engine",
            model_name="mdarix-rule-grounded-hypothesis-engine",
            model_version="1.0",
            prompt_template_version="R1-Day12-Hypothesis-v1",
            orchestration_version="R1-Day12",
            context_refs={"investigation_id": case_id, "api_key": SECRET_MARKER},
            evidence_refs={"evidence_identifiers": ["CA-E-1"]},
            structured_input={"token": SECRET_MARKER},
            structured_output={"guardrails": {"no_root_cause_conclusion": True, "human_authority_required": True}},
            validation_status="VALIDATED",
            execution_timestamp=now - timedelta(minutes=20),
            latency_ms=1200,
        )
        db.add(run)
        hypothesis = Hypothesis(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            investigation_id=case_uuid,
            statement="The sensor batch drifts at low temperature",
            origin="human",
            human_status="STRONGLY_SUPPORTED",
            status_changed_by=investigator,
            status_changed_at=now + timedelta(minutes=1),
            created_by=investigator,
            created_at=now - timedelta(hours=1),
            updated_at=now - timedelta(hours=1),
        )
        db.add(hypothesis)
        db.flush()
        db.add(
            HumanReview(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                investigation_id=case_uuid,
                ai_execution_id=run.id,
                reviewer_ref=investigator,
                disposition="ACCEPTED",
                comments="Hypotheses are plausible",
                review_timestamp=now - timedelta(minutes=15),
            )
        )
        db.add(
            IntelligenceEvent(
                tenant_id=tenant_id,
                investigation_id=case_uuid,
                object_type="HYPOTHESIS",
                object_id=hypothesis.id,
                event_type="STATUS_CHANGED",
                from_value="PROPOSED",
                to_value="STRONGLY_SUPPORTED",
                reason="Bench test reproduced the drift",
                actor_ref=investigator,
                actor_role="INVESTIGATOR",
                details={"business_id": hypothesis.business_id},
                created_at=now + timedelta(minutes=1),
            )
        )
        db.commit()
        run_business_id = run.business_id

        # The approved brief and the signed decision on it (as the signing step stores them).
        bind_tenant(db, tenant_id)
        brief = DecisionBriefVersion(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            investigation_id=case_uuid,
            version=1,
            status="APPROVED_FOR_DECISION",
            title="Decision brief",
            content={},
            narrative={},
            content_hash=brief_rules.content_hash({}, {}),
            created_by=investigator,
            created_at=now - timedelta(minutes=10),
            updated_at=now - timedelta(minutes=10),
        )
        db.add(brief)
        db.flush()
        evidence_hash = rules.evidence_set_hash([(e1, "UNREVIEWED", "UNREVIEWED")])
        decision_id, snapshot_id = uuid.uuid4(), uuid.uuid4()
        snapshot = brief_rules.jsonable(
            {
                "decision_id": decision_id,
                "brief": {"id": brief.id, "business_id": brief.business_id, "version": 1, "content_hash": None},
                "evidence_set_hash": evidence_hash,
                "scope_version": 1,
            }
        )
        decision = Decision(
            id=decision_id,
            tenant_id=tenant_id,
            investigation_id=case_uuid,
            decision_identifier=f"CA-D-{uuid.uuid4().hex[:10]}",
            decision_type="CASE_DECISION",
            disposition="ACCEPT_CONCLUSION",
            rationale="The sensor drift explains the alarms",
            decision_status="SIGNED",
            authorized_by_ref=approver,
            context_snapshot={"snapshot_id": str(snapshot_id), "snapshot_hash": decision_rules.snapshot_hash(snapshot)},
            updated_at=now,
            decision_timestamp=now,
            created_at=now,
            decision_kind="BRIEF",
            brief_version_id=brief.id,
            outcome="ACCEPT_CONCLUSION",
            decided_by_user_id=uuid.UUID(approver),
            decided_under_role="APPROVER",
            decided_at=now,
            brief_content_hash=brief.content_hash,
            evidence_set_hash=evidence_hash,
            context_snapshot_id=snapshot_id,
            ai_execution_refs=[run_business_id],
        )
        db.add(decision)
        db.flush()
        db.add(
            ContextSnapshot(
                id=snapshot_id,
                tenant_id=tenant_id,
                decision_id=decision_id,
                decision_version=brief.content_hash,
                snapshot=snapshot,
                created_by=approver,
                created_at=now,
            )
        )
        # A legacy decision signed the way governance signatures are made, valid until it is changed.
        legacy = Decision(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            investigation_id=case_uuid,
            decision_identifier=f"CA-L-{uuid.uuid4().hex[:10]}",
            decision_type="INVESTIGATION_DECISION",
            disposition="APPROVE",
            rationale=LEGACY_REMARKS,
            decision_status="SIGNED",
            authorized_by_ref=approver,
            updated_at=now - timedelta(days=1),
            decision_timestamp=now - timedelta(days=1),
            created_at=now - timedelta(days=1),
        )
        db.add(legacy)
        db.flush()
        signature = SignedApprovalRecord(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            object_type="Decision",
            object_id=legacy.id,
            object_version="1",
            decision_type="INVESTIGATION_DECISION",
            decision="APPROVE",
            remarks=LEGACY_REMARKS,
            signer_user_id=approver,
            signer_role="APPROVER",
            signature_meaning="Approved as the accountable approver",
            status="SIGNED",
            signed_at=now - timedelta(days=1),
            created_at=now - timedelta(days=1),
            **_legacy_signature(str(legacy.id), approver),
        )
        db.add(signature)
        states.set_state(case, "DECIDED", now)
        db.commit()
        return {
            "decided_at": now,
            "decision_id": str(decision_id),
            "decision_business_id": decision.business_id,
            "legacy_business_id": legacy.business_id,
            "signature_id": str(signature.id),
            "run_business_id": run_business_id,
            "signal_business_id": signal.business_id,
            "brief_business_id": brief.business_id,
            "evidence_hash": evidence_hash,
            "hypothesis_business_id": hypothesis.business_id,
        }


@pytest.fixture(scope="module")
def org():
    """A fresh organization with an investigator (the case owner), an approver and a viewer, one case with history
    from several sources and a second piece of evidence linked after the decision; and another organization with a
    case of its own."""
    tenant_id = _organization("CASEAUDIT")
    other_id = _organization("CASEAUDIT_OTHER")
    try:
        investigator, investigator_id, investigator_token = _client(tenant_id, "INVESTIGATOR", "Ivy")
        approver, approver_id, _ = _client(tenant_id, "APPROVER", "Abe")
        viewer, _, _ = _client(tenant_id, "VIEWER", "Vera")
        case = _open(investigator, _product(tenant_id))
        now = datetime.now(timezone.utc)
        e1, e1_business_id = _evidence(tenant_id, "Field service report", now - timedelta(days=3))
        # Recorded before the decision, but linked to the case only after it: it arrived later for the case.
        e2, e2_business_id = _evidence(tenant_id, "Late service report", now - timedelta(days=2))
        _link(investigator, case["id"], e1)
        made = _history(tenant_id, case["id"], investigator_id, approver_id, e1)
        _link(investigator, case["id"], e2)
        other_client, _, _ = _client(other_id, "INVESTIGATOR", "Otto")
        other_case = _open(other_client, _product(other_id))
        yield {
            "tenant_id": tenant_id,
            "case": case,
            "investigator": investigator,
            "investigator_token": investigator_token,
            "approver": approver,
            "viewer": viewer,
            "e1": e1_business_id,
            "e2": e2_business_id,
            "other_client": other_client,
            "other_case": other_case,
            **made,
        }
    finally:
        _purge(tenant_id)
        _purge(other_id)


def _base(org) -> str:
    return f"/api/v1/investigations/{org['case']['id']}/trust"


# ---------------------------------------------------------------------------------------------------- timeline


def test_the_timeline_merges_every_source_in_order_with_business_ids(org):
    response = org["viewer"].get(_base(org) + "/timeline", params={"page_size": 200})
    assert response.status_code == 200, response.text
    body = response.json()
    items = body["items"]
    assert body["total"] == len(items) and sum(body["categories"].values()) == body["total"]
    assert {"CASE", "SIGNAL", "EVIDENCE", "REVIEW", "AI", "BRIEF", "DECISION", "SIGNATURE", "IMPACT"} <= set(
        body["categories"]
    )
    times = [item["at"] for item in items if item["at"]]
    assert times == sorted(times, key=lambda value: datetime.fromisoformat(value))
    for item in items:
        assert item["category"] in rules.CATEGORIES and item["origin"] in rules.ORIGINS
        assert item["title"] and item["event"]
    titles = {item["title"] for item in items}
    assert "Risk review completed: Risk control review required" in titles

    # Each evidence link appears once, although both the history and the audit trail recorded it.
    links = [item for item in items if item["event"] == "EVIDENCE_LINKED"]
    assert sorted(item["object"]["business_id"] for item in links) == sorted([org["e1"], org["e2"]])

    ai = next(item for item in items if item["event"] == "AI_RUN_RECORDED")
    assert ai["origin"] == "AI" and ai["object"]["business_id"] == org["run_business_id"]
    assert (
        ai["details"]["model"] == "mdarix-rule-grounded-hypothesis-engine" and ai["details"]["model_version"] == "1.0"
    )
    signed = next(item for item in items if item["event"] == "CASE_DECISION_SIGNED")
    assert signed["object"]["business_id"] == org["decision_business_id"]
    assert signed["actor"] == {"name": "Abe Audit", "role_label": signed["actor"]["role_label"]}
    signal = next(item for item in items if item["event"] == "SIGNAL_TRIAGE_STARTED")
    assert signal["object"]["business_id"] == org["signal_business_id"] and "password" not in signal["details"]

    # People by name, never by account id; no secrets anywhere.
    text = response.text
    assert SECRET_MARKER not in text and "Hunter2!" not in text and org["investigator_token"] not in text
    assert "password_hash" not in text
    for item in items:
        if item["actor"] is not None:
            assert rules.as_uuid_text(item["actor"]["name"]) is None


def test_the_timeline_filters_by_category_actor_and_time(org):
    only_ai = org["investigator"].get(_base(org) + "/timeline", params={"types": "AI"}).json()
    assert only_ai["items"] and {item["category"] for item in only_ai["items"]} == {"AI"}
    # The counts ignore the category filter, so the other categories still show theirs.
    assert only_ai["categories"]["AI"] == only_ai["total"] and {"DECISION", "EVIDENCE"} <= set(only_ai["categories"])
    by_abe = org["investigator"].get(_base(org) + "/timeline", params={"actor": "abe audit"}).json()
    assert by_abe["items"] and all(item["actor"]["name"] == "Abe Audit" for item in by_abe["items"])
    later = org["investigator"].get(
        _base(org) + "/timeline", params={"since": (org["decided_at"] + timedelta(days=1)).isoformat()}
    )
    assert later.status_code == 200 and later.json()["total"] == 0
    paged = org["investigator"].get(_base(org) + "/timeline", params={"page": 1, "page_size": 2}).json()
    assert len(paged["items"]) == 2 and paged["total"] > 2


# ------------------------------------------------------------------------------------------------------ replay


def test_the_replay_at_signing_separates_evidence_known_then_from_evidence_linked_later(org):
    response = org["viewer"].get(_base(org) + "/replay")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision"]["business_id"] == org["decision_business_id"]
    assert body["decision"]["decision_id"] == org["decision_id"]
    assert body["decision"]["outcome"] == "ACCEPT_CONCLUSION" and body["decision"]["signer"]["name"] == "Abe Audit"
    assert datetime.fromisoformat(body["as_known_at"]) == org["decided_at"]
    assert [item["business_id"] for item in body["evidence"]["known_then"]] == [org["e1"]]
    assert [item["business_id"] for item in body["evidence"]["arrived_later"]] == [org["e2"]]
    assert body["evidence"]["known_then"][0]["review_status"] == "UNREVIEWED"
    snapshot = body["snapshot"]
    assert snapshot["available"] is True and snapshot["brief_business_id"] == org["brief_business_id"]
    assert snapshot["evidence_set_hash"] == org["evidence_hash"] and snapshot["snapshot_hash_verified"] is True
    # The person judged the hypothesis only after the decision: at signing it was still as first proposed.
    (hypothesis,) = body["hypotheses"]
    assert hypothesis["business_id"] == org["hypothesis_business_id"]
    assert hypothesis["human_status"] == "PROPOSED" and hypothesis["human_status_now"] == "STRONGLY_SUPPORTED"
    assert [review["outcome"] for review in body["reviews"]] == ["RISK_CONTROL_REVIEW_REQUIRED"]
    integrity = body["integrity"]
    assert integrity["evidence_set_hash_then"] == org["evidence_hash"]
    assert integrity["evidence_set_hash_then_source"] == "SIGNED_DECISION"
    assert integrity["changed_since"] is True and integrity["evidence_set_hash_now"] != org["evidence_hash"]
    assert body["limitations"]
    same = org["viewer"].get(_base(org) + "/replay", params={"decision_id": org["decision_id"]}).json()
    assert same["evidence"] == body["evidence"]


def test_the_replay_after_the_late_evidence_knows_both(org):
    moment = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    body = org["viewer"].get(_base(org) + "/replay", params={"as_known_at": moment}).json()
    assert sorted(item["business_id"] for item in body["evidence"]["known_then"]) == sorted([org["e1"], org["e2"]])
    assert body["evidence"]["arrived_later"] == []
    assert body["snapshot"]["available"] is False
    assert body["decision"]["business_id"] == org["decision_business_id"]
    assert body["hypotheses"][0]["human_status"] == "STRONGLY_SUPPORTED"
    assert body["integrity"]["evidence_set_hash_then_source"] == "RECONSTRUCTED"
    assert body["integrity"]["changed_since"] is False
    before = (org["decided_at"] - timedelta(days=30)).isoformat()
    early = org["viewer"].get(_base(org) + "/replay", params={"as_known_at": before}).json()
    assert early["decision"] is None and early["evidence"]["known_then"] == [] and early["hypotheses"] == []
    unknown = org["viewer"].get(_base(org) + "/replay", params={"decision_id": str(uuid.uuid4())})
    assert unknown.status_code == 404


# ----------------------------------------------------------------------------------------------------- AI runs


def test_the_ai_runs_list_the_run_the_signed_decision_disclosed(org):
    response = org["viewer"].get(_base(org) + "/ai-runs")
    assert response.status_code == 200, response.text
    body = response.json()
    (run,) = [item for item in body["items"] if item["business_id"] == org["run_business_id"]]
    assert run["kind"] == "hypotheses" and run["provider"] == "mdarix-controlled-hypothesis-engine"
    assert run["model"] == "mdarix-rule-grounded-hypothesis-engine" and run["model_version"] == "1.0"
    assert run["orchestration_version"] == "R1-Day12" and run["prompt_template_version"] == "R1-Day12-Hypothesis-v1"
    assert len(run["context_hash"]) == 64 and run["duration_ms"] == 1200 and run["started_at"]
    assert run["guardrails"]["checks"] == 2 and run["guardrails"]["passed"] == 2
    assert run["human_review"]["status"] == "ACCEPTED" and run["human_review"]["by"] == "Ivy Audit"
    assert run["used_in_signed_decision"] is True
    assert body["counts"]["total"] == len(body["items"]) and body["counts"]["used_in_signed_decision"] == 1
    assert SECRET_MARKER not in response.text


# --------------------------------------------------------------------------------------------------- integrity


def test_integrity_finds_a_changed_signature_invalid(org):
    tenant_id = org["tenant_id"]
    response = org["viewer"].get(_base(org) + "/integrity")
    assert response.status_code == 200, response.text
    body = response.json()
    (legacy,) = [item for item in body["signatures"] if item["decision_business_id"] == org["legacy_business_id"]]
    assert legacy["status"] == "VALID" and legacy["signer"]["name"] == "Abe Audit"
    assert rules.as_uuid_text(legacy["decision_id"]) == legacy["decision_id"]
    assert body["audit_chain"]["status"] == "VALID" and body["audit_chain"]["checked_events"] > 0
    assert [(item["business_id"], item["hash_verified"]) for item in body["brief_hashes"]] == [
        (org["brief_business_id"], True)
    ]
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = db.query(SignedApprovalRecord).filter(SignedApprovalRecord.id == uuid.UUID(org["signature_id"])).one()
        row.remarks = LEGACY_REMARKS + " (edited)"
        db.commit()
    try:
        tampered = org["viewer"].get(_base(org) + "/integrity").json()
        (legacy,) = [
            item for item in tampered["signatures"] if item["decision_business_id"] == org["legacy_business_id"]
        ]
        assert legacy["status"] == "INVALID"
        assert {check["key"]: check["ok"] for check in legacy["checks"]}["fingerprint"] is False
        assert tampered["summary"]["signatures_invalid"] >= 1
    finally:
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            row = db.query(SignedApprovalRecord).filter(SignedApprovalRecord.id == uuid.UUID(org["signature_id"])).one()
            row.remarks = LEGACY_REMARKS
            db.commit()


# ------------------------------------------------------------------------------------------------------ export


def test_the_export_needs_data_export_and_is_audited_with_its_sha256(org):
    assert org["viewer"].get(_base(org) + "/export").status_code == 403
    response = org["investigator"].get(_base(org) + "/export", params={"format": "json"})
    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"].startswith("attachment;")
    digest = hashlib.sha256(response.content).hexdigest()
    assert response.headers["x-content-sha256"] == digest
    document = response.json()
    assert document["timeline"] and document["ai_runs"]["items"] and document["integrity"]["signatures"]
    assert SECRET_MARKER not in response.text
    with SessionLocal() as db:
        bind_tenant(db, org["tenant_id"])
        events = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.entity_id == uuid.UUID(org["case"]["id"]),
                AuditEvent.action == "CASE_AUDIT_EXPORTED",
            )
            .all()
        )
    assert digest in {(event.details or {}).get("sha256") for event in events}
    csv_response = org["investigator"].get(_base(org) + "/export", params={"format": "csv"})
    assert csv_response.status_code == 200 and csv_response.headers["content-type"].startswith("text/csv")
    assert csv_response.text.splitlines()[0].startswith("section,at,category,event,title")
    timeline = org["investigator"].get(_base(org) + "/timeline", params={"types": "AUDIT"}).json()
    assert "CASE_AUDIT_EXPORTED" in {item["event"] for item in timeline["items"]}


# ------------------------------------------------------------------------------------------------ organizations


def test_another_organizations_case_is_not_found(org):
    other_base = f"/api/v1/investigations/{org['other_case']['id']}/trust"
    for path in ("/timeline", "/replay", "/ai-runs", "/integrity", "/export"):
        assert org["investigator"].get(other_base + path).status_code == 404, path
        assert org["other_client"].get(_base(org) + path).status_code == 404, path
    assert org["investigator"].get(f"/api/v1/investigations/{uuid.uuid4()}/trust/timeline").status_code == 404
