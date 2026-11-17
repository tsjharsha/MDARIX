"""Review C4: a 422 says what is wrong in plain English (``code`` INVALID_INPUT, ``message``), keeps FastAPI's list
the app reads, and never echoes what was submitted."""

import pytest
from tests.conftest import authenticated_client

pytestmark = pytest.mark.db


def test_a_bad_id_in_the_path_reads_as_plain_english():
    answer = authenticated_client().get("/api/v1/investigations/not-an-id/workspace")
    assert answer.status_code == 422
    body = answer.json()
    assert body["code"] == "INVALID_INPUT"
    assert body["message"] == "investigation_id: must be a valid ID"
    assert body["detail"][0]["loc"] == ["path", "investigation_id"] and "input" not in body["detail"][0]


def test_a_query_value_out_of_range_names_its_limit_and_the_value_never_comes_back():
    path = "/api/v1/investigations/00000000-0000-0000-0000-000000000001/workspace"
    answer = authenticated_client().get(path, params={"retrieval_top_k": "987654"})
    assert answer.status_code == 422
    assert answer.json()["message"] == "retrieval_top_k: must be at most 25"
    assert "987654" not in answer.text
