"""The Signal inbox's Data filter (0.10.42): All data, only your imported data, only the sample data, as on the
complaint list (0.10.41). Signals have no source of their own; it is read from their linked complaints
(backend/app/signals/service.py from_source): imported = at least one linked complaint from the import, sample =
every linked complaint from the sample, a signal without complaints under All data only. The counts per status follow
the filter, the filter adds no query, and each organization sees only its own signals.
"""

import uuid
from collections import Counter

import pytest
from sqlalchemy import event

from starlette.background import BackgroundTasks

from backend.app.db.data_plane import open_tenant_data_session
from backend.app.db.models.foundation import Complaint, Product
from backend.app.db.models.signals import Signal, SignalComplaint
from backend.app.db.session import engine
from backend.app.signals import service as signal_service
from backend.app.trial.imports import UPLOAD_SOURCE
from backend.app.trial.sample_data import SAMPLE_SOURCE
from tests.test_free_trial import _approved_trial_client
from tests.test_free_trial import _clean_trial_workspaces  # noqa: F401 (module fixture)
from tests.test_import_follow_up_in_background import _export, _imported, _run

LIST = "/api/v1/triage/signals"


@pytest.fixture
def held_back(monkeypatch):
    """The route's background tasks, kept instead of run, to run when the test says."""
    tasks = []
    monkeypatch.setattr(
        BackgroundTasks, "add_task", lambda self, func, *args, **kwargs: tasks.append((func, args, kwargs))
    )
    return tasks


def _listed(user, **params) -> dict:
    answer = user.get(LIST, params={"page_size": 200, **params})  # every status unless one is given
    assert answer.status_code == 200, answer.text
    return answer.json()


def _ids(body: dict) -> set[str]:
    return {item["id"] for item in body["items"]}


def _truth(tenant_id) -> dict[str, tuple[set[str], str]]:
    """Each signal of the organization: the sources of its linked complaints, and its status (read directly)."""
    tenant = uuid.UUID(str(tenant_id))
    with open_tenant_data_session(tenant) as db:
        signals = {str(row.id): (set(), row.status) for row in db.query(Signal).filter(Signal.tenant_id == tenant)}
        for signal_id, source in (
            db.query(SignalComplaint.signal_id, Complaint.source_system)
            .join(Complaint, Complaint.id == SignalComplaint.complaint_id)
            .filter(SignalComplaint.tenant_id == tenant)
        ):
            signals[str(signal_id)][0].add(source)
        return signals


def _workspace(held):
    """A trial with the sample's signals, a signal from its own import, a mixed one and one without complaints."""
    user, approval, _ = _approved_trial_client()
    tenant = uuid.UUID(approval["tenant_id"])
    _imported(user, held, _export("OWN", 12))
    _run(held, "detect_after_import")
    with open_tenant_data_session(tenant) as db:
        own = (
            db.query(Complaint).filter(Complaint.tenant_id == tenant, Complaint.source_system == UPLOAD_SOURCE).first()
        )
        sample = (
            db.query(Complaint).filter(Complaint.tenant_id == tenant, Complaint.source_system == SAMPLE_SOURCE).first()
        )
        mixed = signal_service.create_signal(
            db,
            tenant,
            title="Pressure alarms in the sample and in our own complaints",
            origin="MANUAL",
            product_id=own.product_id,
            complaint_ids=[own.id, sample.id],
            added_how="MANUAL",
            actor_ref="test",
        )
        mixed_id = str(mixed.id)
        product_id = str(db.query(Product.id).filter(Product.tenant_id == tenant).first()[0])
        db.commit()
    created = user.post(LIST, json={"title": "Checked by hand, no complaints yet", "product_id": product_id})
    assert created.status_code == 201, created.text
    return user, tenant, mixed_id, created.json()["id"]


def test_the_data_filter_reads_where_a_signals_complaints_came_from(held_back):
    user, tenant, mixed_id, manual_id = _workspace(held_back)
    truth = _truth(tenant)
    imported = {key for key, (sources, _) in truth.items() if UPLOAD_SOURCE in sources}
    sample = {key for key, (sources, _) in truth.items() if sources == {SAMPLE_SOURCE}}
    own = {key for key, (sources, _) in truth.items() if sources == {UPLOAD_SOURCE}}
    assert own and sample and mixed_id in imported and truth[manual_id][0] == set()

    everything = _listed(user)
    assert _ids(everything) == set(truth)
    # The filter is offered while the sample data is there (as on the complaint list).
    assert SAMPLE_SOURCE in everything["sources"] and UPLOAD_SOURCE in everything["sources"]

    mine = _listed(user, source_system=UPLOAD_SOURCE)
    assert _ids(mine) == imported and own <= imported  # a mixed signal is your data too
    assert manual_id not in _ids(mine)
    samples = _listed(user, source_system=SAMPLE_SOURCE)
    assert _ids(samples) == sample
    assert mixed_id not in _ids(samples) and manual_id not in _ids(samples)
    # The manual signal without complaints shows under All data only.
    assert manual_id in _ids(everything)

    # The counts per status (the Open, New ... All chips) follow the filter.
    for body, wanted in ((mine, imported), (samples, sample), (everything, set(truth))):
        expected = Counter(truth[key][1] for key in wanted)
        assert {code: count for code, count in body["counts_by_status"].items() if count} == dict(expected)
        assert body["total"] == len(wanted)
    open_mine = _listed(user, source_system=UPLOAD_SOURCE, status="OPEN")
    assert _ids(open_mine) == {key for key in imported if signal_service.logic.is_open(truth[key][1])}


def test_the_filter_adds_no_query_and_keeps_to_the_organization(held_back):
    user, tenant, _mixed, _manual = _workspace(held_back)
    other, other_approval, _ = _approved_trial_client()
    _imported(other, held_back, _export("THEIRS", 12))
    _run(held_back, "detect_after_import")

    statements = []

    def count(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    try:
        _listed(user)
        unfiltered = len(statements)
        statements.clear()
        _listed(user, source_system=UPLOAD_SOURCE)
        filtered = len(statements)
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert filtered == unfiltered  # the source is a condition of the same queries, never a read per signal

    mine = _ids(_listed(user, source_system=UPLOAD_SOURCE))
    theirs = _ids(_listed(other, source_system=UPLOAD_SOURCE))
    assert mine and theirs and not mine & theirs
    assert theirs == {
        key for key, (sources, _) in _truth(uuid.UUID(other_approval["tenant_id"])).items() if UPLOAD_SOURCE in sources
    }
    assert not mine & set(_truth(uuid.UUID(other_approval["tenant_id"])))
    assert set(_truth(tenant)) >= mine
