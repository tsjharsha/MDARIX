"""The distributor and authorised-representative preview (T-G37P) on a free trial's sample data: the status preview
lists only the sample distributor's complaints, with no patient data, and shows the released closing note once the
complaint is closed (TA-37P.1); the authorised representative's preview shows no PulseWatch 410 complaint and both
panels list the expected sample complaints (TA-37P.2); nothing on the pages can be sent or changed, and every opening
is in the audit trail (TA-37P.3); a pilot gets 404; another organization reads nothing; after sample removal the pages
say there is nothing to preview."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.complaint_disposition.service import recurring
from backend.app.db.models.complaint_disposition import ComplaintDisposition
from backend.app.db.models.foundation import AuditEvent, Complaint, Product
from backend.app.db.models.market_assessment import ComplaintMarketAssessment
from backend.app.db.session import RuntimeSessionLocal, SessionLocal, runtime_role_active
from backend.app.db.tenant_scope import bind_tenant
from tests.test_complaint_disposition_api import _acknowledge, _sign
from tests.test_free_trial import _approved_trial_client

pytestmark = pytest.mark.db

PREVIEW = "/api/v1/trial/preview"
PAGES = ("intake", "distributor", "authorised-representative")
BANNER = (
    "Preview with sample data. In a pilot, your distributor or authorised representative signs in separately, with "
    "MFA and an access end date (from MDARIX 1.0.1)."
)
PRRC = "The authorised representative is not your PRRC. It has its own PRRC (MDR Art. 11 and 15(6))."
PULSEWATCH = {"SAMPLE-RT-02", "SAMPLE-RT-03", "SAMPLE-RV-01", "SAMPLE-RV-09"}
# Words that would carry patient or reporter data, or a conclusion, into the distributor's view.
PRIVATE = ("patient", "injury", "death", "description", "conclusion", "root_cause", "attribution")


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        ids = {
            row.complaint_identifier: str(row.id)
            for row in db.query(Complaint.complaint_identifier, Complaint.id).filter(Complaint.tenant_id == tenant_id)
        }
    try:
        yield {"user": user, "tenant_id": tenant_id, "ids": ids}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:party-preview-cleanup")


def _page(client, page: str) -> dict:
    response = client.get(f"{PREVIEW}/{page}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["banner"] == BANNER and body["read_only"] is True
    return body


def _own_distributor_complaint(tenant_id: uuid.UUID) -> None:
    """A complaint another distributor filed, from the organization's own upload: not the sample distributor's. It
    names no product, so no trend moves."""
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        now = datetime.now(timezone.utc)
        db.add(
            Complaint(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                complaint_identifier="OWN-DIST-0001",
                complaint_timestamp=now - timedelta(days=1),
                description="Filed by another distributor; the patient was unharmed.",
                reporter_type="Distributor",
                patient_involved=True,
                country="Germany",
                status="open",
                source_system="TRIAL_UPLOAD",
                source_identifier="OWN-DIST-0001",
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()


def test_the_intake_preview_is_filled_with_the_sample_submission_and_has_no_names(trial):
    body = _page(trial["user"], "intake")
    assert body["page"] == "INTAKE" and body["party"] == "Sample Distributor Europe (Sample)"
    submission = body["submission"]
    assert submission["reference"] == "DIST-REF-2231" and submission["becomes"] == "SAMPLE-RT-01"
    assert submission["product"] == "VentraLink 250 Respiratory Controller (Sample) Rev B"
    assert submission["lot"] == "SAMPLE-VENTRA-250-LOT-004"
    # The distributor knew on the day of the event, a month before it filed with its service report.
    known = datetime.fromisoformat(submission["first_knowledge"]).date()
    assert known <= (datetime.now(timezone.utc) - timedelta(days=30)).date()
    assert "re-seat the filter" in submission["words"]
    assert set(submission) == {"reference", "product", "lot", "first_knowledge", "words", "becomes"}


def test_ta_37p_1_the_status_preview_lists_only_the_sample_distributors_complaints(trial):
    user, tenant_id = trial["user"], trial["tenant_id"]
    _own_distributor_complaint(tenant_id)
    body = _page(user, "distributor")
    assert body["page"] == "DISTRIBUTOR_STATUS" and body["party"] == "Sample Distributor Europe (Sample)"
    assert [item["complaint"] for item in body["items"]] == ["SAMPLE-RT-01"]
    (item,) = body["items"]
    assert set(item) == {"reference", "complaint", "status", "status_label", "received", "last_change", "closing_note"}
    assert item["reference"] == "DIST-REF-2231"
    # Not yet closed: received, and no closing note.
    assert item["status"] == "RECEIVED" and item["status_label"] == "Received" and item["closing_note"] is None
    assert item["received"] and item["last_change"]
    assert [status["label"] for status in body["statuses"]] == ["Received", "Under assessment", "Closed"]
    shown = json.dumps(body["items"]).lower()
    assert not [word for word in PRIVATE if word in shown]

    # Closed at service level (chapter 1): the released closing note shows, still with no patient data.
    _acknowledge(user)
    signed = _sign(user, trial["ids"]["SAMPLE-RT-01"], "SERVICE_LEVEL")
    assert signed.status_code == 200, signed.text
    (item,) = _page(user, "distributor")["items"]
    assert item["status"] == "CLOSED" and item["status_label"] == "Closed"
    assert item["closing_note"].startswith("Closed at service level.")
    assert item["last_change"] == datetime.now(timezone.utc).date().isoformat()
    shown = json.dumps(item).lower()
    assert not [word for word in PRIVATE if word in shown]


def test_ta_37p_2_the_authorised_representative_sees_its_products_only_with_both_panels(trial):
    user, tenant_id = trial["user"], trial["tenant_id"]
    # A second service-level close on PulseWatch 410 makes a recurring matter there (with the sample's RT-03): it is
    # not a represented product, so the panel stays without it.
    _acknowledge(user)
    signed = _sign(user, trial["ids"]["SAMPLE-RT-02"], "SERVICE_LEVEL")
    assert signed.status_code == 200, signed.text
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        everywhere = recurring(db, tenant_id, datetime.now(timezone.utc).date())
        descriptions = [
            row.description for row in db.query(Complaint.description).filter(Complaint.tenant_id == tenant_id)
        ]
    assert [item["product_name"] for item in everywhere] == ["PulseWatch 410 Patient Monitor (Sample)"]

    body = _page(user, "authorised-representative")
    assert body["party"] == "Sample EU Authorised Representative (Sample)" and body["prrc_note"] == PRRC
    assert body["products"] == [
        "OrbitCare 300 Infusion Pump (Sample)",
        "VentraLink 250 Respiratory Controller (Sample)",
    ]
    identifiers = {item["identifier"] for item in body["complaints"]}
    assert not identifiers & PULSEWATCH
    assert {item["product"] for item in body["complaints"]} == set(body["products"])
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        expected = {
            row.complaint_identifier
            for row in db.query(Complaint.complaint_identifier)
            .join(Product, (Product.tenant_id == Complaint.tenant_id) & (Product.id == Complaint.product_id))
            .filter(
                Complaint.tenant_id == tenant_id,
                Product.product_identifier.in_(["SAMPLE-ORBIT-300", "SAMPLE-VENTRA-250"]),
            )
        }
    assert identifiers == expected
    # Every complaint with its state and dates and its EU/NI assessment; RV-07's is signed reportable.
    rows = {item["identifier"]: item for item in body["complaints"]}
    assert rows["SAMPLE-RV-07"]["eu_assessment"]["state"] == "SIGNED"
    assert rows["SAMPLE-RV-07"]["eu_assessment"]["label"] == "Signed: reportable"
    assert rows["SAMPLE-RV-02"]["eu_assessment"]["state"] == "NOT_STARTED"  # Germany, not assessed yet
    assert rows["SAMPLE-RV-06"]["eu_assessment"]["state"] == "NONE"  # a US event
    assert rows["SAMPLE-RV-03"]["state"] == "Closed" and rows["SAMPLE-RV-07"]["state"] == "Under assessment"
    assert all(item["received"] and item["last_change"] for item in body["complaints"])
    assert set(rows["SAMPLE-RV-06"]) == {
        "id",
        "ref",
        "identifier",
        "product",
        "country",
        "status",
        "state",
        "received",
        "last_change",
        "eu_assessment",
    }

    # The high-risk panel: injury (serious, or a patient involved with the outcome unknown) or a reportable conclusion.
    risky = {item["identifier"]: item for item in body["high_risk"]}
    assert set(risky) == {"SAMPLE-RV-02", "SAMPLE-RV-06", "SAMPLE-RV-07", "SAMPLE-RV-08"}
    assert risky["SAMPLE-RV-06"]["codes"] == ["INJURY"] and risky["SAMPLE-RV-07"]["codes"] == ["REPORTABLE"]
    assert risky["SAMPLE-RV-08"]["codes"] == ["INJURY"]
    assert "EU and Northern Ireland (EU MDR) concluded reportable" in risky["SAMPLE-RV-07"]["reasons"]

    # The recurring-issues panel: the OrbitCare pressure-alarm signal; no VentraLink trend; no PulseWatch matter.
    signals = body["recurring"]["signals"]
    assert signals and {item["product"] for item in signals} == {"OrbitCare 300 Infusion Pump (Sample)"}
    assert any("pressure alarm" in item["title"].lower() for item in signals)
    assert body["recurring"]["service_level"] == []
    # No patient or reporter data: no complaint's own words reach the page.
    shown = json.dumps(body)
    assert not [text for text in descriptions if text and text in shown]


def test_ta_37p_3_nothing_can_be_sent_or_changed_and_every_opening_is_audited(trial):
    user, tenant_id = trial["user"], trial["tenant_id"]

    def counts() -> tuple[int, int, int]:
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            return (
                db.query(Complaint).filter(Complaint.tenant_id == tenant_id).count(),
                db.query(ComplaintDisposition).filter(ComplaintDisposition.tenant_id == tenant_id).count(),
                db.query(ComplaintMarketAssessment).filter(ComplaintMarketAssessment.tenant_id == tenant_id).count(),
            )

    def opened() -> list[str]:
        with SessionLocal() as db:
            return [
                row.details["page"]
                for row in db.query(AuditEvent).filter(
                    AuditEvent.tenant_id == tenant_id, AuditEvent.action == "PARTY_VIEW_PREVIEW_OPENED"
                )
            ]

    before, seen = counts(), opened()
    for page in PAGES:
        for method in ("post", "put", "patch", "delete"):
            assert getattr(user, method)(f"{PREVIEW}/{page}").status_code == 405
        _page(user, page)
    assert counts() == before
    added = opened()
    assert len(added) == len(seen) + 3
    assert {"INTAKE", "DISTRIBUTOR_STATUS", "AUTHORISED_REPRESENTATIVE"} <= set(added)
    assert user.get(f"{PREVIEW}/unknown").status_code == 404


def test_the_preview_is_hidden_outside_a_trial():
    from tests.test_reporting_capa_api import _client, _organization

    pilot = _client(_organization("PVW"), "LEADER")
    for page in PAGES:
        refused = pilot.get(f"{PREVIEW}/{page}")
        assert refused.status_code == 404 and refused.json()["detail"]["code"] == "NOT_A_TRIAL_WORKSPACE"


def test_another_organization_reads_nothing_and_sample_removal_leaves_nothing_to_preview(trial):
    from backend.app.party_views import preview, service

    user, tenant_id = trial["user"], trial["tenant_id"]
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        products = [row.id for row in db.query(Product.id).filter(Product.tenant_id == tenant_id)]
        assert service.portfolio(db, uuid.uuid4(), products) == {"complaints": [], "high_risk": []}
        assert service.recurring_issues(db, uuid.uuid4(), products)["signals"] == []
    if runtime_role_active():
        runtime = RuntimeSessionLocal()
        try:
            bind_tenant(runtime, uuid.uuid4())
            assert preview.authorised_representative(runtime, tenant_id)["complaints"] == []
            assert preview.distributor_status(runtime, tenant_id)["items"] == []
        finally:
            runtime.close()

    removed = user.post("/api/v1/trial/sample-data/removal", json={"confirm": True})
    assert removed.status_code == 200, removed.text
    for page in PAGES:
        body = _page(user, page)
        assert body["empty"] == "The sample data was removed, so there is nothing to preview."
