"""B9-D16 (review finding 2): the official MvPI and Health Canada forms are frozen at approval, as the eMDR file is.
The edition is picked from the register by the day sent for approval; the filled PDF is kept in the snapshot with its
SHA-256; a later change to the blank form or the field map never changes an approved report's PDF. A snapshot
approved before this change gets a render marked "DRAFT - NOT THE APPROVED FILE", never a silent change. Spec 6.4:
off, the chains are not shown and their cancel answers 404."""

from __future__ import annotations

import base64
import hashlib
import io
import uuid

import pytest
from pypdf import PdfReader

from backend.app.authority_reports import mvpi_mdae
from backend.app.db.models.authority_reports import ReportSnapshot
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from backend.app.rule_register import register
from tests.test_authority_reports_api import REPORTS, _items, _ok
from tests.test_b9_canada_chain import _children, _fill_and_approve, _sign_canada, _submit, trial  # noqa: F401
from tests.test_b9_india_chain import _create, _state
from tests.test_market_assessment_api import _acknowledge
from tests.test_release_c3_0_10_75 import _flagship, _reports

pytestmark = pytest.mark.db

OTHER_PDF = mvpi_mdae.FORM_FILE.parents[1] / "fda_forms"


def _fields(tenant_id, snapshot: str) -> dict:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        return dict(db.get(ReportSnapshot, uuid.UUID(snapshot)).fields)


def _set_fields(tenant_id, snapshot: str, **changes) -> None:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = db.get(ReportSnapshot, uuid.UUID(snapshot))
        fields = {**row.fields, **changes}
        row.fields = {key: value for key, value in fields.items() if value is not None}
        db.commit()


def _approved(detail: dict) -> str:
    return next(row for row in detail["snapshots"] if row["state"] == "APPROVED")["id"]


@pytest.mark.unit
def test_both_editions_are_in_the_register_from_the_start_and_pin_their_files():
    india, canada = register.pick("mvpi-mdae"), register.pick("hc-mdpr")
    assert (india["code"], canada["code"]) == ("mvpi-mdae-1.2", "hc-mdpr-2018-04")
    assert india["effective_from"] is None and canada["effective_from"] is None
    assert india["content"]["sha256"] == hashlib.sha256(mvpi_mdae.FORM_FILE.read_bytes()).hexdigest()
    assert canada["content"]["file"] is None  # the owner's form file is still awaited
    assert register.file_problems(india) == [] and register.file_problems(canada) == []


@pytest.mark.unit
def test_a_changed_blank_form_or_map_is_a_new_version(monkeypatch):
    india = register.get("mvpi-mdae-1.2")
    monkeypatch.setitem(mvpi_mdae.TEXT, "P1", (1, "text_99jppv"))
    assert register.file_problems(india) == [
        "mvpi-mdae-1.2.json: backend.app.authority_reports.mvpi_mdae:field_map changed without a new version"
    ]


def test_the_approved_india_form_is_frozen_and_never_changes(trial, monkeypatch):  # noqa: F811
    user, tenant_id = trial["user"], trial["tenant_id"]
    initial = _items(user)[("SAMPLE-RV-10", "IN", "INITIAL")]["id"]
    url = f"{REPORTS}/{initial}/worksheet.pdf"
    sample = _approved(_ok(user.get(f"{REPORTS}/{initial}")))
    stored = _fields(tenant_id, sample)
    # The sample's approval freezes it too (its maker approves as a person does).
    assert stored["form_edition"] == "mvpi-mdae-1.2" and stored["official_sha256"]

    # A follow-up approved through the route: frozen at approval, with the edition picked at Send.
    _state(tenant_id, initial, "ACCEPTED")
    follow = _ok(_create(user, initial, "Follow up"))["id"]
    snapshot = _approved(_fill_and_approve(user, follow))
    stored = _fields(tenant_id, snapshot)
    assert stored["form_edition"] == "mvpi-mdae-1.2"
    first = user.get(f"{REPORTS}/{follow}/worksheet.pdf", params={"snapshot": snapshot, "form": "official"})
    assert first.status_code == 200, first.text
    assert first.content == base64.b64decode(stored["official_pdf"])
    assert hashlib.sha256(first.content).hexdigest() == stored["official_sha256"]

    # Today's blank form and map change: the approved report's PDF stays byte-identical.
    other = next(OTHER_PDF.glob("*.pdf"))
    monkeypatch.setattr(mvpi_mdae, "FORM_FILE", other)
    monkeypatch.setitem(mvpi_mdae.TEXT, "P4", (1, "text_98sygn"))
    again = user.get(f"{REPORTS}/{follow}/worksheet.pdf", params={"snapshot": snapshot, "form": "official"})
    assert again.status_code == 200 and again.content == first.content
    monkeypatch.undo()

    # A stored file that no longer matches its SHA-256 is refused, never re-rendered.
    _set_fields(tenant_id, snapshot, official_sha256="0" * 64)
    refused = user.get(f"{REPORTS}/{follow}/worksheet.pdf", params={"snapshot": snapshot, "form": "official"})
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "OFFICIAL_FORM_CHANGED"

    # Approved before 0.11.00 (nothing frozen): filled now and marked, never a silent change.
    _set_fields(tenant_id, sample, official_pdf=None, official_sha256=None)
    older = user.get(url, params={"snapshot": sample, "form": "official"})
    assert older.status_code == 200, older.text
    reader = PdfReader(io.BytesIO(older.content))
    assert reader.metadata["/Title"].startswith("DRAFT - NOT THE APPROVED FILE")
    assert "NOT THE APPROVED FILE" in reader.pages[-1].extract_text()


def test_off_the_india_chain_is_hidden_and_its_cancel_answers_404(trial, monkeypatch):  # noqa: F811
    user, tenant_id = trial["user"], trial["tenant_id"]
    initial = _items(user)[("SAMPLE-RV-10", "IN", "INITIAL")]["id"]
    _state(tenant_id, initial, "ACCEPTED")
    follow = _ok(_create(user, initial, "Follow up"))["id"]
    monkeypatch.setenv("MDARIX_B9_INDIA", "off")
    assert _ok(user.get(f"{REPORTS}/{initial}"))["india_chain"] is None
    cancel = user.post(f"{REPORTS}/{follow}/cancel", json={"reason": "Started by mistake, not needed."})
    assert cancel.status_code == 404, cancel.text
    monkeypatch.setenv("MDARIX_B9_INDIA", "on")
    assert _ok(user.get(f"{REPORTS}/{initial}"))["india_chain"]["items"]
    cancel = user.post(f"{REPORTS}/{follow}/cancel", json={"reason": "Started by mistake, not needed."})
    assert cancel.status_code == 200, cancel.text


def test_canada_records_its_edition_freezes_nothing_without_the_form_file_and_hides_off(trial, monkeypatch):  # noqa: F811
    user, tenant_id = trial["user"], trial["tenant_id"]
    complaint = _flagship(user)
    _acknowledge(user, "CA")
    _sign_canada(user, complaint)
    report = next(row["id"] for row in _reports(user, complaint) if row["market"] == "CA")
    _ok(user.put(f"{REPORTS}/{report}/fields/A5_FINAL_DATE", json={"value": "2027-02-01"}))
    snapshot = _approved(_fill_and_approve(user, report))
    stored = _fields(tenant_id, snapshot)
    assert stored["form_edition"] == "hc-mdpr-2018-04" and "official_pdf" not in stored  # no form file yet
    refused = user.get(f"{REPORTS}/{report}/worksheet.pdf", params={"snapshot": snapshot, "form": "official"})
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "FORM_FILE_NEEDED"
    _submit(user, report)
    (final,) = _children(tenant_id, report)
    monkeypatch.setenv("MDARIX_B9_CANADA", "off")
    assert _ok(user.get(f"{REPORTS}/{report}"))["canada_chain"] is None
    cancel = user.post(f"{REPORTS}/{final.id}/cancel", json={"reason": "Started by mistake, not needed."})
    assert cancel.status_code == 404, cancel.text
    monkeypatch.setenv("MDARIX_B9_CANADA", "on")
    cancel = user.post(f"{REPORTS}/{final.id}/cancel", json={"reason": "Started by mistake, not needed."})
    assert cancel.status_code == 409 and cancel.json()["detail"]["code"] == "FINAL_IS_OWED"
