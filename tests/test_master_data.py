"""Master Data foundation (md_master): allocator, integrity rules, seed and catalog."""

import re
import threading

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from backend.app.db.business_ids import allocate_business_id
from backend.app.db.models.master import MASTER_TABLES_WITH_BUSINESS_IDS
from backend.app.db.session import SessionLocal, engine
from backend.app.master_data import catalog


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _raises_in_savepoint(connection, sql, params=None, match=""):
    savepoint = connection.begin_nested()
    with pytest.raises(DBAPIError, match=match):
        connection.execute(text(sql), params or {})
    savepoint.rollback()


def test_allocator_issues_padded_sequential_ids(db):
    first = allocate_business_id(db, "RCM")
    second = allocate_business_id(db, "RCM")
    assert re.fullmatch(r"RCM\d{5}", first) and re.fullmatch(r"RCM\d{5}", second)
    assert int(second[3:]) == int(first[3:]) + 1


def test_allocator_is_unique_under_concurrency():
    issued: list[str] = []
    lock = threading.Lock()

    def worker():
        session = SessionLocal()
        try:
            for _ in range(10):
                value = allocate_business_id(session, "TSK")
                with lock:
                    issued.append(value)
            session.commit()
        finally:
            session.close()

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(issued) == 50
    assert len(set(issued)) == 50


def test_allocator_never_truncates_and_rejects_unknown_prefix():
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("create sequence md_master.seq_business_id_zztest"))
            connection.execute(
                text(
                    "insert into md_master.business_id_prefix (prefix, entity_name, sequence_name, id_width, owning_schema) "
                    "values ('ZZTEST', 'Test', 'seq_business_id_zztest', 3, 'md_master')"
                )
            )
            connection.execute(text("select setval('md_master.seq_business_id_zztest', 999)"))
            assert connection.execute(text("select md_master.next_business_id('ZZTEST')")).scalar_one() == "ZZTEST1000"
            _raises_in_savepoint(
                connection, "select md_master.next_business_id('NOPE')", match="Unknown business identifier"
            )
        finally:
            transaction.rollback()


def test_business_ids_are_immutable_and_referenced_records_are_retired_not_deleted():
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            _raises_in_savepoint(
                connection,
                "update md_master.external_application set application_id = 'APP99999' where application_code = 'TRACKWISE'",
                match="immutable",
            )
            _raises_in_savepoint(
                connection,
                "delete from md_master.external_application where application_code = 'TRACKWISE'",
                match="retired, not deleted",
            )
            _raises_in_savepoint(
                connection,
                "update md_master.business_id_prefix set sequence_name = 'x' where prefix = 'APP'",
                match="immutable",
            )
            # A never-used DRAFT record may be removed.
            app_uuid = connection.execute(
                text(
                    "insert into md_master.external_application (application_code, application_name, vendor_uuid, category_uuid) "
                    "select 'DRAFT_ONLY_APP', 'Draft', vendor_uuid, category_uuid from md_master.external_application "
                    "where application_code = 'TRACKWISE' returning application_uuid"
                )
            ).scalar_one()
            connection.execute(
                text("delete from md_master.external_application where application_uuid = :u"), {"u": app_uuid}
            )
        finally:
            transaction.rollback()


def test_released_master_mapping_is_immutable():
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            version = connection.execute(
                text(
                    "select v.mapping_version_uuid from md_master.master_mapping_version v "
                    "join md_master.master_mapping_family f using (mapping_family_uuid) "
                    "where f.mapping_code = 'TRACKWISE_COMPLAINT' and v.status = 'RELEASED'"
                )
            ).scalar_one()
            _raises_in_savepoint(
                connection,
                "update md_master.master_mapping_version set change_summary = 'edited' where mapping_version_uuid = :v",
                {"v": version},
                match="immutable",
            )
            _raises_in_savepoint(
                connection,
                "update md_master.master_mapping_version set status = 'DRAFT' where mapping_version_uuid = :v",
                {"v": version},
                match="Invalid status transition",
            )
            _raises_in_savepoint(
                connection,
                "update md_master.master_mapping_item set mapping_notes = 'x' where mapping_version_uuid = :v",
                {"v": version},
                match="cannot change",
            )
            # Superseding a released version is the allowed lifecycle move.
            connection.execute(
                text(
                    "update md_master.master_mapping_version set status = 'SUPERSEDED' where mapping_version_uuid = :v"
                ),
                {"v": version},
            )
        finally:
            transaction.rollback()


def test_every_master_table_uses_its_business_id_prefix(db):
    for table, (column, prefix) in MASTER_TABLES_WITH_BUSINESS_IDS.items():
        values = [row[0] for row in db.execute(text(f"select {column} from md_master.{table}"))]
        assert values, f"{table} has no seed rows"
        assert all(re.fullmatch(rf"{prefix}\d{{5,}}", value) for value in values), table


def test_seed_catalog_is_consistent(db):
    apps = {row["application_id"] for row in catalog.applications(db)}
    assert {"TRACKWISE", "VEEVA_QMS", "TEAMCENTER", "ORACLE_ERP", "COUPA", "PLM", "ERP", "SUPPLIER"} <= apps
    for family in catalog.mapping_families(db):
        assert family["application_id"] in apps
        assert family["source_object_id"].startswith(family["application_id"] + ":")
    # Protected system fields are never mapping targets.
    for entity in catalog.canonical_entities(db):
        for field in catalog.canonical_fields(db, entity["entity_id"]):
            assert not (field["system_managed"] and field["mapping_allowed"]), field["canonical_field_id"]
            if field["data_type"] == "UUID_REF":
                assert field["reference_entity"], field["canonical_field_id"]
    released = {item["family"]: item for item in catalog.released_mappings(db)}
    assert set(released) == {"TRACKWISE_COMPLAINT", "PLM_PRODUCT_VERSION"}
    complaint = released["TRACKWISE_COMPLAINT"]
    assert re.fullmatch(r"[0-9a-f]{64}", complaint["released_content_hash"])
    targets = {rule["target"] for rule in complaint["rules"]}
    required = {
        f["field_name"] for f in catalog.canonical_fields(db, "COMPLAINT") if f["required"] and f["mapping_allowed"]
    }
    assert required <= targets
    assert all(rule["transform"] == "LOOKUP" for rule in complaint["rules"] if rule["target"].endswith("_uuid"))


def test_catalog_reads_trackwise_complaint_source_schema(db):
    fields = {field["field_name"]: field for field in catalog.source_fields(db, "TRACKWISE:COMPLAINT")}
    assert fields["complaint_id"]["required"] is True
    assert fields["event_date"]["data_type"] == "DATE"
    assert fields["serious_injury"]["sensitivity_classification"] == "SENSITIVE_QUALITY"
    assert fields["severity"]["enum_values"] == ["MIN", "MAJ", "CRIT"]
    assert catalog.enum_value_map(db, "TRACKWISE:COMPLAINT", "severity") == {
        "MIN": "MINOR",
        "MAJ": "MAJOR",
        "CRIT": "CRITICAL",
    }
    assert catalog.source_fields(db, "TRACKWISE:NOT_AN_OBJECT") is None
    assert catalog.application_objects(db, "NOT_AN_APP") is None
