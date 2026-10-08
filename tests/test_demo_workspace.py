"""The AcmeCare demo workspace: its own tenant with a curated story, a named team per role, and a reset."""

import time
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app import demo_story as story
from backend.app.db.models.customer_lifecycle import TenantDataPlane
from backend.app.db.models.foundation import AuthUser, Decision, Investigation, Product, Tenant, TenantMembership
from backend.app.db.session import SessionLocal
from backend.app.demo_workspace import (
    DEMO_TEAM,
    DEMO_TENANT_KEY,
    LEGACY_DEMO_TENANT_KEY,
    DemoWorkspaceError,
    reset_demo,
    setup_demo,
    status,
)
from backend.app.main import app
from backend.app.role_codes import canonical_stored_role

PASSWORD = "Demo workspace test 2026!"
STORY = {
    "products": len(story.PRODUCTS),
    "complaints": len(story.COMPLAINTS),
    "investigations": len(story.INVESTIGATIONS),
    "evidence": sum(len(records) for records in story.EVIDENCE.values()),
    "changes": len(story.CHANGES),
    "suppliers": len(story.SUPPLIERS),
}


def _golden_products() -> int:
    db = SessionLocal()
    try:
        golden = db.query(Tenant).filter(Tenant.tenant_key == LEGACY_DEMO_TENANT_KEY).one()
        return db.query(Product).filter(Product.tenant_id == golden.id).count()
    finally:
        db.close()


@pytest.fixture(scope="module")
def demo():
    golden_before = _golden_products()
    db = SessionLocal()
    try:
        first = setup_demo(db, PASSWORD)
        second = setup_demo(db, PASSWORD)
        yield {"first": first, "second": second, "golden_before": golden_before}
    finally:
        db.close()


def _signin(email: str) -> TestClient:
    client = TestClient(app)
    response = client.post("/api/v1/auth/signin", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client


def test_setup_creates_its_own_tenant_and_is_idempotent(demo):
    assert demo["second"]["created"] == [] and demo["second"]["moved"] == []
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.tenant_key == DEMO_TENANT_KEY).one()
        assert tenant.tenant_key != LEGACY_DEMO_TENANT_KEY
        assert db.query(TenantDataPlane).filter(TenantDataPlane.tenant_id == tenant.id).one().status == "ACTIVE"
        for role, email, _ in DEMO_TEAM:
            user = db.query(AuthUser).filter(AuthUser.username == email).one()
            # Built-in roles are stored as canonical codes (backend/app/role_codes.py), e.g. INVESTIGATOR.
            assert (user.tenant_id, user.role, user.status) == (tenant.id, canonical_stored_role(role), "ACTIVE")
        assert status(db)["plan"] == "R1_GOVERNANCE_DEMO"
    finally:
        db.close()


def test_the_golden_evaluation_tenant_is_never_touched(demo):
    assert _golden_products() == demo["golden_before"]
    db = SessionLocal()
    try:
        golden = db.query(Tenant).filter(Tenant.tenant_key == LEGACY_DEMO_TENANT_KEY).one()
        demo_users = [email for _, email, _ in DEMO_TEAM]
        assert (
            db.query(AuthUser).filter(AuthUser.tenant_id == golden.id, AuthUser.username.in_(demo_users)).count() == 0
        )
    finally:
        db.close()


def test_the_story_is_curated_and_current(demo):
    db = SessionLocal()
    try:
        assert status(db)["records"] == STORY
        tenant = db.query(Tenant).filter(Tenant.tenant_key == DEMO_TENANT_KEY).one()
        cases = db.query(Investigation).filter(Investigation.tenant_id == tenant.id).all()
        assert {case.investigation_identifier for case in cases} == {item[0] for item in story.INVESTIGATIONS}
        # Dated relative to today, so recent views are never empty.
        newest = max(case.opened_at for case in cases)
        assert (datetime.now(timezone.utc) - newest).days <= 60
    finally:
        db.close()


def test_setup_refuses_a_weak_password():
    db = SessionLocal()
    try:
        with pytest.raises(DemoWorkspaceError):
            setup_demo(db, "short")
    finally:
        db.close()


def test_a_demo_account_left_in_the_golden_tenant_is_retired_and_recreated(demo):
    email = "viewer@acmecare-demo.invalid"
    db = SessionLocal()
    try:
        golden = db.query(Tenant).filter(Tenant.tenant_key == LEGACY_DEMO_TENANT_KEY).one()
        # An old-style demo account: the address lives in the golden tenant.
        current = db.query(AuthUser).filter(AuthUser.username == email).one()
        current.username = f"parked-{uuid.uuid4().hex[:8]}-{email}"
        now = datetime.now(timezone.utc)
        old = AuthUser(
            id=uuid.uuid4(),
            tenant_id=golden.id,
            username=email,
            display_name="Old demo viewer",
            company="Test",
            password_hash=current.password_hash,
            role="Viewer",
            status="ACTIVE",
            email_verified=True,
            created_at=now,
            updated_at=now,
        )
        db.add(old)
        db.flush()
        db.add(
            TenantMembership(
                id=uuid.uuid4(),
                tenant_id=golden.id,
                user_id=old.id,
                status="ACTIVE",
                is_default=True,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        result = setup_demo(db, PASSWORD)
        assert result["moved"] == [email]
        db.expire_all()
        tenant = db.query(Tenant).filter(Tenant.tenant_key == DEMO_TENANT_KEY).one()
        assert db.query(AuthUser).filter(AuthUser.username == email).one().tenant_id == tenant.id
        retired = db.query(AuthUser).filter(AuthUser.id == old.id).one()
        assert retired.status == "INACTIVE" and retired.username.startswith("retired-")
        assert db.query(TenantMembership).filter_by(tenant_id=golden.id, user_id=old.id).one().status == "INACTIVE"
    finally:
        db.close()


def test_a_user_of_another_tenant_is_never_moved(demo):
    email = "reviewer@acmecare-demo.invalid"
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.tenant_key == DEMO_TENANT_KEY).one()
        other = (
            db.query(Tenant)
            .filter(Tenant.tenant_key.notin_([DEMO_TENANT_KEY, LEGACY_DEMO_TENANT_KEY]))
            .order_by(Tenant.tenant_key)
            .first()
        )
        # The address belongs to a user of an unrelated tenant.
        current = db.query(AuthUser).filter(AuthUser.username == email).one()
        parked = f"parked-{uuid.uuid4().hex[:8]}-{email}"
        current.username = parked
        now = datetime.now(timezone.utc)
        foreign = AuthUser(
            id=uuid.uuid4(),
            tenant_id=other.id,
            username=email,
            display_name="Someone else",
            company="Other",
            password_hash=current.password_hash,
            role="Viewer",
            status="ACTIVE",
            email_verified=True,
            created_at=now,
            updated_at=now,
        )
        db.add(foreign)
        db.commit()
        try:
            with pytest.raises(DemoWorkspaceError):
                setup_demo(db, PASSWORD)
            db.rollback()
            assert db.query(AuthUser).filter(AuthUser.id == foreign.id).one().tenant_id == other.id
        finally:
            db.rollback()
            db.query(AuthUser).filter(AuthUser.id == foreign.id).delete()
            db.query(AuthUser).filter(AuthUser.username == parked).one().username = email
            db.commit()
            assert db.query(AuthUser).filter(AuthUser.username == email).one().tenant_id == tenant.id
    finally:
        db.close()


def test_each_demo_role_signs_in_and_sees_the_story(demo):
    for role, email, _ in DEMO_TEAM:
        counts = _signin(email).get("/api/v1/analytics/command-center").json()["counts"]
        assert (counts["products"], counts["investigations"]) == (STORY["products"], STORY["investigations"]), role


def test_the_demo_viewer_is_read_only(demo):
    viewer = _signin("viewer@acmecare-demo.invalid")
    assert viewer.get("/api/v1/session/context").json()["business_permissions"] == []
    investigation = viewer.get("/api/v1/analytics/investigations").json()["investigations"][0]["id"]
    refused = viewer.post(f"/api/v1/investigations/{investigation}/analysis", json={})
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "PERMISSION_DENIED"


def test_reset_removes_what_the_demo_created_and_restores_the_story(demo):
    golden_before = _golden_products()
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.tenant_key == DEMO_TENANT_KEY).one()
        investigation = db.query(Investigation).filter(Investigation.tenant_id == tenant.id).first()
        now = datetime.now(timezone.utc)
        decision_id = uuid.uuid4()
        db.add(
            Decision(
                id=decision_id,
                tenant_id=tenant.id,
                investigation_id=investigation.id,
                decision_identifier=f"DEMO-RUN-{decision_id.hex[:8]}",
                decision_type="INVESTIGATION_REVIEW",
                disposition="REQUIRES_REVIEW",
                rationale="Made during a demo",
                decision_status="REQUIRES_REVIEW",
                authorized_by_ref="leader@acmecare-demo.invalid",
                updated_at=now,
                decision_timestamp=now,
                created_at=now,
            )
        )
        db.commit()
        started = time.monotonic()
        result = reset_demo(db)
        assert time.monotonic() - started < 120
        assert db.query(Decision).filter(Decision.id == decision_id).first() is None
        assert result["records"] == STORY
        # The reset writes the golden path again (backend/app/demo_golden_path/), signed and verifiable.
        assert result["golden_path_seeded"]["seeded"] is True, result["golden_path_seeded"]
        assert result["golden_path"]["decision"]["verification"] == "VALID"
        assert status(db)["data_location_registered"] is True
    finally:
        db.close()
    assert _golden_products() == golden_before
    # The team survives a reset and can still sign in.
    assert _signin("investigator@acmecare-demo.invalid").get("/api/v1/auth/session").status_code == 200


def test_a_demo_case_has_its_own_graph_and_search_context(demo):
    from backend.app.db.models.foundation import Complaint
    from investigation_workspace.schemas import InvestigationWorkspaceRequest
    from investigation_workspace.service import InvestigationWorkspaceService

    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.tenant_key == DEMO_TENANT_KEY).one()
        case = db.query(Investigation).filter_by(tenant_id=tenant.id, investigation_identifier="ACD-INV-101").one()
        workspace = InvestigationWorkspaceService().workspace(
            db,
            InvestigationWorkspaceRequest(tenant_id=tenant.id, investigation_id=case.id, include_retrieval=True),
        )
        nodes = workspace.relationship_context["nodes"]
        assert nodes, "the graph is built from the demo tenant's own records"
        assert {node["tenant_id"] for node in nodes} == {str(tenant.id)}
        complaint_ids = {str(row.id) for row in db.query(Complaint.id).filter(Complaint.tenant_id == tenant.id)}
        graph_complaints = {node["canonical_entity_id"] for node in nodes if node["entity_type"] == "complaint"}
        assert graph_complaints and graph_complaints <= complaint_ids
        assert workspace.retrieval_context.results_count >= 1  # evidence is linked to its product and version
        assert {item.evidence_identifier for item in workspace.retrieval_context.results} <= {
            code for code, *_ in story.EVIDENCE["ACD-INV-101"]
        }
    finally:
        db.close()


# ------------------------------------------------------------------------------------- Phase 7: the golden path


def _demo_tenant(db):
    return db.query(Tenant).filter(Tenant.tenant_key == DEMO_TENANT_KEY).one()


def _golden_case(db, tenant):
    return db.query(Investigation).filter_by(tenant_id=tenant.id, investigation_identifier=story.GOLDEN_CASE).one()


def test_every_workflow_role_has_a_demo_person(demo):
    from backend.app.role_codes import WORKFLOW_ROLES

    db = SessionLocal()
    try:
        tenant = _demo_tenant(db)
        roles = {
            user.role
            for user in db.query(AuthUser).filter(
                AuthUser.tenant_id == tenant.id,
                AuthUser.username.in_([email for _, email, _ in DEMO_TEAM]),
                AuthUser.status == "ACTIVE",
            )
        }
        assert set(WORKFLOW_ROLES) <= roles
        assert {"TRIAGE_LEAD", "RISK_REVIEWER", "REGULATORY_REVIEWER"} <= roles
        assert all(email.endswith("@acmecare-demo.invalid") for _, email, _ in DEMO_TEAM)
        team = {item["email"]: item for item in status(db)["team"]}
        assert team["triage@acmecare-demo.invalid"]["role_label"] == "PMS / Signal Triage Lead"
        assert team["risk@acmecare-demo.invalid"]["name"] == "Rita Risk"
        assert team["regulatory@acmecare-demo.invalid"]["active"] is True
    finally:
        db.close()


def test_approvers_and_leaders_may_sign_in_the_demo_tenant(demo):
    from backend.app.access.permissions import normalize_role
    from backend.app.db.models.foundation import ApprovalAuthority

    db = SessionLocal()
    try:
        tenant = _demo_tenant(db)
        authorized = {
            normalize_role(row.role_name)
            for row in db.query(ApprovalAuthority).filter_by(
                tenant_id=tenant.id,
                object_type="Decision",
                decision_type="INVESTIGATION_REVIEW",
                authority="AUTHORIZED",
                status="ACTIVE",
            )
        }
        assert {normalize_role("APPROVER"), normalize_role("LEADER")} <= authorized
    finally:
        db.close()


def test_the_golden_path_is_seeded_with_business_ids(demo):
    db = SessionLocal()
    try:
        golden = status(db)["golden_path"]
    finally:
        db.close()
    assert golden["seeded"] is True, golden
    assert golden["investigation"]["identifier"] == story.GOLDEN_CASE
    assert golden["investigation"]["business_id"].startswith("INV")
    assert golden["investigation"]["workflow_state"] == "DECIDED"
    assert [item["status"] for item in golden["signals"]] == ["DECISION_RECORDED"]
    assert golden["signals"][0]["business_id"].startswith("SIG")
    assert [(item["version"], item["status"]) for item in golden["decision_briefs"]] == [
        (1, "RETURNED"),
        (2, "APPROVED_FOR_DECISION"),
    ]
    assert all(item["business_id"].startswith("DBV") for item in golden["decision_briefs"])
    assert {(item["type"], item["outcome"]) for item in golden["reviews"]} == {
        ("RISK", "RISK_CONTROL_REVIEW_REQUIRED"),
        ("REGULATORY", "REPORTABILITY_ASSESSMENT_COMPLETE"),
    }
    assert all(item["business_id"].startswith("REV") for item in golden["reviews"])
    decision = golden["decision"]
    assert decision["business_id"].startswith("DEC")
    assert decision["identifier"] == f"{story.GOLDEN_CASE}-D1"
    assert decision["outcome"] == "ACCEPT_WITH_CONDITIONS"
    assert decision["signature"].startswith("ESIG")
    assert decision["verification"] == "VALID"
    assert [item["action_type"] for item in golden["follow_ups"]] == ["CAPA_REQUIRED"]
    assert golden["follow_ups"][0]["business_id"].startswith("FUP")
    assert len(golden["capas"]) == 1 and golden["capas"][0].startswith("CAPA-")
    assert [item["status"] for item in golden["impact_assessments"]] == ["OPEN"]
    assert golden["impact_assessments"][0]["business_id"].startswith("IMP")
    # A case stays mid-investigation for live demos, and detection leaves signals awaiting triage.
    assert golden["live_case"]["workflow_state"] not in ("DECIDED", "CLOSED", "CANCELLED")
    assert golden["signals_awaiting_triage"] and all(
        item.startswith("SIG") for item in golden["signals_awaiting_triage"]
    )


def test_the_golden_signature_verifies_and_was_seeded_without_credentials(demo):
    from backend.app.db.models.foundation import AuditEvent, Decision
    from backend.app.human_decision import service

    db = SessionLocal()
    try:
        tenant = _demo_tenant(db)
        case = _golden_case(db, tenant)
        decision = service.current_decision(db, case)
        record = service.signature_record(db, decision)
        result = service.verify_signature(db, record, decision)
        assert result["status"] == "VALID" and all(check["ok"] for check in result["checks"])
        approver = db.query(AuthUser).filter(AuthUser.username == "approver@acmecare-demo.invalid").one()
        assert decision.decided_by_user_id == approver.id and record.signer_user_id == str(approver.id)
        assert decision.decision_kind == "BRIEF" and decision.conditions
        # Seeding is a system action: audited as DEMO_SEEDED, never as a signature made with credentials.
        seeded = db.query(AuditEvent).filter_by(tenant_id=tenant.id, action="DEMO_SEEDED", entity_id=decision.id)
        assert seeded.count() == 1
        assert seeded.one().details["signer_reauthenticated"] is False
        assert (
            db.query(AuditEvent)
            .filter_by(tenant_id=tenant.id, action="CASE_DECISION_SIGNED", entity_id=decision.id)
            .count()
            == 0
        )
        assert db.query(Decision).filter_by(tenant_id=tenant.id, investigation_id=case.id).count() == 1
    finally:
        db.close()


def test_the_golden_case_carries_every_workflow_record(demo):
    from backend.app.db.models.case_scope import InvestigationScopeVersion
    from backend.app.db.models.foundation import (
        FailureChain,
        FailureChainEdge,
        Hypothesis,
        HypothesisEvidence,
        InvestigationEvidence,
        Unknown,
    )
    from backend.app.db.models.signals import Signal
    from backend.app.db.models.stage3 import SupplierEvidenceRequest
    from backend.app.db.models.workflow import WorkflowTask

    db = SessionLocal()
    try:
        tenant = _demo_tenant(db)
        case = _golden_case(db, tenant)
        assert case.priority == "HIGH" and case.owner_ref == "investigator@acmecare-demo.invalid"
        versions = (
            db.query(InvestigationScopeVersion)
            .filter_by(tenant_id=tenant.id, investigation_id=case.id)
            .order_by(InvestigationScopeVersion.version)
            .all()
        )
        assert [row.version for row in versions] == [1, 2]
        assert len(versions[1].excluded_complaints) == 1 and versions[1].excluded_complaints[0]["reason"]
        signal = (
            db.query(Signal)
            .filter_by(tenant_id=tenant.id, origin="THRESHOLD_RULE", problem_key=story.GOLDEN_PROBLEM)
            .one()
        )
        assert (signal.confirmed_priority, signal.dispositioned_by) == ("HIGH", str(_user(db, "triage").id))
        links = db.query(InvestigationEvidence).filter_by(tenant_id=tenant.id, investigation_id=case.id).all()
        statuses = {row.review_status for row in links}
        assert {"ACCEPTED", "ACCEPTED_WITH_LIMITATION", "REJECTED", "UNREVIEWED"} <= statuses
        assert all(row.review_reason for row in links if row.review_status == "REJECTED")
        assert {"SUPPORTING", "CONTRADICTING"} <= {row.relationship for row in links}
        request = db.query(SupplierEvidenceRequest).filter_by(tenant_id=tenant.id, investigation_id=case.id).one()
        assert request.request_kind == "INTERNAL" and request.status == "REVIEWED"
        assert request.resolved_evidence_id is not None and request.unknown_id is not None
        resolved = db.query(Unknown).filter_by(tenant_id=tenant.id, id=request.unknown_id).one()
        assert resolved.status == "resolved"
        unknowns = {row.status for row in db.query(Unknown).filter_by(tenant_id=tenant.id, investigation_id=case.id)}
        assert {"resolved", "accepted_limitation"} <= unknowns
        hypotheses = {
            row.origin: row for row in db.query(Hypothesis).filter_by(tenant_id=tenant.id, investigation_id=case.id)
        }
        assert hypotheses["ai"].human_status == "PARTIALLY_SUPPORTED"
        assert hypotheses["human"].human_status == "RETIRED"
        relations = {
            row.relation_type
            for row in db.query(HypothesisEvidence).filter_by(tenant_id=tenant.id, hypothesis_id=hypotheses["ai"].id)
        }
        assert {"support", "contradict"} <= relations
        chain = db.query(FailureChain).filter_by(tenant_id=tenant.id, investigation_id=case.id).one()
        assert chain.origin == "human"
        states = {row.edge_status for row in db.query(FailureChainEdge).filter_by(failure_chain_id=chain.id)}
        assert len(states) >= 3
        # The case's work is in My Work: Ines keeps the case task, the follow-up and the impact assessment.
        open_types = {
            row.task_type
            for row in db.query(WorkflowTask).filter(
                WorkflowTask.tenant_id == tenant.id,
                WorkflowTask.investigation_id == case.id,
                WorkflowTask.status.in_(("NEW", "ASSIGNED", "ACCEPTED", "IN_PROGRESS", "WAITING")),
            )
        }
        assert {"INVESTIGATION", "FOLLOW_UP", "IMPACT_ASSESSMENT"} <= open_types
    finally:
        db.close()


def _user(db, local_part: str):
    return db.query(AuthUser).filter(AuthUser.username == f"{local_part}@acmecare-demo.invalid").one()


def test_the_golden_path_is_written_once_and_never_in_the_golden_tenant(demo):
    from backend.app.db.models.foundation import AuditEvent
    from backend.app.demo_golden_path import seed_golden_path

    assert demo["second"]["golden_path"]["seeded"] is False
    db = SessionLocal()
    try:
        tenant = _demo_tenant(db)
        again = seed_golden_path(db, tenant.id)
        assert again["seeded"] is False
        assert status(db)["golden_path"]["decision"]["verification"] == "VALID"
        golden = db.query(Tenant).filter(Tenant.tenant_key == LEGACY_DEMO_TENANT_KEY).one()
        assert (
            db.query(Investigation).filter_by(tenant_id=golden.id, investigation_identifier=story.GOLDEN_CASE).count()
            == 0
        )
        assert db.query(AuditEvent).filter_by(tenant_id=golden.id, action="DEMO_SEEDED").count() == 0
    finally:
        db.close()
    assert _golden_products() == demo["golden_before"]
