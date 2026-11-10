"""New uploads, newly created exports and connector syncs are rate limited per person and per organization (H1);
downloading a file that already exists is not (owner decision, 10 Nov 2026)."""

import uuid

import pytest

from backend.app import rate_limit
from backend.app.rate_limit import Limit, heavy_work


@pytest.mark.unit
@pytest.mark.parametrize(
    ("method", "path", "kind"),
    [
        ("POST", "/api/v1/data/import/complaints", "upload"),
        ("POST", "/api/v1/data/import/complaints/check", "upload"),
        ("POST", "/api/v1/data/import/detect", "upload"),
        ("POST", "/api/v1/trial/imports/products", "upload"),
        ("POST", "/api/v1/evidence-requests/r1/attachments", "upload"),
        ("POST", "/api/v1/stage3/supplier-evidence-requests/r1/attachments", "upload"),
        ("GET", "/api/v1/risk/export.csv", "export"),
        ("GET", "/api/v1/readiness/inspection-pack.zip", "export"),
        ("GET", "/api/v1/admin/audit-history/export", "export"),
        ("POST", "/api/v1/admin/exports", "export"),
        ("POST", "/api/v1/stage3/reports/PSUR/jobs", "export"),
        ("GET", "/api/v1/admin/exports/e1/download", None),
        ("GET", "/api/v1/platform-admin/tenants/t1/exports/e1/download", None),
        ("GET", "/api/v1/stage3/reports/jobs/j1/download", None),
        ("GET", "/api/v1/evidence/ev1/content", None),
        ("GET", "/api/v1/data/import/templates/complaints.csv", None),
        ("GET", "/api/v1/trial/templates/products.csv", None),
        ("POST", "/api/v1/admin/configuration/connectors/c1/execute", "sync"),
        ("POST", "/api/v1/data/import/quarantine/q1/dismiss", None),
        ("GET", "/api/v1/evidence-requests/r1/attachments", None),
        ("GET", "/api/v1/complaints", None),
        ("POST", "/api/v1/complaints/c1/disposition", None),
    ],
)
def test_heavy_work_is_recognized(method, path, kind):
    assert heavy_work(method, path) == kind


@pytest.mark.db
def test_past_the_limit_an_export_is_refused_with_429_and_a_plain_message(monkeypatch):
    from tests.conftest import authenticated_client

    monkeypatch.setenv("MDARIX_RATE_LIMITS_ENABLED", "true")
    monkeypatch.setenv("MDARIX_RATE_LIMIT_SALT", uuid.uuid4().hex)  # fresh counters for this run
    monkeypatch.setitem(rate_limit.LIMITS, "export:user", Limit(2, 3600))
    client = authenticated_client()
    answers = [client.get("/api/v1/risk/export.csv") for _ in range(3)]
    assert [answer.status_code for answer in answers[:2]] == [200, 200], answers[0].text
    refused = answers[2]
    assert refused.status_code == 429 and int(refused.headers["Retry-After"]) > 0
    assert refused.json()["detail"]["code"] == "RATE_LIMITED"
    assert refused.json()["detail"]["message"].startswith("Too many attempts. Please try again in ")
    # Other work and other people are not affected; without a session nothing is counted (the route answers 401).
    assert client.get("/api/v1/complaints").status_code == 200
    from fastapi.testclient import TestClient

    from backend.app.main import app

    assert TestClient(app).get("/api/v1/risk/export.csv").status_code == 401


@pytest.mark.db
def test_the_organization_limit_is_counted_too(monkeypatch):
    from tests.conftest import authenticated_client

    monkeypatch.setenv("MDARIX_RATE_LIMITS_ENABLED", "true")
    monkeypatch.setenv("MDARIX_RATE_LIMIT_SALT", uuid.uuid4().hex)
    monkeypatch.setitem(rate_limit.LIMITS, "export:org", Limit(1, 3600))
    client = authenticated_client()
    assert client.get("/api/v1/risk/export.csv").status_code == 200
    assert client.get("/api/v1/risk/export.csv").status_code == 429


@pytest.mark.db
def test_a_download_burst_is_never_limited_but_a_create_burst_is(monkeypatch):
    from tests.conftest import authenticated_client

    monkeypatch.setenv("MDARIX_RATE_LIMITS_ENABLED", "true")
    monkeypatch.setenv("MDARIX_RATE_LIMIT_SALT", uuid.uuid4().hex)
    monkeypatch.setitem(rate_limit.LIMITS, "export:user", Limit(1, 3600))
    client = authenticated_client()
    downloads = [
        client.get(path).status_code
        for path in ["/api/v1/data/import/templates/complaints.csv", "/api/v1/admin/exports/e1/download"] * 3
    ]
    assert 429 not in downloads, downloads
    assert [client.post("/api/v1/admin/exports").status_code for _ in range(2)][-1] == 429
