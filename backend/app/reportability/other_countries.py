"""B9b (OC spec, approved 9 Nov 2026; plan approved 11 Nov 2026): a country outside the five built-in markets.

A person picks the country, answers the generic starter questions of ``OTHER-floor-1`` and signs the conclusion. The
assessment is a ``complaint_market_assessments`` row with market ``OTHER`` and the country's ISO code (tr31); its URL
names it ``OTHER-<code>`` (``OTHER-AU``). ``OTHER`` stays out of ``markets.MARKETS``: the five markets' screens, loops
and the B4 equivalence check never see it, and these routes are its own. A signed Reportable conclusion creates the
country's "Other Regulatory Report" (``authority_reports/attached.py``).

Every route answers 404 while ``MDARIX_B9B_OTHER`` is off (or the rule register is off); records already made stay
readable on the complaint and in Authority reports.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app import countries, feature_set, signing_commit
from backend.app.access.permissions import REGULATORY_APPROVE, REGULATORY_REVIEW
from backend.app.business_ids import complaint_ref
from backend.app.complaint_review.service import people
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import SignedApprovalRecord
from backend.app.db.models.market_assessment import ComplaintMarketAssessment
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.evidence_workflow.people import current_person
from backend.app.reportability import assessment_router as base
from backend.app.reportability import assessments, deadlines, facts, markets, rules, service
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.rule_register import engine, register
from backend.app.signer_training.router import is_trial
from backend.app.standards import STARTER_MARK, version_words

SWITCH = "MDARIX_B9B_OTHER"
OTHER = "OTHER"
GENERIC = "Generic starter questions, not this country's law: confirm with your consultant."
EU_MDR_MAYBE = "This may fall under the EU MDR: check with your consultant"
# B9b-N2: places with their own ISO code that belong to an EU member state (outermost regions, Åland). Not in the EU
# list (reportability/rules.py), and not offered here either.
EU_PLACES = ("GF", "GP", "MQ", "RE", "YT", "MF", "AX")
MANUAL_DUE = "Due date entered by the customer"

router = APIRouter(prefix="/api/v1", tags=["Other countries"])


def switched_on() -> bool:
    """B9b is on (``MDARIX_B9B_OTHER``, default on) and the rule register that holds its floor is on."""
    return feature_set.switched_on(SWITCH) and feature_set.rule_register()


def _on() -> None:
    if not switched_on():
        raise base._error(404, "OTHER_COUNTRIES_OFF", "Other countries are switched off")


def _five_markets() -> dict[str, str]:
    """ISO code -> the built-in market whose own tree covers it: the EU 27 and the EEA (EU and Northern Ireland), the
    United Kingdom ("GB", Great Britain or Northern Ireland: asked), the US, Canada and India."""
    found = {code: markets.EU_NI for name in rules._EU if (code := countries.code_of(name))}
    found.update({"GB": markets.GB, "US": markets.US, "CA": markets.CA, "IN": markets.IN})
    return found


def redirect(code: str) -> dict | None:
    """Why a country is not offered here, and where it goes instead; None for a country this tree covers."""
    market = _five_markets().get(code)
    if code == "GB":
        message = (
            "The United Kingdom is two markets: assess Great Britain (MHRA) or Northern Ireland (EU MDR) in their "
            "own trees"
        )
        return {"code": code, "market": market, "message": message}
    if market:
        return {"code": code, "market": market, "message": f"Assess it in {markets.MARKET_LABELS[market]}"}
    if code in EU_PLACES:
        return {"code": code, "market": None, "message": EU_MDR_MAYBE}
    return None


def pickable() -> list[dict]:
    """Every ISO 3166 country this tree covers, by name (OC-01): not the five markets', not the EU's own places."""
    return sorted(
        ({"code": code, "name": name} for code, name in countries.NAMES.items() if redirect(code) is None),
        key=lambda item: item["name"],
    )


def name_of(code: str | None) -> str:
    return countries.NAMES.get(code or "", code or "")


def label(code: str | None) -> str:
    return f"{name_of(code)} (other country)"


def key(code: str) -> str:
    return f"{OTHER}-{code}"


def _country(value: str) -> str:
    code = str(value or "").strip().upper()
    if code not in countries.CODES:
        raise base._error(404, "COUNTRY_UNKNOWN", "Pick a country from the list (ISO 3166 code)")
    moved = redirect(code)
    if moved:
        raise base._error(422, "COUNTRY_HAS_ITS_OWN_TREE", moved["message"], market=moved["market"])
    return code


def _versions(db: Session, tenant_id, complaint_id, country: str, lock: bool = False):
    query = db.query(ComplaintMarketAssessment).filter(
        ComplaintMarketAssessment.tenant_id == tenant_id,
        ComplaintMarketAssessment.complaint_id == complaint_id,
        ComplaintMarketAssessment.market == OTHER,
        ComplaintMarketAssessment.country == country,
    )
    if lock:
        query = query.with_for_update().populate_existing()
    return query.order_by(ComplaintMarketAssessment.version).all()


def rows_by_country(db: Session, tenant_id, complaint_id) -> dict[str, list[ComplaintMarketAssessment]]:
    found: dict[str, list[ComplaintMarketAssessment]] = {}
    for row in (
        db.query(ComplaintMarketAssessment)
        .filter(
            ComplaintMarketAssessment.tenant_id == tenant_id,
            ComplaintMarketAssessment.complaint_id == complaint_id,
            ComplaintMarketAssessment.market == OTHER,
        )
        .order_by(ComplaintMarketAssessment.version)
    ):
        found.setdefault(row.country, []).append(row)
    return found


def _floor(aware, seen: dict, row=None) -> dict | None:
    """The generic floor in force on the awareness day (as the five markets); a signed row's own floor."""
    if row is not None and row.floor_code:
        return register.get(row.floor_code)
    return register.floor_at(OTHER, aware, seen.get("org_zone")) if switched_on() else None


# ------------------------------------------------------------------------------------------------- due date (step 4)


def country_windows(windows: list[dict], country: str) -> list[dict]:
    """The organization's reporting windows that name the country, by name or ISO code (OC-D2). A window naming no
    market covers the five markets only, never a country outside them."""
    wanted = {rules.normalize(country), rules.normalize(name_of(country))}
    return [window for window in windows if wanted & {rules.normalize(item) for item in window.get("markets") or []}]


def clock(windows: list[dict], country: str, state: str | None, aware, now, org_zone: str | None) -> dict | None:
    """The country's clock: the earliest of its windows, counted in the organization's time zone (no authority zone);
    none when no window names it (the report then takes a date the customer enters) or the conclusion is not
    reportable."""
    if aware is None or state == markets.NOT_REPORTABLE:
        return None
    found = [
        markets._clock(w["name"], w["days"], w["day_basis"], aware, now, "WINDOW", OTHER, org_zone)
        for w in country_windows(windows, country)
    ]
    return min(found, key=lambda item: item["due_at"]) if found else None


# ---------------------------------------------------------------------------------------------------------- routes


@router.get("/other-countries", dependencies=[Depends(_on)])
def other_countries(ctx: AuthenticatedRequestContext = Depends(get_request_context)):
    """The country picker (OC-01): the countries this tree covers, and those sent elsewhere with why."""
    sent = [
        {**moved, "name": name_of(code)}
        for code in sorted(countries.CODES)
        if (moved := redirect(code)) and (code in EU_PLACES or code == "GB")
    ]
    return {"countries": pickable(), "not_offered": sent, "generic_note": GENERIC, "starter_mark": STARTER_MARK}


def items(db: Session, control_db: Session, ctx, complaint_id, record: dict, seen: dict, aware, today) -> list:
    """The complaint's other-country assessments for the Reportability tab, one per country, as the five markets'."""
    tenant_id = uuid.UUID(ctx.tenant_id)
    by_country = rows_by_country(db, tenant_id, complaint_id)
    if not by_country:
        return []
    refs = {ref for rows in by_country.values() for row in rows for ref in (row.signed_by, row.created_by) if ref}
    names = people(control_db, tenant_id, list(refs))
    found = []
    windows = service.settings_of(db, tenant_id)["windows"]
    for country, versions in sorted(by_country.items(), key=lambda item: name_of(item[0])):
        current, draft = assessments.current_and_draft(versions)
        floor = _floor(aware, seen, draft if draft is not None else current) or register.get("OTHER-floor-1")
        question_set = markets.floor_question_set(floor)
        state = (
            current.conclusion
            if current is not None and draft is None
            else draft.suggested_conclusion
            if draft
            else None
        )
        found.append(
            {
                "market": OTHER,
                "key": key(country),
                "country": country,
                "country_name": name_of(country),
                "label": label(country),
                "generic_note": GENERIC,
                "question_set": question_set.as_dict(),
                "suggestions": markets.suggestions(question_set, record, floor),
                "record_notes": markets.record_notes(question_set, record, floor),
                "current": _view(current, names, floor),
                "draft": _view(draft, names, floor),
                "evaluation": engine.evaluate(floor["content"], draft.answers or {}) if draft is not None else None,
                "history": [_view(row, names, floor) for row in reversed(versions) if row not in (current, draft)],
                "clock": clock(windows, country, state, aware, today, seen.get("org_zone")),
                "floor": {"code": floor["code"], "title": floor["title"]},
            }
        )
    return found


def _view(row, names: dict | None, floor: dict) -> dict | None:
    found = assessments.row_view(row, names or {}, row.question_set if row is not None else None)
    if found is None:
        return None
    kind = (floor["content"]["report_types"]).get(row.report_type or "")
    return {**found, "country": row.country, "report_type_label": kind["label"] if kind else None}


def _complaint_and_country(db, tenant_id, complaint_id, value: str, today):
    country = _country(value)
    return (*base._found(db, tenant_id, complaint_id, today), country)


@router.put(
    "/complaints/{complaint_id}/market-assessments/OTHER-{country}",
    dependencies=[Depends(_on), base.DECIDERS],
)
def save_draft(
    complaint_id: uuid.UUID,
    country: str,
    payload: base.DraftRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Save a country's answers as a draft; returns the complaint's assessments (the five markets and the countries)."""
    tenant_id = uuid.UUID(ctx.tenant_id)
    today = deadlines.as_moment(None)
    complaint, record, seen, second_look, country = _complaint_and_country(db, tenant_id, complaint_id, country, today)
    versions = _versions(db, tenant_id, complaint_id, country, lock=True)
    if not versions and not base._on_watch(complaint, record, second_look):
        raise base._error(
            409,
            "NOT_ON_WATCH",
            "This complaint is not on the reportability watch: it reports no death, serious injury or malfunction, "
            "and no patient with an unknown outcome",
        )
    draft = next((row for row in versions if row.conclusion is None), None)
    aware = datetime.fromisoformat(seen["aware_at"]) if seen["aware_at"] else None
    floor = _floor(aware, seen)
    question_set = markets.floor_question_set(floor)
    clean = base._clean_draft(question_set, payload, record, floor)
    problem = markets.answers_problem(question_set, clean["answers"], complete=False, floor=floor)
    if problem:
        raise base._error(422, "ASSESSMENT_INVALID", problem)
    evaluation = engine.evaluate(floor["content"], clean["answers"])
    windows = service.settings_of(db, tenant_id)["windows"]
    found = clock(windows, country, evaluation["suggested"], aware, today, seen.get("org_zone"))
    now = datetime.now(timezone.utc)
    action = "COMPLAINT_MARKET_ASSESSMENT_SAVED"
    if draft is None:
        draft = ComplaintMarketAssessment(
            tenant_id=tenant_id,
            complaint_id=complaint_id,
            market=OTHER,
            country=country,
            version=max((row.version for row in versions), default=0) + 1,
            created_by=str(ctx.user_id),
            created_at=now,
        )
        db.add(draft)
        action = "COMPLAINT_MARKET_ASSESSMENT_STARTED"
    # No harm level or scale for a country outside the five markets: its generic questions ask the seriousness.
    draft.question_set, draft.scale_version, draft.answers = (
        question_set.version,
        markets.SCALE_VERSION,
        clean["answers"],
    )
    draft.suggested_conclusion, draft.report_type = evaluation["suggested"], evaluation["report_type"]
    draft.window_name = found["window"] if found else None
    draft.due_on = date.fromisoformat(found["due_date"]) if found else None
    base._record_floor(draft, OTHER, floor, clean["answers"], found, aware, seen)
    draft.updated_at = now
    db.flush()
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action=action,
            entity_type="Complaint",
            entity_id=complaint_id,
            correlation_id=ctx.correlation_id,
            details={
                "complaint": complaint_ref(record),
                "market": OTHER,
                "country": country,
                "version": draft.version,
                "question_set": question_set.version,
                "floor_code": floor["code"],
                "suggested": evaluation["suggested"],
                "answered": len(clean["answers"]),
                "answer_origins": markets.origins(clean["answers"]),
            },
            created_at=now,
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise base._error(409, "SAVED_MEANWHILE", "Someone saved this country a moment ago; reload to see it") from exc
    return base.detail(db, control_db, ctx, complaint_id, today)


def signature_meaning(ref: str, country: str, version: str, conclusion: str) -> str:
    return (
        f"I have assessed {ref} for {name_of(country)} (a country outside the five built-in markets) with the generic "
        f"starter questions, {version_words(version)}, and conclude: "
        f"{markets.CONCLUSION_LABELS[conclusion].lower()}. {GENERIC}"
    )


@router.post(
    "/complaints/{complaint_id}/market-assessments/OTHER-{country}/sign",
    dependencies=[Depends(_on), base.DECIDERS],
)
def sign_conclusion(
    complaint_id: uuid.UUID,
    country: str,
    payload: base.SignRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Sign a country's conclusion (password and MFA, as the five markets'): the answers, the floor and its content
    hash, the generic-starter note, the suggestion and the conclusion are what is signed. Reportable creates the
    country's Other Regulatory Report; a later Not reportable cancels one not yet submitted."""
    from backend.app.authority_reports import attached
    from backend.app.governance_router import verify_signing_credentials
    from backend.app.human_decision.rules import fingerprint, signature_hash

    tenant_id = uuid.UUID(ctx.tenant_id)
    today = deadlines.as_moment(None)
    _, record, seen, _, country = _complaint_and_country(db, tenant_id, complaint_id, country, today)
    ref = record["business_id"] or record["complaint_identifier"]
    # The country is the one picked here: only the other facts (the awareness date) are needed first.
    if any(item.get("fact") != facts.COUNTRY for item in seen["needs"]):
        raise base._error(409, "FACT_NEEDED", " ".join(item["message"] for item in seen["needs"]), needs=seen["needs"])
    versions = _versions(db, tenant_id, complaint_id, country)
    draft = next((row for row in versions if row.conclusion is None), None)
    if draft is None:
        raise base._error(409, "NO_DRAFT", "Save the answers before signing the conclusion")
    if draft.version != payload.version or not base._same_moment(draft.updated_at, payload.saved_at):
        raise base._error(409, "DRAFT_CHANGED", "The answers changed since you opened them; reload and read them again")
    answers = draft.answers or {}
    aware = datetime.fromisoformat(seen["aware_at"]) if seen["aware_at"] else None
    floor = _floor(aware, seen)
    if draft.floor_code and draft.floor_code != floor["code"]:
        raise base._error(
            409,
            "FLOOR_CHANGED",
            f"The rules for this event changed ({draft.floor_code} → {floor['code']}): save the answers again",
            saved_under=draft.floor_code,
            in_force=floor["code"],
        )
    question_set = markets.floor_question_set(floor)
    evaluation = engine.evaluate(floor["content"], answers)
    conclusion = str(payload.conclusion or "").strip().upper()
    override_reason = base._collapse(payload.override_reason)
    problem = markets.answers_problem(question_set, answers, complete=True, floor=floor) or markets.conclusion_problem(
        evaluation["suggested"], conclusion, override_reason
    )
    if problem:
        raise base._error(422, "ASSESSMENT_INCOMPLETE", problem)
    resigning = any(row.conclusion is not None and row.superseded_by is None for row in versions)
    change_reason = base._collapse(payload.change_reason) if resigning else ""
    if resigning and len(change_reason) < markets.REASON_MIN:
        raise base._error(
            422,
            "CHANGE_REASON_NEEDED",
            f"This country's conclusion is signed already: say in at least {markets.REASON_MIN} characters why it "
            "changes",
        )
    person = current_person(control_db, ctx)
    role = person.role_for(REGULATORY_APPROVE if person.holds(REGULATORY_APPROVE) else REGULATORY_REVIEW)
    if (role or "").upper() in base.ADMINISTRATOR_ROLES:
        raise base._error(403, "ADMINISTRATOR_CANNOT_SIGN", "Administrators cannot sign market conclusions")
    draft_id = draft.id

    def refused(action: str) -> None:
        control_db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=ctx.user_id,
                action=action,
                entity_type="Complaint",
                entity_id=complaint_id,
                correlation_id=ctx.correlation_id,
                details={"attempt": "MARKET_CONCLUSION_SIGN", "complaint": ref, "market": OTHER, "country": country},
            )
        )

    verify_signing_credentials(
        control_db, ctx, password=payload.password, mfa_code=payload.mfa_code, record_refusal=refused
    )
    now = datetime.now(timezone.utc)
    versions = _versions(db, tenant_id, complaint_id, country, lock=True)
    draft = next((row for row in versions if row.id == draft_id and row.conclusion is None), None)
    if draft is None or not base._same_moment(draft.updated_at, payload.saved_at):
        raise base._error(409, "DRAFT_CHANGED", "The answers changed a moment ago; reload and read them again")
    report_type = evaluation["report_type_if_reportable"] if conclusion == markets.REPORTABLE else None
    windows = service.settings_of(db, tenant_id)["windows"]
    found = clock(windows, country, conclusion, aware, today, seen.get("org_zone"))
    base._record_floor(draft, OTHER, floor, answers, found, aware, seen)
    trial = is_trial(control_db, tenant_id)
    material = {
        "complaint_id": str(complaint_id),
        "complaint": ref,
        "market": OTHER,
        "country": country,
        "country_name": name_of(country),
        "version": draft.version,
        "question_set": draft.question_set,
        "questions": {
            question.id: {"text": question.text, "clause": question.clause} for question in question_set.questions
        },
        "answers": answers,
        "suggested": evaluation["suggested"],
        "conclusion": conclusion,
        "override_reason": override_reason or None,
        **({"change_reason": change_reason} if change_reason else {}),
        "report_type": report_type,
        "due_on": found["due_date"] if found else None,
        "due_label": found["due_label"] if found else None,
        "generic_note": GENERIC,
        "starter_mark": STARTER_MARK,
        "practice_label": markets.PRACTICE_LABEL if trial else None,
        "floor": {"code": floor["code"], "content_hash": floor["content_hash"]},
        "rules_applied": draft.rules_applied,
        "date_calc": draft.date_calc,
    }
    content_fingerprint = fingerprint(material)
    object_version = str(draft.version)
    record_row = SignedApprovalRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        object_type=base.OBJECT_TYPE,
        object_id=draft.id,
        object_version=object_version,
        decision_type=base.DECISION_TYPE,
        decision=base.SIGNATURE_CODES[conclusion],
        remarks=override_reason or f"Suggested {markets.CONCLUSION_LABELS[evaluation['suggested']].lower()}; confirmed",
        signer_user_id=str(ctx.user_id),
        signer_role=role or "UNKNOWN",
        signature_meaning=signature_meaning(ref, country, draft.question_set, conclusion),
        content_fingerprint=content_fingerprint,
        signature_hash=signature_hash(content_fingerprint, str(ctx.user_id), object_version),
        status="SIGNED",
        signed_at=now,
        created_at=now,
    )
    control_db.add(record_row)
    control_db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="COMPLAINT_MARKET_CONCLUSION_SIGNED",
            entity_type="Complaint",
            entity_id=complaint_id,
            correlation_id=ctx.correlation_id,
            reason=change_reason or override_reason or None,
            details={
                "complaint": ref,
                "market": OTHER,
                "country": country,
                "change_reason": change_reason or None,
                "version": draft.version,
                "question_set": draft.question_set,
                "floor_code": floor["code"],
                "suggested": evaluation["suggested"],
                "conclusion": conclusion,
                "overridden": conclusion != evaluation["suggested"],
                "answer_origins": markets.origins(answers),
                "report_type": report_type,
                "signature_id": str(record_row.id),
                "fingerprint": content_fingerprint,
                "signer_role": role,
            },
            new_values={"conclusion": conclusion},
            created_at=now,
        )
    )
    for earlier in versions:
        if earlier.conclusion is not None and earlier.superseded_by is None:
            earlier.superseded_by = draft.id
    draft.conclusion, draft.override_reason, draft.report_type = conclusion, override_reason or None, report_type
    draft.change_reason = change_reason or None
    draft.suggested_conclusion = evaluation["suggested"]
    draft.window_name = found["window"] if found else None
    draft.due_on = date.fromisoformat(found["due_date"]) if found else None
    draft.signed_record_id, draft.content_fingerprint = record_row.id, content_fingerprint
    draft.signed_by, draft.signed_at, draft.updated_at = str(ctx.user_id), now, now
    attached.follow_conclusion(db, ctx, tenant_id, complaint_id, country, draft, now)
    try:
        signing_commit.commit(db, control_db, "market conclusion")
    except IntegrityError as exc:
        db.rollback()
        control_db.rollback()
        raise base._error(409, "SIGNED_MEANWHILE", "This country was signed a moment ago; reload to see it") from exc
    return base.detail(db, control_db, ctx, complaint_id, today)
