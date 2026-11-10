"""Fill a report's fields as a person does (0.10.81): a date field takes a date, a range a date, an IMDRF code field a
code from the code picker, a published list's field one of its codes, and the rest text."""

from __future__ import annotations

import uuid
from datetime import date

from backend.app.db.session import SessionLocal

TEXT = "Test value (sample)"
# The US contact office (G1) comes from the US responsible party with its e-mail (0.10.92, A5): set there, as a person
# does in Settings › Products, never typed on the report.
US_PARTY = {
    "market": "US",
    "role": "MANUFACTURER",
    "organisation": "Test Devices (sample)",
    "contact_email": "mdr@example.invalid",
}
LIST_VALUES = {"D2A": "FRN"}  # an FDA product code (infusion pump); GMDN and EMDN fields: their patterns
# A 3500A choice block takes one of FDA's choices, so the eMDR file can be made (0.10.96).
US_CHOICES = {"B1": "Product problem", "H1": "Malfunction"}


def _code(annex: str) -> str:
    """A selectable code of the annex in the newest loaded IMDRF release."""
    from backend.app import regulatory_reference as reference
    from tests.code_lists import ensure_loaded

    ensure_loaded()
    with SessionLocal() as db:
        release = reference.newest_release(db)
        from backend.app.db.models.regulatory_reference import ImdrfCode

        rows = (
            db.query(ImdrfCode)
            .filter(ImdrfCode.release == release, ImdrfCode.annex == annex)
            .order_by(ImdrfCode.code)
            .all()
        )
        # A code under a heading (annex B has no headings: any of its codes).
        codes = [row.code for row in rows if reference.selectable(row.status) and row.parent_code] or [
            row.code for row in rows if reference.selectable(row.status)
        ]
        # One FDA's mapping has a code for, so the eMDR file takes it (0.10.96: Send for approval checks the file).
        mapped = reference.fda_codes(db, codes)
        return next((code for code in codes if code in mapped), codes[0])


# What a US report needs beyond the form's mandatory fields for its eMDR file (FDA's required blocks, 0.10.96).
US_EMDR = ["D2A", "G1", "H6_CLINICAL", "H6_IMPACT", "H6_PROBLEM", "H6_COMPONENT", "H6_TYPE", "H6_FINDINGS"]
US_EMDR += ["H6_CONCLUSIONS"]


def body(item: dict) -> dict:
    """The PUT body for one worksheet field (an item of a report detail's sections)."""
    kind = item.get("kind")
    if kind == "IMDRF_CODE":
        return {"codes": [_code(item["code_annex"])]}
    if kind in ("DATE", "DATE_RANGE"):
        return {"value": date.today().isoformat()}
    if kind == "LIST_CODE":
        return {"value": LIST_VALUES.get(item["id"], "Z120101")}  # an EMDN code; a GMDN field takes "12345" (fill)
    if item["id"] == "MFR_REPORT":  # FDA's format, unique in the organization (0.10.96: never reused)
        return {"value": f"1234567-{date.today().year}-{uuid.uuid4().int % 60000 + 1:05d}"}
    return {"value": US_CHOICES.get(item["id"], TEXT)}


def fill(client, reports: str, report_id: str, fields: list[str]):
    """Fill each field; the last answer (the report's detail)."""
    detail = client.get(f"{reports}/{report_id}").json()
    items = {item["id"]: item for section in detail["sections"] for item in section["fields"]}
    for field in fields:
        if field == "G8":
            continue  # follows the front page's manufacturer report number (MFR_REPORT), never typed
        if field == "G1":
            party = client.put("/api/v1/regulatory-reference/responsible-parties", json=US_PARTY)
            assert party.status_code == 200, party.text
            if items[field]["status"] == "ENTERED":  # a typed value that differs from the party: cleared
                cleared = client.put(f"{reports}/{report_id}/fields/{field}", json={"clear": True})
                assert cleared.status_code == 200, cleared.text
            continue
        response = client.put(f"{reports}/{report_id}/fields/{field}", json=body(items[field]))
        if response.status_code == 422 and items[field].get("kind") == "LIST_CODE":
            response = client.put(f"{reports}/{report_id}/fields/{field}", json={"value": "12345"})  # GMDN
        assert response.status_code == 200, (field, response.text)
        detail = response.json()
    return client.get(f"{reports}/{report_id}").json()
