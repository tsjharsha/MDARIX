"""Turn connector records into the tenant's products, lots and complaints through a released mapping.

A connector names a mapping (configuration "mapping_code"). Only a RELEASED mapping of the same tenant is used
(released through the governed workflow: request approval, approval by a second administrator, release). Its rules
use the integration gateway format: {source_field: {"target_field": "<Entity>.<column>",
"transform": "trim|lower|upper|string|date|boolean|identity"}}, where <column> is a column of the import template
(see backend/app/trial/imports.py TEMPLATES). Mapped records go through the same checked import as CSV uploads, so a
batch with any problem writes nothing.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import MappingConfiguration
from backend.app.trial import imports
from integration.gateway import transform

# Canonical mapping targets and the import template that receives them.
TARGET_TEMPLATES = {"Product": "products", "ProductVersion": "products", "Lot": "lots", "LotBatch": "lots"}
TARGET_TEMPLATES["Complaint"] = "complaints"
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


def map_records(mapping: MappingConfiguration, records: list[dict]) -> tuple[str, list[dict]]:
    entity = TARGET_TEMPLATES[mapping.target_entity]
    rules = {key: rule for key, rule in (mapping.mapping_rules or {}).items() if not key.startswith("_")}
    mapped = []
    for record in records:
        row: dict = {}
        for source_field, rule in rules.items():
            if not isinstance(rule, dict) or "." not in str(rule.get("target_field", "")):
                raise MappingNotUsable(f"Rule for '{source_field}' has no '<Entity>.<column>' target")
            column = str(rule["target_field"]).split(".", 1)[1]
            value = transform(record.get(source_field), rule.get("transform") or "identity")
            if value is not None and column.endswith("_date"):
                value = str(value)[:10]  # templates take YYYY-MM-DD
            if value is not None:
                row[column] = value
        mapped.append(row)
    return entity, mapped


def import_connector_records(
    data: Session, tenant_id: uuid.UUID, connector_code: str, mapping: MappingConfiguration, records: list[dict]
) -> dict:
    """Map, check and import one batch. Returns a summary; never writes a partial batch. Does not commit."""
    entity, mapped = map_records(mapping, records)
    policy = imports.ImportPolicy(source=f"CONNECTOR:{connector_code}"[:120])
    report = imports.check_records(data, tenant_id, entity, mapped, policy)
    if not report["ready"]:
        return {"status": "BLOCKED", "entity": entity, "mapping": mapping.code, "report": report}
    try:
        result = imports.import_records(data, tenant_id, entity, mapped, policy)
    except HTTPException as exc:  # a race between check and write; nothing was written for this batch
        return {"status": "BLOCKED", "entity": entity, "mapping": mapping.code, "report": exc.detail}
    return {"status": "IMPORTED", "mapping": mapping.code, **result}
