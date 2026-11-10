"""Did it work? (B5 spec 3.2-3.3): what happened after an investigation's signed decision, computed on read from the
records, never stored, so the same read gives the same answer.

The decision's scope is the scope version its signed brief was composed on: product, versions, lots and the problem
codes of the complaints it included. Later complaints: same product, a scope version (or the new version of a
product-change follow-up), a scope problem code, event after the decision was signed; complaints with no version are
listed apart as "version unknown", never put under a version (PV-1). For each action date (a CAPA's measurement start,
a field action's effective date, a new version's release) the view compares before and after by version, the lots
released before and after the action over the same period, and a new version against the old ones. MDARIX never
says an action worked: only the person's signed effectiveness check does.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime

from sqlalchemy.orm import Session

from backend.app.case_challenge import facts as facts_module
from backend.app.case_challenge.facts import EVENT_AT
from backend.app.closed_loop import rules
from backend.app.db.models.capa_effectiveness import CapaEffectivenessCheck
from backend.app.db.models.case_scope import InvestigationScopeVersion
from backend.app.db.models.decision_outcomes import DecisionFollowUp
from backend.app.db.models.foundation import Capa, Complaint, Decision
from backend.app.db.models.lot_impact import LotDistribution
from backend.app.db.models.reviews import DecisionBriefVersion
from backend.app.trial.sample_source import SAMPLE_SOURCE, is_sample

# The complaints a count opens, at most (the count says how many there are).
REFS_MAX = 200
CAPA, FIELD_ACTION, PRODUCT_CHANGE = "CAPA", "FIELD_ACTION", "PRODUCT_CHANGE"


def _day(value) -> date | None:
    if value is None:
        return None
    return value.date() if isinstance(value, datetime) else value


def current_decision(db: Session, case) -> tuple[Decision | None, list[Decision]]:
    """The case's signed brief decision still in force, and the decisions it superseded (newest first)."""
    rows = (
        db.query(Decision)
        .filter(
            Decision.tenant_id == case.tenant_id,
            Decision.investigation_id == case.id,
            Decision.decision_kind == "BRIEF",
            Decision.decided_at.isnot(None),
        )
        .order_by(Decision.decided_at.desc())
        .all()
    )
    current = next((row for row in rows if row.superseded_by_decision_id is None), None)
    return current, [row for row in rows if row is not current]


def decision_scope(db: Session, case, decision: Decision) -> dict:
    """The scope stored with the signed brief: its scope version's versions, lots and included complaints."""
    brief = (
        db.query(DecisionBriefVersion)
        .filter(DecisionBriefVersion.tenant_id == case.tenant_id, DecisionBriefVersion.id == decision.brief_version_id)
        .first()
    )
    query = db.query(InvestigationScopeVersion).filter(
        InvestigationScopeVersion.tenant_id == case.tenant_id, InvestigationScopeVersion.investigation_id == case.id
    )
    if brief is not None and brief.scope_version is not None:
        query = query.filter(InvestigationScopeVersion.version == brief.scope_version)
    row = query.order_by(InvestigationScopeVersion.version.desc()).first()
    if row is None:
        return {"scope_version": None, "version_ids": [], "lot_ids": [], "complaint_ids": [], "markets": []}
    return {
        "scope_version": row.version,
        "version_ids": [str(item) for item in row.product_version_ids or ()],
        "lot_ids": [str(item) for item in row.lot_ids or ()],
        "complaint_ids": [str(item) for item in row.included_complaint_ids or ()],
        "markets": list(row.markets or ()),
    }


def _actions(db: Session, case, decision: Decision, versions: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """The decision's follow-ups as action dates, its CAPAs with every effectiveness round, and its field actions."""
    follow_ups = (
        db.query(DecisionFollowUp)
        .filter(DecisionFollowUp.tenant_id == case.tenant_id, DecisionFollowUp.decision_id == decision.id)
        .order_by(DecisionFollowUp.created_at)
        .all()
    )
    capa_ids = [row.capa_id for row in follow_ups if row.capa_id]
    capas = {
        row.id: row
        for row in (
            db.query(Capa).filter(Capa.tenant_id == case.tenant_id, Capa.id.in_(capa_ids)).all() if capa_ids else []
        )
    }
    rounds = defaultdict(list)
    if capa_ids:
        for check in (
            db.query(CapaEffectivenessCheck)
            .filter(CapaEffectivenessCheck.tenant_id == case.tenant_id, CapaEffectivenessCheck.capa_id.in_(capa_ids))
            .order_by(CapaEffectivenessCheck.round)
        ):
            rounds[check.capa_id].append(check)
    actions, capa_rows, field_actions = [], [], []
    for row in follow_ups:
        if row.capa_id and row.capa_id in capas:
            capa = capas[row.capa_id]
            checks = rounds.get(capa.id, [])
            capa_rows.append(
                {
                    "id": str(capa.id),
                    "ref": capa.capa_identifier or capa.business_id,
                    "title": capa.title,
                    "status": capa.status,
                    "checks": [
                        {
                            "round": check.round,
                            "status": check.status,
                            "planned_on": check.planned_on,
                            "measured_from": check.measured_from,
                            "signed_at": check.signed_at,
                        }
                        for check in checks
                    ],
                }
            )
            # The measurement starts where its check says; until a check is planned, at the decision.
            actions.append(
                {
                    "kind": CAPA,
                    "on": checks[-1].measured_from if checks else _day(decision.decided_at),
                    "measured_from": "check" if checks else "decision",
                    "ref": capa.capa_identifier or capa.business_id,
                    "follow_up": row.business_id,
                }
            )
        scope = row.action_scope or {}
        if row.action_type == "FIELD_ACTION_REVIEW_REQUIRED" and (row.action_effective_on or row.action_reference):
            field_actions.append(
                {
                    "follow_up": row.business_id,
                    "reference": row.action_reference,
                    "kind": row.action_kind,
                    "effective_on": row.action_effective_on,
                    "lot_ids": scope.get("lot_ids") or [],
                    "version_ids": scope.get("version_ids") or [],
                    "status": row.status,
                }
            )
            if row.action_effective_on:
                actions.append(
                    {
                        "kind": FIELD_ACTION,
                        "on": row.action_effective_on,
                        "ref": row.action_reference or row.business_id,
                        "follow_up": row.business_id,
                        "lot_ids": scope.get("lot_ids") or [],
                    }
                )
        new_version = scope.get("new_version_id")
        if row.action_type == "PRODUCT_CHANGE_REQUIRED" and new_version in versions:
            released = versions[new_version]["released"]
            if released:
                actions.append(
                    {
                        "kind": PRODUCT_CHANGE,
                        "on": released,
                        "ref": versions[new_version]["ref"],
                        "follow_up": row.business_id,
                        "new_version_id": new_version,
                    }
                )
    return sorted(actions, key=lambda item: item["on"]), capa_rows, field_actions


def _lot_inputs(db: Session, tenant_id, lots: dict) -> dict[str, dict]:
    """Each lot as the statistics read it: released on, units, shipments with their dates."""
    shipments = defaultdict(list)
    if lots:
        for lot_id, ship_date, quantity in db.query(
            LotDistribution.lot_batch_id, LotDistribution.ship_date, LotDistribution.quantity
        ).filter(
            LotDistribution.tenant_id == tenant_id,
            LotDistribution.lot_batch_id.in_([uuid.UUID(item) for item in lots]),
        ):
            shipments[str(lot_id)].append((ship_date, quantity))
    return {
        lot_id: {"released_on": lot["released"], "units": lot["units_released"], "shipments": shipments.get(lot_id, [])}
        for lot_id, lot in lots.items()
    }


def _between(complaints: list[dict], start: date, end: date) -> list[dict]:
    return [item for item in complaints if item["event_on"] and start <= item["event_on"] <= end]


def _refs(items: list[dict]) -> list[dict]:
    return [{"id": item["id"], "ref": item["ref"]} for item in items[:REFS_MAX]]


def _later(item: dict, versions: dict) -> dict:
    return {
        **_refs([item])[0],
        "version_id": item["version_id"],
        "version": versions.get(item["version_id"], {}).get("ref"),
        "lot_id": item["lot_id"],
        "event_on": item["event_on"],
        "harm": item["harm"],
        "origin": item["origin"],
    }


def _group(name: str, before: list[dict], after: list[dict], window: dict, lots_before, lots_after, extra=None) -> dict:
    found = rules.compare(len(before), len(after), window, lots_before, lots_after)
    return {
        "name": name,
        **found,
        "before_complaints": _refs(before),
        "after_complaints": _refs(after),
        "lots_with_units_unknown": lots_after["unknown_lots"] or lots_before["unknown_lots"],
        "lots_in_group": lots_after["lots"],
        **(extra or {}),
    }


def _cohort(name: str, old: list[dict], new: list[dict], window: dict, old_exposure, new_exposure) -> dict:
    """Two groups over the same calendar period: by calendar days their split says nothing, so with units unknown the
    cohorts show counts only, untested."""
    if rules.UNKNOWN in (old_exposure["basis"], new_exposure["basis"]):
        return {
            "name": name,
            "before": len(old),
            "after": len(new),
            "basis": rules.UNKNOWN,
            "counts_only": True,
            "result": rules.COUNTS_ONLY,
            "word": rules.WORDS[rules.COUNTS_ONLY],
            "unknown_lots": max(old_exposure["unknown_lots"], new_exposure["unknown_lots"]),
            "before_complaints": _refs(old),
            "after_complaints": _refs(new),
        }
    same_period = {**window, "days": window["after_days"]}
    found = rules.compare(len(old), len(new), same_period, old_exposure, new_exposure)
    return {"name": name, **found, "before_complaints": _refs(old), "after_complaints": _refs(new)}


def did_it_work(db: Session, case, today: date, *, lot_rows: bool) -> dict:
    """The whole view for the case's current signed decision (None when nothing is signed)."""
    decision, superseded = current_decision(db, case)
    base = {
        "rule_version": rules.RULE_VERSION,
        "notice": rules.NOTICE,
        "limits": list(rules.LIMITS),
        "superseded": [
            {"id": str(row.id), "ref": row.business_id or row.decision_identifier, "decided_at": row.decided_at}
            for row in superseded
        ],
    }
    if decision is None:
        return {**base, "decision": None}
    scope = decision_scope(db, case, decision)
    t = str(case.tenant_id)
    versions = facts_module._versions(db, t, [str(case.product_id)])
    actions, capas, field_actions = _actions(db, case, decision, versions)
    new_versions = [item["new_version_id"] for item in actions if item["kind"] == PRODUCT_CHANGE]
    scope_complaints = (
        facts_module._complaints(db, case.tenant_id, [Complaint.id.in_([uuid.UUID(i) for i in scope["complaint_ids"]])])
        if scope["complaint_ids"]
        else []
    )
    problems = sorted({item["problem"] for item in scope_complaints if item["problem"]})
    scope_versions = sorted(
        {*scope["version_ids"], *(item["version_id"] for item in scope_complaints if item["version_id"])}
    )
    followed = [v for v in dict.fromkeys([*scope_versions, *new_versions]) if v in versions]
    lots = {lot_id: lot for lot_id, lot in facts_module._lots(db, t, followed).items() if lot["version_id"] in followed}
    lot_inputs = _lot_inputs(db, case.tenant_id, lots)
    decided_on = _day(decision.decided_at)
    windows = {id(item): rules.windows(item["on"], today, rules.SETTLING_DAYS[item["kind"]]) for item in actions}
    earliest = min([w["before"][0] for w in windows.values()] + [decided_on])
    where = [Complaint.product_id == case.product_id, Complaint.problem_code.in_(problems), EVENT_AT >= earliest]
    if not is_sample(case.source_system):
        # R6: sample complaints never count in a customer's numbers.
        where.append(Complaint.source_system.is_distinct_from(SAMPLE_SOURCE))
    complaints = facts_module._complaints(db, case.tenant_id, where) if problems else []
    later = [item for item in complaints if item["event_on"] and item["event_on"] > decided_on]
    later_known = [item for item in later if item["version_id"] in followed]
    later_unknown = [item for item in later if item["version_id"] is None]
    by_version = defaultdict(list)
    for item in complaints:
        by_version[item["version_id"]].append(item)

    def lots_of(version_ids) -> list[dict]:
        return [lot_inputs[lot_id] for lot_id, lot in lots.items() if lot["version_id"] in version_ids]

    views = []
    for action in actions:
        window = windows[id(action)]
        (b_start, b_end), (a_start, a_end) = window["before"], window["after"]
        rows = []
        for version_id in scope_versions:
            if version_id not in versions:
                continue
            mine = by_version.get(version_id, [])
            group = lots_of({version_id})
            rows.append(
                _group(
                    versions[version_id]["ref"],
                    _between(mine, b_start, b_end),
                    _between(mine, a_start, a_end),
                    window,
                    rules.exposure(group, b_start, b_end),
                    rules.exposure(group, a_start, a_end),
                    {"version_id": version_id},
                )
            )
        view = {**action, "window": window, "by_version": rules.adjust(rows)}
        # Lots released before and after the action, over the same period (the after window).
        old_lots = {
            i
            for i, lot in lots.items()
            if lot["version_id"] in scope_versions and lot["released"] and lot["released"] < action["on"]
        }
        new_lots = {
            i
            for i, lot in lots.items()
            if lot["version_id"] in scope_versions and lot["released"] and lot["released"] >= action["on"]
        }
        in_after = _between([c for v in scope_versions for c in by_version.get(v, [])], a_start, a_end)
        view["lot_cohorts"] = _cohort(
            "Lots released after the action vs before",
            [c for c in in_after if c["lot_id"] in old_lots],
            [c for c in in_after if c["lot_id"] in new_lots],
            window,
            rules.exposure([lot_inputs[i] for i in old_lots], a_start, a_end),
            rules.exposure([lot_inputs[i] for i in new_lots], a_start, a_end),
        )
        view["lot_cohorts"]["lot_unknown"] = sum(1 for c in in_after if c["lot_id"] is None)
        if lot_rows:
            view["lots"] = [
                {
                    "id": lot_id,
                    "ref": lots[lot_id]["ref"],
                    "version": versions[lots[lot_id]["version_id"]]["ref"],
                    "released": lots[lot_id]["released"],
                    "cohort": "after" if lot_id in new_lots else "before",
                    "after_complaints": _refs([c for c in in_after if c["lot_id"] == lot_id]),
                    "after": sum(1 for c in in_after if c["lot_id"] == lot_id),
                    "units": lots[lot_id]["units_released"],
                }
                for lot_id in sorted(old_lots | new_lots, key=lambda i: lots[i]["ref"])
            ]
        if action["kind"] == PRODUCT_CHANGE:
            new_id = action["new_version_id"]
            old_ids = [v for v in scope_versions if v != new_id]
            old_after = _between([c for v in old_ids for c in by_version.get(v, [])], a_start, a_end)
            new_after = _between(by_version.get(new_id, []), a_start, a_end)
            view["new_vs_old"] = _cohort(
                f"{versions[new_id]['ref']} vs the earlier versions",
                old_after,
                new_after,
                window,
                rules.exposure(lots_of(set(old_ids)), a_start, a_end),
                rules.exposure(lots_of({new_id}), a_start, a_end),
            )
        views.append(view)
    return {
        **base,
        "decision": {
            "id": str(decision.id),
            "ref": decision.business_id or decision.decision_identifier,
            "decided_at": decision.decided_at,
            "outcome": decision.outcome,
        },
        "scope": {
            "scope_version": scope["scope_version"],
            "versions": [{"id": v, "ref": versions[v]["ref"]} for v in scope_versions if v in versions],
            "new_versions": [{"id": v, "ref": versions[v]["ref"]} for v in new_versions],
            "problems": problems,
            "complaints": len(scope_complaints),
        },
        "later": {
            "count": len(later_known),
            "complaints": [_later(item, versions) for item in later_known[:REFS_MAX]],
            "version_unknown": {
                "count": len(later_unknown),
                "complaints": [_later(item, versions) for item in later_unknown[:REFS_MAX]],
            },
        },
        "capas": capas,
        "field_actions": field_actions,
        "actions": views,
    }
