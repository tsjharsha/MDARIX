import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from backend.app.db.models.evidence_intelligence import EvidenceChunk, EvidenceEntityLink, EvidenceObservation
from backend.app.business_ids import business_id_map
from backend.app.db.models.foundation import Evidence, Investigation, Product, ProductVersion
from backend.app.product360.service import Product360Service
from graph.service import GraphError, RealityGraphService
from investigation_workspace.schemas import InvestigationWorkspaceRequest, InvestigationWorkspaceResponse
from retrieval.schemas import RetrievalRequest, RetrievalResponse
from retrieval.service import RetrievalError, TrustedRetrievalService


WORKSPACE_VERSION = "R1-Day10"


class InvestigationWorkspaceError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def with_business_ids(db: Session, workspace: InvestigationWorkspaceResponse) -> InvestigationWorkspaceResponse:
    """The workspace as the screens get it: the investigation, its product and each evidence record with its MDARIX
    ID (``business_id``).

    Added only to the API response: ``InvestigationWorkspaceService.workspace`` is also the grounding context of the
    AI workflows, which stays unchanged.
    """
    header = workspace.investigation
    investigation_ids = business_id_map(db, Investigation, [header.get("id")])
    product_ids = business_id_map(db, Product, [header.get("product_id")])
    evidence_ids = business_id_map(db, Evidence, (item.get("id") for item in workspace.evidence_context))
    investigation = {
        **header,
        "business_id": investigation_ids.get(str(header.get("id"))),
        "product_business_id": product_ids.get(str(header.get("product_id"))),
        **_workflow_fields(db, header.get("id")),
    }
    evidence = [
        {"id": item.get("id"), "business_id": evidence_ids.get(str(item.get("id"))), **item}
        for item in workspace.evidence_context
    ]
    return workspace.model_copy(update={"investigation": investigation, "evidence_context": evidence})


def _workflow_fields(db: Session, investigation_id) -> dict[str, Any]:
    """The case's workflow state (with its label), priority and due date for the workspace header (API only). Empty
    when they cannot be read: the header never fails because of them."""
    from sqlalchemy import select

    from backend.app.business_ids import as_uuid
    from backend.app.case_workflow.states import effective_state, state_label

    key = as_uuid(investigation_id)
    if key is None:
        return {}
    try:
        rows = db.execute(
            select(
                Investigation.status, Investigation.workflow_state, Investigation.priority, Investigation.due_at
            ).where(Investigation.id == key)
        ).all()
        status, workflow_state, priority, due_at = rows[0]
    except Exception:
        return {}
    state = effective_state(workflow_state, status)
    return {
        "workflow_state": state,
        "workflow_state_label": state_label(state),
        "priority": priority,
        "due_at": due_at.isoformat() if isinstance(due_at, datetime) else None,
    }


class InvestigationWorkspaceService:
    def __init__(
        self,
        product_service: Product360Service | None = None,
        graph_service: RealityGraphService | None = None,
        retrieval_service: TrustedRetrievalService | None = None,
    ) -> None:
        self.product_service = product_service or Product360Service()
        # Without an injected service the graph is read per request, from the request's own session (data plane).
        self.graph_service = graph_service
        self.retrieval_service = retrieval_service or TrustedRetrievalService()

    def workspace(
        self, db: Session, request: InvestigationWorkspaceRequest, data_plane_engine=None
    ) -> InvestigationWorkspaceResponse:
        if request.tenant_id is None:
            raise InvestigationWorkspaceError("TENANT_REQUIRED", "tenant_id is required")

        investigation = (
            db.query(Investigation)
            .filter(Investigation.tenant_id == request.tenant_id, Investigation.id == request.investigation_id)
            .first()
        )
        if investigation is None:
            raise InvestigationWorkspaceError("INVESTIGATION_NOT_FOUND", "Investigation not found")

        from backend.app.case_workflow import scope as case_scope

        # PV-1 F3: the version asked for, or the case's one version; never a version nobody recorded.
        scope = case_scope.current_scope(db, investigation)
        product_version_id = (
            str(request.product_version_id)
            if request.product_version_id
            else case_scope.single_version(db, investigation, scope)
        )
        if product_version_id:
            version = (
                db.query(ProductVersion)
                .filter(
                    ProductVersion.tenant_id == request.tenant_id,
                    ProductVersion.id == product_version_id,
                    ProductVersion.product_id == investigation.product_id,
                )
                .first()
            )
            if version is None:
                raise InvestigationWorkspaceError(
                    "PRODUCT_VERSION_NOT_FOUND", "ProductVersion is not available for this investigation product"
                )
        product_context = self._product_context(investigation, product_version_id, request, data_plane_engine)
        product_context["scope_product_version_ids"] = scope["product_version_ids"]
        if not product_version_id:
            product_context["limitations"] = [
                *product_context["limitations"],
                {
                    "code": "VERSION_UNKNOWN",
                    "severity": "WARNING",
                    "description": (
                        "The case has no single known product version (unknown, or several): the context is the whole "
                        "product, with no bill of materials."
                    ),
                    "product_version_ids": scope["product_version_ids"],
                },
            ]
        relationship_context = self._relationship_context(db, request.tenant_id, investigation.id)
        evidence_context = self._evidence_context(
            db, request.tenant_id, investigation, request.temporal_mode, request.as_of
        )
        retrieval_context = (
            self._retrieval_context(db, request, investigation, product_version_id)
            if request.include_retrieval
            else None
        )
        temporal_context = self._temporal_context(product_context, request)
        limitations = self._limitations(product_context, evidence_context, retrieval_context)

        return InvestigationWorkspaceResponse(
            investigation=self._investigation_header(investigation),
            product_context=product_context,
            temporal_context=temporal_context,
            relationship_context=relationship_context,
            evidence_context=evidence_context,
            retrieval_context=retrieval_context,
            limitations=limitations,
            guardrails={
                "human_authority_required": True,
                "generates_causality": False,
                "retrieval_rank_semantics": "retrieval relevance only; not truth, confidence, causality, regulatory significance, or probability",
                "ground_truth_isolation": "evaluation ground truth is not used by the investigation workspace",
            },
            metadata={
                "tenant_id": str(request.tenant_id),
                "workspace_version": WORKSPACE_VERSION,
                "generated_at": utcnow().isoformat(),
                "ground_truth_used": False,
            },
        )

    def _product_context(
        self,
        investigation: Investigation,
        product_version_id: str | None,
        request: InvestigationWorkspaceRequest,
        data_plane_engine=None,
    ) -> dict[str, Any]:
        view = self.product_service.product360(
            str(investigation.product_id),
            version_id=product_version_id,
            as_of=request.as_of,
            mode=request.temporal_mode,
            tenant_id=str(request.tenant_id),
            db_engine=data_plane_engine,
            pick_version=False,
        )
        return {
            "product": view.product,
            "selected_version": view.selected_version,
            "overview": view.overview,
            "configuration": view.configuration,
            "changes": view.changes,
            "manufacturing": view.manufacturing,
            "complaints": view.complaints,
            "risks": view.risks,
            "controls": view.controls,
            "limitations": view.limitations,
            "provenance": view.provenance,
        }

    def _investigation_header(self, investigation: Investigation) -> dict[str, Any]:
        return {
            "id": str(investigation.id),
            "investigation_identifier": investigation.investigation_identifier,
            "product_id": str(investigation.product_id),
            "investigation_question": investigation.investigation_question,
            "status": investigation.status,
            "opened_at": investigation.opened_at.isoformat() if investigation.opened_at else None,
            "closed_at": investigation.closed_at.isoformat() if investigation.closed_at else None,
            "owner_ref": investigation.owner_ref,
        }

    def _relationship_context(self, db: Session, tenant_id, investigation_id: uuid.UUID) -> dict[str, Any]:
        # Always the investigation's own tenant: without it the graph service falls back to a default tenant.
        service = self.graph_service or RealityGraphService(db)
        try:
            graph = service.get_investigation_graph(str(investigation_id), depth=2, tenant_id=str(tenant_id))
            return graph.model_dump(mode="json")
        except GraphError as exc:
            return {
                "nodes": [],
                "relationships": [],
                "metadata": {
                    "warning": exc.message,
                    "relationship_semantics": "graph connectivity only; not causality",
                },
            }

    def _evidence_context(
        self,
        db: Session,
        tenant_id: uuid.UUID,
        investigation: Investigation,
        temporal_mode: str,
        as_of: datetime | None,
    ) -> list[dict[str, Any]]:
        rows = self._investigation_evidence_query(db, tenant_id, investigation.id, temporal_mode, as_of).all()
        if not rows:
            return []
        # The chunks, observations and entity links of every evidence record in three statements, not three each.
        ids = [evidence.id for evidence in rows]
        related: dict[str, dict] = {"chunks": {}, "observations": {}, "links": {}}
        for key, model, order in (
            ("chunks", EvidenceChunk, (EvidenceChunk.sequence_number,)),
            ("observations", EvidenceObservation, (EvidenceObservation.created_at,)),
            ("links", EvidenceEntityLink, ()),
        ):
            query = db.query(model).filter(model.tenant_id == tenant_id, model.evidence_id.in_(ids))
            for row in query.order_by(model.evidence_id, *order):
                related[key].setdefault(row.evidence_id, []).append(row)
        return [
            self._evidence_item(
                investigation,
                evidence,
                related["chunks"].get(evidence.id, []),
                related["observations"].get(evidence.id, []),
                related["links"].get(evidence.id, []),
            )
            for evidence in rows
        ]

    def _investigation_evidence_query(
        self, db: Session, tenant_id: uuid.UUID, investigation_id: uuid.UUID, temporal_mode: str, as_of: datetime | None
    ):
        q = db.query(Evidence).filter(Evidence.tenant_id == tenant_id)
        q = q.filter(
            or_(
                Evidence.investigation_id == investigation_id,
                Evidence.id.in_(
                    text(
                        "SELECT evidence_id FROM investigation_evidence "
                        "WHERE tenant_id=CAST(:tenant_id AS uuid) AND investigation_id=CAST(:investigation_id AS uuid)"
                    )
                    .bindparams(tenant_id=tenant_id, investigation_id=investigation_id)
                    .columns(evidence_id=Evidence.id.type)
                ),
            )
        )
        if as_of and temporal_mode == "known":
            q = q.filter(Evidence.ingestion_timestamp.is_not(None), Evidence.ingestion_timestamp <= as_of)
        if as_of and temporal_mode == "event":
            q = q.filter((Evidence.effective_timestamp.is_(None)) | (Evidence.effective_timestamp <= as_of))
        return q.order_by(Evidence.source_timestamp.nulls_last(), Evidence.evidence_identifier)

    def _evidence_item(
        self, investigation: Investigation, evidence: Evidence, chunks: list, observations: list, links: list
    ) -> dict[str, Any]:
        link_payload = [
            {
                "entity_type": link.entity_type,
                "entity_id": str(link.entity_id) if link.entity_id else None,
                "raw_reference": link.raw_reference,
                "resolution_status": link.resolution_status,
                "source": "evidence_entity_links",
            }
            for link in links
        ]
        if not link_payload:
            link_payload = [
                {
                    "entity_type": "Investigation",
                    "entity_id": str(investigation.id),
                    "raw_reference": investigation.investigation_identifier,
                    "resolution_status": "RESOLVED",
                    "source": "workspace_investigation_context",
                },
                {
                    "entity_type": "Product",
                    "entity_id": str(investigation.product_id),
                    "raw_reference": str(investigation.product_id),
                    "resolution_status": "RESOLVED",
                    "source": "workspace_investigation_context",
                },
            ]
        chunk_payload = [
            {
                "chunk_id": str(chunk.id),
                "sequence_number": chunk.sequence_number,
                "source_anchor": chunk.source_anchor or {},
                # The chunk's own text (up to 240 characters) rather than the 100-character anchor excerpt, so a
                # statement is not cut off mid-sentence; the source anchor itself is unchanged.
                "excerpt": (chunk.text_content or "")[:240] or (chunk.source_anchor or {}).get("excerpt"),
                "materialized": True,
            }
            for chunk in chunks
        ]
        if not chunk_payload and evidence.content:
            chunk_payload = [
                {
                    "chunk_id": None,
                    "sequence_number": 1,
                    "source_anchor": {
                        "source": evidence.source_reference or evidence.document_ref or evidence.evidence_identifier,
                        "locator": "evidence.content",
                        "fallback": "workspace_content_excerpt",
                    },
                    "excerpt": evidence.content[:240],
                    "materialized": False,
                }
            ]
        return {
            "id": str(evidence.id),
            "evidence_identifier": evidence.evidence_identifier,
            "evidence_type": evidence.evidence_type,
            "title": evidence.title,
            "source_reference": evidence.source_reference,
            "reliability_status": evidence.reliability_status,
            "fact_type": evidence.fact_type,
            "temporal": {
                "effective_timestamp": evidence.effective_timestamp.isoformat()
                if evidence.effective_timestamp
                else None,
                "recorded_timestamp": evidence.recorded_timestamp.isoformat() if evidence.recorded_timestamp else None,
                "ingestion_timestamp": evidence.ingestion_timestamp.isoformat()
                if evidence.ingestion_timestamp
                else None,
            },
            "chunks": chunk_payload,
            "observations": [
                {
                    "observation_id": str(obs.id),
                    "statement": obs.statement,
                    "observation_type": obs.observation_type,
                    "extraction_method": obs.extraction_method,
                    "source_anchor": obs.source_anchor or {},
                    "quality_status": obs.quality_status,
                    "limitations": obs.limitations or [],
                }
                for obs in observations
            ],
            "entity_links": link_payload,
        }

    def _retrieval_context(
        self,
        db: Session,
        request: InvestigationWorkspaceRequest,
        investigation: Investigation,
        product_version_id: str | None,
    ) -> RetrievalResponse:
        retrieval_request = RetrievalRequest(
            tenant_id=request.tenant_id,
            investigation_id=request.investigation_id,
            product_id=investigation.product_id,
            product_version_id=uuid.UUID(product_version_id) if product_version_id else None,
            query_text=investigation.investigation_question,
            retrieval_mode="hybrid",
            temporal_mode=request.temporal_mode,
            event_as_of=request.as_of if request.temporal_mode == "event" else None,
            knowledge_as_of=request.as_of if request.temporal_mode == "known" else None,
            top_k=request.retrieval_top_k,
        )
        try:
            return self.retrieval_service.retrieve(db, retrieval_request)
        except RetrievalError as exc:
            raise InvestigationWorkspaceError("RETRIEVAL_FAILED", str(exc)) from exc

    def _temporal_context(
        self, product_context: dict[str, Any], request: InvestigationWorkspaceRequest
    ) -> dict[str, Any]:
        return {
            "mode": request.temporal_mode,
            "as_of": request.as_of.isoformat() if request.as_of else None,
            "event_time_distinct_from_known_time": True,
            "late_arriving_evidence_count": sum(
                1 for item in product_context.get("limitations", []) if item.get("code") == "LATE_ARRIVING_EVIDENCE"
            ),
        }

    def _limitations(
        self,
        product_context: dict[str, Any],
        evidence_context: list[dict[str, Any]],
        retrieval_context: RetrievalResponse | None,
    ) -> list[dict[str, Any]]:
        limitations = list(product_context.get("limitations", []))
        if not evidence_context:
            limitations.append(
                {
                    "code": "NO_DIRECT_EVIDENCE",
                    "severity": "WARNING",
                    "description": "No direct evidence records are attached to this investigation.",
                }
            )
        fallback_chunks = sum(
            1 for evidence in evidence_context for chunk in evidence["chunks"] if not chunk["materialized"]
        )
        if fallback_chunks:
            limitations.append(
                {
                    "code": "MISSING_MATERIALIZED_CHUNKS",
                    "severity": "INFO",
                    "description": f"{fallback_chunks} evidence records are shown with workspace fallback source anchors.",
                }
            )
        unresolved = sum(
            1
            for evidence in evidence_context
            for link in evidence["entity_links"]
            if link["resolution_status"] != "RESOLVED"
        )
        if unresolved:
            limitations.append(
                {
                    "code": "UNRESOLVED_EVIDENCE_LINKS",
                    "severity": "WARNING",
                    "description": f"{unresolved} evidence entity links are unresolved.",
                }
            )
        if retrieval_context and retrieval_context.status != "COMPLETED":
            limitations.append(
                {
                    "code": retrieval_context.status,
                    "severity": "WARNING",
                    "description": "Trusted retrieval did not return complete contextual evidence.",
                }
            )
        limitations.append(
            {
                "code": "NO_INVESTIGATION_CONCLUSION",
                "severity": "INFO",
                "description": "Workspace presents context only; regulated conclusions remain human decisions.",
            }
        )
        return limitations
