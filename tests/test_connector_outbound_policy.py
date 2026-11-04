"""Connector requests: internal addresses refused on the live socket, redirects never followed, secrets namespaced."""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from backend.app.access.common import _safe_connector_summary
from backend.app.access.outbound import safe_urlopen
from tests.conftest import authenticated_client


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server naming
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "http://169.254.169.254/latest/meta-data/")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, *_args):
        pass


@pytest.fixture
def local_server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"127.0.0.1:{server.server_port}"
    server.shutdown()


def test_the_live_connection_to_an_internal_address_is_refused_unless_allowlisted(monkeypatch, local_server):
    monkeypatch.delenv("MDARIX_CONNECTOR_ALLOWED_HOSTS", raising=False)
    # Even if a hostname passed an earlier check (DNS rebinding), the open socket's address is checked again.
    with pytest.raises(URLError):
        safe_urlopen(Request(f"http://{local_server}/health"), timeout=5)
    monkeypatch.setenv("MDARIX_CONNECTOR_ALLOWED_HOSTS", local_server)
    with safe_urlopen(Request(f"http://{local_server}/health"), timeout=5) as response:
        assert response.status == 200


def test_redirects_are_never_followed(monkeypatch, local_server):
    monkeypatch.setenv("MDARIX_CONNECTOR_ALLOWED_HOSTS", local_server)
    with pytest.raises(HTTPError) as refused:
        safe_urlopen(Request(f"http://{local_server}/redirect"), timeout=5)
    assert refused.value.code == 302


def test_summary_never_reveals_whether_non_connector_secrets_exist(monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "present")
    row = type(
        "Row",
        (),
        {
            "id": "c1",
            "business_id": "CNX000001",
            "code": "x",
            "connector_type": "REST",
            "version": "1",
            "status": "DRAFT",
        },
    )()
    row.configuration = {"credential_ref": "POSTGRES_PASSWORD"}
    assert _safe_connector_summary(row)["credential_configured"] is False


@pytest.mark.db
def test_api_refuses_a_connector_that_names_a_platform_secret():
    admin = authenticated_client()
    response = admin.post(
        "/api/v1/admin/configuration/connectors",
        json={
            "code": "steal-db-password",
            "connector_type": "REST",
            "version": "1",
            "configuration": {"endpoint": "https://provider.example", "credential_ref": "POSTGRES_PASSWORD"},
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "CONNECTOR_CREDENTIAL_REF_INVALID"
