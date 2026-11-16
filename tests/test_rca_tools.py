"""RCA tools end to end (spec Part A and C): 5 Whys, fishbone, the confirmed cause at signing, the Pareto route, the
version at the event date, permissions, organization isolation and the switches.

Everything runs in fresh organizations of their own (on the shared plane), deleted at the end.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.db.models.foundation import (
    Complaint,
    Decision,
    FailureMode,
    Hypothesis,
    InvestigationComplaint,
    Product,
    ProductVersion,
    RealityRelationship,
    Risk,
)
from backend.app.db.models.stage3 import ContextSnapshot
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.test_decision_brief import _case, _client, _code, _row
from tests.test_human_decision import _approved, _body, _change, _path
from tests.test_human_decision import org as org  # noqa: F401  (the module fixture)

REASON = "The incoming inspection records rule this out"


@pytest.fixture(scope="module")
def other():
    """A second organization with an investigator, for isolation."""
    from backend.app.customer_lifecycle import build_customer_tenant
    from backend.app.trial.retention import purge_trial

    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        customer, tenant = build_customer_tenant(
            db=db, tenant_key=f"RCAOTHER_{uuid.uuid4().hex[:8].upper()}", name="RCA other", status="ACTIVE", now=now
        )
        db.add(customer)
        db.add(tenant)
        db.commit()
        tenant_id = tenant.id
    people = {"investigator": _client(tenant_id, "INVESTIGATOR", "Other")}
    try:
        yield {"tenant_id": tenant_id, **people}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:rca-other-cleanup")


def _rca(case_id) -> str:
    return f"/api/v1/investigations/{case_id}/rca"


def _hypotheses(client, case_id) -> list[dict]:
    response = client.get(f"/api/v1/investigations/{case_id}/intelligence/hypotheses")
    assert response.status_code == 200, response.text
    return response.json()["items"]


def _failure_mode(tenant_id, *, with_risk: bool = False) -> str:
    now = datetime.now(timezone.utc)
    tag = uuid.uuid4().hex[:6].upper()
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        mode = FailureMode(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            failure_mode_identifier=f"FM-{tag}",
            name=f"Sensor reads high {tag}",
            created_at=now,
            updated_at=now,
        )
        db.add(mode)
        if with_risk:
            risk = Risk(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                risk_identifier=f"RSK-{tag}",
                description="Delayed therapy from false alarms",
                created_at=now,
                updated_at=now,
            )
            db.add(risk)
            db.flush()
            db.add(
                RealityRelationship(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    source_entity_type="FailureMode",
                    source_entity_id=mode.id,
                    target_entity_type="Risk",
                    target_entity_id=risk.id,
                    relationship_type="CAN_LEAD_TO",
                    created_at=now,
                )
            )
        db.commit()
        return str(mode.id)


# ----------------------------------------------------------------------------------------------------- 5 Whys


def _whys(count: int) -> list[dict]:
    return [{"text": f"Why number {index + 1}"} for index in range(count)]


def test_five_whys_two_to_seven_whys_link_and_isolation(org, other):
    investigator, _ = org["investigator"]
    case = _case(org, ready=False)
    path = _rca(case["id"]) + "/five-whys"
    for count in (1, 8):
        refused = investigator.post(path, json={"problem": "Pressure alarms", "whys": _whys(count)})
        assert refused.status_code == 422, refused.text
    supported = investigator.post(
        path,
        json={"problem": "Pressure alarms", "whys": [{"text": "Pump reads high", "state": "SUPPORTED"}, *_whys(1)]},
    )
    assert supported.status_code == 422  # SUPPORTED needs evidence
    viewer, _ = org["viewer"]
    assert viewer.post(path, json={"problem": "Pressure alarms", "whys": _whys(2)}).status_code == 403

    made = investigator.post(path, json={"problem": "Pressure alarms on the ward", "whys": _whys(3)})
    assert made.status_code == 201, made.text
    chain = made.json()["items"][0]
    assert chain["method"] == "FIVE_WHYS" and len(chain["nodes"]) == 4 and len(chain["links"]) == 3
    assert chain["nodes"][0]["kind"] == "PROBLEM" and chain["nodes"][-1]["is_last"] is True
    assert all(link["state"] == "UNKNOWN" and link["unknown_prompt"] for link in chain["links"])

    hypothesis = investigator.post(
        f"/api/v1/investigations/{case['id']}/intelligence/hypotheses",
        json={"statement": "Incoming inspection was reduced after the supplier change"},
    ).json()
    before = _row(org["tenant_id"], Hypothesis, id=uuid.UUID(hypothesis["id"]))
    linked = investigator.post(f"{path}/{chain['id']}/link", json={"hypothesis_id": hypothesis["id"]})
    assert linked.status_code == 200, linked.text
    assert linked.json()["items"][0]["nodes"][-1]["hypothesis"]["id"] == hypothesis["id"]
    after = _row(org["tenant_id"], Hypothesis, id=uuid.UUID(hypothesis["id"]))
    # A why never sets a hypothesis status.
    assert (after.human_status, after.status, after.updated_at) == (
        before.human_status,
        before.status,
        before.updated_at,
    )
    assert investigator.post(f"{path}/{chain['id']}/link", json={"hypothesis_id": hypothesis["id"]}).status_code == 409

    stranger, _ = other["investigator"]
    assert stranger.get(path).status_code == 404
    own = _case(other, ready=False)
    assert (
        stranger.post(
            _rca(own["id"]) + f"/five-whys/{chain['id']}/link", json={"hypothesis_id": hypothesis["id"]}
        ).status_code
        == 404
    )


# ---------------------------------------------------------------------------------------------------- fishbone


def test_fishbone_quick_add_rule_out_failure_mode_and_isolation(org, other):
    tenant_id = org["tenant_id"]
    investigator, _ = org["investigator"]
    case = _case(org, ready=False)
    causes = _rca(case["id"]) + "/causes"
    claim = investigator.post(
        causes, json={"statement": "The supplier change is the root cause", "cause_category": "MATERIAL"}
    )
    assert claim.status_code == 422 and "not yet a finding" in claim.text
    assert (
        investigator.post(causes, json={"statement": "Sensor lot drift", "cause_category": "DESIGN"}).status_code == 422
    )
    foreign_mode = _failure_mode(other["tenant_id"])
    foreign = investigator.post(
        causes,
        json={"statement": "Sensor lot drift high", "cause_category": "MATERIAL", "failure_mode_id": foreign_mode},
    )
    assert foreign.status_code == 404 and _code(foreign) == "FAILURE_MODE_NOT_FOUND"

    mode = _failure_mode(tenant_id, with_risk=True)
    added = investigator.post(
        causes,
        json={
            "statement": "Sensor lot drift after the supplier change",
            "cause_category": "MATERIAL",
            "failure_mode_id": mode,
        },
    )
    assert added.status_code == 201, added.text
    grid = added.json()
    material = next(column for column in grid["categories"] if column["code"] == "MATERIAL")
    cause = material["causes"][0]
    assert cause["human_status"] == "PROPOSED" and cause["origin"] == "HUMAN" and cause["confirmed_in"] is None
    assert cause["failure_mode"]["id"] == mode and cause["failure_mode"]["risks"][0]["description"]
    assert "SOFTWARE" not in [column["code"] for column in grid["categories"]]  # not a software product

    ward = investigator.post(
        causes, json={"statement": "Ward alarm limits set too tight", "cause_category": "ENVIRONMENT"}
    ).json()
    ward_cause = next(c for col in ward["categories"] if col["code"] == "ENVIRONMENT" for c in col["causes"])
    status = f"/api/v1/investigations/{case['id']}/intelligence/hypotheses/{ward_cause['id']}/status"
    assert investigator.post(status, json={"human_status": "CONTRADICTED", "reason": "no"}).status_code == 422
    assert investigator.post(status, json={"human_status": "CONTRADICTED", "reason": REASON}).status_code == 200
    grid = investigator.get(_rca(case["id"]) + "/fishbone").json()
    ruled = next(c for col in grid["categories"] if col["code"] == "ENVIRONMENT" for c in col["causes"])
    assert ruled["ruled_out"] is True and ruled["ruled_out_reason"] == REASON  # stays visible with its reason

    moved = investigator.post(
        f"{causes}/{ward_cause['id']}",
        json={"cause_category": "PEOPLE", "reason": "Set by the ward staff, not the site"},
    )
    assert moved.status_code == 200 and any(
        c["id"] == ward_cause["id"] for c in moved.json()["categories"][0]["causes"]
    )
    assert _row(tenant_id, Hypothesis, id=uuid.UUID(ward_cause["id"])).human_status == "CONTRADICTED"  # unchanged

    viewer, _ = org["viewer"]
    assert (
        viewer.post(causes, json={"statement": "Something else entirely", "cause_category": "METHOD"}).status_code
        == 403
    )
    stranger, _ = other["investigator"]
    assert stranger.get(_rca(case["id"]) + "/fishbone").status_code == 404


# ---------------------------------------------------------------------------------- the confirmed cause at signing


def test_the_confirmed_cause_is_ticked_at_signing_and_bound(org, other):
    tenant_id = org["tenant_id"]
    approver, _ = org["approver"]
    approver2, _ = org["approver2"]
    case, brief = _approved(org)
    sign = _path(case["id"]) + "/sign"
    hypotheses = _hypotheses(approver, case["id"])
    judged = next(item for item in hypotheses if item["human_status"] == "STRONGLY_SUPPORTED")
    before = _row(tenant_id, Hypothesis, id=uuid.UUID(judged["id"]))

    missing = approver.post(sign, json=_body(brief, root_cause_category=None))
    assert missing.status_code == 422 and "cause category" in missing.text
    vague = approver.post(sign, json=_body(brief, root_cause_category="NOT_DETERMINED"))
    assert vague.status_code == 422 and "Not determined" in vague.text
    elsewhere, _ = _approved(org)
    foreign_hypothesis = _hypotheses(approver, elsewhere["id"])[0]["id"]
    wrong = approver.post(sign, json=_body(brief, root_cause_hypothesis_ids=[foreign_hypothesis]))
    assert wrong.status_code == 422 and _code(wrong) == "ROOT_CAUSE_HYPOTHESIS_INVALID"

    signed = approver.post(sign, json=_body(brief, root_cause_hypothesis_ids=[judged["id"]]))
    assert signed.status_code == 200, signed.text
    decision = signed.json()["decision"]
    assert decision["root_cause_category"] == "MATERIAL" and decision["root_cause_hypothesis_ids"] == [judged["id"]]
    row = _row(tenant_id, Decision, id=uuid.UUID(decision["id"]))
    snapshot = _row(tenant_id, ContextSnapshot, decision_id=row.id)
    assert snapshot.snapshot["root_cause"]["category"] == "MATERIAL"
    assert [item["id"] for item in snapshot.snapshot["root_cause"]["hypotheses"]] == [judged["id"]]
    # Signing never changes a hypothesis's status.
    after = _row(tenant_id, Hypothesis, id=uuid.UUID(judged["id"]))
    assert (after.human_status, after.status) == (before.human_status, before.status)

    # The snapshot hash covers the category: changing it breaks the verification.
    changed = _change(
        tenant_id,
        ContextSnapshot,
        snapshot.id,
        snapshot={**snapshot.snapshot, "root_cause": {**snapshot.snapshot["root_cause"], "category": "PEOPLE"}},
    )
    record = approver.get(f"/api/v1/decisions/{decision['id']}/record").json()
    assert record["verification"]["status"] == "INVALID"
    _change(tenant_id, ContextSnapshot, snapshot.id, **changed)

    # The fishbone shows it as named in the decision, with the FMEA prompt (no failure mode).
    grid = approver.get(_rca(case["id"]) + "/fishbone").json()
    named = next(c for c in grid["uncategorised"] if c["id"] == judged["id"])
    assert named["confirmed_in"]["id"] == decision["id"] and named["fmea_prompt"].startswith("Not in your FMEA")

    # Later hypothesis edits leave the signed decision row as it was.
    signed_row = {
        key: getattr(row, key) for key in ("root_cause_category", "root_cause_hypothesis_ids", "context_snapshot")
    }
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        db.query(Hypothesis).filter(Hypothesis.id == uuid.UUID(judged["id"])).update(
            {"statement": "Edited after signing", "cause_category": "METHOD"}
        )
        db.commit()
    again = _row(tenant_id, Decision, id=row.id)
    assert {key: getattr(again, key) for key in signed_row} == signed_row

    # Superseding re-categorises; the earlier decision keeps its own.
    second = approver2.post(
        sign,
        json=_body(
            brief,
            root_cause_category="NOT_DETERMINED",
            root_cause_reason="The bench test could not reproduce the drift",
            supersedes_decision_id=decision["id"],
            supersede_reason="Re-categorised after the bench test result",
        ),
    )
    assert second.status_code == 200, second.text
    assert second.json()["decision"]["root_cause_category"] == "NOT_DETERMINED"
    assert _row(tenant_id, Decision, id=row.id).root_cause_category == "MATERIAL"

    stranger, _ = other["investigator"]
    assert stranger.get(_rca(case["id"]) + "/fishbone").status_code == 404


def test_rca_switches_hide_routes_and_signing_fields(org, monkeypatch):
    investigator, _ = org["investigator"]
    approver, _ = org["approver"]
    case = _case(org, ready=False)
    monkeypatch.setenv("MDARIX_RCA_METHODS", "off")
    monkeypatch.setenv("MDARIX_RCA_INTELLIGENCE", "off")
    assert investigator.get(_rca(case["id"]) + "/fishbone").status_code == 404
    assert investigator.get(_rca(case["id"]) + "/five-whys").status_code == 404
    assert investigator.get("/api/v1/rca/pareto").status_code == 404
    assert investigator.get(_rca(case["id"]) + "/event-versions").status_code == 404
    assert investigator.get("/api/v1/session/context").json()["rca"] == {"methods": False, "intelligence": False}
    signed_case, brief = _approved(org)
    sign = _path(signed_case["id"]) + "/sign"
    refused = approver.post(sign, json=_body(brief))  # a category sent while off
    assert refused.status_code == 422 and "switched off" in refused.text
    plain = approver.post(sign, json=_body(brief, root_cause_category=None))
    assert plain.status_code == 200, plain.text  # drafts stay signable
    monkeypatch.setenv("MDARIX_RCA_METHODS", "on")
    monkeypatch.setenv("MDARIX_RCA_INTELLIGENCE", "on")
    assert investigator.get(_rca(case["id"]) + "/fishbone").status_code == 200
    assert investigator.get("/api/v1/rca/pareto").status_code == 200
    assert investigator.get("/api/v1/session/context").json()["rca"] == {"methods": True, "intelligence": True}
    # A decision signed without a category reads "Not categorised".
    record = approver.get(f"/api/v1/decisions/{plain.json()['decision']['id']}/record").json()
    assert record["decision"]["root_cause_category_label"] == "Not categorised"


def test_pareto_counts_confirmed_causes_of_the_organization(org, other):
    approver, _ = org["approver"]
    body = approver.get("/api/v1/rca/pareto").json()
    assert body["unit"] == "complaints" and body["bars"][-1]["label"] == "No confirmed cause yet"
    assert body["bars"][-1]["cumulative_share"] in (0.0, 100.0)
    assert sum(bar["count"] for bar in body["bars"]) == body["total"]
    assert approver.get("/api/v1/rca/pareto", params={"group_by": "colour"}).status_code == 422
    stranger, _ = other["investigator"]
    theirs = stranger.get("/api/v1/rca/pareto").json()
    mine = {item["id"] for bar in body["bars"] for item in bar["complaints"]}
    assert not mine & {item["id"] for bar in theirs["bars"] for item in bar["complaints"]}


# ------------------------------------------------------------------------------------- version at the event date


def test_the_version_at_the_event_date(org, other):
    tenant_id = org["tenant_id"]
    investigator, _ = org["investigator"]
    case = _case(org, ready=False)
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        product = db.query(Product).filter(Product.id == uuid.UUID(case["product_id"])).one()
        late = ProductVersion(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            product_id=product.id,
            version_identifier=f"Rev C {uuid.uuid4().hex[:4]}",
            release_timestamp=now,
            created_at=now,
            updated_at=now,
        )
        db.add(late)
        db.flush()
        rows = []
        for named, event, awareness in (
            (None, now - timedelta(days=30), None),
            (late.id, now - timedelta(days=30), None),
            (None, None, now - timedelta(days=20)),
        ):
            complaint = Complaint(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                complaint_identifier=f"RCA-EV-{uuid.uuid4().hex[:8]}",
                product_id=product.id,
                product_version_id=named,
                event_timestamp=event,
                awareness_timestamp=awareness,
                description="Pressure alarm",
                created_at=now,
                updated_at=now,
            )
            db.add(complaint)
            db.flush()
            db.add(
                InvestigationComplaint(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    investigation_id=uuid.UUID(case["id"]),
                    complaint_id=complaint.id,
                    created_at=now,
                )
            )
            rows.append(str(complaint.id))
        db.commit()
    body = investigator.get(_rca(case["id"]) + "/event-versions").json()
    items = {item["complaint"]["id"]: item for item in body["items"]}
    unknown, flagged, awareness = (items[key] for key in rows)
    assert unknown["version"] is None and unknown["version_label"] == "Version unknown"  # nothing borrowed
    assert flagged["version"]["id"] and flagged["flags"][0]["code"] == "RELEASED_AFTER_EVENT"
    assert awareness["anchor_source"] == "AWARENESS"
    stranger, _ = other["investigator"]
    assert stranger.get(_rca(case["id"]) + "/event-versions").status_code == 404
