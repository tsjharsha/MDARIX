"""Ready-to-use documents API (T-G35, T-G35.1-.5): the management review report, the CAPA log, the investigation
report, the risk-review extract and the change-impact input.

- ``GET /api/v1/documents/types``: the five templates with their clauses, and the cases and change records to choose;
- ``GET /api/v1/documents``: the versions (``code``, ``scope_id`` to narrow);
- ``POST /api/v1/documents``: generate a new draft version from the records now (an export: data.export);
- ``GET /api/v1/documents/{id}``: one version, every row with its source records;
- ``PUT /api/v1/documents/{id}/judgement/{key}``: write a judgement section of a draft (a data section is never
  edited: the record is corrected and the document generated again);
- ``POST /api/v1/documents/{id}/sign``: sign with password and, when signatures require it, an authenticator code;
  the PDF is rendered once, kept, and its SHA-256 recorded in the signature record;
- ``PUT /api/v1/documents/{id}/filing``: the QMS filing reference and the minutes spent, on a signed version;
- ``GET /api/v1/documents/{id}/pdf`` and ``/docx``: the files (the signed PDF exactly as signed).

A signed version is never edited; a new generation is the next version. MDARIX never writes a judgement section and
submits nothing. These routes serve a free trial and a pilot alike: they stay out of mvp-1.0's ``_PILOT_API`` gate
(T-B1).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.downloads import attachment
from backend.app.access.permissions import DATA_EXPORT, QUALITY_REVIEW, require_permission
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import Change, Investigation, SignedApprovalRecord
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.qms_documents import content, render, service, templates
from backend.app.request_context import AuthenticatedRequestContext, get_request_context

router = APIRouter(prefix="/api/v1/documents", tags=["Ready-to-use documents"])

OBJECT_TYPE = "QmsDocumentVersion"
DECISION_TYPE = "QMS_DOCUMENT"
ADMINISTRATOR_ROLES = frozenset({"PLATFORM_ADMIN", "ADMIN", "ADMINISTRATOR", "CUSTOMER_ADMIN"})
CHOICES_MAX = 200
MEDIA = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _error(status: int, code: str, message: str, **extra) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message, **extra})


def _organization(control_db: Session, tenant_id) -> str | None:
    from backend.app.stage3_workflow_router import _organization_name

    return _organization_name(control_db, tenant_id)


def _trial(control_db: Session, tenant_id) -> bool:
    from backend.app.signer_training.router import is_trial

    return is_trial(control_db, tenant_id)


def _names(control_db: Session, tenant_id, jobs) -> dict[str, str]:
    from backend.app.complaint_review.service import people

    return people(control_db, tenant_id, service.people_of(jobs))


def _view(db, control_db, tenant_id, job) -> dict:
    rows = service.versions(db, tenant_id, job.report_code, job.context.get("scope_id"))
    return service.view_of(
        job,
        _names(control_db, tenant_id, [job]),
        organization=_organization(control_db, tenant_id),
        trial=_trial(control_db, tenant_id),
        newer=service.superseded_by(rows, job),
    )


def _audit(control_db, ctx, action: str, job, **details) -> None:
    control_db.add(
        make_audit_event(
            tenant_id=uuid.UUID(ctx.tenant_id),
            actor_ref=ctx.user_id,
            action=action,
            entity_type="QmsDocument",
            entity_id=job.id,
            correlation_id=ctx.correlation_id,
            details={"document": job.report_code, "version": job.context.get("version"), **details},
        )
    )


def _found(db, ctx, version_id, *, lock: bool = False):
    job = service.version_of(db, uuid.UUID(ctx.tenant_id), version_id, lock=lock)
    if job is None:
        raise _error(404, "DOCUMENT_NOT_FOUND", "No such document in your organization")
    return job


@router.get("/types")
def document_types(
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    from backend.app.reportability.markets import PRACTICE_LABEL

    tenant_id = uuid.UUID(ctx.tenant_id)
    cases = (
        db.query(
            Investigation.id,
            Investigation.business_id,
            Investigation.investigation_identifier,
            Investigation.investigation_question,
        )
        .filter(Investigation.tenant_id == tenant_id)
        .order_by(Investigation.investigation_identifier)
        .limit(CHOICES_MAX)
        .all()
    )
    changes = (
        db.query(Change.id, Change.change_identifier, Change.change_type)
        .filter(Change.tenant_id == tenant_id)
        .order_by(Change.change_identifier)
        .limit(CHOICES_MAX)
        .all()
    )
    return {
        "templates": [template.as_dict() for template in templates.TEMPLATES.values()],
        "cases": [
            {
                "id": str(row.id),
                "ref": row.business_id or row.investigation_identifier,
                "identifier": row.investigation_identifier,
                "question": row.investigation_question,
            }
            for row in cases
        ],
        "changes": [{"id": str(row.id), "ref": row.change_identifier, "type": row.change_type} for row in changes],
        "periods": list(templates.PERIODS),
        "default_period": templates.PERIOD_DEFAULT,
        "practice_label": PRACTICE_LABEL if _trial(control_db, tenant_id) else None,
        "written_by_manufacturer": templates.WRITTEN_BY_MANUFACTURER,
        "data_note": templates.DATA_NOTE,
    }


@router.get("")
def document_versions(
    code: str | None = Query(default=None, max_length=40),
    scope_id: uuid.UUID | None = None,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = uuid.UUID(ctx.tenant_id)
    rows = service.versions(db, tenant_id, (code or "").upper() or None, str(scope_id) if scope_id else None)
    names = _names(control_db, tenant_id, rows)
    return {"items": [service.summary_of(row, names, service.superseded_by(rows, row)) for row in rows]}


class GenerateRequest(BaseModel):
    code: str = Field(max_length=40)
    period_days: int = Field(default=templates.PERIOD_DEFAULT, ge=templates.PERIOD_MIN, le=templates.PERIOD_MAX)
    case_id: uuid.UUID | None = None
    change_id: uuid.UUID | None = None


@router.post("", dependencies=[Depends(require_permission(DATA_EXPORT))])
def generate_document(
    payload: GenerateRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    from backend.app.reportability.markets import PRACTICE_LABEL

    tenant_id = uuid.UUID(ctx.tenant_id)
    template = templates.template_of(payload.code)
    if template is None:
        raise _error(400, "DOCUMENT_TYPE_NOT_SUPPORTED", "Choose one of the five documents")
    target = None
    if template.scope == templates.CASE:
        target = content.case_of(db, tenant_id, payload.case_id)
        if target is None:
            raise _error(422, "CASE_REQUIRED", "Choose the case this document is for")
    elif template.scope == templates.CHANGE:
        target = content.change_of(db, tenant_id, payload.change_id)
        if target is None:
            raise _error(422, "CHANGE_REQUIRED", "Choose the change record this document is for")
    job = service.generate(
        db,
        tenant_id,
        ctx.user_id,
        template,
        period_days=payload.period_days,
        target=target,
        control_db=control_db,
        practice_label=PRACTICE_LABEL if _trial(control_db, tenant_id) else None,
    )
    db.commit()
    _audit(
        control_db, ctx, "QMS_DOCUMENT_GENERATED", job, cut_off=job.context["cut_off"], period=job.context.get("period")
    )
    control_db.commit()
    return _view(db, control_db, tenant_id, job)


@router.get("/{version_id}")
def document_version(
    version_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    return _view(db, control_db, uuid.UUID(ctx.tenant_id), _found(db, ctx, version_id))


class JudgementRequest(BaseModel):
    text: str = Field(max_length=templates.JUDGEMENT_MAX * 2)


def _refuse_signed(job) -> None:
    if job.status != service.DRAFT:
        raise _error(
            409,
            "SIGNED_VERSION_NOT_EDITABLE",
            "A signed version is never edited: generate the document again for a new version",
        )


@router.put("/{version_id}/judgement/{key}", dependencies=[Depends(require_permission(QUALITY_REVIEW))])
def write_judgement(
    version_id: uuid.UUID,
    key: str,
    payload: JudgementRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    job = _found(db, ctx, version_id, lock=True)
    _refuse_signed(job)
    text = payload.text.strip()[: templates.JUDGEMENT_MAX]
    key = key.strip().upper()
    problem = service.judgement_problem(templates.TEMPLATES[job.report_code], key, text)
    if problem:
        raise _error(
            422, "DATA_SECTION_NOT_EDITABLE" if problem == templates.DATA_NOTE else "JUDGEMENT_TOO_SHORT", problem
        )
    service.write_judgement(job, key, text, ctx.user_id)
    db.commit()
    _audit(control_db, ctx, "QMS_DOCUMENT_JUDGEMENT_WRITTEN", job, section=key)
    control_db.commit()
    return _view(db, control_db, uuid.UUID(ctx.tenant_id), job)


class SignRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    mfa_code: str | None = Field(default=None, max_length=12)


@router.post("/{version_id}/sign", dependencies=[Depends(require_permission(QUALITY_REVIEW))])
def sign_document(
    version_id: uuid.UUID,
    payload: SignRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Sign a draft: every judgement section written first; then the PDF is rendered with the signature
    manifestation, stored, and its SHA-256 kept in the signature record."""
    from object_storage.service import ObjectStorageService
    from reports.service import OBJECT_PREFIX

    from backend.app.evidence_workflow.people import current_person
    from backend.app.governance_router import verify_signing_credentials
    from backend.app.human_decision.rules import fingerprint, signature_hash

    tenant_id = uuid.UUID(ctx.tenant_id)
    job = _found(db, ctx, version_id)
    _refuse_signed(job)
    template = templates.TEMPLATES[job.report_code]
    missing = service.unwritten(template, job)
    if missing:
        raise _error(
            422, "JUDGEMENT_NOT_WRITTEN", "Write these sections before signing: " + ", ".join(missing), missing=missing
        )
    person = current_person(control_db, ctx)
    role = person.role_for(QUALITY_REVIEW)
    if (role or "").upper() in ADMINISTRATOR_ROLES:
        raise _error(403, "ADMINISTRATOR_CANNOT_SIGN", "Administrators cannot sign documents")

    def refused(action: str) -> None:
        _audit(control_db, ctx, action, job, attempt="QMS_DOCUMENT_SIGN")

    # Re-authenticate first: a refusal commits the control session, so nothing else may be pending in it yet.
    verify_signing_credentials(
        control_db, ctx, password=payload.password, mfa_code=payload.mfa_code, record_refusal=refused
    )
    job = _found(db, ctx, version_id, lock=True)
    _refuse_signed(job)
    now = service.now_utc()
    signed_at = now.isoformat(timespec="seconds")
    material = service.signed_material(job, str(ctx.user_id), signed_at)
    content_fingerprint = fingerprint(material)
    record_id = uuid.uuid4()
    version = str(job.context["version"])
    meaning = templates.signature_meaning(template.title, job.context["version"], service._scope_ref(job.context))
    signature = {
        "record_id": str(record_id),
        "record_business_id": None,
        "signer_user_id": str(ctx.user_id),
        "signer_role": (role or "UNKNOWN").replace("_", " ").title(),
        "meaning": meaning,
        "signed_at": signed_at,
        "content_fingerprint": content_fingerprint,
    }
    context = {**job.context, "signature": signature}
    job.context = context
    view = service.view_of(
        job,
        _names(control_db, tenant_id, [job]),
        organization=_organization(control_db, tenant_id),
        trial=_trial(control_db, tenant_id),
    )
    pdf = render.render_pdf(view)
    pdf_sha256 = service.sha256(pdf)
    stored = ObjectStorageService().put(
        str(tenant_id), f"documents/{job.id}.pdf", pdf, content_type=render_media("pdf"), internal=True
    )
    record = SignedApprovalRecord(
        id=record_id,
        tenant_id=tenant_id,
        object_type=OBJECT_TYPE,
        object_id=job.id,
        object_version=version,
        decision_type=DECISION_TYPE,
        decision="SIGNED",
        remarks=f"{template.title} version {version}, {template.version}",
        signer_user_id=str(ctx.user_id),
        signer_role=role or "UNKNOWN",
        signature_meaning=meaning,
        content_fingerprint=pdf_sha256,
        signature_hash=signature_hash(pdf_sha256, str(ctx.user_id), version),
        status="SIGNED",
        signed_at=now,
        created_at=now,
    )
    control_db.add(record)
    control_db.flush()
    signature = {**signature, "pdf_sha256": pdf_sha256, "record_business_id": record.business_id}
    job.context = {**context, "signature": signature}
    job.status = service.SIGNED
    job.artifact_path = OBJECT_PREFIX + stored["object_key"]
    job.content_type = render_media("pdf")
    job.updated_at = now.replace(tzinfo=None)
    _audit(
        control_db,
        ctx,
        "QMS_DOCUMENT_SIGNED",
        job,
        signature_id=str(record_id),
        pdf_sha256=pdf_sha256,
        fingerprint=content_fingerprint,
        template_version=template.version,
    )
    control_db.commit()
    db.commit()
    return _view(db, control_db, tenant_id, job)


def render_media(kind: str) -> str:
    return MEDIA[kind]


class FilingRequest(BaseModel):
    qms_reference: str = Field(default="", max_length=120)
    minutes_spent: int | None = Field(default=None, ge=0, le=10000)


@router.put("/{version_id}/filing", dependencies=[Depends(require_permission(QUALITY_REVIEW))])
def record_filing(
    version_id: uuid.UUID,
    payload: FilingRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The QMS filing reference and the minutes spent: recorded beside a signed version, never inside it."""
    job = _found(db, ctx, version_id, lock=True)
    if job.status != service.SIGNED:
        raise _error(409, "NOT_SIGNED", "Sign the version first: only a signed version is filed")
    filing = {
        "qms_reference": " ".join(payload.qms_reference.split()) or None,
        "minutes_spent": payload.minutes_spent,
        "recorded_by": str(ctx.user_id),
        "recorded_at": service.now_utc().isoformat(timespec="seconds"),
    }
    job.context = {**job.context, "filing": filing}
    db.commit()
    _audit(control_db, ctx, "QMS_DOCUMENT_FILING_RECORDED", job, qms_reference=filing["qms_reference"])
    control_db.commit()
    return _view(db, control_db, uuid.UUID(ctx.tenant_id), job)


@router.get("/{version_id}/{kind}", dependencies=[Depends(require_permission(DATA_EXPORT))])
def download_document(
    version_id: uuid.UUID,
    kind: str,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    from reports.service import read_report_artifact

    kind = kind.lower()
    if kind not in MEDIA:
        raise _error(404, "FORMAT_NOT_SUPPORTED", "Download the PDF or the DOCX")
    tenant_id = uuid.UUID(ctx.tenant_id)
    job = _found(db, ctx, version_id)
    view = _view(db, control_db, tenant_id, job)
    if kind == "pdf" and job.status == service.SIGNED and job.artifact_path:
        body = read_report_artifact(str(tenant_id), job.artifact_path)
    else:
        body = render.render_pdf(view) if kind == "pdf" else render.render_docx(view)
    _audit(control_db, ctx, "QMS_DOCUMENT_DOWNLOADED", job, format=kind.upper())
    control_db.commit()
    stem = f"mdarix-{job.report_code.lower().replace('_', '-')}-v{job.context['version']}"
    return Response(
        content=body,
        media_type=MEDIA[kind],
        headers={"Content-Disposition": attachment(f"{stem}.{kind}")},
    )
