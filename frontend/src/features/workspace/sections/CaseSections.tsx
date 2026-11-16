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
import { renamed, useIsTrial, useWorkspace } from "../workspaceContext";
import { tabParam } from "../workspaceAddress";
import {
  CASE_SECTIONS,
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
import { isIntelligenceView, type IntelligenceView } from "../intelligence";
import { CaseHeader, ownerText } from "./CaseHeader";
import { CaseScopePanel } from "./CaseScope";
import { LotImpactPanel } from "./LotImpact";
import { CaseEvidencePanel } from "./CaseEvidence";
import { CaseIntelligencePanel } from "./CaseIntelligence";
import { CaseReviewsPanel } from "./CaseReviews";
import { CaseDecisionBriefPanel } from "./CaseDecisionBrief";
import { CaseDecisionPanel } from "./CaseDecision";
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
  const [part, setPart] = useState<string | null>(() => tabParam(requested, "part"));
  const view = tabParam(requested, "view");
  const [intelView, setIntelView] = useState<IntelligenceView>(isIntelligenceView(view) ? view : "Overview");
  // What a link carried: a review to open, a follow-up or an assessment of the decision (the former tabs' own forms).
  const [requestedReview] = useState(() => parseReviewsTab(renamed(requested, "Reviews")));
  const [requestedDecision] = useState(() => parseDecisionTab(renamed(requested, "Decision")));
  const [reviewCase] = useState(() => work.investigationId);
  const [reviewFocus, setReviewFocus] = useState(false);
  const [scopeRound, setScopeRound] = useState(0);
  // The brief's status changed (accepted for decision...): the decision form and the case's header read it again.
  const [briefRound, setBriefRound] = useState(0);
  const [lotRound, setLotRound] = useState(0);
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
      {/* One set of section controls: the progress line above (0.10.72, B2: the tabs repeated it). */}
      <section className="uw-case-body" aria-label={`Investigation section: ${active}`}>
        {active === "Summary" && (
          <>
            <DecisionBoard row={selected} readiness={readiness.data} content={brief.data?.current?.content} />
            <div className="uw-case-part" id={partId("scope")}>
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
          </>
        )}
        {active === "Evidence" && (
          <>
            <div className="uw-case-part" id={partId("evidence")}>
              <CaseEvidencePanel key={id} investigationId={id} caseLabel={caseLabel} />
            </div>
            <div className="uw-case-part" id={partId("intelligence")}>
              <CaseIntelligencePanel
                key={id}
                investigationId={id}
                caseLabel={caseLabel}
                view={intelView}
                onView={setIntelView}
                readOnly={readOnly}
              />
            </div>
            <details
              className="uw-more uw-case-part"
              id={partId("analysis")}
              open={part === "analysis" || part === "ask"}
            >
              <summary>The analysis workspace and Ask MDARIX</summary>
              <Embedded>
                <InvestigationWorkspacePanel
                  key={id}
                  investigationId={id}
                  temporalMode={work.mode}
                  asOf={work.asOf}
                  onOpenDecision={() => go("Decisions & actions", "decision")}
                  onOpenIntelligence={(next) => {
                    setIntelView(next);
                    go("Evidence", "intelligence");
                  }}
                  onOpenBrief={() => go("Decisions & actions", "brief")}
                />
              </Embedded>
              <Embedded>
                <AskMdarixPage
                  investigationId={id}
                  productVersionId={(work.view?.selected_version?.id as string | undefined) ?? undefined}
                />
              </Embedded>
            </details>
          </>
        )}
        {active === "Decisions & actions" && (
          <>
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
            <div className="uw-case-part" id={partId("decision")} hidden={isQuiet("decision")}>
              <CaseDecisionPanel
                key={`${id}:${briefRound}`}
                investigationId={id}
                caseLabel={caseLabel}
                initialFollowUp={id === reviewCase ? requestedDecision.followUp : null}
                initialAssessment={id === reviewCase ? requestedDecision.assessment : null}
                onCaseChanged={onChanged}
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
            <CaseIntegrity
              investigationId={id}
              caseLabel={caseLabel}
              onOpenDecision={() => go("Decisions & actions", "decision")}
            />
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
              <h3>For it ({supporting.length})</h3>
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
