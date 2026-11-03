"""The event: its owner, its stage line, its closure-readiness checklist and its event decision record (T-G28, MVP G28).

An event is a complaint as MDARIX works on it, from triage to "ready to close in the QMS". Everything here is read
from the records that already exist (triage, first-contact checks, market assessments, report obligations, the
disposition, the case and its decision, the communications log, My Work), so there is no second workflow:

- **The event owner** is the person named on the event (``event_closures.owner_id``), else the triage record's event
  owner, else nobody yet.
- **The stage line** is a summary, never a gate: triage, market assessment, investigation, decision, ready to close,
  closed in the QMS. Several can be open at once.
- **The checklist** (a higher-risk function: each blocking item says why and where it is resolved): triage complete;
  the first-contact check signed, where the event began as a contact; every relevant market assessed and signed, no
  reassessment open; every report obligation met; the disposition or the investigation decision signed; every
  information request answered or closed; no task on the event open. Open CAPAs are listed and do not block: they
  close in the QMS.
- **Ready to close in the QMS** is signed by the event owner with their password: when the checklist is clear, or
  with a written reason when it is not. MDARIX never closes the complaint: the QMS does, under the customer's
  procedure.
- **The event decision record** collects every signed decision on the event, with each signature's manifestation
  (the printed name, the date and time in UTC, the meaning) and a SHA-256 checksum of its content.
"""

from __future__ import annotations

from backend.app import links
import hashlib
import json
import uuid

from sqlalchemy.orm import Session

from backend.app.db.models.oversight import EventClosure

PASS, BLOCKED, NOT_REQUIRED, INFO = "PASS", "BLOCKED", "NOT_REQUIRED", "INFO"
RESULT_LABELS = {PASS: "Done", BLOCKED: "Open", NOT_REQUIRED: "Not needed", INFO: "Stays open in your QMS"}
STAGES = (
    ("TRIAGE", "Triage"),
    ("MARKETS", "Market assessment"),
    ("INVESTIGATION", "Investigation"),
    ("DECISION", "Decision"),
    ("READY", "Ready to close"),
    ("CLOSED", "Closed in the QMS"),
)
CLOSED_STATUSES = ("closed", "cancelled", "canceled", "completed", "done")
REASON_MIN, REASON_MAX, FILING_MAX = 20, 2000, 120
OBJECT_TYPE, DECISION_TYPE = "EventClosure", "EVENT_READY_TO_CLOSE"
NEVER_CLOSES = (
    "MDARIX never closes the complaint: it shows when every MDARIX decision on it is signed. Close the complaint in "
    "your QMS under your procedure, and file the event decision record there first."
)


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _check(code: str, label: str, result: str, detail: str, opens: dict | None = None) -> dict:
    return {
        "code": code,
        "label": label,
        "result": result,
        "result_label": RESULT_LABELS[result],
        "detail": detail,
        "opens": opens,
    }


def _n(count: int, noun: str) -> str:
    return f"{count} {noun}" + ("" if count == 1 else "s")


def closure_row(db: Session, tenant_id, complaint_id) -> EventClosure | None:
    return (
        db.query(EventClosure)
        .filter(EventClosure.tenant_id == tenant_id, EventClosure.complaint_id == complaint_id)
        .one_or_none()
    )


def triage_record(db: Session, tenant_id, complaint_id):
    from backend.app.db.models.intake import TriageRecord

    return (
        db.query(TriageRecord)
        .filter(
            TriageRecord.tenant_id == tenant_id,
            TriageRecord.subject_kind == "COMPLAINT",
            TriageRecord.subject_id == complaint_id,
        )
        .one_or_none()
    )


def owner_of(row: EventClosure | None, record) -> str | None:
    if row is not None and row.owner_id:
        return row.owner_id
    return record.event_owner if record is not None else None


def _linked_intakes(db: Session, tenant_id, complaint_id) -> list[uuid.UUID]:
    from backend.app.db.models.intake import RecordLink

    found = []
    for link in db.query(RecordLink).filter(
        RecordLink.tenant_id == tenant_id,
        RecordLink.state == "LINKED",
        (RecordLink.left_id == complaint_id) | (RecordLink.right_id == complaint_id),
    ):
        if link.left_kind == "INTAKE" and link.right_id == complaint_id:
            found.append(link.left_id)
        elif link.right_kind == "INTAKE" and link.left_id == complaint_id:
            found.append(link.right_id)
    return found


def _cases(db: Session, tenant_id, complaint_id, disposition) -> list:
    from backend.app.db.models.foundation import Investigation, InvestigationComplaint

    ids = {
        row.investigation_id
        for row in db.query(InvestigationComplaint.investigation_id).filter(
            InvestigationComplaint.tenant_id == tenant_id, InvestigationComplaint.complaint_id == complaint_id
        )
    }
    if disposition is not None and disposition.investigation_id:
        ids.add(disposition.investigation_id)
    if not ids:
        return []
    return db.query(Investigation).filter(Investigation.tenant_id == tenant_id, Investigation.id.in_(list(ids))).all()


def open_tasks_by_complaint(db: Session, tenant_id) -> dict[str, list]:
    """Open My Work tasks by the complaint they are about (read once for a list of events)."""
    from backend.app.db.models.workflow import OPEN_TASK_STATUSES, WorkflowTask

    found: dict[str, list] = {}
    for task in db.query(WorkflowTask).filter(
        WorkflowTask.tenant_id == tenant_id, WorkflowTask.status.in_(list(OPEN_TASK_STATUSES))
    ):
        key = (task.details or {}).get("complaint_id") or (
            task.source_entity_id if task.source_entity_type == "Complaint" else None
        )
        if key:
            found.setdefault(str(key), []).append(task)
    return found


def open_on_triage(db: Session, tenant_id) -> set[str]:
    """The complaints open on the triage list (flagged or escalated, triage not complete), read once for a list."""
    from backend.app.intake import service as intake

    found: set[str] = set()
    for item in intake.triage(db, None, tenant_id, "open")["items"]:
        found |= {member.split(":", 1)[1] for member in item["members"] if member.startswith(f"{intake.COMPLAINT}:")}
    return found


def facts(
    db: Session, tenant_id, complaint, tasks: dict[str, list] | None = None, triage: set[str] | None = None
) -> dict:
    """Everything the checklist, the stage line and the decision record read, in one place (``tasks``: the open
    tasks by complaint, when already read)."""
    from backend.app.communications.service import open_requests
    from backend.app.db.models.authority_reports import ReportObligation, ReportSnapshot
    from backend.app.db.models.complaint_disposition import ComplaintDisposition
    from backend.app.db.models.foundation import Capa, Decision
    from backend.app.db.models.intake import FirstContactCheck
    from backend.app.intake.service import enabled_markets
    from backend.app.reportability.assessments import rows_by_complaint

    dispositions = (
        db.query(ComplaintDisposition)
        .filter(ComplaintDisposition.tenant_id == tenant_id, ComplaintDisposition.complaint_id == complaint.id)
        .order_by(ComplaintDisposition.version)
        .all()
    )
    current_disposition = next((row for row in reversed(dispositions) if row.superseded_by is None), None)
    cases = _cases(db, tenant_id, complaint.id, current_disposition)
    case_ids = [case.id for case in cases]
    decisions = (
        db.query(Decision).filter(Decision.tenant_id == tenant_id, Decision.investigation_id.in_(case_ids)).all()
        if case_ids
        else []
    )
    intakes = _linked_intakes(db, tenant_id, complaint.id)
    checks = (
        db.query(FirstContactCheck)
        .filter(FirstContactCheck.tenant_id == tenant_id, FirstContactCheck.intake_event_id.in_(intakes))
        .order_by(FirstContactCheck.version)
        .all()
        if intakes
        else []
    )
    obligations = (
        db.query(ReportObligation)
        .filter(ReportObligation.tenant_id == tenant_id, ReportObligation.complaint_id == complaint.id)
        .all()
    )
    snapshots = (
        db.query(ReportSnapshot)
        .filter(ReportSnapshot.tenant_id == tenant_id, ReportSnapshot.obligation_id.in_([o.id for o in obligations]))
        .all()
        if obligations
        else []
    )
    tasks = (tasks if tasks is not None else open_tasks_by_complaint(db, tenant_id)).get(str(complaint.id), [])
    capas = (
        db.query(Capa).filter(Capa.tenant_id == tenant_id, Capa.investigation_id.in_(case_ids)).all()
        if case_ids
        else []
    )
    return {
        "complaint": complaint,
        "record": triage_record(db, tenant_id, complaint.id),
        "on_triage": str(complaint.id) in (triage if triage is not None else open_on_triage(db, tenant_id)),
        "intakes": intakes,
        "first_contact": checks,
        "assessments": rows_by_complaint(db, tenant_id, [complaint.id]).get(complaint.id, {}),
        "enabled": enabled_markets(db, tenant_id),
        "obligations": obligations,
        "snapshots": snapshots,
        "dispositions": dispositions,
        "disposition": current_disposition,
        "cases": cases,
        "decisions": decisions,
        "requests": open_requests(db, tenant_id, [complaint.id]),
        "tasks": tasks,
        "capas": capas,
    }


def _open(case) -> bool:
    return str(case.status or "open").lower() not in CLOSED_STATUSES


def _signed_decision(row) -> bool:
    from backend.app.case_workflow.readiness import SIGNED_DECISION_STATUSES
    from backend.app.human_decision.rules import SIGNED

    return str(row.decision_status or "").upper() in {*SIGNED_DECISION_STATUSES, SIGNED}


def checklist(found: dict) -> list[dict]:
    """The closure-readiness checklist (see the module docstring), each item with where it is resolved."""
    from backend.app.authority_reports import rules as report_rules
    from backend.app.communications.service import TASK_TYPE as REPLY_TASK
    from backend.app.reportability import markets
    from backend.app.reportability import rules as reporting_rules
    from backend.app.reportability.assessments import current_and_draft, required_markets
    from backend.app.reportability.service import _record

    complaint = found["complaint"]
    reports = links.target("Complaints", "Reports", record=("complaint", complaint.id))
    items = []
    # What to do next, one imperative per open item (the event summary's next action and the events list).
    actions: dict[str, str] = {
        "TRIAGE": "Complete the triage record (on the triage list)",
        "FIRST_CONTACT": "Sign the first-contact check",
        "DECISION": "Sign the disposition",
        "TASKS": "Finish the open task in My Work",
    }
    record = found["record"]
    if found["on_triage"] or (record is not None and record.completed_at is None):
        items.append(
            _check(
                "TRIAGE",
                "Triage is complete",
                BLOCKED,
                "On the triage list: its triage record is not complete",
                # Each step opens on this complaint, not on the whole list (0.10.68: the complaint page opens it).
                links.target("Complaints", "Triage", record=("complaint", complaint.id)),
            )
        )
    elif record is None:
        items.append(_check("TRIAGE", "Triage is complete", NOT_REQUIRED, "Not flagged for triage"))
    else:
        items.append(_check("TRIAGE", "Triage is complete", PASS, f"Completed {record.completed_at:%d %b %Y}"))
    if not found["intakes"]:
        items.append(_check("FIRST_CONTACT", "The first-contact check is signed", NOT_REQUIRED, "Not from a contact"))
    else:
        signed = [row for row in found["first_contact"] if row.signed_at is not None]
        items.append(
            _check("FIRST_CONTACT", "The first-contact check is signed", PASS, "Signed")
            if signed or not found["first_contact"]
            else _check(
                "FIRST_CONTACT",
                "The first-contact check is signed",
                BLOCKED,
                "The check is not signed",
                links.target("Complaints", "First contact"),
            )
        )
    by_market = found["assessments"]
    # The event's own market is relevant when the complaint reports harm or a malfunction (the reportability watch's
    # rule); every market already assessed stays relevant.
    watched = reporting_rules.watched(_record(complaint, None, None))
    wanted = required_markets(complaint.country, found["enabled"] if watched else [], by_market)
    open_markets = []
    for market in wanted:
        current, draft = current_and_draft(by_market.get(market, []))
        label = markets.MARKET_LABELS.get(market, market)
        if current is None and draft is None:
            open_markets.append(f"{label} not assessed")
            actions.setdefault("MARKETS", f"Assess the {label} market")
        elif current is None:
            open_markets.append(f"{label} not signed")
            actions.setdefault("MARKETS", f"Sign the {label} market assessment")
        elif draft is not None:
            open_markets.append(f"{label} reassessment open")
            actions.setdefault("MARKETS", f"Sign the {label} reassessment")
    items.append(
        _check(
            "MARKETS",
            "Every relevant market is assessed and signed",
            BLOCKED if open_markets else PASS if wanted else NOT_REQUIRED,
            "; ".join(open_markets)
            if open_markets
            else (f"{_n(len(wanted), 'market')} signed" if wanted else "No market to assess"),
            links.target("Complaints", "Reportability", record=("complaint", complaint.id)) if open_markets else None,
        )
    )
    started = {row.market for row in found["obligations"] if row.kind == "INITIAL"}
    unmet = []
    for row in found["obligations"]:
        if row.state in report_rules.MET:
            continue
        label, state = markets.MARKET_LABELS.get(row.market, row.market), report_rules.STATE_LABELS[row.state].lower()
        unmet.append(f"{label}: {state}")
        actions.setdefault("OBLIGATIONS", f"Complete the {label} report ({state})")
    for market in wanted:
        current, _ = current_and_draft(by_market.get(market, []))
        if (
            current is not None
            and current.conclusion == markets.REPORTABLE
            and market not in started
            and not current.filed_on
        ):
            unmet.append(f"{markets.MARKET_LABELS.get(market, market)}: reportable, the report is not started")
            actions.setdefault("OBLIGATIONS", f"Start the {markets.MARKET_LABELS.get(market, market)} report")
    items.append(
        _check(
            "OBLIGATIONS",
            "Every report obligation is met",
            BLOCKED if unmet else PASS if found["obligations"] else NOT_REQUIRED,
            "; ".join(unmet)
            if unmet
            else (f"{_n(len(found['obligations']), 'obligation')} met" if found["obligations"] else "No report raised"),
            reports if unmet else None,
        )
    )
    disposition = found["disposition"]
    signed_case = [row for row in found["decisions"] if _signed_decision(row)]
    escalated = disposition is not None and disposition.branch.startswith("ESCALATED")
    if signed_case:
        items.append(_check("DECISION", "The decision is signed", PASS, "The investigation decision is signed"))
    elif disposition is not None and not escalated:
        branch = "service-level resolution" if disposition.branch == "SERVICE_LEVEL" else "known issue"
        items.append(_check("DECISION", "The decision is signed", PASS, f"The disposition is signed as a {branch}"))
    else:
        # A complaint in an investigation's scope is decided there (0.10.70: it asked "Sign the disposition" while its
        # stage read "Investigation").
        in_case = escalated or (disposition is None and any(_open(case) for case in found["cases"]))
        if in_case:
            actions["DECISION"] = "Sign the investigation's decision"
        items.append(
            _check(
                "DECISION",
                "The decision is signed",
                BLOCKED,
                "Escalated to an investigation: its decision is not signed"
                if escalated
                else "In an investigation: its decision is not signed"
                if in_case
                else "No disposition or investigation decision is signed",
                _case_decision(found, disposition)
                if in_case
                else links.target("Complaints", "Dispositions", record=("disposition", complaint.id)),
            )
        )
    requests = found["requests"]
    actions["REQUESTS"] = (
        "Answer or close the open information request"
        if len(requests) == 1
        else f"Answer or close the {len(requests)} open information requests"
    )
    items.append(
        _check(
            "REQUESTS",
            "Every information request is answered or closed",
            BLOCKED if requests else PASS,
            f"{_n(len(requests), 'request')} still open" if requests else "None open",
            links.target("Complaints", "Communications", record=("complaint", complaint.id)) if requests else None,
        )
    )
    tasks = [task for task in found["tasks"] if task.task_type != REPLY_TASK]
    if len(tasks) > 1:
        actions["TASKS"] = f"Finish the {len(tasks)} open tasks in My Work"
    items.append(
        _check(
            "TASKS",
            "No task on the event is open",
            BLOCKED if tasks else PASS,
            "; ".join(task.title for task in tasks[:3]) + (f" and {len(tasks) - 3} more" if len(tasks) > 3 else "")
            if tasks
            else "None open",
            links.target("My Work") if tasks else None,
        )
    )
    capas = [row for row in found["capas"] if str(row.status or "").lower() not in CLOSED_STATUSES]
    if capas:
        items.append(
            _check(
                "CAPA",
                "Follow-ups in your QMS",
                INFO,
                ", ".join(row.business_id or row.capa_identifier for row in capas)
                + ": they may stay open and stay on the oversight view until they close in your QMS",
                links.target("Records", "Effectiveness checks", record=("capa", capas[0].id)),
            )
        )
    for item in items:
        item["action"] = actions.get(item["code"]) if item["result"] == BLOCKED else None
    return items


def _case_decision(found: dict, disposition) -> dict:
    """An escalated complaint's decision opens on its investigation's decision, not on the list of investigations
    (stage 8: the walk-through's next step needs no search)."""
    case = next(
        (
            row
            for row in found["cases"]
            if (row.id == disposition.investigation_id if disposition is not None else _open(row))
        ),
        None,
    )
    return (
        links.target("Investigations", "Decision", record=("case", case.id)) if case else links.target("Investigations")
    )


def fingerprint(complaint_id, items: list[dict]) -> str:
    content = {
        "complaint": str(complaint_id),
        "checks": [{key: item[key] for key in ("code", "result", "detail")} for item in items],
    }
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode("utf-8")).hexdigest()


def settled(complaint, items: list[dict], row: EventClosure | None) -> bool:
    """A finished event (0.10.70): closed in the QMS after its ready to close was signed, and its checklist is as it was
    signed. Any item still open was signed with its reason, so the event asks for no next step and no stage is current;
    a change since signing (a new trigger, a report) asks again."""
    return (
        str(complaint.status or "").lower() in CLOSED_STATUSES
        and row is not None
        and row.ready_state is not None
        and row.content_fingerprint == fingerprint(complaint.id, items)
    )


def stage_line(found: dict, items: list[dict], row: EventClosure | None) -> list[dict]:
    """Each stage with its state: done, open (work in it is not finished), later, or not needed (no check of the stage
    applies to this event: no case, no market clock; J29). A summary, never a gate."""
    results = {item["code"]: item["result"] for item in items}

    def done(*codes: str) -> bool:
        return all(results.get(code, NOT_REQUIRED) != BLOCKED for code in codes)

    def needed(*codes: str) -> bool:
        return any(results.get(code, NOT_REQUIRED) != NOT_REQUIRED for code in codes)

    complaint = found["complaint"]
    open_case = any(str(case.status or "").lower() == "open" for case in found["cases"])
    closed = str(complaint.status or "").lower() in CLOSED_STATUSES
    ready = row is not None and row.ready_state is not None
    state = {
        "TRIAGE": done("TRIAGE", "FIRST_CONTACT"),
        "MARKETS": done("MARKETS", "OBLIGATIONS"),
        "INVESTIGATION": not open_case,
        "DECISION": done("DECISION"),
        "READY": ready,
        "CLOSED": closed,
    }
    # Without an investigation, whether one is needed is known only once the decision is signed (0.10.70: it read
    # "Investigation: not needed" before any disposition, a serious injury included).
    undecided = not found["cases"] and not done("DECISION")
    skipped = {
        "TRIAGE": not needed("TRIAGE", "FIRST_CONTACT"),
        "MARKETS": not needed("MARKETS", "OBLIGATIONS"),
        "INVESTIGATION": not found["cases"] and not undecided,
        "DECISION": not needed("DECISION"),
    }
    later = {"INVESTIGATION"} if undecided else set()
    first_open = (
        None
        if settled(complaint, items, row)
        else next((code for code, _ in STAGES if not state[code] and not skipped.get(code) and code not in later), None)
    )
    return [
        {
            "code": code,
            "label": label,
            "state": "LATER"
            if code in later
            else "NOT_NEEDED"
            if skipped.get(code)
            else "DONE"
            if state[code]
            else "CURRENT"
            if code == first_open
            else "OPEN"
            if code != "CLOSED"
            else "LATER",
        }
        for code, label in STAGES
    ]


# --------------------------------------------------------------------------------------------- the decision record


def _manifest(record, names: dict, by: str | None, at) -> dict:
    """A signature's manifestation (21 CFR 11.50): the printed name, the date and time (UTC) and the meaning."""
    return {
        "signer": names.get(by or "") or ("MDARIX sample data" if (by or "").startswith("system:") else "A colleague"),
        "signed_at": _iso(at),
        "meaning": record.signature_meaning if record is not None else None,
        "record_id": str(record.id) if record is not None else None,
        "record_ref": getattr(record, "business_id", None) if record is not None else None,
    }


def decision_record(control_db: Session, found: dict, row: EventClosure | None, names: dict) -> dict:
    """Every signed decision on the event, oldest first, with a SHA-256 checksum of the whole."""
    from backend.app.db.models.foundation import SignedApprovalRecord
    from backend.app.reportability import markets

    def record(record_id):
        if not record_id or control_db is None:
            return None
        return control_db.get(SignedApprovalRecord, record_id)

    entries = []
    for check in found["first_contact"]:
        if check.signed_at is not None:
            entries.append(
                {
                    "kind": "First-contact check",
                    "summary": f"Version {check.version}: {str(check.classification or '').replace('_', ' ').lower()}",
                    "reason": check.reason or check.override_reason,
                    **_manifest(record(check.signed_record_id), names, check.signed_by, check.signed_at),
                }
            )
    record_row = found["record"]
    if record_row is not None and record_row.completed_at is not None:
        entries.append(
            {
                "kind": "Triage",
                "summary": "Triage record completed"
                + (f", severity {record_row.severity.lower()}" if record_row.severity else ""),
                "reason": record_row.immediate_action or record_row.no_action_reason,
                **_manifest(None, names, record_row.completed_by, record_row.completed_at),
                "meaning": "Recorded, not signed",
            }
        )
    for market, versions in found["assessments"].items():
        for version in versions:
            if version.conclusion is None:
                continue
            kind = markets.REPORT_TYPES.get(version.report_type or "")
            entries.append(
                {
                    "kind": f"Market conclusion, {markets.MARKET_LABELS.get(market, market)}",
                    "summary": f"Version {version.version}: {markets.CONCLUSION_LABELS.get(version.conclusion, version.conclusion)}"
                    + (f" ({kind.label})" if kind else "")
                    + (", superseded" if version.superseded_by else ""),
                    "reason": version.override_reason,
                    **_manifest(record(version.signed_record_id), names, version.signed_by, version.signed_at),
                }
            )
    for disposition in found["dispositions"]:
        entries.append(
            {
                "kind": "Disposition",
                "summary": f"Version {disposition.version}: {disposition.branch.replace('_', ' ').lower()}"
                + (
                    f"; attribution {disposition.attribution.replace('_', ' ').lower()}"
                    if disposition.attribution
                    else ""
                )
                + (", superseded" if disposition.superseded_by else ""),
                "reason": disposition.attribution_reason or disposition.change_reason,
                **_manifest(record(disposition.signed_record_id), names, disposition.signed_by, disposition.signed_at),
            }
        )
    for decision in found["decisions"]:
        if not _signed_decision(decision):
            continue
        attribution = getattr(decision, "root_cause_attribution", None)
        entries.append(
            {
                "kind": "Investigation decision",
                "summary": f"{decision.business_id or decision.decision_identifier}: "
                + str(decision.outcome or decision.disposition).replace("_", " ").lower()
                + (f"; attribution {attribution.replace('_', ' ').lower()}" if attribution else ""),
                "reason": decision.rationale,
                **_manifest(
                    None,
                    names,
                    str(decision.decided_by_user_id or decision.authorized_by_ref),
                    decision.decided_at or decision.decision_timestamp,
                ),
                "meaning": "Signed decision on the case",
            }
        )
    for snapshot in found["snapshots"]:
        if snapshot.approved_at is None:
            continue
        obligation = next((o for o in found["obligations"] if o.id == snapshot.obligation_id), None)
        entries.append(
            {
                "kind": "Report approval",
                "summary": f"{markets.MARKET_LABELS.get(obligation.market, obligation.market) if obligation else 'Report'}"
                f", snapshot {snapshot.version} approved",
                "reason": None,
                **_manifest(record(snapshot.signed_record_id), names, snapshot.approved_by, snapshot.approved_at),
            }
        )
    if row is not None and row.ready_state is not None:
        entries.append(
            {
                "kind": "Ready to close in the QMS",
                "summary": f"Version {row.version}: "
                + ("checklist clear" if row.ready_state == "READY" else "signed with items still open"),
                "reason": row.ready_reason,
                **_manifest(record(row.signed_record_id), names, row.signed_by, row.signed_at),
            }
        )
    entries.sort(key=lambda entry: entry["signed_at"] or "")
    checksum = hashlib.sha256(json.dumps(entries, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return {
        "entries": entries,
        "sha256": checksum,
        "version": row.version if row is not None else 0,
        "filed": {
            "reference": row.qms_filing_ref,
            "by": names.get(row.filed_by or "") or "A colleague",
            "at": _iso(row.filed_at),
        }
        if row is not None and row.qms_filing_ref
        else None,
    }


def signature_meaning(ref: str, version: int, blocked: int) -> str:
    if blocked:
        return (
            f"I, the event owner, sign that event {ref} (version {version}) is ready to close in the QMS with "
            f"{_n(blocked, 'item')} still open, for the reason I gave"
        )
    return (
        f"I, the event owner, sign that every MDARIX decision on event {ref} (version {version}) is signed and it is "
        "ready to close in the QMS"
    )


def render_pdf(view: dict, organization: str | None) -> bytes:
    from reports import pdf

    event, record = view["event"], view["decision_record"]
    header = [
        f"Organization: {organization or '-'}",
        f"Event: {event['ref']} ({event['product'] or 'no product'})",
        f"Event owner: {event['owner_name'] or 'not named'}",
        f"Record version {record['version']}; SHA-256 of its content: {record['sha256']}",
    ]
    if view.get("practice_label"):
        header.append(view["practice_label"])
    lines = [("Signed decisions", "heading")]
    for entry in record["entries"]:
        lines.append((f"{entry['kind']}: {entry['summary']}", "body"))
        if entry.get("reason"):
            lines.append((f"    Reason: {entry['reason']}", "muted"))
        lines.append(
            (f"    {entry['signer']}, {entry['signed_at'] or '-'} UTC. Meaning: {entry['meaning'] or '-'}", "muted")
        )
        if entry.get("record_ref") or entry.get("record_id"):
            lines.append((f"    Signature record: {entry['record_ref'] or entry['record_id']}", "muted"))
    lines += [("", "body"), ("Closure-readiness checklist", "heading")]
    for item in view["checklist"]:
        lines.append((f"{item['result_label']}: {item['label']}. {item['detail']}", "body"))
    lines += [("", "body"), (NEVER_CLOSES, "muted")]
    watermark = (
        "PRACTICE RECORD - NOT YOUR REGULATORY RECORD" if view.get("practice_label") else "EVENT DECISION RECORD"
    )
    return pdf.render(
        f"MDARIX event decision record: {event['ref']}",
        header,
        lines,
        watermark=watermark,
        footer=f"{event['ref']} - record version {record['version']} - MDARIX never decides",
    )
