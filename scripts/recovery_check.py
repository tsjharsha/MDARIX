"""Recovery check of a restored database (B6b Part D, D1; runbook docs/runbooks/BACKUP_AND_RESTORE.md, sections 2-3).

Run it on the RESTORED database with the outbox worker and the scheduler stopped, before anyone signs in:

    python scripts/recovery_check.py --database mdarix_restore_drill --restore-point 20261113T021500Z \
        [--backup-dir /backups/20261113T021500Z] [--source-counts counts.json] [--erasure-log erasure_log.jsonl] \
        --restored-copy [--dry-run] [--out artifacts/recovery-check]

and, read only, on the source database to record what the restore must bring back:

    python scripts/recovery_check.py --database mdarix --write-counts counts.json

``--database`` must name the database the settings point at (``current_database()``), so the check never runs on a
database the operator did not name. The steps:

1. the backup's ``MANIFEST.sha256`` (with ``--backup-dir``);
2. nothing ran against the restored copy: no worker heartbeat after the restore point;
3. schema head equal to this code's head; policy count and forced row-level-security table count (equal to the
   source with ``--source-counts``); row counts of every table (compared with ``--source-counts``);
4. the audit chain of every organisation, recomputed from its first event (``verify_tenant_chain``);
5. each organisation's configuration against its latest signed G21 snapshot: every difference must be explained by
   a change event after the snapshot (``compare``, ``events_between``), otherwise it is flagged;
6. outbox hold (owner decision B6b-D10): every event of the copy not yet published is dead-lettered with the reason
   "held after restore" and one audit record per organisation, so nothing is sent twice; those that occurred after
   the restore point (written while the backup was taken) are counted apart and flagged. Only with
   ``--restored-copy``, and never when a background service runs against the database. A person replays only those
   the mail provider's log shows as not sent (``scripts/replay_outbox.py``). ``--dry-run`` lists them and changes
   nothing; organisations on a dedicated database are listed as not checked (run the check on each restored copy);
7. clock check (B6a G19);
8. erasure dry-run (``reapply_erasures`` with ``dry_run``; ``--erasure-log`` adds the newer log rows first, in a
   transaction that is rolled back);
9. the recovery window of each organisation (restore point to now): what its users back-enter (B6a G18).

Writes ``recovery-check-<UTC time>.json`` and ``.pdf`` (the record for MDX-OPS-001) and one customer summary PDF
per organisation, holding that organisation's lines only. Only the outbox hold writes to the database.

Exit status: 0 PASS; 1 FAIL (do not open the system); 2 usage error; 3 PASS WITH FLAGS (each flag needs a written
explanation in the signed recovery record before the system opens).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PASS, FAIL, FLAG, INFO = "PASS", "FAIL", "FLAG", "INFO"
EXIT_FLAGS = 3  # PASS WITH FLAGS (2 is a usage error, from argparse)
HELD_REASON = "held after restore"
HOLD_ACTION = "OUTBOX_EVENTS_HELD_AFTER_RESTORE"
ACTOR = "operator:recovery_check"
ITEMS_PER_AUDIT = 500  # events named in one audit record; the count always covers all of them
STAMP = re.compile(r"^\d{8}T\d{6}Z$")


def parse_restore_point(value: str) -> datetime:
    """A backup folder name (``20261113T021500Z``) or an ISO time with its offset; a time without a zone is refused."""
    value = value.strip()
    if STAMP.match(value):
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError("the restore point needs a time zone (UTC: end it with Z)")
    return moment.astimezone(timezone.utc)


def step(name: str, state: str, summary: str, **details) -> dict:
    return {"step": name, "state": state, "summary": summary, **details}


# ----------------------------------------------------------------------------------------------- 1. manifest


def check_manifest(backup_dir: Path) -> dict:
    """Every file named in MANIFEST.sha256 exists and has its SHA-256; a missing manifest or file is a failure."""
    manifest = backup_dir / "MANIFEST.sha256"
    if not manifest.is_file():
        return step("manifest", FAIL, f"No MANIFEST.sha256 in {backup_dir}")
    problems, checked = [], 0
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, _, name = line.partition("  ")
        name = name.strip().lstrip("*")
        target = (backup_dir / name).resolve()
        if backup_dir.resolve() not in target.parents:
            problems.append(f"{name}: outside the backup folder")
            continue
        if not target.is_file():
            problems.append(f"{name}: missing")
            continue
        digest = hashlib.sha256()
        with target.open("rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
        checked += 1
        if digest.hexdigest() != expected.strip().lower():
            problems.append(f"{name}: SHA-256 differs")
    if problems or not checked:
        return step("manifest", FAIL, "The backup does not match its manifest", problems=problems or ["empty manifest"])
    return step("manifest", PASS, f"{checked} file(s) match MANIFEST.sha256")


# ------------------------------------------------------------------------------- 2. nothing ran on the copy


QUIET_MINUTES = 15  # a running worker or scheduler writes its heartbeat every cycle (seconds)


def check_quiet(db, restore_point: datetime, now: datetime) -> dict:
    """The worker and the scheduler must stay stopped until the check is signed. A heartbeat of the last
    ``QUIET_MINUTES`` means one of them runs against this database: FAIL. A heartbeat after the restore point but
    older than that is flagged: the backup's folder time is taken before the dump reads the data, so production's
    own heartbeats of the dump's minutes come back with the copy (explain it from the backup log)."""
    from datetime import timedelta

    from sqlalchemy import text

    rows = db.execute(
        text(
            "SELECT service, instance_id, updated_at FROM worker_heartbeats WHERE updated_at > :point "
            "ORDER BY updated_at DESC"
        ),
        {"point": restore_point},
    ).all()
    services = [{"service": r.service, "instance": r.instance_id, "at": r.updated_at.isoformat()} for r in rows]
    recent = [item for row, item in zip(rows, services) if row.updated_at > now - timedelta(minutes=QUIET_MINUTES)]
    if recent:
        return step(
            "worker_stopped",
            FAIL,
            f"A background service wrote a heartbeat in the last {QUIET_MINUTES} minutes: stop the worker and the "
            "scheduler, then restore again",
            services=recent,
        )
    if rows:
        return step(
            "worker_stopped",
            FLAG,
            "Heartbeats after the restore point, none recent: written while the backup was being taken? Check the "
            "backup log's dump times",
            services=services,
        )
    return step("worker_stopped", PASS, "No background service ran after the restore point")


# ------------------------------------------------------------------------------- 3. schema and row counts


def database_facts(db) -> dict:
    """Schema head, policy count, forced-RLS table count and the row count of every table (read only)."""
    from sqlalchemy import text

    head = db.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
    policies = int(db.execute(text("SELECT count(*) FROM pg_policies WHERE schemaname = 'public'")).scalar())
    forced = int(
        db.execute(
            text(
                "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relforcerowsecurity"
            )
        ).scalar()
    )
    tables = db.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
    ).scalars()
    quote = db.get_bind().dialect.identifier_preparer.quote
    counts = {name: int(db.execute(text(f"SELECT count(*) FROM public.{quote(name)}")).scalar()) for name in tables}
    return {"schema_head": sorted(head), "policies": policies, "forced_rls_tables": forced, "row_counts": counts}


def check_schema(facts: dict, code_head: str) -> dict:
    if facts["schema_head"] != [code_head]:
        return step(
            "schema_head",
            FAIL,
            f"Schema head {facts['schema_head']} is not this release's head {code_head}",
            schema_head=facts["schema_head"],
            expected=code_head,
        )
    return step("schema_head", PASS, f"Schema head {code_head}", schema_head=code_head)


def check_security(facts: dict, source: dict | None) -> dict:
    found = {"policies": facts["policies"], "forced_rls_tables": facts["forced_rls_tables"]}
    if not facts["policies"] or not facts["forced_rls_tables"]:
        return step("row_level_security", FAIL, "No row-level-security policies or no forced tables", **found)
    if source is None:
        return step("row_level_security", FLAG, "No source counts given (--source-counts): not compared", **found)
    expected = {key: source.get(key) for key in found}
    if found != expected:
        return step(
            "row_level_security", FAIL, "Policy or forced-table count differs from the source", **found, source=expected
        )
    return step("row_level_security", PASS, "Policy and forced-table counts equal the source", **found)


def check_counts(facts: dict, source: dict | None) -> dict:
    counts = facts["row_counts"]
    total = sum(counts.values())
    if source is None:
        return step(
            "row_counts",
            FLAG,
            f"{len(counts)} tables, {total} rows; no source counts given: not compared",
            tables=counts,
        )
    theirs = source.get("row_counts") or {}
    differences = [
        {"table": name, "restored": counts.get(name), "source": theirs.get(name)}
        for name in sorted(set(counts) | set(theirs))
        if counts.get(name) != theirs.get(name)
    ]
    if differences:
        return step(
            "row_counts",
            FLAG,
            f"{len(differences)} table(s) differ from the source counts: explain each (for example, written after "
            "the backup)",
            differences=differences,
        )
    return step("row_counts", PASS, f"{len(counts)} tables, {total} rows: equal to the source counts")


# ------------------------------------------------------------------------------------------- 4. audit chain


def check_chains(db, tenant_ids: list | None = None) -> dict:
    """Recompute every organisation's audit chain from its first event (no anchor: the anchors came back with the
    same backup, so they prove nothing about it)."""
    from sqlalchemy import text

    from backend.app.audit_chain import verify_tenant_chain

    if tenant_ids is None:
        tenant_ids = db.execute(text("SELECT DISTINCT tenant_id FROM audit_events ORDER BY tenant_id")).scalars().all()
    results = []
    for tenant_id in tenant_ids:
        result = verify_tenant_chain(db, tenant_id)
        results.append(
            {
                "tenant_id": str(tenant_id),
                "valid": result["valid"],
                "checked": result["checked"],
                "first_broken_seq": result["first_broken_seq"],
                "last_seq": result["last_seq"],
            }
        )
    broken = [item for item in results if not item["valid"]]
    if broken:
        return step(
            "audit_chain",
            FAIL,
            f"The audit chain of {len(broken)} organisation(s) is broken: do not open the system",
            organisations=results,
        )
    return step(
        "audit_chain",
        PASS,
        f"The audit chain of all {len(results)} organisation(s) verifies ({sum(r['checked'] for r in results)} events)",
        organisations=results,
    )


# ------------------------------------------------------------------------------- 5. configuration vs G21


def _shared_plane(db, tenant_id) -> bool:
    from backend.app.db.data_plane import SHARED_CONTROL_DATA_PLANE
    from backend.app.db.models.customer_lifecycle import TenantDataPlane

    row = (
        db.query(TenantDataPlane)
        .filter(TenantDataPlane.tenant_id == tenant_id, TenantDataPlane.status == "ACTIVE")
        .first()
    )
    return row is None or row.connection_secret_ref == SHARED_CONTROL_DATA_PLANE


def configuration_of(db, tenant_id, now: datetime) -> dict:
    """One organisation's configuration against its latest signed snapshot (shared plane: ``db`` holds both)."""
    from backend.app.signed_reviews import configuration, signing

    latest = signing.signed_events(db, tenant_id, "configuration", limit=1)
    if not latest:
        return {"tenant_id": str(tenant_id), "state": INFO, "note": "no signed configuration snapshot"}
    if not _shared_plane(db, tenant_id):
        return {
            "tenant_id": str(tenant_id),
            "state": FLAG,
            "note": "dedicated database: compare on its restored copy (not checked here)",
        }
    review = signing.read(db, tenant_id, latest[0].entity_id)
    if not review["intact"]:
        return {
            "tenant_id": str(tenant_id),
            "state": FAIL,
            "review_id": review["review_id"],
            "note": "the signed snapshot no longer matches its signature",
        }
    # The customer administrator's view (the role that signs snapshots): MDARIX staff accounts are not listed.
    viewer = SimpleNamespace(tenant_id=tenant_id, role="CUSTOMER_ADMIN", id=None)
    current = configuration.snapshot(db, db, viewer, now)
    start = datetime.fromisoformat(review["content"]["taken_at"])
    events, incomplete = configuration.events_between(db, db, tenant_id, start, now)
    result = configuration.compare(review["content"], current, events)
    unexplained = [
        {"item": change["item"], "signed": change["before"], "now": change["after"]}
        for change in result["changes"]
        if not change["events"]
    ]
    explained = [change["item"] for change in result["changes"] if change["events"]]
    return {
        "tenant_id": str(tenant_id),
        "state": FLAG if unexplained or incomplete else PASS,
        "review_id": review["review_id"],
        "snapshot_taken_at": review["content"]["taken_at"],
        "explained": explained,
        "unexplained": unexplained,
        "events_incomplete": incomplete,
    }


def check_configuration(db, tenant_ids: list, now: datetime) -> dict:
    results = []
    for tenant_id in tenant_ids:
        try:
            results.append(configuration_of(db, tenant_id, now))
        except Exception as exc:  # one organisation's error is flagged and never hides the others
            db.rollback()
            results.append({"tenant_id": str(tenant_id), "state": FLAG, "note": f"not compared: {type(exc).__name__}"})
    states = {item["state"] for item in results}
    flagged = [item for item in results if item["state"] in (FAIL, FLAG)]
    state = FAIL if FAIL in states else FLAG if FLAG in states else PASS
    summary = (
        f"{len(flagged)} organisation(s) with a configuration difference no change event explains, or not compared"
        if flagged
        else "Every configuration difference since the latest signed snapshot is explained by a change event"
    )
    return step("configuration", state, summary, organisations=results)


def check_dedicated(db) -> dict:
    """Organisations on a dedicated database: their chain, counts and configuration live in that database, which
    this run does not read. Each is listed, so the check is run again against its restored copy."""
    from backend.app.db.data_plane import SHARED_CONTROL_DATA_PLANE
    from backend.app.db.models.customer_lifecycle import TenantDataPlane

    rows = (
        db.query(TenantDataPlane.tenant_id, TenantDataPlane.database_ref)
        .filter(TenantDataPlane.status == "ACTIVE", TenantDataPlane.connection_secret_ref != SHARED_CONTROL_DATA_PLANE)
        .all()
    )
    if rows:
        return step(
            "dedicated_databases",
            FLAG,
            f"{len(rows)} organisation(s) on a dedicated database: not checked here; run this check against each "
            "restored dedicated database too",
            organisations=[{"tenant_id": str(row.tenant_id), "database": row.database_ref} for row in rows],
        )
    return step("dedicated_databases", PASS, "Every organisation is on this database")


# ------------------------------------------------------------------------------------------- 6. outbox hold


def hold_outbox(db, restore_point: datetime, now: datetime, *, apply: bool, tenant_ids: list | None = None) -> dict:
    """Dead-letter every unpublished event of the restored copy (B6b-D10), with one audit record per organisation
    naming the events (never their payload). Does not commit. The events that occurred after the restore point are
    held too and counted apart: the backup's folder time is taken before the dump reads the data, so events of the
    dump's minutes come back unsent and may already have been sent by production. ``tenant_ids`` limits it to those
    organisations (tests); the script always holds every organisation's events."""
    from backend.app.db.models.stage2 import OutboxEvent
    from backend.app.enterprise_audit import make_audit_event

    unsent = db.query(OutboxEvent).filter(OutboxEvent.published_at.is_(None), OutboxEvent.dead_lettered_at.is_(None))
    if tenant_ids is not None:
        unsent = unsent.filter(OutboxEvent.tenant_id.in_(tenant_ids))
    pending = unsent.order_by(OutboxEvent.tenant_id, OutboxEvent.occurred_at).with_for_update().all()
    later = sum(row.occurred_at > restore_point for row in pending)
    by_tenant: dict = {}
    for row in pending:
        by_tenant.setdefault(row.tenant_id, []).append(row)
    per_tenant = {str(tenant_id): len(rows) for tenant_id, rows in by_tenant.items()}
    if apply:
        for tenant_id, rows in by_tenant.items():
            db.add(
                make_audit_event(
                    tenant_id=tenant_id,
                    actor_ref=ACTOR,
                    action=HOLD_ACTION,
                    entity_type="OutboxEvent",
                    details={
                        "source": "RECOVERY_CHECK",
                        "count": len(rows),
                        "listed": min(len(rows), ITEMS_PER_AUDIT),
                        "restore_point": restore_point.isoformat(),
                        "items": [
                            {
                                "id": str(row.id),
                                "event_name": row.event_name,
                                "occurred_at": row.occurred_at.isoformat(),
                            }
                            for row in rows[:ITEMS_PER_AUDIT]
                        ],
                    },
                    reason=f"{HELD_REASON}: replay only events the mail provider's log shows as not sent (B6b-D10)",
                    created_at=now,
                )
            )
            for row in rows:
                row.dead_lettered_at = now
                row.last_error = HELD_REASON
                row.claimed_by = None
                row.claimed_at = None
        db.flush()
    details = {
        "held" if apply else "to_hold": len(pending),
        "per_organisation": per_tenant,
        "after_restore_point": later,
    }
    if later:
        return step(
            "outbox_hold",
            FLAG,
            f"{later} unsent event(s) occurred after the restore point ({'held' if apply else 'to hold'}): written "
            "while the backup was taken, or something wrote to the restored database; explain from the backup log",
            **details,
        )
    if pending and not apply:
        return step("outbox_hold", FLAG, f"Dry run: {len(pending)} unsent event(s) would be held", **details)
    return step(
        "outbox_hold",
        PASS,
        f"{len(pending)} unsent event(s) held; replay only with scripts/replay_outbox.py after checking the mail "
        "provider's log"
        if pending
        else "No unsent event to hold",
        **details,
    )


# ---------------------------------------------------------------------------------- 7, 8, 9: clock, erasures


def check_clock(connection=None) -> dict:
    from backend.app import clock_check

    result = clock_check.check(connection)
    clock_state = result.pop("state")
    state = {clock_check.OK: PASS, clock_check.DEGRADED: FAIL}.get(clock_state, FLAG)
    summary = f"Clock check {clock_state} (limit {result['limit_seconds']} s)"
    return step("clock", state, summary, clock_state=clock_state, **result)


def check_erasures(db, log_rows: list[dict] | None) -> dict:
    """``reapply_erasures`` as a dry run (the caller rolls the session back)."""
    from backend.app.tenant_purge import import_erasure_log, reapply_erasures

    imported = import_erasure_log(db, log_rows, commit=False) if log_rows else 0
    summary = reapply_erasures(db, ACTOR, dry_run=True)
    pending, failed = len(summary["pending"]), len(summary["failed"])
    details = {"imported_log_rows": imported, "pending": pending, "skipped": len(summary["skipped"]), "failed": failed}
    if failed:
        return step("erasures", FAIL, f"{failed} erasure(s) could not be checked", **details)
    if pending:
        return step(
            "erasures",
            FLAG,
            f"{pending} erasure(s) to re-apply before anyone signs in (runbook section 4)",
            **details,
        )
    return step("erasures", PASS, "No erasure to re-apply", **details)


def organisations(db, restore_point: datetime, now: datetime) -> list[dict]:
    """Each organisation's recovery window: what was entered after the restore point is not in the restored copy and
    is back-entered by its users (B6a G18)."""
    from sqlalchemy import text

    rows = db.execute(
        text(
            "SELECT t.id, t.name, t.tenant_key, t.status, "
            "(SELECT max(a.created_at) FROM audit_events a WHERE a.tenant_id = t.id AND a.created_at <= :point) AS last "
            "FROM tenants t ORDER BY t.tenant_key"
        ),
        {"point": restore_point},
    ).all()
    hours = round((now - restore_point).total_seconds() / 3600, 1)
    return [
        {
            "tenant_id": str(row.id),
            "name": row.name,
            "key": row.tenant_key,
            "status": row.status,
            "last_record_in_copy": row.last.isoformat() if row.last else None,
            "window_from": restore_point.isoformat(),
            "window_to": now.isoformat(),
            "window_hours": hours,
        }
        for row in rows
    ]


# ----------------------------------------------------------------------------------------------- the record


def overall(steps: list[dict]) -> str:
    states = {item["state"] for item in steps}
    return "FAIL" if FAIL in states else "PASS WITH FLAGS" if FLAG in states else "PASS"


def _org_lines(record: dict, tenant_id: str) -> list[tuple[str, str]]:
    """Only this organisation's lines from every step."""
    lines: list[tuple[str, str]] = []
    for item in record["steps"]:
        for entry in item.get("organisations") or []:
            if entry.get("tenant_id") == tenant_id:
                text = {k: v for k, v in entry.items() if k != "tenant_id"}
                lines.append((f"{item['step']}: {json.dumps(text, default=str, sort_keys=True)}", "body"))
        held = (item.get("per_organisation") or {}).get(tenant_id)
        if held:
            lines.append((f"{item['step']}: {held} notification(s) held, not sent again automatically", "body"))
    return lines


def customer_summary(record: dict, org: dict) -> bytes:
    """One organisation's summary page: its recovery window, its chain and configuration lines and its held
    notifications. Nothing of another organisation."""
    from reports import pdf

    body = [
        ("What happened", "heading"),
        (f"MDARIX was restored from the backup taken at {org['window_from']}.", "body"),
        (
            f"Records your users entered between {org['window_from']} and {org['window_to']} "
            f"({org['window_hours']} hours) are not in the restored system. Please enter them again "
            "(back-entry keeps the original dates and the reason).",
            "body",
        ),
        ("Checks of your organisation", "heading"),
        *(_org_lines(record, org["tenant_id"]) or [("No organisation-specific finding.", "body")]),
        ("Signed record", "heading"),
        ("The full recovery record is signed by MDARIX's quality approver before the system is reopened.", "body"),
    ]
    return pdf.render(
        "MDARIX recovery summary",
        [f"Organisation: {org['name']}", f"Checked at {record['finished_at']}"],
        body,
        watermark="RECOVERY SUMMARY",
        footer=f"Recovery summary {org['key']}",
    )


def record_pdf(record: dict) -> bytes:
    from reports import pdf

    body: list[tuple[str, str]] = []
    for item in record["steps"]:
        body.append((f"{item['step']}: {item['state']}", "heading"))
        body.append((item["summary"], "body"))
        details = {k: v for k, v in item.items() if k not in ("step", "state", "summary")}
        if details:
            body.extend(pdf.flatten(details, 2, max_items=60))
    body.append(("Recovery window per organisation", "heading"))
    for org in record["organisations"]:
        body.append((f"{org['key']}: {org['window_hours']} h from {org['window_from']}", "body"))
    body.append(("Explanations and signatures (MDX-OPS-001)", "heading"))
    body.append(
        ("Each FLAG explained in writing; executed by the system owner, signed by the quality approver.", "body")
    )
    return pdf.render(
        "MDARIX recovery check",
        [
            f"Database: {record['database']}",
            f"Restore point: {record['restore_point']}",
            f"Result: {record['result']}",
            f"Started {record['started_at']}, finished {record['finished_at']}",
        ],
        body,
        watermark="RECOVERY CHECK",
        footer=f"Recovery check {record['database']} {record['finished_at']}",
    )


def write_record(record: dict, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    stamp = record["finished_at"].replace(":", "").replace("-", "")[:15] + "Z"
    written = [out / f"recovery-check-{stamp}.json", out / f"recovery-check-{stamp}.pdf"]
    written[0].write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    written[1].write_bytes(record_pdf(record))
    for org in record["organisations"]:
        safe = re.sub(r"[^A-Za-z0-9_-]", "_", org["key"] or org["tenant_id"])
        target = out / f"recovery-summary-{safe}-{stamp}.pdf"
        target.write_bytes(customer_summary(record, org))
        written.append(target)
    return written


# ------------------------------------------------------------------------------------------------------ run


def _session(reason: str):
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_system

    session = SessionLocal()
    bind_system(session, reason)
    return session


def run(
    *,
    restore_point: datetime,
    backup_dir: Path | None = None,
    source: dict | None = None,
    erasure_log: list[dict] | None = None,
    apply: bool = True,
    now: datetime | None = None,
    session_factory=_session,
    clock=check_clock,
) -> dict:
    """Every step, each on a session of its own; only the outbox hold commits (and only with ``apply``)."""
    from sqlalchemy import text

    from backend.app.db.data_plane import schema_head

    started = now or datetime.now(timezone.utc)
    steps: list[dict] = []
    if backup_dir is not None:
        steps.append(check_manifest(backup_dir))
    read = session_factory("recovery check: read the restored database")
    try:
        database = read.execute(text("SELECT current_database()")).scalar()
        quiet = check_quiet(read, restore_point, started)
        steps.append(quiet)
        facts = database_facts(read)
        steps += [check_schema(facts, schema_head()), check_security(facts, source), check_counts(facts, source)]
        steps.append(check_chains(read))
        orgs = organisations(read, restore_point, started)
        steps.append(check_configuration(read, [org["tenant_id"] for org in orgs], started))
        steps.append(check_dedicated(read))
    finally:
        read.rollback()
        read.close()
    if quiet["state"] == FAIL:
        apply = False  # a service runs against this database: never hold its live events (list them only)
    hold = session_factory("recovery check: hold unsent outbox events (B6b-D10)")
    try:
        steps.append(hold_outbox(hold, restore_point, started, apply=apply))
        if apply:
            hold.commit()
        else:
            hold.rollback()
    finally:
        hold.close()
    steps.append(clock())
    erasures = session_factory("recovery check: erasure dry-run")
    try:
        steps.append(check_erasures(erasures, erasure_log))
    finally:
        erasures.rollback()
        erasures.close()
    return {
        "record": "MDARIX recovery check (input to MDX-OPS-001)",
        "database": database,
        "restore_point": restore_point.isoformat(),
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "outbox_hold_applied": apply,
        "result": overall(steps),
        "steps": steps,
        "organisations": orgs,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--database", required=True, help="the database the settings point at (a safety check)")
    parser.add_argument("--restore-point", help="the backup's time: its folder name (20261113T021500Z) or ISO UTC")
    parser.add_argument("--backup-dir", type=Path, help="the backup folder, to check its MANIFEST.sha256")
    parser.add_argument("--source-counts", type=Path, help="counts JSON written by --write-counts on the source")
    parser.add_argument("--erasure-log", type=Path, help="erasure log (JSON Lines) from the newest copy")
    parser.add_argument("--dry-run", action="store_true", help="list the outbox events to hold; change nothing")
    parser.add_argument(
        "--restored-copy",
        action="store_true",
        help="confirm this database is a restored copy (needed to hold its outbox events)",
    )
    parser.add_argument("--write-counts", type=Path, help="write this database's counts (read only) and stop")
    parser.add_argument("--out", type=Path, default=ROOT / "artifacts" / "recovery-check", help="folder for the record")
    args = parser.parse_args(argv)

    from sqlalchemy import text

    probe = _session("recovery check: which database")
    try:
        current = probe.execute(text("SELECT current_database()")).scalar()
        if current != args.database:
            print(f"Refused: the settings point at database {current!r}, not {args.database!r}", file=sys.stderr)
            return 1
        if args.write_counts:
            facts = database_facts(probe)
            args.write_counts.write_text(
                json.dumps(
                    {"database": current, "taken_at": datetime.now(timezone.utc).isoformat(), **facts}, indent=2
                ),
                encoding="utf-8",
            )
            print(f"Counts written to {args.write_counts}")
            return 0
    finally:
        probe.rollback()
        probe.close()
    if not args.dry_run and not args.restored_copy:
        parser.error("holding outbox events needs --restored-copy (or use --dry-run)")
    if not args.restore_point and args.backup_dir is None:
        parser.error("give --restore-point (or --backup-dir named by the backup's time)")
    try:
        point = parse_restore_point(args.restore_point or args.backup_dir.name)
    except ValueError as exc:
        parser.error(f"--restore-point: {exc}")
    source = json.loads(args.source_counts.read_text(encoding="utf-8")) if args.source_counts else None
    if source and source.get("database") == args.database and not args.dry_run:
        print(
            "Refused: the source counts were taken on this same database; is this the restored copy?", file=sys.stderr
        )
        return 1
    log_rows = None
    if args.erasure_log:
        with args.erasure_log.open(encoding="utf-8") as handle:
            log_rows = [json.loads(line) for line in handle if line.strip()]
    record = run(
        restore_point=point, backup_dir=args.backup_dir, source=source, erasure_log=log_rows, apply=not args.dry_run
    )
    written = write_record(record, args.out)
    for item in record["steps"]:
        print(f"{item['state']:5} {item['step']}: {item['summary']}")
    print(f"Result: {record['result']}")
    for path in written[:2]:
        print(f"Saved {path}")
    print(f"Saved {len(written) - 2} customer summary PDF(s) in {args.out}")
    return {"PASS": 0, "FAIL": 1}.get(record["result"], EXIT_FLAGS)


if __name__ == "__main__":
    raise SystemExit(main())
