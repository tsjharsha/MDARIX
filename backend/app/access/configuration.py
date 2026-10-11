"""Tenant configuration: connectors, mappings, releases and the generic control-plane editor."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
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
    Tenant,
)
from backend.app.db.session import get_db
from integration.gateway import MappingDefinition, preview
from backend.app.access.schemas import (
    AdminUpdateRequest,
    ConnectorRequest,
    ConnectorRunRequest,
    MappingPreviewRequest,
    MappingCheckRequest,
    MappingRequest,
    ReleaseActionRequest,
    StatusRequest,
)
from backend.app.access.authz import (
    _admin_tenant,
    _guard_user_administration,
    _require_platform_admin,
    is_hidden_from,
)
from backend.app import support_access
from backend.app.access.common import _audit_configuration, _provider_get
from backend.app.access.connector_mapping import (
    IMPORTABLE_TARGETS,
    check_mapping,
    field_rules,
    mapping_targets,
    standard_mappings,
)
from backend.app.db.models.enterprise import ConnectorRun
from backend.app.role_codes import CUSTOMER_ADMIN_ALIASES, is_customer_admin_role

router = APIRouter(prefix="/api/v1", tags=["Access Control"])


# Mapping states reachable only through the release workflow (request approval -> approve -> release).
GOVERNED_MAPPING_STATUSES = frozenset({"READY_FOR_APPROVAL", "APPROVED", "ACTIVE", "RELEASED"})
# The governed states a mapping leaves only by rolling back (a request for approval can still be withdrawn).
APPROVED_MAPPING_STATUSES = frozenset({"APPROVED", "ACTIVE", "RELEASED"})


def _code_taken(db: Session, model, tenant_id, code: str, version: str, kind: str) -> None:
    """A clear refusal when this tenant already has the code at this version (instead of a database error)."""
    exists = (
        db.query(model.id).filter(model.tenant_id == tenant_id, model.code == code, model.version == version).first()
    )
    if exists is not None:
        raise HTTPException(
            409,
            detail={
                "code": f"{kind.upper()}_CODE_EXISTS",
                "message": f"A {kind} with code {code} (version {version}) already exists. Choose another code.",
            },
        )


# Connectors that no longer count against the plan's connector limit.
RETIRED_CONNECTOR_STATUSES = ("RETIRED", "ARCHIVED", "DELETED")


def _enforce_connector_limit(db: Session, tenant_id) -> None:
    from backend.app.access.common import _active_plan_limits

    limit = _active_plan_limits(db, tenant_id).get("connector_limit")
    if not isinstance(limit, int):
        return
    used = (
        db.query(ConnectorConfiguration.id)
        .filter(
            ConnectorConfiguration.tenant_id == tenant_id,
            ~func.upper(ConnectorConfiguration.status).in_(RETIRED_CONNECTOR_STATUSES),
        )
        .count()
    )
    if used >= limit:
        raise HTTPException(
            409,
            detail={
                "code": "CONNECTOR_LIMIT_REACHED",
                "message": f"Your plan allows {limit} connectors and all are in use. Retire one or ask MDARIX for more.",
                "allowed": limit,
                "allocated": used,
            },
        )


def _commit_unique(db: Session, kind: str, code: str) -> None:
    """Commit, turning a race with another request that took the same code into the same clear refusal."""
    from sqlalchemy.exc import IntegrityError

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            409,
            detail={"code": f"{kind.upper()}_CODE_EXISTS", "message": f"A {kind} with code {code} already exists."},
        ) from exc


def _check_secret_namespace(db: Session, tenant_id, configuration: dict) -> None:
    """A credential reference must be in this tenant's namespace (staging and production)."""
    from backend.app.access.outbound import secret_ref_problem, tenant_secret_prefix

    ref = (configuration or {}).get("credential_ref")
    if ref is None:
        return
    tenant = db.get(Tenant, tenant_id)
    identifier = tenant.tenant_identifier if tenant else None
    if secret_ref_problem(ref, identifier) == "CONNECTOR_CREDENTIAL_REF_NOT_FOR_TENANT":
        raise HTTPException(
            422,
            detail={
                "code": "CONNECTOR_CREDENTIAL_REF_NOT_FOR_TENANT",
                "message": f"Name a server secret that starts with {tenant_secret_prefix(identifier or '')}",
            },
        )


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
    _check_secret_namespace(db, admin.tenant_id, configuration)
    _code_taken(db, ConnectorConfiguration, admin.tenant_id, payload.code, payload.version, "connector")
    _enforce_connector_limit(db, admin.tenant_id)
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
    _commit_unique(db, "connector", payload.code)
    return {
        "connector_id": str(row.id),
        "business_id": row.business_id,
        "tenant_id": str(admin.tenant_id),
        "code": row.code,
        "version": row.version,
        "status": row.status,
    }


def _rule_count(rules) -> int:
    if isinstance(rules, dict) and isinstance(rules.get("rules"), list):
        return len(rules["rules"])
    return len(field_rules(rules))


@router.get("/admin/configuration/mapping-targets")
def list_mapping_targets(request: Request, db: Session = Depends(get_db)):
    """The MDARIX records a connector mapping can fill (with their fields) and the conversions it may apply."""
    _admin_tenant(request, db)
    return mapping_targets()


@router.get("/admin/configuration/standard-mappings")
def list_standard_mappings(
    request: Request, application: str | None = None, record: str | None = None, db: Session = Depends(get_db)
):
    """MDARIX's standard mapping for each record of each supported customer system (the CSV templates' layout).
    A mapping started from one is still a draft: it is checked, approved by a second administrator and released."""
    _admin_tenant(request, db)
    return {"mappings": standard_mappings(application, record)}


@router.post("/admin/configuration/mappings/check")
def check_new_mapping(payload: MappingCheckRequest, request: Request, db: Session = Depends(get_db)):
    """Check a mapping before it is saved: can it import records as written?"""
    _admin_tenant(request, db)
    return check_mapping(payload.target_entity, payload.mapping_rules)


@router.get("/admin/configuration/mappings/{configuration_id}/check")
def check_saved_mapping(configuration_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    """Check a saved mapping of this tenant: can it import records as written?"""
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
    return {"mapping_id": str(row.id), "code": row.code, **check_mapping(row.target_entity, row.mapping_rules)}


def _new_mapping(db: Session, tenant_id, payload: MappingRequest, now: datetime) -> MappingConfiguration:
    """A draft mapping for the tenant (its code must be free); the caller audits and commits."""
    rules = dict(payload.mapping_rules)
    rules["_configuration"] = {
        "source_database": payload.source_database,
        "source_schema": payload.source_schema,
        "source_table": payload.source_table,
        "target_schema": payload.target_schema,
        "target_table": payload.target_table or payload.target_entity,
    }
    _code_taken(db, MappingConfiguration, tenant_id, payload.code, payload.version, "mapping")
    row = MappingConfiguration(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
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
    return row


def _mapping_summary(row: MappingConfiguration) -> dict:
    return {
        "id": str(row.id),
        "code": row.code,
        "source_system": row.source_system,
        "target_entity": row.target_entity,
        "version": row.version,
        "status": row.status,
        "mapping_rules": row.mapping_rules,
    }


@router.post("/admin/configuration/mappings")
def create_mapping(payload: MappingRequest, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    row = _new_mapping(db, admin.tenant_id, payload, datetime.now(timezone.utc))
    _audit_configuration(db, admin, "MAPPING_CONFIGURATION_CREATED", "MappingConfiguration", row.id, row.version)
    _commit_unique(db, "mapping", payload.code)
    return {
        "mapping_id": str(row.id),
        "tenant_id": str(admin.tenant_id),
        "code": row.code,
        "version": row.version,
        "status": row.status,
    }


def _customer_tenant(db: Session, tenant_id: uuid.UUID) -> Tenant:
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Tenant not found"})
    return tenant


@router.get("/platform-admin/tenants/{tenant_id}/mappings")
def platform_list_tenant_mappings(tenant_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    """A customer tenant's mapping sheets, for the MDARIX team that helps set them up, under the Configuration
    access the customer approved (backend/app/support_access.py)."""
    admin = _require_platform_admin(request, db)
    _customer_tenant(db, tenant_id)
    support_access.require_customer_approved_access(db, admin, tenant_id, support_access.CONFIGURATION, request=request)
    rows = (
        db.query(MappingConfiguration)
        .filter(MappingConfiguration.tenant_id == tenant_id)
        .order_by(MappingConfiguration.code, MappingConfiguration.version)
        .all()
    )
    return [_mapping_summary(row) for row in rows]


@router.post("/platform-admin/tenants/{tenant_id}/mappings")
def platform_create_tenant_mapping(
    tenant_id: uuid.UUID, payload: MappingRequest, request: Request, db: Session = Depends(get_db)
):
    """Prepare a draft mapping sheet for a customer tenant. Releasing it stays with the customer's own
    administrators (request, approve by a second administrator, release), so the customer decides what imports.
    Needs the Configuration access, with changes, the customer approved."""
    admin = _require_platform_admin(request, db)
    tenant = _customer_tenant(db, tenant_id)
    support_access.require_customer_approved_access(
        db, admin, tenant.id, support_access.CONFIGURATION, write=True, request=request
    )
    now = datetime.now(timezone.utc)
    row = _new_mapping(db, tenant.id, payload, now)
    from backend.app.enterprise_audit import make_audit_event

    db.add(
        make_audit_event(
            tenant_id=tenant.id,
            actor_ref=str(admin.id),
            action="MAPPING_CONFIGURATION_CREATED",
            entity_type="MappingConfiguration",
            entity_id=row.id,
            details={"version": row.version, "source": "PLATFORM_ADMIN", "code": row.code},
            request=request,
            created_at=now,
        )
    )
    _commit_unique(db, "mapping", payload.code)
    return {
        "mapping_id": str(row.id),
        "tenant_id": str(tenant.id),
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
            "business_id": row.business_id,
            "code": row.code,
            "connector_type": row.connector_type,
            "version": row.version,
            "status": row.status,
            "configuration": row.configuration,
            # Whether the connector holds its own API key; the key itself is never returned.
            "has_api_key": bool(row.credential_encrypted),
            "api_key_ends_with": row.credential_hint,
            "api_key_set_at": row.credential_set_at.isoformat() if row.credential_set_at else None,
        }
        for row in rows
    ]


class ConnectorApiKeyRequest(BaseModel):
    api_key: str = Field(min_length=8, max_length=512)


def _tenant_connector(db: Session, tenant_id, configuration_id: uuid.UUID) -> ConnectorConfiguration:
    row = (
        db.query(ConnectorConfiguration)
        .filter(ConnectorConfiguration.id == configuration_id, ConnectorConfiguration.tenant_id == tenant_id)
        .first()
    )
    if row is None:
        raise HTTPException(404, detail={"code": "CONNECTOR_NOT_FOUND", "message": "Connector not found"})
    return row


@router.put("/admin/configuration/connectors/{configuration_id}/api-key")
def set_connector_api_key(
    configuration_id: uuid.UUID, payload: ConnectorApiKeyRequest, request: Request, db: Session = Depends(get_db)
):
    """Store the customer system's API key for this connector, encrypted. It is never shown again."""
    from access_control.connector_secrets import ConnectorSecretsUnavailable, seal

    admin = _admin_tenant(request, db)
    row = _tenant_connector(db, admin.tenant_id, configuration_id)
    try:
        sealed = seal(payload.api_key.strip(), row.tenant_id, row.id)
    except ValueError as exc:
        raise HTTPException(
            422, detail={"code": "CONNECTOR_API_KEY_INVALID", "message": "Use the key exactly as the system issued it"}
        ) from exc
    except ConnectorSecretsUnavailable as exc:
        raise HTTPException(
            503, detail={"code": "CONNECTOR_KEYS_UNAVAILABLE", "message": "Connector keys cannot be stored here yet"}
        ) from exc
    replaced = bool(row.credential_encrypted)
    now = datetime.now(timezone.utc)
    row.credential_encrypted, row.credential_hint, row.credential_set_at = sealed, payload.api_key.strip()[-4:], now
    row.updated_at = now
    _audit_configuration(
        db,
        admin,
        "CONNECTOR_API_KEY_REPLACED" if replaced else "CONNECTOR_API_KEY_SET",
        "ConnectorConfiguration",
        row.id,
        row.version,
        request=request,
    )
    db.commit()
    return {
        "connector_id": str(row.id),
        "business_id": row.business_id,
        "has_api_key": True,
        "api_key_ends_with": row.credential_hint,
    }


@router.delete("/admin/configuration/connectors/{configuration_id}/api-key")
def remove_connector_api_key(configuration_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    row = _tenant_connector(db, admin.tenant_id, configuration_id)
    if not row.credential_encrypted:
        raise HTTPException(404, detail={"code": "NO_API_KEY", "message": "This connector has no stored key"})
    row.credential_encrypted = row.credential_hint = row.credential_set_at = None
    row.updated_at = datetime.now(timezone.utc)
    _audit_configuration(
        db, admin, "CONNECTOR_API_KEY_REMOVED", "ConnectorConfiguration", row.id, row.version, request=request
    )
    db.commit()
    return {"connector_id": str(row.id), "business_id": row.business_id, "has_api_key": False}


@router.get("/admin/configuration/mappings")
def list_mappings(request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    rows = (
        db.query(MappingConfiguration)
        .filter(MappingConfiguration.tenant_id == admin.tenant_id)
        .order_by(MappingConfiguration.code, MappingConfiguration.version)
        .all()
    )
    return [_mapping_summary(row) for row in rows]


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
        # Field rules live under "fields" (older mappings) or as a list under "rules" (the mapping wizard).
        configured_fields = rules.get("fields", rules.get("rules", rules)) if isinstance(rules, dict) else {}
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
    return {"id": str(row.id), "business_id": row.business_id, "status": row.status, "version": row.version}


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
            "business_id": row.business_id,
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
    if resource == "mappings":
        # The release workflow is the only way into READY_FOR_APPROVAL, APPROVED and RELEASED (a second administrator
        # approves), and what it approved stays as approved: this route neither sets a mapping's status nor edits a
        # mapping that is under review, approved or released.
        if "status" in payload.values:
            raise HTTPException(
                409,
                detail={
                    "code": "MAPPING_STATUS_GOVERNED",
                    "message": "Change a mapping's status through its status endpoint or the release workflow.",
                },
            )
        if str(row.status).upper() in GOVERNED_MAPPING_STATUSES:
            raise HTTPException(
                409,
                detail={
                    "code": "MAPPING_FROZEN",
                    "message": "A mapping awaiting approval, approved or released cannot be edited. "
                    "Roll it back, or create a new version.",
                },
            )
    if resource == "users":
        from backend.app.role_codes import canonical_stored_role

        _guard_user_administration(
            admin,
            target=row,
            new_role=str(payload.values["role"]) if "role" in payload.values else None,
            changes_access=bool({"role", "status"} & set(payload.values)),
        )
        if "role" in payload.values:
            payload.values["role"] = canonical_stored_role(str(payload.values["role"]))
    if resource == "approval-authorities":
        # The same rule as creating one (access/governance.py): an administrator role never holds approval authority.
        from backend.app.access.governance import _refuse_administrator_authority

        _refuse_administrator_authority(str(payload.values.get("role_name", row.role_name)))
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
        _check_secret_namespace(db, admin.tenant_id, payload.values["configuration"])
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
    return {
        "id": str(row.id),
        # Users and connectors have an MDARIX ID; roles, policies and mappings do not (None).
        "business_id": getattr(row, "business_id", None),
        "resource": resource,
        "status": getattr(row, "status", "ACTIVE"),
        "version": version,
    }


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
    result = connection_test(row)
    _audit_configuration(db, admin, "CONNECTOR_TEST_EXECUTED", "ConnectorConfiguration", row.id, row.version)
    db.commit()
    return result


def connection_test(row: ConnectorConfiguration) -> dict:
    """Whether MDARIX can reach the connector's system now, as a real request through the outbound policy.

    A connector with an endpoint is asked for its health path (the same SSRF-safe request as provider health: public
    destinations only, no redirects, its credential sent): SUCCESS only when it answers 2xx, otherwise FAILED with
    the reason. A connector without an endpoint has nothing to reach: file connectors receive uploads
    (NOT_APPLICABLE); any other type is NOT_CONFIGURED until an endpoint is saved.
    """
    connector_type = str(row.connector_type or "").upper()
    if not (row.configuration or {}).get("endpoint"):
        if connector_type == "FILE":
            return {
                "status": "NOT_APPLICABLE",
                "connector_type": connector_type,
                "reason": "FILE_CONNECTOR_RECEIVES_UPLOADS",
            }
        return {"status": "NOT_CONFIGURED", "connector_type": connector_type, "reason": "CONNECTOR_ENDPOINT_MISSING"}
    probe = _provider_get(row, "health_path")
    outcome = {"status": "SUCCESS" if probe.get("status") == "HEALTHY" else "FAILED", "connector_type": connector_type}
    for key in ("http_status", "reason"):
        if probe.get(key) is not None:
            outcome[key] = probe[key]
    if probe.get("status") == "INVALID_CONFIGURATION":
        outcome["status"] = "INVALID_CONFIGURATION"
    return outcome


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
    return {"connector_id": str(row.id), "business_id": row.business_id, "code": row.code, **result}


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
    return {"connector_id": str(row.id), "business_id": row.business_id, "code": row.code, **result}


def _record_sync(tenant_id, connector: ConnectorConfiguration, source_system: str, read: int, outcome) -> ConnectorRun:
    """One run per sync, for Sync activity and Reconciliation: what was read, kept and refused, and whether the
    imported rows match what was read. Operational metadata only; the records stay in the tenant's data plane."""
    now = datetime.now(timezone.utc)
    status, accepted, rejected, reconciliation, failure = "COMPLETED", read, 0, None, None
    if outcome:
        if outcome.get("status") == "IMPORTED":
            accepted = int(outcome.get("rows") or 0)
            reconciliation = "MATCH" if accepted == read else "MISMATCH"
        else:
            status, accepted, rejected = "FAILED", 0, read
            reconciliation = "MISMATCH"
            failure = "MAPPING_NOT_USABLE" if outcome.get("reason") else "IMPORT_BLOCKED"
    return ConnectorRun(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        connection_id=connector.code,
        source_system=(connector.configuration or {}).get("source_object") or source_system or connector.connector_type,
        run_type="MANUAL",
        status=status,
        records_received=read,
        records_accepted=accepted,
        records_rejected=rejected,
        reconciliation_status=reconciliation,
        failure_category=failure,
        started_at=now,
        completed_at=now,
        created_at=now,
    )


@router.post("/admin/configuration/connectors/{configuration_id}/execute")
def execute_connector(
    configuration_id: uuid.UUID,
    payload: ConnectorRunRequest,
    request: Request,
    background: BackgroundTasks,
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
    from backend.app.access.connector_sync import ProviderReadError, sync_connector

    try:
        outcome = sync_connector(
            db, admin.tenant_id, row, payload.source_system, str(admin.id), records=payload.records, run_type="MANUAL"
        )
    except ProviderReadError as exc:
        db.rollback()
        raise HTTPException(exc.status, detail={"code": exc.code, "message": exc.message}) from exc
    canonical_import = outcome["canonical_import"]
    if canonical_import and canonical_import.get("status") == "IMPORTED" and canonical_import.get("rows"):
        # Semantic search over the imported records (their text is already searchable by product and record).
        from backend.app.db.data_plane import open_tenant_data_session
        from retrieval.record_evidence import embed_tenant_evidence

        background.add_task(embed_tenant_evidence, open_tenant_data_session, admin.tenant_id)
    return {
        "status": "COMPLETE",
        "run_id": str(outcome["run"].id),
        "tenant_id": str(admin.tenant_id),
        "connector_id": str(row.id),
        "connector_business_id": row.business_id,
        "records_read": outcome["records_read"],
        "outbox_enqueued": outcome["records_read"],
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
    if str(row.status).upper() in APPROVED_MAPPING_STATUSES:
        # Leaving an approved or released state is a rollback (audited, through /release-action), never a plain
        # status change that would put an approved mapping back under editing. A request for approval that has not
        # been approved yet may still be withdrawn here.
        raise HTTPException(
            409,
            detail={
                "code": "MAPPING_STATUS_GOVERNED",
                "message": "An approved or released mapping leaves that state only through the release workflow.",
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
            "rule_count": _rule_count(rules),
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
    # Settings such as "_configuration" are not rules: a mapping without field rules cannot be released.
    has_rules = _rule_count(rules) > 0
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
    self_approved = False
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
            # Segregation of duties: the administrator who asked for approval cannot also approve, unless they are
            # the organization's only administrator; then they approve with a typed reason (the request's
            # ``reason``, at least 10 characters), audited MAPPING_RELEASE_SELF_APPROVED. The two-person rule
            # applies again as soon as a second administrator is active.
            single_admin = requester is not None and is_customer_admin_role(admin.role)
            if not (single_admin and _active_customer_admins(db, admin.tenant_id) == 1):
                raise HTTPException(
                    403,
                    detail={
                        "code": "SOD_DENIED",
                        "message": "A different administrator from the one who requested approval must approve.",
                    },
                )
            self_approved = True
    if payload.action in {"REQUEST_APPROVAL", "APPROVE", "PROMOTE"} and not has_rules:
        raise HTTPException(
            409,
            detail={
                "code": "RELEASE_GATE_BLOCKED",
                "message": "A release must contain validated mapping rules before approval or promotion.",
            },
        )
    if payload.action in {"REQUEST_APPROVAL", "APPROVE", "PROMOTE"} and row.target_entity in IMPORTABLE_TARGETS:
        # A mapping that imports data is released only when it can import as written: every target is a field of
        # its record, every conversion is known, and every required field is filled.
        verdict = check_mapping(row.target_entity, rules)
        if verdict.get("status") != "READY":
            raise HTTPException(
                409,
                detail={
                    "code": "RELEASE_GATE_BLOCKED",
                    "message": "This mapping cannot import as written. Fix it before approval or release.",
                    "problems": verdict.get("problems", []),
                    "missing_required": verdict.get("missing_required", []),
                },
            )
    previous = current
    row.status = target
    row.updated_at = datetime.now(timezone.utc)
    event = AuditEvent(
        id=uuid.uuid4(),
        tenant_id=admin.tenant_id,
        actor_ref=str(admin.id),
        action="MAPPING_RELEASE_SELF_APPROVED" if self_approved else f"MAPPING_RELEASE_{payload.action}",
        entity_type="MappingConfiguration",
        entity_id=row.id,
        details={
            "from_status": previous,
            "to_status": target,
            "version": row.version,
            "reason": payload.reason,
            "dependencies": [row.source_system, row.target_entity],
            **({"self_approved": True, "single_administrator": True} if self_approved else {}),
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
        "self_approved": self_approved,
    }


def _active_customer_admins(db: Session, tenant_id) -> int:
    """How many active Customer Administrators the organization has (any spelling of the role)."""
    normalized = func.upper(func.replace(func.trim(func.coalesce(AuthUser.role, "")), " ", "_"))
    return (
        db.query(func.count(AuthUser.id))
        .filter(
            AuthUser.tenant_id == tenant_id,
            normalized.in_(sorted(CUSTOMER_ADMIN_ALIASES)),
            func.upper(AuthUser.status) == "ACTIVE",
        )
        .scalar()
        or 0
    )
