import { useEffect, useState } from "react";
import { Empty, Panel } from "../../admin/console/charts";
import { useResource } from "../../customer-admin/shared";
import { ComplaintNextStep } from "./ComplaintNextStep";
import { displayId } from "../../../app/displayId";
import { tabParts } from "../../../app/linkTable";
import { InvestigationWorkspacePanel } from "../../investigator/InvestigationWorkspacePanel";
import { AskMdarixPage } from "../../ask/AskMdarixPage";
import { CaseRecordDownload } from "../../reports/CaseRecordDownload";
import {
  renamed,
  useChallenge,
  useIsTrial,
  useRcaIntelligence,
  useRcaMethods,
  useWorkspace,
} from "../workspaceContext";
import { tabParam } from "../workspaceAddress";
import { AI_PROPOSALS_PART, useVisited } from "../oneStory";
import {
  caseState,
  caseSteps,
  cockpitStep,
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
import { FishboneView, FiveWhysView, OverviewView } from "./caseIntelligence/RootCause";
import { ChallengeView } from "./caseIntelligence/Challenge";
import { FailureChainView } from "./caseIntelligence/FailureChain";
import { ObservationsView } from "./caseIntelligence/Observations";
import { HistoryView } from "./caseIntelligence/History";
import { CaseHeader, ownerText } from "./CaseHeader";
import { CaseScopePanel } from "./CaseScope";
import { LotImpactPanel } from "./LotImpact";
import { CaseEvidencePanel } from "./CaseEvidence";
import { CaseReviewsPanel } from "./CaseReviews";
import { CaseDecisionBriefPanel } from "./CaseDecisionBrief";
import { CaseDecisionPanel } from "./CaseDecision";
import { DecisionSummaryView } from "./DecisionSummary";
import { DidItWorkView } from "./DidItWork";
import { CaseIntegrity, CaseTimeline } from "./CaseAudit";
import { Embedded } from "./common";
import { Fold, StepHeading } from "./Cockpit";
import { VersionCompareCard } from "./VersionCompare";

/** The parts that fold into "Not started yet" while empty, with their cockpit step, recorded step and checks. */
const QUIET_PARTS: ReadonlyArray<{ part: string; in: CaseSection; step: string; checks: string[]; label: string }> = [
  {
    part: "reviews",
    in: "Brief",
    step: "risk_regulatory",
    checks: ["risk_review", "regulatory_review"],
    label: "Risk and regulatory reviews",
  },
  { part: "brief", in: "Brief", step: "brief", checks: [], label: "Investigation brief" },
  { part: "decision", in: "Decision & action", step: "human_review", checks: [], label: "Decision and follow-ups" },
];

/** A part of a step, for a link or the next step to scroll to (`part=brief`). */
const partId = (part: string) => `case-part-${part}`;

/** The intelligence views a step shows open (W1b); every other view is one of Possible causes' named tools (UX3). */
const MAIN_VIEW_PLACE: Partial<Record<IntelligenceView, { section: CaseSection; part: string }>> = {
  Overview: { section: "Evidence", part: "glance" },
  Hypotheses: { section: "Possible causes", part: "causes" },
  Unknowns: { section: "Evidence", part: "unknowns" },
  Contradictions: { section: "Evidence", part: "unknowns" },
};
export const ADVANCED_VIEWS = INTELLIGENCE_VIEWS.filter((view) => !MAIN_VIEW_PLACE[view]);
/** Each cause tool's name on its fold. */
const TOOL_LABEL: Partial<Record<IntelligenceView, string>> = {
  Fishbone: "Fishbone: causes by category",
  "5 Whys": "5 Whys",
  "Failure chain": "Failure chains: how a cause leads to the failure",
  Observations: "Observations",
  Challenge: "Challenge: questions drawn from the records",
  History: "Judgement history: who changed what, and why",
};

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
    <section className="uw-card uw-card-pad uw-ai-proposals" aria-label="AI proposals" id={partId(AI_PROPOSALS_PART)}>
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
 * One investigation on the new navigation: the investigation cockpit (UX3, Persona Blueprint wave C). A summary strip
 * and one 6-step rail (Cockpit.tsx) over the step shown:
 * - Signal: the question and the complaints in scope.
 * - Product reality: the version the complaints carry beside the one before it, and the lots that share the part.
 * - Evidence: what is known and what is not, the evidence records, the open unknowns and contradictions, Ask MDARIX.
 * - Possible causes: the AI proposals waiting for a person, the hypotheses, and the cause tools (fishbone, 5 Whys,
 *   failure chains, observations, challenges, judgement history, the AI analysis workspace), each a named fold.
 * - Brief: what the decision rests on, the risk and regulatory reviews, the Investigation Brief.
 * - Decision & action: the signed decision, its CAPA and follow-ups, did it work, and the record with its history.
 * Every former address (the four sections and their parts, linkTable.json newHomes) opens its step (cockpitStep).
 * Classic keeps the tabs.
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
  const view = tabParam(requested, "view");
  const [first] = useState(() => cockpitStep(tabParts(requested).name, tabParam(requested, "part"), view));
  const [active, setActive] = useState<CaseSection>(first?.section ?? "Signal");
  const [part, setPart] = useState<string | null>(first?.part ?? null);
  const [intelView, setIntelView] = useState<IntelligenceView | null>(
    isIntelligenceView(view) && !MAIN_VIEW_PLACE[view] ? view : null,
  );
  const methods = useRcaMethods();
  const overview = useRcaIntelligence();
  const challenge = useChallenge();
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
  // Flagship step 5 (UX1) counts once the brief, accepted for decision by the sample reviewer, has loaded.
  useVisited(
    { step: "brief", investigationId: work.investigationId || undefined },
    active === "Brief" && part === "brief" && brief.state === "ready" && !!brief.data?.current,
  );
  // A link to another part of this investigation while it is open (the flagship's Next) moves there (UX1): the part
  // was read only when the page opened, so the link reloaded the page in place.
  const askedPart = tabParam(requested, "part");
  const askedSection = tabParts(requested).name;
  useEffect(() => {
    if (!askedPart) return;
    const place = cockpitStep(askedSection, askedPart, tabParam(requested, "view"));
    if (!place) return;
    setActive(place.section);
    setPart(place.part);
    if (place.part) document.getElementById(partId(place.part))?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [askedPart, askedSection]);
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
  const quietIn = (step: CaseSection) => {
    const here = quiet.filter((item) => item.in === step);
    return here.length ? (
      <p className="uw-cr-meta uw-not-started">
        Not started yet: {here.map((item) => item.label).join(", ")} ·{" "}
        <button type="button" className="ac-link" onClick={() => setShowQuiet(true)}>
          Show
        </button>
      </p>
    ) : null;
  };
  const caseLabel = selected ? displayId(selected, "investigation_identifier") : "this investigation";
  const readOnly =
    ["CLOSED", "CANCELLED"].includes(caseState(selected) ?? "") || /^closed$/i.test(String(selected?.status ?? ""));
  // The step is part of the screen's address; the first report keeps what the link carried, under the step's name.
  useEffect(() => {
    reportStep?.(requested ? renamed(requested, active) : active, "replace");
  }, []);
  const go = (next: CaseSection, nextPart?: string) => {
    setActive(next);
    setPart(nextPart ?? null);
    if (next !== active || tabParts(shownTab).name !== next) reportStep?.(next);
    if (!nextPart) window.scrollTo({ top: 0 });
  };
  // An intelligence view opens in its own step; a cause tool opens its fold in Possible causes.
  const showView = (next: IntelligenceView) => {
    const main = MAIN_VIEW_PLACE[next];
    if (main) return go(main.section, main.part);
    setIntelView(next);
    go("Possible causes", "advanced");
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
  const product = work.products.find((item) => item.id === String(selected.product_id ?? work.productId ?? ""));
  const tools = ADVANCED_VIEWS.filter(
    (item) => (challenge || item !== "Challenge") && (methods || (item !== "Fishbone" && item !== "5 Whys")),
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
        active={active}
        onChanged={onChanged}
      />
      <section className="uw-case-body" aria-label={`Investigation step: ${active}`}>
        <StepHeading step={active} />
        {active === "Signal" && (
          <div className="uw-case-part" id={partId("scope")}>
            <CaseScopePanel
              key={`scope:${id}:${scopeRound}`}
              investigationId={id}
              caseQuestion={selected?.investigation_question ?? undefined}
              onChanged={() => setLotRound((value) => value + 1)}
            />
          </div>
        )}
        {active === "Product reality" && (
          <>
            {/* The product's version beside the one before it, in one click (the Product Lifecycle Twin). */}
            <VersionCompareCard
              product={(product?.product_identifier as string | undefined) ?? null}
              productName={(product?.name as string | undefined) ?? null}
              version={(selected.version_identifier as string | undefined) ?? null}
            />
            {isTrial && (
              <div className="uw-case-part" id={partId("lot-impact")}>
                <h3>Lot impact: which other lots share the suspect part</h3>
                <LotImpactPanel
                  key={`lot:${id}:${lotRound}`}
                  investigationId={id}
                  caseLabel={caseLabel}
                  focus={part === "lot-impact"}
                  onChanged={() => setScopeRound((value) => value + 1)}
                />
              </div>
            )}
          </>
        )}
        {active === "Evidence" && (
          <>
            {/* Hero review 2: Ask leads when asked for (F-A3). */}
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
            <p className="ac-note">Every statement shows its kind and its author. AI suggestions are never facts.</p>
            {readOnly && (
              <p className="ac-message tone-warning" role="note">
                This investigation is closed: its intelligence can be read but not changed.
              </p>
            )}
            <div className="uw-case-part" id={partId("glance")}>
              {overview && (
                <OverviewView investigationId={id} caseLabel={caseLabel} onView={showView} methods={methods} />
              )}
              <details className="uw-more" id={partId("evidence")} open={part === "evidence" || !overview}>
                <summary>The evidence records</summary>
                <CaseEvidencePanel key={id} investigationId={id} caseLabel={caseLabel} />
              </details>
            </div>
            <div className="uw-case-part" id={partId("unknowns")}>
              <h3>What we still do not know</h3>
              <UnknownsView key={id} investigationId={id} caseLabel={caseLabel} readOnly={readOnly} />
              <ContradictionsView investigationId={id} caseLabel={caseLabel} onView={showView} />
            </div>
            {part !== "ask" && (
              <Fold summary="Ask MDARIX about this investigation">
                <Embedded>
                  <AskMdarixPage
                    investigationId={id}
                    productVersionId={(work.view?.selected_version?.id as string | undefined) ?? undefined}
                  />
                </Embedded>
              </Fold>
            )}
          </>
        )}
        {active === "Possible causes" && (
          <>
            <div className="uw-case-part" id={partId("causes")}>
              <AiProposalsCard investigationId={id} onOpen={showView} />
              <HypothesesView key={id} investigationId={id} caseLabel={caseLabel} readOnly={readOnly} />
            </div>
            {/* The cause tools, each a named fold (the Advanced drawer and its tab list before UX3). */}
            <div className="uw-case-part" id={partId("advanced")}>
              <h3>More ways to test a cause</h3>
              {tools.map((tool) => {
                const opened = part === "advanced" && intelView === tool;
                return (
                  <Fold key={`${tool}:${opened}`} summary={TOOL_LABEL[tool] ?? tool} initiallyOpen={opened}>
                    {tool === "Fishbone" && (
                      <FishboneView investigationId={id} caseLabel={caseLabel} readOnly={readOnly} />
                    )}
                    {tool === "5 Whys" && (
                      <FiveWhysView investigationId={id} caseLabel={caseLabel} readOnly={readOnly} onView={showView} />
                    )}
                    {tool === "Failure chain" && (
                      <FailureChainView investigationId={id} caseLabel={caseLabel} readOnly={readOnly} />
                    )}
                    {tool === "Observations" && (
                      <ObservationsView investigationId={id} caseLabel={caseLabel} readOnly={readOnly} />
                    )}
                    {tool === "Challenge" && (
                      <ChallengeView investigationId={id} caseLabel={caseLabel} readOnly={readOnly} />
                    )}
                    {tool === "History" && <HistoryView investigationId={id} caseLabel={caseLabel} />}
                  </Fold>
                );
              })}
              <Fold
                key={`analysis:${part === "analysis"}`}
                id={partId("analysis")}
                summary="The AI analysis workspace: run the analysis, hypotheses and a brief draft"
                initiallyOpen={part === "analysis"}
              >
                <Embedded>
                  <InvestigationWorkspacePanel
                    key={id}
                    investigationId={id}
                    temporalMode={work.mode}
                    asOf={work.asOf}
                    onOpenDecision={() => go("Decision & action", "decision")}
                    onOpenIntelligence={showView}
                    onOpenBrief={() => go("Brief", "brief")}
                  />
                </Embedded>
              </Fold>
            </div>
          </>
        )}
        {active === "Brief" && (
          <>
            <div className="uw-case-part" id={partId("board")}>
              <DecisionBoard row={selected} readiness={readiness.data} content={brief.data?.current?.content} />
            </div>
            {quietIn("Brief")}
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
                onOpenDecision={() => go("Decision & action", "decision")}
                onChanged={() => {
                  setBriefRound((round) => round + 1);
                  readiness.reload();
                  brief.reload();
                  onChanged();
                }}
              />
            </div>
          </>
        )}
        {active === "Decision & action" && (
          <>
            {/* E3 + W6: once signed, the decision and its impact lead the step, on one screen. */}
            <div className="uw-case-part" id={partId(part === "record" ? "record" : "summary")}>
              <DecisionSummaryView
                key={`${id}:${briefRound}:${signedRound}`}
                investigationId={id}
                recordOpen={part === "record"}
              />
            </div>
            {quietIn("Decision & action")}
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
                  go("Brief", "brief");
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
            {/* The record and its history (the History section before UX3), folded at the end of the story. */}
            <Fold
              key={`history:${part === "history" || part === "trust"}`}
              id={partId("history")}
              summary="The record: download, history and trust details"
              initiallyOpen={part === "history" || part === "trust"}
            >
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
                onOpenDecision={() => go("Decision & action", "decision")}
              />
              <details className="uw-more uw-case-part" id={partId("trust")} open={part === "trust"}>
                <summary>Trust details: the integrity checks of this record</summary>
                <CaseIntegrity
                  investigationId={id}
                  caseLabel={caseLabel}
                  onOpenDecision={() => go("Decision & action", "decision")}
                />
              </details>
            </Fold>
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
