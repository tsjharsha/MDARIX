"""Validation evidence (E2): requirement -> test -> last recorded result, and the release validation pack.

An organization's administrator, a free trial's owner and a platform administrator read it; anyone else is refused.
Only a platform administrator records a test run (a pytest JUnit XML upload). The mapping and the pack come from the
repository (``validation/evidence_view.py``); results come only from the newest recorded run.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from sqlalchemy.orm import Session

from backend.app.access.authz import _require_platform_admin, admin_or_trial_owner
from backend.app.access.common import _audit_configuration
from backend.app.db.models.validation_runs import ValidationTestRun
from backend.app.db.session import get_db
from backend.app.downloads import attachment
from validation import evidence_view

router = APIRouter(prefix="/api/v1", tags=["Validation evidence"])


def _latest(db: Session) -> ValidationTestRun | None:
    return db.query(ValidationTestRun).order_by(ValidationTestRun.uploaded_at.desc()).first()


def _run(row: ValidationTestRun | None) -> dict | None:
    if row is None:
        return None
    return {"commit": row.commit, "meta": row.meta, "tests": row.tests}


def _iso(moment) -> str | None:
    return moment.isoformat() if moment else None


@router.get("/admin/validation-evidence")
def validation_evidence(request: Request, db: Session = Depends(get_db)):
    admin_or_trial_owner(request, db)
    row = _latest(db)
    view = evidence_view.evidence(evidence_view.repo_sources(), _run(row))
    view["run"] = (
        None
        if row is None
        else {
            "commit": row.commit,
            "tree": (row.meta or {}).get("tree") or "not recorded",
            "ran_at": _iso(row.ran_at),
            "uploaded_at": _iso(row.uploaded_at),
            "passed": row.passed,
            "failed": row.failed,
            "skipped": row.skipped,
            "file_name": row.file_name,
        }
    )
    return view


@router.get("/admin/validation-evidence/pack")
def validation_pack(request: Request, db: Session = Depends(get_db)):
    """The B6b release validation pack, generated now as a dry run (every document watermarked)."""
    admin_or_trial_owner(request, db)
    row = _latest(db)
    release = evidence_view.current_release() or "unreleased"
    moment = (row.ran_at or row.uploaded_at) if row else datetime.now(timezone.utc)
    content = evidence_view.release_pack(evidence_view.repo_sources(), _run(row), release, moment.date().isoformat())
    return Response(
        content,
        media_type="application/zip",
        headers={"Content-Disposition": attachment(f"mdarix-validation-pack-{release}.zip")},
    )


@router.post("/platform-admin/validation-runs", status_code=201)
def record_validation_run(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Record one pytest JUnit XML (with the requirement markers) as the newest test run."""
    admin = _require_platform_admin(request, db)
    raw = file.file.read(evidence_view.MAX_JUNIT_BYTES + 1)
    try:
        parsed = evidence_view.parse_junit(raw)
    except ValueError as error:
        raise HTTPException(422, detail={"code": "NOT_A_TEST_REPORT", "message": str(error)}) from error
    row = ValidationTestRun(
        commit=parsed["commit"] or "not recorded",
        ran_at=parsed["ran_at"],
        passed=parsed["passed"],
        failed=parsed["failed"],
        skipped=parsed["skipped"],
        meta=parsed["meta"],
        tests=parsed["tests"],
        file_name=(file.filename or "junit.xml")[:255],
        file_sha256=parsed["sha256"],
        uploaded_by=admin.id,
        uploaded_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    _audit_configuration(
        db,
        admin,
        "VALIDATION_TEST_RUN_RECORDED",
        "ValidationTestRun",
        row.id,
        "v1",
        request=request,
        after={"commit": row.commit, "passed": row.passed, "failed": row.failed, "sha256": row.file_sha256},
    )
    db.commit()
    return {"id": str(row.id), "commit": row.commit, "passed": row.passed, "failed": row.failed}
