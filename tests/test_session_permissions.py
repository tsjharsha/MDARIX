"""The session tells the interface which business actions the role may take, by the same rule the API enforces."""

import pytest

from backend.app.access.permissions import permissions_for_role
from tests.test_business_permissions import _client_with_role


@pytest.mark.parametrize("role", ["Viewer", "Investigator", "Approver", "CUSTOMER_ADMIN", "SomeCustomRole"])
def test_session_lists_the_business_permissions_of_the_role(role):
    session = _client_with_role(role).get("/api/v1/session/context")
    assert session.status_code == 200, session.text
    assert session.json()["business_permissions"] == sorted(permissions_for_role(role))


def test_a_viewer_is_shown_read_only_and_refused_by_the_api_alike():
    viewer = _client_with_role("Viewer")
    assert viewer.get("/api/v1/session/context").json()["business_permissions"] == []
    refused = viewer.post("/api/v1/stage3/interactions", json={"prompt": "What changed?"})
    assert refused.status_code == 403 and refused.json()["detail"]["permission"] == "ai.run"
