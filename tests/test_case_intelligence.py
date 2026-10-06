"""Case intelligence end to end: hypotheses people add, judge and link evidence to (and withdraw it from), the
contradictions view, the unknown lifecycle with its evidence requests, failure chains built by hand or adopted from an
AI run with link state changes, observations of an explicit kind (never an AI interpretation by a person), the
history, readiness, permissions, organization isolation, closed cases, and an AI re-run that keeps people's work.

Everything runs in a fresh organization of its own (on the shared plane), deleted at the end.
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
from backend.app.db.models.evidence_intelligence import EvidenceObservation
from backend.app.db.models.foundation import (
    AIExecution,
    AuditEvent,
    AuthUser,
    Evidence,
    Hypothesis,
    HypothesisEvidence,
    Investigation,
    Product,
    TenantMembership,
    Unknown,
)
from backend.app.db.models.stage3 import SupplierEvidenceRequest
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from backend.app.main import app
from tests.reports_seed import role_client

PASSWORD = "Case intelligence 2026!"
REASON = "The service report shows the alarm before the release"
OTHER_REASON = "No sterilization record exists for this lot"


@pytest.fixture(scope="module")
def org():
    """A fresh organization with a product, an investigator, a risk reviewer (evidence.review only) and a viewer."""
    from backend.app.customer_lifecycle import build_customer_tenant
    from backend.app.trial.retention import purge_trial

    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        customer, tenant = build_customer_tenant(
            db=db,
            tenant_key=f"INTELLIGENCE_{uuid.uuid4().hex[:8].upper()}",
            name="Case intelligence",
            status="ACTIVE",
            now=now,
        )
        db.add(customer)
        db.add(tenant)
        db.commit()  # registers the organization on the shared plane (migration md20)
        tenant_id = tenant.id
    people = {}
    for name, role in (("investigator", "INVESTIGATOR"), ("risk", "RISK_REVIEWER"), ("viewer", "VIEWER")):
        people[name] = _client(tenant_id, role, name.title())
    try:
        yield {"tenant_id": tenant_id, "product_id": _product(tenant_id), **people}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:case-intelligence-cleanup")


def _client(tenant_id, role: str, name: str) -> tuple[TestClient, str]:
    with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        user = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            username=f"intelligence-{role.lower()}-{uuid.uuid4().hex[:8]}@example.invalid",
            display_name=f"{name} Intelligence",
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
    return client, user_id


def _product(tenant_id) -> str:
    now = datetime.now(timezone.utc)
    tag = uuid.uuid4().hex[:8].upper()
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        product = Product(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            product_identifier=f"INT-P-{tag}",
            name=f"Intelligence Pump {tag}",
            created_at=now,
            updated_at=now,
        )
        db.add(product)
        db.commit()
        return str(product.id)


def _case(org) -> dict:
    client, _ = org["investigator"]
    made = client.post(
        "/api/v1/investigations",
        json={
            "product_id": org["product_id"],
            "investigation_question": "Why do occlusion alarms rise after release B?",
            "assign_to_me": True,
        },
    )
    assert made.status_code == 201, made.text
    return made.json()


def _base(case_id) -> str:
    return f"/api/v1/investigations/{case_id}/intelligence"


def _evidence(tenant_id, *, case_id=None, title: str = "Service report") -> dict:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = Evidence(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            evidence_identifier=f"INT-{uuid.uuid4().hex[:10].upper()}",
            investigation_id=uuid.UUID(case_id) if case_id else None,
            evidence_type="SERVICE_REPORT",
            title=title,
            source_system="Service desk",
            source_identifier=f"SR-{uuid.uuid4().hex[:6]}",
            source_timestamp=now - timedelta(days=3),
            ingestion_timestamp=now,
            content="Occlusion alarm reproduced at 4 psi.",
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        return {"id": str(row.id), "identifier": row.evidence_identifier, "business_id": row.business_id}


def _hypothesis(tenant_id, case_id, statement: str, *, origin: str = "ai", status: str = "mixed_evidence") -> dict:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = Hypothesis(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            investigation_id=uuid.UUID(case_id),
            statement=statement,
            status=status,
            origin=origin,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        return {"id": str(row.id), "business_id": row.business_id}


def _ai_link(tenant_id, hypothesis_id, evidence_id, relation_type: str = "contradict") -> str:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = HypothesisEvidence(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            hypothesis_id=uuid.UUID(hypothesis_id),
            evidence_id=uuid.UUID(evidence_id),
            relation_type=relation_type,
            rationale="The complaint precedes the release",
            created_by_type="system",
            created_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
        return str(row.id)


def _unknown(tenant_id, case_id, *, hypothesis_id=None, status: str = "open", origin: str = "system") -> dict:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = Unknown(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            investigation_id=uuid.UUID(case_id),
            hypothesis_id=uuid.UUID(hypothesis_id) if hypothesis_id else None,
            category="evidence_gap",
            description=f"Unknown {uuid.uuid4().hex[:6]}: was the alarm log exported?",
            status=status,
            origin=origin,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        return {"id": str(row.id), "business_id": row.business_id}


def _ai_execution(tenant_id, case_id, *, provider: str, model: str, version: str, output: dict) -> str:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = AIExecution(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            investigation_id=uuid.UUID(case_id),
            provider=provider,
            model_name=model,
            orchestration_version=version,
            structured_output=output,
            validation_status="COMPLETED",
            execution_timestamp=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
        return str(row.id)


def _row(tenant_id, model, row_id):
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        found = db.query(model).filter(model.id == uuid.UUID(str(row_id))).one()
        db.expunge(found)
        return found


def _close(tenant_id, case_id) -> None:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        case = db.query(Investigation).filter(Investigation.id == uuid.UUID(case_id)).one()
        case.workflow_state = "CLOSED"
        case.status = "closed"
        db.commit()


def _audit_actions(tenant_id, entity_id) -> list[str]:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        return [
            row[0]
            for row in db.query(AuditEvent.action)
            .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.entity_id == uuid.UUID(str(entity_id)))
            .order_by(AuditEvent.created_at)
        ]


def _code(response) -> str | None:
    detail = response.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


def _get(client, path: str, **params) -> dict:
    response = client.get(path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _readiness(client, case_id) -> dict:
    body = _get(client, f"/api/v1/investigations/{case_id}/readiness")
    return {check["key"]: check for check in body["checks"]}


def _item(items: list[dict], item_id: str) -> dict:
    (found,) = [item for item in items if item["id"] == item_id]
    return found


# ------------------------------------------------------------------------------------------------- hypotheses


def test_people_add_judge_and_link_evidence_to_hypotheses(org):
    tenant_id = org["tenant_id"]
    client, _ = org["investigator"]
    risk, _ = org["risk"]
    case = _case(org)
    base = _base(case["id"])
    direct = _evidence(tenant_id, case_id=case["id"])
    elsewhere = _evidence(tenant_id, title="Unrelated report")
    ai = _hypothesis(tenant_id, case["id"], "Tubing wall thickness varies between lots")

    made = client.post(
        f"{base}/hypotheses", json={"statement": "Release B firmware lowered the alarm threshold", "rationale": REASON}
    )
    assert made.status_code == 201, made.text
    mine = made.json()
    assert mine["origin"] == "HUMAN" and mine["human_status"] == "PROPOSED" and mine["ai_status"] is None
    assert mine["kind_label"] == "Added by Investigator Intelligence"
    assert mine["created_by_name"] == "Investigator Intelligence" and mine["status_reason"] == REASON
    assert mine["business_id"] and mine["evidence"] == {
        "supporting": [],
        "contradicting": [],
        "contextual": [],
        "unresolved": [],
    }
    duplicate = client.post(f"{base}/hypotheses", json={"statement": "RELEASE B FIRMWARE LOWERED THE ALARM THRESHOLD"})
    assert duplicate.status_code == 409 and _code(duplicate) == "HYPOTHESIS_EXISTS"
    assert client.post(f"{base}/hypotheses", json={"statement": "too short"}).status_code == 422

    listed = _get(client, f"{base}/hypotheses")
    theirs = _item(listed["items"], ai["id"])
    assert theirs["kind_label"] == "AI interpretation" and theirs["origin"] == "AI"
    assert theirs["ai_status"] == "mixed_evidence" and theirs["ai_status_label"] == "Mixed evidence"
    assert theirs["human_status"] is None and theirs["business_id"] == ai["business_id"]
    assert theirs["actions"] == {"can_set_status": True, "can_link_evidence": True}
    assert listed["counts"]["ai"] == 1 and listed["counts"]["human"] == 1 and listed["counts"]["not_judged"] == 1

    path = f"{base}/hypotheses/{ai['id']}"
    judged = client.post(f"{path}/status", json={"human_status": "weakly_supported", "reason": REASON})
    assert judged.status_code == 200, judged.text
    body = judged.json()
    assert body["human_status"] == "WEAKLY_SUPPORTED" and body["human_status_label"] == "Weakly supported"
    assert body["ai_status"] == "mixed_evidence"  # the AI's own status stays as the AI left it
    assert body["kind_label"] == "Judged by Investigator Intelligence" and body["status_reason"] == REASON
    assert body["status_changed_by_name"] == "Investigator Intelligence" and body["status_changed_at"]
    assert _row(tenant_id, Hypothesis, ai["id"]).reviewer_disposition == "HUMAN_JUDGED"
    same = client.post(f"{path}/status", json={"human_status": "WEAKLY_SUPPORTED", "reason": REASON})
    assert same.status_code == 409 and _code(same) == "HYPOTHESIS_STATUS_UNCHANGED"
    assert client.post(f"{path}/status", json={"human_status": "CONFIRMED", "reason": REASON}).status_code == 422
    assert client.post(f"{path}/status", json={"human_status": "RETIRED", "reason": "short"}).status_code == 422

    linked = client.post(
        f"{path}/evidence", json={"evidence_id": direct["id"], "relation": "CONTRADICTING", "rationale": REASON}
    )
    assert linked.status_code == 201, linked.text
    (link,) = linked.json()["evidence"]["contradicting"]
    assert link["added_by"] == "Investigator Intelligence" and link["created_by_type"] == "human"
    assert link["evidence"]["business_id"] == direct["business_id"] and link["retracted"] is False
    again = client.post(
        f"{path}/evidence", json={"evidence_id": direct["id"], "relation": "contradicting", "rationale": REASON}
    )
    assert again.status_code == 409 and _code(again) == "EVIDENCE_ALREADY_LINKED"
    context = client.post(
        f"{path}/evidence", json={"evidence_id": direct["id"], "relation": "CONTEXTUAL", "rationale": REASON}
    )
    assert context.status_code == 201, context.text
    assert len(context.json()["evidence"]["contextual"]) == 1
    outside = client.post(
        f"{path}/evidence", json={"evidence_id": elsewhere["id"], "relation": "SUPPORTING", "rationale": REASON}
    )
    assert outside.status_code == 404 and _code(outside) == "EVIDENCE_NOT_IN_CASE"
    missing = client.post(
        f"{path}/evidence", json={"evidence_id": str(uuid.uuid4()), "relation": "SUPPORTING", "rationale": REASON}
    )
    assert missing.status_code == 404 and _code(missing) == "EVIDENCE_NOT_FOUND"

    # evidence.review alone links evidence, under the role that grants it; judging needs investigation.work.
    by_reviewer = risk.post(
        f"{path}/evidence", json={"evidence_id": direct["id"], "relation": "SUPPORTING", "rationale": REASON}
    )
    assert by_reviewer.status_code == 201, by_reviewer.text
    assert by_reviewer.json()["evidence"]["supporting"][0]["added_by"] == "Risk Intelligence"
    refused = risk.post(f"{path}/status", json={"human_status": "RETIRED", "reason": REASON})
    assert refused.status_code == 403 and _code(refused) == "PERMISSION_DENIED"
    assert risk.post(f"{base}/hypotheses", json={"statement": "A reviewer's own hypothesis"}).status_code == 403

    withdrawn = client.post(f"{path}/evidence/{link['id']}/retract", json={"reason": REASON})
    assert withdrawn.status_code == 200, withdrawn.text
    (gone,) = withdrawn.json()["evidence"]["contradicting"]
    assert gone["retracted"] is True and gone["retracted_by_name"] == "Investigator Intelligence"
    assert gone["retraction_reason"] == REASON
    twice = client.post(f"{path}/evidence/{link['id']}/retract", json={"reason": REASON})
    assert twice.status_code == 409 and _code(twice) == "EVIDENCE_LINK_RETRACTED"
    unknown_link = client.post(f"{path}/evidence/{uuid.uuid4()}/retract", json={"reason": REASON})
    assert unknown_link.status_code == 404 and _code(unknown_link) == "EVIDENCE_LINK_NOT_FOUND"
    # A withdrawn link is kept; the same evidence can be linked again.
    relinked = client.post(
        f"{path}/evidence", json={"evidence_id": direct["id"], "relation": "CONTRADICTING", "rationale": REASON}
    )
    assert relinked.status_code == 201 and len(relinked.json()["evidence"]["contradicting"]) == 2
    assert _row(tenant_id, HypothesisEvidence, link["id"]).retracted_at is not None

    history = _get(client, f"{base}/history")
    assert [item["event_type"] for item in history["items"]] == [
        "EVIDENCE_LINKED",
        "EVIDENCE_RETRACTED",
        "EVIDENCE_LINKED",
        "EVIDENCE_LINKED",
        "EVIDENCE_LINKED",
        "STATUS_CHANGED",
        "CREATED",
    ]
    assert history["total"] == 7 and history["page"] == 1 and history["page_size"] == 50
    status_event = history["items"][5]
    assert status_event["object_business_id"] == ai["business_id"] and status_event["reason"] == REASON
    assert status_event["from_value"] is None and status_event["to_value"] == "WEAKLY_SUPPORTED"
    assert status_event["actor_name"] == "Investigator Intelligence" and status_event["actor_role"] == "INVESTIGATOR"
    assert history["items"][2]["actor_role"] == "RISK_REVIEWER"
    page = _get(client, f"{base}/history", page=2, page_size=2)
    assert [item["event_type"] for item in page["items"]] == ["EVIDENCE_LINKED", "EVIDENCE_LINKED"]
    assert page["total"] == 7 and page["page"] == 2 and page["page_size"] == 2
    assert len(_get(client, f"{base}/history", page=4, page_size=2)["items"]) == 1
    assert status_event["object_label"] == "Hypothesis" and status_event["event_label"] == "Status changed"
    assert _audit_actions(tenant_id, ai["id"]) == ["INTELLIGENCE_STATUS_CHANGED"]
    assert _audit_actions(tenant_id, mine["id"]) == ["INTELLIGENCE_CREATED"]
    assert _audit_actions(tenant_id, link["id"]) == ["INTELLIGENCE_EVIDENCE_LINKED", "INTELLIGENCE_EVIDENCE_RETRACTED"]

    retired = client.post(f"{base}/hypotheses/{mine['id']}/status", json={"human_status": "RETIRED", "reason": REASON})
    assert retired.status_code == 200
    assert mine["id"] not in [item["id"] for item in _get(client, f"{base}/hypotheses")["items"]]
    assert mine["id"] in [item["id"] for item in _get(client, f"{base}/hypotheses", include_retired=True)["items"]]


# ---------------------------------------------------------------------------------------------- contradictions


def test_contradictions_from_people_and_the_ai_and_their_readiness_check(org):
    from challenger.engine import MODEL, ORCHESTRATION_VERSION, PROVIDER
    from challenger.schemas import ChallengeSet, InvestigationChallenge
    from investigator.schemas import SourceReference

    tenant_id = org["tenant_id"]
    client, _ = org["investigator"]
    case = _case(org)
    base = _base(case["id"])
    direct = _evidence(tenant_id, case_id=case["id"])
    reviewed = _evidence(tenant_id, case_id=case["id"], title="Field return analysis")
    ai = _hypothesis(tenant_id, case["id"], "Tubing supplier change raised occlusion alarms")
    _ai_link(tenant_id, ai["id"], direct["id"])
    review = client.post(
        f"/api/v1/investigations/{case['id']}/evidence/{reviewed['id']}/review",
        json={"review_status": "ACCEPTED", "relationship": "CONTRADICTING", "reason": REASON},
    )
    assert review.status_code == 200, review.text
    case_uuid = uuid.UUID(case["id"])
    challenges = ChallengeSet(
        investigation_id=case_uuid,
        source_hypothesis_set_id=uuid.uuid4(),
        context_snapshot_id="test:current:None",
        context_snapshot_version="1",
        challenges=[
            InvestigationChallenge(
                investigation_id=case_uuid,
                hypothesis_id=uuid.UUID(ai["id"]),
                challenge_type="CONTRADICTORY_EVIDENCE",
                statement="Alarms were reported before the supplier change",
                rationale="The service report predates the change",
                contradiction_references=[
                    SourceReference(reference_type="EVIDENCE", evidence_identifier=direct["identifier"])
                ],
            )
        ],
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    output = challenges.model_dump(mode="json")
    execution_id = _ai_execution(
        tenant_id, case["id"], provider=PROVIDER, model=MODEL, version=ORCHESTRATION_VERSION, output=output
    )

    body = _get(client, f"{base}/contradictions")
    by_kind = {item["kind"]: item for item in body["items"]}
    assert body["counts"] == {"total": 3, "hypothesis_links": 1, "case_evidence": 1, "challenger": 1}
    linked = by_kind["HYPOTHESIS_LINK"]
    assert linked["origin"] == "SYSTEM" and linked["label"] == "AI interpretation" and linked["added_by"] == "AI"
    assert linked["hypothesis"]["business_id"] == ai["business_id"] and linked["created_at"]
    assert linked["evidence"] == {"id": direct["id"], "business_id": direct["business_id"], "title": "Service report"}
    assert linked["judged_since"] is False and linked["rationale"] == "The complaint precedes the release"
    case_level = by_kind["CASE_EVIDENCE"]
    assert case_level["origin"] == "HUMAN" and case_level["label"] == "Person"
    assert case_level["added_by"] == "Investigator Intelligence" and case_level["rationale"] == REASON
    assert case_level["evidence"]["business_id"] == reviewed["business_id"] and case_level["hypothesis"] is None
    assert case_level["judged_since"] is False
    challenge = by_kind["CHALLENGER"]
    assert challenge["origin"] == "AI" and challenge["label"] == "AI interpretation"
    assert challenge["ai_execution_id"] == execution_id and challenge["challenge_type"] == "CONTRADICTORY_EVIDENCE"
    assert challenge["hypothesis"]["id"] == ai["id"] and challenge["judged_since"] is False
    assert challenge["evidence"]["business_id"] == direct["business_id"]
    assert challenge["rationale"] == "The service report predates the change"

    check = _readiness(client, case["id"])["contradictions_documented"]
    assert check["result"] == "PENDING" and ai["business_id"] in check["rationale"]

    judged = client.post(
        f"{base}/hypotheses/{ai['id']}/status", json={"human_status": "CONTRADICTED", "reason": REASON}
    )
    assert judged.status_code == 200, judged.text
    after = {item["kind"]: item for item in _get(client, f"{base}/contradictions")["items"]}
    assert after["HYPOTHESIS_LINK"]["judged_since"] is True and after["CHALLENGER"]["judged_since"] is True
    assert after["HYPOTHESIS_LINK"]["hypothesis"]["human_status"] == "CONTRADICTED"
    assert _readiness(client, case["id"])["contradictions_documented"]["result"] == "PASS"
    # Reading never changes the AI output.
    assert _row(tenant_id, AIExecution, execution_id).structured_output == output


# ---------------------------------------------------------------------------------------------------- unknowns


def test_the_unknown_lifecycle_with_its_evidence_requests(org):
    tenant_id = org["tenant_id"]
    client, client_id = org["investigator"]
    case = _case(org)
    base = _base(case["id"])
    ai = _hypothesis(tenant_id, case["id"], "Sterilization cycle drift weakened the tubing")
    superseded = _unknown(tenant_id, case["id"], status="superseded")

    made = client.post(
        f"{base}/unknowns",
        json={
            "description": "Was lot KS-5521 sterilized in the validated cycle?",
            "category": "MISSING_TEST_RESULT",
            "evidence_needed": "The sterilization record of the lot",
            "hypothesis_id": ai["id"],
        },
    )
    assert made.status_code == 201, made.text
    unknown = made.json()
    assert unknown["origin"] == "HUMAN" and unknown["origin_label"] == "Person" and unknown["status"] == "open"
    assert unknown["hypothesis"]["business_id"] == ai["business_id"] and unknown["business_id"]
    assert unknown["created_by_name"] == "Investigator Intelligence" and unknown["requests"] == []
    wrong = client.post(
        f"{base}/unknowns", json={"description": "Another open question here", "hypothesis_id": str(uuid.uuid4())}
    )
    assert wrong.status_code == 404 and _code(wrong) == "HYPOTHESIS_NOT_FOUND"
    assert client.post(f"{base}/unknowns", json={"description": "short"}).status_code == 422
    assert _readiness(client, case["id"])["unknowns"]["result"] == "PENDING"

    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        request = SupplierEvidenceRequest(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            investigation_id=uuid.UUID(case["id"]),
            requested_by=client_id,
            title="Sterilization record of lot KS-5521",
            requested_items={"items": ["Sterilization record"]},
            status="OPEN",
            request_kind="INTERNAL",
            recipient_role="INVESTIGATOR",
            unknown_id=uuid.UUID(unknown["id"]),
            created_at=now,
            updated_at=now,
        )
        db.add(request)
        db.commit()
        request_business_id = request.business_id
    listed = _get(client, f"{base}/unknowns")
    mine = _item(listed["items"], unknown["id"])
    assert mine["requests"] == [
        {
            "id": mine["requests"][0]["id"],
            "business_id": request_business_id,
            "title": "Sterilization record of lot KS-5521",
            "status": "OPEN",
            "status_label": "Open",
        }
    ]
    assert superseded["id"] not in [item["id"] for item in listed["items"]]
    assert listed["counts"]["superseded"] == 1 and listed["counts"]["human"] == 1 and listed["counts"]["open"] == 1
    everything = _get(client, f"{base}/unknowns", include_superseded=True)
    assert _item(everything["items"], superseded["id"])["locked"] is True

    path = f"{base}/unknowns/{unknown['id']}/status"
    started = client.post(path, json={"status": "in_progress", "reason": REASON})
    assert started.status_code == 200, started.text
    assert started.json()["status_label"] == "In progress" and started.json()["resolution"] is None
    assert started.json()["status_changed_by_name"] == "Investigator Intelligence"
    resolved = client.post(path, json={"status": "resolved", "reason": REASON})
    assert resolved.status_code == 200 and resolved.json()["resolution"] == REASON
    same = client.post(path, json={"status": "resolved", "reason": REASON})
    assert same.status_code == 409 and _code(same) == "UNKNOWN_STATUS_UNCHANGED"
    answered = client.post(path, json={"status": "superseded", "reason": REASON})
    assert answered.status_code == 409 and _code(answered) == "UNKNOWN_TRANSITION_NOT_ALLOWED"
    reopened = client.post(path, json={"status": "open", "reason": REASON})
    assert reopened.status_code == 200 and reopened.json()["resolution"] is None
    assert client.post(path, json={"status": "accepted_limitation"}).status_code == 422
    assert client.post(path, json={"status": "closed", "reason": REASON}).status_code == 422
    accepted = client.post(path, json={"status": "accepted_limitation", "reason": OTHER_REASON})
    assert accepted.status_code == 200 and accepted.json()["resolution"] == OTHER_REASON
    assert accepted.json()["status_label"] == "Accepted as a limitation"
    locked = client.post(f"{base}/unknowns/{superseded['id']}/status", json={"status": "open", "reason": REASON})
    assert locked.status_code == 409 and _code(locked) == "UNKNOWN_SUPERSEDED"
    # A person sets an open unknown aside as no longer relevant; it never changes again.
    aside = client.post(f"{base}/unknowns", json={"description": "Was the pump serviced before the alarm?"}).json()
    set_aside = client.post(f"{base}/unknowns/{aside['id']}/status", json={"status": "superseded", "reason": REASON})
    assert set_aside.status_code == 200, set_aside.text
    assert set_aside.json()["status_label"] == "No longer relevant" and set_aside.json()["resolution"] == REASON
    assert set_aside.json()["locked"] is True
    back = client.post(f"{base}/unknowns/{aside['id']}/status", json={"status": "open", "reason": REASON})
    assert back.status_code == 409 and _code(back) == "UNKNOWN_SUPERSEDED"
    missing = client.post(f"{base}/unknowns/{uuid.uuid4()}/status", json={"status": "open", "reason": REASON})
    assert missing.status_code == 404 and _code(missing) == "UNKNOWN_NOT_FOUND"
    # Every unknown is resolved, accepted as a limitation or superseded: nothing is left to answer.
    assert _readiness(client, case["id"])["unknowns"]["result"] == "PASS"

    events = [
        (item["event_type"], item["from_value"], item["to_value"])
        for item in _get(client, f"{base}/history")["items"]
        if item["object_type"] == "UNKNOWN" and item["object_business_id"] == unknown["business_id"]
    ]
    assert events == [
        ("STATUS_CHANGED", "open", "accepted_limitation"),
        ("STATUS_CHANGED", "resolved", "open"),
        ("STATUS_CHANGED", "in_progress", "resolved"),
        ("STATUS_CHANGED", "open", "in_progress"),
        ("CREATED", None, "open"),
    ]


# ---------------------------------------------------------------------------------------------- failure chains


def _ai_chain_output(case_id, evidence_identifier: str) -> dict:
    from failure_chain.schemas import FailureChain, FailureChainLink, FailureChainSet
    from investigator.schemas import SourceReference

    case_uuid = uuid.UUID(case_id)
    chain = FailureChain(
        investigation_id=case_uuid,
        chain_statement="Supplier change -> thin tubing wall -> occlusion alarms",
        start_state="Supplier change",
        end_state="Occlusion alarms",
        overall_status="BROKEN_CHAIN",
        links=[
            FailureChainLink(
                sequence=1,
                from_entity_or_state="Supplier change",
                relationship="is associated with",
                to_entity_or_state="Thin tubing wall",
                epistemic_status="OBSERVED_SOURCE_SUPPORTED",
                evidence_references=[
                    SourceReference(reference_type="EVIDENCE", evidence_identifier=evidence_identifier)
                ],
            ),
            FailureChainLink(
                sequence=2,
                from_entity_or_state="Thin tubing wall",
                relationship="may contribute to",
                to_entity_or_state="Pressure build-up",
                epistemic_status="DETERMINISTICALLY_DERIVED",
            ),
            FailureChainLink(
                sequence=3,
                from_entity_or_state="Pressure build-up",
                relationship="may contribute to",
                to_entity_or_state="Occlusion alarms",
                epistemic_status="UNKNOWN_GAP",
            ),
        ],
    )
    return FailureChainSet(
        investigation_id=case_uuid,
        source_hypothesis_set_id=uuid.uuid4(),
        context_snapshot_id="test:current:None",
        context_snapshot_version="1",
        chains=[chain],
    ).model_dump(mode="json")


def test_failure_chains_built_by_people_and_adopted_from_the_ai(org):
    from failure_chain.engine import MODEL, ORCHESTRATION_VERSION, PROVIDER

    tenant_id = org["tenant_id"]
    client, _ = org["investigator"]
    case = _case(org)
    base = _base(case["id"])
    direct = _evidence(tenant_id, case_id=case["id"])
    elsewhere = _evidence(tenant_id, title="Unrelated report")
    body = {
        "name": "Supplier change to alarms",
        "nodes": ["Tubing supplier changed", "Wall thickness varies", "Occlusion alarms rise"],
        "links": [
            {"from_index": 0, "to_index": 1, "state": "SUPPORTED", "evidence_id": direct["id"], "rationale": REASON},
            {"from_index": 1, "to_index": 2, "state": "HYPOTHESIZED"},
        ],
    }
    made = client.post(f"{base}/failure-chains", json=body)
    assert made.status_code == 201, made.text
    chain = made.json()
    assert chain["origin"] == "HUMAN" and chain["status"] == "draft" and chain["business_id"]
    assert chain["created_by_name"] == "Investigator Intelligence" and chain["source_ai_execution_id"] is None
    assert [node["sequence"] for node in chain["nodes"]] == [1, 2, 3]
    first, second = chain["links"]
    assert (first["from_label"], first["to_label"], first["state"]) == (
        "Tubing supplier changed",
        "Wall thickness varies",
        "SUPPORTED",
    )
    assert first["state_label"] == "Supported by evidence" and first["evidence"]["business_id"] == direct["business_id"]
    assert second["state"] == "HYPOTHESIZED" and second["evidence"] is None
    confirmed = {**body, "links": [{"from_index": 0, "to_index": 1, "state": "CONFIRMED"}]}
    assert client.post(f"{base}/failure-chains", json=confirmed).status_code == 422
    outside = {
        **body,
        "links": [{"from_index": 0, "to_index": 1, "state": "SUPPORTED", "evidence_id": elsewhere["id"]}],
    }
    refused = client.post(f"{base}/failure-chains", json=outside)
    assert refused.status_code == 404 and _code(refused) == "EVIDENCE_NOT_IN_CASE"
    unsupported = {**body, "links": [{"from_index": 0, "to_index": 1, "state": "SUPPORTED"}]}
    assert client.post(f"{base}/failure-chains", json=unsupported).status_code == 422

    link_path = f"{base}/failure-chains/{chain['id']}/links/{second['id']}/state"
    bare = client.post(link_path, json={"state": "SUPPORTED", "reason": REASON})
    assert bare.status_code == 422 and _code(bare) == "EVIDENCE_REQUIRED"
    changed = client.post(
        link_path, json={"state": "partially_supported", "reason": REASON, "evidence_id": direct["id"]}
    )
    assert changed.status_code == 200, changed.text
    moved = _item(changed.json()["links"], second["id"])
    assert moved["state"] == "PARTIALLY_SUPPORTED" and moved["state_reason"] == REASON
    assert moved["updated_by_name"] == "Investigator Intelligence" and moved["evidence"]["id"] == direct["id"]
    same = client.post(link_path, json={"state": "PARTIALLY_SUPPORTED", "reason": REASON})
    assert same.status_code == 409 and _code(same) == "LINK_STATE_UNCHANGED"
    assert client.post(link_path, json={"state": "CONFIRMED", "reason": REASON}).status_code == 422
    missing = client.post(
        f"{base}/failure-chains/{chain['id']}/links/{uuid.uuid4()}/state", json={"state": "UNKNOWN", "reason": REASON}
    )
    assert missing.status_code == 404 and _code(missing) == "FAILURE_CHAIN_LINK_NOT_FOUND"

    output = _ai_chain_output(case["id"], direct["identifier"])
    execution_id = _ai_execution(
        tenant_id, case["id"], provider=PROVIDER, model=MODEL, version=ORCHESTRATION_VERSION, output=output
    )
    listed = _get(client, f"{base}/failure-chains")
    assert listed["ai_latest"]["ai_execution_id"] == execution_id
    (ai_chain,) = listed["ai_latest"]["chains"]
    assert [link["epistemic_status"] for link in ai_chain["links"]] == [
        "OBSERVED_SOURCE_SUPPORTED",
        "DETERMINISTICALLY_DERIVED",
        "UNKNOWN_GAP",
    ]
    assert [link["state"] for link in ai_chain["links"]] == ["SUPPORTED", "PARTIALLY_SUPPORTED", "UNKNOWN"]
    assert ai_chain["origin_label"] == "AI interpretation" and ai_chain["adopted_chain"] is None

    adopt = {"ai_execution_id": execution_id, "ai_chain_id": ai_chain["chain_id"]}
    adopted = client.post(f"{base}/failure-chains/adopt", json=adopt)
    assert adopted.status_code == 201, adopted.text
    copy = adopted.json()
    assert copy["origin"] == "AI_ADOPTED" and copy["source_ai_execution_id"] == execution_id
    # The second AI link claims partial support but names no evidence of this case: it comes in as hypothesized.
    assert [link["state"] for link in copy["links"]] == ["SUPPORTED", "HYPOTHESIZED", "UNKNOWN"]
    assert "adopted as hypothesized" in copy["links"][1]["rationale"]
    assert "OBSERVED_SOURCE_SUPPORTED" in copy["links"][0]["rationale"]
    assert copy["links"][0]["evidence"]["business_id"] == direct["business_id"]
    assert [node["label"] for node in copy["nodes"]] == [
        "Supplier change",
        "Thin tubing wall",
        "Pressure build-up",
        "Occlusion alarms",
    ]
    twice = client.post(f"{base}/failure-chains/adopt", json=adopt)
    assert twice.status_code == 409 and _code(twice) == "CHAIN_ALREADY_ADOPTED"
    unknown = client.post(f"{base}/failure-chains/adopt", json={**adopt, "ai_chain_id": str(uuid.uuid4())})
    assert unknown.status_code == 404 and _code(unknown) == "AI_CHAIN_NOT_FOUND"

    after = _get(client, f"{base}/failure-chains")
    assert {item["id"] for item in after["stored"]} == {chain["id"], copy["id"]}
    assert after["ai_latest"]["chains"][0]["adopted_chain"]["id"] == copy["id"]
    assert "CONFIRMED" not in {link["state"] for item in after["stored"] for link in item["links"]}
    # The AI output is only ever read.
    assert _row(tenant_id, AIExecution, execution_id).structured_output == output
    events = [item for item in _get(client, f"{base}/history")["items"] if item["object_type"] == "FAILURE_CHAIN"]
    assert [item["event_type"] for item in events] == ["ADOPTED", "CREATED"]
    assert events[0]["details"]["ai_chain_id"] == ai_chain["chain_id"]


# ------------------------------------------------------------------------------------------------ observations


def test_observations_say_what_kind_of_statement_they_are(org):
    tenant_id = org["tenant_id"]
    client, _ = org["investigator"]
    case = _case(org)
    base = _base(case["id"])
    direct = _evidence(tenant_id, case_id=case["id"])
    linked = _evidence(tenant_id, title="Supplier certificate")
    elsewhere = _evidence(tenant_id, title="Unrelated report")
    link = client.post(f"/api/v1/investigations/{case['id']}/evidence-links", json={"evidence_ids": [linked["id"]]})
    assert link.status_code == 200, link.text
    assert _readiness(client, case["id"])["analysis_run"]["result"] == "PENDING"

    fact = client.post(
        f"{base}/observations",
        json={
            "evidence_id": direct["id"],
            "statement": "Alarm at 4 psi",
            "epistemic_type": "fact",
            "rationale": REASON,
        },
    )
    assert fact.status_code == 201, fact.text
    recorded = fact.json()
    assert recorded["epistemic_type"] == "FACT" and recorded["epistemic_label"] == "Fact"
    assert recorded["origin"] == "HUMAN" and recorded["origin_label"] == "Person"
    assert recorded["created_by_name"] == "Investigator Intelligence" and recorded["rationale"] == REASON
    assert recorded["evidence"]["business_id"] == direct["business_id"]
    assertion = client.post(
        f"{base}/observations",
        json={
            "evidence_id": linked["id"],
            "statement": "Supplier states the wall is 0.8 mm",
            "epistemic_type": "SOURCE_ASSERTION",
        },
    )
    assert assertion.status_code == 201, assertion.text
    ai_kind = client.post(
        f"{base}/observations",
        json={
            "evidence_id": direct["id"],
            "statement": "Probably a supplier issue",
            "epistemic_type": "AI_INTERPRETATION",
        },
    )
    assert ai_kind.status_code == 422
    outside = client.post(
        f"{base}/observations",
        json={"evidence_id": elsewhere["id"], "statement": "Alarm at 4 psi", "epistemic_type": "FACT"},
    )
    assert outside.status_code == 404 and _code(outside) == "EVIDENCE_NOT_IN_CASE"

    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        db.add(
            EvidenceObservation(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                evidence_id=uuid.UUID(direct["id"]),
                statement="The alarm pattern suggests partial occlusion",
                observation_type="AI_EXTRACTED_OBSERVATION",
                extraction_method="GENAI",
                quality_status="VALIDATED",
            )
        )
        db.commit()
    body = _get(client, f"{base}/observations")
    counts = body["counts"]
    assert counts["total"] == 3 and counts["human"] == 2
    assert (counts["FACT"], counts["SOURCE_ASSERTION"], counts["AI_INTERPRETATION"]) == (1, 1, 1)
    (machine,) = [item for item in body["items"] if item["origin"] != "HUMAN"]
    assert machine["origin"] == "AI" and machine["epistemic_label"] == "AI interpretation"
    assert machine["created_by_name"] is None
    # People's own observations count as analysis: AI is never required.
    assert _readiness(client, case["id"])["analysis_run"]["result"] == "PASS"
    assert _audit_actions(tenant_id, recorded["id"]) == ["INTELLIGENCE_CREATED"]


# ------------------------------------------------------------------------------- permissions and closed cases


def _writes(base: str, ids: dict) -> list[tuple[str, dict]]:
    return [
        (f"{base}/hypotheses", {"statement": "A hypothesis someone tries to add"}),
        (f"{base}/hypotheses/{ids['hypothesis']}/status", {"human_status": "RETIRED", "reason": REASON}),
        (
            f"{base}/hypotheses/{ids['hypothesis']}/evidence",
            {"evidence_id": ids["evidence"], "relation": "SUPPORTING", "rationale": REASON},
        ),
        (f"{base}/hypotheses/{ids['hypothesis']}/evidence/{uuid.uuid4()}/retract", {"reason": REASON}),
        (f"{base}/unknowns", {"description": "An unknown someone tries to add"}),
        (f"{base}/unknowns/{ids['unknown']}/status", {"status": "resolved", "reason": REASON}),
        (
            f"{base}/failure-chains",
            {
                "name": "Chain",
                "nodes": ["One step", "Two steps"],
                "links": [{"from_index": 0, "to_index": 1, "state": "UNKNOWN"}],
            },
        ),
        (f"{base}/failure-chains/adopt", {"ai_execution_id": str(uuid.uuid4()), "ai_chain_id": str(uuid.uuid4())}),
        (f"{base}/failure-chains/{uuid.uuid4()}/links/{uuid.uuid4()}/state", {"state": "UNKNOWN", "reason": REASON}),
        (
            f"{base}/observations",
            {"evidence_id": ids["evidence"], "statement": "Alarm at 4 psi", "epistemic_type": "FACT"},
        ),
    ]


def test_permissions_other_organizations_and_closed_cases(org):
    tenant_id = org["tenant_id"]
    client, _ = org["investigator"]
    viewer, _ = org["viewer"]
    outsider, _ = role_client("LEADER")  # the golden organization, with every permission
    case = _case(org)
    base = _base(case["id"])
    ids = {
        "hypothesis": _hypothesis(tenant_id, case["id"], "Tubing supplier change raised alarms")["id"],
        "unknown": _unknown(tenant_id, case["id"])["id"],
        "evidence": _evidence(tenant_id, case_id=case["id"])["id"],
    }
    reads = ["hypotheses", "contradictions", "unknowns", "failure-chains", "observations", "history"]
    for name in reads:
        assert viewer.get(f"{base}/{name}").status_code == 200, name  # reading needs only a session
    assert _get(viewer, f"{base}/hypotheses")["items"][0]["actions"] == {
        "can_set_status": False,
        "can_link_evidence": False,
    }
    for path, body in _writes(base, ids):
        denied = viewer.post(path, json=body)
        assert denied.status_code == 403 and _code(denied) == "PERMISSION_DENIED", path
    for name in reads:
        hidden = outsider.get(f"{base}/{name}")
        assert hidden.status_code == 404 and _code(hidden) == "INVESTIGATION_NOT_FOUND", name
    for path, body in _writes(base, ids):
        hidden = outsider.post(path, json=body)
        assert hidden.status_code == 404 and _code(hidden) == "INVESTIGATION_NOT_FOUND", path
    assert client.get(f"{_base(uuid.uuid4())}/hypotheses").status_code == 404

    _close(tenant_id, case["id"])
    for path, body in _writes(base, ids):
        closed = client.post(path, json=body)
        assert closed.status_code == 409 and _code(closed) == "CASE_CLOSED", path
    listed = _get(client, f"{base}/hypotheses")
    assert listed["actions"] == {"can_add": False}
    assert listed["items"][0]["actions"] == {"can_set_status": False, "can_link_evidence": False}
    assert _get(client, f"{base}/history")["total"] == 0


# ------------------------------------------------------------------------------------------------- AI re-runs


def test_an_ai_rerun_keeps_what_people_judged_and_added(org):
    from hypothesis_engine.service import CompetingHypothesisService

    tenant_id = org["tenant_id"]
    client, _ = org["investigator"]
    case = _case(org)
    base = _base(case["id"])
    stale = _hypothesis(tenant_id, case["id"], "An earlier AI hypothesis nobody judged")
    judged = _hypothesis(tenant_id, case["id"], "An earlier AI hypothesis a person judged")
    response = client.post(
        f"{base}/hypotheses/{judged['id']}/status", json={"human_status": "PARTIALLY_SUPPORTED", "reason": REASON}
    )
    assert response.status_code == 200, response.text
    human = client.post(f"{base}/hypotheses", json={"statement": "A person's own hypothesis about release B"}).json()
    ai_unknown = _unknown(tenant_id, case["id"], hypothesis_id=stale["id"])
    working = _unknown(tenant_id, case["id"], hypothesis_id=stale["id"], status="in_progress")
    person_unknown = client.post(
        f"{base}/unknowns", json={"description": "A person's open question on it", "hypothesis_id": stale["id"]}
    ).json()

    now = datetime.now(timezone.utc)
    item = SimpleNamespace(
        hypothesis_id=uuid.uuid4(),
        statement="A new AI hypothesis about release B",
        status="MIXED_EVIDENCE",
        updated_at=now,
        unknowns=["Was the alarm log exported?"],
        evidence_gaps=[],
        supporting_evidence=[],
        contradicting_evidence=[],
    )
    hypothesis_set = SimpleNamespace(created_at=now, provenance={"author": "LANGUAGE_MODEL"}, hypotheses=[item])
    request = SimpleNamespace(tenant_id=tenant_id, investigation_id=uuid.UUID(case["id"]))
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        CompetingHypothesisService()._materialize_domain_intelligence(db, request, hypothesis_set)

    assert _row(tenant_id, Hypothesis, stale["id"]).status == "superseded"
    kept = _row(tenant_id, Hypothesis, judged["id"])
    assert kept.status == "mixed_evidence" and kept.human_status == "PARTIALLY_SUPPORTED"
    assert _row(tenant_id, Hypothesis, human["id"]).status == "proposed"
    assert _row(tenant_id, Unknown, ai_unknown["id"]).status == "superseded"
    assert _row(tenant_id, Unknown, working["id"]).status == "in_progress"
    assert _row(tenant_id, Unknown, person_unknown["id"]).status == "open"
    new = _row(tenant_id, Hypothesis, item.hypothesis_id)
    assert new.origin == "ai" and new.status == "mixed_evidence"
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        origins = {row.origin for row in db.query(Unknown).filter(Unknown.hypothesis_id == item.hypothesis_id)}
    assert origins == {"ai"}

    shown = {entry["id"] for entry in _get(client, f"{base}/hypotheses")["items"]}
    assert shown == {judged["id"], human["id"], str(item.hypothesis_id)}
    everything = _get(client, f"{base}/hypotheses", include_superseded=True)
    old = _item(everything["items"], stale["id"])
    assert old["superseded"] is True and old["actions"]["can_set_status"] is False
    refused = client.post(f"{base}/hypotheses/{stale['id']}/status", json={"human_status": "RETIRED", "reason": REASON})
    assert refused.status_code == 409 and _code(refused) == "HYPOTHESIS_SUPERSEDED"
    assert _readiness(client, case["id"])["hypotheses_present"]["rationale"] == "3 hypotheses recorded"
