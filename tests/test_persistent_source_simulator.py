from fastapi.testclient import TestClient
from pathlib import Path
from uuid import uuid4

from source_simulator import persistent_app


def test_persistent_provider_requires_token_and_enforces_tenant_scope():
    client = TestClient(persistent_app.app)
    assert client.get("/ready").status_code == 200
    assert client.get("/records/Complaint").status_code == 401
    assert (
        client.get(
            "/records/Complaint", headers={"X-Provider-Token": "sim-a"}, params={"tenant": "TENANT_B"}
        ).status_code
        == 403
    )


def test_persistent_provider_writes_reads_and_versions_records():
    client = TestClient(persistent_app.app)
    headers = {"X-Provider-Token": "sim-a"}
    external_id = f"CMP-{uuid4()}"
    first = client.post(
        "/records/Complaint",
        headers=headers,
        json={"external_id": external_id, "record_version": "1", "payload": {"severity": "LOW"}},
    )
    second = client.post(
        "/records/Complaint",
        headers=headers,
        json={"external_id": external_id, "record_version": "2", "payload": {"severity": "HIGH"}},
    )
    assert first.status_code == second.status_code == 200
    assert client.get("/records/Complaint", headers=headers).json()["records"][0]["severity"] == "HIGH"
    assert len(client.get(f"/records/Complaint/{external_id}/history", headers=headers).json()["history"]) == 1


def _new_tenant(client, monkeypatch, prefix):
    monkeypatch.setenv("SIMULATOR_ADMIN_TOKEN", "test-admin")
    key = f"{prefix}_{uuid4().hex[:8].upper()}"
    created = client.post("/admin/tenants", headers={"X-Admin-Token": "test-admin"}, json={"tenant_key": key})
    assert created.status_code == 201, created.text
    return key, created.json()


def _cleanup(*databases):
    for name in databases:
        persistent_app.store.tenant_engine(name).dispose()
        Path(name).unlink(missing_ok=True)


def test_each_tenant_gets_its_own_database_and_key_and_cannot_see_another(monkeypatch):
    client = TestClient(persistent_app.app)
    first, first_body = _new_tenant(client, monkeypatch, "ACME")
    second, second_body = _new_tenant(client, monkeypatch, "BETA")
    try:
        assert first_body["database"] != second_body["database"]
        assert first_body["api_key"].startswith("sk_trackwise_")
        csv_text = "complaint_id,complaint_number,product_code,problem_description\nTW-1,CMP-1,PUMP-200,Alarm\n"
        uploaded = client.post(
            "/records/complaints/csv",
            headers={"X-Provider-Token": first_body["api_key"], "Content-Type": "text/csv"},
            content=csv_text,
        )
        assert uploaded.status_code == 200, uploaded.text
        assert uploaded.json()["created"] == 1
        mine = client.get("/records/complaints", headers={"X-Provider-Token": first_body["api_key"]}).json()["records"]
        theirs = client.get("/records/complaints", headers={"X-Provider-Token": second_body["api_key"]}).json()
        assert [row["complaint_number"] for row in mine] == ["CMP-1"]
        assert theirs["records"] == [] and theirs["tenant_key"] == second
        # A tenant cannot ask for another tenant's records with its own key.
        denied = client.get(
            "/records/complaints", headers={"X-Provider-Token": first_body["api_key"]}, params={"tenant": second}
        )
        assert denied.status_code == 403
        # Uploading the same file again changes nothing; a changed row is a new version with history.
        again = client.post(
            "/records/complaints/csv",
            headers={"X-Provider-Token": first_body["api_key"], "Content-Type": "text/csv"},
            content=csv_text.replace("Alarm", "Alarm at start"),
        ).json()
        assert again["updated"] == 1
        history = client.get("/records/complaints/TW-1/history", headers={"X-Provider-Token": first_body["api_key"]})
        assert len(history.json()["history"]) == 1
    finally:
        _cleanup(first_body["database"], second_body["database"])


def test_a_bad_csv_stores_nothing_and_says_why(monkeypatch):
    client = TestClient(persistent_app.app)
    _, body = _new_tenant(client, monkeypatch, "GAMMA")
    headers = {"X-Provider-Token": body["api_key"], "Content-Type": "text/csv"}
    try:
        unknown = client.post("/records/complaints/csv", headers=headers, content="complaint_id,colour\nTW-1,red\n")
        assert unknown.status_code == 422 and "Unknown columns: colour" in unknown.text
        rows = (
            "complaint_id,complaint_number,product_code,problem_description\n"
            "TW-1,CMP-1,PUMP-200,Alarm\nTW-2,CMP-2,,No product\nTW-1,CMP-3,PUMP-200,Duplicate key\n"
        )
        rejected = client.post("/records/complaints/csv", headers=headers, content=rows)
        assert rejected.status_code == 422
        messages = [problem["message"] for problem in rejected.json()["detail"]["problems"]]
        assert any("product_code" in message for message in messages)
        assert any("Same key as row 2" in message for message in messages)
        listed = client.get("/records/complaints", headers={"X-Provider-Token": body["api_key"]}).json()
        assert listed["records"] == []
        assert client.post("/records/colours/csv", headers=headers, content="a\n1\n").status_code == 404
    finally:
        _cleanup(body["database"])


def test_admin_api_needs_its_token_and_a_rotated_key_replaces_the_old_one(monkeypatch):
    client = TestClient(persistent_app.app)
    monkeypatch.delenv("SIMULATOR_ADMIN_TOKEN", raising=False)
    assert client.post("/admin/tenants", json={"tenant_key": "NOPE_1"}).status_code == 503
    key, body = _new_tenant(client, monkeypatch, "DELTA")
    try:
        assert (
            client.post("/admin/tenants", headers={"X-Admin-Token": "wrong"}, json={"tenant_key": "X_1"}).status_code
            == 401
        )
        listed = client.get("/admin/tenants", headers={"X-Admin-Token": "test-admin"}).json()["tenants"]
        entry = next(row for row in listed if row["tenant_key"] == key)
        assert "api_key" not in entry and entry["api_key_ends_with"] == body["api_key"][-4:]
        rotated = client.post(f"/admin/tenants/{key}/rotate-key", headers={"X-Admin-Token": "test-admin"}).json()
        assert client.get("/whoami", headers={"X-Provider-Token": body["api_key"]}).status_code == 401
        assert client.get("/whoami", headers={"X-Provider-Token": rotated["api_key"]}).json()["tenant_key"] == key
        duplicate = client.post("/admin/tenants", headers={"X-Admin-Token": "test-admin"}, json={"tenant_key": key})
        assert duplicate.status_code == 409
    finally:
        _cleanup(body["database"])


def test_the_upload_page_and_catalog_describe_this_application():
    client = TestClient(persistent_app.app)
    assert "TrackWise Digital" in client.get("/").text
    records = client.get("/catalog").json()["records"]
    assert (
        records["complaints"]["key"] == ["complaint_id"] and "problem_description" in records["complaints"]["required"]
    )
