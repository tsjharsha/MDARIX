import { useEffect } from "react";
import { ArrowLeft, ChevronRight, Clock, FileSpreadsheet, Inbox, LineChart, Scale, X } from "lucide-react";
import { useWorkspace, type WorkspaceSection } from "../workspaceContext";
import { SCENARIOS, markEntranceSeen, storyStep, type Scenario } from "../entrance";
import { ReadinessNumbers } from "./MyWork";
import { RestartSamplePanel } from "./RemoveSample";

const ICONS: Record<Scenario["key"], typeof Inbox> = {
  complaint: Inbox,
  rising: LineChart,
  reportable: Scale,
  own: FileSpreadsheet,
};

/**
 * The five-minute entrance (stage 8, 8.4; wow screen 8): three stories on the sample and one on your own export,
 * each with its time; the four inspection-readiness numbers; "Restart the sample story". The ten chapters follow
 * under "Explore all capabilities" (GettingStarted.tsx). Seeing it once makes My work the start screen next time.
 */
export function Entrance({ onRestarted }: { onRestarted: (text: string) => void }) {
  const { open, startStory } = useWorkspace();
  useEffect(markEntranceSeen, []);
  const start = (scenario: Scenario) => {
    startStory?.(scenario.key);
    open(scenario.start.section as WorkspaceSection, scenario.start.tab);
  };
  return (
    <section className="uw-entrance" aria-labelledby="entrance-title">
      <header>
        <p className="ac-eyebrow">Your free trial</p>
        <h2 id="entrance-title">Pick a five-minute story</h2>
        <p className="ac-muted">
          Each story starts on the sample's own record and shows you each step. You can leave it at any time.
        </p>
      </header>
      <ul className="uw-entrance-tiles">
        {SCENARIOS.map((scenario) => {
          const Icon = ICONS[scenario.key];
          return (
            <li key={scenario.key} className={`uw-entrance-tile is-${scenario.key}`}>
              <button type="button" onClick={() => start(scenario)} aria-describedby={`entrance-${scenario.key}`}>
                <Icon size={22} aria-hidden="true" />
                <strong>{scenario.title}</strong>
                <span id={`entrance-${scenario.key}`} className="uw-entrance-lede">
                  {scenario.lede}
                </span>
                <span className="uw-entrance-time">
                  <Clock size={14} aria-hidden="true" /> About {scenario.minutes} minutes
                  {scenario.key === "own" ? " · optional" : ` · ${scenario.steps.length} steps`}
                </span>
                <span className="uw-entrance-go">
                  {scenario.key === "own" ? "Upload your export" : "Start"}{" "}
                  <ChevronRight size={15} aria-hidden="true" />
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      <section aria-label="Inspection readiness" className="uw-entrance-numbers">
        <h3>Inspection readiness on the sample</h3>
        <div className="uw-team-numbers">
          <ReadinessNumbers />
        </div>
      </section>
      <RestartSamplePanel onRestarted={onRestarted} />
    </section>
  );
}

/** The story bar (8.4): which story, which step, and the way back to the entrance. */
export function StoryBar({ section, tab }: { section: string; tab?: string }) {
  const { story, startStory, open } = useWorkspace();
  const scenario = SCENARIOS.find((item) => item.key === story);
  if (!scenario || section === "Getting started") return null;
  const step = storyStep(scenario, { section, tab });
  return (
    <nav className="uw-story-bar" aria-label="Your story">
      <span className="uw-story-title">{scenario.title}</span>
      <span className="uw-story-step" aria-live="polite">
        {step >= 0
          ? `Step ${step + 1} of ${scenario.steps.length}: ${scenario.steps[step].label}`
          : "Off the story's path: its next step is on the record's page"}
      </span>
      <span className="uw-story-actions">
        <button type="button" className="ac-link" onClick={() => open("Getting started")}>
          <ArrowLeft size={14} aria-hidden="true" /> Back to the stories
        </button>
        <button type="button" className="ac-link" onClick={() => startStory?.(null)} aria-label="End this story">
          <X size={14} aria-hidden="true" /> End
        </button>
      </span>
    </nav>
  );
}
