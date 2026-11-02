import { useEffect } from "react";
import { ArrowLeft, ChevronRight, Clock, FileSpreadsheet, Inbox, LineChart, Scale, X } from "lucide-react";
import { useWorkspace, type WorkspaceSection } from "../workspaceContext";
import { SCENARIOS, markEntranceSeen, onStoryRecord, storyStep, type Scenario, type StoryIds } from "../entrance";
import { useResource } from "../../customer-admin/shared";
import { eventPath, type EventView } from "../oversight";
import { dispositionPath } from "../disposition";
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
        <h2 id="entrance-title">Pick a five-minute story</h2>
        <p className="ac-muted">
          Each story starts on the sample's own record and shows each step; leave it at any time.
        </p>
      </header>
      <ul className="uw-entrance-tiles">
        {/* Your own data is under Help › Try your own data, not on the entrance (0.10.71). */}
        {SCENARIOS.filter((scenario) => scenario.key !== "own").map((scenario) => {
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

/**
 * The story's records as the server knows them (0.10.70): the complaint's id, and the investigation its disposition
 * opened (the flagship) or the one it names (SAMPLE-INV-001). Read again when the screen changes, since the flagship's
 * investigation opens during the story.
 */
function useStoryIds(scenario: Scenario | undefined, section: string): StoryIds {
  const ref = scenario?.record?.complaint ?? null;
  const named = scenario?.record?.investigation;
  const event = useResource<EventView>(ref ? eventPath(ref) : null);
  const complaintId = event.data?.event?.complaint_id ?? null;
  const disposition = useResource<{ current: { investigation_id?: string | null } | null }>(
    complaintId && named === "escalated" ? dispositionPath(complaintId) : null,
  );
  const resolved = useResource<{ investigation_id: string }>(
    named && named !== "escalated"
      ? `/api/v1/workspace/context/resolve?investigation=${encodeURIComponent(named)}`
      : null,
  );
  useEffect(() => {
    if (section === "Investigations" && named === "escalated" && complaintId) disposition.reload();
  }, [section, complaintId]);
  return {
    complaintId: event.data ? complaintId : undefined,
    caseId:
      named === "escalated"
        ? disposition.data
          ? (disposition.data.current?.investigation_id ?? null)
          : undefined
        : resolved.data?.investigation_id,
  };
}

/** The story bar (8.4): which story, which step, and the way back to the entrance; off the story's record, the way
 * back to the story (0.10.70: it kept counting steps on another complaint). */
export function StoryBar({ section, tab }: { section: string; tab?: string }) {
  const { story, startStory, open, work } = useWorkspace();
  const scenario = SCENARIOS.find((item) => item.key === story);
  const ids = useStoryIds(scenario, section);
  if (!scenario || section === "Getting started") return null;
  const place = { section, tab };
  const step = onStoryRecord(scenario, place, ids, work?.investigationId) ? storyStep(scenario, place) : -1;
  return (
    <nav className="uw-story-bar" aria-label="Your story">
      <span className="uw-story-title">{scenario.title}</span>
      <span className="uw-story-step" aria-live="polite">
        {step >= 0
          ? `Step ${step + 1} of ${scenario.steps.length}: ${scenario.steps[step].label}`
          : "Off the story's path"}
      </span>
      <span className="uw-story-actions">
        {step < 0 && (
          <button
            type="button"
            className="ac-link"
            onClick={() => open(scenario.start.section as WorkspaceSection, scenario.start.tab)}
          >
            <ArrowLeft size={14} aria-hidden="true" /> Back to the story
          </button>
        )}
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
