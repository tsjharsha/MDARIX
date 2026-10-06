"""The objects that carry a human-readable business identifier (migration md26), shared by the migration and the
schema-drift policy so the two cannot disagree.

Each object gets ``business_id``: its prefix and a number padded to six digits (CUST000001, CMP000001). The number is
assigned by the database when the row is inserted, never changes, and is never reused.

- ``scope`` "global": one sequence for the whole platform (objects platform administrators list across organizations).
  "tenant": one sequence per organization, so each customer's first complaint is CMP000001.
- ``natural_key``: the columns an upsert (INSERT ... ON CONFLICT) is keyed on. When a row with that key already exists
  the insert is a re-import, and it keeps the existing number instead of consuming a new one.
- ``order_by``: the column existing rows are numbered by (oldest first).
"""

from __future__ import annotations

from dataclasses import dataclass

WIDTH = 6
GLOBAL_SCOPE = "00000000-0000-0000-0000-000000000000"


@dataclass(frozen=True)
class BusinessObject:
    table: str
    prefix: str
    entity: str
    scope: str  # "global" | "tenant"
    natural_key: tuple[str, ...] = ()
    order_by: str = "created_at"

    @property
    def index_name(self) -> str:
        return f"ix_{self.table}_business_id"

    @property
    def trigger_name(self) -> str:
        return f"{self.table}_business_id"

    @property
    def immutable_trigger_name(self) -> str:
        return f"{self.table}_business_id_immutable"


OBJECTS: tuple[BusinessObject, ...] = (
    # Platform: numbered across all organizations.
    BusinessObject("customers", "CUST", "Customer", "global", ("customer_identifier",)),
    BusinessObject("tenants", "TEN", "Tenant", "global", ("tenant_key",)),
    BusinessObject("auth_users", "USR", "User", "global"),
    BusinessObject("plan_definitions", "PLAN", "Plan", "global"),
    BusinessObject("subscription_lifecycles", "SUB", "Subscription", "global"),
    BusinessObject("onboarding_requests", "TRQ", "Trial Request", "global"),
    BusinessObject("demo_requests", "DEMO", "Demo Request", "global"),
    BusinessObject("support_problem_reports", "SUPT", "Support Problem Report", "global"),
    BusinessObject("trial_feedback", "FDBK", "Feedback", "global"),
    BusinessObject("platform_incidents", "INC", "System Incident", "global"),
    BusinessObject("tenant_exports", "DEXP", "Data Export", "global"),
    # Organization master data: numbered per organization.
    BusinessObject("products", "PROD", "Product", "tenant", ("product_identifier",)),
    BusinessObject("product_versions", "PV", "Product Version", "tenant", ("product_id", "version_identifier")),
    BusinessObject("components", "COMP", "Component", "tenant", ("component_identifier", "revision")),
    BusinessObject("suppliers", "SUP", "Supplier", "tenant", ("supplier_identifier",)),
    BusinessObject("manufacturing_sites", "SITE", "Manufacturing Site", "tenant", ("site_identifier",)),
    BusinessObject("lot_batches", "LOT", "Lot / Batch", "tenant", ("lot_identifier",)),
    BusinessObject("requirements", "REQ", "Requirement", "tenant", ("requirement_identifier",)),
    BusinessObject("risks", "RSK", "Risk", "tenant", ("risk_identifier",)),
    BusinessObject("failure_modes", "FM", "Failure Mode", "tenant", ("failure_mode_identifier",)),
    BusinessObject("controls", "CTL", "Control", "tenant", ("control_identifier",)),
    BusinessObject("changes", "CHG", "Product Change", "tenant", ("change_identifier",)),
    BusinessObject("connector_configurations", "CNX", "Connector", "tenant"),
    # Organization transactions: numbered per organization.
    BusinessObject("complaints", "CMP", "Complaint", "tenant", ("complaint_identifier",)),
    BusinessObject("investigations", "INV", "Investigation", "tenant", ("investigation_identifier",)),
    BusinessObject("evidence", "EVD", "Evidence", "tenant", ("evidence_identifier",)),
    BusinessObject("capas", "CAPA", "CAPA", "tenant"),
    BusinessObject("decisions", "DEC", "Decision", "tenant"),
    BusinessObject("hypotheses", "HYP", "Hypothesis", "tenant"),
    BusinessObject("unknowns", "UNK", "Unknown", "tenant"),
    BusinessObject("scenarios", "SCN", "Scenario", "tenant"),
    BusinessObject("failure_chains", "FC", "Failure Chain", "tenant"),
    BusinessObject("regulatory_documents", "RDOC", "Regulatory Document", "tenant"),
    BusinessObject("supplier_evidence_requests", "EVR", "Evidence Request", "tenant"),
    BusinessObject("signed_approval_records", "ESIG", "Electronic Signature", "tenant"),
    BusinessObject("investigation_briefs", "DBR", "Decision Brief", "tenant"),
    BusinessObject("report_jobs", "RPT", "Report Execution", "tenant"),
    BusinessObject("ai_executions", "AIEX", "AI Execution", "tenant", order_by="execution_timestamp"),
    BusinessObject("evaluation_runs", "EVAL", "Evaluation Run", "tenant"),
)

# Objects whose tables were created after md26. md26 numbers only OBJECTS; each of these is numbered by the
# migration that creates its table (named in the comment).
LATER_OBJECTS: tuple[BusinessObject, ...] = (
    BusinessObject("workflow_tasks", "TASK", "Task", "tenant"),  # md27
)

COUNTER_TABLE = "business_id_counters"
INDEX_NAMES = frozenset(item.index_name for item in OBJECTS + LATER_OBJECTS)
