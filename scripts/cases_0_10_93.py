"""List what the 0.10.93 upgrade would change in the free trials' existing Cases (spec 9.2). Writes nothing.

    python scripts/cases_0_10_93.py            # one line per change (Case references, who logged it, country text)
    python scripts/cases_0_10_93.py --counts   # counts only: trials numbered, no reference, name or person

Migration tr19casesescalation adds the Case columns with their defaults, so every Case logged before 0.10.93 reads
"To check" (OPEN) with no channel, owner or complaint. This lists, per trial on the shared plane, the backfill the
owner reviews before anything is written (no judgement is made for anyone):

- channel: CONTACT and URGENT -> PHONE; SERVICE_RECORD -> SERVICE_RECORD_IMPORT;
- country: a recognised name or code -> its ISO code; anything else kept in country_text, "country to confirm";
- state, computed once from the latest Case check: unsigned -> OPEN; signed pending -> PENDING; signed service only,
  inquiry or not a complaint -> IN_REVIEW while its QA review is open, CLOSED once agreed; signed complaint (or
  complaint and service, or reclassified by the review) and linked to a complaint -> ESCALATED (attached);
- complaint: the earliest LINKED Case <-> complaint link;
- owner: the person who logged it, for every Case still open;
- record owner: Cases and sample complaints MDARIX, imported complaints EXTERNAL;
- OD-3: a signed complaint Case of the trial's own with no linked complaint would be escalated by the upgrade (a
  complaint created, actor "system: 0.10.93 upgrade"); its open QMS task completed "Not needed: owned in MDARIX"
  (a trial owns its complaints in MDARIX). The sample's SAMPLE-CALL-02 is never escalated here (spec 9.3);
- triage records: version 1 and one "as recorded before 0.10.93" version row each; speed FAST when completed;
- sample triage records with no severity: listed for the severity the story author would have chosen (T-M13).

Unflagged open complaints need no row: the routine triage queue reads them by query. Only Cases still at the
default state (OPEN) are considered, so Cases 0.10.93 itself moved are never touched. Writing is a later, separate
step after the owner's approval.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session  # noqa: E402

from backend.app.db.session import SessionLocal  # noqa: E402

CHANNEL_OF_KIND = {"CONTACT": "PHONE", "URGENT": "PHONE", "SERVICE_RECORD": "SERVICE_RECORD_IMPORT"}
NEVER_ESCALATED = ("SAMPLE-CALL-02",)


class Change(str):
    """One listed change: its words, the kind of change it is and how many records it covers (for ``--counts``)."""

    def __new__(cls, text: str, kind: str, count: int = 1):
        line = super().__new__(cls, text)
        line.kind, line.count = kind, count
        return line


def counts(lines: list[Change]) -> Counter:
    """How many records each kind of change covers. The kinds name no record, organization or person."""
    found: Counter = Counter()
    for line in lines:
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


def plan_tenant(db: Session, tenant_id) -> list[Change]:
    """What the upgrade would change in one tenant's records, one line each. Reads only."""
    from backend.app.db.models.foundation import Complaint
    from backend.app.db.models.intake import (
        FirstContactCheck,
        IntakeEvent,
        RecordLink,
        TriageRecord,
        TriageRecordVersion,
    )
    from backend.app.db.models.workflow import WorkflowTask
    from backend.app.intake import case_rules
    from backend.app.intake.service import COMPLAINT, INTAKE, QMS, SOURCE_TYPE
    from backend.app.trial.imports import UPLOAD_SOURCE
    from backend.app.trial.sample_source import SAMPLE_SOURCE
    from backend.app.workflow.tasks import OPEN_TASK_STATUSES

    lines: list[Change] = []
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
    escalated_by_upgrade = []
    for event in events:
        ref = event.reference
        if event.channel is None and event.kind in CHANNEL_OF_KIND:
            channel = CHANNEL_OF_KIND[event.kind]
            lines.append(
                Change(
                    f'{ref}: channel -> {channel} ("{case_rules.CHANNELS[channel]}", was kind {event.kind})',
                    f"Case channel set to {channel} from its old kind",
                )
            )
        country = country_change(event.country)
        if country and country[0]:
            lines.append(Change(f"{ref}: country {event.country!r} -> {country[0]}", "Case country set to its code"))
        elif country:
            lines.append(
                Change(
                    f"{ref}: country {event.country!r} kept as text, flagged 'country to confirm'",
                    "Case country kept as text, flagged 'country to confirm'",
                )
            )
        if event.record_owner is None:
            lines.append(Change(f"{ref}: record owner -> MDARIX", "Case record owner set to MDARIX"))
        complaint_id = event.complaint_id or linked.get(event.id)
        if event.complaint_id is None and complaint_id is not None:
            lines.append(
                Change(
                    f"{ref}: complaint -> {complaint_id} (its earliest link)",
                    "Case linked to its complaint (the earliest link)",
                )
            )
        if event.status != case_rules.OPEN:
            continue  # moved by 0.10.93 itself
        state = state_for(checks.get(event.id), complaint_id is not None, voided=bool(event.voided_by))
        if state is None:
            if ref in NEVER_ESCALATED or event.source_system == SAMPLE_SOURCE:
                lines.append(
                    Change(
                        f"{ref}: signed complaint, no complaint: left for a person to escalate (sample, 9.3)",
                        "sample signed complaint Case left for a person to escalate",
                    )
                )
            else:
                escalated_by_upgrade.append(event.id)
                lines.append(
                    Change(
                        f"{ref}: signed complaint, no complaint: ESCALATED by the upgrade, a complaint created (OD-3)",
                        "signed complaint Case escalated by the upgrade (a complaint created)",
                    )
                )
        elif state != case_rules.OPEN:
            note = " (attached)" if state == case_rules.ESCALATED else ""
            lines.append(Change(f"{ref}: state OPEN -> {state}{note}", f"Case state OPEN -> {state}{note}"))
        if state in (case_rules.OPEN, case_rules.PENDING) and not event.owner_id:
            lines.append(
                Change(f"{ref}: owner -> {event.created_by} (who logged it)", "Case owner set to who logged it")
            )
    if escalated_by_upgrade:
        for task in db.query(WorkflowTask).filter(
            WorkflowTask.tenant_id == tenant_id,
            WorkflowTask.task_type == QMS,
            WorkflowTask.source_entity_type == SOURCE_TYPE,
            WorkflowTask.source_entity_id.in_(escalated_by_upgrade),
            WorkflowTask.status.in_(OPEN_TASK_STATUSES),
        ):
            lines.append(
                Change(
                    f"{task.business_id}: QMS task completed 'Not needed: owned in MDARIX'",
                    "QMS task completed 'Not needed: owned in MDARIX'",
                )
            )
    for source, owner in ((UPLOAD_SOURCE, "EXTERNAL"), (SAMPLE_SOURCE, "MDARIX")):
        count = (
            db.query(Complaint)
            .filter(
                Complaint.tenant_id == tenant_id, Complaint.source_system == source, Complaint.record_owner.is_(None)
            )
            .count()
        )
        if count:
            lines.append(
                Change(
                    f"{count} {source} complaint(s): record owner -> {owner}",
                    f"{source} complaint record owner set to {owner}",
                    count,
                )
            )
    records = db.query(TriageRecord).filter(TriageRecord.tenant_id == tenant_id).all()
    versioned = {
        row[0]
        for row in db.query(TriageRecordVersion.triage_record_id).filter(TriageRecordVersion.tenant_id == tenant_id)
    }
    missing = [row for row in records if row.id not in versioned]
    if missing:
        lines.append(
            Change(
                f"{len(missing)} triage record(s): version 1 kept as 'as recorded before 0.10.93'",
                "triage record version 1 kept as 'as recorded before 0.10.93'",
                len(missing),
            )
        )
    fast = [row for row in records if row.speed is None and row.completed_at is not None]
    if fast:
        lines.append(
            Change(
                f"{len(fast)} completed triage record(s): speed -> FAST",
                "completed triage record speed set to FAST",
                len(fast),
            )
        )
    unrated = [row for row in records if row.source_system == SAMPLE_SOURCE and row.severity is None]
    if unrated:
        lines.append(
            Change(
                f"{len(unrated)} sample triage record(s) with no severity: the story author's severity (T-M13)",
                "sample triage record given the story author's severity",
                len(unrated),
            )
        )
    return lines


def plan(db: Session) -> list[tuple[str, str, list[str]]]:
    from backend.app.db.tenant_scope import bind_tenant
    from scripts.refresh_trial_story import trials

    found = []
    for tenant_id, tenant_key, name in trials(db):
        with SessionLocal() as session:
            bind_tenant(session, tenant_id)
            found.append((tenant_key, name, plan_tenant(session, tenant_id)))
            session.rollback()  # reads only
    return found


def print_counts(found: list[tuple[str, str, list[Change]]]) -> None:
    """Counts only: each trial by its number in this list, never its key, name, records or people."""
    total: Counter = Counter()
    for number, (_key, _name, lines) in enumerate(found, start=1):
        found_here = counts(lines)
        total.update(found_here)
        print(f"Trial {number} of {len(found)}: {'records to change' if found_here else 'no change'}")
        for kind, count in sorted(found_here.items()):
            print(f"  {count:>6}  {kind}")
    if found:
        print(f"All {len(found)} trial(s): {'records to change' if total else 'no change'}")
        for kind, count in sorted(total.items()):
            print(f"  {count:>6}  {kind}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--counts", action="store_true", help="counts only: no reference, name or person is printed")
    args = parser.parse_args(argv)
    db = SessionLocal()
    try:
        found = plan(db)
    finally:
        db.close()
    if args.counts:
        print_counts(found)
    else:
        for tenant_key, name, lines in found:
            print(f"{tenant_key} ({name[:40]}): {f'{len(lines)} change(s)' if lines else 'no change'}")
            for line in lines:
                print(f"  {line}")
    if not found:
        print("No free trial holds data.")
    print("\nNothing was changed (list only). The owner approves this list before any write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
