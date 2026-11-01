"""G2a: registrations, identity and responsible parties are checked before they are stored; an IMDRF annex loads
only from a clean file; a person may not review a mapping they proposed. Pure functions and stand-ins: no database
(the stored paths and the per-organization isolation need PostgreSQL)."""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from backend.app import regulatory_reference as reference
from backend.app.db.models.regulatory_reference import ImdrfCodeMapping
from scripts.load_imdrf_annex import dropped_codes, parse_annex

pytestmark = pytest.mark.unit


def _code(call) -> str:
    with pytest.raises(HTTPException) as caught:
        call()
    return caught.value.detail["code"]


def test_registration_rules_per_market():
    us = {"market": "us", "registration_type": "510k", "registration_number": "K123456", "product_code": "FRN"}
    assert reference.check_registration(us)["market"] == "US"
    assert _code(lambda: reference.check_registration({**us, "product_code": ""})) == "PRODUCT_CODE_REQUIRED"
    assert _code(lambda: reference.check_registration({**us, "registration_type": "CE"})) == "REGISTRATION_TYPE_UNKNOWN"
    assert _code(lambda: reference.check_registration({**us, "market": "XX"})) == "MARKET_UNKNOWN"
    eu = {"market": "EU", "registration_type": "CE", "registration_number": "SRN-1"}
    assert _code(lambda: reference.check_registration(eu)) == "NOTIFIED_BODY_REQUIRED"
    assert reference.check_registration({**eu, "body_name": "BSI", "body_number": "2797"})["body_number"] == "2797"


def test_identity_and_party_checks():
    assert reference.check_identity({"udi_di": " 0123 ", "gmdn_code": "35173"})["udi_di"] == "0123"
    assert _code(lambda: reference.check_identity({"gmdn_code": "35A"})) == "GMDN_CODE_INVALID"
    party = {"market": "GB", "role": "uk_responsible_person", "organisation": "Acme UK Ltd"}
    assert reference.check_party(party)["role"] == "UK_RESPONSIBLE_PERSON"
    assert _code(lambda: reference.check_party({**party, "role": "AGENT"})) == "ROLE_UNKNOWN"
    assert _code(lambda: reference.check_party({**party, "contact_email": "nope"})) == "EMAIL_INVALID"


def test_annex_file_is_checked_whole():
    good = "code,term,definition,parent_code\nA01,Material problem,,\nA0101,Crack,Split in material,A01\n"
    codes, problems = parse_annex("﻿" + good)
    assert problems == [] and [item["code"] for item in codes] == ["A01", "A0101"]
    _, problems = parse_annex("code,term,parent_code\nA01,One,\nA01,Again,\nA02,,A99\n")
    assert "line 3: A01: appears twice" in problems
    assert "line 4: A02: no term" in problems
    assert "A02: parent A99 is not in the file" in problems
    assert parse_annex("id,name\n1,x\n")[1] == ["missing column: code", "missing column: term"]


class _Query:
    def __init__(self, item):
        self.item = item

    def filter(self, *_):
        return self

    def with_for_update(self):
        return self

    def one_or_none(self):
        return self.item


class _Session:
    def __init__(self, item):
        self.item = item

    def query(self, _model):
        return _Query(self.item)


def _proposed(by: str) -> ImdrfCodeMapping:
    return ImdrfCodeMapping(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        customer_system="problem_code",
        customer_code="PC-7",
        release="2026",
        annex="A",
        imdrf_code="A0101",
        status="PROPOSED",
        proposed_by=by,
        proposed_at=datetime.now(timezone.utc),
    )


def test_mapping_review_needs_another_person_and_a_reason_to_reject():
    item = _proposed("alice")
    session = _Session(item)
    assert _code(lambda: reference.review_mapping(session, item.tenant_id, item.id, True, None, "alice")) == (
        "MAPPING_SELF_REVIEW"
    )
    assert _code(lambda: reference.review_mapping(session, item.tenant_id, item.id, False, " ", "bob")) == (
        "REASON_REQUIRED"
    )
    approved = reference.review_mapping(session, item.tenant_id, item.id, True, None, "bob")
    assert (approved["status"], approved["reviewed_by"]) == ("APPROVED", "bob")
    assert _code(lambda: reference.review_mapping(session, item.tenant_id, item.id, True, None, "carol")) == (
        "MAPPING_DECIDED"
    )


def test_a_reload_may_not_drop_a_loaded_code():
    codes, _ = parse_annex("code,term\nA01,One\nA03,Three\n")
    assert dropped_codes({"A01", "A02"}, codes) == ["A02"]
    assert dropped_codes({"A01"}, codes) == []


def test_numbers_sent_as_numbers_are_read_as_text():
    us = {"market": "US", "registration_type": "PMA", "registration_number": 510123, "product_code": "FRN"}
    assert reference.check_registration(us)["registration_number"] == "510123"
    assert reference.check_identity({"gmdn_code": 35173})["gmdn_code"] == "35173"
