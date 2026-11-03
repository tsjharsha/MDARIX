"""One record's page on the new navigation (0.10.74, Release C part C2): what the complaint page's Related and Activity
show, and the latest record each person signed (Records leads with it, for every organization).

- **Related**: the records linked to the complaint, each group in one or two plain lines: communications, market
  assessments, the service work, investigations, authority reports and decision records.
- **Activity**: the complaint's own audit events, newest first, in plain words (who, what, when). Nothing else is read
  or shown of an event (no network address, no browser). Sample records were loaded without audit events, so a sample
  complaint's activity starts with the record's own received and awareness times, marked as such.
- **Latest signed record**: the newest signature of this person in this organization (signed_approval_records, not
  invalidated), with what it signed and where it opens.

Reads only; every route keeps the organization's scope (another organization's complaint is "not found").
"""

from __future__ import annotations

import uuid

from sqlalchemy import or_

from backend.app.case_audit import rules as audit_rules
from backend.app.db.models.foundation import AuditEvent, SignedApprovalRecord

ACTIVITY_LIMIT = 100

# Plain words for the complaint's own audit events, where the code read as a sentence is not plain enough.
TITLES = {
    "COMPLAINT_MARKET_ASSESSMENT_STARTED": "Market assessment started",
    "COMPLAINT_MARKET_ASSESSMENT_SAVED": "Market assessment saved",
    "COMPLAINT_MARKET_CONCLUSION_SIGNED": "Market conclusion signed",
    "COMPLAINT_SERVICE_RECORDED": "Service work recorded",
    "COMPLAINT_SECOND_LOOK_DECIDED": "Second look decided",
    "COMPLAINT_STEP_SENT": "A step was sent to a colleague",
    "COMMUNICATION_RECORDED": "Message or request recorded",
    "COMMUNICATION_ANSWERED": "Reply recorded",
    "COMMUNICATION_CLOSED": "Request closed",
    "COMMUNICATION_ATTEMPT_RECORDED": "Contact attempt recorded",
    "TRIAGE_RECORDED": "Triage record completed",
    "TRIAGE_ESCALATED": "Triage escalated",
    "INTAKE_LOGGED": "Call logged",
    "FIRST_CONTACT_SIGNED": "First-contact check signed",
    "REPORT_SNAPSHOT_REQUESTED": "Authority report sent for approval",
    "REPORT_SNAPSHOT_APPROVED": "Authority report approved",
    "REPORT_SUBMISSION_RECORDED": "Submission to the authority recorded",
    "EVENT_OWNER_SET": "Owner named",
    "EVENT_READY_TO_CLOSE_SIGNED": "Ready to close signed",
    "EVENT_DECISION_RECORD_DOWNLOADED": "Decision record downloaded",
    "EVENT_DECISION_RECORD_FILED": "Decision record filed in the QMS",
}

# What each kind of signature is, in words (signed_approval_records.object_type).
SIGNED_WHAT = {
    "ComplaintMarketAssessment": "Market conclusion",
    "ComplaintDisposition": "Disposition",
    "EventClosure": "Ready to close",
    "ReportSnapshot": "Authority report approval",
    "FirstContactCheck": "First-contact check",
    "Decision": "Investigation decision",
    "CapaEffectivenessCheck": "CAPA effectiveness check",
    "DecisionGuideVersion": "Reportability guide version",
    "QmsDocumentVersion": "QMS document",
}


def _day(value) -> str | None:
    return value.isoformat() if value is not None else None


def related(db, found: dict, complaint, names: dict[str, str], service: dict | None, markets: list[str]) -> list[dict]:
    """The records linked to the complaint, in the order the page lists them; a group with nothing says so."""
    from backend.app.db.models.guides_communications import CommunicationEntry
    from backend.app.reportability import markets as market_rules
    from backend.app.reportability.assessments import current_and_draft

    entries = (
        db.query(CommunicationEntry)
        .filter(CommunicationEntry.tenant_id == complaint.tenant_id, CommunicationEntry.complaint_id == complaint.id)
        .order_by(CommunicationEntry.logged_at.desc())
        .limit(20)
        .all()
    )
    open_count = sum(1 for row in entries if row.status == "OPEN")
    communications = [
        f"{row.subject}"
        + (f" · reply due {row.reply_due_on.isoformat()}" if row.status == "OPEN" and row.reply_due_on else "")
        + ("" if row.status == "OPEN" else " · closed")
        for row in entries[:3]
    ]
    label = market_rules.MARKET_LABELS
    assessments = []
    for market in sorted(set(found["assessments"]) | set(markets)):
        current, draft = current_and_draft(found["assessments"].get(market, []))
        if current is not None:
            text = market_rules.CONCLUSION_LABELS.get(current.conclusion, current.conclusion)
            assessments.append(f"{label.get(market, market)}: {text}, signed {current.signed_at.date().isoformat()}")
        elif draft is not None:
            assessments.append(f"{label.get(market, market)}: started, not signed")
        else:
            assessments.append(f"{label.get(market, market)}: not assessed yet")
    from backend.app.authority_reports import forms as report_forms
    from backend.app.authority_reports import rules as report_rules

    # The form's name and the report's state in words, not their codes (0.10.75: it read "FDA_3500A · draft").
    reports = [
        f"{label.get(row.market, row.market)} · {report_forms.FORMS[row.form_code].title} · "
        + report_rules.STATE_LABELS.get(row.state, row.state).lower()
        for row in found["obligations"]
    ]
    decisions = [
        f"Disposition signed {row.signed_at.date().isoformat()} by {names.get(row.signed_by) or 'a colleague'}"
        for row in found["dispositions"]
        if row.signed_at is not None
    ]
    decisions += [
        f"Report approved {row.approved_at.date().isoformat()} by {names.get(row.approved_by or '') or 'a colleague'}"
        for row in found["snapshots"]
        if row.approved_at is not None
    ]
    return [
        {
            "key": "communications",
            "label": "Communications",
            "count": len(entries),
            "lines": [f"{len(entries)} recorded, {open_count} open", *communications] if entries else ["None recorded"],
        },
        {
            "key": "assessments",
            "label": "Market assessments",
            "count": len(assessments),
            "lines": assessments or ["No market to assess"],
        },
        {
            "key": "service",
            "label": "Service work",
            "count": 1 if service else 0,
            "lines": [
                f"{service['reference']} · {service['status_label']}"
                + (f" · owner {service['owner_name']}" if service.get("owner_name") else "")
            ]
            if service
            else ["None linked"],
        },
        {
            "key": "investigations",
            "label": "Investigation",
            "count": len(found["cases"]),
            "lines": [
                f"{case.business_id or case.investigation_identifier}: {case.investigation_question}"
                for case in found["cases"]
            ]
            or ["Not opened"],
            "items": [
                {"id": str(case.id), "ref": case.business_id or case.investigation_identifier}
                for case in found["cases"]
            ],
        },
        {
            "key": "reports",
            "label": "Authority reports",
            "count": len(reports),
            "lines": reports or ["None started"],
            "items": [{"id": str(row.id), "ref": row.market} for row in found["obligations"] if row.kind == "INITIAL"],
        },
        {
            "key": "decisions",
            "label": "Decision records",
            "count": len(decisions),
            "lines": decisions or ["Nothing signed yet: the event decision record lists each signature once made"],
        },
    ]


def _related_ids(found: dict, complaint) -> list[uuid.UUID]:
    ids = [complaint.id]
    record = found.get("record")
    if record is not None:
        ids.append(record.id)
    ids += [row.id for versions in found["assessments"].values() for row in versions]
    ids += [row.id for row in found["obligations"]] + [row.id for row in found["snapshots"]]
    ids += [row.id for row in found["dispositions"]] + [row.id for row in found["first_contact"]]
    ids += [uuid.UUID(str(item)) for item in found.get("intakes") or []]
    return ids


def activity(db, found: dict, complaint, names_of) -> dict:
    """The complaint's own audit events, newest first, in plain words; the record's own start below them."""
    from backend.app.db.models.guides_communications import CommunicationEntry
    from backend.app.db.models.oversight import EventClosure

    ids = _related_ids(found, complaint)
    ids += [
        row.id
        for row in db.query(CommunicationEntry.id).filter(
            CommunicationEntry.tenant_id == complaint.tenant_id, CommunicationEntry.complaint_id == complaint.id
        )
    ]
    ids += [
        row.id
        for row in db.query(EventClosure.id).filter(
            EventClosure.tenant_id == complaint.tenant_id, EventClosure.complaint_id == complaint.id
        )
    ]
    rows = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.tenant_id == complaint.tenant_id,
            or_(AuditEvent.entity_id.in_(ids), AuditEvent.details["complaint_id"].astext == str(complaint.id)),
            AuditEvent.action.notin_(list(audit_rules.IGNORED_AUDIT_ACTIONS)),
        )
        .order_by(AuditEvent.created_at.desc())
        .limit(ACTIVITY_LIMIT + 1)
        .all()
    )
    names = names_of({row.actor_ref for row in rows if row.actor_ref})
    items = [
        {
            "at": _day(row.created_at),
            "title": TITLES.get(row.action) or audit_rules.audit_title(row.action),
            "who": names.get(row.actor_ref or "") or ("MDARIX" if not row.actor_ref else "A colleague"),
            "reason": audit_rules.shorten(row.reason) if row.reason else None,
        }
        for row in rows[:ACTIVITY_LIMIT]
    ]
    # The record's own start (a sample record was loaded without audit events): from the complaint, not the trail.
    received, aware = complaint.complaint_timestamp, complaint.awareness_timestamp
    moments = (
        [(aware, "Received; awareness: the legal clocks count from here")]
        if received is not None and received == aware
        else [(received, "Complaint received"), (aware, "Awareness: the legal clocks count from here")]
    )
    start = [
        {"at": _day(at), "title": title, "who": None, "reason": None, "from_record": True}
        for at, title in sorted(
            (item for item in moments if item[0] is not None), key=lambda item: item[0], reverse=True
        )
    ]
    return {"items": items + start, "more": len(rows) > ACTIVITY_LIMIT}


def latest_signed(db, tenant_id, me: str, names_of) -> dict | None:
    """The newest record this person signed in this organization, with what it is and where it opens."""
    from backend.app.db.models.authority_reports import ReportObligation, ReportSnapshot
    from backend.app.db.models.complaint_disposition import ComplaintDisposition
    from backend.app.db.models.foundation import Complaint, Decision, Investigation
    from backend.app.db.models.market_assessment import ComplaintMarketAssessment
    from backend.app.db.models.oversight import EventClosure
    from backend.app.reportability import markets as market_rules

    row = (
        db.query(SignedApprovalRecord)
        .filter(
            SignedApprovalRecord.tenant_id == tenant_id,
            SignedApprovalRecord.signer_user_id == me,
            SignedApprovalRecord.invalidated_at.is_(None),
        )
        .order_by(SignedApprovalRecord.signed_at.desc())
        .first()
    )
    if row is None:
        return None
    what = SIGNED_WHAT.get(row.object_type) or audit_rules.readable(row.object_type)
    complaint_id = investigation_id = None
    if row.object_type == "ComplaintMarketAssessment":
        found = db.get(ComplaintMarketAssessment, row.object_id)
        if found is not None:
            complaint_id = found.complaint_id
            conclusion = market_rules.CONCLUSION_LABELS.get(found.conclusion or "", "")
            what = f"{market_rules.MARKET_LABELS.get(found.market, found.market)} conclusion: {conclusion.lower()}"
    elif row.object_type in ("ComplaintDisposition", "EventClosure"):
        model = ComplaintDisposition if row.object_type == "ComplaintDisposition" else EventClosure
        found = db.get(model, row.object_id)
        complaint_id = found.complaint_id if found is not None else None
    elif row.object_type == "ReportSnapshot":
        found = db.get(ReportSnapshot, row.object_id)
        obligation = db.get(ReportObligation, found.obligation_id) if found is not None else None
        if obligation is not None:
            complaint_id = obligation.complaint_id
            what = f"Authority report approved: {market_rules.MARKET_LABELS.get(obligation.market, obligation.market)}"
    elif row.object_type == "Decision":
        found = db.get(Decision, row.object_id)
        investigation_id = found.investigation_id if found is not None else None
    complaint = (
        db.query(Complaint).filter(Complaint.tenant_id == tenant_id, Complaint.id == complaint_id).one_or_none()
        if complaint_id
        else None
    )
    case = (
        db.query(Investigation)
        .filter(Investigation.tenant_id == tenant_id, Investigation.id == investigation_id)
        .one_or_none()
        if investigation_id
        else None
    )
    return {
        "what": what,
        "signed_at": _day(row.signed_at),
        "signed_by": names_of({me}).get(me),
        "meaning": row.signature_meaning,
        "complaint": {"id": str(complaint.id), "ref": complaint.complaint_identifier or complaint.business_id}
        if complaint is not None
        else None,
        "investigation": {"id": str(case.id), "ref": case.business_id or case.investigation_identifier}
        if case is not None
        else None,
    }
