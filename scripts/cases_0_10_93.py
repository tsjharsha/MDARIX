"""The 0.10.93 upgrade of the free trials' existing Cases (B2 spec 9.1, 9.2). Lists by default; writes only with --apply.

    python scripts/cases_0_10_93.py            # list: one line per change (Case references, who logged it, country)
    python scripts/cases_0_10_93.py --counts   # list, counts only: trials numbered, no reference, name or person
    python scripts/cases_0_10_93.py --apply    # list the counts, ask for the typed confirmation, then change them

Migration tr19casesescalation adds the Case columns with their defaults, so every Case logged before 0.10.93 reads
"To check" (OPEN) with no channel, owner or complaint. Per trial on the shared plane, in that trial's own
tenant-bound session (row-level security), this sets (no judgement is made for anyone):

- channel: CONTACT and URGENT -> PHONE; SERVICE_RECORD -> SERVICE_RECORD_IMPORT;
- country: a recognised name or code -> its ISO code; anything else moved to country_text ("country to confirm");
- state, computed once from the latest Case check: unsigned -> OPEN; signed pending -> PENDING; signed service only,
  inquiry or not a complaint -> IN_REVIEW while its QA review is open, CLOSED once agreed; signed complaint (or
  complaint and service, or reclassified by the review) and linked to a complaint -> ESCALATED (attached);
- complaint: the earliest LINKED Case <-> complaint link;
- owner: the person who logged it, for every Case still open;
- record owner: Cases and sample complaints MDARIX, imported complaints EXTERNAL;
- OD-3: a signed complaint Case of the trial's own with no linked complaint is escalated by the upgrade (a complaint
  created, actor "system: 0.10.93 upgrade"); its open QMS task completed "Not needed: owned in MDARIX" (or, where the
  organization keeps complaints in its QMS, replaced by the escalation's QMS complaint ID task, as the "Signed before
  0.10.93: escalate" action does). The sample's SAMPLE-CALL-02 is never escalated here (spec 9.3);
- triage records: one "as recorded before 0.10.93" version row each (version 1); speed FAST when completed.

Left as they are and listed as such (an owner choice the spec leaves open): a service-only Case whose QA review was
agreed but which has no resolution summary (S-2 closes a service-only Case only with one), and the sample triage
records with no severity (T-M13: the story author's severity is not written down anywhere).

Unflagged open complaints need no row: the routine triage queue reads them by query. Only Cases still at the default
state (OPEN) are touched, so Cases 0.10.93 itself moved are never changed; every change fills a field that is empty or
moves a Case off OPEN, so a second run changes nothing. Signed checks and their signatures are never changed. ``--apply`` commits in batches of
BATCH changes and audits each change (actor UPGRADE_ACTOR); it prints counts only.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session  # noqa: E402

from backend.app.db.session import SessionLocal  # noqa: E402

CHANNEL_OF_KIND = {"CONTACT": "PHONE", "URGENT": "PHONE", "SERVICE_RECORD": "SERVICE_RECORD_IMPORT"}
NEVER_ESCALATED = ("SAMPLE-CALL-02",)
UPGRADE_ACTOR = "system: 0.10.93 upgrade"
CONFIRMATION = "APPLY 0.10.93"
BATCH = 200
QMS_SOURCE = "QMS"  # triage taken over from a QMS import is 0.10.93's own (T-D9): it is never "before 0.10.93"


def _covered() -> None:
    """The action of a line another line's action carries out (listed for what it changes)."""


class Change(str):
    """One listed change: its words, the kind of change it is, how many records it covers (for ``--counts``) and what
    ``--apply`` does for it. ``held``: listed, but left as it is (an owner choice); never counted as a change."""

    def __new__(cls, text: str, kind: str, count: int = 1, do=None, held: bool = False):
        line = super().__new__(cls, text)
        line.kind, line.count, line.do, line.held = kind, count, do, held
        return line


def counts(lines: list[Change], held: bool = False) -> Counter:
    """How many records each kind of change covers (``held``: the records left as they are). The kinds name no record,
    organization or person."""
    found: Counter = Counter()
    for line in lines:
        if bool(getattr(line, "held", False)) == held:
            found[line.kind] += line.count
    return found


def state_for(check, linked: bool, voided: bool = False) -> str | None:
    """The state a pre-0.10.93 Case reads from its latest check; None for a signed complaint with no complaint (OD-3:
    the upgrade escalates it). Pure."""
    from backend.app.intake import case_rules, rules

    if voided:
        return case_rules.VOIDED
    if check is None or check.signed_at is None:
        return case_rules.OPEN
    classification = check.classification
    if classification in rules.PENDING_OUTCOMES:
        return case_rules.PENDING
    if classification in case_rules.REVIEWED_OUTCOMES and check.review_outcome != "RECLASSIFIED":
        return case_rules.CLOSED if check.review_outcome == "AGREED" else case_rules.IN_REVIEW
    return case_rules.ESCALATED if linked else None


def country_change(value: str | None) -> tuple[str | None, str | None] | None:
    """(ISO code, text to keep) for a Case's country, or None when nothing changes (empty, or already a code)."""
    from backend.app.countries import code_of

    text = (value or "").strip()
    if not text:
        return None
    code = code_of(text)
    if code == text:
        return None
    return (code, None) if code else (None, text)


def plan_tenant(db: Session, tenant_id, now: datetime | None = None) -> list[Change]:
    """What the upgrade changes in one tenant's records, one line each, with the action ``apply_tenant`` runs for it.
    Building the list reads only; ``db`` must be bound to ``tenant_id``."""
    from backend.app.db.models.foundation import Complaint
    from backend.app.db.models.intake import (
        FirstContactCheck,
        IntakeEvent,
        RecordLink,
        TriageRecord,
        TriageRecordVersion,
    )
    from backend.app.db.models.workflow import WorkflowTask
    from backend.app.intake import case_rules, service
    from backend.app.intake.service import COMPLAINT, INTAKE, QMS, SOURCE_TYPE
    from backend.app.trial.imports import UPLOAD_SOURCE
    from backend.app.trial.sample_source import SAMPLE_SOURCE
    from backend.app.db.tenant_scope import scope_of
    from backend.app.workflow.tasks import OPEN_TASK_STATUSES, complete_tasks

    if scope_of(db).get("tenant_id") != str(tenant_id):
        raise ValueError("The session must be bound to the trial it changes (bind_tenant): one trial at a time")
    now = now or datetime.now(timezone.utc)
    lines: list[Change] = []

    def audit(event, field: str) -> None:
        service._audit(db, tenant_id, UPGRADE_ACTOR, "CASE_FIELD_SET_BY_UPGRADE", event, now, None, field=field)

    def set_field(event, field: str, value, also: dict | None = None):
        def do():
            setattr(event, field, value)
            for name, other in (also or {}).items():
                setattr(event, name, other)
            event.updated_at = now
            audit(event, field)

        return do

    def move(event, targets: tuple[str, ...], classification):
        def do():
            for target in targets:
                service.set_case_status(
                    db,
                    db,
                    tenant_id,
                    event,
                    target,
                    UPGRADE_ACTOR,
                    now,
                    why=_why(target),
                    classification=classification,
                )

        return do

    def attach(event, complaint_id, check):
        def do():
            event.complaint_id, event.escalation = complaint_id, "ATTACHED"
            event.escalated_at, event.escalated_by = now, UPGRADE_ACTOR
            service.set_case_status(
                db, db, tenant_id, event, case_rules.ESCALATED, UPGRADE_ACTOR, now, why=_why_signed(check)
            )
            service._audit(
                db,
                tenant_id,
                UPGRADE_ACTOR,
                "CASE_ESCALATED",
                event,
                now,
                None,
                complaint_id=str(complaint_id),
                escalation="ATTACHED",
            )

        return do

    def escalate(event, check, owner: str, flow: str):
        def do():
            # The old "Awaiting import" task first: an EXTERNAL escalation then adds its own QMS complaint ID task.
            complete_tasks(
                db,
                tenant_id,
                source_type=SOURCE_TYPE,
                source_id=event.id,
                task_types=[QMS],
                outcome="NOT_NEEDED",
                actor_ref=UPGRADE_ACTOR,
                reason="Not needed: owned in MDARIX"
                if owner == "MDARIX"
                else "Replaced by the QMS complaint ID task of the escalation",
            )
            service.escalate_case(
                db,
                db,
                tenant_id,
                event,
                check,
                UPGRADE_ACTOR,
                now,
                record_owner=owner,
                flow=flow,
                why=_why_signed(check),
            )

        return do

    # Triage first: an escalation below hands a finished triage to its new complaint as it then stands.
    records = db.query(TriageRecord).filter(TriageRecord.tenant_id == tenant_id).all()
    versioned = {
        row[0]
        for row in db.query(TriageRecordVersion.triage_record_id).filter(TriageRecordVersion.tenant_id == tenant_id)
    }
    missing = [row for row in records if row.id not in versioned and row.source_system != QMS_SOURCE]
    if missing:

        def add_versions():
            for row in missing:
                row.version = 1
                service.add_triage_version(db, tenant_id, row, None, UPGRADE_ACTOR, now, "As recorded before 0.10.93")

        lines.append(
            Change(
                f"{len(missing)} triage record(s): version 1 kept as 'as recorded before 0.10.93'",
                "triage record version 1 kept as 'as recorded before 0.10.93'",
                len(missing),
                add_versions,
            )
        )
    fast = [row for row in records if row.speed is None and row.completed_at is not None]
    if fast:

        def set_fast():
            from backend.app.intake.triage_rules import FAST

            for row in fast:
                row.speed, row.updated_at = FAST, now

        lines.append(
            Change(
                f"{len(fast)} completed triage record(s): speed -> FAST",
                "completed triage record speed set to FAST",
                len(fast),
                set_fast,
            )
        )
    unrated = [row for row in records if row.source_system == SAMPLE_SOURCE and row.severity is None]
    if unrated:
        lines.append(
            Change(
                f"{len(unrated)} sample triage record(s) with no severity: LEFT AS THEY ARE (T-M13: the story author's "
                "severity is not written down; owner choice)",
                "sample triage record with no severity left as it is (owner choice, T-M13)",
                len(unrated),
                held=True,
            )
        )
    triaged = {(row.subject_kind, row.subject_id): row for row in records}

    events = db.query(IntakeEvent).filter(IntakeEvent.tenant_id == tenant_id).order_by(IntakeEvent.reference).all()
    checks: dict = {}
    for check in (
        db.query(FirstContactCheck)
        .filter(FirstContactCheck.tenant_id == tenant_id, FirstContactCheck.superseded_by.is_(None))
        .order_by(FirstContactCheck.version)
    ):
        checks[check.intake_event_id] = check  # the latest version wins
    linked: dict = {}
    for link in (
        db.query(RecordLink)
        .filter(RecordLink.tenant_id == tenant_id, RecordLink.state == "LINKED")
        .order_by(RecordLink.created_at)
    ):
        for (kind, rid), (other, oid) in (
            ((link.left_kind, link.left_id), (link.right_kind, link.right_id)),
            ((link.right_kind, link.right_id), (link.left_kind, link.left_id)),
        ):
            if kind == INTAKE and other == COMPLAINT:
                linked.setdefault(rid, oid)  # the earliest link
    owner_of_complaints, flow = service.case_setup(db, tenant_id, trial=True)
    escalated_by_upgrade = []
    for event in events:
        ref = event.reference
        if event.status != case_rules.OPEN:
            continue  # moved by 0.10.93 itself (or by this upgrade): a Case past "To check" is never touched
        check = checks.get(event.id)
        complaint_id = event.complaint_id or linked.get(event.id)
        state = state_for(check, complaint_id is not None, voided=bool(event.voided_by))
        if event.channel is None and event.kind in CHANNEL_OF_KIND:
            channel = CHANNEL_OF_KIND[event.kind]
            lines.append(
                Change(
                    f'{ref}: channel -> {channel} ("{case_rules.CHANNELS[channel]}", was kind {event.kind})',
                    f"Case channel set to {channel} from its old kind",
                    do=set_field(event, "channel", channel),
                )
            )
        country = country_change(event.country)
        if country and country[0]:
            lines.append(
                Change(
                    f"{ref}: country {event.country!r} -> {country[0]}",
                    "Case country set to its code",
                    do=set_field(event, "country", country[0]),
                )
            )
        elif country:
            lines.append(
                Change(
                    f"{ref}: country {event.country!r} kept as text, flagged 'country to confirm'",
                    "Case country kept as text, flagged 'country to confirm'",
                    do=set_field(event, "country_text", country[1], {"country": None}),
                )
            )
        if event.record_owner is None:
            lines.append(
                Change(
                    f"{ref}: record owner -> MDARIX",
                    "Case record owner set to MDARIX",
                    do=set_field(event, "record_owner", "MDARIX"),
                )
            )
        # The owner before the state: a run stopped between the two never leaves a moved Case without its owner.
        if state in (case_rules.OPEN, case_rules.PENDING) and not event.owner_id:
            lines.append(
                Change(
                    f"{ref}: owner -> {event.created_by} (who logged it)",
                    "Case owner set to who logged it",
                    do=set_field(event, "owner_id", event.created_by),
                )
            )
        if event.complaint_id is None and complaint_id is not None and state != case_rules.ESCALATED:
            lines.append(
                Change(
                    f"{ref}: complaint -> {complaint_id} (its earliest link)",
                    "Case linked to its complaint (the earliest link)",
                    do=set_field(event, "complaint_id", complaint_id),
                )
            )
        if state is None:
            if ref in NEVER_ESCALATED or event.source_system == SAMPLE_SOURCE:
                lines.append(
                    Change(
                        f"{ref}: signed complaint, no complaint: left for a person to escalate (sample, 9.3)",
                        "sample signed complaint Case left for a person to escalate",
                        held=True,
                    )
                )
            else:
                escalated_by_upgrade.append(event.id)
                lines.append(
                    Change(
                        f"{ref}: signed complaint, no complaint: ESCALATED by the upgrade, a complaint created (OD-3)",
                        "signed complaint Case escalated by the upgrade (a complaint created)",
                        do=escalate(event, check, owner_of_complaints, flow),
                    )
                )
                source = triaged.get((INTAKE, event.id))
                if source is not None and source.completed_at is not None:
                    lines.append(
                        Change(
                            f"{ref}: its finished triage copied to the new complaint (T-D8)",
                            "Case triage copied to the complaint the upgrade created",
                            do=_covered,
                        )
                    )
        elif state == case_rules.ESCALATED:
            lines.append(
                Change(
                    f"{ref}: state OPEN -> ESCALATED (attached to {complaint_id}, its earliest link)",
                    "Case state OPEN -> ESCALATED (attached)",
                    do=attach(event, complaint_id, check),
                )
            )
        elif state == case_rules.CLOSED and case_rules.close_problem(check.classification, event.resolution_summary):
            lines.append(
                Change(
                    f"{ref}: QA review agreed, no resolution summary: LEFT 'To check' (S-2 closes a service-only Case "
                    "only with its resolution summary; owner choice)",
                    "Case agreed in QA review but with no resolution summary left as it is (owner choice, S-2)",
                    held=True,
                )
            )
        elif state != case_rules.OPEN:
            targets = (case_rules.IN_REVIEW, case_rules.CLOSED) if state == case_rules.CLOSED else (state,)
            lines.append(
                Change(
                    f"{ref}: state OPEN -> {state}",
                    f"Case state OPEN -> {state}",
                    do=move(event, targets, check.classification if check else None),
                )
            )
    if escalated_by_upgrade:
        reason = (
            "Not needed: owned in MDARIX"
            if owner_of_complaints == "MDARIX"
            else "replaced by the escalation's QMS complaint ID task"
        )
        for task in db.query(WorkflowTask).filter(
            WorkflowTask.tenant_id == tenant_id,
            WorkflowTask.task_type == QMS,
            WorkflowTask.source_entity_type == SOURCE_TYPE,
            WorkflowTask.source_entity_id.in_(escalated_by_upgrade),
            WorkflowTask.status.in_(OPEN_TASK_STATUSES),
        ):
            lines.append(
                Change(
                    f"{task.business_id}: QMS task completed '{reason}'",
                    f"QMS task completed '{reason}'",
                    do=_covered,  # completed by its Case's escalation, before the escalation's own task is added
                )
            )
    for source, owner in ((UPLOAD_SOURCE, "EXTERNAL"), (SAMPLE_SOURCE, "MDARIX")):
        unowned = (
            db.query(Complaint)
            .filter(
                Complaint.tenant_id == tenant_id, Complaint.source_system == source, Complaint.record_owner.is_(None)
            )
            .all()
        )
        if unowned:

            def set_owner(rows=unowned, owner=owner):
                for row in rows:
                    row.record_owner = owner

            lines.append(
                Change(
                    f"{len(unowned)} {source} complaint(s): record owner -> {owner}",
                    f"{source} complaint record owner set to {owner}",
                    len(unowned),
                    set_owner,
                )
            )
    return lines


def _why(target: str) -> str:
    return f"Set by the 0.10.93 upgrade from the Case's signed check ({target})"


def _why_signed(check) -> str:
    """OD-3's reason: the signed Case check the escalation carries out."""
    when = check.signed_at.date().isoformat() if check and check.signed_at else "an unknown date"
    return f"Escalated from the signed Case check of {when} by {check.signed_by if check else 'an unknown signer'}"


def apply_tenant(db: Session, tenant_id, now: datetime | None = None, batch: int = BATCH) -> list[Change]:
    """Carry out ``plan_tenant``'s changes in ``db`` (bound to ``tenant_id``), committing every ``batch`` changes and
    once at the end, with a summary audit event. Returns the lines carried out (held lines are left as they are)."""
    from backend.app.enterprise_audit import make_audit_event

    now = now or datetime.now(timezone.utc)
    lines = plan_tenant(db, tenant_id, now)
    done: list[Change] = []
    for line in lines:
        if line.held:
            continue
        line.do()
        done.append(line)
        if len(done) % batch == 0:
            db.commit()
    if done:
        db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=UPGRADE_ACTOR,
                action="CASES_UPGRADED_0_10_93",
                entity_type="Tenant",
                entity_id=tenant_id,
                details={"changes": dict(counts(done)), "left_as_they_are": dict(counts(lines, held=True))},
                created_at=now,
            )
        )
    db.commit()
    return done


def _each_trial(db: Session, work) -> list[tuple[str, str, list[Change]]]:
    from backend.app.db.tenant_scope import bind_tenant
    from scripts.refresh_trial_story import trials

    found = []
    for tenant_id, tenant_key, name in trials(db):
        with SessionLocal() as session:
            bind_tenant(session, tenant_id)
            found.append((tenant_key, name, work(session, tenant_id)))
    return found


def plan(db: Session) -> list[tuple[str, str, list[Change]]]:
    def reads_only(session, tenant_id):
        lines = plan_tenant(session, tenant_id)
        session.rollback()
        return lines

    return _each_trial(db, reads_only)


def apply(db: Session) -> list[tuple[str, str, list[Change]]]:
    return _each_trial(db, apply_tenant)


def print_counts(found: list[tuple[str, str, list[Change]]]) -> None:
    """Counts only: each trial by its number in this list, never its key, name, records or people."""
    total: Counter = Counter()
    held: Counter = Counter()
    for number, (_key, _name, lines) in enumerate(found, start=1):
        found_here, held_here = counts(lines), counts(lines, held=True)
        total.update(found_here)
        held.update(held_here)
        print(f"Trial {number} of {len(found)}: {'records to change' if found_here else 'no change'}")
        for kind, count in sorted(found_here.items()):
            print(f"  {count:>6}  {kind}")
        for kind, count in sorted(held_here.items()):
            print(f"  {count:>6}  (left as it is) {kind}")
    if found:
        print(f"All {len(found)} trial(s): {'records to change' if total else 'no change'}")
        for kind, count in sorted(total.items()):
            print(f"  {count:>6}  {kind}")
        for kind, count in sorted(held.items()):
            print(f"  {count:>6}  (left as it is) {kind}")


def main(argv: list[str] | None = None, ask=input) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="list only (the default): exactly what --apply changes")
    mode.add_argument("--apply", action="store_true", help="change the records, after a typed confirmation")
    parser.add_argument("--counts", action="store_true", help="counts only: no reference, name or person is printed")
    args = parser.parse_args(argv)
    db = SessionLocal()
    try:
        found = plan(db)
        if args.counts or args.apply:
            print_counts(found)
        else:
            for tenant_key, name, lines in found:
                changes = [line for line in lines if not line.held]
                print(f"{tenant_key} ({name[:40]}): {f'{len(changes)} change(s)' if changes else 'no change'}")
                for line in lines:
                    print(f"  {line}")
        if not found:
            print("No free trial holds data.")
        if not args.apply:
            print("\nNothing was changed (list only). Run with --apply, after the owner approves this list.")
            return 0
        if not any(counts(lines) for _key, _name, lines in found):
            print("\nNothing to change.")
            return 0
        try:
            typed = ask(f'\nType "{CONFIRMATION}" to change the records counted above: ')
        except EOFError:
            typed = ""
        if typed.strip() != CONFIRMATION:
            print("Refused: the confirmation was not typed. Nothing was changed.")
            return 2
        done = apply(db)
    finally:
        db.close()
    print("\nChanged:")
    print_counts(done)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
