"""B8 step 5: values MDARIX derives for an EU MIR, and the ones only a person gives. 1.1a from the incident country
(the Commission's vigilance contact points), 1.2a the day sent for approval, 1.2d asked with the signing day as a
hint only (B8-D2), 2.5 a hint from the product's registrations, the UDI issuing entity only from an unambiguous
format (B8-D11). No database."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.app.authority_reports import forms, worksheet
from tests.test_authority_reports_api import _empty_context

pytestmark = pytest.mark.unit


def _eu(context: dict, entries: dict | None = None) -> dict:
    sections = worksheet.build(forms.EU_MIR, context, entries or {}, {})
    return {item["id"]: item for section in sections for item in section["fields"]}


def test_b8_the_nca_follows_the_incident_country():
    assert worksheet.nca_for("France")["authority"].endswith("(ANSM)")
    assert worksheet.nca_for(" germany ")["code"] == "DE" and worksheet.nca_for("IE")["code"] == "IE"
    assert worksheet.nca_for("Northern Ireland") is None  # B8-D4: asked until MHRA confirms
    assert worksheet.nca_for("Switzerland") is None and worksheet.nca_for(None) is None  # not on the list: asked
    with worksheet.NCA_LIST.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len({row["code"] for row in rows}) == len(rows) == 32  # 27 EU states, IS, LI, NO, TR and XI
    context = _empty_context()
    context["record"]["country"] = "France"
    field = _eu(context)["1_1A"]
    assert field["value"].endswith("(ANSM)") and field["status"] == worksheet.FROM_RECORD
    context["record"]["country"] = "Switzerland"
    assert _eu(context)["1_1A"]["value"] is None


def test_b8_1_2a_is_the_day_sent_in_the_organisations_zone():
    field = next(item for item in forms.EU_MIR.fields() if item.id == "1_2A")
    assert field.source == "sent_day" and worksheet.derived_only(field.source)
    context = _empty_context()
    draft = _eu(context, {"1_2A": {"value": "2026-01-01"}})["1_2A"]
    assert draft["value"] is None and not draft["editable"]  # never typed; filled at Send for approval
    sections = worksheet.build(forms.EU_MIR, context, {}, {})
    assert "1_2A" not in worksheet.mandatory(sections)["missing"]
    context["sent_day"] = "2026-11-12"  # the router's organisation day (_org_day), as frozen at Send
    assert _eu(context)["1_2A"]["value"] == "2026-11-12"


def test_b8_1_2d_is_never_filled_without_a_person():
    context = _empty_context()
    context["seen"] = {"org_zone": "Asia/Kolkata"}
    context["current"] = SimpleNamespace(
        conclusion="REPORTABLE", report_type=None, signed_at=datetime(2026, 11, 10, 20, 0, tzinfo=timezone.utc)
    )
    field = _eu(context)["1_2D"]
    assert field["value"] is None and "2026-11-11" in field["hint"]  # 01:30 in India: the organisation's day
    typed = _eu(context, {"1_2D": {"value": "2026-11-09"}})["1_2D"]
    assert typed["value"] == "2026-11-09" and typed["hint"] is None
    assert (
        "hint" not in worksheet.frozen([{"code": "1_2", "title": "", "note": None, "fields": [field]}])[0]["fields"][0]
    )
    context["current"] = SimpleNamespace(
        conclusion="NOT_REPORTABLE", report_type=None, signed_at=datetime.now(timezone.utc)
    )
    assert _eu(context)["1_2D"]["hint"] is None


def test_b8_the_nca_list_is_pinned_to_the_commissions_file():
    folder = worksheet.NCA_LIST.parents[4] / "data" / "mir_forms" / "eu-nca-2026-09"
    source = json.loads((folder / "source.json").read_text(encoding="utf-8"))
    assert source["page"].startswith("https://health.ec.europa.eu/")
    for entry in source["files"]:
        assert hashlib.sha256((folder / entry["file"]).read_bytes()).hexdigest() == entry["sha256"]
        assert entry["source_url"].startswith("https://health.ec.europa.eu/document/download/")
    assert hashlib.sha256(worksheet.NCA_LIST.read_bytes()).hexdigest() == source["derived"]["sha256"]


def test_b8_2_5_market_distribution_is_a_hint_only():
    context = {**_empty_context(), "registered_markets": ["EU", "GB", "US"]}
    field = _eu(context)["2_5"]
    assert field["value"] is None and field["hint"].startswith("Registered in: EU, GB, US")


def test_b8_an_ambiguous_udi_never_gets_an_issuing_entity():
    assert worksheet.udi_issuing_entity("04012345678901") == "GS1"  # valid GTIN-14 check digit
    assert worksheet.udi_issuing_entity("04012345678902") is None  # wrong check digit
    assert worksheet.udi_issuing_entity("4012345678901") is None  # 13 digits
    assert worksheet.udi_issuing_entity("+H123PROD1") == "HIBCC"
    assert worksheet.udi_issuing_entity("=/A9999XYZ") == "ICCBBA"
    assert worksheet.udi_issuing_entity("PZN-12345678") is None  # IFA is never derived
    assert worksheet.udi_issuing_entity("") is None and worksheet.udi_issuing_entity(None) is None
