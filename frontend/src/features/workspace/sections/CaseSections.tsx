import { useEffect, useState } from "react";
import { Empty, Panel } from "../../admin/console/charts";
import { Tabs, useResource } from "../../customer-admin/shared";
import { ComplaintNextStep } from "./ComplaintNextStep";
import { displayId } from "../../../app/displayId";
import { offeredTab } from "../../../app/featureSet";
import { tabParts } from "../../../app/linkTable";
import { InvestigationWorkspacePanel } from "../../investigator/InvestigationWorkspacePanel";
import { AskMdarixPage } from "../../ask/AskMdarixPage";
import { CaseRecordDownload } from "../../reports/CaseRecordDownload";
import { renamed, useIsTrial, useWorkspace } from "../workspaceContext";
import { tabParam } from "../workspaceAddress";
import { CASE_SECTIONS, caseState, type CaseSection } from "../caseWorkflow";
import { parseDecisionTab } from "../decisionTabs";
import { parseReviewsTab } from "../reviews";
import { isIntelligenceView, type IntelligenceView } from "../intelligence";
import { CaseHeader } from "./CaseHeader";
import { CaseScopePanel } from "./CaseScope";
import { LotImpactPanel } from "./LotImpact";
import { CaseEvidencePanel } from "./CaseEvidence";
import { CaseIntelligencePanel } from "./CaseIntelligence";
import { CaseReviewsPanel } from "./CaseReviews";
import { CaseDecisionBriefPanel } from "./CaseDecisionBrief";
import { CaseDecisionPanel } from "./CaseDecision";
import { CaseIntegrity, CaseTimeline } from "./CaseAudit";
import { Embedded } from "./common";

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
  const [intelView, setIntelView] = useState<IntelligenceView>(isIntelligenceView(view) ? view : "Hypotheses");
  // What a link carried: a review to open, a follow-up or an assessment of the decision (the former tabs' own forms).
  const [requestedReview] = useState(() => parseReviewsTab(renamed(requested, "Reviews")));
  const [requestedDecision] = useState(() => parseDecisionTab(renamed(requested, "Decision")));
  const [reviewCase] = useState(() => work.investigationId);
  const [reviewFocus, setReviewFocus] = useState(false);
  const [scopeRound, setScopeRound] = useState(0);
  const [lotRound, setLotRound] = useState(0);
  const scope = useResource<{ current?: { version: number; included_complaints?: Array<{ id: string }> } | null }>(
    work.investigationId ? `/api/v1/investigations/${encodeURIComponent(work.investigationId)}/scope` : null,
  );
  const selected = work.investigations.find((item) => String(item.id) === work.investigationId);
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
        key={id}
        investigationId={id}
        row={selected}
        onManage={onManage && selected ? () => onManage(selected) : undefined}
        onLotImpact={isTrial ? () => go("Summary", "lot-impact") : undefined}
        onStep={() => undefined}
        onSection={go}
        onChanged={onChanged}
      />
      <Tabs tabs={CASE_SECTIONS} active={active} onChange={(next) => go(next)} label="Investigation sections">
        {active === "Summary" && (
          <>
            <div className="uw-case-part" id={partId("scope")}>
              <CaseScopePanel
                key={`scope:${id}:${scopeRound}`}
                investigationId={id}
                caseQuestion={selected?.investigation_question ?? undefined}
                onChanged={() => setLotRound((value) => value + 1)}
              />
            </div>
            {isTrial && (
              <div className="uw-case-part" id={partId("lot-impact")}>
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
            <div className="uw-case-part" id={partId("reviews")}>
              <CaseReviewsPanel
                key={id}
                investigationId={id}
                caseLabel={caseLabel}
                initialReview={id === reviewCase ? requestedReview : null}
                readOnly={readOnly}
              />
            </div>
            <div className="uw-case-part" id={partId("brief")}>
              <CaseDecisionBriefPanel
                key={id}
                investigationId={id}
                caseLabel={caseLabel}
                readOnly={readOnly}
                focusReview={reviewFocus}
                onOpenDecision={() => go("Decisions & actions", "decision")}
              />
            </div>
            <div className="uw-case-part" id={partId("decision")}>
              <CaseDecisionPanel
                key={id}
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
      </Tabs>
    </div>
  );
}
