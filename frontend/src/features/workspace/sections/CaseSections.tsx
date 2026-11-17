import { useEffect, useState } from "react";
import { Empty, Panel } from "../../admin/console/charts";
import { useResource } from "../../customer-admin/shared";
import { ComplaintNextStep } from "./ComplaintNextStep";
import { displayId } from "../../../app/displayId";
import { offeredTab } from "../../../app/featureSet";
import { tabParts } from "../../../app/linkTable";
import { InvestigationWorkspacePanel } from "../../investigator/InvestigationWorkspacePanel";
import { AskMdarixPage } from "../../ask/AskMdarixPage";
import { CaseRecordDownload } from "../../reports/CaseRecordDownload";
import { renamed, useIsTrial, useRcaIntelligence, useRcaMethods, useWorkspace } from "../workspaceContext";
import { tabParam } from "../workspaceAddress";
import { useVisited } from "../oneStory";
import {
  CASE_SECTIONS,
  INVESTIGATION_QUESTIONS,
  caseState,
  caseSteps,
  nextCaseStep,
  readinessChecks,
  readinessPath,
  type CaseReadiness,
  type CaseSection,
} from "../caseWorkflow";
import { forAndAgainst } from "../decisionBrief";
import { parseDecisionTab } from "../decisionTabs";
import { parseReviewsTab } from "../reviews";
import {
  INTELLIGENCE_VIEWS,
  hypothesesPath,
  intelligencePath,
  isIntelligenceView,
  originGroup,
  type HypothesisList,
  type IntelligenceView,
  type Observation,
} from "../intelligence";
import { AI_UNREVIEWED_LABEL } from "../../shared/AiReview";
import { Sparkles } from "lucide-react";
import { HypothesesView } from "./caseIntelligence/Hypotheses";
import { UnknownsView } from "./caseIntelligence/Unknowns";
import { ContradictionsView } from "./caseIntelligence/Contradictions";
import { OverviewView } from "./caseIntelligence/RootCause";
import { CaseHeader, ownerText } from "./CaseHeader";
import { CaseScopePanel } from "./CaseScope";
import { LotImpactPanel } from "./LotImpact";
import { CaseEvidencePanel } from "./CaseEvidence";
import { CaseIntelligencePanel } from "./CaseIntelligence";
import { CaseReviewsPanel } from "./CaseReviews";
import { CaseDecisionBriefPanel } from "./CaseDecisionBrief";
import { CaseDecisionPanel } from "./CaseDecision";
import { DecisionSummaryView } from "./DecisionSummary";
import { DidItWorkView } from "./DidItWork";
import { CaseIntegrity, CaseTimeline } from "./CaseAudit";
import { Embedded } from "./common";

/** The Decisions & actions parts that fold into "Not started yet" while empty, with their step and checks. */
const QUIET_PARTS = [
  {
    part: "reviews",
    step: "risk_regulatory",
    checks: ["risk_review", "regulatory_review"],
    label: "Risk and regulatory reviews",
  },
  { part: "brief", step: "brief", checks: [], label: "Investigation brief" },
  { part: "decision", step: "human_review", checks: [], label: "Decision and follow-ups" },
];

/** A part of a section, for a link or the next step to scroll to (`part=brief`). */
const partId = (part: string) => `case-part-${part}`;

/** W1b: the intelligence views the Evidence section shows open, each under its question's part; the rest fold. */
const MAIN_VIEW_PART: Partial<Record<IntelligenceView, string>> = {
  Overview: "glance",
  Hypotheses: "causes",
  Unknowns: "unknowns",
  Contradictions: "unknowns",
};
export const ADVANCED_VIEWS = INTELLIGENCE_VIEWS.filter((view) => !MAIN_VIEW_PART[view]);
const viewPart = (view: IntelligenceView) => MAIN_VIEW_PART[view] ?? "advanced";

/** One question's heading (W1b), numbered in the order of INVESTIGATION_QUESTIONS. */
function Question({ n }: { n: number }) {
  return (
    <h2 className="uw-question">
      <span className="uw-num">{n}</span> {INVESTIGATION_QUESTIONS[n - 1].question}
    </h2>
  );
}

/** The six questions in order (W1b), each opening the section and part that answers it. Never the main button. */
export function QuestionGuide({
  active,
  onGo,
}: {
  active: CaseSection;
  onGo: (section: CaseSection, part: string) => void;
}) {
  return (
    <nav className="uw-question-guide" aria-label="The investigation in six questions">
      <ol>
        {INVESTIGATION_QUESTIONS.map((item, index) => (
          <li key={item.part}>
            <button
              type="button"
              aria-current={item.section === active ? "location" : undefined}
              onClick={() => onGo(item.section, item.part)}
            >
              <span className="uw-num">{index + 1}</span> {item.question}
            </button>
          </li>
        ))}
      </ol>
    </nav>
  );
}

/**
 * The AI proposals waiting for a person, at the top of the Evidence step (hero review 2, F-A2): the observations still
 * labelled "AI proposal, not reviewed" and the AI hypotheses nobody has judged, each opening its view. Nothing when
 * none waits. Exported for its test.
 */
export function AiProposalsCard({
  investigationId,
  onOpen,
}: {
  investigationId: string;
  onOpen: (view: IntelligenceView) => void;
}) {
  const observations = useResource<{ items?: Observation[] | null }>(intelligencePath(investigationId, "observations"));
  const hypotheses = useResource<HypothesisList>(hypothesesPath(investigationId));
  const waitingObservations = (observations.data?.items ?? []).filter((item) => item.ai_label === AI_UNREVIEWED_LABEL);
  const waitingHypotheses = (hypotheses.data?.items ?? []).filter(
    (item) => originGroup(item.origin) === "AI" && (!item.human_status || /^proposed$/i.test(item.human_status)),
  );
  const total = waitingObservations.length + waitingHypotheses.length;
  if (!total) return null;
  return (
    <section className="uw-card uw-card-pad uw-ai-proposals" aria-label="AI proposals">
      <h2>
        <Sparkles size={18} aria-hidden="true" /> AI proposals · {total} waiting for your review
      </h2>
      <p className="ac-muted">Each is a proposal until a person accepts, edits or rejects it.</p>
      <div className="ca-action-row">
        {waitingObservations.length > 0 && (
          // W1b: one main button per screen (the progress line's next step); these are secondary.
          <button type="button" className="ac-secondary" onClick={() => onOpen("Observations")}>
            Review {waitingObservations.length} {waitingObservations.length === 1 ? "observation" : "observations"}
          </button>
        )}
        {waitingHypotheses.length > 0 && (
          <button type="button" className="ac-secondary" onClick={() => onOpen("Hypotheses")}>
            Review {waitingHypotheses.length} {waitingHypotheses.length === 1 ? "hypothesis" : "hypotheses"}
          </button>
        )}
      </div>
    </section>
  );
}

/**
 * One investigation on the new navigation (stage 8, 8.1): the same four sections as one complaint's page, under one
 * progress line, instead of eleven tabs and a nine-step stepper.
 * - Summary: the question, the scope, lot impact and the state.
 * - Evidence: the case's evidence and its reviews, the open unknowns, hypotheses and failure chain, the analysis.
 * - Decisions & actions: the risk and regulatory reviews, the Decision Brief, the decision, the CAPA recorded for the
 *   QMS and what follows the decision.
 * - History: the audit trail, the versions and the signatures.
 * Every former tab's address opens its section and part (linkTable.json newHomes). Classic keeps the tabs.
 */
export function CaseSections({
  tab: requested,
  onManage,
  onChanged,
}: {
  tab?: string;
  onManage?: (row: Record<string, unknown>) => void;
  onChanged: () => void;
}) {
  const { work, open, reportStep, shownTab } = useWorkspace();
  const isTrial = useIsTrial();
  const [active, setActive] = useState<CaseSection>(() => offeredTab(requested, CASE_SECTIONS, "Summary"));
  const view = tabParam(requested, "view");
  // A former Intelligence link (part=intelligence&view=Unknowns) opens the view's own question (W1b).
  const [part, setPart] = useState<string | null>(() => {
    const asked = tabParam(requested, "part");
    return asked === "intelligence" && isIntelligenceView(view) ? viewPart(view) : asked;
  });
  const [intelView, setIntelView] = useState<IntelligenceView>(isIntelligenceView(view) ? view : "Overview");
  const methods = useRcaMethods();
  const overview = useRcaIntelligence();
  // What a link carried: a review to open, a follow-up or an assessment of the decision (the former tabs' own forms).
  const [requestedReview] = useState(() => parseReviewsTab(renamed(requested, "Reviews")));
  const [requestedDecision] = useState(() => parseDecisionTab(renamed(requested, "Decision")));
  const [reviewCase] = useState(() => work.investigationId);
  const [reviewFocus, setReviewFocus] = useState(false);
  const [scopeRound, setScopeRound] = useState(0);
  // The brief's status changed (accepted for decision...): the decision form and the case's header read it again.
  const [briefRound, setBriefRound] = useState(0);
  const [lotRound, setLotRound] = useState(0);
  // A decision signed (or a follow-up changed) on this screen: the decision summary reads it again.
  const [signedRound, setSignedRound] = useState(0);
  const scope = useResource<{ current?: { version: number; included_complaints?: Array<{ id: string }> } | null }>(
    work.investigationId ? `/api/v1/investigations/${encodeURIComponent(work.investigationId)}/scope` : null,
  );
  const selected = work.investigations.find((item) => String(item.id) === work.investigationId);
  const readiness = useResource<CaseReadiness>(work.investigationId ? readinessPath(work.investigationId) : null);
  const [showQuiet, setShowQuiet] = useState(false);
  const brief = useResource<{ current?: { content?: Record<string, unknown> } | null }>(
    work.investigationId ? `/api/v1/investigations/${encodeURIComponent(work.investigationId)}/decision-brief` : null,
  );
  const steps = caseSteps(readiness.data);
  // Flagship step 3 (W1) counts once the case's evidence overview has loaded.
  useVisited(
    { step: "evidence", investigationId: work.investigationId || undefined },
    active === "Evidence" && !!selected,
  );
  const nextPart = nextCaseStep(steps)?.part;
  const checks = readinessChecks(readiness.data);
  // A part with nothing in it yet folds into one line, "Not started yet: …" (0.10.72, B2); the next step, the part a
  // link asked for and a required step that blocks the decision (listed with its owner above) stay open.
  const quiet =
    readiness.data && !showQuiet
      ? QUIET_PARTS.filter(({ part: name, step, checks: own }) => {
          if (name === nextPart || name === part) return false;
          const status = steps.find((item) => item.key === step)?.status;
          const notRequired =
            own.length > 0 && own.every((key) => checks.find((check) => check.key === key)?.result === "NOT_REQUIRED");
          return status === "NOT_STARTED" || notRequired;
        })
      : [];
  const isQuiet = (name: string) => quiet.some((item) => item.part === name);
  const caseLabel = selected ? displayId(selected, "investigation_identifier") : "this investigation";
  const readOnly =
    ["CLOSED", "CANCELLED"].includes(caseState(selected) ?? "") || /^closed$/i.test(String(selected?.status ?? ""));
  // The section is part of the screen's address; the first report keeps what the link carried.
  useEffect(() => {
    // A link without a section ("?part=lot-impact") keeps what it carries on the section it opens.
    const name = tabParts(requested).name;
    reportStep?.(requested && (!name || name === active) ? renamed(requested, active) : active, "replace");
  }, []);
  const go = (next: CaseSection, nextPart?: string) => {
    setActive(next);
    setPart(nextPart ?? null);
    if (next !== active || tabParts(shownTab).name !== next) reportStep?.(next);
    if (!nextPart) window.scrollTo({ top: 0 });
  };
  // An intelligence view opens under its question; an advanced one opens the folded tools on it.
  const showView = (next: IntelligenceView) => {
    setIntelView(next);
    go("Evidence", viewPart(next));
  };
  useEffect(() => {
    if (part) document.getElementById(partId(part))?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [part, active]);
  // A link to an investigation (?case=INV000001&step=Summary) is still being opened: say so, never "No investigation
  // open" (0.10.92, A4).
  if (!work.investigationId && work.caseLink?.state === "resolving")
    return (
      <Panel title="Opening the investigation…">
        <p className="ac-muted" role="status">
          Finding {work.caseLink.id} and its product.
        </p>
      </Panel>
    );
  if (!work.investigationId)
    return (
      <Panel title="No investigation open">
        <Empty
          title="Open an investigation"
          detail="An investigation opens from its complaint, its trend or the list of investigations."
          action={
            <button type="button" className="ac-primary" onClick={() => open("Investigations", "All investigations")}>
              Open the investigations
            </button>
          }
        />
      </Panel>
    );
  const id = work.investigationId;
  // Opened a moment ago and not in the product's list yet: say so, never a header with no question, owner or due
  // date (0.10.70).
  if (!selected)
    return (
      <Panel title="Opening the investigation…">
        <p className="ac-muted" role="status">
          Reading its question, owner and due date.
        </p>
      </Panel>
    );
  return (
    <div className="uw-case-sections">
      <CaseHeader
        key={`${id}:${briefRound}`}
        investigationId={id}
        row={selected}
        onManage={onManage && selected ? () => onManage(selected) : undefined}
        onStep={() => undefined}
        onSection={go}
        onChanged={onChanged}
      />
      <QuestionGuide active={active} onGo={go} />
      {/* One set of section controls: the progress line above (0.10.72, B2: the tabs repeated it). */}
      <section className="uw-case-body" aria-label={`Investigation section: ${active}`}>
        {active === "Summary" && (
          <>
            <div className="uw-case-part" id={partId("scope")}>
              <Question n={1} />
              <CaseScopePanel
                key={`scope:${id}:${scopeRound}`}
                investigationId={id}
                caseQuestion={selected?.investigation_question ?? undefined}
                onChanged={() => setLotRound((value) => value + 1)}
              />
            </div>
            {isTrial && (
              <details className="uw-more uw-case-part" id={partId("lot-impact")} open={part === "lot-impact"}>
                <summary>Lot impact: which other lots share the suspect part</summary>
                <LotImpactPanel
                  key={`lot:${id}:${lotRound}`}
                  investigationId={id}
                  caseLabel={caseLabel}
                  focus={part === "lot-impact"}
                  onChanged={() => setScopeRound((value) => value + 1)}
                />
              </details>
            )}
            {/* Where the case stands on the later questions: the leading explanation, for and against, and blocks. */}
            <DecisionBoard row={selected} readiness={readiness.data} content={brief.data?.current?.content} />
          </>
        )}
        {active === "Evidence" && (
          <>
            {/* Hero review 2: Ask leads when asked for (F-A3); the method tabs come first and the evidence table is
                folded under them (F-R1), so the root-cause tools are on the first screen. */}
            {part === "ask" && (
              <div className="uw-case-part" id={partId("ask")}>
                <Embedded>
                  <AskMdarixPage
                    investigationId={id}
                    productVersionId={(work.view?.selected_version?.id as string | undefined) ?? undefined}
                  />
                </Embedded>
              </div>
            )}
            {/* W1b: questions 2 to 4 in order, open; the advanced tools folded below them. */}
            <div className="uw-case-questions" id={partId("intelligence")}>
              <p className="ac-note">Every statement shows its kind and its author. AI suggestions are never facts.</p>
              {readOnly && (
                <p className="ac-message tone-warning" role="note">
                  This investigation is closed: its intelligence can be read but not changed.
                </p>
              )}
              <div className="uw-case-part" id={partId("glance")}>
                <Question n={2} />
                {overview && (
                  <OverviewView investigationId={id} caseLabel={caseLabel} onView={showView} methods={methods} />
                )}
                <details className="uw-more" id={partId("evidence")} open={part === "evidence" || !overview}>
                  <summary>The evidence records</summary>
                  <CaseEvidencePanel key={id} investigationId={id} caseLabel={caseLabel} />
                </details>
              </div>
              <div className="uw-case-part" id={partId("causes")}>
                <Question n={3} />
                <AiProposalsCard investigationId={id} onOpen={showView} />
                <HypothesesView key={id} investigationId={id} caseLabel={caseLabel} readOnly={readOnly} />
              </div>
              <div className="uw-case-part" id={partId("unknowns")}>
                <Question n={4} />
                <UnknownsView key={id} investigationId={id} caseLabel={caseLabel} readOnly={readOnly} />
                <ContradictionsView investigationId={id} caseLabel={caseLabel} onView={showView} />
              </div>
            </div>
            <details className="uw-more uw-case-part" id={partId("advanced")} open={part === "advanced"}>
              <summary>Advanced: challenges, failure chains, observations, root-cause tools and history</summary>
              <CaseIntelligencePanel
                key={id}
                investigationId={id}
                caseLabel={caseLabel}
                view={intelView}
                onView={showView}
                readOnly={readOnly}
                only={ADVANCED_VIEWS}
              />
            </details>
            <details className="uw-more uw-case-part" id={partId("analysis")} open={part === "analysis"}>
              <summary>{part === "ask" ? "The analysis workspace" : "The analysis workspace and Ask MDARIX"}</summary>
              <Embedded>
                <InvestigationWorkspacePanel
                  key={id}
                  investigationId={id}
                  temporalMode={work.mode}
                  asOf={work.asOf}
                  onOpenDecision={() => go("Decisions & actions", "decision")}
                  onOpenIntelligence={showView}
                  onOpenBrief={() => go("Decisions & actions", "brief")}
                />
              </Embedded>
              {part !== "ask" && (
                <Embedded>
                  <AskMdarixPage
                    investigationId={id}
                    productVersionId={(work.view?.selected_version?.id as string | undefined) ?? undefined}
                  />
                </Embedded>
              )}
            </details>
          </>
        )}
        {active === "Decisions & actions" && (
          <>
            {/* E3 + W6: once signed, the decision and its impact lead the section, on one screen. */}
            <div className="uw-case-part" id={partId(part === "record" ? "record" : "summary")}>
              <DecisionSummaryView
                key={`${id}:${briefRound}:${signedRound}`}
                investigationId={id}
                recordOpen={part === "record"}
              />
            </div>
            <Question n={5} />
            {quiet.length > 0 && (
              <p className="uw-cr-meta uw-not-started">
                Not started yet: {quiet.map((item) => item.label).join(", ")} ·{" "}
                <button type="button" className="ac-link" onClick={() => setShowQuiet(true)}>
                  Show
                </button>
              </p>
            )}
            <div className="uw-case-part" id={partId("reviews")} hidden={isQuiet("reviews")}>
              <CaseReviewsPanel
                key={id}
                investigationId={id}
                caseLabel={caseLabel}
                initialReview={id === reviewCase ? requestedReview : null}
                readOnly={readOnly}
              />
            </div>
            <div className="uw-case-part" id={partId("brief")} hidden={isQuiet("brief")}>
              <CaseDecisionBriefPanel
                key={id}
                investigationId={id}
                caseLabel={caseLabel}
                readOnly={readOnly}
                focusReview={reviewFocus}
                onOpenDecision={() => go("Decisions & actions", "decision")}
                onChanged={() => {
                  setBriefRound((round) => round + 1);
                  readiness.reload();
                  brief.reload();
                  onChanged();
                }}
              />
            </div>
            <Question n={6} />
            <div className="uw-case-part" id={partId("decision")} hidden={isQuiet("decision")}>
              <CaseDecisionPanel
                key={`${id}:${briefRound}`}
                investigationId={id}
                caseLabel={caseLabel}
                initialFollowUp={id === reviewCase ? requestedDecision.followUp : null}
                initialAssessment={id === reviewCase ? requestedDecision.assessment : null}
                onCaseChanged={() => {
                  setSignedRound((round) => round + 1);
                  onChanged();
                }}
                onReviewBrief={() => {
                  setReviewFocus(true);
                  go("Decisions & actions", "brief");
                }}
              />
            </div>
            {/* B5b: what happened after the signed decision (hidden while the switch is off). */}
            <div className="uw-case-part" id={partId("did-it-work")}>
              <DidItWorkView key={`${id}:${briefRound}`} investigationId={id} caseLabel={caseLabel} />
            </div>
            {/* An investigation opened from one complaint ends with that complaint's next step (8.7). */}
            {scope.data?.current?.included_complaints?.length === 1 && (
              <ComplaintNextStep
                complaintId={scope.data.current.included_complaints[0].id}
                here="Decision"
                refreshKey={String(scope.data.current.version)}
              />
            )}
          </>
        )}
        {active === "History" && (
          <>
            <Panel eyebrow="History" title={`The record of ${caseLabel}`}>
              <p className="ac-muted">
                Everything this investigation holds, from its question and evidence to its reviews, decision and audit
                trail, in one record you can hand an inspector.
              </p>
              <CaseRecordDownload investigationId={id} label={caseLabel} />
            </Panel>
            <CaseTimeline
              investigationId={id}
              caseLabel={caseLabel}
              onOpenDecision={() => go("Decisions & actions", "decision")}
            />
            <details className="uw-more uw-case-part" id={partId("trust")} open={part === "trust"}>
              <summary>Trust details: the integrity checks of this record</summary>
              <CaseIntegrity
                investigationId={id}
                caseLabel={caseLabel}
                onOpenDecision={() => go("Decisions & actions", "decision")}
              />
            </details>
          </>
        )}
      </section>
    </div>
  );
}

/**
 * The investigation's Summary leads with what the decision rests on (0.10.72, B2): the leading explanation with the
 * evidence for and against it, and what blocks the decision, each open item with its owner. The full scope, its
 * versions and the lot impact are below it, revealed on request.
 */
export function DecisionBoard({
  row,
  readiness,
  content,
}: {
  row: Record<string, unknown> | null | undefined;
  readiness: CaseReadiness | null | undefined;
  /** The current Decision Brief's content, where one is composed. */
  content: Record<string, unknown> | null | undefined;
}) {
  const { leading, supporting, contradicting } = forAndAgainst(content);
  const blocking = readinessChecks(readiness).filter(
    (check) => (check.result === "BLOCKED" || check.result === "PENDING") && check.key !== "decision",
  );
  const inReview = String(readiness?.workflow_state ?? "") === "BRIEF_IN_REVIEW";
  const owner = (key: string) =>
    key === "brief_ready" && inReview ? "A quality reviewer (not the author)" : ownerText(row);
  return (
    <Panel eyebrow="The decision" title="What the decision rests on">
      {leading ? (
        <>
          <p>
            <strong>Leading explanation:</strong> {leading}
          </p>
          <div className="uw-board-sides">
            <section aria-label="Evidence for it">
              <h3>For the leading explanation ({supporting.length})</h3>
              {supporting.length ? (
                <ul>
                  {supporting.map((line) => (
                    <li key={line.key}>
                      {line.label}
                      {line.detail ? <small> · {line.detail}</small> : null}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="ac-muted">Nothing recorded for it yet.</p>
              )}
            </section>
            <section aria-label="Evidence against it">
              <h3>Against it ({contradicting.length})</h3>
              {contradicting.length ? (
                <ul>
                  {contradicting.map((line) => (
                    <li key={line.key}>
                      {line.label}
                      {line.detail ? <small> · {line.detail}</small> : null}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="ac-muted">Nothing recorded against it.</p>
              )}
            </section>
          </div>
        </>
      ) : (
        <p className="ac-muted">
          No leading explanation yet: a person judges the hypotheses on the evidence (Evidence section).
        </p>
      )}
      <section aria-label="What blocks the decision">
        <h3>What blocks the decision</h3>
        {!readiness ? (
          <p className="ac-muted" role="status">
            Reading what is still open…
          </p>
        ) : blocking.length ? (
          <ul className="uw-board-blocks">
            {blocking.map((check) => (
              <li key={check.key}>
                <strong>{check.label}</strong>
                {check.rationale ? `: ${check.rationale}` : ""} · Owner: {owner(check.key)}
              </li>
            ))}
          </ul>
        ) : (
          <p className="ac-muted">Nothing blocks the decision.</p>
        )}
      </section>
    </Panel>
  );
}
