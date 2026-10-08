"""Seeded records for the report, investigation-record, story, risk and regulatory tests.

Every record carries a unique tag, so the tests find their own rows among the golden organization's data and never
depend on what other tests left behind. ``seed_case`` builds one complete case: a product and version, a flagged
complaint, an investigation with direct and linked evidence, a hypothesis, an unknown, two decisions (one signed with
a valid signature), a risk linked to a failure mode, a control (with verification evidence) and a requirement, an AI
execution with an assurance result, and an audit event about the case.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import text

from auth.durable import persist_session
from auth.service import _hash
from backend.app.db.models.evidence_intelligence import EvidenceEntityLink
from backend.app.db.models.foundation import (
    AIExecution,
    AssuranceResult,
    AuditEvent,
    AuthUser,
    Complaint,
    Control,
    Decision,
    Evidence,
    FailureMode,
    Hypothesis,
    HypothesisEvidence,
    Investigation,
    InvestigationComplaint,
    InvestigationEvidence,
    Product,
    ProductVersion,
    RealityRelationship,
    Requirement,
    Risk,
    SignedApprovalRecord,
    Tenant,
    TenantMembership,
    Unknown,
)
from backend.app.db.models.retrieval_intelligence import RetrievalQuery
from backend.app.db.session import SessionLocal
from backend.app.main import app

PASSWORD = "Report seed 2026!"
GOLDEN = "ACME_CARE_SYNTHETIC"


def golden_tenant_id() -> uuid.UUID:
    with SessionLocal() as db:
        return db.query(Tenant.id).filter(Tenant.tenant_key == GOLDEN).one()[0]


def role_client(role: str) -> tuple[TestClient, str]:
    """A signed-in client of the golden organization with ``role``, and the account's id."""
    with SessionLocal() as db:
        tenant_id = db.query(Tenant.id).filter(Tenant.tenant_key == GOLDEN).one()[0]
        now = datetime.now(timezone.utc)
        user = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            username=f"reports-{role.lower()}-{uuid.uuid4().hex[:8]}@example.invalid",
            display_name=f"{role} reports test",
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


def _signature(tenant_id, decision: Decision, signer: str) -> SignedApprovalRecord:
    """A signature with the same material and hashes the Decision Center writes, so it verifies as valid."""
    version = decision.updated_at.isoformat()
    material = {
        "decision_id": str(decision.id),
        "version": version,
        "type": "INVESTIGATION_REVIEW",
        "decision": "APPROVE",
        "remarks": "Seeded approval",
    }
    fingerprint = hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()
    now = datetime.now(timezone.utc)
    return SignedApprovalRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        object_type="Decision",
        object_id=decision.id,
        object_version=version,
        decision_type="INVESTIGATION_REVIEW",
        decision="APPROVE",
        remarks="Seeded approval",
        signer_user_id=signer,
        signer_role="APPROVER",
        signature_meaning="I have reviewed this record and approve this decision.",
        content_fingerprint=fingerprint,
        signature_hash=hashlib.sha256((fingerprint + signer + version).encode()).hexdigest(),
        status="SIGNED",
        signed_at=now,
        created_at=now,
    )


def seed_case() -> dict:
    """One complete, tagged case in the golden organization (see the module docstring); returns its ids and tags."""
    tag = uuid.uuid4().hex[:8].upper()
    now = datetime.now(timezone.utc)
    stamp = {"created_at": now, "updated_at": now}
    with SessionLocal() as db:
        tenant_id = db.query(Tenant.id).filter(Tenant.tenant_key == GOLDEN).one()[0]
        t = {"tenant_id": tenant_id}
        product = Product(id=uuid.uuid4(), product_identifier=f"P-{tag}", name=f"Seed pump {tag}", **t, **stamp)
        db.add(product)
        db.flush()
        version = ProductVersion(
            id=uuid.uuid4(),
            product_id=product.id,
            version_identifier=f"V-{tag}",
            lifecycle_status="released",
            **t,
            **stamp,
        )
        db.add(version)
        db.flush()
        complaint = Complaint(
            id=uuid.uuid4(),
            complaint_identifier=f"C-{tag}",
            description="Occlusion alarm during infusion",
            product_id=product.id,
            product_version_id=version.id,
            status="open",
            severity="high",
            serious_injury=True,
            # A value a spreadsheet would run as a formula: every CSV must neutralize it.
            problem_code='=HYPERLINK("http://evil.example","x")',
            event_timestamp=now - timedelta(days=40),
            awareness_timestamp=now - timedelta(days=2),
            complaint_timestamp=now,
            **t,
            **stamp,
        )
        case = Investigation(
            id=uuid.uuid4(),
            investigation_identifier=f"INV-{tag}",
            product_id=product.id,
            investigation_question="Why do occlusion alarms occur?",
            status="open",
            owner_ref="owner@example.invalid",
            opened_at=now - timedelta(days=3),
            **t,
            **stamp,
        )
        db.add_all([complaint, case])
        db.flush()
        direct = Evidence(
            id=uuid.uuid4(),
            evidence_identifier=f"EV-{tag}-1",
            evidence_type="test_report",
            title="Bench test of occlusion sensor",
            investigation_id=case.id,
            fact_type="source_fact",
            reliability_status="verified",
            source_system="QMS",
            source_identifier=f"QMS-{tag}",
            source_reference=f"qms://reports/{tag}",
            effective_timestamp=now - timedelta(days=5),
            recorded_timestamp=now - timedelta(days=4),
            ingestion_timestamp=now,
            **t,
            **stamp,
        )
        linked = Evidence(
            id=uuid.uuid4(),
            evidence_identifier=f"EV-{tag}-2",
            evidence_type="service_record",
            title="Field service note",
            fact_type="source_fact",
            source_system="SERVICE",
            **t,
            **stamp,
        )
        verification = Evidence(
            id=uuid.uuid4(),
            evidence_identifier=f"EV-{tag}-V",
            evidence_type="verification_report",
            title="Control verification",
            fact_type="source_fact",
            **t,
            **stamp,
        )
        db.add_all([direct, linked, verification])
        db.flush()
        db.add_all(
            [
                InvestigationComplaint(
                    id=uuid.uuid4(), investigation_id=case.id, complaint_id=complaint.id, created_at=now, **t
                ),
                InvestigationEvidence(
                    id=uuid.uuid4(), investigation_id=case.id, evidence_id=linked.id, created_at=now, **t
                ),
            ]
        )
        hypothesis = Hypothesis(
            id=uuid.uuid4(),
            investigation_id=case.id,
            statement=f"Sensor drift may be associated with alarms ({tag})",
            origin="human",
            **t,
            **stamp,
        )
        db.add(hypothesis)
        db.flush()
        db.add(
            HypothesisEvidence(
                id=uuid.uuid4(),
                hypothesis_id=hypothesis.id,
                evidence_id=direct.id,
                relation_type="support",
                created_by_type="human",
                created_at=now,
                **t,
            )
        )
        db.add(
            Unknown(
                id=uuid.uuid4(),
                investigation_id=case.id,
                description="Lot of the returned device",
                status="open",
                **t,
                **stamp,
            )
        )
        decisions = []
        for suffix, status in (("R", "REQUIRES_REVIEW"), ("S", "APPROVED")):
            decisions.append(
                Decision(
                    id=uuid.uuid4(),
                    investigation_id=case.id,
                    decision_identifier=f"D-{tag}-{suffix}",
                    decision_type="INVESTIGATION_REVIEW",
                    disposition="CONTINUE",
                    rationale="Seeded decision",
                    decision_status=status,
                    authorized_by_ref="someone-else",
                    decision_timestamp=now,
                    **t,
                    **stamp,
                )
            )
        db.add_all(decisions)
        db.flush()
        signature = _signature(tenant_id, decisions[1], "seed-approver")
        db.add(signature)
        risk = Risk(
            id=uuid.uuid4(),
            risk_identifier=f"R-{tag}",
            description="=cmd|' /C calc'!A0",
            product_id=product.id,
            **t,
            **stamp,
        )
        mode = FailureMode(id=uuid.uuid4(), failure_mode_identifier=f"FM-{tag}", name="Sensor drift", **t, **stamp)
        control = Control(
            id=uuid.uuid4(), control_identifier=f"CTL-{tag}", description="Sensor calibration", **t, **stamp
        )
        unlinked = Control(
            id=uuid.uuid4(), control_identifier=f"CTL-{tag}-U", description="Orphan control", **t, **stamp
        )
        requirement = Requirement(
            id=uuid.uuid4(), requirement_identifier=f"REQ-{tag}", text="Alarm within 30 s", **t, **stamp
        )
        db.add_all([risk, mode, control, unlinked, requirement])
        db.flush()
        for source_type, source_id, kind in (
            ("Control", control.id, "CONTROLS"),
            ("FailureMode", mode.id, "CAN_LEAD_TO"),
            ("Requirement", requirement.id, "MITIGATES"),
        ):
            db.add(
                RealityRelationship(
                    id=uuid.uuid4(),
                    source_entity_type=source_type,
                    source_entity_id=source_id,
                    target_entity_type="Risk",
                    target_entity_id=risk.id,
                    relationship_type=kind,
                    created_at=now,
                    **t,
                )
            )
        db.add(
            EvidenceEntityLink(
                id=uuid.uuid4(), evidence_id=verification.id, entity_type="Control", entity_id=control.id, **t
            )
        )
        execution = AIExecution(
            id=uuid.uuid4(),
            investigation_id=case.id,
            provider="controlled",
            model_name="mdarix-rule-grounded",
            validation_status="PASSED",
            execution_timestamp=now,
            latency_ms=12,
            **t,
        )
        db.add(execution)
        db.flush()
        db.add(
            AssuranceResult(
                id=uuid.uuid4(),
                ai_execution_id=execution.id,
                output_type="INVESTIGATION_ANALYSIS",
                status="PASS",
                generated_at=now,
                trust_policy_version="MDARIX_AI_TRUST_POLICY_R1_V1",
                created_at=now,
                **t,
            )
        )
        event = AuditEvent(
            id=uuid.uuid4(),
            actor_ref="seed",
            action="INVESTIGATION_SEEDED",
            entity_type="Investigation",
            entity_id=case.id,
            details={"tag": tag},
            created_at=now,
            **t,
        )
        db.add(event)
        db.commit()
        return {
            "tag": tag,
            "tenant_id": str(tenant_id),
            "product_id": str(product.id),
            "version_id": str(version.id),
            "investigation_id": str(case.id),
            "decision_ids": [str(item.id) for item in decisions],
            "signature_id": str(signature.id),
            "risk_id": str(risk.id),
            "audit_event_id": str(event.id),
        }


def bare_case() -> dict:
    """An investigation with a product and nothing else (no evidence, analysis or decision)."""
    tag = uuid.uuid4().hex[:8].upper()
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        tenant_id = db.query(Tenant.id).filter(Tenant.tenant_key == GOLDEN).one()[0]
        product = Product(
            id=uuid.uuid4(),
            product_identifier=f"P-{tag}",
            name="Bare",
            tenant_id=tenant_id,
            created_at=now,
            updated_at=now,
        )
        db.add(product)
        db.flush()
        case = Investigation(
            id=uuid.uuid4(),
            investigation_identifier=f"INV-{tag}",
            product_id=product.id,
            investigation_question="Bare case",
            tenant_id=tenant_id,
            created_at=now,
            updated_at=now,
        )
        db.add(case)
        db.commit()
        return {"tag": tag, "investigation_id": str(case.id)}


def cleanup(seed: dict) -> None:
    """Remove a seeded case's records (audit events and signatures are immutable by design and stay)."""
    from backend.app.db.models.foundation import FailureChain, HumanReview, Scenario

    tag = seed["tag"]
    with SessionLocal() as db:
        tenant_id = db.query(Tenant.id).filter(Tenant.tenant_key == GOLDEN).one()[0]
        cases = [
            row.id for row in db.query(Investigation.id).filter(Investigation.investigation_identifier == f"INV-{tag}")
        ]
        evidence = [row.id for row in db.query(Evidence.id).filter(Evidence.evidence_identifier.like(f"EV-{tag}-%"))]
        risks = [row.id for row in db.query(Risk.id).filter(Risk.risk_identifier == f"R-{tag}")]
        controls = [row.id for row in db.query(Control.id).filter(Control.control_identifier.like(f"CTL-{tag}%"))]
        modes = [row.id for row in db.query(FailureMode.id).filter(FailureMode.failure_mode_identifier == f"FM-{tag}")]
        requirements = [
            row.id for row in db.query(Requirement.id).filter(Requirement.requirement_identifier == f"REQ-{tag}")
        ]
        hypotheses = [row.id for row in db.query(Hypothesis.id).filter(Hypothesis.investigation_id.in_(cases))]
        executions = [row.id for row in db.query(AIExecution.id).filter(AIExecution.investigation_id.in_(cases))]
        decisions = [row.id for row in db.query(Decision.id).filter(Decision.investigation_id.in_(cases))]
        steps = [
            db.query(EvidenceEntityLink).filter(EvidenceEntityLink.evidence_id.in_(evidence)),
            db.query(RealityRelationship).filter(RealityRelationship.target_entity_id.in_(risks)),
            db.query(HypothesisEvidence).filter(HypothesisEvidence.hypothesis_id.in_(hypotheses)),
            # Unknowns and failure chains may point at a hypothesis (md30), so they go first.
            db.query(Unknown).filter(Unknown.investigation_id.in_(cases)),
            db.query(FailureChain).filter(FailureChain.investigation_id.in_(cases)),
            db.query(Hypothesis).filter(Hypothesis.id.in_(hypotheses)),
            db.query(Scenario).filter(Scenario.investigation_id.in_(cases)),
            db.query(AssuranceResult).filter(AssuranceResult.ai_execution_id.in_(executions)),
            db.query(AIExecution).filter(AIExecution.id.in_(executions)),
            db.query(HumanReview).filter(HumanReview.decision_id.in_(decisions)),
            db.query(Decision).filter(Decision.id.in_(decisions)),
            db.query(InvestigationComplaint).filter(InvestigationComplaint.investigation_id.in_(cases)),
            db.query(InvestigationEvidence).filter(InvestigationEvidence.investigation_id.in_(cases)),
            db.query(Evidence).filter(Evidence.id.in_(evidence)),
            # Questions asked about a case (Ask, scenarios) keep a reference to it.
            db.query(RetrievalQuery).filter(RetrievalQuery.investigation_id.in_(cases)),
            db.query(Investigation).filter(Investigation.id.in_(cases)),
            db.query(Complaint).filter(Complaint.complaint_identifier == f"C-{tag}"),
            db.query(Risk).filter(Risk.id.in_(risks)),
            db.query(Control).filter(Control.id.in_(controls)),
            db.query(FailureMode).filter(FailureMode.id.in_(modes)),
            db.query(Requirement).filter(Requirement.id.in_(requirements)),
            db.query(ProductVersion).filter(ProductVersion.version_identifier == f"V-{tag}"),
            db.query(Product).filter(Product.product_identifier == f"P-{tag}"),
        ]
        # Records the workflow adds around a case (tasks and their history, review and intelligence events, scope
        # versions, signal links, CAPAs, briefs) go before the case; children before parents.
        if cases:
            for statement in (
                "DELETE FROM workflow_task_events WHERE task_id IN "
                "(SELECT id FROM workflow_tasks WHERE tenant_id = :tenant AND investigation_id = ANY(:cases))",
                "DELETE FROM workflow_tasks WHERE tenant_id = :tenant AND investigation_id = ANY(:cases)",
                "DELETE FROM evidence_review_events WHERE tenant_id = :tenant AND investigation_id = ANY(:cases)",
                "DELETE FROM intelligence_events WHERE tenant_id = :tenant AND investigation_id = ANY(:cases)",
                "DELETE FROM investigation_scope_versions WHERE tenant_id = :tenant AND investigation_id = ANY(:cases)",
                "DELETE FROM investigation_signals WHERE tenant_id = :tenant AND investigation_id = ANY(:cases)",
                "DELETE FROM capas WHERE tenant_id = :tenant AND investigation_id = ANY(:cases)",
                "DELETE FROM investigation_briefs WHERE tenant_id = :tenant AND investigation_id = ANY(:cases)",
            ):
                db.execute(text(statement), {"tenant": tenant_id, "cases": list(cases)})
        for query in steps:
            query.filter_by(tenant_id=tenant_id).delete(synchronize_session=False)
        db.commit()
