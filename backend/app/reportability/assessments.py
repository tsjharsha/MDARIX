"""Reading per-market assessments (markets.py decides; this module only reads and shapes).

A market's assessment of a complaint is a list of versions (complaint_market_assessments, tr01): at most one draft (no
conclusion yet), and signed versions, the latest of which is the market's current conclusion. The watch asks, for each
complaint, which markets it must be assessed for (the market of the event's country, when the organization enabled
it, and every market already assessed) and whether each is settled: not reportable, or reportable with the filing
recorded. Earlier single decisions (complaint_reportability) stay as they are and still settle a complaint.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.trial.sample_source import is_sample
from backend.app.db.models.market_assessment import ComplaintMarketAssessment
from backend.app.reportability import markets

NOT_STARTED, DRAFT = "NOT_STARTED", "DRAFT"


def rows_by_complaint(
    db: Session, tenant_id: uuid.UUID, complaint_ids
) -> dict[uuid.UUID, dict[str, list[ComplaintMarketAssessment]]]:
    """``{complaint id: {market: versions, oldest first}}``."""
    found: dict[uuid.UUID, dict[str, list[ComplaintMarketAssessment]]] = {}
    ids = list(complaint_ids)
    if not ids:
        return found
    for row in (
        db.query(ComplaintMarketAssessment)
        .filter(ComplaintMarketAssessment.tenant_id == tenant_id, ComplaintMarketAssessment.complaint_id.in_(ids))
        .order_by(ComplaintMarketAssessment.version)
    ):
        found.setdefault(row.complaint_id, {}).setdefault(row.market, []).append(row)
    return found


def current_and_draft(versions: list[ComplaintMarketAssessment]):
    """``(the current signed version or None, the draft or None)``."""
    signed = [row for row in versions if row.conclusion is not None]
    draft = next((row for row in versions if row.conclusion is None), None)
    return (signed[-1] if signed else None), draft


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def signed_floor(market: str, row, in_force: dict) -> dict:
    """The floor a signed conclusion counts by: the one it names; one signed before the register names none and
    counts by version 1 (B9: a later correction such as IN-floor-2 never moves an older signature's clock)."""
    from backend.app.rule_register import register

    code = row.floor_code or f"{register.FLOOR_RULES.get(market, '')}-1"
    return register.get(code) or in_force


def type_label(row: ComplaintMarketAssessment, kind) -> str | None:
    """The report type's words, as the floor the row was saved or signed under has them (B9: a conclusion signed under
    IN-floor-1 keeps its words; one under IN-floor-2 reads "Serious adverse event: 15 days (India MDR 2017 Rule 26,
    starter)"); the floor in force for a row saved before the register."""
    if kind is None:
        return None
    if not row.floor_code:
        # Signed before the register: version 1's words (B9: IN-floor-2's 15 days never reach an older signature).
        old = markets.V1_REPORT_TYPES.get(row.report_type or "") if row.conclusion is not None else None
        return (old or kind).label
    from backend.app.rule_register import register

    held = (((register.get(row.floor_code) or {}).get("content") or {}).get("report_types") or {}).get(row.report_type)
    return (held or {}).get("label") or kind.label


def row_view(
    row: ComplaintMarketAssessment | None, names: dict[str, str], current_code: str | None = None
) -> dict | None:
    """``current_code``: the code of the market's guide version in use now (the starter's when not given)."""
    if row is None:
        return None
    kind = markets.REPORT_TYPES.get(row.report_type or "")
    return {
        "id": str(row.id),
        "market": row.market,
        "version": row.version,
        "question_set": row.question_set,
        "question_set_current": row.question_set == (current_code or markets.QUESTION_SETS[row.market].version),
        "answers": row.answers or {},
        "harm_level": row.harm_level,
        "harm_code": row.harm_code,
        "harm_level_reason": row.harm_level_reason,
        "scale_version": row.scale_version,
        "scale_disagreement_reason": row.scale_disagreement_reason,
        "suggested_conclusion": row.suggested_conclusion,
        "conclusion": row.conclusion,
        "override_reason": row.override_reason,
        "change_reason": row.change_reason,
        "report_type": row.report_type,
        "report_type_label": type_label(row, kind),
        "window_name": row.window_name,
        "due_on": _iso(row.due_on),
        "filing_reference": row.filing_reference,
        "filed_on": _iso(row.filed_on),
        "signed_record_id": str(row.signed_record_id) if row.signed_record_id else None,
        "content_fingerprint": row.content_fingerprint,
        "signed_by": (names.get(row.signed_by) or "A colleague") if row.signed_by else None,
        "signed_at": _iso(row.signed_at),
        "superseded": row.superseded_by is not None,
        "floor_code": row.floor_code,  # B4/B9: the rules the version was decided under (None: before the register)
        "sample": is_sample(row.source_system),
        "created_by": names.get(row.created_by) or "A colleague",
        "saved_at": _iso(row.updated_at),
    }


def market_state(versions: list[ComplaintMarketAssessment]) -> dict:
    """What a market's versions say now: its state, the conclusion or suggestion, the report type, and the draft."""
    current, draft = current_and_draft(versions)
    if current is not None:
        state = current.conclusion
        report_type = current.report_type
    elif draft is not None:
        state = DRAFT
        report_type = draft.report_type
    else:
        state, report_type = NOT_STARTED, None
    return {
        "state": state,
        "suggested": draft.suggested_conclusion if draft is not None else None,
        "report_type": report_type,
        "filed": bool(current and current.filed_on),
        "version": (current or draft).version if (current or draft) else None,
        "draft": draft is not None,
    }


def required_markets(country: object, enabled: list[str], assessed) -> list[str]:
    """The markets a complaint must be assessed for: its event's markets (when enabled; a cell may name several
    countries, "India, Germany") and every one assessed."""
    wanted = {*assessed, *(market for market in markets.markets_of(country) if market in enabled)}
    return [market for market in markets.MARKETS if market in wanted]


def floor_at(market: str, aware, org_zone: str | None) -> dict | None:
    """The market's floor in force at awareness (B4; None while the register is off or without awareness)."""
    from backend.app import feature_set
    from backend.app.rule_register import register

    return register.floor_at(market, aware, org_zone) if aware is not None and feature_set.rule_register() else None


def markets_summary(
    record: dict, windows: list[dict], versions_by_market: dict, aware, today, org_zone: str | None = None
) -> list[dict]:
    """Each market the complaint must be assessed for, with its state and its clock (for the watch)."""
    enabled = markets.enabled_markets(windows)
    pre = markets.markets_of(record.get("country"))
    found = []
    for market in required_markets(record.get("country"), enabled, versions_by_market):
        seen = market_state(versions_by_market.get(market, []))
        clock_state = seen["state"] if seen["state"] in markets.CONCLUSIONS else seen["suggested"]
        report_type = seen["report_type"]
        kind = markets.REPORT_TYPES.get(report_type or "")
        # A market not assessed yet runs no clock of its own: the complaint's windows (by what it reports) bind it.
        started = seen["state"] != NOT_STARTED and not seen["filed"]
        signed, draft = current_and_draft(versions_by_market.get(market, []))
        # B4: the floor at awareness; a signed conclusion's clock counts by the floor it was signed under.
        floor = floor_at(market, aware, org_zone)
        if floor is not None and signed is not None and seen["state"] in markets.CONCLUSIONS:
            floor = signed_floor(market, signed, floor)
        # A draft's pending clock also counts the report a signed "reportable" would start (code audit 3).
        if_reportable = (
            markets.evaluate(market, draft.answers or {}, floor)["report_type_if_reportable"]
            if draft is not None and seen["state"] == DRAFT
            else None
        )
        clock = (
            markets.market_clock(
                market,
                clock_state,
                report_type,
                windows,
                aware,
                today,
                org_zone,
                if_reportable,
                floor,
            )
            if started
            else None
        )
        found.append(
            {
                "market": market,
                "label": markets.MARKET_LABELS[market],
                "preselected": market in pre,
                "enabled": market in enabled,
                **seen,
                "report_type_label": (
                    type_label(signed, kind) if signed is not None and seen["state"] in markets.CONCLUSIONS else None
                )
                or (kind.label if kind else None),
                "clock": clock,
            }
        )
    return found


def settled(summary: list[dict]) -> bool:
    """Every required market is concluded: not reportable, or reportable with the filing recorded."""
    return bool(summary) and all(
        item["state"] == markets.NOT_REPORTABLE or (item["state"] == markets.REPORTABLE and item["filed"])
        for item in summary
    )


def signed_counts(db: Session, tenant_id: uuid.UUID, begin, end) -> dict:
    """Current signed market conclusions signed in a period, by conclusion, and how many have their filing recorded
    (the management review's reporting section)."""
    filed = ComplaintMarketAssessment.filed_on.isnot(None)
    rows = (
        db.query(ComplaintMarketAssessment.conclusion, filed, func.count())
        .filter(
            ComplaintMarketAssessment.tenant_id == tenant_id,
            ComplaintMarketAssessment.conclusion.isnot(None),
            ComplaintMarketAssessment.superseded_by.is_(None),
            ComplaintMarketAssessment.signed_at >= begin,
            ComplaintMarketAssessment.signed_at < end,
        )
        .group_by(ComplaintMarketAssessment.conclusion, filed)
        .all()
    )
    found = {"signed": 0, "reportable": 0, "not_reportable": 0, "filed": 0}
    for conclusion, is_filed, count in rows:
        found["signed"] += count
        found["reportable" if conclusion == markets.REPORTABLE else "not_reportable"] += count
        found["filed"] += count if is_filed else 0
    return found


def disagreements(db: Session, tenant_id: uuid.UUID) -> list[ComplaintMarketAssessment]:
    """Current signed conclusions whose answers disagree with the harm-severity scale (each with its written reason),
    for Readiness."""
    return (
        db.query(ComplaintMarketAssessment)
        .filter(
            ComplaintMarketAssessment.tenant_id == tenant_id,
            ComplaintMarketAssessment.conclusion.isnot(None),
            ComplaintMarketAssessment.superseded_by.is_(None),
            ComplaintMarketAssessment.scale_disagreement_reason.isnot(None),
        )
        .order_by(ComplaintMarketAssessment.signed_at.desc())
        .all()
    )
