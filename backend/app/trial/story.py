"""The trial's story: the quality loop MDARIX closes, chapter by chapter, with what the trial's own data shows in each
and whether the organization has acted on it yet.

Each chapter answers one pain FDA and notified bodies cite in 2026 (MDARIX Final Lightweight MVP Plan, P1-P8): a
finding read from the organization's records (the sample data at first, its own export later) and a real action
recorded in MDARIX (a person decided a second-look record, recorded a reporting decision, opened a case from a
signal, ran the AI, signed a decision, planned or signed an effectiveness check, completed a risk review, downloaded
the readiness summary, imported their own complaints). Nothing here is inferred from page views.

``story`` serves the trial's Getting started page (findings and actions); ``progress`` gives one trial's actions, and
``trial_overview`` the same for every trial at once in a fixed number of statements (the Platform Admin overview).
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

logger = logging.getLogger("mdarix.trial.story")

# code, number, title, what MDARIX does (the promise), the pain it answers, where it opens, the readiness check whose
# value is the chapter's finding (None: a count of its own).
CHAPTERS = (
    (
        "HIDDEN_COMPLAINTS",
        "Recover complaints hidden as cancellations or inquiries",
        "The second look finds records cancelled, logged as inquiries or coded No Fault Found that carry signs of a "
        "complaint; a person confirms or dismisses each, with a reason.",
        "FDA warning letters in 2026 cite complaints cancelled or logged as inquiries although they met the firm's "
        "own complaint definition.",
        {"section": "Complaints", "tab": "Second look"},
        "COMPLAINTS_TO_RECHECK",
    ),
    (
        "REPORTING_CLOCKS",
        "Decide every report inside its window",
        "Every complaint reporting a death, a serious injury or a malfunction runs a clock against your reporting "
        "windows, per market; missing answers are flagged and a person decides.",
        "Reports filed months late, or never evaluated, are a repeat finding in FDA inspections.",
        {"section": "Complaints", "tab": "Reportability"},
        "REPORTING_CLOCKS",
    ),
    (
        "TRENDS_TO_CASES",
        "Turn a rising trend into a case in one click",
        "Signals count every complaint per product version, a statistical check compares each version with its own "
        "history, and Open case starts the investigation with every complaint attached.",
        "Trends counted on a subset of complaints, or by root-cause code, hide real rises until they are cited.",
        {"section": "Signals", "tab": "Signal inbox"},
        None,
    ),
    (
        "INVESTIGATE_WITH_AI",
        "Investigate with AI that shows its sources",
        "One AI run drafts the analysis, competing explanations and challenges; every statement cites the evidence "
        "and passes the automatic trust check, and the investigator judges each one.",
        "Small teams with large backlogs; AI that cannot show its sources is not trusted.",
        # Inside the guided investigation, on its case page (Getting started opens the chapter's case).
        {"section": "Investigations", "tab": "Workspace"},
        None,
    ),
    (
        "DECIDE_AND_SIGN",
        "Decide, sign and open the CAPA",
        "The sample case's Decision Brief is written and waiting for you: review it as the quality reviewer, accept "
        "it, then sign the decision with your password and authenticator code; the CAPA opens from the signed "
        "decision. The person who writes a brief never reviews or signs it, on every case.",
        "Trends that never become a CAPA are cited in most device warning letters.",
        {"section": "Investigations", "tab": "Decision Brief"},
        None,
    ),
    (
        "CAPA_EFFECTIVE",
        "Prove each CAPA worked",
        "Every CAPA gets an effectiveness check with a plan, a day, the complaint recurrence before and since, and a "
        "signed result.",
        "CAPAs closed without a verified effect are among the most cited quality-system findings.",
        {"section": "Records", "tab": "Effectiveness checks"},
        "CAPA_EFFECTIVENESS",
    ),
    (
        "RISK_FILE",
        "Feed post-market data into the risk file",
        "Per product, what post-market data said (harm, malfunctions, rising trends) beside what reached the risk "
        "file (reviews, assessed risks, reassessments).",
        "Since February 2026 FDA inspects under QMSR and names post-market data not used in risk management a "
        "significant deficiency (ISO 14971 clause 10).",
        {"section": "Records", "tab": "Risk file input"},
        "RISK_FILE_INPUT",
    ),
    (
        "SHOW_THE_INSPECTOR",
        "Hand management review and the inspector one summary",
        "Readiness shows what an inspector would find today, and the summary PDF organizes it by the management "
        "review inputs of ISO 13485 clause 5.6.2.",
        "Management review records are now inspectable under QMSR.",
        {"section": "Readiness", "tab": None},
        None,
    ),
    (
        "YOUR_DATA",
        "See it on your own data",
        "Upload your complaints export as it comes from your quality system (Excel or CSV): MDARIX reads its column "
        "names, adds the products and lots it names, and checks every file for problems and personal data before "
        "anything is saved; every chapter above then reads it.",
        "Data spread across systems; teams spend hours a month on manual compilation.",
        {"section": "Getting started", "tab": None},
        None,
    ),
)
CODES = tuple(chapter[0] for chapter in CHAPTERS)
ENGAGED_CHAPTERS = 4


def _count(db: Session, query) -> int:
    try:
        return int(query.scalar() or 0)
    except Exception:  # an older database without one of the tables: the chapter is simply not reached
        logger.exception("Trial story: a count could not be read")
        db.rollback()
        return 0


# Where AI does not answer for the organization yet (no AI service here, or switched off), the investigation chapter
# says what the case page does without it, so the trial never promises AI it does not get.
WITHOUT_AI = {
    "INVESTIGATE_WITH_AI": (
        "Investigate with evidence you can trace",
        "The case page brings the complaints, lots, changes and evidence together; ask MDARIX a question and the answer "
        "cites the records it comes from; the investigator weighs each explanation. AI assistance joins when it is "
        "switched on for your organization.",
        "Small teams with large backlogs; conclusions that cannot show their sources are not trusted.",
    )
}


def chapter_text(code: str, title: str, promise: str, pain: str, ai_ready: bool) -> tuple[str, str, str]:
    """A chapter's title, promise and pain, as this organization gets it (with or without AI)."""
    if not ai_ready and code in WITHOUT_AI:
        return WITHOUT_AI[code]
    return title, promise, pain


def chapter_counters() -> tuple:
    """``(chapter code, model, conditions)`` for each kind of record that counts as acting in a chapter (records the
    organization created in MDARIX, sample data excluded); a chapter with two kinds counts both. One definition for
    one organization (``acted_counts``) and for every trial at once (the Platform Admin overview)."""
    from backend.app.db.models.capa_effectiveness import CapaEffectivenessCheck
    from backend.app.db.models.case_ai import CaseAiRun
    from backend.app.db.models.complaint_review import ComplaintSecondLook
    from backend.app.db.models.foundation import AuditEvent, Complaint, Decision
    from backend.app.db.models.reportability import ComplaintReportability
    from backend.app.db.models.reviews import CaseReview
    from backend.app.db.models.signals import InvestigationSignal
    from backend.app.db.models.stage3 import AIInteraction
    from backend.app.trial.imports import UPLOAD_SOURCE

    return (
        ("HIDDEN_COMPLAINTS", ComplaintSecondLook, ()),
        ("REPORTING_CLOCKS", ComplaintReportability, ()),
        ("TRENDS_TO_CASES", InvestigationSignal, ()),
        # A question asked of MDARIX, or an analysis a person started (the case page's automatic first run does not
        # count: opening a page is not investigating).
        ("INVESTIGATE_WITH_AI", CaseAiRun, (CaseAiRun.trigger == "MANUAL",)),
        ("INVESTIGATE_WITH_AI", AIInteraction, ()),
        ("DECIDE_AND_SIGN", Decision, (Decision.decision_kind == "BRIEF",)),
        ("CAPA_EFFECTIVE", CapaEffectivenessCheck, ()),
        ("RISK_FILE", CaseReview, (CaseReview.review_type == "RISK", CaseReview.status == "COMPLETED")),
        (
            "SHOW_THE_INSPECTOR",
            AuditEvent,
            (AuditEvent.action.in_(("READINESS_SUMMARY_EXPORTED", "READINESS_INSPECTION_PACK_EXPORTED")),),
        ),
        ("YOUR_DATA", Complaint, (Complaint.source_system == UPLOAD_SOURCE,)),
    )


def acted_counts(db: Session, tenant_id: uuid.UUID) -> dict[str, int]:
    """How often the organization acted in each chapter (records it created in MDARIX), sample data excluded."""
    counts = dict.fromkeys(CODES, 0)
    for code, model, conditions in chapter_counters():
        counts[code] += _count(db, db.query(func.count(model.id)).filter(model.tenant_id == tenant_id, *conditions))
    return counts


def _person_activity(model):
    """Audit events a person caused (system events excluded): what "last activity" reads."""
    return ~model.actor_ref.like("system:%")


def last_activity(db: Session, tenant_id: uuid.UUID) -> datetime | None:
    """When a person last did something recorded in the audit trail (system events excluded)."""
    from backend.app.db.models.foundation import AuditEvent

    try:
        return (
            db.query(func.max(AuditEvent.created_at))
            .filter(AuditEvent.tenant_id == tenant_id, _person_activity(AuditEvent))
            .scalar()
        )
    except Exception:
        logger.exception("Trial story: the last activity could not be read")
        db.rollback()
        return None


REMEMBERED = "tried_before_sample_removed"


def remembered(profile: dict | None) -> tuple:
    """The chapters tried before the organization removed the sample data (kept in its trial request's profile)."""
    return tuple((profile or {}).get(REMEMBERED) or ())


def progress(db: Session, tenant_id: uuid.UUID, tried_before: tuple = ()) -> dict:
    """The chapters the organization acted in, for the Platform Admin overview; ``tried_before``: chapters tried before
    the sample data was removed (backend/app/trial/sample_removal.py), still counted."""
    return _reached(acted_counts(db, tenant_id), tried_before, last_activity(db, tenant_id))


def _reached(counts: dict[str, int], tried_before: tuple, moment: datetime | None) -> dict:
    """``progress`` from the chapter counts, the chapters tried before the sample was removed and the last activity."""
    acted = [code for code in CODES if counts.get(code) or code in tried_before]
    nxt = next((code for code in CODES if code not in acted), None)
    return {
        "acted": acted,
        "acted_count": len(acted),
        "total": len(CODES),
        "next": nxt,
        "counts": counts,
        "last_activity": moment.isoformat() if moment else None,
    }


def _investigations_open(db: Session, tenant_id: uuid.UUID) -> int:
    from backend.app.db.models.foundation import Investigation

    return _count(
        db,
        db.query(func.count(Investigation.id)).filter(
            Investigation.tenant_id == tenant_id, func.lower(Investigation.status).notin_(("closed", "cancelled"))
        ),
    )


def _decisions_open(db: Session, tenant_id: uuid.UUID) -> int:
    from backend.app.db.models.foundation import Decision, Investigation

    signed = db.query(Decision.investigation_id).filter(
        Decision.tenant_id == tenant_id, Decision.decision_kind == "BRIEF"
    )
    return _count(
        db,
        db.query(func.count(Investigation.id)).filter(
            Investigation.tenant_id == tenant_id,
            func.lower(Investigation.status).notin_(("closed", "cancelled")),
            Investigation.id.notin_(signed),
        ),
    )


# Signals still waiting for a person: not yet triaged, or decided for investigation but not yet in a case.
WAITING_SIGNAL_STATUSES = ("NEW", "TRIAGE", "INVESTIGATION_REQUIRED", "ESCALATED")


def _signals_waiting(db: Session, tenant_id: uuid.UUID) -> int:
    from backend.app.db.models.signals import InvestigationSignal, Signal

    linked = db.query(InvestigationSignal.signal_id).filter(InvestigationSignal.tenant_id == tenant_id)
    return _count(
        db,
        db.query(func.count(Signal.id)).filter(
            Signal.tenant_id == tenant_id,
            Signal.status.in_(WAITING_SIGNAL_STATUSES),
            Signal.id.notin_(linked),
        ),
    )


def _trends_finding(db: Session, tenant_id: uuid.UUID, trends: dict | None) -> dict:
    """Signals waiting for a decision or a case, and trends with no CAPA or risk review (the readiness check)."""
    waiting = _signals_waiting(db, tenant_id)
    without_action = int((trends or {}).get("value") or 0)
    parts = [f"{_plural(waiting, 'signal')} waiting for a decision or a case"]
    if without_action:
        parts.append(f"{_plural(without_action, 'trend')} with no CAPA or risk review")
    state = (trends or {}).get("state")
    return {
        "value": waiting + without_action,
        "text": "; ".join(parts),
        "state": "CRITICAL" if state == "CRITICAL" else "ATTENTION" if waiting or without_action else "CLEAR",
    }


# The trend chapter's finding while an import's signals are being found (they appear within seconds).
FINDING_SIGNALS = "Finding signals in the complaints you just imported…"


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


CASE_CHAPTERS = ("INVESTIGATE_WITH_AI", "DECIDE_AND_SIGN")


def _sample_case(db: Session, tenant_id: uuid.UUID) -> dict | None:
    """The guided investigation (SAMPLE-INV-001) while it is open: its id and product, else None."""
    from backend.app.db.models.foundation import Investigation

    try:
        case = (
            db.query(Investigation)
            .filter(Investigation.tenant_id == tenant_id, Investigation.investigation_identifier == "SAMPLE-INV-001")
            .first()
        )
    except Exception:
        db.rollback()
        return None
    if case is None or str(case.status or "").lower() in ("closed", "cancelled"):
        return None
    return {"id": str(case.id), "product_id": str(case.product_id) if case.product_id else None}


def story(
    db: Session,
    tenant_id: uuid.UUID,
    today: date | None = None,
    ai_ready: bool = False,
    cited: tuple = (),
    tried_before: tuple = (),
    signals_pending: bool = False,
) -> dict:
    """Every chapter with its finding from the organization's records and whether it acted on it. ``ai_ready``: AI
    answers for this organization now (backend/app/ai_settings.py ai_ready); without it the investigation chapter
    says what the case page does by itself. ``cited``: the chapters answering what the organization was cited for
    (backend/app/trial/citations.py): they are marked, and the next step is the first of them not yet tried.
    ``signals_pending``: an import's signals are still being found (backend/app/signals/hooks.py detection_pending):
    the trend chapter says so rather than count the signals found so far."""
    from backend.app.readiness_home.service import readiness

    today = today or datetime.now(timezone.utc).date()
    try:
        checks = {check["code"]: check for check in readiness(db, tenant_id, today)["checks"]}
    except Exception:
        logger.exception("Trial story: the readiness checks could not be read")
        db.rollback()
        checks = {}
    counts = acted_counts(db, tenant_id)
    open_cases = _investigations_open(db, tenant_id)
    awaiting = _decisions_open(db, tenant_id)
    findings = {
        "INVESTIGATE_WITH_AI": (open_cases, f"{_plural(open_cases, 'open case')} to investigate"),
        "DECIDE_AND_SIGN": (awaiting, f"{_plural(awaiting, 'case')} without a signed decision"),
        "YOUR_DATA": (
            counts["YOUR_DATA"],
            f"{_plural(counts['YOUR_DATA'], 'complaint')} of your own imported"
            if counts["YOUR_DATA"]
            else "Sample data only so far",
        ),
    }
    sample_case = _sample_case(db, tenant_id)
    chapters = []
    for number, (code, title, promise, pain, opens, check_code) in enumerate(CHAPTERS, 1):
        title, promise, pain = chapter_text(code, title, promise, pain, ai_ready)
        check = checks.get(check_code) if check_code else None
        if code == "TRENDS_TO_CASES" and signals_pending:
            finding = {"value": None, "text": FINDING_SIGNALS, "state": "NOT_SET"}
        elif code == "TRENDS_TO_CASES":
            finding = _trends_finding(db, tenant_id, checks.get("TRENDS_WITHOUT_ACTION"))
        elif code == "SHOW_THE_INSPECTOR":
            needing = [item for item in checks.values() if item.get("state") in ("CRITICAL", "ATTENTION")]
            finding = {
                "value": len(needing),
                "text": f"{len(needing)} of {len(checks)} inspection checks need attention" if checks else None,
                "state": "CRITICAL"
                if any(item.get("state") == "CRITICAL" for item in needing)
                else "ATTENTION"
                if needing
                else "CLEAR",
            }
        elif check is not None:
            finding = {"value": check.get("value"), "text": check.get("detail"), "state": check.get("state")}
        elif code in findings:
            value, text = findings[code]
            finding = {"value": value, "text": text, "state": "ATTENTION" if value and code != "YOUR_DATA" else "CLEAR"}
        else:
            finding = {"value": None, "text": None, "state": "NOT_SET"}
        chapters.append(
            {
                "code": code,
                "number": number,
                "title": title,
                "promise": promise,
                "pain": pain,
                "opens": opens,
                "finding": finding,
                "acted": {"done": bool(counts.get(code)) or code in tried_before, "count": counts.get(code, 0)},
                # The case these chapters are about (the guided investigation), so its button opens that case.
                "case": sample_case if code in CASE_CHAPTERS else None,
                "cited": code in cited,
            }
        )
    acted = sum(1 for chapter in chapters if chapter["acted"]["done"])
    waiting = [chapter["code"] for chapter in chapters if not chapter["acted"]["done"]]
    return {
        "as_of": today.isoformat(),
        "signals_pending": signals_pending,
        "acted": acted,
        "total": len(chapters),
        # What the organization was cited for comes first, then the story's order.
        "next": next((code for code in waiting if code in cited), waiting[0] if waiting else None),
        "chapters": chapters,
    }


# ------------------------------------------------------------------------------------------- Platform Admin overview
#
# Every trial at once, in a fixed number of statements however many trials there are: one per kind of information
# (the trials, their requests, feedback, demo requests, chapter counts, last activity), each grouped by tenant, then
# the people and uploads of the trials on the page shown. The summary and the attention list cover every trial; the
# table is one page of them, filtered and sorted on the server.

OVERVIEW_PAGE_SIZE = 50
OVERVIEW_PAGE_SIZE_MAX = 200
OVERVIEW_STATES = ("ACTIVE", "ENDING_SOON", "ENDED")
# How many trials "Who needs attention first" names (the most urgent, whatever page or filter the table shows).
ATTENTION_SHOWN = 5
# Columns the table can be sorted by across every page; without one it is in attention order.
OVERVIEW_SORTS = {
    "name": lambda item: item["name"],
    "tenant_key": lambda item: item["tenant_key"],
    "state": lambda item: item["expires_at"],
    "expires_at": lambda item: item["expires_at"],
    "days_left": lambda item: item["days_left"],
    "story": lambda item: item["story"]["acted_count"],
    "last_activity": lambda item: item["story"]["last_activity"],
    "demo": lambda item: (item["demo_request"] or {}).get("created_at"),
    "feedback": lambda item: (item["feedback"] or {}).get("overall"),
}


def _attention_rank(item: dict) -> tuple:
    """Trials that need a person first: ending soon and not engaged, then the least progress, then the fewest days
    left. Python's sort is stable, so equal trials keep the overview's base order (end date, then subscription)."""
    acted = item["story"]["acted_count"]
    state = item["state"]
    rank = 3 if state == "ENDED" else 0 if state == "ENDING_SOON" and acted < ENGAGED_CHAPTERS else 1
    return rank, acted, item["days_left"]


def _on_trial(statement):
    """``statement`` (a select from subscription lifecycles) limited to the Free Trial organizations still holding
    data on the trials' shared data plane: the overview's trials, as rows or as a subquery of their tenant ids."""
    from backend.app.db.data_plane import TRIAL_SHARED_DATA_PLANE
    from backend.app.db.models.customer_lifecycle import TenantDataPlane
    from backend.app.db.models.foundation import PlanDefinition, Tenant
    from backend.app.db.models.stage2 import SubscriptionLifecycle
    from backend.app.trial import service

    return (
        statement.join(PlanDefinition, PlanDefinition.id == SubscriptionLifecycle.plan_id)
        .join(Tenant, Tenant.id == SubscriptionLifecycle.tenant_id)
        .join(TenantDataPlane, TenantDataPlane.tenant_id == Tenant.id)
        .where(
            PlanDefinition.code == service.FREE_TRIAL_PLAN,
            TenantDataPlane.connection_secret_ref == TRIAL_SHARED_DATA_PLANE,
            Tenant.status != "ARCHIVED",
        )
    )


def grouped_counts(db: Session, counters, tenants) -> dict:
    """``{index: {tenant id: records}}`` for each ``(model, conditions)`` of ``counters``, among ``tenants`` (a list of
    ids or a subquery of them), in one statement. Should it fail (an older database without one of the tables), each
    is counted on its own and one that fails counts nothing, as ``_count`` does for one organization."""
    from sqlalchemy import literal, select, union_all

    if isinstance(tenants, (list, tuple, set)) and not tenants:
        return {}
    statements = [
        select(literal(index).label("counter"), model.tenant_id, func.count(model.id))
        .where(model.tenant_id.in_(tenants), *conditions)
        .group_by(model.tenant_id)
        for index, (model, conditions) in enumerate(counters)
    ]
    try:
        rows = db.execute(union_all(*statements)).all()
    except Exception:
        logger.exception("Trial overview: the counts could not be read together")
        db.rollback()
        rows = []
        for statement in statements:
            try:
                rows.extend(db.execute(statement).all())
            except Exception:
                logger.exception("Trial overview: a count could not be read")
                db.rollback()
    found: dict = {}
    for counter, tenant_id, records in rows:
        found.setdefault(counter, {})[tenant_id] = int(records or 0)
    return found


def acted_counts_by_tenant(db: Session, tenants) -> dict:
    """``{tenant id: acted_counts}`` for many organizations at once; one with no record at all is left out."""
    counters = chapter_counters()
    grouped = grouped_counts(db, [(model, conditions) for _code, model, conditions in counters], tenants)
    found: dict = {}
    for index, (code, _model, _conditions) in enumerate(counters):
        for tenant_id, records in grouped.get(index, {}).items():
            found.setdefault(tenant_id, dict.fromkeys(CODES, 0))[code] += records
    return found


def last_activity_by_tenant(db: Session, tenants) -> dict:
    """``{tenant id: last_activity}`` for many organizations at once."""
    from backend.app.db.models.foundation import AuditEvent

    try:
        return dict(
            db.query(AuditEvent.tenant_id, func.max(AuditEvent.created_at))
            .filter(AuditEvent.tenant_id.in_(tenants), _person_activity(AuditEvent))
            .group_by(AuditEvent.tenant_id)
            .all()
        )
    except Exception:
        logger.exception("Trial overview: the last activity could not be read")
        db.rollback()
        return {}


def uploaded_rows_by_tenant(db: Session, tenant_ids: list) -> dict:
    """``{tenant id: uploaded_rows}`` (backend/app/trial/imports.py) for many organizations at once."""
    from backend.app.trial.imports import upload_counters

    totals: dict = {}
    for per_tenant in grouped_counts(db, upload_counters(), tenant_ids).values():
        for tenant_id, records in per_tenant.items():
            totals[tenant_id] = totals.get(tenant_id, 0) + records
    return totals


def _requests_by_tenant(db: Session, tenants) -> dict:
    """``{tenant id: (email, profile)}``: the trial request that created each trial (backend/app/trial/team.py)."""
    from backend.app.db.models.stage2 import OnboardingRequest

    found: dict = {}
    for row in (
        db.query(
            OnboardingRequest.tenant_id,
            OnboardingRequest.email,
            OnboardingRequest.organization,
            OnboardingRequest.profile,
        )
        .filter(OnboardingRequest.tenant_id.in_(tenants))
        .order_by(OnboardingRequest.created_at, OnboardingRequest.id)
    ):
        found.setdefault(row.tenant_id, row)
    return found


def _people_by_tenant(db: Session, tenant_ids: list) -> dict:
    """``{tenant id: (seats used, owner, people)}``: people holding a seat (active or invited), the trial's first
    person, and those holding a seat as Platform Admin reads them (to reset one's MFA). The sample author, an account
    nobody signs in with, is none of them."""
    from backend.app.db.models.foundation import AuthUser
    from backend.app.trial.team import SEATED_STATUSES

    if not tenant_ids:
        return {}
    seats: dict = {}
    owners: dict = {}
    people: dict = {}
    for person in (
        db.query(AuthUser.id, AuthUser.tenant_id, AuthUser.username, AuthUser.display_name, AuthUser.status)
        .filter(AuthUser.tenant_id.in_(tenant_ids))
        .order_by(AuthUser.tenant_id, AuthUser.created_at, AuthUser.id)
    ):
        if person.status in SEATED_STATUSES:
            seats[person.tenant_id] = seats.get(person.tenant_id, 0) + 1
        if person.username.startswith("sample-author+"):
            continue
        view = {"id": str(person.id), "email": person.username, "name": person.display_name, "status": person.status}
        owners.setdefault(person.tenant_id, view)
        if person.status in SEATED_STATUSES:
            people.setdefault(person.tenant_id, []).append(view)
    return {
        tenant_id: (seats.get(tenant_id, 0), owners.get(tenant_id), people.get(tenant_id, []))
        for tenant_id in tenant_ids
    }


# How many of a trial's latest team changes the overview lists.
TEAM_CHANGES_SHOWN = 5


def _team_changes_by_tenant(data: Session, db: Session, tenant_ids: list) -> dict:
    """``{tenant id: [{change, person, at}]}``: the latest removals, withdrawn invitations and MFA resets each trial's
    owner made (backend/app/trial/team.py), newest first, from the trial's audit trail (``data``, in system scope);
    ``person`` is the email of the account changed (``db``)."""
    from backend.app.db.models.foundation import AuditEvent, AuthUser
    from backend.app.trial.team import SOURCE

    if not tenant_ids:
        return {}
    try:
        events = (
            data.query(
                AuditEvent.tenant_id, AuditEvent.action, AuditEvent.entity_id, AuditEvent.details, AuditEvent.created_at
            )
            .filter(
                AuditEvent.tenant_id.in_(tenant_ids),
                AuditEvent.action.in_(("TRIAL_COLLEAGUE_REMOVED", "USER_MFA_RESET")),
                AuditEvent.details["source"].astext == SOURCE,
            )
            .order_by(AuditEvent.created_at.desc(), AuditEvent.chain_seq.desc())
            .all()
        )
    except Exception:
        logger.exception("Trial overview: the team changes could not be read")
        data.rollback()
        return {}
    people = {event.entity_id for event in events if event.entity_id}
    emails = dict(db.query(AuthUser.id, AuthUser.username).filter(AuthUser.id.in_(people))) if people else {}
    found: dict = {}
    for event in events:
        changes = found.setdefault(event.tenant_id, [])
        if len(changes) >= TEAM_CHANGES_SHOWN:
            continue
        if event.action == "USER_MFA_RESET":
            change = "MFA_RESET"
        else:
            change = "INVITATION_WITHDRAWN" if (event.details or {}).get("invitation_withdrawn") else "REMOVED"
        changes.append(
            {
                "change": change,
                "person": emails.get(event.entity_id),
                "at": event.created_at.isoformat() if event.created_at else None,
            }
        )
    return found


def trial_overview(
    db: Session,
    now: datetime | None = None,
    *,
    page: int = 1,
    page_size: int = OVERVIEW_PAGE_SIZE,
    sort: str = "",
    order: str = "",
    state: str = "",
    q: str = "",
) -> dict:
    """Every Free Trial organization still holding data: its dates, usage, story progress and feedback.

    ``summary``, ``chapters`` and ``attention`` (who needs a person first) cover every trial; ``items`` is one page
    (``page``, ``page_size`` up to 200) of the trials in ``state`` (ACTIVE, ENDING_SOON or ENDED) whose name, tenant
    key, MDARIX ID or owner's email contains ``q``, in attention order or by ``sort``/``order`` (``OVERVIEW_SORTS``).
    ``db`` is the control database, which is also the trials' shared data plane: their records are read for every
    trial at once in a session of their own, in system scope (the caller has verified the Platform Admin)."""
    from sqlalchemy import select

    from backend.app.ai_settings import _models_in_use
    from backend.app.db.models.foundation import Tenant
    from backend.app.db.models.stage2 import SubscriptionLifecycle
    from backend.app.db.tenant_scope import bind_system
    from backend.app.sorting import parse_sort, sort_rows
    from backend.app.trial import citations
    from backend.app.trial import retention
    from backend.app.trial.mvp_request import data_move
    from backend.app.trial.service import TRIAL_ROW_LIMIT, TRIAL_USER_LIMIT

    ai_on_server = bool(_models_in_use())
    now = now or datetime.now(timezone.utc)
    page_size = min(OVERVIEW_PAGE_SIZE_MAX, max(1, int(page_size)))
    rows = db.execute(
        _on_trial(
            select(
                SubscriptionLifecycle.tenant_id,
                SubscriptionLifecycle.starts_at,
                SubscriptionLifecycle.expires_at,
                SubscriptionLifecycle.grace_ends_at,
                Tenant.business_id,
                Tenant.tenant_key,
                Tenant.name,
            ).select_from(SubscriptionLifecycle)
        ).order_by(SubscriptionLifecycle.expires_at, SubscriptionLifecycle.id)
    ).all()
    trial_ids = _on_trial(select(SubscriptionLifecycle.tenant_id).select_from(SubscriptionLifecycle))
    with Session(bind=db.get_bind(), autoflush=False) as data:
        bind_system(data, "platform administrator: trial overview")
        requests = _requests_by_tenant(db, trial_ids)
        feedback = _feedback_by_tenant(db, trial_ids) if rows else {}
        demos = _demos_by_tenant(db, trial_ids) if rows else {}
        counts = acted_counts_by_tenant(data, trial_ids) if rows else {}
        moments = last_activity_by_tenant(data, trial_ids) if rows else {}
        # When each trial's data is deleted: 30 days after it ends, or later while it asks to move it into the MVP.
        moves = retention.move_requests(db, trial_ids) if rows else {}
        movable = {
            tenant_id: bool(data_move(data, tenant_id)["allowed"])
            for tenant_id, asked in moves.items()
            if asked["open"] is not None
        }
        items, tenant_of, searched = [], {}, []
        for row in rows:
            request = requests.get(row.tenant_id)
            trial_end = max(row.expires_at, row.grace_ends_at or row.expires_at)
            kept = retention.plan_view(
                retention.retention_plan(trial_end, moves.get(row.tenant_id), movable.get(row.tenant_id, False), now)
            )
            ended = row.expires_at <= now
            seconds_left = (row.expires_at - now).total_seconds()
            item = {
                "tenant_id": str(row.tenant_id),
                "tenant_business_id": row.business_id,
                "tenant_key": row.tenant_key,
                "name": row.name,
                "owner": None,
                "people": [],
                "starts_at": row.starts_at.isoformat() if row.starts_at else None,
                "expires_at": row.expires_at.isoformat(),
                "data_deleted_at": kept["delete_after"],
                # Held while an open request asks to move the data into the MVP (backend/app/trial/retention.py).
                "retention": kept,
                "state": "ENDED" if ended else "ENDING_SOON" if seconds_left <= 7 * 86400 else "ACTIVE",
                "days_left": 0 if ended else max(0, int(-(-seconds_left // 86400))),
                "users": {"used": 0, "limit": TRIAL_USER_LIMIT},
                # The owner's latest removals, withdrawn invitations and MFA resets (filled in for the trials shown).
                "team_changes": [],
                "rows": {"used": 0, "limit": TRIAL_ROW_LIMIT},
                "story": _reached(
                    counts.get(row.tenant_id) or dict.fromkeys(CODES, 0),
                    remembered(request.profile if request else None),
                    moments.get(row.tenant_id),
                ),
                "feedback": feedback.get(row.tenant_id),
                "demo_request": demos.get(row.tenant_id),
                # What the organization said it was cited for (Getting started), to prepare the demo.
                "cited_for": citations.labels((request.profile or {}).get("citations") if request else ()),
            }
            items.append(item)
            tenant_of[id(item)] = row.tenant_id
            searched.append(
                " ".join(
                    str(value)
                    for value in (row.name, row.tenant_key, row.business_id, request.email if request else None)
                    if value
                ).casefold()
            )

        wanted = (state or "").strip().upper()
        needle = (q or "").strip().casefold()
        shown = [
            item
            for item, text in zip(items, searched)
            if (not wanted or item["state"] == wanted) and (not needle or needle in text)
        ]
        if parse_sort(sort, order)[0] in OVERVIEW_SORTS:
            shown = sort_rows(shown, sort, order, OVERVIEW_SORTS)
        else:
            shown = sorted(shown, key=_attention_rank)
        total = len(shown)
        pages = max(1, -(-total // page_size))
        page = min(max(1, int(page)), pages)
        page_items = shown[(page - 1) * page_size : page * page_size]
        attention = [item for item in sorted(items, key=_attention_rank) if item["state"] != "ENDED"][:ATTENTION_SHOWN]

        # The people, uploads and team changes of the trials shown (the page and the attention list), in four more
        # statements.
        shown_ids = list(dict.fromkeys(tenant_of[id(item)] for item in [*page_items, *attention]))
        people = _people_by_tenant(db, shown_ids)
        uploaded = uploaded_rows_by_tenant(data, shown_ids)
        team_changes = _team_changes_by_tenant(data, db, shown_ids)
    for item in {id(item): item for item in [*page_items, *attention]}.values():
        tenant_id = tenant_of[id(item)]
        seats, owner, seated = people.get(tenant_id, (0, None, []))
        item["owner"] = owner
        item["people"] = seated
        item["users"]["used"] = seats
        item["rows"]["used"] = uploaded.get(tenant_id, 0)
        item["team_changes"] = team_changes.get(tenant_id, [])

    active = [item for item in items if item["state"] != "ENDED"]
    return {
        "summary": {
            "trials": len(items),
            "active": len(active),
            "ending_soon": sum(1 for item in items if item["state"] == "ENDING_SOON"),
            "acted": sum(1 for item in active if item["story"]["acted_count"]),
            "engaged": sum(1 for item in active if item["story"]["acted_count"] >= ENGAGED_CHAPTERS),
            "own_data": sum(1 for item in active if item["story"]["counts"].get("YOUR_DATA")),
            "feedback": sum(1 for item in items if item["feedback"]),
            "demo_requested": sum(1 for item in items if item["demo_request"]),
            "chapters": {code: sum(1 for item in active if code in item["story"]["acted"]) for code in CODES},
        },
        # With no AI service on this server, the investigation chapter carries its without-AI title here too.
        "chapters": [
            {"code": code, "number": number, "title": chapter_text(code, title, promise, pain, ai_on_server)[0]}
            for number, (code, title, promise, pain, *_) in enumerate(CHAPTERS, 1)
        ],
        "engaged_chapters": ENGAGED_CHAPTERS,
        "attention": attention,
        "items": page_items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": pages,
    }


def _demos_by_tenant(db: Session, tenant_ids) -> dict:
    """``{tenant id: {status, created_at, business_id}}``: each trial's latest one-to-one demo request; ``tenant_ids``
    is a list of ids or a subquery of them."""
    from backend.app.db.models.stage2 import DemoRequest

    if isinstance(tenant_ids, list) and not tenant_ids:
        return {}
    found: dict = {}
    for row in (
        db.query(DemoRequest.trial_tenant_id, DemoRequest.status, DemoRequest.created_at, DemoRequest.business_id)
        .filter(DemoRequest.trial_tenant_id.in_(tenant_ids), DemoRequest.source == "TRIAL")
        .order_by(DemoRequest.created_at.desc())
    ):
        found.setdefault(
            row.trial_tenant_id,
            {
                "status": row.status,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "business_id": row.business_id,
            },
        )
    return found


def _feedback_by_tenant(db: Session, tenant_ids) -> dict:
    """``{tenant id: {responses, overall, recommend}}`` from the trial feedback (averages, rounded); ``tenant_ids`` is a
    list of ids or a subquery of them."""
    if isinstance(tenant_ids, list) and not tenant_ids:
        return {}
    from backend.app.db.models.stage2 import TrialFeedback

    try:
        rows = (
            db.query(
                TrialFeedback.tenant_id,
                func.count(TrialFeedback.id),
                func.avg(TrialFeedback.rating_overall),
                func.avg(TrialFeedback.recommend_score),
            )
            .filter(TrialFeedback.tenant_id.in_(tenant_ids))
            .group_by(TrialFeedback.tenant_id)
            .all()
        )
    except Exception:
        logger.exception("Trial overview: feedback could not be read")
        db.rollback()
        return {}
    return {
        tenant_id: {
            "responses": int(count),
            "overall": round(float(overall), 1) if overall is not None else None,
            "recommend": round(float(recommend), 1) if recommend is not None else None,
        }
        for tenant_id, count, overall, recommend in rows
    }
