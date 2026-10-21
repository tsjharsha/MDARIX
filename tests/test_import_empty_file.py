"""DEV-018: checking an import file without a single data row (empty, or a header alone) is refused with 422 and a
plain message, on the trial's import and on the workspace's, as importing such a file already was."""

from tests.test_business_permissions import _client_with_role
from tests.test_free_trial import _approved_trial_client

MISSING_ID = "Required column 'complaint_id' (for example 'Complaint Id' or 'Complaint Number') is missing."


def _refused(response, message: str) -> dict:
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "IMPORT_FILE_EMPTY" and detail["message"] == message
    assert not detail["report"]["ready"] and detail["report"]["rows"] == 0
    assert "Traceback" not in response.text
    return detail


def _empty_files_are_refused(client, base: str) -> None:
    check = f"{base}/complaints/check"
    _refused(client.post(check, content=b""), "The file is empty.")
    _refused(client.post(check, content=b"\n\n"), "The file is empty.")
    _refused(
        client.post(check, content=b"complaint_id,product_id,description\n"), "The file has a header but no data rows."
    )
    # Blank lines under the header are no rows either.
    _refused(
        client.post(check, content=b"complaint_id,product_id,description\n,,\n\n"),
        "The file has a header but no data rows.",
    )
    # A JSON body is read as a one-line table: a header without the required columns, and no rows (Document 1,
    # FT-09-005 step 4).
    detail = _refused(client.post(check, content=b"{}", headers={"Content-Type": "application/json"}), MISSING_ID)
    assert [issue["column"] for issue in detail["report"]["issues"]] == ["complaint_id", "product_id", "description"]
    # A file with rows still answers its report, with its problems when it has some.
    problems = client.post(check, content=b"complaint_id,product_id\nC-1,P-1\n")
    assert problems.status_code == 200 and not problems.json()["ready"] and problems.json()["error_count"] == 1
    ready = client.post(check, content=b"complaint_id,product_id,description\nC-1,P-1,Alarm with no occlusion\n")
    assert ready.status_code == 200, ready.text
    # Importing an empty file is refused as before.
    imported = client.post(f"{base}/complaints", content=b"complaint_id,product_id,description\n")
    assert imported.status_code == 422 and imported.json()["detail"]["code"] == "IMPORT_CHECK_FAILED"


def test_the_trial_import_refuses_an_empty_file():
    user, _approval, _email = _approved_trial_client()
    _empty_files_are_refused(user, "/api/v1/trial/imports")
    # The workspace's import, which a free trial reaches too.
    _empty_files_are_refused(user, "/api/v1/data/import")


def test_the_workspace_import_refuses_an_empty_file():
    investigator = _client_with_role("Investigator")
    _empty_files_are_refused(investigator, "/api/v1/data/import")
