"""Every administration route refuses people who may not use it.

Walks all routes under /api/v1/admin, /api/v1/platform-admin, /api/v1/platform/, /api/v1/customer-admin and
/api/v1/me (so a route added later is covered without a code change) and calls each one:

* with no session: never a success, never a server error;
* as a business user (Investigator): platform routes are refused.

Body validation (422) may answer before the permission check; it returns no data, so it counts as a refusal.
"""

import re
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from tests.route_inventory import api_routes
from tests.test_business_permissions import _client_with_role

PREFIXES = ("/api/v1/admin", "/api/v1/platform-admin", "/api/v1/platform/", "/api/v1/customer-admin", "/api/v1/me")
REFUSED = {401, 403, 404, 405, 422}


def _url(path: str) -> str:
    def value(match: re.Match) -> str:
        name = match.group(1)
        return str(uuid.uuid4()) if name.endswith("id") or name == "tenant" else "x"

    return re.sub(r"\{([^}:]+)(?::[^}]*)?\}", value, path)


def _routes():
    seen = set()
    for path, route in api_routes(app):
        if not path.startswith(PREFIXES):
            continue
        for method in sorted(route.methods & {"GET", "POST", "PUT", "PATCH", "DELETE"}):
            if (method, path) not in seen:
                seen.add((method, path))
                yield method, path


ROUTES = list(_routes())


def _call(client: TestClient, method: str, path: str):
    kwargs = {} if method in {"GET", "DELETE"} else {"json": {}}
    return client.request(method, _url(path), **kwargs)


def test_the_walk_sees_the_administration_routes():
    # A broken route walker would otherwise pass vacuously.
    assert len(ROUTES) > 150


@pytest.mark.parametrize(("method", "path"), ROUTES, ids=[f"{m} {p}" for m, p in ROUTES])
def test_no_administration_route_answers_without_a_session(method, path):
    response = _call(TestClient(app), method, path)
    assert response.status_code in REFUSED, f"{method} {path} -> {response.status_code}"


PLATFORM_ROUTES = [(m, p) for m, p in ROUTES if p.startswith(("/api/v1/platform-admin", "/api/v1/platform/"))]


@pytest.fixture(scope="module")
def business_user():
    return _client_with_role("Investigator")


@pytest.mark.parametrize(("method", "path"), PLATFORM_ROUTES, ids=[f"{m} {p}" for m, p in PLATFORM_ROUTES])
def test_platform_routes_refuse_a_business_user(business_user, method, path):
    response = _call(business_user, method, path)
    assert response.status_code in REFUSED, f"{method} {path} -> {response.status_code}"
