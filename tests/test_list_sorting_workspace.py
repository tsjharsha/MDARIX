"""Column sorting of the workspace lists covers every page, not only the page on screen.

Each list sent one page at a time takes ``sort`` (a column key of the screen) and ``order`` (asc/desc): page 2
continues where page 1 stopped in that order, an unknown key keeps the list's usual order, and the parameters each list
already took still mean what they meant. Everything runs in a fresh organization of its own (on the shared plane),
removed at the end, so each list holds only the rows this module creates. Text is compared on names differing in their
last word, so the database's collation and Python agree on the expected order.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from auth.durable import persist_session
from auth.service import _hash
from backend.app.db.models.foundation import AuthUser, Complaint, Product, ProductVersion, Risk, TenantMembership
from backend.app.db.models.signals import Signal
from backend.app.db.models.stage3 import SupplierEvidenceRequest
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from backend.app.main import app

PASSWORD = "List sorting 2026!"
SIGNALS = "/api/v1/triage/signals"
COMPLAINTS = "/api/v1/complaints"
TASKS = "/api/v1/tasks"
REQUESTS = "/api/v1/evidence-requests"
QUEUE = "/api/v1/decisions/queue"
REGISTER = "/api/v1/risk/register"


def _user(tenant_id, role: str, name: str) -> tuple[TestClient, str]:
    """A signed-in person of the organization (``name`` is their display name)."""
    with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        user = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            username=f"sorting-{uuid.uuid4().hex[:10]}@example.invalid",
            display_name=name,
            company="Test",
            password_hash=_hash(PASSWORD),
            role=role,
            status="ACTIVE",
            email_verified=True,
            created_at=now,
            updated_at=now,
        )
        db.add(user)
        db.flush()
        db.add(
            TenantMembership(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                user_id=user.id,
                status="ACTIVE",
                is_default=True,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        token = secrets.token_urlsafe(32)
        persist_session(db, token, user.id, tenant_id)
        user_id = str(user.id)
    client = TestClient(app)
    client.cookies.set("mdarix_session", token)
    return client, user_id


@pytest.fixture(scope="module")
def org():
    """A fresh organization: an approver (who reads every list), two colleagues, one product, and per list three
    rows "A", "B", "C" created in the order B, C, A, so no column order matches the order of creation."""
    from backend.app.customer_lifecycle import build_customer_tenant
    from backend.app.trial.retention import purge_trial
    from backend.app.workflow import tasks as task_service

    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        customer, tenant = build_customer_tenant(
            db=db,
            tenant_key=f"SORTWS_{uuid.uuid4().hex[:8].upper()}",
            name="Workspace sorting",
            status="ACTIVE",
            now=now,
        )
        db.add(customer)
        db.add(tenant)
        db.commit()
        tenant_id = tenant.id
    client, approver_id = _user(tenant_id, "APPROVER", "Approver Sortwell")
    _, abel_id = _user(tenant_id, "INVESTIGATOR", "Abel Sortwell")
    _, zelda_id = _user(tenant_id, "INVESTIGATOR", "Zelda Sortwell")
    try:
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            product = Product(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                product_identifier=f"SRT-P-{uuid.uuid4().hex[:6].upper()}",
                name="Sorting Pump",
                created_at=now,
                updated_at=now,
            )
            db.add(product)
            db.flush()
            version = ProductVersion(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                product_id=product.id,
                version_identifier="Rev A",
                created_at=now,
                updated_at=now,
            )
            db.add(version)
            db.flush()
            signals = {}
            # letter: (complaints, priority, owner, age in days)
            signal_rows = {"B": (5, "LOW", None, 3), "C": (1, "CRITICAL", zelda_id, 1), "A": (3, "HIGH", abel_id, 2)}
            for letter, (count, priority, owner, age) in signal_rows.items():
                signal = Signal(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    title=f"Sort signal {letter}",
                    origin="MANUAL",
                    product_id=product.id,
                    product_version_id=version.id,
                    complaint_count=count,
                    suggested_priority=priority,
                    status="NEW",
                    owner_user_id=uuid.UUID(owner) if owner else None,
                    created_by=approver_id,
                    created_at=now - timedelta(days=age),
                    updated_at=now,
                )
                db.add(signal)
                db.flush()
                signals[letter] = signal.id
            for days, letter in ((5, "B"), (1, "C"), (9, "A")):
                db.add(
                    Complaint(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        complaint_identifier=f"SRT-C-{uuid.uuid4().hex[:10].upper()}",
                        product_id=product.id,
                        product_version_id=version.id,
                        event_timestamp=now - timedelta(days=days),
                        description=f"Sort complaint {letter}",
                        status="open",
                        created_at=now,
                        updated_at=now,
                    )
                )
            for letter, priority, due in (("B", "LOW", 2), ("C", "HIGH", 9), ("A", "CRITICAL", 5)):
                task_service.create_task(
                    db,
                    tenant_id,
                    task_type="INVESTIGATION",
                    title=f"Sort task {letter}",
                    source_type="Signal",
                    source_id=signals[letter],
                    assigned_user_id=uuid.UUID(approver_id),
                    priority=priority,
                    due_at=now + timedelta(days=due),
                    created_by=approver_id,
                )
            # letter: (recipient person, recipient role, priority, created minutes ago)
            request_rows = {
                "B": (None, "INVESTIGATOR", "HIGH", 3),
                "C": (zelda_id, None, "LOW", 2),
                "A": (abel_id, None, "CRITICAL", 1),
            }
            for letter, (person, role, priority, minutes) in request_rows.items():
                db.add(
                    SupplierEvidenceRequest(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        requested_by=approver_id,
                        title=f"Sort request {letter}",
                        requested_items={"items": ["Device history record"]},
                        status="OPEN",
                        request_kind="INTERNAL",
                        recipient_user_id=uuid.UUID(person) if person else None,
                        recipient_role=role,
                        priority=priority,
                        created_at=now - timedelta(minutes=minutes),
                        updated_at=now,
                    )
                )
            for identifier, letter in (("SRT-R-1", "B"), ("SRT-R-2", "C"), ("SRT-R-3", "A")):
                db.add(
                    Risk(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        risk_identifier=identifier,
                        product_id=product.id,
                        description=f"Sort risk {letter}",
                        created_at=now,
                        updated_at=now,
                    )
                )
            db.commit()
        yield {"tenant_id": tenant_id, "client": client, "abel": abel_id, "zelda": zelda_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:list-sorting-workspace-cleanup")


def _get(client, path, **params) -> dict:
    response = client.get(path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _pages(client, path, size_name="page_size", **params) -> list[dict]:
    """Every row of the list, read two at a time (page/page_size)."""
    rows, page = [], 1
    while True:
        data = _get(client, path, page=page, **{size_name: 2}, **params)
        rows += data["items"]
        if len(data["items"]) < 2 or len(rows) >= data["total"]:
            return rows
        page += 1


def _offset_pages(client, path, **params) -> list[dict]:
    """Every row of an offset-paged list (limit/offset), two at a time."""
    rows, offset = [], 0
    while True:
        data = _get(client, path, limit=2, offset=offset, **params)
        rows += data["items"]
        if data["next_offset"] is None:
            return rows
        offset = data["next_offset"]


def _letters(rows, field="title") -> list[str]:
    return [str(row[field]).split()[-1] for row in rows]


# ------------------------------------------------------------------------------------------------- signal inbox


def test_signal_inbox_sorts_columns_across_pages(org):
    client = org["client"]
    assert _letters(_pages(client, SIGNALS, sort="title", order="asc")) == ["A", "B", "C"]
    assert _letters(_pages(client, SIGNALS, sort="title", order="desc")) == ["C", "B", "A"]
    # Owner by name (Abel before Zelda), the unowned signal last whichever the direction.
    assert _letters(_pages(client, SIGNALS, sort="owner", order="asc")) == ["A", "C", "B"]
    assert _letters(_pages(client, SIGNALS, sort="owner", order="desc")) == ["C", "A", "B"]
    # Priority from low to critical; age from the youngest.
    assert _letters(_pages(client, SIGNALS, sort="priority", order="asc")) == ["B", "A", "C"]
    assert _letters(_pages(client, SIGNALS, sort="age_days", order="asc")) == ["C", "A", "B"]
    assert _letters(_pages(client, SIGNALS, sort="complaint_count", order="asc")) == ["C", "A", "B"]


def test_signal_inbox_keeps_its_sort_by_choices(org):
    client = org["client"]
    # "Sort by" values keep their natural direction (most complaints first, newest first); "-" reverses them.
    assert _letters(_pages(client, SIGNALS, sort="complaint_count")) == ["B", "A", "C"]
    assert _letters(_pages(client, SIGNALS, sort="-created_at")) == ["B", "A", "C"]
    assert _letters(_pages(client, SIGNALS, sort="priority")) == ["C", "A", "B"]
    # The default order (no sort) is unchanged, and an unknown key is still refused as before.
    assert _letters(_pages(client, SIGNALS)) == ["C", "A", "B"]
    assert client.get(SIGNALS, params={"sort": "x"}).status_code == 422
    assert client.get(SIGNALS, params={"sort": "title", "order": "sideways"}).status_code == 422


# ----------------------------------------------------------------------------------------------- complaint list


def test_complaint_list_sorts_across_pages(org):
    client = org["client"]
    assert _letters(_pages(client, COMPLAINTS, sort="description", order="asc"), "description") == ["A", "B", "C"]
    assert _letters(_pages(client, COMPLAINTS, sort="description", order="desc"), "description") == ["C", "B", "A"]
    # Received: oldest first ascending (A 9 days ago, B 5, C 1).
    assert _letters(_pages(client, COMPLAINTS, sort="received", order="asc"), "description") == ["A", "B", "C"]
    # The usual order (newest first) without a sort and for an unknown key.
    usual = _letters(_pages(client, COMPLAINTS), "description")
    assert usual == ["C", "B", "A"]
    assert _letters(_pages(client, COMPLAINTS, sort="nonsense", order="asc"), "description") == usual


# --------------------------------------------------------------------------------------------------- My Work


def test_my_work_tasks_sort_across_pages(org):
    client = org["client"]
    assert _letters(_pages(client, TASKS, view="assigned", sort="title", order="asc")) == ["A", "B", "C"]
    assert _letters(_pages(client, TASKS, view="assigned", sort="title", order="desc")) == ["C", "B", "A"]
    assert _letters(_pages(client, TASKS, view="assigned", sort="priority", order="asc")) == ["B", "C", "A"]
    assert _letters(_pages(client, TASKS, view="assigned", sort="due_at", order="desc")) == ["C", "A", "B"]
    sources = [
        row["source"]["business_id"] for row in _pages(client, TASKS, view="assigned", sort="source", order="asc")
    ]
    assert sources == sorted(sources, key=str.casefold) and all(sources)
    # Most urgent first by default; an unknown key keeps that order.
    usual = _letters(_pages(client, TASKS, view="assigned"))
    assert usual == ["A", "C", "B"]
    assert _letters(_pages(client, TASKS, view="assigned", sort="nonsense", order="desc")) == usual


# -------------------------------------------------------------------------------------------- evidence requests


def _recipient(row) -> str:
    from backend.app.workflow.labels import role_label

    user = (row["recipient"] or {}).get("user") or {}
    return user.get("name") or role_label(row["recipient"]["role"])


def test_evidence_requests_sort_and_search_every_page(org):
    client = org["client"]
    assert _letters(_pages(client, REQUESTS, box="sent", sort="title", order="asc")) == ["A", "B", "C"]
    assert _letters(_pages(client, REQUESTS, box="sent", sort="priority", order="desc")) == ["A", "B", "C"]
    # "To": the person's name, else the role queue's name.
    recipients = [_recipient(row) for row in _pages(client, REQUESTS, box="sent", sort="party", order="asc")]
    assert recipients == sorted(recipients, key=str.casefold)
    # Newest first by default; an unknown key keeps that order.
    usual = _letters(_pages(client, REQUESTS, box="sent"))
    assert usual == ["A", "C", "B"]
    assert _letters(_pages(client, REQUESTS, box="sent", sort="nonsense")) == usual
    # The search runs on the server over every page: by title, and by the recipient's name.
    assert _letters(_get(client, REQUESTS, box="sent", q="sort request b")["items"]) == ["B"]
    found = _get(client, REQUESTS, box="sent", q="Zelda")
    assert found["total"] == 1 and _letters(found["items"]) == ["C"]


# --------------------------------------------------------------------------------------------- approvals queue


def test_decision_queue_sorts_before_paging(org):
    from types import SimpleNamespace

    from backend.app.human_decision.router import QUEUE_SORTS
    from backend.app.sorting import sort_rows

    def item(case_id, priority, waiting):
        return {
            "investigation": {"business_id": case_id, "product": {"name": None, "business_id": "PRD1"}},
            "brief": {"business_id": f"DB-{case_id}"},
            "required_reviews": [],
            "_case": SimpleNamespace(priority=priority),
            "_due_at": None,
            "_waiting": waiting,
        }

    now = datetime.now(timezone.utc)
    items = [item("INV2", "LOW", now), item("INV3", "CRITICAL", now - timedelta(days=2)), item("INV1", None, None)]

    def ids(rows):
        return [row["investigation"]["business_id"] for row in rows]

    assert ids(sort_rows(items, "caseId", "asc", QUEUE_SORTS)) == ["INV1", "INV2", "INV3"]
    assert ids(sort_rows(items, "priority", "desc", QUEUE_SORTS)) == ["INV3", "INV2", "INV1"]
    assert ids(sort_rows(items, "awaitingSince", "asc", QUEUE_SORTS)) == ["INV3", "INV2", "INV1"]
    assert ids(sort_rows(items, "unknown", "asc", QUEUE_SORTS)) == ["INV2", "INV3", "INV1"]
    # The endpoint takes the parameters (this organization has nothing waiting).
    data = _get(org["client"], QUEUE, sort="priority", order="desc")
    assert data["items"] == [] and data["total"] == 0


# ------------------------------------------------------------------------------------------------ risk register


def test_risk_register_sorts_across_pages(org):
    client = org["client"]
    assert _letters(_offset_pages(client, REGISTER, sort="risk", order="asc"), "description") == ["A", "B", "C"]
    assert _letters(_offset_pages(client, REGISTER, sort="risk", order="desc"), "description") == ["C", "B", "A"]
    # By risk identifier by default (SRT-R-1 is B); an unknown key keeps it.
    assert _letters(_offset_pages(client, REGISTER), "description") == ["B", "C", "A"]
    assert _letters(_offset_pages(client, REGISTER, sort="nonsense", order="desc"), "description") == ["B", "C", "A"]
    # Columns worked out from the links sort the whole register (none is linked here: the usual order remains).
    rows = _offset_pages(client, REGISTER, sort="residual", order="asc")
    assert _letters(rows, "description") == ["B", "C", "A"]
    data = _get(client, REGISTER, limit=2, offset=0, sort="links", order="desc")
    assert data["total"] == 3 and data["next_offset"] == 2 and len(data["items"]) == 2
