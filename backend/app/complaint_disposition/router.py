"""Complaint disposition API (T-G36, T-G36T, T-G36R, T-U13, T-G39).

- ``GET /api/v1/complaints/dispositions``: complaints waiting for a disposition (with the routine-path offer), or the
  signed dispositions;
- ``GET /api/v1/complaints/dispositions/trend``: service-level and known-issue resolutions beside the complaint counts;
- ``GET /api/v1/complaints/{id}/disposition``: the decision tree for one complaint, read now;
- ``POST /api/v1/complaints/{id}/disposition/sign``: sign one branch with password and, when signatures require it,
  an authenticator code, after a training record (in a trial a practice acknowledgement) on the current version of the
  disposition rules and the coding criteria. The signature confirms the classification; on the routine path it also
  covers a "not reportable" market conclusion on the routine basis for each enabled market. A trigger met at signing
  that was not met when the screen opened refuses the signature. Escalation opens a case at once (the existing
  open-case path); a known issue joins the case's scope through a new scope version. A signed version is never edited.

Reading is open to every signed-in member; signing needs the second look's permissions (triage, opening cases or
quality review). Administrators never sign. MDARIX never answers, never signs and never submits. These routes serve a
free trial and a pilot alike: they are not part of mvp-1.0's ``_PILOT_API`` gate (T-B1).
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app import mfa
from backend.app.access.permissions import INVESTIGATION_CREATE, QUALITY_REVIEW, SIGNAL_TRIAGE
from backend.app.complaint_classification import rules as coding
from backend.app.complaint_disposition import rules, service, triggers
from backend.app.complaint_review.service import people
from backend.app import signing_commit
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import AuthUser, Investigation, SignedApprovalRecord
from backend.app.db.models.complaint_disposition import ComplaintDisposition
from backend.app.db.models.market_assessment import ComplaintClassification, ComplaintMarketAssessment
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.evidence_workflow.people import current_person, require_any_permission
from backend.app.reportability import markets
from backend.app.reportability import rules as reporting_rules
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.signer_training import service as training
from backend.app.signer_training.router import is_trial
from backend.app.standards import STARTER_MARK, chips

logger = logging.getLogger("mdarix.complaint_disposition")
router = APIRouter(prefix="/api/v1/complaints", tags=["Complaint disposition"])

OBJECT_TYPE = "ComplaintDisposition"
DECISION_TYPE = "COMPLAINT_DISPOSITION"
ADMINISTRATOR_ROLES = frozenset({"PLATFORM_ADMIN", "ADMIN", "ADMINISTRATOR", "CUSTOMER_ADMIN"})
DECIDERS = Depends(require_any_permission(SIGNAL_TRIAGE, INVESTIGATION_CREATE, QUALITY_REVIEW))


def _error(status: int, code: str, message: str, **extra) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message, **extra})


class ServiceRecordIn(BaseModel):
    troubleshooting: str = Field(default="", max_length=rules.TEXT_MAX * 2)
    correction_type: str = Field(default="", max_length=30)
    correction: str = Field(default="", max_length=rules.TEXT_MAX * 2)
    result: str = Field(default="", max_length=rules.TEXT_MAX * 2)
    service_ticket: str = Field(default="", max_length=rules.TICKET_MAX * 2)
    no_investigation_rationale: str = Field(default="", max_length=rules.TEXT_MAX * 2)
    no_investigation_reason: str = Field(default="", max_length=40)
    device_returned: str = Field(default="", max_length=20)


class ClassificationIn(BaseModel):
    use_environment: str = Field(max_length=30)
    use_environment_text: str | None = Field(default=None, max_length=coding.TEXT_MAX * 2)
    user_type: str = Field(max_length=30)
    user_type_text: str | None = Field(default=None, max_length=coding.TEXT_MAX * 2)


class SignRequest(BaseModel):
    branch: str = Field(max_length=30)
    case_id: uuid.UUID | None = None
    rationale: str = Field(default="", max_length=rules.TEXT_MAX * 2)
    not_known_reason: str = Field(default="", max_length=rules.TEXT_MAX * 2)
    service_record: ServiceRecordIn | None = None
    attribution: str | None = Field(default=None, max_length=30)
    attribution_reason: str = Field(default="", max_length=rules.TEXT_MAX * 2)
    classification: ClassificationIn
    change_reason: str = Field(default="", max_length=rules.TEXT_MAX * 2)
    # What the person saw: the triggers met when the screen opened, the version current then, and when it opened.
    seen_triggers: list[str] = Field(default_factory=list, max_length=20)
    seen_version: int = Field(default=0, ge=0)
    routine: bool = False
    opened_at: str | None = Field(default=None, max_length=40)
    password: str = Field(min_length=1, max_length=128)
    mfa_code: str | None = Field(default=None, max_length=12)


def _reportability(db: Session, tenant_id: uuid.UUID, complaint_id, today: date) -> dict:
    """The complaint's per-market assessment state: a disposition never replaces it."""
    from backend.app.reportability import assessments
    from backend.app.reportability import service as reporting

    found = reporting.one(db, tenant_id, complaint_id, today)
    if found is None:
        return {"on_watch": False, "markets": [], "settled": True}
    complaint, record, seen, second_look = found
    on_watch = reporting_rules.watched(record) and reporting.counts_as_complaint(
        complaint.status, complaint.complaint_type, second_look
    )
    windows = reporting.settings_of(db, tenant_id)["windows"]
    aware = datetime.fromisoformat(seen["aware_at"]) if seen["aware_at"] else None
    by_market = assessments.rows_by_complaint(db, tenant_id, [complaint_id]).get(complaint_id, {})
    summary = (
        assessments.markets_summary(record, windows, by_market, aware, today, seen.get("org_zone")) if on_watch else []
    )
    settled = (not on_watch) or assessments.settled(summary) or bool(seen.get("decided"))
    return {
        "on_watch": on_watch,
        "markets": [
            {"market": item["market"], "label": item["label"], "state": item["state"], "clock": item["clock"]}
            for item in summary
        ],
        "settled": settled,
    }


def _routine_markets(facts: dict) -> list[str]:
    return [market for market in markets.MARKETS if market in facts["enabled"]]


# The worksheet's report source (Form FDA 3500A G2) and the classification's user type it maps to.
_REPORT_SOURCE = {"health professional": "HEALTHCARE_PROFESSIONAL"}


def _from_report(db: Session, tenant_id, complaint_id, view: dict) -> dict:
    """With no classification yet, the user type a report worksheet already recorded (its report source, G2) is
    proposed, with where it came from (stage 8: a fact the record holds is not asked again). A person confirms it."""
    from backend.app.db.models.authority_reports import ReportObligation

    if view["id"] is not None or view["user_type"] != coding.UNKNOWN:
        return view
    for row in db.query(ReportObligation.entries).filter(
        ReportObligation.tenant_id == tenant_id, ReportObligation.complaint_id == complaint_id
    ):
        said = str(((row.entries or {}).get("G2") or {}).get("value") or "").strip()
        code = _REPORT_SOURCE.get(said.lower())
        if code:
            return {
                **view,
                "user_type": code,
                "source_values": {**view["source_values"], "user_type": f"{said} (report worksheet G2)"},
            }
    return view


def _complaint_as_evidence(db: Session, control_db: Session, ctx, case, complaint, ref: str, now: datetime) -> None:
    """The escalated complaint's own record is the investigation's first evidence, linked for a person to review
    (stage 8: the facts flow from the complaint into the investigation, not typed again)."""
    from backend.app.db.models.foundation import Evidence, InvestigationEvidence
    from backend.app.evidence_workflow.inventory import review_event
    from backend.app.evidence_workflow.rules import UNREVIEWED
    from backend.app.access.permissions import EVIDENCE_REVIEW

    person = current_person(control_db, ctx)
    evidence = Evidence(
        id=uuid.uuid4(),
        tenant_id=case.tenant_id,
        evidence_identifier=f"{case.business_id or case.investigation_identifier}-{ref}"[:120],
        investigation_id=case.id,
        evidence_type="COMPLAINT_RECORD",
        title=f"Complaint {ref}: {' '.join((complaint.description or '').split())}"[:255],
        source_system="MDARIX",
        source_identifier=ref,
        source_reference=f"Complaint {ref}",
        source_timestamp=complaint.awareness_timestamp,
        effective_timestamp=complaint.awareness_timestamp,
        recorded_timestamp=now,
        ingestion_timestamp=now,
        content=complaint.description,
        fact_type="source_fact",
        created_at=now,
        updated_at=now,
    )
    db.add(evidence)
    db.flush()
    db.add(
        InvestigationEvidence(
            id=uuid.uuid4(),
            tenant_id=case.tenant_id,
            investigation_id=case.id,
            evidence_id=evidence.id,
            relevance="The escalated complaint's own record",
            created_at=now,
            review_status=UNREVIEWED,
            linked_by=person.user_id,
        )
    )
    db.flush()
    review_event(
        db,
        tenant_id=case.tenant_id,
        case_id=case.id,
        evidence_id=evidence.id,
        event_type="LINKED",
        actor=person,
        permission=EVIDENCE_REVIEW,
        to_status=UNREVIEWED,
        reason="The escalated complaint's own record",
        now=now,
    )


def screen(db: Session, control_db: Session, ctx, complaint_id: uuid.UUID, today: date | None = None) -> dict:
    tenant_id = uuid.UUID(ctx.tenant_id)
    today = today or service.today_utc()
    facts = service.screen_facts(db, tenant_id, complaint_id, today)
    if facts is None:
        raise _error(404, "COMPLAINT_NOT_FOUND", "No such complaint in your organization")
    versions = service.versions_of(db, tenant_id, complaint_id)
    current = next((row for row in reversed(versions) if row.superseded_by is None), None)
    classifications = service.classifications_of(db, tenant_id, complaint_id)
    latest = classifications[-1] if classifications else None
    needed = training.for_disposition()
    holders = training.holders(db, tenant_id, needed, exclude=str(ctx.user_id))
    refs = {row.signed_by for row in versions} | set(holders)
    refs |= {row.confirmed_by for row in classifications if row.confirmed_by}
    names = people(control_db, tenant_id, [ref for ref in refs if ref])
    cases = service.case_refs(db, tenant_id, [row.investigation_id for row in versions])
    complaint = facts["complaint"]
    trial = is_trial(control_db, tenant_id)
    return {
        "complaint": service.summary_of(complaint, facts["product_name"], facts["version"], facts["lot"]),
        "opened_at": datetime.now(timezone.utc).isoformat(),
        "triggers": facts["triggers"],
        "trigger_codes": triggers.codes(facts["triggers"]),
        "trigger_rules": [
            {"code": code, "label": triggers.LABELS[code], "definition": triggers.DEFINITIONS[code]}
            for code in triggers.CODES
        ],
        "candidates": facts["candidates"],
        "routine": {
            **facts["routine"],
            "markets": [
                {"market": market, "label": markets.MARKET_LABELS[market]} for market in _routine_markets(facts)
            ],
            "target_seconds": rules.ROUTINE_TARGET_SECONDS,
        },
        "second_look": facts["second_look"],
        "reportability": _reportability(db, tenant_id, complaint_id, today),
        "questions": [{"key": key, "text": text} for key, text in rules.QUESTIONS],
        "branch_labels": rules.BRANCH_LABELS,
        "corrections": rules.CORRECTION_LABELS,
        "no_investigation_reasons": rules.NO_INVESTIGATION_REASONS,
        "device_returned": rules.DEVICE_RETURNED,
        "attributions": [
            {"code": code, "label": rules.ATTRIBUTION_LABELS[code], "definition": rules.ATTRIBUTION_DEFINITIONS[code]}
            for code in rules.ATTRIBUTION_LABELS
        ],
        "no_investigation_clause": rules.NO_INVESTIGATION_CLAUSE,
        "basis": chips(rules.CLAUSE_IDS),
        "classification": _from_report(db, tenant_id, complaint_id, service.classification_view(latest, names)),
        "classification_history": [service.classification_view(row, names) for row in reversed(classifications[:-1])],
        "use_environments": coding.USE_ENVIRONMENT_LABELS,
        "user_types": coding.USER_TYPE_LABELS,
        "coding_criteria": {"version": coding.CODING_CRITERIA_VERSION, "rules": list(coding.CODING_CRITERIA)},
        "disposition_rules": {"version": rules.RULES_VERSION, "rules": list(rules.DISPOSITION_RULES)},
        "current": service.disposition_view(current, names, cases) if current is not None else None,
        "history": [service.disposition_view(row, names, cases) for row in reversed(versions) if row is not current],
        "version": max((row.version for row in versions), default=0),
        "training": training.status(db, tenant_id, ctx.user_id, needed),
        # The practice training before signing is a free trial's rule (T-G40P).
        "training_required": trial,
        # The signature needs an authenticator code (verify_signing_credentials): the form asks for it before sending.
        "code_required": mfa.signatures_require_mfa(),
        "trained_colleagues": [names.get(ref) or "A colleague" for ref in holders],
        "starter_mark": STARTER_MARK,
        "practice_label": markets.PRACTICE_LABEL if trial else None,
    }


@router.get("/dispositions")
def dispositions(
    show: str = Query("waiting", max_length=20),
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = uuid.UUID(ctx.tenant_id)
    found = service.board(db, tenant_id, show=show, page=page, page_size=page_size)
    signers = [item["disposition"].pop("signed_by_ref") for item in found["items"] if "disposition" in item]
    names = people(control_db, tenant_id, signers) if signers else {}
    for item in found["items"]:
        if "disposition" in item:
            item["disposition"]["signed_by"] = names.get(signers.pop(0)) or "A colleague"
    return found


@router.get("/dispositions/trend")
def disposition_trend(
    group: str = Query("problem", max_length=30),
    use_environment: str | None = Query(None, max_length=30),
    user_type: str | None = Query(None, max_length=30),
    attribution: str | None = Query(None, max_length=30),
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    return service.trend(
        db,
        uuid.UUID(ctx.tenant_id),
        group=group,
        use_environment=use_environment or None,
        user_type=user_type or None,
        attribution=attribution or None,
    )


@router.get("/{complaint_id}/disposition")
def disposition_screen(
    complaint_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    return screen(db, control_db, ctx, complaint_id)


def _seconds_since(opened_at: str | None, now: datetime) -> float | None:
    try:
        opened = datetime.fromisoformat(opened_at) if opened_at else None
    except ValueError:
        return None
    if opened is None or opened.tzinfo is None:
        return None
    return (now - opened).total_seconds()


def _triage_first(db, tenant_id, complaint_id) -> bool:
    """TR-22 (B2): a flagged complaint (or its event) whose triage is open is triaged before its disposition."""
    from backend.app.intake import rules as intake_rules
    from backend.app.intake import service as intake

    key = f"{intake.COMPLAINT}:{complaint_id}"
    return any(
        key in item["members"] and item["tier"] != intake_rules.UNFLAGGED
        for item in intake.triage(db, None, tenant_id, "open")["items"]
    )


def _classification_problem(payload: ClassificationIn, latest: ComplaintClassification | None, reason: str):
    """``(problem, the classification as it is signed, whether it is a change of a confirmed one)``."""
    values = {
        "use_environment": rules.collapse(payload.use_environment).upper(),
        "use_environment_text": rules.collapse(payload.use_environment_text) or None,
        "user_type": rules.collapse(payload.user_type).upper(),
        "user_type_text": rules.collapse(payload.user_type_text) or None,
    }
    for code_key, text_key in (("use_environment", "use_environment_text"), ("user_type", "user_type_text")):
        if values[code_key] != coding.OTHER:
            values[text_key] = None  # text belongs to "Other" only
    problem = coding.classification_problem(**values)
    if problem:
        return problem, values, False
    changed = (
        latest is not None
        and latest.state == "CONFIRMED"
        and any(getattr(latest, key) != value for key, value in values.items())
    )
    if changed and len(reason) < rules.REASON_MIN:
        return (
            f"The classification was confirmed before: say in at least {rules.REASON_MIN} characters why it changes",
            values,
            changed,
        )
    return None, values, changed


@router.post("/{complaint_id}/disposition/sign", dependencies=[DECIDERS])
def sign_disposition(
    complaint_id: uuid.UUID,
    payload: SignRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Sign the disposition: the branch with each answer's rationale, the triggers met with their facts, the
    service-level record and attribution, the confirmed classification and, on the routine path, each enabled market's
    "not reportable" conclusion on the routine basis are what is signed."""
    from backend.app.case_workflow import scope as case_scope
    from backend.app.governance_router import verify_signing_credentials
    from backend.app.human_decision.rules import fingerprint, signature_hash
    from backend.app.investigation_open_router import open_case
    from backend.app.workflow.people import acting_role

    tenant_id = uuid.UUID(ctx.tenant_id)
    today = service.today_utc()
    facts = service.screen_facts(db, tenant_id, complaint_id, today)
    if facts is None:
        raise _error(404, "COMPLAINT_NOT_FOUND", "No such complaint in your organization")
    complaint = facts["complaint"]
    if _triage_first(db, tenant_id, complaint_id):
        raise _error(422, "TRIAGE_FIRST", "Triage first: this complaint is flagged and its triage is not done yet")
    ref = service.ref_of(complaint)
    met = facts["triggers"]
    new = [code for code in triggers.codes(met) if code not in set(payload.seen_triggers)]
    if new:
        raise _error(
            409,
            "TRIGGER_MET_SINCE_OPENED",
            "An escalation trigger is met that was not when you opened the screen: "
            + "; ".join(item["fact"] for item in met if item["code"] in new),
            triggers=[item for item in met if item["code"] in new],
        )
    branch = rules.collapse(payload.branch).upper()
    rationale = rules.collapse(payload.rationale)
    not_known = rules.collapse(payload.not_known_reason)
    change_reason = rules.collapse(payload.change_reason)
    candidates = [case["id"] for case in facts["candidates"]]
    case_id = str(payload.case_id) if payload.case_id else None
    problem = rules.branch_problem(branch, bool(met), candidates, case_id, rationale, not_known)
    record = None
    attribution, attribution_reason = None, None
    if not problem and branch == rules.SERVICE_LEVEL:
        record = rules.clean_service_record(payload.service_record.model_dump() if payload.service_record else None)
        attribution = rules.collapse(payload.attribution).upper() or None
        attribution_reason = rules.collapse(payload.attribution_reason) or None
        problem = (
            rules.service_record_problem(record, facts["on_watch"])
            or rules.attribution_problem(attribution, attribution_reason)
            or rules.no_fault_problem(record, attribution)
        )
    if not problem and branch in rules.ESCALATED and complaint.product_id is None:
        problem = (
            "This complaint names no product: an investigation needs one; record the product in your QMS export first"
        )
    classifications = service.classifications_of(db, tenant_id, complaint_id)
    latest = classifications[-1] if classifications else None
    classification_problem, values, changed = _classification_problem(payload.classification, latest, change_reason)
    problem = problem or classification_problem
    versions = service.versions_of(db, tenant_id, complaint_id)
    if not problem and versions and len(change_reason) < rules.REASON_MIN:
        problem = f"A disposition is signed already: say in at least {rules.REASON_MIN} characters why it changes"
    if problem:
        raise _error(422, "DISPOSITION_INCOMPLETE", problem)
    if max((row.version for row in versions), default=0) != payload.seen_version:
        raise _error(409, "SIGNED_MEANWHILE", "A colleague signed a disposition a moment ago; reload to see it")
    if payload.routine and not facts["routine"]["offered"]:
        raise _error(
            409,
            "ROUTINE_NOT_OFFERED",
            "The routine path is no longer offered: " + "; ".join(facts["routine"]["blocked"]),
            blocked=facts["routine"]["blocked"],
        )
    routine = payload.routine and branch in rules.RESOLVED
    routine_markets = []
    if routine:
        concluded = {
            row.market for row in facts["facts"].assessments if row.conclusion is not None and row.superseded_by is None
        }
        routine_markets = [market for market in _routine_markets(facts) if market not in concluded]
    person = current_person(control_db, ctx)
    role = person.role_for(QUALITY_REVIEW) or person.role_for(SIGNAL_TRIAGE) or person.role_for(INVESTIGATION_CREATE)
    if (role or "").upper() in ADMINISTRATOR_ROLES:
        raise _error(403, "ADMINISTRATOR_CANNOT_SIGN", "Administrators cannot sign dispositions")
    needed = training.for_disposition()
    trial = is_trial(control_db, tenant_id)
    # The practice training before signing is a free trial's rule (T-G40P); other organizations sign without it.
    untrained = training.missing(db, tenant_id, ctx.user_id, needed) if trial else []
    if untrained:
        trained = training.holders(db, tenant_id, needed, exclude=str(ctx.user_id))
        names = people(control_db, tenant_id, trained)
        raise _error(
            409,
            "TRAINING_REQUIRED",
            "Practice training needed before signing: "
            + " and ".join(f"{document.title}, version {document.version}" for document in untrained)
            + ".",
            missing=[document.as_dict() for document in untrained],
            trained_colleagues=[names.get(user) or "A colleague" for user in trained],
        )

    def refused(action: str) -> None:
        control_db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=ctx.user_id,
                action=action,
                entity_type="Complaint",
                entity_id=complaint_id,
                correlation_id=ctx.correlation_id,
                details={"attempt": "COMPLAINT_DISPOSITION_SIGN", "complaint": ref, "branch": branch},
            )
        )

    # Re-authenticate first: a refusal commits the control session, so nothing else may be pending in it yet.
    verify_signing_credentials(
        control_db, ctx, password=payload.password, mfa_code=payload.mfa_code, record_refusal=refused
    )

    now = datetime.now(timezone.utc)
    versions = service.versions_of(db, tenant_id, complaint_id, lock=True)
    if max((row.version for row in versions), default=0) != payload.seen_version:
        raise _error(409, "SIGNED_MEANWHILE", "A colleague signed a disposition a moment ago; reload to see it")
    disposition_id = uuid.uuid4()
    record_id = uuid.uuid4()
    case = None
    opened = False
    if branch in rules.ESCALATED:
        user = control_db.query(AuthUser.username).filter(AuthUser.id == uuid.UUID(str(ctx.user_id))).first()
        # The question carries what the complaint said and why it escalated, in words (stage 8: no codes, nothing
        # typed twice); the person's reason follows.
        question = (
            f"{(complaint.description or '').strip()} Escalated from complaint {ref} "
            + (
                f"by the trigger{'s' if len(triggers.codes(met)) > 1 else ''} {triggers.words(triggers.codes(met))}"
                if met
                else "by choice"
            )
            + f". {rationale}"
        ).strip()[:2000]
        case, _, _ = open_case(
            db,
            tenant_id,
            actor_ref=ctx.user_id,
            product_id=complaint.product_id,
            investigation_question=question,
            complaint_ids=[complaint.id],
            owner_ref=user[0] if user else None,
            actor_role=acting_role(control_db, tenant_id, ctx.user_id, INVESTIGATION_CREATE),
        )
        _complaint_as_evidence(db, control_db, ctx, case, complaint, ref, now)
        opened = True
    elif branch == rules.KNOWN_ISSUE:
        case = (
            db.query(Investigation)
            .filter(Investigation.tenant_id == tenant_id, Investigation.id == payload.case_id)
            .with_for_update()
            .one()
        )
        data = case_scope.current_scope(db, case)
        included = case_scope.id_list([*data["included_complaint_ids"], str(complaint.id)])
        data.update(
            {
                "included_complaint_ids": included,
                "change_reason": f"Known issue: {ref} added as a contributing complaint (disposition, {rationale})"[
                    :2000
                ],
                "reviews_must_restart": False,
                "conclusions_invalidated": False,
            }
        )
        actor_role = acting_role(control_db, tenant_id, ctx.user_id, INVESTIGATION_CREATE)
        scope_row = case_scope.write_version(db, case, data, actor_ref=str(ctx.user_id), actor_role=actor_role, now=now)
        linked, _ = case_scope.sync_complaint_links(db, case, scope_row.included_complaint_ids, now)
        case.updated_at = now
        db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=str(ctx.user_id),
                action="INVESTIGATION_SCOPE_CHANGED",
                entity_type="Investigation",
                entity_id=case.id,
                correlation_id=ctx.correlation_id,
                reason=scope_row.change_reason,
                details={
                    "version": scope_row.version,
                    "complaint_links_added": len(linked),
                    "complaint_links_removed": 0,
                    "contributing_complaint": ref,
                    "from_disposition": str(disposition_id),
                    "actor_role": actor_role,
                },
                created_at=now,
            )
        )
    answers = rules.answers_of(branch, met, candidates, rationale, not_known)
    classification = None
    if latest is None or latest.state != "CONFIRMED" or changed:
        classification = ComplaintClassification(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            complaint_id=complaint_id,
            version=(latest.version if latest else 0) + 1,
            **values,
            source_values=(latest.source_values if latest else None) or {},
            state="CONFIRMED",
            coding_criteria_version=coding.CODING_CRITERIA_VERSION,
            confirmed_by=str(ctx.user_id),
            confirmed_at=now,
            signed_record_id=record_id,
            change_reason=change_reason if changed else None,
            created_by=str(ctx.user_id),
            created_at=now,
        )
    seconds = rules.hands_on(_seconds_since(payload.opened_at, now))
    material = {
        "complaint_id": str(complaint_id),
        "complaint": ref,
        "version": max((row.version for row in versions), default=0) + 1,
        "rules_version": rules.RULES_VERSION,
        "branch": branch,
        "answers": answers,
        "triggers": met,
        "service_record": record,
        "attribution": attribution,
        "attribution_reason": attribution_reason,
        "case": str(case.id) if case is not None else None,
        "classification": {**values, "coding_criteria": coding.CODING_CRITERIA_VERSION},
        "routine_markets": [
            {"market": market, "question_set": rules.ROUTINE_QUESTION_SET, "conclusion": markets.NOT_REPORTABLE}
            for market in routine_markets
        ],
        "covers": [
            "disposition",
            "classification",
            *(f"market conclusion {market}" for market in routine_markets),
        ],
        "change_reason": change_reason or None,
        "training": [document.as_dict() for document in needed] if trial else [],
        "starter_mark": STARTER_MARK,
        "practice_label": markets.PRACTICE_LABEL if trial else None,
    }
    content_fingerprint = fingerprint(material)
    object_version = str(material["version"])
    control_db.add(
        SignedApprovalRecord(
            id=record_id,
            tenant_id=tenant_id,
            object_type=OBJECT_TYPE,
            object_id=disposition_id,
            object_version=object_version,
            decision_type=DECISION_TYPE,
            decision=rules.SIGNATURE_CODES[branch],
            remarks=(record or {}).get("no_investigation_rationale") or rationale or rules.BRANCH_LABELS[branch],
            signer_user_id=str(ctx.user_id),
            signer_role=role or "UNKNOWN",
            signature_meaning=rules.signature_meaning(
                ref, branch, [markets.MARKET_LABELS[market] for market in routine_markets], True
            ),
            content_fingerprint=content_fingerprint,
            signature_hash=signature_hash(content_fingerprint, str(ctx.user_id), object_version),
            status="SIGNED",
            signed_at=now,
            created_at=now,
        )
    )
    control_db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="COMPLAINT_DISPOSITION_SIGNED",
            entity_type="Complaint",
            entity_id=complaint_id,
            correlation_id=ctx.correlation_id,
            reason=change_reason or None,
            details={
                "complaint": ref,
                "version": material["version"],
                "branch": branch,
                "triggers": triggers.codes(met),
                "attribution": attribution,
                "case": case.business_id if case is not None else None,
                "case_opened": opened,
                "routine_path": routine,
                "market_conclusions": routine_markets,
                "hands_on_seconds": seconds,
                "classification": values,
                "signature_id": str(record_id),
                "fingerprint": content_fingerprint,
                "signer_role": role,
            },
            new_values={"branch": branch},
            created_at=now,
        )
    )
    if classification is not None:
        db.add(classification)
        db.flush()
        if latest is not None and latest.superseded_by is None:
            latest.superseded_by = classification.id
    for market in routine_markets:
        existing = [row for row in facts["facts"].assessments if row.market == market]
        db.add(
            ComplaintMarketAssessment(
                tenant_id=tenant_id,
                complaint_id=complaint_id,
                market=market,
                version=max((row.version for row in existing), default=0) + 1,
                question_set=rules.ROUTINE_QUESTION_SET,
                answers={"BASIS": {"answer": "NO", "rationale": rules.ROUTINE_BASIS, "evidence": []}},
                scale_version=markets.SCALE_VERSION,
                suggested_conclusion=markets.NOT_REPORTABLE,
                conclusion=markets.NOT_REPORTABLE,
                signed_record_id=record_id,
                content_fingerprint=content_fingerprint,
                signed_by=str(ctx.user_id),
                signed_at=now,
                created_by=str(ctx.user_id),
                created_at=now,
                updated_at=now,
            )
        )
    db.add(
        ComplaintDisposition(
            id=disposition_id,
            tenant_id=tenant_id,
            complaint_id=complaint_id,
            version=material["version"],
            branch=branch,
            triggers=met,
            answers=answers,
            service_record=record,
            attribution=attribution,
            attribution_reason=attribution_reason,
            investigation_id=case.id if case is not None else None,
            routine_path=routine,
            hands_on_seconds=seconds,
            change_reason=change_reason or None,
            signed_record_id=record_id,
            content_fingerprint=content_fingerprint,
            signed_by=str(ctx.user_id),
            signed_at=now,
            created_by=str(ctx.user_id),
            created_at=now,
        )
    )
    db.flush()
    for earlier in versions:
        if earlier.superseded_by is None:
            earlier.superseded_by = disposition_id
    try:
        signing_commit.commit(db, control_db, "disposition")
    except IntegrityError as exc:
        db.rollback()
        control_db.rollback()
        raise _error(
            409, "SIGNED_MEANWHILE", "A colleague signed a disposition a moment ago; reload to see it"
        ) from exc
    if opened:
        # The case's first task, as when a person opens a case; a failure is logged and never undoes the signature.
        from backend.app.workflow.hooks import on_investigation_opened

        on_investigation_opened(db, control_db, case, actor_user_id=ctx.user_id, owner_user_id=ctx.user_id)
    return screen(db, control_db, ctx, complaint_id, today)
