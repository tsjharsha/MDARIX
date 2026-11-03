import { deadlineLabel, timeLeft } from "../../../app/dates";
import {
  CONCLUSION_LABELS,
  type AssessmentDetail,
  type MarketItem,
  type Question,
  type Suggestion,
} from "../marketAssessment";
import type { QuestionGroup, TreeForm } from "../treeAnswer";
import type { TreeMarket, TreePath } from "../decisionTrees";

export type HarmState = { level: string; reason: string; disagreement: string };

/** The outcome, live from the saved answers: Reportable · type · rule · due date, Not reportable, or Pending
 * information; its "Why" chips jump to the answers that lead to it. */
export function SignCard({
  item,
  outcome,
  chips,
  signed,
}: {
  detail: AssessmentDetail;
  item: MarketItem;
  tree: TreeMarket | null;
  path: TreePath | null;
  outcome: Suggestion | null;
  chips: { id: string; label: string }[];
  signed: boolean;
  canDecide: boolean;
  groups: QuestionGroup[];
  form: TreeForm;
  folded: Record<string, string>;
  harm: HarmState;
  onHarm: (next: HarmState) => void;
  flush: () => Promise<MarketItem | null>;
  onSigned: (next: MarketItem) => void;
  flat: readonly Question[];
}) {
  const version = signed ? item.current : item.draft;
  const tone = outcome === "REPORTABLE" ? "is-rep" : outcome === "NOT_REPORTABLE" ? "is-not" : "is-open";
  const clock = signed && item.current?.due_on ? { due_date: item.current.due_on } : item.clock;
  return (
    <section className={`uw-card dt-outcome ${tone}`} id="dt-outcome" aria-live="polite" aria-label="The outcome">
      <p className="ac-eyebrow">{signed ? "Signed conclusion" : "Points to"}</p>
      <p className="dt-big">{outcome ? CONCLUSION_LABELS[outcome] : "Not decided yet"}</p>
      {outcome === "REPORTABLE" && version?.report_type_label && <p className="dt-type">{version.report_type_label}</p>}
      {outcome && outcome !== "NOT_REPORTABLE" && clock && (
        <p>
          Due <b>{deadlineLabel(clock)}</b>
          {"days_left" in clock ? ` · ${timeLeft(clock)}` : ""}
        </p>
      )}
      {!outcome && <p className="ac-muted">The outcome updates as you answer.</p>}
      {!signed &&
        (item.evaluation?.notes ?? []).map((note) => (
          <p key={note} className="dt-hint">
            {note}
          </p>
        ))}
      {chips.length > 0 && (
        <p className="dt-whys">
          <span className="ac-muted">Why:</span>
          {chips.map((chip) => (
            <a key={chip.id} className="dt-whychip" href={`#q-${chip.id}`}>
              {chip.label}
            </a>
          ))}
        </p>
      )}
    </section>
  );
}
