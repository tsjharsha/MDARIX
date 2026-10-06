"""Regulatory documents: approved content is locked, and no author of any version may approve."""

import uuid

from tests.test_business_permissions import _client_with_role


def _document(author):
    identifier = f"REG-TEST-{uuid.uuid4().hex[:8]}"
    made = author.post("/api/v1/regulatory/draft", json={"document_type": "IFU", "document_identifier": identifier})
    assert made.status_code == 200, made.text
    return identifier, made.json()["document_id"]


def _status(client, document_id, status):
    lock = client.get(f"/api/v1/regulatory/documents/{document_id}").json()
    lock = (lock.get("document") or lock).get("lock_version", 1)
    body = {"status": status, "expected_lock_version": lock, "reason": "Test"}
    if status == "APPROVED":
        # Approval re-authenticates like a signature (tests/test_regulatory_copilot.py covers the refusals).
        body["password"] = "Permission test 2026!"
    return client.post(f"/api/v1/regulatory/documents/{document_id}/status", json=body)


def test_an_approved_document_cannot_be_rewritten():
    author, approver = _client_with_role("INVESTIGATOR"), _client_with_role("APPROVER")
    identifier, document_id = _document(author)
    assert _status(author, document_id, "IN_REVIEW").status_code == 200
    assert _status(approver, document_id, "APPROVED").status_code == 200
    rewrite = approver.post(
        "/api/v1/regulatory/draft", json={"document_type": "IFU", "document_identifier": identifier}
    )
    assert rewrite.status_code == 409 and rewrite.json()["detail"]["code"] == "REGULATORY_DOCUMENT_LOCKED"
    after = approver.get(f"/api/v1/regulatory/documents/{document_id}").json()
    assert (after.get("document") or after)["status"] == "APPROVED"


def test_text_in_review_changes_only_after_returning_to_draft():
    author = _client_with_role("INVESTIGATOR")
    identifier, document_id = _document(author)
    assert _status(author, document_id, "IN_REVIEW").status_code == 200
    blocked = author.post("/api/v1/regulatory/draft", json={"document_type": "IFU", "document_identifier": identifier})
    assert blocked.status_code == 409
    assert _status(author, document_id, "DRAFT").status_code == 200
    again = author.post("/api/v1/regulatory/draft", json={"document_type": "IFU", "document_identifier": identifier})
    assert again.status_code == 200 and again.json()["version"] == 2


def test_whoever_wrote_any_version_cannot_approve():
    author, approver = _client_with_role("INVESTIGATOR"), _client_with_role("APPROVER")
    identifier, document_id = _document(author)
    # The approver writes version 2, then tries to approve the document.
    rewritten = approver.post(
        "/api/v1/regulatory/draft", json={"document_type": "IFU", "document_identifier": identifier}
    )
    assert rewritten.status_code == 200
    assert _status(approver, document_id, "IN_REVIEW").status_code == 200
    refused = _status(approver, document_id, "APPROVED")
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "SOD_DENIED"
    assert _status(_client_with_role("APPROVER"), document_id, "APPROVED").status_code == 200
