"""The sample story's clock: a trial opened on day 0, 7, 15 or 29 tells the same story (quality plan stage 3, J2).

The sample is dated from the moment it is seeded (its **anchor**, kept in the trial request's profile as
``sample_anchor``; a trial approved before 0.10.64 has its approval time). The sample's events **move with the trial's
day**: the first time the hourly scheduler (``keep_current``) runs after midnight in the organization's time zone, it
moves every sample record, and everything hanging off one (the sample records ``sample_removal.plan`` reaches through
sample records only), forward by the whole days passed since the anchor, and moves the anchor by the same days. So
the deadlines stay ahead of the reader, the OrbitCare rise stays inside the trend check's last 30 days, and the
alerts, labels and next steps stay the same on day 0, 7, 15 or 29. (The alternative, a trend read "as of" the
sample's own date, would have left every deadline and alert ageing.)

- **Never during the day** (0.10.92, owner decision on A1, option C): a time of day never changes, so a signed time
  or an awareness time read twice in a session reads the same (it moved hourly before, 16:33 then 17:27). Times move
  by whole days, dates (an absence's days, a report's due day) by the same days. The sample's signatures and signed
  records say so: "Sample: dates follow your trial day" (``DATES_NOTE``). Dates written inside a record's text or a
  signed record's content stay as written. A target shorter than a day (a triage target) can come due late in the
  day, as it would on the day the sample was seeded.
- **The clock stops once a person works on the sample** (a signed disposition, market conclusion, decision, review,
  document, question to MDARIX, case from a signal or effectiveness check: ``story.acted_counts``, own uploads
  excluded; 0.10.92, D11: also a call logged, a first-contact check or a triage record): signed
  practice records are never re-dated. "Restart the sample story" (``restart``) then seeds the sample again at the
  current time.
- The audit trail is never changed; the trial's own records are never moved (0.10.92, H10: a row from any other source
  than the sample, such as a call logged on a sample product, is neither moved nor followed, so its awareness and
  signed times stay as written).

``restart`` removes the sample (``sample_removal``) and seeds it again now, for the person who started the trial; with
``own=True`` it also removes the organization's own uploaded records and everything done with them ("also remove my
practice work"). Audited as TRIAL_SAMPLE_RESTARTED.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("mdarix.trial.sample_clock")
ANCHOR = "sample_anchor"
# Move the sample once at least this much time has passed (the scheduler runs hourly).
# What the sample's signatures and signed records say (owner's wording, 0.10.92): their dates move by whole days.
DATES_NOTE = "Sample: dates follow your trial day"
_MOMENTS = ("timestamp with time zone", "timestamp without time zone")


def seed_sample(db: Session, tenant_id, now: datetime, owner_id: str) -> dict:
    """The whole sample story, dated from ``now``, with ``owner_id`` (the person who started the trial) as its owner of
    the open request, the absence's backup and the two events. Flushes; the caller commits. Each part is idempotent."""
    from backend.app.trial.sample_ai import stage_sample_ai
    from backend.app.trial.sample_assessments import stage_sample_assessments
    from backend.app.trial.sample_calm import stage_calm_story
    from backend.app.trial.sample_data import (
        seed_lot_quantities,
        seed_product_facts,
        seed_sample_workspace,
        seed_story_examples,
    )
    from backend.app.trial import sample_persona_work
    from backend.app.trial.sample_decision import stage_sample_decision
    from backend.app.trial.sample_dispositions import seed_routine_examples
    from backend.app.trial.sample_guides import stage_sample_guides
    from backend.app.trial.sample_imports import stage_sample_import
    from backend.app.trial.sample_intake import stage_sample_intake
    from backend.app.trial.sample_lot_impact import stage_sample_lot_impact
    from backend.app.trial.sample_supply import stage_sample_supply
    from backend.app.trial.sample_sources import stage_sample_sources
    from backend.app.trial.sample_follow_up import stage as stage_follow_up
    from backend.app.trial.sample_oversight import stage_sample_oversight
    from backend.app.trial import reports_0_10_75
    from backend.app.trial.sample_reports import stage_sample_reports

    sample = seed_sample_workspace(db, tenant_id, now)
    # The rest of the story: hidden complaints, reporting clocks, the flagship, CAPAs, the risk register and sample
    # reporting windows, so Complaints, Records and Readiness show findings from the first minute.
    sample["story"] = seed_story_examples(db, tenant_id, now)
    # Units per sample lot (md43), so the trend check counts per device in the field.
    sample["lot_quantities"] = seed_lot_quantities(db, tenant_id)
    # The guided investigation's Decision Brief, written by a sample author and submitted for quality review.
    sample["decision"] = stage_sample_decision(db, tenant_id, now)
    # UX1: that brief accepted for decision by a sample reviewer (waiting for a signature) and a risk review requested.
    sample["persona_work"] = sample_persona_work.stage(db, tenant_id, now)
    # Pre-recorded AI proposals on the guided investigation (no model called), waiting for a person's review.
    sample["ai"] = stage_sample_ai(db, tenant_id, now)
    # Signed EU/NI and Canada assessments of one event, and a pending US draft.
    sample["assessments"] = stage_sample_assessments(db, tenant_id, now)
    # The routine complaints, their proposed classifications and a signed service-level example.
    sample["routine"] = seed_routine_examples(db, tenant_id, now)
    # The import run with its data-quality report and set-aside rows, UDI-DI, GMDN and IMDRF links. After every
    # complaint: it reads them all.
    sample["imports"] = stage_sample_import(db, tenant_id, now)
    # The first contacts, the urgent intake and a finished triage record.
    sample["intake"] = stage_sample_intake(db, tenant_id, now)
    # The report worksheets (a finished US example, an India example with a rejected attempt). After the import run.
    sample["reports"] = stage_sample_reports(db, tenant_id, now)
    # On the new navigation, a signed reportable conclusion has its report (0.10.75; 0.10.76: SAMPLE-RV-07's EU MIR).
    sample["reports_signed"] = reports_0_10_75.refresh(db, tenant_id, apply=True, now=now)
    # The organization's own US guide version and a draft whose test fails, and the communications log's examples.
    sample["guides"] = stage_sample_guides(db, tenant_id, now, owner_id=owner_id)
    # The sample author away to the trial's end with the owner as backup, and the two events the owner owns.
    sample["oversight"] = stage_sample_oversight(db, tenant_id, now, owner_id=owner_id)
    # Lot genealogy and distribution for a case's Lot impact. The trend's units in the field stay the same.
    sample["lot_impact"] = stage_sample_lot_impact(db, tenant_id, now)
    # Rev A configurations and the evidence linked to NovaSense, for Product 360 and Supplier 360 (W1, 0.10.94).
    sample["supply"] = stage_sample_supply(db, tenant_id, now)
    # W5: the simulated PLM, ERP and eQMS runs behind OrbitCare 300's records (after the lot impact; adds no record).
    sample["sources"] = stage_sample_sources(db, tenant_id, now)
    # W1d (D04): SAMPLE-CAPA-02's labelled synthetic follow-up (one evidence record; shown once its check is planned).
    sample["follow_up"] = stage_follow_up(db, tenant_id, now)
    # The sample products' device categories and the lots' expiry dates (J32), after every sample lot exists.
    sample["product_facts"] = seed_product_facts(db, tenant_id)
    # Day 0 is calm: what the story does not need open is finished (sample_calm.py). Last: it reads the triage list.
    sample["calm"] = stage_calm_story(db, tenant_id, now)
    # 0.10.93 (B2 spec 9.2): the sample's complaints are owned in MDARIX from the start, as the upgrade sets them in a
    # trial created before it (scripts/cases_0_10_93.py then lists nothing for a new trial).
    sample["record_owner"] = own_sample_complaints(db, tenant_id)
    return sample


def own_sample_complaints(db: Session, tenant_id) -> int:
    """Every sample complaint with no record owner yet: MDARIX (the sample is MDARIX's own). Flushes; returns how many."""
    from backend.app.db.models.foundation import Complaint
    from backend.app.trial.sample_data import SAMPLE_SOURCE

    rows = (
        db.query(Complaint)
        .filter(
            Complaint.tenant_id == tenant_id, Complaint.source_system == SAMPLE_SOURCE, Complaint.record_owner.is_(None)
        )
        .all()
    )
    for row in rows:
        row.record_owner = "MDARIX"
    db.flush()
    return len(rows)


def anchor_of(request) -> datetime | None:
    """When the trial's sample was last dated: the anchor in the request's profile, else the approval."""
    raw = (getattr(request, "profile", None) or {}).get(ANCHOR)
    if raw:
        try:
            value = datetime.fromisoformat(str(raw))
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    moment = getattr(request, "reviewed_at", None)
    if isinstance(moment, datetime):
        return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    return None


def _sample_ai_reviewed(data: Session, tenant_id) -> bool:
    """W1: a person reviewed one of the sample's recorded AI proposals (the saved result or one of its observations)."""
    from sqlalchemy import String, cast, or_, select

    from backend.app.db.models.ai_records import AiOutputReview
    from backend.app.db.models.evidence_intelligence import EvidenceObservation
    from backend.app.db.models.foundation import AIExecution
    from backend.app.trial.sample_ai import PROVIDER

    sample = (AIExecution.tenant_id == tenant_id, AIExecution.provider == PROVIDER)
    observations = select(cast(EvidenceObservation.id, String)).where(
        EvidenceObservation.tenant_id == tenant_id,
        EvidenceObservation.ai_execution_id.in_(select(AIExecution.id).where(*sample)),
    )
    return (
        data.query(AiOutputReview.id)
        .filter(
            AiOutputReview.tenant_id == tenant_id,
            or_(
                AiOutputReview.subject_id.in_(select(cast(AIExecution.id, String)).where(*sample)),
                AiOutputReview.subject_id.in_(observations),
            ),
        )
        .first()
        is not None
    )


def worked_on(data: Session, tenant_id) -> bool:
    """Whether a person has acted on the sample (``story.acted_counts``, the organization's own uploads excluded, a
    review of the sample's recorded AI proposals, or any work on calls)."""
    from sqlalchemy import and_, or_

    from backend.app.db.models.intake import FirstContactCheck, IntakeEvent, TriageRecord
    from backend.app.trial import story
    from backend.app.trial.sample_data import SAMPLE_SOURCE

    if any(count for code, count in story.acted_counts(data, tenant_id).items() if code != "YOUR_DATA"):
        return True
    if _sample_ai_reviewed(data, tenant_id):
        return True
    # Work on calls (D11): a call, first-contact check or triage record of a person, or a sample one a person signed,
    # reviewed, escalated or completed (it keeps the sample's source; the sample author made and signed the others).
    work = (
        (IntakeEvent, ()),
        (FirstContactCheck, (FirstContactCheck.signed_by, FirstContactCheck.reviewed_by)),
        (TriageRecord, (TriageRecord.completed_by, TriageRecord.escalated_by)),
    )
    return any(
        data.query(model.id)
        .filter(
            model.tenant_id == tenant_id,
            or_(
                model.source_system.is_distinct_from(SAMPLE_SOURCE),
                *(and_(person.isnot(None), person != model.created_by) for person in people),
            ),
        )
        .first()
        is not None
        for model, people in work
    )


def _date_and_time_columns(data: Session) -> dict[str, tuple[list[str], list[str]]]:
    found: dict[str, tuple[list[str], list[str]]] = {}
    for table, column, kind in data.execute(
        text(
            "SELECT table_name, column_name, data_type FROM information_schema.columns WHERE table_schema = 'public' "
            "AND data_type IN ('date', 'timestamp with time zone', 'timestamp without time zone')"
        )
    ):
        moments, days = found.setdefault(table, ([], []))
        (moments if kind in _MOMENTS else days).append(column)
    return found


def move(data: Session, tenant_id, by: timedelta, days: int) -> dict[str, int]:
    """Move every sample record and everything hanging off one forward: times by ``by``, dates by ``days``. Returns
    rows moved per table. Flushes; the caller commits."""
    from backend.app.trial import sample_removal

    planned = sample_removal.plan(data, tenant_id, owned_only=True)
    columns = _date_and_time_columns(data)
    moved: dict[str, int] = {}
    for table, ids in planned["rows"].items():
        moments, dates = columns.get(table, ([], []))
        sets = [f'"{column}" = "{column}" + :by' for column in moments]
        if days:
            sets += [f'"{column}" = "{column}" + CAST(:days AS integer)' for column in dates]
        if not sets or not ids:
            continue
        moved[table] = data.execute(
            text(f"UPDATE {table} SET {', '.join(sets)} WHERE tenant_id = :tenant AND id = ANY(:ids)"),
            {"by": by, "days": days, "tenant": tenant_id, "ids": list(ids)},
        ).rowcount
    _absence_to_trial_end(data, tenant_id)
    data.flush()
    return moved


def _absence_to_trial_end(data: Session, tenant_id) -> None:
    from backend.app.db.models.oversight import UserAbsence
    from backend.app.trial.sample_data import SAMPLE_SOURCE
    from backend.app.trial.sample_oversight import absence_end

    for row in data.query(UserAbsence).filter(
        UserAbsence.tenant_id == tenant_id, UserAbsence.source_system == SAMPLE_SOURCE
    ):
        row.ends_on = absence_end(data, tenant_id, row.starts_on)


def keep_current(control: Session, data: Session, tenant_id, now: datetime | None = None) -> dict:
    """Bring one trial's sample to ``now`` (see the module docstring). Commits both sessions when it moves anything."""
    from backend.app.oversight.service import calendar_of
    from backend.app.trial import team
    from backend.app.trial.sample_data import has_sample_data

    now = now or datetime.now(timezone.utc)
    request = team.trial_request(control, tenant_id)
    since = anchor_of(request)
    if request is None or since is None:
        return {"moved": False, "why": "CURRENT"}
    # Whole days on the organization's calendar: nothing moves until its next day has begun (A1, option C).
    calendar = calendar_of(data, tenant_id)
    days = (calendar.local_day(now) - calendar.local_day(since)).days
    if days < 1:
        return {"moved": False, "why": "CURRENT"}
    if not has_sample_data(data, tenant_id):
        return {"moved": False, "why": "NO_SAMPLE"}
    if worked_on(data, tenant_id):
        return {"moved": False, "why": "WORKED_ON"}
    # Whole days on that calendar's clock (wall time), so a summer-time change never shifts a sample time by an hour.
    data.execute(text("SELECT set_config('TimeZone', :zone, true)"), {"zone": calendar.zone})
    moved = move(data, tenant_id, timedelta(days=days), days)
    data.commit()
    # The anchor moves by the same days, so its time of day, and every sample time's, stays as seeded.
    request.profile = {
        **(request.profile or {}),
        ANCHOR: (since.astimezone(calendar.tz) + timedelta(days=days)).isoformat(),
    }
    control.commit()
    return {"moved": True, "by_days": days, "rows": sum(moved.values())}


def run_for_all_trials(control: Session) -> dict:
    """The scheduler job: ``keep_current`` for every trial on the shared plane still holding data; a failing trial is
    logged and the others go on."""
    from backend.app.db.data_plane import TRIAL_SHARED_DATA_PLANE
    from backend.app.db.models.customer_lifecycle import TenantDataPlane
    from backend.app.db.models.foundation import PlanDefinition, Tenant
    from backend.app.db.models.stage2 import SubscriptionLifecycle
    from backend.app.db.tenant_scope import bind_tenant
    from backend.app.trial.service import FREE_TRIAL_PLAN, trial_has_ended

    tenants = [
        tenant_id
        for (tenant_id,) in control.query(Tenant.id)
        .join(SubscriptionLifecycle, SubscriptionLifecycle.tenant_id == Tenant.id)
        .join(PlanDefinition, PlanDefinition.id == SubscriptionLifecycle.plan_id)
        .join(TenantDataPlane, TenantDataPlane.tenant_id == Tenant.id)
        .filter(
            PlanDefinition.code == FREE_TRIAL_PLAN,
            TenantDataPlane.connection_secret_ref == TRIAL_SHARED_DATA_PLANE,
            Tenant.status == "ACTIVE",
        )
        .distinct()
    ]
    totals = {"trials": 0, "moved": 0, "failed": 0}
    for tenant_id in tenants:
        if trial_has_ended(control, tenant_id):
            continue
        with Session(bind=control.get_bind(), autoflush=False) as data:
            bind_tenant(data, tenant_id)
            try:
                done = keep_current(control, data, tenant_id)
            except Exception:
                data.rollback()
                control.rollback()
                logger.exception("The sample story of %s could not be brought up to date", tenant_id)
                totals["failed"] += 1
                continue
        totals["trials"] += 1
        totals["moved"] += int(done["moved"])
    return totals


# --------------------------------------------------------------------------------------------- restart


def own_records(data: Session, tenant_id) -> int:
    """How many records the organization uploaded itself (what "also remove my practice work" removes with what was
    done on them)."""
    if not _has_own(data, tenant_id):
        return 0
    return sum(len(ids) for ids in _own_plan(data, tenant_id)["rows"].values())


def _has_own(data: Session, tenant_id) -> bool:
    from backend.app.db.models.foundation import Complaint, Product
    from backend.app.trial.sample_removal import OWN_SOURCES

    return any(
        data.query(model.id).filter(model.tenant_id == tenant_id, model.source_system.in_(OWN_SOURCES)).first()
        is not None
        for model in (Complaint, Product)
    )


def _own_plan(data: Session, tenant_id) -> dict:
    from backend.app.trial import sample_removal

    return sample_removal.plan(data, tenant_id, sources=sample_removal.OWN_SOURCES, marked=sample_removal.OWN_MARKED)


def restart(control: Session, data: Session, tenant_id, user, *, own: bool, correlation_id=None) -> dict:
    """Remove the sample (and, with ``own``, the organization's own uploads and what was done with them) and seed the
    sample again now. Raises RuntimeError when the removal would leave rows (nothing is changed then). Commits."""
    from backend.app.enterprise_audit import make_audit_event
    from backend.app.signals.hooks import seed_demo_signals
    from backend.app.trial import sample_removal, story, team

    now = datetime.now(timezone.utc)
    request = team.trial_request(control, tenant_id)
    before = story.progress(data, tenant_id, story.remembered(request.profile if request else None))
    removed = sample_removal.remove(data, tenant_id, before["acted"])["deleted"]
    removed_own: dict = {}
    if own:
        removed_own = sample_removal.remove(
            data,
            tenant_id,
            [],
            sources=sample_removal.OWN_SOURCES,
            marked=sample_removal.OWN_MARKED,
        )["deleted"]
    seeded = seed_sample(data, tenant_id, now, owner_id=str(user.id))
    data.commit()
    request.profile = {**(request.profile or {}), ANCHOR: now.isoformat(), story.REMEMBERED: before["acted"]}
    control.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=str(user.id),
            action="TRIAL_SAMPLE_RESTARTED",
            entity_type="Tenant",
            entity_id=tenant_id,
            details={
                "removed": removed,
                "removed_own": removed_own,
                "own_removed": own,
                "chapters_kept": before["acted"],
                "seeded_at": now.isoformat(),
            },
            correlation_id=correlation_id,
        )
    )
    control.commit()
    seed_demo_signals(data, tenant_id)
    return {"status": "SAMPLE_RESTARTED", "seeded_at": now.isoformat(), "own_removed": own, "seeded": bool(seeded)}
