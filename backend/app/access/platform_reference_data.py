"""Read-only view of the platform's master reference data (md_master), for the platform administrator.

Value sets, countries, regions, time zones, units, jurisdictions, data-quality rules and reference resolution
rules are seeded master data used by mappings and validation. They are shown here, not edited: changing master
reference data is a controlled release, not a screen action.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.access.authz import _require_platform_admin
from backend.app.db.models.master import (
    CanonicalEntityDefinition,
    CanonicalValueItem,
    CanonicalValueSet,
    CountryReference,
    DataQualityRule,
    JurisdictionReference,
    ReferenceResolutionRule,
    RegionReference,
    TimezoneReference,
    UnitOfMeasure,
)
from backend.app.db.session import get_db

router = APIRouter(prefix="/api/v1", tags=["Platform reference data"])

ACTIVE = "ACTIVE"


@router.get("/platform-admin/reference-data")
def reference_data(request: Request, db: Session = Depends(get_db)):
    """Every kind of master reference data with its active entries (value sets as a summary)."""
    _require_platform_admin(request, db)
    item_counts = dict(
        db.query(CanonicalValueItem.value_set_uuid, func.count(CanonicalValueItem.value_item_uuid))
        .filter(CanonicalValueItem.status == ACTIVE)
        .group_by(CanonicalValueItem.value_set_uuid)
        .all()
    )
    value_sets = [
        {
            "code": row.value_set_code,
            "name": row.value_set_name,
            "domain": row.domain,
            "version": row.version,
            "values": item_counts.get(row.value_set_uuid, 0),
        }
        for row in db.query(CanonicalValueSet)
        .filter(CanonicalValueSet.status == ACTIVE)
        .order_by(CanonicalValueSet.domain, CanonicalValueSet.value_set_name)
    ]
    region_counts = dict(
        db.query(RegionReference.country_uuid, func.count(RegionReference.region_uuid))
        .filter(RegionReference.status == ACTIVE)
        .group_by(RegionReference.country_uuid)
        .all()
    )
    countries = [
        {
            "code": row.iso_alpha2,
            "code3": row.iso_alpha3,
            "name": row.country_name,
            "region_group": row.region_group,
            "regions": region_counts.get(row.country_uuid, 0),
        }
        for row in db.query(CountryReference)
        .filter(CountryReference.status == ACTIVE)
        .order_by(CountryReference.country_name)
    ]
    units = [
        {"code": row.uom_code, "name": row.uom_name, "dimension": row.dimension}
        for row in db.query(UnitOfMeasure)
        .filter(UnitOfMeasure.status == ACTIVE)
        .order_by(UnitOfMeasure.dimension, UnitOfMeasure.uom_code)
    ]
    timezones = [
        {"code": row.iana_name, "name": row.display_name}
        for row in db.query(TimezoneReference)
        .filter(TimezoneReference.status == ACTIVE)
        .order_by(TimezoneReference.iana_name)
    ]
    jurisdictions = [
        {"code": row.jurisdiction_code, "name": row.jurisdiction_name, "type": row.jurisdiction_type}
        for row in db.query(JurisdictionReference)
        .filter(JurisdictionReference.status == ACTIVE)
        .order_by(JurisdictionReference.jurisdiction_name)
    ]
    entities = dict(db.query(CanonicalEntityDefinition.canonical_entity_uuid, CanonicalEntityDefinition.entity_name))
    quality_rules = [
        {
            "code": row.rule_code,
            "entity": entities.get(row.canonical_entity_uuid),
            "type": row.rule_type,
            "description": row.description,
            "severity": row.severity,
            "blocking": bool(row.blocking),
            "version": row.version,
        }
        for row in db.query(DataQualityRule)
        .filter(DataQualityRule.status == ACTIVE)
        .order_by(DataQualityRule.rule_code)
    ]
    resolution_rules = [
        {
            "code": row.rule_code,
            "entity": entities.get(row.target_entity_uuid),
            "lookup_fields": row.lookup_fields,
            "match": row.match_strategy,
            "if_ambiguous": row.ambiguity_policy,
            "if_not_found": row.not_found_policy,
            "version": row.version,
        }
        for row in db.query(ReferenceResolutionRule)
        .filter(ReferenceResolutionRule.status == ACTIVE)
        .order_by(ReferenceResolutionRule.rule_code)
    ]
    return {
        "value_sets": value_sets,
        "countries": countries,
        "units": units,
        "timezones": timezones,
        "jurisdictions": jurisdictions,
        "data_quality_rules": quality_rules,
        "reference_resolution_rules": resolution_rules,
    }


@router.get("/platform-admin/reference-data/value-sets/{code}")
def value_set_items(code: str, request: Request, db: Session = Depends(get_db)):
    """The values of one value set (its newest active version), in display order."""
    _require_platform_admin(request, db)
    value_set = (
        db.query(CanonicalValueSet)
        .filter(
            func.upper(CanonicalValueSet.value_set_code) == code.strip().upper(), CanonicalValueSet.status == ACTIVE
        )
        .order_by(CanonicalValueSet.version.desc())
        .first()
    )
    if value_set is None:
        raise HTTPException(404, detail={"code": "VALUE_SET_NOT_FOUND", "message": "Value set is not available"})
    items = (
        db.query(CanonicalValueItem)
        .filter(CanonicalValueItem.value_set_uuid == value_set.value_set_uuid, CanonicalValueItem.status == ACTIVE)
        .order_by(CanonicalValueItem.display_order.nulls_last(), CanonicalValueItem.value_code)
        .all()
    )
    return {
        "code": value_set.value_set_code,
        "name": value_set.value_set_name,
        "domain": value_set.domain,
        "version": value_set.version,
        "items": [
            {
                "code": row.value_code,
                "label": row.display_label,
                "description": row.description,
                "effective_from": row.effective_from.isoformat() if row.effective_from else None,
                "effective_to": row.effective_to.isoformat() if row.effective_to else None,
            }
            for row in items
        ],
    }
