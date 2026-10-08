import { Tabs } from "../../customer-admin/shared";
import { INTELLIGENCE_VIEWS, type IntelligenceView } from "../intelligence";
import { ContradictionsView } from "./caseIntelligence/Contradictions";
import { FailureChainView } from "./caseIntelligence/FailureChain";
import { HistoryView } from "./caseIntelligence/History";
import { HypothesesView } from "./caseIntelligence/Hypotheses";
import { ObservationsView } from "./caseIntelligence/Observations";
import { UnknownsView } from "./caseIntelligence/Unknowns";

// The views live in ./caseIntelligence/, one file per view; the chain drawing stays importable from here.
export { ChainDiagram, ChainLegend } from "./caseIntelligence/FailureChain";

/**
 * A case's intelligence: hypotheses and how people judge them, contradictions, unknowns, failure chains, observations
 * and the history of every judgement. AI output stays as the AI produced it; people record their own judgements here,
 * each with a reason. Works with AI switched off: everything can be added by hand.
 */
export function CaseIntelligencePanel({
  investigationId,
  caseLabel,
  view,
  onView,
  readOnly = false,
}: {
  investigationId: string;
  caseLabel: string;
  view: IntelligenceView;
  onView: (view: IntelligenceView) => void;
  /** A closed or cancelled case: its intelligence can be read, not changed. */
  readOnly?: boolean;
}) {
  return (
    <>
      <p className="ac-note">
        Every statement shows what kind it is and who made it. AI interpretations are suggestions to review, never facts
        or signed records; a person's judgement is recorded with its reason.
      </p>
      {readOnly && (
        <p className="ac-message tone-warning" role="note">
          This case is closed: its intelligence can be read but not changed.
        </p>
      )}
      <Tabs tabs={INTELLIGENCE_VIEWS} active={view} onChange={onView} label="Case intelligence views">
        {view === "Hypotheses" && (
          <HypothesesView investigationId={investigationId} caseLabel={caseLabel} readOnly={readOnly} />
        )}
        {view === "Contradictions" && (
          <ContradictionsView investigationId={investigationId} caseLabel={caseLabel} onView={onView} />
        )}
        {view === "Unknowns" && (
          <UnknownsView investigationId={investigationId} caseLabel={caseLabel} readOnly={readOnly} />
        )}
        {view === "Failure chain" && (
          <FailureChainView investigationId={investigationId} caseLabel={caseLabel} readOnly={readOnly} />
        )}
        {view === "Observations" && (
          <ObservationsView investigationId={investigationId} caseLabel={caseLabel} readOnly={readOnly} />
        )}
        {view === "History" && <HistoryView investigationId={investigationId} caseLabel={caseLabel} />}
      </Tabs>
    </>
  );
}
