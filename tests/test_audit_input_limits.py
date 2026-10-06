"""Audit events tolerate hostile request headers, and exported spreadsheets are formula-safe."""

import uuid

from starlette.requests import Request

from backend.app.csv_safe import safe_cell
from backend.app.enterprise_audit import make_audit_event
from backend.app.tenant_export import _cell


def _request(user_agent: str) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [(b"user-agent", user_agent.encode())],
        "client": ("203.0.113.9", 4000),
    }
    return Request(scope)


def test_an_over_long_user_agent_is_cut_to_the_audit_column():
    event = make_audit_event(
        tenant_id=uuid.uuid4(), actor_ref="test", action="TEST", entity_type="Test", request=_request("x" * 5000)
    )
    assert event.user_agent == "x" * 512


def test_a_missing_user_agent_stays_empty():
    event = make_audit_event(
        tenant_id=uuid.uuid4(), actor_ref="test", action="TEST", entity_type="Test", request=_request("")
    )
    assert event.user_agent is None


def test_readable_export_cells_cannot_run_as_formulas():
    for hostile in ('=HYPERLINK("http://x")', "+1+1", "-2+3", "@SUM(A1)"):
        assert safe_cell(_cell(hostile)).startswith("'")
    assert safe_cell(_cell("Seal leak on lot L24-0815")) == "Seal leak on lot L24-0815"
