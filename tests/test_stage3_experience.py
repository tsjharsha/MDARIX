import re
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.app.stage3_router import (
    agent_catalog,
    product_version_story,
    reports_catalog,
    signal_detail,
    story_view,
)


def _ctx():
    return SimpleNamespace(tenant_id="tenant-a", user_id="user-a")


def test_stage3_catalogs_are_governed_and_tenant_scoped():
    ctx = _ctx()
    reports = reports_catalog(ctx)
    agents = agent_catalog(ctx)
    assert reports["tenant_id"] == "tenant-a"
    # Exactly the twelve reports the renderer supports (reports/service.py:REPORTS), each in JSON, CSV and PDF.
    assert len(reports["reports"]) == 12
    assert all(item["formats"] == ["JSON", "CSV", "PDF"] for item in reports["reports"])
    assert agents["human_authority_required"] is True
    assert all("DECLARE_ROOT_CAUSE" in item["forbidden"] for item in agents["agents"])


def test_story_not_found_is_non_disclosing():
    class EmptyDB:
        def execute(self, *args, **kwargs):
            return self

        def first(self):
            return None

    # Owner decision 2 (10 Nov): another organization's or an unknown id answers 404, the same for both.
    with pytest.raises(HTTPException) as missing:
        story_view("foreign-investigation", EmptyDB(), EmptyDB(), _ctx())
    assert missing.value.status_code == 404
    assert missing.value.detail["code"] == "INVESTIGATION_NOT_FOUND"
    assert "foreign" not in missing.value.detail["message"].lower()


def test_signal_detail_is_tenant_scoped_and_non_disclosing_when_missing():
    class EmptyDB:
        def execute(self, *args, **kwargs):
            return self

        def rollback(self):
            pass

        def __iter__(self):
            return iter(())

    result = signal_detail("foreign-signal", EmptyDB(), _ctx())
    assert result["status"] == "NOT_FOUND"
    assert result["tenant_id"] == "tenant-a"
    assert "foreign" not in result["message"].lower()


def test_product_version_story_is_tenant_scoped_when_missing():
    class EmptyDB:
        def execute(self, *args, **kwargs):
            return self

        def rollback(self):
            pass

        def __iter__(self):
            return iter(())

    result = product_version_story("product-b", "version-b", EmptyDB(), _ctx())
    assert result["status"] == "NOT_FOUND"
    assert result["tenant_id"] == "tenant-a"


def test_product_version_story_reaches_cases_and_evidence_through_the_versions_complaints():
    """Investigations and evidence have no product version column: the story follows investigation_complaints from the
    version's complaints, then the cases' direct and linked (investigation_evidence) evidence, always in the tenant."""

    class RecordingDB:
        def __init__(self):
            self.statements = []
            self._rows = []

        def execute(self, statement, params=None):
            sql = str(statement)
            self.statements.append((sql, params))
            found = "FROM product_versions" in sql
            self._rows = [SimpleNamespace(_mapping={"id": "version-a", "business_id": "PV000001"})] if found else []
            return self

        def scalar(self):
            return 0

        def rollback(self):
            pass

        def __iter__(self):
            return iter(self._rows)

    db = RecordingDB()
    result = product_version_story("product-a", "version-a", db, _ctx())
    assert result["status"] == "READY_FOR_REVIEW"
    assert set(result["counts"]) == {"complaints", "investigations", "evidence"}
    assert all(params["tenant_id"] == "tenant-a" for _, params in db.statements)
    for table in ("investigations", "evidence"):
        # PV-1: the evidence reads name the version's investigations too; each table's own reads are counted.
        reads = [
            sql
            for sql, _ in db.statements
            if f"FROM {table} " in sql and (table == "evidence") == ("FROM evidence " in sql)
        ]
        assert len(reads) == 2, table  # the count and the rows
        for sql in reads:
            assert "investigation_complaints ic" in sql and "c.product_version_id = :version_id" in sql
            assert "ic.tenant_id = :tenant_id" in sql
            # Never the column those tables do not have.
            assert not re.search(r"(?<![.\w])product_version_id", sql), sql
    evidence = [sql for sql, _ in db.statements if "FROM evidence " in sql]
    assert all("investigation_evidence ie" in sql and "ie.tenant_id = :tenant_id" in sql for sql in evidence)
