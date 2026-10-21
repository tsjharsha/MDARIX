"""What follows an import, made light for the API (0.10.42).

- Detection links an import's complaints to its signals in a few statements instead of one per complaint
  (backend/app/signals/service.py link_complaints), and finds exactly the signals the one-by-one linking found.
- The embeddings for semantic search are no longer made in the API: once the signals are found the import queues one
  RECORD_EMBEDDINGS_REQUESTED outbox event (retrieval/record_evidence.py queue_embeddings), and the background
  service's outbox worker embeds the records in slices (run_embeddings_job, scripts/run_outbox_worker.py). A failure
  is tried again by the outbox and never touches the import; search finds the imported records once the job ran.
"""

import importlib.util
import json
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import event, text

from starlette.background import BackgroundTasks

from backend.app.db.data_plane import open_tenant_data_session
from backend.app.db.models.evidence_intelligence import EvidenceChunk
from backend.app.db.models.foundation import Complaint, Evidence
from backend.app.db.models.retrieval_intelligence import EvidenceChunkEmbedding
from backend.app.db.models.signals import Signal, SignalComplaint, SignalEvent
from backend.app.db.models.stage2 import OutboxEvent
from backend.app.db.session import SessionLocal, engine
from backend.app.db.tenant_scope import bind_system
from backend.app.signals import service as signal_service
from backend.app.signals.labels import DETECTION_ACTOR
from outbox.worker import OutboxWorker
from retrieval import record_evidence
from retrieval.embedding_provider import DeterministicEmbeddingProvider
from retrieval.schemas import RetrievalRequest
from retrieval.service import TrustedRetrievalService
from tests.test_free_trial import _approved_trial_client
from tests.test_free_trial import _clean_trial_workspaces  # noqa: F401 (module fixture)

IMPORT = "/api/v1/trial/imports/complaints"
EVENT = record_evidence.EMBEDDINGS_EVENT


@pytest.fixture
def held_back(monkeypatch):
    """The route's background tasks, kept instead of run, to run when the test says."""
    tasks = []
    monkeypatch.setattr(
        BackgroundTasks, "add_task", lambda self, func, *args, **kwargs: tasks.append((func, args, kwargs))
    )
    return tasks


def _worker_script():
    """scripts/run_outbox_worker.py, whose ``publish`` the background service's outbox worker delivers with."""
    spec = importlib.util.spec_from_file_location(
        "run_outbox_worker_follow_up", Path(__file__).resolve().parents[1] / "scripts" / "run_outbox_worker.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


publish = _worker_script().publish


@pytest.fixture(autouse=True, scope="module")
def _no_embedding_events_left():
    """The embedding events this module queued are removed afterwards, delivered or not."""
    started = datetime.now(timezone.utc)
    yield
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM event_outbox WHERE event_name = :name AND occurred_at >= :started"),
            {"name": EVENT, "started": started},
        )


def _export(prefix: str, count: int, start: int = 0) -> str:
    """``count`` recent complaints of one problem on one pump version (one threshold signal)."""
    recent = date.today() - timedelta(days=3)
    rows = "".join(
        f"{prefix}-{number},{prefix}-PUMP,Aster Pump,Pressure alarm sounded during priming,Rev C,{prefix}-LOT-1,"
        f"{(recent - timedelta(days=number % 5)).isoformat()}\n"
        for number in range(start, start + count)
    )
    return "complaint_id,product_id,product_name,description,version,lot_id,received_date\n" + rows


def _imported(user, held, text: str) -> None:
    held.clear()
    answer = user.post(IMPORT, content=text, headers={"Content-Type": "text/csv"})
    assert answer.status_code == 200, answer.text


def _run(held, *names) -> None:
    """Run the held-back follow-up steps of the last import (those named, else all), in order."""
    for func, args, kwargs in list(held):
        if not names or func.__name__ in names:
            func(*args, **kwargs)
    held.clear()


def _one_by_one(db, signal, complaint_ids, *, how, actor_ref):
    """link_complaints as it was until 0.10.41: one SignalComplaint object, so one INSERT, per complaint."""
    from backend.app.business_ids import as_uuid

    wanted = list(dict.fromkeys(as_uuid(item) for item in complaint_ids if as_uuid(item) is not None))
    if not wanted:
        return []
    present = {
        row[0]
        for row in db.query(SignalComplaint.complaint_id).filter(
            SignalComplaint.tenant_id == signal.tenant_id,
            SignalComplaint.signal_id == signal.id,
            SignalComplaint.complaint_id.in_(wanted),
        )
    }
    now = signal_service.now_utc()
    added = [complaint_id for complaint_id in wanted if complaint_id not in present]
    for complaint_id in added:
        db.add(
            SignalComplaint(
                id=uuid.uuid4(),
                tenant_id=signal.tenant_id,
                signal_id=signal.id,
                complaint_id=complaint_id,
                added_how=how,
                added_by=str(actor_ref or DETECTION_ACTOR),
                added_at=now,
            )
        )
    if added:
        db.flush()
    return added


def _found(tenant_id) -> list[tuple]:
    """The organization's import signals: facts, status, history and linked complaints (by their numbers)."""
    tenant = uuid.UUID(str(tenant_id))
    with SessionLocal() as db:
        bind_system(db, "test: the organization's signals")
        found = []
        for row in db.query(Signal).filter(Signal.tenant_id == tenant, Signal.title.like("%Aster Pump%")):
            linked = sorted(
                number
                for (number,) in db.query(Complaint.complaint_identifier)
                .join(SignalComplaint, SignalComplaint.complaint_id == Complaint.id)
                .filter(SignalComplaint.tenant_id == tenant, SignalComplaint.signal_id == row.id)
            )
            events = sorted(
                (kind, json.dumps(details, sort_keys=True))
                for kind, details in db.query(SignalEvent.event_type, SignalEvent.details).filter(
                    SignalEvent.tenant_id == tenant, SignalEvent.signal_id == row.id
                )
            )
            found.append(
                (
                    row.title,
                    row.complaint_count,
                    row.suggested_priority,
                    row.status,
                    row.origin,
                    row.highest_severity,
                    row.first_event_at,
                    row.last_event_at,
                    tuple(linked),
                    tuple(events),
                )
            )
        return sorted(found)


def _statements(table: str):
    """A list that collects the INSERT statements into ``table`` while the test runs."""
    seen = []

    def count(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith(f"INSERT INTO {table.upper()} "):
            seen.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    return seen, lambda: event.remove(engine, "before_cursor_execute", count)


def test_detection_links_an_imports_complaints_in_bulk_and_finds_the_signals_it_found_before(held_back, monkeypatch):
    # 1,200 complaints in one group: more than one statement's worth of links (LINK_BATCH).
    first, first_approval, _ = _approved_trial_client()
    _imported(first, held_back, _export("BULK", 1200))
    inserts, stop = _statements("signal_complaints")
    try:
        _run(held_back, "detect_after_import")
    finally:
        stop()
    assert len(inserts) <= 3, f"{len(inserts)} INSERT statements for 1,200 links"
    found = _found(first_approval["tenant_id"])
    assert len(found) == 1 and found[0][1] == 1200 and len(found[0][8]) == 1200

    # The same file in another trial, linked one by one as until 0.10.41: the same signal, facts and history.
    second, second_approval, _ = _approved_trial_client()
    _imported(second, held_back, _export("BULK", 1200))
    monkeypatch.setattr(signal_service, "link_complaints", _one_by_one)
    _run(held_back, "detect_after_import")
    monkeypatch.undo()
    assert _found(second_approval["tenant_id"]) == found

    # More complaints of the same group later: added to the open signal (LINK), again the same either way.
    _imported(first, held_back, _export("BULK", 30, start=1200))
    _run(held_back, "detect_after_import")
    _imported(second, held_back, _export("BULK", 30, start=1200))
    monkeypatch.setattr(signal_service, "link_complaints", _one_by_one)
    _run(held_back, "detect_after_import")
    monkeypatch.undo()
    first_found = _found(first_approval["tenant_id"])
    assert first_found[0][1] == 1230
    assert _found(second_approval["tenant_id"]) == first_found


def _events(tenant_id) -> list[OutboxEvent]:
    with SessionLocal() as db:
        bind_system(db, "test: the organization's embedding events")
        rows = (
            db.query(OutboxEvent)
            .filter(OutboxEvent.tenant_id == uuid.UUID(str(tenant_id)), OutboxEvent.event_name == EVENT)
            .order_by(OutboxEvent.occurred_at)
            .all()
        )
        db.expunge_all()
        return rows


def _embedded(tenant_id) -> tuple[int, int]:
    """(chunks, chunks with a current INDEXED embedding) of the organization's records."""
    tenant = uuid.UUID(str(tenant_id))
    with SessionLocal() as db:
        bind_system(db, "test: the organization's embeddings")
        chunks = db.query(EvidenceChunk).filter(EvidenceChunk.tenant_id == tenant).count()
        indexed = (
            db.query(EvidenceChunkEmbedding.chunk_id)
            .filter(EvidenceChunkEmbedding.tenant_id == tenant, EvidenceChunkEmbedding.indexing_status == "INDEXED")
            .distinct()
            .count()
        )
        return chunks, indexed


def _deliver(event_id) -> OutboxEvent:
    """The outbox worker's delivery of one event (its own transaction), as in the background service."""
    worker = OutboxWorker(publish, base_delay_seconds=30, max_delay_seconds=3600)
    stats = {"published": 0, "failed": 0, "dead_lettered": 0, "stale_recovered": 0}
    with SessionLocal() as db:
        bind_system(db, "test: deliver one embedding event")
        worker._deliver_one(db, event_id, stats)
    with SessionLocal() as db:
        bind_system(db, "test: the event after delivery")
        row = db.get(OutboxEvent, event_id)
        db.expunge(row)
        return row


def _search(tenant_id, text: str) -> set[str]:
    """Semantic search only (the embeddings): the evidence identifiers it finds."""
    tenant = uuid.UUID(str(tenant_id))
    with open_tenant_data_session(tenant) as db:
        response = TrustedRetrievalService().retrieve(
            db, RetrievalRequest(query_text=text, tenant_id=tenant, retrieval_mode="semantic", top_k=50)
        )
        db.rollback()
        found = {result.evidence_id for result in response.results}
        return {
            identifier
            for (identifier,) in db.query(Evidence.evidence_identifier).filter(
                Evidence.tenant_id == tenant, Evidence.id.in_(found)
            )
        }


def test_the_embeddings_are_queued_once_after_detection_and_made_by_the_background_service(held_back):
    user, approval, _ = _approved_trial_client()
    tenant_id = approval["tenant_id"]
    _run(held_back)  # the sign-up's own steps
    before = len(_events(tenant_id))
    _imported(user, held_back, _export("EMBED", 12))
    # After the answer: detection first, then the embeddings are queued (they are not made in the API).
    assert [func.__name__ for func, _, _ in held_back] == ["detect_after_import", "queue_embeddings"]
    _run(held_back)
    events = _events(tenant_id)[before:]
    assert len(events) == 1
    queued = events[0]
    assert set(queued.payload) == {"tenant_id", "source", "records", "imported_at"}
    assert queued.payload["records"] == 12 and queued.payload["source"] == "trial import"
    assert "Pressure alarm" not in json.dumps(queued.payload)  # counts and times only, never record text
    chunks, indexed = _embedded(tenant_id)
    assert chunks >= 12 and indexed < chunks
    # Until the job runs, semantic search does not know the new records (structured search does, as before).
    assert not any("EMBED-" in item for item in _search(tenant_id, "pressure alarm sounded during priming"))

    delivered = _deliver(queued.id)
    assert delivered.published_at is not None and delivered.attempts == 0
    assert _embedded(tenant_id) == (chunks, chunks)
    assert len(_events(tenant_id)[before:]) == 1  # finished in one slice: nothing more queued
    found = _search(tenant_id, "pressure alarm sounded during priming")
    assert {f"RECORD:COMPLAINT:EMBED-{number}" for number in range(12)} <= found


def test_a_large_import_is_embedded_in_slices_each_queueing_the_next(held_back):
    user, approval, _ = _approved_trial_client()
    tenant_id = approval["tenant_id"]
    _run(held_back)
    before = len(_events(tenant_id))
    _imported(user, held_back, _export("SLICE", 150))
    _run(held_back)
    chunks, _ = _embedded(tenant_id)
    batch = TrustedRetrievalService.BATCH_SIZE
    # A slice of no time still embeds one batch, then hands the rest on, with the counts so far.
    payload = _events(tenant_id)[-1].payload
    slices = 0
    while True:
        result = record_evidence.run_embeddings_job(payload, slice_seconds=0)
        slices += 1
        assert result["indexed"] <= batch and result["failed"] == 0
        if not result["deferred"]:
            break
        payload = _events(tenant_id)[-1].payload
        assert payload["embedded"] == slices * batch and payload["records"] == 150
        assert slices < 20
    assert _embedded(tenant_id) == (chunks, chunks)
    assert len(_events(tenant_id)) - before == slices  # the import's event and one per slice handed on


def test_a_failed_embedding_is_tried_again_by_the_outbox_and_never_touches_the_import(held_back, monkeypatch):
    user, approval, _ = _approved_trial_client()
    tenant_id = approval["tenant_id"]
    _run(held_back)
    _imported(user, held_back, _export("RETRY", 12))
    _run(held_back)
    queued = _events(tenant_id)[-1]
    count = len(_events(tenant_id))

    def down(*_args, **_kwargs):
        raise RuntimeError("the embedding model is down")

    monkeypatch.setattr(DeterministicEmbeddingProvider, "embed_batch", down)
    monkeypatch.setattr(DeterministicEmbeddingProvider, "embed_text", down)
    started = datetime.now(timezone.utc)
    failed = _deliver(queued.id)
    # Tried again later by the outbox (30 s, doubling); no slice is handed on while nothing can be embedded.
    assert failed.published_at is None and failed.dead_lettered_at is None and failed.attempts == 1
    assert timedelta(seconds=25) <= failed.next_attempt_at - started <= timedelta(seconds=40)
    assert failed.last_error.startswith("EmbeddingsIncomplete:")
    assert len(_events(tenant_id)) == count
    # The import is untouched.
    assert user.get("/api/v1/trial/status").json()["own_data"]["complaints"] >= 12

    monkeypatch.undo()
    with SessionLocal() as db:
        bind_system(db, "test: the retry is due")
        db.get(OutboxEvent, queued.id).next_attempt_at = datetime.now(timezone.utc)
        db.commit()
    retried = _deliver(queued.id)
    assert retried.published_at is not None and retried.attempts == 1
    chunks, indexed = _embedded(tenant_id)
    assert indexed == chunks


def test_queueing_the_embeddings_never_fails_the_import(held_back, monkeypatch, caplog):
    user, approval, _ = _approved_trial_client()
    _run(held_back)

    def broken(*_args, **_kwargs):
        raise RuntimeError("the control database is away")

    monkeypatch.setattr(record_evidence, "_add_embeddings_event", broken)
    _imported(user, held_back, _export("QUEUE", 12))
    _run(held_back)  # logged, never raised
    assert "could not be queued" in caplog.text
    assert user.get("/api/v1/trial/status").json()["own_data"]["complaints"] >= 12


def test_the_job_runs_at_a_lower_priority_in_a_thread_of_its_own_and_hands_back_its_outcome():
    import threading

    seen = []
    assert record_evidence._at_low_priority(lambda: seen.append(threading.current_thread().name) or 7) == 7
    assert seen == ["mdarix-embeddings"]
    with pytest.raises(ValueError, match="no"):
        record_evidence._at_low_priority(lambda: (_ for _ in ()).throw(ValueError("no")))
    if sys.platform.startswith("linux"):
        import os

        niceness = record_evidence._at_low_priority(lambda: os.getpriority(os.PRIO_PROCESS, threading.get_native_id()))
        assert niceness >= record_evidence.EMBEDDING_NICE


def test_the_scheduled_catch_up_leaves_an_organization_to_its_queued_job(held_back, monkeypatch):
    from backend.app import scheduler

    user, approval, _ = _approved_trial_client()
    tenant = uuid.UUID(approval["tenant_id"])
    _run(held_back)
    _imported(user, held_back, _export("CATCH", 12))
    _run(held_back)
    queued = _events(tenant)[-1]
    seen = []

    def index(self, db, tenant_id, **kwargs):
        seen.append(tenant_id)
        return {"indexed": 0, "failed": 0, "deferred": 0}

    monkeypatch.setattr(TrustedRetrievalService, "index_evidence_chunks", index)

    def catch_up():
        seen.clear()
        with SessionLocal() as db:
            bind_system(db, "test: the scheduled embedding catch-up")
            scheduler.embedding_catch_up(db, {})
        return set(seen)

    # Queued (or under way in the worker): the job embeds them, the catch-up does not as well.
    assert tenant not in catch_up() and seen
    # Dead-lettered: the catch-up takes over again; delivered: nothing holds it back either.
    for column in ("dead_lettered_at", "published_at"):
        with SessionLocal() as db:
            bind_system(db, "test: the job's outcome")
            row = db.get(OutboxEvent, queued.id)
            row.dead_lettered_at = row.published_at = None
            setattr(row, column, datetime.now(timezone.utc))
            db.commit()
        assert tenant in catch_up()
