"""Risk and regulatory reviews end to end: the review policy of a case, requesting a review (its queue task, one open
per type), starting, completing (outcome per type, assessed risks of the product), recusing and cancelling with their
tasks and permissions (no segregation of duties), readiness blocked by policy until a review completes, an outcome
asking for more evidence (blocked again and a follow-up for the case owner), a scope change that restarts reviews, the
reviewer's context, lists and dashboard, the next steps, and other organizations.

Everything runs in fresh organizations of their own (on the shared plane), deleted at the end.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from auth.durable import persist_session
from auth.service import _hash
from backend.app.db.models.foundation import (
    AuditEvent,
    AuthUser,
    Complaint,
    Evidence,
    FailureChain,
    FailureMode,
    Hypothesis,
    HypothesisEvidence,
    Investigation,
    Product,
    Risk,
    TenantMembership,
    Unknown,
)
from backend.app.db.models.reviews import CaseReview
from backend.app.db.models.stage3 import SupplierEvidenceRequest
from backend.app.db.models.workflow import UserAdditionalRole, WorkflowTask
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from backend.app.main import app

PASSWORD = "Case reviews 2026!"
QUESTION = "Why do occlusion alarms rise after release B?"
REASON = "The complaints report harm to patients"
RATIONALE = "The complaints do not change the risk estimate of the occlusion hazard"
BASE = "/api/v1/case-reviews"


def _organization(prefix: str):
    from backend.app.customer_lifecycle import build_customer_tenant

    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        customer, tenant = build_customer_tenant(
            db=db, tenant_key=f"{prefix}_{uuid.uuid4().hex[:8].upper()}", name="Case reviews", status="ACTIVE", now=now
        )
        db.add(customer)
        db.add(tenant)
        db.commit()  # registers the organization on the shared plane (migration md20)
        return tenant.id


def _purge(tenant_id) -> None:
    from backend.app.trial.retention import purge_trial

    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        db.query(CaseReview).filter(CaseReview.tenant_id == tenant_id).delete(synchronize_session=False)
        db.commit()
    with SessionLocal() as db:
        purge_trial(db, tenant_id, "test:case-reviews-cleanup")


@pytest.fixture(scope="module")
def org():
    """A fresh organization with an investigator (the case owner), a colleague investigator, a risk reviewer, a
    regulatory reviewer, a quality reviewer (assigns work), an investigator who is also a risk reviewer, and a viewer;
    and another organization with a case and a review of its own."""
    tenant_id = _organization("REVIEWS")
    other_id = _organization("REVIEWS_OTHER")
    people = {
        name: _client(tenant_id, role, name.title())
        for name, role in (
            ("investigator", "INVESTIGATOR"),
            ("colleague", "INVESTIGATOR"),
            ("risk", "RISK_REVIEWER"),
            ("regulatory", "REGULATORY_REVIEWER"),
            ("quality", "REVIEWER"),
            ("both", "INVESTIGATOR"),
            ("viewer", "VIEWER"),
        )
    }
    _grant(tenant_id, people["both"][1], "RISK_REVIEWER")
    try:
        seed = _seed(tenant_id)
        other_client, _ = _client(other_id, "INVESTIGATOR", "Other")
        other_seed = _seed(other_id)
        other_case = _open(other_client, other_seed, [other_seed["injury"]])
        other_review = other_client.post(
            f"/api/v1/investigations/{other_case['id']}/reviews", json={"review_type": "RISK"}
        )
        assert other_review.status_code == 201, other_review.text
        yield {
            "tenant_id": tenant_id,
            "seed": seed,
            "other_case": other_case["id"],
            "other_review": other_review.json()["id"],
            **people,
        }
    finally:
        _purge(tenant_id)
        _purge(other_id)


def _client(tenant_id, role: str, name: str) -> tuple[TestClient, str]:
    with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        user = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            username=f"reviews-{role.lower()}-{uuid.uuid4().hex[:8]}@example.invalid",
            display_name=f"{name} Reviews",
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


def _grant(tenant_id, user_id: str, role: str) -> None:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        db.add(
            UserAdditionalRole(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                user_id=uuid.UUID(user_id),
                role_code=role,
                status="ACTIVE",
                reason="Small team: investigators also review risk",
                granted_by="test",
            )
        )
        db.commit()


def _seed(tenant_id) -> dict:
    """A product with a complaint reporting a serious injury (DE), one reporting a malfunction (US) and one without
    harm; a risk of the product and one of another product; a failure mode."""
    now = datetime.now(timezone.utc)
    tag = uuid.uuid4().hex[:8].upper()
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)

        def product(suffix: str) -> Product:
            row = Product(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                product_identifier=f"RV-P-{tag}-{suffix}",
                name=f"Review Pump {tag} {suffix}",
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            db.flush()
            return row

        def complaint(product_id, *, country, received_days: int, **flags) -> str:
            row = Complaint(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                complaint_identifier=f"RV-C-{uuid.uuid4().hex[:10].upper()}",
                product_id=product_id,
                event_timestamp=now - timedelta(days=received_days + 2),
                complaint_timestamp=now - timedelta(days=received_days),
                description="Occlusion alarm during infusion",
                status="open",
                country=country,
                created_at=now,
                updated_at=now,
                **flags,
            )
            db.add(row)
            db.flush()
            return str(row.id)

        def risk(product_id, description: str) -> str:
            row = Risk(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                risk_identifier=f"RV-R-{uuid.uuid4().hex[:10].upper()}",
                product_id=product_id,
                description=description,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            db.flush()
            return str(row.id)

        main, other = product("M"), product("O")
        seed = {
            "product_id": str(main.id),
            "injury": complaint(main.id, country="DE", received_days=20, serious_injury=True),
            "malfunction": complaint(main.id, country="US", received_days=10, malfunction=True),
            "plain": complaint(main.id, country=None, received_days=5),
            "risk_id": risk(main.id, "Delayed therapy from a false occlusion alarm"),
            "foreign_risk_id": risk(other.id, "Another product's risk"),
        }
        mode = FailureMode(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            failure_mode_identifier=f"RV-FM-{tag}",
            name="Pressure sensor drift",
            created_at=now,
            updated_at=now,
        )
        db.add(mode)
        db.commit()
        seed["failure_mode_id"] = str(mode.id)
        return seed


def _open(client, seed: dict, complaints: list[str]) -> dict:
    made = client.post(
        "/api/v1/investigations",
        json={
            "product_id": seed["product_id"],
            "investigation_question": QUESTION,
            "complaint_ids": complaints,
            "assign_to_me": True,
        },
    )
    assert made.status_code == 201, made.text
    return made.json()


def _code(response) -> str | None:
    detail = response.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


def _readiness(client, case_id) -> tuple[dict, dict]:
    body = client.get(f"/api/v1/investigations/{case_id}/readiness").json()
    return (
        {check["key"]: check for check in body["checks"]},
        {step["key"]: step for step in body["steps"]},
    )


def _tasks(tenant_id, review_id, task_type: str | None = None) -> list[WorkflowTask]:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        query = db.query(WorkflowTask).filter(
            WorkflowTask.source_entity_type == "CaseReview", WorkflowTask.source_entity_id == uuid.UUID(review_id)
        )
        if task_type:
            query = query.filter(WorkflowTask.task_type == task_type)
        rows = query.order_by(WorkflowTask.created_at).all()
        for row in rows:
            db.expunge(row)
        return rows


def _audits(tenant_id, entity_id, action: str) -> list[AuditEvent]:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        rows = (
            db.query(AuditEvent)
            .filter(AuditEvent.entity_id == uuid.UUID(str(entity_id)), AuditEvent.action == action)
            .order_by(AuditEvent.created_at)
            .all()
        )
        for row in rows:
            db.expunge(row)
        return rows


def _set_case(tenant_id, case_id, **values) -> None:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        db.query(Investigation).filter(Investigation.id == uuid.UUID(case_id)).update(values)
        db.commit()


def _request(client, case_id, review_type: str, **extra):
    return client.post(f"/api/v1/investigations/{case_id}/reviews", json={"review_type": review_type, **extra})


def _complete(client, review_id, outcome: str, **extra):
    return client.post(f"{BASE}/{review_id}/complete", json={"outcome": outcome, "rationale": RATIONALE, **extra})


# ------------------------------------------------------------------------------- request, start and complete


def test_a_policy_required_review_blocks_readiness_until_it_is_completed(org):
    tenant_id, seed = org["tenant_id"], org["seed"]
    investigator, _ = org["investigator"]
    risk, risk_id = org["risk"]
    regulatory, _ = org["regulatory"]
    viewer, _ = org["viewer"]
    case = _open(investigator, seed, [seed["injury"], seed["malfunction"]])

    policy = viewer.get(f"/api/v1/investigations/{case['id']}/reviews/policy")
    assert policy.status_code == 200, policy.text
    assert policy.json() == {
        "risk": {"required": True, "reasons": ["1 complaint in scope reports a serious injury"]},
        "regulatory": {
            "required": True,
            "reasons": [
                "1 complaint in scope reports a serious injury",
                "1 complaint in scope reports a malfunction",
            ],
        },
    }
    checks, steps = _readiness(viewer, case["id"])
    assert checks["risk_review"]["result"] == "BLOCKED"
    assert checks["risk_review"]["rationale"] == (
        "Request a risk review: required because 1 complaint in scope reports a serious injury"
    )
    assert checks["regulatory_review"]["result"] == "BLOCKED" and steps["risk_regulatory"]["status"] == "BLOCKED"

    refused = _request(viewer, case["id"], "RISK")
    assert refused.status_code == 403 and _code(refused) == "PERMISSION_DENIED"
    made = _request(investigator, case["id"], "RISK", reason="Serious injury reported in Germany")
    assert made.status_code == 201, made.text
    review = made.json()
    assert review["business_id"].startswith("REV") and review["status"] == "REQUESTED"
    assert review["review_type_label"] == "Risk review" and review["status_label"] == "Requested"
    assert review["required_by_policy"] is True
    assert review["policy_reasons"] == ["1 complaint in scope reports a serious injury"]
    assert review["scope_version"] == 1 and review["reviewer"] is None and review["outcome"] is None
    assert review["request_reason"] == "Serious injury reported in Germany"
    assert review["requested_by_name"] == "Investigator Reviews"
    assert review["investigation"]["business_id"] == case["business_id"]
    assert review["investigation"]["product"]["id"] == seed["product_id"]
    assert review["actions"] == {"can_start": False, "can_complete": False, "can_recuse": False, "can_cancel": True}
    (task,) = _tasks(tenant_id, review["id"])
    assert task.task_type == "RISK_REVIEW" and task.status == "NEW" and task.assigned_user_id is None
    assert task.assigned_role == "RISK_REVIEWER" and task.title == f"Risk review of {case['business_id']}"
    assert str(task.investigation_id) == case["id"]

    again = _request(investigator, case["id"], "risk")
    assert again.status_code == 409 and _code(again) == "REVIEW_ALREADY_OPEN"
    checks, steps = _readiness(investigator, case["id"])
    assert checks["risk_review"]["result"] == "PENDING" and steps["risk_regulatory"]["status"] == "BLOCKED"

    queue = risk.get(BASE, params={"box": "queue", "type": "RISK"}).json()
    assert review["id"] in [item["id"] for item in queue["items"]]
    assert next(item for item in queue["items"] if item["id"] == review["id"])["actions"]["can_start"] is True
    assert review["id"] not in [item["id"] for item in regulatory.get(BASE, params={"box": "queue"}).json()["items"]]

    wrong_type = regulatory.post(f"{BASE}/{review['id']}/start")
    assert wrong_type.status_code == 403 and _code(wrong_type) == "PERMISSION_DENIED"
    started = risk.post(f"{BASE}/{review['id']}/start")
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["status"] == "IN_PROGRESS" and body["reviewer"] == {"id": risk_id, "name": "Risk Reviews"}
    assert body["reviewer_role_label"] == "Risk Reviewer"
    assert body["actions"] == {"can_start": False, "can_complete": True, "can_recuse": True, "can_cancel": False}
    (task,) = _tasks(tenant_id, review["id"])
    assert task.status == "IN_PROGRESS" and str(task.assigned_user_id) == risk_id
    twice = risk.post(f"{BASE}/{review['id']}/start")
    assert twice.status_code == 409 and _code(twice) == "REVIEW_STATE_CONFLICT"

    not_yours = _complete(investigator, review["id"], "NO_CHANGE_REQUIRED")
    assert not_yours.status_code == 403 and _code(not_yours) == "REVIEW_NOT_YOURS"
    wrong_outcome = _complete(risk, review["id"], "REPORTING_REQUIRED")
    assert wrong_outcome.status_code == 422 and _code(wrong_outcome) == "OUTCOME_NOT_FOR_REVIEW_TYPE"
    foreign_risk = _complete(risk, review["id"], "NO_CHANGE_REQUIRED", assessed={"risk_ids": [seed["foreign_risk_id"]]})
    assert foreign_risk.status_code == 422 and _code(foreign_risk) == "RISK_NOT_FOR_PRODUCT"
    short = risk.post(f"{BASE}/{review['id']}/complete", json={"outcome": "NO_CHANGE_REQUIRED", "rationale": "ok"})
    assert short.status_code == 422

    done = _complete(
        risk,
        review["id"],
        "NO_CHANGE_REQUIRED",
        assessed={"risk_ids": [seed["risk_id"]], "markets": ["EU", "eu"], "notes": "Risk file RF-12 checked"},
    )
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["status"] == "COMPLETED" and body["outcome"] == "NO_CHANGE_REQUIRED"
    assert body["outcome_label"] == "No change to the risk file required" and body["rationale"] == RATIONALE
    assert body["completed_at"] and body["assessed"]["markets"] == ["EU"]
    assert body["assessed"]["notes"] == "Risk file RF-12 checked"
    assert [item["id"] for item in body["assessed"]["risks"]] == [seed["risk_id"]]
    assert body["assessed"]["risks"][0]["business_id"] and body["assessed"]["risks"][0]["title"]
    assert not any(body["actions"].values())
    (task,) = _tasks(tenant_id, review["id"])
    assert task.status == "COMPLETED" and task.completion_outcome == "NO_CHANGE_REQUIRED"
    assert _tasks(tenant_id, review["id"], "FOLLOW_UP") == []
    finished = _complete(risk, review["id"], "NO_CHANGE_REQUIRED")
    assert finished.status_code == 409 and _code(finished) == "REVIEW_STATE_CONFLICT"

    checks, steps = _readiness(investigator, case["id"])
    assert checks["risk_review"]["result"] == "PASS"
    assert checks["risk_review"]["rationale"] == (
        f"Risk review {review['business_id']} completed: No change to the risk file required"
    )
    assert checks["regulatory_review"]["result"] == "BLOCKED" and steps["risk_regulatory"]["status"] == "BLOCKED"
    for action in ("CASE_REVIEW_REQUESTED", "CASE_REVIEW_STARTED", "CASE_REVIEW_COMPLETED"):
        (event,) = _audits(tenant_id, review["id"], action)
        assert event.entity_type == "CaseReview" and event.details["actor_role"]
    assert _audits(tenant_id, review["id"], "CASE_REVIEW_STARTED")[0].details["actor_role"] == "RISK_REVIEWER"

    listed = viewer.get(f"/api/v1/investigations/{case['id']}/reviews").json()
    assert [item["id"] for item in listed["items"]] == [review["id"]]
    assert listed["policy"]["regulatory"]["required"] is True


def test_an_outcome_asking_for_more_evidence_blocks_and_returns_the_case_to_its_owner(org):
    tenant_id, seed = org["tenant_id"], org["seed"]
    investigator, investigator_id = org["investigator"]
    regulatory, _ = org["regulatory"]
    case = _open(investigator, seed, [seed["malfunction"]])
    review = _request(investigator, case["id"], "REGULATORY").json()
    assert review["required_by_policy"] is True
    assert regulatory.post(f"{BASE}/{review['id']}/start").status_code == 200
    returned = _complete(regulatory, review["id"], "ADDITIONAL_EVIDENCE_REQUIRED")
    assert returned.status_code == 200, returned.text
    assert returned.json()["outcome_label"] == "Additional evidence required"

    (follow_up,) = _tasks(tenant_id, review["id"], "FOLLOW_UP")
    assert follow_up.is_return is True and str(follow_up.assigned_user_id) == investigator_id
    assert follow_up.status == "ASSIGNED" and str(follow_up.investigation_id) == case["id"]
    assert follow_up.title == f"Regulatory review of {case['business_id']} returned: Additional evidence required"
    assert RATIONALE in follow_up.details["description"]
    checks, steps = _readiness(investigator, case["id"])
    assert checks["regulatory_review"]["result"] == "BLOCKED"
    assert checks["regulatory_review"]["rationale"] == (
        f"Regulatory review {review['business_id']} concluded: Additional evidence required. "
        "A new regulatory review must be completed"
    )
    assert steps["risk_regulatory"]["status"] == "BLOCKED"

    second = _request(investigator, case["id"], "REGULATORY")
    assert second.status_code == 201, second.text
    assert _readiness(investigator, case["id"])[0]["regulatory_review"]["result"] == "PENDING"
    assert regulatory.post(f"{BASE}/{second.json()['id']}/start").status_code == 200
    assert _complete(regulatory, second.json()["id"], "REPORTABILITY_ASSESSMENT_COMPLETE").status_code == 200
    checks, steps = _readiness(investigator, case["id"])
    assert checks["regulatory_review"]["result"] == "PASS"
    # A medium case whose complaint reports a malfunction only: no risk review is required.
    assert checks["risk_review"]["result"] == "NOT_REQUIRED" and steps["risk_regulatory"]["status"] == "DONE"


def test_recusing_and_cancelling_a_review(org):
    tenant_id, seed = org["tenant_id"], org["seed"]
    investigator, _ = org["investigator"]
    colleague, _ = org["colleague"]
    risk, _ = org["risk"]
    quality, _ = org["quality"]
    viewer, _ = org["viewer"]
    case = _open(investigator, seed, [seed["plain"]])
    review = _request(investigator, case["id"], "RISK").json()
    assert review["required_by_policy"] is False and review["policy_reasons"] == []
    assert risk.post(f"{BASE}/{review['id']}/start").status_code == 200

    not_reviewer = investigator.post(f"{BASE}/{review['id']}/recuse", json={"reason": "Not my area of expertise"})
    assert not_reviewer.status_code == 403 and _code(not_reviewer) == "REVIEW_NOT_YOURS"
    assert risk.post(f"{BASE}/{review['id']}/recuse", json={"reason": "short"}).status_code == 422
    recused = risk.post(f"{BASE}/{review['id']}/recuse", json={"reason": "I worked on this product's design"})
    assert recused.status_code == 200, recused.text
    assert recused.json()["status"] == "REQUESTED" and recused.json()["reviewer"] is None
    (task,) = _tasks(tenant_id, review["id"])
    assert task.status == "NEW" and task.assigned_user_id is None and task.assigned_role == "RISK_REVIEWER"
    assert _audits(tenant_id, review["id"], "CASE_REVIEW_RECUSED")[0].reason == "I worked on this product's design"

    # Neither a viewer nor a colleague who did not ask for it may cancel; the requester may.
    for client in (viewer, colleague):
        refused = client.post(f"{BASE}/{review['id']}/cancel", json={"reason": "No longer needed for this case"})
        assert refused.status_code == 403 and _code(refused) == "PERMISSION_DENIED"
    cancelled = investigator.post(f"{BASE}/{review['id']}/cancel", json={"reason": "No longer needed for this case"})
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"
    (task,) = _tasks(tenant_id, review["id"])
    assert task.status == "CANCELLED" and task.completion_outcome == "REVIEW_CANCELLED"
    again = investigator.post(f"{BASE}/{review['id']}/cancel", json={"reason": "No longer needed for this case"})
    assert again.status_code == 409
    assert _audits(tenant_id, review["id"], "CASE_REVIEW_CANCELLED")
    # A cancelled review leaves the case as the policy says: not required here.
    assert _readiness(investigator, case["id"])[0]["risk_review"]["result"] == "NOT_REQUIRED"

    # Whoever assigns work may cancel a review someone else asked for, also one in progress.
    other = _request(investigator, case["id"], "RISK").json()
    assert risk.post(f"{BASE}/{other['id']}/start").status_code == 200
    assert quality.get(f"{BASE}/{other['id']}").json()["actions"]["can_cancel"] is True
    by_lead = quality.post(f"{BASE}/{other['id']}/cancel", json={"reason": "Duplicate of the brief's review"})
    assert by_lead.status_code == 200 and by_lead.json()["status"] == "CANCELLED"
    assert [task.status for task in _tasks(tenant_id, other["id"])] == ["CANCELLED"]


def test_reviews_have_no_segregation_of_duties(org):
    """In a small team the investigator who asked for a review may do it when they also hold the reviewer role."""
    seed = org["seed"]
    both, both_id = org["both"]
    case = _open(both, seed, [seed["injury"]])
    review = _request(both, case["id"], "RISK").json()
    assert review["actions"]["can_start"] is True
    started = both.post(f"{BASE}/{review['id']}/start")
    assert started.status_code == 200 and started.json()["reviewer"]["id"] == both_id
    assert started.json()["reviewer_role"] == "RISK_REVIEWER"
    assert _complete(both, review["id"], "RISK_FILE_REASSESSMENT_REQUIRED").status_code == 200
    assert _readiness(both, case["id"])[0]["risk_review"]["result"] == "PASS"


def test_a_review_task_taken_by_another_reviewer_cannot_be_started(org):
    tenant_id, seed = org["tenant_id"], org["seed"]
    investigator, _ = org["investigator"]
    risk, _ = org["risk"]
    both, _ = org["both"]
    case = _open(investigator, seed, [seed["plain"]])
    review = _request(investigator, case["id"], "RISK").json()
    (task,) = _tasks(tenant_id, review["id"])
    assert both.post(f"/api/v1/tasks/{task.id}/claim").status_code == 200
    taken = risk.post(f"{BASE}/{review['id']}/start")
    assert taken.status_code == 409 and _code(taken) == "REVIEW_TASK_TAKEN"
    assert risk.get(f"{BASE}/{review['id']}").json()["actions"]["can_start"] is False
    started = both.post(f"{BASE}/{review['id']}/start")
    assert started.status_code == 200, started.text
    (task,) = _tasks(tenant_id, review["id"])
    assert task.status == "IN_PROGRESS"


# ------------------------------------------------------------------------------------------------ scope change


def test_a_scope_change_that_restarts_reviews_supersedes_them(org):
    tenant_id, seed = org["tenant_id"], org["seed"]
    investigator, _ = org["investigator"]
    risk, _ = org["risk"]
    case = _open(investigator, seed, [seed["injury"]])
    completed = _request(investigator, case["id"], "RISK").json()
    assert risk.post(f"{BASE}/{completed['id']}/start").status_code == 200
    assert _complete(risk, completed["id"], "ADDITIONAL_EVIDENCE_REQUIRED").status_code == 200
    open_review = _request(investigator, case["id"], "REGULATORY").json()
    assert _readiness(investigator, case["id"])[0]["risk_review"]["result"] == "BLOCKED"

    path = f"/api/v1/investigations/{case['id']}/scope"
    kept = investigator.put(
        path,
        json={
            "question": QUESTION,
            "included_complaint_ids": [seed["injury"]],
            "change_reason": "Objectives clarified, nothing else changed",
        },
    )
    assert kept.status_code == 200, kept.text
    assert investigator.get(f"{BASE}/{open_review['id']}").json()["status"] == "REQUESTED"

    restarted = investigator.put(
        path,
        json={
            "question": QUESTION,
            "included_complaint_ids": [seed["injury"], seed["malfunction"]],
            "change_reason": "A malfunction complaint belongs to this case",
            "reviews_must_restart": True,
        },
    )
    assert restarted.status_code == 200, restarted.text
    version = restarted.json()["scope"]["version"]
    for review in (completed, open_review):
        body = investigator.get(f"{BASE}/{review['id']}").json()
        assert body["status"] == "SUPERSEDED" and body["superseded_reason"] == f"Scope changed in version {version}"
        assert not any(body["actions"].values())
        assert all(task.status in ("SUPERSEDED", "COMPLETED") for task in _tasks(tenant_id, review["id"]))
        (event,) = _audits(tenant_id, review["id"], "CASE_REVIEW_SUPERSEDED")
        assert event.details["scope_version"] == version
    # The returned review's follow-up and the open review's queue task were open: both are superseded.
    assert [task.status for task in _tasks(tenant_id, completed["id"], "FOLLOW_UP")] == ["SUPERSEDED"]
    assert [task.status for task in _tasks(tenant_id, open_review["id"])] == ["SUPERSEDED"]
    checks, _ = _readiness(investigator, case["id"])
    assert checks["risk_review"]["result"] == checks["regulatory_review"]["result"] == "BLOCKED"
    assert checks["risk_review"]["rationale"].startswith("Request a risk review")
    fresh = _request(investigator, case["id"], "REGULATORY")
    assert fresh.status_code == 201 and fresh.json()["scope_version"] == version


# -------------------------------------------------------------------------------------------------- context


def test_what_the_reviewer_sees(org):
    tenant_id, seed = org["tenant_id"], org["seed"]
    investigator, _ = org["investigator"]
    risk, _ = org["risk"]
    regulatory, _ = org["regulatory"]
    case = _open(investigator, seed, [seed["injury"], seed["malfunction"], seed["plain"]])
    scope = investigator.put(
        f"/api/v1/investigations/{case['id']}/scope",
        json={
            "question": QUESTION,
            "included_complaint_ids": [seed["injury"], seed["malfunction"], seed["plain"]],
            "failure_mode_ids": [seed["failure_mode_id"]],
            "markets": ["EU", "US"],
            "change_reason": "The sensor failure mode is in scope",
        },
    )
    assert scope.status_code == 200, scope.text
    now = datetime.now(timezone.utc)
    case_id = uuid.UUID(case["id"])
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        hypothesis = Hypothesis(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            investigation_id=case_id,
            statement="The pressure sensor drifts after release B",
            status="proposed",
            origin="human",
            human_status="PARTIALLY_SUPPORTED",
            status_reason="Two service reports match",
            created_at=now,
            updated_at=now,
        )
        evidence = [
            Evidence(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                evidence_identifier=f"RV-E-{uuid.uuid4().hex[:10].upper()}",
                investigation_id=case_id,
                evidence_type="SERVICE_REPORT",
                title=title,
                created_at=now,
                updated_at=now,
            )
            for title in ("Service report 1", "Service report 2")
        ]
        db.add_all([hypothesis, *evidence])
        db.flush()
        db.add_all(
            [
                HypothesisEvidence(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    hypothesis_id=hypothesis.id,
                    evidence_id=item.id,
                    relation_type=relation,
                    created_by_type="human",
                    created_at=now,
                )
                for item, relation in zip(evidence, ("support", "contradict"))
            ]
            + [
                Unknown(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    investigation_id=case_id,
                    description="Firmware of the returned devices",
                    status="open",
                    created_at=now,
                    updated_at=now,
                ),
                FailureChain(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    investigation_id=case_id,
                    name="Sensor drift to delayed therapy",
                    status="draft",
                    origin="human",
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        db.commit()

    risk_review = _request(investigator, case["id"], "RISK").json()
    detail = risk.get(f"{BASE}/{risk_review['id']}")
    assert detail.status_code == 200, detail.text
    context = detail.json()["context"]
    assert context["type"] == "RISK" and context["product"]["id"] == seed["product_id"]
    risk_ids = [item["id"] for item in context["risks"]]
    assert seed["risk_id"] in risk_ids and seed["foreign_risk_id"] not in risk_ids
    assert "hazard" in context["risks"][0] and "controls" in context["risks"][0] and context["risks"][0]["title"]
    # Hazards, harms and controls as the risk records hold them: none is captured or linked here, none is estimated.
    assert context["hazards"] == [] and context["harms"] == [] and context["controls"] == []
    (mode,) = [item for item in context["failure_modes"] if item["id"] == seed["failure_mode_id"]]
    assert mode["in_scope"] is True and mode["name"] == "Pressure sensor drift"
    (item,) = context["hypotheses"]
    assert item["human_status"] == "PARTIALLY_SUPPORTED" and item["human_status_label"] == "Partially supported"
    assert item["supporting"] == 1 and item["contradicting"] == 1
    assert item["human_judgement"] == {"status": "PARTIALLY_SUPPORTED", "label": "Partially supported"}
    assert item["evidence_counts"] == {"supporting": 1, "contradicting": 1}
    assert context["contradictions"] == context["contradictions_count"] == 1
    assert mode["title"] == "Pressure sensor drift"
    assert [unknown["description"] for unknown in context["open_unknowns"]] == ["Firmware of the returned devices"]
    assert [chain["name"] for chain in context["failure_chains"]] == ["Sensor drift to delayed therapy"]

    regulatory_review = _request(investigator, case["id"], "REGULATORY").json()
    context = regulatory.get(f"{BASE}/{regulatory_review['id']}").json()["context"]
    assert context["type"] == "REGULATORY"
    assert context["note"] == "Reportability and deadlines are determined by the reviewer"
    assert context["counts"] == {"complaints": 3, "serious_injury": 1, "death": 0, "malfunction": 1}
    markets = {item["market"]: item for item in context["markets"]}
    assert markets["DE"]["serious_injury"] == 1 and markets["US"]["malfunction"] == 1
    assert markets["Not recorded"]["complaints"] == 1
    assert context["counts_by_market"] == {"DE": 1, "US": 1, "Not recorded": 1}
    assert context["scope_markets"] == ["EU", "US"]
    injury = next(item for item in context["complaints"] if item["id"] == seed["injury"])
    assert injury["country"] == "DE" and injury["serious_injury"] is True and injury["received_at"]
    assert injury["event_at"] < injury["received_at"]
    # The earliest awareness is the injury complaint, received 20 days ago; no deadline is computed.
    assert context["earliest_awareness"]["complaint"]["id"] == seed["injury"]
    assert context["earliest_awareness_date"] == context["earliest_awareness"]["at"]
    assert injury["event_date"] == injury["event_at"] and injury["received_date"] == injury["received_at"]
    assert "deadline" not in {key for key in context if key != "note"}


# --------------------------------------------------------------------------------------- lists and dashboard


def test_the_reviewer_dashboard_and_lists(org):
    tenant_id, seed = org["tenant_id"], org["seed"]
    investigator, _ = org["investigator"]
    viewer, _ = org["viewer"]
    reviewer, reviewer_id = _client(tenant_id, "RISK_REVIEWER", "Dashboard")
    case = _open(investigator, seed, [seed["injury"]])
    soon = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    first = _request(investigator, case["id"], "RISK", due_at=soon).json()
    assert reviewer.post(f"{BASE}/{first['id']}/start").status_code == 200
    second_case = _open(investigator, seed, [seed["injury"]])
    second = _request(investigator, second_case["id"], "RISK").json()
    assert reviewer.post(f"{BASE}/{second['id']}/start").status_code == 200
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        db.query(CaseReview).filter(CaseReview.id == uuid.UUID(second["id"])).update(
            {"due_at": datetime.now(timezone.utc) - timedelta(days=1)}
        )
        db.commit()
    third_case = _open(investigator, seed, [seed["plain"]])
    third = _request(investigator, third_case["id"], "RISK").json()
    assert reviewer.post(f"{BASE}/{third['id']}/start").status_code == 200
    assert _complete(reviewer, third["id"], "NO_CHANGE_REQUIRED").status_code == 200
    queued_case = _open(investigator, seed, [seed["plain"]])
    queued = _request(investigator, queued_case["id"], "RISK").json()

    summary = reviewer.get(f"{BASE}/summary")
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert body["roles"] == {"risk": True, "regulatory": False}
    assert body["counts"]["mine_open"] == 2 and body["counts"]["completed_30d"] == 1
    assert body["counts"]["overdue"] >= 1 and body["counts"]["due_soon"] >= 1
    assert body["counts"]["risk_queue"] >= 1 and body["counts"]["regulatory_queue"] == 0
    assert {item["id"] for item in body["mine"]} == {first["id"], second["id"]}
    assert queued["id"] in {item["id"] for item in body["queue"]}
    assert next(item for item in body["mine"] if item["id"] == second["id"])["overdue"] is True
    assert reviewer_id

    mine = reviewer.get(BASE, params={"box": "mine"}).json()
    assert mine["total"] == 3 and {item["id"] for item in mine["items"]} == {first["id"], second["id"], third["id"]}
    completed = reviewer.get(BASE, params={"box": "mine", "status": "COMPLETED"}).json()
    assert [item["id"] for item in completed["items"]] == [third["id"]]
    assert reviewer.get(BASE, params={"box": "mine", "status": "DONE"}).status_code == 422
    assert reviewer.get(BASE, params={"box": "elsewhere"}).status_code == 422
    everything = viewer.get(BASE, params={"box": "all", "type": "RISK", "page_size": 200}).json()
    assert {first["id"], second["id"], third["id"], queued["id"]} <= {item["id"] for item in everything["items"]}
    assert all(item["review_type"] == "RISK" for item in everything["items"])

    nobody = viewer.get(f"{BASE}/summary").json()
    assert nobody["roles"] == {"risk": False, "regulatory": False}
    assert nobody["queue"] == [] and nobody["counts"]["risk_queue"] == 0
    assert viewer.get(BASE, params={"box": "queue"}).json()["items"] == []


# ------------------------------------------------------------------------------------------------ next steps


def test_the_next_steps_of_a_case(org):
    tenant_id, seed = org["tenant_id"], org["seed"]
    investigator, investigator_id = org["investigator"]
    colleague, colleague_id = org["colleague"]
    viewer, viewer_id = org["viewer"]
    case = _open(investigator, seed, [seed["plain"]])
    path = f"/api/v1/investigations/{case['id']}/next-steps"

    options = investigator.get(f"{path}/options")
    assert options.status_code == 200, options.text
    by_action = {item["action"]: item for item in options.json()["options"]}
    assert len(by_action) == 9 and by_action["CONTINUE_INVESTIGATION"]["available"] is True
    assert by_action["ESCALATE_FOR_QUALITY_REVIEW"]["available"] is False
    assert by_action["ESCALATE_FOR_QUALITY_REVIEW"]["unavailable_reason"] == (
        "Prepare and submit the Decision Brief for quality review"
    )
    assert not any(item["available"] for item in viewer.get(f"{path}/options").json()["options"])
    refused = viewer.post(path, json={"action": "CONTINUE_INVESTIGATION", "reason": REASON})
    assert refused.status_code == 403 and _code(refused) == "PERMISSION_DENIED"

    for action in ("CONTINUE_INVESTIGATION", "NO_DECISION_YET"):
        noted = investigator.post(path, json={"action": action, "reason": REASON})
        assert noted.status_code == 201, noted.text
        assert noted.json()["action"] == action and noted.json()["result"] == {"recorded": True, "business_id": None}
    recorded = _audits(tenant_id, case["id"], "NEXT_STEP_RECORDED")
    assert [event.details["action"] for event in recorded] == ["CONTINUE_INVESTIGATION", "NO_DECISION_YET"]
    assert recorded[0].reason == REASON and recorded[0].details["actor_role"] == "INVESTIGATOR"
    history = investigator.get(f"/api/v1/investigations/{case['id']}/intelligence/history").json()
    assert {item["to_value"] for item in history["items"] if item["object_type"] == "NEXT_STEP"} == {
        "CONTINUE_INVESTIGATION",
        "NO_DECISION_YET",
    }

    escalate = investigator.post(path, json={"action": "ESCALATE_FOR_QUALITY_REVIEW", "reason": REASON})
    assert escalate.status_code == 409 and _code(escalate) == "USE_DECISION_BRIEF"
    assert escalate.json()["detail"]["message"] == "Prepare and submit the Decision Brief for quality review"

    risk_step = investigator.post(path, json={"action": "REQUEST_RISK_REVIEW", "reason": REASON})
    assert risk_step.status_code == 201, risk_step.text
    review_id = risk_step.json()["result"]["review_id"]
    assert risk_step.json()["result"]["review_business_id"].startswith("REV")
    assert risk_step.json()["result"]["business_id"] == risk_step.json()["result"]["review"]["business_id"]
    review = investigator.get(f"{BASE}/{review_id}").json()
    assert review["status"] == "REQUESTED" and review["request_reason"] == REASON
    assert [task.task_type for task in _tasks(tenant_id, review_id)] == ["RISK_REVIEW"]
    again = investigator.post(path, json={"action": "REQUEST_RISK_REVIEW", "reason": REASON})
    assert again.status_code == 409 and _code(again) == "REVIEW_ALREADY_OPEN"
    options = {item["action"]: item for item in investigator.get(f"{path}/options").json()["options"]}
    assert options["REQUEST_RISK_REVIEW"]["available"] is False
    due = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    regulatory_step = investigator.post(
        path, json={"action": "REQUEST_REGULATORY_REVIEW", "reason": REASON, "details": {"due_at": due}}
    )
    assert regulatory_step.status_code == 201, regulatory_step.text
    assert investigator.get(f"{BASE}/{regulatory_step.json()['result']['review_id']}").json()["due_at"]

    missing = investigator.post(path, json={"action": "REQUEST_ADDITIONAL_EVIDENCE", "reason": REASON})
    assert missing.status_code == 422 and _code(missing) == "INVALID_NEXT_STEP_DETAILS"
    evidence_step = investigator.post(
        path,
        json={
            "action": "REQUEST_ADDITIONAL_EVIDENCE",
            "reason": REASON,
            "details": {
                "title": "Lot history of the returned pumps",
                "requested_items": ["Batch record", "Service history"],
                "recipient_role": "INVESTIGATOR",
                "priority": "HIGH",
            },
        },
    )
    assert evidence_step.status_code == 201, evidence_step.text
    testing_step = investigator.post(
        path,
        json={
            "action": "REQUEST_ADDITIONAL_TESTING",
            "reason": REASON,
            "details": {
                "title": "Burst pressure of lot 42",
                "requested_items": ["Bench test report"],
                "recipient_user_id": colleague_id,
            },
        },
    )
    assert testing_step.status_code == 201, testing_step.text
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        requests = {
            str(row.id): row
            for row in db.query(SupplierEvidenceRequest).filter(
                SupplierEvidenceRequest.investigation_id == uuid.UUID(case["id"])
            )
        }
        evidence_request = requests[evidence_step.json()["result"]["evidence_request_id"]]
        testing_request = requests[testing_step.json()["result"]["evidence_request_id"]]
        assert evidence_request.request_kind == "INTERNAL" and evidence_request.recipient_role == "INVESTIGATOR"
        assert evidence_request.priority == "HIGH" and evidence_request.requested_items["rationale"] == REASON
        assert testing_request.title == "Testing: Burst pressure of lot 42"
        assert str(testing_request.recipient_user_id) == colleague_id
        assert evidence_request.business_id == evidence_step.json()["result"]["evidence_request_business_id"]
        assert evidence_step.json()["result"]["business_id"] == evidence_request.business_id

    supplier = investigator.post(path, json={"action": "REVIEW_SUPPLIER_CHANGE", "reason": REASON})
    assert supplier.status_code == 201, supplier.text
    result = supplier.json()["result"]
    assert result["task_created"] is True and result["task_business_id"].startswith("TASK")
    assert result["business_id"] == result["task"]["business_id"] == result["task_business_id"]
    repeated = investigator.post(path, json={"action": "REVIEW_SUPPLIER_CHANGE", "reason": REASON}).json()
    assert repeated["result"]["task_id"] == result["task_id"] and repeated["result"]["task_created"] is False
    product = investigator.post(
        path, json={"action": "REVIEW_PRODUCT_CHANGE", "reason": REASON, "details": {"assigned_role": "INVESTIGATOR"}}
    )
    assert product.status_code == 201, product.text
    ineligible = investigator.post(
        path, json={"action": "REVIEW_PRODUCT_CHANGE", "reason": REASON, "details": {"assignee_user_id": viewer_id}}
    )
    assert ineligible.status_code == 422 and _code(ineligible) == "ASSIGNEE_NOT_ELIGIBLE"
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        supplier_task = db.query(WorkflowTask).filter(WorkflowTask.id == uuid.UUID(result["task_id"])).one()
        assert supplier_task.task_type == "FOLLOW_UP" and str(supplier_task.assigned_user_id) == investigator_id
        assert supplier_task.title == f"Review supplier change for {case['business_id']}"
        assert supplier_task.source_entity_type == "Investigation" and supplier_task.status == "ASSIGNED"
        product_task = (
            db.query(WorkflowTask).filter(WorkflowTask.id == uuid.UUID(product.json()["result"]["task_id"])).one()
        )
        assert product_task.assigned_user_id is None and product_task.assigned_role == "INVESTIGATOR"
        assert product_task.title == f"Review product change for {case['business_id']}"
    actions = [event.details["action"] for event in _audits(tenant_id, case["id"], "NEXT_STEP_RECORDED")]
    assert actions.count("REVIEW_SUPPLIER_CHANGE") == 2 and "REQUEST_ADDITIONAL_TESTING" in actions

    # The decision endpoints keep working beside the next steps.
    assert investigator.get(f"/api/v1/investigations/{case['id']}/decisions").status_code == 200

    _set_case(tenant_id, case["id"], status="closed", workflow_state="CLOSED")
    closed = investigator.post(path, json={"action": "CONTINUE_INVESTIGATION", "reason": REASON})
    assert closed.status_code == 409 and _code(closed) == "INVESTIGATION_CLOSED"
    closed_review = _request(investigator, case["id"], "REGULATORY")
    assert closed_review.status_code == 409 and _code(closed_review) == "INVESTIGATION_CLOSED"


# ----------------------------------------------------------------------------------------------- isolation


def test_other_organizations_reviews_and_cases_are_not_found(org):
    investigator, _ = org["investigator"]
    risk, _ = org["risk"]
    other_case, other_review = org["other_case"], org["other_review"]
    for path in (
        f"/api/v1/investigations/{other_case}/reviews/policy",
        f"/api/v1/investigations/{other_case}/reviews",
        f"/api/v1/investigations/{other_case}/next-steps/options",
        f"{BASE}/{other_review}",
        f"{BASE}/{uuid.uuid4()}",
    ):
        assert investigator.get(path).status_code == 404, path
    assert _request(investigator, other_case, "RISK").status_code == 404
    step = investigator.post(
        f"/api/v1/investigations/{other_case}/next-steps", json={"action": "NO_DECISION_YET", "reason": REASON}
    )
    assert step.status_code == 404
    for action in ("start", "complete", "recuse", "cancel"):
        body = {"outcome": "NO_CHANGE_REQUIRED", "rationale": RATIONALE, "reason": "Not my area of expertise"}
        assert risk.post(f"{BASE}/{other_review}/{action}", json=body).status_code == 404, action
    everything = risk.get(BASE, params={"box": "all", "page_size": 200}).json()["items"]
    assert other_review not in {item["id"] for item in everything}
