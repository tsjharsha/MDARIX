"""Supplier replies are recorded with their file; uploads are refused by declared size before the body is read."""

import uuid

from sqlalchemy import text

from backend.app.db.session import engine
from backend.app.stage3_workflow_router import MAX_UPLOAD_REQUEST_BYTES, upload_supplier_attachment
from tests.reports_seed import role_client
from tests.test_supplier_evidence_requests import PATH, _body, own_supplier


def _request(client) -> str:
    made = client.post(PATH, json=_body(own_supplier(client)))
    assert made.status_code == 200, made.text
    return made.json()["id"]


def _upload(client, request_id, content=b"%PDF-1.4 certificate", name="certificate.pdf"):
    return client.post(f"{PATH}/{request_id}/attachments", files={"file": (name, content, "application/pdf")})


def test_a_reply_is_recorded_with_its_attachment_and_audited():
    client = role_client("INVESTIGATOR")[0]
    request_id = _request(client)
    uploaded = _upload(client, request_id)
    assert uploaded.status_code == 200, uploaded.text
    attachment_id = uploaded.json()["id"]
    reply = client.post(
        f"/api/v1/stage3/supplier-requests/{request_id}/reply",
        json={"note": "Certificate of conformance received", "attachment_id": attachment_id},
    )
    assert reply.status_code == 200, reply.text
    body = reply.json()
    assert body["status"] == "REPLIED" and body["evidence_acceptance"] == "NEVER_AUTOMATIC"
    assert body["reply"]["attachment_id"] == attachment_id and body["reply"]["note"].startswith("Certificate")
    listed = next(item for item in client.get(PATH).json() if item["id"] == request_id)
    assert listed["status"] == "REPLIED" and listed["replies"][0]["attachment_id"] == attachment_id
    second = client.post(f"/api/v1/stage3/supplier-evidence-requests/{request_id}/reply", json={"note": "Follow-up"})
    assert second.status_code == 200 and len(second.json()["replies"]) == 2
    with engine.connect() as connection:
        audited = connection.execute(
            text("SELECT count(*) FROM audit_events WHERE action = 'SUPPLIER_REPLY_RECORDED' AND entity_id = :id"),
            {"id": request_id},
        ).scalar()
    assert audited == 2


def test_replies_are_tenant_scoped_and_need_write_permission():
    client = role_client("INVESTIGATOR")[0]
    request_id = _request(client)
    path = f"/api/v1/stage3/supplier-requests/{request_id}/reply"
    assert role_client("VIEWER")[0].post(path, json={"note": "x"}).status_code == 403
    missing = client.post(f"/api/v1/stage3/supplier-requests/{uuid.uuid4()}/reply", json={"note": "x"})
    assert missing.status_code == 404
    # An attachment of another request cannot be linked.
    other = _request(client)
    foreign = _upload(client, other).json()["id"]
    refused = client.post(path, json={"note": "Wrong file", "attachment_id": foreign})
    assert refused.status_code == 404 and refused.json()["detail"]["code"] == "ATTACHMENT_NOT_FOUND"
    assert client.post(path, json={"note": "   "}).status_code == 422


def test_an_upload_declared_too_large_is_refused_before_reading():
    client = role_client("INVESTIGATOR")[0]
    request_id = _request(client)
    response = client.post(
        f"{PATH}/{request_id}/attachments",
        content=b"--x--",
        headers={
            "Content-Type": "multipart/form-data; boundary=x",
            "Content-Length": str(MAX_UPLOAD_REQUEST_BYTES + 1),
        },
    )
    assert response.status_code == 413 and response.json()["detail"]["code"] == "ATTACHMENT_TOO_LARGE"


def test_the_upload_handler_runs_in_the_thread_pool():
    import inspect

    # A plain function: its database, malware-scan and storage work never blocks the event loop.
    assert not inspect.iscoroutinefunction(upload_supplier_attachment)
