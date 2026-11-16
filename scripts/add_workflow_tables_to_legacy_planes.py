"""Give legacy dedicated organization databases the workflow changes of migrations md27 (roles, tasks), md28
(signals), md29 (case scope and evidence review), md30 (intelligence judgements), md31 (intelligence values), md32 (reviews and the Decision Brief), md33 (the human decision), md40 (complaint review), md41 (reporting and CAPA), md42 (the case AI run), md43 (units per lot), md44 (email preferences, trial demo requests), tr01 (per-market assessments,
complaint classifications, signer training), tr02 (complaint dispositions, the decision's root-cause attribution)
tr04 to tr08 (the trial line's intake, reports, guides, oversight and lot impact tables) and tr09 (a CAPA's QMS
reference, a lot's expiry date, a product's device category and a complaint's other lots), tr10 (a set-aside import
row dismissed with a reason), tr11 (each organization's navigation, classic or new) and tr12 (a sample-only trial,
a complaint's linked service work) tr13 (each person's workspace persona), tr14 (a cancelled authority report), tr15 (a Canada assessment), tr16 (a product's Basic UDI-DI and EMDN code, a
registration's risk class, a responsible party's SRN), tr18 (a re-signed market conclusion's change reason),
tr19 (Cases, escalation to a Complaint, triage at two speeds), the DB-1 database hardening: tr21 (the runtime role
only reads the schema stamp and the business-ID counters), tr22 + tr23 (the pre-check, then references between
organization tables that include the organization, a version always a version of its product), tr24 (indexes on the
organization filter and references, built inside the transaction) and tr24a (a Case's lot and the product of
decisions, briefs, assurance results and AI interactions; a case context's version needs its product; the tr22 and
tr24a pre-checks refuse a database with rows that break a rule, with the counts, and nothing is changed there),
and tr25 (the routine path, Case attachments,
e-mail intake) and tr26 (a hypothesis's drafting rule, a follow-up's field action or product change) and tr27 (the
reportability floor a market conclusion used) and tr28 (reporting roles per market, the user facility
profile) and tr31 (a country outside the five markets) and trrcatools (root-cause methods, the confirmed cause at
signing, section comments, the per-risk harm estimate).

    python scripts/add_workflow_tables_to_legacy_planes.py            # dry run: what would change
    python scripts/add_workflow_tables_to_legacy_planes.py --apply    # change them

A dedicated database built before migrations managed planes (scripts/migrate_data_planes.py reports it as LEGACY)
cannot be upgraded with Alembic, so it would lack the tables the application now writes when a case is opened, a
decision recorded or a signal detected. This runs each migration's own table function (the same steps, so the result
is identical) on each such database that does not have those tables yet, in order and in one transaction per
database. It needs md26's business identifiers there first (scripts/add_business_ids_to_legacy_planes.py). Databases
managed by migrations are left to scripts/migrate_data_planes.py.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from alembic.operations import Operations  # noqa: E402
from alembic.runtime.migration import MigrationContext  # noqa: E402
from sqlalchemy import create_engine, inspect, text  # noqa: E402

from backend.app.db.data_plane import SHARED_CONTROL_DATA_PLANE, _secret_url  # noqa: E402
from backend.app.db.models.customer_lifecycle import TenantDataPlane  # noqa: E402
from backend.app.db.session import SessionLocal  # noqa: E402
from backend.app.db.tenant_scope import bind_system  # noqa: E402
from backend.app.db.tls import connect_args  # noqa: E402
from infrastructure.database.migrations import product_references, tenant_references, tenant_indexes  # noqa: E402

VERSIONS = ROOT / "infrastructure" / "database" / "migrations" / "versions"


@dataclass(frozen=True)
class Step:
    name: str
    module_file: str
    function: str
    tables: tuple[str, ...]
    required: tuple[str, ...]
    # For a step that creates no table: SQL answering "is this step already applied?" (true/false).
    done_sql: str | None = None


def _has_constraint(name: str) -> str:
    return f"SELECT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{name}')"


# tr21 is in place when the runtime role (if any) cannot insert business-ID counters and the plane registry (if the
# database has one and system scope) has its policies.
_TR21_DONE = (
    "SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdarix_runtime') "
    "OR to_regclass('public.business_id_counters') IS NULL THEN true "
    "ELSE NOT has_table_privilege('mdarix_runtime', 'public.business_id_counters', 'INSERT') END "
    "AND (to_regproc('public.mdarix_system_scope') IS NULL OR to_regclass('public.tenant_data_planes') IS NULL "
    "OR EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND policyname = 'mdarix_plane_read'))"
)
_TR23_TABLES = tuple(
    sorted(
        {ref.child for ref in tenant_references.REFERENCES}
        | {ref.parent for ref in tenant_references.REFERENCES}
        | set(tenant_references.PRODUCT_VERSION_TABLES)
        | {"product_versions"}
    )
)

# In migration order: a later step may reference an earlier step's tables.
STEPS = (
    Step(
        "md27",
        "md27_workflow_foundation.py",
        "create_workflow_tables",
        ("user_additional_roles", "workflow_tasks", "workflow_task_events"),
        ("tenants", "auth_users", "investigations", "business_id_counters"),
    ),
    Step(
        "md28",
        "md28_signals.py",
        "create_signal_tables",
        ("signals", "signal_complaints", "signal_events", "investigation_signals", "signal_rules"),
        ("tenants", "products", "product_versions", "complaints", "investigations", "business_id_counters"),
    ),
    Step(
        "md29",
        "md29_case_scope_evidence.py",
        "apply_case_scope_changes",
        ("investigation_scope_versions", "evidence_review_events"),
        (
            "investigations",
            "investigation_complaints",
            "complaints",
            "investigation_evidence",
            "evidence",
            "supplier_evidence_requests",
        ),
    ),
    Step(
        "md30",
        "md30_intelligence.py",
        "apply_intelligence_changes",
        ("intelligence_events",),
        ("investigations", "hypotheses", "hypothesis_evidence", "unknowns", "failure_chains", "evidence_observations"),
    ),
    Step(
        "md31",
        "md31_intelligence_values.py",
        "widen_intelligence_values",
        (),
        ("hypothesis_evidence", "failure_chain_edges", "evidence_observations"),
        done_sql=(
            "SELECT coalesce(bool_or(pg_get_constraintdef(oid) LIKE '%contextual%'), false) FROM pg_constraint "
            "WHERE conname = 'ck_hypothesis_evidence_hypothesis_evidence_relation_allowed'"
        ),
    ),
    Step(
        "md32",
        "md32_reviews_and_brief.py",
        "create_review_tables",
        ("case_reviews", "decision_brief_versions", "brief_review_actions"),
        ("tenants", "investigations", "business_id_counters"),
    ),
    Step(
        "md33",
        "md33_human_decision.py",
        "apply_decision_changes",
        ("decision_follow_ups", "impact_assessments"),
        ("tenants", "investigations", "decisions", "business_id_counters"),
    ),
    Step(
        "md40",
        "md40_complaint_review.py",
        "create_complaint_review_tables",
        ("complaint_settings", "complaint_second_looks"),
        ("tenants", "complaints"),
    ),
    Step(
        "md41",
        "md41_reporting_and_capa.py",
        "create_reporting_and_capa_tables",
        ("reportability_settings", "complaint_reportability", "capa_effectiveness_checks"),
        ("tenants", "complaints", "capas"),
    ),
    Step(
        "md42",
        "md42_case_ai_run.py",
        "create_case_ai_run_table",
        ("case_ai_runs",),
        ("tenants", "investigations"),
    ),
    Step(
        "md43",
        "md43_lot_quantity.py",
        "add_lot_quantity",
        (),
        ("lot_batches",),
        done_sql=(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' "
            "AND table_name = 'lot_batches' AND column_name = 'quantity')"
        ),
    ),
    Step(
        "md44",
        "md44_digest_and_demo_requests.py",
        "add_digest_and_demo_columns",
        (),
        ("auth_users", "demo_requests"),
        done_sql=(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' "
            "AND table_name = 'demo_requests' AND column_name = 'trial_tenant_id')"
        ),
    ),
    Step(
        "tr01",
        "tr01_trial_market_assessments.py",
        "create_market_assessment_tables",
        ("complaint_market_assessments", "complaint_classifications", "signer_training_records"),
        ("tenants", "complaints"),
    ),
    Step(
        "tr02",
        "tr02_trial_complaint_dispositions.py",
        "create_disposition_tables",
        ("complaint_dispositions",),
        ("tenants", "complaints", "decisions"),
    ),
    Step(
        "tr04",
        "tr04_trial_intake_triage.py",
        "create_intake_tables",
        ("intake_events", "first_contact_checks", "triage_records", "record_links", "record_field_changes"),
        ("tenants", "products"),
    ),
    Step(
        "tr05",
        "tr05_trial_authority_reports.py",
        "create_report_tables",
        ("report_obligations", "report_snapshots", "report_submissions", "report_evidence"),
        ("tenants", "complaints", "complaint_market_assessments"),
    ),
    Step(
        "tr06",
        "tr06_trial_guides_communications.py",
        "create_guide_communication_tables",
        ("decision_guide_versions", "external_parties", "communication_entries", "communication_settings"),
        ("tenants", "complaints"),
    ),
    Step(
        "tr07",
        "tr07_trial_oversight.py",
        "create_oversight_tables",
        ("oversight_settings", "user_absences", "due_alerts", "event_closures"),
        ("tenants", "complaints"),
    ),
    Step(
        "tr08",
        "tr08_trial_lot_impact.py",
        "create_lot_impact_tables",
        ("lot_distributions",),
        ("tenants", "lot_batches", "investigation_scope_versions"),
    ),
    Step(
        "tr09",
        "tr09_trial_record_facts.py",
        "add_record_facts",
        (),
        ("capas", "lot_batches", "products", "complaints"),
        done_sql=(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' "
            "AND table_name = 'capas' AND column_name = 'qms_reference')"
        ),
    ),
    Step(
        "tr10",
        "tr10_trial_set_aside_dismissed.py",
        "allow_dismissed_rows",
        (),
        ("import_quarantine_rows",),
        done_sql=(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' "
            "AND table_name = 'import_quarantine_rows' AND column_name = 'resolution_note')"
        ),
    ),
    Step(
        "tr11",
        "tr11_trial_navigation.py",
        "add_navigation",
        (),
        ("tenants",),
        done_sql=(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' "
            "AND table_name = 'tenants' AND column_name = 'navigation')"
        ),
    ),
    Step(
        "tr12",
        "tr12_trial_sample_only_service.py",
        "add_sample_only_and_service",
        (),
        ("tenants", "complaints"),
        done_sql=(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' "
            "AND table_name = 'complaints' AND column_name = 'service_status')"
        ),
    ),
    Step(
        "tr13",
        "tr13_trial_view_persona.py",
        "add_view_persona",
        (),
        ("auth_users",),
        done_sql=(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' "
            "AND table_name = 'auth_users' AND column_name = 'view_persona')"
        ),
    ),
    Step(
        "tr14",
        "tr14_trial_report_cancelled.py",
        "allow_cancelled_reports",
        (),
        ("report_obligations",),
        done_sql=(
            "SELECT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_report_obligations_state_known' "
            "AND pg_get_constraintdef(oid) LIKE '%CANCELLED%')"
        ),
    ),
    Step(
        "tr15",
        "tr15_trial_canada_market.py",
        "allow_canada_assessments",
        (),
        ("complaint_market_assessments",),
        done_sql=(
            "SELECT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_complaint_market_assessments_market_known' "
            "AND pg_get_constraintdef(oid) LIKE '%''CA''%')"
        ),
    ),
    Step(
        "tr16",
        "tr16_trial_code_lists.py",
        "add_identity_columns",
        (),
        ("products", "product_registrations", "market_responsible_parties"),
        done_sql=(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' "
            "AND table_name = 'market_responsible_parties' AND column_name = 'srn')"
        ),
    ),
    Step(
        "tr18",
        "tr18_trial_conclusion_change_reason.py",
        "add_change_reason",
        (),
        ("complaint_market_assessments",),
        done_sql=(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' "
            "AND table_name = 'complaint_market_assessments' AND column_name = 'change_reason')"
        ),
    ),
    Step(
        "tr19",
        "tr19_trial_cases_escalation.py",
        "add_cases_escalation",
        ("triage_record_versions", "case_addenda", "record_ownership"),
        (
            "intake_events",
            "first_contact_checks",
            "triage_records",
            "complaints",
            "external_parties",
            "oversight_settings",
            "due_alerts",
        ),
    ),
    # DB-1 (owner decision 6, 14 Nov 2026): the database hardening, before any dedicated customer goes live.
    Step(
        "tr21",
        "tr21_runtime_privileges.py",
        "restrict_runtime_writes",
        (),
        (),
        done_sql=_TR21_DONE,
    ),
    Step(
        "tr22+tr23",
        "tr23_composite_tenant_fks.py",
        "apply_to_legacy_plane",
        (),
        _TR23_TABLES,
        done_sql=_has_constraint(tenant_references.version_check_name(tenant_references.PRODUCT_VERSION_TABLES[-1])),
    ),
    Step(
        "tr24",
        "tr24_tenant_indexes.py",
        "create_tenant_indexes",
        (),
        tuple(sorted({table for _name, table, _columns in tenant_indexes.INDEXES})),
        done_sql=f"SELECT to_regclass('public.{tenant_indexes.INDEXES[-1][0]}') IS NOT NULL",
    ),
    Step(
        "tr24a",
        "tr24a_product_references.py",
        "apply_to_legacy_plane",
        (),
        tuple(product_references.tables_read()),
        done_sql=_has_constraint(product_references.REFERENCES[-1].name),
    ),
    Step(
        "tr25",
        "tr25_trial_routine_path.py",
        "add_routine_path",
        ("inbound_messages", "case_attachments"),
        ("intake_events", "case_addenda", "event_closures", "oversight_settings"),
    ),
    Step(
        "tr26",
        "tr26_trial_challenge_loop.py",
        "add_challenge_loop",
        (),
        ("hypotheses", "decision_follow_ups"),
        done_sql=(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' "
            "AND table_name = 'decision_follow_ups' AND column_name = 'action_scope')"
        ),
    ),
    Step(
        "tr27",
        "tr27_trial_rule_register.py",
        "add_rule_register",
        (),
        ("complaint_market_assessments",),
        done_sql=(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' "
            "AND table_name = 'complaint_market_assessments' AND column_name = 'date_calc')"
        ),
    ),
    Step(
        "tr28",
        "tr28_trial_market_roles.py",
        "add_market_roles",
        (),
        ("reportability_settings", "market_responsible_parties"),
        done_sql=(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' "
            "AND table_name = 'reportability_settings' AND column_name = 'reporting_roles')"
        ),
    ),
    Step(
        "tr29",
        "tr29_trial_party_parts.py",
        "add_party_parts",
        (),
        ("market_responsible_parties", "products"),
        done_sql=(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' "
            "AND table_name = 'products' AND column_name = 'udi_issuing_entity')"
        ),
    ),
    Step(
        "tr30",
        "tr30_trial_personal_data.py",
        "add_personal_data",
        (),
        ("reportability_settings",),
        done_sql=(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' "
            "AND table_name = 'reportability_settings' AND column_name = 'report_personal_data')"
        ),
    ),
    Step(
        "tr31",
        "tr31_trial_other_countries.py",
        "add_other_countries",
        (),
        ("complaint_market_assessments", "report_obligations"),
        done_sql=(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' "
            "AND table_name = 'report_obligations' AND column_name = 'country')"
        ),
    ),
    Step(
        "trrca",
        "tr3x_trial_rca_tools.py",
        "add_rca_tools",
        (),
        ("hypotheses", "failure_chains", "decisions", "brief_review_actions", "risks", "failure_modes"),
        done_sql=(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' "
            "AND table_name = 'failure_chains' AND column_name = 'method')"
        ),
    ),
)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def state(url: str) -> tuple[bool, list[Step], list[str]]:
    """(is legacy, the steps still to run, problems that stop a step: partly present tables or missing needs)."""
    engine = create_engine(url, connect_args=connect_args())
    try:
        tables = set(inspect(engine).get_table_names())
        legacy, _ = _load("migrate_data_planes", ROOT / "scripts" / "migrate_data_planes.py").plane_state(url)
        todo: list[Step] = []
        problems: list[str] = []
        for step in STEPS:
            if step.done_sql is not None:
                with engine.connect() as connection:
                    if connection.execute(text(step.done_sql)).scalar():
                        continue
                absent = [table for table in step.required if table not in tables and table not in _created_by(todo)]
                if absent:
                    problems.append(f"{step.name}: needs {', '.join(absent)} first")
                else:
                    todo.append(step)
                continue
            missing = [table for table in step.tables if table not in tables]
            if not missing:
                continue
            if len(missing) != len(step.tables):
                problems.append(f"{step.name}: only some tables exist ({', '.join(missing)} missing); fix by hand")
                continue
            absent = [table for table in step.required if table not in tables and table not in _created_by(todo)]
            if absent:
                problems.append(f"{step.name}: needs {', '.join(absent)} first")
                continue
            todo.append(step)
        return legacy == "LEGACY", todo, problems
    finally:
        engine.dispose()


def _created_by(steps: list[Step]) -> set[str]:
    return {table for step in steps for table in step.tables}


def apply(url: str, steps: list[Step]) -> None:
    engine = create_engine(url, connect_args=connect_args())
    try:
        with engine.begin() as connection:
            # Older databases isolate by organization only (no system scope function); match their other tables.
            system_scope = bool(connection.execute(text("SELECT to_regproc('public.mdarix_system_scope')")).scalar())
            # The numbering triggers call md26's function; refuse to start without it.
            if not connection.execute(text("SELECT to_regproc('public.mdarix_assign_business_id')")).scalar():
                raise RuntimeError("md26's numbering function is missing; run add_business_ids_to_legacy_planes.py")
            with Operations.context(MigrationContext.configure(connection)):
                for step in steps:
                    module = _load(step.module_file.removesuffix(".py"), VERSIONS / step.module_file)
                    getattr(module, step.function)(system_scope)
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="change the databases (default: dry run)")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        bind_system(db, "add workflow tables to legacy organization databases")
        planes = (
            db.query(TenantDataPlane)
            .filter(
                TenantDataPlane.status == "ACTIVE", TenantDataPlane.connection_secret_ref != SHARED_CONTROL_DATA_PLANE
            )
            .all()
        )
    finally:
        db.close()
    failures = 0
    for plane in planes:
        label = f"{plane.database_ref} (tenant {plane.tenant_id})"
        url = os.getenv(f"{plane.connection_secret_ref}_OWNER", "").strip() or _secret_url(plane.connection_secret_ref)
        try:
            legacy, todo, problems = state(url)
            names = ", ".join(step.name for step in todo)
            if not legacy:
                print(f"SKIP      {label}: managed by migrations (scripts/migrate_data_planes.py)")
            elif problems:
                failures += 1
                print(f"FAILED    {label}: {'; '.join(problems)}")
            elif not todo:
                print(f"OK        {label}: workflow tables present")
            elif not args.apply:
                print(f"PENDING   {label}: {names} (dry run)")
            else:
                apply(url, todo)
                print(f"DONE      {label}: {names} created")
        except Exception as exc:  # report every database, then fail
            failures += 1
            print(f"FAILED    {label}: {type(exc).__name__}: {exc}")
    if not planes:
        print("No dedicated organization databases are registered.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
