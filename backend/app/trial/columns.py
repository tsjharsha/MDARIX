"""Reading a quality system's export as it comes: its column headers matched to the template's columns.

A header is compared after normalizing (lower case, letters and digits only: "Complaint No." -> "complaintno"), first
with the template's own column names, then with the names quality systems commonly use (TrackWise, Veeva,
MasterControl, ETQ and spreadsheet exports). A column the template does not know is left out of the import and listed
back to the uploader, never stored, so an export can be uploaded without deleting columns first; a column that would
fill a field twice keeps the first and lists the other. Matching is per template, so "description" means the complaint
description in a complaints file and the risk description in a risks file.
"""

from __future__ import annotations

import re

_NOT_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize(header: str) -> str:
    """'Complaint No.' -> 'complaintno'; '#' reads as 'number' ('Lot #' -> 'lotnumber')."""
    text = str(header or "").strip().lower().replace("#", " number ")
    return _NOT_ALNUM.sub("", text)


# Names each template column goes by in exports, per template (the column's own name always matches too).
_COMPLAINT_SYNONYMS: dict[str, tuple[str, ...]] = {
    "complaint_id": (
        "complaint id",
        "complaint number",
        "complaint no",
        "complaint ref",
        "complaint reference",
        "record id",
        "record number",
        "record no",
        "pr id",
        "pr number",
        "case number",
        "case id",
        "reference number",
        "ticket number",
        "event id",
    ),
    "product_id": (
        "product code",
        "product id",
        "product number",
        "product no",
        "product",
        "item number",
        "item code",
        "part number",
        "material number",
        "material",
        "catalog number",
        "catalogue number",
        "catalog no",
        "sku",
        "model number",
        "model",
        "device code",
    ),
    "product_name": ("product name", "device name", "product description", "item description", "trade name"),
    "description": (
        "description",
        "complaint description",
        "event description",
        "issue description",
        "problem description",
        "short description",
        "complaint details",
        "details",
        "narrative",
        "summary",
        "complaint summary",
    ),
    "version": (
        "version",
        "revision",
        "rev",
        "product version",
        "model version",
        "hardware revision",
        "software version",
    ),
    "lot_id": ("lot", "lot number", "lot no", "batch", "batch number", "batch no", "lot batch", "lot batch number"),
    "event_date": ("event date", "date of event", "incident date", "occurrence date", "date of occurrence"),
    "received_date": (
        "received date",
        "date received",
        "receipt date",
        "complaint date",
        "date opened",
        "opened date",
        "open date",
        "created date",
        "date created",
        "reported date",
        "date reported",
        "initiation date",
        "initiated date",
    ),
    "status": ("status", "state", "record status", "complaint status", "workflow status", "current state"),
    "awareness_date": (
        "awareness date",
        "date of awareness",
        "aware date",
        "date aware",
        "date became aware",
        "became aware date",
        "first awareness date",
    ),
    "severity": ("severity", "severity level", "risk level", "criticality", "priority"),
    "country": ("country", "country of occurrence", "event country", "country code", "country of event"),
    "reporter_type": (
        "reporter type",
        "reporter",
        "complainant type",
        "source type",
        "reported by",
        "reporter category",
    ),
    "complaint_type": (
        "complaint type",
        "type",
        "record type",
        "category",
        "complaint category",
        "classification",
        "complaint classification",
    ),
    "problem_code": (
        "problem code",
        "failure code",
        "defect code",
        "event code",
        "complaint code",
        "symptom code",
        "imdrf code",
        "imdrf annex a code",
        "failure mode code",
        "issue code",
    ),
    "serial_number": ("serial number", "serial no", "serial", "sn"),
    "udi": ("udi", "udi di", "device identifier", "udi device identifier"),
    "device_returned": ("device returned", "returned", "sample returned", "product returned", "return received"),
    "patient_involved": ("patient involved", "patient involvement", "patient impact", "patient affected"),
    "serious_injury": ("serious injury", "injury", "serious injury reported"),
    "death": ("death", "patient death", "death reported", "fatal"),
    "malfunction": ("malfunction", "device malfunction", "malfunction reported"),
    "use_environment": ("use environment", "environment of use", "location of use", "care setting", "use setting"),
    "user_type": ("user type", "user", "operator", "operator type", "user category"),
}

_SYNONYMS: dict[str, dict[str, tuple[str, ...]]] = {
    "complaints": _COMPLAINT_SYNONYMS,
    "products": {
        "product_id": _COMPLAINT_SYNONYMS["product_id"],
        "product_name": (
            "product name",
            "name",
            "device name",
            "product description",
            "item description",
            "trade name",
        ),
        "version": _COMPLAINT_SYNONYMS["version"],
        "product_family": ("product family", "family", "product line", "product group", "therapy area"),
        "version_release_date": (
            "version release date",
            "release date",
            "launch date",
            "effective date",
            "market release date",
        ),
    },
    "lots": {
        "lot_id": _COMPLAINT_SYNONYMS["lot_id"],
        "product_id": _COMPLAINT_SYNONYMS["product_id"],
        "version": _COMPLAINT_SYNONYMS["version"],
        "manufacture_date": (
            "manufacture date",
            "manufacturing date",
            "date of manufacture",
            "mfg date",
            "production date",
            "build date",
            "release date",
        ),
        "site_id": ("site", "site id", "site code", "plant", "manufacturing site", "plant code"),
        "quantity": (
            "quantity",
            "qty",
            "lot size",
            "batch size",
            "lot quantity",
            "units",
            "quantity released",
            "released quantity",
            "units released",
        ),
    },
    "distribution": {
        "lot_id": _COMPLAINT_SYNONYMS["lot_id"],
        "consignee": ("consignee name", "customer", "customer name", "ship to", "ship to name", "sold to name"),
        "country": ("ship to country", "destination country", "country code", "customer country"),
        "quantity": ("qty", "quantity shipped", "shipped quantity", "units shipped", "units", "shipped qty"),
        "ship_date": ("shipping date", "shipped date", "date shipped", "dispatch date", "delivery date", "ship dt"),
        "consignee_type": ("consignee type", "customer type", "account type", "channel"),
        "consignee_reference": ("customer number", "customer id", "account number", "ship to number", "sold to"),
    },
    "investigations": {
        "investigation_id": (
            "investigation id",
            "investigation number",
            "investigation no",
            "case number",
            "ncr number",
        ),
        "product_id": _COMPLAINT_SYNONYMS["product_id"],
        "question": ("question", "investigation question", "title", "subject", "problem statement", "description"),
        "status": _COMPLAINT_SYNONYMS["status"],
        "opened_date": ("opened date", "open date", "date opened", "initiated date", "initiation date", "created date"),
        "owner": ("owner", "investigator", "assigned to", "responsible"),
        "complaint_ids": (
            "complaint ids",
            "complaints",
            "related complaints",
            "complaint numbers",
            "linked complaints",
        ),
    },
    "capas": {
        "capa_id": ("capa id", "capa number", "capa no", "capa", "capa reference", "record id", "record number"),
        "title": ("title", "short description", "subject", "capa title", "description"),
        "status": _COMPLAINT_SYNONYMS["status"],
        "action_type": ("action type", "capa type", "type"),
        "source_type": ("source type", "source", "origin"),
        "source_reference": ("source reference", "source number", "source id", "originating record"),
        "product_id": _COMPLAINT_SYNONYMS["product_id"],
        "investigation_id": ("investigation id", "investigation number", "investigation no"),
        "opened_date": ("opened date", "open date", "date opened", "initiated date", "initiation date", "created date"),
        "due_date": ("due date", "target date", "target completion date", "planned completion date"),
        "effectiveness_check_date": (
            "effectiveness check date",
            "effectiveness check due date",
            "effectiveness due date",
            "verification of effectiveness date",
            "voe date",
            "verification date",
        ),
    },
    "risks": {
        "risk_id": ("risk id", "risk number", "risk no", "hazard id", "hazard number", "risk reference"),
        "product_id": _COMPLAINT_SYNONYMS["product_id"],
        "description": (
            "description",
            "risk description",
            "hazard description",
            "hazardous situation",
            "harm",
            "hazard",
        ),
        "version": _COMPLAINT_SYNONYMS["version"],
        "status": _COMPLAINT_SYNONYMS["status"],
    },
}


def match(entity: str, headers: list[str], columns: list[str]) -> dict:
    """How each header of a file reads for the template ``entity`` whose columns are ``columns``: ``fields`` (one per
    header: the template column it fills, or None when it is left out), ``mapping`` (``[{header, column}]`` for the
    headers read under another name), ``ignored`` (headers left out) and ``duplicates`` (headers left out because an
    earlier one fills the same column)."""
    by_name: dict[str, str] = {}
    for column in columns:
        by_name.setdefault(normalize(column), column)
    synonyms = _SYNONYMS.get(entity, {})
    for column in columns:
        for name in synonyms.get(column, ()):
            by_name.setdefault(normalize(name), column)
    # A template column's own name wins over any synonym that happens to equal it.
    for column in columns:
        by_name[normalize(column)] = column
    fields: list[str | None] = []
    mapping: list[dict] = []
    ignored: list[str] = []
    duplicates: list[dict] = []
    taken: dict[str, str] = {}
    # Exact template names claim their column first, so "status" beats "Record Status" when both are present.
    exact = {index: by_name.get(normalize(header)) for index, header in enumerate(headers)}
    order = sorted(
        range(len(headers)),
        key=lambda index: (0 if normalize(headers[index]) == normalize(exact[index] or "") else 1, index),
    )
    chosen: dict[int, str | None] = {}
    for index in order:
        header = headers[index]
        column = exact[index]
        if column is None or not header.strip():
            chosen[index] = None
            if header.strip():
                ignored.append(header.strip())
            continue
        if column in taken:
            chosen[index] = None
            duplicates.append({"header": header.strip(), "column": column, "kept": taken[column]})
            continue
        taken[column] = header.strip()
        chosen[index] = column
    for index, header in enumerate(headers):
        column = chosen.get(index)
        fields.append(column)
        if column is not None and normalize(header) != normalize(column):
            mapping.append({"header": header.strip(), "column": column})
    ignored = [header for header in (h.strip() for h in headers) if header in ignored]
    return {"fields": fields, "mapping": mapping, "ignored": ignored, "duplicates": duplicates}


def examples(entity: str, column: str, count: int = 2) -> list[str]:
    """Names a column goes by in exports, for a message about a missing column ("for example 'Complaint Number'")."""
    names = _SYNONYMS.get(entity, {}).get(column, ())
    return [name.title() for name in names[:count]]
