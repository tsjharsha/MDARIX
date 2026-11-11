"""G21 customer configuration report (B6a 5.4): a snapshot of the configuration in force for one organization, and a
comparison of two snapshots with who, when and why from the audit events between them.

The snapshot is built only from named, non-secret values: a connector contributes its code, type, status, version
and endpoint fields, never its key, key hint, secret reference or free-form configuration. ``configuration_baselines``
(the platform template) is not used.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.db.models.foundation import AuditEvent, ConnectorConfiguration, MappingConfiguration, Tenant

CONNECTOR_FIELDS = ("endpoint", "health_path", "schema_path", "records_path", "mapping_version", "timeout_seconds")
# The audit actions of the routes that change what a snapshot holds (the comparison's who, when and why).
CHANGE_ACTIONS = (
    "REPORTABILITY_SETTINGS_UPDATED",
    "REPORTING_ROLE_SET",
    "REPORT_PERSONAL_DATA_SET",
    "OVERSIGHT_SETTINGS_CHANGED",
    "COMPLAINT_REVIEW_SETTINGS_UPDATED",
    "COMMUNICATION_SETTINGS_CHANGED",
    "EMAIL_INTAKE_SETTINGS_CHANGED",
    "EMAIL_INTAKE_ADDRESS_ROTATED",
    "AI_PROCESSING_SETTING_CHANGED",
    "SIGNAL_RULE_UPDATED",
    "CONNECTOR_CONFIGURATION_CREATED",
    "CONNECTOR_CONFIGURATION_STATUS_CHANGED",
    "CONNECTOR_UPDATED",
    "CONNECTOR_API_KEY_SET",
    "CONNECTOR_API_KEY_REPLACED",
    "CONNECTOR_API_KEY_REMOVED",
    "MAPPING_CONFIGURATION_CREATED",
    "MAPPING_CONFIGURATION_STATUS_CHANGED",
    "ROLE_GRANTED",
    "ROLE_REVOKED",
    "USER_STATUS_CHANGED",
    "USER_REACTIVATED",
)


def _rule_entry(entry: dict | None) -> dict | None:
    if entry is None:
        return None
    return {
        "code": entry["code"],
        "version": entry["version"],
        "effective_from": entry["effective_from"],
        "fingerprint": entry.get("content_hash") or entry.get("code_hash"),
    }


def snapshot(control_db: Session, data_db: Session, viewer, now: datetime) -> dict:
    """The configuration in force now (no secrets)."""
    from backend.app import feature_set
    from backend.app.access.permissions import roles_of_user
    from backend.app.communications.service import attempts_limit
    from backend.app.complaint_review.service import settings_of as review_settings
    from backend.app.mail_in.router import _settings_view as mail_settings
    from backend.app.oversight import service as oversight
    from backend.app.reportability import service as reportability
    from backend.app.role_codes import role_label
    from backend.app.rule_register import register
    from backend.app.signals.service import rule_settings
    from backend.app.signed_reviews.access_review import active_users

    tenant_id = viewer.tenant_id
    reporting = reportability.settings_of(data_db, tenant_id)
    roles = reportability.reporting_roles(data_db, tenant_id)
    review = review_settings(data_db, tenant_id)
    signal = rule_settings(data_db, tenant_id)
    mail = mail_settings(data_db, control_db, tenant_id)
    tenant = control_db.query(Tenant).filter(Tenant.id == tenant_id).one()
    floors = {
        market: _rule_entry(register.floor(market, role=roles.get(market)))
        for market in [*register.FLOOR_RULES, *register.GENERIC_RULES]
    }
    connectors = [
        {
            "code": row.code,
            "type": row.connector_type,
            "status": row.status,
            "version": row.version,
            "key_set": bool(row.credential_set_at),
            **{field: (row.configuration or {}).get(field) for field in CONNECTOR_FIELDS},
        }
        for row in control_db.query(ConnectorConfiguration)
        .filter(ConnectorConfiguration.tenant_id == tenant_id)
        .order_by(ConnectorConfiguration.code)
    ]
    mappings = [
        {
            "code": row.code,
            "source_system": row.source_system,
            "target_entity": row.target_entity,
            "version": row.version,
            "status": row.status,
        }
        for row in control_db.query(MappingConfiguration)
        .filter(MappingConfiguration.tenant_id == tenant_id)
        .order_by(MappingConfiguration.code)
    ]
    users = [
        {
            "user_id": str(user.id),
            "email": user.username,
            "role": role_label(user.role),
            "roles": sorted(role_label(role) for role in roles_of_user(control_db, user)),
        }
        for user in active_users(control_db, viewer)
    ]
    return {
        "taken_at": now.isoformat(),
        "reporting": {
            "windows": reporting.get("windows"),
            "lookback_days": reporting.get("lookback_days"),
            "version": reporting.get("version"),
        },
        "roles_per_market": roles,
        "personal_data_in_reports": reportability.personal_data_on(data_db, tenant_id),
        "rule_register_floors": floors,
        "switches": {name: feature_set.switched_on(name) for name in sorted(feature_set.SWITCHES)},
        "oversight": {
            key: value
            for key, value in oversight.settings_view(oversight.settings_row(data_db, tenant_id)).items()
            if key != "updated_at"
        },
        "complaint_review": {
            key: review.get(key) for key in ("backlog_target_days", "second_look_words", "custom_words", "version")
        },
        "communication": {"attempts_before_escalation": attempts_limit(data_db, tenant_id)},
        "email_intake": {
            key: mail.get(key) for key in ("address", "on", "old_addresses", "allowed_domains", "daily_limit")
        },
        "ai": {
            "processing_allowed": bool(tenant.ai_processing_allowed),
            "monthly_budget": tenant.ai_monthly_token_budget,
        },
        "signal_rule": {key: signal.get(key) for key in ("enabled", "version", "min_complaints", "window_days")},
        "connectors": connectors,
        "mappings": mappings,
        "users": users,
    }


def _flatten(value, prefix: str = "") -> dict[str, object]:
    """``{"a.b": 1}`` paths for dicts; lists of records keyed by their code / user id, other lists kept whole."""
    if isinstance(value, dict):
        out: dict[str, object] = {}
        for key, item in value.items():
            out.update(_flatten(item, f"{prefix}{key}."))
        return out
    if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
        key = next((k for k in ("code", "user_id") if all(k in item for item in value)), None)
        if key:
            out = {}
            for item in value:
                out.update(_flatten({k: v for k, v in item.items() if k != key}, f"{prefix}{item[key]}."))
            return out
    return {prefix.rstrip("."): value}


def compare(before: dict, after: dict, events: list[AuditEvent]) -> dict:
    """Each changed item with its before and after, and the audit events between the two snapshots (who, when, why)."""
    ignored = {"taken_at"}
    left, right = _flatten(before), _flatten(after)
    changes = [
        {"item": path, "before": left.get(path), "after": right.get(path)}
        for path in sorted(set(left) | set(right))
        if path not in ignored and left.get(path) != right.get(path)
    ]
    why = [
        {
            "action": row.action,
            "who": row.actor_ref,
            "when": row.created_at.isoformat(),
            "why": row.reason,
            "old_values": row.old_values,
            "new_values": row.new_values,
        }
        for row in events
    ]
    return {
        "changes": [{**change, "events": [e for e in why if _concerns(change["item"], e)]} for change in changes],
        "events": why,
    }


# Which top-level snapshot section each audit action changes (an item's events are those of its section).
SECTIONS = {
    "reporting": ("REPORTABILITY_SETTINGS_UPDATED",),
    "roles_per_market": ("REPORTING_ROLE_SET",),
    "personal_data_in_reports": ("REPORT_PERSONAL_DATA_SET",),
    "oversight": ("OVERSIGHT_SETTINGS_CHANGED",),
    "complaint_review": ("COMPLAINT_REVIEW_SETTINGS_UPDATED",),
    "communication": ("COMMUNICATION_SETTINGS_CHANGED",),
    "email_intake": ("EMAIL_INTAKE_SETTINGS_CHANGED", "EMAIL_INTAKE_ADDRESS_ROTATED"),
    "ai": ("AI_PROCESSING_SETTING_CHANGED",),
    "signal_rule": ("SIGNAL_RULE_UPDATED",),
    "connectors": tuple(action for action in CHANGE_ACTIONS if action.startswith("CONNECTOR_")),
    "mappings": ("MAPPING_CONFIGURATION_CREATED", "MAPPING_CONFIGURATION_STATUS_CHANGED"),
    "users": ("ROLE_GRANTED", "ROLE_REVOKED", "USER_STATUS_CHANGED", "USER_REACTIVATED"),
}


def _concerns(item: str, event: dict) -> bool:
    return event["action"] in SECTIONS.get(item.split(".", 1)[0], ())


def events_between(control_db: Session, data_db: Session, tenant_id, start: datetime, end: datetime) -> list:
    from backend.app.signed_reviews.audit_review import sessions

    found = []
    for _plane, session in sessions(control_db, data_db):
        found.extend(
            session.query(AuditEvent)
            .filter(
                AuditEvent.tenant_id == tenant_id,
                AuditEvent.action.in_(CHANGE_ACTIONS),
                AuditEvent.created_at > start,
                AuditEvent.created_at <= end,
            )
            .order_by(AuditEvent.created_at.asc())
            .limit(5000)
            .all()
        )
    return sorted(found, key=lambda row: row.created_at)
