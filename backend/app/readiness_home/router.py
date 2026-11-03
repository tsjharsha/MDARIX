"""Readiness API: the checks an inspector would make, from the organization's records, and their summary as a PDF.

- ``GET /api/v1/readiness``: every check (the four home numbers first), open to every signed-in member, and
  ``detection_pending`` while an import's signals are still being found (the trend check waits for them).
- ``GET /api/v1/readiness/summary``: the summary's data for a period (30 to 1095 days; 365 by default).
- ``GET /api/v1/readiness/summary.pdf``: the same as a PDF for management review (data.export), audited.
- ``GET /api/v1/readiness/inspection-pack.zip``: the inspection pack (pack.py): the PDF, every check and every record
  behind it as CSV, and a manifest of SHA-256 fingerprints (data.export), audited.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from backend.app.downloads import attachment
from backend.app.access.permissions import DATA_EXPORT, require_permission
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.readiness_home import service, summary
from backend.app.request_context import AuthenticatedRequestContext, get_request_context

logger = logging.getLogger("mdarix.readiness")
router = APIRouter(prefix="/api/v1/readiness", tags=["Readiness"])


def _tenant(ctx: AuthenticatedRequestContext) -> uuid.UUID:
    return uuid.UUID(str(ctx.tenant_id))


def _organization(control_db: Session, tenant_id: uuid.UUID) -> str:
    from backend.app.db.models.foundation import Tenant

    try:
        row = control_db.query(Tenant.name).filter(Tenant.id == tenant_id).first()
        return (row.name if row is not None else None) or "Your organization"
    except Exception:  # the name is decoration; the summary never fails for it
        logger.warning("Readiness summary: the organization's name could not be read", exc_info=True)
        return "Your organization"


@router.get("")
def readiness(
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    from backend.app.signals.hooks import detection_pending

    tenant_id = _tenant(ctx)
    return {**service.readiness(db, tenant_id), "detection_pending": detection_pending(control_db, db, tenant_id)}


@router.get("/summary")
def readiness_summary(
    period_days: int = Query(summary.PERIOD_DEFAULT, ge=summary.PERIOD_MIN, le=summary.PERIOD_MAX),
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    return summary.build(db, _tenant(ctx), period_days=period_days)


@router.get("/summary.pdf", dependencies=[Depends(require_permission(DATA_EXPORT))])
def readiness_summary_pdf(
    period_days: int = Query(summary.PERIOD_DEFAULT, ge=summary.PERIOD_MIN, le=summary.PERIOD_MAX),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = _tenant(ctx)
    now = datetime.now(timezone.utc)
    data = summary.build(db, tenant_id, period_days=period_days)
    content = summary.render_pdf(data, _organization(control_db, tenant_id), now.strftime("%Y-%m-%d %H:%M UTC"))
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="READINESS_SUMMARY_EXPORTED",
            entity_type="Tenant",
            entity_id=tenant_id,
            correlation_id=ctx.correlation_id,
            details={"period": data["period"], "bytes": len(content), "format": "PDF"},
            created_at=now,
        )
    )
    db.commit()
    filename = f"mdarix-readiness-summary-{data['period']['to']}.pdf"
    return Response(
        content,
        media_type="application/pdf",
        headers={"Content-Disposition": attachment(f"{filename}"), "Cache-Control": "no-store"},
    )


@router.get("/inspection-pack.zip", dependencies=[Depends(require_permission(DATA_EXPORT))])
def readiness_inspection_pack(
    period_days: int = Query(summary.PERIOD_DEFAULT, ge=summary.PERIOD_MIN, le=summary.PERIOD_MAX),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The inspection pack (pack.py): the summary PDF, every check and every record behind it as CSV, and a manifest
    of SHA-256 fingerprints, in one ZIP (data.export), audited."""
    from backend.app.readiness_home import pack

    tenant_id = _tenant(ctx)
    now = datetime.now(timezone.utc)
    content, manifest = pack.build_pack(
        db, tenant_id, organization=_organization(control_db, tenant_id), period_days=period_days, now=now
    )
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="READINESS_INSPECTION_PACK_EXPORTED",
            entity_type="Tenant",
            entity_id=tenant_id,
            correlation_id=ctx.correlation_id,
            details={
                "period": manifest["period"],
                "bytes": len(content),
                "files": len(manifest["files"]),
                "unreadable": manifest["unreadable"],
                "format": "ZIP",
            },
            created_at=now,
        )
    )
    db.commit()
    filename = f"mdarix-inspection-pack-{manifest['period']['to']}.zip"
    return Response(
        content,
        media_type="application/zip",
        headers={"Content-Disposition": attachment(f"{filename}"), "Cache-Control": "no-store"},
    )
