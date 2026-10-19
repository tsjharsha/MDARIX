"""Public company details and legal documents for the website.

Company details come from the server configuration (``MDARIX_COMPANY_LEGAL_NAME``, ``MDARIX_COMPANY_ADDRESS``,
``MDARIX_SUPPORT_EMAIL``, ``MDARIX_PRIVACY_EMAIL``). Legal documents are Markdown files supplied by the company's
lawyer and placed in ``MDARIX_LEGAL_DIR`` (``privacy.md``, ``terms.md``, ``trial-agreement.md``), so they can be
updated without rebuilding the site. Staging and production refuse to start until the company details are set and
``MDARIX_LEGAL_TEXT_APPROVED`` is true (backend/app/config_check.py).
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response

from backend.app.deployment_role import deployment_role
from backend.app.trial.auto_approval import FREE_MAIL_DOMAINS
from backend.app.version import APP_VERSION

router = APIRouter(prefix="/api/v1/public", tags=["Website"])

LEGAL_DOCUMENTS = {"privacy": "privacy.md", "terms": "terms.md", "trial-agreement": "trial-agreement.md"}
MAX_DOCUMENT_BYTES = 200_000


def _get(name: str) -> str:
    return os.getenv(name, "").strip()


_LAST_UPDATED = re.compile(r"^\s*Last updated:\s*(.+?)\s*$", re.MULTILINE)


def _document_path(document: str) -> Path | None:
    filename = LEGAL_DOCUMENTS.get(document)
    folder = _get("MDARIX_LEGAL_DIR")
    path = Path(folder) / filename if folder and filename else None
    if path is None or not path.is_file() or path.stat().st_size > MAX_DOCUMENT_BYTES:
        return None
    return path


def legal_versions() -> dict:
    """The version of each legal document the website serves now: its "Last updated" date (None when the text has
    none) and the SHA-256 of its exact text, or ``available: false`` when it is not provided. A trial request stores
    this with the time it was sent (``OnboardingRequest.legal_acceptance``), as the record of which texts were
    accepted."""
    versions = {}
    for document in LEGAL_DOCUMENTS:
        path = _document_path(document)
        if path is None:
            versions[document] = {"available": False, "last_updated": None, "sha256": None}
            continue
        content = path.read_bytes()
        found = _LAST_UPDATED.search(content.decode("utf-8", errors="replace"))
        versions[document] = {
            "available": True,
            "last_updated": found.group(1).strip("*_ ") if found else None,
            "sha256": hashlib.sha256(content).hexdigest(),
        }
    return versions


@router.get("/site-info")
def site_info(response: Response) -> dict:
    response.headers["Cache-Control"] = "public, max-age=300"
    return {
        "company_name": _get("MDARIX_COMPANY_LEGAL_NAME") or None,
        "company_address": _get("MDARIX_COMPANY_ADDRESS") or None,
        "support_email": _get("MDARIX_SUPPORT_EMAIL") or None,
        "privacy_email": _get("MDARIX_PRIVACY_EMAIL") or None,
        "legal_text_approved": _get("MDARIX_LEGAL_TEXT_APPROVED").lower() == "true",
        "trial": {
            "days": 30,
            "users": 3,
            "rows": 5000,
            "data_deleted_after_days": 30,
            # The addresses whose requests a person reviews (automatic approval's own list), so sign-up can say so
            # before the request is sent.
            "free_mail_domains": sorted(FREE_MAIL_DOMAINS),
        },
        # MULTI, PLATFORM or CELL (backend/app/deployment_role.py); free trials exist on MULTI only.
        "deployment_role": deployment_role(),
    }


@router.get("/version")
def version(response: Response) -> dict:
    """The version the server runs (the repository's VERSION file), for an open tab to see that a newer MDARIX was
    deployed and offer a reload (frontend/src/features/shared/appVersion.ts). Never cached, and it reads no session,
    so asking does not keep an idle sign-in alive. The built pages carry the same number, so nothing new is disclosed."""
    response.headers["Cache-Control"] = "no-store"
    return {"version": APP_VERSION}


@router.get("/legal/{document}")
def legal_document(document: str, response: Response) -> dict:
    """One lawyer-supplied legal document as Markdown, or ``available: false`` while it has not been provided."""
    if document not in LEGAL_DOCUMENTS:
        raise HTTPException(404, detail={"code": "DOCUMENT_NOT_FOUND", "message": "No such document"})
    response.headers["Cache-Control"] = "public, max-age=300"
    path = _document_path(document)
    if path is None:
        return {"document": document, "available": False, "markdown": None}
    return {"document": document, "available": True, "markdown": path.read_text(encoding="utf-8")}
