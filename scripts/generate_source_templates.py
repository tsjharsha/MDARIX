"""Write the CSV templates for the simulated customer source systems (TrackWise Digital, Teamcenter, SAP, ...).

Each template uses the column names that system uses, filled with one connected synthetic story: the AquaFlow 200
pump (Teamcenter, SAP, TrackWise, MES, LIMS, risk file) and the AquaFlow 300 pump (Windchill, Oracle, Veeva). The
same product, lot and supplier numbers appear in every system, so MDARIX can link a complaint to its lot, the lot to
its components and the components to their suppliers.

The data dictionary (_data_dictionary.csv) says, for every column, which MDARIX field the standard mapping fills.
The standard mappings themselves go to backend/app/access/standard_mappings.json, served to Mapping Studio. Run:  python scripts/generate_source_templates.py   (writes data/source-templates/)
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "source-templates"


def col(name: str, required: bool, data_type: str, description: str) -> dict:
    return {"name": name, "required": required, "type": data_type, "description": description}


# The MDARIX standard mapping of each template: which MDARIX record it fills (a mapping target in
# backend/app/access/connector_mapping.py), source column -> MDARIX field, and optionally the records to keep
# ("filter": column, values) and fixed values for fields the source does not carry ("defaults"). A file that mixes
# kinds of records (items that are products or components) has one mapping per kind.
def std(target: str, fields: dict[str, str], keep: tuple[str, list[str]] | None = None, defaults=None) -> dict:
    return {"target": target, "fields": fields, "filter": keep, "defaults": defaults or {}}


SAME = lambda *names: {name: name for name in names}  # noqa: E731

STANDARD = {
    ("TRACKWISE", "complaints.csv"): [
        std(
            "Complaint",
            {
                "complaint_number": "complaint_id",
                "product_code": "product_id",
                "product_revision": "version",
                "problem_description": "description",
                "lot_number": "lot_id",
                **SAME("event_date", "received_date", "awareness_date", "status", "severity", "country"),
                **SAME("reporter_type", "complaint_type", "problem_code", "serial_number", "udi"),
                **SAME("device_returned", "patient_involved", "serious_injury", "death", "malfunction"),
            },
        )
    ],
    ("TRACKWISE", "investigations.csv"): [
        std(
            "Investigation",
            {
                "investigation_number": "investigation_id",
                "product_code": "product_id",
                "investigation_question": "question",
                "related_complaints": "complaint_ids",
                **SAME("status", "opened_date", "owner"),
            },
        )
    ],
    ("TRACKWISE", "capas.csv"): [
        std(
            "Capa",
            {
                "capa_number": "capa_id",
                "product_code": "product_id",
                **SAME("title", "status", "action_type", "source_type", "source_reference"),
                **SAME("opened_date", "due_date", "effectiveness_check_date"),
            },
        )
    ],
    ("SALESFORCE_SERVICE", "cases.csv"): [
        std(
            "Evidence",
            {
                "case_number": "evidence_id",
                "subject": "title",
                "description": "content",
                "product_code": "product_id",
                "opened_datetime": "effective_date",
            },
            defaults={"evidence_type": "Service case"},
        )
    ],
    ("VEEVA_QMS", "quality_events.csv"): [
        std(
            "Complaint",
            {
                "event_number": "complaint_id",
                "product_code": "product_id",
                "product_version": "version",
                "lot_number": "lot_id",
                "opened_date": "received_date",
                **SAME("description", "event_date", "severity", "status"),
            },
            keep=("event_type", ["Complaint"]),
        )
    ],
    ("VEEVA_QMS", "capas.csv"): [
        std(
            "Capa",
            {
                "capa_number": "capa_id",
                "source_event": "source_reference",
                "product_code": "product_id",
                **SAME("title", "action_type", "opened_date", "due_date", "status"),
            },
        )
    ],
    ("VEEVA_QMS", "documents.csv"): [
        std(
            "Evidence",
            {
                "document_number": "evidence_id",
                "document_type": "evidence_type",
                "lifecycle_state": "review_status",
                "product_code": "product_id",
                "file_name": "document_ref",
                **SAME("title", "effective_date"),
            },
        )
    ],
    ("TEAMCENTER", "items.csv"): [
        std(
            "Product",
            {"item_number": "product_id", "name": "product_name", "product_family": "product_family"},
            keep=("item_type", ["Product"]),
        ),
        std(
            "Component",
            {
                "item_number": "component_id",
                "name": "component_name",
                "description": "description",
                "lifecycle": "status",
            },
            keep=("item_type", ["Component", "Assembly", "Software"]),
        ),
    ],
    ("TEAMCENTER", "item_revisions.csv"): [
        std(
            "Product",
            {
                "product_id": "product_id",
                "item_name": "product_name",
                "revision": "version",
                "release_date": "version_release_date",
            },
        )
    ],
    ("TEAMCENTER", "bom_lines.csv"): [
        std(
            "BomLine",
            {
                "parent_item_number": "product_id",
                "parent_revision": "version",
                "child_item_number": "component_id",
                "effective_from": "effective_date",
            },
        )
    ],
    ("TEAMCENTER", "change_notices.csv"): [
        std(
            "Change",
            {
                "change_number": "change_id",
                "affected_items": "affected_ids",
                **SAME("change_type", "description", "effective_date"),
            },
        )
    ],
    ("TEAMCENTER", "requirements.csv"): [
        std(
            "Requirement",
            {
                "product_code": "product_id",
                "revision": "version",
                "trace_to_risk": "risk_id",
                **SAME("requirement_id", "requirement_type", "text", "status"),
            },
        )
    ],
    ("WINDCHILL", "parts.csv"): [
        std(
            "Product",
            {"number": "product_id", "name": "product_name", "product_line": "product_family"},
            keep=("part_type", ["End item"]),
        ),
        std(
            "Component",
            {"number": "component_id", "name": "component_name", "state": "status"},
            keep=("part_type", ["Component", "Software"]),
        ),
    ],
    ("WINDCHILL", "part_versions.csv"): [
        std(
            "Product",
            {
                "number": "product_id",
                "name": "product_name",
                "version": "version",
                "released_date": "version_release_date",
            },
        )
    ],
    ("WINDCHILL", "bom.csv"): [
        std("BomLine", {"parent_number": "product_id", "parent_version": "version", "child_number": "component_id"})
    ],
    ("WINDCHILL", "change_notices.csv"): [
        std(
            "Change",
            {
                "number": "change_id",
                "description": "description",
                "affected_parts": "affected_ids",
                "resolution_date": "effective_date",
            },
            defaults={"change_type": "Change notice"},
        )
    ],
    ("SAP_ERP", "materials.csv"): [
        std(
            "Product",
            {"MATNR": "product_id", "MAKTX": "product_name", "REVLV": "version"},
            keep=("MTART", ["FERT"]),
        ),
        std(
            "Component",
            {"MATNR": "component_id", "MAKTX": "component_name", "REVLV": "revision"},
            keep=("MTART", ["ROH", "HALB"]),
        ),
    ],
    ("SAP_ERP", "plants.csv"): [std("Site", {"WERKS": "site_id", "NAME1": "site_name", "ORT01": "location"})],
    ("SAP_ERP", "batches.csv"): [
        std(
            "Lot",
            {
                "CHARG": "lot_id",
                "MATNR": "product_id",
                "REVLV": "version",
                "HSDAT": "manufacture_date",
                "WERKS": "site_id",
            },
        )
    ],
    ("SAP_ERP", "batch_where_used.csv"): [
        std(
            "LotGenealogy",
            {"CHARG_PARENT": "lot_id", "MATNR_COMPONENT": "component_id", "CHARG_COMPONENT": "component_lot_id"},
        )
    ],
    ("SAP_ERP", "vendors.csv"): [std("Supplier", {"LIFNR": "supplier_id", "NAME1": "supplier_name"})],
    ("SAP_ERP", "source_list.csv"): [
        std("ComponentSupplier", {"MATNR": "component_id", "LIFNR": "supplier_id", "VDATU": "effective_date"})
    ],
    ("ORACLE_ERP", "items.csv"): [
        std(
            "Product",
            {"ITEM_NUMBER": "product_id", "DESCRIPTION": "product_name", "REVISION": "version"},
            keep=("ITEM_TYPE", ["FG"]),
        ),
        std(
            "Component",
            {"ITEM_NUMBER": "component_id", "DESCRIPTION": "component_name", "REVISION": "revision"},
            keep=("ITEM_TYPE", ["PURCHASED", "SUBASSEMBLY"]),
        ),
    ],
    ("ORACLE_ERP", "organizations.csv"): [
        std("Site", {"ORGANIZATION_CODE": "site_id", "ORGANIZATION_NAME": "site_name", "LOCATION_CODE": "location"})
    ],
    ("ORACLE_ERP", "lots.csv"): [
        std(
            "Lot",
            {
                "LOT_NUMBER": "lot_id",
                "ITEM_NUMBER": "product_id",
                "REVISION": "version",
                "ORIGINATION_DATE": "manufacture_date",
                "ORGANIZATION_CODE": "site_id",
            },
        )
    ],
    ("ORACLE_ERP", "suppliers.csv"): [
        std("Supplier", {"SUPPLIER_NUMBER": "supplier_id", "VENDOR_NAME": "supplier_name"})
    ],
    ("ORACLE_ERP", "approved_supplier_list.csv"): [
        std("ComponentSupplier", {"ITEM_NUMBER": "component_id", "SUPPLIER_NUMBER": "supplier_id"})
    ],
    ("MES", "production_orders.csv"): [
        std(
            "Lot",
            {
                "lot_number": "lot_id",
                "material_number": "product_id",
                "revision": "version",
                "end_date": "manufacture_date",
                "site_code": "site_id",
            },
        )
    ],
    ("MES", "genealogy.csv"): [
        std(
            "LotGenealogy",
            {"lot_number": "lot_id", "component_material": "component_id", "component_lot": "component_lot_id"},
        )
    ],
    ("LIMS", "test_results.csv"): [
        std(
            "Evidence",
            {
                "result_id": "evidence_id",
                "test_method": "title",
                "result": "content",
                "tested_date": "effective_date",
                "review_status": "review_status",
            },
            defaults={"evidence_type": "Test result"},
        )
    ],
    ("RISK", "risks.csv"): [
        std(
            "Risk",
            {
                "risk_id": "risk_id",
                "product_code": "product_id",
                "revision": "version",
                "harm": "description",
                "status": "status",
            },
        )
    ],
    ("RISK", "failure_modes.csv"): [
        std(
            "FailureMode",
            {
                "fmea_id": "failure_mode_id",
                "failure_mode": "failure_mode_name",
                "effect": "description",
                "linked_risk_id": "risk_id",
            },
        )
    ],
    ("RISK", "risk_controls.csv"): [
        std("Control", SAME("control_id", "risk_id", "control_type", "description", "status"))
    ],
    ("COUPA", "suppliers.csv"): [
        std("Supplier", {"supplier_number": "supplier_id", "name": "supplier_name", "status": "status"})
    ],
    ("COUPA", "supplier_certificates.csv"): [
        std(
            "Evidence",
            {
                "certificate_number": "evidence_id",
                "certificate_type": "title",
                "status": "review_status",
                "issue_date": "effective_date",
            },
            defaults={"evidence_type": "Supplier certificate"},
        )
    ],
}
# The order in which to load records, so that every record finds the ones it refers to.
LOAD_ORDER = [
    "Supplier",
    "Site",
    "Product",
    "Component",
    "BomLine",
    "ComponentSupplier",
    "Lot",
    "LotGenealogy",
    "Risk",
    "FailureMode",
    "Control",
    "Requirement",
    "Complaint",
    "Investigation",
    "Capa",
    "Change",
    "Evidence",
]
MAPPINGS_FILE = Path(__file__).resolve().parents[1] / "backend" / "app" / "access" / "standard_mappings.json"


def transform_for(target: str, column: str) -> str:
    if column.endswith("_date"):
        return "date"
    if column == "status" and target == "Complaint":
        return "lower"
    return "trim"


def standard_mappings() -> list[dict]:
    """Every standard mapping in the format MDARIX stores (mapping_rules), in load order."""
    out = []
    for (application, file), specs in STANDARD.items():
        for spec in specs:
            rules: dict = {
                source: {
                    "target_field": f"{spec['target']}.{column}",
                    "transform": transform_for(spec["target"], column),
                }
                for source, column in spec["fields"].items()
            }
            if spec["filter"]:
                rules["_filter"] = {"field": spec["filter"][0], "in": spec["filter"][1]}
            if spec["defaults"]:
                rules["_defaults"] = spec["defaults"]
            record = file.removesuffix(".csv")
            suffix = f"_{spec['target'].upper()}" if len(specs) > 1 else ""
            out.append(
                {
                    "application": application,
                    "record": record,
                    "code": f"{application}_{record.upper()}{suffix}"[:100],
                    "target_entity": spec["target"],
                    "mapping_rules": rules,
                }
            )
    return sorted(out, key=lambda item: (LOAD_ORDER.index(item["target_entity"]), item["code"]))


APPLICATIONS: list[dict] = [
    {
        "code": "TRACKWISE",
        "name": "TrackWise Digital (quality management)",
        "simulator": "8101",
        "files": [
            {
                "file": "complaints.csv",
                "record": "Complaint",
                "columns": [
                    col("complaint_id", True, "text", "TrackWise internal record ID"),
                    col("complaint_number", True, "text", "Complaint number people use"),
                    col("product_code", True, "text", "Product (same number as in PLM)"),
                    col("product_revision", False, "text", "Product version/revision"),
                    col("event_date", False, "date YYYY-MM-DD", "When the event happened"),
                    col(
                        "received_date",
                        False,
                        "date YYYY-MM-DD",
                        "When the company received it",
                    ),
                    col(
                        "awareness_date", False, "date YYYY-MM-DD", "Regulatory awareness date (reporting clock starts)"
                    ),
                    col("opened_date", False, "date YYYY-MM-DD", "When the record was opened"),
                    col("country", False, "ISO country code", "Country where the event happened"),
                    col(
                        "reporter_type",
                        False,
                        "text",
                        "Healthcare professional, User facility, Patient or caregiver, Distributor",
                    ),
                    col("complaint_type", False, "text", "Device malfunction, Device performance, Labeling, Packaging"),
                    col("problem_code", False, "text", "Company or IMDRF problem code"),
                    col(
                        "problem_description",
                        True,
                        "text",
                        "What happened, without personal data",
                    ),
                    col("severity", False, "text", "Minor, Major, Critical"),
                    col("lot_number", False, "text", "Lot/batch (same number as in ERP)"),
                    col("serial_number", False, "text", "Device serial number"),
                    col("udi", False, "text", "Unique device identifier"),
                    col("device_returned", False, "Y/N", "Device returned for evaluation"),
                    col("patient_involved", False, "Y/N", "A patient was involved"),
                    col("serious_injury", False, "Y/N", "Serious injury reported"),
                    col("death", False, "Y/N", "Death reported"),
                    col("malfunction", False, "Y/N", "Device malfunction"),
                    col("status", False, "text", "Open, Under investigation, Closed"),
                    col("investigation_number", False, "text", "Linked investigation"),
                    col(
                        "created_at",
                        False,
                        "date-time ISO 8601 UTC",
                        "Record created in TrackWise",
                    ),
                    col(
                        "updated_at",
                        False,
                        "date-time ISO 8601 UTC",
                        "Last change in TrackWise",
                    ),
                ],
                "rows": [
                    [
                        "TWD-C-000981",
                        "CMP-10021",
                        "PUMP-200",
                        "Rev D",
                        "2026-08-28",
                        "2026-08-30",
                        "2026-08-30",
                        "2026-08-31",
                        "IE",
                        "Healthcare professional",
                        "Device malfunction",
                        "ALM-OCC-FALSE",
                        "Occlusion alarm sounded with no occlusion present; infusion stopped and was restarted. Device returned for evaluation.",
                        "Major",
                        "L24-0815",
                        "SN-200D-004471",
                        "(01)05012345678900",
                        "Y",
                        "Y",
                        "N",
                        "N",
                        "Y",
                        "Under investigation",
                        "INV-3001",
                        "2026-08-31T09:12:00Z",
                        "2026-09-02T14:05:00Z",
                    ],
                    [
                        "TWD-C-000982",
                        "CMP-10022",
                        "PUMP-200",
                        "Rev D",
                        "2026-09-03",
                        "2026-09-04",
                        "2026-09-04",
                        "2026-09-04",
                        "DE",
                        "Healthcare professional",
                        "Device malfunction",
                        "ALM-OCC-FALSE",
                        "Repeated occlusion alarms during a night infusion with a clear line. The set was replaced and the alarm continued.",
                        "Major",
                        "L24-0902",
                        "SN-200D-005102",
                        "(01)05012345678900",
                        "Y",
                        "Y",
                        "N",
                        "N",
                        "Y",
                        "Under investigation",
                        "INV-3001",
                        "2026-09-04T07:40:00Z",
                        "2026-09-05T10:21:00Z",
                    ],
                    [
                        "TWD-C-000983",
                        "CMP-10023",
                        "PUMP-200",
                        "Rev C",
                        "2026-08-14",
                        "2026-08-16",
                        "2026-08-16",
                        "2026-08-17",
                        "US",
                        "User facility",
                        "Device performance",
                        "BAT-DRAIN",
                        "Battery drained within 3 hours instead of the labelled 8 hours.",
                        "Minor",
                        "L24-0611",
                        "SN-200C-003318",
                        "(01)05012345678894",
                        "N",
                        "N",
                        "N",
                        "N",
                        "Y",
                        "Closed",
                        "INV-2987",
                        "2026-08-17T15:02:00Z",
                        "2026-09-20T08:45:00Z",
                    ],
                    [
                        "TWD-C-000984",
                        "CMP-10024",
                        "PUMP-200",
                        "Rev D",
                        "2026-09-10",
                        "2026-09-11",
                        "2026-09-11",
                        "2026-09-11",
                        "IE",
                        "Healthcare professional",
                        "Device malfunction",
                        "ALM-OCC-FALSE",
                        "Occlusion alarm at the start of an infusion; therapy was delayed about 40 minutes while the pump was swapped.",
                        "Critical",
                        "L24-0815",
                        "SN-200D-004498",
                        "(01)05012345678900",
                        "N",
                        "Y",
                        "N",
                        "N",
                        "Y",
                        "Open",
                        "INV-3001",
                        "2026-09-11T11:30:00Z",
                        "2026-09-11T11:30:00Z",
                    ],
                ],
            },
            {
                "file": "investigations.csv",
                "record": "Investigation",
                "columns": [
                    col(
                        "investigation_number",
                        True,
                        "text",
                        "Investigation number",
                    ),
                    col("title", True, "text", "Short title"),
                    col(
                        "investigation_question",
                        True,
                        "text",
                        "The question the investigation answers",
                    ),
                    col("product_code", True, "text", "Product investigated"),
                    col("product_revision", False, "text", "Revision in scope"),
                    col(
                        "related_complaints",
                        False,
                        "list separated by ;",
                        "Complaint numbers in scope",
                    ),
                    col("opened_date", False, "date YYYY-MM-DD", "Opened"),
                    col("due_date", False, "date YYYY-MM-DD", "Due"),
                    col(
                        "owner",
                        False,
                        "user ID (no names or emails)",
                        "Owner's user ID in TrackWise",
                    ),
                    col("status", True, "text", "Open, In progress, Closed"),
                    col(
                        "root_cause_category",
                        False,
                        "text",
                        "Design, Manufacturing, Supplier, Use error, Not confirmed",
                    ),
                    col("conclusion", False, "text", "Conclusion when closed"),
                ],
                "rows": [
                    [
                        "INV-3001",
                        "False occlusion alarms on AquaFlow 200 Rev D",
                        "Why do AquaFlow 200 Rev D pumps raise occlusion alarms when no occlusion is present?",
                        "PUMP-200",
                        "Rev D",
                        "CMP-10021;CMP-10022;CMP-10024",
                        "2026-09-02",
                        "2026-10-30",
                        "QE-INV-014",
                        "In progress",
                        "",
                        "",
                    ],
                    [
                        "INV-2987",
                        "Short battery life on AquaFlow 200 Rev C",
                        "Why does the AquaFlow 200 Rev C battery drain faster than labelled?",
                        "PUMP-200",
                        "Rev C",
                        "CMP-10023",
                        "2026-08-18",
                        "2026-09-30",
                        "QE-INV-009",
                        "Closed",
                        "Supplier",
                        "Battery cells from one supplier lot had low capacity; lot quarantined.",
                    ],
                ],
            },
            {
                "file": "capas.csv",
                "record": "CAPA",
                "columns": [
                    col("capa_number", True, "text", "CAPA number"),
                    col("title", True, "text", "Short title"),
                    col("source_type", False, "text", "Investigation, Complaint, Audit, Nonconformance"),
                    col("source_reference", False, "text", "Number of the source record"),
                    col("product_code", False, "text", "Product"),
                    col("action_type", False, "text", "Corrective, Preventive"),
                    col("opened_date", False, "date YYYY-MM-DD", "Opened"),
                    col("due_date", False, "date YYYY-MM-DD", "Due"),
                    col("status", True, "text", "Open, Implementation, Effectiveness check, Closed"),
                    col("effectiveness_check_date", False, "date YYYY-MM-DD", "When effectiveness is checked"),
                ],
                "rows": [
                    [
                        "CAPA-0450",
                        "Restore occlusion threshold margin on Rev D",
                        "Investigation",
                        "INV-3001",
                        "PUMP-200",
                        "Corrective",
                        "2026-09-15",
                        "2026-12-15",
                        "Open",
                        "",
                    ],
                    [
                        "CAPA-0431",
                        "Incoming capacity test for battery cells",
                        "Investigation",
                        "INV-2987",
                        "PUMP-200",
                        "Preventive",
                        "2026-09-05",
                        "2026-11-05",
                        "Effectiveness check",
                        "2026-12-01",
                    ],
                ],
            },
        ],
    },
    {
        "code": "SALESFORCE_SERVICE",
        "name": "Salesforce Service (complaint intake)",
        "simulator": "8114",
        "note": "Use only if Salesforce is where complaints are first logged; the complaint itself still comes from the quality system.",
        "files": [
            {
                "file": "cases.csv",
                "record": "Service case",
                "columns": [
                    col("case_number", True, "text", "Case number"),
                    col("subject", True, "text", "Short subject"),
                    col("description", True, "text", "What the customer reported, without personal data"),
                    col("product_code", False, "text", "Product"),
                    col("serial_number", False, "text", "Device serial number"),
                    col("lot_number", False, "text", "Lot/batch"),
                    col("case_origin", False, "text", "Phone, Web, Field service, Email"),
                    col("opened_datetime", False, "date-time ISO 8601 UTC", "When the case was opened"),
                    col("status", False, "text", "New, Working, Escalated, Closed"),
                    col("escalated_to_complaint", False, "Y/N", "Became a complaint in the quality system"),
                    col("complaint_number", False, "text", "Complaint number in the quality system"),
                ],
                "rows": [
                    [
                        "00012871",
                        "Pump alarms with clear line",
                        "Customer reports occlusion alarm with no blockage; pump being returned.",
                        "PUMP-200",
                        "SN-200D-004471",
                        "L24-0815",
                        "Phone",
                        "2026-08-29T16:20:00Z",
                        "Escalated",
                        "Y",
                        "CMP-10021",
                    ],
                    [
                        "00012904",
                        "Question about battery indicator",
                        "Customer asked how to read the battery indicator; no malfunction reported.",
                        "PUMP-200",
                        "SN-200C-003001",
                        "",
                        "Web",
                        "2026-09-06T09:05:00Z",
                        "Closed",
                        "N",
                        "",
                    ],
                ],
            }
        ],
    },
    {
        "code": "VEEVA_QMS",
        "name": "Veeva Vault QMS (quality management)",
        "simulator": "8105",
        "files": [
            {
                "file": "quality_events.csv",
                "record": "Quality event",
                "columns": [
                    col("event_number", True, "text", "Quality event number"),
                    col(
                        "event_type",
                        True,
                        "text",
                        "Complaint, Deviation, Nonconformance (only Complaint becomes an MDARIX complaint)",
                    ),
                    col("title", True, "text", "Short title"),
                    col("description", True, "text", "What happened, without personal data"),
                    col("product_code", True, "text", "Product (same number as in PLM)"),
                    col("product_version", False, "text", "Product version"),
                    col("lot_number", False, "text", "Lot (same number as in ERP)"),
                    col("event_date", False, "date YYYY-MM-DD", "When it happened"),
                    col("opened_date", False, "date YYYY-MM-DD", "When it was opened"),
                    col("severity", False, "text", "Minor, Major, Critical"),
                    col("status", False, "text", "Open, In review, Closed"),
                    col("investigation_number", False, "text", "Linked investigation"),
                ],
                "rows": [
                    [
                        "QE-2026-0311",
                        "Complaint",
                        "Display froze during infusion",
                        "The display froze during an ambulatory infusion; the pump kept delivering at the set rate.",
                        "PUMP-300",
                        "Rev A",
                        "OL-3001",
                        "2026-09-01",
                        "2026-09-02",
                        "Major",
                        "Open",
                        "",
                    ],
                    [
                        "QE-2026-0318",
                        "Complaint",
                        "Clip on carry case broke",
                        "The belt clip on the carry case broke after two weeks of use.",
                        "PUMP-300",
                        "Rev A",
                        "OL-3002",
                        "2026-09-08",
                        "2026-09-09",
                        "Minor",
                        "Closed",
                        "",
                    ],
                    [
                        "QE-2026-0322",
                        "Deviation",
                        "Torque check skipped on one shift",
                        "The screw torque check was not recorded for one shift on lot OL-3002.",
                        "PUMP-300",
                        "Rev A",
                        "OL-3002",
                        "2026-09-10",
                        "2026-09-10",
                        "Minor",
                        "In review",
                        "",
                    ],
                ],
            },
            {
                "file": "capas.csv",
                "record": "CAPA",
                "columns": [
                    col("capa_number", True, "text", "CAPA number"),
                    col("title", True, "text", "Short title"),
                    col("source_event", False, "text", "Quality event number"),
                    col("product_code", False, "text", "Product"),
                    col("action_type", False, "text", "Corrective, Preventive"),
                    col("opened_date", False, "date YYYY-MM-DD", "Opened"),
                    col("due_date", False, "date YYYY-MM-DD", "Due"),
                    col("status", True, "text", "Open, Implementation, Effectiveness check, Closed"),
                ],
                "rows": [
                    [
                        "VCAPA-0077",
                        "Add torque record check to shift handover",
                        "QE-2026-0322",
                        "PUMP-300",
                        "Corrective",
                        "2026-09-12",
                        "2026-10-31",
                        "Implementation",
                    ]
                ],
            },
            {
                "file": "documents.csv",
                "record": "Controlled document",
                "columns": [
                    col("document_number", True, "text", "Document number"),
                    col("title", True, "text", "Document title"),
                    col(
                        "document_type",
                        True,
                        "text",
                        "Design verification report, Test report, Risk management file, IFU, SOP",
                    ),
                    col("version", False, "text", "Document version"),
                    col("lifecycle_state", False, "text", "Effective, Draft, Superseded"),
                    col("effective_date", False, "date YYYY-MM-DD", "Effective from"),
                    col("product_code", False, "text", "Product it applies to"),
                    col("owner_department", False, "text", "Owning department"),
                    col("file_name", False, "text", "File name of the document"),
                ],
                "rows": [
                    [
                        "DOC-VV-0091",
                        "Design verification report AquaFlow 200 Rev D",
                        "Design verification report",
                        "2.0",
                        "Effective",
                        "2026-06-20",
                        "PUMP-200",
                        "R&D",
                        "DVR-AF200-RevD.pdf",
                    ],
                    [
                        "DOC-VV-0104",
                        "Occlusion detection test report",
                        "Test report",
                        "1.1",
                        "Effective",
                        "2026-06-12",
                        "PUMP-200",
                        "Verification",
                        "TR-OCC-AF200.pdf",
                    ],
                    [
                        "DOC-VV-0120",
                        "Instructions for use AquaFlow 300",
                        "IFU",
                        "3.0",
                        "Effective",
                        "2026-04-01",
                        "PUMP-300",
                        "Regulatory",
                        "IFU-AF300-v3.pdf",
                    ],
                ],
            },
        ],
    },
    {
        "code": "TEAMCENTER",
        "name": "Siemens Teamcenter (PLM)",
        "simulator": "8106",
        "files": [
            {
                "file": "items.csv",
                "record": "Item (product, assembly, component, software)",
                "columns": [
                    col("item_number", True, "text", "Item number (products and components)"),
                    col("name", True, "text", "Item name"),
                    col(
                        "item_type", True, "text", "Product, Assembly, Component, Software (only Product imports today)"
                    ),
                    col("description", False, "text", "Description"),
                    col("product_family", False, "text", "Product family"),
                    col("lifecycle", False, "text", "In work, Released, Obsolete"),
                    col("owner_group", False, "text", "Owning engineering group"),
                ],
                "rows": [
                    [
                        "PUMP-200",
                        "AquaFlow 200 Infusion Pump",
                        "Product",
                        "Large-volume infusion pump",
                        "Infusion therapy",
                        "Released",
                        "Infusion R&D",
                    ],
                    [
                        "PS-110",
                        "Downstream pressure sensor assembly",
                        "Component",
                        "Measures line pressure for occlusion detection",
                        "",
                        "Released",
                        "Sensors",
                    ],
                    [
                        "MB-220",
                        "Main control board",
                        "Assembly",
                        "Controller board with alarm logic",
                        "",
                        "Released",
                        "Electronics",
                    ],
                    [
                        "FW-AF200",
                        "AquaFlow 200 firmware",
                        "Software",
                        "Pump control and alarm firmware",
                        "",
                        "Released",
                        "Software",
                    ],
                    [
                        "BAT-18",
                        "Rechargeable battery pack",
                        "Component",
                        "Li-ion pack, 8 hours labelled runtime",
                        "",
                        "Released",
                        "Electronics",
                    ],
                ],
            },
            {
                "file": "item_revisions.csv",
                "record": "Item revision (product version)",
                "columns": [
                    col(
                        "version_id",
                        True,
                        "text",
                        "Teamcenter revision record ID",
                    ),
                    col("product_id", True, "text", "Item number"),
                    col("item_name", True, "text", "Item name, repeated on every revision"),
                    col("revision", True, "text", "Revision"),
                    col("version_name", False, "text", "Revision name"),
                    col(
                        "effective_date",
                        False,
                        "date YYYY-MM-DD",
                        "Effective from",
                    ),
                    col("release_date", False, "date YYYY-MM-DD", "Released"),
                    col("status", False, "text", "In work, Released, Superseded"),
                    col("software_version", False, "text", "Firmware/software version in this revision"),
                    col("configuration_id", False, "text", "Configuration or variant"),
                    col(
                        "change_order_id",
                        False,
                        "text",
                        "Change that created this revision",
                    ),
                    col(
                        "recorded_at",
                        False,
                        "date-time ISO 8601 UTC",
                        "When Teamcenter recorded it",
                    ),
                    col("known_at", False, "date-time ISO 8601 UTC", "When the company knew it"),
                ],
                "rows": [
                    [
                        "TC-REV-20031",
                        "PUMP-200",
                        "AquaFlow 200 Infusion Pump",
                        "Rev C",
                        "AquaFlow 200 Rev C",
                        "2026-03-15",
                        "2026-03-15",
                        "Superseded",
                        "4.1.3",
                        "CFG-EU-US",
                        "ECN-4402",
                        "2026-03-15T08:00:00Z",
                        "2026-03-15T08:00:00Z",
                    ],
                    [
                        "TC-REV-20047",
                        "PUMP-200",
                        "AquaFlow 200 Infusion Pump",
                        "Rev D",
                        "AquaFlow 200 Rev D",
                        "2026-07-01",
                        "2026-07-01",
                        "Released",
                        "4.2.0",
                        "CFG-EU-US",
                        "ECN-4471",
                        "2026-07-01T08:00:00Z",
                        "2026-07-01T08:00:00Z",
                    ],
                ],
            },
            {
                "file": "bom_lines.csv",
                "record": "Bill of materials line",
                "columns": [
                    col("parent_item_number", True, "text", "Parent item"),
                    col("parent_revision", True, "text", "Parent revision"),
                    col("child_item_number", True, "text", "Child item"),
                    col("child_revision", False, "text", "Child revision"),
                    col("quantity", False, "number", "Quantity per parent"),
                    col("unit", False, "text", "EA, M, G"),
                    col("find_number", False, "text", "Position on the drawing"),
                    col(
                        "effective_from",
                        False,
                        "date YYYY-MM-DD",
                        "Effective from",
                    ),
                    col("effective_to", False, "date YYYY-MM-DD", "Effective until (empty = still effective)"),
                ],
                "rows": [
                    ["PUMP-200", "Rev D", "PS-110", "B", "1", "EA", "10", "2026-07-01", ""],
                    ["PUMP-200", "Rev D", "MB-220", "F", "1", "EA", "20", "2026-07-01", ""],
                    ["PUMP-200", "Rev D", "FW-AF200", "4.2.0", "1", "EA", "30", "2026-07-01", ""],
                    ["PUMP-200", "Rev D", "BAT-18", "C", "1", "EA", "40", "2026-07-01", ""],
                    ["PUMP-200", "Rev C", "PS-110", "A", "1", "EA", "10", "2026-03-15", "2026-06-30"],
                ],
            },
            {
                "file": "change_notices.csv",
                "record": "Engineering change",
                "columns": [
                    col("change_number", True, "text", "Change number"),
                    col("title", True, "text", "Short title"),
                    col("change_type", True, "text", "ECN, ECO, Deviation"),
                    col("description", True, "text", "What changed and why"),
                    col("affected_items", False, "list separated by ;", "Items changed"),
                    col("status", False, "text", "In review, Approved, Implemented"),
                    col("release_date", False, "date YYYY-MM-DD", "Released"),
                    col("effective_date", False, "date YYYY-MM-DD", "Effective from"),
                ],
                "rows": [
                    [
                        "ECN-4471",
                        "Occlusion filter threshold for Rev D",
                        "ECN",
                        "Firmware 4.2.0 lowers the occlusion filter threshold from 12 kPa to 9 kPa and uses pressure sensor revision B.",
                        "FW-AF200;PS-110;PUMP-200",
                        "Implemented",
                        "2026-06-25",
                        "2026-07-01",
                    ],
                    [
                        "ECN-4402",
                        "Battery pack revision C",
                        "ECN",
                        "Battery pack moves to revision C cells from a second supplier.",
                        "BAT-18;PUMP-200",
                        "Implemented",
                        "2026-03-10",
                        "2026-03-15",
                    ],
                ],
            },
            {
                "file": "requirements.csv",
                "record": "Requirement",
                "columns": [
                    col("requirement_id", True, "text", "Requirement ID"),
                    col("product_code", True, "text", "Product"),
                    col("revision", False, "text", "Product revision"),
                    col(
                        "requirement_type",
                        False,
                        "text",
                        "User need, System, Software, Safety",
                    ),
                    col("text", True, "text", "Requirement text"),
                    col("verification_method", False, "text", "Test, Inspection, Analysis"),
                    col("status", False, "text", "Draft, Approved, Obsolete"),
                    col("trace_to_risk", False, "text", "Risk ID it controls"),
                ],
                "rows": [
                    [
                        "REQ-AF200-045",
                        "PUMP-200",
                        "Rev D",
                        "Safety",
                        "The occlusion alarm shall trigger within 30 s at 103 kPa downstream pressure (plus or minus 10%) and shall not trigger below 60 kPa.",
                        "Test",
                        "Approved",
                        "RSK-0012",
                    ],
                    [
                        "REQ-AF200-061",
                        "PUMP-200",
                        "Rev C",
                        "System",
                        "The battery shall power continuous infusion at 25 mL/h for at least 8 hours.",
                        "Test",
                        "Approved",
                        "RSK-0019",
                    ],
                ],
            },
        ],
    },
    {
        "code": "WINDCHILL",
        "name": "PTC Windchill (PLM)",
        "simulator": "8110",
        "files": [
            {
                "file": "parts.csv",
                "record": "Part",
                "columns": [
                    col("number", True, "text", "Part number"),
                    col("name", True, "text", "Part name"),
                    col("part_type", True, "text", "End item, Component, Software (only End item imports today)"),
                    col("state", False, "text", "In work, Released, Obsolete"),
                    col("product_line", False, "text", "Product line"),
                ],
                "rows": [
                    ["PUMP-300", "AquaFlow 300 Ambulatory Pump", "End item", "Released", "Ambulatory infusion"],
                    ["DSP-31", "Colour display module", "Component", "Released", ""],
                    ["CC-07", "Carry case with belt clip", "Component", "Released", ""],
                ],
            },
            {
                "file": "part_versions.csv",
                "record": "Part version",
                "columns": [
                    col("number", True, "text", "Part number"),
                    col("name", True, "text", "Part name"),
                    col("version", True, "text", "Version (A, B, ...)"),
                    col("iteration", False, "number", "Iteration within the version"),
                    col("state", False, "text", "In work, Released, Superseded"),
                    col("released_date", False, "date YYYY-MM-DD", "Released"),
                ],
                "rows": [["PUMP-300", "AquaFlow 300 Ambulatory Pump", "Rev A", "3", "Released", "2026-02-10"]],
            },
            {
                "file": "bom.csv",
                "record": "Bill of materials line",
                "columns": [
                    col("parent_number", True, "text", "Parent part"),
                    col("parent_version", True, "text", "Parent version"),
                    col("child_number", True, "text", "Child part"),
                    col("quantity", False, "number", "Quantity"),
                    col("unit", False, "text", "EA, M, G"),
                ],
                "rows": [["PUMP-300", "Rev A", "DSP-31", "1", "EA"], ["PUMP-300", "Rev A", "CC-07", "1", "EA"]],
            },
            {
                "file": "change_notices.csv",
                "record": "Change notice",
                "columns": [
                    col("number", True, "text", "Change notice number"),
                    col("name", True, "text", "Title"),
                    col("description", True, "text", "What changed"),
                    col("affected_parts", False, "list separated by ;", "Parts changed"),
                    col("state", False, "text", "Open, Resolved"),
                    col("resolution_date", False, "date YYYY-MM-DD", "Resolved"),
                ],
                "rows": [
                    [
                        "CN-0912",
                        "Display supplier change",
                        "Display module moves to a second-source supplier.",
                        "DSP-31",
                        "Resolved",
                        "2026-05-20",
                    ]
                ],
            },
        ],
    },
    {
        "code": "SAP_ERP",
        "name": "SAP S/4HANA (ERP)",
        "simulator": "8109",
        "note": "Headers are SAP technical field names (MATNR = material, CHARG = batch, WERKS = plant, LIFNR = vendor).",
        "files": [
            {
                "file": "materials.csv",
                "record": "Material (MARA/MAKT)",
                "columns": [
                    col("MATNR", True, "text", "Material number (same as the PLM item number)"),
                    col("MAKTX", True, "text", "Material description"),
                    col(
                        "MTART",
                        True,
                        "text",
                        "Material type: FERT finished product, HALB semi-finished, ROH raw/purchased",
                    ),
                    col("MATKL", False, "text", "Material group"),
                    col("MEINS", False, "text", "Base unit of measure"),
                    col("REVLV", False, "text", "Revision level"),
                    col("LVORM", False, "X or empty", "Flagged for deletion"),
                ],
                "rows": [
                    ["PUMP-200", "AquaFlow 200 Infusion Pump", "FERT", "INFUSION", "EA", "Rev D", ""],
                    ["PS-110", "Downstream pressure sensor assembly", "ROH", "SENSORS", "EA", "B", ""],
                    ["BAT-18", "Rechargeable battery pack", "ROH", "POWER", "EA", "C", ""],
                ],
            },
            {
                "file": "plants.csv",
                "record": "Plant (T001W)",
                "columns": [
                    col("WERKS", True, "text", "Plant code"),
                    col("NAME1", True, "text", "Plant name"),
                    col("LAND1", False, "ISO country code", "Country"),
                    col("ORT01", False, "text", "City"),
                ],
                "rows": [
                    ["1100", "Galway final assembly", "IE", "Galway"],
                    ["2100", "Penang electronics", "MY", "Penang"],
                ],
            },
            {
                "file": "batches.csv",
                "record": "Batch (MCH1/MCHA)",
                "columns": [
                    col("CHARG", True, "text", "Batch number"),
                    col("MATNR", True, "text", "Material"),
                    col("WERKS", True, "text", "Plant where it was made"),
                    col("REVLV", True, "text", "Revision level built"),
                    col("HSDAT", False, "date YYYY-MM-DD", "Date of manufacture"),
                    col("VFDAT", False, "date YYYY-MM-DD", "Shelf-life expiry date"),
                    col("ZUSTD", False, "X or empty", "Batch in restricted use (quarantine)"),
                    col("LIFNR", False, "text", "Vendor, for purchased batches"),
                    col("LICHA", False, "text", "Vendor's own batch number"),
                ],
                "rows": [
                    ["L24-0611", "PUMP-200", "1100", "Rev C", "2026-06-11", "2031-06-11", "", "", ""],
                    ["L24-0815", "PUMP-200", "1100", "Rev D", "2026-07-20", "2031-07-20", "", "", ""],
                    ["L24-0902", "PUMP-200", "1100", "Rev D", "2026-08-11", "2031-08-11", "", "", ""],
                ],
            },
            {
                "file": "batch_where_used.csv",
                "record": "Batch genealogy (which component batches went into which product batch)",
                "columns": [
                    col("CHARG_PARENT", True, "text", "Product batch"),
                    col("MATNR_PARENT", True, "text", "Product material"),
                    col("CHARG_COMPONENT", True, "text", "Component batch used"),
                    col("MATNR_COMPONENT", True, "text", "Component material"),
                    col("MENGE", False, "number", "Quantity consumed"),
                    col("MEINS", False, "text", "Unit"),
                ],
                "rows": [
                    ["L24-0815", "PUMP-200", "KS-5521", "PS-110", "480", "EA"],
                    ["L24-0902", "PUMP-200", "KS-5521", "PS-110", "520", "EA"],
                    ["L24-0611", "PUMP-200", "KS-5490", "PS-110", "500", "EA"],
                ],
            },
            {
                "file": "vendors.csv",
                "record": "Vendor (LFA1)",
                "columns": [
                    col("LIFNR", True, "text", "Vendor number"),
                    col("NAME1", True, "text", "Vendor name"),
                    col("LAND1", False, "ISO country code", "Country"),
                    col("SPERR", False, "X or empty", "Blocked for purchasing"),
                    col("KTOKK", False, "text", "Vendor account group"),
                ],
                "rows": [
                    ["SUP-1001", "Kestrel Sensors Ltd", "GB", "", "ZMED"],
                    ["SUP-1002", "Norvale Electronics", "MY", "", "ZMED"],
                    ["SUP-1004", "Halden Cells AS", "NO", "", "ZMED"],
                ],
            },
            {
                "file": "source_list.csv",
                "record": "Source list (EORD): which vendor supplies which material",
                "columns": [
                    col("MATNR", True, "text", "Material"),
                    col("WERKS", True, "text", "Plant"),
                    col("LIFNR", True, "text", "Vendor"),
                    col("VDATU", False, "date YYYY-MM-DD", "Valid from"),
                    col("BDATU", False, "date YYYY-MM-DD", "Valid to"),
                    col("FLIFN", False, "X or empty", "Fixed vendor"),
                ],
                "rows": [
                    ["PS-110", "1100", "SUP-1001", "2025-01-01", "9999-12-31", "X"],
                    ["BAT-18", "1100", "SUP-1004", "2026-03-15", "9999-12-31", "X"],
                ],
            },
        ],
    },
    {
        "code": "ORACLE_ERP",
        "name": "Oracle Fusion Cloud (ERP)",
        "simulator": "8107",
        "files": [
            {
                "file": "items.csv",
                "record": "Item",
                "columns": [
                    col("ITEM_NUMBER", True, "text", "Item number"),
                    col("DESCRIPTION", True, "text", "Description"),
                    col("ITEM_TYPE", True, "text", "FG finished good, PURCHASED, SUBASSEMBLY"),
                    col("REVISION", False, "text", "Current revision"),
                    col("INVENTORY_ITEM_STATUS_CODE", False, "text", "Active, Inactive"),
                ],
                "rows": [
                    ["PUMP-300", "AquaFlow 300 Ambulatory Pump", "FG", "Rev A", "Active"],
                    ["DSP-31", "Colour display module", "PURCHASED", "B", "Active"],
                ],
            },
            {
                "file": "organizations.csv",
                "record": "Inventory organization (site)",
                "columns": [
                    col("ORGANIZATION_CODE", True, "text", "Organization code"),
                    col("ORGANIZATION_NAME", True, "text", "Name"),
                    col("LOCATION_CODE", False, "text", "Location"),
                ],
                "rows": [["M1", "Monterrey assembly", "MX-MTY"]],
            },
            {
                "file": "lots.csv",
                "record": "Lot",
                "columns": [
                    col("LOT_NUMBER", True, "text", "Lot number"),
                    col("ITEM_NUMBER", True, "text", "Item"),
                    col("REVISION", True, "text", "Revision built"),
                    col("ORGANIZATION_CODE", False, "text", "Where it was made"),
                    col("ORIGINATION_DATE", False, "date YYYY-MM-DD", "Made on"),
                    col("EXPIRATION_DATE", False, "date YYYY-MM-DD", "Expires"),
                    col("STATUS_CODE", False, "text", "Active, Hold"),
                ],
                "rows": [
                    ["OL-3001", "PUMP-300", "Rev A", "M1", "2026-06-20", "2031-06-20", "Active"],
                    ["OL-3002", "PUMP-300", "Rev A", "M1", "2026-07-25", "2031-07-25", "Hold"],
                ],
            },
            {
                "file": "suppliers.csv",
                "record": "Supplier",
                "columns": [
                    col("SUPPLIER_NUMBER", True, "text", "Supplier number"),
                    col("VENDOR_NAME", True, "text", "Name"),
                    col("COUNTRY", False, "ISO country code", "Country"),
                    col("ENABLED_FLAG", False, "Y/N", "Enabled"),
                ],
                "rows": [["SUP-2001", "Lumora Displays", "TW", "Y"], ["SUP-2002", "Castell Plastics", "MX", "Y"]],
            },
            {
                "file": "approved_supplier_list.csv",
                "record": "Approved supplier list",
                "columns": [
                    col("ITEM_NUMBER", True, "text", "Item"),
                    col("SUPPLIER_NUMBER", True, "text", "Supplier"),
                    col("ORGANIZATION_CODE", False, "text", "Organization"),
                    col("ASL_STATUS", False, "text", "Approved, Debarred"),
                ],
                "rows": [["DSP-31", "SUP-2001", "M1", "Approved"], ["CC-07", "SUP-2002", "M1", "Approved"]],
            },
        ],
    },
    {
        "code": "MES",
        "name": "Manufacturing execution system",
        "simulator": "8111",
        "files": [
            {
                "file": "production_orders.csv",
                "record": "Production order",
                "columns": [
                    col("order_number", True, "text", "Production order"),
                    col("material_number", True, "text", "Product built"),
                    col("revision", True, "text", "Revision built"),
                    col("lot_number", True, "text", "Lot produced"),
                    col("site_code", True, "text", "Site"),
                    col("start_date", False, "date YYYY-MM-DD", "Started"),
                    col("end_date", False, "date YYYY-MM-DD", "Finished"),
                    col("quantity_built", False, "number", "Units built"),
                    col("status", False, "text", "Released, In progress, Completed"),
                ],
                "rows": [
                    [
                        "PO-77120",
                        "PUMP-200",
                        "Rev D",
                        "L24-0815",
                        "1100",
                        "2026-07-14",
                        "2026-07-20",
                        "480",
                        "Completed",
                    ],
                    [
                        "PO-77188",
                        "PUMP-200",
                        "Rev D",
                        "L24-0902",
                        "1100",
                        "2026-08-05",
                        "2026-08-11",
                        "520",
                        "Completed",
                    ],
                ],
            },
            {
                "file": "genealogy.csv",
                "record": "Lot genealogy",
                "columns": [
                    col("lot_number", True, "text", "Product lot"),
                    col("material_number", True, "text", "Product"),
                    col("component_material", True, "text", "Component"),
                    col("component_lot", True, "text", "Component lot used"),
                    col("quantity_consumed", False, "number", "Quantity"),
                    col("consumed_date", False, "date YYYY-MM-DD", "When it was used"),
                ],
                "rows": [
                    ["L24-0815", "PUMP-200", "PS-110", "KS-5521", "480", "2026-07-15"],
                    ["L24-0815", "PUMP-200", "BAT-18", "HC-2207", "480", "2026-07-16"],
                ],
            },
        ],
    },
    {
        "code": "LIMS",
        "name": "Laboratory information management system",
        "simulator": "8112",
        "files": [
            {
                "file": "test_results.csv",
                "record": "Test result",
                "columns": [
                    col("result_id", True, "text", "Result ID"),
                    col("sample_id", True, "text", "Sample ID"),
                    col("lot_number", False, "text", "Lot tested"),
                    col("material_number", False, "text", "Material tested"),
                    col("test_method", True, "text", "Test method"),
                    col("parameter", True, "text", "What was measured"),
                    col("result_value", True, "number", "Measured value"),
                    col("unit", False, "text", "Unit"),
                    col("lower_limit", False, "number", "Lower specification limit"),
                    col("upper_limit", False, "number", "Upper specification limit"),
                    col("result", True, "text", "Pass, Fail"),
                    col("tested_date", False, "date YYYY-MM-DD", "Tested on"),
                    col("review_status", False, "text", "Pending review, Approved"),
                ],
                "rows": [
                    [
                        "TR-88120",
                        "SMP-5521-07",
                        "KS-5521",
                        "PS-110",
                        "TM-PS-004 sensor drift at 37 C",
                        "Pressure reading offset",
                        "7.8",
                        "kPa",
                        "-5",
                        "5",
                        "Fail",
                        "2026-09-08",
                        "Approved",
                    ],
                    [
                        "TR-88121",
                        "SMP-5490-03",
                        "KS-5490",
                        "PS-110",
                        "TM-PS-004 sensor drift at 37 C",
                        "Pressure reading offset",
                        "1.9",
                        "kPa",
                        "-5",
                        "5",
                        "Pass",
                        "2026-09-08",
                        "Approved",
                    ],
                ],
            }
        ],
    },
    {
        "code": "RISK",
        "name": "Risk management file (ISO 14971)",
        "simulator": "8113",
        "files": [
            {
                "file": "risks.csv",
                "record": "Risk",
                "columns": [
                    col("risk_id", True, "text", "Risk ID"),
                    col("product_code", True, "text", "Product"),
                    col("revision", False, "text", "Product revision"),
                    col("hazard", True, "text", "Hazard"),
                    col("hazardous_situation", False, "text", "Hazardous situation"),
                    col("harm", True, "text", "Harm"),
                    col("severity", False, "number 1-5", "Severity"),
                    col("probability", False, "number 1-5", "Probability"),
                    col("risk_level", False, "text", "Acceptable, ALARP, Unacceptable"),
                    col("status", False, "text", "Open, Controlled, Closed"),
                ],
                "rows": [
                    [
                        "RSK-0012",
                        "PUMP-200",
                        "Rev D",
                        "Interrupted infusion",
                        "False occlusion alarm stops the infusion",
                        "Delayed therapy",
                        "4",
                        "2",
                        "ALARP",
                        "Controlled",
                    ],
                    [
                        "RSK-0019",
                        "PUMP-200",
                        "Rev C",
                        "Loss of power",
                        "Battery runs out during transport",
                        "Delayed therapy",
                        "3",
                        "2",
                        "Acceptable",
                        "Controlled",
                    ],
                ],
            },
            {
                "file": "failure_modes.csv",
                "record": "FMEA line (failure mode)",
                "columns": [
                    col("fmea_id", True, "text", "Failure mode ID"),
                    col("product_code", True, "text", "Product"),
                    col("item_or_function", False, "text", "Item or function"),
                    col("failure_mode", True, "text", "Failure mode"),
                    col("effect", False, "text", "Effect"),
                    col("cause", False, "text", "Cause"),
                    col("severity", False, "number 1-10", "Severity"),
                    col("occurrence", False, "number 1-10", "Occurrence"),
                    col("detection", False, "number 1-10", "Detection"),
                    col("linked_risk_id", False, "text", "Risk it leads to"),
                ],
                "rows": [
                    [
                        "FM-031",
                        "PUMP-200",
                        "PS-110 pressure sensor",
                        "Sensor reading drifts high at body temperature",
                        "False occlusion alarm",
                        "Sensor offset outside specification",
                        "7",
                        "3",
                        "4",
                        "RSK-0012",
                    ],
                    [
                        "FM-044",
                        "PUMP-200",
                        "BAT-18 battery",
                        "Cell capacity below specification",
                        "Shortened runtime",
                        "Low-capacity cell lot",
                        "6",
                        "2",
                        "5",
                        "RSK-0019",
                    ],
                ],
            },
            {
                "file": "risk_controls.csv",
                "record": "Risk control",
                "columns": [
                    col("control_id", True, "text", "Control ID"),
                    col("risk_id", True, "text", "Risk it controls"),
                    col(
                        "control_type",
                        False,
                        "text",
                        "Inherent safety by design, Protective measure, Information for safety",
                    ),
                    col("description", True, "text", "What the control does"),
                    col("verification_reference", False, "text", "Test or document that proves it"),
                    col("status", False, "text", "Planned, Implemented, Verified"),
                ],
                "rows": [
                    [
                        "CTL-019",
                        "RSK-0012",
                        "Protective measure",
                        "Occlusion threshold verified at 60 and 103 kPa in production test",
                        "DOC-VV-0104",
                        "Verified",
                    ],
                    [
                        "CTL-024",
                        "RSK-0019",
                        "Information for safety",
                        "Low-battery warning 30 minutes before shutdown",
                        "REQ-AF200-061",
                        "Verified",
                    ],
                ],
            },
        ],
    },
    {
        "code": "COUPA",
        "name": "Coupa (supplier management)",
        "simulator": "8108",
        "files": [
            {
                "file": "suppliers.csv",
                "record": "Supplier",
                "columns": [
                    col(
                        "supplier_number",
                        True,
                        "text",
                        "Supplier number (same as in ERP)",
                    ),
                    col("name", True, "text", "Supplier name"),
                    col("status", False, "text", "Active, On hold, Inactive"),
                    col("country", False, "ISO country code", "Country"),
                    col("commodity", False, "text", "What they supply"),
                    col("preferred", False, "Y/N", "Preferred supplier"),
                ],
                "rows": [
                    ["SUP-1001", "Kestrel Sensors Ltd", "Active", "GB", "Pressure sensors", "Y"],
                    ["SUP-1002", "Norvale Electronics", "Active", "MY", "Circuit boards", "Y"],
                    ["SUP-1004", "Halden Cells AS", "On hold", "NO", "Battery cells", "N"],
                ],
            },
            {
                "file": "supplier_risks.csv",
                "record": "Supplier risk assessment",
                "columns": [
                    col("risk_number", True, "text", "Assessment number"),
                    col("supplier_number", True, "text", "Supplier"),
                    col("risk_type", False, "text", "Quality, Delivery, Financial, Compliance"),
                    col("rating", False, "text", "Low, Medium, High"),
                    col("assessed_date", False, "date YYYY-MM-DD", "Assessed on"),
                    col("status", False, "text", "Open, Mitigated, Closed"),
                    col("notes", False, "text", "Short note, no personal data"),
                ],
                "rows": [
                    [
                        "SRA-0301",
                        "SUP-1001",
                        "Quality",
                        "Medium",
                        "2026-09-10",
                        "Open",
                        "Two complaints linked to sensor lot KS-5521.",
                    ],
                    [
                        "SRA-0288",
                        "SUP-1004",
                        "Quality",
                        "High",
                        "2026-08-25",
                        "Mitigated",
                        "Low-capacity cell lot quarantined.",
                    ],
                ],
            },
            {
                "file": "supplier_certificates.csv",
                "record": "Supplier certificate",
                "columns": [
                    col("certificate_number", True, "text", "Certificate number"),
                    col("supplier_number", True, "text", "Supplier"),
                    col("certificate_type", True, "text", "ISO 13485, ISO 9001, RoHS declaration"),
                    col("issuer", False, "text", "Issuing body"),
                    col("issue_date", False, "date YYYY-MM-DD", "Issued"),
                    col("expiry_date", False, "date YYYY-MM-DD", "Expires"),
                    col("status", False, "text", "Valid, Expired, Withdrawn"),
                ],
                "rows": [
                    [
                        "CERT-13485-KS-22",
                        "SUP-1001",
                        "ISO 13485",
                        "Notified certification body",
                        "2024-04-01",
                        "2027-03-31",
                        "Valid",
                    ],
                    [
                        "CERT-13485-HC-19",
                        "SUP-1004",
                        "ISO 13485",
                        "Notified certification body",
                        "2023-02-01",
                        "2026-01-31",
                        "Expired",
                    ],
                ],
            },
        ],
    },
]


# Records whose key is not the first column (the simulators use the key to update a record instead of adding it).
KEYS = {
    ("TEAMCENTER", "bom_lines.csv"): ["parent_item_number", "parent_revision", "child_item_number"],
    ("WINDCHILL", "part_versions.csv"): ["number", "version"],
    ("WINDCHILL", "bom.csv"): ["parent_number", "parent_version", "child_number"],
    ("SAP_ERP", "batch_where_used.csv"): ["CHARG_PARENT", "CHARG_COMPONENT"],
    ("SAP_ERP", "source_list.csv"): ["MATNR", "WERKS", "LIFNR"],
    ("ORACLE_ERP", "approved_supplier_list.csv"): ["ITEM_NUMBER", "SUPPLIER_NUMBER"],
    ("MES", "genealogy.csv"): ["lot_number", "component_material", "component_lot"],
}
CATALOG = Path(__file__).resolve().parents[1] / "source_simulator" / "source_catalog.json"


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    path.write_text(buffer.getvalue(), encoding="utf-8", newline="")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    dictionary: list[list[str]] = []
    for app in APPLICATIONS:
        folder = OUT / app["code"]
        folder.mkdir(exist_ok=True)
        for spec in app["files"]:
            header = [c["name"] for c in spec["columns"]]
            for row in spec["rows"]:
                assert len(row) == len(header), (app["code"], spec["file"], row[0])
            write_csv(folder / spec["file"], header, spec["rows"])
            mapped = {
                source: f"{item['target']}.{column}"
                for item in STANDARD.get((app["code"], spec["file"]), [])
                for source, column in item["fields"].items()
            }
            for c in spec["columns"]:
                dictionary.append(
                    [
                        app["code"],
                        app["name"],
                        spec["file"],
                        spec["record"],
                        c["name"],
                        "Yes" if c["required"] else "No",
                        c["type"],
                        c["description"],
                        mapped.get(c["name"], "-"),
                        "Yes" if c["name"] in mapped else "No MDARIX field yet",
                    ]
                )
    write_csv(
        OUT / "_data_dictionary.csv",
        [
            "application",
            "application_name",
            "file",
            "record_type",
            "column",
            "required",
            "data_type",
            "description",
            "mdarix_field",
            "imported_by_mdarix_today",
        ],
        dictionary,
    )
    # The simulators read this catalog: which records each application holds, their columns and key.
    catalog = {
        app["code"]: {
            "name": app["name"],
            "port": int(app["simulator"]),
            "records": {
                spec["file"].removesuffix(".csv"): {
                    "label": spec["record"],
                    "key": KEYS.get((app["code"], spec["file"]), [spec["columns"][0]["name"]]),
                    "columns": [c["name"] for c in spec["columns"]],
                    "required": [c["name"] for c in spec["columns"] if c["required"]],
                }
                for spec in app["files"]
            },
        }
        for app in APPLICATIONS
    }
    for code, app in catalog.items():
        for name, record in app["records"].items():
            assert set(record["key"]) <= set(record["columns"]), (code, name)
    CATALOG.write_text(json.dumps(catalog, indent=1) + "\n", encoding="utf-8", newline="\n")
    known = {
        (app["code"], spec["file"]): {c["name"] for c in spec["columns"]}
        for app in APPLICATIONS
        for spec in app["files"]
    }
    for key, specs in STANDARD.items():
        for spec in specs:
            unknown = set(spec["fields"]) - known[key]
            assert not unknown, (key, unknown)
    MAPPINGS_FILE.write_text(json.dumps(standard_mappings(), indent=1) + "\n", encoding="utf-8", newline="\n")
    files = sum(len(app["files"]) for app in APPLICATIONS)
    print(
        f"Wrote {files} templates for {len(APPLICATIONS)} applications and {len(dictionary)} dictionary rows to {OUT}"
    )


if __name__ == "__main__":
    main()
