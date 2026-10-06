"""Controlled metadata contracts for the Mapping Studio.

The catalog is deliberately server-owned: the frontend consumes these
responses and does not carry a second hard-coded field model.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import AuditEvent, AuthUser, MappingImpactHistory
from backend.app.db.session import get_db
from backend.app.master_data import catalog
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.role_codes import is_customer_admin_role, is_platform_admin_role

router = APIRouter(prefix="/api/v1/admin/mapping", tags=["Mapping Studio Catalog"])


class DriftRequest(BaseModel):
    source_object_id: str = Field(min_length=3)
    source_fields: list[str] = []


class DryRunRequest(BaseModel):
    source_object_id: str = Field(min_length=3)
    rules: list[dict] = []
    records: list[dict] = []


class ValidationRequest(BaseModel):
    entity_id: str = Field(min_length=1)
    rules: list[dict] = []


class ValidationDecisionRequest(BaseModel):
    entity_id: str = Field(min_length=1, max_length=120)
    decision: str = Field(pattern="^(REVIEW|ACCEPT_WITH_REMEDIATION|REJECT|APPROVE_FOR_RELEASE)$")
    remediation_plan: str = Field(default="", max_length=2000)
    validation_result: dict = {}


class DiscoveryRequest(BaseModel):
    source_object_id: str = Field(min_length=3)
    fields: list[dict] = []
    baseline_fields: list[dict] = []


class CompareRequest(BaseModel):
    master_mapping_id: uuid.UUID
    from_version: str = Field(min_length=1)
    to_version: str = Field(min_length=1)
    from_rules: list[dict] = []
    to_rules: list[dict] = []


class SuggestionRequest(BaseModel):
    source_fields: list[dict] = []
    canonical_fields: list[dict] = []


class SuggestionDecision(BaseModel):
    suggestion_id: str = Field(min_length=1)
    decision: str = Field(pattern="^(ACCEPT|MODIFY|REJECT)$")
    reason: str | None = None


def _platform_admin(db: Session, ctx: AuthenticatedRequestContext):
    user = (
        db.query(AuthUser)
        .filter(AuthUser.id == ctx.user_id, AuthUser.tenant_id == ctx.tenant_id, AuthUser.status == "ACTIVE")
        .first()
    )
    if user is None or not is_platform_admin_role(user.role):
        raise HTTPException(
            403, detail={"code": "PLATFORM_ADMIN_REQUIRED", "message": "Platform administrator access is required"}
        )


def _guard(db, ctx):
    _platform_admin(db, ctx)


def _catalog_reader(db: Session, ctx: AuthenticatedRequestContext):
    """Platform administrators, and Customer Administrators reading the source-system catalog to map their data.

    The catalog (systems, their records and fields) is product metadata, not tenant data; every write and every
    check stays platform-only.
    """
    user = (
        db.query(AuthUser)
        .filter(AuthUser.id == ctx.user_id, AuthUser.tenant_id == ctx.tenant_id, AuthUser.status == "ACTIVE")
        .first()
    )
    if user is not None and is_customer_admin_role(user.role):
        return
    _platform_admin(db, ctx)


def _not_found(code: str, message: str) -> HTTPException:
    return HTTPException(404, detail={"code": code, "message": message})


@router.get("/applications")
def applications(db: Session = Depends(get_db), ctx: AuthenticatedRequestContext = Depends(get_request_context)):
    _catalog_reader(db, ctx)
    return catalog.applications(db)


@router.get("/applications/{application_id}/objects")
def application_objects(
    application_id: str, db: Session = Depends(get_db), ctx: AuthenticatedRequestContext = Depends(get_request_context)
):
    _catalog_reader(db, ctx)
    objects = catalog.application_objects(db, application_id)
    if objects is None:
        raise _not_found("APPLICATION_NOT_FOUND", "External application is not available")
    return objects


@router.get("/objects/{source_object_id}/fields")
def source_fields(
    source_object_id: str,
    db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    _catalog_reader(db, ctx)
    fields = catalog.source_fields(db, source_object_id)
    if fields is None:
        raise _not_found("SOURCE_OBJECT_NOT_FOUND", "Source object is not available for this application")
    return fields


@router.get("/canonical/entities")
def canonical_entities(db: Session = Depends(get_db), ctx: AuthenticatedRequestContext = Depends(get_request_context)):
    _guard(db, ctx)
    return catalog.canonical_entities(db)


@router.get("/canonical/entities/{entity_id}/fields")
def canonical_fields(
    entity_id: str, db: Session = Depends(get_db), ctx: AuthenticatedRequestContext = Depends(get_request_context)
):
    _guard(db, ctx)
    fields = catalog.canonical_fields(db, entity_id)
    if fields is None:
        raise _not_found("CANONICAL_ENTITY_NOT_FOUND", "Canonical entity is not available")
    return fields


@router.get("/transforms")
def transforms(db: Session = Depends(get_db), ctx: AuthenticatedRequestContext = Depends(get_request_context)):
    _guard(db, ctx)
    return catalog.transformations(db)


@router.get("/validation-rules")
def validation_rules(db: Session = Depends(get_db), ctx: AuthenticatedRequestContext = Depends(get_request_context)):
    _guard(db, ctx)
    return catalog.validation_rules(db)


@router.get("/override-policies")
def override_policies(db: Session = Depends(get_db), ctx: AuthenticatedRequestContext = Depends(get_request_context)):
    _guard(db, ctx)
    return catalog.override_policies(db)


@router.get("/source-priorities")
def source_priorities(db: Session = Depends(get_db), ctx: AuthenticatedRequestContext = Depends(get_request_context)):
    _guard(db, ctx)
    return catalog.source_authorities(db)


@router.get("/families")
def mapping_families(db: Session = Depends(get_db), ctx: AuthenticatedRequestContext = Depends(get_request_context)):
    _guard(db, ctx)
    return catalog.mapping_families(db)


@router.get("/connector-versions")
def connector_versions(
    application_id: str | None = None,
    db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    _guard(db, ctx)
    return catalog.connector_versions(db, application_id)


@router.get("/initial-mappings")
def initial_mappings(
    family: str | None = None,
    db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    _guard(db, ctx)
    return catalog.released_mappings(db, family)


@router.post("/schema-drift")
def schema_drift(
    payload: DriftRequest,
    db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    _guard(db, ctx)
    fields = catalog.source_fields(db, payload.source_object_id)
    if fields is None:
        raise _not_found("SOURCE_OBJECT_NOT_FOUND", "Source object is not available for this application")
    expected = [field["field_name"] for field in fields]
    unknown = sorted(set(payload.source_fields) - set(expected))
    return {
        "source_object_id": payload.source_object_id,
        "status": "DRIFT_DETECTED" if unknown else "NO_DRIFT",
        "expected_fields": expected,
        "unknown_fields": unknown,
    }


TRUE_TOKENS = {"true", "t", "yes", "y", "1"}
FALSE_TOKENS = {"false", "f", "no", "n", "0"}


def _apply_transform(transform: str, value, enum_map: dict[str, str]):
    """Apply one controlled Master Data transformation. Returns (value, issue_code or None, blocking)."""
    if value is None:
        return None, None, False
    if transform in {"DIRECT_COPY", ""}:
        return value, None, False
    if transform == "TRIM":
        return str(value).strip(), None, False
    if transform == "UPPERCASE":
        return str(value).upper(), None, False
    if transform == "LOWERCASE":
        return str(value).lower(), None, False
    if transform == "DATE_PARSE":
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date().isoformat(), None, False
        except ValueError:
            return value, "INVALID_DATE", True
    if transform == "BOOLEAN_MAP":
        token = str(value).strip().lower()
        if token in TRUE_TOKENS:
            return True, None, False
        if token in FALSE_TOKENS:
            return False, None, False
        return value, "UNMAPPED_BOOLEAN_VALUE", False
    if transform == "ENUM_MAP":
        # Unknown source values are never silently coerced (Master Data 12.7).
        if str(value) in enum_map:
            return enum_map[str(value)], None, False
        return value, "UNMAPPED_ENUM_VALUE", False
    if transform in {"LOOKUP", "UNIT_CONVERSION"}:
        return (
            value,
            "REFERENCE_UNRESOLVED_IN_DRY_RUN" if transform == "LOOKUP" else "UNIT_NOT_CONVERTED_IN_DRY_RUN",
            False,
        )
    return value, "UNKNOWN_TRANSFORM", True


@router.post("/dry-run")
def dry_run(
    payload: DryRunRequest,
    db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    _guard(db, ctx)
    families = [
        family
        for family in catalog.mapping_families(db)
        if family["source_object_id"] == payload.source_object_id.upper()
    ]
    target_fields = {}
    for family in families:
        for field in catalog.canonical_fields(db, family["canonical_entity"]) or []:
            target_fields[field["field_name"]] = field
    enum_maps: dict[str, dict[str, str]] = {}
    output = []
    for record in payload.records:
        target = {}
        warnings = []
        blocked = []
        for rule in payload.rules:
            source, dest = str(rule.get("source", "")), str(rule.get("target", ""))
            if not source or not dest:
                continue
            field = target_fields.get(dest)
            if field is not None and not field["mapping_allowed"]:
                blocked.append({"target": dest, "code": "PROTECTED_FIELD"})
                continue
            transform = str(rule.get("transform") or "DIRECT_COPY")
            if transform == "ENUM_MAP" and source not in enum_maps:
                enum_maps[source] = catalog.enum_value_map(db, payload.source_object_id, source)
            value, issue, blocking = _apply_transform(transform, record.get(source), enum_maps.get(source, {}))
            if issue and blocking:
                blocked.append({"target": dest, "code": issue})
                continue
            if issue:
                warnings.append({"target": dest, "code": issue})
            if value is None and rule.get("required"):
                warnings.append({"target": dest, "code": "REQUIRED_VALUE_MISSING"})
            target[dest] = value
        outcome = "BLOCKED" if blocked else "PASS WITH LIMITATIONS" if warnings else "PASS"
        output.append(
            {"source": record, "target": target, "warnings": warnings, "blocked": blocked, "outcome": outcome}
        )
    blocked_count = sum(1 for row in output if row["outcome"] == "BLOCKED")
    warning_count = sum(1 for row in output if row["outcome"] == "PASS WITH LIMITATIONS")
    return {
        "status": "READY",
        "outcome": "BLOCKED" if blocked_count else "PASS WITH LIMITATIONS" if warning_count else "PASS",
        "source_object_id": payload.source_object_id,
        "record_count": len(output),
        "passed": len(output) - blocked_count - warning_count,
        "warnings": warning_count,
        "blocked": blocked_count,
        "records": output,
        "persisted": False,
    }


REFERENCE_TYPES = {"UUID_REF", "UUID"}


@router.post("/validate")
def validate_mapping(
    payload: ValidationRequest,
    db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    _guard(db, ctx)
    canonical = catalog.canonical_fields(db, payload.entity_id)
    if canonical is None:
        raise _not_found("CANONICAL_ENTITY_NOT_FOUND", "Canonical entity is not available")
    fields = {field["field_name"]: field for field in canonical}
    allowed_transforms = {item["code"] for item in catalog.transformations(db)}
    allowed_policies = {item["code"] for item in catalog.override_policies(db)}
    entity_code = payload.entity_id.upper()
    targets = [str(rule.get("target", "")) for rule in payload.rules]
    errors = []
    for target in sorted({t for t in targets if targets.count(t) > 1}):
        errors.append({"code": "DUPLICATE_TARGET", "target": target})
    for rule in payload.rules:
        target = str(rule.get("target", ""))
        transform = str(rule.get("transform") or "DIRECT_COPY")
        field = fields.get(target)
        if field is None:
            errors.append({"code": "UNKNOWN_TARGET", "target": target})
        elif not field["mapping_allowed"]:
            errors.append({"code": "PROTECTED_FIELD", "target": target})
        if transform not in allowed_transforms:
            errors.append({"code": "INVALID_TRANSFORM", "transform": transform})
        if field is not None and field["data_type"] == "UUID_REF" and transform != "LOOKUP":
            errors.append({"code": "REFERENCE_REQUIRES_LOOKUP", "target": target})
        if transform == "LOOKUP" and field is not None and field["data_type"] not in REFERENCE_TYPES:
            errors.append({"code": "INVALID_REFERENCE", "target": target})
        reference = rule.get("reference_entity")
        if reference and str(reference).upper() == entity_code:
            errors.append({"code": "CIRCULAR_REFERENCE", "target": target})
        if rule.get("enum_values") is not None and not isinstance(rule.get("enum_values"), list):
            errors.append({"code": "INVALID_ENUM_CONFIG", "target": target})
        if (
            rule.get("source_type")
            and rule.get("target_type")
            and str(rule["source_type"]).upper() != str(rule["target_type"]).upper()
            and transform == "DIRECT_COPY"
        ):
            errors.append({"code": "TYPE_INCOMPATIBLE", "target": target})
        if rule.get("override_policy") is not None and rule.get("override_policy") not in allowed_policies:
            errors.append({"code": "INVALID_OVERRIDE_POLICY", "target": target})
    missing = [
        name for name, field in fields.items() if field["required"] and field["mapping_allowed"] and name not in targets
    ]
    return {
        "status": "PASS" if not errors and not missing else "BLOCKED",
        "errors": errors,
        "missing_required": missing,
        "checked_rules": len(payload.rules),
        "schema_compatible": not any(e["code"] in {"TYPE_INCOMPATIBLE", "UNKNOWN_TARGET"} for e in errors),
        "release_blocked": bool(errors or missing),
    }


@router.post("/validation-decisions")
def save_validation_decision(
    payload: ValidationDecisionRequest,
    db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    _guard(db, ctx)
    if payload.decision == "APPROVE_FOR_RELEASE" and (
        payload.validation_result.get("release_blocked")
        or payload.validation_result.get("errors")
        or payload.validation_result.get("missing_required")
    ):
        raise HTTPException(
            409, detail={"code": "VALIDATION_BLOCKED", "message": "A blocked validation cannot be approved for release"}
        )
    now = datetime.now(timezone.utc)
    event = AuditEvent(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        actor_ref=ctx.user_id,
        action="MAPPING_VALIDATION_DECISION_RECORDED",
        entity_type="CanonicalValidation",
        entity_id=uuid.uuid4(),
        details={
            "entity_id": payload.entity_id,
            "decision": payload.decision,
            "remediation_plan": payload.remediation_plan,
            "validation_result": payload.validation_result,
        },
        created_at=now,
    )
    db.add(event)
    db.commit()
    return {
        "id": str(event.id),
        "tenant_id": str(ctx.tenant_id),
        "entity_id": payload.entity_id,
        "decision": payload.decision,
        "remediation_plan": payload.remediation_plan,
        "created_at": now.isoformat(),
    }


@router.get("/validation-decisions")
def list_validation_decisions(
    entity_id: str | None = None,
    db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    _guard(db, ctx)
    query = (
        db.query(AuditEvent)
        .filter(AuditEvent.tenant_id == ctx.tenant_id, AuditEvent.action == "MAPPING_VALIDATION_DECISION_RECORDED")
        .order_by(AuditEvent.created_at.desc())
        .limit(50)
    )
    rows = query.all()
    result = []
    for row in rows:
        details = row.details or {}
        if entity_id and details.get("entity_id") != entity_id:
            continue
        result.append(
            {
                "id": str(row.id),
                "entity_id": details.get("entity_id"),
                "decision": details.get("decision"),
                "remediation_plan": details.get("remediation_plan", ""),
                "validation_result": details.get("validation_result", {}),
                "created_at": row.created_at,
            }
        )
    return result


@router.post("/schema-discovery")
def schema_discovery(
    payload: DiscoveryRequest,
    db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    _guard(db, ctx)
    before = {str(x.get("name")): x for x in payload.baseline_fields}
    after = {str(x.get("name")): x for x in payload.fields}
    changes = [{"type": "NEW_FIELD", "field": name, "risk": "LOW"} for name in sorted(set(after) - set(before))] + [
        {"type": "REMOVED_FIELD", "field": name, "risk": "HIGH"} for name in sorted(set(before) - set(after))
    ]
    for name in sorted(set(before) & set(after)):
        if before[name].get("data_type") != after[name].get("data_type"):
            changes.append(
                {
                    "type": "TYPE_CHANGED",
                    "field": name,
                    "from": before[name].get("data_type"),
                    "to": after[name].get("data_type"),
                    "risk": "CRITICAL",
                }
            )
        if before[name].get("required") != after[name].get("required") or before[name].get("nullable") != after[
            name
        ].get("nullable"):
            changes.append({"type": "REQUIRED_NULLABLE_CHANGED", "field": name, "risk": "HIGH"})
        if before[name].get("enum_values") != after[name].get("enum_values"):
            changes.append({"type": "ENUM_CHANGED", "field": name, "risk": "MEDIUM"})
    return {
        "source_object_id": payload.source_object_id,
        "schema_status": "DRIFT_DETECTED" if changes else "UNCHANGED",
        "changes": changes,
        "auto_applied": False,
    }


@router.post("/compare")
def compare_versions(
    payload: CompareRequest,
    db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    _guard(db, ctx)
    before = {f"{r.get('source')}->{r.get('target')}": r for r in payload.from_rules}
    after = {f"{r.get('source')}->{r.get('target')}": r for r in payload.to_rules}
    changes = []
    for key in sorted(set(after) - set(before)):
        changes.append({"change_type": "ADDED", "mapping": after[key], "risk": "LOW"})
    for key in sorted(set(before) - set(after)):
        changes.append({"change_type": "REMOVED", "mapping": before[key], "risk": "HIGH"})
    for key in sorted(set(before) & set(after)):
        if before[key] != after[key]:
            changes.append(
                {"change_type": "MODIFIED", "mapping": after[key], "old_mapping": before[key], "risk": "MEDIUM"}
            )
    impact = {"changes": changes, "affected_rules": len(changes), "tenant_overrides_preserved": True}
    row = MappingImpactHistory(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        master_mapping_id=payload.master_mapping_id,
        from_version=payload.from_version,
        to_version=payload.to_version,
        impact=impact,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    return {
        "id": str(row.id),
        "from_version": payload.from_version,
        "to_version": payload.to_version,
        "impact": impact,
        "persisted": True,
    }


@router.get("/impact-history")
def impact_history(
    master_mapping_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    _guard(db, ctx)
    query = db.query(MappingImpactHistory).filter(MappingImpactHistory.tenant_id == ctx.tenant_id)
    if master_mapping_id:
        query = query.filter(MappingImpactHistory.master_mapping_id == master_mapping_id)
    return [
        {
            "id": str(row.id),
            "master_mapping_id": str(row.master_mapping_id),
            "from_version": row.from_version,
            "to_version": row.to_version,
            "impact": row.impact,
            "created_at": row.created_at,
        }
        for row in query.order_by(MappingImpactHistory.created_at.desc()).all()
    ]


@router.post("/suggestions")
def suggestions(
    payload: SuggestionRequest,
    db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    _guard(db, ctx)
    canonical = {str(f.get("field_name")): f for f in payload.canonical_fields}
    result = []
    for field in payload.source_fields:
        source = str(field.get("field_name", ""))
        candidates = [
            name
            for name in canonical
            if name.lower() == source.lower() or name.lower().replace("_", "") == source.lower().replace("_", "")
        ]
        if candidates:
            result.append(
                {
                    "suggestion_id": str(uuid.uuid4()),
                    "source_field": source,
                    "suggested_target": candidates[0],
                    "transformation": "DIRECT",
                    "reason": "Name similarity",
                    "confidence": "MEDIUM",
                    "status": "AI_SUGGESTION_NOT_ACTIVE",
                }
            )
    return {"suggestions": result, "activation": "HUMAN_ACCEPTANCE_REQUIRED"}


@router.post("/suggestions/decision")
def suggestion_decision(
    payload: SuggestionDecision,
    db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    _guard(db, ctx)
    return {
        "suggestion_id": payload.suggestion_id,
        "decision": payload.decision,
        "reason": payload.reason,
        "status": "RECORDED",
        "active": False,
        "human_acceptance_required": True,
    }
