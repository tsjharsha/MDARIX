"""Phase 1 workflow roles without a database: codes and labels, the permissions of each role, the union over several
roles, approval with several roles, and the deep links in work emails."""

from types import SimpleNamespace

import pytest

from auth import emailer
from backend.app import notifications
from backend.app.access import permissions
from backend.app.access.permissions import (
    AI_RUN,
    ALL,
    DATA_EXPORT,
    DECISION_SIGN,
    EVIDENCE_REQUEST,
    EVIDENCE_REVIEW,
    INVESTIGATION_ASSIGN,
    INVESTIGATION_CREATE,
    INVESTIGATION_WORK,
    QUALITY_REVIEW,
    RECORDS_WRITE,
    REGULATORY_APPROVE,
    REGULATORY_REVIEW,
    RISK_REVIEW,
    SIGNAL_TRIAGE,
    permissions_for_role,
    permissions_for_roles,
)
from backend.app.db.models.foundation import ApprovalAuthority, SegregationOfDutiesPolicy
from backend.app.governance_router import ADMINISTRATOR_CANNOT_SIGN, approval_check, approval_denial
from backend.app.role_codes import (
    CANONICAL_SYSTEM_ROLES,
    ROLE_LABELS,
    WORKFLOW_ROLES,
    canonical_stored_role,
    role_label,
)

pytestmark = pytest.mark.unit

WORK = {RECORDS_WRITE, AI_RUN, DATA_EXPORT}
EVIDENCE = {EVIDENCE_REVIEW, EVIDENCE_REQUEST}
CASES = {"case.log", "case.classify"}


# ------------------------------------------------------------------------------------------- codes and labels


def test_the_new_roles_are_standard_roles_with_labels():
    assert {"TRIAGE_LEAD", "RISK_REVIEWER", "REGULATORY_REVIEWER"} <= CANONICAL_SYSTEM_ROLES
    assert WORKFLOW_ROLES == (
        "TRIAGE_LEAD",
        "INVESTIGATOR",
        "RISK_REVIEWER",
        "REGULATORY_REVIEWER",
        "REVIEWER",
        "APPROVER",
        "LEADER",
    )
    assert role_label("Approver") == "Decision Maker"
    assert role_label("risk reviewer") == "Risk Reviewer"
    assert role_label("TRIAGE_LEAD") == "Complaint Handler"
    assert role_label("Customer Admin") == "Customer Administrator"
    assert role_label("Quality Lead") == "Quality Lead"  # a custom role keeps its own name
    assert set(ROLE_LABELS) == CANONICAL_SYSTEM_ROLES
    assert canonical_stored_role("Regulatory Reviewer") == "REGULATORY_REVIEWER"


# ------------------------------------------------------------------------------------------- permissions


@pytest.mark.parametrize(
    ("role", "allowed"),
    [
        ("Viewer", set()),
        # 0.10.93 (B2, OD-4): case.log, case.classify and complaint.triage.
        ("TRIAGE_LEAD", WORK | CASES | {SIGNAL_TRIAGE, INVESTIGATION_CREATE, INVESTIGATION_ASSIGN, "complaint.triage"}),
        ("Investigator", WORK | EVIDENCE | {INVESTIGATION_CREATE, INVESTIGATION_WORK, "case.log"}),
        ("Risk Reviewer", {AI_RUN, DATA_EXPORT, RISK_REVIEW} | EVIDENCE),
        (
            "REGULATORY_REVIEWER",
            {AI_RUN, DATA_EXPORT, REGULATORY_REVIEW, REGULATORY_APPROVE, "complaint.triage"} | EVIDENCE,
        ),
        ("Reviewer", WORK | EVIDENCE | CASES | {QUALITY_REVIEW, INVESTIGATION_ASSIGN, "complaint.triage"}),
        ("Approver", WORK | {REGULATORY_APPROVE, DECISION_SIGN}),
        ("Leader", set(ALL)),
        ("PLATFORM_ADMIN", set(ALL)),
        ("CUSTOMER_ADMIN", WORK),
        ("Something custom", set()),
    ],
)
def test_each_role_has_the_permissions_of_the_contract(role, allowed):
    assert permissions_for_role(role) == allowed


def test_existing_roles_keep_every_permission_they_had():
    before = {
        "INVESTIGATOR": WORK,
        "REVIEWER": WORK,
        "APPROVER": WORK | {REGULATORY_APPROVE},
        "LEADER": WORK | {REGULATORY_APPROVE},
        "CUSTOMER_ADMIN": WORK,
    }
    for role, granted in before.items():
        assert granted <= permissions_for_role(role), role
    assert len(ALL) == 17  # 0.10.93 (B2): case.log, case.classify, complaint.triage


def test_permissions_of_several_roles_are_their_union():
    assert permissions_for_roles([]) == frozenset()
    assert permissions_for_roles(["Viewer", "Risk Reviewer"]) == permissions_for_role("Risk Reviewer")
    assert permissions_for_roles(["Investigator", "RISK_REVIEWER"]) == (
        permissions_for_role("Investigator") | permissions_for_role("RISK_REVIEWER")
    )
    # One role: exactly that role's permissions, as before.
    assert permissions_for_roles(["Approver"]) == permissions_for_role("Approver")


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args):
        return self

    def filter_by(self, **kwargs):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


def test_only_workflow_roles_count_as_additional_roles():
    db = SimpleNamespace(query=lambda *args: _Rows([("LEADER",), ("customer_admin",), ("PLATFORM_ADMIN",), ("x",)]))
    user = SimpleNamespace(id="u", tenant_id="t")
    assert permissions.additional_roles_of_user(db, user) == ["LEADER"]


def test_roles_of_a_user_put_the_account_role_first_and_appear_once(monkeypatch):
    monkeypatch.setattr(permissions, "role_of_user", lambda db, user: "Investigator")
    monkeypatch.setattr(permissions, "additional_roles_of_user", lambda db, user: ["INVESTIGATOR", "RISK_REVIEWER"])
    assert permissions.roles_of_user(None, SimpleNamespace()) == ["Investigator", "RISK_REVIEWER"]
    monkeypatch.setattr(permissions, "additional_roles_of_user", lambda db, user: [])
    assert permissions.roles_of_user(None, SimpleNamespace()) == ["Investigator"]


def test_a_legacy_session_keeps_the_permissions_of_its_role():
    ctx = SimpleNamespace(user_id="not-a-uuid", tenant_id="t", active_role_id="Investigator")
    assert permissions.effective_permissions(None, ctx) == permissions_for_role("Investigator")


# ------------------------------------------------------------------------------------------- approval with roles


class _GovernanceDB:
    """Approval authorities for the named roles, and a segregation-of-duties policy forbidding self-approval."""

    def __init__(self, authorized_roles):
        self.authorities = [SimpleNamespace(role_name=name) for name in authorized_roles]

    def query(self, model):
        if model is ApprovalAuthority:
            return _Rows(self.authorities)
        if model is SegregationOfDutiesPolicy:
            return _Rows([SimpleNamespace(creator_cannot_approve=True, last_material_editor_cannot_approve=False)])
        raise AssertionError(model)


DECISION = SimpleNamespace(authorized_by_ref="author")


def test_one_role_gives_exactly_the_single_role_answer():
    db = _GovernanceDB(["APPROVER", "LEADER"])
    assert approval_check(db, "t", "Approver", DECISION, "signer") == (None, "Approver")
    assert approval_denial(db, "t", "Approver", DECISION, "signer") is None
    assert approval_denial(db, "t", "Investigator", DECISION, "signer")[0] == "APPROVAL_AUTHORITY_DENIED"
    assert approval_denial(db, "t", "Approver", DECISION, "author")[0] == "SOD_DENIED"
    assert approval_denial(db, "t", "CUSTOMER_ADMIN", DECISION, "signer") == ADMINISTRATOR_CANNOT_SIGN
    assert approval_denial(db, "t", None, DECISION, "signer")[0] == "APPROVAL_AUTHORITY_DENIED"


def test_any_role_with_authority_may_approve_and_is_the_role_recorded():
    db = _GovernanceDB(["APPROVER", "LEADER"])
    assert approval_check(db, "t", ["Investigator", "APPROVER"], DECISION, "signer") == (None, "APPROVER")
    assert approval_check(db, "t", ["Leader", "APPROVER"], DECISION, "signer") == (None, "Leader")
    denial, role = approval_check(db, "t", ["Investigator", "RISK_REVIEWER"], DECISION, "signer")
    assert denial[0] == "APPROVAL_AUTHORITY_DENIED" and role is None
    # Separation of duties still applies to a person with several roles.
    denial, role = approval_check(db, "t", ["Investigator", "APPROVER"], DECISION, "author")
    assert denial[0] == "SOD_DENIED" and role is None


def test_an_administrator_role_among_several_still_cannot_sign():
    db = _GovernanceDB(["APPROVER", "CUSTOMER_ADMIN"])
    assert approval_check(db, "t", ["CUSTOMER_ADMIN", "APPROVER"], DECISION, "signer") == (
        ADMINISTRATOR_CANNOT_SIGN,
        None,
    )


# ------------------------------------------------------------------------------------------- email deep links


@pytest.fixture
def outbox(monkeypatch):
    monkeypatch.setenv("MDARIX_APP_URL", "https://app.example.com")
    sent = []
    monkeypatch.setattr(
        emailer,
        "_send_email",
        lambda to, subject, text, html=None, reply_to=None: sent.append({"text": text, "html": html}) or "SENT",
    )
    return sent


def test_work_emails_open_the_case_when_they_know_it(outbox):
    emailer.send_assignment_notice(
        "a@x.test", organization="Acme", reference="INV000147", assigned_by=None, case="INV000147"
    )
    emailer.send_review_pending_notice(
        "a@x.test", organization="Acme", reference="DEC000003", submitted_by=None, case="INV000147"
    )
    emailer.send_signoff_completed_notice(
        "a@x.test", organization="Acme", reference="DEC000003", signed_by=None, decision="APPROVE", case="INV000147"
    )
    assert "https://app.example.com/app/investigations?case=INV000147" in outbox[0]["text"]
    # The decision is the case page's Decision step (0.10.67; /app/decision?case= still opens it from older e-mails).
    assert "https://app.example.com/app/investigations?case=INV000147&step=Decision" in outbox[1]["text"]
    assert "https://app.example.com/app/investigations?case=INV000147&step=Decision" in outbox[2]["text"]


def test_work_emails_without_a_case_keep_their_links(outbox):
    emailer.send_assignment_notice("a@x.test", organization="Acme", reference="INV-7", assigned_by=None)
    emailer.send_review_pending_notice("a@x.test", organization="Acme", reference="DEC1", submitted_by=None)
    emailer.send_signoff_completed_notice("a@x.test", organization="Acme", reference="DEC1", signed_by=None)
    assert "https://app.example.com/app/my-work" in outbox[0]["text"] and "?case=" not in outbox[0]["text"]
    assert (
        "https://app.example.com/app/my-work?tab=Approvals" in outbox[1]["text"] and "?case=" not in outbox[1]["text"]
    )
    assert "https://app.example.com/app/investigations" in outbox[2]["text"] and "?case=" not in outbox[2]["text"]


def test_the_queue_carries_a_case_number_only_when_given_and_well_formed():
    assert notifications._case({"investigation_business_id": "INV000147"}) == {"investigation_business_id": "INV000147"}
    assert notifications._case({}) == {}
    assert notifications._case({"investigation_business_id": "x@y.test"}) == {}
    assert notifications._case({"investigation_business_id": "INV 1"}) == {}
