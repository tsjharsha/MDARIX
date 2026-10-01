import os
from pathlib import Path
from typing import Any, Dict, Optional
import uuid

from sqlalchemy.orm import Session
from backend.app.db.models.foundation import Evidence


class ContentSecurityError(Exception):
    """Raised when an illegal path traversal or cross-tenant file access attempt is detected."""

    pass


# Evidence files live in one storage folder: MDARIX_EVIDENCE_STORAGE_ROOT, or the golden dataset folder by default.
# References are relative paths inside it; nothing else on the server (application code, .env) can ever be read.
_DEFAULT_STORAGE_ROOT = Path(__file__).resolve().parents[2] / "data" / "golden"
ALLOWED_EVIDENCE_SUFFIXES = {".md", ".txt", ".csv", ".json"}


def evidence_storage_root() -> Path:
    configured = os.getenv("MDARIX_EVIDENCE_STORAGE_ROOT", "").strip()
    return Path(configured).resolve() if configured else _DEFAULT_STORAGE_ROOT.resolve()


class EvidenceContentReader:
    """Securely reads and resolves evidence content from DB records or the evidence storage folder."""

    def __init__(self, workspace_root: Optional[Path] = None):
        self._configured_root = workspace_root

    @property
    def workspace_root(self) -> Path:
        return (self._configured_root or evidence_storage_root()).resolve()

    def get_evidence_content(
        self, db: Session, tenant_id: uuid.UUID, evidence_id: uuid.UUID
    ) -> tuple[str, Dict[str, Any]]:
        """Retrieves raw content and metadata for a tenant-scoped evidence item."""
        evidence = db.query(Evidence).filter(Evidence.tenant_id == tenant_id, Evidence.id == evidence_id).first()
        if not evidence:
            raise ValueError(f"Evidence {evidence_id} not found for tenant {tenant_id}")

        metadata = {
            "evidence_id": str(evidence.id),
            "evidence_identifier": evidence.evidence_identifier,
            "evidence_type": evidence.evidence_type,
            "title": evidence.title,
            "source_system": evidence.source_system,
            "source_reference": evidence.source_reference,
            "reliability_status": evidence.reliability_status,
            "fact_type": evidence.fact_type,
            "document_ref": evidence.document_ref,
            "effective_timestamp": evidence.effective_timestamp.isoformat() if evidence.effective_timestamp else None,
            "recorded_timestamp": evidence.recorded_timestamp.isoformat() if evidence.recorded_timestamp else None,
            "ingestion_timestamp": evidence.ingestion_timestamp.isoformat() if evidence.ingestion_timestamp else None,
        }

        # 1. Directly stored text content in DB
        if evidence.content and evidence.content.strip():
            return evidence.content, metadata

        # 2. File-backed evidence reference resolving with strict path traversal defense
        # source_reference is a citation label (e.g. "TW-1"), never a file path, so only document_ref is read.
        if evidence.document_ref and "://" not in evidence.document_ref.replace("file://", ""):
            safe_content = self.read_file_reference(evidence.document_ref)
            return safe_content, metadata

        # Default fallback string if no content text is populated
        return f"Evidence record: {evidence.title} ({evidence.evidence_type})", metadata

    def read_file_reference(self, file_ref: str) -> str:
        """Read a relative reference inside the evidence storage folder; anything else is refused."""
        clean_ref = file_ref.replace("file:///", "").replace("file://", "").replace("\\", "/").strip()
        relative = Path(clean_ref)
        if (
            not clean_ref
            or relative.is_absolute()
            or relative.drive
            or clean_ref.startswith("/")
            or ".." in relative.parts
            or relative.suffix.lower() not in ALLOWED_EVIDENCE_SUFFIXES
        ):
            raise ContentSecurityError("Access denied: evidence references must be relative paths in evidence storage.")
        root = self.workspace_root
        target_path = (root / relative).resolve()
        # Resolving follows links, so a link pointing outside the storage folder is refused too.
        try:
            target_path.relative_to(root)
        except ValueError:
            raise ContentSecurityError("Access denied: evidence reference is outside evidence storage.")

        if not target_path.is_file():
            return "The referenced evidence file is not available."

        with open(target_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
