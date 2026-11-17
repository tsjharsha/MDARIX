"""Add the rest of the sample story to free trials approved before it existed.

    python scripts/refresh_trial_story.py            # list what would be added, change nothing
    python scripts/refresh_trial_story.py --counts   # the same, counts only: trials numbered, no name or reference
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
(backend/app/trial/sample_imports.py) unless it is there, and the sample's first contacts, urgent intake and finished
triage record (backend/app/trial/sample_intake.py) unless they are there, and the sample's report worksheets (a
finished US example, an India complaint with a rejected attempt, and India in the sample's own reporting windows,
backend/app/trial/sample_reports.py) unless they are there, and the sample's own US guide version, a draft whose test
fails, and the communications log's examples (backend/app/trial/sample_guides.py; the open request is owned by the
trial's first user) unless they are there (a sample draft seeded before 0.10.64 takes the locked wording and MDARIX's
starter worked complaints, and its matrix is run again), and the sample author's absence with the trial's first user as backup and
the two events that user owns (backend/app/trial/sample_oversight.py) unless they are there, and the lot genealogy, the
three OrbitCare lots without complaints and the distribution with its import run for a case's Lot impact
(backend/app/trial/sample_lot_impact.py; lot 005 then releases 60 units and the new lots 30 each, made the same day, so
the trend's units in the field stay the same) unless they are there, and the sample products' device categories and
single-use fields and the sample lots' expiry dates (``SAMPLE_PRODUCT_FACTS``, 0.10.64) where they are not set, and
the flagship complaint SAMPLE-RV-11 and a calm day 0 (backend/app/trial/sample_calm.py: finished triage for what the
story does not need open, the sample's first-contact tasks due two working days ahead, RV-09 signed ready to close, the
absence to the trial's end) unless they are there (0.10.64), RV-09's ready to close signed again with its checklist
as it stood, the day after its US report was accepted (0.10.70: it was signed over an empty checklist), and today's wording on sample records written before
0.10.66 (backend/app/trial/sample_words.py: the RV-08 request named the US questions by code; a follow-up task's
title listed every question), and SAMPLE-RV-11's linked service work, in progress under its sample service ticket
(0.10.71, ``seed_flagship_service``) where it has none, and 0.10.72's corrections (backend/app/trial/sample_0_10_72.py:
SPO2_READING_HIGH's IMDRF Annex A term; the sample guide's example text, its approval re-recorded), and 0.10.73's
Free Trial plan, whose "up to 3 users" and licensed-user limit read the trial's safety cap (``refresh_plan``), and
0.10.75's reports: on the new navigation, the report of each US or India conclusion signed reportable before the
upgrade that has none (backend/app/trial/reports_0_10_75.py; the sample's own reports fit the status path as they are);
from 0.10.76 the same step covers EU / NI, Great Britain and Canada, so SAMPLE-RV-07's signed EU conclusion gets its
EU MIR worksheet, once, and 0.10.77's code corrections (backend/app/trial/sample_0_10_77.py: the sample's IMDRF links
re-recorded to IMDRF Release 2026's most specific terms; the code fields of the sample's frozen reports recorded as
confirmed by the sample author, with the values they were approved with), and 0.10.79's two new sample links
(backend/app/trial/sample_0_10_79.py: FLOW_ZERO_READING and SPO2_DROPOUT_HARM, which had none), and 0.10.96's
FDA-valid SAMPLE-RV-09 US report with its eMDR file (backend/app/trial/sample_0_10_96.py), and W1's SAMPLE-RV-07
signed Canada example where the sample answers predate it and the recorded AI proposals on SAMPLE-INV-001 where its
decision is not signed (backend/app/trial/sample_assessments.py, sample_ai.py), W5's simulated PLM, ERP and
eQMS source runs behind OrbitCare 300 (backend/app/trial/sample_sources.py; no record added), W1d's synthetic
follow-up of SAMPLE-CAPA-02 unless its check is signed (backend/app/trial/sample_follow_up.py), and 0.10.97's
reply to SAMPLE-RT-03's reporter in the communications log, so the customer-told check is met on day 0
(backend/app/trial/sample_0_10_97.py; the signed disposition is never edited), and, in every trial
with or without its sample, 0.10.81's deadline rules (backend/app/trial/open_deadlines.py: every market's starter
reporting windows; the open reports and draft assessments whose report type or due date the fixed rules change; the
signed conclusions they would change, listed for a person to sign again), and 0.10.93's SAMPLE-CASE-11 (the call
behind SAMPLE-RV-11, unsigned, for Getting started Part 1; backend/app/trial/sample_intake.py ``stage_story_case``)
unless it is there, and two PulseWatch shipments to its hospital, "Sample Lakeside Hospital (Sample)", so Log a case
offers that hospital's products and lots (ID-2; backend/app/trial/sample_lot_impact.py) unless they are there; the old SAMPLE-CALL-01..04 keep their references and are never escalated here. The sample's dates themselves are brought to today by the
hourly "trial-sample-clock" job (backend/app/trial/sample_clock.py) while nobody has worked on the sample. Each trial
is committed on its own, with an audit event.
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
    from backend.app.db.models.foundation import LotBatch, Product, ProductVersion
    from sqlalchemy import or_
    from backend.app.signals.hooks import seed_demo_signals
    from backend.app.trial import open_deadlines, reports_0_10_75, sample_0_10_72, sample_0_10_77, sample_0_10_79
    from backend.app.trial import sample_0_10_96, sample_0_10_97
    from backend.app.trial import sample_supply
    from backend.app.trial.sample_calm import has_calm_story, rerecord_rv09, stage_calm_story
    from backend.app.trial.sample_clock import _absence_to_trial_end
    from backend.app.trial.sample_data import (
        FLAGSHIP,
        SAMPLE_PRODUCT_FACTS,
        SAMPLE_SOURCE,
        has_sample_data,
        has_story_examples,
        seed_flagship,
        seed_flagship_service,
        seed_lot_quantities,
        seed_product_facts,
        seed_story_examples,
    )
    from backend.app.db.models.foundation import Complaint
    from backend.app.trial.sample_assessments import (
        has_canada_example,
        has_sample_assessments,
        stage_canada_example,
        stage_sample_assessments,
    )
    from backend.app.trial.sample_decision import has_sample_decision, stage_sample_decision
    from backend.app.trial.sample_dispositions import has_routine_examples, seed_routine_examples
    from backend.app.trial.sample_imports import has_sample_import, stage_sample_import
    from backend.app.trial.sample_intake import has_sample_intake, has_story_case, stage_sample_intake, stage_story_case
    from backend.app.trial.sample_guides import has_sample_guides, relock_sample_drafts, stage_sample_guides
    from backend.app.trial.sample_oversight import has_sample_oversight, stage_sample_oversight
    from backend.app.trial.sample_lot_impact import (
        has_lakeside_shipments,
        has_sample_lot_impact,
        stage_lakeside_shipments,
        stage_sample_lot_impact,
    )
    from backend.app.trial.sample_ai import stage_sample_ai
    from backend.app.trial.sample_sources import has_sample_sources, stage_sample_sources
    from backend.app.trial import sample_follow_up
    from backend.app.trial.sample_reports import has_sample_reports, stage_sample_reports
    from backend.app.trial.sample_words import reword_sample

    results = []
    for tenant_id, tenant_key, name in trials(db):
        with Session(bind=db.get_bind(), autoflush=False) as session:
            bind_tenant(session, tenant_id)
            # 0.10.81: every trial, sample or not (backend/app/trial/open_deadlines.py).
            fixes = open_deadlines.refresh(session, tenant_id, apply)
            if fixes:
                results.append(
                    {"tenant": tenant_key, "name": name, "result": "; ".join(fixes), "deadlines": len(fixes)}
                )
                if apply:
                    session.commit()
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
            intake_missing = not has_sample_intake(session, tenant_id)
            reports_missing = not has_sample_reports(session, tenant_id)
            guides_missing = not has_sample_guides(session, tenant_id)
            guides_unlocked = relock_sample_drafts(session, tenant_id, apply=False)
            oversight_missing = not has_sample_oversight(session, tenant_id)
            lot_impact_missing = not has_sample_lot_impact(session, tenant_id)
            facts_missing = (
                session.query(Product.id)
                .filter(
                    Product.tenant_id == tenant_id,
                    Product.source_system == SAMPLE_SOURCE,
                    Product.product_identifier.in_(list(SAMPLE_PRODUCT_FACTS)),
                    or_(Product.device_category.is_(None), Product.single_use.is_(None)),
                )
                .count()
                + session.query(LotBatch.id)
                .join(ProductVersion, ProductVersion.id == LotBatch.product_version_id)
                .join(Product, Product.id == ProductVersion.product_id)
                .filter(
                    LotBatch.tenant_id == tenant_id,
                    LotBatch.source_system == SAMPLE_SOURCE,
                    LotBatch.expiry_date.is_(None),
                    Product.product_identifier.in_(
                        [code for code, facts in SAMPLE_PRODUCT_FACTS.items() if facts.get("shelf_life_days")]
                    ),
                )
                .count()
            )
            flagship_missing = (
                session.query(Complaint.id)
                .filter(Complaint.tenant_id == tenant_id, Complaint.complaint_identifier == FLAGSHIP)
                .first()
                is None
            )
            calm_missing = not has_calm_story(session, tenant_id)
            # 0.10.93: SAMPLE-CASE-11, the call behind the flagship (Getting started Part 1).
            story_case_missing = not has_story_case(session, tenant_id)
            # 0.10.93 (ID-2): SAMPLE-CASE-11's hospital's shipments, so Log a case offers its products and lots.
            lakeside_missing = not has_lakeside_shipments(session, tenant_id)
            old_words = reword_sample(session, tenant_id, apply=False)
            # RV-09 signed ready to close over an empty checklist before 0.10.70 (sample_calm.py).
            rv09_unrecorded = not calm_missing and rerecord_rv09(session, tenant_id, apply=False)
            # SAMPLE-RV-11's linked service work (0.10.71, A5).
            service_missing = not flagship_missing and seed_flagship_service(session, tenant_id, apply=False)
            # 0.10.72: SPO2_READING_HIGH's IMDRF term and the sample guide's example text.
            corrections = sample_0_10_72.refresh(session, tenant_id, apply=False)
            # 0.10.75: on the new navigation, the report of a reportable conclusion signed before the upgrade.
            reports_owed = reports_0_10_75.refresh(session, tenant_id, apply=False)
            # 0.10.77: the sample's IMDRF links (Release 2026) and its frozen reports' confirmed codes.
            codes_owed = sample_0_10_77.refresh(session, tenant_id, apply=False)
            # 0.10.79: the two sample problem codes that had no IMDRF link.
            links_owed = sample_0_10_79.refresh(session, tenant_id, apply=False)
            # 0.10.96 (B3 A9): SAMPLE-RV-09's US report FDA-valid, its approved snapshot with its eMDR file.
            emdr_owed = sample_0_10_96.refresh(session, tenant_id, apply=False)
            # 0.10.97 (B7-D5): SAMPLE-RT-03's customer told, as a reply in the communications log.
            told_owed = sample_0_10_97.refresh(session, tenant_id, apply=False)
            # 0.10.94 (W1): Rev A configurations and the evidence linked to NovaSense (Product 360, Supplier 360).
            supply_owed = sample_supply.refresh(session, tenant_id, apply=False, now=datetime.now(timezone.utc))
            # W1 (review B, G6): the signed Canada example on SAMPLE-RV-07, for sample answers staged before it.
            canada_missing = not assessments_missing and not has_canada_example(session, tenant_id)
            # W1: the sample's recorded AI proposals on SAMPLE-INV-001, unless its decision is signed already.
            ai_missing = sample_ai_owed(session, tenant_id)
            # W5: the simulated PLM, ERP and eQMS runs behind OrbitCare 300's records (no record added).
            sources_missing = not has_sample_sources(session, tenant_id)
            # W1d (D04): SAMPLE-CAPA-02's synthetic follow-up, unless its effectiveness check is signed already.
            follow_up_owed = sample_follow_up.refresh(session, tenant_id, apply=False)
            if not (
                story_missing
                or flagship_missing
                or calm_missing
                or lots_missing
                or decision_missing
                or assessments_missing
                or routine_missing
                or import_missing
                or intake_missing
                or reports_missing
                or guides_missing
                or guides_unlocked
                or oversight_missing
                or lot_impact_missing
                or facts_missing
                or old_words
                or rv09_unrecorded
                or service_missing
                or corrections
                or reports_owed
                or codes_owed
                or links_owed
                or emdr_owed
                or told_owed
                or story_case_missing
                or supply_owed
                or lakeside_missing
                or canada_missing
                or ai_missing
                or sources_missing
                or follow_up_owed
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
                    *(["the sample first contacts and urgent intake"] if intake_missing else []),
                    *(["the sample report worksheets"] if reports_missing else []),
                    *(["the sample guide versions and communications log"] if guides_missing else []),
                    *(["the locked wording and starter matrix in the sample guide draft"] if guides_unlocked else []),
                    *(["the sample absence and event owners"] if oversight_missing else []),
                    *(["the sample lot genealogy and distribution"] if lot_impact_missing else []),
                    *(["the sample products' device categories and lot expiry dates"] if facts_missing else []),
                    *(["the flagship complaint SAMPLE-RV-11"] if flagship_missing else []),
                    *(
                        ["a calm day 0 (finished triage, tasks due later, RV-09 ready to close)"]
                        if calm_missing
                        else []
                    ),
                    *([f"today's wording on {old_words} sample records (0.10.66)"] if old_words else []),
                    *(["RV-09's ready to close with its checklist as it stood (0.10.70)"] if rv09_unrecorded else []),
                    *(["SAMPLE-RV-11's service work, in progress (0.10.71)"] if service_missing else []),
                    *(
                        [f"{corrections} sample corrections (0.10.72: an IMDRF term, the guide's example text)"]
                        if corrections
                        else []
                    ),
                    *(
                        [f"{reports_owed} authority reports of conclusions signed reportable (0.10.75)"]
                        if reports_owed
                        else []
                    ),
                    *(
                        [f"{codes_owed} sample code corrections (0.10.77: IMDRF Release 2026 links, confirmed codes)"]
                        if codes_owed
                        else []
                    ),
                    *([f"{links_owed} sample IMDRF links (0.10.79)"] if links_owed else []),
                    *(["SAMPLE-RV-09's US report with its eMDR file (0.10.96)"] if emdr_owed else []),
                    *(["SAMPLE-RT-03's reply to its reporter (0.10.97)"] if told_owed else []),
                    *(
                        ["SAMPLE-CASE-11, the call behind SAMPLE-RV-11, unsigned (0.10.93)"]
                        if story_case_missing
                        else []
                    ),
                    *([f"{supply_owed} sample supply-chain rows (0.10.94)"] if supply_owed else []),
                    *(["the shipments to SAMPLE-CASE-11's hospital (0.10.93)"] if lakeside_missing else []),
                    *(["SAMPLE-RV-07's signed Canada example (W1)"] if canada_missing else []),
                    *(["the recorded AI proposals on SAMPLE-INV-001 (W1)"] if ai_missing else []),
                    *(["the simulated sources (W5)"] if sources_missing else []),
                    *(["SAMPLE-CAPA-02's synthetic follow-up (W1d)"] if follow_up_owed else []),
                ]
                results.append(
                    {
                        "tenant": tenant_key,
                        "name": name,
                        "result": f"would add {' and '.join(wanted)}",
                        "sample": wanted,
                    }
                )
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
            if intake_missing:
                added["intake"] = stage_sample_intake(session, tenant_id, now)
            if reports_missing:
                added["reports"] = stage_sample_reports(session, tenant_id, now)
            if guides_missing:
                added["guides"] = stage_sample_guides(session, tenant_id, now)
            if guides_unlocked:
                added["guide_drafts_relocked"] = relock_sample_drafts(session, tenant_id, apply=True)
            if oversight_missing:
                added["oversight"] = stage_sample_oversight(session, tenant_id, now)
            if lot_impact_missing:
                # After the quantities: lot 005's units are shared with the three new lots.
                added["lot_impact"] = stage_sample_lot_impact(session, tenant_id, now)
            if lakeside_missing:
                # After the distribution (a trial staged with 0.10.93's sample already has them: nothing added).
                added["lakeside_shipments"] = stage_lakeside_shipments(session, tenant_id, now)
            # Last: every sample lot exists by now.
            added["product_facts"] = seed_product_facts(session, tenant_id)
            if flagship_missing and not story_missing:
                added["flagship"] = seed_flagship(session, tenant_id, now)
            if story_case_missing:
                # After the flagship (it copies RV-11's facts), before the calm day 0 (which leaves its triage open).
                added["story_case"] = stage_story_case(session, tenant_id)
            if calm_missing:
                # After the flagship and the intake: it finishes the triage the story does not need open.
                added["calm"] = stage_calm_story(session, tenant_id, now)
                _absence_to_trial_end(session, tenant_id)
            if old_words:
                added["reworded"] = reword_sample(session, tenant_id, apply=True)
            if rv09_unrecorded:
                added["rv09_rerecorded"] = rerecord_rv09(session, tenant_id, apply=True, now=now)
            if service_missing:
                added["flagship_service"] = seed_flagship_service(session, tenant_id, apply=True)
            if corrections:
                added["corrections_0_10_72"] = sample_0_10_72.refresh(session, tenant_id, apply=True, now=now)
            if reports_owed:
                added["reports_0_10_75"] = reports_0_10_75.refresh(session, tenant_id, apply=True, now=now)
            if codes_owed:
                # After the reports: a report the step above creates is a draft, never frozen.
                added["codes_0_10_77"] = sample_0_10_77.refresh(session, tenant_id, apply=True, now=now)
            if links_owed:
                added["links_0_10_79"] = sample_0_10_79.refresh(session, tenant_id, apply=True, now=now)
            if emdr_owed:
                # After 0.10.77's codes and 0.10.79's links: RV-09's problem code is confirmed from the newest link.
                added["emdr_0_10_96"] = sample_0_10_96.refresh(session, tenant_id, apply=True, now=now)
            if told_owed:
                added["told_0_10_97"] = sample_0_10_97.refresh(session, tenant_id, apply=True, now=now)
            if supply_owed:
                # After the lot genealogy above, as in a new trial (sample_clock.seed_sample).
                added["supply_0_10_94"] = sample_supply.refresh(session, tenant_id, apply=True, now=now)
            if canada_missing:
                added["canada_example"] = stage_canada_example(session, tenant_id, now)
            if ai_missing:
                added["sample_ai"] = stage_sample_ai(session, tenant_id, now)
            if sources_missing:
                # After the lot genealogy and the supply chain: the runs read them (sample_sources.py).
                added["sources"] = stage_sample_sources(session, tenant_id, now)
            if follow_up_owed:
                added["follow_up"] = sample_follow_up.refresh(session, tenant_id, apply=True, now=now)
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


def sample_ai_owed(db: Session, tenant_id) -> bool:
    """W1: SAMPLE-INV-001 is there with no recorded AI proposal and no signed decision (a decided case keeps the story
    it was decided on)."""
    from backend.app.db.models.foundation import Decision
    from backend.app.trial.flagship import find_case
    from backend.app.trial.sample_ai import has_sample_ai

    case = find_case(db, tenant_id)
    if case is None or has_sample_ai(db, tenant_id):
        return False
    return (
        db.query(Decision.id)
        .filter(
            Decision.tenant_id == tenant_id, Decision.investigation_id == case.id, Decision.decision_status == "SIGNED"
        )
        .first()
        is None
    )


def refresh_plan(db: Session, apply: bool) -> list[str]:
    """0.10.73: the Free Trial plan's "up to 3 users" and its licensed-user limit of 3 read the trial's safety cap
    (MDARIX_TRIAL_USER_CAP, default 50). Idempotent; committed with ``apply``."""
    from backend.app.db.tenant_scope import bind_system
    from backend.app.trial.service import refresh_plan_limits

    bind_system(db, "refresh the free trial plan's user cap")
    changes = refresh_plan_limits(db, apply)
    if apply and changes:
        db.commit()
    return changes


def count_lines(results: list[dict]) -> list[str]:
    """``--counts``: each trial by its number in the list, never its key or name; the deadline changes (they name
    the trial's own complaints) as a count; the sample items by name (the sample is synthetic). Pure."""
    numbers: dict[str, int] = {}
    for item in results:
        numbers.setdefault(item["tenant"], len(numbers) + 1)
    lines = []
    for item in results:
        label = f"Trial {numbers[item['tenant']]} of {len(numbers)}:"
        if "deadlines" in item:
            lines.append(f"{label} {item['deadlines']} deadline-rule change(s) to the trial's own records (0.10.81)")
        elif "sample" in item:
            lines.append(f"{label} would add {len(item['sample'])} sample item(s): {'; '.join(item['sample'])}")
        else:
            lines.append(f"{label} {item['result']}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="add the story (without it, only list what would change)")
    parser.add_argument("--counts", action="store_true", help="list only, counts only: no trial name or reference")
    args = parser.parse_args(argv)
    if args.apply and args.counts:
        parser.error("--counts lists only; it cannot be used with --apply")
    db = SessionLocal()
    try:
        plan = refresh_plan(db, args.apply)
        results = refresh(db, args.apply)
    finally:
        db.close()
    print(
        f"Free Trial plan: {'changed' if args.apply else 'would change'} {'; '.join(plan)}"
        if plan
        else "Free Trial plan: already reads the user cap"
    )
    if args.counts:
        for line in count_lines(results):
            print(line)
    else:
        for item in results:
            print(f"{item['tenant']:<40} {item['name'][:40]:<40} {item['result']}")
    if not results:
        print("No free trial holds data.")
    elif not args.apply:
        print("\nNothing was changed. Run again with --apply to add the story.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
