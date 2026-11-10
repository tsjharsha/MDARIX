"""The routine sample complaints of a free trial, their proposed classifications and the sample parties (T-SAM for the
disposition release, the trial plan's "0.10.52").

| ID | Product | What happened | Shows |
|---|---|---|---|
| SAMPLE-RT-01 | VentraLink 250 Rev B | Low-flow alarm after a filter change, re-seated on the phone; filed late by Sample Distributor Europe | The routine path |
| SAMPLE-RT-02 | PulseWatch 410 Rev A | SpO2 cable frayed at the connector; replaced; no patient | A second service-level close |
| SAMPLE-RT-03 | PulseWatch 410 Rev A | The same cable wear, three weeks earlier; signed by the sample author | With RT-02: a recurring matter |
| SAMPLE-RT-04 | OrbitCare 300 Rev B, lot 4 | Intermittent pressure alarm; nurse restarted the pump; no harm | A known issue (SAMPLE-INV-001) |
| SAMPLE-RT-05 | VentraLink 250 Rev B | Shut down on battery during transport although the indicator showed full; reported a month later | NEW_FAILURE_MODE, on the watch |

Every complaint carries a proposed classification (use environment and user type) for a person to confirm when the
disposition is signed; RT-02's source value "Step-down unit" is not on the list, so it stays Unknown with the source
value shown. The story complaints RV-01..09 carry proposed values too. RT-03's disposition (service level,
device-related) is signed by the sample author, who holds the practice training acknowledgements it relies on.

Every row is marked ``MDARIX_SAMPLE`` (sample removal takes it and everything done with it). Idempotent; flushes but
never commits (the caller owns the transaction).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.app.trial.sample_data import SAMPLE_SOURCE

logger = logging.getLogger("mdarix.trial.sample_dispositions")

# The sample parties (fixed constants, read by the distributor and authorised-representative preview, T-G37P).
SAMPLE_DISTRIBUTOR = "Sample Distributor Europe (Sample)"
SAMPLE_AUTHORISED_REPRESENTATIVE = "Sample EU Authorised Representative (Sample)"
# What the sample distributor filed: complaint -> its own reference. Fixed like the parties (no table holds a submitter
# until G37), so a running trial needs no refresh; RT-01's reporter type is Distributor.
DISTRIBUTOR_SUBMISSIONS = {"SAMPLE-RT-01": "DIST-REF-2231"}
# RT-01 as the distributor typed it into the intake form (the intake preview; the form asks for no names).
DISTRIBUTOR_WORDS = {
    "SAMPLE-RT-01": "The respiratory therapist called our service desk: low-flow alarm right after a filter change. We "
    "told them to re-seat the filter and the alarm cleared. No patient harm.",
}
# The closing note the sample released to the distributor, shown once the complaint is closed.
RELEASED_CLOSING_NOTES = {
    "SAMPLE-RT-01": "Closed at service level. The low-flow alarm followed a filter change; re-seating the filter "
    "cleared it and the controller works as specified. No further action is needed. Thank you for your report.",
}
# The products the sample authorised representative represents (not PulseWatch 410).
AUTHORISED_REPRESENTATIVE_PRODUCTS = ("SAMPLE-ORBIT-300", "SAMPLE-VENTRA-250")
MARKER = "SAMPLE-RT-01"
HCP = "Healthcare professional"

# identifier, product, version, lot number, days since awareness, description, fields, (use environment, user type) as
# the source gives them.
ROUTINE_COMPLAINTS = [
    (
        "SAMPLE-RT-01",
        "SAMPLE-VENTRA-250",
        "Rev B",
        4,
        2,
        "Low-flow alarm after a filter change. The respiratory therapist called the distributor's service desk, was told "
        "to re-seat the filter, and the alarm cleared. No patient harm. Filed by Sample Distributor Europe with its "
        "monthly service report.",
        {
            "problem_code": None,
            "country": "Germany",
            "reporter_type": "Distributor",
            "patient_involved": True,
            "serious_injury": False,
            "death": False,
            "malfunction": False,
        },
        ("Intensive care unit", HCP),
    ),
    (
        "SAMPLE-RT-02",
        "SAMPLE-PULSE-410",
        "Rev A",
        2,
        3,
        "SpO2 sensor cable frayed at the connector. The field engineer replaced the cable and the monitor tested OK. "
        "No patient was connected.",
        {"problem_code": "CABLE_WEAR", "country": "US", "patient_involved": False, "malfunction": False},
        ("Step-down unit", HCP),
    ),
    (
        "SAMPLE-RT-03",
        "SAMPLE-PULSE-410",
        "Rev A",
        1,
        21,
        "SpO2 sensor cable worn through at the connector. The field engineer replaced the cable and the monitor tested "
        "OK. No patient was connected.",
        {"problem_code": "CABLE_WEAR", "country": "US", "patient_involved": False, "malfunction": False},
        ("Hospital ward", HCP),
    ),
    (
        "SAMPLE-RT-04",
        "SAMPLE-ORBIT-300",
        "Rev B",
        4,
        4,
        "Intermittent pressure alarm during an infusion. The nurse restarted the pump and the infusion completed. No "
        "harm.",
        {
            "problem_code": "PRESSURE_ALARM",
            "country": "US",
            "patient_involved": True,
            "serious_injury": False,
            "death": False,
            "malfunction": False,
        },
        ("Hospital ward", HCP),
    ),
    (
        "SAMPLE-RT-05",
        "SAMPLE-VENTRA-250",
        "Rev B",
        4,
        1,
        "The controller switched off on battery during a patient transport although the battery indicator showed full. "
        "Staff ventilated the patient manually. No harm. The hospital reported it a month later, after its incident "
        "review.",
        {
            "problem_code": "BATTERY_SHUTDOWN",
            "country": "Germany",
            "patient_involved": True,
            "serious_injury": False,
            "death": False,
            "malfunction": True,
        },
        ("Ambulance", HCP),
    ),
]
# Days since the event for the two VentraLink 250 Rev B complaints, reported late (the others: six hours before
# awareness). Their events fall before the trend check's last 30 days, so VentraLink keeps at most 2 complaints there
# and stays flat by version and by type, as the sample's explanation says; only OrbitCare 300 rises. Both are on lot 4,
# made 68 days ago, before the event. Awareness stays recent: the routine path and the reporting clocks read it.
LATE_EVENT_DAYS = {"SAMPLE-RT-01": 36, "SAMPLE-RT-05": 33}
# The story complaints' proposed values, as the source gives them.
STORY_CLASSIFICATIONS = {
    "SAMPLE-RV-01": ("Hospital ward", HCP),
    "SAMPLE-RV-02": ("Intensive care unit", HCP),
    "SAMPLE-RV-03": ("Hospital ward", HCP),
    "SAMPLE-RV-04": ("Hospital ward", HCP),
    "SAMPLE-RV-05": ("Hospital ward", HCP),
    "SAMPLE-RV-06": ("Hospital ward", HCP),
    "SAMPLE-RV-07": ("Intensive care unit", HCP),
    "SAMPLE-RV-08": ("Hospital ward", HCP),
    "SAMPLE-RV-09": ("Hospital ward", HCP),
}
RT03_RECORD = {
    "troubleshooting": "Inspected the SpO2 sensor cable and connector; checked the monitor's self-test log.",
    "correction_type": "PART_REPLACED",
    "correction": "Replaced the SpO2 sensor cable with a new one from stock.",
    "result": "Monitor tested OK with a simulator; back in use.",
    "service_ticket": "FSE-4417",
    "no_investigation_rationale": "Wear of a consumable cable at the connector, corrected by replacement; no patient "
    "involved and no product defect beyond wear indicated; trended under ISO 13485:2016 8.2.2.",
}


def has_routine_examples(db: Session, tenant_id) -> bool:
    from backend.app.db.models.foundation import Complaint

    return (
        db.query(Complaint.id)
        .filter(Complaint.tenant_id == tenant_id, Complaint.complaint_identifier == MARKER)
        .first()
        is not None
    )


def _proposal(tenant_id, complaint_id, source: tuple[str, str], author_id: str, now) -> object:
    from backend.app.complaint_classification import rules as coding
    from backend.app.db.models.market_assessment import ComplaintClassification

    environment, environment_source = coding.code_source_value("use_environment", source[0])
    user, user_source = coding.code_source_value("user_type", source[1])
    return ComplaintClassification(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        complaint_id=complaint_id,
        version=1,
        use_environment=environment,
        user_type=user,
        source_values={"use_environment": environment_source, "user_type": user_source},
        state="PROPOSED",
        coding_criteria_version=coding.CODING_CRITERIA_VERSION,
        source_system=SAMPLE_SOURCE,
        created_by=author_id,
        created_at=now,
    )


def seed_routine_examples(db: Session, tenant_id, now: datetime | None = None) -> dict:
    """Add the routine sample complaints, the proposed classifications and RT-03's signed disposition. ``{"created":
    False}`` when the sample products are missing or the examples are there already."""
    from backend.app.complaint_disposition import rules
    from backend.app.db.models.complaint_disposition import ComplaintDisposition
    from backend.app.db.models.foundation import Complaint, LotBatch, Product, ProductVersion, SignedApprovalRecord
    from backend.app.human_decision.rules import fingerprint, signature_hash
    from backend.app.reportability import markets
    from backend.app.signer_training import service as training
    from backend.app.standards import STARTER_MARK
    from backend.app.trial.sample_decision import SAMPLE_AUTHOR_ROLE, sample_author

    now = now or datetime.now(timezone.utc)
    if has_routine_examples(db, tenant_id):
        return {"created": False, "why": "ALREADY_STAGED"}
    products = {
        row.product_identifier: row
        for row in db.query(Product).filter(Product.tenant_id == tenant_id, Product.source_system == SAMPLE_SOURCE)
    }
    if not {"SAMPLE-VENTRA-250", "SAMPLE-PULSE-410", "SAMPLE-ORBIT-300"} <= set(products):
        return {"created": False, "why": "NO_SAMPLE_PRODUCTS"}
    versions = {
        (row.product_id, row.version_identifier): row
        for row in db.query(ProductVersion).filter(ProductVersion.tenant_id == tenant_id)
    }
    lots = {
        row.lot_identifier: row
        for row in db.query(LotBatch).filter(LotBatch.tenant_id == tenant_id, LotBatch.source_system == SAMPLE_SOURCE)
    }
    savepoint = db.begin_nested()
    try:
        author_id = str(sample_author(db, tenant_id, now).id)
        added: dict[str, Complaint] = {}
        for identifier, code, revision, lot_number, days, description, fields, source in ROUTINE_COMPLAINTS:
            product = products[code]
            version = versions.get((product.id, revision))
            lot = lots.get(f"{code}-LOT-{lot_number:03d}")
            aware = now - timedelta(days=days)
            complaint = Complaint(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                complaint_identifier=identifier,
                product_id=product.id,
                product_version_id=version.id if version else None,
                lot_batch_id=lot.id if lot else None,
                event_timestamp=(
                    now - timedelta(days=LATE_EVENT_DAYS[identifier])
                    if identifier in LATE_EVENT_DAYS
                    else aware - timedelta(hours=6)
                ),
                complaint_timestamp=aware,
                awareness_timestamp=aware,
                description=description,
                status="open",
                source_system=SAMPLE_SOURCE,
                source_identifier=identifier,
                source_timestamp=aware,
                effective_timestamp=aware,
                recorded_timestamp=aware,
                ingestion_timestamp=now,
                created_at=aware,
                updated_at=aware,
                **fields,
            )
            db.add(complaint)
            added[identifier] = complaint
        db.flush()
        proposals = [
            _proposal(tenant_id, added[identifier].id, source, author_id, now)
            for identifier, *_, source in ROUTINE_COMPLAINTS
        ]
        story = {
            row.complaint_identifier: row
            for row in db.query(Complaint).filter(
                Complaint.tenant_id == tenant_id, Complaint.complaint_identifier.in_(list(STORY_CLASSIFICATIONS))
            )
        }
        proposals += [
            _proposal(tenant_id, story[identifier].id, source, author_id, now)
            for identifier, source in STORY_CLASSIFICATIONS.items()
            if identifier in story
        ]
        db.add_all(proposals)
        db.flush()

        # RT-03: closed at service level three weeks ago by the sample author, device-related.
        rt03 = added["SAMPLE-RT-03"]
        signed_at = now - timedelta(days=20)
        for document in training.for_disposition():
            training.acknowledge(
                db,
                tenant_id,
                author_id,
                document,
                signed_at - timedelta(minutes=5),
                trial=True,
                source_system=SAMPLE_SOURCE,
            )
        proposal = next(row for row in proposals if row.complaint_id == rt03.id)
        proposal.state, proposal.confirmed_by, proposal.confirmed_at = "CONFIRMED", author_id, signed_at
        disposition_id, record_id = uuid.uuid4(), uuid.uuid4()
        proposal.signed_record_id = record_id
        answers = rules.answers_of(rules.SERVICE_LEVEL, [], [], "", "")
        record = rules.clean_service_record(RT03_RECORD)
        # B7-D5: the sample's customer was told through the distributor, signed with the disposition.
        record["customer_told"] = {
            "how": "DISTRIBUTOR",
            "at": signed_at.isoformat(),
            "note": "The distributor told the hospital the cause and the fix.",
            "qms_letter_id": None,
            "reason": None,
        }
        material = {
            "complaint_id": str(rt03.id),
            "complaint": "SAMPLE-RT-03",
            "version": 1,
            "rules_version": rules.RULES_VERSION,
            "branch": rules.SERVICE_LEVEL,
            "answers": answers,
            "triggers": [],
            "service_record": record,
            "attribution": rules.DEVICE_RELATED,
            "classification": {"use_environment": "HOSPITAL_WARD", "user_type": "HEALTHCARE_PROFESSIONAL"},
            "starter_mark": STARTER_MARK,
            "practice_label": markets.PRACTICE_LABEL,
            "sample": True,
        }
        content_fingerprint = fingerprint(material)
        db.add(
            SignedApprovalRecord(
                id=record_id,
                tenant_id=tenant_id,
                object_type="ComplaintDisposition",
                object_id=disposition_id,
                object_version="1",
                decision_type="COMPLAINT_DISPOSITION",
                decision=rules.SIGNATURE_CODES[rules.SERVICE_LEVEL],
                remarks="Sample: a finished example signed by the MDARIX sample author",
                signer_user_id=author_id,
                signer_role=SAMPLE_AUTHOR_ROLE,
                signature_meaning=rules.signature_meaning("SAMPLE-RT-03", rules.SERVICE_LEVEL, [], True),
                content_fingerprint=content_fingerprint,
                signature_hash=signature_hash(content_fingerprint, author_id, "1"),
                status="SIGNED",
                signed_at=signed_at,
                created_at=signed_at,
            )
        )
        db.add(
            ComplaintDisposition(
                id=disposition_id,
                tenant_id=tenant_id,
                complaint_id=rt03.id,
                version=1,
                branch=rules.SERVICE_LEVEL,
                triggers=[],
                answers=answers,
                service_record=record,
                attribution=rules.DEVICE_RELATED,
                routine_path=True,
                hands_on_seconds=262,
                signed_record_id=record_id,
                content_fingerprint=content_fingerprint,
                signed_by=author_id,
                signed_at=signed_at,
                source_system=SAMPLE_SOURCE,
                created_by=author_id,
                created_at=signed_at,
            )
        )
        db.flush()
        savepoint.commit()
    except Exception:
        savepoint.rollback()
        logger.exception("Trial routine sample complaints could not be staged")
        return {"created": False, "why": "ERROR"}
    return {"created": True, "complaints": len(added), "classifications": len(proposals), "dispositions": 1}
