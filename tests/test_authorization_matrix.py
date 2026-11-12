"""DEV-08: the authorization and tenant-isolation matrix, generated from the application's route table.

Actors x actions x states, executed against the real API (least-privilege runtime role, row-level security, pooled
connections). Every /api/v1 route is in the matrix: a new route is classified from its guard, and a route that opens to
someone the matrix says must be refused fails here.

- Actors: the trial owner, colleagues given each persona, a colleague with two personas, a Viewer with a persona view
  only, a Reviewer, a Customer Administrator, a Platform Administrator.
- States that must reach nothing: no session, a signed-out (reused) token, an idle session, a session past its
  absolute end, a session still owing MFA, a removed colleague, a suspended membership, an ended trial.
- Actions: read, write, export, search, download and background work (each route is labelled; the assertion is the
  same for all of them).

Related tests kept where they are: cross-tenant reads with real record IDs (test_cross_tenant_routes.py), the guard on
every business write (test_business_permissions.py), RLS under the runtime role (test_row_level_security.py), support
grants (test_trial_support_workspace.py, test_support_access_*.py), additional roles (test_additional_roles.py).
"""

from __future__ import annotations

import re
import secrets
import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from auth.durable import new_session
from auth.service import _hash
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
)
from backend.app.db.models.foundation import AuthUser, TenantMembership
from backend.app.db.models.stage2 import AuthSession, SubscriptionLifecycle
from backend.app.db.session import SessionLocal, runtime_engine, runtime_role_active
from backend.app.db.tenant_scope import bind_system
from backend.app.main import app
from tests.route_inventory import api_routes

METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")

# Routes anyone may call without a session, each with its reason. Anything else must refuse every dead state below.
PUBLIC = {
    ("GET", "/health"): "liveness",
    ("GET", "/health/live"): "liveness",
    ("GET", "/health/ready"): "readiness probe",
    ("GET", "/health/status"): "status probe",
    ("GET", "/health/version"): "the deployed release only",
    ("GET", "/api/v1/public/testimonials"): "published testimonials (website)",
    ("GET", "/api/v1/public/site-info"): "website facts",
    ("GET", "/api/v1/public/version"): "the deployed release only",
    ("GET", "/api/v1/public/legal/{document}"): "published legal texts",
    ("POST", "/api/v1/public/demo-requests"): "website form, rate limited",
    ("POST", "/api/v1/client-errors"): "error reports from the sign-in page, rate limited",
    ("POST", "/api/v1/auth/signup"): "trial request",
    ("POST", "/api/v1/auth/signin"): "sign-in",
    ("POST", "/api/v1/auth/signout"): "ends the caller's own session, whatever its state",
    ("POST", "/api/v1/auth/forgot-password"): "same answer for every email",
    ("POST", "/api/v1/auth/link-status"): "a one-time link's own state",
    ("POST", "/api/v1/auth/reset-password"): "a one-time link",
    ("POST", "/api/v1/auth/activate-account"): "a one-time link",
    ("POST", "/api/v1/cells/enroll"): "a cell's one-time enrollment token, not a person",
    ("POST", "/api/v1/cells/heartbeat"): "a cell's own credential, not a person",
    ("POST", "/api/v1/communication/resend/webhook"): "provider webhook, signature checked",
    ("POST", "/api/v1/stage3/resend/webhook"): "provider webhook, signature checked",
}
# The second-factor steps a session that still owes MFA may use (and nothing else): the steps themselves, and the
# session check that tells the browser a code is due (it names the person, whose password was just given).
MFA_STEPS = ("/api/v1/auth/mfa/", "/api/v1/auth/session")
# What a refused dead session may be told: never a permission or business code, which would mean it got past the
# session check.
ACCESS_ENDED = {
    "UNAUTHENTICATED",
    "SESSION_IDLE_TIMEOUT",
    "MFA_REQUIRED",
    "MFA_ENROLLMENT_REQUIRED",
    "TRIAL_ENDED",
    "MEMBERSHIP_SUSPENDED",
    "TENANT_ACCESS_SUSPENDED",
    "CELL_CREDENTIAL_REQUIRED",
    "INVALID_WEBHOOK_SIGNATURE",
}
ADMIN_PREFIXES = ("/api/v1/admin", "/api/v1/customer-admin")
PLATFORM_PREFIXES = ("/api/v1/platform-admin", "/api/v1/platform/")
SKIP_POSITIVE = {"/api/v1/evaluations/runs"}
# Routes under /admin that are not for a customer's administrator, each with who it is for (reviewed): the matrix
# expects exactly these refusals of a Customer Administrator or a Platform Administrator there.
ADMIN_ROUTES_FOR = {
    # MDARIX's own configuration and the shared mapping catalog: the Platform Administrator only.
    **{
        path: {"PLATFORM_ADMIN"}
        for path in (
            "/api/v1/admin/smtp-status",
            "/api/v1/admin/catalog/master-mappings",
            "/api/v1/admin/mapping/canonical/entities",
            "/api/v1/admin/mapping/canonical/entities/{entity_id}/fields",
            "/api/v1/admin/mapping/transforms",
            "/api/v1/admin/mapping/validation-rules",
            "/api/v1/admin/mapping/override-policies",
            "/api/v1/admin/mapping/source-priorities",
            "/api/v1/admin/mapping/families",
            "/api/v1/admin/mapping/connector-versions",
            "/api/v1/admin/mapping/initial-mappings",
            "/api/v1/admin/mapping/validation-decisions",
            "/api/v1/admin/mapping/impact-history",
        )
    },
    # Support access is decided by the customer's own administrator, never MDARIX; in a trial by its owner only
    # (/trial/support-access, test_trial_support_workspace.py), so in this trial nobody here.
    "/api/v1/admin/support-access": set(),
    "/api/v1/admin/support-access/{grant_id}/activity": set(),
}  # a long real-pipeline run; tenant scope in test_evaluation_router.py

_WORK = {RECORDS_WRITE, AI_RUN, DATA_EXPORT}
_EVIDENCE = {EVIDENCE_REVIEW, EVIDENCE_REQUEST}
# The reviewed role matrix: what each role may do. Signing also needs an approval authority and segregation of duties
# (checked in the signing routes); administrators never hold DECISION_SIGN through a customer role.
ROLE_MATRIX = {
    "VIEWER": set(),
    # 0.10.93 (B2, spec 6.3, OD-4): case.log, case.classify, complaint.triage; the Service Desk role.
    "SERVICE_DESK": {RECORDS_WRITE, "case.log", "case.classify"},
    "TRIAGE_LEAD": _WORK
    | {SIGNAL_TRIAGE, INVESTIGATION_CREATE, INVESTIGATION_ASSIGN, "case.log", "case.classify", "complaint.triage"},
    "INVESTIGATOR": _WORK | _EVIDENCE | {INVESTIGATION_CREATE, INVESTIGATION_WORK, "case.log"},
    "RISK_REVIEWER": {AI_RUN, DATA_EXPORT, RISK_REVIEW} | _EVIDENCE,
    "REGULATORY_REVIEWER": {AI_RUN, DATA_EXPORT, REGULATORY_REVIEW, REGULATORY_APPROVE, "complaint.triage"} | _EVIDENCE,
    "REVIEWER": _WORK
    | _EVIDENCE
    | {QUALITY_REVIEW, INVESTIGATION_ASSIGN, "case.log", "case.classify", "complaint.triage"},
    "APPROVER": _WORK | {REGULATORY_APPROVE, DECISION_SIGN},
    "LEADER": set(ALL),
    "CUSTOMER_ADMIN": set(_WORK),
    "PLATFORM_ADMIN": set(ALL),
    "SOMETHING_CUSTOM": set(),
}


# ------------------------------------------------------------------------------------------------ the route table


# B6b B3: the scenarios this file verifies (requirements.csv, class A); file level, so every test here carries them.
pytestmark = pytest.mark.requirement("DT-13")


def _walk(dependant):
    for dep in dependant.dependencies:
        yield dep
        yield from _walk(dep)


def guard_permissions(route) -> frozenset[str] | None:
    """The permissions a route's guard accepts (any one of them), or None when it has no permission guard."""
    for dep in _walk(route.dependant):
        name = getattr(dep.call, "__qualname__", "")
        if "require_permission" in name or "require_any_permission" in name:
            cells = [cell.cell_contents for cell in (dep.call.__closure__ or ())]
            found = {value for value in cells if isinstance(value, str) and value in ALL}
            found |= {item for value in cells if isinstance(value, tuple) for item in value if item in ALL}
            return frozenset(found)
    return None


def action_kind(method: str, path: str) -> str:
    """The matrix's action column for a route."""
    if re.search(r"/jobs\b|/runs?\b|/run-|/index\b|/process\b|/retry\b|/sync\b|retention/run", path):
        return "background"
    if re.search(r"/download|/file\b|/content\b|/attachments/\{", path) and method == "GET":
        return "download"
    if re.search(r"export|dossier|\.csv|estar|/pdf|/docx|evidence-package", path):
        return "export"
    if re.search(r"search|/ask\b|/retrieval/|/query\b", path):
        return "search"
    return "read" if method == "GET" else "write"


def route_class(method: str, path: str, route) -> str:
    """The access class the matrix expects of a route."""
    if (method, path) in PUBLIC:
        return "public"
    if path.startswith(PLATFORM_PREFIXES):
        return "platform-admin"
    if path.startswith(ADMIN_PREFIXES):
        return "administrator"
    permissions = guard_permissions(route)
    if permissions:
        return "permission"
    return "signed-in"


def matrix_routes():
    for path, route in api_routes(app):
        if not (path.startswith("/api/v1/") or path.startswith("/health")):
            continue
        for method in METHODS:
            if method in route.methods:
                yield method, path, route


def _sample(schema: dict, defs: dict, name: str = ""):
    """A value that satisfies a JSON schema well enough to pass request validation (so a guard that runs after
    validation is reached). Not a meaningful record: every caller of it must be refused before anything is saved."""
    if "$ref" in schema:
        return _sample(defs[schema["$ref"].split("/")[-1]], defs, name)
    for key in ("anyOf", "oneOf", "allOf"):
        if key in schema:
            options = [item for item in schema[key] if item.get("type") != "null"] or schema[key]
            return _sample(options[0], defs, name)
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    if "default" in schema and schema["default"] is not None:
        return schema["default"]
    kind = schema.get("type")
    if kind == "string":
        fmt = schema.get("format", "")
        if fmt == "uuid" or name.endswith("_id"):
            return str(uuid.uuid4())
        if fmt == "date-time":
            return datetime.now(timezone.utc).isoformat()
        if fmt == "date":
            return datetime.now(timezone.utc).date().isoformat()
        if fmt == "email" or "email" in name:
            return "matrix-check@example.invalid"
        pattern = schema.get("pattern", "")
        if re.fullmatch(r"\^\(([A-Za-z0-9_|]+)\)\$", pattern):
            return pattern[2:-2].split("|")[0]  # ^(A|B|C)$: one of the listed values
        if pattern:
            return "MATRIX-1"
        size = max(int(schema.get("minLength", 0)), 24)
        return ("Matrix check value " * 10)[: min(size, int(schema.get("maxLength", size)))]
    if kind in {"integer", "number"}:
        return schema.get("minimum", schema.get("exclusiveMinimum", 0) + 1)
    if kind == "boolean":
        return True
    if kind == "array":
        return [_sample(schema.get("items", {}), defs, name) for _ in range(int(schema.get("minItems", 0)))]
    if kind == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        return {key: _sample(properties[key], defs, key) for key in schema.get("required", []) if key in properties}
    return "x"


_BODIES: dict[int, object] = {}


def valid_body(route):
    if id(route) not in _BODIES:
        _BODIES[id(route)] = _valid_body(route)
    return _BODIES[id(route)]


def _valid_body(route):
    field = route.body_field
    if field is None:
        return None
    from pydantic import TypeAdapter

    try:
        schema = TypeAdapter(field.field_info.annotation).json_schema()
    except Exception:
        return {}
    return _sample(schema, schema.get("$defs", {}))


def url_for(path: str) -> str:
    return re.sub(
        r"\{([^}:]+)(?::[^}]*)?\}", lambda m: "products" if m.group(1) == "entity" else str(uuid.uuid4()), path
    )


def sweep(client: TestClient, calls: list[tuple[str, str, object]], workers: int = 6) -> list:
    """Send (method, url, json) calls with ``client``'s cookies on a few threads (one client each, the real pooled
    connections underneath); the responses come back in the order of ``calls``."""
    import logging
    from concurrent.futures import ThreadPoolExecutor

    local = threading.local()
    cookies = dict(client.cookies)
    headers = {key: value for key, value in client.headers.items() if key.lower() in {"origin", "referer"}}

    def send(call):
        if not hasattr(local, "client"):
            local.client = TestClient(app, raise_server_exceptions=False, cookies=cookies, headers=headers)
        method, url, body = call
        return local.client.request(method, url, json=body)

    quiet = [logging.getLogger(name) for name in ("mdarix.api", "httpx")]
    levels = [logger.level for logger in quiet]
    for logger in quiet:
        logger.setLevel(logging.WARNING)
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(send, calls))
    finally:
        for logger, level in zip(quiet, levels):
            logger.setLevel(level)


def _code(response) -> str | None:
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        return None
    return detail.get("code") if isinstance(detail, dict) else None


@pytest.mark.unit
def test_every_route_has_a_place_in_the_matrix():
    rows = list(matrix_routes())
    assert len(rows) > 600, f"only {len(rows)} routes found; the route walker may be broken"
    classes = {route_class(method, path, route) for method, path, route in rows}
    assert classes == {"public", "platform-admin", "administrator", "permission", "signed-in"}
    kinds = {action_kind(method, path) for method, path, _ in rows}
    assert kinds == {"read", "write", "export", "search", "download", "background"}
    present = {(method, path) for method, path, _ in rows}
    assert set(PUBLIC) <= present, f"PUBLIC lists routes that no longer exist: {sorted(set(PUBLIC) - present)}"
    # Every permission a guard names is in the reviewed role matrix.
    named = set().union(*(guard_permissions(route) or set() for _, _, route in rows))
    assert named and named <= set(ALL)


@pytest.mark.unit
def test_the_reviewed_role_matrix_is_the_one_the_server_applies():
    for role, allowed in ROLE_MATRIX.items():
        assert permissions_for_role(role) == allowed, role


@pytest.mark.unit
def test_the_body_sampler_passes_validation_so_late_guards_are_reached():
    """The dead-state sweep sends a valid body so a guard that runs after validation is the one that answers."""
    from backend.app.trial.router import ColleagueInvite

    route = next(r for p, r in api_routes(app) if p == "/api/v1/trial/team" and "POST" in r.methods)
    assert route.body_field.field_info.annotation is ColleagueInvite
    ColleagueInvite(**valid_body(route))


# ---------------------------------------------------------------------------------------------------- the world


def _db():
    db = SessionLocal()
    bind_system(db, "test: authorization matrix fixtures")
    return db


def _client(token: str) -> TestClient:
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set("mdarix_session", token)
    return client


def _session_for(user_id, tenant_id, **changes) -> str:
    db = _db()
    try:
        token = new_session(db, user_id, tenant_id, mfa_state=changes.pop("mfa_state", None))
        db.flush()
        row = db.query(AuthSession).order_by(AuthSession.created_at.desc()).first()
        from auth.durable import hash_token

        row = db.query(AuthSession).filter(AuthSession.session_hash == hash_token(token)).one()
        for key, value in changes.items():
            setattr(row, key, value)
        db.commit()
        return token
    finally:
        db.close()


def _account(tenant_id, role: str, *, membership: str = "ACTIVE", view_persona: str | None = None):
    db = _db()
    try:
        now = datetime.now(timezone.utc)
        user = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            username=f"matrix-{role.lower()}-{uuid.uuid4().hex[:8]}@example.invalid",
            display_name=f"Matrix {role}",
            company="Matrix",
            password_hash=_hash("Matrix check 2026!"),
            role=role,
            view_persona=view_persona,
            status="ACTIVE",
            email_verified=True,
            created_at=now,
            updated_at=now,
        )
        db.add(user)
        db.flush()
        db.add(
            TenantMembership(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                user_id=user.id,
                status=membership,
                is_default=True,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        return user.id
    finally:
        db.close()


def _token_of(client: TestClient) -> str:
    return client.cookies.get("mdarix_session")


PERSONA_ACTORS = {
    # actor: (personas the owner gives, the roles that follow)
    "viewer": (["executive"], {"VIEWER"}),
    "handler": (["handler"], {"TRIAGE_LEAD"}),
    "investigator": (["investigator"], {"INVESTIGATOR"}),
    "risk": (["risk"], {"RISK_REVIEWER"}),
    "regulatory": (["regulatory"], {"REGULATORY_REVIEWER"}),
    "approver": (["decision"], {"APPROVER"}),
    "multi_role": (["investigator", "decision"], {"INVESTIGATOR", "APPROVER"}),
}


@pytest.fixture(scope="module")
def world():
    import os

    from tests.test_free_trial import (
        _activate_and_sign_in,
        _activation_token,
        _approved_trial_client,
        _purge_trial_business_data,
    )

    previous = os.environ.get("MDARIX_FEATURE_SET")
    os.environ["MDARIX_FEATURE_SET"] = "full"  # every route served, so the guards themselves answer
    _purge_trial_business_data()
    try:
        owner, approval, owner_email = _approved_trial_client()
        tenant_id = uuid.UUID(approval["tenant_id"])
        actors: dict[str, tuple[TestClient, set[str]]] = {"owner": (owner, {"LEADER"})}
        people: dict[str, tuple[str, str]] = {}
        for name, (personas, roles) in [*PERSONA_ACTORS.items(), ("leaver", (["investigator"], set()))]:
            email = f"matrix-{name}-{uuid.uuid4().hex[:6]}@example.invalid"
            invited = owner.post(
                "/api/v1/trial/team", json={"email": email, "display_name": name, "personas": personas}
            )
            assert invited.status_code == 200, invited.text
            client = _activate_and_sign_in(email, _activation_token(invited.json(), email))
            people[name] = (invited.json()["id"], email)
            actors[name] = (client, roles)
        # A Viewer whose persona view says "Decision Maker": a view only, never a permission.
        persona_only = _account(tenant_id, "Viewer", view_persona="decision")
        actors["persona_only"] = (_client(_session_for(persona_only, tenant_id)), {"VIEWER"})
        reviewer = _account(tenant_id, "Reviewer")
        actors["reviewer"] = (_client(_session_for(reviewer, tenant_id)), {"REVIEWER"})
        customer_admin = _account(tenant_id, "CUSTOMER_ADMIN")
        actors["customer_admin"] = (_client(_session_for(customer_admin, tenant_id)), {"CUSTOMER_ADMIN"})
        platform_admin = _account(tenant_id, "PLATFORM_ADMIN")
        actors["platform_admin"] = (_client(_session_for(platform_admin, tenant_id)), {"PLATFORM_ADMIN"})

        # The states that must reach nothing.
        now = datetime.now(timezone.utc)
        dead: dict[str, TestClient] = {"anonymous": TestClient(app, raise_server_exceptions=False)}
        investigator_id = uuid.UUID(people["investigator"][0])
        signed_out = _session_for(investigator_id, tenant_id)
        assert _client(signed_out).post("/api/v1/auth/signout").status_code == 200
        dead["signed_out_token_reused"] = _client(signed_out)
        dead["idle"] = _client(_session_for(investigator_id, tenant_id, last_seen_at=now - timedelta(hours=3)))
        dead["past_absolute_end"] = _client(
            _session_for(investigator_id, tenant_id, expires_at=now - timedelta(minutes=1))
        )
        dead["owes_mfa"] = _client(_session_for(investigator_id, tenant_id, mfa_state="VERIFY"))
        leaver_client = actors.pop("leaver")[0]
        removed = owner.post(f"/api/v1/trial/team/{people['leaver'][0]}/remove")
        assert removed.status_code == 200, removed.text
        dead["removed_colleague"] = leaver_client
        suspended = _account(tenant_id, "Investigator", membership="SUSPENDED")
        dead["suspended_membership"] = _client(_session_for(suspended, tenant_id))
        # A second trial, ended: its owner's live session must reach nothing.
        ended_owner, ended_approval, ended_email = _approved_trial_client()
        db = _db()
        try:
            row = db.query(SubscriptionLifecycle).filter_by(tenant_id=uuid.UUID(ended_approval["tenant_id"])).one()
            row.expires_at = now - timedelta(minutes=1)
            db.commit()
        finally:
            db.close()
        dead["ended_trial"] = ended_owner
        yield {
            "tenant_id": tenant_id,
            "owner_email": owner_email,
            "actors": actors,
            "dead": dead,
            "people": people,
            "ended_email": ended_email,
        }
    finally:
        _purge_trial_business_data()
        if previous is None:
            os.environ.pop("MDARIX_FEATURE_SET", None)
        else:
            os.environ["MDARIX_FEATURE_SET"] = previous


# ------------------------------------------------------------------------------------------- dead states: nothing


DEAD_STATES = (
    "anonymous",
    "signed_out_token_reused",
    "idle",
    "past_absolute_end",
    "owes_mfa",
    "removed_colleague",
    "suspended_membership",
    "ended_trial",
)


@pytest.mark.db
@pytest.mark.parametrize("state", DEAD_STATES)
def test_a_dead_session_reaches_no_route(world, state):
    assert runtime_role_active(), "the matrix must run as the least-privilege runtime role (RLS enforced)"
    rows = [
        (method, path, route)
        for method, path, route in matrix_routes()
        if (method, path) not in PUBLIC and not (state == "owes_mfa" and path.startswith(MFA_STEPS))
    ]
    responses = sweep(
        world["dead"][state],
        [(method, url_for(path), valid_body(route) if method != "GET" else None) for method, path, route in rows],
    )
    opened, crashed, calls = [], [], len(rows)
    for (method, path, _route), response in zip(rows, responses):
        code = _code(response)
        if response.status_code >= 500:
            crashed.append(f"{method} {path} -> {response.status_code}")
        elif response.status_code == 422:
            # Validation answered before the guard: only acceptable when the body could not be sampled validly.
            opened.append(f"{method} {path} -> 422 (guard not reached; fix the sampler or the route)")
        elif response.status_code not in {401, 403} or code not in ACCESS_ENDED:
            opened.append(f"{method} {path} -> {response.status_code} {code}")
    assert calls > 600
    assert opened == [], f"{state}: routes answered past the session check:\n" + "\n".join(opened)
    assert crashed == [], f"{state}: server errors:\n" + "\n".join(crashed)


# ------------------------------------------------------------------------------- live actors: permission routes


ACTORS = (
    "owner",
    *PERSONA_ACTORS,
    "persona_only",
    "reviewer",
    "customer_admin",
    "platform_admin",
)


@pytest.mark.db
@pytest.mark.parametrize("actor", ACTORS)
def test_an_actor_is_refused_exactly_where_its_roles_lack_the_permission(world, actor):
    client, roles = world["actors"][actor]
    granted = set().union(*(ROLE_MATRIX[role] for role in roles))
    rows = [
        (method, path, guard_permissions(route))
        for method, path, route in matrix_routes()
        if guard_permissions(route)
        and path not in SKIP_POSITIVE
        and not path.startswith(ADMIN_PREFIXES + PLATFORM_PREFIXES)
    ]
    # An empty body: a permission guard answers before validation, so an allowed call stops at 422 or 404 (random
    # IDs) and changes nothing.
    responses = sweep(client, [(method, url_for(path), {} if method != "GET" else None) for method, path, _ in rows])
    wrong, crashed, checked = [], [], len(rows)
    for (method, path, permissions), response in zip(rows, responses):
        refused = response.status_code == 403 and _code(response) == "PERMISSION_DENIED"
        if response.status_code >= 500:
            crashed.append(f"{method} {path} -> {response.status_code}")
        elif refused == bool(permissions & granted):
            expected = "allowed" if permissions & granted else "refused"
            wrong.append(f"{method} {path} [{action_kind(method, path)}; {sorted(permissions)}] expected {expected}")
    assert checked > 150
    assert wrong == [], f"{actor} ({sorted(roles)}):\n" + "\n".join(wrong)
    assert crashed == [], f"{actor}: server errors:\n" + "\n".join(crashed)


# --------------------------------------------------------------------------------------- administration routes


@pytest.mark.db
@pytest.mark.parametrize("actor", ACTORS)
def test_administration_opens_only_to_its_administrators(world, actor):
    """Customer administration (/admin, /customer-admin) opens to administrators; platform administration only to
    the Platform Administrator. Everyone else is refused on every route, reads and writes alike."""
    client, roles = world["actors"][actor]
    customer_admin = bool(roles & {"CUSTOMER_ADMIN", "PLATFORM_ADMIN"})
    platform_admin = "PLATFORM_ADMIN" in roles
    rows = []
    for method, path, route in matrix_routes():
        platform = path.startswith(PLATFORM_PREFIXES)
        if not (platform or path.startswith(ADMIN_PREFIXES)) or (method, path) in PUBLIC:
            continue
        allowed = platform_admin if platform else customer_admin
        if path in ADMIN_ROUTES_FOR:
            allowed = bool(roles & ADMIN_ROUTES_FOR[path])
        if allowed and method != "GET":
            continue  # positive checks read only: an administrator's write would change the shared fixtures
        rows.append((method, path, route, allowed))
    responses = sweep(
        client,
        [(method, url_for(path), valid_body(route) if method != "GET" else None) for method, path, route, _ in rows],
    )
    wrong = []
    for (method, path, route, allowed), response in zip(rows, responses):
        refused = response.status_code in {401, 403} and _code(response) not in {None, "TRIAL_ENDED"}
        if response.status_code >= 500 or refused == allowed:
            wrong.append(f"{method} {path} -> {response.status_code} {_code(response)} (expected allowed={allowed})")
    # A refusal of an administrator that is about a record or a grant, not about the role, is still "allowed".
    wrong = [
        line
        for line in wrong
        if not re.search(r"-> 403 (SUPPORT_ACCESS_REQUIRED|CUSTOMER_APPROVAL_REQUIRED|MFA_ENROLLMENT_REQUIRED)", line)
        or "expected allowed=False" in line
    ]
    assert wrong == [], f"{actor}:\n" + "\n".join(wrong)


# --------------------------------------------------------------------------------------------- persona and roles


@pytest.mark.db
def test_a_persona_alone_grants_nothing_and_viewing_as_changes_no_right(world):
    owner, _ = world["actors"]["owner"]
    multi, _ = world["actors"]["multi_role"]
    persona_only, _ = world["actors"]["persona_only"]
    write = "/api/v1/investigations/{0}/analysis".format(uuid.uuid4())
    # The persona view "Decision Maker" on a Viewer account: refused like any Viewer, and the view cannot be switched.
    assert _code(persona_only.post(write, json={})) == "PERMISSION_DENIED"
    assert _code(persona_only.post("/api/v1/me/persona", json={"persona": "decision"})) == "PERSONA_LOCKED"
    # A colleague with two personas switches the view between them; their rights stay the union either way.
    for persona in ("decision", "investigator"):
        assert multi.post("/api/v1/me/persona", json={"persona": persona}).status_code == 200
        assert _code(multi.post(write, json={})) != "PERMISSION_DENIED"
    assert _code(multi.post("/api/v1/me/persona", json={"persona": "quality"})) == "PERSONA_LOCKED"
    # The owner viewing as the Executive (view only) keeps the owner's rights.
    assert owner.post("/api/v1/me/persona", json={"persona": "executive"}).status_code == 200
    assert _code(owner.post(write, json={})) != "PERMISSION_DENIED"
    assert owner.post("/api/v1/me/persona", json={"persona": "admin"}).status_code == 200


@pytest.mark.db
def test_a_role_change_applies_to_the_very_next_request_of_a_live_session(world):
    owner, _ = world["actors"]["owner"]
    handler, _ = world["actors"]["handler"]
    handler_id = world["people"]["handler"][0]
    triage = "/api/v1/triage/rules/run"
    assert _code(handler.post(triage)) != "PERMISSION_DENIED"
    try:
        assert (
            owner.post(f"/api/v1/trial/team/{handler_id}/persona", json={"personas": ["executive"]}).status_code == 200
        )
        assert _code(handler.post(triage)) == "PERMISSION_DENIED"
    finally:
        assert owner.post(f"/api/v1/trial/team/{handler_id}/persona", json={"personas": ["handler"]}).status_code == 200
    assert _code(handler.post(triage)) != "PERMISSION_DENIED"


@pytest.mark.db
def test_only_the_trial_owner_runs_the_owner_routes(world):
    owner_routes = [
        ("POST", "/api/v1/trial/team"),
        ("POST", "/api/v1/trial/team/{user_id}/remove"),
        ("POST", "/api/v1/trial/team/{user_id}/persona"),
        ("POST", "/api/v1/trial/team/{user_id}/mfa-reset"),
        ("POST", "/api/v1/trial/team/{user_id}/resend-invitation"),
        ("POST", "/api/v1/trial/sample-data/removal"),
        ("POST", "/api/v1/trial/sample-data/restart"),
        ("POST", "/api/v1/trial/exit-request"),
        ("POST", "/api/v1/trial/support-access/{grant_id}/approve"),
    ]
    routes = {(method, path): route for method, path, route in matrix_routes()}
    for actor in ACTORS:
        if actor == "owner":
            continue
        client, _ = world["actors"][actor]
        for key in owner_routes:
            response = client.request(key[0], url_for(key[1]), json=valid_body(routes[key]))
            assert response.status_code in {403, 404} and _code(response) in {
                "TRIAL_OWNER_REQUIRED",
                "TRIAL_OWNER_ONLY",
                "PERMISSION_DENIED",
                "USER_NOT_FOUND",
                "NOT_A_TRIAL",
            }, f"{actor} {key} -> {response.status_code} {_code(response)}"


# ----------------------------------------------------------------------------------- account-status disclosure


@pytest.mark.db
def test_sign_in_and_password_reset_never_say_whether_or_how_an_account_exists(world):
    """A wrong password reads the same for an unknown email, a removed colleague, a suspended person and an ended
    trial's owner; a password-reset request reads the same for all of them."""
    anonymous = TestClient(app)
    emails = {
        "unknown": f"nobody-{uuid.uuid4().hex[:8]}@example.invalid",
        "removed": world["people"]["leaver"][1],
        "active": world["people"]["viewer"][1],
        "ended_trial": world["ended_email"],
    }
    signin = {
        name: anonymous.post("/api/v1/auth/signin", json={"email": email, "password": "Not the password 2026!"})
        for name, email in emails.items()
    }
    answers = {(response.status_code, response.text) for response in signin.values()}
    assert len(answers) == 1, {name: (r.status_code, r.text) for name, r in signin.items()}
    reset = {
        name: anonymous.post("/api/v1/auth/forgot-password", json={"email": email}).json()
        for name, email in emails.items()
    }
    assert len({str({k: v for k, v in body.items() if k != "development_token"}) for body in reset.values()}) == 1


# --------------------------------------------------------------------------------------------- CSRF and origins


@pytest.mark.db
def test_a_cookie_request_from_another_site_changes_nothing_anywhere(world, monkeypatch):
    """Production-like: every state-changing route refuses a cookie-authenticated request naming a foreign origin, or
    naming none, before the route runs."""
    from auth import cookies

    monkeypatch.setenv("MDARIX_ENV", "production")
    monkeypatch.setenv("MDARIX_APP_URL", "https://app.mdarix.example")
    owner, _ = world["actors"]["owner"]
    token = _token_of(owner)
    rows = [(method, path) for method, path, _ in matrix_routes() if method != "GET"]
    leaks = []
    for headers in ({"Origin": "https://evil.example"}, {}):
        foreign = TestClient(app, raise_server_exceptions=False, headers=headers)
        foreign.cookies.set(cookies.SECURE_NAME, token)
        responses = sweep(foreign, [(method, url_for(path), {}) for method, path in rows])
        leaks += [
            f"{method} {path} {headers or 'no origin'} -> {response.status_code}"
            for (method, path), response in zip(rows, responses)
            if _code(response) != "CSRF_ORIGIN_DENIED"
        ]
    assert len(rows) > 300
    assert leaks == []


# ------------------------------------------------------------------------------- invitations and one-time tokens


@pytest.mark.db
def test_two_invitations_of_one_email_at_once_make_one_account(world):
    owner, _ = world["actors"]["owner"]
    email = f"matrix-race-{uuid.uuid4().hex[:8]}@example.invalid"
    token = _token_of(owner)
    answers: list[int] = []
    barrier = threading.Barrier(2)

    def invite():
        client = _client(token)
        barrier.wait()
        answers.append(client.post("/api/v1/trial/team", json={"email": email, "display_name": "Race"}).status_code)

    threads = [threading.Thread(target=invite) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    db = _db()
    try:
        accounts = (
            db.query(AuthUser).filter(AuthUser.tenant_id == world["tenant_id"], AuthUser.username == email).count()
        )
    finally:
        db.close()
    assert accounts == 1, f"{accounts} accounts for one invited email (answers {answers})"
    assert sorted(answers) == [200, 409]


@pytest.mark.db
def test_an_activation_link_works_once(world):
    from tests.test_free_trial import PASSWORD, _activation_token

    owner, _ = world["actors"]["owner"]
    email = f"matrix-once-{uuid.uuid4().hex[:8]}@example.invalid"
    invited = owner.post("/api/v1/trial/team", json={"email": email, "display_name": "Once"})
    assert invited.status_code == 200, invited.text
    link = _activation_token(invited.json(), email)
    anonymous = TestClient(app)
    assert (
        anonymous.post("/api/v1/auth/activate-account", json={"token": link, "password": PASSWORD}).status_code == 200
    )
    again = anonymous.post("/api/v1/auth/activate-account", json={"token": link, "password": PASSWORD + "x"})
    assert again.status_code in {400, 403, 404, 409, 410} and _code(again) == "INVALID_ACTIVATION"


# ------------------------------------------------------------------------------- pooled connections under RLS


@pytest.mark.db
def test_no_tenant_scope_survives_on_a_pooled_connection_after_requests(world):
    """Requests of two organizations through the same pool: afterwards no pooled connection carries a tenant or the
    system scope, and the runtime role sees no tenant row without binding one."""
    from sqlalchemy import text

    assert runtime_role_active()
    owner, _ = world["actors"]["owner"]
    for _ in range(3):
        assert owner.get("/api/v1/complaints").status_code == 200
        assert world["dead"]["anonymous"].get("/api/v1/complaints").status_code == 401
    connections = [runtime_engine.connect() for _ in range(3)]
    try:
        for connection in connections:
            scope = connection.execute(
                text("SELECT current_setting('app.tenant_id', true), current_setting('app.rls_bypass', true)")
            ).one()
            assert (scope[0] or "", scope[1] or "") == ("", "")
            assert connection.execute(text("SELECT count(*) FROM complaints")).scalar() == 0
            assert (
                connection.execute(text("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user")).scalar()
                is False
            )
    finally:
        for connection in connections:
            connection.close()


@pytest.mark.db
def test_the_secret_value_of_the_session_cookie_is_never_echoed(world):
    owner, _ = world["actors"]["owner"]
    token = _token_of(owner)
    for path in ("/api/v1/auth/session", "/api/v1/me/context", "/api/v1/session/context"):
        response = owner.get(path)
        assert response.status_code == 200 and token not in response.text, path
    assert secrets.compare_digest(token, _token_of(owner))
