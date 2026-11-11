"""DEV-13 (0.10.88): a free trial measured against the approved targets. Opt-in, local only:

    MDARIX_TRIAL_LOAD_MEASURE=1 python -m pytest tests/test_trial_load_measure.py -s

It makes trials on the test database and measures, in-process (FastAPI's TestClient, no network, one Python process):
a 5,000-row complaints import (check and import, queries, peak Python memory); the reads people make on that data
(p50 and p95 of 10 calls each, queries per call); a communications log of more than 500 entries; a team at the trial's
cap of 50 people; a write (a decision tree's saved answers); and several trials read at once from threads. Every
number is printed as one JSON report (and written to MDARIX_TRIAL_LOAD_REPORT as it goes, when set; each read is
asked MDARIX_TRIAL_LOAD_REPEAT times, 10 by default) with the target it is held
against. The trials it makes are deleted at the end. It asserts only that nothing failed: the timings depend on the
machine, so they are reported, not asserted.
"""

from __future__ import annotations

import csv
import io
import json
import os
import statistics
import threading
import time
import tracemalloc
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.engine import Engine


pytestmark = pytest.mark.skipif(
    not os.getenv("MDARIX_TRIAL_LOAD_MEASURE"), reason="set MDARIX_TRIAL_LOAD_MEASURE=1 to measure (DEV-13)"
)

# The approved targets (owner, 3 Nov 2026).
READ_MS, WRITE_MS, IMPORT_S = 500, 1000, 60

# The app runs on TestClient's own thread, so the count is process-wide; the measured calls run one at a time.
_counter = {"on": False, "queries": 0}


@event.listens_for(Engine, "before_cursor_execute")
def _count(*_args, **_kwargs):
    if _counter["on"]:
        _counter["queries"] += 1


def _timed(call):
    _counter.update(on=True, queries=0)
    started = time.perf_counter()
    try:
        response = call()
    finally:
        _counter["on"] = False
    return response, (time.perf_counter() - started) * 1000, _counter["queries"]


def _pct(values: list[float], share: float) -> float:
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(round(share * (len(ordered) - 1))))], 1)


def _series(client: TestClient, method: str, path: str, times: int = 0, body=None, target: int = READ_MS) -> dict:
    times = times or int(os.getenv("MDARIX_TRIAL_LOAD_REPEAT", "10"))
    took, queries, errors = [], [], 0
    for _ in range(times):
        response, ms, count = _timed(lambda: client.request(method, path, json=body))
        errors += response.status_code >= 500
        assert response.status_code < 400, (path, response.status_code, response.text[:300])
        took.append(ms)
        queries.append(count)
    p95 = _pct(took, 0.95)
    return {
        "path": path.split("?")[0],
        "p50_ms": _pct(took, 0.5),
        "p95_ms": p95,
        "queries": int(statistics.median(queries)),
        "server_errors": errors,
        "target_ms": target,
        "meets": p95 <= target,
    }


def _profile(client: TestClient, path: str, name: str) -> None:
    """B6a B1: one call profiled, MDARIX's own 45 slowest functions by cumulative time written next to the report."""
    import cProfile
    import pstats

    folder = os.getenv("MDARIX_TRIAL_LOAD_PROFILE")
    if not folder:
        return
    profiler = cProfile.Profile()
    profiler.runcall(client.get, path)
    with open(os.path.join(folder, f"profile-{name}.txt"), "w", encoding="utf-8") as handle:
        pstats.Stats(profiler, stream=handle).sort_stats("cumulative").print_stats(r"backend[\\/]app", 45)


def _save(report: dict) -> None:
    """Write the report so far (a long run keeps what it measured if it is stopped)."""
    if os.getenv("MDARIX_TRIAL_LOAD_REPORT"):
        with open(os.environ["MDARIX_TRIAL_LOAD_REPORT"], "w", encoding="utf-8") as handle:
            handle.write(json.dumps(report, indent=2))


def _complaints_csv(rows: int) -> bytes:
    """A synthetic export of ``rows`` complaints: five products, two versions, forty lots, five countries."""
    out = io.StringIO()
    columns = ["complaint_id", "product_id", "description", "version", "lot_id", "event_date", "received_date"]
    columns += ["country", "patient_involved", "malfunction", "serious_injury", "death"]
    writer = csv.writer(out)
    writer.writerow(columns)
    start = date(2026, 5, 1)
    for index in range(rows):
        day = start + timedelta(days=index % 180)
        writer.writerow(
            [
                f"LOAD-{index:05d}",
                f"LOAD-PUMP-{index % 5}",
                f"Synthetic complaint {index}: the occlusion alarm sounded during infusion and the pump stopped.",
                "Rev B" if index % 3 else "Rev A",
                f"LOAD-LOT-{index % 40:03d}",
                day.isoformat(),
                (day + timedelta(days=1)).isoformat(),
                ["US", "IN", "DE", "GB", "CA"][index % 5],
                "yes" if index % 7 == 0 else "no",
                "yes" if index % 2 == 0 else "no",
                "yes" if index % 97 == 0 else "no",
                "no",
            ]
        )
    return out.getvalue().encode("utf-8")


def test_measure_a_trial_against_the_targets(monkeypatch):
    from backend.app.db.session import SessionLocal
    from backend.app.trial.retention import purge_trial
    from tests.test_free_trial import _approved_trial_client
    from tests.test_release_0_10_86 import _many_entries

    report: dict = {"topology": "one Python process, FastAPI TestClient in-process, local PostgreSQL 16 in Docker"}
    trials = []
    try:
        user, approval, _ = _approved_trial_client()
        tenant_id = uuid.UUID(approval["tenant_id"])
        trials.append(tenant_id)

        # B6a B1: the complaint page and the story on the sample alone, before any import.
        pages = ["/api/v1/oversight/events/SAMPLE-RV-11", "/api/v1/trial/one-story"]
        report["reads_sample"] = [_series(user, "GET", path) for path in pages]
        _save(report)

        # 1. A 5,000-row import, as one file: check, then import. TestClient would run the work the server does after
        # the answer (finding signals, queueing embeddings) before returning: it is held and timed on its own.
        from backend.app.trial import imports

        deferred, real_after = [], imports.after_import

        class _Later:
            def add_task(self, task, *args, **kwargs):
                deferred.append((task, args, kwargs))

        monkeypatch.setattr(
            imports,
            "after_import",
            lambda _bg, tenant, result, *, source: real_after(_Later(), tenant, result, source=source),
        )
        body = _complaints_csv(5000)
        headers = {"Content-Type": "text/csv"}
        query = "?date_format=ISO&on_problems=skip&personal_data=refuse&file_name=load-5000.csv"
        tracemalloc.start()
        checked, check_ms, check_queries = _timed(
            lambda: user.post(f"/api/v1/data/import/complaints/check{query}", content=body, headers=headers)
        )
        imported, import_ms, import_queries = _timed(
            lambda: user.post(f"/api/v1/data/import/complaints{query}", content=body, headers=headers)
        )
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        started = time.perf_counter()
        for task, args, kwargs in deferred:
            task(*args, **kwargs)
        after_s = time.perf_counter() - started
        assert checked.status_code == 200, checked.text[:500]
        assert imported.status_code == 200, imported.text[:500]
        report["import_5000"] = {
            "bytes": len(body),
            "check_s": round(check_ms / 1000, 1),
            "check_queries": check_queries,
            "import_s": round(import_ms / 1000, 1),
            "import_queries": import_queries,
            "after_the_answer_s": round(after_s, 1),
            "answer": {k: v for k, v in imported.json().items() if isinstance(v, (int, str)) and len(str(v)) < 80},
            "peak_python_mb": round(peak / 2**20, 1),
            "target_s": IMPORT_S,
            "meets": (check_ms + import_ms) / 1000 <= IMPORT_S,
        }

        # 2. The reads a person makes on that data.
        reads = [
            "/api/v1/trial/one-story",
            "/api/v1/trial/story",
            "/api/v1/trial/status",
            "/api/v1/oversight/alerts",
            "/api/v1/triage",
            "/api/v1/complaints/dispositions",
            "/api/v1/communications",
            "/api/v1/readiness",
            "/api/v1/intake",
            "/api/v1/intake/duplicates",
            "/api/v1/oversight/events/SAMPLE-RV-11",
        ]
        # B6a: MDARIX_TRIAL_LOAD_PAGES=1 measures only the complaint page and the story, then stops.
        pages_only = bool(os.getenv("MDARIX_TRIAL_LOAD_PAGES"))
        report["reads_5000"] = []
        for path in pages if pages_only else reads:
            report["reads_5000"].append(_series(user, "GET", path))
            _save(report)
        _profile(user, pages[0], "complaint-page-5000")
        _profile(user, pages[1], "story-5000")
        if pages_only:
            return

        _save(report)
        # 3. A communications log of more than 500 entries.
        _many_entries(tenant_id)
        report["communications_502"] = _series(user, "GET", "/api/v1/communications")

        _save(report)
        # 4. A team at the trial's cap: 49 colleagues besides the owner.
        team_ms = []
        for index in range(49):
            response, ms, _ = _timed(
                lambda: user.post(
                    "/api/v1/trial/team",
                    json={
                        "email": f"load{index}-{tenant_id.hex[:6]}@example.invalid",
                        "display_name": f"Colleague {index:02d}",
                        "personas": ["regulatory", "decision"] if index % 2 else ["quality"],
                    },
                )
            )
            assert response.status_code == 200, response.text[:300]
            team_ms.append(ms)
        report["team_50"] = {
            "invite_p50_ms": _pct(team_ms, 0.5),
            "invite_p95_ms": _pct(team_ms, 0.95),
            "reads": [
                _series(user, "GET", "/api/v1/trial/team"),
                _series(user, "GET", "/api/v1/oversight/events/SAMPLE-RV-11"),
                _series(user, "GET", "/api/v1/oversight/settings"),
            ],
        }

        _save(report)
        # 5. A write: a decision tree's answers saved (each answer saves every answer).
        sample = user.get("/api/v1/oversight/events/SAMPLE-RV-11").json()
        complaint_id = sample["event"]["complaint_id"]
        path = f"/api/v1/complaints/{complaint_id}/market-assessments/IN"
        answers = {"answers": {}, "harm_level": None, "harm_code": None, "harm_level_reason": ""}
        report["write_tree_answers"] = _series(user, "PUT", path, body=answers, target=WRITE_MS)

        _save(report)
        # 6. Several trials read at once (threads), each its own session.
        others = []
        for _ in range(3):
            other, other_approval, _ = _approved_trial_client()
            trials.append(uuid.UUID(other_approval["tenant_id"]))
            others.append(other)
        clients = [user, *others]
        took, failures, lock = [], 0, threading.Lock()

        def work(client: TestClient):
            nonlocal failures
            for path in ["/api/v1/trial/one-story", "/api/v1/triage", "/api/v1/oversight/alerts"] * 3:
                started = time.perf_counter()
                status = client.get(path).status_code
                with lock:
                    took.append((time.perf_counter() - started) * 1000)
                    failures += status >= 500

        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(work, clients * 2))
        report["concurrent_4_trials_8_threads"] = {
            "requests": len(took),
            "wall_s": round(time.perf_counter() - started, 1),
            "p50_ms": _pct(took, 0.5),
            "p95_ms": _pct(took, 0.95),
            "failure_rate": round(failures / max(1, len(took)), 4),
            "target_ms": READ_MS,
        }
    finally:
        with SessionLocal() as db:
            for tenant in trials:
                purge_trial(db, tenant, "test:load-measure-cleanup")
        print(json.dumps(report, indent=2))
        _save(report)
    assert all(item["server_errors"] == 0 for item in report["reads_5000"])
    assert report["concurrent_4_trials_8_threads"]["failure_rate"] == 0
