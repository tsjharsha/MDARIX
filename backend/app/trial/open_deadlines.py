"""Running trials brought up to 0.10.81's deadline rules, for scripts/refresh_trial_story.py (dry run, then
``apply``). Idempotent: a second run finds nothing.

- **Every market's reporting windows** (F5): a market no window covers gets its starter templates
  (reportability/rules.py ``TEMPLATES``), so a Great Britain or Canada complaint gets its assessment and clock.
"""

from __future__ import annotations

from datetime import datetime

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
    return found
