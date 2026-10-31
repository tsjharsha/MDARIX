"""Versions of the ready-to-use documents (T-G35): generated, written, signed, filed. No migration: a version is a
``report_jobs`` row (``report_code`` the template's code, ``status`` DRAFT or SIGNED, ``context`` the period, cut-off,
template version, the data sections as generated, the judgement texts with their writers, and once signed the
signature and the filing reference) and its signature a ``signed_approval_records`` row whose content fingerprint is
the signed PDF's SHA-256. The signed PDF is kept in object storage, so the file filed in the QMS is always the one
downloaded again. A signed version is never edited: a new generation is the next version.

Design note (T-B2): the MVP adds the customer's approved template versions (G15's version control), the enforced
separation of writer and signer (G33), the minutes field feeding G34 and the filing reference as in G28, on this row.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.db.models.reporting import ReportJob
from backend.app.qms_documents import content, templates
from backend.app.standards import STARTER_MARK

DRAFT, SIGNED = "DRAFT", "SIGNED"
FORMAT = "PDF"
FOOTER_NOTE = (
    "MDARIX fills the data sections from your records and never writes a judgement section. MDARIX submits nothing "
    "to a regulator: you file this document in your QMS."
)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def today_utc() -> date:
    return now_utc().date()


def _iso(value) -> str | None:
    return value.isoformat(timespec="seconds") if value else None


def build(
    db: Session,
    tenant_id: uuid.UUID,
    template: templates.Template,
    *,
    period_days: int,
    today: date,
    target,
    control_db,
) -> dict:
    """The document's data as generated now: its sections (judgement sections empty) and its scope."""
    from backend.app.readiness_home.summary import management_review

    builders = {
        "MANAGEMENT_REVIEW": management_review,
        "CAPA_LOG": content.capa_log,
        "INVESTIGATION_REPORT": content.investigation_report,
        "RISK_REVIEW_EXTRACT": content.risk_review_extract,
        "CHANGE_IMPACT": content.change_impact,
    }
    target_arg = {templates.CASE: {"case": target}, templates.CHANGE: {"change": target}}.get(template.scope, {})
    return builders[template.code](
        db, tenant_id, period_days=period_days, today=today, control_db=control_db, **target_arg
    )


def source_ids(sections: list[dict]) -> list[str]:
    return sorted(
        {
            source[field]
            for section in sections
            for item in section.get("rows") or []
            for source in item.get("sources") or []
            for field in ("id", "case")
            if source.get(field)
        }
    )


def generate(
    db: Session,
    tenant_id: uuid.UUID,
    actor: str,
    template: templates.Template,
    *,
    period_days: int,
    target=None,
    control_db=None,
    practice_label: str | None = None,
) -> ReportJob:
    """A new draft version: the data sections generated now, for the period (organization documents) or the case or
    change record named, with the next version number of that document."""
    now = now_utc()
    today = now.date()
    built = build(db, tenant_id, template, period_days=period_days, today=today, target=target, control_db=control_db)
    scope = built.get("scope") or {}
    scope_id = (scope.get("case") or scope.get("change") or {}).get("id")
    version = (
        int(
            db.query(func.count(ReportJob.id))
            .filter(
                ReportJob.tenant_id == tenant_id,
                ReportJob.report_code == template.code,
                ReportJob.context["scope_id"].astext == scope_id
                if scope_id
                else ReportJob.context["scope_id"].astext.is_(None),
            )
            .scalar()
            or 0
        )
        + 1
    )
    period = None
    if template.scope == templates.ORGANIZATION:
        start = today.toordinal() - period_days + 1
        period = {"from": date.fromordinal(start).isoformat(), "to": today.isoformat(), "days": period_days}
    job = ReportJob(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        actor_id=str(actor),
        report_code=template.code,
        output_format=FORMAT,
        context={
            "version": version,
            "template_version": template.version,
            "period": period,
            "cut_off": _iso(now),
            "scope": scope,
            "scope_id": scope_id,
            "sections": built["sections"],
            "figures": built.get("figures"),
            "source_ids": source_ids(built["sections"]),
            "practice_label": practice_label,
            "judgement": {},
        },
        hidden_fields=[],
        status=DRAFT,
        attempts=0,
        report_version=template.version,
        created_at=now.replace(tzinfo=None),
        updated_at=now.replace(tzinfo=None),
    )
    db.add(job)
    db.flush()
    return job


def versions(
    db: Session, tenant_id: uuid.UUID, code: str | None = None, scope_id: str | None = None
) -> list[ReportJob]:
    query = db.query(ReportJob).filter(ReportJob.tenant_id == tenant_id, ReportJob.report_code.in_(templates.CODES))
    if code:
        query = query.filter(ReportJob.report_code == code)
    if scope_id:
        query = query.filter(ReportJob.context["scope_id"].astext == scope_id)
    return query.order_by(ReportJob.created_at.desc()).all()


def version_of(db: Session, tenant_id: uuid.UUID, version_id, *, lock: bool = False) -> ReportJob | None:
    try:
        key = uuid.UUID(str(version_id))
    except (TypeError, ValueError):
        return None
    query = db.query(ReportJob).filter(
        ReportJob.tenant_id == tenant_id, ReportJob.id == key, ReportJob.report_code.in_(templates.CODES)
    )
    return (query.with_for_update() if lock else query).one_or_none()


def judgement_problem(template: templates.Template, key: str, text: str) -> str | None:
    if key not in {item.key for item in template.judgements}:
        return templates.DATA_NOTE
    if len(text) < templates.JUDGEMENT_MIN:
        return f"Write the section in at least {templates.JUDGEMENT_MIN} characters"
    return None


def write_judgement(job: ReportJob, key: str, text: str, actor: str) -> None:
    context = dict(job.context)
    context["judgement"] = {
        **(context.get("judgement") or {}),
        key: {"text": text, "written_by": str(actor), "written_at": _iso(now_utc())},
    }
    job.context = context
    job.updated_at = now_utc().replace(tzinfo=None)


def unwritten(template: templates.Template, job: ReportJob) -> list[str]:
    written = job.context.get("judgement") or {}
    return [item.title for item in template.judgements if not (written.get(item.key) or {}).get("text")]


def signed_material(job: ReportJob, signer: str, signed_at: str) -> dict:
    """What the signature covers: the template and its version, the period and cut-off, the data sections as
    generated, each judgement text with its writer, the signer and the moment."""
    context = job.context
    return {
        "document": job.report_code,
        "document_id": str(job.id),
        "version": context["version"],
        "template_version": context["template_version"],
        "period": context.get("period"),
        "cut_off": context["cut_off"],
        "scope": context.get("scope"),
        "sections": context["sections"],
        "judgement": {
            key: {"text": item["text"], "written_by": item["written_by"]}
            for key, item in (context.get("judgement") or {}).items()
        },
        "signer": signer,
        "signed_at": signed_at,
        "practice_label": context.get("practice_label"),
    }


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _scope_ref(context: dict) -> str | None:
    scope = context.get("scope") or {}
    if scope.get("case"):
        return f"case {scope['case']['ref']}"
    if scope.get("change"):
        return f"change record {scope['change']['ref']}"
    return None


def superseded_by(rows: list[ReportJob], job: ReportJob) -> int | None:
    """The version that supersedes a signed one: the next signed version of the same document."""
    if job.status != SIGNED:
        return None
    later = [
        row.context["version"]
        for row in rows
        if row.status == SIGNED
        and row.report_code == job.report_code
        and row.context.get("scope_id") == job.context.get("scope_id")
        and row.context["version"] > job.context["version"]
    ]
    return min(later) if later else None


def summary_of(job: ReportJob, names: dict[str, str], newer: int | None = None) -> dict:
    template = templates.TEMPLATES[job.report_code]
    context = job.context
    signature = context.get("signature") or {}
    return {
        "id": str(job.id),
        "business_id": job.business_id,
        "code": job.report_code,
        "title": template.title,
        "version": context["version"],
        "status": job.status,
        "template_version": context["template_version"],
        "period": context.get("period"),
        "cut_off": context["cut_off"],
        "scope": context.get("scope") or {},
        "scope_ref": _scope_ref(context),
        "generated_by": names.get(job.actor_id) or "A colleague",
        "generated_at": context["cut_off"],
        "signed_by": names.get(signature.get("signer_user_id")) if signature else None,
        "signed_at": signature.get("signed_at"),
        "superseded_by": newer,
        "filing": context.get("filing"),
    }


def writer_note(job: ReportJob, names: dict[str, str], trial: bool) -> str | None:
    signature = job.context.get("signature")
    writers = sorted({item["written_by"] for item in (job.context.get("judgement") or {}).values()})
    if not signature or not writers:
        return None
    if writers == [signature["signer_user_id"]]:
        return "Writer of the judgement sections and signer: same person" + (
            " (allowed in a trial; a pilot separates them)." if trial else "."
        )
    return (
        "Judgement sections written by "
        + ", ".join(names.get(writer, "a colleague") for writer in writers)
        + f"; signed by {names.get(signature['signer_user_id'], 'a colleague')}."
    )


def view_of(job: ReportJob, names: dict[str, str], *, organization: str | None, trial: bool, newer=None) -> dict:
    """Everything the screen, the PDF and the DOCX show of one version."""
    template = templates.TEMPLATES[job.report_code]
    context = job.context
    judgement = {
        key: {**item, "written_by_name": names.get(item["written_by"]) or "A colleague"}
        for key, item in (context.get("judgement") or {}).items()
    }
    signature = context.get("signature")
    if signature:
        signature = {**signature, "signer_name": names.get(signature["signer_user_id"]) or "A colleague"}
    return {
        **summary_of(job, names, newer),
        "organization": organization,
        "clauses": template.clause_list(),
        "purpose": template.purpose,
        "sections": context["sections"],
        "judgement": judgement,
        "signature": signature,
        "writer_note": writer_note(job, names, trial),
        "practice_label": context.get("practice_label"),
        "starter_mark": STARTER_MARK,
        "data_note": templates.DATA_NOTE,
        "footer_note": FOOTER_NOTE,
        "editable": job.status == DRAFT,
    }


def people_of(job_list: list[ReportJob]) -> set[str]:
    refs: set[str] = set()
    for job in job_list:
        refs.add(job.actor_id)
        refs |= {item["written_by"] for item in (job.context.get("judgement") or {}).values()}
        if job.context.get("signature"):
            refs.add(job.context["signature"]["signer_user_id"])
    return refs


def signed_count(db: Session, tenant_id: uuid.UUID) -> int:
    """Signed versions of the five documents (the trial story's chapter 9)."""
    return int(
        db.query(func.count(ReportJob.id))
        .filter(
            ReportJob.tenant_id == tenant_id, ReportJob.report_code.in_(templates.CODES), ReportJob.status == SIGNED
        )
        .scalar()
        or 0
    )
