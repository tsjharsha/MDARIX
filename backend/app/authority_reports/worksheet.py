"""A worksheet drafted from the records (T-G2c, MVP G2b's field rules): every field of the form, in its order, with
its value, its status and where the value came from.

Statuses (G2b): **from record** (with the record it came from), **entered by a person** (who and when),
**confirmed** (a person checked a record's value), one of the three missing classes, **not used** in this report,
and, for a patient or reporter field outside the sample, **enter in the authority's route** (T-B9: MDARIX never
stores them). Values are copied by fixed mappings (``SOURCES``); MDARIX never invents a patient outcome, a device
identifier, a date, an investigation result, a root cause or a conclusion. IMDRF codes are the organization's
approved mappings of the complaint's problem code (T-G2a, ``regulatory_reference.approved_links``).

Codes (0.10.77, C5): on the new navigation a code the approved mapping supplies is only **suggested**: it shows as
"Suggested from your approved mapping" and counts as missing until the regulatory manager confirms it or changes it
(``code_state`` CONFIRMED or CHANGED, with who and when). An unconfirmed suggestion is never frozen into a snapshot,
so it never reaches the form or the PDF. On the FDA's form each IMDRF code carries its FDA code (FDA's published
FDA-IMDRF mapping): one choice fills both.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from backend.app import product_facts
from backend.app.authority_reports import forms
from backend.app.reportability import deadlines, markets

FROM_RECORD, ENTERED, CONFIRMED, OUTSIDE = "FROM_RECORD", "ENTERED", "CONFIRMED", "OUTSIDE"
SUGGESTED, CHANGED = "SUGGESTED", "CHANGED"
FICTIONAL_STATUS = "FICTIONAL"
STATUS_LABELS = {
    FROM_RECORD: "From record",
    ENTERED: "Entered by a person",
    CONFIRMED: "Confirmed",
    SUGGESTED: "Suggested from your approved mapping",
    CHANGED: "Changed from the suggestion",
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
    # The registry names the EU market "EU" (regulatory_reference.MARKETS); every other market by its own code.
    registry_market = {markets.EU_NI: "EU"}.get(market, market)
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
        "market": market,
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
        # FDA's code for each IMDRF code, on the FDA's form (0.10.77): one choice fills both.
        "fda": regulatory_reference.fda_codes(control_db, [code["code"] for code in codes])
        if market == markets.US
        else {},
        # Codes are suggestions a person confirms (the new navigation; the router sets it, 0.10.77).
        "confirm_codes": False,
        "sample": complaint.source_system == SAMPLE_SOURCE,
    }


def _ref(context) -> str:
    # The customer's own reference, as every screen names the complaint (navigation finding L1; 0.10.83).
    record = context["record"]
    return record["complaint_identifier"] or record["business_id"]


def _complaint(context, label: str) -> dict:
    return _source("Complaint", _ref(context), label, context["complaint"].id)


def _assessment(context, label: str):
    row = context["current"] or context["draft"]
    if row is None:
        return None
    state = "signed" if row.conclusion else "draft"
    market = markets.MARKET_LABELS.get(row.market, row.market)
    return _source("MarketAssessment", f"{_ref(context)} {market} v{row.version} ({state})", label, row.id)


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


CONTACT_EMAIL = "CONTACT_EMAIL"
EMAIL_NEEDED = "The eMDR file needs the contact office's e-mail"


def contact_office_problem(context, value: str) -> str | None:
    """Why FDA's eMDR file could not carry this contact office (G1), said while the report is a draft (0.10.92, A5:
    approval froze the report and only then the XML said it was missing): the file takes G1 from the US responsible
    party, with its e-mail of up to 50 characters, only while the report reads exactly as that party
    (authority_reports/emdr.py ``check``). None when it can."""
    roles = ("MANUFACTURER", "IMPORTER")
    found = _party(context, roles, "")
    if found is None or found[0] != value:
        return (
            "Differs from your US responsible party in Settings › Products: the eMDR file takes the contact office "
            "from it, so set it there and clear this value"
        )
    party = next(item for role in roles for item in context["parties"] if item.role == role)
    email = party.contact_email or ""
    if not email or len(email) > 50:
        return (
            f"{EMAIL_NEEDED} (up to 50 characters): add it here, or to your US responsible party in Settings › Products"
        )
    return None


def _registration(context, types: tuple[str, ...], column: str, label: str):
    for item in context["registrations"]:
        if item.registration_type in types and getattr(item, column):
            return getattr(item, column), _source(
                "Registration", f"{item.market} {item.registration_type} {item.registration_number}", label, item.id
            )
    return None


def _event_type(context):
    """US B1 and India B2: "Adverse event" only for harm the record states (death or serious injury, the injury
    fields a complaint holds), "Product problem" for a recorded malfunction (0.10.89). A patient merely involved, or an
    outcome not recorded, ticks neither: the field then stays empty for a person to give."""
    complaint = context["complaint"]
    found = []
    if complaint.death or complaint.serious_injury:
        found.append("Adverse event")
    if complaint.malfunction:
        found.append("Product problem (e.g., defects/malfunctions)")
    return ("; ".join(found), _complaint(context, "The complaint's harm and malfunction fields")) if found else None


def _aware_day(context):
    """The organization's local day of awareness, as its own records show it (owner decision 10 Nov, after code audit
    11), not the UTC day: an awareness at 07:00 IST is that day for an organization in India. The deadline still counts
    from the market clock's day (deadlines.start_day), which can be one day earlier, never later."""
    seen = context["seen"]
    if not seen.get("aware_at"):
        return None
    day = deadlines.start_day(datetime.fromisoformat(seen["aware_at"]), None, seen.get("org_zone"))
    return day.isoformat(), _complaint(context, "Awareness: the earliest awareness, received or recorded date")


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
    # A death or serious injury is reportable only where the device caused or contributed (US3; code audit 10).
    caused = _answer(context, "US3") == markets.YES
    if _answer(context, "US1") == markets.YES and caused:
        found.append("Death")
    if markets.YES in (_answer(context, q) for q in ("US2A", "US2B", "US2C")) and caused:
        found.append("Serious injury")
    if _answer(context, "US4") == markets.YES and _answer(context, "US5") == markets.YES:
        found.append("Malfunction")
    source = _assessment(context, "The US assessment: death, serious injury and malfunction")
    return ("; ".join(found), source) if found and source else None


def _us_report_type(context):
    follow = context.get("follow_up")
    if follow:  # a US follow-up (0.10.96, B3 B1): the initial report's clock, and its number in the chain
        kind = {"US_30_DAY": "30-day", "US_5_WORK_DAY": "5-day"}.get(follow["report_type"] or "")
        text = "; ".join(part for part in (kind, f"Follow-up #{follow['number']}") if part)
        return text, _source("Obligation", None, "A follow-up of the initial report, numbered in its chain")
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
        from backend.app.regulatory_reference import code_text

        text = "; ".join(
            code_text(code["code"], code["term"], context.get("fda", {}).get(code["code"])) for code in codes
        )
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
        f"Investigation {case.business_id or case.investigation_identifier}: {case.workflow_state.replace('_', ' ').lower()}",
        _source(
            "Case",
            case.business_id or case.investigation_identifier,
            "The investigation that holds this complaint",
            case.id,
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
    return text, _source(
        "Capa", case.business_id or case.investigation_identifier, "The CAPAs of the investigation", case.id
    )


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


def _party_name(context, roles: tuple[str, ...], label: str):
    found = _party(context, roles, label)
    party = next((item for item in context["parties"] if item.role in roles), None)
    return (party.organisation, found[1]) if found and party and party.organisation else None


def _signed(context):
    row = context["current"]
    return row if row is not None and row.conclusion == markets.REPORTABLE else None


def _mir_classification(context):
    """EU and GB 1.2g from the signed conclusion's report type: 2 days a public health threat; 10 days a death
    (question 2) or else an unanticipated serious deterioration; 15 days all other reportable incidents."""
    row = _signed(context)
    kind = (row.report_type or "") if row else ""
    if kind.endswith("_2_DAY"):
        value = "Serious public health threat"
    elif kind.endswith("_10_DAY"):
        died = _answer(context, f"{kind.split('_')[0]}2") == markets.YES
        value = "Death" if died else "Unanticipated serious deterioration in state of health"
    elif kind.endswith("_15_DAY"):
        value = "All other reportable incidents"
    else:
        return None
    return value, _assessment(context, "The signed conclusion's report type")


def _ca_classification(context):
    """Canada B1 from the signed conclusion's report type."""
    row = _signed(context)
    kind = {"CA_10_DAY": "10-Day; Canadian", "CA_30_DAY": "30-Day; Canadian", "CA_FOREIGN": "Foreign"}.get(
        (row.report_type or "") if row else ""
    )
    return (kind, _assessment(context, "The signed Canada conclusion's report type")) if kind else None


def _consequences(context):
    """Canada B4 from the complaint's harm fields: what the record states, never more."""
    complaint = context["complaint"]
    if complaint.death:
        value = "Death"
    elif complaint.serious_injury:
        value = "Serious injury"
    elif complaint.death is False and complaint.serious_injury is False:
        value = "No death or serious injury reported"
    else:
        return None
    return value, _complaint(context, "The complaint's harm fields")


def _lot_serial(context):
    parts = [found[0] for found in (_lots(context), SOURCES["serial"](context)) if found]
    return ("; ".join(parts), _complaint(context, "The complaint's lot and serial number")) if parts else None


def _user_type(table: dict):
    return lambda c: _classification(c, table, "user_type", "The confirmed classification's user type")


def _returned(value: str):
    return lambda c: (
        (value, _complaint(c, "The complaint's device-returned field")) if c["complaint"].device_returned else None
    )


def _risk_class(context):
    for item in context["registrations"]:
        if item.risk_class:
            return item.risk_class, _source(
                "Registration",
                f"{item.market} {item.registration_type} {item.registration_number}",
                "The registration's risk class",
                item.id,
            )
    return None


def _srn(context):
    party = next((item for item in context["parties"] if item.role == "MANUFACTURER" and item.srn), None)
    return (
        (party.srn, _source("ResponsibleParty", f"{party.market} manufacturer", "The manufacturer's SRN", party.id))
        if party
        else None
    )


def _nomenclature(context, part: int):
    """EU 2.2a and 2.2b: the product's EMDN code where it has one (the EU's nomenclature), else its GMDN code."""
    product = context["product"]
    if product is None:
        return None
    if product.emdn_code:
        return _product(context, ("EMDN", product.emdn_code)[part], "The product's EMDN code")
    return SOURCES[("gmdn_system", "gmdn_code")[part]](context)


def _immediate_action(context):
    triage = context["triage"]
    text = triage.immediate_action if triage else None
    return (text, _source("Triage", _ref(context), "The triage record's immediate action", triage.id)) if text else None


def _sent_day(context):
    """FDA's B4, "date of this report": the organization's day the report is sent for approval (0.10.96, owner Q3), so
    the approver signs the exact file; sending again refreshes it. Blank on a draft."""
    day = context.get("sent_day")
    return (day, _source("Worksheet", None, "The day the report was sent for approval")) if day else None


def _carried(context, key: str, label: str):
    value = (context.get("ca_chain") or {}).get(key)
    return (value, _source("Obligation", None, label)) if value else None


def derived_only(source: str | None) -> bool:
    """A source a typed value never overrides: B4/P1 (the day sent for approval) and, while MDARIX_B9_INDIA is on,
    India's P2 (the chain, B9). Off, P2 is typed over "Initial" as before B9. B9 steps 7-8: F1 (the role), F7 (the
    chain) and F11/F13 (who must receive the report)."""
    return source in _DERIVED or (source == "in_report_type" and forms.india_derived())


_DERIVED = {"sent_day", "us_role_name", "us_role_report_type", "us_sent_fda", "us_sent_manufacturer"}
_ROLE_WORDS = {"IMPORTER": "Importer", "USER_FACILITY": "User facility"}
# An importer's initial report needs a code of each of F10's four kinds (FDA's list, rule book v2); a user facility's
# codes are optional.
F10_CODES = ("F10_CLINICAL", "F10_IMPACT", "F10_PROBLEM", "F10_COMPONENT")


def us_recipients(context) -> list[str]:
    """Who must receive a US importer's or user facility's report (B9 step 8, us-recipients-1 in the role floors): the
    recipients of every rule of the signed conclusion that applies or could apply (Unknown is never No), FDA when the
    rule says so for an unknown manufacturer and none is set. Nothing named (a conclusion signed before B9): both."""
    if context.get("frozen_recipients") is not None:  # approved: the list frozen at Send for approval (B9-D8)
        return list(context["frozen_recipients"])
    row = context.get("current")
    rules = ((row.rules_applied or {}).get("rules") or []) if row is not None else []
    named = {name for rule in rules for name in rule.get("recipients") or []}
    out = []
    if "FDA" in named or ("FDA_IF_MANUFACTURER_UNKNOWN" in named and SOURCES["us_manufacturer"](context) is None):
        out.append("FDA")
    if "MANUFACTURER" in named:
        out.append("MANUFACTURER")
    return out or ["FDA", "MANUFACTURER"]


def _role_party(context):
    role = context.get("us_role")
    return next((item for item in context["parties"] if item.role == role), None) if role else None


def _sent_to(recipient: str):
    def read(context):
        if not context.get("us_role"):
            return None
        sent = recipient in us_recipients(context)
        day = context.get("sent_day")
        text = ("Yes, " + day if day else "Yes") if sent else "No"
        return text, _source("Obligation", None, "Who must receive the report, from the signed conclusion's rule")

    return read


def _role_reporter(context):
    """India's R1 and Canada's A1 (B9 step 11): the organization's role in the market."""
    role = (context["seen"].get("roles") or {}).get(context["market"])
    return ("Importer" if role == "IMPORTER" else "Manufacturer"), _source(
        "Settings", None, "Your organization's role in this market (Settings, reporting windows)"
    )


def _role_field(context, value, label: str):
    party = _role_party(context)
    return (value(party), _source("ResponsibleParty", f"US {party.role.lower()}", label, party.id)) if party else None


SOURCES = {
    "sent_day": _sent_day,
    # B8 step 3: the same reference on every report of a MIR chain (1.3.1b), and the authority's number (1.1c).
    "complaint_ref": lambda c: (
        c["record"]["business_id"] or c["record"]["complaint_identifier"],
        _complaint(c, "The complaint's ID, the same on every report of the chain"),
    ),
    "nca_reference": lambda c: (
        (c["nca_reference"], _source("Obligation", None, "From the first report's recorded submission"))
        if c.get("nca_reference")
        else None
    ),
    "description": lambda c: (c["complaint"].description, _complaint(c, "The complaint's description, as recorded")),
    "event_date": lambda c: (
        (c["complaint"].event_timestamp.date().isoformat(), _complaint(c, "The complaint's event date"))
        if c["complaint"].event_timestamp
        else None
    ),
    "aware_date": _aware_day,
    "event_type": _event_type,
    "us_outcome": _us_outcome,
    "us_event_type": _us_event_type,
    "us_report_type": _us_report_type,
    # B9 steps 7-8: section F of an importer's or user facility's US report.
    "us_role_name": lambda c: (
        (_ROLE_WORDS[c["us_role"]], _source("Settings", None, "Your organization's role in the US"))
        if c.get("us_role")
        else None
    ),
    "us_role_address": lambda c: _role_field(
        c, lambda p: ", ".join(part for part in (p.organisation, p.address) if part), "The US responsible party"
    ),
    "us_role_contact": lambda c: (
        _party(c, (c["us_role"],), "The US responsible party (importer or user facility)") if c.get("us_role") else None
    ),
    "us_role_phone": lambda c: _role_field(c, lambda p: p.contact_phone, "The US responsible party's phone"),
    "us_role_report_type": lambda c: (
        (
            f"Follow-up #{c['follow_up']['number']}" if c.get("follow_up") else "Initial",
            _source("Obligation", None, "The report's place in its chain"),
        )
        if c.get("us_role")
        else None
    ),
    "us_sent_fda": _sent_to("FDA"),
    "us_sent_manufacturer": _sent_to("MANUFACTURER"),
    "role_reporter": _role_reporter,
    # B9 step 14: Initial, Follow up or Final, from the report's place in its chain (never typed).
    "in_report_type": lambda c: (
        c.get("chain_type") or "Initial",
        _source("Obligation", None, "The report's place in its chain (Initial, Follow up, Final)"),
    ),
    # B9 step 11: carried along Canada's chain from Health Canada's acknowledgement and the last report sent.
    "ca_hc_file": lambda c: _carried(c, "hc_file", "Health Canada's file number, from its acknowledgement"),
    "ca_previous": lambda c: _carried(c, "previous", "The day the previous report in the chain was submitted"),
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
    # 0.10.76 (C4): the EU, GB and Canada forms.
    "mir_classification": _mir_classification,
    "ca_classification": _ca_classification,
    "consequences": _consequences,
    "lot_serial": _lot_serial,
    "manufacturer_name": lambda c: _party_name(c, ("MANUFACTURER",), "The market's responsible party (manufacturer)"),
    "manufacturer": lambda c: _party(c, ("MANUFACTURER",), "The market's responsible party (manufacturer)"),
    "importer": lambda c: _party(c, ("IMPORTER",), "The market's importer"),
    "contact_office": lambda c: _party(c, ("MANUFACTURER", "IMPORTER"), "The market's responsible party"),
    "authorised_rep": lambda c: _party(c, ("AUTHORISED_REPRESENTATIVE",), "The EU authorised representative"),
    "uk_responsible_person": lambda c: _party(
        c, ("UK_RESPONSIBLE_PERSON", "AUTHORISED_REPRESENTATIVE"), "The UK Responsible Person"
    ),
    "eu_certificate": lambda c: _registration(c, ("CE",), "registration_number", "The EU registration (CE)"),
    "gb_certificate": lambda c: _registration(c, ("UKCA",), "registration_number", "The GB registration (UKCA)"),
    "ca_licence": lambda c: _registration(c, ("MDL",), "registration_number", "The Health Canada device licence"),
    "gb_nca": lambda c: (
        "Medicines and Healthcare products Regulatory Agency (MHRA)",
        _source("Form", None, "The authority for an incident in Great Britain"),
    ),
    "gmdn_system": lambda c: _product(
        c, "GMDN" if c["product"] and c["product"].gmdn_code else None, "The product's GMDN code"
    ),
    "incident_country": lambda c: (
        (c["record"]["country"], _complaint(c, "The complaint's event country")) if c["record"].get("country") else None
    ),
    "ca_available": _returned("Returned to Manufacturer/Importer"),
    "mir_operator": _user_type(
        {
            "HEALTHCARE_PROFESSIONAL": "Healthcare professional",
            "LAY_USER": "Patient/lay user",
            "PATIENT": "Patient/lay user",
        }
    ),
    "mir_reporter_role": _user_type(
        {"HEALTHCARE_PROFESSIONAL": "Healthcare professional", "LAY_USER": "Lay user", "PATIENT": "Patient"}
    ),
    # 0.10.77 (C5): the product and organization identity fields.
    "basic_udi": lambda c: _product(
        c, c["product"].basic_udi_di if c["product"] else None, "The product's Basic UDI-DI"
    ),
    "risk_class": _risk_class,
    "manufacturer_srn": _srn,
    "nb_number": lambda c: _registration(c, ("CE",), "body_number", "The notified body of the EU registration (CE)"),
    "eu_nomenclature_system": lambda c: _nomenclature(c, 0),
    "eu_nomenclature_code": lambda c: _nomenclature(c, 1),
    "ca_complainant": _user_type(
        {"HEALTHCARE_PROFESSIONAL": "Health professional", "LAY_USER": "Consumer", "PATIENT": "Consumer"}
    ),
}


# 0.10.83 (D2.7): who knows each field. A product's or the organization's fact is entered once and reused on every
# report (``ONCE``); the rest belong to this event.
PRODUCT, ORGANIZATION, EVENT = "PRODUCT", "ORGANIZATION", "EVENT"
_PRODUCT_SOURCES = {
    "brand_name",
    "common_name",
    "gmdn_code",
    "gmdn_system",
    "model",
    "udi",
    "basic_udi",
    "us_product_code",
    "us_clearance",
    "in_licence",
    "eu_certificate",
    "gb_certificate",
    "ca_licence",
    "risk_class",
    "nb_number",
    "eu_nomenclature_system",
    "eu_nomenclature_code",
    "implantable",
    "use",
    "single_use",
}
_ORGANIZATION_SOURCES = {
    "us_manufacturer",
    "us_contact_office",
    "in_manufacturer",
    "in_importer",
    "in_reporter",
    "manufacturer_name",
    "manufacturer",
    "importer",
    "contact_office",
    "authorised_rep",
    "uk_responsible_person",
    "manufacturer_srn",
}
# What "enter once" writes for a field's source: a product identity column, a registration (market, type, column), or
# the market's responsible party (its role). Anything else is entered on this report.
ONCE_IDENTITY = {
    "common_name": "gmdn_term",
    "gmdn_code": "gmdn_code",
    "udi": "udi_di",
    "basic_udi": "basic_udi_di",
    "eu_nomenclature_code": "emdn_code",
}
ONCE_REGISTRATION = {
    "us_product_code": ("US", "product_code"),
    "us_clearance": ("US", "registration_number"),
    "in_licence": ("IN", "registration_number"),
    "gb_certificate": ("GB", "registration_number"),
    "ca_licence": ("CA", "registration_number"),
}
ONCE_PARTY = {
    "us_manufacturer": "MANUFACTURER",
    "us_contact_office": "MANUFACTURER",
    "in_manufacturer": "MANUFACTURER",
    "manufacturer_name": "MANUFACTURER",
    "manufacturer": "MANUFACTURER",
    "contact_office": "MANUFACTURER",
    "in_importer": "IMPORTER",
    "importer": "IMPORTER",
    "in_reporter": "LICENCE_HOLDER",
    "authorised_rep": "AUTHORISED_REPRESENTATIVE",
    "uk_responsible_person": "UK_RESPONSIBLE_PERSON",
}


def scope_of(source: str | None) -> str:
    if source in _PRODUCT_SOURCES:
        return PRODUCT
    if source in _ORGANIZATION_SOURCES:
        return ORGANIZATION
    return EVENT


def once_of(source: str | None) -> bool:
    """Whether a field can be entered once for every report (the product's or the organization's own fact)."""
    return source in ONCE_IDENTITY or source in ONCE_REGISTRATION or source in ONCE_PARTY


def build(
    form: forms.Form, context: dict, entries: dict, names: dict[str, str], request: str | None = None
) -> list[dict]:
    """The worksheet's sections, each field with its value, status and source, in the form's order."""
    personal = SAMPLE_PERSONAL.get(context["complaint"].complaint_identifier, {}) if context["sample"] else {}
    # B8 step 3: a MIR chain's later report reads the reports before it, under what is typed on it.
    entries = {**context.get("carried", {}), **entries}
    # The report type decides which fields are mandatory (0.10.76: the EU, GB and Canada forms).
    kind = forms.report_kind(form, entries)
    confirm = context.get("confirm_codes", False)
    # B9 step 7: a US importer's or user facility's report has section F and no G, H or front-page manufacturer
    # number; a manufacturer's keeps section F empty, as before.
    role = context.get("us_role") if form.code == forms.FDA_3500A.code else None
    required = forms.CODES_REQUIRED.get(form.code, ()) if confirm and not role else ()
    if role == "IMPORTER" and not context.get("follow_up"):
        required = F10_CODES
    us = form.code == forms.FDA_3500A.code
    out = []
    for section in form.sections:
        rows = []
        dropped = us and ((role and section.code in ("G", "H")) or (not role and section.code == "F"))
        for item in section.fields:
            if dropped or (role and item.id == "MFR_REPORT"):
                continue
            item = forms.in_force(form, item)
            entry = entries.get(item.id) or {}
            missing = forms.MUST if item.id in required else forms.missing_class(item, kind)
            if item.id == "H2" and context.get("follow_up"):
                missing = forms.MUST  # a US follow-up says what type it is (0.10.96, B3 B1; spec 3.3)
            if item.id == "B4" and context.get("follow_up"):
                missing = forms.NOT_USED  # FDA's follow-up leaves B4 out (0.10.96)
            annex = item.source[-1] if item.source and item.source.startswith("imdrf_") else None
            found = None
            if item.personal:
                value = personal.get(item.id)
                found = (value, _source("Sample", None, FICTIONAL)) if value else None
            elif item.source == "front_page":
                # The front page's number, entered once (stage 8: nothing typed twice).
                front = (entries.get("MFR_REPORT") or {}).get("value")
                found = (front, _source("Worksheet", None, "This worksheet's front page")) if front else None
            elif item.source == "report_type":
                found = (
                    form.report_types[0],
                    _source("Worksheet", None, "A new report starts as the form's first type"),
                )
            elif item.source == "request":
                found = (
                    (request, _source("Obligation", None, "The authority's request, as recorded")) if request else None
                )
            elif item.source:
                found = SOURCES[item.source](context)
            value, source = found if found and found[0] else (None, None)
            status = (FICTIONAL_STATUS if item.personal else FROM_RECORD) if value else None
            suggestion = None
            if annex and confirm and value and not entry.get("value") and not entry.get("confirmed"):
                # A code the mapping supplies waits for a person (0.10.77): never filed unconfirmed.
                suggestion, value, status = value, None, SUGGESTED
            if not item.personal and entry.get("value") and not derived_only(item.source):  # B4 typed before 0.10.96
                value, status = (
                    entry["value"],
                    {CONFIRMED: CONFIRMED, CHANGED: CHANGED}.get(entry.get("code_state"), ENTERED),
                )
                source = source if status == CONFIRMED else None
            elif value and entry.get("confirmed"):
                status = CONFIRMED
            # A value typed before 0.10.81 that does not fit its field is flagged, never deleted (F6): it counts as
            # missing until a person corrects it.
            problem = None
            if status == ENTERED and not entry.get("codes"):  # the code picker's codes are checked when chosen
                problem = forms.value_problem(item, value)
                if item.source == "front_page" and found and found[0] != value:
                    problem = "Differs from the front page's manufacturer report number: clear it to use that one"
            ask = None
            if item.source == "us_contact_office" and value and not problem and context.get("check_contact_office"):
                problem = contact_office_problem(context, value)
                # Only the e-mail is missing: it is asked for here, beside the field (PUT .../once contact_email).
                ask = CONTACT_EMAIL if problem and problem.startswith(EMAIL_NEEDED) else None
            if status is None:
                status = (
                    OUTSIDE
                    if item.personal and not context["sample"]
                    else (forms.NOT_USED if missing == forms.NOT_USED else missing)
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
                    "missing_class": missing,
                    "editable": not item.personal and missing != forms.NOT_USED and not derived_only(item.source),
                    "options": list(item.options) or None,
                    "note": item.note or None,
                    "kind": item.kind,
                    "problem": problem,
                    "ask": ask,
                    "by": names.get(entry.get("by")) if entry else None,
                    "at": entry.get("at") if entry else None,
                    # Codes (0.10.77): the annex the field codes, the suggestion waiting, what was suggested before a
                    # change, and how the person settled it.
                    "code_annex": annex,
                    "suggestion": suggestion,
                    "suggested": entry.get("suggested") if annex else None,
                    # Who knows it, and whether it is entered once for every report (0.10.83, D2.7).
                    "scope": scope_of(item.source),
                    "once": once_of(item.source),
                    # Fields entered together once (a US registration: its product code and its number).
                    "once_key": "US_REGISTRATION" if item.source in ("us_product_code", "us_clearance") else item.id,
                }
            )
        note = section.note or None
        if dropped and role:
            note = "Left out: an importer's or user facility's report has no section G or H (manufacturers only)."
        elif role and section.code == "FRONT":
            note = "An importer's or user facility's report number is F2, in section F."
        out.append({"code": section.code, "title": section.title, "note": note, "fields": rows})
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
            # A suggestion nobody confirmed is never frozen (0.10.77): it never reaches the form or the PDF.
            "fields": [
                {
                    key: value
                    for key, value in item.items()
                    if key not in ("editable", "suggestion", "scope", "once", "once_key", "ask")
                }
                for item in section["fields"]
            ],
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
    missing = [item["id"] for item in fields if item["status"] in (forms.MUST, SUGGESTED) or item.get("problem")]
    return {"total": len(fields), "filled": len(fields) - len(missing), "missing": missing}


def confirm_suggestions(form: forms.Form, context: dict, entries: dict, actor: str, at: str) -> dict:
    """The entries with every code the mapping suggests confirmed by ``actor`` (the sample author's own report):
    what a person does field by field on the report page."""
    out = dict(entries)
    for item in form.fields():
        if item.source and item.source.startswith("imdrf_") and not (out.get(item.id) or {}).get("value"):
            found = SOURCES[item.source](context)
            if found:
                out[item.id] = {
                    "value": found[0],
                    "code_state": CONFIRMED,
                    "suggested": found[0],
                    "by": actor,
                    "at": at,
                }
    return out
