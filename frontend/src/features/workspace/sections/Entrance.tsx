import { useEffect } from "react";
import { ArrowLeft, ChevronRight, Inbox, LineChart, Scale, X } from "lucide-react";
import { useWorkspace, type WorkspaceSection } from "../workspaceContext";
import {
  FLAGSHIP,
  MORE_STORIES,
  SCENARIOS,
  SHORT,
  markEntranceSeen,
  onStoryRecord,
  storyStep,
  type Scenario,
  type StoryIds,
} from "../entrance";
import { useResource } from "../../customer-admin/shared";
import { eventPath, type EventView } from "../oversight";
import { dispositionPath } from "../disposition";
import { RestartSamplePanel } from "./RemoveSample";
import { ResumeShortStory, useShortStory } from "./ShortStory";
import { stepText } from "../shortStory";

const ICONS: Partial<Record<Scenario["key"], typeof Inbox>> = {
  complaint: Inbox,
  rising: LineChart,
  reportable: Scale,
};

/**
 * The entrance (stage 8, 8.4; 0.10.71, A3): one event first, the short story on SAMPLE-RV-11, in the reporter's own
 * words as the sample records them; the other stories under "More stories"; "Restart the sample story" under "More".
 * Step counts only, no time claims. The inspection-readiness numbers are on the manager's My work, not here. The ten
 * chapters follow under "Explore all capabilities" (GettingStarted.tsx). Seeing it once makes My work the start
 * screen next time.
 */
export function Entrance({ onRestarted }: { onRestarted: (text: string) => void }) {
  const { open, startStory } = useWorkspace();
  useEffect(markEntranceSeen, []);
  const event = useResource<EventView>(eventPath(FLAGSHIP));
  const start = (scenario: Scenario) => {
    startStory?.(scenario.key);
    open(scenario.start.section as WorkspaceSection, scenario.start.tab);
  };
  const words = event.data?.event.description;
  return (
    <section className="uw-entrance" aria-labelledby="entrance-title">
      {/* Unfinished short-story work comes first (0.10.71, A3). */}
      <ResumeShortStory />
      {event.state === "error" ? (
        <header>
          <h2 id="entrance-title">Your trial</h2>
          <p className="ac-muted">The sample event is not in this workspace. Explore all capabilities below.</p>
        </header>
      ) : (
        <article className="uw-entrance-event" aria-describedby="entrance-words">
          <p className="ac-eyebrow">
            Sample event · {FLAGSHIP} · {SHORT.steps.length} steps
          </p>
          <h2 id="entrance-title">{SHORT.title}</h2>
          <blockquote id="entrance-words" className="uw-entrance-words">
            {words ? `“${words}”` : "Reading the sample event…"}
          </blockquote>
          <div className="ca-action-row">
            <button type="button" className="ac-primary" onClick={() => start(SHORT)} disabled={!words}>
              Review this sample event <ChevronRight size={15} aria-hidden="true" />
            </button>
          </div>
          <p className="uw-entrance-tag">Fictional manufacturer · Sample data only</p>
        </article>
      )}
      <details className="uw-entrance-more">
        <summary>More stories</summary>
        <ul className="uw-entrance-tiles">
          {MORE_STORIES.map((scenario) => {
            const Icon = ICONS[scenario.key] ?? Inbox;
            return (
              <li key={scenario.key} className={`uw-entrance-tile is-${scenario.key}`}>
                <button type="button" onClick={() => start(scenario)} aria-describedby={`entrance-${scenario.key}`}>
                  <Icon size={22} aria-hidden="true" />
                  <strong>{scenario.title}</strong>
                  <span id={`entrance-${scenario.key}`} className="uw-entrance-lede">
                    {scenario.lede}
                  </span>
                  <span className="uw-entrance-time">{scenario.steps.length} steps</span>
                  <span className="uw-entrance-go">
                    Start <ChevronRight size={15} aria-hidden="true" />
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </details>
      <details className="uw-entrance-more">
        <summary>More</summary>
        <RestartSamplePanel onRestarted={onRestarted} />
      </details>
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
 * back to the story (0.10.70: it kept counting steps on another complaint). The short story's step is what was saved
 * on SAMPLE-RV-11 (0.10.71, A4), never the screen on show. */
export function StoryBar({ section, tab }: { section: string; tab?: string }) {
  const { story, startStory, open, work } = useWorkspace();
  const scenario = SCENARIOS.find((item) => item.key === story);
  const ids = useStoryIds(scenario, section);
  // The short story and the full evaluation of SAMPLE-RV-11 count their steps from saved records (0.10.71, 0.10.72).
  const short = useShortStory(scenario?.key === "short" || scenario?.key === "reportable");
  if (!scenario || section === "Getting started") return null;
  const place = { section, tab };
  const onRecord = onStoryRecord(scenario, place, ids, work?.investigationId);
  const isShort = scenario.key === "short";
  const step = isShort
    ? onRecord && section === "Complaint"
      ? (short.data?.current ?? 0)
      : -1
    : onRecord
      ? scenario.key === "reportable" && short.data?.full_evaluation
        ? Math.min(short.data.full_evaluation.current, scenario.steps.length - 1)
        : storyStep(scenario, place)
      : -1;
  const back = () => open(scenario.start.section as WorkspaceSection, scenario.start.tab);
  return (
    <nav className="uw-story-bar" aria-label="Your story">
      <span className="uw-story-title">{scenario.title}</span>
      <span className="uw-story-step" aria-live="polite">
        {step < 0
          ? "Off the story's path"
          : isShort
            ? short.data
              ? stepText(short.data)
              : "Reading your progress…"
            : `Step ${step + 1} of ${scenario.steps.length}: ${scenario.steps[step].label}`}
      </span>
      <span className="uw-story-actions">
        {step < 0 && (
          <button type="button" className="ac-link" onClick={back}>
            <ArrowLeft size={14} aria-hidden="true" /> {isShort ? `Resume ${FLAGSHIP}` : "Back to the story"}
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
