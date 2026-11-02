"""A worksheet drafted from the records (T-G2c, MVP G2b's field rules): every field of the form, in its order, with
its value, its status and where the value came from.

Statuses (G2b): **from record** (with the record it came from), **entered by a person** (who and when),
**confirmed** (a person checked a record's value), one of the three missing classes, **not used** in this report,
and, for a patient or reporter field outside the sample, **enter in the authority's route** (T-B9: MDARIX never
stores them). Values are copied by fixed mappings (``SOURCES``); MDARIX never invents a patient outcome, a device
identifier, a date, an investigation result, a root cause or a conclusion. IMDRF codes are the organization's
approved mappings of the complaint's problem code (T-G2a, ``regulatory_reference.approved_links``).
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy.orm import Session

from backend.app import product_facts
from backend.app.authority_reports import forms
from backend.app.reportability import markets

FROM_RECORD, ENTERED, CONFIRMED, OUTSIDE = "FROM_RECORD", "ENTERED", "CONFIRMED", "OUTSIDE"
FICTIONAL_STATUS = "FICTIONAL"
STATUS_LABELS = {
    FROM_RECORD: "From record",
    ENTERED: "Entered by a person",
    CONFIRMED: "Confirmed",
    OUTSIDE: "Enter in the authority's route",
    FICTIONAL_STATUS: "Fictional (sample only)",
    **forms.MISSING_LABELS,
}
VALUE_MAX = 4000
FICTIONAL = "Fictional sample value"

# The sample's patient and reporter fields: fictional, for the sample complaints only (T-B9). Nothing here is a person.
_US_PERSON = {
    "A1": "PT-{n} (fictional)",
    "A3": "Female",
    "A5": "Not stated",
    "B6": "None reported (fictional sample)",
    "B7": "None reported (fictional sample)",
    "D10": "None reported (fictional sample)",
    "E1": "Ward nurse, Sample General Hospital (fictional), 1 Sample Street, Springfield, US; phone and e-mail not "
    "given",
    "E3": "Nurse",
}
SAMPLE_PERSONAL = {
    "SAMPLE-RV-06": {**_US_PERSON, "A1": "PT-0006 (fictional)", "A2": "64 years", "A4": "71 kg"},
    "SAMPLE-RV-09": {**_US_PERSON, "A1": "PT-0009 (fictional)", "A2": "78 years", "A3": "Male", "A4": "80 kg"},
    "SAMPLE-RV-10": {
        "C1": "SAMPLE-HOSP-0010 (fictional)",
        "C2": "R.K. (fictional)",
        "C3": "57 years",
        "C4": "Male",
        "C5": "68 kg",
        "C6": "None reported (fictional sample)",
        "C7": "Not yet recovered (fictional sample)",
        "D1": "Sample City Hospital (fictional)",
        "D2": "1 Sample Road, Pune, India (fictional)",
        "D3": "Biomedical engineer on duty (fictional)",
        "D4": "Not given",
        "D5": "Not given",
    },
}

_OPERATORS_US = {
    "HEALTHCARE_PROFESSIONAL": "Health professional",
    "LAY_USER": "Patient/consumer",
    "PATIENT": "Patient/consumer",
}
_OPERATORS_IN = {"HEALTHCARE_PROFESSIONAL": "Healthcare professional", "PATIENT": "Patient", "LAY_USER": "Patient"}
_LOCATIONS_IN = {
    "HOSPITAL_WARD": "Hospital",
    "INTENSIVE_CARE_UNIT": "Hospital",
    "OPERATING_THEATRE": "Hospital",
    "HOME": "Home",
    "CLINIC": "Others: clinic",
    "AMBULANCE": "Others: ambulance",
}
_IMDRF_ANNEX_NAMES = {
    "A": "Annex A",
    "B": "Annex B",
    "C": "Annex C",
    "D": "Annex D",
    "E": "Annex E",
    "F": "Annex F",
    "G": "Annex G",
}


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _source(kind: str, ref: str | None, label: str, record_id=None) -> dict:
    return {"type": kind, "ref": ref, "label": label, "id": str(record_id) if record_id else None}


def load(db: Session, control_db: Session, tenant_id: uuid.UUID, complaint_id: uuid.UUID, market: str) -> dict:
    """Everything a worksheet may read for one complaint and market. ``None`` when the complaint does not exist."""
    from backend.app import regulatory_reference
    from backend.app.db.models.foundation import Capa, Investigation, InvestigationComplaint, LotBatch, Product
    from backend.app.db.models.intake import TriageRecord
    from backend.app.db.models.market_assessment import ComplaintClassification
    from backend.app.db.models.regulatory_reference import MarketResponsibleParty, ProductRegistration
    from backend.app.reportability import assessments, service
    from backend.app.trial.sample_data import SAMPLE_SOURCE

    found = service.one(db, tenant_id, complaint_id)
    if found is None:
        return None
    complaint, record, seen, _ = found
    product = db.get(Product, complaint.product_id) if complaint.product_id else None
    lot = db.get(LotBatch, complaint.lot_batch_id) if complaint.lot_batch_id else None
    versions = assessments.rows_by_complaint(db, tenant_id, [complaint_id]).get(complaint_id, {}).get(market, [])
    current, draft = assessments.current_and_draft(versions)
    classification = (
        db.query(ComplaintClassification)
        .filter(
            ComplaintClassification.tenant_id == tenant_id,
            ComplaintClassification.complaint_id == complaint_id,
            ComplaintClassification.superseded_by.is_(None),
        )
        .order_by(ComplaintClassification.version.desc())
        .first()
    )
    case = (
        db.query(Investigation)
        .join(
            InvestigationComplaint,
            (InvestigationComplaint.tenant_id == Investigation.tenant_id)
            & (InvestigationComplaint.investigation_id == Investigation.id),
        )
        .filter(InvestigationComplaint.tenant_id == tenant_id, InvestigationComplaint.complaint_id == complaint_id)
        .order_by(Investigation.opened_at.desc())
        .first()
    )
    capas = db.query(Capa).filter(Capa.tenant_id == tenant_id, Capa.investigation_id == case.id).all() if case else []
    triage = (
        db.query(TriageRecord)
        .filter(
            TriageRecord.tenant_id == tenant_id,
            TriageRecord.subject_kind == "COMPLAINT",
            TriageRecord.subject_id == complaint_id,
        )
        .first()
    )
    registry_market = "IN" if market == markets.IN else market
    registrations = (
        db.query(ProductRegistration)
        .filter(
            ProductRegistration.tenant_id == tenant_id,
            ProductRegistration.product_id == product.id,
            ProductRegistration.market == registry_market,
        )
        .all()
        if product
        else []
    )
    parties = (
        db.query(MarketResponsibleParty)
        .filter(MarketResponsibleParty.tenant_id == tenant_id, MarketResponsibleParty.market == registry_market)
        .all()
    )
    codes = (
        regulatory_reference.approved_links(db, control_db, tenant_id, "problem_code", [complaint.problem_code])
        if complaint.problem_code
        else {}
    ).get(complaint.problem_code or "", [])
    return {
        "complaint": complaint,
        "record": record,
        "seen": seen,
        "product": product,
        "lot": lot,
        "current": current,
        "draft": draft,
        "classification": classification if classification and classification.state == "CONFIRMED" else None,
        "case": case,
        "capas": capas,
        "triage": triage,
        "registrations": registrations,
        "parties": parties,
        "imdrf": codes,
        "sample": complaint.source_system == SAMPLE_SOURCE,
    }


def _ref(context) -> str:
    record = context["record"]
    return record["business_id"] or record["complaint_identifier"]


def _complaint(context, label: str) -> dict:
    return _source("Complaint", _ref(context), label, context["complaint"].id)


def _assessment(context, label: str):
    row = context["current"] or context["draft"]
    if row is None:
        return None
    state = "signed" if row.conclusion else "draft"
    return _source("MarketAssessment", f"{_ref(context)} {row.market} v{row.version} ({state})", label, row.id)


def _answer(context, question_id: str) -> str | None:
    row = context["current"] or context["draft"]
    return ((row.answers or {}).get(question_id) or {}).get("answer") if row else None


def _product(context, value, label: str):
    product = context["product"]
    return (value, _source("Product", product.product_identifier, label, product.id)) if value and product else None


def _party(context, roles: tuple[str, ...], label: str):
    for role in roles:
        party = next((item for item in context["parties"] if item.role == role), None)
        if party:
            text = ", ".join(part for part in (party.organisation, party.address) if part)
            contact = ", ".join(part for part in (party.contact_name, party.contact_phone, party.contact_email) if part)
            value = f"{text}; contact: {contact}" if contact else text
            return value, _source("ResponsibleParty", f"{party.market} {party.role.lower()}", label, party.id)
    return None


def _registration(context, types: tuple[str, ...], column: str, label: str):
    for item in context["registrations"]:
        if item.registration_type in types and getattr(item, column):
            return getattr(item, column), _source(
                "Registration", f"{item.market} {item.registration_type} {item.registration_number}", label, item.id
            )
    return None


def _event_type(context):
    complaint = context["complaint"]
    found = []
    if complaint.death or complaint.serious_injury or complaint.patient_involved:
        found.append("Adverse event")
    if complaint.malfunction:
        found.append("Product problem (e.g., defects/malfunctions)")
    return ("; ".join(found), _complaint(context, "The complaint's harm and malfunction fields")) if found else None


def _us_outcome(context):
    outcomes = [
        label
        for question, label in (
            ("US1", "Death"),
            ("US2A", "Life-threatening"),
            ("US2B", "Disability or permanent damage"),
            ("US2C", "Required intervention to prevent permanent impairment/damage"),
        )
        if _answer(context, question) == markets.YES
    ]
    source = _assessment(context, "The US assessment's answers to questions 1 and 2(a)-(c)")
    return ("; ".join(outcomes), source) if outcomes and source else None


def _us_event_type(context):
    found = []
    if _answer(context, "US1") == markets.YES:
        found.append("Death")
    if (
        markets.YES in (_answer(context, q) for q in ("US2A", "US2B", "US2C"))
        and _answer(context, "US3") == markets.YES
    ):
        found.append("Serious injury")
    if _answer(context, "US4") == markets.YES and _answer(context, "US5") == markets.YES:
        found.append("Malfunction")
    source = _assessment(context, "The US assessment: death, serious injury and malfunction")
    return ("; ".join(found), source) if found and source else None


def _us_report_type(context):
    row = context["current"]
    if row is None or row.conclusion != markets.REPORTABLE:
        return None
    kind = {"US_30_DAY": "30-day", "US_5_WORK_DAY": "5-day"}.get(row.report_type or "")
    if not kind:
        return None
    return f"{kind}; Initial", _assessment(context, "The signed US conclusion's report type")


def _in_serious(context):
    reasons = [
        label
        for question, label in (
            ("IN2A", "a) Death"),
            ("IN2B", "b) Life threatening"),
            ("IN2D", "c) Disability or permanent damage"),
            ("IN2C", "d) Hospitalization / prolongation of existing hospitalization"),
            ("IN2E", "e) Congenital anomaly"),
            ("IN2F", "f) Required intervention to prevent permanent impairment / damage"),
        )
        if _answer(context, question) == markets.YES
    ]
    source = _assessment(context, "The India assessment's seriousness answers")
    return (f"Yes: {'; '.join(reasons)}", source) if reasons and source else None


def _in_non_serious(context):
    row = context["current"]
    if row is None or row.conclusion is None:
        return None
    serious = _in_serious(context)
    return ("No" if serious else "Yes"), _assessment(context, "The signed India conclusion")


def _classification(context, table: dict, column: str, label: str):
    row = context["classification"]
    value = table.get(getattr(row, column)) if row else None
    return (value, _source("Classification", f"{_ref(context)} v{row.version}", label, row.id)) if value else None


def _available(context):
    returned = context["complaint"].device_returned
    if returned is None:
        return None
    value = "Returned to manufacturer" if returned else "No"
    return value, _complaint(context, "The complaint's device-returned field")


def _imdrf(annex: str):
    def read(context):
        codes = [code for code in context["imdrf"] if code["annex"] == annex]
        if not codes:
            return None
        text = "; ".join(f"{code['code']} {code['term'] or '(term not loaded)'}" for code in codes)
        release = codes[0]["release"]
        complaint = context["complaint"]
        return text, _source(
            "ImdrfMapping",
            f"{complaint.problem_code} -> IMDRF {_IMDRF_ANNEX_NAMES[annex]}, release {release}",
            "Your approved IMDRF mapping of the complaint's problem code",
        )

    return read


def _case(context):
    case = context["case"]
    if case is None:
        return None
    return (
        f"Case {case.business_id or case.investigation_identifier}: {case.workflow_state.replace('_', ' ').lower()}",
        _source(
            "Case", case.business_id or case.investigation_identifier, "The case that holds this complaint", case.id
        ),
    )


def _capas(context):
    if not context["capas"]:
        return None
    from backend.app.decision_followups.rules import capa_qms_words

    text = "; ".join(
        f"{capa.capa_identifier}: {capa.title} ({', '.join(filter(None, (capa.status, capa_qms_words(capa))))})"
        for capa in context["capas"]
    )
    case = context["case"]
    return text, _source("Capa", case.business_id or case.investigation_identifier, "The CAPAs of the case", case.id)


# A version that reads as a software version number ("2.1", "v1.4.2", "1.4.2+build"); "Rev B" does not.
_SOFTWARE_VERSION = re.compile(r"(?i)^v?\d+(\.\d+)+")


def _software_version(context):
    """A8 (J32): the complaint's product version, for a software product or a version that reads as a software
    version number; a hardware revision is not a software version."""
    product, version = context["product"], context["record"].get("version")
    if not product or not version:
        return None
    if product.device_category == product_facts.SOFTWARE:
        label = "The product version (a software product)"
    elif _SOFTWARE_VERSION.match(version):
        label = "The product version (a version number: check it is the software's)"
    else:
        return None
    return version, _source("Product", f"{product.product_identifier} {version}", label, product.id)


def _lots(context):
    """The complaint's lot, and a kit's other lots after it (J32)."""
    lot = context["lot"]
    if lot is None:
        return None
    others = list(context["complaint"].other_lots or [])
    label = "The complaint's lots (its first, then the others it names)" if others else "The complaint's lot"
    return "; ".join([lot.lot_identifier, *others]), _source("Lot", lot.lot_identifier, label, lot.id)


def _expiry(context):
    lot = context["lot"]
    if lot is None or lot.expiry_date is None:
        return None
    return lot.expiry_date.isoformat(), _source("Lot", lot.lot_identifier, "The lot's expiry date", lot.id)


def _category(table: dict, label: str):
    def read(context):
        product = context["product"]
        value = table.get(product.device_category) if product else None
        return _product(context, value, label)

    return read


_IMPLANTABLE = {code: "Non-implantable device" for code in product_facts.CATEGORY_LABELS} | {
    product_facts.IMPLANT: "Implantable device"
}
_USE = {product_facts.SINGLE_USE: "Single use", product_facts.REUSABLE: "Reusable"}


def _single_use(context):
    """US H5 "Labeled for single use?" from the product's single-use field."""
    product = context["product"]
    flag = getattr(product, "single_use", None) if product else None
    return _product(context, None if flag is None else ("Yes" if flag else "No"), "The product's single-use field")


def _immediate_action(context):
    triage = context["triage"]
    text = triage.immediate_action if triage else None
    return (text, _source("Triage", _ref(context), "The triage record's immediate action", triage.id)) if text else None


SOURCES = {
    "description": lambda c: (c["complaint"].description, _complaint(c, "The complaint's description, as recorded")),
    "event_date": lambda c: (
        (c["complaint"].event_timestamp.date().isoformat(), _complaint(c, "The complaint's event date"))
        if c["complaint"].event_timestamp
        else None
    ),
    "aware_date": lambda c: (
        (c["seen"]["aware_date"], _complaint(c, "Awareness: the earliest awareness, received or recorded date"))
        if c["seen"].get("aware_date")
        else None
    ),
    "event_type": _event_type,
    "us_outcome": _us_outcome,
    "us_event_type": _us_event_type,
    "us_report_type": _us_report_type,
    "in_report_type": lambda c: ("Initial", _source("Obligation", None, "An initial report")),
    "in_serious": _in_serious,
    "in_non_serious": _in_non_serious,
    "follow_up_type": lambda c: None,
    "brand_name": lambda c: _product(c, c["product"].name if c["product"] else None, "The product's name"),
    "common_name": lambda c: _product(c, c["product"].gmdn_term if c["product"] else None, "The product's GMDN term"),
    "gmdn_code": lambda c: _product(c, c["product"].gmdn_code if c["product"] else None, "The product's GMDN code"),
    "model": lambda c: _product(
        c,
        " ".join(part for part in (c["product"].product_identifier, c["record"].get("version")) if part)
        if c["product"]
        else None,
        "The product identifier and version",
    ),
    "lot": _lots,
    "lot_expiry": _expiry,
    "software_version": _software_version,
    "implantable": _category(_IMPLANTABLE, "The product's device category"),
    "use": _category(_USE, "The product's device category"),
    "single_use": _single_use,
    "serial": lambda c: (
        (c["complaint"].serial_number, _complaint(c, "The complaint's serial number"))
        if c["complaint"].serial_number
        else None
    ),
    "udi": lambda c: (
        (c["complaint"].udi, _complaint(c, "The complaint's UDI"))
        if c["complaint"].udi
        else _product(
            c,
            c["product"].udi_di if c["product"] else None,
            "The product's UDI-DI (the device identifier only: add the production identifier)",
        )
    ),
    "us_product_code": lambda c: _registration(
        c, ("510K", "PMA", "DE_NOVO", "EXEMPT"), "product_code", "FDA product code"
    ),
    "us_clearance": lambda c: _registration(c, ("510K", "PMA", "DE_NOVO"), "registration_number", "US registration"),
    "in_licence": lambda c: _registration(c, ("CDSCO_LICENCE",), "registration_number", "CDSCO licence"),
    "us_manufacturer": lambda c: _party(c, ("MANUFACTURER",), "The US responsible party (manufacturer)"),
    "us_contact_office": lambda c: _party(c, ("MANUFACTURER", "IMPORTER"), "The US responsible party"),
    "in_manufacturer": lambda c: _party(c, ("MANUFACTURER", "LICENCE_HOLDER"), "The India responsible party"),
    "in_importer": lambda c: _party(c, ("IMPORTER",), "The India importer"),
    "in_reporter": lambda c: _party(c, ("LICENCE_HOLDER", "MANUFACTURER", "IMPORTER"), "The India responsible party"),
    "us_operator": lambda c: _classification(c, _OPERATORS_US, "user_type", "The confirmed classification's user type"),
    "in_operator": lambda c: _classification(c, _OPERATORS_IN, "user_type", "The confirmed classification's user type"),
    "in_location": lambda c: _classification(
        c, _LOCATIONS_IN, "use_environment", "The confirmed classification's use environment"
    ),
    "health_professional": lambda c: _classification(
        c,
        {"HEALTHCARE_PROFESSIONAL": "Yes", "LAY_USER": "No", "PATIENT": "No"},
        "user_type",
        "The confirmed classification's user type",
    ),
    "report_source": lambda c: _classification(
        c,
        {"HEALTHCARE_PROFESSIONAL": "Health professional", "LAY_USER": "Consumer", "PATIENT": "Consumer"},
        "user_type",
        "The confirmed classification's user type",
    ),
    "available": _available,
    "in_disposition": lambda c: (
        ("a) Returned to company", _complaint(c, "The complaint's device-returned field"))
        if c["complaint"].device_returned
        else None
    ),
    **{f"imdrf_{annex}": _imdrf(annex) for annex in "ABCDEFG"},
    "case": _case,
    "capas": _capas,
    "investigation_needed": lambda c: ("Yes", _case(c)[1]) if c["case"] else None,
    "immediate_action": _immediate_action,
    "request": lambda c: None,  # a response obligation's request is set by build()
}


def build(
    form: forms.Form, context: dict, entries: dict, names: dict[str, str], request: str | None = None
) -> list[dict]:
    """The worksheet's sections, each field with its value, status and source, in the form's order."""
    personal = SAMPLE_PERSONAL.get(context["complaint"].complaint_identifier, {}) if context["sample"] else {}
    out = []
    for section in form.sections:
        rows = []
        for item in section.fields:
            entry = entries.get(item.id) or {}
            found = None
            if item.personal:
                value = personal.get(item.id)
                found = (value, _source("Sample", None, FICTIONAL)) if value else None
            elif item.source == "front_page":
                # The front page's number, entered once (stage 8: nothing typed twice).
                front = (entries.get("MFR_REPORT") or {}).get("value")
                found = (front, _source("Worksheet", None, "This worksheet's front page")) if front else None
            elif item.source == "request":
                found = (
                    (request, _source("Obligation", None, "The authority's request, as recorded")) if request else None
                )
            elif item.source:
                found = SOURCES[item.source](context)
            value, source = found if found and found[0] else (None, None)
            status = (FICTIONAL_STATUS if item.personal else FROM_RECORD) if value else None
            if not item.personal and entry.get("value"):
                value, status, source = entry["value"], ENTERED, None
            elif value and entry.get("confirmed"):
                status = CONFIRMED
            if status is None:
                status = (
                    OUTSIDE
                    if item.personal and not context["sample"]
                    else (forms.NOT_USED if item.missing == forms.NOT_USED else item.missing)
                )
            rows.append(
                {
                    "id": item.id,
                    "number": item.number,
                    "label": item.label,
                    "value": value,
                    "status": status,
                    "status_label": STATUS_LABELS[status],
                    "source": source,
                    "personal": item.personal,
                    "missing_class": item.missing,
                    "editable": not item.personal and item.missing != forms.NOT_USED,
                    "note": item.note or None,
                    "by": names.get(entry.get("by")) if entry else None,
                    "at": entry.get("at") if entry else None,
                }
            )
        out.append({"code": section.code, "title": section.title, "note": section.note or None, "fields": rows})
    return out


def counts(sections: list[dict]) -> dict:
    """How many fields have each status (the worksheet's summary line)."""
    found: dict[str, int] = {}
    for section in sections:
        for item in section["fields"]:
            found[item["status"]] = found.get(item["status"], 0) + 1
    return found


def frozen(sections: list[dict]) -> list[dict]:
    """The sections as a snapshot keeps them: no names resolved later, nothing that changes on its own."""
    return [
        {
            **section,
            "fields": [{key: value for key, value in item.items() if key != "editable"} for item in section["fields"]],
        }
        for section in sections
    ]


def mandatory(sections: list[dict]) -> dict:
    """The mandatory-fields meter (0.10.75): the form's fields that must have a value before submission (its "must
    have" class, never a patient or reporter field), how many have one, and the ones still empty, in the form's order."""
    fields = [
        item
        for section in sections
        for item in section["fields"]
        if item["missing_class"] == forms.MUST and not item.get("personal")
    ]
    missing = [item["id"] for item in fields if item["status"] == forms.MUST]
    return {"total": len(fields), "filled": len(fields) - len(missing), "missing": missing}
