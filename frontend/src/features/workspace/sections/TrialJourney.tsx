import { BookOpen, CheckCircle2, ChevronRight, ListChecks } from "lucide-react";
import { Panel, type PanelSource } from "../../admin/console/charts";
import { TRIAL_GUIDE_PATH, type JourneyKey, type JourneyStep } from "../../help/trialGuide";
import { USER_GUIDE_PATH } from "../../help/userGuide";

/** What each unfinished step's button says. */
const GO: Partial<Record<JourneyKey, string>> = {
  team: "Invite colleagues",
  sample: "Continue the story",
  "own-data": "Upload your data",
  feedback: "Share feedback",
  demo: "Book the demo",
};

/**
 * The trial journey in Getting started: the seven steps of the free trial user guide (/help/trial-guide), each ticked
 * from the trial's own records, with a button for the next one and the guide one click away.
 */
export function TrialJourney({
  steps,
  source,
  onGo,
}: {
  steps: readonly JourneyStep[];
  source?: PanelSource;
  onGo: (key: JourneyKey) => void;
}) {
  const done = steps.filter((step) => step.done).length;
  const next = steps.find((step) => !step.done) ?? null;
  return (
    <Panel
      eyebrow="Your trial journey"
      title={next ? `${done} of ${steps.length} steps done · next: ${next.title.toLowerCase()}` : "Every step done"}
      source={source}
      action={
        <span className="uw-journey-guides">
          <a className="ac-secondary" href={TRIAL_GUIDE_PATH} target="_blank" rel="noopener">
            <BookOpen size={15} aria-hidden="true" /> Free trial user guide
          </a>
          <a className="ac-secondary" href={USER_GUIDE_PATH} target="_blank" rel="noopener">
            <ListChecks size={15} aria-hidden="true" /> Step-by-step user guide
          </a>
        </span>
      }
    >
      <ol className="uw-journey">
        {steps.map((step, index) => {
          const isNext = step.key === next?.key;
          return (
            <li key={step.key} className={`uw-journey-step${step.done ? " is-done" : ""}${isNext ? " is-next" : ""}`}>
              <span className="uw-journey-mark" aria-hidden="true">
                {step.done ? <CheckCircle2 size={18} /> : index + 1}
              </span>
              <strong>{step.title}</strong>
              <small>{step.detail}</small>
              {!step.done && GO[step.key] && (
                <button type="button" className={isNext ? "ac-primary" : "ac-link"} onClick={() => onGo(step.key)}>
                  {GO[step.key]} <ChevronRight size={14} aria-hidden="true" />
                </button>
              )}
              <span className="ca-sr-only">{step.done ? "Done" : "Not done yet"}</span>
            </li>
          );
        })}
      </ol>
    </Panel>
  );
}
