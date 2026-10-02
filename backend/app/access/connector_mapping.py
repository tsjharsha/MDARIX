"""Turn connector records into the tenant's business records (products, lots, complaints, components, suppliers,
investigations, ...) through a released mapping.

A connector names a mapping (configuration "mapping_code"). Only a RELEASED mapping of the same tenant is used
(released through the governed workflow: request approval, approval by a second administrator, release). Its rules
use the integration gateway format: {source_field: {"target_field": "<Entity>.<column>",
"transform": "trim|lower|upper|string|date|boolean|identity"}}, where <column> is a column of the import template
(see backend/app/trial/imports.py TEMPLATES). Mapped records go through the same checked import as CSV uploads, so a
batch with any problem writes nothing.

A mapping can keep only some source records: its "_filter" setting {"field": "<source field>", "in": [values]} imports
the records whose field holds one of the values (compared without case) and counts the others as skipped. For example
a Teamcenter item list holds products and components; a products mapping keeps item_type "Product".

Its "_defaults" setting {column: value} fills an MDARIX field the source does not carry with a fixed value, for
example evidence_type "Test result" for a laboratory system's results. A mapped value always wins over a default.
"""

from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import MappingConfiguration
from backend.app.trial import imports
from integration.gateway import transform

# The records a mapping can fill, with the import template that receives them (shown in Mapping Studio).
IMPORTABLE_TARGETS = {
    "Complaint": "complaints",
    "Product": "products",
    "Lot": "lots",
    "Component": "components",
    "Supplier": "suppliers",
    "Site": "sites",
    "BomLine": "bom",
    "ComponentSupplier": "component_suppliers",
    "LotGenealogy": "lot_genealogy",
    "Change": "changes",
    "Requirement": "requirements",
    "Risk": "risks",
    "FailureMode": "failure_modes",
    "Control": "controls",
    "Investigation": "investigations",
    "Evidence": "evidence",
    "Capa": "capas",
}
# Also accepted as targets: the canonical names some mappings already use for the same templates.
TARGET_TEMPLATES = {
    **IMPORTABLE_TARGETS,
    "ProductVersion": "products",
    "LotBatch": "lots",
    "ManufacturingSite": "sites",
}
# Only a mapping that a second administrator approved and that was then released can write records.
USABLE_STATUSES = {"RELEASED"}


class MappingNotUsable(ValueError):
    pass


def released_mapping(db: Session, tenant_id, code: str) -> MappingConfiguration:
    mapping = (
        db.query(MappingConfiguration)
        .filter(
            MappingConfiguration.tenant_id == tenant_id,
            MappingConfiguration.code == code,
            MappingConfiguration.status.in_(sorted(USABLE_STATUSES)),
        )
        .order_by(MappingConfiguration.updated_at.desc())
        .first()
    )
    if mapping is None:
        raise MappingNotUsable(f"No released mapping named '{code}' for this tenant")
    if mapping.target_entity not in TARGET_TEMPLATES:
        raise MappingNotUsable(f"Mapping target '{mapping.target_entity}' cannot be imported yet")
    return mapping


class RecordsNotConvertible(ValueError):
    """Source values a rule could not convert (for example a date that is not a date). Nothing is imported."""

    def __init__(self, issues: list[dict]):
        super().__init__(f"{len(issues)} value(s) could not be converted")
        self.issues = issues


def record_filter(mapping_rules) -> dict | None:
    """The mapping's row filter {"field": ..., "in": [...]}, or None when it keeps every record."""
    settings = mapping_rules.get("_filter") if isinstance(mapping_rules, dict) else None
    if not isinstance(settings, dict) or not settings.get("field") or not isinstance(settings.get("in"), list):
        return None
    return {"field": str(settings["field"]), "in": [str(value) for value in settings["in"]]}


def record_defaults(mapping_rules) -> dict[str, str]:
    """The mapping's fixed values {column: value} for fields the source does not carry."""
    settings = mapping_rules.get("_defaults") if isinstance(mapping_rules, dict) else None
    if not isinstance(settings, dict):
        return {}
    return {str(column): str(value) for column, value in settings.items() if str(value).strip()}


def keep_record(selection: dict | None, record: dict) -> bool:
    if selection is None:
        return True
    value = str(record.get(selection["field"]) or "").strip().lower()
    return value in {item.strip().lower() for item in selection["in"]}


def map_records(mapping: MappingConfiguration, records: list[dict]) -> tuple[str, list[dict]]:
    entity = TARGET_TEMPLATES[mapping.target_entity]
    rules = {key: rule for key, rule in (mapping.mapping_rules or {}).items() if not key.startswith("_")}
    selection = record_filter(mapping.mapping_rules)
    defaults = record_defaults(mapping.mapping_rules)
    mapped = []
    issues: list[dict] = []
    for index, record in enumerate(records, start=1):
        if not keep_record(selection, record):
            continue
        row: dict = {}
        for source_field, rule in rules.items():
            if not isinstance(rule, dict) or "." not in str(rule.get("target_field", "")):
                raise MappingNotUsable(f"Rule for '{source_field}' has no '<Entity>.<column>' target")
            column = str(rule["target_field"]).split(".", 1)[1]
            conversion = rule.get("transform") or "identity"
            try:
                raw = record.get(source_field)
                # An empty cell is no value (CSV exports send ""), never a value to convert.
                value = None if isinstance(raw, str) and not raw.strip() else transform(raw, conversion)
            except (TypeError, ValueError):
                if len(issues) < 50:
                    issues.append(
                        {
                            "row": index,
                            "column": source_field,
                            "message": f"'{str(record.get(source_field))[:60]}' cannot be converted {TRANSFORMS.get(conversion, conversion).lower()}",
                        }
                    )
                continue
            if value is not None and column.endswith("_date"):
                value = str(value)[:10]  # templates take YYYY-MM-DD
            if value is not None:
                row[column] = value
        for column, value in defaults.items():
            row.setdefault(column, value)
        mapped.append(row)
    if issues:
        raise RecordsNotConvertible(issues)
    return entity, mapped


def import_connector_records(
    data: Session, tenant_id: uuid.UUID, connector_code: str, mapping: MappingConfiguration, records: list[dict]
) -> dict:
    """Map, check and import one batch. Returns a summary; never writes a partial batch. Does not commit."""
    try:
        entity, mapped = map_records(mapping, records)
    except RecordsNotConvertible as exc:
        report = {"ready": False, "rows": len(records), "error_count": len(exc.issues), "issues": exc.issues}
        return {
            "status": "BLOCKED",
            "entity": TARGET_TEMPLATES[mapping.target_entity],
            "mapping": mapping.code,
            "report": report,
        }
    skipped = len(records) - len(mapped)
    if records and not mapped:
        # Every record was left out by the mapping's filter: nothing to import, and nothing wrong.
        return {
            "status": "IMPORTED",
            "mapping": mapping.code,
            "entity": entity,
            "created": 0,
            "updated": 0,
            "rows": 0,
            "skipped": skipped,
        }
    policy = imports.ImportPolicy(source=f"CONNECTOR:{connector_code}"[:120])
    report = imports.check_records(data, tenant_id, entity, mapped, policy)
    if not report["ready"]:
        return {"status": "BLOCKED", "entity": entity, "mapping": mapping.code, "report": report}
    try:
        result = imports.import_records(data, tenant_id, entity, mapped, policy)
    except HTTPException as exc:  # a race between check and write; nothing was written for this batch
        return {"status": "BLOCKED", "entity": entity, "mapping": mapping.code, "report": exc.detail}
    return {"status": "IMPORTED", "mapping": mapping.code, **result, "skipped": skipped}


# Conversions the import applies to a value on its way in (integration.gateway.transform), in words.
TRANSFORMS = {
    "identity": "As is",
    "trim": "Remove spaces at the ends",
    "upper": "UPPER CASE",
    "lower": "lower case",
    "string": "As text",
    "date": "As a date",
    "boolean": "As yes / no",
}


_STANDARD_FILE = Path(__file__).with_name("standard_mappings.json")


@lru_cache(maxsize=1)
def _standard() -> tuple[dict, ...]:
    return tuple(json.loads(_STANDARD_FILE.read_text(encoding="utf-8")))


def standard_mappings(application: str | None = None, record: str | None = None) -> list[dict]:
    """The standard mappings (generated with the CSV templates by scripts/generate_source_templates.py), in the order
    their records should be loaded, optionally for one system and one record type."""
    return [
        dict(item)
        for item in _standard()
        if (not application or item["application"] == application.upper())
        and (not record or item["record"] == record.lower())
    ]


def mapping_targets() -> dict:
    """What a connector mapping can fill: each importable record with its columns, and the conversions."""
    return {
        "targets": [
            {
                "entity": entity,
                "label": imports.TEMPLATES[template]["title"],
                "required": list(imports.TEMPLATES[template]["required"]),
                "optional": list(imports.TEMPLATES[template]["optional"]),
            }
            for entity, template in IMPORTABLE_TARGETS.items()
        ],
        "transforms": [{"code": code, "label": label} for code, label in TRANSFORMS.items()],
    }


def field_rules(mapping_rules) -> dict:
    """The field rules of a stored mapping (settings such as "_configuration" are not rules)."""
    if not isinstance(mapping_rules, dict):
        return {}
    return {key: rule for key, rule in mapping_rules.items() if not str(key).startswith("_")}


def check_mapping(target_entity: str, mapping_rules) -> dict:
    """Whether a mapping can import records: a known record, known columns and conversions, required columns filled.

    Returns the problems in plain words, so the same answer is shown before saving, on demand and at release.
    """
    problems: list[str] = []
    template = TARGET_TEMPLATES.get(target_entity)
    rules = field_rules(mapping_rules)
    if template is None:
        problems.append(
            f"MDARIX cannot import '{target_entity}' records yet; choose one of: {', '.join(IMPORTABLE_TARGETS)}."
        )
        return {"status": "NEEDS_CHANGES", "problems": problems, "missing_required": [], "rule_count": len(rules)}
    spec = imports.TEMPLATES[template]
    columns = set(spec["required"]) | set(spec["optional"])
    filled: list[str] = []
    for source, rule in rules.items():
        target = str(rule.get("target_field", "")) if isinstance(rule, dict) else ""
        if "." not in target:
            problems.append(f"'{source}' has no MDARIX field.")
            continue
        column = target.split(".", 1)[1]
        if column not in columns:
            problems.append(f"'{column}' is not a field of {spec['title'].lower()}.")
        if (rule.get("transform") or "identity") not in TRANSFORMS:
            problems.append(f"'{rule.get('transform')}' is not a conversion MDARIX applies.")
        filled.append(column)
    for column in sorted({column for column in filled if filled.count(column) > 1}):
        problems.append(f"'{column}' is filled by more than one customer field.")
    defaults = record_defaults(mapping_rules)
    for column in defaults:
        if column not in columns:
            problems.append(f"'{column}' is not a field of {spec['title'].lower()}.")
    if not rules:
        problems.append("The mapping has no field rules.")
    missing = [column for column in spec["required"] if column not in filled and column not in defaults]
    return {
        "status": "READY" if not problems and not missing else "NEEDS_CHANGES",
        "problems": problems,
        "missing_required": missing,
        "rule_count": len(rules),
    }
