"""0.10.93 (B2) step 4: who may do what with Cases and triage (spec 6.1-6.3, OD-4), as the role table on the server."""

from __future__ import annotations

import pytest

from access_control.personas import persona_for_role, workspace_persona
from backend.app.access.permissions import (
    CASE_CLASSIFY,
    CASE_LOG,
    COMPLAINT_TRIAGE,
    QUALITY_REVIEW,
    permissions_for_role,
)
from backend.app.access.platform_accounts import PERMISSION_TEXT
from backend.app.role_codes import ROLE_LABELS

pytestmark = pytest.mark.unit

# Spec 6.3: (log a case, classify, QA review, triage) per role.
TABLE = {
    "SERVICE_DESK": (True, True, False, False),
    "TRIAGE_LEAD": (True, True, False, True),
    "INVESTIGATOR": (True, False, False, False),  # OD-4: classification and triage removed
    "REVIEWER": (True, True, True, True),
    "REGULATORY_REVIEWER": (False, False, False, True),  # OD-4 / T-D10: triage added
    "APPROVER": (False, False, False, False),
    "LEADER": (True, True, True, True),
    "VIEWER": (False, False, False, False),
    "CUSTOMER_ADMIN": (False, False, False, False),  # administrators never sign
}


@pytest.mark.parametrize("role", sorted(TABLE))
def test_each_role_gets_exactly_the_case_permissions_of_the_table(role):
    granted = permissions_for_role(role)
    assert tuple(p in granted for p in (CASE_LOG, CASE_CLASSIFY, QUALITY_REVIEW, COMPLAINT_TRIAGE)) == TABLE[role]


def test_an_unknown_role_gets_nothing():  # deny by default
    assert permissions_for_role("SOMETHING_NEW") == frozenset()


def test_the_service_desk_role_and_persona():  # spec 6.2
    assert ROLE_LABELS["SERVICE_DESK"] == "Service Desk Agent"
    assert permissions_for_role("Service Desk") == permissions_for_role("SERVICE_DESK")
    persona = workspace_persona(persona_for_role("SERVICE_DESK"))
    assert persona.label == "Service Desk" and persona.tabs == ("home", "complaints") and persona.role == "SERVICE_DESK"


def test_every_new_permission_has_its_plain_words():
    assert {CASE_LOG, CASE_CLASSIFY, COMPLAINT_TRIAGE} <= set(PERMISSION_TEXT)
