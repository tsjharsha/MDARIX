import time
from sqlalchemy.orm import Session
from ai.execution import record_ai_execution
from backend.app.db.models.foundation import AIExecution
from hypothesis_engine.service import CompetingHypothesisService, HypothesisEngineError
from hypothesis_engine.schemas import HypothesisSetRequest
from investigator.model_provider import ModelAnalysisUnavailable
from .engine import ControlledChallenger, PROVIDER, MODEL, ORCHESTRATION_VERSION
from .model_engine import ModelChallenger
from .schemas import ChallengeRequest, ChallengeResponse, ChallengeSet


class ChallengerError(ValueError):
    def __init__(self, code, message):
        self.code, self.message = code, message


class ChallengerService:
    def __init__(self, hypothesis_service=None, engine=None, model_engine=None):
        self.hypothesis_service = hypothesis_service or CompetingHypothesisService()
        self.engine = engine or ControlledChallenger()
        self.model_engine = model_engine or ModelChallenger()

    def generate(self, db: Session, request: ChallengeRequest):
        if request.tenant_id is None:
            raise ChallengerError("TENANT_REQUIRED", "tenant_id is required")
        hs = None
        if request.hypothesis_set_id:
            latest = self.hypothesis_service.latest(db, request.tenant_id, request.investigation_id)
            if latest and latest.hypothesis_set.hypothesis_set_id == request.hypothesis_set_id:
                hs = latest.hypothesis_set
        if hs is None:
            try:
                hs = self.hypothesis_service.generate(
                    db,
                    HypothesisSetRequest(
                        tenant_id=request.tenant_id,
                        investigation_id=request.investigation_id,
                        temporal_mode=request.temporal_mode,
                        as_of=request.as_of,
                        persist=True,
                    ),
                ).hypothesis_set
            except HypothesisEngineError as e:
                raise ChallengerError(e.code, e.message) from e
        started = time.time()
        result = self.engine.generate(hs, request.user_question)
        result = self._with_model_challenges(hs, request, result)
        persisted = False
        execution_id = None
        if result.provenance.get("author") == "LANGUAGE_MODEL":
            live_advisory = {"status": "NOT_NEEDED", "reason": "The language model wrote these challenges."}
        else:
            from genai.grounding import advisory, build_authorized_context

            grounded = build_authorized_context(
                db,
                tenant_id=request.tenant_id,
                investigation_id=request.investigation_id,
                temporal_mode=request.temporal_mode,
                as_of=request.as_of,
            )
            live_advisory = advisory(
                workflow="AI_CHALLENGER",
                deterministic_result=result.model_dump(mode="json"),
                grounded_context=grounded,
                question=request.user_question,
            )
        result = result.model_copy(
            update={"provenance": {**result.provenance, "live_provider_advisory": live_advisory}}
        )
        if request.persist:
            row = record_ai_execution(
                db=db,
                tenant_id=request.tenant_id,
                investigation_id=request.investigation_id,
                provider=PROVIDER,
                model_name=result.provenance.get("model_analysis", {}).get("model", MODEL),
                model_version=result.provenance.get("model_analysis", {}).get("model_version", "1.0"),
                prompt_template_version=result.provenance.get("model_analysis", {}).get(
                    "prompt_template_version", "R1-Day13-Challenger-v1"
                ),
                orchestration_version=ORCHESTRATION_VERSION,
                context_refs={
                    "context_snapshot_id": result.context_snapshot_id,
                    "context_snapshot_version": result.context_snapshot_version,
                    "source_hypothesis_set_id": str(hs.hypothesis_set_id),
                },
                evidence_refs={
                    "challenge_ids": [str(c.challenge_id) for c in result.challenges],
                    "source_anchor_count": sum(len(c.evidence_references) for c in result.challenges),
                },
                structured_input=request.model_dump(mode="json"),
                structured_output=result.model_dump(mode="json"),
                validation_status="COMPLETED",
                latency_ms=int((time.time() - started) * 1000),
                requestor_ref="MDARIX-AI-Challenger",
            )
            db.commit()
            persisted = True
            execution_id = row.id
        return ChallengeResponse(challenge_set=result, persisted=persisted, ai_execution_id=execution_id)

    def _with_model_challenges(self, hs, request, rules):
        """Model-written challenges for model-written hypotheses; otherwise the rule-based challenges."""
        try:
            challenges, dropped, provenance = self.model_engine.generate(hs, request.user_question)
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
                "challenges": challenges,
                "no_material_challenge": not any(item.materiality == "MATERIAL" for item in challenges),
                "validation_summary": {
                    **rules.validation_summary,
                    "invented_evidence": 0,
                    "model_items_dropped_by_checks": len(dropped),
                },
                "provenance": {
                    **rules.provenance,
                    "author": "LANGUAGE_MODEL",
                    "model_analysis": provenance,
                    "checks_dropped": dropped,
                },
            }
        )

    def latest(self, db, tenant_id, investigation_id):
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
        return (
            ChallengeResponse(
                challenge_set=ChallengeSet.model_validate(row.structured_output), persisted=True, ai_execution_id=row.id
            )
            if row and row.structured_output
            else None
        )
