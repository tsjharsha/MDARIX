import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from auth.cookies import read_session_token
from auth.durable import hash_token
from backend.app.logging_setup import (
    accept_request_id,
    configure_logging,
    current_request_id,
    request_id_var,
)
from backend.app.version import APP_VERSION
from backend.app.access_router import router as access_router
from backend.app.ask_router import router as ask_router
from backend.app.auth_router import router as auth_router
from backend.app.challenger_router import router as challenger_router
from backend.app.communication_router import router as communication_router
from backend.app.unknowns_failure_chain_router import router as unknowns_failure_chain_router
from backend.app.db.models.stage2 import AuthSession
from backend.app.db.session import SessionLocal, engine, get_db
from backend.app.decision_router import router as decision_router
from backend.app.enterprise_audit import make_audit_event
from backend.app.evaluation_router import router as evaluation_router
from backend.app.evidence.router import router as evidence_router
from backend.app.governance_router import router as governance_router
from backend.app.integration_router import router as integration_router
from backend.app.investigations.brief_router import router as brief_router
from backend.app.investigations.router import router as investigations_router
from backend.app.mapping_catalog_router import router as mapping_catalog_router
from backend.app.product360.schemas import (
    Product360Response,
    ProductSummary,
    TemporalRealityResponse,
)
from backend.app.product360.service import Product360Error, Product360Service
from backend.app.product360.supplier_router import router as supplier360_router
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.retrieval.router import router as retrieval_router
from backend.app.regulatory_router import router as regulatory_router
from backend.app.stage3_router import router as stage3_router
from backend.app.stage3_workflow_router import router as stage3_workflow_router
from backend.app.trust_router import router as trust_router
from backend.app.trial.router import router as trial_router
from backend.app.demo_requests import router as demo_requests_router
from backend.app.trial.feedback import router as trial_feedback_router
from backend.app.site_info import router as site_info_router
from backend.app.paging import Page
from backend.app.ai_settings import router as ai_settings_router
from backend.app.audit_chain_api import router as audit_chain_router
from backend.app.tenant_export_api import router as tenant_export_router
from backend.app.data_import_router import router as data_import_router
from backend.app.regulatory_reference_router import router as regulatory_reference_router
from backend.app.investigation_open_router import assignees_router as investigation_assignees_router
from backend.app.investigation_open_router import router as investigation_open_router
from backend.app.case_workflow.router import router as case_workflow_router
from backend.app.complaints_router import router as complaints_router
from backend.app.complaint_review.router import router as complaint_review_router
from backend.app.complaint_disposition.router import router as complaint_disposition_router
from backend.app.complaint_disposition.resolve import router as resolve_and_close_router
from backend.app.intake.router import router as intake_router
from backend.app.intake.case_export import router as case_export_router
from backend.app.intake.case_attachments import router as case_attachments_router
from backend.app.mail_in.router import router as email_intake_router
from backend.app.authority_reports.router import router as authority_reports_router
from backend.app.communications.router import router as communications_router
from backend.app.decision_guides.router import router as decision_guides_router
from backend.app.decision_guides.trees import router as decision_trees_router
from backend.app.oversight.router import router as oversight_router
from backend.app.lot_impact.router import router as lot_impact_router
from backend.app.qms_documents.router import router as qms_documents_router
from backend.app.party_views.router import router as party_views_router
from backend.app.reportability.assessment_router import router as market_assessment_router
from backend.app.reportability.router import router as reportability_router
from backend.app.signer_training.router import router as signer_training_router
from backend.app.capa_effectiveness.router import router as capa_effectiveness_router
from backend.app.case_ai.router import router as case_ai_router
from backend.app.readiness_home.router import router as readiness_router
from backend.app.post_market.router import router as post_market_router
from backend.app.ai_release_gate import router as ai_release_gate_router
from backend.app.email_preferences import router as email_preferences_router
from backend.app.client_errors import router as client_errors_router
from backend.app.support_api import router as support_router
from backend.app.risk_router import router as risk_router
from backend.app.workflow.router import router as workflow_tasks_router
from backend.app.signals.router import router as signals_triage_router
from backend.app.evidence_workflow.inventory import router as evidence_inventory_router
from backend.app.evidence_workflow.requests import router as evidence_requests_router
from backend.app.case_challenge.router import router as case_challenge_router
from backend.app.closed_loop.router import router as closed_loop_router
from backend.app.case_intelligence.router import router as case_intelligence_router
from backend.app.case_reviews.next_steps import router as case_next_steps_router
from backend.app.case_reviews.router import router as case_reviews_router
from backend.app.decision_brief.router import router as decision_brief_router
from backend.app.decision_followups.router import router as decision_followups_router
from backend.app.human_decision.router import router as human_decision_router
from backend.app.case_audit.router import router as case_audit_router
from backend.app.workspace_context import router as workspace_context_router
from backend.app.data_plane_router import router as data_plane_router
from backend.app.db.data_plane import get_data_plane_db
from counterfactual.router import router as counterfactual_router
from graph.schemas import GraphResponse, HealthResponse, RelationshipDetail
from graph.service import GraphError, RealityGraphService
from scenario_intelligence.router import router as scenario_router
from backend.app.runtime_env import is_production_like
from backend.app import cell_link
from backend.app.cell_link_api import admin_router as cell_admin_router, router as cell_link_router
from backend.app.support_access_api import router as support_access_router
from backend.app.support_workspace import router as support_workspace_router
from backend.app.deployment_role import is_cell, serves_path
from backend.app import feature_set
from backend.app.db.tenant_scope import bind_tenant, scoped_bind

configure_logging()
logger = logging.getLogger("mdarix.api")
_production_like = is_production_like()
_docs_enabled = os.getenv("MDARIX_ENABLE_API_DOCS", "true" if not _production_like else "false").lower() == "true"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Staging and production refuse to start with a missing or unsafe configuration."""
    from backend.app.config_check import enforce

    enforce()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="MDARIX R1 API",
    version=APP_VERSION,
    description=(
        "Tenant-scoped medical-device product lifecycle, investigation, evidence, "
        "and governed decision APIs. Authentication and tenant authorization are "
        "enforced by the server; AI output is advisory and requires human review."
    ),
    contact={"name": "MDARIX Platform Engineering"},
    openapi_tags=[
        {"name": "Authentication", "description": "Sign-in, sessions, invitations, and password recovery."},
        {"name": "Access Control", "description": "Tenant context, permissions, and administration."},
        {"name": "Investigations", "description": "Tenant-scoped investigations and lifecycle context."},
        {"name": "Evidence", "description": "Evidence, provenance, retrieval, and authorized exports."},
        {"name": "Integration Gateway", "description": "Connector previews and provider health checks."},
        {"name": "Communication", "description": "Provider status and verified inbound events."},
        {"name": "Stage 3", "description": "AI advisory, reports, attachments, and workflow evidence."},
    ],
    docs_url="/docs" if _docs_enabled and not _production_like else None,
    redoc_url="/redoc" if _docs_enabled and not _production_like else None,
    openapi_url="/openapi.json" if _docs_enabled and not _production_like else None,
)


def _origin(url: str) -> str:
    parsed = urlparse(url or "")
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/") if parsed.scheme and parsed.netloc else ""


def _trusted_origins() -> set[str]:
    configured = {_origin(os.getenv("MDARIX_APP_URL", ""))}
    configured |= {_origin(item.strip()) for item in os.getenv("MDARIX_ALLOWED_ORIGINS", "").split(",")}
    return {origin for origin in configured if origin}


@app.middleware("http")
async def enforce_cookie_csrf(request: Request, call_next):
    """Reject cross-origin state changes authenticated only by a browser cookie.

    Production-like: an unsafe request that names a browser origin (Origin, else Referer) must name the app's own
    (MDARIX_APP_URL or MDARIX_ALLOWED_ORIGINS), with or without a session cookie (so sign-in cannot be forged from
    another site), and a cookie-authenticated one must name it. Local development: a browser origin that is not the
    app, not this server and not a loopback address is refused as well; requests without one (scripts, tests) pass.
    """
    has_session = read_session_token(request) is not None
    supplied = _origin(request.headers.get("origin", "")) or _origin(request.headers.get("referer", ""))
    if request.method not in {"GET", "HEAD", "OPTIONS"} and (has_session or supplied):
        trusted = _trusted_origins()
        if is_production_like():
            # A browser always names its origin on these requests; scripts without a cookie may omit it.
            allowed = supplied in trusted if supplied else not has_session
        else:
            host = urlparse(supplied).hostname or ""
            allowed = (
                not supplied
                or supplied in trusted
                or supplied == _origin(str(request.base_url))
                or host in {"127.0.0.1", "localhost", "::1"}
            )
        if not allowed:
            return JSONResponse(
                status_code=403,
                content={"detail": {"code": "CSRF_ORIGIN_DENIED", "message": "A trusted browser origin is required"}},
            )
    return await call_next(request)


@app.middleware("http")
async def limit_heavy_work(request: Request, call_next):
    """Uploads, exports and connector syncs a signed-in person starts count per person and per organization; past
    the limit the answer is 429 with a plain message and Retry-After (backend/app/rate_limit.py HEAVY_WORK)."""
    from backend.app import rate_limit

    kind = rate_limit.heavy_work(request.method, request.url.path)
    token = read_session_token(request) if kind else None
    if token:
        try:
            await run_in_threadpool(_count_heavy_work, kind, token)
        except HTTPException as refused:
            return JSONResponse({"detail": refused.detail}, status_code=refused.status_code, headers=refused.headers)
    return await call_next(request)


def _count_heavy_work(kind: str, token: str) -> None:
    from backend.app import rate_limit

    with SessionLocal() as db:
        session = (
            db.query(AuthSession.user_id, AuthSession.tenant_id)
            .filter(AuthSession.session_hash == hash_token(token), AuthSession.revoked_at.is_(None))
            .first()
        )
    if session is not None:  # no valid session: the route itself answers 401
        rate_limit.enforce(f"{kind}:user", str(session.user_id))
        rate_limit.enforce(f"{kind}:org", str(session.tenant_id))


@app.middleware("http")
async def audit_mutating_requests(request: Request, call_next):
    """Create a uniform request-level audit envelope for every state change.

    Domain handlers continue to record detailed events; this envelope guarantees
    that successful authenticated mutations cannot silently lack actor, origin,
    correlation, and outcome metadata.
    """
    response = await call_next(request)
    token = read_session_token(request)
    if request.method in {"GET", "HEAD", "OPTIONS"} or not token:
        return response
    await run_in_threadpool(_record_mutation, request, token, response.status_code)
    return response


def _record_mutation(request: Request, token: str, status_code: int) -> None:
    db = SessionLocal()
    try:
        session = (
            db.query(AuthSession)
            .filter(AuthSession.session_hash == hash_token(token), AuthSession.revoked_at.is_(None))
            .first()
        )
        if session:
            bind_tenant(db, session.tenant_id)
            db.add(
                make_audit_event(
                    tenant_id=session.tenant_id,
                    actor_ref=str(session.user_id),
                    action="REQUEST_MUTATION_COMPLETED",
                    entity_type="HTTP_REQUEST",
                    correlation_id=current_request_id(request),
                    details={"method": request.method, "path": request.url.path, "status_code": status_code},
                    request=request,
                    reason=request.headers.get("X-Change-Reason"),
                    created_at=datetime.now(timezone.utc),
                )
            )
            db.commit()
    except Exception:
        db.rollback()
        logger.exception("Request audit record could not be written")
    finally:
        db.close()


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """The headers Caddy adds in production (infrastructure/docker/Caddyfile), set by the API too, so a deployment
    without that proxy, or a route it does not cover, is protected the same way."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'; form-action 'self'",
    )
    if request.url.path.startswith("/api/"):
        # API answers carry personal and customer data: never kept by a browser or a shared cache, unless a route
        # chose its own caching (the public company details and legal texts).
        response.headers.setdefault("Cache-Control", "no-store")
    forwarded_https = request.headers.get("x-forwarded-proto", "").lower() == "https"
    if is_production_like() or request.url.scheme == "https" or forwarded_https:
        # Browsers keep to HTTPS for this site for a year once they have seen it over HTTPS.
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.middleware("http")
async def genai_request_scope(request: Request, call_next):
    """Open this request's AI scope; the authenticated request context records the organization in it, so every
    model call made while handling the request applies that organization's AI controls (genai/governance.py)."""
    from genai.governance import begin_request_scope, end_request_scope

    marker = begin_request_scope()
    try:
        return await call_next(request)
    finally:
        end_request_scope(marker)


@app.middleware("http")
async def deployment_role_gate(request: Request, call_next):
    """A PLATFORM deployment does not serve the investigation workspace and a CELL does not serve platform
    administration (backend/app/deployment_role.py): those paths answer 404 here, before any handler runs."""
    if not serves_path(request.url.path):
        return JSONResponse(
            status_code=404,
            content={
                "detail": {
                    "code": "NOT_SERVED_BY_THIS_DEPLOYMENT",
                    "message": "This deployment does not serve that part of MDARIX",
                }
            },
        )
    return await call_next(request)


@app.middleware("http")
async def feature_set_gate(request: Request, call_next):
    """Under MDARIX_FEATURE_SET=mvp the routes of the parked areas answer 404 here, before any handler runs
    (backend/app/feature_set.py); under ``full`` (the default) every route is served."""
    if not feature_set.serves_path(request.url.path, request.method):
        return JSONResponse(
            status_code=404,
            content={
                "detail": {
                    "code": "NOT_IN_THIS_FEATURE_SET",
                    "message": "This part of MDARIX is not offered in this deployment",
                }
            },
        )
    return await call_next(request)


_WRITABLE_WHEN_EXPIRED = (
    "/api/v1/auth/",
    "/api/v1/session",
    "/api/v1/me",
    "/api/v1/public/",
    "/api/v1/client-errors",
    "/health",
)


@app.middleware("http")
async def licence_read_only_gate(request: Request, call_next):
    """A CELL whose licence has passed its end date and its grace period (decision D6) keeps serving everything it
    holds but refuses state changes, except signing in; nothing is deleted (backend/app/cell_link.py)."""
    if (
        request.method in {"GET", "HEAD", "OPTIONS"}
        or not is_cell()
        or request.url.path.startswith(_WRITABLE_WHEN_EXPIRED)
    ):
        return await call_next(request)
    state = await run_in_threadpool(cell_link.read_only)
    if state:
        return JSONResponse(
            status_code=423,
            content={
                "detail": {
                    "code": "LICENCE_EXPIRED",
                    "message": "This organization's licence has expired: records can be read but not changed until a "
                    "new licence is applied",
                    "valid_until": state.get("valid_until"),
                    "grace_until": state.get("grace_until"),
                }
            },
        )
    return await call_next(request)


@app.middleware("http")
async def request_id_and_log(request: Request, call_next):
    """Give every request an id (the caller's X-Request-ID when it is plain, else a new one), attach it to every
    log record written while handling it, return it in X-Request-ID, and log one line per request."""
    request_id = accept_request_id(request.headers.get("x-request-id") or request.headers.get("x-correlation-id"))
    request_id = request_id or current_request_id()
    request.state.request_id = request_id
    marker = request_id_var.set(request_id)
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        if not request.url.path.startswith("/health"):
            logger.info(
                "%s %s %s",
                request.method,
                request.url.path,
                status_code,
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
        request_id_var.reset(marker)


@app.exception_handler(Exception)
async def safe_internal_error(request: Request, exc: Exception) -> JSONResponse:
    """Log the failure in full on the server; the caller gets no implementation details, only the request id."""
    request_id = current_request_id(request)
    logger.error(
        "Unhandled error on %s %s",
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
        extra={"method": request.method, "path": request.url.path},
    )
    body = {
        "code": "INTERNAL_ERROR",
        "message": "The request could not be completed.",
        "request_id": request_id,
        # Earlier clients read this name.
        "correlation_id": request_id,
    }
    return JSONResponse(status_code=500, content={"detail": body}, headers={"X-Request-ID": request_id})


@app.exception_handler(RequestValidationError)
async def validation_error_without_input(request: Request, exc: RequestValidationError) -> JSONResponse:
    """FastAPI's 422 answer (``{"detail": [{"type", "loc", "msg", ...}]}``, which the app reads field by field),
    without each error's ``input``: what was submitted is never sent back, so a password or an oversized body does not
    come back in the answer."""
    errors = [{key: value for key, value in error.items() if key != "input"} for error in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})


# First, so its fixed path /api/v1/investigations/mine/summary is matched before any /{investigation_id} route.
app.include_router(case_workflow_router)  # Case workflow: states, scope, readiness, my cases
app.include_router(evidence_router)
app.include_router(investigations_router)
app.include_router(retrieval_router)
app.include_router(regulatory_router)
app.include_router(challenger_router)
app.include_router(unknowns_failure_chain_router)
app.include_router(decision_router)
app.include_router(counterfactual_router)
app.include_router(brief_router)
app.include_router(trust_router)
app.include_router(evaluation_router)
app.include_router(integration_router)
app.include_router(access_router)
app.include_router(auth_router)
app.include_router(governance_router)
app.include_router(ask_router)
app.include_router(scenario_router)
app.include_router(workspace_context_router)
app.include_router(stage3_router)
app.include_router(communication_router)
app.include_router(stage3_workflow_router)
app.include_router(mapping_catalog_router)
app.include_router(trial_router)
app.include_router(demo_requests_router)
app.include_router(trial_feedback_router)
app.include_router(site_info_router)
app.include_router(ai_settings_router)
app.include_router(audit_chain_router)
app.include_router(tenant_export_router)
app.include_router(data_import_router)
app.include_router(regulatory_reference_router)
app.include_router(investigation_open_router)
app.include_router(investigation_assignees_router)
app.include_router(complaints_router)
app.include_router(complaint_review_router)  # Second look and backlog board (md40)
app.include_router(complaint_disposition_router)  # Complaint disposition, triggers, routine path (tr02)
app.include_router(resolve_and_close_router)  # Resolve and close, reopen (B7, tr25)
app.include_router(case_export_router)  # B7: Cases export and export for QMS entry (before /intake/{id})
app.include_router(case_attachments_router)  # B7: files on a Case
app.include_router(email_intake_router)  # B7b: E-mail to check and the intake address (404 while switched off)
app.include_router(intake_router)  # First contact, urgent intake and triage, duplicates (tr04)
app.include_router(authority_reports_router)  # Report worksheets, obligations and the submission record (tr05)
app.include_router(decision_guides_router)  # The customer's own decision guide versions (tr06)
app.include_router(
    decision_trees_router
)  # The Decision trees tab: one tree per market, each complaint's path (0.10.75)
app.include_router(communications_router)  # The external communications log (tr06)
app.include_router(oversight_router)  # Reminders and escalation, the oversight view, the event closure (tr07)
app.include_router(qms_documents_router)  # Ready-to-use documents, signed PDF and DOCX (T-G35)
app.include_router(party_views_router)  # Distributor and authorised-representative preview, trial only (T-G37P)
app.include_router(lot_impact_router)  # Lot impact on a case, trial only (T-G5, tr08)
app.include_router(reportability_router)  # Reportability watch and reporting windows (md41)
app.include_router(market_assessment_router)  # Seriousness and causation per market, signed conclusions (tr01)
app.include_router(signer_training_router)  # Training on the current version of what a signature relies on (tr01)
app.include_router(capa_effectiveness_router)  # CAPA effectiveness checks (md41)
app.include_router(case_ai_router)  # The case AI run in one pass (md42)
app.include_router(readiness_router)  # Readiness: the inspector's checks and the management review summary
app.include_router(post_market_router)  # Post-market data and the risk file, per product
app.include_router(ai_release_gate_router)  # The AI release gate: the four bars before AI goes to a pilot
app.include_router(email_preferences_router)  # My account: the weekly readiness email on or off
app.include_router(client_errors_router)
app.include_router(support_router)
app.include_router(risk_router)  # Risk & Traceability
app.include_router(workflow_tasks_router)  # My Work: workflow tasks and role queues
app.include_router(signals_triage_router)  # Signals and triage
app.include_router(evidence_inventory_router)  # Case evidence: inventory, links, review, provenance
app.include_router(evidence_requests_router)  # Evidence requests to colleagues, roles and suppliers
app.include_router(case_intelligence_router)  # Case intelligence: hypotheses, unknowns, chains, observations
app.include_router(case_challenge_router)  # B5a: rule drafts and challenge questions
app.include_router(closed_loop_router)  # B5b: Did it work? after a signed decision
app.include_router(case_reviews_router)  # Risk and regulatory reviews: policy, requests, reviewers, dashboard
app.include_router(case_next_steps_router)  # Next steps of a case (the old decision options as actions)
app.include_router(decision_brief_router)  # Decision Brief: versions, submission gate, quality review, dashboard
app.include_router(decision_followups_router)  # After the decision: follow-ups, impact assessments, closure check
app.include_router(human_decision_router)  # Human decision: queue, decision screen, signing, record
app.include_router(case_audit_router)  # Trust & audit of a case: timeline, replay, AI runs, integrity, export
app.include_router(cell_link_router)  # The link the tenant cells call: enrollment, heartbeat, packages
app.include_router(cell_admin_router)  # Platform administration of packages and the fleet of cells
app.include_router(support_access_router)  # The customer approves, denies and revokes support access
app.include_router(support_workspace_router)  # MDARIX reads what the customer granted, read-only (support access)
app.include_router(supplier360_router)  # W1: Supplier 360, read-only (product360/supplier_router.py)
graph_service = RealityGraphService()
product360_service = Product360Service()


def graph_error(exc: GraphError) -> HTTPException:
    status = 404 if exc.code in {"NODE_NOT_FOUND", "RELATIONSHIP_NOT_FOUND", "PATH_NOT_FOUND"} else 400
    return HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message})


def product_error(exc: Product360Error) -> HTTPException:
    status = 404 if exc.code in {"PRODUCT_NOT_FOUND", "VERSION_NOT_FOUND"} else 400
    return HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message})


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1")).scalar_one()
    return HealthResponse(status="ok", database="reachable")


@app.get("/health/live")
def liveness() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/health/version")
def deployed_version() -> dict[str, str]:
    """The deployed release, so anyone can confirm the build (0.10.71, A7): unauthenticated, the version only."""
    from backend.app.version import APP_VERSION

    return {"release": f"v{APP_VERSION}"}


@app.get("/health/ready")
def readiness():
    """Ready for traffic: the database answers and its schema is the one this code was built for. Other parts
    (data planes, object storage, worker, scheduler, email) are reported but do not take the API out of rotation."""
    from backend.app.readiness import readiness_report

    report = readiness_report()
    # Degraded (a worker, scheduler, plane or mail check failing) keeps the API in rotation, as /health/status does:
    # only a database that does not answer, or a schema this code was not built for, takes it out (503).
    return JSONResponse(status_code=503 if report["status"] == "not_ready" else 200, content=report)


@app.get("/health/status")
def public_status():
    """For a status page or an uptime monitor: ``ok``, ``degraded`` (200) or ``down`` (503) and nothing else. The
    component details stay on /health/ready, which only the deployment's own probes call."""
    from backend.app.readiness import public_status

    code, body = public_status()
    return JSONResponse(status_code=code, content=body, headers={"Cache-Control": "no-store"})


@app.get("/api/v1/graph/nodes/{entity_type}/{entity_id}")
def get_node(
    entity_type: str,
    entity_id: str,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    data_db: Session = Depends(get_data_plane_db),
):
    try:
        return RealityGraphService(data_db).get_node(entity_type, entity_id, ctx.tenant_id)
    except GraphError as exc:
        raise graph_error(exc) from exc


@app.get("/api/v1/graph/nodes/{entity_type}/{entity_id}/neighbors", response_model=GraphResponse)
def get_neighbors(
    entity_type: str,
    entity_id: str,
    depth: int = Query(1, ge=0, le=3),
    direction: str = "both",
    relationship_type: str | None = None,
    target_entity_type: str | None = None,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    data_db: Session = Depends(get_data_plane_db),
) -> GraphResponse:
    try:
        return RealityGraphService(data_db).get_neighbors(
            entity_type, entity_id, depth, direction, relationship_type, target_entity_type, ctx.tenant_id
        )
    except GraphError as exc:
        raise graph_error(exc) from exc


@app.get("/api/v1/graph/products/{product_id}", response_model=GraphResponse)
def get_product_graph(
    product_id: str,
    depth: int = Query(2, ge=0, le=3),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    data_db: Session = Depends(get_data_plane_db),
) -> GraphResponse:
    try:
        return RealityGraphService(data_db).get_product_graph(product_id, depth, ctx.tenant_id)
    except GraphError as exc:
        raise graph_error(exc) from exc


@app.get("/api/v1/graph/investigations/{investigation_id}", response_model=GraphResponse)
def get_investigation_graph(
    investigation_id: str,
    depth: int = Query(2, ge=0, le=3),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    data_db: Session = Depends(get_data_plane_db),
) -> GraphResponse:
    try:
        return RealityGraphService(data_db).get_investigation_graph(investigation_id, depth, ctx.tenant_id)
    except GraphError as exc:
        raise graph_error(exc) from exc


@app.get("/api/v1/graph/relationships/{relationship_id}", response_model=RelationshipDetail)
def get_relationship(
    relationship_id: str,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    data_db: Session = Depends(get_data_plane_db),
) -> RelationshipDetail:
    try:
        return RealityGraphService(data_db).get_relationship_detail(relationship_id, ctx.tenant_id)
    except GraphError as exc:
        raise graph_error(exc) from exc


@app.get("/api/v1/graph/paths", response_model=GraphResponse)
def get_path(
    source_type: str,
    source_id: str,
    target_type: str,
    target_id: str,
    max_depth: int = Query(4, ge=0, le=5),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    data_db: Session = Depends(get_data_plane_db),
) -> GraphResponse:
    try:
        return RealityGraphService(data_db).get_path(
            source_type, source_id, target_type, target_id, max_depth, ctx.tenant_id
        )
    except GraphError as exc:
        raise graph_error(exc) from exc


@app.get("/api/v1/products", response_model=list[ProductSummary])
def list_products(
    response: Response,
    page: Page = Depends(),
    counts: bool = Query(False, description="W1: the newest version's open records per product"),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    data_db: Session = Depends(get_data_plane_db),
) -> list[ProductSummary]:
    """The tenant's products, paged (backend/app/paging.py: X-Total-Count, X-Next-Offset)."""
    source = scoped_bind(data_db)
    total = product360_service.count_products(ctx.tenant_id, db_engine=source)
    response.headers["X-Total-Count"] = str(total)
    following = page.offset + page.limit
    response.headers["X-Next-Offset"] = str(following) if following < total else ""
    return product360_service.list_products(
        ctx.tenant_id, db_engine=source, limit=page.limit, offset=page.offset, with_counts=counts
    )


@app.get("/api/v1/products/{product_id}/investigations")
def list_product_investigations(
    product_id: str,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    data_db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
) -> list[dict]:
    from backend.app.case_workflow.states import with_owner_names

    try:
        rows = product360_service.list_product_investigations(product_id, ctx.tenant_id, db_engine=scoped_bind(data_db))
    except Product360Error as exc:
        raise product_error(exc) from exc
    # Each case's owner by name, next to its workflow state (backend/app/case_workflow/states.py).
    return with_owner_names(control_db, ctx.tenant_id, rows)


def _product360_audit(
    db: Session, product: Product360Response, mode: str, as_of: datetime | None, ctx: AuthenticatedRequestContext
) -> None:
    actor = ctx.user_id
    tenant_id = ctx.tenant_id
    details = {
        "temporal_mode": {"current": "CURRENT", "event": "EVENT_AS_OF", "known": "KNOWN_AS_OF"}[mode],
        "result_count": len(product.timeline),
    }
    if as_of:
        details["temporal_cutoff"] = as_of.isoformat()
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=actor,
            action="PRODUCT360_TEMPORAL_RETRIEVAL",
            entity_type="Product360",
            correlation_id=ctx.correlation_id,
            details=details,
        )
    )
    db.commit()


@app.get("/api/v1/products/{product_id}/product-360", response_model=Product360Response)
def get_product360(
    request: Request,
    product_id: str,
    version_id: str | None = None,
    as_of: datetime | None = None,
    mode: str = Query("current", pattern="^(current|event|known)$"),
    light: bool = Query(False, description="W1: counts instead of complaint rows, evidence and the timeline"),
    db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    data_db: Session = Depends(get_data_plane_db),
) -> Product360Response:
    try:
        result = product360_service.product360(
            product_id, version_id, as_of, mode, ctx.tenant_id, db_engine=scoped_bind(data_db), light=light
        )
        _product360_audit(db, result, mode, as_of, ctx)
        return result
    except Product360Error as exc:
        raise product_error(exc) from exc


@app.get("/api/v1/products/{product_id}/links")
def get_product_links(
    product_id: str,
    response: Response,
    version: str | None = None,
    kind: str | None = Query(None, pattern="^(complaints|investigations|signals|capas|risks|reports)$"),
    page: Page = Depends(),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    data_db: Session = Depends(get_data_plane_db),
):
    """W1: the product's connected records, as six tiles (no ``kind``) or one list, paged (backend/app/product360/links.py)."""
    from backend.app.product360 import links

    try:
        if kind is None:
            return links.tiles(data_db, ctx.tenant_id, product_id, version)
        return links.one_list(data_db, ctx.tenant_id, product_id, version, kind, page.limit, page.offset, response)
    except Product360Error as exc:
        raise product_error(exc) from exc


@app.get("/api/v1/products/{product_id}/timeline", response_model=TemporalRealityResponse)
def get_timeline(
    request: Request,
    product_id: str,
    version_id: str | None = None,
    as_of: datetime | None = None,
    mode: str = Query("event", pattern="^(event|known)$"),
    db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    data_db: Session = Depends(get_data_plane_db),
) -> TemporalRealityResponse:
    try:
        result = product360_service.temporal_reality(
            product_id, version_id, as_of, mode, ctx.tenant_id, db_engine=scoped_bind(data_db)
        )
        _product360_audit(
            db,
            product360_service.product360(
                product_id, version_id, as_of, mode, ctx.tenant_id, db_engine=scoped_bind(data_db)
            ),
            mode,
            as_of,
            ctx,
        )
        return result
    except Product360Error as exc:
        raise product_error(exc) from exc


# Keep this registration after the app-declared product routes.  The project
# historically registers several routers before the remaining app decorators;
# registering the data-plane surface here guarantees it is present in the
# final application route map.
app.include_router(data_plane_router)
