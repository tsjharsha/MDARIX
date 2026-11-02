"""0.10.67, quality plan stage 6: every link the server sends lands on a screen that exists, and on a record that
exists. The places are frontend/src/app/linkTable.json (the browser's link table); backend/app/links.py builds every
server-sent target and e-mail link from the same values.

- The server's copy of the places and record parameters equals the browser's table.
- Every target a free trial's screens receive (Readiness checks, Oversight rows, alerts, each event's checklist and
  next action, the trial story's chapters) names an existing screen and tab; its record, where it names one, exists
  in the organization; and the fields screens read before 0.10.67 (section, tab) say the same.
- Every e-mail's links open an existing screen and tab; none points to a parked or removed screen.
- The navigation setting (task 6.9): classic by default, set by a platform administrator only, named by the session.
"""

from __future__ import annotations

import inspect
import json
import re
import urllib.parse
import uuid
from pathlib import Path

import pytest

from auth import emailer
from backend.app import links
from backend.app.db.models.foundation import Capa, Complaint, Investigation, Tenant
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system, bind_tenant
from tests.test_free_trial import _approved_trial_client

ROOT = Path(__file__).resolve().parents[1]
TABLE = json.loads((ROOT / "frontend" / "src" / "app" / "linkTable.json").read_text(encoding="utf-8"))
PLACES = TABLE["places"]
# Addresses outside the workspace that e-mails may open (the browser routes them itself: app/router.ts, App.tsx).
OTHER_APP_PATHS = {"/app", "/app/admin", "/app/customer-admin", "/platform-admin/onboarding"}


def test_the_server_names_the_same_places_as_the_browser():
    assert links.PATHS == {name: place["path"] for name, place in PLACES.items()}
    assert {kind: list(value) for kind, value in links.RECORDS.items()} == {
        kind: [value["section"], value["tab"], value["param"]] for kind, value in TABLE["records"].items()
    }
    for kind, (section, tab, _param) in links.RECORDS.items():
        assert tab in PLACES[section]["tabs"], kind


@pytest.mark.unit
def test_a_target_keeps_the_fields_older_screens_read():
    complaint = uuid.uuid4()
    made = links.target("Complaints", "Reports", record=("complaint", complaint))
    assert made["section"] == "Complaints" and made["tab"] == f"Reports?complaint={complaint}"
    assert made["target"] == {
        "section": "Complaints",
        "tab": "Reports",
        "record": {"kind": "complaint", "id": str(complaint)},
        "panel": None,
    }
    # A record alone opens its own place, named by its own parameter.
    assert links.target(record=("complaint", "c1"))["tab"] == "Oversight?event=c1"
    assert links.target(record=("capa", "p1"))["tab"] == "Effectiveness checks?capa=p1"
    assert links.target("My Work") == {
        "section": "My Work",
        "tab": None,
        "target": {"section": "My Work", "tab": None, "record": None, "panel": None},
    }
    for bad in (lambda: links.target("Decisions"), lambda: links.target(record=("hypothesis", "h1"))):
        with pytest.raises(ValueError):
            bad()


@pytest.mark.unit
def test_an_e_mail_address_is_the_browser_s_address():
    assert links.app_path("Investigations", "Decision", record=("case", "INV000147")) == (
        "/app/investigations?case=INV000147&step=Decision"
    )
    assert links.app_path("Getting started", "Team") == "/app/getting-started?tab=Team"
    assert links.app_path("Complaints", "Reports", record=("complaint", "c1")) == (
        "/app/complaints?tab=Reports&complaint=c1"
    )


# ------------------------------------------------------------------------------------------- a trial's targets


def _place_ok(target: dict, where: str) -> None:
    section, tab = target["section"], target.get("tab")
    assert section in PLACES, f"{where}: no screen {section!r}"
    assert not tab or tab in PLACES[section]["tabs"], f"{where}: {section} has no tab {tab!r}"


def _opens_of(value, where="", found=None):
    """Every "opens" in a JSON answer, with where it was found."""
    found = [] if found is None else found
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "opens" and isinstance(item, dict):
                found.append((where, item))
            else:
                _opens_of(item, f"{where}.{key}", found)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _opens_of(item, f"{where}[{index}]", found)
    return found


RECORD_MODELS = {"complaint": Complaint, "disposition": Complaint, "capa": Capa, "case": Investigation}


def _record_exists(db, tenant_id, record: dict) -> bool:
    from backend.app.db.models.authority_reports import ReportObligation
    from backend.app.db.models.guides_communications import CommunicationEntry
    from backend.app.db.models.signals import Signal

    model = {**RECORD_MODELS, "report": ReportObligation, "communication": CommunicationEntry, "signal": Signal}[
        record["kind"]
    ]
    key = uuid.UUID(record["id"])
    return db.query(model).filter(model.id == key, model.tenant_id == tenant_id).first() is not None


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:link-targets-cleanup")


@pytest.mark.db
def test_every_target_a_trial_receives_names_an_existing_screen_and_record(trial):
    user, tenant_id = trial["user"], trial["tenant_id"]
    answers = {
        path: user.get(path)
        for path in (
            "/api/v1/readiness",
            "/api/v1/oversight?show=all",
            "/api/v1/oversight/alerts",
            "/api/v1/trial/story",
        )
    }
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        complaints = [str(row.id) for row in db.query(Complaint.id).filter(Complaint.tenant_id == tenant_id).limit(60)]
    for complaint in complaints:
        answers[f"/api/v1/oversight/events/{complaint}"] = user.get(f"/api/v1/oversight/events/{complaint}")
    found = []
    for path, response in answers.items():
        assert response.status_code == 200, (path, response.text)
        found += _opens_of(response.json(), path)
    assert len(found) >= 40, len(found)
    with_record = 0
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        for where, opens in found:
            target = opens.get("target")
            assert target, f"{where}: no structured target beside section and tab"
            _place_ok(target, where)
            # The fields screens read before 0.10.67 say the same place.
            assert opens == links.target(
                target["section"],
                target["tab"],
                record=(target["record"]["kind"], target["record"]["id"]) if target["record"] else None,
                panel=target["panel"],
            ), where
            if target["record"]:
                with_record += 1
                assert _record_exists(db, tenant_id, target["record"]), f"{where}: no such {target['record']}"
    assert with_record >= 1


@pytest.mark.unit
def test_the_story_chapters_open_existing_screens():
    from backend.app.trial.story import CHAPTERS

    for chapter in CHAPTERS:
        opens = chapter[4]
        _place_ok(opens["target"], chapter[0])


# ------------------------------------------------------------------------------------------- e-mails

APP = "https://app.example.com"


@pytest.fixture
def outbox(monkeypatch):
    monkeypatch.setenv("MDARIX_APP_URL", APP)
    sent = []
    monkeypatch.setattr(
        emailer,
        "_send_email",
        lambda to, subject, text, html=None, reply_to=None: sent.append({"subject": subject, "text": text}) or "SENT",
    )
    return sent


def _filler(parameter: inspect.Parameter):
    annotation = str(parameter.annotation)
    if "bool" in annotation:
        return True
    if "int" in annotation:
        return 3
    if "dict" in annotation:
        return {}
    if "tuple" in annotation or "list" in annotation:
        return ()
    return "x"


def _check_address(url: str, where: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    path = parsed.path.rstrip("/") or "/"
    query = urllib.parse.parse_qs(parsed.query)
    workspace = {place["path"]: name for name, place in PLACES.items()}
    if path in workspace:
        section = workspace[path]
        tab = (query.get("step") if section == "Investigations" else query.get("tab")) or [None]
        _place_ok({"section": section, "tab": tab[0]}, where)
    elif path.startswith("/app") or path.startswith("/platform-admin"):
        assert path in OTHER_APP_PATHS, f"{where}: {url} opens no screen"
        assert "section" not in query, f"{where}: {url} uses ?section="


def test_every_e_mail_link_opens_an_existing_screen(outbox):
    sends = {
        name: function for name, function in inspect.getmembers(emailer, inspect.isfunction) if name.startswith("send_")
    }
    assert len(sends) >= 35
    for name, function in sends.items():
        arguments = {
            parameter.name: _filler(parameter)
            for parameter in inspect.signature(function).parameters.values()
            if parameter.default is inspect.Parameter.empty
        }
        function(**arguments)
    # The links that carry a case, and the trial's support access, are sent as well.
    emailer.send_assignment_notice(
        "a@x.test", organization="Acme", reference="INV000147", assigned_by=None, case="INV000147"
    )
    emailer.send_review_pending_notice(
        "a@x.test", organization="Acme", reference="D1", submitted_by=None, case="INV000147"
    )
    emailer.send_signoff_completed_notice("a@x.test", organization="Acme", reference="D1", signed_by=None, case="INV9")
    emailer.send_support_access_request(
        "a@x.test",
        organization="Acme",
        person="Ravi",
        areas=["Complaints"],
        write=False,
        expires="x",
        reason="x",
        trial=True,
    )
    checked = 0
    for message in outbox:
        for url in re.findall(rf"{re.escape(APP)}[^\s\"'<>)]*", message["text"]):
            _check_address(url, message["subject"])
            checked += 1
    assert checked >= 30
    text = "\n".join(message["text"] for message in outbox)
    # Parked screens are never linked (0.10.67: the risk review linked Risk & Traceability; the approval "Decisions").
    for parked in ("/app/risk-traceability", "/app/decision", "Open Decisions", "/app?section="):
        assert parked not in text, parked
    assert f"{APP}/app/getting-started?tab=Team" in text  # support access in a trial: Getting started › Team
    assert f"{APP}/app/investigations?case=INV000147&step=Decision" in text


# ------------------------------------------------------------------------------------------- the navigation setting


@pytest.mark.db
def test_the_navigation_is_classic_until_a_platform_administrator_sets_it(trial):
    from tests.conftest import authenticated_client

    user, tenant_id = trial["user"], trial["tenant_id"]
    assert user.get("/api/v1/session/context").json()["navigation"] == "classic"
    admin = authenticated_client()
    path = f"/api/v1/platform-admin/tenants/{tenant_id}"
    with SessionLocal() as db:
        bind_system(db, "test: the tenant's lock version")
        lock = db.get(Tenant, tenant_id).lock_version
    assert (
        admin.patch(path, json={"navigation": "sideways", "reason": "Trying stage 7", "lock_version": lock}).status_code
        == 422
    )
    # The trial's own user is no platform administrator: refused.
    assert user.patch(
        path, json={"navigation": "new", "reason": "Demo trial first", "lock_version": lock}
    ).status_code in (
        401,
        403,
    )
    changed = admin.patch(
        path, json={"navigation": "new", "reason": "Demo trial first (stage 7)", "lock_version": lock}
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["updated"] == {"navigation": "new"} and changed.json()["tenant"]["navigation"] == "new"
    assert user.get("/api/v1/session/context").json()["navigation"] == "new"
