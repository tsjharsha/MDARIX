"""Add the rest of the sample story to free trials approved before it existed.

    python scripts/refresh_trial_story.py            # list what would be added, change nothing
    python scripts/refresh_trial_story.py --apply    # add it

New trials get the whole story at approval (backend/app/trial/sample_data.py). A trial approved earlier holds the
sample products, complaints and the guided investigation, but not the hidden complaints, reporting clocks, CAPAs, risk
register and sample reporting windows that Complaints, Records and Readiness show, nor the units per sample lot the
trend check counts by (md43), and its signals wait for the scheduler. This adds exactly those sample records (marked
MDARIX_SAMPLE) and quantities, once, to every trial that still holds its sample data, then runs signal detection; a
trial's own records and its own reporting windows are never changed. The guided investigation also gets its
sample Decision Brief, written by the sample author and waiting for quality review (backend/app/trial/sample_decision.py),
unless the case already has a brief, and the per-market assessment's sample answers (a signed EU/NI example, a pending
US draft and the harm complaints' severities, backend/app/trial/sample_assessments.py) unless they are there, and
the routine complaints with their proposed classifications and a signed service-level example
(backend/app/trial/sample_dispositions.py) unless they are there, and the sample's import run with its
data-quality report, set-aside rows, the products' UDI-DI and GMDN and the IMDRF links of its problem codes
(backend/app/trial/sample_imports.py) unless it is there. Each trial is committed on its own, with an audit event.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session  # noqa: E402

from backend.app.db.session import SessionLocal  # noqa: E402


def trials(db: Session) -> list[tuple]:
    """(tenant id, tenant key, name) of every Free Trial still holding data, on the shared plane."""
    from backend.app.db.data_plane import TRIAL_SHARED_DATA_PLANE
    from backend.app.db.models.customer_lifecycle import TenantDataPlane
    from backend.app.db.models.foundation import PlanDefinition, Tenant
    from backend.app.db.models.stage2 import SubscriptionLifecycle
    from backend.app.db.tenant_scope import bind_system
    from backend.app.trial.service import FREE_TRIAL_PLAN

    bind_system(db, "refresh the free trials' sample story")
    rows = (
        db.query(Tenant.id, Tenant.tenant_key, Tenant.name)
        .join(SubscriptionLifecycle, SubscriptionLifecycle.tenant_id == Tenant.id)
        .join(PlanDefinition, PlanDefinition.id == SubscriptionLifecycle.plan_id)
        .join(TenantDataPlane, TenantDataPlane.tenant_id == Tenant.id)
        .filter(
            PlanDefinition.code == FREE_TRIAL_PLAN,
            TenantDataPlane.connection_secret_ref == TRIAL_SHARED_DATA_PLANE,
            Tenant.status != "ARCHIVED",
        )
        .order_by(Tenant.tenant_key)
        .all()
    )
    return [tuple(row) for row in rows]


def refresh(db: Session, apply: bool) -> list[dict]:
    from backend.app.db.tenant_scope import bind_tenant
    from backend.app.enterprise_audit import make_audit_event
    from backend.app.db.models.foundation import LotBatch
    from backend.app.signals.hooks import seed_demo_signals
    from backend.app.trial.sample_data import (
        SAMPLE_SOURCE,
        has_sample_data,
        has_story_examples,
        seed_lot_quantities,
        seed_story_examples,
    )
    from backend.app.trial.sample_assessments import has_sample_assessments, stage_sample_assessments
    from backend.app.trial.sample_decision import has_sample_decision, stage_sample_decision
    from backend.app.trial.sample_dispositions import has_routine_examples, seed_routine_examples
    from backend.app.trial.sample_imports import has_sample_import, stage_sample_import

    results = []
    for tenant_id, tenant_key, name in trials(db):
        with Session(bind=db.get_bind(), autoflush=False) as session:
            bind_tenant(session, tenant_id)
            if not has_sample_data(session, tenant_id):
                results.append({"tenant": tenant_key, "name": name, "result": "no sample data (left as it is)"})
                continue
            story_missing = not has_story_examples(session, tenant_id)
            lots_missing = (
                session.query(LotBatch.id)
                .filter(
                    LotBatch.tenant_id == tenant_id,
                    LotBatch.source_system == SAMPLE_SOURCE,
                    LotBatch.quantity.is_(None),
                )
                .count()
            )
            decision_missing = not has_sample_decision(session, tenant_id)
            assessments_missing = not has_sample_assessments(session, tenant_id)
            routine_missing = not has_routine_examples(session, tenant_id)
            import_missing = not has_sample_import(session, tenant_id)
            if not (
                story_missing
                or lots_missing
                or decision_missing
                or assessments_missing
                or routine_missing
                or import_missing
            ):
                results.append({"tenant": tenant_key, "name": name, "result": "already has the story"})
                continue
            if not apply:
                wanted = [
                    *(["the story"] if story_missing else []),
                    *([f"quantities for {lots_missing} sample lots"] if lots_missing else []),
                    *(["the sample decision brief"] if decision_missing else []),
                    *(["the sample market assessments"] if assessments_missing else []),
                    *(["the routine sample complaints"] if routine_missing else []),
                    *(["the sample import run"] if import_missing else []),
                ]
                results.append({"tenant": tenant_key, "name": name, "result": f"would add {' and '.join(wanted)}"})
                continue
            now = datetime.now(timezone.utc)
            added = seed_story_examples(session, tenant_id, now) if story_missing else {"created": False}
            added["lot_quantities"] = seed_lot_quantities(session, tenant_id)
            if decision_missing:
                added["decision"] = stage_sample_decision(session, tenant_id, now)
            if assessments_missing:
                added["assessments"] = stage_sample_assessments(session, tenant_id, now)
            if routine_missing:
                added["routine"] = seed_routine_examples(session, tenant_id, now)
            if import_missing:
                # Last: the run's lineage covers every sample complaint, the routine ones included.
                added["imports"] = stage_sample_import(session, tenant_id, now)
            session.add(
                make_audit_event(
                    tenant_id=tenant_id,
                    actor_ref="system:trial-sample",
                    action="TRIAL_SAMPLE_STORY_ADDED",
                    entity_type="Tenant",
                    entity_id=tenant_id,
                    details={key: value for key, value in added.items() if key != "created"},
                    created_at=now,
                )
            )
            session.commit()
            # The sample's signals now, rather than at the scheduler's next run (logged, never fatal).
            seed_demo_signals(session, tenant_id)
            results.append({"tenant": tenant_key, "name": name, "result": f"added {added}"})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="add the story (without it, only list what would change)")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        results = refresh(db, args.apply)
    finally:
        db.close()
    for item in results:
        print(f"{item['tenant']:<40} {item['name'][:40]:<40} {item['result']}")
    if not results:
        print("No free trial holds data.")
    elif not args.apply:
        print("\nNothing was changed. Run again with --apply to add the story.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
