"""B8 step 3 (B8-01, 04, 05, 07, 08, 10, 11): the EU MIR chain on the sample's EU report (SAMPLE-RV-07). The first
report is an Initial or a Combined initial and final; later reports are a Follow up or a Final, one open at a time;
nothing follows a Combined or a Final except an "Updated final report" on demand. Values carry from the reports
before, never copied. States are set directly here (the approval and submission flows have their own tests)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.app.authority_reports import router as reports
from backend.app.db.models.authority_reports import ReportObligation, ReportSnapshot, ReportSubmission
from backend.app.db.models.market_assessment import ComplaintMarketAssessment
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.test_authority_reports_api import REPORTS, _fields, _items, _ok, trial  # noqa: F401

pytestmark = pytest.mark.db

WHAT = "The returned flow sensor was examined: a blocked port gave the zero reading."
FU, FR, FNR = "Follow up", "Final (Reportable incident)", "Final (Non-reportable incident)"


def _initial(trial) -> str:  # noqa: F811
    """The sample's EU report, reset: no chain, a draft Initial with no submission."""
    initial = _items(trial["user"])[("SAMPLE-RV-07", "EU_NI", "INITIAL")]["id"]
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        row = db.get(ReportObligation, uuid.UUID(initial))
        children = db.query(ReportObligation).filter_by(parent_id=row.id).all()
        for item in (row, *children):
            db.query(ReportSubmission).filter_by(obligation_id=item.id).delete()
            db.query(ReportSnapshot).filter_by(obligation_id=item.id).delete()
        for item in children:
            db.delete(item)
        row.state = "DRAFT"
        row.entries = {key: value for key, value in (row.entries or {}).items() if key not in ("1_2E", "4_2H")}
        db.commit()
    return initial


def _state(trial, report_id: str, state: str) -> None:  # noqa: F811
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        db.get(ReportObligation, uuid.UUID(report_id)).state = state
        db.commit()


def _create(user, report_id: str, kind: str, **extra):
    return user.post(f"{REPORTS}/{report_id}/mir-chain", json={"type": kind, "what_is_new": WHAT, **extra})


def _code(response) -> str:
    return response.json()["detail"]["code"]


def test_b8_an_initial_offers_initial_or_combined_only(trial):  # noqa: F811
    user, initial = trial["user"], _initial(trial)
    view = _ok(user.get(f"{REPORTS}/{initial}"))["mir_chain"]
    assert view["type"] == "Initial" and view["types"] == ["Initial", "Combined initial and final"]
    for kind in (FU, FR, FNR):
        refused = user.put(f"{REPORTS}/{initial}/fields/1_2E", json={"value": kind})
        assert refused.status_code == 422 and _code(refused) == "NOT_THIS_POSITION", kind
    combined = _ok(user.put(f"{REPORTS}/{initial}/fields/1_2E", json={"value": "Combined initial and final"}))
    assert combined["mir_chain"]["type"] == "Combined initial and final"
    _ok(user.put(f"{REPORTS}/{initial}/fields/1_2E", json={"clear": True}))
    assert _create(user, initial, FU).json()["detail"]["code"] == "NOT_SUBMITTED"


def test_b8_a_child_offers_follow_up_or_a_final(trial):  # noqa: F811
    user, initial = trial["user"], _initial(trial)
    _state(trial, initial, "SUBMITTED_PENDING")
    assert _code(_create(user, initial, "Initial")) == "NOT_THIS_POSITION"
    child = _ok(_create(user, initial, FU))
    assert child["parent_id"] == initial and child["kind"] == "RESPONSE"
    assert child["mir_chain"]["type"] == FU and child["mir_chain"]["types"] == [FU, FR, FNR]
    for kind in ("Initial", "Combined initial and final"):
        refused = user.put(f"{REPORTS}/{child['id']}/fields/1_2E", json={"value": kind})
        assert refused.status_code == 422 and _code(refused) == "NOT_THIS_POSITION"
    assert _code(user.put(f"{REPORTS}/{child['id']}/fields/1_2E", json={"clear": True})) == "FOLLOWS_CHAIN"
    switched = _ok(user.put(f"{REPORTS}/{child['id']}/fields/1_2E", json={"value": FR}))
    assert switched["mir_chain"]["type"] == FR
    assert _code(_create(user, initial, FU)) == "CHAIN_OPEN"  # one open at a time


def test_b8_nothing_follows_a_combined_or_final_report(trial):  # noqa: F811
    user, initial = trial["user"], _initial(trial)
    _ok(user.put(f"{REPORTS}/{initial}/fields/1_2E", json={"value": "Combined initial and final"}))
    _state(trial, initial, "ACCEPTED")
    assert _ok(user.get(f"{REPORTS}/{initial}"))["mir_chain"]["ended"] is True
    assert _code(_create(user, initial, FU)) == "CHAIN_ENDED"
    assert _code(_create(user, initial, FU, updated_final=True)) == "CHAIN_ENDED"  # an update is a Final again
    updated = _ok(_create(user, initial, FR, updated_final=True))  # B8-11: on demand only
    assert updated["mir_chain"]["type"] == FR


def test_b8_the_next_report_waits_until_the_last_is_accepted(trial):  # noqa: F811
    user, initial = trial["user"], _initial(trial)
    _state(trial, initial, "SUBMITTED_PENDING")
    child = _ok(_create(user, initial, FU))
    refused = user.post(f"{REPORTS}/{child['id']}/snapshots")
    assert refused.status_code == 409 and _code(refused) == "PREVIOUS_NOT_ACCEPTED"
    _state(trial, initial, "ACCEPTED")
    passed = user.post(f"{REPORTS}/{child['id']}/snapshots")
    assert passed.status_code != 409 or _code(passed) != "PREVIOUS_NOT_ACCEPTED"


def test_b8_the_reference_and_ncas_number_carry_to_every_report(trial):  # noqa: F811
    user, initial = trial["user"], _initial(trial)
    _state(trial, initial, "ACCEPTED")
    first = _fields(_ok(user.get(f"{REPORTS}/{initial}")))
    assert first["1_3_1B"]["value"] and first["1_1C"]["value"] is None
    child = _ok(_create(user, initial, FU))
    values = _fields(child)
    assert values["1_3_1B"]["value"] == first["1_3_1B"]["value"]
    assert values["1_1C"]["value"] == "Unknown"  # none recorded (help text)
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        db.add(
            ReportSubmission(
                tenant_id=trial["tenant_id"],
                obligation_id=uuid.UUID(initial),
                attempt=1,
                route="EU_NCA",
                submitted_at=datetime.now(timezone.utc),
                authority_reference="ANSM-2026-0042",
                recorded_by="test",
                recorded_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
    assert _fields(_ok(user.get(f"{REPORTS}/{child['id']}")))["1_1C"]["value"] == "ANSM-2026-0042"


def _approve(trial, report_id: str, state: str) -> None:  # noqa: F811
    """The report's worksheet as an approved snapshot (the approval flow has its own tests), then ``state``."""
    sections = _ok(trial["user"].get(f"{REPORTS}/{report_id}"))["sections"]
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        row = db.get(ReportObligation, uuid.UUID(report_id))
        versions = [item.version for item in db.query(ReportSnapshot).filter_by(obligation_id=row.id)]
        db.add(
            ReportSnapshot(
                tenant_id=row.tenant_id,
                obligation_id=row.id,
                version=max(versions, default=0) + 1,
                form_version=row.form_version,
                fields={"sections": sections},
                content_fingerprint="0" * 64,
                state="APPROVED",
                requested_by="test",
                requested_at=now,
                approved_by="test-approver",
                approved_at=now,
                signed_record_id=uuid.uuid4(),
            )
        )
        row.state = state
        db.commit()


def _reopen(trial, report_id: str) -> None:  # noqa: F811
    """As a reopen or a re-sign does: the approved snapshot is superseded, the report a draft again."""
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        for item in db.query(ReportSnapshot).filter_by(obligation_id=uuid.UUID(report_id), state="APPROVED"):
            item.state = "SUPERSEDED"
        db.get(ReportObligation, uuid.UUID(report_id)).state = "DRAFT"
        db.commit()


def test_b8_a_correction_to_an_earlier_report_reaches_the_open_draft(trial):  # noqa: F811
    """Values carry from the earlier report's approved snapshot: a reopened report's draft never reaches the open
    child; once the correction is approved, it does."""
    user, initial = trial["user"], _initial(trial)
    _ok(user.put(f"{REPORTS}/{initial}/fields/4_2H", json={"value": "Sensor recall planned (sample)."}))
    _approve(trial, initial, "ACCEPTED")
    child = _ok(_create(user, initial, FU))
    assert _fields(child)["4_2H"]["value"] == "Sensor recall planned (sample)."
    with SessionLocal() as db:  # nothing was copied onto the child
        bind_tenant(db, trial["tenant_id"])
        assert set(db.get(ReportObligation, uuid.UUID(child["id"])).entries) == {"1_2E", "CHAIN"}
    _reopen(trial, initial)
    _ok(user.put(f"{REPORTS}/{initial}/fields/4_2H", json={"value": "Sensor recall done (sample)."}))
    assert _fields(_ok(user.get(f"{REPORTS}/{child['id']}")))["4_2H"]["value"] == "Sensor recall planned (sample)."
    _approve(trial, initial, "ACCEPTED")
    assert _fields(_ok(user.get(f"{REPORTS}/{child['id']}")))["4_2H"]["value"] == "Sensor recall done (sample)."


def test_b8_a_draft_value_never_carried_before_approval(trial):  # noqa: F811
    user, initial = trial["user"], _initial(trial)
    _ok(user.put(f"{REPORTS}/{initial}/fields/4_2H", json={"value": "Typed, never approved (sample)."}))
    _state(trial, initial, "ACCEPTED")  # no approved snapshot: nothing to carry
    child = _ok(_create(user, initial, FU))
    assert _fields(child)["4_2H"]["value"] is None


def test_b8_re_signing_supersedes_an_approved_unsent_follow_up(trial):  # noqa: F811
    user, initial = trial["user"], _initial(trial)
    _state(trial, initial, "ACCEPTED")
    child = _ok(_create(user, initial, FU))
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        row = db.get(ReportObligation, uuid.UUID(child["id"]))
        due = row.due_on
        db.add(
            ReportSnapshot(
                tenant_id=row.tenant_id,
                obligation_id=row.id,
                version=1,
                form_version=row.form_version,
                fields={"sections": []},
                content_fingerprint="0" * 64,
                state="APPROVED",
                requested_by="test",
                requested_at=now,
                approved_by="test-approver",
                approved_at=now,
                signed_record_id=uuid.uuid4(),
            )
        )
        row.state = "APPROVED"
        db.flush()
        other = (  # a later signed version stands in: any other assessment row of the tenant
            db.query(ComplaintMarketAssessment.id)
            .filter(
                ComplaintMarketAssessment.tenant_id == row.tenant_id, ComplaintMarketAssessment.id != row.assessment_id
            )
            .first()
        )
        signed = SimpleNamespace(id=other.id, report_type="OTHER", due_on=None, version=9)
        ctx = SimpleNamespace(user_id=uuid.uuid4(), correlation_id=None)
        reports.follow_signed(db, ctx, row, signed, now)
        db.commit()
        row = db.get(ReportObligation, row.id)
        assert row.state == "DRAFT" and row.due_on == due  # its own clock stays
        assert {item.state for item in db.query(ReportSnapshot).filter_by(obligation_id=row.id)} == {"SUPERSEDED"}


# ------------------------------------------------------------------------------------------------- B8 step 4 (D14)


def _record(user, report_id: str, reference: str = ""):
    return user.post(
        f"{REPORTS}/{report_id}/submissions",
        json={
            "route": "EU_NCA",
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "content_note": "Sent by e-mail to the authority (sample).",
            "no_differences": True,
            "authority_reference": reference,
        },
    )


def _audits(trial, action: str) -> list:  # noqa: F811
    from backend.app.db.models.foundation import AuditEvent

    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        return db.query(AuditEvent).filter_by(tenant_id=trial["tenant_id"], action=action).all()


def test_b8_recording_an_initial_creates_one_follow_up_due_on_1_2f(trial):  # noqa: F811
    user, initial = trial["user"], _initial(trial)
    _ok(user.put(f"{REPORTS}/{initial}/fields/1_2F", json={"value": "2026-12-15"}))
    _state(trial, initial, "APPROVED")
    before = len(_audits(trial, "REPORT_FOLLOW_UP_CREATED"))
    view = _ok(_record(user, initial, "ANSM-2026-0042"))
    (item,) = view["mir_chain"]["items"]
    assert (item["type"], item["state"], item["due_on"]) == (FU, "DRAFT", "2026-12-15")
    child = _ok(user.get(f"{REPORTS}/{item['id']}"))
    assert child["mir_chain"]["due_note"] == "Your date (1.2f): no fixed legal period"
    assert _fields(child)["1_1C"]["value"] == "ANSM-2026-0042"
    events = _audits(trial, "REPORT_FOLLOW_UP_CREATED")
    assert len(events) == before + 1 and events[-1].details["automatic"] is True


def test_b8_recording_a_follow_up_creates_the_next(trial):  # noqa: F811
    user, initial = trial["user"], _initial(trial)
    _state(trial, initial, "ACCEPTED")
    follow = _ok(_create(user, initial, FU))
    _ok(user.put(f"{REPORTS}/{follow['id']}/fields/1_2F", json={"value": "2027-01-20"}))
    _state(trial, follow["id"], "APPROVED")
    _ok(_record(user, follow["id"]))
    items = _ok(user.get(f"{REPORTS}/{initial}"))["mir_chain"]["items"]
    assert [(row["type"], row["due_on"]) for row in items] == [(FU, None), (FU, "2027-01-20")]


def test_b8_a_second_attempt_creates_no_second_draft(trial):  # noqa: F811
    user, initial = trial["user"], _initial(trial)
    _state(trial, initial, "APPROVED")
    _ok(_record(user, initial))
    _state(trial, initial, "APPROVED")  # a second attempt (e.g. after a rejected send)
    _ok(_record(user, initial))
    assert len(_ok(user.get(f"{REPORTS}/{initial}"))["mir_chain"]["items"]) == 1


def test_b8_nothing_is_created_after_a_combined_report_or_with_the_switch_off(trial, monkeypatch):  # noqa: F811
    user, initial = trial["user"], _initial(trial)
    _ok(user.put(f"{REPORTS}/{initial}/fields/1_2E", json={"value": "Combined initial and final"}))
    _state(trial, initial, "APPROVED")
    _ok(_record(user, initial))
    assert _ok(user.get(f"{REPORTS}/{initial}"))["mir_chain"]["items"] == []
    initial = _initial(trial)
    monkeypatch.setenv("MDARIX_B8_EU_MIR", "off")
    _state(trial, initial, "APPROVED")
    view = _ok(_record(user, initial))
    assert view["mir_chain"] is None and view["responses"] == []


def test_b8_a_not_reportable_re_sign_never_cancels_a_chain_draft(trial):  # noqa: F811
    user, initial = trial["user"], _initial(trial)
    _state(trial, initial, "ACCEPTED")
    child = _ok(_create(user, initial, FU))
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        row = db.get(ReportObligation, uuid.UUID(child["id"]))
        other = (
            db.query(ComplaintMarketAssessment.id)
            .filter(
                ComplaintMarketAssessment.tenant_id == row.tenant_id, ComplaintMarketAssessment.id != row.assessment_id
            )
            .first()
        )
        signed = SimpleNamespace(id=other.id, report_type=None, due_on=None, version=9, conclusion="NOT_REPORTABLE")
        reports.follow_signed(
            db, SimpleNamespace(user_id=uuid.uuid4(), correlation_id=None), row, signed, datetime.now(timezone.utc)
        )
        db.commit()
        assert db.get(ReportObligation, row.id).state == "DRAFT"
    current = SimpleNamespace(
        conclusion="NOT_REPORTABLE", override_reason="No serious deterioration (sample).", change_reason=None
    )
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        row = db.get(ReportObligation, uuid.UUID(child["id"]))
        offer = reports.mir_chain_view(row, [], current)["offer_final_non"]
    assert offer == {"type": FNR, "4_2B": "No serious deterioration (sample)."}


def test_b8_switching_the_draft_to_a_final_changes_what_is_mandatory(trial):  # noqa: F811
    user, initial = trial["user"], _initial(trial)
    _state(trial, initial, "ACCEPTED")
    child = _ok(_create(user, initial, FU))
    final = _ok(user.put(f"{REPORTS}/{child['id']}/fields/1_2E", json={"value": FR}))
    assert {"4_2A", "4_3_3A"} <= set(final["mandatory"]["missing"]) and "4_1C" not in final["mandatory"]["missing"]
    assert "4_1C" in _ok(user.put(f"{REPORTS}/{child['id']}/fields/1_2E", json={"value": FU}))["mandatory"]["missing"]


# ------------------------------------------------------------------------------------------------- B8 step 5


def test_b8_personal_fields_stay_blank_while_the_setting_is_off(trial):  # noqa: F811
    """B8-D9 (as B9-D9): no setting turns report-step personal data on yet, so patient and reporter boxes are refused
    and never stored."""
    user, initial = trial["user"], _initial(trial)
    for field in ("3_3B", "3_4B"):
        refused = user.put(f"{REPORTS}/{initial}/fields/{field}", json={"value": "Someone (sample)"})
        assert refused.status_code == 422 and _code(refused) == "PERSONAL_FIELD"
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        assert not {"3_3B", "3_4B"} & set(db.get(ReportObligation, uuid.UUID(initial)).entries or {})


def test_b8_the_sample_eu_report_names_ansm_and_leaves_1_2d_to_a_person(trial):  # noqa: F811
    values = _fields(_ok(trial["user"].get(f"{REPORTS}/{_initial(trial)}")))
    assert values["1_1A"]["value"].endswith("(ANSM)")  # the incident in France
    assert values["1_2D"]["value"] is None and "a hint only" in (values["1_2D"]["hint"] or "")
    assert values["1_2A"]["value"] is None and values["1_2A"]["editable"] is False


# ------------------------------------------------------------------------------------------------- B8 step 6

PARTIES = "/api/v1/regulatory-reference/responsible-parties"
PARTS = {
    "street": "1 Rue Exemple",
    "city": "Paris",
    "postcode": "75001",
    "country_code": "FR",
    "contact_first_name": "Ana",
    "contact_last_name": "Sample",
}


def test_b8_parts_entered_once_reach_every_report(trial):  # noqa: F811
    user, initial = trial["user"], _initial(trial)
    role = "AUTHORISED_REPRESENTATIVE"  # the sample's own parties are held in memory only: one is set here
    party = _ok(user.put(PARTIES, json={"market": "EU", "role": role, "organisation": "EU Rep (sample)"}))
    try:
        _ok(user.put(f"{REPORTS}/{initial}/once", json={"party_parts": {role: PARTS}}))
        saved = next(item for item in _ok(user.get(PARTIES))["parties"] if item["id"] == party["id"])
        assert {key: saved[key] for key in PARTS} == PARTS  # on the party: every EU report reads it from there
        assert saved["organisation"] == "EU Rep (sample)"  # nothing else changed
        again = user.put(f"{REPORTS}/{initial}/once", json={"party_parts": {role: {**PARTS, "city": "Lyon"}}})
        assert again.status_code == 409 and _code(again) == "PARTY_EXISTS"  # never overwritten
        missing = user.put(f"{REPORTS}/{initial}/once", json={"party_parts": {"SPONSOR": PARTS}})
        assert missing.status_code == 409 and _code(missing) == "NO_PARTY"
        assert user.put(f"{REPORTS}/{initial}/once", json={"udi_issuing_entity": "ACME"}).status_code == 422
        resent = _ok(user.put(PARTIES, json={"market": "EU", "role": role, "organisation": "EU Rep (sample)"}))
        assert resent["city"] == "Paris"  # a Settings save that does not send the parts keeps them
    finally:
        assert user.delete(f"{PARTIES}/{party['id']}").status_code == 204
