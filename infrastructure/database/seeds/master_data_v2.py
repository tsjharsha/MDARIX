"""Master Data seed v2: the source records of each customer application, from the CSV templates.

Adds to md_master the record types and columns that the simulated customer systems hold and that the CSV templates
in data/source-templates define (TrackWise complaints and investigations, Teamcenter items and BOM lines, SAP
materials and batches, ...), so Mapping Studio lists each application's real objects and fields.

Content is frozen with this file (generated from source_simulator/source_catalog.json and the data dictionary on
2026-10-03). Existing v1 objects are left as they are; objects and fields already present are skipped, so loading
twice changes nothing.
"""

from __future__ import annotations

from sqlalchemy import text

from infrastructure.database.seeds.master_data_v1 import (
    CONFIDENTIAL_FIELDS,
    FIELD_GROUP_OF,
    SENSITIVE_QUALITY_FIELDS,
    _insert,
    _label,
)

SCHEMA_VERSION = "v2"
LONG_TEXT = {"description", "problem_description", "text", "investigation_question", "conclusion", "notes"}


def _data_type(column: str, declared: str) -> str:
    declared = declared.lower()
    if declared.startswith("date-time"):
        return "DATETIME"
    if declared.startswith("date"):
        return "DATE"
    if declared in {"y/n", "x or empty"}:
        return "BOOLEAN"
    if declared.startswith("number"):
        return "DECIMAL"
    return "TEXT" if column in LONG_TEXT else "STRING"


def _classification(column: str) -> str:
    if column in CONFIDENTIAL_FIELDS:
        return "CONFIDENTIAL"
    if column in SENSITIVE_QUALITY_FIELDS:
        return "SENSITIVE_QUALITY"
    return "INTERNAL"


def load(conn, catalog: dict, dictionary: list[dict]) -> dict[str, int]:
    """Insert the catalog's objects and fields that md_master does not have yet."""
    declared = {(row["application"], row["file"], row["column"]): row for row in dictionary}
    groups = dict(conn.execute(text("select group_code, field_group_uuid from md_master.field_group_definition")).all())
    classifications = dict(
        conn.execute(text("select classification_code, classification_uuid from md_master.data_classification")).all()
    )
    counts = {"source_object_definition": 0, "source_field_definition": 0, "applications_missing": 0}
    for app_code, application in catalog.items():
        app = conn.execute(
            text(
                "select a.application_uuid, v.application_version_uuid from md_master.external_application a "
                "left join md_master.application_version_definition v on v.application_uuid = a.application_uuid "
                "where a.application_code = :code order by v.created_at limit 1"
            ),
            {"code": app_code},
        ).first()
        if app is None:
            counts["applications_missing"] += 1
            continue
        for record_name, record in application["records"].items():
            object_code = record_name.upper()
            source_object = conn.execute(
                text(
                    "select source_object_uuid from md_master.source_object_definition "
                    "where application_uuid = :app and object_code = :code"
                ),
                {"app": app.application_uuid, "code": object_code},
            ).scalar()
            if source_object is None:
                columns = record["columns"]
                source_object = _insert(
                    conn,
                    "source_object_definition",
                    "source_object_uuid",
                    application_uuid=app.application_uuid,
                    application_version_uuid=app.application_version_uuid,
                    object_code=object_code,
                    object_name=record["label"][:200],
                    api_object_name=record_name,
                    primary_key_field="+".join(record["key"])[:120],
                    incremental_cursor_field="updated_at" if "updated_at" in columns else None,
                    schema_version=SCHEMA_VERSION,
                )
                counts["source_object_definition"] += 1
            present = set(
                conn.execute(
                    text("select field_name from md_master.source_field_definition where source_object_uuid = :obj"),
                    {"obj": source_object},
                ).scalars()
            )
            for column in record["columns"]:
                if column in present:
                    continue
                info = declared.get((app_code, f"{record_name}.csv", column), {})
                required = column in record["required"] or column in record["key"]
                _insert(
                    conn,
                    "source_field_definition",
                    "source_field_uuid",
                    source_object_uuid=source_object,
                    field_name=column,
                    field_label=_label(column),
                    field_group_uuid=groups[FIELD_GROUP_OF.get(column, "GENERAL")],
                    description=(info.get("description") or None),
                    data_type=_data_type(column, info.get("data_type", "")),
                    required=required,
                    nullable=not required,
                    data_classification_uuid=classifications[_classification(column)],
                    introduced_schema_version=SCHEMA_VERSION,
                )
                counts["source_field_definition"] += 1
    return counts
