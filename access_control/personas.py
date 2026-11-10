"""Canonical R1 persona catalog and safe assignment validation."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PersonaDefinition:
    code: str
    label: str
    dashboard_emphasis: tuple[str, ...]


R1_PERSONAS = (
    PersonaDefinition(
        "INVESTIGATOR", "Quality/PMS Investigator", ("signals", "investigations", "evidence_gaps", "unknowns")
    ),
    PersonaDefinition(
        "PRODUCT_QUALITY",
        "Product/Design Quality Engineer",
        ("products", "revisions", "components", "suppliers", "changes"),
    ),
    PersonaDefinition(
        "REVIEWER", "Regulatory/PMS Reviewer", ("evidence_completeness", "provenance", "contradictions", "limitations")
    ),
    PersonaDefinition(
        "APPROVER",
        "Quality/Regulatory Approver",
        ("decision_briefs", "authority", "segregation_of_duties", "material_changes"),
    ),
    PersonaDefinition("LEADER", "Product/Quality Leader", ("portfolio_signals", "aging", "decision_load", "risk")),
    PersonaDefinition(
        "ADMINISTRATOR", "MDARIX Administrator", ("users", "roles", "connectors", "mappings", "plans", "audit")
    ),
)

PERSONAS_BY_CODE = {persona.code: persona for persona in R1_PERSONAS}


def get_persona(code: str) -> PersonaDefinition:
    try:
        return PERSONAS_BY_CODE[code.strip().upper()]
    except (AttributeError, KeyError) as exc:
        raise ValueError("UNKNOWN_PERSONA") from exc


def validate_persona_assignments(codes: list[str]) -> list[PersonaDefinition]:
    """Validate and normalize assignments without granting authority."""
    normalized = [code.strip().upper() for code in codes]
    if len(normalized) != len(set(normalized)):
        raise ValueError("DUPLICATE_PERSONA")
    return [get_persona(code) for code in normalized]


# ------------------------------------------------------------------------------- Workspace personas (0.10.73, C1)
# "Viewing as": which destinations and Home a person sees on the new navigation. A persona is never a permission:
# signing and every server route follow the person's real role (backend/app/access/permissions.py). An invited
# colleague's persona is their real role (``role``), set by the trial owner; only the trial owner switches their own
# view, and their role stays Leader whatever they view as.


@dataclass(frozen=True)
class WorkspacePersona:
    code: str
    label: str
    sub: str
    role: str
    tabs: tuple[str, ...]


WORKSPACE_PERSONAS = (
    WorkspacePersona(
        "admin",
        "Admin",
        "Trial owner · sees everything",
        "LEADER",
        ("home", "complaints", "trees", "reports", "investigations", "trends", "products", "records", "team"),
    ),
    WorkspacePersona(
        "quality",
        "Quality Leader",
        "Complaints, investigations, CAPA, trends",
        "LEADER",
        ("home", "complaints", "reports", "investigations", "trends", "products", "records"),
    ),
    WorkspacePersona(
        "regulatory",
        "Regulatory Leader",
        "Reportability, legal clocks, authority reports",
        "REGULATORY_REVIEWER",
        ("home", "complaints", "trees", "reports", "records"),
    ),
    # B2 (spec 6.2): the Service Desk logs, checks and classifies Cases.
    WorkspacePersona(
        "servicedesk", "Service Desk", "Cases: log, check and classify", "SERVICE_DESK", ("home", "complaints")
    ),
    WorkspacePersona(
        "handler", "Complaint Handler", "Calls, triage, second look", "TRIAGE_LEAD", ("home", "complaints")
    ),
    WorkspacePersona(
        "investigator",
        "Investigator",
        "Investigations and the evidence",
        "INVESTIGATOR",
        ("home", "investigations", "trends", "products"),
    ),
    WorkspacePersona(
        "risk",
        "Risk Reviewer",
        "Risk reviews and the risk file",
        "RISK_REVIEWER",
        ("home", "investigations", "products", "records"),
    ),
    WorkspacePersona(
        "decision",
        "Decision Maker",
        "Approvals and signed decisions",
        "APPROVER",
        ("home", "complaints", "reports", "records"),
    ),
    WorkspacePersona(
        "executive", "Executive", "View only: what needs attention", "VIEWER", ("home", "trends", "products", "records")
    ),
)
WORKSPACE_PERSONAS_BY_CODE = {persona.code: persona for persona in WORKSPACE_PERSONAS}
# The persona a colleague may be given: every one but Admin, which is the trial owner's.
COLLEAGUE_PERSONAS = tuple(persona.code for persona in WORKSPACE_PERSONAS if persona.code != "admin")
# The persona of a role, for a colleague and for a pilot user: the role's own screens. Leader is the Quality Leader
# (the trial owner's Admin is their own choice), a quality reviewer works as one, an administrator sees everything.
_ROLE_PERSONA = {
    "LEADER": "quality",
    "REVIEWER": "quality",
    "REGULATORY_REVIEWER": "regulatory",
    "SERVICE_DESK": "servicedesk",
    "TRIAGE_LEAD": "handler",
    "INVESTIGATOR": "investigator",
    "RISK_REVIEWER": "risk",
    "APPROVER": "decision",
    "VIEWER": "executive",
    "CUSTOMER_ADMIN": "admin",
    "PLATFORM_ADMIN": "admin",
}


def persona_for_role(role_code: str | None) -> str:
    """The persona a role's screens are: an organization's own role reads as the Quality Leader's (the tabs are only
    a view; the server still decides every action)."""
    return _ROLE_PERSONA.get(str(role_code or "").strip().upper(), "quality")


def workspace_persona(code: str | None) -> WorkspacePersona:
    try:
        return WORKSPACE_PERSONAS_BY_CODE[str(code or "").strip().lower()]
    except KeyError as exc:
        raise ValueError("UNKNOWN_PERSONA") from exc
