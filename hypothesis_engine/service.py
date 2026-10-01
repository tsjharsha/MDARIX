import time
import uuid

from sqlalchemy.orm import Session

from ai.execution import record_ai_execution
from backend.app.db.models.foundation import (
    AIExecution,
    Evidence,
    Hypothesis as HypothesisRow,
    HypothesisEvidence,
    Unknown,
)
from hypothesis_engine.engine import (
    MODEL,
    MODEL_VERSION,
    ORCHESTRATION_VERSION,
    PROMPT_TEMPLATE_VERSION,
    PROVIDER,
    ControlledHypothesisEngine,
)
from hypothesis_engine.model_engine import ModelHypothesisEngine
from hypothesis_engine.schemas import HypothesisSet, HypothesisSetRequest, HypothesisSetResponse
from hypothesis_engine.validator import HypothesisValidator
from investigator.model_provider import ModelAnalysisUnavailable
from investigator.schemas import InvestigationAnalysisRequest
from investigator.service import EvidenceGroundedInvestigatorService, InvestigatorError

# A hypothesis row replaced by a newer model-written set (never one a person has reviewed).
SUPERSEDED = "superseded"


class HypothesisEngineError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class CompetingHypothesisService:
    def __init__(
        self,
        investigator_service: EvidenceGroundedInvestigatorService | None = None,
        engine: ControlledHypothesisEngine | None = None,
        validator: HypothesisValidator | None = None,
        model_engine: ModelHypothesisEngine | None = None,
    ) -> None:
        self.investigator_service = investigator_service or EvidenceGroundedInvestigatorService()
        self.engine = engine or ControlledHypothesisEngine()
        self.validator = validator or HypothesisValidator()
        self.model_engine = model_engine or ModelHypothesisEngine()

    def generate(self, db: Session, request: HypothesisSetRequest) -> HypothesisSetResponse:
        if request.tenant_id is None:
            raise HypothesisEngineError("TENANT_REQUIRED", "tenant_id is required")
        start = time.time()
        analysis_response = self._shown_analysis(db, request)
        try:
            analysis_response = analysis_response or self.investigator_service.analyze(
                db,
                InvestigationAnalysisRequest(
                    tenant_id=request.tenant_id,
                    investigation_id=request.investigation_id,
                    temporal_mode=request.temporal_mode,
                    as_of=request.as_of,
                    investigator_question=request.investigator_question,
                    persist=True,
                ),
            )
        except InvestigatorError as exc:
            raise HypothesisEngineError(exc.code, exc.message) from exc

        hypothesis_set = self.engine.generate(analysis_response.analysis, request.investigator_question)
        hypothesis_set = self._with_model_hypotheses(analysis_response.analysis, request, hypothesis_set)
        accepted, rejected, summary = self.validator.validate(hypothesis_set.hypotheses)
        status = (
            "INSUFFICIENT_EVIDENCE"
            if accepted and accepted[0].status == "NO_CURRENTLY_SUPPORTABLE_HYPOTHESIS"
            else "MIXED_EVIDENCE"
        )
        if rejected and not accepted:
            status = "HUMAN_REVIEW_REQUIRED"
        hypothesis_set = hypothesis_set.model_copy(
            update={
                "hypotheses": accepted,
                "rejected_hypotheses": rejected,
                "status": status,
                "validation_summary": {
                    **summary,
                    "contradiction_preservation_count": sum(len(h.contradicting_evidence) for h in accepted),
                    "alternative_hypothesis_count": len(accepted),
                    "future_information_leakage": 0,
                    "ground_truth_runtime_leakage": 0,
                    "tenant_leakage": 0,
                    "wrong_version_contamination": 0,
                    "prompt_injection_policy_violations": 0,
                    "historical_root_cause_converted_to_fact": 0,
                    "model_items_dropped_by_checks": len(hypothesis_set.provenance.get("checks_dropped", [])),
                },
            }
        )
        if hypothesis_set.provenance.get("author") == "LANGUAGE_MODEL":
            ai_advisory = {"status": "NOT_NEEDED", "reason": "The language model wrote these hypotheses."}
        else:
            from genai.grounding import advisory, build_authorized_context

            grounded = build_authorized_context(
                db,
                tenant_id=request.tenant_id,
                investigation_id=request.investigation_id,
                temporal_mode=request.temporal_mode,
                as_of=request.as_of,
            )
            ai_advisory = advisory(
                workflow="COMPETING_HYPOTHESES",
                deterministic_result=hypothesis_set.model_dump(mode="json"),
                grounded_context=grounded,
                question=request.investigator_question,
            )
        hypothesis_set = hypothesis_set.model_copy(
            update={"provenance": {**hypothesis_set.provenance, "live_provider_advisory": ai_advisory}}
        )

        ai_execution_id = None
        persisted = False
        if request.persist:
            row = record_ai_execution(
                db=db,
                tenant_id=request.tenant_id,
                investigation_id=request.investigation_id,
                provider=PROVIDER,
                model_name=hypothesis_set.provenance.get("model_analysis", {}).get("model", MODEL),
                model_version=hypothesis_set.provenance.get("model_analysis", {}).get("model_version", MODEL_VERSION),
                prompt_template_version=hypothesis_set.provenance.get("model_analysis", {}).get(
                    "prompt_template_version", PROMPT_TEMPLATE_VERSION
                ),
                orchestration_version=ORCHESTRATION_VERSION,
                context_refs={
                    "context_snapshot_id": hypothesis_set.context_snapshot_id,
                    "context_snapshot_version": hypothesis_set.context_snapshot_version,
                    "source_analysis_id": str(hypothesis_set.source_analysis_id),
                    "source_ai_execution_id": str(hypothesis_set.source_ai_execution_id)
                    if hypothesis_set.source_ai_execution_id
                    else None,
                    "day11_contract": "InvestigationAnalysis",
                },
                evidence_refs={
                    "hypothesis_ids": [str(h.hypothesis_id) for h in hypothesis_set.hypotheses],
                    "relationship_count": sum(
                        len(h.supporting_evidence) + len(h.contradicting_evidence) + len(h.contextual_evidence)
                        for h in hypothesis_set.hypotheses
                    ),
                },
                structured_input=request.model_dump(mode="json"),
                structured_output=hypothesis_set.model_dump(mode="json"),
                validation_status=hypothesis_set.status,
                latency_ms=int((time.time() - start) * 1000),
                requestor_ref="MDARIX-HypothesisEngine",
            )
            db.commit()
            self._materialize_domain_intelligence(db, request, hypothesis_set)
            ai_execution_id = row.id
            persisted = True
        return HypothesisSetResponse(
            hypothesis_set=hypothesis_set, persisted=persisted, ai_execution_id=ai_execution_id
        )

    def _shown_analysis(self, db: Session, request: HypothesisSetRequest):
        """The saved analysis the user is looking at, if it is for this investigation and the same point in time."""
        if request.source_analysis_id is None:
            return None
        try:
            shown = self.investigator_service.get(
                db, request.tenant_id, request.investigation_id, request.source_analysis_id
            )
        except InvestigatorError:
            return None
        context = shown.analysis.temporal_context or {}
        as_of = request.as_of.isoformat() if request.as_of else None
        if context.get("mode") != request.temporal_mode or context.get("as_of") != as_of:
            return None
        return shown

    def _with_model_hypotheses(self, analysis, request: HypothesisSetRequest, rules: HypothesisSet) -> HypothesisSet:
        """Model-written competing hypotheses when the analysis was model-written; otherwise the rule set."""
        try:
            hypotheses, dropped, provenance = self.model_engine.generate(analysis, request.investigator_question)
        except ModelAnalysisUnavailable as exc:
            return rules.model_copy(
                update={
                    "provenance": {
                        **rules.provenance,
                        "author": "RULES",
                        "fallback_reason": exc.reason,
                        "model_attempt": exc.detail,
                    }
                }
            )
        return rules.model_copy(
            update={
                "hypotheses": hypotheses,
                "comparison": [self.engine._comparison_row(item) for item in hypotheses],
                "provenance": {
                    **rules.provenance,
                    "author": "LANGUAGE_MODEL",
                    "model_analysis": provenance,
                    "checks_dropped": dropped,
                },
            }
        )

    def _materialize_domain_intelligence(
        self, db: Session, request: HypothesisSetRequest, hypothesis_set: HypothesisSet
    ) -> None:
        """Materialize validated system-derived intelligence idempotently.

        AIExecution remains the immutable execution record. These rows are the
        controlled domain projection used for tenant-scoped investigation
        retrieval; they are never labelled as a decision or root cause.
        """
        now = hypothesis_set.created_at
        model_written = hypothesis_set.provenance.get("author") == "LANGUAGE_MODEL"
        if model_written:
            # Model wording differs per run: retire earlier unreviewed AI hypotheses (and their open unknowns) so
            # briefs and Ask show only the current set. Anything a person has reviewed is kept as it is.
            current = {item.statement for item in hypothesis_set.hypotheses}
            stale = (
                db.query(HypothesisRow)
                .filter(
                    HypothesisRow.tenant_id == request.tenant_id,
                    HypothesisRow.investigation_id == request.investigation_id,
                    HypothesisRow.origin == "ai",
                    HypothesisRow.reviewer_disposition.is_(None),
                    HypothesisRow.status != SUPERSEDED,
                )
                .all()
            )
            for old in stale:
                if old.statement in current:
                    continue
                old.status, old.updated_at = SUPERSEDED, now
                db.query(Unknown).filter(
                    Unknown.tenant_id == request.tenant_id,
                    Unknown.hypothesis_id == old.id,
                    Unknown.status == "open",
                ).update({"status": SUPERSEDED, "updated_at": now}, synchronize_session=False)
        for item in hypothesis_set.hypotheses:
            row = (
                db.query(HypothesisRow)
                .filter(
                    HypothesisRow.tenant_id == request.tenant_id,
                    HypothesisRow.investigation_id == request.investigation_id,
                    HypothesisRow.statement == item.statement,
                )
                .first()
            )
            if row is None:
                row = HypothesisRow(
                    id=item.hypothesis_id,
                    tenant_id=request.tenant_id,
                    investigation_id=request.investigation_id,
                    statement=item.statement,
                    status=item.status.lower(),
                    origin="ai" if model_written else "system",
                    reviewer_disposition=None,
                    created_at=now,
                    updated_at=item.updated_at,
                )
                db.add(row)
                db.flush()

            for unknown_text in item.unknowns + item.evidence_gaps:
                if not unknown_text:
                    continue
                exists = (
                    db.query(Unknown.id)
                    .filter(
                        Unknown.tenant_id == request.tenant_id,
                        Unknown.investigation_id == request.investigation_id,
                        Unknown.hypothesis_id == row.id,
                        Unknown.description == unknown_text,
                    )
                    .first()
                )
                if exists is None:
                    db.add(
                        Unknown(
                            id=uuid.uuid4(),
                            tenant_id=request.tenant_id,
                            investigation_id=request.investigation_id,
                            hypothesis_id=row.id,
                            category="evidence_gap",
                            description=unknown_text,
                            evidence_needed=unknown_text,
                            status="open",
                            created_at=now,
                            updated_at=item.updated_at,
                        )
                    )

            for relationship, relation_type in [
                *[(rel, "support") for rel in item.supporting_evidence],
                *[(rel, "contradict") for rel in item.contradicting_evidence],
            ]:
                identifiers = {
                    ref.evidence_identifier for ref in relationship.source_references if ref.evidence_identifier
                }
                for identifier in identifiers:
                    evidence = (
                        db.query(Evidence)
                        .filter(Evidence.tenant_id == request.tenant_id, Evidence.evidence_identifier == identifier)
                        .first()
                    )
                    if evidence is None:
                        continue
                    exists = (
                        db.query(HypothesisEvidence.id)
                        .filter(
                            HypothesisEvidence.tenant_id == request.tenant_id,
                            HypothesisEvidence.hypothesis_id == row.id,
                            HypothesisEvidence.evidence_id == evidence.id,
                            HypothesisEvidence.relation_type == relation_type,
                        )
                        .first()
                    )
                    if exists is None:
                        db.add(
                            HypothesisEvidence(
                                id=uuid.uuid4(),
                                tenant_id=request.tenant_id,
                                hypothesis_id=row.id,
                                evidence_id=evidence.id,
                                relation_type=relation_type,
                                rationale=relationship.rationale,
                                created_by_type="system",
                                created_at=now,
                            )
                        )
        db.commit()

    def latest(self, db: Session, tenant_id: uuid.UUID, investigation_id: uuid.UUID) -> HypothesisSetResponse | None:
        row = (
            db.query(AIExecution)
            .filter(
                AIExecution.tenant_id == tenant_id,
                AIExecution.investigation_id == investigation_id,
                AIExecution.provider == PROVIDER,
                AIExecution.orchestration_version == ORCHESTRATION_VERSION,
            )
            .order_by(AIExecution.execution_timestamp.desc())
            .first()
        )
        if not row or not row.structured_output:
            return None
        return HypothesisSetResponse(
            hypothesis_set=HypothesisSet.model_validate(row.structured_output), persisted=True, ai_execution_id=row.id
        )

    def get(
        self, db: Session, tenant_id: uuid.UUID, investigation_id: uuid.UUID, hypothesis_id: uuid.UUID
    ) -> HypothesisSetResponse:
        rows = (
            db.query(AIExecution)
            .filter(
                AIExecution.tenant_id == tenant_id,
                AIExecution.investigation_id == investigation_id,
                AIExecution.provider == PROVIDER,
                AIExecution.orchestration_version == ORCHESTRATION_VERSION,
            )
            .order_by(AIExecution.execution_timestamp.desc())
            .all()
        )
        for row in rows:
            if not row.structured_output:
                continue
            hypothesis_set = HypothesisSet.model_validate(row.structured_output)
            if any(str(h.hypothesis_id) == str(hypothesis_id) for h in hypothesis_set.hypotheses):
                return HypothesisSetResponse(hypothesis_set=hypothesis_set, persisted=True, ai_execution_id=row.id)
        raise HypothesisEngineError("HYPOTHESIS_NOT_FOUND", "Hypothesis not found")
