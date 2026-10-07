"""Real complaint files: import the rows that pass and get the rest back, or mask personal data instead of refusing.

By default one problem row (or one value that looks like personal data) still stops the whole file. The uploader may
choose ``on_problems=skip`` (the rows that pass are imported; the others come back as a rejects file with each row's
problems, never stored) and ``personal_data=mask`` (personal data in free text is replaced by placeholders such as
[PERSON] and [PHONE]); a problem of the file itself always stops it all.
"""

import csv
import io
import uuid

import pytest
from sqlalchemy import text

from backend.app.db.session import engine
from tests.test_business_permissions import _client_with_role
from tests.test_data_import_path import _cleanup

CHECK = "/api/v1/data/import/complaints/check"
IMPORT = "/api/v1/data/import/complaints"


@pytest.fixture(autouse=True, scope="module")
def _clean():
    _cleanup()
    yield
    _cleanup()


@pytest.fixture(scope="module")
def investigator():
    return _client_with_role("Investigator")


@pytest.fixture
def product(investigator):
    product_id = f"OPT-{uuid.uuid4().hex[:6].upper()}"
    loaded = investigator.post("/api/v1/data/import/products", content=f"product_id,product_name\n{product_id},Pump\n")
    assert loaded.status_code == 200, loaded.text
    return product_id


def _complaints(product_id: str, *rows: tuple[str, str]) -> tuple[str, list[str]]:
    ids = [f"C-{product_id}-{index}" for index in range(len(rows))]
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["complaint_id", "product_id", "description"])
    for identifier, (product, description) in zip(ids, rows):
        writer.writerow([identifier, product, description])
    return out.getvalue(), ids


def _stored(identifiers: list[str]) -> dict[str, str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT complaint_identifier, description FROM complaints WHERE complaint_identifier = ANY(:ids)"),
            {"ids": identifiers},
        )
        return {identifier: description for identifier, description in rows}


def test_by_default_one_personal_value_still_stops_the_whole_file(investigator, product):
    body, ids = _complaints(
        product, (product, "Occlusion alarm during infusion"), (product, "Caller left 555-123-4567 for follow-up")
    )
    check = investigator.post(CHECK, content=body).json()
    assert not check["ready"] and check["rows_to_import"] == 0 and "rejects_csv" not in check
    assert "or choose to mask it" in check["issues"][0]["message"]
    assert investigator.post(IMPORT, content=body).status_code == 422
    assert _stored(ids) == {}


def test_skip_imports_the_rows_that_pass_and_returns_the_rest(investigator, product):
    body, ids = _complaints(
        product,
        (product, "Occlusion alarm during infusion"),
        (product, "Caller left 555-123-4567 for follow-up"),
        ("NOT-LOADED", "Pump stopped"),
        (product, "Battery drained within two hours"),
    )
    check = investigator.post(CHECK, params={"on_problems": "skip"}, content=body).json()
    assert check["ready"] and check["rows"] == 4 and check["rows_to_import"] == 2 and check["rejected_rows"] == 2
    assert len(check["preview"]) == 2

    imported = investigator.post(IMPORT, params={"on_problems": "skip"}, content=body)
    assert imported.status_code == 200, imported.text
    result = imported.json()
    assert result["created"] == 2 and result["rejected_rows"] == 2
    assert set(_stored(ids)) == {ids[0], ids[3]}

    rejects = list(csv.DictReader(io.StringIO(result["rejects_csv"])))
    assert [row["complaint_id"] for row in rejects] == [ids[1], ids[2]]
    assert rejects[0]["description"] == "Caller left 555-123-4567 for follow-up"  # as sent, to fix and send again
    assert "Row 3:" in rejects[0]["problems"] and "phone number" in rejects[0]["problems"]
    assert "is not in your workspace" in rejects[1]["problems"]

    # The audit keeps the counts, never the rejected rows themselves.
    with engine.connect() as connection:
        details = connection.execute(
            text(
                "SELECT details FROM audit_events WHERE action = 'DATA_IMPORTED' AND details->>'entity' = 'complaints' "
                "ORDER BY created_at DESC LIMIT 1"
            )
        ).scalar()
    assert details["rejected_rows"] == 2 and "rejects_csv" not in details


def test_mask_replaces_personal_data_and_keeps_the_investigation_facts(investigator, product):
    body, ids = _complaints(
        product,
        (product, "Dr. Alan Grant called from 555-123-4567: occlusion alarm during infusion"),
        (product, "Patient John Smith, MRN 004512, DOB 1961-04-02, reported the pump stopped"),
        (product, "Battery drained within two hours"),
    )
    check = investigator.post(CHECK, params={"personal_data": "mask"}, content=body).json()
    assert check["ready"] and check["masked_values"] == 2 and check["rows_to_import"] == 3
    assert "[PHONE]" in check["preview"][0]["description"]

    result = investigator.post(IMPORT, params={"personal_data": "mask"}, content=body).json()
    assert result["created"] == 3 and result["masked_values"] == 2
    stored = _stored(ids)
    assert stored[ids[0]] == "[PERSON] called from [PHONE]: occlusion alarm during infusion"
    for secret in ("Alan Grant", "555-123-4567", "John Smith", "004512", "1961-04-02"):
        assert all(secret not in description for description in stored.values()), secret
    assert "reported the pump stopped" in stored[ids[1]]
    assert stored[ids[2]] == "Battery drained within two hours"


def test_mask_and_skip_together_set_aside_only_the_rows_with_other_problems(investigator, product):
    body, ids = _complaints(
        product, (product, "Contact jane.doe@hospital.org about the alarm"), (product, '=HYPERLINK("http://x")')
    )
    result = investigator.post(IMPORT, params={"on_problems": "skip", "personal_data": "mask"}, content=body).json()
    assert result["created"] == 1 and result["masked_values"] == 1 and result["rejected_rows"] == 1
    assert _stored(ids) == {ids[0]: "Contact [EMAIL] about the alarm"}
    rejected = list(csv.DictReader(io.StringIO(result["rejects_csv"])))[0]
    # A formula sent back in the rejects file is quoted, so a spreadsheet shows it instead of running it.
    assert rejected["description"] == '\'=HYPERLINK("http://x")'


def test_a_problem_of_the_file_itself_stops_everything_even_when_skipping(investigator, product):
    body = f"complaint_id,product_id,description,notes\nC-{product}-X,{product},Alarm,extra\n"
    check = investigator.post(CHECK, params={"on_problems": "skip"}, content=body).json()
    assert not check["ready"] and check["rows_to_import"] == 0 and "rejects_csv" not in check
    assert investigator.post(IMPORT, params={"on_problems": "skip"}, content=body).status_code == 422
    assert _stored([f"C-{product}-X"]) == {}


def test_a_file_where_every_row_has_a_problem_imports_nothing(investigator, product):
    body, ids = _complaints(product, ("NOT-LOADED", "Pump stopped"))
    check = investigator.post(CHECK, params={"on_problems": "skip"}, content=body).json()
    assert not check["ready"] and check["rejected_rows"] == 1 and check["rejects_csv"]
    assert investigator.post(IMPORT, params={"on_problems": "skip"}, content=body).status_code == 422
    assert _stored(ids) == {}


@pytest.mark.parametrize("params", [{"on_problems": "ignore"}, {"personal_data": "keep"}])
def test_unknown_options_are_refused(investigator, product, params):
    body, _ = _complaints(product, (product, "Alarm"))
    refused = investigator.post(CHECK, params=params, content=body)
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "INVALID_IMPORT_OPTION"
