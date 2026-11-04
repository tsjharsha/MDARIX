import { useEffect, useState } from "react";
import { BookOpen, ChevronRight, Compass, Settings2, ShieldCheck, Upload, Users } from "lucide-react";
import { Panel, StatTile } from "../../admin/console/charts";
import { useSiteInfo } from "../../../site/legal";
import { TRIAL_GUIDE_PATH, USER_GUIDE_PATH } from "../../help/paths";
import { NEXT_STEPS_LINK } from "../../help/trialNextSteps";
import { formatDay } from "../../../app/dates";
import { BookDemo } from "./BookDemo";
import { EndTrialPanel } from "./EndTrial";
import { RemoveSamplePanel, RestartSamplePanel } from "./RemoveSample";
import { SampleDataPanel } from "./SampleData";
import type { StoryChapter } from "../trialStory";
import type { TrialStatus } from "./GettingStarted";

/** Getting started's library of other workflows, opened by "Choose a focus" (its address: ?tab=Other+workflows). */
export const OTHER_WORKFLOWS = "Other workflows";
/** The collapsed section's anchor: links to the sample data or the trial's dates open it here. */
export const TRIAL_SETTINGS_ID = "trial-settings";

/**
 * "Explore at your own pace" (owner's specification, 5 Nov 2026): three compact cards under the walkthrough. A, the
 * team (inviting is the trial owner's; anyone else sees who is on it); B, the library of other workflows; C, the
 * guides, support, feedback, the demo and the trial-to-pilot page, shown when asked for, none of them a main button.
 */
export function ExploreCards({
  owner,
  onTeam,
  onWorkflows,
  onFeedback,
  onNextSteps,
  chapters,
  onDemoBooked,
}: {
  owner: boolean;
  onTeam: () => void;
  onWorkflows: () => void;
  onFeedback: () => void;
  onNextSteps: () => void;
  chapters: readonly StoryChapter[];
  onDemoBooked?: () => void;
}) {
  const [resources, setResources] = useState(false);
  const info = useSiteInfo();
  const support = info?.support_email;
  return (
    <section className="uw-gs-explore" aria-labelledby="gs-explore-title">
      <h2 id="gs-explore-title">Explore at your own pace</h2>
      <div className="uw-gs-cards">
        <article className="uw-gs-card">
          <Users size={20} aria-hidden="true" />
          <h3>Invite your team</h3>
          <p>
            {owner
              ? "Try review and approval with colleagues."
              : "See who is on your trial. The trial owner invites and manages colleagues."}
          </p>
          <button type="button" className="ac-secondary" onClick={onTeam}>
            {owner ? "Manage team" : "View team"} <ChevronRight size={15} aria-hidden="true" />
          </button>
        </article>
        <article className="uw-gs-card">
          <Compass size={20} aria-hidden="true" />
          <h3>Explore other workflows</h3>
          <p>Routine complaints, trends, CAPA and more.</p>
          <button type="button" className="ac-secondary" onClick={onWorkflows}>
            Choose a focus <ChevronRight size={15} aria-hidden="true" />
          </button>
        </article>
        <article className="uw-gs-card">
          <BookOpen size={20} aria-hidden="true" />
          <h3>Guides &amp; support</h3>
          <p>Get help or plan your next steps.</p>
          <button
            type="button"
            className="ac-secondary"
            aria-expanded={resources}
            aria-controls={resources ? "gs-resources" : undefined}
            onClick={() => setResources((value) => !value)}
          >
            {resources ? "Hide resources" : "Open resources"}
          </button>
          {resources && (
            <GuideLinks
              support={support}
              onFeedback={onFeedback}
              onNextSteps={onNextSteps}
              chapters={chapters}
              onDemoBooked={onDemoBooked}
            />
          )}
        </article>
      </div>
    </section>
  );
}

/** Card C's destinations, as quiet links (exported for its test): the guides, support, feedback, the trial-to-pilot
 * page and the one-to-one demo (its own form, as before). */
export function GuideLinks({
  support,
  onFeedback,
  onNextSteps,
  chapters,
  onDemoBooked,
}: {
  support?: string | null;
  onFeedback: () => void;
  onNextSteps: () => void;
  chapters: readonly StoryChapter[];
  onDemoBooked?: () => void;
}) {
  return (
    <ul id="gs-resources" className="uw-gs-resources">
      <li>
        <a href={TRIAL_GUIDE_PATH} target="_blank" rel="noopener">
          Free trial user guide
        </a>
      </li>
      <li>
        <a href={`${USER_GUIDE_PATH}?navigation=new`} target="_blank" rel="noopener">
          Step-by-step user guide
        </a>
      </li>
      <li>
        <a href={support ? `mailto:${support}` : "/contact"} target={support ? undefined : "_blank"} rel="noopener">
          Help and support{support ? ` (${support})` : ""}
        </a>
      </li>
      <li>
        <button type="button" className="ac-link" onClick={onFeedback}>
          Share feedback
        </button>
      </li>
      <li>
        <button type="button" className="ac-link" onClick={onNextSteps}>
          {NEXT_STEPS_LINK}
        </button>
      </li>
      <li className="uw-gs-demo">
        <BookDemo chapters={chapters} onBooked={onDemoBooked} />
      </li>
    </ul>
  );
}

/**
 * "Sample data & trial settings": one collapsed section at the foot of Getting started, the only place on it for the
 * sample's explanation and counts, the trial's dates and limits, and the trial owner's restart, removal and early end
 * (each with its own confirmation, unchanged). Nothing in it runs by itself. `startOpen`: a link named it.
 */
export function TrialSettings({
  trial,
  startOpen,
  allowed,
  onOpen,
  onRestarted,
  onRemoved,
  onNextSteps,
}: {
  trial: TrialStatus | null;
  startOpen: boolean;
  allowed: (section: string) => boolean;
  onOpen: (opens: { section: string; tab?: string }) => void;
  onRestarted: (text: string) => void;
  onRemoved: (text: string) => void;
  onNextSteps: () => void;
}) {
  const [shown, setShown] = useState(startOpen);
  useEffect(() => {
    if (!startOpen) return;
    setShown(true);
    const timer = window.setTimeout(
      () => document.getElementById(TRIAL_SETTINGS_ID)?.scrollIntoView?.({ block: "start" }),
      0,
    );
    return () => window.clearTimeout(timer);
  }, [startOpen]);
  const hasSample = (trial?.sample?.products ?? 0) > 0;
  return (
    <details
      id={TRIAL_SETTINGS_ID}
      className="uw-gs-settings uw-anchor"
      open={shown}
      onToggle={(event) => setShown(event.currentTarget.open)}
    >
      <summary>
        <Settings2 size={16} aria-hidden="true" /> Sample data &amp; trial settings
      </summary>
      {shown && (
        <div className="uw-gs-settings-body">
          {hasSample ? (
            <SampleDataPanel counts={trial?.sample} allowed={allowed} onOpen={onOpen} />
          ) : (
            trial && (
              <Panel eyebrow="Sample data" title="The sample data is not in this trial">
                <p className="uw-trial-note">Every screen shows only your own records.</p>
              </Panel>
            )
          )}
          <Panel title="Your free trial" eyebrow="Dates and limits">
            <div className="uw-trial-stats">
              <StatTile
                label="Trial ends"
                value={trial?.expires_at ? formatDay(trial.expires_at) : null}
                detail={
                  trial?.data_deleted_at
                    ? `Data is deleted on ${formatDay(trial.data_deleted_at)} unless you continue`
                    : "Your data stays if you continue"
                }
                icon={<ShieldCheck size={18} />}
              />
              <StatTile
                label="Users"
                value={trial?.usage ? `${trial.usage.users} of ${trial.limits?.users}` : null}
                detail={trial?.is_owner ? "Invite or remove colleagues under Team" : "Your trial team"}
                icon={<Users size={18} />}
              />
              <StatTile
                label="Uploaded rows"
                value={
                  trial?.usage ? `${trial.usage.rows.toLocaleString()} of ${trial.limits?.rows.toLocaleString()}` : null
                }
                detail="One row in your file is one row; the sample data does not count"
                icon={<Upload size={18} />}
              />
            </div>
          </Panel>
          {hasSample && !trial?.is_owner && (
            <p className="ac-muted">Only the person who started the trial can restart or remove the sample data.</p>
          )}
          {hasSample && <RestartSamplePanel onRestarted={onRestarted} />}
          {hasSample && <RemoveSamplePanel onRemoved={onRemoved} />}
          <EndTrialPanel onNextSteps={onNextSteps} />
        </div>
      )}
    </details>
  );
}
