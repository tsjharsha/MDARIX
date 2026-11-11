"""Running trials brought up to 0.10.81's deadline rules, for scripts/refresh_trial_story.py (dry run, then
``apply``). Idempotent: a second run finds nothing.

- **Every market's reporting windows** (F5): a market no window covers gets its starter templates
  (reportability/rules.py ``TEMPLATES``), so a Great Britain or Canada complaint gets its assessment and clock.
- **The sample's FDA product code** (F6): the sample US report's D2A held "SMP (sample: your FDA product code)", which
  a code field no longer takes; it becomes FRN (Pump, Infusion), as new trials have it.
- **Open reports and assessments under the fixed rules** (F1, F2): an open report (not yet submitted) whose report
  type, due date or provisional flag differs from its market's latest signed reportable conclusion follows it,
  audited (authority_reports/router.py ``follow_signed``); a draft assessment whose stored suggestion, report type or
  due date the fixed Unknown rule changes is recomputed, audited. A signed conclusion is never changed: one the fixed
  rule would give another report type is listed for a person to sign again, and a submitted report whose type
  differs is listed (its page already flags it).
"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

from sqlalchemy.orm import Session

from backend.app.trial.sample_data import STORY_WINDOWS_BY


def missing_windows(db: Session, tenant_id) -> list[dict]:
    """The starter templates of every market no saved window covers (F5)."""
    from backend.app.reportability import markets, rules, service

    covered = set(markets.enabled_markets(service.settings_of(db, tenant_id)["windows"]))
    return [
        rules.clean_window(template)
        for template in rules.TEMPLATES
        if not covered & markets.window_markets(rules.clean_window(template))
    ]


def add_windows(db: Session, tenant_id, now: datetime) -> list[str]:
    """Add the missing markets' templates to the trial's windows, audited; the names added."""
    from backend.app.db.models.reportability import ReportabilitySettings
    from backend.app.enterprise_audit import make_audit_event

    wanted = missing_windows(db, tenant_id)
    if not wanted:
        return []
    row = db.query(ReportabilitySettings).filter(ReportabilitySettings.tenant_id == tenant_id).with_for_update().first()
    if row is None:
        row = ReportabilitySettings(tenant_id=tenant_id, windows=[], lookback_days=365, version=0)
        db.add(row)
    before = list(row.windows or [])
    row.windows = [*before, *wanted]
    row.version = (row.version or 0) + 1
    row.updated_by, row.updated_at = STORY_WINDOWS_BY, now
    db.flush()
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=STORY_WINDOWS_BY,
            action="REPORTABILITY_SETTINGS_UPDATED",
            entity_type="ReportabilitySettings",
            entity_id=row.id,
            reason="0.10.81: every market's starter reporting windows, so each complaint's own market is assessed",
            old_values={"windows": [window["name"] for window in before]},
            new_values={"windows": [window["name"] for window in row.windows]},
            created_at=now,
        )
    )
    return [window["name"] for window in wanted]


def refresh(db: Session, tenant_id, apply: bool, now: datetime | None = None) -> list[str]:
    """What 0.10.81 changes in this trial, in words; with ``apply`` it is done (flushed; the caller commits)."""
    from datetime import timezone

    now = now or datetime.now(timezone.utc)
    found = []
    windows = [window["name"] for window in missing_windows(db, tenant_id)]
    if windows:
        if apply:
            add_windows(db, tenant_id, now)
        found.append(f"{'added' if apply else 'would add'} the reporting windows {', '.join(windows)}")
    found += _deadline_changes(db, tenant_id, apply, now)
    old_code = _sample_product_code(db, tenant_id, apply, now)
    if old_code:
        found.append(f"{'set' if apply else 'would set'} the sample US report's FDA product code to FRN")
    return found


OLD_SAMPLE_CODE = "SMP (sample: your FDA product code)"


def _sample_product_code(db: Session, tenant_id, apply: bool, now: datetime) -> int:
    """The sample's report entries still holding the old D2A text (F6), set to FRN with ``apply``."""
    from backend.app.db.models.authority_reports import ReportObligation
    from backend.app.trial.sample_data import SAMPLE_SOURCE

    rows = [
        row
        for row in db.query(ReportObligation).filter(
            ReportObligation.tenant_id == tenant_id, ReportObligation.source_system == SAMPLE_SOURCE
        )
        if ((row.entries or {}).get("D2A") or {}).get("value") == OLD_SAMPLE_CODE
    ]
    if apply:
        for row in rows:
            row.entries = {**row.entries, "D2A": {**row.entries["D2A"], "value": "FRN"}}
            row.updated_at = now
        db.flush()
    return len(rows)


SYSTEM = SimpleNamespace(user_id="system:trial-refresh-0.10.81", correlation_id=None)


def _deadline_changes(db: Session, tenant_id, apply: bool, now: datetime) -> list[str]:
    """F1 and F2 for one trial: what would change (or, with ``apply``, changed), one line per record."""
    from backend.app.authority_reports import router as reports
    from backend.app.authority_reports import rules as report_rules
    from backend.app.db.models.authority_reports import ReportObligation
    from backend.app.db.models.foundation import Complaint
    from backend.app.enterprise_audit import make_audit_event
    from backend.app.reportability import assessments, markets, service

    lines: list[str] = []
    verb = "updated" if apply else "would update"
    complaint_ids = [row[0] for row in db.query(Complaint.id).filter(Complaint.tenant_id == tenant_id)]
    versions = assessments.rows_by_complaint(db, tenant_id, complaint_ids)
    obligations = {
        (row.complaint_id, row.market): row
        for row in db.query(ReportObligation).filter(
            ReportObligation.tenant_id == tenant_id, ReportObligation.kind == "INITIAL"
        )
    }
    windows = service.settings_of(db, tenant_id)["windows"]
    for complaint_id, by_market in versions.items():
        complaint = db.get(Complaint, complaint_id)
        ref = complaint.complaint_identifier or complaint.business_id
        for market, rows in by_market.items():
            current, draft = assessments.current_and_draft(rows)
            label = markets.MARKET_LABELS.get(market, market)
            if draft is not None and draft.answers:
                seen = service.one(db, tenant_id, complaint_id, now)[2]
                aware = datetime.fromisoformat(seen["aware_at"]) if seen["aware_at"] else None
                floor = assessments.floor_at(market, aware, seen["org_zone"], seen["roles"].get(market))
                evaluation = markets.evaluate(market, draft.answers, floor)
                clock = markets.market_clock(
                    market,
                    evaluation["suggested"],
                    evaluation["report_type"],
                    windows,
                    aware,
                    now,
                    seen["org_zone"],
                    evaluation["report_type_if_reportable"],
                    floor,
                )
                due = date.fromisoformat(clock["due_date"]) if clock else None
                old = {
                    "suggested": draft.suggested_conclusion,
                    "report_type": draft.report_type,
                    "due_on": _iso(draft.due_on),
                }
                new = {
                    "suggested": evaluation["suggested"],
                    "report_type": evaluation["report_type"],
                    "due_on": _iso(due),
                }
                if old != new:
                    lines.append(f"{verb} {ref} {label} draft assessment: {_change(old, new)}")
                    if apply:
                        draft.suggested_conclusion, draft.report_type, draft.due_on = (
                            new["suggested"],
                            new["report_type"],
                            due,
                        )
                        draft.window_name = clock["window"] if clock else None
                        draft.updated_at = now
                        db.add(
                            make_audit_event(
                                tenant_id=tenant_id,
                                actor_ref=SYSTEM.user_id,
                                action="COMPLAINT_MARKET_ASSESSMENT_RECOMPUTED",
                                entity_type="Complaint",
                                entity_id=complaint_id,
                                reason="0.10.81: an Unknown answer keeps the shortest category not yet excluded",
                                details={"complaint": ref, "market": market, "version": draft.version},
                                old_values=old,
                                new_values=new,
                                created_at=now,
                            )
                        )
            if current is None or current.conclusion != markets.REPORTABLE:
                continue
            fixed = markets.evaluate(market, current.answers or {})["report_type_if_reportable"]
            if fixed != current.report_type:
                lines.append(
                    f"listed {ref} {label} conclusion version {current.version}: signed as {current.report_type}, "
                    f"the fixed rule gives {fixed}; a person signs it again (never changed here)"
                )
            obligation = obligations.get((complaint_id, market))
            if obligation is None:
                continue
            if obligation.state in report_rules.SUBMITTED:
                if obligation.report_type != current.report_type:
                    lines.append(
                        f"listed {ref} {label} report: submitted as {obligation.report_type}, the latest signed "
                        f"conclusion says {current.report_type}; its page flags a follow-up"
                    )
                continue
            if obligation.state not in report_rules.CANCELLABLE:
                continue
            old = {
                "report_type": obligation.report_type,
                "due_on": _iso(obligation.due_on),
                "provisional": obligation.due_provisional,
            }
            new = {"report_type": current.report_type, "due_on": _iso(current.due_on), "provisional": False}
            if old != new:
                lines.append(f"{verb} {ref} {label} report: {_change(old, new)}")
                if apply:
                    ended = reports.follow_signed(db, SYSTEM, obligation, current, now)
                    reports.end_cancelled_approvals(
                        db, SYSTEM, tenant_id, ended, "Replaced: the signed conclusion changed the report type"
                    )
    if apply:
        db.flush()
    return lines


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _change(old: dict, new: dict) -> str:
    return ", ".join(f"{key} {old[key]} -> {new[key]}" for key in old if old[key] != new[key])
