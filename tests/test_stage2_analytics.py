from types import SimpleNamespace

from backend.app.stage3_router import persona_dashboard, signals_summary


def _ctx():
    return SimpleNamespace(tenant_id="tenant-a", user_id="user-a")


class EmptyDB:
    def execute(self, *args, **kwargs):
        return self

    def rollback(self):
        pass

    def __iter__(self):
        return iter(())

    def scalar(self):
        return 0


def test_signals_are_tenant_scoped_and_limited_when_optional_data_is_missing():
    result = signals_summary(EmptyDB(), _ctx())
    assert result["tenant_id"] == "tenant-a"
    assert result["signals"] == []
    assert result["limitations"]


def test_signals_return_the_recorded_severity():
    class RowsDB(EmptyDB):
        def __init__(self):
            self.statements = []

        def execute(self, statement, *args, **kwargs):
            self.statements.append(str(statement))
            return self

        def __iter__(self):
            return iter([SimpleNamespace(_mapping={"business_id": "CMP000001", "severity": "high", "status": "open"})])

    db = RowsDB()
    result = signals_summary(db, _ctx())
    assert result["signals"][0]["severity"] == "high"
    assert "NULL AS severity" not in db.statements[0] and "severity" in db.statements[0]


def test_persona_dashboard_preserves_tenant_and_human_review():
    result = persona_dashboard("executive", EmptyDB(), _ctx())
    assert result["status"] == "READY_FOR_REVIEW"
    assert result["tenant_id"] == "tenant-a"
    assert result["human_review_required"] is True
