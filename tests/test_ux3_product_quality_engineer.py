"""UX3 (Persona Blueprint wave C): the Product Quality Engineer, a workspace persona and an assignable role.

- One role list: PRODUCT_QUALITY_ENGINEER is a standard role named "Product Quality Engineer" everywhere (signatures,
  Team, the invite form, "Viewing as"), whose persona's Today is the Product Lifecycle Twin (Today, Investigations,
  Products).
- Its rights are the server's: it reads products, versions, changes and lots (any signed-in person may), and works on
  investigations (judges hypotheses, reviews and asks for evidence) and exports. It changes no records, never triages,
  approves a regulatory document or signs a decision.
- A trial owner invites one as a colleague; a customer administrator gives the role like any other.
"""

from __future__ import annotations

import uuid

import pytest

from access_control.personas import COLLEAGUE_PERSONAS, persona_for_role, workspace_persona
from backend.app.access import permissions as perms
from backend.app.access.identity import STANDARD_ROLES
from backend.app.role_codes import CANONICAL_SYSTEM_ROLES, ROLE_LABELS, WORKFLOW_ROLES, canonical_stored_role

PQE = "PRODUCT_QUALITY_ENGINEER"


def test_the_role_is_one_standard_role_with_one_name():
    assert PQE in CANONICAL_SYSTEM_ROLES and PQE in STANDARD_ROLES and PQE in WORKFLOW_ROLES
    assert ROLE_LABELS[PQE] == "Product Quality Engineer"
    assert canonical_stored_role("Product Quality Engineer") == PQE
    persona = workspace_persona("pqe")
    assert persona.label == ROLE_LABELS[PQE] and persona.role == PQE
    assert persona.tabs == ("home", "investigations", "products")
    assert persona_for_role(PQE) == "pqe" and "pqe" in COLLEAGUE_PERSONAS


def test_it_contributes_to_investigations_and_never_signs_changes_records_or_triages():
    granted = perms.permissions_for_role(PQE)
    assert granted == {perms.INVESTIGATION_WORK, perms.EVIDENCE_REVIEW, perms.EVIDENCE_REQUEST, perms.DATA_EXPORT}
    for refused in (
        perms.DECISION_SIGN,
        perms.RECORDS_WRITE,
        perms.REGULATORY_APPROVE,
        perms.QUALITY_REVIEW,
        perms.RISK_REVIEW,
        perms.SIGNAL_TRIAGE,
        perms.COMPLAINT_TRIAGE,
        perms.CASE_LOG,
        perms.AI_RUN,
    ):
        assert refused not in granted, refused


@pytest.mark.db
def test_a_trial_colleague_works_as_a_product_quality_engineer():
    from backend.app.db.session import SessionLocal
    from tests.test_free_trial import _approved_trial_client
    from tests.test_release_c1_0_10_73 import _invite, _ok

    owner, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        invited, pqe, _ = _invite(owner, "pqe", "Priya Product")
        context = _ok(pqe.get("/api/v1/session/context"))
        assert context["persona"] == "pqe" and context["persona_label"] == "Product Quality Engineer"
        assert context["persona_tabs"] == ["home", "investigations", "products"]
        assert set(context["business_permissions"]) == {
            "investigation.work",
            "evidence.review",
            "evidence.request",
            "data.export",
        }
        # Today: the trend check by version and the rising version's product page.
        trends = _ok(pqe.get("/api/v1/triage/trends", params={"group": "version"}))
        rising = [row for row in trends["items"] if row["result"] in ("SIGNIFICANT", "ELEVATED")]
        assert rising, "the sample's rising version"
        product = rising[0]["product"]["identifier"]
        page = _ok(pqe.get(f"/api/v1/products/{product}/product-360", params={"light": 1}))
        assert [row["version_identifier"] for row in page["versions"]][:2] == ["Rev A", "Rev B"]
        # It works on the sample investigation: adds a hypothesis of its own.
        case_id = _ok(owner.get("/api/v1/trial/one-story"))["flagship"]["investigation"]["id"]
        added = pqe.post(
            f"/api/v1/investigations/{case_id}/intelligence/hypotheses",
            json={"statement": "The Rev B sensor's incoming inspection was cut from 32 to 13 units a lot"},
        )
        assert added.status_code == 201, added.text
        # It never signs: the approvals queue and the signature are refused on the server.
        assert pqe.get("/api/v1/decisions/queue").status_code == 403
        signed = pqe.post(
            f"/api/v1/investigations/{case_id}/decision/return",
            json={"comment": "A product quality engineer may not return or sign a decision."},
        )
        assert signed.status_code == 403
        # It changes no records: recording a decision on the investigation needs records.write.
        assert pqe.post(f"/api/v1/investigations/{case_id}/decisions", json={}).status_code == 403
        assert invited["persona"] == "pqe"
    finally:
        from backend.app.trial.retention import purge_trial

        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:ux3-cleanup")
