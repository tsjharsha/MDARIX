"""B6a Part C: reviews the customer signs (G1 audit trail review, G14 access review, G21 configuration snapshot) and
the one way they are signed (5.1). Scenario rows B6-28..B6-35, B6-45, B6-46.

Everything runs in two fresh organizations on the shared plane (deleted at the end); the audit trail of the G1 tests
is crafted in a past week of its own so the flags are exact.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from backend.app.db.data_plane import open_tenant_data_session
from backend.app.db.models.foundation import AuditEvent, AuthUser, ConnectorConfiguration, SignedApprovalRecord
from backend.app.db.models.stage2 import LoginThrottle
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system, bind_tenant
from backend.app.enterprise_audit import make_audit_event
from backend.app.signed_reviews import audit_review
from backend.app.signed_reviews.signing import fingerprint_of
from tests.test_reporting_capa_api import PASSWORD, REASON, SETTINGS, _client, _organization

URL = "/api/v1/reviews"
# A crafted week (Monday 5 Oct .. Sunday 11 Oct 2026) and a clean one (Monday 21 .. Friday 25 Sep 2026), both UTC.
WEEK = {"from": "2026-10-05", "to": "2026-10-11"}
CLEAN = {"from": "2026-09-21", "to": "2026-09-25"}


def _person(tenant_id, role: str):
    name = f"{role.title()} {uuid.uuid4().hex[:6]}"
    client = _client(tenant_id, role, name)
    with SessionLocal() as db:
        bind_system(db, "test: find the person")
        user_id = db.query(AuthUser.id).filter(AuthUser.display_name == name).scalar()
    return client, str(user_id)


@pytest.fixture(scope="module")
def org():
    from backend.app.trial.retention import purge_trial

    tenant_id, other_id = _organization("REVIEWS_A"), _organization("REVIEWS_B")
    people = {
        "reviewer": _person(tenant_id, "REVIEWER"),
        "leader": _person(tenant_id, "LEADER"),
        "admin": _person(tenant_id, "CUSTOMER_ADMIN"),
        "regulatory": _person(tenant_id, "REGULATORY_REVIEWER"),
        "viewer": _person(tenant_id, "VIEWER"),
        "other": _person(other_id, "LEADER"),
        "other_admin": _person(other_id, "CUSTOMER_ADMIN"),
    }
    try:
        yield {"tenant_id": tenant_id, "other_id": other_id, **people}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:b6a-signed-reviews-cleanup")
            purge_trial(db, other_id, "test:b6a-signed-reviews-cleanup")


def _at(day: str, hour: int, minute: int = 0, second: int = 0) -> datetime:
    start = datetime.fromisoformat(day).replace(hour=hour, minute=minute, tzinfo=timezone.utc)
    return start + timedelta(seconds=second)


def _write(tenant_id, events: list[dict]) -> None:
    with open_tenant_data_session(tenant_id) as db:
        for event in events:
            db.add(make_audit_event(tenant_id=tenant_id, entity_type=event.pop("entity_type", "Complaint"), **event))
        db.commit()


@pytest.fixture(scope="module")
def trail(org):
    """One event for each flag, by known people, inside WEEK; one clean edit inside CLEAN."""
    tenant_id, reviewer, admin = org["tenant_id"], org["reviewer"][1], org["admin"][1]
    regulatory = org["regulatory"][1]
    signed_case, plain_case, bulk_case = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    change = {"old_values": {"country": "IN"}, "new_values": {"country": "DE"}}
    events = [
        # A conclusion signed on Monday, then its complaint edited on Tuesday (with a reason): flag 2 only.
        {
            "actor_ref": regulatory,
            "action": "COMPLAINT_MARKET_CONCLUSION_SIGNED",
            "entity_id": signed_case,
            "created_at": _at("2026-10-05", 9),
        },
        {
            "actor_ref": regulatory,
            "action": "COMPLAINT_REPORTING_FACTS_SET",
            "entity_id": signed_case,
            "reason": "Customer corrected the country",
            "created_at": _at("2026-10-06", 10),
            **change,
        },
        # The reviewer edits without a reason on Wednesday: flag 1 (and the reviewer's own flag).
        {
            "actor_ref": reviewer,
            "action": "COMPLAINT_REPORTING_FACTS_SET",
            "entity_id": plain_case,
            "created_at": _at("2026-10-07", 11),
            **change,
        },
        # The customer administrator changes data on Thursday, with a reason: flag 3.
        {
            "actor_ref": admin,
            "action": "OVERSIGHT_SETTINGS_CHANGED",
            "entity_type": "OversightSettings",
            "entity_id": uuid.uuid4(),
            "reason": "New escalation role",
            "created_at": _at("2026-10-08", 12),
            **change,
        },
        # On Saturday (outside the Monday-Friday calendar) the regulatory reviewer edits with a reason: flag 4b.
        {
            "actor_ref": regulatory,
            "action": "COMPLAINT_REPORTING_FACTS_SET",
            "entity_id": uuid.uuid4(),
            "reason": "Weekend correction",
            "created_at": _at("2026-10-10", 10),
            **change,
        },
    ]
    # 51 edits by one person within ten minutes on Friday: flag 4a.
    events += [
        {
            "actor_ref": regulatory,
            "action": "COMPLAINT_REPORTING_FACTS_SET",
            "entity_id": bulk_case,
            "reason": "Bulk fix",
            "created_at": _at("2026-10-09", 14, second=10 * i),
            **change,
        }
        for i in range(51)
    ]
    # Ten failed sign-ins for one account on Friday: flag 5.
    events += [
        {
            "actor_ref": regulatory,
            "action": "SIGN_IN_FAILED",
            "entity_type": "AuthUser",
            "entity_id": uuid.UUID(regulatory),
            "created_at": _at("2026-10-09", 8, i),
        }
        for i in range(10)
    ]
    # The clean week: one weekday edit, with a reason, of a record never signed, by a non-administrator.
    events.append(
        {
            "actor_ref": regulatory,
            "action": "COMPLAINT_REPORTING_FACTS_SET",
            "entity_id": uuid.uuid4(),
            "reason": "Clean edit",
            "created_at": _at("2026-09-22", 10),
            **change,
        }
    )
    _write(tenant_id, events)
    return {"signed_case": str(signed_case), "plain_case": str(plain_case)}


def _flags(body: dict) -> dict[str, dict]:
    return {flag["code"]: flag for flag in body["flags"]}


def test_each_flag_is_found_on_a_crafted_trail_and_absent_on_a_clean_one(org, trail):  # B6-28
    found = org["reviewer"][0].get(f"{URL}/audit-trail", params=WEEK)
    assert found.status_code == 200, found.text
    flags = _flags(found.json())
    regulatory, reviewer, admin = org["regulatory"][1], org["reviewer"][1], org["admin"][1]
    assert flags["EDIT_WITHOUT_REASON"]["count"] == 1 and flags["EDIT_WITHOUT_REASON"]["actors"] == [reviewer]
    after = flags["EDIT_AFTER_SIGNATURE"]
    assert after["count"] == 1 and after["events"][0]["entity_id"] == trail["signed_case"]
    assert after["events"][0]["reason"] == "Customer corrected the country"
    assert flags["ADMIN_CHANGE"]["count"] == 1 and flags["ADMIN_CHANGE"]["actors"] == [admin]
    assert flags["BULK_CHANGE"]["count"] == 51 and flags["BULK_CHANGE"]["actors"] == [regulatory]
    assert flags["OUTSIDE_CALENDAR"]["count"] == 1
    assert flags["FAILED_SIGN_IN_SPIKE"]["count"] == 10
    assert found.json()["chain_valid"] is True and found.json()["own_flags"] == ["EDIT_WITHOUT_REASON"]
    # Old and new values are shown with every event.
    assert after["events"][0]["old_values"] == {"country": "IN"} and after["events"][0]["new_values"]["country"] == "DE"
    clean = org["reviewer"][0].get(f"{URL}/audit-trail", params=CLEAN).json()
    assert all(flag["count"] == 0 for flag in clean["flags"]) and clean["edits"] == 1
    # Nine failed sign-ins in a day are not a spike; a 10-minute window with exactly 50 edits is not bulk.
    assert (
        audit_review._bulk(
            [{"id": str(i), "actor": "a", "at": _at("2026-10-09", 14, second=10 * i).isoformat()} for i in range(50)]
        )
        == set()
    )
    # All events of the period, paged, with old and new values.
    page = org["reviewer"][0].get(f"{URL}/audit-trail/events", params={**WEEK, "limit": 20, "offset": 60}).json()
    assert page["total"] == 66 and len(page["events"]) == 6


def test_a_broken_chain_is_shown(org, trail):
    with SessionLocal() as db:
        bind_tenant(db, org["tenant_id"])
        try:
            event = (
                db.query(AuditEvent)
                .filter(AuditEvent.tenant_id == org["tenant_id"], AuditEvent.action == "SIGN_IN_FAILED")
                .first()
            )
            db.execute(text("ALTER TABLE audit_events DISABLE TRIGGER audit_events_immutable"))
            db.execute(text("UPDATE audit_events SET reason = 'edited later' WHERE id = :id"), {"id": event.id})
            content = audit_review.build(db, db, org["tenant_id"], date(2026, 10, 5), date(2026, 10, 11))
            assert content["chain_valid"] is False and content["planes"][0]["first_broken_seq"] is not None
        finally:
            db.rollback()


def test_a_dedicated_plane_is_read_beside_the_control_database(org, trail):
    """Two sessions (here on one database) are both read: on a dedicated plane the second is the plane's own."""
    with SessionLocal() as control, SessionLocal() as plane:
        bind_tenant(control, org["tenant_id"])
        bind_tenant(plane, org["tenant_id"])
        one = audit_review.build(control, control, org["tenant_id"], date(2026, 10, 5), date(2026, 10, 11))
        two = audit_review.build(control, plane, org["tenant_id"], date(2026, 10, 5), date(2026, 10, 11))
    assert [read["plane"] for read in one["planes"]] == ["control"]
    assert [read["plane"] for read in two["planes"]] == ["control", "data"] and two["events"] == 2 * one["events"]
    # What is signed keeps a plane's events as a reference and a hash, never their values (review finding 1).
    kept = audit_review.for_signing(two)
    lines = [line for flag in kept["flags"] for line in flag["events"]]
    data = [line for line in lines if line["plane"] == "data"]
    assert data and all("old_values" not in line and len(line["values_sha256"]) == 64 for line in data)
    assert all(
        line["old_values"] is not None
        for line in lines
        if line["plane"] == "control" and line["action"] != "SIGN_IN_FAILED"
    )


def _sign(client, path: str, **extra):
    return client.post(f"{URL}/{path}", json={"findings": "Reviewed; see flags", "password": PASSWORD, **extra})


def test_who_signs_the_audit_trail_review_and_what_is_kept(org, trail):  # B6-30, B6-31, B6-45
    admin, leader, viewer = org["admin"][0], org["leader"][0], org["viewer"][0]
    # A customer administrator reads but never signs alone (D4); a viewer neither reads nor signs.
    assert admin.get(f"{URL}/audit-trail", params=WEEK).status_code == 200
    refused = _sign(admin, "audit-trail/sign", period_from=WEEK["from"], period_to=WEEK["to"])
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "REVIEW_SIGNER_REQUIRED"
    assert viewer.get(f"{URL}/audit-trail", params=WEEK).status_code == 403
    # A wrong password is refused, audited and counted on the signing throttle.
    wrong = leader.post(f"{URL}/audit-trail/sign", json={"findings": "x", "password": "wrong", **_period(WEEK)})
    assert wrong.status_code == 403 and wrong.json()["detail"]["code"] == "INVALID_REAUTHENTICATION"
    with SessionLocal() as db:
        bind_system(db, "test: refusals")
        assert (
            db.query(AuditEvent)
            .filter(
                AuditEvent.tenant_id == org["tenant_id"],
                AuditEvent.action == "SIGNATURE_REAUTHENTICATION_FAILED",
                AuditEvent.entity_type == "AuditTrailReview",
            )
            .count()
            == 1
        )
        throttle = db.query(LoginThrottle).filter(LoginThrottle.identifier == f"sign:{org['leader'][1]}").one()
        assert throttle.failure_count == 1
    signed = _sign(leader, "audit-trail/sign", **_period(WEEK))
    assert signed.status_code == 200, signed.text
    assert signed.json()["needs_second_reviewer"] is False
    review_id = signed.json()["review_id"]
    read = leader.get(f"{URL}/signed/{review_id}").json()
    assert read["intact"] is True and read["content"]["period"] == {"from": WEEK["from"], "to": WEEK["to"]}
    with SessionLocal() as db:
        bind_system(db, "test: the signature")
        record = db.query(SignedApprovalRecord).filter(SignedApprovalRecord.object_id == uuid.UUID(review_id)).one()
        event = (
            db.query(AuditEvent)
            .filter(AuditEvent.entity_id == uuid.UUID(review_id), AuditEvent.action == "AUDIT_TRAIL_REVIEW_SIGNED")
            .one()
        )
        assert (
            record.content_fingerprint
            == fingerprint_of(event.details["material"])
            == read["signatures"][0]["fingerprint"]
        )
        assert record.signer_role == "LEADER" and record.status == "SIGNED"
    # Later events change nothing that was signed; nothing can edit a review (no write route exists for one).
    _write(
        org["tenant_id"], [{"actor_ref": org["admin"][1], "action": "LATE_EVENT", "created_at": _at("2026-10-07", 9)}]
    )
    again = leader.get(f"{URL}/signed/{review_id}").json()
    assert again["content"] == read["content"] and again["intact"] is True
    for method in ("put", "patch", "delete"):
        assert getattr(leader, method)(f"{URL}/signed/{review_id}").status_code == 405
    # A changed signature is caught (review finding 6), then put back.
    with SessionLocal() as db:
        bind_system(db, "test: tamper with the signature")
        db.execute(
            text("UPDATE signed_approval_records SET content_fingerprint = :bad WHERE object_id = :id"),
            {"bad": "0" * 64, "id": uuid.UUID(review_id)},
        )
        db.commit()
        try:
            assert leader.get(f"{URL}/signed/{review_id}").json()["intact"] is False
        finally:
            db.execute(
                text("UPDATE signed_approval_records SET content_fingerprint = :good WHERE object_id = :id"),
                {"good": record.content_fingerprint, "id": uuid.UUID(review_id)},
            )
            db.commit()
    # A correction names an earlier review of this organization; MDARIX staff never read the reviews.
    unknown = _sign(leader, "audit-trail/sign", corrects=str(uuid.uuid4()), **_period(WEEK))
    assert unknown.status_code == 404
    assert _person(org["tenant_id"], "PLATFORM_ADMIN")[0].get(f"{URL}/audit-trail").status_code == 403
    # Downloads: a PDF from the stored content and the JSON; both audited.
    pdf = leader.get(f"{URL}/signed/{review_id}/download", params={"format": "pdf"})
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert (
        json.loads(leader.get(f"{URL}/signed/{review_id}/download", params={"format": "json"}).content)["review_id"]
        == review_id
    )
    # Another organization never sees it (404), nor its flags.
    assert org["other"][0].get(f"{URL}/signed/{review_id}").status_code == 404
    theirs = org["other"][0].get(f"{URL}/audit-trail", params=WEEK).json()
    assert all(flag["count"] == 0 for flag in theirs["flags"])
    assert org["other"][0].get(f"{URL}/audit-trail/signed").json() == []


def _period(week: dict) -> dict:
    return {"period_from": week["from"], "period_to": week["to"]}


def test_own_flags_need_a_second_reviewer(org, trail):  # B6-29
    reviewer, leader = org["reviewer"][0], org["leader"][0]
    signed = _sign(reviewer, "audit-trail/sign", **_period(WEEK))
    assert signed.status_code == 200, signed.text
    assert signed.json()["needs_second_reviewer"] is True
    review_id = signed.json()["review_id"]
    awaiting = leader.get(f"{URL}/audit-trail", params=WEEK).json()["awaiting_confirmation"]
    assert review_id in [item["review_id"] for item in awaiting]
    own = _sign(reviewer, f"audit-trail/{review_id}/confirm")
    assert own.status_code == 403 and own.json()["detail"]["code"] == "SECOND_REVIEWER_REQUIRED"
    assert _sign(org["admin"][0], f"audit-trail/{review_id}/confirm").status_code == 403
    confirmed = _sign(leader, f"audit-trail/{review_id}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    read = leader.get(f"{URL}/signed/{review_id}").json()
    assert len(read["signatures"]) == 2 and read["intact"] is True
    assert _sign(leader, f"audit-trail/{review_id}/confirm").status_code == 409
    assert review_id not in [i["review_id"] for i in leader.get(f"{URL}/audit-trail").json()["awaiting_confirmation"]]


def test_the_access_review(org):  # B6-32, B6-33, B6-45
    admin, leader = org["admin"][0], org["leader"][0]
    admin_id = org["admin"][1]
    review = admin.get(f"{URL}/access")
    assert review.status_code == 200, review.text
    rows = {row["user_id"]: row for row in review.json()["rows"]}
    assert set(rows) >= {org[key][1] for key in ("reviewer", "leader", "admin", "regulatory", "viewer")}
    assert org["other"][1] not in rows and review.json()["administrators"] == 1
    assert org["viewer"][0].get(f"{URL}/access").status_code == 403
    # Signing before every row is marked is refused.
    early = _sign(admin, "access/sign")
    assert early.status_code == 409 and early.json()["detail"]["code"] == "ROWS_UNMARKED"
    # The administrator never marks their own row; a Leader marks it only because there is one administrator, and
    # never anyone else's row.
    own = admin.post(f"{URL}/access/marks", json={"user_id": admin_id, "mark": "KEEP"})
    assert own.status_code == 403 and own.json()["detail"]["code"] == "OWN_ROW"
    assert leader.post(f"{URL}/access/marks", json={"user_id": org["viewer"][1], "mark": "KEEP"}).status_code == 403
    assert leader.post(f"{URL}/access/marks", json={"user_id": admin_id, "mark": "KEEP"}).status_code == 200
    # Another organization's person cannot be marked from here.
    assert admin.post(f"{URL}/access/marks", json={"user_id": org["other"][1], "mark": "KEEP"}).status_code == 404
    for user_id in rows:
        if user_id == admin_id:
            continue
        mark = "REMOVE" if user_id == org["viewer"][1] else "KEEP"
        done = admin.post(f"{URL}/access/marks", json={"user_id": user_id, "mark": mark, "note": "Quarterly"})
        assert done.status_code == 200, done.text
    # Remove is done with the existing route, audited as today.
    removed = admin.patch(f"/api/v1/admin/identity/users/{org['viewer'][1]}/status", json={"status": "SUSPENDED"})
    assert removed.status_code == 200, removed.text
    marked = admin.get(f"{URL}/access").json()
    assert marked["unmarked"] == 0
    assert _sign(leader, "access/sign").status_code == 403  # a customer administrator signs
    signed = _sign(admin, "access/sign")
    assert signed.status_code == 200, signed.text
    read = admin.get(f"{URL}/signed/{signed.json()['review_id']}").json()
    content_rows = {row["user_id"]: row for row in read["content"]["rows"]}
    assert content_rows[admin_id]["mark"]["by"] == org["leader"][1]
    assert org["viewer"][1] not in content_rows  # no longer active once removed
    with SessionLocal() as db:
        bind_system(db, "test: removal audited")
        assert (
            db.query(AuditEvent)
            .filter(AuditEvent.entity_id == uuid.UUID(org["viewer"][1]), AuditEvent.action == "USER_STATUS_CHANGED")
            .count()
            == 1
        )
    # A new period starts unmarked; another organization sees none of this.
    assert admin.get(f"{URL}/access").json()["unmarked"] == len(content_rows)
    assert org["other_admin"][0].get(f"{URL}/signed/{signed.json()['review_id']}").status_code == 404


def test_the_configuration_snapshot_and_comparison(org):  # B6-34, B6-35
    admin, leader = org["admin"][0], org["leader"][0]
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_tenant(db, org["tenant_id"])
        db.add(
            ConnectorConfiguration(
                id=uuid.uuid4(),
                tenant_id=org["tenant_id"],
                code="QMS-SNAPSHOT",
                connector_type="REST",
                configuration={
                    "endpoint": "https://user:SNAPSHOT_URL_PASSWORD@qms.example.invalid/api?key=SNAPSHOT_URL_KEY",
                    "credential_ref": "SNAPSHOT_SECRET_REF",
                    "tenant_key": "SNAPSHOT_TENANT_KEY",
                    "api_key": "SNAPSHOT_RAW_KEY",
                },
                version="1",
                status="ACTIVE",
                credential_encrypted="SNAPSHOT_ENCRYPTED_KEY",
                credential_hint="KEY9",
                credential_set_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
    snapshot = admin.get(f"{URL}/configuration")
    assert snapshot.status_code == 200, snapshot.text
    body = json.dumps(snapshot.json())
    for secret in (
        "SNAPSHOT_SECRET_REF",
        "SNAPSHOT_TENANT_KEY",
        "SNAPSHOT_RAW_KEY",
        "SNAPSHOT_ENCRYPTED_KEY",
        "KEY9",
        "SNAPSHOT_URL_PASSWORD",
        "SNAPSHOT_URL_KEY",
    ):
        assert secret not in body
    connector = next(item for item in snapshot.json()["connectors"] if item["code"] == "QMS-SNAPSHOT")
    assert connector["endpoint"] == "https://qms.example.invalid/api" and connector["key_set"] is True
    assert "MDARIX_B6_REVIEWS" in snapshot.json()["switches"] and snapshot.json()["users"]
    assert org["regulatory"][0].get(f"{URL}/configuration").status_code == 403
    signed = _sign(admin, "configuration/sign")
    assert signed.status_code == 200, signed.text
    first = signed.json()["review_id"]
    kept = admin.get(f"{URL}/signed/{first}").json()
    # The India window changes, with its reason.
    settings = org["regulatory"][0].get(SETTINGS).json()
    saved = org["regulatory"][0].put(
        SETTINGS, json={"windows": settings["templates"][:1], "lookback_days": 200, "reason": REASON}
    )
    assert saved.status_code == 200, saved.text
    compared = leader.get(f"{URL}/configuration/compare", params={"before": first, "after": "now"})
    assert compared.status_code == 200, compared.text
    items = {change["item"]: change for change in compared.json()["changes"]}
    assert items["reporting.lookback_days"]["after"] == 200
    why = items["reporting.lookback_days"]["events"]
    assert why and why[0]["why"] == REASON and why[0]["who"] == org["regulatory"][1]
    # The signed snapshot is unchanged by the later edit.
    assert admin.get(f"{URL}/signed/{first}").json() == kept
    second = _sign(leader, "configuration/sign")
    assert second.status_code == 200, second.text
    between = admin.get(f"{URL}/configuration/compare", params={"before": first, "after": second.json()["review_id"]})
    assert "reporting.lookback_days" in {change["item"] for change in between.json()["changes"]}
    assert org["other_admin"][0].get(f"{URL}/configuration/compare", params={"before": first}).status_code == 404


def test_a_review_signature_needs_the_authenticator_code_when_signatures_need_mfa(org, monkeypatch):  # B6-30
    import time

    from auth import totp

    leader = org["leader"][0]
    monkeypatch.setenv("MDARIX_REQUIRE_MFA_FOR_SIGNATURES", "true")
    not_set_up = _sign(leader, "configuration/sign")
    assert not_set_up.status_code == 403 and not_set_up.json()["detail"]["code"] == "SIGNATURE_MFA_NOT_SET_UP"
    secret = leader.post("/api/v1/auth/mfa/enroll").json()["secret"]
    enrolled = leader.post("/api/v1/auth/mfa/verify-enrollment", json={"code": totp.current_code(secret)})
    assert enrolled.status_code == 200, enrolled.text
    wrong = _sign(leader, "configuration/sign", mfa_code="000000")
    assert wrong.status_code == 403 and wrong.json()["detail"]["code"] == "SIGNATURE_CODE_INVALID"
    code = totp.code_at(secret, int(time.time() // 30) + 1)
    assert _sign(leader, "configuration/sign", mfa_code=code).status_code == 200


def test_the_switch_off_on_off(org, monkeypatch):  # B6-46
    leader = org["leader"][0]
    signed = leader.get(f"{URL}/audit-trail/signed").json()
    assert signed
    monkeypatch.setenv("MDARIX_B6_REVIEWS", "off")
    assert leader.get(f"{URL}/audit-trail").status_code == 404
    assert leader.get(f"{URL}/signed/{signed[0]['review_id']}").status_code == 404
    # The signed review stays in the audit trail (and its export).
    with SessionLocal() as db:
        bind_system(db, "test: signed review kept")
        assert db.query(AuditEvent).filter(AuditEvent.entity_id == uuid.UUID(signed[0]["review_id"])).count() >= 1
    monkeypatch.setenv("MDARIX_B6_REVIEWS", "on")
    assert leader.get(f"{URL}/signed/{signed[0]['review_id']}").json()["intact"] is True
    monkeypatch.setenv("MDARIX_B6_REVIEWS", "off")
    assert leader.get(f"{URL}/access").status_code == 404
