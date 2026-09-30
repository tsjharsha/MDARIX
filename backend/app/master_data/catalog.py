"""Mapping catalog read model backed by Master Data (md_master).

Replaces the application/object/field/canonical catalog that used to be
hard-coded in backend/app/mapping_catalog_router.py. Identifiers exposed to the
Mapping Studio keep their established shape (application code, and
"<APPLICATION>:<OBJECT>" for source objects) and also carry the immutable
Master Data business ID.
"""

from __future__ import annotations

from sqlalchemy.orm import Session, aliased

from backend.app.db.models.master import (
    ApplicationCategory,
    CanonicalEntityDefinition,
    CanonicalFieldDefinition,
    ConnectorDefinition,
    ConnectorVersionDefinition,
    DataClassification,
    ExternalApplication,
    FieldGroupDefinition,
    MappingOverridePolicy,
    MasterMappingFamily,
    MasterMappingItem,
    MasterMappingVersion,
    ReferenceResolutionRule,
    SourceAuthorityType,
    SourceFieldDefinition,
    SourceObjectDefinition,
    SourceValueItem,
    SourceValueSet,
    TransformationDefinition,
    ValidationRuleDefinition,
    ValueMappingDefinition,
    CanonicalValueItem,
)

ACTIVE = "ACTIVE"


def source_object_key(application_code: str, object_code: str) -> str:
    return f"{application_code}:{object_code}"


def _split_object_key(source_object_id: str) -> tuple[str, str]:
    application, _, obj = source_object_id.partition(":")
    return application.upper(), obj.upper()


def applications(db: Session) -> list[dict]:
    rows = (
        db.query(ExternalApplication, ApplicationCategory)
        .join(ApplicationCategory, ApplicationCategory.category_uuid == ExternalApplication.category_uuid)
        .filter(ExternalApplication.status == ACTIVE)
        .order_by(ExternalApplication.application_id)
        .all()
    )
    connector_types = {
        application_uuid: connector_type
        for application_uuid, connector_type in db.query(
            ConnectorDefinition.application_uuid, ConnectorDefinition.connector_type
        ).filter(ConnectorDefinition.status == ACTIVE)
    }
    return [
        {
            "application_id": app.application_code,
            "business_id": app.application_id,
            "application_code": app.application_code,
            "display_name": app.application_name,
            "category": category.category_code,
            "status": app.status,
            "description": app.description,
            "integration_support_status": app.integration_support_status,
            "default_connector_type": connector_types.get(app.application_uuid, "REST"),
            "supports_schema_discovery": app.supports_schema_discovery,
            "supports_sample_payload": True,
            "created_at": app.created_at,
            "updated_at": app.updated_at,
        }
        for app, category in rows
    ]


def _application(db: Session, application_code: str) -> ExternalApplication | None:
    return (
        db.query(ExternalApplication)
        .filter(ExternalApplication.application_code == application_code.upper(), ExternalApplication.status == ACTIVE)
        .first()
    )


def application_objects(db: Session, application_code: str) -> list[dict] | None:
    app = _application(db, application_code)
    if app is None:
        return None
    rows = (
        db.query(SourceObjectDefinition)
        .filter(
            SourceObjectDefinition.application_uuid == app.application_uuid, SourceObjectDefinition.status == ACTIVE
        )
        .order_by(SourceObjectDefinition.source_object_id)
        .all()
    )
    return [
        {
            "source_object_id": source_object_key(app.application_code, row.object_code),
            "business_id": row.source_object_id,
            "application_id": app.application_code,
            "object_name": row.object_name,
            "primary_key_field": row.primary_key_field,
            "status": row.status,
        }
        for row in rows
    ]


def _source_object(db: Session, source_object_id: str):
    application_code, object_code = _split_object_key(source_object_id)
    return (
        db.query(SourceObjectDefinition, ExternalApplication)
        .join(ExternalApplication, ExternalApplication.application_uuid == SourceObjectDefinition.application_uuid)
        .filter(
            ExternalApplication.application_code == application_code,
            SourceObjectDefinition.object_code == object_code,
            SourceObjectDefinition.status == ACTIVE,
        )
        .first()
    )


def source_fields(db: Session, source_object_id: str) -> list[dict] | None:
    found = _source_object(db, source_object_id)
    if found is None:
        return None
    obj, app = found
    key = source_object_key(app.application_code, obj.object_code)
    rows = (
        db.query(SourceFieldDefinition, FieldGroupDefinition, DataClassification)
        .outerjoin(
            FieldGroupDefinition, FieldGroupDefinition.field_group_uuid == SourceFieldDefinition.field_group_uuid
        )
        .outerjoin(
            DataClassification,
            DataClassification.classification_uuid == SourceFieldDefinition.data_classification_uuid,
        )
        .filter(
            SourceFieldDefinition.source_object_uuid == obj.source_object_uuid, SourceFieldDefinition.status == ACTIVE
        )
        .order_by(SourceFieldDefinition.source_field_id)
        .all()
    )
    enum_values: dict = {}
    for field_uuid, value in (
        db.query(SourceValueSet.source_field_uuid, SourceValueItem.source_value)
        .join(SourceValueItem, SourceValueItem.source_value_set_uuid == SourceValueSet.source_value_set_uuid)
        .filter(SourceValueSet.source_object_uuid == obj.source_object_uuid, SourceValueItem.status == ACTIVE)
        .order_by(SourceValueItem.source_value_item_id)
    ):
        enum_values.setdefault(field_uuid, []).append(value)
    return [
        {
            "source_field_id": f"{key}:{field.field_name}",
            "business_id": field.source_field_id,
            "application_id": app.application_code,
            "source_object_id": key,
            "field_name": field.field_name,
            "field_label": field.field_label,
            "field_group": group.group_code if group else "GENERAL",
            "data_type": field.data_type,
            "required": field.required,
            "nullable": field.nullable,
            "sample_value": field.sample_value,
            "enum_values": enum_values.get(field.source_field_uuid, []),
            "schema_version": field.introduced_schema_version,
            "status": field.status,
            "is_standard_field": True,
            "is_customer_field": False,
            "sensitivity_classification": classification.classification_code if classification else None,
        }
        for field, group, classification in rows
    ]


def canonical_entities(db: Session) -> list[dict]:
    rows = (
        db.query(CanonicalEntityDefinition)
        .filter(CanonicalEntityDefinition.status == ACTIVE)
        .order_by(CanonicalEntityDefinition.canonical_entity_id)
        .all()
    )
    return [
        {
            "entity_id": row.entity_code,
            "business_id": row.canonical_entity_id,
            "entity_name": row.entity_name,
            "status": row.status,
        }
        for row in rows
    ]


def canonical_fields(db: Session, entity_code: str) -> list[dict] | None:
    entity = (
        db.query(CanonicalEntityDefinition)
        .filter(
            CanonicalEntityDefinition.entity_code == entity_code.upper(), CanonicalEntityDefinition.status == ACTIVE
        )
        .first()
    )
    if entity is None:
        return None
    reference = aliased(CanonicalEntityDefinition)
    rows = (
        db.query(CanonicalFieldDefinition, MappingOverridePolicy, reference, DataClassification)
        .outerjoin(
            MappingOverridePolicy,
            MappingOverridePolicy.override_policy_uuid == CanonicalFieldDefinition.override_policy_uuid,
        )
        .outerjoin(reference, reference.canonical_entity_uuid == CanonicalFieldDefinition.reference_entity_uuid)
        .outerjoin(
            DataClassification,
            DataClassification.classification_uuid == CanonicalFieldDefinition.data_classification_uuid,
        )
        .filter(
            CanonicalFieldDefinition.canonical_entity_uuid == entity.canonical_entity_uuid,
            CanonicalFieldDefinition.status == ACTIVE,
        )
        .order_by(CanonicalFieldDefinition.canonical_field_id)
        .all()
    )
    return [
        {
            "canonical_field_id": f"{entity.entity_code}:{field.field_name}",
            "business_id": field.canonical_field_id,
            "entity_id": entity.entity_code,
            "field_name": field.field_name,
            "field_label": field.field_label,
            "data_type": field.data_type,
            "required": field.required,
            "nullable": field.nullable,
            "system_managed": field.system_managed,
            "mapping_allowed": field.mapping_allowed,
            "override_policy": policy.policy_code if policy else None,
            "validation_rule": None,
            "reference_entity": ref.entity_code if ref else None,
            "data_classification": classification.classification_code if classification else None,
            "status": field.status,
        }
        for field, policy, ref, classification in rows
    ]


def transformations(db: Session) -> list[dict]:
    rows = (
        db.query(TransformationDefinition)
        .filter(TransformationDefinition.status == ACTIVE)
        .order_by(TransformationDefinition.transformation_id)
    )
    return [
        {
            "code": row.transformation_code,
            "label": row.transformation_name,
            "business_id": row.transformation_id,
            "category": row.category,
            "version": row.version,
            "customer_override_allowed": row.customer_override_allowed,
        }
        for row in rows
    ]


def validation_rules(db: Session) -> list[dict]:
    rows = (
        db.query(ValidationRuleDefinition)
        .filter(ValidationRuleDefinition.status == ACTIVE)
        .order_by(ValidationRuleDefinition.validation_rule_id)
    )
    return [
        {
            "code": row.rule_code,
            "label": row.rule_name,
            "business_id": row.validation_rule_id,
            "rule_type": row.rule_type,
            "severity": row.severity,
            "blocking": row.blocking,
        }
        for row in rows
    ]


def override_policies(db: Session) -> list[dict]:
    rows = (
        db.query(MappingOverridePolicy)
        .filter(MappingOverridePolicy.status == ACTIVE)
        .order_by(MappingOverridePolicy.override_policy_id)
    )
    return [
        {
            "code": row.policy_code,
            "label": row.policy_name,
            "business_id": row.override_policy_id,
            "can_edit_source": row.can_edit_source,
            "can_edit_target": row.can_edit_target,
            "can_edit_transform": row.can_edit_transform,
            "can_edit_validation": row.can_edit_validation,
            "can_edit_enum_mapping": row.can_edit_enum_mapping,
            "requires_approval": row.requires_approval,
        }
        for row in rows
    ]


def source_authorities(db: Session) -> list[dict]:
    rows = (
        db.query(SourceAuthorityType)
        .filter(SourceAuthorityType.status == ACTIVE)
        .order_by(SourceAuthorityType.precedence, SourceAuthorityType.source_authority_id)
    )
    return [
        {
            "code": row.authority_code,
            "label": row.authority_name,
            "business_id": row.source_authority_id,
            "precedence": row.precedence,
        }
        for row in rows
    ]


def mapping_families(db: Session) -> list[dict]:
    entity = aliased(CanonicalEntityDefinition)
    rows = (
        db.query(MasterMappingFamily, ExternalApplication, SourceObjectDefinition, entity)
        .join(ExternalApplication, ExternalApplication.application_uuid == MasterMappingFamily.application_uuid)
        .join(
            SourceObjectDefinition, SourceObjectDefinition.source_object_uuid == MasterMappingFamily.source_object_uuid
        )
        .join(entity, entity.canonical_entity_uuid == MasterMappingFamily.default_canonical_entity_uuid)
        .filter(MasterMappingFamily.status == ACTIVE)
        .order_by(MasterMappingFamily.mapping_family_id)
        .all()
    )
    return [
        {
            "code": family.mapping_code,
            "business_id": family.mapping_family_id,
            "name": family.mapping_name,
            "application_id": app.application_code,
            "source_object_id": source_object_key(app.application_code, obj.object_code),
            "canonical_entity": target.entity_code,
            "status": family.status,
        }
        for family, app, obj, target in rows
    ]


def connector_versions(db: Session, application_code: str | None = None) -> list[dict]:
    query = (
        db.query(ConnectorVersionDefinition, ConnectorDefinition, ExternalApplication)
        .join(ConnectorDefinition, ConnectorDefinition.connector_uuid == ConnectorVersionDefinition.connector_uuid)
        .join(ExternalApplication, ExternalApplication.application_uuid == ConnectorDefinition.application_uuid)
        .filter(ConnectorVersionDefinition.status == ACTIVE)
    )
    if application_code:
        query = query.filter(ExternalApplication.application_code == application_code.upper())
    return [
        {
            "application_id": app.application_code,
            "connector_id": connector.connector_code,
            "business_id": version.connector_version_id,
            "connector_type": connector.connector_type,
            "version": version.version_code,
            "status": version.status,
            "supports_schema_discovery": connector.supports_schema_discovery,
            "supports_incremental_sync": connector.supports_incremental_sync,
        }
        for version, connector, app in query.order_by(ConnectorVersionDefinition.connector_version_id)
    ]


def released_mappings(db: Session, family_code: str | None = None) -> list[dict]:
    query = (
        db.query(
            MasterMappingVersion,
            MasterMappingFamily,
            ExternalApplication,
            SourceObjectDefinition,
            CanonicalEntityDefinition,
        )
        .join(MasterMappingFamily, MasterMappingFamily.mapping_family_uuid == MasterMappingVersion.mapping_family_uuid)
        .join(ExternalApplication, ExternalApplication.application_uuid == MasterMappingFamily.application_uuid)
        .join(
            SourceObjectDefinition, SourceObjectDefinition.source_object_uuid == MasterMappingFamily.source_object_uuid
        )
        .join(
            CanonicalEntityDefinition,
            CanonicalEntityDefinition.canonical_entity_uuid == MasterMappingFamily.default_canonical_entity_uuid,
        )
        .filter(MasterMappingVersion.status == "RELEASED")
    )
    if family_code:
        query = query.filter(MasterMappingFamily.mapping_code == family_code.upper())
    result = []
    for version, family, app, obj, entity in query.order_by(MasterMappingVersion.mapping_version_id):
        items = (
            db.query(
                MasterMappingItem,
                SourceFieldDefinition,
                CanonicalFieldDefinition,
                TransformationDefinition,
                ReferenceResolutionRule,
                MappingOverridePolicy,
            )
            .join(SourceFieldDefinition, SourceFieldDefinition.source_field_uuid == MasterMappingItem.source_field_uuid)
            .join(
                CanonicalFieldDefinition,
                CanonicalFieldDefinition.canonical_field_uuid == MasterMappingItem.canonical_field_uuid,
            )
            .outerjoin(
                TransformationDefinition,
                TransformationDefinition.transformation_uuid == MasterMappingItem.transformation_uuid,
            )
            .outerjoin(
                ReferenceResolutionRule,
                ReferenceResolutionRule.reference_rule_uuid == MasterMappingItem.reference_rule_uuid,
            )
            .join(
                MappingOverridePolicy,
                MappingOverridePolicy.override_policy_uuid == MasterMappingItem.override_policy_uuid,
            )
            .filter(MasterMappingItem.mapping_version_uuid == version.mapping_version_uuid)
            .order_by(MasterMappingItem.sequence_no)
            .all()
        )
        result.append(
            {
                "mapping_id": f"{family.mapping_code}_{version.version_code}",
                "business_id": version.mapping_version_id,
                "family": family.mapping_code,
                "source_object_id": source_object_key(app.application_code, obj.object_code),
                "canonical_entity": entity.entity_code,
                "version": version.version_code,
                "status": version.status,
                "released_at": version.released_at,
                "released_content_hash": version.released_content_hash,
                "rules": [
                    {
                        "business_id": item.mapping_item_id,
                        "source": source.field_name,
                        "target": target.field_name,
                        "mapping_type": item.mapping_type,
                        "transform": transform.transformation_code if transform else None,
                        "reference_rule": reference.rule_code if reference else None,
                        "override_policy": policy.policy_code,
                        "required": item.required_for_mapping,
                        "null_handling_policy": item.null_handling_policy,
                    }
                    for item, source, target, transform, reference, policy in items
                ],
            }
        )
    return result


def enum_value_map(db: Session, source_object_id: str, field_name: str) -> dict[str, str]:
    """Source enumeration value -> canonical value code for one source field."""
    found = _source_object(db, source_object_id)
    if found is None:
        return {}
    obj, _app = found
    rows = (
        db.query(SourceValueItem.source_value, CanonicalValueItem.value_code)
        .join(SourceValueSet, SourceValueSet.source_value_set_uuid == SourceValueItem.source_value_set_uuid)
        .join(SourceFieldDefinition, SourceFieldDefinition.source_field_uuid == SourceValueSet.source_field_uuid)
        .join(
            ValueMappingDefinition,
            ValueMappingDefinition.source_value_item_uuid == SourceValueItem.source_value_item_uuid,
        )
        .join(
            CanonicalValueItem, CanonicalValueItem.value_item_uuid == ValueMappingDefinition.canonical_value_item_uuid
        )
        .filter(
            SourceValueSet.source_object_uuid == obj.source_object_uuid,
            SourceFieldDefinition.field_name == field_name,
            ValueMappingDefinition.status == ACTIVE,
        )
    )
    return {source: canonical for source, canonical in rows}
