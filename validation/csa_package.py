from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json


@dataclass(frozen=True)
class ValidationTest:
    test_id: str
    phase: str
    requirement_id: str
    objective: str
    procedure: tuple[str, ...]
    acceptance: str
    evidence: str


REQUIREMENTS = (
    ("MDX-SEC-001", "Authenticated users can access only authorized tenant data."),
    ("MDX-SEC-002", "Protected fields are excluded from API, search, export, and AI context."),
    ("MDX-AI-001", "AI output is advisory, provenance-aware, and requires human review."),
    ("MDX-AUD-001", "Governed mutations create tenant-scoped audit evidence."),
    ("MDX-DOC-001", "Regulatory drafts preserve version, citations, limitations, and approval state."),
    ("MDX-OPS-001", "Migrations, health checks, worker processing, and recovery are observable."),
)


TESTS = (
    ValidationTest("IQ-001", "IQ", "MDX-OPS-001", "Verify installation identity and source integrity.", ("Record release commit and package versions.", "Record Python, Node, PostgreSQL, and pgvector versions.", "Verify migration head."), "All versions and the approved migration head are recorded.", "IQ-001 environment record"),
    ValidationTest("IQ-002", "IQ", "MDX-SEC-001", "Verify required services and configuration are installed.", ("Start the controlled test stack.", "Verify API, database, worker, simulator, and frontend health endpoints."), "All required services report healthy without secrets in logs.", "IQ-002 health traces"),
    ValidationTest("OQ-001", "OQ", "MDX-SEC-001", "Verify two tenants cannot read each other's records.", ("Sign in as Tenant A.", "Request Tenant B record, search, export, attachment, and AI context by ID.", "Repeat in reverse."), "Every unauthorized request returns denial or no foreign data.", "OQ-001 API traces and audit IDs"),
    ValidationTest("OQ-002", "OQ", "MDX-SEC-002", "Verify field policy enforcement across all retrieval surfaces.", ("Mark a field hidden.", "Read API, search, export, attachment metadata, and AI context."), "The hidden value is absent from every response and artifact.", "OQ-002 redacted response set"),
    ValidationTest("OQ-003", "OQ", "MDX-AI-001", "Verify grounded AI safeguards.", ("Submit a scoped investigation question.", "Inspect citations, provenance, uncertainty, limitations, and human-review flag.", "Submit an unsupported causal claim."), "Unsupported causality is rejected or abstained from and human review remains required.", "OQ-003 AI response evidence"),
    ValidationTest("OQ-004", "OQ", "MDX-AUD-001", "Verify governed mutation auditability.", ("Perform a governed update and approval.", "Inspect actor, tenant, timestamp, reason, old/new values, and signature binding."), "The mutation and approval are immutable and version-bound.", "OQ-004 audit/signature evidence"),
    ValidationTest("PQ-001", "PQ", "MDX-DOC-001", "Verify a complete regulatory authoring journey.", ("Create CER, IFU, GSPR, and eSTAR preparation documents.", "Create a second version.", "Review, approve, archive, export, and verify the content hash."), "The complete history is reproducible and no version is silently overwritten.", "PQ-001 document package"),
    ValidationTest("PQ-002", "PQ", "MDX-OPS-001", "Verify normal and failure recovery workflows.", ("Run connector ingestion, retry, dead-letter, replay, report generation, and stale-job recovery.", "Capture worker and audit evidence."), "Retries are bounded, replay is idempotent, and failures are visible and recoverable.", "PQ-002 operational report"),
    ValidationTest("PQ-003", "PQ", "MDX-SEC-001", "Verify browser persona workflows.", ("Exercise Platform Admin, Customer Admin, investigator, and approver journeys on desktop and mobile.", "Review keyboard focus and screen-reader semantics."), "Authorized journeys work without overflow, leakage, or inaccessible critical controls.", "PQ-003 browser/accessibility evidence"),
)


def build_package(release: str = "MVP-1.0") -> dict:
    return {
        "package_id": "MDARIX-CSA-MVP-1.0",
        "release": release,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "intended_use": "Internal design-partner MVP validation; not a regulatory certification.",
        "requirements": [{"id": key, "statement": statement} for key, statement in REQUIREMENTS],
        "tests": [asdict(test) for test in TESTS],
        "deviation_process": ["Record deviation ID and impact.", "Assess patient/product/data integrity impact.", "Approve corrective action.", "Retest affected requirement.", "Obtain QA and system-owner approval."],
        "approval": {"system_owner": "PENDING", "quality_reviewer": "PENDING", "approval_date": None},
        "status": "READY_FOR_EXECUTION",
        "limitations": ["Execution evidence must be generated against the approved test environment.", "This package does not certify FDA, ISO, HIPAA, or 21 CFR Part 11 compliance."],
    }


def render_markdown(package: dict) -> str:
    lines = [f"# {package['package_id']}", "", f"Release: `{package['release']}`", f"Status: **{package['status']}**", "", "## Intended use", package["intended_use"], "", "## Requirements"]
    lines.extend(f"- **{item['id']}** — {item['statement']}" for item in package["requirements"])
    lines += ["", "## IQ/OQ/PQ tests"]
    for test in package["tests"]:
        lines += [f"### {test['test_id']} — {test['objective']}", f"Phase: `{test['phase']}`; Requirement: `{test['requirement_id']}`", "Procedure:"]
        lines.extend(f"1. {step}" for step in test["procedure"])
        lines += [f"Acceptance: {test['acceptance']}", f"Evidence: `{test['evidence']}`", ""]
    lines += ["## Deviations", *[f"{i}. {item}" for i, item in enumerate(package["deviation_process"], 1)], "", "## Approval", "System owner: PENDING", "Quality reviewer: PENDING", "", "## Limitations", *[f"- {item}" for item in package["limitations"]]]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    package = build_package()
    print(json.dumps(package, indent=2))
