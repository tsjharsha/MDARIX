"""Reopen triggers (B5 spec 3.6, B5-D7): when the records after a signed decision say its action may not have worked,
MDARIX opens an impact assessment for a person. It never reopens, changes or decides anything itself.

``fired`` is pure: it reads one Did it work? view (closed_loop/service.py) and lists what fires, each with a group
(the CAPA round, version, field action or complaint it is about) and the records as at firing. ``sweep_tenant`` runs
in the hourly late-evidence pass (decision_followups/impact.py ``run_for_all_tenants``) for every DECIDED or CLOSED
case with a current signed brief decision. One assessment per decision, trigger and group: the group is kept in the
``REOPEN_TRIGGER_FIRED`` audit event (with the counts and records, frozen), and that event is what makes it idempotent.
A superseded decision is never read (only the current one is). Off with ``MDARIX_CLOSED_LOOP=off``.
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import and_, exists
from sqlalchemy.orm import Session

from backend.app import feature_set
from backend.app.business_ids import as_uuid
from backend.app.closed_loop import rules as loop_rules
from backend.app.closed_loop.service import did_it_work
from backend.app.db.models.foundation import AuditEvent, Decision, Investigation
from backend.app.decision_followups import common, impact, rules

logger = logging.getLogger("mdarix.closed_loop")

AUDIT_ACTION = "REOPEN_TRIGGER_FIRED"
# Later complaints that make "again" more than a single report (B5 spec 3.6).
MIN_LATER = 2
RECORDS_MAX = 50


def _day(value) -> date | None:
    return value.date() if hasattr(value, "date") else value


def _refs(items) -> list[str]:
    return [item["ref"] for item in items][:RECORDS_MAX]


def fired(view: dict) -> list[dict]:
    """``[{trigger, group, summary, records}]`` for one view, in a fixed order (same view, same list)."""
    if not view.get("decision"):
        return []
    later = [*view["later"]["complaints"], *view["later"]["version_unknown"]["complaints"]]
    found: list[dict] = []

    def add(trigger: str, group: str, summary: str, records: list[str]) -> None:
        found.append({"trigger": trigger, "group": group, "summary": summary, "records": records})

    for capa in view["capas"]:
        for check in capa["checks"]:
            group = f"{capa['ref']} round {check['round']}"
            if check["status"] == "NOT_EFFECTIVE":
                add("CAPA_NOT_EFFECTIVE", group, f"{group} was signed not effective", [capa["ref"]])
            elif check["status"] == "EFFECTIVE" and check["signed_at"]:
                signed = _day(check["signed_at"])
                again = [item for item in later if item["event_on"] and item["event_on"] > signed]
                if len(again) >= MIN_LATER:
                    add(
                        "RECURRENCE_AFTER_EFFECTIVE",
                        group,
                        f"{len(again)} complaints with the problem after {group} was signed effective",
                        _refs(again),
                    )
    for action in view["actions"]:
        where = f"{action['kind'].replace('_', ' ').lower()} {action['ref']}"
        groups = [
            *action["by_version"],
            action["lot_cohorts"],
            *([action["new_vs_old"]] if "new_vs_old" in action else []),
        ]
        for group in groups:
            if group.get("result") == loop_rules.MORE:
                add(
                    "LATER_COMPLAINTS_MORE",
                    f"{where} · {group['name']}",
                    f"More after {where}: {group['name']}, {group['before']} before and {group['after']} after",
                    _refs(group["after_complaints"]),
                )
    for version in view["scope"]["new_versions"]:
        on_new = [item for item in view["later"]["complaints"] if item["version_id"] == version["id"]]
        if len(on_new) >= MIN_LATER:
            add(
                "PROBLEM_ON_NEW_VERSION",
                version["ref"],
                f"{len(on_new)} complaints with the problem on the new version {version['ref']}",
                _refs(on_new),
            )
    for action in view["field_actions"]:
        covered = set(action["lot_ids"])
        effective = action["effective_on"]
        hits = [item for item in later if effective and item["lot_id"] in covered and item["event_on"] > effective]
        if hits:
            ref = action["reference"] or action["follow_up"]
            add(
                "COMPLAINT_ON_ACTIONED_LOT",
                ref,
                f"{len(hits)} complaint(s) on lots covered by field action {ref}, after it took effect",
                _refs(hits),
            )
    for item in later:
        if item["harm"]:
            add("LATER_SERIOUS_HARM", item["ref"], f"{item['ref']} reports death or serious injury", [item["ref"]])
    return found


def _already(db: Session, tenant_id, decision_id) -> set[tuple[str, str]]:
    rows = db.query(AuditEvent.details).filter(
        AuditEvent.tenant_id == tenant_id,
        AuditEvent.action == AUDIT_ACTION,
        AuditEvent.details["decision_id"].astext == str(decision_id),
    )
    return {(details.get("trigger"), details.get("group")) for (details,) in rows if details}


def check_case(db: Session, control_db, case: Investigation, today: date) -> int:
    """Impact assessments for what fires on ``case`` (locked by the caller). Does not commit."""
    decision = common.current_decision(db, case.tenant_id, case.id)
    if decision is None:
        return 0
    view = did_it_work(db, case, today, lot_rows=False)
    if not view["decision"] or view["decision"]["id"] != str(decision.id):
        return 0
    known = _already(db, case.tenant_id, decision.id)
    made = 0
    for item in fired(view):
        if (item["trigger"], item["group"]) in known:
            continue
        label = rules.trigger_label(item["trigger"])
        now = rules.now_utc()
        row, task, role = impact.open_assessment(
            db,
            control_db,
            case,
            decision,
            trigger=item["trigger"],
            title=f"{label}: {item['summary']}. Does it change decision {decision.business_id}?",
            actor_ref=impact.SCHEDULER_ACTOR,
            now=now,
        )
        common.audit(
            db,
            tenant_id=case.tenant_id,
            actor_ref=impact.SCHEDULER_ACTOR,
            action=AUDIT_ACTION,
            entity_type=rules.IMPACT_ENTITY,
            entity_id=row.id,
            details={
                "investigation_id": str(case.id),
                "decision_id": str(decision.id),
                "decision_business_id": decision.business_id,
                "trigger": item["trigger"],
                "group": item["group"],
                "summary": item["summary"],
                "records": item["records"],
                "rule_version": loop_rules.RULE_VERSION,
                "task_id": str(task.id),
                "actor_role": role,
            },
            now=now,
        )
        known.add((item["trigger"], item["group"]))
        made += 1
    return made


def sweep_tenant(db: Session, control_db, tenant_id, today: date | None = None) -> int:
    """The triggers for one organization's decided cases, each in a SAVEPOINT of its own (a case that fails is logged
    and tried again next run). Idempotent. Does not commit."""
    if not feature_set.closed_loop():
        return 0
    tenant = as_uuid(tenant_id)
    today = today or rules.now_utc().date()
    # shortcut: reads Did it work? for every decided case each hour; fine for trials and pilots, batch it past ~1,000.
    case_ids = [
        row.id
        for row in db.query(Investigation.id)
        .filter(
            Investigation.tenant_id == tenant,
            Investigation.workflow_state.in_(rules.DECIDED_STATES),
            exists().where(
                and_(
                    Decision.tenant_id == Investigation.tenant_id,
                    Decision.investigation_id == Investigation.id,
                    Decision.decision_kind == rules.BRIEF_KIND,
                    Decision.decision_status == rules.SIGNED_STATUS,
                    Decision.superseded_by_decision_id.is_(None),
                )
            ),
        )
        .order_by(Investigation.id)
    ]
    made = 0
    for case_id in case_ids:
        try:
            with db.begin_nested():
                case = (
                    db.query(Investigation)
                    .filter(Investigation.tenant_id == tenant, Investigation.id == case_id)
                    .with_for_update()
                    .first()
                )
                made += check_case(db, control_db, case, today) if case is not None else 0
        except Exception:
            logger.exception("Reopen triggers of case %s could not be checked; tried again next run", case_id)
    return made
