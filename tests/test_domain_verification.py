"""Domain verification proves control for real (a token published over HTTPS, fetched through the outbound policy),
and identity-provider verification is refused: single sign-on is not part of this release."""

import io
import uuid
from urllib.error import HTTPError

import pytest

from backend.app.access import outbound, platform_onboarding
from tests.conftest import authenticated_client


@pytest.fixture(scope="module")
def platform():
    return authenticated_client()


@pytest.fixture(scope="module")
def tenant_id(platform):
    code = f"DOM{uuid.uuid4().hex[:6].upper()}"
    created = platform.post(
        "/api/v1/platform-admin/customers",
        json={"company_name": f"Domain Test {code}", "tenant_code": code, "plan_code": "STARTER"},
    )
    assert created.status_code == 200, created.text
    return created.json()["id"]


def _domain() -> str:
    return f"verify-{uuid.uuid4().hex[:8]}.example.com"


def _verify(platform, tenant_id, **body):
    return platform.post(f"/api/v1/platform-admin/tenants/{tenant_id}/domain-verifications", json=body)


def test_a_domain_is_verified_only_when_it_publishes_the_issued_token(platform, tenant_id, monkeypatch):
    domain = _domain()
    issued = _verify(platform, tenant_id, domain=domain)
    assert issued.status_code == 200, issued.text
    body = issued.json()
    token = body["verification_token"]
    assert body["status"] == "PENDING" and token.startswith("mdarix-verify-")
    assert body["proof_url"] == f"https://{domain}/.well-known/mdarix-verify.txt"

    published = {"content": "something else\n"}
    fetched = []

    def fake_fetch(name, timeout=5.0):
        fetched.append(name)
        return published["content"], None

    monkeypatch.setattr(platform_onboarding, "fetch_domain_proof", fake_fetch)
    mismatch = _verify(platform, tenant_id, domain=domain, verification_token=token).json()
    assert mismatch["status"] == "PENDING" and mismatch["last_error"] == "PROOF_MISMATCH"
    assert mismatch["last_checked_at"] and fetched == [domain]

    published["content"] = f"# MDARIX\n{token}\n"
    verified = _verify(platform, tenant_id, domain=domain, verification_token=token).json()
    assert verified["status"] == "VERIFIED" and verified["verified_at"] and verified["last_error"] is None


def test_an_unreachable_domain_stays_pending_with_the_reason(platform, tenant_id, monkeypatch):
    monkeypatch.setattr(platform_onboarding, "fetch_domain_proof", lambda name, timeout=5.0: (None, "PROOF_NOT_FOUND"))
    result = _verify(platform, tenant_id, domain=_domain(), verification_token="customer-chosen-token").json()
    assert result["status"] == "PENDING" and result["last_error"] == "PROOF_NOT_FOUND"


@pytest.mark.parametrize("domain", ["127.0.0.1", "localhost", "intranet", "exa mple.com", "-bad.example.com"])
def test_only_public_domain_names_are_accepted(platform, tenant_id, domain):
    refused = _verify(platform, tenant_id, domain=domain, verification_token="whatever-token")
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "DOMAIN_INVALID"


def test_the_proof_is_fetched_safely(monkeypatch):
    def blocked(request, timeout):
        assert request.full_url == "https://example.com/.well-known/mdarix-verify.txt"
        raise outbound.ConnectorDestinationBlocked("CONNECTOR_PRIVATE_DESTINATION_BLOCKED")

    monkeypatch.setattr(outbound, "safe_urlopen", blocked)
    assert platform_onboarding.fetch_domain_proof("example.com") == (None, "PROOF_DESTINATION_BLOCKED")

    def redirect(request, timeout):
        raise HTTPError(request.full_url, 302, "Found", {}, io.BytesIO(b""))

    monkeypatch.setattr(outbound, "safe_urlopen", redirect)
    assert platform_onboarding.fetch_domain_proof("example.com") == (None, "PROOF_REDIRECT_NOT_FOLLOWED")

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(outbound, "safe_urlopen", lambda request, timeout: Response(b"x" * 5000))
    assert platform_onboarding.fetch_domain_proof("example.com") == (None, "PROOF_TOO_LARGE")
    monkeypatch.setattr(outbound, "safe_urlopen", lambda request, timeout: Response(b"mdarix-verify-abc\n"))
    assert platform_onboarding.fetch_domain_proof("example.com") == ("mdarix-verify-abc\n", None)


def test_identity_provider_verification_is_not_available(platform, tenant_id):
    refused = platform.post(
        f"/api/v1/platform-admin/tenants/{tenant_id}/identity-provider/verify",
        json={"provider_type": "OIDC", "issuer": "https://login.example.com"},
    )
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "SSO_NOT_AVAILABLE"
