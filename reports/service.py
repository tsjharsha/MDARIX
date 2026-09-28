"""Tenant-scoped, policy-aware report generation.

Large reports are represented as jobs so an API request never has to hold a
large rendering operation open.  The in-process queue is suitable locally;
deployments should call ``run_pending_jobs`` from the outbox/worker process.
"""
from __future__ import annotations

import csv
import io
import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPORTS = {"PRODUCT_INTELLIGENCE":"Product Intelligence Report", "COMPLAINT_TREND":"Complaint Trend Report", "SIGNAL_ASSESSMENT":"Signal Assessment Report", "INVESTIGATION":"Investigation Report", "EVIDENCE_PROVENANCE":"Evidence & Provenance Report", "DECISION_BRIEF":"Decision Brief", "AI_ASSURANCE":"AI Assurance Report", "AUDIT_APPROVAL":"Audit & Approval Report"}
REPORT_VERSION = "1.0"
_jobs: dict[str, dict] = {}
_lock = threading.RLock()


def _safe_data(value, hidden: set[str]):
    if isinstance(value, dict):
        return {k: _safe_data(v, hidden) for k, v in value.items() if k not in hidden}
    if isinstance(value, list):
        return [_safe_data(v, hidden) for v in value]
    return value


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "[").replace(")", "]")


def _render_pdf(data: dict, watermark: str) -> bytes:
    lines = [f"MDARIX {data['title']}", f"Report version: {data['report_version']}", f"Tenant: {data['tenant_id']}", f"Generated: {data['generated_at']}", f"WATERMARK: {watermark}"]
    lines.extend(f"{key}: {value}" for key, value in data.items() if key not in {"context", "tenant_id"})
    stream = "BT /F1 9 Tf 40 760 Td " + " ".join(f"({_pdf_escape(line)}) Tj 0 -14 Td" for line in lines) + " ET"
    return (f"%PDF-1.4\n1 0 obj<< /Type /Catalog /Pages 2 0 R>>endobj\n2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1>>endobj\n3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources<< /Font<< /F1 4 0 R>>>> /Contents 5 0 R>>endobj\n4 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica>>endobj\n5 0 obj<< /Length {len(stream.encode())}>>stream\n{stream}\nendstream endobj\ntrailer<< /Root 1 0 R>>\n%%EOF").encode("latin-1")


def generate_report(code: str, tenant_id: str, *, context: dict | None = None, output_format: str = "JSON", hidden_fields: set[str] | None = None, watermark: str | None = None) -> dict:
    if code not in REPORTS: raise ValueError("REPORT_TYPE_NOT_SUPPORTED")
    fmt = output_format.upper()
    if fmt not in {"JSON", "CSV", "PDF"}: raise ValueError("REPORT_FORMAT_NOT_SUPPORTED")
    generated = datetime.now(timezone.utc).isoformat()
    data = {"report_type": code, "title": REPORTS[code], "tenant_id": str(tenant_id), "report_version": REPORT_VERSION, "status": "READY_FOR_REVIEW", "generated_at": generated, "context": _safe_data(context or {}, hidden_fields or set()), "limitations": ["Report is a governed summary; it does not establish causality or replace human approval."], "human_review_required": True}
    data["watermark"] = watermark or f"MDARIX CONTROLLED COPY · {tenant_id} · v{REPORT_VERSION}"
    if fmt == "CSV":
        out = io.StringIO(); writer = csv.writer(out); writer.writerow(["field", "value"])
        for key, value in data.items(): writer.writerow([key, json.dumps(value, default=str) if isinstance(value, (dict, list)) else str(value)])
        data["content_type"], data["content"] = "text/csv", out.getvalue()
    elif fmt == "PDF":
        data["content_type"], data["content"] = "application/pdf", _render_pdf(data, data["watermark"])
    data["format"] = fmt
    return data


def _job_dict(job):
    if isinstance(job, dict):
        return dict(job)
    return {"id": str(job.id), "tenant_id": str(job.tenant_id), "actor_id": job.actor_id,
            "code": job.report_code, "format": job.output_format, "context": job.context or {},
            "hidden_fields": set(job.hidden_fields or []), "status": job.status,
            "attempts": job.attempts, "path": job.artifact_path, "content_type": job.content_type,
            "report_version": job.report_version, "last_error": job.last_error,
            "created_at": job.created_at.isoformat() if job.created_at else None}


def submit_report_job(code: str, tenant_id: str, *, actor_id: str, output_format: str = "PDF", context: dict | None = None, hidden_fields: set[str] | None = None, db=None) -> dict:
    job_id = str(uuid.uuid4())
    if db is not None:
        from backend.app.db.models.reporting import ReportJob
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        job = ReportJob(id=uuid.UUID(job_id), tenant_id=uuid.UUID(str(tenant_id)), actor_id=str(actor_id),
                        report_code=code, output_format=output_format.upper(), context=context or {},
                        hidden_fields=list(hidden_fields or set()), status="QUEUED", attempts=0,
                        report_version=REPORT_VERSION, created_at=now, updated_at=now)
        db.add(job); db.commit()
        return run_report_job(job_id, db=db)
    with _lock:
        _jobs[job_id] = {"id": job_id, "tenant_id": str(tenant_id), "actor_id": str(actor_id), "code": code, "format": output_format.upper(), "context": context or {}, "hidden_fields": hidden_fields or set(), "status": "QUEUED", "attempts": 0, "created_at": datetime.now(timezone.utc).isoformat()}
    return run_report_job(job_id)


def run_report_job(job_id: str, *, max_attempts: int = 3, db=None) -> dict:
    if db is not None:
        from backend.app.db.models.reporting import ReportJob
        job = db.query(ReportJob).filter(ReportJob.id == uuid.UUID(str(job_id))).with_for_update().one_or_none()
        if not job: raise ValueError("REPORT_JOB_NOT_FOUND")
        if job.status == "READY": return _job_dict(job)
        job.status = "RUNNING"; job.updated_at = datetime.now(timezone.utc).replace(tzinfo=None); db.commit()
        for attempt in range(job.attempts + 1, max_attempts + 1):
            try:
                result = generate_report(job.report_code, str(job.tenant_id), context=job.context or {}, output_format=job.output_format, hidden_fields=set(job.hidden_fields or []))
                directory = Path(os.getenv("MDARIX_REPORT_TEMP_ROOT", tempfile.gettempdir())) / "mdarix-reports" / str(job.tenant_id)
                directory.mkdir(parents=True, exist_ok=True)
                suffix = {"PDF": ".pdf", "CSV": ".csv", "JSON": ".json"}[job.output_format]
                path = directory / f"{job.id}{suffix}"
                payload = result["content"] if isinstance(result.get("content"), (bytes, str)) else json.dumps(result, default=str)
                path.write_bytes(payload if isinstance(payload, bytes) else payload.encode())
                job.status = "READY"; job.attempts = attempt; job.artifact_path = str(path)
                job.content_type = result.get("content_type", "application/json"); job.updated_at = datetime.now(timezone.utc).replace(tzinfo=None); db.commit()
                return _job_dict(job)
            except Exception as exc:
                job.attempts = attempt; job.last_error = type(exc).__name__; db.commit()
        job.status = "FAILED"; job.updated_at = datetime.now(timezone.utc).replace(tzinfo=None); db.commit()
        return _job_dict(job)
    with _lock:
        job = _jobs.get(job_id)
        if not job: raise ValueError("REPORT_JOB_NOT_FOUND")
        if job["status"] == "READY": return job
        job["status"] = "RUNNING"
    for attempt in range(job["attempts"] + 1, max_attempts + 1):
        try:
            result = generate_report(job["code"], job["tenant_id"], context=job["context"], output_format=job["format"], hidden_fields=job["hidden_fields"])
            # Keep generated bytes tenant-isolated and outside the source tree.
            directory = Path(os.getenv("MDARIX_REPORT_TEMP_ROOT", tempfile.gettempdir())) / "mdarix-reports" / job["tenant_id"]
            directory.mkdir(parents=True, exist_ok=True)
            suffix = {"PDF": ".pdf", "CSV": ".csv", "JSON": ".json"}[job["format"]]
            path = directory / f"{job_id}{suffix}"
            payload = result["content"] if isinstance(result.get("content"), (bytes, str)) else json.dumps(result, default=str)
            path.write_bytes(payload if isinstance(payload, bytes) else payload.encode())
            with _lock:
                job.update({"status": "READY", "attempts": attempt, "path": str(path), "content_type": result["content_type"] if "content_type" in result else "application/json", "report_version": REPORT_VERSION})
            return job
        except Exception as exc:
            with _lock: job.update({"attempts": attempt, "last_error": type(exc).__name__})
    with _lock: job["status"] = "FAILED"
    return job


def get_report_job(job_id: str, tenant_id: str, db=None) -> dict:
    if db is not None:
        from backend.app.db.models.reporting import ReportJob
        job = db.query(ReportJob).filter(ReportJob.id == uuid.UUID(str(job_id)), ReportJob.tenant_id == uuid.UUID(str(tenant_id))).one_or_none()
        if not job: raise ValueError("REPORT_JOB_NOT_FOUND")
        return _job_dict(job)
    with _lock:
        job = _jobs.get(job_id)
        if not job or job["tenant_id"] != str(tenant_id): raise ValueError("REPORT_JOB_NOT_FOUND")
        return dict(job)


def run_pending_report_jobs(db, *, limit: int = 10) -> dict:
    """Claim and process queued jobs safely for one tenant data plane."""
    from backend.app.db.models.reporting import ReportJob
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    # Recover a claim left behind by a terminated worker. The timeout is
    # intentionally conservative so a slow render is not double-processed.
    stale_before = now - __import__("datetime").timedelta(minutes=15)
    db.query(ReportJob).filter(ReportJob.status == "CLAIMED", ReportJob.updated_at < stale_before).update(
        {ReportJob.status: "QUEUED", ReportJob.updated_at: now}, synchronize_session=False
    )
    db.commit()
    rows = (db.query(ReportJob)
            .filter(ReportJob.status == "QUEUED")
            .order_by(ReportJob.created_at)
            .with_for_update(skip_locked=True)
            .limit(limit).all())
    ids = [str(row.id) for row in rows]
    for row in rows:
        row.status = "CLAIMED"
        row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    ready = failed = 0
    for job_id in ids:
        result = run_report_job(job_id, db=db)
        if result["status"] == "READY": ready += 1
        elif result["status"] == "FAILED": failed += 1
    return {"claimed": len(ids), "ready": ready, "failed": failed}
