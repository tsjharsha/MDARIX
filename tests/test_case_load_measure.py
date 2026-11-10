"""B2 (0.10.93), A5 and B2-15: the Cases list (GET /api/v1/intake/cases) measured on a trial holding 5,000 Cases,
against the budget (p95 under 1 s a read) and the approved read target (500 ms). Opt-in, local only:

    MDARIX_TRIAL_LOAD_MEASURE=1 POSTGRES_DB=mdarix_b2_test python -m pytest tests/test_case_load_measure.py -s

5,000 Cases are written straight into a new trial beside its sample (bulk insert, as the 0.10.86 cap test does), in
every live and finished state, each with a Case check version (signed where its state needs one), owners on half of
them, a serial number each and "Not sure" lots on one in ten. Every view and the searches are then asked
MDARIX_TRIAL_LOAD_REPEAT times (10 by default), in-process, with their queries counted; the bounded old list once
more for comparison. Timings are reported, not asserted; the test asserts only that every read answered without an
error and that the query count of a page does not grow with the page size.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.test_trial_load_measure import _save, _series

pytestmark = pytest.mark.skipif(
    not os.getenv("MDARIX_TRIAL_LOAD_MEASURE"), reason="set MDARIX_TRIAL_LOAD_MEASURE=1 to measure (B2, A5)"
)

BUDGET_MS = 1000
CASES = 5000
# (state, share in tenths): live states first, then finished ones; ESCALATED needs a complaint and is left out.
STATES = [("OPEN", 4), ("PENDING", 1), ("WAITING_INTERNAL", 1), ("IN_REVIEW", 1), ("CLOSED", 2), ("VOIDED", 1)]
SIGNED = {"PENDING": "PENDING", "IN_REVIEW": "SERVICE_ONLY", "CLOSED": "SERVICE_ONLY"}


def _write_cases(tenant_id, owner: str) -> None:
    from backend.app.db.bulk import insert_rows
    from backend.app.db.models.intake import FirstContactCheck, IntakeEvent
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_tenant
    from backend.app.intake import case_rules

    now = datetime.now(timezone.utc)
    plan = [state for state, tenths in STATES for _ in range(tenths)]
    answers = case_rules.clean_answers({f"Q{n}": {"answer": "NO"} for n in range(1, 10)})
    unknown = case_rules.clean_answers(
        {f"Q{n}": {"answer": "NO"} for n in range(1, 10)} | {"Q4": {"answer": "UNKNOWN"}}
    )
    events, checks = [], []
    for index in range(CASES):
        state = plan[index % len(plan)]
        at = now - timedelta(minutes=17 * index)
        event_id = uuid.uuid4()
        events.append(
            {
                "id": event_id,
                "tenant_id": tenant_id,
                "reference": f"CASE-LOAD-{index:05d}",
                "kind": "CONTACT",
                "reporter_words": f"Pump {index % 5} alarmed during an infusion; the nurse restarted it ({index}).",
                "serial_number": f"SN-LOAD-{index:05d}",
                "product_text": f"LoadPump {index % 5}",
                "lot_text": f"LOT-LOAD-{index % 40}",
                "status": state,
                "owner_id": owner if index % 2 else None,
                "identifiers": {"lot": {"not_sure": True, "status": "UNCONFIRMED", "source": "CALLER"}}
                if index % 10 == 0
                else {},
                "voided_at": at if state == "VOIDED" else None,
                "void_reason": "Entered in error (load)" if state == "VOIDED" else None,
                "received_at": at,
                "received_zone": "UTC",
                "created_by": owner,
                "created_at": at,
                "updated_at": at,
            }
        )
        signed = SIGNED.get(state)
        given = unknown if index % 7 == 0 else answers
        checks.append(
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "intake_event_id": event_id,
                "version": 1,
                "guide_version": case_rules.GUIDE_VERSION,
                "answers": given,
                "suggestion": case_rules.case_outcome(given),
                "classification": signed,
                "signed_by": owner if signed else None,
                "signed_at": at if signed else None,
                "review_outcome": "AGREED" if state == "CLOSED" else None,
                "created_by": owner,
                "created_at": at,
                "updated_at": at,
                "history": [],
            }
        )
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        insert_rows(db, IntakeEvent, events)
        insert_rows(db, FirstContactCheck, checks)
        db.commit()


def test_measure_the_cases_list_on_5000_cases():
    from backend.app.db.session import SessionLocal
    from backend.app.intake import cases_list
    from backend.app.trial.retention import purge_trial
    from tests.test_free_trial import _approved_trial_client

    report: dict = {"topology": "one Python process, FastAPI TestClient in-process, local PostgreSQL 16 in Docker"}
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        owner = user.get("/api/v1/intake/cases?size=1").json()["people"][0]["id"]
        _write_cases(tenant_id, owner)
        reads = [f"/api/v1/intake/cases?view={view}&size=25" for view in cases_list.VIEWS]
        reads += [
            "/api/v1/intake/cases?view=all&size=100",
            "/api/v1/intake/cases?view=all&size=25&page=150",
            "/api/v1/intake/cases?view=all&size=25&q=SN-LOAD-04242",
            "/api/v1/intake/cases?view=all&size=25&q=CASE-LOAD-00042",
            "/api/v1/intake/cases?view=all&size=25&q=LoadPump%203",
            "/api/v1/intake/cases?view=to_check&size=25&q=LOT-LOAD-7",
        ]
        report["reads_5000"] = []
        for path in reads:
            item = _series(user, "GET", path, target=BUDGET_MS)
            item["path"] = path
            item["meets_500ms"] = item["p95_ms"] <= 500
            report["reads_5000"].append(item)
            _save(report)
        # The bounded old list (at most 2,000 Cases, each read in full), for comparison: three times only.
        old = _series(user, "GET", "/api/v1/intake", times=3, target=BUDGET_MS)
        old["path"] = "/api/v1/intake (bounded old list)"
        report["old_list"] = old
        report["total"] = user.get("/api/v1/intake/cases?size=1").json()["total"]
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:b2-case-load-measure-cleanup")
        print(json.dumps(report, indent=2))
        _save(report)
    assert report["total"] >= CASES
    assert all(item["server_errors"] == 0 for item in report["reads_5000"])
    small, large = report["reads_5000"][0], next(i for i in report["reads_5000"] if "size=100" in i["path"])
    assert small.get("queries") == large.get("queries"), (small, large)
