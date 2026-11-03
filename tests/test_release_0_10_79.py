"""Release 0.10.79: small owner-approved follow-ups to Release C.

- Settings › Products: the Regulatory Leader (role Regulatory Reviewer) may change a product's identity, its
  registrations per market and the responsible parties; the other read-only roles stay read-only, and nothing else is
  granted.
- The sample's two problem codes without an IMDRF link (FLOW_ZERO_READING, SPO2_DROPOUT_HARM) get one; a running trial
  is brought up to date once (backend/app/trial/sample_0_10_79.py).
"""

from __future__ import annotations

import uuid

import pytest

from backend.app.access.permissions import permissions_for_role
from tests.code_lists import ensure_loaded
from tests.test_free_trial import _approved_trial_client
from tests.test_release_c1_0_10_73 import _invite
from tests.test_release_c3_0_10_75 import _ok, _purge

pytestmark = pytest.mark.db

REFERENCE = "/api/v1/regulatory-reference"


def _refused(response) -> bool:
    return response.status_code == 403 and response.json()["detail"]["code"] == "PERMISSION_DENIED"


def test_the_regulatory_leader_may_edit_products_and_the_read_only_roles_may_not():
    ensure_loaded()
    owner, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        product = _ok(owner.get("/api/v1/complaints", params={"q": "SAMPLE-RV-07"}))["items"][0]["product_id"]
        path = f"{REFERENCE}/products/{product}"
        _, regulatory, _ = _invite(owner, "regulatory", "Rina Regulatory")
        _, risk, _ = _invite(owner, "risk", "Ravi Risk")
        _, executive, _ = _invite(owner, "executive", "Esha Executive")

        # The Regulatory Leader keeps the identity, the registrations and the responsible parties.
        profile = _ok(regulatory.put(f"{path}/identity", json={"basic_udi_di": "SAMPLE-BUDI-250"}))
        assert profile["basic_udi_di"] == "SAMPLE-BUDI-250"
        registration = {"market": "EU", "registration_type": "CE", "risk_class": "IIb", "registration_number": "CE-1",
                        "body_name": "NB", "body_number": "0123"}  # fmt: skip
        added = _ok(regulatory.post(f"{path}/registrations", json=registration))
        party = {"market": "EU", "role": "MANUFACTURER", "organisation": "Sample maker", "srn": "XX-MF-000000001"}
        saved = _ok(regulatory.put(f"{REFERENCE}/responsible-parties", json=party))

        # Risk Reviewer and Executive (View only) stay read only: they read, and every change is refused.
        for person in (risk, executive):
            assert _ok(person.get(path))["basic_udi_di"] == "SAMPLE-BUDI-250"
            assert _refused(person.put(f"{path}/identity", json={"basic_udi_di": "X"}))
            assert _refused(person.post(f"{path}/registrations", json=registration))
            assert _refused(person.delete(f"{path}/registrations/{added['id']}"))
            assert _refused(person.put(f"{REFERENCE}/responsible-parties", json=party))
            assert _refused(person.delete(f"{REFERENCE}/responsible-parties/{saved['id']}"))

        # Nothing else is granted: proposing a code mapping still needs records.write, and the role is unchanged.
        mapping = {"customer_code": "X", "release": "2026", "annex": "A", "imdrf_code": "A1601"}
        assert _refused(regulatory.post(f"{REFERENCE}/imdrf/mappings", json=mapping))
        assert "records.write" not in permissions_for_role("REGULATORY_REVIEWER")
        assert regulatory.delete(f"{path}/registrations/{added['id']}").status_code == 204
        assert regulatory.delete(f"{REFERENCE}/responsible-parties/{saved['id']}").status_code == 204
    finally:
        _purge(tenant_id)


def test_a_running_trial_gets_the_two_new_links_once():
    from backend.app.db.models.regulatory_reference import ImdrfCodeMapping
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_tenant
    from backend.app.trial import sample_0_10_79
    from backend.app.trial.sample_imports import PROBLEM_CODES

    ensure_loaded()
    owner, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    codes = ("FLOW_ZERO_READING", "SPO2_DROPOUT_HARM")
    try:
        links = _ok(owner.get(f"{REFERENCE}/imdrf/links", params={"code": "FLOW_ZERO_READING"}))["links"]
        assert [link["code"] for link in links["FLOW_ZERO_READING"]] == ["A090808"]
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            assert sample_0_10_79.refresh(db, tenant_id, apply=False) == 0  # a new trial has them
            rows = db.query(ImdrfCodeMapping).filter(
                ImdrfCodeMapping.tenant_id == tenant_id,
                ImdrfCodeMapping.customer_system == PROBLEM_CODES,
                ImdrfCodeMapping.customer_code.in_(codes),
            )
            assert sorted((row.customer_code, row.release, row.imdrf_code) for row in rows) == [
                ("FLOW_ZERO_READING", "2026", "A090808"),
                ("SPO2_DROPOUT_HARM", "2026", "A090811"),
            ]
            rows.delete(synchronize_session=False)  # as a trial made before 0.10.79 had it
            db.flush()
            assert sample_0_10_79.refresh(db, tenant_id, apply=False) == 2
            assert rows.count() == 0  # the dry run changes nothing
            assert sample_0_10_79.refresh(db, tenant_id, apply=True) == 2
            assert sample_0_10_79.refresh(db, tenant_id, apply=True) == 0  # idempotent
            assert all(row.status == "APPROVED" and row.annex == "A" for row in rows)
            # A trial user's own link of the code is kept: the step adds only where the code has none.
            rows.filter(ImdrfCodeMapping.customer_code == "SPO2_DROPOUT_HARM").update({"imdrf_code": "A070911"})
            db.flush()
            assert sample_0_10_79.refresh(db, tenant_id, apply=False) == 0
            db.commit()
    finally:
        _purge(tenant_id)
