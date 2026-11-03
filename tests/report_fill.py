"""Fill a report's fields as a person does (0.10.81): a date field takes a date, a range a date, an IMDRF code field a
code from the code picker, a published list's field one of its codes, and the rest text."""

from __future__ import annotations

from datetime import date

from backend.app.db.session import SessionLocal

TEXT = "Test value (sample)"
LIST_VALUES = {"D2A": "FRN"}  # an FDA product code (infusion pump); GMDN and EMDN fields: their patterns


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
        return next(row.code for row in rows if reference.selectable(row.status) and row.parent_code)


def body(item: dict) -> dict:
    """The PUT body for one worksheet field (an item of a report detail's sections)."""
    kind = item.get("kind")
    if kind == "IMDRF_CODE":
        return {"codes": [_code(item["code_annex"])]}
    if kind in ("DATE", "DATE_RANGE"):
        return {"value": date.today().isoformat()}
    if kind == "LIST_CODE":
        return {"value": LIST_VALUES.get(item["id"], "Z120101")}  # an EMDN code; a GMDN field takes "12345" (fill)
    return {"value": TEXT}


def fill(client, reports: str, report_id: str, fields: list[str]):
    """Fill each field; the last answer (the report's detail)."""
    detail = client.get(f"{reports}/{report_id}").json()
    items = {item["id"]: item for section in detail["sections"] for item in section["fields"]}
    for field in fields:
        if field == "G8":
            continue  # follows the front page's manufacturer report number (MFR_REPORT), never typed
        response = client.put(f"{reports}/{report_id}/fields/{field}", json=body(items[field]))
        if response.status_code == 422 and items[field].get("kind") == "LIST_CODE":
            response = client.put(f"{reports}/{report_id}/fields/{field}", json={"value": "12345"})  # GMDN
        assert response.status_code == 200, (field, response.text)
        detail = response.json()
    return client.get(f"{reports}/{report_id}").json()
