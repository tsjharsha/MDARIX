"""Getting started › Automatic insights: the headline numbers, the monthly trend, the complaints for filtering on screen
and the questions to ask next, each answered from the workspace's own records by rules (backend/app/trial/imports.py
insights, backend/app/trial/insight_questions.py).

Each workspace here is a fresh organization: the sample dataset seeded at a fixed day (so its months are known), or
complaints written as a trial upload without the optional columns. Every workspace is purged afterwards.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.customer_lifecycle import build_customer_tenant
from backend.app.db.models.foundation import (
    Change,
    Complaint,
    Component,
    ComponentSupplier,
    Investigation,
    LotBatch,
    Product,
    ProductComponent,
    ProductVersion,
    RealityRelationship,
    Supplier,
    Unknown,
)
from backend.app.db.models.stage3 import SupplierEvidenceRequest
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from backend.app.trial.imports import UPLOAD_SOURCE, insights
from backend.app.trial.retention import purge_trial
from backend.app.trial.sample_data import seed_lot_quantities, seed_sample_workspace, seed_story_examples

# The sample's complaints are dated back from this day: April to October 2026, the last three months August to October.
NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
# The sample's supplier change, as "What changed" shows it (sample_data.py links it to the OrbitCare pressure sensor).
CHANGE_FACT = (
    "Change SAMPLE-CHG-014 (Supplier change, 28 Jul 2026): OrbitCare 300 Rev B: pressure sensor sourced from NovaSense "
    "Components instead of Precision Sensors Ltd. Incoming inspection sampling reduced from 32 to 13 units per lot."
)
NOTE = "Counts and patterns from your records. They point to where to look; people decide what they mean."
LEGACY_FIELDS = (
    "scope",
    "total_complaints",
    "by_product",
    "by_version",
    "by_lot",
    "by_month",
    "findings",
    "suggested_questions",
    "note",
)


def _tenant(db, label: str):
    customer, tenant = build_customer_tenant(
        db=db, tenant_key=f"INSIGHTS_{label}_{uuid.uuid4().hex[:8].upper()}", name=label, status="ACTIVE", now=NOW
    )
    db.add(customer)
    db.add(tenant)
    db.flush()
    return tenant


@pytest.fixture
def workspaces():
    """Fresh organizations made by the test, purged afterwards."""
    made = []
    yield made
    for tenant_id in made:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:trial-insights-cleanup")


def _sample_workspace(made) -> uuid.UUID:
    with SessionLocal() as db:
        tenant = _tenant(db, "SAMPLE")
        seed_sample_workspace(db, tenant.id, NOW)
        seed_story_examples(db, tenant.id, NOW)
        seed_lot_quantities(db, tenant.id)
        db.commit()
        made.append(tenant.id)
        return tenant.id


def _insights(tenant_id) -> dict:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        return insights(db, tenant_id)


def _question(result: dict, key: str) -> dict:
    return next(item for item in result["questions"] if item["key"] == key)


def _stamp(when: datetime) -> dict:
    return {
        "source_system": UPLOAD_SOURCE,
        "source_timestamp": when,
        "effective_timestamp": when,
        "recorded_timestamp": when,
        "ingestion_timestamp": NOW,
        "created_at": when,
        "updated_at": when,
    }


def _uploaded_workspace(made, *, linked_records: bool = False) -> uuid.UUID:
    """A trial's own upload as a bare complaints export makes it: one product, two versions, two lots without a
    quantity or site, and complaints with no problem code, country, reporter type or harm and malfunction fields.
    Complaints rise from one a month (May to July 2026) to three a month (August to October)."""
    with SessionLocal() as db:
        tenant = _tenant(db, "UPLOAD")
        product = Product(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            product_identifier="PUMP-200",
            name="AquaFlow 200 Infusion Pump",
            source_identifier="PUMP-200",
            **_stamp(NOW - timedelta(days=300)),
        )
        db.add(product)
        db.flush()
        versions = []
        for revision in ("Rev C", "Rev D"):
            version = ProductVersion(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                product_id=product.id,
                version_identifier=revision,
                source_identifier=f"PUMP-200:{revision}",
                **_stamp(NOW - timedelta(days=300)),
            )
            db.add(version)
            versions.append(version)
        db.flush()
        lots = []
        for number, version in (("L24-0815", versions[1]), ("L24-0902", versions[1]), ("L23-1101", versions[0])):
            lot = LotBatch(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                lot_identifier=number,
                product_version_id=version.id,
                source_identifier=number,
                **_stamp(NOW - timedelta(days=200)),
            )
            db.add(lot)
            lots.append(lot)
        db.flush()
        days = [
            # May, June, July: one a month on Rev C.
            (150, 0, 2),
            (120, 0, 2),
            (90, 0, 2),
            # August to October: three a month on Rev D, from the two new lots.
            *((d, 1, i % 2) for i, d in enumerate((70, 66, 62, 40, 36, 32, 14, 10, 6))),
        ]
        for index, (days_ago, version_index, lot_index) in enumerate(days, 1):
            when = NOW - timedelta(days=days_ago)
            db.add(
                Complaint(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    complaint_identifier=f"UP-{index:03d}",
                    product_id=product.id,
                    product_version_id=versions[version_index].id,
                    lot_batch_id=lots[lot_index].id,
                    complaint_timestamp=when,
                    description="Pump alarm during infusion.",
                    source_identifier=f"UP-{index:03d}",
                    **_stamp(when),
                )
            )
        if linked_records:
            supplier = Supplier(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                supplier_identifier="SUP-9",
                name="Valve Works",
                source_identifier="SUP-9",
                **_stamp(NOW),
            )
            component = Component(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                component_identifier="VALVE-1",
                name="Check valve",
                source_identifier="VALVE-1",
                **_stamp(NOW),
            )
            change = Change(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                change_identifier="CHG-77",
                change_type="Design change",
                description="Rev D: check valve moved to a new housing.",
                event_timestamp=NOW - timedelta(days=80),
                source_identifier="CHG-77",
                **_stamp(NOW - timedelta(days=80)),
            )
            db.add_all([supplier, component, change])
            db.flush()
            db.add_all(
                [
                    ComponentSupplier(
                        id=uuid.uuid4(),
                        tenant_id=tenant.id,
                        component_id=component.id,
                        supplier_id=supplier.id,
                        effective_timestamp=NOW - timedelta(days=80),
                        created_at=NOW,
                    ),
                    ProductComponent(
                        id=uuid.uuid4(),
                        tenant_id=tenant.id,
                        product_version_id=versions[1].id,
                        component_id=component.id,
                        relationship_status="active",
                        created_at=NOW,
                    ),
                    RealityRelationship(
                        id=uuid.uuid4(),
                        tenant_id=tenant.id,
                        source_entity_type="Change",
                        source_entity_id=change.id,
                        target_entity_type="Component",
                        target_entity_id=component.id,
                        relationship_type="AFFECTS",
                        created_at=NOW,
                    ),
                ]
            )
        db.commit()
        made.append(tenant.id)
        return tenant.id


def test_the_sample_keeps_every_earlier_field_and_adds_the_headline_trend_and_records(workspaces):
    result = _insights(_sample_workspace(workspaces))
    for field in LEGACY_FIELDS:
        assert field in result
    assert result["scope"] == "sample data" and result["total_complaints"] == 38 and result["note"] == NOTE
    assert result["by_version"][0]["version"] == "Rev B" and result["by_version"][0]["complaints"] == 17
    # The finding names the product as people read it, not its identifier.
    assert "45% of complaints (17 of 38) concern OrbitCare 300 Infusion Pump (Sample) Rev B." in result["findings"]
    assert "Complaints in the last 3 months average 8.7 per month, up from 3.0 before." in result["findings"]

    headline = result["headline"]
    assert headline["total"] == 38 and headline["harm"] == 3 and headline["malfunction"] == 6
    assert headline["top_version"] == {
        "label": "OrbitCare 300 Infusion Pump (Sample) Rev B",
        "version": "Rev B",
        "complaints": 17,
        "share": 45,
    }
    assert headline["rate"] == {"recent": 8.7, "earlier": 3.0, "direction": "up"}

    trend = result["trend"]
    assert [item["month"] for item in trend["months"]] == [f"2026-{m:02d}" for m in range(4, 11)]
    assert sum(item["complaints"] for item in trend["months"]) == 38
    assert trend["recent_months"] == 3 and trend["recent_average"] == 8.7 and trend["earlier_average"] == 3.0

    records = result["records"]
    assert len(records) == 38
    assert set(records[0]) == {
        "id",
        "ref",
        "version",
        "lot",
        "code",
        "country",
        "month",
        "harm",
        "malfunction",
        "status",
    }
    assert sum(row["harm"] for row in records) == 3 and sum(row["malfunction"] for row in records) == 6
    assert {row["version"] for row in records} <= set(result["version_labels"])
    assert "OrbitCare 300 Infusion Pump (Sample) Rev B" in result["version_labels"].values()

    # The questions read as people do: product names, and lots in the plural only when there are two.
    assert result["suggested_questions"] == [item["question"] for item in result["questions"]]
    assert result["suggested_questions"] == [
        "What changed in OrbitCare 300 Infusion Pump (Sample) Rev B?",
        "What do lots SAMPLE-ORBIT-300-LOT-003 and SAMPLE-ORBIT-300-LOT-004 have in common?",
        "Is the rise real, or just more devices in use?",
        "Which complaints report harm or a malfunction?",
        "Which problem codes are rising?",
        "Where are complaints coming from?",
        "What evidence is still missing?",
    ]
    for item in result["questions"]:
        answer = item["answer"]
        assert answer["summary"] and answer["basis"]
        assert "caused" not in answer["summary"] and "because" not in answer["summary"]


def test_every_sample_question_is_answered_from_the_records(workspaces):
    result = _insights(_sample_workspace(workspaces))

    version = _question(result, "version")["answer"]
    assert version["summary"] == (
        "OrbitCare 300 Infusion Pump (Sample): Rev B has 17 complaints, 5.7 per month since its first complaint in "
        "Aug 2026; Rev A has 6 complaints, 0.9 per month since its first complaint in Apr 2026."
    )
    assert [row[0] for row in version["table"]["rows"]] == ["Rev B", "Rev A"]
    assert version["table"]["rows"][0][4] == "SAMPLE-ORBIT-300-LOT-003 (9), SAMPLE-ORBIT-300-LOT-004 (6)"
    assert any("Pressure Sensor (Sample): NovaSense Components (Sample)" in fact for fact in version["facts"])
    assert version["ids_total"] == 17
    # The sample's supplier change names the OrbitCare pressure sensor as the component it affects, so it is shown.
    assert version["facts"][-1] == CHANGE_FACT
    assert not any("change record" in line for line in version["missing"])
    assert any("Rev A has no components recorded" in line for line in version["missing"])

    lots = _question(result, "lots")["answer"]
    assert lots["summary"] == (
        "Lots SAMPLE-ORBIT-300-LOT-003 and SAMPLE-ORBIT-300-LOT-004 are both OrbitCare 300 Infusion Pump (Sample) "
        "Rev B lots made at Assembly Site 1 (Sample); together they have 15 of 38 complaints."
    )
    assert [row[5] for row in lots["table"]["rows"]] == ["6.0", "4.0"]  # per 100 units: 9 and 6 of 150
    assert any("do not link a lot to the component lots" in line for line in lots["missing"])

    rise = _question(result, "rise")["answer"]
    assert rise["summary"].startswith("Complaints rose from 3.0 to 8.7 per month. Per 1,000 units released: ")
    assert "OrbitCare 300 Infusion Pump (Sample) Rev B 37.8 (17 complaints from 450 units)" in rise["summary"]
    assert rise["missing"] == []

    harm = _question(result, "harm")["answer"]
    assert harm["summary"] == "3 complaints report harm (3 serious injuries) and 6 complaints report a malfunction."
    assert harm["ids_total"] == 6 and harm["missing"] == [
        "32 complaints leave death, serious injury and malfunction empty."
    ]

    # OrbitCare's sample complaints carry PRESSURE_ALARM, the story's rising problem.
    codes = _question(result, "codes")["answer"]
    assert codes["summary"] == (
        "1 problem code rose in the last 3 months (Aug 2026 to Oct 2026): PRESSURE_ALARM from 1.0 to 4.7 per month."
    )
    assert codes["missing"] == ["11 complaints have no problem code and are not counted here."]

    origin = _question(result, "origin")["answer"]
    assert origin["summary"] == "US has the most complaints (8 of 10 with a country; 3 countries in all)."
    assert origin["bars"][0] == {"label": "US", "count": 8}
    assert origin["missing"] == ["28 complaints have no country.", "No complaint records a reporter type."]

    evidence = _question(result, "evidence")["answer"]
    assert evidence["summary"].startswith(
        "No evidence request or open question is recorded on the 1 open investigation"
    )
    assert len(evidence["cases"]) == 1


def test_open_requests_and_questions_are_listed_for_their_own_workspace_only(workspaces):
    mine, other = _sample_workspace(workspaces), _sample_workspace(workspaces)
    with SessionLocal() as db:
        bind_tenant(db, other)
        case = db.query(Investigation).filter(Investigation.tenant_id == other).one()
        db.add_all(
            [
                SupplierEvidenceRequest(
                    id=uuid.uuid4(),
                    tenant_id=other,
                    investigation_id=case.id,
                    requested_by="quality.lead@sample.invalid",
                    title="Incoming inspection records for lot 003",
                    requested_items={"items": ["Inspection records"]},
                    status="OPEN",
                    request_kind="INTERNAL",
                    recipient_role="Quality engineer",
                    created_at=NOW,
                    updated_at=NOW,
                ),
                # Finished requests and resolved questions no longer wait for anything.
                SupplierEvidenceRequest(
                    id=uuid.uuid4(),
                    tenant_id=other,
                    investigation_id=case.id,
                    requested_by="quality.lead@sample.invalid",
                    title="Sensor drift data",
                    requested_items={"items": ["Drift data"]},
                    status="REVIEWED",
                    recipient="supplier@example.invalid",
                    created_at=NOW,
                    updated_at=NOW,
                ),
                Unknown(
                    id=uuid.uuid4(),
                    tenant_id=other,
                    investigation_id=case.id,
                    description="Do NovaSense sensors drift at high pressure?",
                    evidence_needed="Bench test of 20 NovaSense sensors",
                    status="open",
                    created_at=NOW,
                    updated_at=NOW,
                ),
                Unknown(
                    id=uuid.uuid4(),
                    tenant_id=other,
                    investigation_id=case.id,
                    description="Was the inspection sampling reduced?",
                    status="resolved",
                    created_at=NOW,
                    updated_at=NOW,
                ),
            ]
        )
        db.commit()

    theirs = _question(_insights(other), "evidence")["answer"]
    assert theirs["summary"].startswith("1 open investigation (")
    assert theirs["summary"].endswith("waits on 1 evidence request and 1 open question.")
    assert [row[1:3] for row in theirs["table"]["rows"]] == [
        ["Evidence request", "Incoming inspection records for lot 003"],
        ["Open question", "Bench test of 20 NovaSense sensors"],
    ]
    assert theirs["missing"] == []

    # The other organization's requests and questions never reach this one, nor its complaints.
    result = _insights(mine)
    ours = _question(result, "evidence")["answer"]
    assert ours["table"] is None and ours["summary"].startswith("No evidence request or open question")
    assert result["total_complaints"] == 38 and len(result["records"]) == 38
    with SessionLocal() as db:
        bind_tenant(db, mine)
        own_ids = {row.business_id for row in db.query(Complaint).filter(Complaint.tenant_id == mine)}
    assert {row["id"] for row in result["records"]} == own_ids
    assert {case["id"] for case in ours["cases"]} != {case["id"] for case in theirs["cases"]}


def test_an_upload_without_the_optional_columns_says_what_is_missing(workspaces):
    _sample_workspace(workspaces)  # another organization's sample stays out of this one's answers
    result = _insights(_uploaded_workspace(workspaces))
    assert result["scope"] == "your data" and result["total_complaints"] == 12 and len(result["records"]) == 12
    assert result["headline"]["harm"] == 0 and result["headline"]["malfunction"] == 0
    assert result["headline"]["rate"] == {"recent": 3.0, "earlier": 1.0, "direction": "up"}
    assert {row["code"] for row in result["records"]} == {None} and {row["country"] for row in result["records"]} == {
        None
    }
    # No harm fields, problem codes, countries or reporter types: those questions are not asked.
    assert [item["key"] for item in result["questions"]] == ["version", "lots", "rise", "evidence"]

    version = _question(result, "version")
    assert version["question"] == "What changed in AquaFlow 200 Infusion Pump Rev D?"
    assert version["answer"]["missing"] == [
        "Rev D has no components recorded.",
        "No change record is linked to AquaFlow 200 Infusion Pump or its components.",
    ]
    assert version["answer"]["table"]["rows"][0][5] == "—"  # no problem codes

    lots = _question(result, "lots")["answer"]
    assert lots["summary"] == (
        "Lots L24-0815 and L24-0902 are both AquaFlow 200 Infusion Pump Rev D lots; together they have 9 of 12 "
        "complaints."
    )
    assert "Lot L24-0815 has no manufacturing site recorded." in lots["missing"]
    assert "Lot L24-0815 has no quantity, so complaints per 100 units cannot be shown." in lots["missing"]
    assert [row[5] for row in lots["table"]["rows"]] == ["—", "—"]

    rise = _question(result, "rise")["answer"]
    assert rise["summary"] == (
        "Complaints rose from 1.0 to 3.0 per month, but lot quantities are missing, so complaints per unit cannot be "
        "shown."
    )
    assert "3 lots with complaints have no quantity (L23-1101, L24-0815 and L24-0902)." in rise["missing"]

    evidence = _question(result, "evidence")["answer"]
    assert evidence["summary"] == "No investigation is open on these products, so no evidence is being waited for."


def test_linked_components_and_changes_are_shown_for_the_version(workspaces):
    result = _insights(_uploaded_workspace(workspaces, linked_records=True))
    version = _question(result, "version")["answer"]
    assert "Rev D lists 1 component: Check valve: Valve Works since 28 Jul 2026." in version["facts"]
    assert any(
        fact.startswith("Change CHG-77 (Design change, 28 Jul 2026): Rev D: check valve") for fact in version["facts"]
    )
    assert "Rev C has no components recorded, so its parts cannot be compared." in version["missing"]
    assert not any("No change record" in line for line in version["missing"])


def test_a_workspace_without_complaints_has_no_questions(workspaces):
    with SessionLocal() as db:
        tenant = _tenant(db, "EMPTY")
        db.commit()
        workspaces.append(tenant.id)
    result = _insights(tenant.id)
    assert result["total_complaints"] == 0 and result["records"] == [] and result["questions"] == []
    assert result["suggested_questions"] == [] and result["headline"]["top_version"] is None
    assert result["headline"]["rate"] is None and result["trend"]["months"] == []
