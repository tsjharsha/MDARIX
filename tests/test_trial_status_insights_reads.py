"""0.10.44: right after a large import, GET /api/v1/trial/status and /trial/insights took up to 11 s on a 2-CPU server.
The status counts the sample's records, the organization's own and its uploaded rows in one statement (24 round trips
before); the insights read only the complaint columns they use and each complaint's month from the database (whole
records parsed eight timestamps each). The answers are the same.
"""

import uuid
from datetime import timedelta

from sqlalchemy import event, func

from backend.app.db.models.foundation import Capa, Complaint, Investigation, LotBatch, Product, Risk
from backend.app.db.session import SessionLocal, engine
from backend.app.db.tenant_scope import bind_tenant
from backend.app.trial import imports, insight_questions
from backend.app.trial.router import OWN_COUNTED, SAMPLE_COUNTED, _data_counts
from backend.app.trial.sample_data import SAMPLE_SOURCE
from tests.test_trial_insights import (  # noqa: F401  (the fixture is used by name)
    NOW,
    _sample_workspace,
    _stamp,
    _uploaded_workspace,
    workspaces,
)


class _Statements:
    """The SQL statements run while it is open, but the organization's binding a transaction starts with
    (``set_config``, backend/app/db/tenant_scope.py)."""

    def __init__(self):
        self.seen: list[str] = []

    def _record(self, conn, cursor, statement, parameters, context, executemany):
        if "set_config(" not in statement:
            self.seen.append(statement)

    def __enter__(self):
        event.listen(engine, "before_cursor_execute", self._record)
        return self

    def __exit__(self, *exc):
        event.remove(engine, "before_cursor_execute", self._record)


def _counted_one_by_one(db, tenant_id, model, source) -> int:
    return db.query(func.count(model.id)).filter(model.tenant_id == tenant_id, model.source_system == source).scalar()


def _uploaded_one_by_one(db, tenant_id) -> int:
    """``imports.uploaded_rows`` as it was before 0.10.44: one count per kind of record."""
    return sum(
        db.query(func.count(model.id)).filter(model.tenant_id == tenant_id, *conditions).scalar() or 0
        for model, conditions in imports.upload_counters()
    )


def test_the_status_counts_everything_in_one_statement_with_the_same_numbers(workspaces):  # noqa: F811
    tenant_id = _uploaded_workspace(workspaces, linked_records=True)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        # The sample's records next to the upload, as in a trial that imported its own complaints.
        from backend.app.trial.sample_data import seed_sample_workspace

        seed_sample_workspace(db, tenant_id, NOW)
        db.commit()
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        with _Statements() as statements:
            sample, own, uploaded = _data_counts(db, tenant_id)
        assert len(statements.seen) == 1
        assert sample == {
            key: _counted_one_by_one(db, tenant_id, model, SAMPLE_SOURCE) for key, model in SAMPLE_COUNTED.items()
        }
        assert own == {
            key: _counted_one_by_one(db, tenant_id, model, imports.UPLOAD_SOURCE) for key, model in OWN_COUNTED.items()
        }
        assert uploaded == _uploaded_one_by_one(db, tenant_id) == imports.uploaded_rows(db, tenant_id)
        assert sample["complaints"] > 0 and own["complaints"] == 12 and uploaded > 0
        assert set(SAMPLE_COUNTED.values()) == {Product, LotBatch, Complaint, Investigation, Capa, Risk}
        with _Statements() as statements:
            imports.uploaded_rows(db, tenant_id)
        assert len(statements.seen) == 1


def test_the_insights_read_complaint_columns_and_months_not_whole_records(workspaces):  # noqa: F811
    tenant_id = _uploaded_workspace(workspaces)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        product = db.query(Product).filter(Product.tenant_id == tenant_id).one()
        # A complaint's month: received, else the event, else when the record was made.
        for identifier, received, event_at, made in (
            ("UP-EVENT", None, NOW - timedelta(days=400), NOW - timedelta(days=5)),
            ("UP-MADE", None, None, NOW - timedelta(days=430)),
        ):
            stamp = {**_stamp(made)}
            db.add(
                Complaint(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    complaint_identifier=identifier,
                    product_id=product.id,
                    complaint_timestamp=received,
                    event_timestamp=event_at,
                    description="Pump alarm during infusion.",
                    source_identifier=identifier,
                    **stamp,
                )
            )
        db.commit()
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        with _Statements() as statements:
            result = imports.insights(db, tenant_id)
        complaint_reads = [sql for sql in statements.seen if "FROM complaints" in sql and "to_char" in sql]
        assert len(complaint_reads) == 1
        # Never the whole record: not its text, nor the timestamps the panel does not use.
        assert "complaints.description" not in complaint_reads[0]
        assert "complaints.awareness_timestamp" not in complaint_reads[0]
        months = {row["ref"]: row["month"] for row in result["records"]}
        assert months["UP-EVENT"] == (NOW - timedelta(days=400)).strftime("%Y-%m")
        assert months["UP-MADE"] == (NOW - timedelta(days=430)).strftime("%Y-%m")
        assert months["UP-001"] == (NOW - timedelta(days=150)).strftime("%Y-%m")
        assert sum(item["complaints"] for item in result["by_month"]) == result["total_complaints"] == 14
        # The month the database works out is the one Python gave the whole record before.
        for complaint in db.query(Complaint).filter(Complaint.tenant_id == tenant_id):
            when = complaint.complaint_timestamp or complaint.event_timestamp or complaint.created_at
            assert months[complaint.complaint_identifier] == when.strftime("%Y-%m")
    assert insight_questions.MONTH.name == "month"


def test_the_insights_route_answers_the_same_body_as_before(workspaces):  # noqa: F811
    """The route answers its JSON as it is (FastAPI's generic conversion of 100,000 values took seconds): the same
    bytes as the default encoding of the same answer."""
    import json

    from fastapi.encoders import jsonable_encoder
    from fastapi.responses import JSONResponse

    tenant_id = _sample_workspace(workspaces)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        answer = imports.insights(db, tenant_id)
    assert JSONResponse(answer).body == JSONResponse(jsonable_encoder(answer)).body
    assert json.loads(JSONResponse(answer).body) == jsonable_encoder(answer)
