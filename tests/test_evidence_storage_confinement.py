"""Evidence files are read only from the evidence storage folder; application files such as .env are never served."""

import uuid
from datetime import datetime, timezone

import pytest

from backend.app.db.models.foundation import Evidence
from backend.app.db.session import SessionLocal
from evidence.services.content_reader import ContentSecurityError, EvidenceContentReader
from tests.conftest import authenticated_client


@pytest.mark.parametrize(
    "reference",
    [
        ".env",
        "../.env",
        "../../.env",
        "source/evidence/../../../.env",
        "/etc/passwd",
        "C:/Windows/System32/drivers/etc/hosts",
        "file:///C:/Users/user/Srinivas/MDARIX-R1/.env",
        "backend/app/main.py",
        "",
    ],
)
def test_references_outside_evidence_storage_are_refused(reference):
    with pytest.raises(ContentSecurityError):
        EvidenceContentReader().read_file_reference(reference)


def test_a_relative_reference_inside_evidence_storage_is_read():
    content = EvidenceContentReader().read_file_reference("source/evidence/EV-GEN-011.md")
    assert content.strip() and "MDARIX_" not in content


def test_the_api_never_serves_a_file_outside_evidence_storage():
    client = authenticated_client()
    tenant_id = client.get("/api/v1/auth/session").json()["tenant_id"]
    now = datetime.now(timezone.utc)
    evidence_id = uuid.uuid4()
    db = SessionLocal()
    try:
        db.add(
            Evidence(
                id=evidence_id,
                tenant_id=uuid.UUID(tenant_id),
                evidence_identifier=f"EV-PATH-{evidence_id.hex[:8]}",
                evidence_type="document",
                title="Crafted reference",
                document_ref=".env",
                source_reference="../.env",
                reliability_status="unreviewed",
                fact_type="source_fact",
                content=None,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        response = client.get(f"/api/v1/evidence/{evidence_id}/content")
        assert response.status_code == 403
        assert "POSTGRES" not in response.text and "MDARIX_" not in response.text
    finally:
        db.query(Evidence).filter(Evidence.id == evidence_id).delete()
        db.commit()
        db.close()
