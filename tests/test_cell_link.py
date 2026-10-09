"""The platform-cell link (ADR-014): enrollment, heartbeats, packages, the licence and its grace period.

The platform's routes are served by this MULTI test deployment; the cell's side (backend/app/cell_link.py) runs in
the same process with its HTTPS transport routed into the application, forwarding the fingerprint of the
certificate the cell would present, as the platform's front door does.
"""

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import cell_link
from backend.app.cell_licence import apply_licence, licence_content
from backend.app.cell_packages import generate_keypair, sign
from backend.app.cell_pki import (
    certificate_common_name,
    csr_pem,
    fingerprint,
    generate_ca,
    generate_key,
    platform_ca_problem,
    sign_csr,
)
from backend.app.db.models.customer_lifecycle import Cell, CellHeartbeat, CellLicence, CellPackageState, ReceivedPackage
from backend.app.db.models.foundation import Tenant
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.main import app
from scripts import cell_platform
from tests.conftest import authenticated_client
from tests.test_deployment_roles import _set_role
from tests.test_mapping_release_self_approval import _admin, _organization

PLATFORM = "https://platform.test"
HEARTBEAT = "/api/v1/cells/heartbeat"
CONTEXT = "/api/v1/session/context"


@pytest.fixture
def platform(monkeypatch, tmp_path):
    """The platform's keys for this process: the package-signing pair and the certificate authority files."""
    private, public = generate_keypair()
    ca_key, ca_cert = generate_ca()
    (tmp_path / "ca.key").write_text(ca_key, encoding="ascii")
    (tmp_path / "ca.crt").write_text(ca_cert, encoding="ascii")
    monkeypatch.setenv("MDARIX_PLATFORM_SIGNING_PUBLIC_KEY", public)
    monkeypatch.setenv("MDARIX_PLATFORM_CA_KEY_FILE", str(tmp_path / "ca.key"))
    monkeypatch.setenv("MDARIX_PLATFORM_CA_CERT_FILE", str(tmp_path / "ca.crt"))
    monkeypatch.setenv("MDARIX_CELL_MTLS_REQUIRED", "true")
    monkeypatch.setenv("MDARIX_PLATFORM_URL", PLATFORM)
    monkeypatch.setenv("MDARIX_CELL_IDENTITY_DIR", str(tmp_path / "identity"))
    monkeypatch.delenv("MDARIX_CELL_ENROLLMENT_TOKEN", raising=False)
    cell_link.clear_cache()
    return {"private": private, "public": public, "ca_cert": ca_cert}


def _tenant(tenant_id: str) -> Tenant:
    db = SessionLocal()
    try:
        bind_system(db, "test: read the organization")
        row = db.query(Tenant).filter(Tenant.id == uuid.UUID(tenant_id)).one()
        db.expunge(row)
        return row
    finally:
        db.close()


def _issue(tenant_key: str, private: str) -> tuple[dict, dict]:
    db = SessionLocal()
    try:
        return cell_platform.issue(
            db,
            tenant_key,
            hosting_mode="CUSTOMER_CLOUD",
            admin_email="admin@cell.invalid",
            admin_name="Cell Admin",
            private_key=private,
            platform_url=PLATFORM,
        )
    finally:
        db.close()


def _into_the_app(client: TestClient):
    """The cell's transport, routed into the application like the platform's front door: the fingerprint of the
    certificate the cell would present travels in the header the front door sets."""

    def transport(method, url, body, headers, who, timeout):
        extra = dict(headers)
        if who and who.get("certificate_file"):
            extra["X-Client-Certificate-Fingerprint"] = fingerprint(Path(who["certificate_file"]).read_text("ascii"))
        response = client.request(method, url.removeprefix(PLATFORM), json=body, headers=extra)
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        return response.status_code, payload

    return transport


def _cell_row(tenant_id) -> Cell:
    db = SessionLocal()
    try:
        bind_system(db, "test: read the cell")
        row = db.query(Cell).filter(Cell.tenant_id == tenant_id).one()
        db.expunge(row)
        return row
    finally:
        db.close()


def test_certificates_round_trip_under_the_platform_authority(platform, tmp_path):
    assert platform_ca_problem() is None
    key = generate_key()
    ca_key, ca_cert = generate_ca()
    certificate = sign_csr(csr_pem(key, "cell:ACME"), ca_key, ca_cert, common_name="cell:ACME")
    assert certificate_common_name(certificate) == "cell:ACME"
    assert len(fingerprint(certificate)) == 64 and fingerprint(certificate) != fingerprint(platform["ca_cert"])


def test_a_cell_enrolls_once_reports_metadata_and_receives_the_licence_and_packages(platform, monkeypatch):
    organization = _tenant(_organization())
    enrollment, licence = _issue(organization.tenant_key, platform["private"])
    token = enrollment["content"]["enrollment_token"]
    assert enrollment["content"]["platform_url"] == PLATFORM and _cell_row(organization.id).status == "PROVISIONING"
    monkeypatch.setattr(cell_link, "_transport", _into_the_app(TestClient(app)))
    monkeypatch.setenv("MDARIX_CELL_ENROLLMENT_TOKEN", token)

    # A platform administrator releases a signed package; tampered or repeated uploads are refused.
    admin = authenticated_client()
    package = sign(
        "REFERENCE_DATA",
        {"code": "IMDRF_CODES", "version": f"2026.{uuid.uuid4().hex[:8]}", "codes": ["A01"]},
        platform["private"],
    )
    uploaded = admin.post("/api/v1/platform-admin/packages", json={"envelope": package})
    assert uploaded.status_code == 200, uploaded.text
    assert admin.post("/api/v1/platform-admin/packages", json={"envelope": package}).status_code == 409
    tampered = {**package, "content": {**package["content"], "codes": ["B02"]}}
    assert admin.post("/api/v1/platform-admin/packages", json={"envelope": tampered}).status_code == 422
    assert admin.post("/api/v1/platform-admin/packages", json={"envelope": licence}).status_code == 422  # not a package

    with SessionLocal() as db:
        bind_system(db, "test: the cell's first sync")
        first = cell_link.sync(db, organization.id, organization.tenant_key)
    assert first["enrolled"] and first["heartbeat"] == "SENT"
    assert first["licence"]["status"] == "APPLIED"
    # Packages are offered to every cell: other released packages (from other runs) arrive too, all as OFFERED.
    package_id = uploaded.json()["id"]
    assert {item["status"] for item in first["packages"]} == {"OFFERED"}
    assert package_id in {item["id"] for item in first["packages"]}
    who = cell_link.identity()
    assert (
        who
        and certificate_common_name(Path(who["certificate_file"]).read_text("ascii"))
        == f"cell:{organization.tenant_key}"
    )
    cell = _cell_row(organization.id)
    assert cell.status == "ACTIVE" and cell.enrollment_token_hash is None
    assert cell.client_certificate_fingerprint == fingerprint(Path(who["certificate_file"]).read_text("ascii"))
    assert cell.health in {"ok", "degraded", "down"} and cell.last_heartbeat["counts"]["users_active"] >= 0
    assert all(job["status"] in {"OK", "FAILED", "NEVER"} for job in cell.last_heartbeat["jobs"])

    # The token is spent: a second enrollment needs a new bundle.
    with SessionLocal() as db, pytest.raises(cell_link.LinkError, match="ENROLLMENT_REFUSED:CELL_ALREADY_ENROLLED"):
        bind_system(db, "test: enroll again")
        cell_link.enroll(db, organization.id, organization.tenant_key, token)

    # The next round: nothing to enroll, the licence is current, the package state is reported to the platform.
    monkeypatch.delenv("MDARIX_CELL_ENROLLMENT_TOKEN")
    with SessionLocal() as db:
        bind_system(db, "test: the cell's second sync")
        second = cell_link.sync(db, organization.id, organization.tenant_key)
        assert not second["enrolled"] and second["licence"]["status"] == "CURRENT"
        assert db.query(CellHeartbeat).filter(CellHeartbeat.tenant_id == organization.id).count() == 2
        assert db.query(CellLicence).filter(CellLicence.tenant_id == organization.id).one().status == "ACTIVE"
        received = db.query(ReceivedPackage).filter(ReceivedPackage.id == uuid.UUID(package_id)).one()
        assert (received.kind, received.code, received.version, received.status) == (
            "REFERENCE_DATA",
            "IMDRF_CODES",
            package["content"]["version"],
            "OFFERED",
        )
        reported = (
            db.query(CellPackageState)
            .filter(CellPackageState.tenant_id == organization.id, CellPackageState.package_id == uuid.UUID(package_id))
            .one()
        )
        assert reported.state == "OFFERED" and str(reported.package_id) == uploaded.json()["id"]

    fleet = admin.get("/api/v1/platform-admin/console/cells")
    assert fleet.status_code == 200, fleet.text
    mine = next(item for item in fleet.json()["items"] if item["tenant_key"] == organization.tenant_key)
    assert mine["contact"] == "CURRENT" and mine["status"] == "ACTIVE" and mine["hosting_mode"] == "CUSTOMER_CLOUD"
    assert mine["licence_status"] == "ACTIVE" and mine["packages"].get("OFFERED", 0) >= 1
    assert "patient" not in fleet.text.lower()
    listed = admin.get("/api/v1/platform-admin/packages").json()["items"]
    assert next(item for item in listed if item["id"] == package_id)["cells"] == {"OFFERED": 1}

    # A withdrawn package is no longer offered.
    assert admin.post(f"/api/v1/platform-admin/packages/{uploaded.json()['id']}/withdraw").status_code == 200
    status, listing = cell_link._call("GET", "/api/v1/cells/packages", None, cell_link.identity())
    assert status == 200 and listing["licence"]["content_sha256"] == licence["content_sha256"]
    assert package_id not in {item["id"] for item in listing["packages"]}


def test_the_heartbeat_refuses_free_text_unknown_fields_and_strangers(platform, monkeypatch):
    organization = _tenant(_organization())
    enrollment, _ = _issue(organization.tenant_key, platform["private"])
    client = TestClient(app)
    monkeypatch.setattr(cell_link, "_transport", _into_the_app(client))
    with SessionLocal() as db:
        bind_system(db, "test: enroll")
        cell_link.enroll(db, organization.id, organization.tenant_key, enrollment["content"]["enrollment_token"])
    who = cell_link.identity()
    print_ = fingerprint(Path(who["certificate_file"]).read_text("ascii"))
    headers = {"Authorization": f"Bearer {who['credential']}", "X-Client-Certificate-Fingerprint": print_}
    good = {
        "software_version": "v1.2.3",
        "schema_version": "md37platformcelllink",
        "health": "ok",
        "uptime_seconds": 10,
        "jobs": [{"name": "signal_detection", "status": "OK", "error_type": None}],
        "counts": {"products": 3},
        "packages": [],
    }
    assert client.post(HEARTBEAT, json=good, headers=headers).status_code == 200
    for bad in (
        {**good, "note": "patient Jane Doe"},
        {**good, "software_version": "v1 patient Jane"},
        {**good, "jobs": [{"name": "x", "status": "OK", "message": "failed for Jane"}]},
        {**good, "counts": {"patient name": 1}},
        {**good, "health": "fine"},
    ):
        assert client.post(HEARTBEAT, json=bad, headers=headers).status_code == 422, bad
    assert (
        client.post(HEARTBEAT, json=good, headers={**headers, "Authorization": "Bearer not-a-credential"}).status_code
        == 401
    )
    assert client.post(HEARTBEAT, json=good, headers={"Authorization": headers["Authorization"]}).status_code == 401
    assert (
        client.post(HEARTBEAT, json=good, headers={**headers, "X-Client-Certificate-Fingerprint": "0" * 64}).status_code
        == 401
    )
    assert client.get("/api/v1/cells/packages", headers=headers).status_code == 200


def test_an_expired_licence_makes_a_cell_read_only_after_the_grace_period(platform, monkeypatch):
    organization = _tenant(_organization())
    admin, _ = _admin(str(organization.id))
    now = datetime.now(timezone.utc)
    private, public = platform["private"], platform["public"]

    def licence(valid_until, applied_at):
        with SessionLocal() as db:
            bind_system(db, "test: a licence")
            tenant = db.query(Tenant).filter(Tenant.id == organization.id).one()
            plan, entitlements, assignment = cell_platform.active_plan(db, tenant)
            content = licence_content(
                tenant, plan, entitlements, assignment.limits, issued_at=now, valid_until=valid_until
            )
            apply_licence(db, sign("LICENCE", content, private), public, now=applied_at)
            return cell_link.licence_state(db, organization.id, now=now)

    assert licence(now - timedelta(days=1), now)["state"] == "GRACE"
    expired = licence(now - timedelta(days=40), now + timedelta(seconds=1))
    assert expired["state"] == "EXPIRED" and expired["read_only"]
    assert cell_link.read_only() is None  # not a cell: the plans apply as before

    _set_role(monkeypatch, "CELL", organization)
    cell_link.clear_cache()
    context = admin.get(CONTEXT)
    assert context.status_code == 200 and context.json()["licence"]["state"] == "EXPIRED"
    refused = admin.post(
        "/api/v1/admin/configuration/mappings",
        json={"code": "RO-1", "source_system": "TRACKWISE", "target_entity": "Complaint", "mapping_rules": {}},
    )
    assert refused.status_code == 423 and refused.json()["detail"]["code"] == "LICENCE_EXPIRED"
    # Reading, and signing in, still work.
    assert admin.get("/api/v1/admin/configuration/mappings").status_code == 200
    assert (
        TestClient(app).post("/api/v1/auth/signin", json={"email": "x@y.invalid", "password": "nope"}).status_code
        == 401
    )

    renewed = licence(None, now + timedelta(seconds=2))
    assert renewed["state"] == "VALID"
    cell_link.clear_cache()
    assert (
        admin.post(
            "/api/v1/admin/configuration/mappings",
            json={"code": "RO-2", "source_system": "TRACKWISE", "target_entity": "Complaint", "mapping_rules": {}},
        ).status_code
        != 423
    )
