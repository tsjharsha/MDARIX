import uuid
from datetime import datetime, timezone
from typing import Any
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import (
    AuditEvent,
    Decision,
    Evidence,
    Investigation,
    InvestigationBrief,
    Product,
    ProductVersion,
    Hypothesis,
    Unknown,
    FailureChain,
    Scenario,
)
from investigation_workspace.schemas import InvestigationWorkspaceRequest
from investigation_workspace.service import InvestigationWorkspaceService, InvestigationWorkspaceError


class BriefError(ValueError):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message


def _same_point_in_time(temporal_context: dict, mode: str, cutoff) -> bool:
    """Whether an analysis was made for the brief's view: same temporal mode and, if historical, same as-of time."""
    if (temporal_context or {}).get("mode") != mode:
        return False
    if mode == "current":
        return True
    as_of = (temporal_context or {}).get("as_of")
    try:
        return as_of is not None and cutoff is not None and datetime.fromisoformat(as_of) == cutoff
    except (TypeError, ValueError):
        return False


class BriefService:
    def __init__(self, model_writer=None):
        self.workspace = InvestigationWorkspaceService()
        self._model_writer = model_writer

    def _model_brief(self, db, tenant_id, investigation_id, evidence, mode, cutoff) -> tuple[dict | None, dict]:
        """A model-drafted brief from the latest checked analysis, hypotheses and challenges, or why not."""
        from briefs.model_writer import ModelBriefWriter
        from challenger.service import ChallengerService
        from hypothesis_engine.service import CompetingHypothesisService
        from investigator.model_provider import ModelAnalysisUnavailable
        from investigator.service import EvidenceGroundedInvestigatorService

        analysis = EvidenceGroundedInvestigatorService().latest(db, tenant_id, investigation_id)
        hypotheses = CompetingHypothesisService().latest(db, tenant_id, investigation_id)
        challenges = ChallengerService().latest(db, tenant_id, investigation_id)
        analysis = analysis.analysis if analysis else None
        if analysis is not None and not _same_point_in_time(analysis.temporal_context, mode, cutoff):
            # The brief must describe the same point in time as the analysis it is drafted from.
            return None, {"hypothesis_set": None, "challenge_set": None, "fallback_reason": "ANALYSIS_FOR_ANOTHER_TIME"}
        hypothesis_set = hypotheses.hypothesis_set if hypotheses else None
        challenge_set = challenges.challenge_set if challenges else None
        known = {e.evidence_identifier for e in evidence}
        if analysis is not None:
            known |= {
                ref.evidence_identifier
                for item in analysis.accepted_items()
                for ref in item.source_references
                if ref.evidence_identifier
            }
        sources = {"hypothesis_set": hypothesis_set, "challenge_set": challenge_set}
        try:
            writer = self._model_writer or ModelBriefWriter()
            return writer.draft(analysis, hypothesis_set, challenge_set, known), sources
        except ModelAnalysisUnavailable as exc:
            return None, {**sources, "fallback_reason": exc.reason}

    @staticmethod
    def _record_draft(db, tenant_id, investigation_id, ai_brief: dict, request, version_num: int) -> uuid.UUID:
        from ai.execution import record_ai_execution
        from trust_engine.auto import INVESTIGATION_BRIEF

        model = ai_brief.get("model") if isinstance(ai_brief.get("model"), dict) else {}
        sections = ai_brief.get("sections") if isinstance(ai_brief.get("sections"), dict) else {}
        cited = sorted(
            {
                str(ref)
                for items in sections.values()
                if isinstance(items, list)
                for item in items
                if isinstance(item, dict)
                for ref in item.get("evidence") or []
            }
        )
        execution = record_ai_execution(
            db,
            tenant_id,
            provider=INVESTIGATION_BRIEF,
            model_name=str(model.get("model") or "unknown"),
            model_version=model.get("model_version"),
            prompt_template_version=model.get("prompt_template_version") or "brief",
            orchestration_version="R1-MVP-P6-Brief",
            investigation_id=investigation_id,
            context_refs={"temporal_mode": request.temporal_mode, "brief_version": version_num},
            evidence_refs={"evidence_identifiers": cited},
            structured_output={key: value for key, value in ai_brief.items() if key != "label"},
            validation_status="VALIDATED",
            latency_ms=model.get("latency_ms"),
            requestor_ref=str(request.generated_by),
        )
        return execution.id

    def _investigation(self, db, tenant_id, investigation_id):
        row = (
            db.query(Investigation)
            .filter(Investigation.tenant_id == tenant_id, Investigation.id == investigation_id)
            .first()
        )
        if not row:
            raise BriefError("INVESTIGATION_NOT_FOUND", "Investigation is not available for this tenant")
        return row

    def _payload(self, row: InvestigationBrief, investigation: Investigation) -> dict[str, Any]:
        return {
            "id": row.id,
            "business_id": row.business_id,
            "investigation_id": row.investigation_id,
            "investigation_business_id": investigation.business_id,
            "brief_version": row.brief_version,
            "status": row.status,
            "title": row.title,
            "temporal_mode": row.temporal_mode,
            "temporal_cutoff": row.temporal_cutoff,
            "human_review_state": row.human_review_state,
            "content": row.content,
            "provenance": row.provenance,
            "limitations": row.limitations,
            "created_at": row.created_at,
            "ai_execution_id": row.ai_execution_id,
        }

    def generate(self, db: Session, tenant_id: uuid.UUID, investigation_id: uuid.UUID, request) -> dict[str, Any]:
        inv = self._investigation(db, tenant_id, investigation_id)
        if request.temporal_mode == "current":
            cutoff = None
        else:
            cutoff = request.as_of or datetime.now(timezone.utc)
        try:
            ws = self.workspace.workspace(
                db,
                InvestigationWorkspaceRequest(
                    tenant_id=tenant_id,
                    investigation_id=investigation_id,
                    temporal_mode=request.temporal_mode,
                    as_of=cutoff,
                    include_retrieval=True,
                ),
            )
        except InvestigationWorkspaceError as exc:
            raise BriefError(exc.code, exc.message) from exc
        product = db.query(Product).filter(Product.tenant_id == tenant_id, Product.id == inv.product_id).first()
        version_id = ws.product_context.get("product_version_id")
        version = (
            db.query(ProductVersion)
            .filter(ProductVersion.tenant_id == tenant_id, ProductVersion.id == version_id)
            .first()
            if version_id
            else None
        )
        evidence = (
            db.query(Evidence)
            .filter(Evidence.tenant_id == tenant_id, Evidence.investigation_id == investigation_id)
            .all()
        )
        hypotheses = (
            db.query(Hypothesis)
            .filter(Hypothesis.tenant_id == tenant_id, Hypothesis.investigation_id == investigation_id)
            .filter(Hypothesis.status != "superseded")  # replaced by a newer model-written set
            .all()
        )
        unknowns = (
            db.query(Unknown)
            .filter(Unknown.tenant_id == tenant_id, Unknown.investigation_id == investigation_id)
            .filter(Unknown.status != "superseded")
            .all()
        )
        chains = (
            db.query(FailureChain)
            .filter(FailureChain.tenant_id == tenant_id, FailureChain.investigation_id == investigation_id)
            .all()
        )
        scenarios = (
            db.query(Scenario)
            .filter(Scenario.tenant_id == tenant_id, Scenario.investigation_id == investigation_id)
            .order_by(Scenario.created_at.desc())
            .limit(25)
            .all()
        )
        decisions = (
            db.query(Decision)
            .filter(Decision.tenant_id == tenant_id, Decision.investigation_id == investigation_id)
            .order_by(Decision.decision_timestamp.desc())
            .all()
        )
        decision = decisions[0] if decisions else None
        version_num = (
            db.query(InvestigationBrief)
            .filter(InvestigationBrief.tenant_id == tenant_id, InvestigationBrief.investigation_id == investigation_id)
            .count()
            + 1
        )
        now = datetime.now(timezone.utc)
        limitations = ws.limitations + [
            {
                "code": "NO_ROOT_CAUSE",
                "severity": "info",
                "description": "This Brief does not establish root cause or causality.",
            }
        ]
        content = {
            "investigation_identity": {
                "investigation_id": str(inv.id),
                "identifier": inv.investigation_identifier,
                "question": inv.investigation_question,
                "status": inv.status,
                "product_id": str(product.id) if product else None,
                "product": product.name if product else None,
                "product_version_id": str(version.id) if version else None,
                "product_version": version.version_identifier if version else None,
                "temporal_mode": request.temporal_mode,
                "temporal_cutoff": cutoff.isoformat() if cutoff else None,
                "brief_version": version_num,
            },
            "executive_summary": {
                "text": "This evidence-grounded Brief preserves observed context and uncertainty. It is not a root-cause conclusion.",
                "observed_facts": [inv.investigation_question],
                "derived_facts": [],
                "ai_interpretation": [],
                "uncertainty": [item["description"] for item in limitations],
            },
            "what_happened": {"statement": inv.investigation_question, "status": "UNDER_INVESTIGATION"},
            "temporal_reconstruction": ws.temporal_context,
            "key_evidence": [
                {
                    "evidence_id": str(e.id),
                    "identifier": e.evidence_identifier,
                    "title": e.title,
                    "type": e.evidence_type,
                    "source": e.source_reference,
                    "reliability": e.reliability_status,
                    "fact_type": e.fact_type,
                }
                for e in evidence
            ],
            "supporting_evidence": [],
            "contradicting_evidence": [],
            "hypotheses": [
                {"id": str(h.id), "statement": h.statement, "status": h.status, "origin": h.origin} for h in hypotheses
            ],
            "ai_challenger_findings": [],
            "unknowns": [
                {"id": str(u.id), "description": u.description, "status": u.status, "category": u.category}
                for u in unknowns
            ],
            "failure_chain": [{"id": str(c.id), "name": c.name, "status": c.status} for c in chains],
            "scenario_findings": [
                s.assumptions.get("result", {})
                for s in scenarios
                if isinstance(s.assumptions, dict) and s.assumptions.get("kind") == "SCENARIO"
            ],
            "counterfactual_analysis": {
                "status": "NOT_INCLUDED",
                "label": "HYPOTHETICAL / NON-OBSERVED ANALYSIS",
                "message": "No persisted Counterfactual result was selected for this Brief.",
            },
            "ai_advisory": {
                "label": "AI ADVISORY — HUMAN REVIEW REQUIRED",
                "status": "NOT_EMBEDDED",
                "message": "AI recommendation remains separate from this deterministic Brief.",
            },
            "supported_conclusions": ["The investigation context and listed evidence are preserved for review."],
            "not_established": [
                "Causality is not established.",
                "Root cause is not established.",
                "This Brief is not an approval, recall, CAPA, vigilance decision, or automatic closure.",
            ],
            "human_decision": {
                "present": bool(decision),
                "decision_id": str(decision.id) if decision else None,
                "disposition": decision.disposition if decision else None,
                "rationale": decision.rationale if decision else None,
                "authorized_by_ref": decision.authorized_by_ref if decision else None,
                "timestamp": decision.decision_timestamp.isoformat()
                if decision and decision.decision_timestamp
                else None,
            },
            "limitations": limitations,
        }
        ai_brief, sources = self._model_brief(db, tenant_id, investigation_id, evidence, request.temporal_mode, cutoff)
        if ai_brief is not None:
            hypothesis_set, challenge_set = sources["hypothesis_set"], sources["challenge_set"]
            sections = ai_brief["sections"]
            content["ai_brief"] = {"label": "AI DRAFT — HUMAN REVIEW REQUIRED", **ai_brief}
            content["executive_summary"] = {
                **content["executive_summary"],
                "text": ai_brief["headline"],
                "observed_facts": [item["statement"] for item in sections["what_we_know"]],
                "ai_interpretation": [item["statement"] for item in sections["leading_hypotheses"]],
            }
            if hypothesis_set is not None:
                for key, attribute in (
                    ("supporting_evidence", "supporting_evidence"),
                    ("contradicting_evidence", "contradicting_evidence"),
                ):
                    content[key] = [
                        {
                            "hypothesis": item.statement,
                            "evidence": ref.evidence_identifier,
                            "why": relation.rationale,
                        }
                        for item in hypothesis_set.hypotheses
                        for relation in getattr(item, attribute)
                        for ref in relation.source_references[:1]
                    ]
            if challenge_set is not None:
                content["ai_challenger_findings"] = [
                    {
                        "type": item.challenge_type,
                        "statement": item.statement,
                        "severity": item.severity,
                        "evidence": [ref.evidence_identifier for ref in item.evidence_references],
                        "missing": item.missing_information,
                    }
                    for item in challenge_set.challenges
                ]
            content["ai_advisory"] = {
                "label": "AI ADVISORY — HUMAN REVIEW REQUIRED",
                "status": "NOT_NEEDED",
                "message": "The language model drafted this brief; see ai_brief.",
            }
        else:
            content["ai_brief"] = {"author": "RULES", "fallback_reason": sources.get("fallback_reason")}
            from genai.grounding import advisory, build_authorized_context

            grounded = build_authorized_context(
                db,
                tenant_id=tenant_id,
                investigation_id=investigation_id,
                product_version_id=version.id if version else None,
                temporal_mode=request.temporal_mode,
                as_of=cutoff,
            )
            content["ai_advisory"] = {
                "label": "AI ADVISORY — HUMAN REVIEW REQUIRED",
                **advisory(
                    workflow="DECISION_BRIEF_DRAFT",
                    deterministic_result=content,
                    grounded_context=grounded,
                    question=inv.investigation_question,
                ),
            }
        ai_execution_id = None
        if ai_brief is not None:
            # The model's draft is an AI result like any other: saved with its provenance and the evidence it cites,
            # which gives it the automatic trust check (trust_engine/auto.py).
            ai_execution_id = self._record_draft(db, tenant_id, inv.id, ai_brief, request, version_num)
            content["ai_brief"]["ai_execution_id"] = str(ai_execution_id)
        provenance = {
            "investigation_id": str(inv.id),
            "product_id": str(inv.product_id),
            "product_version_id": str(version.id) if version else None,
            "evidence_ids": [str(e.id) for e in evidence],
            "hypothesis_ids": [str(h.id) for h in hypotheses],
            "unknown_ids": [str(u.id) for u in unknowns],
            "failure_chain_ids": [str(c.id) for c in chains],
            "scenario_ids": [str(s.id) for s in scenarios],
            "decision_id": str(decision.id) if decision else None,
            "assembler": "MDARIX-Controlled-Brief-Assembler-v1",
            "drafted_by": "LANGUAGE_MODEL" if ai_brief is not None else "RULES",
            "ground_truth_references": [],
            "generated_at": now.isoformat(),
        }
        row = InvestigationBrief(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            investigation_id=inv.id,
            product_id=inv.product_id,
            product_version_id=version.id if version else None,
            brief_version=version_num,
            status="GENERATED",
            title=f"Investigation Brief — {inv.investigation_identifier}",
            generated_by=request.generated_by,
            temporal_mode=request.temporal_mode,
            temporal_cutoff=cutoff,
            human_review_state="NOT_REVIEWED",
            decision_id=decision.id if decision else None,
            ai_execution_id=ai_execution_id,
            limitations={"items": limitations},
            content=content,
            provenance=provenance,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.add(
            AuditEvent(
                tenant_id=tenant_id,
                actor_ref=request.generated_by,
                action="BRIEF_GENERATED" if version_num == 1 else "BRIEF_REGENERATED",
                entity_type="investigation_brief",
                entity_id=row.id,
                details={"investigation_id": str(inv.id), "brief_version": version_num},
                created_at=now,
            )
        )
        db.commit()
        db.refresh(row)
        return self._payload(row, inv)

    def list(self, db, tenant_id, investigation_id):
        inv = self._investigation(db, tenant_id, investigation_id)
        return [
            self._payload(x, inv)
            for x in db.query(InvestigationBrief)
            .filter(InvestigationBrief.tenant_id == tenant_id, InvestigationBrief.investigation_id == investigation_id)
            .order_by(InvestigationBrief.brief_version.desc())
            .all()
        ]

    def get(self, db, tenant_id, investigation_id, brief_id=None, latest=False):
        inv = self._investigation(db, tenant_id, investigation_id)
        q = db.query(InvestigationBrief).filter(
            InvestigationBrief.tenant_id == tenant_id, InvestigationBrief.investigation_id == investigation_id
        )
        row = (
            q.order_by(InvestigationBrief.brief_version.desc()).first()
            if latest
            else q.filter(InvestigationBrief.id == brief_id).first()
        )
        if not row:
            raise BriefError("BRIEF_NOT_FOUND", "Investigation Brief is not available for this tenant")
        return self._payload(row, inv)
