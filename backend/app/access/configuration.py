"""Tenant configuration: connectors, mappings, releases and the generic control-plane editor."""

import json
import uuid
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest
from backend.app.access.outbound import safe_urlopen

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from access_control.configuration_safety import safe_configuration
from access_control.personas import get_persona
from auth.durable import revoke_user_sessions
from backend.app.db.models.foundation import (
    ApprovalAuthority,
    AuditEvent,
    AuthUser,
    ConnectorConfiguration,
    MappingConfiguration,
    PermissionSetDefinition,
    PersonaAssignment,
    RoleDefinition,
    SegregationOfDutiesPolicy,
)
from backend.app.db.models.stage2 import (
    OutboxEvent,
)
from backend.app.db.session import get_db
from integration.gateway import ConnectionConfig, Connector, MappingDefinition, preview
from backend.app.access.schemas import (
    AdminUpdateRequest,
    ConnectorRequest,
    ConnectorRunRequest,
    MappingPreviewRequest,
    MappingRequest,
    ReleaseActionRequest,
    StatusRequest,
)
from backend.app.access.authz import _admin_tenant, _guard_user_administration, is_hidden_from
from backend.app.access.common import _audit_configuration, _connector_credential, _provider_get, _safe_provider_url
from backend.app.access.connector_mapping import MappingNotUsable, import_connector_records, released_mapping
from backend.app.db.data_plane import get_data_plane_db
from backend.app.request_context import get_request_context

router = APIRouter(prefix="/api/v1", tags=["Access Control"])


# Mapping states reachable only through the release workflow (request approval -> approve -> release).
GOVERNED_MAPPING_STATUSES = frozenset({"READY_FOR_APPROVAL", "APPROVED", "ACTIVE", "RELEASED"})


@router.post("/admin/configuration/connectors")
def create_connector(payload: ConnectorRequest, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    now = datetime.now(timezone.utc)
    try:
        configuration = safe_configuration(payload.configuration)
    except ValueError as exc:
        if str(exc).startswith("INVALID_SECRET_REFERENCE"):
            raise HTTPException(
                422,
                detail={
                    "code": "CONNECTOR_CREDENTIAL_REF_INVALID",
                    "message": "A credential reference must name a connector secret (MDARIX_CONNECTOR_SECRET_...)",
                },
            ) from exc
        raise HTTPException(
            422,
            detail={
                "code": "SENSITIVE_CONFIGURATION_REJECTED",
                "message": "Secrets must be stored in a managed secret provider, not configuration",
            },
        ) from exc
    row = ConnectorConfiguration(
        id=uuid.uuid4(),
        tenant_id=admin.tenant_id,
        code=payload.code,
        connector_type=payload.connector_type,
        configuration=configuration,
        version=payload.version,
        status="DRAFT",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    _audit_configuration(db, admin, "CONNECTOR_CONFIGURATION_CREATED", "ConnectorConfiguration", row.id, row.version)
    db.commit()
    return {
        "connector_id": str(row.id),
        "tenant_id": str(admin.tenant_id),
        "code": row.code,
        "version": row.version,
        "status": row.status,
    }


@router.post("/admin/configuration/mappings")
def create_mapping(payload: MappingRequest, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    now = datetime.now(timezone.utc)
    rules = dict(payload.mapping_rules)
    rules["_configuration"] = {
        "source_database": payload.source_database,
        "source_schema": payload.source_schema,
        "source_table": payload.source_table,
        "target_schema": payload.target_schema,
        "target_table": payload.target_table or payload.target_entity,
    }
    row = MappingConfiguration(
        id=uuid.uuid4(),
        tenant_id=admin.tenant_id,
        code=payload.code,
        source_system=payload.source_system,
        target_entity=payload.target_entity,
        mapping_rules=rules,
        version=payload.version,
        status="DRAFT",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    _audit_configuration(db, admin, "MAPPING_CONFIGURATION_CREATED", "MappingConfiguration", row.id, row.version)
    db.commit()
    return {
        "mapping_id": str(row.id),
        "tenant_id": str(admin.tenant_id),
        "code": row.code,
        "version": row.version,
        "status": row.status,
    }


@router.get("/admin/configuration/connectors")
def list_connectors(request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    rows = (
        db.query(ConnectorConfiguration)
        .filter(ConnectorConfiguration.tenant_id == admin.tenant_id)
        .order_by(ConnectorConfiguration.code, ConnectorConfiguration.version)
        .all()
    )
    return [
        {
            "id": str(row.id),
            "code": row.code,
            "connector_type": row.connector_type,
            "version": row.version,
            "status": row.status,
            "configuration": row.configuration,
        }
        for row in rows
    ]


@router.get("/admin/configuration/mappings")
def list_mappings(request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    rows = (
        db.query(MappingConfiguration)
        .filter(MappingConfiguration.tenant_id == admin.tenant_id)
        .order_by(MappingConfiguration.code, MappingConfiguration.version)
        .all()
    )
    return [
        {
            "id": str(row.id),
            "code": row.code,
            "source_system": row.source_system,
            "target_entity": row.target_entity,
            "version": row.version,
            "status": row.status,
            "mapping_rules": row.mapping_rules,
        }
        for row in rows
    ]


@router.get("/admin/configuration/data-mappings")
def list_data_mapping_fields(request: Request, db: Session = Depends(get_db)):
    """Return tenant-authorized external-to-internal field mapping configuration."""
    admin = _admin_tenant(request, db)
    rows = (
        db.query(MappingConfiguration)
        .filter(
            MappingConfiguration.tenant_id == admin.tenant_id,
        )
        .order_by(MappingConfiguration.code, MappingConfiguration.version)
        .all()
    )
    result: list[dict] = []
    for row in rows:
        rules = row.mapping_rules or {}
        configuration = rules.get("_configuration", {}) if isinstance(rules, dict) else {}
        configured_fields = rules.get("fields", rules) if isinstance(rules, dict) else {}
        if isinstance(configured_fields, list):
            field_entries = [(str(index), item) for index, item in enumerate(configured_fields)]
        elif isinstance(configured_fields, dict):
            field_entries = [(key, value) for key, value in configured_fields.items() if not str(key).startswith("_")]
        else:
            field_entries = []
        if not field_entries:
            field_entries = [("Not configured", {"target_field": "Not configured", "transform": "DIRECT"})]
        for source_key, rule in field_entries:
            normalized = rule if isinstance(rule, dict) else {"target": rule}
            source_field = normalized.get("source_field") or normalized.get("source") or source_key
            target_field = normalized.get("target_field") or normalized.get("target") or normalized.get("field")
            if isinstance(target_field, str) and "." in target_field:
                target_table, target_field = target_field.rsplit(".", 1)
            else:
                target_table = configuration.get("target_table") or row.target_entity
            result.append(
                {
                    "mapping_id": str(row.id),
                    "mapping_code": row.code,
                    "tenant_id": str(row.tenant_id),
                    "source_system": row.source_system,
                    "source_database": configuration.get("source_database") or row.source_system,
                    "source_schema": configuration.get("source_schema") or "customer",
                    "source_table": normalized.get("source_table")
                    or configuration.get("source_table")
                    or normalized.get("source_object")
                    or "Not configured",
                    "source_field": source_field,
                    "target_schema": configuration.get("target_schema") or "public",
                    "target_table": target_table,
                    "target_field": target_field or "Not configured",
                    "transform": normalized.get("transform") or normalized.get("type") or "DIRECT",
                    "required": bool(normalized.get("required", False)),
                    "version": row.version,
                    "status": row.status,
                }
            )
    return result


@router.patch("/admin/configuration/connectors/{configuration_id}/status")
def activate_connector(
    configuration_id: uuid.UUID, payload: StatusRequest, request: Request, db: Session = Depends(get_db)
):
    admin = _admin_tenant(request, db)
    row = (
        db.query(ConnectorConfiguration)
        .filter(ConnectorConfiguration.id == configuration_id, ConnectorConfiguration.tenant_id == admin.tenant_id)
        .first()
    )
    if row is None:
        raise HTTPException(
            404,
            detail={
                "code": "CONNECTOR_NOT_FOUND",
                "message": "Connector configuration is not available for this tenant",
            },
        )
    row.status = payload.status
    row.updated_at = datetime.now(timezone.utc)
    _audit_configuration(
        db, admin, "CONNECTOR_CONFIGURATION_STATUS_CHANGED", "ConnectorConfiguration", row.id, row.version
    )
    db.commit()
    return {"id": str(row.id), "status": row.status, "version": row.version}


@router.get("/admin/configuration/connectors/{code}/versions")
def connector_versions(code: str, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    rows = (
        db.query(ConnectorConfiguration)
        .filter(ConnectorConfiguration.tenant_id == admin.tenant_id, ConnectorConfiguration.code == code)
        .order_by(ConnectorConfiguration.version)
        .all()
    )
    return [
        {
            "id": str(row.id),
            "code": row.code,
            "connector_type": row.connector_type,
            "version": row.version,
            "status": row.status,
        }
        for row in rows
    ]


@router.get("/admin/configuration/mappings/{code}/versions")
def mapping_versions(code: str, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    rows = (
        db.query(MappingConfiguration)
        .filter(MappingConfiguration.tenant_id == admin.tenant_id, MappingConfiguration.code == code)
        .order_by(MappingConfiguration.version)
        .all()
    )
    return [
        {
            "id": str(row.id),
            "code": row.code,
            "source_system": row.source_system,
            "target_entity": row.target_entity,
            "version": row.version,
            "status": row.status,
        }
        for row in rows
    ]


@router.patch("/admin/control-plane/{resource}/{resource_id}")
def update_control_plane_resource(
    resource: str, resource_id: uuid.UUID, payload: AdminUpdateRequest, request: Request, db: Session = Depends(get_db)
):
    admin = _admin_tenant(request, db)
    resources = {
        "users": (AuthUser, {"display_name", "company", "email", "role", "status"}, "USER_UPDATED"),
        "roles": (RoleDefinition, {"code", "name", "version", "status"}, "ROLE_UPDATED"),
        "permission-sets": (
            PermissionSetDefinition,
            {"code", "version", "status", "object_permissions", "field_permissions", "action_permissions"},
            "PERMISSION_SET_UPDATED",
        ),
        "connectors": (
            ConnectorConfiguration,
            {"code", "connector_type", "version", "status", "configuration"},
            "CONNECTOR_UPDATED",
        ),
        "mappings": (
            MappingConfiguration,
            {"code", "source_system", "target_entity", "version", "status", "mapping_rules"},
            "MAPPING_UPDATED",
        ),
        "approval-authorities": (
            ApprovalAuthority,
            {"role_name", "object_type", "decision_type", "authority", "version", "status"},
            "APPROVAL_AUTHORITY_UPDATED",
        ),
        "sod-policies": (
            SegregationOfDutiesPolicy,
            {
                "name",
                "object_type",
                "decision_type",
                "version",
                "status",
                "creator_cannot_approve",
                "last_material_editor_cannot_approve",
            },
            "SOD_POLICY_UPDATED",
        ),
        "persona-assignments": (PersonaAssignment, {"persona_code", "status"}, "PERSONA_ASSIGNMENT_UPDATED"),
    }
    item = resources.get(resource)
    if item is None:
        raise HTTPException(
            404, detail={"code": "RESOURCE_NOT_SUPPORTED", "message": "Administrator resource is not supported"}
        )
    model, allowed_fields, action = item
    unknown = set(payload.values) - allowed_fields
    if unknown:
        raise HTTPException(422, detail={"code": "FIELD_NOT_ALLOWED", "message": "One or more fields cannot be edited"})
    row = db.query(model).filter(model.id == resource_id, model.tenant_id == admin.tenant_id).first()
    if row is not None and resource == "persona-assignments":
        # A platform account's assignments are not the customer's to see or change.
        owner = db.query(AuthUser).filter(AuthUser.id == row.user_id).first()
        if owner is not None and is_hidden_from(admin, owner):
            row = None
    if row is None:
        raise HTTPException(
            404, detail={"code": "RESOURCE_NOT_FOUND", "message": "Resource is not available for this tenant"}
        )
    if resource == "users":
        _guard_user_administration(
            admin,
            target=row,
            new_role=str(payload.values["role"]) if "role" in payload.values else None,
            changes_access=bool({"role", "status"} & set(payload.values)),
        )
    if resource == "users" and "email" in payload.values:
        new_email = str(payload.values["email"]).strip().lower()
        if (
            db.query(AuthUser)
            .filter(AuthUser.tenant_id == admin.tenant_id, AuthUser.username == new_email, AuthUser.id != row.id)
            .first()
        ):
            raise HTTPException(
                409, detail={"code": "ACCOUNT_EXISTS", "message": "That email already exists in this tenant"}
            )
        payload.values["email"] = new_email
    if resource == "connectors" and "configuration" in payload.values:
        try:
            payload.values["configuration"] = safe_configuration(payload.values["configuration"])
        except ValueError as exc:
            raise HTTPException(
                422,
                detail={
                    "code": "SENSITIVE_CONFIGURATION_REJECTED",
                    "message": "Secrets must use a managed secret provider",
                },
            ) from exc
    if resource == "persona-assignments" and "persona_code" in payload.values:
        try:
            payload.values["persona_code"] = get_persona(payload.values["persona_code"]).code
        except ValueError as exc:
            raise HTTPException(
                422, detail={"code": "UNKNOWN_PERSONA", "message": "Persona is not in the R1 catalog"}
            ) from exc
    for field, value in payload.values.items():
        setattr(row, "username" if resource == "users" and field == "email" else field, value)
    if resource == "users" and str(payload.values.get("status", "ACTIVE")).upper() != "ACTIVE":
        revoke_user_sessions(db, row.id, row.tenant_id)
    if hasattr(row, "updated_at"):
        row.updated_at = datetime.now(timezone.utc)
    version = getattr(row, "version", "v1")
    _audit_configuration(db, admin, action, model.__name__, row.id, version)
    db.commit()
    return {"id": str(row.id), "resource": resource, "status": getattr(row, "status", "ACTIVE"), "version": version}


@router.post("/admin/configuration/connectors/{configuration_id}/test")
def test_connector(configuration_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    row = (
        db.query(ConnectorConfiguration)
        .filter(ConnectorConfiguration.id == configuration_id, ConnectorConfiguration.tenant_id == admin.tenant_id)
        .first()
    )
    if row is None:
        raise HTTPException(
            404, detail={"code": "CONNECTOR_NOT_FOUND", "message": "Connector is not available for this tenant"}
        )
    result = Connector(
        ConnectionConfig(str(admin.tenant_id), str(row.id), row.code, row.connector_type, "CONFIGURED")
    ).test_connection()
    _audit_configuration(db, admin, "CONNECTOR_TEST_EXECUTED", "ConnectorConfiguration", row.id, row.version)
    db.commit()
    return result


@router.post("/admin/configuration/connectors/{configuration_id}/provider-health")
def provider_health(configuration_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    row = (
        db.query(ConnectorConfiguration)
        .filter(ConnectorConfiguration.id == configuration_id, ConnectorConfiguration.tenant_id == admin.tenant_id)
        .first()
    )
    if row is None:
        raise HTTPException(
            404, detail={"code": "CONNECTOR_NOT_FOUND", "message": "Connector is not available for this tenant"}
        )
    result = _provider_get(row, "health_path")
    _audit_configuration(db, admin, "CONNECTOR_PROVIDER_HEALTH_CHECKED", "ConnectorConfiguration", row.id, row.version)
    db.commit()
    return {"connector_id": str(row.id), "code": row.code, **result}


@router.post("/admin/configuration/connectors/{configuration_id}/discover-schema")
def provider_schema(configuration_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    row = (
        db.query(ConnectorConfiguration)
        .filter(ConnectorConfiguration.id == configuration_id, ConnectorConfiguration.tenant_id == admin.tenant_id)
        .first()
    )
    if row is None:
        raise HTTPException(
            404, detail={"code": "CONNECTOR_NOT_FOUND", "message": "Connector is not available for this tenant"}
        )
    result = _provider_get(row, "schema_path")
    result["auto_applied"] = False
    result["schema_version"] = (row.configuration or {}).get("schema_version", row.version)
    _audit_configuration(db, admin, "CONNECTOR_SCHEMA_DISCOVERED", "ConnectorConfiguration", row.id, row.version)
    db.commit()
    return {"connector_id": str(row.id), "code": row.code, **result}


@router.post("/admin/configuration/connectors/{configuration_id}/execute")
def execute_connector(
    configuration_id: uuid.UUID,
    payload: ConnectorRunRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    admin = _admin_tenant(request, db)
    row = (
        db.query(ConnectorConfiguration)
        .filter(
            ConnectorConfiguration.id == configuration_id,
            ConnectorConfiguration.tenant_id == admin.tenant_id,
            ConnectorConfiguration.status == "ACTIVE",
        )
        .first()
    )
    if row is None:
        raise HTTPException(
            404,
            detail={
                "code": "ACTIVE_CONNECTOR_NOT_FOUND",
                "message": "Active connector is not available for this tenant",
            },
        )
    records = payload.records
    configuration = row.configuration or {}
    if not records and configuration.get("endpoint"):
        source_object = configuration.get("source_object", payload.source_system)
        timeout = float(configuration.get("timeout_seconds", 10))
        try:
            url = _safe_provider_url(
                configuration["endpoint"],
                configuration.get("records_path", f"records/{source_object}"),
                timeout=timeout,
            )
            token = _connector_credential(configuration)
        except ValueError as exc:
            raise HTTPException(
                422, detail={"code": str(exc), "message": "Connector endpoint configuration is not safe or valid"}
            ) from exc
        tenant_key = configuration.get("tenant_key")
        if tenant_key:
            url += ("&" if "?" in url else "?") + f"tenant={tenant_key}"
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
            headers["X-Provider-Token"] = token
        try:
            with safe_urlopen(UrlRequest(url, headers=headers, method="GET"), timeout=timeout) as response:
                raw = response.read(5_000_001)
                if len(raw) > 5_000_000:
                    raise HTTPException(
                        502,
                        detail={
                            "code": "PROVIDER_RESPONSE_TOO_LARGE",
                            "message": "Provider response exceeds the configured safety limit",
                        },
                    )
                body = json.loads(raw.decode())
            if tenant_key and body.get("tenant_key") != tenant_key:
                raise HTTPException(
                    502,
                    detail={
                        "code": "PROVIDER_TENANT_SCOPE_INVALID",
                        "message": "Provider returned an unexpected tenant scope",
                    },
                )
            records = body.get("records", [])
        except HTTPException:
            raise
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            raise HTTPException(
                502, detail={"code": "PROVIDER_READ_FAILED", "message": "Provider read failed"}
            ) from exc
    connector = Connector(
        ConnectionConfig(str(admin.tenant_id), str(row.id), row.code, row.connector_type, payload.source_system),
        records,
    )
    result = connector.read_records()
    # With a released mapping, the records also become the tenant's products, lots or complaints through the same
    # checked import as CSV uploads (all or nothing). The raw records are staged in the outbox either way.
    canonical_import = None
    mapping_code = (row.configuration or {}).get("mapping_code")
    if mapping_code and result:
        try:
            mapping = released_mapping(db, admin.tenant_id, str(mapping_code))
        except MappingNotUsable as exc:
            canonical_import = {"status": "BLOCKED", "reason": str(exc)}
        else:
            # The tenant's data plane is opened only when a mapping is configured.
            sessions = get_data_plane_db(get_request_context(request, db), db)
            data = next(sessions)
            try:
                canonical_import = import_connector_records(data, admin.tenant_id, row.code, mapping, result)
                if canonical_import.get("status") == "IMPORTED":
                    data.commit()
                else:
                    data.rollback()
            finally:
                sessions.close()
    for record in result:
        db.add(
            OutboxEvent(
                tenant_id=admin.tenant_id,
                event_name="PROVIDER_RECORD_RECEIVED",
                aggregate_type=f"{row.code}:{payload.source_system}",
                payload={"tenant_id": str(admin.tenant_id), "source_system": payload.source_system, "record": record},
                occurred_at=datetime.now(timezone.utc),
            )
        )
    _audit_configuration(db, admin, "CONNECTOR_EXECUTED", "ConnectorConfiguration", row.id, row.version)
    db.commit()
    return {
        "status": "COMPLETE",
        "tenant_id": str(admin.tenant_id),
        "connector_id": str(row.id),
        "records_read": len(result),
        "outbox_enqueued": len(result),
        "records": result,
        "canonical_import": canonical_import,
    }


@router.post("/admin/configuration/mappings/{configuration_id}/preview")
def preview_mapping(
    configuration_id: uuid.UUID, payload: MappingPreviewRequest, request: Request, db: Session = Depends(get_db)
):
    admin = _admin_tenant(request, db)
    row = (
        db.query(MappingConfiguration)
        .filter(
            MappingConfiguration.id == configuration_id,
            MappingConfiguration.tenant_id == admin.tenant_id,
            MappingConfiguration.status.notin_(["RETIRED", "SUPERSEDED"]),
        )
        .first()
    )
    if row is None:
        raise HTTPException(
            404,
            detail={"code": "ACTIVE_MAPPING_NOT_FOUND", "message": "Active mapping is not available for this tenant"},
        )
    result = preview(
        payload.records,
        MappingDefinition(payload.source_object, payload.target_entity, payload.mapping_version, payload.rules),
    )
    _audit_configuration(db, admin, "MAPPING_PREVIEW_EXECUTED", "MappingConfiguration", row.id, row.version)
    db.commit()
    return {"tenant_id": str(admin.tenant_id), "mapping_id": str(row.id), "preview": result}


@router.patch("/admin/configuration/mappings/{configuration_id}/status")
def activate_mapping(
    configuration_id: uuid.UUID, payload: StatusRequest, request: Request, db: Session = Depends(get_db)
):
    admin = _admin_tenant(request, db)
    row = (
        db.query(MappingConfiguration)
        .filter(MappingConfiguration.id == configuration_id, MappingConfiguration.tenant_id == admin.tenant_id)
        .first()
    )
    if row is None:
        raise HTTPException(
            404,
            detail={"code": "MAPPING_NOT_FOUND", "message": "Mapping configuration is not available for this tenant"},
        )
    if payload.status in GOVERNED_MAPPING_STATUSES:
        # Approval and release only through /release-action, where a second administrator approves.
        raise HTTPException(
            409,
            detail={
                "code": "MAPPING_STATUS_GOVERNED",
                "message": "Use the release workflow (request approval, approve, release) for this status.",
            },
        )
    row.status = payload.status
    row.updated_at = datetime.now(timezone.utc)
    _audit_configuration(db, admin, "MAPPING_CONFIGURATION_STATUS_CHANGED", "MappingConfiguration", row.id, row.version)
    db.commit()
    return {"id": str(row.id), "status": row.status, "version": row.version}


@router.get("/admin/configuration/mappings/{configuration_id}/release")
def mapping_release_detail(configuration_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    """Return the server-owned release, dependency, and audit evidence for a mapping."""
    admin = _admin_tenant(request, db)
    row = (
        db.query(MappingConfiguration)
        .filter(MappingConfiguration.id == configuration_id, MappingConfiguration.tenant_id == admin.tenant_id)
        .first()
    )
    if row is None:
        raise HTTPException(
            404,
            detail={"code": "MAPPING_NOT_FOUND", "message": "Mapping configuration is not available for this tenant"},
        )
    events = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.tenant_id == admin.tenant_id,
            AuditEvent.entity_type == "MappingConfiguration",
            AuditEvent.entity_id == row.id,
        )
        .order_by(AuditEvent.created_at.desc())
        .limit(25)
        .all()
    )
    rules = row.mapping_rules or {}
    dependencies = [value for value in (row.source_system, row.target_entity) if value]
    return {
        "id": str(row.id),
        "code": row.code,
        "version": row.version,
        "status": row.status,
        "dependencies": dependencies,
        "impact": {
            "source_system": row.source_system,
            "target_entity": row.target_entity,
            "tenant_id": str(row.tenant_id),
        },
        "validation": {
            "status": "PASS" if rules else "REVIEW_REQUIRED",
            "rule_count": len(rules.get("rules", rules)) if isinstance(rules, dict) else 0,
        },
        "audit": [
            {"action": item.action, "actor": item.actor_ref, "created_at": item.created_at, "details": item.details}
            for item in events
        ],
    }


@router.post("/admin/configuration/mappings/{configuration_id}/release-action")
def mapping_release_action(
    configuration_id: uuid.UUID, payload: ReleaseActionRequest, request: Request, db: Session = Depends(get_db)
):
    """Perform an audited, optimistic-lock protected configuration release transition."""
    admin = _admin_tenant(request, db)
    row = (
        db.query(MappingConfiguration)
        .filter(MappingConfiguration.id == configuration_id, MappingConfiguration.tenant_id == admin.tenant_id)
        .with_for_update()
        .first()
    )
    if row is None:
        raise HTTPException(
            404,
            detail={"code": "MAPPING_NOT_FOUND", "message": "Mapping configuration is not available for this tenant"},
        )
    current = str(row.status).upper()
    if payload.expected_status and current != payload.expected_status.upper():
        raise HTTPException(
            409,
            detail={
                "code": "RELEASE_VERSION_CONFLICT",
                "message": "The release changed; refresh before retrying.",
                "current_status": current,
            },
        )
    rules = row.mapping_rules or {}
    has_rules = bool(rules.get("rules", rules)) if isinstance(rules, dict) else bool(rules)
    transitions = {
        "REQUEST_APPROVAL": ("READY_FOR_APPROVAL", {"DRAFT", "VALIDATION", "READY_FOR_APPROVAL"}),
        "APPROVE": ("APPROVED", {"READY_FOR_APPROVAL"}),
        "PROMOTE": ("RELEASED", {"APPROVED"}),
        "ROLLBACK": ("SUPERSEDED", {"RELEASED", "ACTIVE"}),
    }
    target, allowed = transitions[payload.action]
    if current not in allowed:
        raise HTTPException(
            409,
            detail={
                "code": "RELEASE_TRANSITION_INVALID",
                "message": f"Cannot {payload.action.lower()} a {current} release.",
            },
        )
    if payload.action == "APPROVE":
        requester = (
            db.query(AuditEvent.actor_ref)
            .filter(
                AuditEvent.entity_type == "MappingConfiguration",
                AuditEvent.entity_id == row.id,
                AuditEvent.action == "MAPPING_RELEASE_REQUEST_APPROVAL",
            )
            .order_by(AuditEvent.created_at.desc())
            .first()
        )
        if requester is None or requester[0] == str(admin.id):
            # Segregation of duties: the administrator who asked for approval cannot also approve.
            raise HTTPException(
                403,
                detail={
                    "code": "SOD_DENIED",
                    "message": "A different administrator from the one who requested approval must approve.",
                },
            )
    if payload.action in {"REQUEST_APPROVAL", "APPROVE", "PROMOTE"} and not has_rules:
        raise HTTPException(
            409,
            detail={
                "code": "RELEASE_GATE_BLOCKED",
                "message": "A release must contain validated mapping rules before approval or promotion.",
            },
        )
    previous = current
    row.status = target
    row.updated_at = datetime.now(timezone.utc)
    event = AuditEvent(
        id=uuid.uuid4(),
        tenant_id=admin.tenant_id,
        actor_ref=str(admin.id),
        action=f"MAPPING_RELEASE_{payload.action}",
        entity_type="MappingConfiguration",
        entity_id=row.id,
        details={
            "from_status": previous,
            "to_status": target,
            "version": row.version,
            "reason": payload.reason,
            "dependencies": [row.source_system, row.target_entity],
        },
        created_at=datetime.now(timezone.utc),
    )
    db.add(event)
    db.commit()
    return {
        "id": str(row.id),
        "code": row.code,
        "version": row.version,
        "previous_status": previous,
        "status": target,
        "audit_event_id": str(event.id),
        "rollback_supported": target in {"RELEASED", "ACTIVE"},
    }
