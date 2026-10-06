"""Tenant-scoped, policy-aware report generation.

Large reports are represented as jobs so an API request never has to hold a
large rendering operation open.  The in-process queue is suitable locally;
deployments should call ``run_pending_jobs`` from the outbox/worker process.
"""

from __future__ import annotations

import csv
import html
import io
import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.app.csv_safe import safe_cell

# The twelve governed reports. Their content comes from the organization's records (reports/content.py); this module
# renders it. The catalog endpoint lists exactly these, so a report cannot be offered without a renderer.
REPORTS = {
    "PRODUCT_INTELLIGENCE": "Product Intelligence Report",
    "PRODUCT_VERSION_IMPACT": "ProductVersion Impact Report",
    "COMPLAINT_TREND": "Complaint Trend Report",
    "SIGNAL_ASSESSMENT": "Signal Assessment Report",
    "INVESTIGATION": "Investigation Report",
    "EVIDENCE_PROVENANCE": "Evidence & Provenance Report",
    "RISK_IMPACT": "Risk Impact Report",
    "SCENARIO_COMPARISON": "Scenario Comparison Report",
    "DECISION_BRIEF": "Decision Brief",
    "AI_ASSURANCE": "AI Assurance Report",
    "AUDIT_APPROVAL": "Audit & Approval Report",
    "EXECUTIVE_QUALITY_REVIEW": "Executive Quality Review",
}
# 2.0: reports carry the organization's records (1.0 rendered only a header and the request context).
REPORT_VERSION = "2.0"
FORMATS = {"JSON", "CSV", "PDF", "WORD", "DOC", "ESTAR_XML"}
HUMAN_REVIEW_NOTICE = (
    "Human review required: this report summarizes records; it does not establish causality or replace approval."
)
_jobs: dict[str, dict] = {}
_lock = threading.RLock()

# Keys that the PDF prints in its title block (or not at all) rather than as body sections.
_PDF_HEADER_KEYS = frozenset(
    {
        "title",
        "tenant_id",
        "tenant",
        "report_type",
        "report_version",
        "generated_at",
        "data_cut_off",
        "watermark",
        "human_review_required",
        "status",
        "format",
        "content",
        "content_type",
    }
)
# Report metadata rows at the top of a CSV, in this order.
_CSV_META_KEYS = (
    "report_type",
    "title",
    "tenant_id",
    "tenant_name",
    "report_version",
    "status",
    "generated_at",
    "data_cut_off",
    "human_review_required",
    "watermark",
)


def _safe_data(value, hidden: set[str]):
    if isinstance(value, dict):
        return {k: _safe_data(v, hidden) for k, v in value.items() if k not in hidden}
    if isinstance(value, list):
        return [_safe_data(v, hidden) for v in value]
    return value


def _heading(key: str) -> str:
    return str(key).replace("_", " ").strip().capitalize()


def _render_pdf(data: dict, watermark: str) -> bytes:
    """Every part of ``data`` as a paginated PDF (reports/pdf.py): the title block, then one section per key.

    ``context`` (the report content: audit events, signatures, tables) is expanded section by section, so an
    evidence package lists every event and signature, not just a header. Also used by the eSTAR preparation package
    (regulatory_intelligence/estar.py), whose ``data`` has its own keys (sections, citation_verification, ...).
    """
    from reports import pdf

    tenant = data.get("tenant") if isinstance(data.get("tenant"), dict) else {}
    organization = tenant.get("name") or data.get("tenant_id") or "-"
    header = [f"Organization: {organization}" + (f" ({data['tenant_id']})" if tenant.get("name") else "")]
    if data.get("report_type"):
        header.append(f"Report: {data['report_type']}  version {data.get('report_version', '-')}")
    elif data.get("report_version"):
        header.append(f"Version: {data['report_version']}")
    header.append(f"Generated: {data.get('generated_at', '-')}")
    if data.get("data_cut_off"):
        header.append(f"Data cut-off: {data['data_cut_off']}")
    header.append(HUMAN_REVIEW_NOTICE)
    body: list = []
    for key, value in data.items():
        if key in _PDF_HEADER_KEYS:
            continue
        sections = value.items() if key == "context" and isinstance(value, dict) else [(key, value)]
        for name, item in sections:
            if name == "data_cut_off":
                continue
            body.append((_heading(name), "heading"))
            body.extend(pdf.flatten(item))
            body.append(("", "body"))
    footer = f"{organization} - {data.get('report_type') or data.get('title', '')} - generated {data.get('generated_at', '')}"
    return pdf.render(f"MDARIX {data.get('title', 'report')}", header, body, watermark=watermark, footer=footer)


def _csv_value(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str, sort_keys=True)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _render_csv(data: dict) -> str:
    """The report as stacked CSV tables: metadata rows first, then one block per content section.

    A section that is a list of records becomes a table (one column per field); a mapping becomes field/value rows.
    Every cell goes through ``csv_safe.safe_cell`` so no value is run as a spreadsheet formula.
    """
    out = io.StringIO()
    writer = csv.writer(out)

    def row(*cells):
        writer.writerow([safe_cell(_csv_value(cell)) for cell in cells])

    row("field", "value")
    tenant = data.get("tenant") if isinstance(data.get("tenant"), dict) else {}
    meta = {**data, "tenant_name": tenant.get("name")}
    for key in _CSV_META_KEYS:
        if meta.get(key) is not None:
            row(key, meta[key])
    row("limitations", data.get("limitations", []))
    context = data.get("context") if isinstance(data.get("context"), dict) else {}
    for section, value in context.items():
        if section == "data_cut_off":
            continue
        writer.writerow([])
        row(f"[{section}]")
        if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            fields = list(dict.fromkeys(key for item in value for key in item))
            row(*fields)
            for item in value:
                row(*[item.get(field) for field in fields])
        elif isinstance(value, dict):
            for key, item in value.items():
                row(key, item)
        elif isinstance(value, list):
            for item in value:
                row(item)
        else:
            row(value)
    return out.getvalue()


def _render_word(data: dict) -> bytes:
    """Render a portable Word-compatible document without a server dependency.

    Word opens this standards-based HTML document directly.  Keeping the
    renderer dependency-free makes local and CI export tests deterministic;
    customers can replace the template with a signed DOCX renderer later.
    """
    rows = []
    for key, value in data.items():
        if key == "content":
            continue
        rendered = json.dumps(value, default=str, indent=2) if isinstance(value, (dict, list)) else str(value)
        rows.append(f"<tr><th>{html.escape(str(key))}</th><td><pre>{html.escape(rendered)}</pre></td></tr>")
    document = (
        """<!DOCTYPE html><html><head><meta charset="utf-8"><title>MDARIX report</title>
    <style>body{font-family:Arial;color:#102f45}h1{border-bottom:2px solid #087f7b}table{border-collapse:collapse;width:100%}th,td{border:1px solid #b8cbd4;padding:8px;text-align:left;vertical-align:top}th{width:22%;background:#eef7f7}pre{white-space:pre-wrap;font-family:Arial}.watermark{color:#087f7b;font-weight:bold}</style>
    </head><body><h1>MDARIX governed report</h1><p class="watermark">WATERMARK: """
        + html.escape(str(data["watermark"]))
        + "</p><table>"
        + "".join(rows)
        + "</table></body></html>"
    )
    return document.encode("utf-8")


def _render_estar_xml(data: dict) -> bytes:
    """Render MDARIX's auditable eSTAR handoff envelope.

    This is intentionally an interchange envelope, not a claim of FDA
    eSTAR submission-schema certification.  Official FDA templates must be
    supplied and version-pinned before production submission use.
    """
    from xml.etree.ElementTree import Element, SubElement, tostring

    root = Element("mdarix-estar-handoff", {"schema-version": "internal-1.0"})
    for name in ("report_type", "report_version", "tenant_id", "generated_at", "watermark"):
        SubElement(root, name).text = str(data.get(name, ""))
    SubElement(root, "official-fda-schema-validation").text = "NOT_PERFORMED"
    context = SubElement(root, "context-json")
    context.text = json.dumps(data.get("context", {}), default=str, sort_keys=True)
    return b'<?xml version="1.0" encoding="UTF-8"?>' + tostring(root, encoding="utf-8")


def generate_report(
    code: str,
    tenant_id: str,
    *,
    context: dict | None = None,
    output_format: str = "JSON",
    hidden_fields: set[str] | None = None,
    watermark: str | None = None,
    tenant_name: str | None = None,
) -> dict:
    """Render report ``code`` for one organization. ``context`` is its content (reports/content.py builds it from the
    organization's records); its ``data_cut_off`` is the instant those records were read."""
    if code not in REPORTS:
        raise ValueError("REPORT_TYPE_NOT_SUPPORTED")
    fmt = output_format.upper()
    if fmt not in FORMATS:
        raise ValueError("REPORT_FORMAT_NOT_SUPPORTED")
    generated = datetime.now(timezone.utc).isoformat()
    content = _safe_data(context or {}, hidden_fields or set())
    data = {
        "report_type": code,
        "title": REPORTS[code],
        "tenant_id": str(tenant_id),
        "tenant": {"id": str(tenant_id), "name": tenant_name},
        "report_version": REPORT_VERSION,
        "status": "READY_FOR_REVIEW",
        "generated_at": generated,
        "data_cut_off": content.get("data_cut_off"),
        "context": content,
        "limitations": ["Report is a governed summary; it does not establish causality or replace human approval."],
        "human_review_required": True,
    }
    data["watermark"] = watermark or f"MDARIX CONTROLLED COPY · {tenant_name or tenant_id} · v{REPORT_VERSION}"
    return _render(data, fmt)


def _render(data: dict, fmt: str) -> dict:
    if fmt == "CSV":
        data["content_type"], data["content"] = "text/csv", _render_csv(data)
    elif fmt == "PDF":
        data["content_type"], data["content"] = "application/pdf", _render_pdf(data, data["watermark"])
    elif fmt in {"WORD", "DOC"}:
        data["content_type"], data["content"] = "application/msword", _render_word(data)
    elif fmt == "ESTAR_XML":
        data["content_type"], data["content"] = "application/xml", _render_estar_xml(data)
    data["format"] = fmt
    return data


def render_investigation_record(record: dict, tenant_id: str, *, output_format: str, tenant_name: str | None = None):
    """The investigation record (reports/content.py:investigation_record) as JSON, CSV or PDF, with the same title
    block, watermark and human-review notice as the governed reports."""
    fmt = output_format.upper()
    if fmt not in {"JSON", "CSV", "PDF"}:
        raise ValueError("REPORT_FORMAT_NOT_SUPPORTED")
    case = record.get("investigation") or {}
    generated = datetime.now(timezone.utc).isoformat()
    data = {
        "report_type": "INVESTIGATION_RECORD",
        "title": f"Investigation Record {case.get('business_id') or case.get('investigation_identifier') or case.get('id')}",
        "tenant_id": str(tenant_id),
        "tenant": {"id": str(tenant_id), "name": tenant_name},
        "report_version": REPORT_VERSION,
        "status": "READY_FOR_REVIEW",
        "generated_at": generated,
        "data_cut_off": generated,
        "context": record,
        "limitations": ["The record lists what is stored; it does not establish causality or replace human approval."],
        "human_review_required": True,
        "watermark": f"MDARIX CONTROLLED COPY · {tenant_name or tenant_id} · v{REPORT_VERSION}",
    }
    return _render(data, fmt)


# A report stored in object storage records its key with this prefix; older reports hold a file path.
OBJECT_PREFIX = "object:"


def read_report_artifact(tenant_id: str, path: str) -> bytes:
    """The bytes of a generated report, from object storage (or, for reports made before, the file path)."""
    if path.startswith(OBJECT_PREFIX):
        from object_storage.service import ObjectStorageService

        return ObjectStorageService().get(str(tenant_id), path[len(OBJECT_PREFIX) :])
    return Path(path).read_bytes()


def _job_dict(job):
    if isinstance(job, dict):
        return dict(job)
    return {
        "id": str(job.id),
        "business_id": job.business_id,
        "tenant_id": str(job.tenant_id),
        "actor_id": job.actor_id,
        "code": job.report_code,
        "format": job.output_format,
        "context": job.context or {},
        "hidden_fields": set(job.hidden_fields or []),
        "status": job.status,
        "attempts": job.attempts,
        "path": job.artifact_path,
        "content_type": job.content_type,
        "report_version": job.report_version,
        "last_error": job.last_error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


def submit_report_job(
    code: str,
    tenant_id: str,
    *,
    actor_id: str,
    output_format: str = "PDF",
    context: dict | None = None,
    hidden_fields: set[str] | None = None,
    db=None,
    control_db=None,
    tenant_name: str | None = None,
) -> dict:
    """Queue report ``code`` and render it now. With ``db`` (the organization's data plane) the job is a durable
    ``ReportJob`` and the content is read from that plane when it renders; ``control_db`` adds the signatures and the
    audit trail, which live in the control plane (a job the worker renders later has no control-plane session)."""
    if code not in REPORTS:
        raise ValueError("REPORT_TYPE_NOT_SUPPORTED")
    if output_format.upper() not in FORMATS:
        raise ValueError("REPORT_FORMAT_NOT_SUPPORTED")
    job_id = str(uuid.uuid4())
    if db is not None:
        from backend.app.db.models.reporting import ReportJob

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        job = ReportJob(
            id=uuid.UUID(job_id),
            tenant_id=uuid.UUID(str(tenant_id)),
            actor_id=str(actor_id),
            report_code=code,
            output_format=output_format.upper(),
            context=context or {},
            hidden_fields=list(hidden_fields or set()),
            status="QUEUED",
            attempts=0,
            report_version=REPORT_VERSION,
            created_at=now,
            updated_at=now,
        )
        db.add(job)
        db.commit()
        return run_report_job(job_id, db=db, control_db=control_db, tenant_name=tenant_name)
    with _lock:
        _jobs[job_id] = {
            "id": job_id,
            "tenant_id": str(tenant_id),
            "actor_id": str(actor_id),
            "code": code,
            "format": output_format.upper(),
            "context": context or {},
            "hidden_fields": hidden_fields or set(),
            "status": "QUEUED",
            "attempts": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    return run_report_job(job_id)


def run_report_job(job_id: str, *, max_attempts: int = 3, db=None, control_db=None, tenant_name=None) -> dict:
    if db is not None:
        from reports.content import BUILDERS, build_report_context

        from backend.app.db.models.reporting import ReportJob

        job = db.query(ReportJob).filter(ReportJob.id == uuid.UUID(str(job_id))).with_for_update().one_or_none()
        if not job:
            raise ValueError("REPORT_JOB_NOT_FOUND")
        if job.status == "READY":
            return _job_dict(job)
        job.status = "RUNNING"
        job.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
        for attempt in range(job.attempts + 1, max_attempts + 1):
            try:
                # The content is read when the job renders, so the data cut-off is the moment of rendering.
                context = dict(job.context or {})
                if job.report_code in BUILDERS:
                    context.update(build_report_context(db, job.tenant_id, job.report_code, control_db=control_db))
                result = generate_report(
                    job.report_code,
                    str(job.tenant_id),
                    context=context,
                    output_format=job.output_format,
                    hidden_fields=set(job.hidden_fields or []),
                    tenant_name=tenant_name,
                )
                suffix = {
                    "PDF": ".pdf",
                    "CSV": ".csv",
                    "JSON": ".json",
                    "WORD": ".doc",
                    "DOC": ".doc",
                    "ESTAR_XML": ".xml",
                }[job.output_format]
                payload = (
                    result["content"]
                    if isinstance(result.get("content"), (bytes, str))
                    else json.dumps(result, default=str)
                )
                content_type = result.get("content_type", "application/json")
                # Encrypted, tenant-scoped object storage, readable by every API and worker instance and backed up.
                from object_storage.service import ObjectStorageService

                stored = ObjectStorageService().put(
                    str(job.tenant_id),
                    f"reports/{job.id}{suffix}",
                    payload if isinstance(payload, bytes) else payload.encode(),
                    content_type=content_type,
                    internal=True,
                )
                job.status = "READY"
                job.attempts = attempt
                job.artifact_path = OBJECT_PREFIX + stored["object_key"]
                job.content_type = content_type
                job.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                db.commit()
                return _job_dict(job)
            except Exception as exc:
                # A failed query leaves the transaction aborted: roll back before recording the attempt.
                db.rollback()
                job = db.query(ReportJob).filter(ReportJob.id == uuid.UUID(str(job_id))).one()
                job.attempts = attempt
                job.last_error = type(exc).__name__
                db.commit()
        job.status = "FAILED"
        job.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
        return _job_dict(job)
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            raise ValueError("REPORT_JOB_NOT_FOUND")
        if job["status"] == "READY":
            return job
        job["status"] = "RUNNING"
    for attempt in range(job["attempts"] + 1, max_attempts + 1):
        try:
            result = generate_report(
                job["code"],
                job["tenant_id"],
                context=job["context"],
                output_format=job["format"],
                hidden_fields=job["hidden_fields"],
            )
            # Keep generated bytes tenant-isolated and outside the source tree.
            directory = (
                Path(os.getenv("MDARIX_REPORT_TEMP_ROOT", tempfile.gettempdir())) / "mdarix-reports" / job["tenant_id"]
            )
            directory.mkdir(parents=True, exist_ok=True)
            suffix = {
                "PDF": ".pdf",
                "CSV": ".csv",
                "JSON": ".json",
                "WORD": ".doc",
                "DOC": ".doc",
                "ESTAR_XML": ".xml",
            }[job["format"]]
            path = directory / f"{job_id}{suffix}"
            payload = (
                result["content"]
                if isinstance(result.get("content"), (bytes, str))
                else json.dumps(result, default=str)
            )
            path.write_bytes(payload if isinstance(payload, bytes) else payload.encode())
            with _lock:
                job.update(
                    {
                        "status": "READY",
                        "attempts": attempt,
                        "path": str(path),
                        "content_type": result["content_type"] if "content_type" in result else "application/json",
                        "report_version": REPORT_VERSION,
                    }
                )
            return job
        except Exception as exc:
            with _lock:
                job.update({"attempts": attempt, "last_error": type(exc).__name__})
    with _lock:
        job["status"] = "FAILED"
    return job


def get_report_job(job_id: str, tenant_id: str, db=None) -> dict:
    if db is not None:
        from backend.app.db.models.reporting import ReportJob

        job = (
            db.query(ReportJob)
            .filter(ReportJob.id == uuid.UUID(str(job_id)), ReportJob.tenant_id == uuid.UUID(str(tenant_id)))
            .one_or_none()
        )
        if not job:
            raise ValueError("REPORT_JOB_NOT_FOUND")
        return _job_dict(job)
    with _lock:
        job = _jobs.get(job_id)
        if not job or job["tenant_id"] != str(tenant_id):
            raise ValueError("REPORT_JOB_NOT_FOUND")
        return dict(job)


def run_pending_report_jobs(db, *, limit: int = 10, tenant_id=None) -> dict:
    """Claim and process queued jobs safely for one tenant data plane (only `tenant_id`'s jobs when given)."""
    from backend.app.db.models.reporting import ReportJob

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    # Recover a claim left behind by a terminated worker. The timeout is
    # intentionally conservative so a slow render is not double-processed.
    stale_before = now - __import__("datetime").timedelta(minutes=15)
    tenant_filter = [ReportJob.tenant_id == tenant_id] if tenant_id is not None else []
    db.query(ReportJob).filter(
        ReportJob.status == "CLAIMED", ReportJob.updated_at < stale_before, *tenant_filter
    ).update({ReportJob.status: "QUEUED", ReportJob.updated_at: now}, synchronize_session=False)
    db.commit()
    rows = (
        db.query(ReportJob)
        .filter(ReportJob.status == "QUEUED", *tenant_filter)
        .order_by(ReportJob.created_at)
        .with_for_update(skip_locked=True)
        .limit(limit)
        .all()
    )
    ids = [str(row.id) for row in rows]
    for row in rows:
        row.status = "CLAIMED"
        row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    ready = failed = 0
    for job_id in ids:
        result = run_report_job(job_id, db=db)
        if result["status"] == "READY":
            ready += 1
        elif result["status"] == "FAILED":
            failed += 1
    return {"claimed": len(ids), "ready": ready, "failed": failed}
