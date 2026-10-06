"""CSV exports open in a spreadsheet as data, never as formulas (CSV injection)."""

import csv
import io
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.app import csv_safe
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.enterprise_audit import make_audit_event
from tests.test_customer_admin_account_security import _client_for, _tenant, _user

ROOT = Path(__file__).resolve().parents[1]
# The exports that go through csv_safe.writer (the CSV files administrators download).
CALL_SITES = {
    "backend/app/access/observability.py": 2,  # audit history export and evidence package
    "backend/app/access/platform_customers.py": 1,  # customer directory
    "backend/app/access/platform_tenants.py": 1,  # tenant directory
}


@pytest.mark.parametrize(
    "value",
    ['=HYPERLINK("http://evil","x")', "+1+1", "-2+3", "@SUM(A1)", "\t=1", "\r=1", "=cmd|' /C calc'!A0"],
)
def test_a_formula_trigger_becomes_text(value):
    assert csv_safe.safe_cell(value) == "'" + value


@pytest.mark.parametrize("value", ["Pump occlusion", "", "a=b", "1-2", 42, 3.5, None, True])
def test_everything_else_is_unchanged(value):
    assert csv_safe.safe_cell(value) == value


def test_the_writer_applies_it_to_every_cell_and_keeps_the_header():
    stream = io.StringIO()
    writer = csv_safe.writer(stream, fieldnames=["name", "count", "note"])
    writer.writeheader()
    writer.writerow({"name": "=1+1", "count": 3, "note": "fine"})
    writer.writerows([{"name": "@x", "count": None, "note": "-5"}])
    rows = list(csv.reader(io.StringIO(stream.getvalue())))
    assert rows == [["name", "count", "note"], ["'=1+1", "3", "fine"], ["'@x", "", "'-5"]]


def test_the_admin_exports_use_the_safe_writer_and_nothing_else():
    for relative, expected in CALL_SITES.items():
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert len(re.findall(r"csv_safe\.writer\(", source)) == expected, relative
        assert not re.search(r"csv\.(DictWriter|writer)\(", source), f"{relative} writes CSV without csv_safe"


def test_an_audit_export_never_carries_a_live_formula():
    with SessionLocal() as db:
        bind_system(db, "test: an organization with a hostile audit value")
        tenant = _tenant(db, "CSV")
        admin = _user(db, tenant, "CUSTOMER_ADMIN", "csv-admin")
        action = f"CSV_TEST_{uuid.uuid4().hex[:8].upper()}"
        db.add(
            make_audit_event(
                tenant_id=tenant.id,
                actor_ref=str(admin.id),
                action=action,
                entity_type="Test",
                reason='=HYPERLINK("http://attacker.invalid","open")',
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        client = _client_for(db, admin)
    response = client.get("/api/v1/admin/audit-history/export", params={"action": action})
    assert response.status_code == 200, response.text
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 1
    assert rows[0]["reason"] == '\'=HYPERLINK("http://attacker.invalid","open")'
