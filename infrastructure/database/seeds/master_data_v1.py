"""Master Data seed v1 (controlled load, Master Data Foundation §2 and §12.2).

Frozen: loaded once by migration md02. Later changes ship as a new seed version
through a new migration, never by editing this file.

Sources: the application/object/field catalog previously hard-coded in
backend/app/mapping_catalog_router.py, the simulator provider catalog, the
canonical tables of the Transactional Data Architecture v1.0 and the example
values in the Master Data Foundation v1.0. All values are public reference data
or synthetic; no customer data.
"""

from __future__ import annotations

import hashlib
import json
import re

from sqlalchemy import text

SEED_VERSION = "master-data-v1"


def _code(name: str) -> str:
    """'Product Version' / 'ProductVersion' / 'product_version' -> PRODUCT_VERSION."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name.strip())
    return re.sub(r"[^A-Za-z0-9]+", "_", spaced).strip("_").upper()


def _label(field: str) -> str:
    return field.replace("_", " ").strip().title()


# --- Industry and application catalog ------------------------------------------------

INDUSTRIES = [
    ("MEDICAL_DEVICE", "Medical Device", "Medical device design, manufacturing and post-market quality."),
    ("PHARMACEUTICAL", "Pharmaceutical", "Pharmaceutical manufacturing and pharmacovigilance."),
    ("BIOTECH", "Biotechnology", "Biotechnology research, manufacturing and quality."),
]

CATEGORIES = [
    ("QMS", "Quality Management System"),
    ("PLM", "Product Lifecycle Management"),
    ("ERP", "Enterprise Resource Planning"),
    ("MES", "Manufacturing Execution System"),
    ("LIMS", "Laboratory Information Management System"),
    ("RIM", "Regulatory Information Management"),
    ("CRM", "Customer Relationship Management"),
    ("PROCUREMENT", "Procurement and Supplier Management"),
    ("RISK", "Risk Management"),
    ("SAFETY", "Safety and Field Action Management"),
]

VENDORS = [
    ("HONEYWELL", "Honeywell (Sparta Systems)", "https://www.spartasystems.com"),
    ("VEEVA", "Veeva Systems", "https://www.veeva.com"),
    ("SALESFORCE", "Salesforce", "https://www.salesforce.com"),
    ("SIEMENS", "Siemens Digital Industries Software", "https://www.sw.siemens.com"),
    ("COUPA", "Coupa Software", "https://www.coupa.com"),
    ("PTC", "PTC", "https://www.ptc.com"),
    ("SAP", "SAP", "https://www.sap.com"),
    ("ORACLE", "Oracle", "https://www.oracle.com"),
    ("CONFIGURABLE", "Customer-configured system", None),
    ("MDARIX_SIMULATOR", "MDARIX synthetic provider simulator", None),
]

# code, name, category, vendor, integration_support_status (SUPPORTED = simulator-backed)
APPLICATIONS = [
    ("TRACKWISE", "TrackWise Digital", "QMS", "HONEYWELL", "SUPPORTED"),
    ("VEEVA_QMS", "Veeva Vault QMS", "QMS", "VEEVA", "SUPPORTED"),
    ("SALESFORCE_SERVICE", "Salesforce Service", "CRM", "SALESFORCE", "CONFIGURABLE"),
    ("TEAMCENTER", "Teamcenter PLM", "PLM", "SIEMENS", "SUPPORTED"),
    ("COUPA", "Coupa Supplier Network", "PROCUREMENT", "COUPA", "SUPPORTED"),
    ("WINDCHILL", "Windchill PLM", "PLM", "PTC", "CONFIGURABLE"),
    ("SAP_ERP", "SAP ERP", "ERP", "SAP", "CONFIGURABLE"),
    ("ORACLE_ERP", "Oracle ERP", "ERP", "ORACLE", "SUPPORTED"),
    ("RISK", "Risk Management System", "RISK", "CONFIGURABLE", "CONFIGURABLE"),
    ("RIM", "RIM / Vigilance System", "RIM", "CONFIGURABLE", "CONFIGURABLE"),
    ("SAFETY", "Safety / Field Action System", "SAFETY", "CONFIGURABLE", "CONFIGURABLE"),
    ("LIMS", "LIMS", "LIMS", "CONFIGURABLE", "CONFIGURABLE"),
    ("MES", "MES", "MES", "CONFIGURABLE", "CONFIGURABLE"),
    ("PLM", "Generic PLM (synthetic simulator)", "PLM", "MDARIX_SIMULATOR", "SUPPORTED"),
    ("ERP", "Generic ERP (synthetic simulator)", "ERP", "MDARIX_SIMULATOR", "SUPPORTED"),
    ("SUPPLIER", "Supplier portal (synthetic simulator)", "PROCUREMENT", "MDARIX_SIMULATOR", "SUPPORTED"),
]
MULTI_INDUSTRY_APPS = {"TRACKWISE", "VEEVA_QMS", "SAP_ERP", "ORACLE_ERP", "LIMS", "MES"}

# Objects per application: previous Mapping Studio catalog plus simulator provider entities.
APPLICATION_OBJECTS = {
    "TRACKWISE": ["Complaint", "Investigation", "CAPA", "Evidence", "Quality Event"],
    "VEEVA_QMS": ["QualityEvent", "Investigation", "CAPA", "Evidence", "Document"],
    "TEAMCENTER": ["Item", "ItemRevision", "ChangeNotice", "Product", "Product Version", "Component", "BOM", "Change"],
    "WINDCHILL": ["Product", "Product Version", "Component", "BOM", "Change"],
    "SAP_ERP": ["Supplier", "Manufacturing Site", "Lot", "Batch", "Material"],
    "SALESFORCE_SERVICE": ["Case", "Service Event", "Complaint Intake"],
    "ORACLE_ERP": ["Supplier", "PurchaseOrder", "Manufacturing Site", "Lot", "Batch", "Material"],
    "COUPA": ["Supplier", "PurchaseOrder", "SupplierRisk"],
    "RISK": ["Risk", "Failure Mode", "Control", "Hazard"],
    "RIM": ["Vigilance", "Regulatory Assessment"],
    "SAFETY": ["Field Action", "Recall"],
    "LIMS": ["Result", "Sample"],
    "MES": ["Production Record", "Genealogy", "Process Event"],
    "PLM": ["Product", "ProductVersion", "Component", "Change"],
    "ERP": ["Supplier", "Site", "Lot"],
    "SUPPLIER": ["SupplierPart", "Certificate", "SupplierEvent"],
}

TRACKWISE_COMPLAINT_FIELDS = [
    "complaint_id", "complaint_number", "product_code", "product_revision", "event_date", "received_date",
    "awareness_date", "opened_date", "country", "reporter_type", "complaint_type", "problem_code",
    "problem_description", "severity", "lot_number", "serial_number", "udi", "device_returned",
    "patient_involved", "serious_injury", "death", "malfunction", "status", "investigation_number",
    "created_at", "updated_at",
]  # fmt: skip
TEAMCENTER_PRODUCT_VERSION_FIELDS = [
    "version_id", "product_id", "revision", "version_name", "effective_date", "release_date", "status",
    "software_version", "configuration_id", "change_order_id", "recorded_at", "known_at",
]  # fmt: skip

# Source fields of the synthetic simulator providers (source_simulator/provider_catalog.py).
SIMULATOR_FIELDS = {
    ("TRACKWISE", "Investigation"): ["investigation_number", "opened_date", "status"],
    ("TRACKWISE", "CAPA"): ["capa_number", "opened_date", "status"],
    ("PLM", "Product"): ["product_number", "name", "status"],
    ("PLM", "ProductVersion"): ["product_number", "version", "release_date"],
    ("PLM", "Component"): ["component_number", "name", "status"],
    ("PLM", "Change"): ["change_number", "effective_date", "status"],
    ("ERP", "Supplier"): ["supplier_number", "name", "status"],
    ("ERP", "Site"): ["site_number", "name", "status"],
    ("ERP", "Lot"): ["lot_number", "product_number", "status"],
    ("SUPPLIER", "SupplierPart"): ["part_number", "description", "status"],
    ("SUPPLIER", "Certificate"): ["certificate_number", "expiry_date", "status"],
    ("SUPPLIER", "SupplierEvent"): ["event_number", "event_date", "event_type"],
    ("VEEVA_QMS", "QualityEvent"): ["event_number", "opened_date", "severity", "status"],
    ("VEEVA_QMS", "Investigation"): ["investigation_number", "opened_date", "status"],
    ("VEEVA_QMS", "CAPA"): ["capa_number", "opened_date", "status"],
    ("TEAMCENTER", "Item"): ["item_number", "name", "lifecycle"],
    ("TEAMCENTER", "ItemRevision"): ["item_number", "revision", "release_date"],
    ("TEAMCENTER", "ChangeNotice"): ["change_number", "effective_date", "status"],
    ("ORACLE_ERP", "Supplier"): ["supplier_number", "name", "status"],
    ("ORACLE_ERP", "PurchaseOrder"): ["order_number", "supplier_number", "status"],
    ("ORACLE_ERP", "Lot"): ["lot_number", "item_number", "status"],
    ("COUPA", "Supplier"): ["supplier_number", "name", "status"],
    ("COUPA", "PurchaseOrder"): ["order_number", "supplier_number", "status"],
    ("COUPA", "SupplierRisk"): ["risk_number", "supplier_number", "status"],
    ("TRACKWISE", "Complaint"): TRACKWISE_COMPLAINT_FIELDS,
    ("TEAMCENTER", "Product Version"): TEAMCENTER_PRODUCT_VERSION_FIELDS,
}
GENERIC_FIELDS = ["id", "name", "status", "created_at", "updated_at"]

FIELD_GROUPS = [
    ("IDENTIFIERS", "Identifiers"), ("PRODUCT", "Product"), ("DATES", "Dates"), ("REPORTER", "Reporter"),
    ("CLASSIFICATION", "Classification"), ("CLINICAL", "Clinical and safety"), ("LIFECYCLE", "Lifecycle"),
    ("RELATIONSHIPS", "Relationships"), ("AUDIT", "Audit"), ("GENERAL", "General"),
]  # fmt: skip
FIELD_GROUP_OF = {
    "complaint_id": "IDENTIFIERS", "complaint_number": "IDENTIFIERS", "product_code": "PRODUCT",
    "product_revision": "PRODUCT", "event_date": "DATES", "received_date": "DATES", "awareness_date": "DATES",
    "opened_date": "DATES", "country": "REPORTER", "reporter_type": "REPORTER", "complaint_type": "CLASSIFICATION",
    "problem_code": "CLASSIFICATION", "problem_description": "CLASSIFICATION", "severity": "CLASSIFICATION",
    "lot_number": "PRODUCT", "serial_number": "PRODUCT", "udi": "PRODUCT", "device_returned": "CLINICAL",
    "patient_involved": "CLINICAL", "serious_injury": "CLINICAL", "death": "CLINICAL", "malfunction": "CLINICAL",
    "status": "LIFECYCLE", "lifecycle": "LIFECYCLE", "investigation_number": "RELATIONSHIPS",
    "created_at": "AUDIT", "updated_at": "AUDIT", "recorded_at": "AUDIT", "known_at": "AUDIT",
}  # fmt: skip
BOOLEAN_FIELDS = {"device_returned", "patient_involved", "serious_injury", "death", "malfunction"}
CONFIDENTIAL_FIELDS = {"problem_description", "serial_number", "udi"}
SENSITIVE_QUALITY_FIELDS = {"patient_involved", "serious_injury", "death", "malfunction"}


def _source_type(field: str) -> str:
    if field in BOOLEAN_FIELDS:
        return "BOOLEAN"
    if field.endswith("_date"):
        return "DATE"
    if field.endswith("_at"):
        return "DATETIME"
    return "STRING"


# --- Canonical model (Transactional Data Architecture v1.0, md_transaction) ----------------
# Field tuple: (name, data_type, required, reference_entity_code)
STANDARD_SYSTEM_FIELDS = {"tenant_id", "source_record_uuid", "created_at", "updated_at", "created_by", "record_origin"}


def _entity(key: str, *fields):
    """Business entity with its UUID key and business ID (both system-managed)."""
    return [(f"{key}_uuid", "UUID", True, None), (f"{key}_id", "STRING", True, None), ("tenant_id", "UUID", True, None), *fields]


CANONICAL_ENTITIES = {
    "PRODUCT": ("Product", _entity(
        "product",
        ("external_id", "STRING", False, None), ("product_code", "STRING", True, None),
        ("product_name", "STRING", True, None), ("product_family", "STRING", False, None),
        ("product_type", "STRING", False, None), ("manufacturer_name", "STRING", False, None),
        ("lifecycle_status", "STRING", True, None), ("source_record_uuid", "UUID", False, None),
        ("created_at", "DATETIME", True, None), ("updated_at", "DATETIME", True, None),
    )),
    "PRODUCT_VERSION": ("Product Version", _entity(
        "product_version",
        ("product_uuid", "UUID_REF", True, "PRODUCT"), ("external_id", "STRING", False, None),
        ("version_code", "STRING", True, None), ("version_name", "STRING", False, None),
        ("effective_at", "DATETIME", False, None), ("released_at", "DATETIME", False, None),
        ("software_version", "STRING", False, None), ("configuration_reference", "STRING", False, None),
        ("change_reference", "STRING", False, None), ("status", "STRING", True, None),
        ("source_record_uuid", "UUID", False, None), ("created_at", "DATETIME", True, None),
        ("updated_at", "DATETIME", True, None),
    )),
    "COMPONENT": ("Component", _entity(
        "component",
        ("component_code", "STRING", True, None), ("component_name", "STRING", True, None),
        ("revision", "STRING", False, None), ("supplier_uuid", "UUID_REF", False, "SUPPLIER"),
        ("status", "STRING", True, None), ("source_record_uuid", "UUID", False, None),
    )),
    "PRODUCT_COMPONENT": ("Product Component", [
        ("product_component_uuid", "UUID", True, None), ("tenant_id", "UUID", True, None),
        ("product_version_uuid", "UUID_REF", True, "PRODUCT_VERSION"), ("component_uuid", "UUID_REF", True, "COMPONENT"),
        ("quantity", "DECIMAL", False, None), ("effective_from", "DATETIME", False, None),
        ("effective_to", "DATETIME", False, None), ("status", "STRING", True, None),
    ]),
    "SUPPLIER": ("Supplier", _entity(
        "supplier",
        ("supplier_code", "STRING", True, None), ("supplier_name", "STRING", True, None),
        ("country_uuid", "UUID", False, None), ("qualification_status", "STRING", False, None),
        ("status", "STRING", True, None), ("source_record_uuid", "UUID", False, None),
    )),
    "SITE": ("Manufacturing Site", _entity(
        "site",
        ("site_code", "STRING", True, None), ("site_name", "STRING", True, None),
        ("country_uuid", "UUID", False, None), ("status", "STRING", True, None),
        ("source_record_uuid", "UUID", False, None),
    )),
    "LOT": ("Lot / Batch", _entity(
        "lot",
        ("lot_number", "STRING", True, None), ("product_uuid", "UUID_REF", False, "PRODUCT"),
        ("product_version_uuid", "UUID_REF", False, "PRODUCT_VERSION"), ("site_uuid", "UUID_REF", False, "SITE"),
        ("manufactured_at", "DATETIME", False, None), ("released_at", "DATETIME", False, None),
        ("status", "STRING", True, None), ("source_record_uuid", "UUID", False, None),
    )),
    "PRODUCT_CHANGE": ("Product Change", _entity(
        "change",
        ("product_uuid", "UUID_REF", True, "PRODUCT"), ("product_version_uuid", "UUID_REF", False, "PRODUCT_VERSION"),
        ("change_type", "STRING", True, None), ("title", "STRING", True, None), ("description", "TEXT", False, None),
        ("effective_at", "DATETIME", False, None), ("status", "STRING", True, None),
        ("source_record_uuid", "UUID", False, None),
    )),
    "COMPLAINT": ("Complaint", _entity(
        "complaint",
        ("external_id", "STRING", False, None), ("complaint_number", "STRING", True, None),
        ("product_uuid", "UUID_REF", True, "PRODUCT"), ("product_version_uuid", "UUID_REF", False, "PRODUCT_VERSION"),
        ("event_at", "DATETIME", False, None), ("received_at", "DATETIME", False, None),
        ("awareness_at", "DATETIME", False, None), ("country_uuid", "UUID", False, None),
        ("complaint_type", "STRING", False, None), ("problem_code", "STRING", False, None),
        ("problem_description", "TEXT", False, None), ("severity", "ENUM", False, None),
        ("lot_uuid", "UUID_REF", False, "LOT"), ("serial_number", "STRING", False, None), ("udi", "STRING", False, None),
        ("device_returned", "BOOLEAN", False, None), ("patient_involved", "BOOLEAN", False, None),
        ("serious_injury", "BOOLEAN", False, None), ("death", "BOOLEAN", False, None),
        ("malfunction", "BOOLEAN", False, None), ("status", "STRING", True, None),
        ("source_record_uuid", "UUID", False, None),
    )),
    "SIGNAL": ("Signal", _entity(
        "signal",
        ("product_uuid", "UUID_REF", True, "PRODUCT"), ("product_version_uuid", "UUID_REF", False, "PRODUCT_VERSION"),
        ("signal_type", "STRING", True, None), ("title", "STRING", True, None), ("description", "TEXT", False, None),
        ("detected_at", "DATETIME", True, None), ("severity", "STRING", False, None),
        ("origin_type", "STRING", True, None), ("status", "STRING", True, None), ("created_by", "UUID", True, None),
        ("created_at", "DATETIME", True, None), ("updated_at", "DATETIME", True, None),
    )),
    "INVESTIGATION": ("Investigation", _entity(
        "investigation",
        ("product_uuid", "UUID_REF", True, "PRODUCT"), ("product_version_uuid", "UUID_REF", False, "PRODUCT_VERSION"),
        ("signal_uuid", "UUID_REF", False, "SIGNAL"), ("investigation_question", "TEXT", True, None),
        ("title", "STRING", True, None), ("investigation_type", "STRING", False, None),
        ("priority", "STRING", False, None), ("status", "STRING", True, None), ("owner_user_id", "UUID", False, None),
        ("opened_at", "DATETIME", True, None), ("due_at", "DATETIME", False, None), ("closed_at", "DATETIME", False, None),
        ("source_record_uuid", "UUID", False, None), ("created_by", "UUID", True, None),
        ("created_at", "DATETIME", True, None), ("updated_at", "DATETIME", True, None),
    )),
    "EVIDENCE": ("Evidence", _entity(
        "evidence",
        ("evidence_type", "STRING", True, None), ("title", "STRING", True, None), ("description", "TEXT", False, None),
        ("source_record_uuid", "UUID", False, None), ("document_reference", "STRING", False, None),
        ("object_storage_reference", "STRING", False, None), ("checksum", "STRING", False, None),
        ("effective_at", "DATETIME", False, None), ("recorded_at", "DATETIME", False, None),
        ("known_at", "DATETIME", False, None), ("reliability_status", "STRING", False, None),
        ("review_status", "STRING", True, None), ("created_at", "DATETIME", True, None),
        ("updated_at", "DATETIME", True, None),
    )),
    # Section 3.16 tables: entity registered; fields are defined with their tables in Phase 3.
    "RISK": ("Risk", _entity("risk", ("status", "STRING", True, None))),
    "HAZARD": ("Hazard", _entity("hazard", ("status", "STRING", True, None))),
    "FAILURE_MODE": ("Failure Mode", _entity("failure_mode", ("status", "STRING", True, None))),
    "CONTROL": ("Control", _entity("control", ("status", "STRING", True, None))),
    "RISK_ASSESSMENT": ("Risk Assessment", _entity("risk_assessment", ("status", "STRING", True, None))),
    "CAPA": ("CAPA", _entity("capa", ("status", "STRING", True, None))),
    "VIGILANCE_ASSESSMENT": ("Vigilance Assessment", _entity("vigilance_assessment", ("status", "STRING", True, None))),
    "FIELD_ACTION": ("Field Action", _entity("field_action", ("status", "STRING", True, None))),
    "RECALL": ("Recall", _entity("recall", ("status", "STRING", True, None))),
}  # fmt: skip
CONFIDENTIAL_CANONICAL = {"problem_description", "serial_number", "udi"}


def _system_managed(fields: list, field: str) -> bool:
    """Primary key, business ID and standard system columns are never mapping targets."""
    key = fields[0][0]
    business_id = fields[1][0] if fields[1][0].endswith("_id") and fields[1][1] == "STRING" else None
    return field in STANDARD_SYSTEM_FIELDS or field in {key, business_id}


# --- Mapping governance --------------------------------------------------------------------

OVERRIDE_POLICIES = [
    # code, name, source, target, transform, validation, enum, requires_approval
    ("CUSTOMER_OVERRIDE_ALLOWED", "Customer Override Allowed", True, False, True, True, True, True),
    ("RESTRICTED", "Restricted", False, False, True, False, True, True),
    ("PLATFORM_ONLY", "Platform Only", False, False, False, False, False, True),
]
SOURCE_AUTHORITIES = [
    ("AUTHORITATIVE", "Authoritative", "System of record for the value.", 10),
    ("REFERENCE", "Reference", "Trusted reference that does not own the value.", 20),
    ("SUPPLEMENTARY", "Supplementary", "Adds context; never overrides authoritative values.", 30),
    ("OBSERVED_SOURCE_VALUE", "Observed Source Value", "Value as observed in the source, unverified.", 40),
]
TRANSFORMATIONS = [
    ("DIRECT_COPY", "Direct Copy", "DIRECT", "Copies the source value unchanged.", None, False),
    ("TRIM", "Trim Whitespace", "FORMAT", "Removes leading and trailing whitespace.", None, True),
    ("UPPERCASE", "Uppercase", "FORMAT", "Converts text to upper case.", None, True),
    ("LOWERCASE", "Lowercase", "FORMAT", "Converts text to lower case.", None, True),
    ("DATE_PARSE", "Date Parse", "FORMAT", "Parses a date/timestamp into UTC.", {"format": "string", "timezone": "iana"}, True),
    ("BOOLEAN_MAP", "Boolean Map", "VALUE", "Maps source tokens to true/false.", {"true_values": "array", "false_values": "array"}, True),
    ("ENUM_MAP", "Enumeration Map", "VALUE", "Maps source enumeration values through a value mapping.", {"value_set": "string"}, True),
    ("LOOKUP", "Lookup", "LOOKUP", "Resolves a value through a reference resolution rule.", {"reference_rule": "string"}, False),
    ("UNIT_CONVERSION", "Unit Conversion", "VALUE", "Converts a quantity between units of measure.", {"from_unit": "string", "to_unit": "string"}, False),
]  # fmt: skip
VALIDATION_RULES = [
    ("REQUIRED", "Required", "FIELD", "Value must be present.", "ERROR", True),
    ("TYPE", "Type", "FIELD", "Value must match the declared data type.", "ERROR", True),
    ("FORMAT", "Format", "FIELD", "Value must match the declared format.", "WARNING", False),
    ("ENUM", "Enumeration", "FIELD", "Value must belong to the controlled value set.", "ERROR", False),
    ("RANGE", "Range", "FIELD", "Value must fall within the configured range.", "WARNING", False),
    ("DATE", "Date", "FIELD", "Value must be a valid date/timestamp.", "ERROR", False),
    ("REFERENCE", "Reference", "REFERENCE", "Referenced record must resolve.", "ERROR", True),
    ("UNIQUENESS", "Uniqueness", "CROSS_FIELD", "Value must be unique within its tenant scope.", "ERROR", True),
]
REFERENCE_RULES = [
    ("PRODUCT_LOOKUP", "PRODUCT", ["product_code"]),
    ("PRODUCT_VERSION_LOOKUP", "PRODUCT_VERSION", ["product_code", "version_code"]),
    ("LOT_LOOKUP", "LOT", ["lot_number"]),
    ("SUPPLIER_LOOKUP", "SUPPLIER", ["supplier_code"]),
    ("COMPONENT_LOOKUP", "COMPONENT", ["component_code"]),
    ("SITE_LOOKUP", "SITE", ["site_code"]),
]
DATA_QUALITY_RULES = [
    ("AWARENESS_AFTER_EVENT", "COMPLAINT", "TEMPORAL", "awareness_at >= event_at", "WARNING", False),
    ("RECEIVED_AFTER_EVENT", "COMPLAINT", "TEMPORAL", "received_at >= event_at", "WARNING", False),
    ("VERSION_BELONGS_TO_PRODUCT", "COMPLAINT", "REFERENTIAL", "product_version_uuid must belong to product_uuid", "BLOCKING", True),
]  # fmt: skip

FAMILY_OBJECT = {
    # family suffix -> (source object name hint, default canonical entity)
    "COMPLAINT": ("Complaint", "COMPLAINT"), "INVESTIGATION": ("Investigation", "INVESTIGATION"),
    "CAPA": ("CAPA", "CAPA"), "EVIDENCE": ("Evidence", "EVIDENCE"), "QUALITY_EVENT": ("QualityEvent", "COMPLAINT"),
    "DOCUMENT": ("Document", "EVIDENCE"), "PRODUCT": ("Product", "PRODUCT"),
    "PRODUCT_VERSION": ("Product Version", "PRODUCT_VERSION"), "COMPONENT": ("Component", "COMPONENT"),
    "BOM": ("BOM", "PRODUCT_COMPONENT"), "PRODUCT_CHANGE": ("Change", "PRODUCT_CHANGE"), "SUPPLIER": ("Supplier", "SUPPLIER"),
    "SITE": ("Manufacturing Site", "SITE"), "LOT": ("Lot", "LOT"), "BATCH": ("Batch", "LOT"), "MATERIAL": ("Material", "COMPONENT"),
    "CASE": ("Case", "COMPLAINT"), "SERVICE_EVENT": ("Service Event", "COMPLAINT"), "RISK": ("Risk", "RISK"),
    "FAILURE_MODE": ("Failure Mode", "FAILURE_MODE"), "CONTROL": ("Control", "CONTROL"),
    "VIGILANCE": ("Vigilance", "VIGILANCE_ASSESSMENT"), "REGULATORY_ASSESSMENT": ("Regulatory Assessment", "VIGILANCE_ASSESSMENT"),
    "FIELD_ACTION": ("Field Action", "FIELD_ACTION"), "RECALL": ("Recall", "RECALL"), "RESULT": ("Result", "EVIDENCE"),
    "SAMPLE": ("Sample", "EVIDENCE"), "PRODUCTION_RECORD": ("Production Record", "LOT"), "GENEALOGY": ("Genealogy", "LOT"),
    "PROCESS_EVENT": ("Process Event", "EVIDENCE"),
}  # fmt: skip
FAMILY_APP_PREFIX = {
    "TRACKWISE": "TRACKWISE", "VEEVA": "VEEVA_QMS", "PLM": "TEAMCENTER", "SAP": "SAP_ERP", "SALESFORCE": "SALESFORCE_SERVICE",
    "RISK": "RISK", "RIM": "RIM", "SAFETY": "SAFETY", "LIMS": "LIMS", "MES": "MES",
}  # fmt: skip
FAMILIES = [
    "TRACKWISE_COMPLAINT", "TRACKWISE_INVESTIGATION", "TRACKWISE_CAPA", "TRACKWISE_EVIDENCE", "VEEVA_QUALITY_EVENT",
    "VEEVA_INVESTIGATION", "VEEVA_EVIDENCE", "VEEVA_DOCUMENT", "PLM_PRODUCT", "PLM_PRODUCT_VERSION", "PLM_COMPONENT",
    "PLM_BOM", "PLM_PRODUCT_CHANGE", "SAP_SUPPLIER", "SAP_SITE", "SAP_LOT", "SAP_BATCH", "SAP_MATERIAL", "SALESFORCE_CASE",
    "SALESFORCE_SERVICE_EVENT", "RISK_RISK", "RISK_FAILURE_MODE", "RISK_CONTROL", "RIM_VIGILANCE",
    "RIM_REGULATORY_ASSESSMENT", "SAFETY_FIELD_ACTION", "SAFETY_RECALL", "LIMS_RESULT", "LIMS_SAMPLE",
    "MES_PRODUCTION_RECORD", "MES_GENEALOGY", "MES_PROCESS_EVENT",
]  # fmt: skip

# Released M1 items: (source field, canonical field, mapping type, transform, reference rule, override policy, required)
RELEASED_MAPPINGS = {
    "TRACKWISE_COMPLAINT": [
        ("complaint_id", "external_id", "DIRECT", "DIRECT_COPY", None, "PLATFORM_ONLY", False),
        ("complaint_number", "complaint_number", "DIRECT", "DIRECT_COPY", None, "PLATFORM_ONLY", True),
        ("product_code", "product_uuid", "REFERENCE", "LOOKUP", "PRODUCT_LOOKUP", "RESTRICTED", True),
        ("product_revision", "product_version_uuid", "REFERENCE", "LOOKUP", "PRODUCT_VERSION_LOOKUP", "RESTRICTED", False),
        ("event_date", "event_at", "TRANSFORM", "DATE_PARSE", None, "CUSTOMER_OVERRIDE_ALLOWED", False),
        ("received_date", "received_at", "TRANSFORM", "DATE_PARSE", None, "CUSTOMER_OVERRIDE_ALLOWED", False),
        ("awareness_date", "awareness_at", "TRANSFORM", "DATE_PARSE", None, "CUSTOMER_OVERRIDE_ALLOWED", False),
        ("country", "country_uuid", "LOOKUP", "LOOKUP", None, "CUSTOMER_OVERRIDE_ALLOWED", False),
        ("complaint_type", "complaint_type", "DIRECT", "DIRECT_COPY", None, "CUSTOMER_OVERRIDE_ALLOWED", False),
        ("problem_code", "problem_code", "DIRECT", "DIRECT_COPY", None, "CUSTOMER_OVERRIDE_ALLOWED", False),
        ("problem_description", "problem_description", "DIRECT", "DIRECT_COPY", None, "CUSTOMER_OVERRIDE_ALLOWED", False),
        ("severity", "severity", "TRANSFORM", "ENUM_MAP", None, "CUSTOMER_OVERRIDE_ALLOWED", False),
        ("lot_number", "lot_uuid", "REFERENCE", "LOOKUP", "LOT_LOOKUP", "CUSTOMER_OVERRIDE_ALLOWED", False),
        ("serial_number", "serial_number", "DIRECT", "DIRECT_COPY", None, "CUSTOMER_OVERRIDE_ALLOWED", False),
        ("udi", "udi", "DIRECT", "DIRECT_COPY", None, "CUSTOMER_OVERRIDE_ALLOWED", False),
        ("device_returned", "device_returned", "TRANSFORM", "BOOLEAN_MAP", None, "CUSTOMER_OVERRIDE_ALLOWED", False),
        ("patient_involved", "patient_involved", "TRANSFORM", "BOOLEAN_MAP", None, "CUSTOMER_OVERRIDE_ALLOWED", False),
        ("serious_injury", "serious_injury", "TRANSFORM", "BOOLEAN_MAP", None, "CUSTOMER_OVERRIDE_ALLOWED", False),
        ("death", "death", "TRANSFORM", "BOOLEAN_MAP", None, "CUSTOMER_OVERRIDE_ALLOWED", False),
        ("malfunction", "malfunction", "TRANSFORM", "BOOLEAN_MAP", None, "CUSTOMER_OVERRIDE_ALLOWED", False),
        ("status", "status", "DIRECT", "DIRECT_COPY", None, "CUSTOMER_OVERRIDE_ALLOWED", True),
    ],
    "PLM_PRODUCT_VERSION": [
        ("version_id", "external_id", "DIRECT", "DIRECT_COPY", None, "PLATFORM_ONLY", False),
        ("product_id", "product_uuid", "REFERENCE", "LOOKUP", "PRODUCT_LOOKUP", "RESTRICTED", True),
        ("revision", "version_code", "DIRECT", "DIRECT_COPY", None, "RESTRICTED", True),
        ("version_name", "version_name", "DIRECT", "DIRECT_COPY", None, "CUSTOMER_OVERRIDE_ALLOWED", False),
        ("effective_date", "effective_at", "TRANSFORM", "DATE_PARSE", None, "CUSTOMER_OVERRIDE_ALLOWED", False),
        ("release_date", "released_at", "TRANSFORM", "DATE_PARSE", None, "CUSTOMER_OVERRIDE_ALLOWED", False),
        ("status", "status", "DIRECT", "DIRECT_COPY", None, "CUSTOMER_OVERRIDE_ALLOWED", True),
        ("software_version", "software_version", "DIRECT", "DIRECT_COPY", None, "CUSTOMER_OVERRIDE_ALLOWED", False),
        ("configuration_id", "configuration_reference", "DIRECT", "DIRECT_COPY", None, "CUSTOMER_OVERRIDE_ALLOWED", False),
        ("change_order_id", "change_reference", "DIRECT", "DIRECT_COPY", None, "CUSTOMER_OVERRIDE_ALLOWED", False),
    ],
}  # fmt: skip

VALUE_SETS = {
    "COMPLAINT_SEVERITY": ("Complaint Severity", "Quality", [("MINOR", "Minor"), ("MAJOR", "Major"), ("CRITICAL", "Critical")]),
    "COMPLAINT_STATUS": ("Complaint Status", "Quality", [("OPEN", "Open"), ("UNDER_INVESTIGATION", "Under Investigation"), ("CLOSED", "Closed")]),
    "INVESTIGATION_PRIORITY": ("Investigation Priority", "Quality", [("LOW", "Low"), ("MEDIUM", "Medium"), ("HIGH", "High"), ("CRITICAL", "Critical")]),
    "MATERIALITY": ("Materiality", "Quality", [("LOW", "Low"), ("MEDIUM", "Medium"), ("HIGH", "High")]),
}  # fmt: skip
# TrackWise severity enumeration -> COMPLAINT_SEVERITY
TRACKWISE_SEVERITY = [("MIN", "Minor", "MINOR"), ("MAJ", "Major", "MAJOR"), ("CRIT", "Critical", "CRITICAL")]

# --- Integration masters ---------------------------------------------------------------------

AUTH_TYPES = [
    ("API_KEY", "API Key", {"api_key_secret_ref": "string"}),
    ("BEARER_TOKEN", "Bearer Token", {"token_secret_ref": "string"}),
    ("OAUTH2_CLIENT_CREDENTIALS", "OAuth2 Client Credentials", {"client_id_ref": "string", "client_secret_ref": "string", "token_url": "string"}),
    ("BASIC_AUTH", "Basic Authentication", {"username_ref": "string", "password_secret_ref": "string"}),
    ("MUTUAL_TLS", "Mutual TLS", {"certificate_secret_ref": "string", "private_key_secret_ref": "string"}),
]  # fmt: skip
PAGINATION_TYPES = [("NONE", "None"), ("OFFSET_LIMIT", "Offset / Limit"), ("PAGE_NUMBER", "Page Number"), ("CURSOR", "Cursor"), ("NEXT_LINK", "Next Link")]
SYNC_MODES = [("FULL", "Full"), ("INCREMENTAL", "Incremental"), ("WEBHOOK", "Webhook"), ("HYBRID", "Hybrid"), ("MANUAL", "Manual"), ("SCHEDULED", "Scheduled")]
# Connectors: previous CONNECTOR_VERSIONS catalog plus the three generic simulators.
CONNECTOR_APPS = ["TRACKWISE", "TEAMCENTER", "SAP_ERP", "SALESFORCE_SERVICE", "VEEVA_QMS", "ORACLE_ERP", "COUPA", "PLM", "ERP", "SUPPLIER"]

# --- Reference, security and regulatory masters ------------------------------------------------

DATA_CLASSIFICATIONS = [
    # code, name, level, mask, encrypt, export_restricted, ai_restricted
    ("PUBLIC", "Public", 0, False, False, False, False),
    ("INTERNAL", "Internal", 1, False, False, False, False),
    ("CONFIDENTIAL", "Confidential", 2, False, True, True, False),
    ("RESTRICTED", "Restricted", 3, True, True, True, True),
    ("PII", "Personally Identifiable Information", 4, True, True, True, True),
    ("PHI", "Protected Health Information", 5, True, True, True, True),
    ("SENSITIVE_QUALITY", "Sensitive Quality Information", 3, False, True, True, False),
    ("REGULATORY", "Regulatory Information", 2, False, True, True, False),
]
COUNTRIES = [
    ("IN", "IND", "India", "APAC"), ("US", "USA", "United States", "AMERICAS"), ("GB", "GBR", "United Kingdom", "EMEA"),
    ("DE", "DEU", "Germany", "EMEA"), ("FR", "FRA", "France", "EMEA"), ("IE", "IRL", "Ireland", "EMEA"),
    ("NL", "NLD", "Netherlands", "EMEA"), ("BE", "BEL", "Belgium", "EMEA"), ("CH", "CHE", "Switzerland", "EMEA"),
    ("IT", "ITA", "Italy", "EMEA"), ("ES", "ESP", "Spain", "EMEA"), ("SE", "SWE", "Sweden", "EMEA"),
    ("DK", "DNK", "Denmark", "EMEA"), ("FI", "FIN", "Finland", "EMEA"), ("NO", "NOR", "Norway", "EMEA"),
    ("AT", "AUT", "Austria", "EMEA"), ("PL", "POL", "Poland", "EMEA"), ("PT", "PRT", "Portugal", "EMEA"),
    ("CA", "CAN", "Canada", "AMERICAS"), ("MX", "MEX", "Mexico", "AMERICAS"), ("BR", "BRA", "Brazil", "AMERICAS"),
    ("AU", "AUS", "Australia", "APAC"), ("NZ", "NZL", "New Zealand", "APAC"), ("JP", "JPN", "Japan", "APAC"),
    ("CN", "CHN", "China", "APAC"), ("KR", "KOR", "South Korea", "APAC"), ("SG", "SGP", "Singapore", "APAC"),
    ("IL", "ISR", "Israel", "EMEA"), ("ZA", "ZAF", "South Africa", "EMEA"), ("AE", "ARE", "United Arab Emirates", "EMEA"),
]  # fmt: skip
REGIONS = [
    ("IN", "TG", "Telangana", "State"), ("IN", "KA", "Karnataka", "State"), ("IN", "MH", "Maharashtra", "State"),
    ("US", "CA", "California", "State"), ("US", "MA", "Massachusetts", "State"), ("US", "MN", "Minnesota", "State"),
    ("DE", "BY", "Bavaria", "State"), ("DE", "BW", "Baden-Wuerttemberg", "State"),
]  # fmt: skip
TIMEZONES = [
    ("UTC", "Coordinated Universal Time"), ("Asia/Kolkata", "India Standard Time"),
    ("America/New_York", "US Eastern Time"), ("America/Chicago", "US Central Time"), ("America/Denver", "US Mountain Time"),
    ("America/Los_Angeles", "US Pacific Time"), ("America/Toronto", "Canada Eastern Time"),
    ("America/Sao_Paulo", "Brasilia Time"), ("Europe/London", "UK Time"), ("Europe/Dublin", "Ireland Time"),
    ("Europe/Berlin", "Central European Time (Berlin)"), ("Europe/Paris", "Central European Time (Paris)"),
    ("Europe/Zurich", "Central European Time (Zurich)"), ("Europe/Amsterdam", "Central European Time (Amsterdam)"),
    ("Asia/Dubai", "Gulf Standard Time"), ("Asia/Jerusalem", "Israel Time"), ("Asia/Singapore", "Singapore Time"),
    ("Asia/Shanghai", "China Standard Time"), ("Asia/Tokyo", "Japan Standard Time"), ("Australia/Sydney", "Australian Eastern Time"),
]  # fmt: skip
# code, name, dimension, canonical code, factor to canonical
UNITS = [
    ("g", "Gram", "Mass", None, None), ("mg", "Milligram", "Mass", "g", "0.001"), ("kg", "Kilogram", "Mass", "g", "1000"),
    ("L", "Litre", "Volume", None, None), ("mL", "Millilitre", "Volume", "L", "0.001"),
    ("m", "Metre", "Length", None, None), ("mm", "Millimetre", "Length", "m", "0.001"), ("cm", "Centimetre", "Length", "m", "0.01"),
    ("s", "Second", "Time", None, None), ("min", "Minute", "Time", "s", "60"), ("h", "Hour", "Time", "s", "3600"),
    ("°C", "Degree Celsius", "Temperature", None, None), ("V", "Volt", "Voltage", None, None),
    ("A", "Ampere", "Current", None, None), ("mA", "Milliampere", "Current", "A", "0.001"),
    ("Pa", "Pascal", "Pressure", None, None), ("kPa", "Kilopascal", "Pressure", "Pa", "1000"), ("%", "Percent", "Ratio", None, None),
]  # fmt: skip
JURISDICTIONS = [
    ("USA", "United States", "COUNTRY", "US"), ("EU", "European Union", "REGION", None), ("UK", "United Kingdom", "COUNTRY", "GB"),
    ("CANADA", "Canada", "COUNTRY", "CA"), ("AUSTRALIA", "Australia", "COUNTRY", "AU"), ("JAPAN", "Japan", "COUNTRY", "JP"),
    ("INDIA", "India", "COUNTRY", "IN"),
]  # fmt: skip
AUTHORITIES = [
    ("US_FDA", "U.S. Food and Drug Administration", "USA", "US", "Regulator", "https://www.fda.gov"),
    ("UK_MHRA", "Medicines and Healthcare products Regulatory Agency", "UK", "GB", "Regulator", "https://www.gov.uk/mhra"),
    ("HEALTH_CANADA", "Health Canada", "CANADA", "CA", "Regulator", "https://www.canada.ca/en/health-canada.html"),
    ("AU_TGA", "Therapeutic Goods Administration", "AUSTRALIA", "AU", "Regulator", "https://www.tga.gov.au"),
    ("JP_PMDA", "Pharmaceuticals and Medical Devices Agency", "JAPAN", "JP", "Regulator", "https://www.pmda.go.jp"),
    ("IN_CDSCO", "Central Drugs Standard Control Organisation", "INDIA", "IN", "Regulator", "https://cdsco.gov.in"),
]  # fmt: skip
CHANGE_REASONS = [
    ("SOURCE_SCHEMA_CHANGE", "Source Schema Change", True, True),
    ("CUSTOMER_REQUEST", "Customer Request", True, True),
    ("REGULATORY_CHANGE", "Regulatory Change", True, True),
    ("BUG_FIX", "Bug Fix", True, False),
    ("MAPPING_CORRECTION", "Mapping Correction", True, True),
]
RECORD_STATUSES = {
    "APPLICATION": [("DRAFT", "Draft", False), ("ACTIVE", "Active", False), ("DEPRECATED", "Deprecated", False), ("RETIRED", "Retired", True)],
    "MAPPING": [("DRAFT", "Draft", False), ("VALIDATION", "Validation", False), ("APPROVED", "Approved", False),
                ("RELEASED", "Released", False), ("SUPERSEDED", "Superseded", True), ("RETIRED", "Retired", True)],
    "CONNECTOR": [("ACTIVE", "Active", False), ("DEPRECATED", "Deprecated", False), ("RETIRED", "Retired", True)],
}  # fmt: skip

# --- AI governance masters -----------------------------------------------------------------------

AI_OUTPUT_TYPES = [
    ("INVESTIGATION_ANALYSIS", "Investigation Analysis"), ("PRODUCT_SUMMARY", "Product Summary"),
    ("EVIDENCE_EXTRACTION", "Evidence Extraction"), ("HYPOTHESIS_GENERATION", "Hypothesis Generation"),
    ("CHALLENGER", "Challenger"), ("UNKNOWNS", "Unknowns Radar"), ("FAILURE_CHAIN", "Failure Chain"),
    ("SCENARIO", "Scenario / Counterfactual"), ("DECISION_BRIEF", "Decision Brief"),
    ("ASK_MDARIX_ANSWER", "Ask MDARIX Answer"), ("REGULATORY_DRAFT", "Regulatory Draft"),
]  # fmt: skip
GUARDRAILS = [
    ("TENANT_ISOLATION", "Tenant Isolation", "Context contains only the authenticated tenant's records.", "BLOCKING", True),
    ("SOURCE_GROUNDING_REQUIRED", "Source Grounding Required", "Every statement cites an authorized source.", "BLOCKING", True),
    ("UNKNOWN_PRESERVATION", "Unknown Preservation", "Material unknowns are preserved, not suppressed.", "BLOCKING", True),
    ("NO_AUTOMATIC_APPROVAL", "No Automatic Approval", "AI never approves or signs regulated decisions.", "BLOCKING", True),
    ("CAUSALITY_RESTRAINT", "Causality Restraint", "Causality is not asserted without authorized human review.", "BLOCKING", True),
    ("PII_REDACTION", "PII Redaction", "Personal data is removed from AI context.", "BLOCKING", True),
    ("PROMPT_INJECTION_SCREEN", "Prompt Injection Screen", "Source content is treated as data, never instructions.", "WARNING", False),
]  # fmt: skip


# --- Loader ---------------------------------------------------------------------------------------


def _insert(conn, table: str, pk: str, **values):
    columns = list(values)
    placeholders = [f"cast(:{c} as jsonb)" if isinstance(values[c], (dict, list)) else f":{c}" for c in columns]
    sql = f"insert into md_master.{table} ({', '.join(columns)}) values ({', '.join(placeholders)}) returning {pk}"
    params = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in values.items()}
    return conn.execute(text(sql), params).scalar_one()


def load(conn) -> dict[str, int]:
    """Load Master Data seed v1 into md_master (idempotent: skips if already loaded)."""
    if conn.execute(text("select count(*) from md_master.industry_domain")).scalar_one():
        return {"skipped": 1}
    counts: dict[str, int] = {}

    def count(table):
        counts[table] = counts.get(table, 0) + 1

    ids: dict[tuple, object] = {}

    for code, name, sensitivity, mask, encrypt, export, ai in DATA_CLASSIFICATIONS:
        ids["dcl", code] = _insert(
            conn, "data_classification", "classification_uuid", classification_code=code, classification_name=name,
            sensitivity_level=sensitivity, masking_required=mask, encryption_required=encrypt,
            export_restricted=export, ai_usage_restricted=ai,
        )  # fmt: skip
        count("data_classification")
    for alpha2, alpha3, name, group in COUNTRIES:
        ids["country", alpha2] = _insert(
            conn, "country_reference", "country_uuid", iso_alpha2=alpha2, iso_alpha3=alpha3, country_name=name,
            region_group=group,
        )  # fmt: skip
        count("country_reference")
    for country, code, name, kind in REGIONS:
        _insert(conn, "region_reference", "region_uuid", country_uuid=ids["country", country], region_code=code,
                region_name=name, region_type=kind)  # fmt: skip
        count("region_reference")
    for iana, display in TIMEZONES:
        _insert(conn, "timezone_reference", "timezone_uuid", iana_name=iana, display_name=display)
        count("timezone_reference")
    for code, name, dimension, canonical, factor in UNITS:
        ids["uom", code] = _insert(
            conn, "unit_of_measure", "uom_uuid", uom_code=code, uom_name=name, dimension=dimension,
            canonical_unit_uuid=ids.get(("uom", canonical)) if canonical else None, conversion_factor=factor,
        )  # fmt: skip
        count("unit_of_measure")
    for code, name, kind, country in JURISDICTIONS:
        ids["jur", code] = _insert(
            conn, "jurisdiction_reference", "jurisdiction_uuid", jurisdiction_code=code, jurisdiction_name=name,
            jurisdiction_type=kind, country_uuid=ids["country", country] if country else None,
        )  # fmt: skip
        count("jurisdiction_reference")
    for code, name, jur, country, kind, site in AUTHORITIES:
        _insert(conn, "regulatory_authority", "authority_uuid", authority_code=code, authority_name=name,
                jurisdiction_uuid=ids["jur", jur], country_uuid=ids["country", country], authority_type=kind,
                website_reference=site)  # fmt: skip
        count("regulatory_authority")
    for code, label, comment, approval in CHANGE_REASONS:
        _insert(conn, "change_reason_code", "change_reason_uuid", reason_code=code, reason_label=label,
                requires_comment=comment, requires_approval=approval)  # fmt: skip
        count("change_reason_code")
    for domain, statuses in RECORD_STATUSES.items():
        for order, (code, label, terminal) in enumerate(statuses, 1):
            _insert(conn, "record_status_definition", "status_uuid", domain=domain, status_code=code,
                    status_label=label, terminal=terminal, display_order=order)  # fmt: skip
            count("record_status_definition")
    for code, name in AI_OUTPUT_TYPES:
        _insert(conn, "ai_output_type_definition", "ai_output_type_uuid", output_code=code, output_name=name,
                human_review_required=True, regulated_decision_prohibited=True)  # fmt: skip
        count("ai_output_type_definition")
    for code, name, description, severity, blocking in GUARDRAILS:
        _insert(conn, "ai_guardrail_definition", "guardrail_uuid", guardrail_code=code, guardrail_name=name,
                description=description, severity=severity, blocking=blocking)  # fmt: skip
        count("ai_guardrail_definition")

    for order, (code, name, description) in enumerate(INDUSTRIES, 1):
        ids["industry", code] = _insert(conn, "industry_domain", "industry_uuid", industry_code=code,
                                        industry_name=name, description=description, display_order=order)  # fmt: skip
        count("industry_domain")
    for order, (code, name) in enumerate(CATEGORIES, 1):
        ids["category", code] = _insert(conn, "application_category", "category_uuid", category_code=code,
                                        category_name=name, display_order=order)  # fmt: skip
        count("application_category")
    for code, name, site in VENDORS:
        ids["vendor", code] = _insert(conn, "application_vendor", "vendor_uuid", vendor_code=code, vendor_name=name,
                                      website=site)  # fmt: skip
        count("application_vendor")

    for code, name, category, vendor, support in APPLICATIONS:
        app = ids["app", code] = _insert(
            conn, "external_application", "application_uuid", application_code=code, application_name=name,
            vendor_uuid=ids["vendor", vendor], category_uuid=ids["category", category],
            description=f"Controlled {name} metadata catalog", integration_support_status=support,
            supports_api=True, supports_webhook=False, supports_schema_discovery=True,
            supports_incremental_sync=support == "SUPPORTED", status="ACTIVE",
        )  # fmt: skip
        count("external_application")
        industries = ["MEDICAL_DEVICE"] + (["PHARMACEUTICAL", "BIOTECH"] if code in MULTI_INDUSTRY_APPS else [])
        for industry in industries:
            _insert(conn, "external_application_industry", "relation_uuid", application_uuid=app,
                    industry_uuid=ids["industry", industry], is_primary=industry == "MEDICAL_DEVICE")  # fmt: skip
            count("external_application_industry")
        ids["appver", code] = _insert(conn, "application_version_definition", "application_version_uuid",
                                      application_uuid=app, version_code="v1", api_version="v1", schema_version="v1",
                                      support_status="SUPPORTED")  # fmt: skip
        count("application_version_definition")

    for order, (code, name) in enumerate(FIELD_GROUPS, 1):
        ids["group", code] = _insert(conn, "field_group_definition", "field_group_uuid", group_code=code,
                                     group_name=name, display_order=order)  # fmt: skip
        count("field_group_definition")

    for app_code, objects in APPLICATION_OBJECTS.items():
        for name in objects:
            object_code = _code(name)
            if ("object", app_code, object_code) in ids:
                continue
            fields = SIMULATOR_FIELDS.get((app_code, name), GENERIC_FIELDS)
            primary = "complaint_id" if (app_code, name) == ("TRACKWISE", "Complaint") else fields[0]
            obj = ids["object", app_code, object_code] = _insert(
                conn, "source_object_definition", "source_object_uuid", application_uuid=ids["app", app_code],
                application_version_uuid=ids["appver", app_code], object_code=object_code, object_name=name,
                api_object_name=name, primary_key_field=primary,
                incremental_cursor_field="updated_at" if "updated_at" in fields else None, schema_version="v1",
            )  # fmt: skip
            count("source_object_definition")
            for field in fields:
                classification = (
                    "CONFIDENTIAL" if field in CONFIDENTIAL_FIELDS
                    else "SENSITIVE_QUALITY" if field in SENSITIVE_QUALITY_FIELDS else "INTERNAL"
                )  # fmt: skip
                ids["sfield", app_code, object_code, field] = _insert(
                    conn, "source_field_definition", "source_field_uuid", source_object_uuid=obj, field_name=field,
                    field_label=_label(field), field_group_uuid=ids["group", FIELD_GROUP_OF.get(field, "GENERAL")],
                    data_type=_source_type(field), required=field == primary, nullable=field != primary,
                    data_classification_uuid=ids["dcl", classification], introduced_schema_version="v1",
                )  # fmt: skip
                count("source_field_definition")

    for code, name, source, target, transform, validation, enum, approval in OVERRIDE_POLICIES:
        ids["policy", code] = _insert(
            conn, "mapping_override_policy", "override_policy_uuid", policy_code=code, policy_name=name,
            can_edit_source=source, can_edit_target=target, can_edit_transform=transform,
            can_edit_validation=validation, can_edit_enum_mapping=enum, requires_approval=approval,
        )  # fmt: skip
        count("mapping_override_policy")
    for code, name, description, precedence in SOURCE_AUTHORITIES:
        ids["authority", code] = _insert(conn, "source_authority_type", "source_authority_uuid", authority_code=code,
                                         authority_name=name, description=description, precedence=precedence)  # fmt: skip
        count("source_authority_type")

    for key, (name, _fields) in CANONICAL_ENTITIES.items():
        ids["entity", key] = _insert(conn, "canonical_entity_definition", "canonical_entity_uuid", entity_code=key,
                                     entity_name=name, domain="Medical Device", version="v1",
                                     description=f"Canonical {name} (Transactional Data Architecture v1.0)")  # fmt: skip
        count("canonical_entity_definition")
    for key, (_name, fields) in CANONICAL_ENTITIES.items():
        for field, data_type, required, reference in fields:
            system = _system_managed(fields, field)
            policy = "PLATFORM_ONLY" if system else "RESTRICTED" if data_type == "UUID_REF" else "CUSTOMER_OVERRIDE_ALLOWED"
            classification = "CONFIDENTIAL" if field in CONFIDENTIAL_CANONICAL else "SENSITIVE_QUALITY" if field in SENSITIVE_QUALITY_FIELDS else "INTERNAL"
            ids["cfield", key, field] = _insert(
                conn, "canonical_field_definition", "canonical_field_uuid", canonical_entity_uuid=ids["entity", key],
                field_name=field, field_label=_label(field), data_type=data_type, required=required,
                nullable=not required, reference_entity_uuid=ids["entity", reference] if reference else None,
                system_managed=system, mapping_allowed=not system, override_policy_uuid=ids["policy", policy],
                data_classification_uuid=ids["dcl", classification],
            )  # fmt: skip
            count("canonical_field_definition")

    for code, name, category, description, parameters, override in TRANSFORMATIONS:
        ids["transform", code] = _insert(
            conn, "transformation_definition", "transformation_uuid", transformation_code=code,
            transformation_name=name, category=category, description=description, parameter_schema=parameters,
            customer_override_allowed=override, version="v1",
        )  # fmt: skip
        count("transformation_definition")
    for code, name, rule_type, description, severity, blocking in VALIDATION_RULES:
        ids["validation", code] = _insert(
            conn, "validation_rule_definition", "validation_rule_uuid", rule_code=code, rule_name=name,
            rule_type=rule_type, description=description, severity=severity, blocking=blocking, version="v1",
        )  # fmt: skip
        count("validation_rule_definition")
    for code, entity, lookup in REFERENCE_RULES:
        ids["reference", code] = _insert(
            conn, "reference_resolution_rule", "reference_rule_uuid", rule_code=code,
            target_entity_uuid=ids["entity", entity], lookup_fields=lookup, match_strategy="NORMALIZED",
            case_sensitive=False, ambiguity_policy="REVIEW", not_found_policy="PRESERVE_UNRESOLVED", version="v1",
        )  # fmt: skip
        count("reference_resolution_rule")
    for code, entity, rule_type, description, severity, blocking in DATA_QUALITY_RULES:
        _insert(conn, "data_quality_rule", "data_quality_rule_uuid", rule_code=code,
                canonical_entity_uuid=ids["entity", entity], rule_type=rule_type, description=description,
                severity=severity, blocking=blocking, version="v1")  # fmt: skip
        count("data_quality_rule")

    for family in FAMILIES:
        prefix = next(p for p in sorted(FAMILY_APP_PREFIX, key=len, reverse=True) if family.startswith(p + "_"))
        app_code = FAMILY_APP_PREFIX[prefix]
        object_name, entity = FAMILY_OBJECT[family[len(prefix) + 1 :]]
        family_uuid = ids["family", family] = _insert(
            conn, "master_mapping_family", "mapping_family_uuid", application_uuid=ids["app", app_code],
            source_object_uuid=ids["object", app_code, _code(object_name)], mapping_code=family,
            mapping_name=_label(family), default_canonical_entity_uuid=ids["entity", entity],
        )  # fmt: skip
        count("master_mapping_family")
        version = _insert(
            conn, "master_mapping_version", "mapping_version_uuid", mapping_family_uuid=family_uuid, version_code="M1",
            status="DRAFT", source_schema_version="v1", change_summary="Initial controlled mapping (seed v1).",
        )  # fmt: skip
        count("master_mapping_version")
        items = RELEASED_MAPPINGS.get(family)
        if not items:
            continue
        content = []
        for sequence, (source, target, mapping_type, transform, reference, policy, required) in enumerate(items, 1):
            _insert(
                conn, "master_mapping_item", "mapping_item_uuid", mapping_version_uuid=version,
                source_field_uuid=ids["sfield", app_code, _code(object_name), source],
                canonical_entity_uuid=ids["entity", entity], canonical_field_uuid=ids["cfield", entity, target],
                sequence_no=sequence, mapping_type=mapping_type, transformation_uuid=ids["transform", transform],
                validation_rule_uuid=ids["validation", "REQUIRED"] if required else None,
                reference_rule_uuid=ids["reference", reference] if reference else None,
                null_handling_policy="REJECT" if required else "ALLOW_NULL",
                source_authority_uuid=ids["authority", "AUTHORITATIVE"], required_for_mapping=required,
                customer_override_allowed=policy == "CUSTOMER_OVERRIDE_ALLOWED", override_policy_uuid=ids["policy", policy],
            )  # fmt: skip
            count("master_mapping_item")
            content.append([sequence, source, target, mapping_type, transform, reference, policy, required])
        digest = hashlib.sha256(json.dumps(content, sort_keys=True).encode("utf-8")).hexdigest()
        conn.execute(
            text(
                "update md_master.master_mapping_version set status = 'RELEASED', released_at = now(), "
                "released_content_hash = :digest, validated_at = now(), approved_at = now(), "
                "effective_from = current_date where mapping_version_uuid = :version"
            ),
            {"digest": digest, "version": version},
        )

    for code, (name, domain, items) in VALUE_SETS.items():
        value_set = _insert(conn, "canonical_value_set", "value_set_uuid", value_set_code=code, value_set_name=name,
                            domain=domain, version="v1")  # fmt: skip
        count("canonical_value_set")
        for order, (value, label) in enumerate(items, 1):
            ids["cvalue", code, value] = _insert(conn, "canonical_value_item", "value_item_uuid",
                                                 value_set_uuid=value_set, value_code=value, display_label=label,
                                                 display_order=order)  # fmt: skip
            count("canonical_value_item")
    source_set = _insert(
        conn, "source_value_set", "source_value_set_uuid", application_uuid=ids["app", "TRACKWISE"],
        source_object_uuid=ids["object", "TRACKWISE", "COMPLAINT"],
        source_field_uuid=ids["sfield", "TRACKWISE", "COMPLAINT", "severity"], schema_version="v1",
    )  # fmt: skip
    count("source_value_set")
    for value, label, canonical in TRACKWISE_SEVERITY:
        item = _insert(conn, "source_value_item", "source_value_item_uuid", source_value_set_uuid=source_set,
                       source_value=value, source_label=label)  # fmt: skip
        count("source_value_item")
        _insert(conn, "value_mapping_definition", "value_mapping_uuid", application_uuid=ids["app", "TRACKWISE"],
                source_value_item_uuid=item, canonical_value_item_uuid=ids["cvalue", "COMPLAINT_SEVERITY", canonical],
                mapping_version="v1", customer_override_allowed=True)  # fmt: skip
        count("value_mapping_definition")

    for code, name, secrets in AUTH_TYPES:
        ids["auth", code] = _insert(conn, "authentication_type_definition", "authentication_type_uuid", auth_code=code,
                                    display_name=name, secret_fields_schema=secrets)  # fmt: skip
        count("authentication_type_definition")
    for code, name in PAGINATION_TYPES:
        ids["page", code] = _insert(conn, "pagination_type_definition", "pagination_type_uuid",
                                    pagination_code=code, display_name=name)  # fmt: skip
        count("pagination_type_definition")
    for code, name in SYNC_MODES:
        ids["sync", code] = _insert(conn, "sync_mode_definition", "sync_mode_uuid", sync_code=code, display_name=name)
        count("sync_mode_definition")
    for app_code in CONNECTOR_APPS:
        simulator = next(a for a in APPLICATIONS if a[0] == app_code)[4] == "SUPPORTED"
        auth = "API_KEY" if simulator else "OAUTH2_CLIENT_CREDENTIALS"
        connector = _insert(
            conn, "connector_definition", "connector_uuid", application_uuid=ids["app", app_code],
            connector_code=f"{app_code}_REST", connector_name=f"{next(a for a in APPLICATIONS if a[0] == app_code)[1]} REST Connector",
            connector_type="REST", default_authentication_type_uuid=ids["auth", auth], supports_schema_discovery=True,
            supports_incremental_sync=True, supports_webhook=False,
        )  # fmt: skip
        count("connector_definition")
        _insert(conn, "connector_version_definition", "connector_version_uuid", connector_uuid=connector,
                version_code="v1.0", api_version="v1", schema_version="v1", authentication_type_uuid=ids["auth", auth],
                pagination_type_uuid=ids["page", "CURSOR"], default_sync_mode_uuid=ids["sync", "INCREMENTAL"])  # fmt: skip
        count("connector_version_definition")
    return counts
