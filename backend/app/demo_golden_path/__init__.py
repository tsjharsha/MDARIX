"""The golden path of the AcmeCare demo workspace: case ACD-INV-401 (FlowSure 300 flow interruptions) taken from a
signal all the way to a signed decision, so every Phase 1-6 screen has a worked example. Synthetic data only.

The story, dated in days before the day the workspace is loaded:

- day 63: the complaint threshold rule raises a signal (SIG...) for flow interruption on FlowSure 300 Rev 2;
- day 62: Tara Triage (PMS / Signal Triage Lead) takes it into triage, sets priority HIGH and dispositions it
  INVESTIGATION_REQUIRED; day 61: she opens the case for Ines Investigator, who accepts its task;
- scope version 1 (the signal's complaints), later complaints added by the rule, scope version 2 (one complaint
  excluded with its reason);
- evidence reviewed (accepted, accepted with a limitation, one rejected with its reason; supporting and
  contradicting), an AI-origin and a human hypothesis judged by Ines (PARTIALLY_SUPPORTED with supporting and
  contradicting links, and RETIRED), unknowns (one resolved, one accepted as a limitation), a failure chain built by
  hand with mixed link states, and observations;
- risk review (Rita Risk: RISK_CONTROL_REVIEW_REQUIRED) and regulatory review (Rory Regulatory:
  REPORTABILITY_ASSESSMENT_COMPLETE);
- Decision Brief v1 returned by Ravi Reviewer for evidence, an internal evidence request answered and reviewed into
  evidence (resolving an unknown), Decision Brief v2 accepted for decision;
- day 6: Ana Approver signs ACCEPT_WITH_CONDITIONS with a CAPA_REQUIRED follow-up and its CAPA record;
- after signing: a late complaint, and late evidence with an OPEN impact assessment.

Records are written the way the domain services write them (their helpers are called where they need no request;
otherwise rows, history and audit events are written as the endpoint writes them), each at its moment of the story.
Helpers that stamp the wall clock (workflow tasks, signals) are re-dated to the story moment afterwards; the audit
events they wrote keep the real time.

The signature is made with the signing code's own functions (``human_decision.rules``: signature material,
fingerprint, signature hash, snapshot hash; ``service.reviewers``), so verification reports VALID. Seeding is a system
action: no password is checked, and it is audited as DEMO_SEEDED (never as CASE_DECISION_SIGNED).

``seed_golden_path`` runs in a session of its own bound to the demo tenant, writes everything in one transaction
(nothing is half-seeded), is idempotent (a case already opened from a signal is left alone) and never fails the setup
or the reset: a failure is logged and reported.

The story is split by section: context, triage, case, evidence, intelligence, reviews, requests, brief, decision,
seed and status. Everything is re-exported here, so callers keep importing from backend.app.demo_golden_path.
"""

from __future__ import annotations

from backend.app.demo_golden_path.context import (
    GoldenPathSkipped,
    NEEDED_ROLES,
    SEEDED_ACTION,
    SEED_ACTOR,
    Story,
    _context,
    _opened_days,
    _person,
    logger,
    retimed,
    scope_split,
    story_moment,
    story_today,
)
from backend.app.demo_golden_path.triage import DISPOSITION_REASON, TRIAGE_PRIORITY_REASON, seed_signal, triage_signal
from backend.app.demo_golden_path.case import (
    EXCLUSION_REASON,
    SCOPE_CHANGE_REASON,
    SCOPE_OBJECTIVES,
    add_later_complaints,
    open_case,
    rescope_case,
)
from backend.app.demo_golden_path.evidence import EVIDENCE_REVIEWS, _ctx, review_case_evidence, review_evidence
from backend.app.demo_golden_path.intelligence import (
    AI_HYPOTHESIS,
    CHAIN_LINKS,
    CHAIN_NAME,
    CHAIN_NODES,
    HUMAN_HYPOTHESIS,
    HUMAN_HYPOTHESIS_RATIONALE,
    OBSERVATIONS,
    UNKNOWN_LOTS,
    UNKNOWN_REV1,
    judge_hypothesis,
    seed_ai_hypothesis,
    seed_human_intelligence,
    settle_unknown,
)
from backend.app.demo_golden_path.reviews import CASE_REVIEWS, complete_case_review
from backend.app.demo_golden_path.requests import (
    REQUEST_ITEMS,
    REQUEST_RATIONALE,
    REQUEST_TITLE,
    RESPONSE_NOTE,
    answer_evidence_request,
)
from backend.app.demo_golden_path.brief import (
    ACCEPT_COMMENT,
    BRIEF_V1,
    BRIEF_V2,
    RETURN_COMMENT,
    create_brief_version,
    quality_review,
)
from backend.app.demo_golden_path.decision import (
    CAPA_TITLE,
    DECISION_CONDITIONS,
    DECISION_RATIONALE,
    LATE_LINK_REASON,
    link_late_evidence,
    open_capa,
    record_decision_on_signal,
    sign_decision,
)
from backend.app.demo_golden_path.seed import _already_seeded, run_story, seed_golden_path, summary
from backend.app.demo_golden_path.status import LIVE_CASE, _status_of, golden_path_status

__all__ = [
    "ACCEPT_COMMENT",
    "AI_HYPOTHESIS",
    "BRIEF_V1",
    "BRIEF_V2",
    "CAPA_TITLE",
    "CASE_REVIEWS",
    "CHAIN_LINKS",
    "CHAIN_NAME",
    "CHAIN_NODES",
    "DECISION_CONDITIONS",
    "DECISION_RATIONALE",
    "DISPOSITION_REASON",
    "EVIDENCE_REVIEWS",
    "EXCLUSION_REASON",
    "GoldenPathSkipped",
    "HUMAN_HYPOTHESIS",
    "HUMAN_HYPOTHESIS_RATIONALE",
    "LATE_LINK_REASON",
    "LIVE_CASE",
    "NEEDED_ROLES",
    "OBSERVATIONS",
    "REQUEST_ITEMS",
    "REQUEST_RATIONALE",
    "REQUEST_TITLE",
    "RESPONSE_NOTE",
    "RETURN_COMMENT",
    "SCOPE_CHANGE_REASON",
    "SCOPE_OBJECTIVES",
    "SEEDED_ACTION",
    "SEED_ACTOR",
    "Story",
    "TRIAGE_PRIORITY_REASON",
    "UNKNOWN_LOTS",
    "UNKNOWN_REV1",
    "_already_seeded",
    "_context",
    "_ctx",
    "_opened_days",
    "_person",
    "_status_of",
    "add_later_complaints",
    "answer_evidence_request",
    "complete_case_review",
    "create_brief_version",
    "golden_path_status",
    "judge_hypothesis",
    "link_late_evidence",
    "logger",
    "open_capa",
    "open_case",
    "quality_review",
    "record_decision_on_signal",
    "rescope_case",
    "retimed",
    "review_case_evidence",
    "review_evidence",
    "run_story",
    "scope_split",
    "seed_ai_hypothesis",
    "seed_golden_path",
    "seed_human_intelligence",
    "seed_signal",
    "settle_unknown",
    "sign_decision",
    "story_moment",
    "story_today",
    "summary",
    "triage_signal",
]
