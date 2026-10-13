"""The trial's story: the quality loop MDARIX closes, chapter by chapter, with what the trial's own data shows in each
and whether the organization has acted on it yet.

Each chapter answers one pain FDA and notified bodies cite in 2026 (MDARIX Final Lightweight MVP Plan, P1-P8): a
finding read from the organization's records (the sample data at first, its own export later) and a real action
recorded in MDARIX (a person decided a second-look record, recorded a reporting decision, opened a case from a
signal, ran the AI, signed a decision, planned or signed an effectiveness check, completed a risk review, downloaded
the readiness summary, imported their own complaints). Nothing here is inferred from page views.

``story`` serves the trial's Getting started page (findings and actions); ``progress`` serves the Platform Admin trial
overview (actions only, cheap enough for every trial at once).
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone

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
        "TRENDS_WITHOUT_ACTION",
    ),
    (
        "INVESTIGATE_WITH_AI",
        "Investigate with AI that shows its sources",
        "One AI run drafts the analysis, competing explanations and challenges; every statement cites the evidence "
        "and passes the automatic trust check, and the investigator judges each one.",
        "Small teams with large backlogs; AI that cannot show its sources is not trusted.",
        {"section": "Investigations", "tab": None},
        None,
    ),
    (
        "DECIDE_AND_SIGN",
        "Decide, sign and open the CAPA",
        "The Decision Brief writes itself from the case; a different person reviews it, the approver signs with "
        "password and authenticator code, and the CAPA opens from the signed decision.",
        "Trends that never become a CAPA are cited in most device warning letters.",
        {"section": "Decisions", "tab": None},
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
        "Upload an anonymized export of products, lots and complaints: each file is checked for problems and personal "
        "data before anything is saved, and every chapter above reads it.",
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


def acted_counts(db: Session, tenant_id: uuid.UUID) -> dict[str, int]:
    """How often the organization acted in each chapter (records it created in MDARIX), sample data excluded."""
    from backend.app.db.models.capa_effectiveness import CapaEffectivenessCheck
    from backend.app.db.models.case_ai import CaseAiRun
    from backend.app.db.models.complaint_review import ComplaintSecondLook
    from backend.app.db.models.foundation import AuditEvent, Complaint, Decision
    from backend.app.db.models.reportability import ComplaintReportability
    from backend.app.db.models.reviews import CaseReview
    from backend.app.db.models.signals import InvestigationSignal
    from backend.app.db.models.stage3 import AIInteraction
    from backend.app.trial.imports import UPLOAD_SOURCE

    def count(model, *conditions) -> int:
        return _count(db, db.query(func.count(model.id)).filter(model.tenant_id == tenant_id, *conditions))

    return {
        "HIDDEN_COMPLAINTS": count(ComplaintSecondLook),
        "REPORTING_CLOCKS": count(ComplaintReportability),
        "TRENDS_TO_CASES": count(InvestigationSignal),
        "INVESTIGATE_WITH_AI": count(CaseAiRun) + count(AIInteraction),
        "DECIDE_AND_SIGN": count(Decision, Decision.decision_kind == "BRIEF"),
        "CAPA_EFFECTIVE": count(CapaEffectivenessCheck),
        "RISK_FILE": count(CaseReview, CaseReview.review_type == "RISK", CaseReview.status == "COMPLETED"),
        "SHOW_THE_INSPECTOR": count(AuditEvent, AuditEvent.action == "READINESS_SUMMARY_EXPORTED"),
        "YOUR_DATA": count(Complaint, Complaint.source_system == UPLOAD_SOURCE),
    }


def last_activity(db: Session, tenant_id: uuid.UUID) -> datetime | None:
    """When a person last did something recorded in the audit trail (system events excluded)."""
    from backend.app.db.models.foundation import AuditEvent

    try:
        return (
            db.query(func.max(AuditEvent.created_at))
            .filter(AuditEvent.tenant_id == tenant_id, ~AuditEvent.actor_ref.like("system:%"))
            .scalar()
        )
    except Exception:
        logger.exception("Trial story: the last activity could not be read")
        db.rollback()
        return None


def progress(db: Session, tenant_id: uuid.UUID) -> dict:
    """The chapters the organization acted in, for the Platform Admin overview."""
    counts = acted_counts(db, tenant_id)
    acted = [code for code in CODES if counts.get(code)]
    nxt = next((code for code in CODES if not counts.get(code)), None)
    moment = last_activity(db, tenant_id)
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


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def story(db: Session, tenant_id: uuid.UUID, today: date | None = None) -> dict:
    """Every chapter with its finding from the organization's records and whether it acted on it."""
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
    chapters = []
    for number, (code, title, promise, pain, opens, check_code) in enumerate(CHAPTERS, 1):
        check = checks.get(check_code) if check_code else None
        if code == "SHOW_THE_INSPECTOR":
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
                "acted": {"done": bool(counts.get(code)), "count": counts.get(code, 0)},
            }
        )
    acted = sum(1 for chapter in chapters if chapter["acted"]["done"])
    return {
        "as_of": today.isoformat(),
        "acted": acted,
        "total": len(chapters),
        "next": next((chapter["code"] for chapter in chapters if not chapter["acted"]["done"]), None),
        "chapters": chapters,
    }


# ------------------------------------------------------------------------------------------- Platform Admin overview


def trial_overview(db: Session, now: datetime | None = None) -> dict:
    """Every Free Trial organization still holding data: its dates, usage, story progress and feedback. ``db`` is the
    control database (the trials' shared data plane); each trial's records are read in a session bound to it."""
    from backend.app.db.data_plane import TRIAL_SHARED_DATA_PLANE
    from backend.app.db.models.customer_lifecycle import TenantDataPlane
    from backend.app.db.models.foundation import AuthUser, PlanDefinition, Tenant
    from backend.app.db.models.stage2 import SubscriptionLifecycle
    from backend.app.db.tenant_scope import bind_tenant
    from backend.app.trial import imports
    from backend.app.trial.retention import RETENTION_DAYS
    from backend.app.trial.service import FREE_TRIAL_PLAN, TRIAL_ROW_LIMIT, TRIAL_USER_LIMIT

    now = now or datetime.now(timezone.utc)
    rows = (
        db.query(SubscriptionLifecycle, Tenant)
        .join(PlanDefinition, PlanDefinition.id == SubscriptionLifecycle.plan_id)
        .join(Tenant, Tenant.id == SubscriptionLifecycle.tenant_id)
        .join(TenantDataPlane, TenantDataPlane.tenant_id == Tenant.id)
        .filter(
            PlanDefinition.code == FREE_TRIAL_PLAN,
            TenantDataPlane.connection_secret_ref == TRIAL_SHARED_DATA_PLANE,
            Tenant.status != "ARCHIVED",
        )
        .order_by(SubscriptionLifecycle.expires_at)
        .all()
    )
    feedback = _feedback_by_tenant(db, [tenant.id for _, tenant in rows])
    items = []
    for subscription, tenant in rows:
        users = (
            db.query(func.count(AuthUser.id))
            .filter(AuthUser.tenant_id == tenant.id, AuthUser.status.in_(["ACTIVE", "INVITED"]))
            .scalar()
        )
        owner = (
            db.query(AuthUser.username, AuthUser.display_name, AuthUser.status)
            .filter(AuthUser.tenant_id == tenant.id)
            .order_by(AuthUser.created_at)
            .first()
        )
        with Session(bind=db.get_bind(), autoflush=False) as session:
            bind_tenant(session, tenant.id)
            reached = progress(session, tenant.id)
            rows_uploaded = imports.uploaded_rows(session, tenant.id)
        ended = subscription.expires_at <= now
        seconds_left = (subscription.expires_at - now).total_seconds()
        items.append(
            {
                "tenant_id": str(tenant.id),
                "tenant_business_id": tenant.business_id,
                "tenant_key": tenant.tenant_key,
                "name": tenant.name,
                "owner": {"email": owner.username, "name": owner.display_name, "status": owner.status}
                if owner
                else None,
                "starts_at": subscription.starts_at.isoformat() if subscription.starts_at else None,
                "expires_at": subscription.expires_at.isoformat(),
                "data_deleted_at": (subscription.expires_at + timedelta(days=RETENTION_DAYS)).isoformat(),
                "state": "ENDED" if ended else "ENDING_SOON" if seconds_left <= 7 * 86400 else "ACTIVE",
                "days_left": 0 if ended else max(0, int(-(-seconds_left // 86400))),
                "users": {"used": int(users or 0), "limit": TRIAL_USER_LIMIT},
                "rows": {"used": int(rows_uploaded or 0), "limit": TRIAL_ROW_LIMIT},
                "story": reached,
                "feedback": feedback.get(tenant.id),
            }
        )
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
            "chapters": {code: sum(1 for item in active if code in item["story"]["acted"]) for code in CODES},
        },
        "chapters": [
            {"code": code, "number": number, "title": title} for number, (code, title, *_) in enumerate(CHAPTERS, 1)
        ],
        "engaged_chapters": ENGAGED_CHAPTERS,
        "items": items,
    }


def _feedback_by_tenant(db: Session, tenant_ids: list) -> dict:
    """``{tenant id: {responses, overall, recommend}}`` from the trial feedback (averages, rounded)."""
    if not tenant_ids:
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
