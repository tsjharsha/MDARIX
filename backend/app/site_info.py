"""Public company details and legal documents for the website.

Company details come from the server configuration (``MDARIX_COMPANY_LEGAL_NAME``, ``MDARIX_COMPANY_ADDRESS``,
``MDARIX_SUPPORT_EMAIL``, ``MDARIX_PRIVACY_EMAIL``). Legal documents are Markdown files supplied by the company's
lawyer and placed in ``MDARIX_LEGAL_DIR`` (``privacy.md``, ``terms.md``, ``trial-agreement.md``), so they can be
updated without rebuilding the site. Staging and production refuse to start until the company details are set and
``MDARIX_LEGAL_TEXT_APPROVED`` is true (backend/app/config_check.py).
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response

from backend.app.deployment_role import deployment_role

router = APIRouter(prefix="/api/v1/public", tags=["Website"])

LEGAL_DOCUMENTS = {"privacy": "privacy.md", "terms": "terms.md", "trial-agreement": "trial-agreement.md"}
MAX_DOCUMENT_BYTES = 200_000


def _get(name: str) -> str:
    return os.getenv(name, "").strip()


@router.get("/site-info")
def site_info(response: Response) -> dict:
    response.headers["Cache-Control"] = "public, max-age=300"
    return {
        "company_name": _get("MDARIX_COMPANY_LEGAL_NAME") or None,
        "company_address": _get("MDARIX_COMPANY_ADDRESS") or None,
        "support_email": _get("MDARIX_SUPPORT_EMAIL") or None,
        "privacy_email": _get("MDARIX_PRIVACY_EMAIL") or None,
        "legal_text_approved": _get("MDARIX_LEGAL_TEXT_APPROVED").lower() == "true",
        "trial": {"days": 30, "users": 3, "rows": 5000, "data_deleted_after_days": 30},
        # MULTI, PLATFORM or CELL (backend/app/deployment_role.py); free trials exist on MULTI only.
        "deployment_role": deployment_role(),
    }


@router.get("/legal/{document}")
def legal_document(document: str, response: Response) -> dict:
    """One lawyer-supplied legal document as Markdown, or ``available: false`` while it has not been provided."""
    filename = LEGAL_DOCUMENTS.get(document)
    if filename is None:
        raise HTTPException(404, detail={"code": "DOCUMENT_NOT_FOUND", "message": "No such document"})
    response.headers["Cache-Control"] = "public, max-age=300"
    folder = _get("MDARIX_LEGAL_DIR")
    path = Path(folder) / filename if folder else None
    if path is None or not path.is_file() or path.stat().st_size > MAX_DOCUMENT_BYTES:
        return {"document": document, "available": False, "markdown": None}
    return {"document": document, "available": True, "markdown": path.read_text(encoding="utf-8")}
