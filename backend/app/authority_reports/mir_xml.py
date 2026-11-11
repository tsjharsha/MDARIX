"""The EU MIR file (B8 step 7): one builder for the five report types of MIR 7.3.1 (schemas SB-11252, vendored in
``data/mir_forms/eu-7.3.1-SB-11252``). Root ``<incident>``, no namespace; elements in the schema's own order (read
from the type's XSD, so one table of values serves every type).

The file holds only what the report holds: a blank stays blank, never "Unknown" unless a person (or the help text's
rule, as 1.1c's) put it there. Personal fields (3.3b-f, 3.4b-g, 3.4i-n) are never written while no tenant setting
allows them (B8-D9, today's "off"). A value that does not fit its element is written as it is, so the schema refuses
it and names the block: the builder never drops a value to make a file pass. A file that fails its XSD is never
returned (``build`` raises ``MirRefused``).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from lxml import etree

from backend.app.authority_reports import forms, mir_rules, worksheet

FOLDER = Path(__file__).resolve().parents[3] / "data" / "mir_forms" / "eu-7.3.1-SB-11252"
FILES = {
    forms.MIR_INITIAL: "incident-Initial-v7.3.1.xsd",
    forms.MIR_FOLLOW_UP: "incident-Followup-v7.3.1.xsd",
    forms.MIR_COMBINED: "incident-InitialFinal-v7.3.1.xsd",
    forms.MIR_FINAL: "incident-FinalRep-v7.3.1.xsd",
    forms.MIR_FINAL_NON: "incident-FinalNonRep-v7.3.1.xsd",
}
XS = "{http://www.w3.org/2001/XMLSchema}"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
LANGUAGE = "en"

# The worksheet fields the file holds as they are (field id -> element path under <incident>).
PLAIN = {
    "1_1A": "admin_info/ncaName",
    "1_1B": "admin_info/ncaEudamedNum",
    "1_1C": "admin_info/ncaReportNo",
    "1_1D": "admin_info/refNumEudamed",
    "1_2A": "admin_info/reportDate",
    "1_2C": "admin_info/mfrAwarenessDate",
    "1_2D": "admin_info/mfrAwarenessReportDate",
    "1_2E": "admin_info/reportType",
    "1_2F": "admin_info/reportNextDate",
    "1_2G": "admin_info/eventClassification",
    "1_3_1B": "admin_info/mfrRef",
    # shortcut: 1.3.1c and 1.3.1d are one text each; the file has NCA, EUDAMED and manufacturer numbers apart. The
    # text goes in the manufacturer's number; split them when a customer reports several devices or an FSCA.
    "1_3_1C": "admin_info/mfrRefMultiDev",
    "1_3_1D": "admin_info/mfrRefFSCA",
    "1_3_1E": "admin_info/psrId",
    "2_1A": "device_info/udiDI",
    "2_1B": "device_info/udiPI",
    "2_1C": "device_info/udiDIBasic",
    "2_1D": "device_info/udiDIUnitUse",
    "2_2A": "device_info/nomenclatureSystem",
    "2_2B": "device_info/nomenclatureCode",
    "2_3A": "device_info/brandName",
    "2_3B": "device_info/deviceDescription",
    "2_3B_TEXT": "device_info/deviceNomenclature",
    "2_3C": "device_info/modelNum",
    "2_3D": "device_info/catalogNum",
    "2_3E": "device_info/serialNum",
    "2_3F": "device_info/batchNum",
    "2_3G": "device_info/deviceSoftwareVer",
    "2_3H": "device_info/deviceFirmwareVer",
    "2_3I": "device_info/deviceMfrDate",
    "2_3J": "device_info/deviceExpiryDate",
    "2_3N": "device_info/implantFacilityName",
    "2_3O": "device_info/explantFacilityName",
    "2_4E": "device_info/DevicePlacedMarket",
    "2_4F": "device_info/DeviceFulfill",
    "2_6A": "device_info/deviceAccessories",
    "2_6B": "device_info/deviceAssociated",
    "3_1A": "incident_info/clinical_event_info/eventDescription",
    "3_2B": "incident_info/clinical_event_info/numPatientsInvolved",
    "3_2C": "incident_info/clinical_event_info/currentDeviceLocation",
    "3_2D": "incident_info/clinical_event_info/deviceOperatorAtEvent",
    "3_2E": "incident_info/clinical_event_info/deviceUsage",
    "3_2F": "incident_info/clinical_event_info/patientRemedialAction",
    "3_4A": "incident_info/initial_reporter_info/initialReporterRole",
    "4_1A": "mfr_invest/manufacturersPrelimAnalysis",
    "4_1B": "mfr_invest/suspicionRelationShip",
    "4_1C": "mfr_invest/manufacturersInitialCorrecAction",
    "4_1D": "mfr_invest/furtherInvestigations",
    "4_2A": "mfr_invest/rootCauses",
    "4_2B": "mfr_invest/manufacturersWhyNotReportable",
    "4_2C": "mfr_invest/rootCauseConfirmed",
    "4_2G": "mfr_invest/correctiveAction",
    "4_2H": "mfr_invest/correctiveActionSchedule",
    "4_2I": "mfr_invest/manufacturersFinalComments",
    "4_3_3D": "mfr_invest/similarIncidents/howWereDetermined",
    "5": "other_reporting_info/AdditionalComments",
}
# IMDRF codes: up to six (eight for Annex B) choices, in the order the report lists them.
CODES = {
    "3_2A": "incident_info/clinical_event_info/imdrfCodeChoice",
    "3_3A_E": "incident_info/patient_info/imdrfClinicalCodeChoice",
    "3_3A_F": "incident_info/patient_info/imdrfHealthCodeChoice",
    "4_2E_B": "mfr_invest/imdrfTypeInvestigationCodeChoice",
    "4_2E_C": "mfr_invest/imdrfInvestigationFindingsCodeChoice",
    "4_2E_D": "mfr_invest/imdrfInvestigationConclusionCodeChoice",
    "4_2F": "mfr_invest/imdrfComponentCodeChoice",
}
# Fields read by a rule of their own below (ranges, parts, choices with details, the 4.3 table).
SHAPED = frozenset(
    {"1_2B", "1_3_1A", "1_3_1F", "2_3K", "2_3L", "2_3M", "2_3P_NB", "2_3P_CERT", "2_3Q", "2_4", "2_5", "3_4H", "4_2D"}
    | {"4_3_1A", "4_3_3A", "4_3_3B", "4_3_3C"}
)
# The parties' parts (step 6) in the file: element -> attribute of the responsible party.
_PARTY = {
    "Name": "organisation",
    "SRN": "srn",
    "ContactPersonFirstName": "contact_first_name",
    "ContactPersonSecondName": "contact_last_name",
    "Street": "street",
    "City": "city",
    "Country": "country_code",
    "Postcode": "postcode",
    "Phone": "contact_phone",
    "EmailAddress": "contact_email",
}
_MFR = {"Name": "mfrName", "SRN": "mfrSRN", "Street": "mfrOrgStreet", "City": "mfrCity", "Country": "mfrCountry"}
_MFR |= {"Postcode": "mfrPostcode", "Phone": "mfrPhone", "EmailAddress": "mfrEmailAddress"}
_MFR |= {"ContactPersonFirstName": "mfrContactPersonFirstName", "ContactPersonSecondName": "mfrContactPersonSecondName"}
_AR = {key: "AR" + key for key in _PARTY} | {"Postcode": "ARPostCode"}
# The parts a party needs in the file: the schema's required ones for the manufacturer; the same for the authorised
# representative (the help text's 1.3.3, stricter than the schema's all-optional block, B8-D6).
NEEDED_PARTS = ("contact_first_name", "contact_last_name", "street", "city", "postcode", "country_code")
NEEDED_PARTS += ("contact_phone", "contact_email")
PART_LABELS = {
    "contact_first_name": "contact's first name",
    "contact_last_name": "contact's last name",
    "street": "street",
    "city": "city",
    "postcode": "postcode",
    "country_code": "country",
    "contact_phone": "phone",
    "contact_email": "e-mail",
}
_SUBMITTER = {
    "manufacturer": ("reporterMfr", "Manufacturer"),
    "authorised representative": ("reporterAR", "Authorised representative"),
    "other": ("reporterOther", "Others"),
}
# shortcut: 1.3.4 (a submitter other than the manufacturer or AR) is one text; the file wants its parts
# (reporterDetails). The report is still built without them; add a parts form like step 6's when a customer needs it.
NOT_IN_FILE = frozenset({"1_3_4"})
# 1.3.2 and 1.3.3: the parties on the worksheet; the file takes their parts (``file_values``).
PARTY_FIELDS = frozenset({"1_3_2A", "1_3_2B", "1_3_2C", "1_3_3"})
_CODE = re.compile(r"[A-G]\d{2,7}")
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
_YES_NO = re.compile(r"^\s*(yes|no)\b[\s,:;.-]*(.*)$", re.IGNORECASE | re.DOTALL)
_LEGISLATION = re.compile(r"\b(aimdd|mdd|ivdd|ivdr|mdr)\b", re.IGNORECASE)


class MirRefused(ValueError):
    """The file would be refused: the blocks missing and the schema's errors, each naming its block."""

    def __init__(self, missing: list[str], errors: list[str]):
        super().__init__("; ".join([*missing, *errors]))
        self.missing, self.errors = missing, errors


# ------------------------------------------------------------------------------------------------- the schema
@lru_cache(maxsize=len(FILES))
def _schema(report_type: str) -> etree.XMLSchema:
    return etree.XMLSchema(etree.parse(str(FOLDER / FILES[report_type])))


@lru_cache(maxsize=len(FILES))
def _layout(report_type: str) -> tuple:
    """The type's elements under <incident>, in order: (name, children or None, enumeration or None, max occurs)."""
    root = etree.parse(str(FOLDER / FILES[report_type])).getroot()
    types = {node.get("name"): node for node in root if node.get("name") and node.tag != XS + "element"}

    def enum(node) -> tuple[str, ...] | None:
        found = tuple(item.get("value") for item in node.iter(XS + "enumeration")) if node is not None else ()
        return found or None

    def walk(node) -> list:
        out = []
        for child in node:
            if child.tag in (XS + "sequence", XS + "choice", XS + "all"):
                out.extend(walk(child))
            elif child.tag == XS + "element":
                named = types.get(child.get("type") or "")
                complex_ = child.find(XS + "complexType")
                if named is not None and named.tag == XS + "complexType":
                    complex_ = named
                simple = (
                    named if named is not None and named.tag == XS + "simpleType" else child.find(XS + "simpleType")
                )
                kids = tuple(walk(complex_)) if complex_ is not None else None
                out.append((child.get("name"), kids, None if kids else enum(simple), child.get("maxOccurs", "1")))
        return out

    incident = next(node for node in root if node.tag == XS + "element" and node.get("name") == "incident")
    return tuple(walk(incident.find(XS + "complexType")))


def _fit(value: str, choices: tuple[str, ...] | None) -> str:
    """A choice in the schema's own spelling (case and spaces aside): "UMDNS (ECRI)" is "UMDNS(ECRI)"."""
    if not choices:
        return value
    key = re.sub(r"\s+", "", value).lower()
    return next((choice for choice in choices if re.sub(r"\s+", "", choice).lower() == key), value)


def _write(parent, layout, values: dict, prefix: str, used: set) -> None:
    for name, kids, choices, most in layout:
        path = prefix + name
        if kids is not None:
            element = etree.SubElement(parent, name)
            _write(element, kids, values, path + "/", used)
            if len(element) == 0:
                parent.remove(element)
            continue
        found = values.get(path)
        if found is None or found == []:
            continue
        used.add(path)
        for text in found if isinstance(found, list) else [found]:
            etree.SubElement(parent, name).text = _fit(str(text), choices)
        if isinstance(found, list) and most == "1" and len(found) > 1:
            raise MirRefused([], [f"{_block(name)}: one value only"])


# ------------------------------------------------------------------------------------------------- the values
def _day(text: str) -> str:
    found = _DAY.fullmatch(text.strip())
    return found.group(0) if found else text


def _range(text: str) -> tuple[str, str]:
    found = forms._RANGE.match(text.strip())
    return (found.group(1), found.group(2) or found.group(1)) if found else (text, text)


def _codes(text: str) -> list[str]:
    """Each part's code ("A090807 High Readings; A0401 ..." -> A090807, A0401); a part that is no code stays whole,
    so the schema refuses it."""
    out = []
    for part in filter(None, (piece.strip() for piece in text.split(";"))):
        head = part.split()[0]
        out.append(head if _CODE.fullmatch(head) else part)
    return out


def _yes_no(text: str) -> tuple[str, str]:
    found = _YES_NO.match(text)
    return (found.group(1).capitalize(), found.group(2).strip()) if found else (text, "")


def country_code(text: str | None) -> str | None:
    """An ISO 3166 alpha-2 code from a code or a country's name (the Commission's list), else the text as it is."""
    words = " ".join((text or "").split())
    if re.fullmatch(r"[A-Za-z]{2}", words):
        return words.upper()
    row = worksheet.eu_ncas().get(words.lower())
    return row["code"] if row else words or None


def _risk_class(text: str) -> dict:
    """2.4: the legislation and the class. MDARIX's EU registrations hold the MDR (I to III) and IVDR (A to D) classes;
    a legacy device is written with its directive ("MDD class IIb"). Starter, for your consultant to confirm."""
    low = text.strip().lower()
    if "unknown" in low:
        return {"device_info/AppLegislationUnknown": "Applicable legislation unknown"}
    if "before" in low:
        return {"device_info/deviceClass": text.strip()}
    found = _LEGISLATION.search(low)
    rest = re.sub(r"^class\s*", "", _LEGISLATION.sub("", low).strip(" :,-"))
    law = found.group(1) if found else ("ivdr" if re.fullmatch(r"[a-d]", rest) else "mdr")
    value = f"class {rest}" if re.fullmatch(r"i{1,3}[ab]?|i[sm]{1,2}|[a-d]", rest) else rest  # the schema's case: _fit
    element = {"mdr": "deviceClassMDR", "ivdr": "deviceClassIVDR", "mdd": "deviceClassMDD", "aimdd": "deviceClassMDD"}
    return {f"device_info/{element.get(law, 'deviceClassIVDD')}": value}


def _distribution(text: str) -> dict:
    """2.5: EEA countries (with CH, TR and Northern Ireland) as the schema's codes; "all" as its one choice; anything
    else, as written, in other countries."""
    eea = dict.fromkeys(next(c for n, _, c, _ in _device_layout() if n == "distributionEEA"))
    codes, other = [], []
    for part in filter(None, (piece.strip() for piece in re.split(r"[;,]", text))):
        if part.lower().startswith("all eea"):
            codes.append("ALL")
            continue
        code = country_code(part)
        (codes if code in eea else other).append(code if code in eea else part)
    out: dict = {"device_info/distribution/distributionEEA": [code for code in codes if code != "ALL"]}
    if "ALL" in codes:
        out["device_info/distribution/distribution_all"] = "All EEA, Turkey and Northern Ireland"
    if other:
        out["device_info/distribution/otherCountries"] = ", ".join(other)
    return out


def _device_layout():
    device = next(kids for name, kids, _, _ in _layout(forms.MIR_INITIAL) if name == "device_info")
    return next(kids for name, kids, _, _ in device if name == "distribution")


def _duration(text: str) -> dict:
    parts = {
        unit: re.search(rf"(\d+)\s*{word}", text, re.IGNORECASE)
        for unit, word in (("numYears", "y"), ("numMonths", "mo"), ("numDays", "d"))
    }
    found = {f"device_info/implantDuration/{unit}": hit.group(1) for unit, hit in parts.items() if hit}
    return found or {"device_info/implantDuration/numYears": text}


def _market_date(text: str) -> dict:
    choice = next((item for item in forms._MIR_MARKET_DATE if text.lower().startswith(item.lower())), None)
    when = re.search(r"(\d{4})(?:-(\d{1,2}))?", text)
    out = {"device_info/deviceMarketDateType": choice or text}
    if when:
        out["device_info/deviceMarketDate/year"] = when.group(1)
        if when.group(2):
            out["device_info/deviceMarketDate/month"] = str(int(when.group(2)))
    return out


def _numbers(text: str, first: str, second: str, digits: bool) -> dict:
    parts = [piece.strip() for piece in re.split(r"[;,]", text) if piece.strip()]
    if digits:
        parts = [re.sub(r"(?i)^nb\s*", "", piece) for piece in parts]
    out = {f"device_info/{first}": parts[0]} if parts else {}
    if len(parts) > 1:
        out[f"device_info/{second}"] = parts[1] if len(parts) == 2 else parts[1:]
    return out


def _similar(values: dict) -> dict:
    """4.3: the identification (4.3.1a), basis (4.3.3a), denominator (4.3.3b) and the table of periods (4.3.3c)."""
    out: dict = {}
    base = "mfr_invest/similarIncidents/"
    text = values.get("4_3_1A")
    if text:
        low = text.lower()
        named = {annex: f"annex {annex.lower()}" in low for annex in "AC"}
        for annex, said in named.items():
            if said:
                out[base + f"similarIncImdrfCodesAnnex{annex}"] = "Yes"
        if not any(named.values()):
            out[base + "similarIncOtherReportingCodes"] = "Yes"
            out[base + "similarIncOtherReportingCodesText"] = text
    basis = values.get("4_3_3A")
    if basis:
        choice = next((item for item in forms._MIR_VARIANT if basis.lower().startswith(item.lower())), None)
        out[base + "similarVariant"] = ("Other" if choice == "Other variant" else choice) or basis
        details = basis[len(choice) :].strip(" :,-") if choice else ""
        if details:
            out[base + "similarVariantDetails"] = details
    count = values.get("4_3_3B")
    if count:
        known = next((c for n, _, c, _ in _similar_layout() if n == "numberBasedOn"))
        if _fit(count, known) in known:
            out[base + "numberBasedOn"] = count
        else:
            out[base + "numberBasedOn"], out[base + "numberBasedOnOther"] = "Other", count
    table = values.get("4_3_3C")
    if table:
        out |= _periods(table)
    return out


def _similar_layout():
    invest = next(kids for name, kids, _, _ in _layout(forms.MIR_INITIAL) if name == "mfr_invest")
    return next(kids for name, kids, _, _ in invest if name == "similarIncidents")


PERIODS = ("timePeriodN", "timePeriodN-1", "timePeriodN-2", "timePeriodN-3")
PERIOD_KEYS = {
    "start": "startDate",
    "end": "endDate",
    "country_incidents": "countrySimInc",
    "eea_incidents": "eeaChTrSimInc",
    "world_incidents": "worldSimInc",
    "country_devices": "countrySimDev",
    "eea_devices": "eeaChTrSimDev",
    "world_devices": "worldSimDev",
}


def _periods(text: str) -> dict:
    """4.3.3c, stored as one structured entry (step 10): a JSON list of up to four periods, N first, each with the
    keys of ``PERIOD_KEYS``. Text that is not the table goes in N's first count, so the schema refuses it."""
    base = "mfr_invest/similarIncidents/"
    try:
        rows = json.loads(text)
    except ValueError:
        rows = None
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows) or len(rows) > len(PERIODS):
        return {base + "timePeriodN/countrySimInc": text}
    out = {}
    for name, row in zip(PERIODS, rows):
        for key, element in PERIOD_KEYS.items():
            if row.get(key) not in (None, ""):
                out[f"{base}{name}/{element}"] = str(row[key])
    return out


def _party_of(parties, role: str):
    return next((item for item in parties if getattr(item, "role", None) == role), None)


def file_values(values: dict, parties, *, udi_entity: str | None = None) -> dict:
    """Every element's value by its path under <incident>, from the report's values (field id -> text), the EU
    responsible parties (with their parts) and the product's UDI issuing entity (B8-D11)."""
    out: dict = {PLAIN[key]: text for key, text in values.items() if key in PLAIN}
    for key in ("1_2A", "1_2C", "1_2D", "1_2F", "2_3I", "2_3J"):
        if key in values:
            out[PLAIN[key]] = _day(values[key])
    for key, path in CODES.items():
        if key in values:
            out |= {f"{path}{index}": code for index, code in enumerate(_codes(values[key]), 1)}
    if "1_2B" in values:
        out["admin_info/adverseEventDateFrom"], out["admin_info/adverseEventDateTo"] = _range(values["1_2B"])
    for key, element in (("2_3K", "Implanted"), ("2_3L", "Explanted")):
        if key in values:
            start, end = _range(values[key])
            out[f"device_info/{element}DateFrom"], out[f"device_info/{element}DateTo"] = start, end
    if "2_3M" in values:
        out |= _duration(values["2_3M"])
    if "2_3P_NB" in values:
        out |= _numbers(values["2_3P_NB"], "nbIdNum", "nbIdNum2", True)
    if "2_3P_CERT" in values:
        out |= _numbers(values["2_3P_CERT"], "nbCertNum", "nbCertNum2", False)
    if "2_3Q" in values:
        out |= _market_date(values["2_3Q"])
    if "2_4" in values:
        out |= _risk_class(values["2_4"])
    if "2_5" in values:
        out |= _distribution(values["2_5"])
    if "3_4H" in values:
        out["incident_info/initial_reporter_info/healthcareFacilityCountry"] = country_code(values["3_4H"])
    if "1_3_1F" in values:
        answer, detail = _yes_no(values["1_3_1F"])
        out["admin_info/pmcfpmpfQuestion"] = answer
        if detail:
            out["admin_info/pmcfpmpfId"] = detail
    if "4_2D" in values:
        answer, detail = _yes_no(values["4_2D"])
        out["mfr_invest/riskAssReviewed"] = answer
        if detail:
            out["mfr_invest/" + ("rationaleNoReview" if answer == "No" else "riskAssResults")] = detail
    out |= _similar(values)
    for key, path in (("2_1A", "udiDI_Entity"), ("2_1C", "Basic_Entity"), ("2_1D", "UnitofUse_Entity")):
        entity = udi_entity or worksheet.udi_issuing_entity(values.get("2_1A"))
        if key in values and entity:
            out[f"device_info/{path}"] = entity
    submitter = (values.get("1_3_1A") or "").strip()
    holder, status = _SUBMITTER.get(submitter.lower(), (None, None))
    if submitter and holder is None:
        holder, status = "reporterMfr", submitter  # not one of the three: the schema refuses it, naming 1.3.1a
    if holder:
        base = f"admin_info/contact_info/{holder}/"
        out[base + "statusReporter"] = status
        maker, rep = _party_of(parties, "MANUFACTURER"), _party_of(parties, "AUTHORISED_REPRESENTATIVE")
        for party, block, names in ((maker, "mfrDetails", _MFR), (rep, "arDetails", _AR)):
            if party is not None:
                for key, attribute in _PARTY.items():
                    text = getattr(party, attribute, None)
                    if text:
                        out[f"{base}{block}/{names[key]}"] = country_code(text) if key == "Country" else text
        for key, path in (("1_3_2A", "mfrName"), ("1_3_2B", "mfrSRN")):  # as the report shows them
            if values.get(key):
                out[f"{base}mfrDetails/{path}"] = values[key]
    return out


# ------------------------------------------------------------------------------------------------- the file
def _block(name: str) -> str:
    """The MIR block an element belongs to ("reportNextDate" -> "1.2f Expected date of next report"), from the rule
    book's XML paths; a numbered place (imdrfCodeChoice7) by its first one's block."""
    key = re.sub(r"\d+$", "", name)
    for row in mir_rules.rows(forms.EU_MIR.code):
        for path in row["xpath"].split(";"):
            if key in [re.sub(r"\d+$", "", part) for part in path.strip().split("/")[2:]]:
                return f"{row['block']} {row['label']}"
    return name


def _named(message: str) -> str:
    found = re.search(r"Expected is (?:one of )?\( ([^)]+) \)", message)
    names = [name.strip() for name in found.group(1).split(",")] if found else []
    element = re.match(r"Element '([^']+)'", message)
    blocks = [_block(name) for name in names] or ([_block(element.group(1))] if element else [])
    return f"{', '.join(dict.fromkeys(blocks))}: {message}" if blocks else message


def validate(xml: bytes, report_type: str) -> list[str]:
    """The schema errors of a file against its type's XSD (none: the Commission's schema takes it), each naming its
    MIR block."""
    schema = _schema(report_type)
    if schema.validate(etree.fromstring(xml)):
        return []
    return [_named(error.message) for error in schema.error_log]


def missing(values: dict, parties, report_type: str) -> list[str]:
    """The blocks the report type needs that hold nothing (the rule book's "M"), and the parts a party in the file
    lacks (1.3.2, 1.3.3)."""
    needed = mir_rules.mandatory_fields(forms.EU_MIR.code, report_type)
    out = [f"{block} ({field})" for field, block in needed.items() if not values.get(field)]
    for role, block in (("MANUFACTURER", "1.3.2"), ("AUTHORISED_REPRESENTATIVE", "1.3.3")):
        party = _party_of(parties, role)
        if party is not None:
            lacking = [PART_LABELS[part] for part in NEEDED_PARTS if not getattr(party, part, None)]
            if lacking:
                out.append(f"{block} {party.organisation}: {', '.join(lacking)} (Settings, Products)")
    return out


def build(values: dict, parties, *, report_type: str, now: datetime, udi_entity: str | None = None) -> bytes:
    """The MIR XML of a report of this type, valid against its XSD, or ``MirRefused``: never a partial file.
    ``now`` is the moment it is sent for approval (``sCreateTimeStamp``); the same values build the same bytes."""
    found = file_values(values, parties, udi_entity=udi_entity)
    root = etree.Element("incident", nsmap={"xsi": XSI})
    root.set(f"{{{XSI}}}noNamespaceSchemaLocation", FILES[report_type])
    root.set("sCreateTimeStamp", now.isoformat(timespec="seconds"))
    root.set("sFormLanguage", LANGUAGE)
    used: set = set()
    _write(root, _layout(report_type), found, "", used)
    stray = sorted(set(found) - used)
    errors = [f"{_block(path.rsplit('/', 1)[-1])}: not a place in this report type's file ({path})" for path in stray]
    xml = etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)
    errors += validate(xml, report_type)
    if errors:
        raise MirRefused([], errors)
    return xml


def prepare(values: dict, parties, *, report_type: str, now: datetime, udi_entity: str | None = None) -> dict:
    """The file as Send for approval checks it: the blocks missing; when none, the file or the schema's errors."""
    lacking = missing(values, parties, report_type)
    if lacking:
        return {"missing": lacking, "errors": [], "xml": None}
    try:
        return {
            "missing": [],
            "errors": [],
            "xml": build(values, parties, report_type=report_type, now=now, udi_entity=udi_entity),
        }
    except MirRefused as refused:
        return {"missing": refused.missing, "errors": refused.errors, "xml": None}
